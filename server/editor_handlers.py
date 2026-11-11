"""
LUKB Investment Office — Editor-, Autosave- & Kollaborations-Handler.
Behandelt Asset-Uploads, Live-Fokus / Cursor-Presence, Debounced Autosave und 3-Wege-Block-Merge.
"""

from __future__ import annotations

import base64
import logging
from shiny import Inputs, Outputs, Session, reactive, ui

from database.repository import save_article, save_asset
from schemas.article import ArticleDocument
from server.collab import (
    broadcast_article_sync,
    broadcast_presence,
    broadcast_preview_to_coauthors,
    collect_article_assets_map,
    get_peer_user,
    is_peer_auto_preview,
    set_peer_auto_preview,
    set_peer_focus,
)
from server.state import SessionState

logger = logging.getLogger("lukb_cms.editor_handlers")


def register_editor_handlers(
    input: Inputs,
    output: Outputs,
    session: Session,
    state: SessionState,
) -> None:
    """Registriert alle Autosave-, Block- und Asset-Events an der Session."""

    # Upload einer Grafikdatei (SVG, PNG, JPG) in die MSSQL-Datenbank
    @reactive.effect
    @reactive.event(input.lukb_upload_asset)
    async def _on_upload_asset() -> None:
        payload = input.lukb_upload_asset()
        if not isinstance(payload, dict):
            return
        b64_str = payload.get("base64_data", "")
        if not b64_str:
            return
        raw_bytes = base64.b64decode(b64_str)
        save_asset(
            filename=payload.get("filename", "grafik.svg"),
            mime_type=payload.get("mime_type", "image/svg+xml"),
            data=raw_bytes,
            article_id=payload.get("article_id"),
            asset_id=payload.get("asset_id"),
        )
        doc = state.current_doc.get()
        if doc is not None:
            auto_preview = is_peer_auto_preview(state.session_id, default=True)
            await state.send_preview(doc, include_typst=auto_preview)

    # Live-Fokus-Meldung eines Autors (welcher Block / welches Feld wird gerade editiert?)
    @reactive.effect
    @reactive.event(input.lukb_collab_focus)
    async def _on_collab_focus() -> None:
        payload = input.lukb_collab_focus()
        if not isinstance(payload, dict):
            return
        target = str(payload.get("target", ""))
        custom_name = str(payload.get("user_name", "")).strip()
        aid = set_peer_focus(state.session_id, target, user=custom_name or None)
        if aid:
            await broadcast_presence(aid)

    # Debounced Autosave & Manuelles Speichern (inkl. 3-Wege-Block-Merge & Live-Broadcast)
    @reactive.effect
    @reactive.event(input.lukb_autosave_payload)
    async def _on_autosave() -> None:
        payload = input.lukb_autosave_payload()
        if not isinstance(payload, dict) or "article" not in payload:
            return
        try:
            doc = ArticleDocument.model_validate(payload["article"])
            base_doc = None
            if payload.get("base_article"):
                try:
                    base_doc = ArticleDocument.model_validate(payload["base_article"])
                except Exception:
                    base_doc = None

            user_label = get_peer_user(state.session_id, fallback=state.current_user)
            save_info = save_article(
                doc=doc,
                user=user_label,
                create_revision=bool(payload.get("create_revision", False)),
                revision_note=str(payload.get("revision_note", "")),
                base_doc=base_doc,
            )
            merged_doc = ArticleDocument.model_validate(save_info["article"])
            state.current_article_id.set(merged_doc.id)
            state.current_doc.set(merged_doc)

            save_info["assets"] = collect_article_assets_map(merged_doc)
            await session.send_custom_message("lukb_autosave_ack", save_info)
            await state.send_article_list(merged_doc.id)

            auto_preview = bool(payload.get("auto_preview", is_peer_auto_preview(state.session_id, default=True)))
            set_peer_auto_preview(state.session_id, auto_preview)
            await state.send_preview(merged_doc, include_typst=auto_preview)

            # Synchronisiere alle Co-Autoren (und bei erfolgtem DB-Merge auch den Sender selbst)
            await broadcast_article_sync(
                article_id=merged_doc.id,
                doc=merged_doc,
                sender_session_id=state.session_id,
                author_name=user_label,
                include_sender=bool(save_info.get("merged", False)),
            )
            # Aktualisiere auch die Live-Vorschau bei allen Co-Autoren im selben Artikel
            await broadcast_preview_to_coauthors(state.session_id, merged_doc)
        except Exception as exc:
            logger.exception("Fehler beim Speichern des Artikels")
            ui.notification_show(f"Speicherfehler: {exc}", type="error")
