"""
LUKB Investment Office — Session State & Dispatcher.
Kapselt den reaktiven Session-Zustand und WebSocket-Meldungen an das Frontend.
"""

from __future__ import annotations

import logging
from typing import Any
from shiny import Inputs, Session, reactive

from database.repository import create_new_article, get_article, list_articles, list_available_tickers
from schemas.article import ArticleDocument
from server.collab import (
    broadcast_presence,
    cleanup_peer,
    collect_article_assets_map,
    get_peer_color,
    register_peer,
    set_peer_article,
)
from services.renderer import render_preview_svg_pages, render_web_html

logger = logging.getLogger("lukb_cms.state")


class SessionState:
    """Repräsentiert den reaktiven Zustand einer einzelnen Benutzer-Sitzung."""

    def __init__(self, session: Session, input_ref: Inputs):
        self.session = session
        self.input = input_ref
        self.session_id = getattr(session, "id", f"sess_{id(session)}")
        self.peer_color = get_peer_color(self.session_id)
        self.current_article_id: reactive.Value[str] = reactive.Value("")
        self.current_doc: reactive.Value[ArticleDocument | None] = reactive.Value(None)

        # Peer in Registry anmelden
        register_peer(
            session_id=self.session_id,
            session=session,
            user=self.current_user,
            color=self.peer_color,
            sync_doc_cb=self._update_local_doc_from_peer,
        )

        session.on_ended(self._on_session_ended)

    @property
    def current_user(self) -> str:
        """Gibt den auf Posit Connect authentifizierten Benutzer oder einen Fallback-Namen zurück."""
        user_name = getattr(self.session, "user", None)
        if user_name:
            return str(user_name)
        return f"Analyst ({self.session_id[:4]})"

    def _update_local_doc_from_peer(self, new_doc: ArticleDocument) -> None:
        self.current_doc.set(new_doc)

    def _on_session_ended(self) -> None:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cleanup_peer(self.session_id))
        except Exception:
            pass

    async def send_article_list(self, active_id: str) -> None:
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

        items = list_articles(search_query=search_q, status_filter=status_f)
        all_items = (
            items
            if (not search_q.strip() and status_f == "all")
            else list_articles(search_query="", status_filter="all")
        )
        await self.session.send_custom_message(
            "lukb_update_article_list",
            {
                "articles": items,
                "all_articles": all_items,
                "active_id": active_id,
                "sidebar_search_active": bool(search_q.strip()),
                "sidebar_status_filter": status_f,
            },
        )

    async def send_preview(
        self,
        doc: ArticleDocument | None = None,
        include_typst: bool = True,
    ) -> tuple[list[str] | None, str | None]:
        """Rendert die SVG- und HTML-Vorschau, sendet sie an den Client und gibt (svg_pages, web_html) zurück."""
        if doc is None:
            doc = self.current_doc.get()
        if doc is None:
            return None, None

        svg_pages: list[str] | None = None
        if include_typst:
            try:
                svg_pages = render_preview_svg_pages(doc)
            except Exception as exc:
                logger.exception("Typst Preview-Fehler")
                err_svg = (
                    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 200">'
                    f'<rect width="600" height="200" fill="#FEF2F2"/>'
                    f'<text x="24" y="50" fill="#B91C1C" font-size="14">'
                    f"Typst Vorschau-Hinweis: {str(exc)[:90]}</text></svg>"
                )
                svg_pages = [err_svg]

        try:
            web_html = render_web_html(doc)
        except Exception as exc:
            logger.exception("Web HTML Preview-Fehler")
            web_html = f"<pre>Fehler beim HTML-Rendering: {exc}</pre>"

        await self.session.send_custom_message(
            "lukb_update_preview",
            {
                "svg_pages": svg_pages,
                "web_html": web_html,
                "typst_skipped": not include_typst,
            },
        )
        return svg_pages, web_html

    async def load_and_broadcast_article(self, article_id: str) -> None:
        """Lädt einen Artikel, setzt den Session-Zustand und informiert andere Co-Autoren."""
        doc = get_article(article_id)
        if doc is None:
            all_items = list_articles()
            if all_items:
                doc = get_article(all_items[0]["id"])
            else:
                doc = create_new_article(user=self.current_user)

        if doc is None:
            return

        prev_article_id = set_peer_article(self.session_id, doc.id)
        self.current_article_id.set(doc.id)
        self.current_doc.set(doc)

        assets_map = collect_article_assets_map(doc)
        await self.session.send_custom_message(
            "lukb_load_article",
            {
                "article": doc.model_dump(),
                "assets": assets_map,
                "available_tickers": list_available_tickers(limit=25),
                "self_session_id": self.session_id,
            },
        )
        await self.send_article_list(doc.id)
        await self.send_preview(doc)
        if prev_article_id and prev_article_id != doc.id:
            await broadcast_presence(prev_article_id)
        await broadcast_presence(doc.id)
