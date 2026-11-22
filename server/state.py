"""
LUKB Investment Office — Session State & Dispatcher.
Kapselt den reaktiven Session-Zustand und WebSocket-Meldungen an das Frontend.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from shiny import Inputs, Session, reactive, ui

from config import LOCAL_DEV_USER, is_connect_environment, is_technical_session_user, normalize_user_id
from database.permissions import check_article_permission
from database.repository import (
    create_new_article,
    get_article,
    get_first_article_id,
    get_published_sync_status,
    list_articles,
    list_available_tickers,
)
from schemas.article import ArticleDocument
from server.collab import (
    broadcast_global_presence,
    broadcast_presence,
    cleanup_peer,
    collect_article_assets_map,
    filter_presence_by_allowed_articles,
    get_active_articles_presence,
    get_peer_color,
    get_peer_preview_mode,
    is_peer_auto_preview,
    register_peer,
    set_peer_article,
)
from services.renderer import render_preview_pdf_base64, render_web_html

logger = logging.getLogger("lukb_cms.state")

# Prozessweite Begrenzung gleichzeitiger Renderaufträge (zusätzlich zum Typst-Lock)
_PROCESS_RENDER_SEMAPHORE = asyncio.Semaphore(2)


class SessionState:
    """Repräsentiert den reaktiven Zustand einer einzelnen Benutzer-Sitzung."""

    def __init__(self, session: Session, input_ref: Inputs):
        self.session = session
        self.input = input_ref
        self.session_id = getattr(session, "id", f"sess_{id(session)}")
        self.peer_color = get_peer_color(self.session_id)
        self.current_article_id: reactive.Value[str] = reactive.Value("")
        self.current_doc: reactive.Value[ArticleDocument | None] = reactive.Value(None)
        self._active_article_id_plain: str = ""
        self._preview_running: bool = False
        self._preview_pending_job: dict[str, Any] | None = None
        self._preview_job_seq: int = 0
        self._preview_worker_task: asyncio.Task | None = None

        # Peer in Registry anmelden
        register_peer(
            session_id=self.session_id,
            session=session,
            user=self.current_user,
            color=self.peer_color,
            sync_doc_cb=self._update_local_doc_from_peer,
            revoke_cb=self._revoke_article_from_session,
        )

        session.on_ended(self._on_session_ended)

    @property
    def current_user(self) -> str:
        """Gibt den auf Posit Connect authentifizierten Benutzer oder im lokalen Dev-Modus `LOCAL_DEV_USER` zurück."""
        user_name = getattr(self.session, "user", None)
        if user_name:
            return str(user_name)
        if not is_connect_environment():
            return LOCAL_DEV_USER
        return f"Analyst ({self.session_id[:4]})"

    @property
    def current_user_id(self) -> str:
        """Normalisierte Benutzerkennung (lowercase)."""
        return normalize_user_id(self.current_user)

    @property
    def is_authenticated(self) -> bool:
        """True nur bei einer echten, nicht-technischen Benutzeridentität."""
        return not is_technical_session_user(self.current_user)

    def can_access_article(
        self,
        article_id: str,
        action: str = "read",
        *,
        allow_admin_override: bool = False,
    ) -> bool:
        """Zentrale Berechtigungsprüfung für diese Session."""
        return check_article_permission(
            article_id,
            self.current_user_id,
            action,
            allow_admin_override=allow_admin_override,
        )

    def _revoke_article_from_session(self, revoked_article_id: str) -> None:
        if self._active_article_id_plain == revoked_article_id:
            self._active_article_id_plain = ""
            self.current_article_id.set("")
            self.current_doc.set(None)

    def _update_local_doc_from_peer(self, new_doc: ArticleDocument) -> None:
        self.current_doc.set(new_doc)

    def _on_session_ended(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cleanup_peer(self.session_id))
        except Exception:
            pass

    async def send_article_list(self, active_id: str, include_all: bool = True) -> None:
        """Sendet die gefilterte Liste aller Artikel an die Sidebar und das Modal."""
        search_q = ""
        status_f = "all"
        try:
            search_q = self.input.sidebar_search_query() or ""
        except Exception:
            pass
        try:
            status_f = self.input.sidebar_status_val() or "all"
        except Exception:
            pass

        uid = self.current_user_id

        def _fetch_lists():
            filtered = list_articles(search_query=search_q, status_filter=status_f, user_id=uid)
            if not search_q.strip() and status_f == "all":
                all_res = filtered
            elif include_all:
                all_res = list_articles(search_query="", status_filter="all", user_id=uid)
            else:
                all_res = None
            return filtered, all_res

        items, all_items = await asyncio.to_thread(_fetch_lists)
        allowed_ids = {it["id"] for it in (all_items if all_items is not None else items) if it.get("id")}
        filtered_presence = filter_presence_by_allowed_articles(get_active_articles_presence(), allowed_ids)
        await self.session.send_custom_message(
            "lukb_update_article_list",
            {
                "articles": items,
                "all_articles": all_items,
                "active_id": active_id,
                "self_session_id": self.session_id,
                "active_peers_by_article": filtered_presence,
                "sidebar_search_active": bool(search_q.strip()),
                "sidebar_status_filter": status_f,
            },
        )

    async def send_preview(
        self,
        doc: ArticleDocument | None = None,
        include_typst: bool = True,
        include_web: bool = False,
        *,
        client_edit_seq: int | None = None,
        preview_mode: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Rendert die PDF- (PDF.js) und/oder HTML-Vorschau unter Prozess-Semaphore, verwirft überholte Ergebnisse."""
        if doc is None:
            doc = self.current_doc.get()
        if doc is None:
            return None, None

        target_article_id = doc.id
        resolved_mode = (preview_mode or ("pdf" if include_typst else "web")).strip().lower()

        pdf_base64: str | None = None
        preview_error: str | None = None
        web_html: str | None = None

        async with _PROCESS_RENDER_SEMAPHORE:
            if include_typst:
                try:
                    pdf_base64 = await asyncio.to_thread(render_preview_pdf_base64, doc)
                except Exception as exc:
                    logger.exception("Typst Preview-Fehler")
                    preview_error = f"Typst Vorschau-Hinweis: {str(exc)[:180]}"

            if include_web:
                try:
                    web_html = await asyncio.to_thread(render_web_html, doc)
                except Exception as exc:
                    logger.exception("Web HTML Preview-Fehler")
                    web_html = f"<pre>Fehler beim HTML-Rendering: {exc}</pre>"

        # Überholte Ergebnisse verwerfen, falls Benutzer inzwischen Artikel gewechselt hat
        active_aid = self._active_article_id_plain
        if active_aid and active_aid != target_article_id:
            return None, None

        await self.session.send_custom_message(
            "lukb_update_preview",
            {
                "article_id": target_article_id,
                "preview_mode": resolved_mode,
                "client_edit_seq": client_edit_seq,
                "pdf_base64": pdf_base64,
                "web_html": web_html,
                "typst_skipped": not include_typst,
                "web_skipped": not include_web,
                "error": preview_error,
            },
        )
        return pdf_base64, web_html

    async def _run_preview_worker(self) -> None:
        """Arbeitet pro Session höchstens 1 laufenden und 1 wartenden ('latest wins') Vorschauauftrag ab."""
        try:
            while self._preview_pending_job is not None:
                job = self._preview_pending_job
                self._preview_pending_job = None
                job_seq = job["job_seq"]
                doc = job["doc"]
                mode = job["mode"]
                client_edit_seq = job.get("client_edit_seq")

                # Überholten Auftrag überspringen, bevor Typst gestartet wird
                active_aid = self._active_article_id_plain
                if active_aid and active_aid != doc.id:
                    continue

                await self.send_preview(
                    doc,
                    include_typst=(mode == "pdf"),
                    include_web=(mode == "web"),
                    client_edit_seq=client_edit_seq,
                    preview_mode=mode,
                )
        finally:
            self._preview_running = False

    def enqueue_preview(
        self,
        doc: ArticleDocument | None = None,
        *,
        preview_mode: str | None = None,
        client_edit_seq: int | None = None,
    ) -> int:
        """
        Reiht einen Vorschauauftrag ein (Max 1 laufend + Max 1 wartend, jeweils jüngste Fassung).
        Gibt die zugewiesene Job-Sequenznummer zurück.
        """
        target_doc = doc or self.current_doc.get()
        if target_doc is None:
            return 0
        mode = (preview_mode or get_peer_preview_mode(self.session_id, default="pdf")).strip().lower()
        self._preview_job_seq += 1
        seq = self._preview_job_seq
        self._preview_pending_job = {
            "job_seq": seq,
            "doc": target_doc,
            "mode": mode,
            "client_edit_seq": client_edit_seq,
        }
        if not self._preview_running:
            self._preview_running = True
            try:
                loop = asyncio.get_running_loop()
                self._preview_worker_task = loop.create_task(self._run_preview_worker())
            except RuntimeError:
                self._preview_running = False
        return seq

    async def send_active_preview(
        self,
        doc: ArticleDocument | None = None,
        *,
        respect_auto_preview: bool = True,
        preview_mode: str | None = None,
        client_edit_seq: int | None = None,
    ) -> tuple[str | None, str | None]:
        """Sendet die Vorschau entsprechend dem aktiven Preview-Modus und Auto-Preview-Status der Session."""
        target_doc = doc or self.current_doc.get()
        if target_doc is None:
            return None, None
        mode = (preview_mode or get_peer_preview_mode(self.session_id, default="pdf")).strip().lower()
        if respect_auto_preview and not is_peer_auto_preview(self.session_id, default=True):
            if mode == "pdf":
                await self.session.send_custom_message(
                    "lukb_update_preview",
                    {
                        "article_id": target_doc.id,
                        "preview_mode": mode,
                        "client_edit_seq": client_edit_seq,
                        "pdf_base64": None,
                        "web_html": None,
                        "typst_skipped": True,
                        "web_skipped": True,
                    },
                )
                return None, None
        return await self.send_preview(
            target_doc,
            include_typst=(mode == "pdf"),
            include_web=(mode == "web"),
            client_edit_seq=client_edit_seq,
            preview_mode=mode,
        )

    async def load_and_broadcast_article(self, article_id: str) -> None:
        """Lädt einen berechtigten Artikel, setzt den Session-Zustand und informiert Co-Autoren."""
        uid = self.current_user_id

        if article_id:
            has_access = await asyncio.to_thread(check_article_permission, article_id, uid, "read")
            if not has_access:
                ui.notification_show(
                    "Kein Zugriff auf diesen Artikel.",
                    type="warning",
                    duration=5,
                )
                return

        def _load_doc_and_assets():
            loaded_doc = get_article(article_id) if article_id else None
            if loaded_doc is None:
                first_id = get_first_article_id(user_id=uid)
                if first_id:
                    loaded_doc = get_article(first_id)
            if loaded_doc is None:
                return None, {}, [], None
            a_map = collect_article_assets_map(loaded_doc)
            tickers = list_available_tickers(limit=25)
            pub_sync = get_published_sync_status(loaded_doc.id)
            return loaded_doc, a_map, tickers, pub_sync

        doc, assets_map, available_tickers, publish_sync = await asyncio.to_thread(_load_doc_and_assets)
        if doc is None:
            set_peer_article(self.session_id, "")
            self._active_article_id_plain = ""
            self.current_article_id.set("")
            self.current_doc.set(None)
            await self.send_article_list("")
            await self.session.send_custom_message(
                "lukb_no_article_access",
                {
                    "authenticated": self.is_authenticated,
                    "user": self.current_user,
                },
            )
            return

        prev_article_id = set_peer_article(self.session_id, doc.id)
        self._active_article_id_plain = doc.id
        self.current_article_id.set(doc.id)
        self.current_doc.set(doc)

        await self.session.send_custom_message(
            "lukb_load_article",
            {
                "article": doc.model_dump(),
                "assets": assets_map,
                "available_tickers": available_tickers,
                "self_session_id": self.session_id,
                "publish_sync": publish_sync,
            },
        )
        await self.send_article_list(doc.id)
        await self.send_active_preview(doc, respect_auto_preview=True)
        if prev_article_id and prev_article_id != doc.id:
            await broadcast_presence(prev_article_id)
        await broadcast_presence(doc.id)
        await broadcast_global_presence()
