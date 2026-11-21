"""
LUKB Investment Office — Editor-, Autosave- & Kollaborations-Handler.
Behandelt Asset-Uploads, Live-Fokus / Cursor-Presence, Debounced Autosave und 3-Wege-Block-Merge.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from shiny import Inputs, Outputs, Session, reactive, ui

from database.repository import (
    get_published_sync_status,
    list_article_revisions,
    restore_article_revision,
    save_article,
    save_asset,
)
from schemas.article import ArticleDocument
from server.collab import (
    broadcast_article_list_to_all,
    broadcast_article_sync,
    broadcast_presence,
    broadcast_preview_to_coauthors,
    collect_article_assets_map,
    get_peer_preview_mode,
    is_peer_auto_preview,
    set_peer_auto_preview,
    set_peer_focus,
    set_peer_preview_mode,
    transfer_block_lock,
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
        await asyncio.to_thread(
            save_asset,
            filename=payload.get("filename", "grafik.svg"),
            mime_type=payload.get("mime_type", "image/svg+xml"),
            data=raw_bytes,
            article_id=payload.get("article_id"),
            asset_id=payload.get("asset_id"),
        )
        await state.send_active_preview(respect_auto_preview=True)

    # Live-Fokus-Meldung eines Autors (welcher Block / welches Feld wird gerade editiert?)
    @reactive.effect
    @reactive.event(input.lukb_collab_focus)
    async def _on_collab_focus() -> None:
        payload = input.lukb_collab_focus()
        if not isinstance(payload, dict):
            return
        target = str(payload.get("target", ""))
        aid = set_peer_focus(state.session_id, target)
        if aid:
            await broadcast_presence(aid)

    # Soft-Lock für einen Block aktiv übernehmen
    @reactive.effect
    @reactive.event(input.lukb_request_block_lock)
    async def _on_request_block_lock() -> None:
        payload = input.lukb_request_block_lock()
        if not isinstance(payload, dict):
            return
        block_id = str(payload.get("block_id", "")).strip()
        if block_id:
            await transfer_block_lock(state.session_id, block_id)

    # Revisions-Historie für aktuellen Artikel laden
    @reactive.effect
    @reactive.event(input.lukb_open_revisions)
    async def _on_open_revisions() -> None:
        aid = state.current_article_id.get()
        if not aid:
            return
        revs = await asyncio.to_thread(list_article_revisions, aid, 40)
        doc = state.current_doc.get()
        await session.send_custom_message(
            "lukb_revisions_list",
            {
                "article_id": aid,
                "title": doc.metadata.title if doc else "",
                "revisions": revs,
            },
        )

    # Gespeicherte Revision wiederherstellen
    @reactive.effect
    @reactive.event(input.lukb_restore_revision)
    async def _on_restore_revision() -> None:
        payload = input.lukb_restore_revision()
        if not isinstance(payload, dict):
            return
        aid = state.current_article_id.get()
        rev_id = payload.get("revision_id")
        if not aid or not rev_id:
            return
        try:
            save_info = await asyncio.to_thread(
                restore_article_revision,
                aid,
                int(rev_id),
                user=state.current_user,
            )
            if not save_info:
                ui.notification_show("Revision konnte nicht wiederhergestellt werden.", type="warning", duration=4)
                return
            restored_doc = save_info.pop("doc_obj", None) or ArticleDocument.model_validate(save_info["article"])
            state.current_doc.set(restored_doc)
            assets_map = await asyncio.to_thread(collect_article_assets_map, restored_doc)
            pub_sync = await asyncio.to_thread(get_published_sync_status, restored_doc.id)

            await broadcast_article_sync(
                article_id=restored_doc.id,
                doc=restored_doc,
                sender_session_id=state.session_id,
                author_name=state.current_user,
                include_sender=True,
                assets_map=assets_map,
                publish_sync=pub_sync,
            )
            await state.send_article_list(restored_doc.id)
            await broadcast_article_list_to_all(exclude_session_id=state.session_id)
            pdf_b64, web_html = await state.send_active_preview(restored_doc, respect_auto_preview=False)
            await broadcast_preview_to_coauthors(
                state.session_id,
                restored_doc,
                pre_rendered_pdf_base64=pdf_b64,
                pre_rendered_html=web_html,
            )
            ui.notification_show(f"Revision #{rev_id} wurde wiederhergestellt.", type="message", duration=4)
        except Exception as exc:
            logger.exception("Fehler bei Revisions-Wiederherstellung")
            ui.notification_show(f"Wiederherstellung fehlgeschlagen: {exc}", type="error")

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

            user_label = state.current_user
            save_info = await asyncio.to_thread(
                save_article,
                doc=doc,
                user=user_label,
                create_revision=bool(payload.get("create_revision", False)),
                revision_note=str(payload.get("revision_note", "")),
                base_doc=base_doc,
                preserve_db_status=True,
            )
            merged_doc = save_info.pop("doc_obj", None) or ArticleDocument.model_validate(save_info["article"])
            state.current_article_id.set(merged_doc.id)
            state.current_doc.set(merged_doc)

            known_asset_ids = payload.get("known_asset_ids")
            assets_map = await asyncio.to_thread(
                collect_article_assets_map,
                merged_doc,
                known_asset_ids=known_asset_ids,
            )
            save_info["assets"] = assets_map
            pub_sync = (
                await asyncio.to_thread(get_published_sync_status, merged_doc.id)
                if merged_doc.status == "published"
                else None
            )
            save_info["publish_sync"] = pub_sync
            await session.send_custom_message("lukb_autosave_ack", save_info)

            # Sidebar-Refresh nur ausführen, wenn Titel, Status, Kategorie oder Revisions-Snapshot geändert wurden
            meta_changed = False
            if base_doc is not None:
                meta_changed = (
                    doc.metadata.title != base_doc.metadata.title
                    or doc.metadata.category != base_doc.metadata.category
                    or doc.status != base_doc.status
                )
            else:
                meta_changed = True

            if meta_changed or payload.get("create_revision"):
                await state.send_article_list(merged_doc.id)
                if meta_changed:
                    await broadcast_article_list_to_all(exclude_session_id=state.session_id)

            auto_preview = bool(payload.get("auto_preview", is_peer_auto_preview(state.session_id, default=True)))
            set_peer_auto_preview(state.session_id, auto_preview)

            preview_mode = str(payload.get("preview_mode", get_peer_preview_mode(state.session_id, default="pdf")))
            set_peer_preview_mode(state.session_id, preview_mode)

            # Vorschau für den Sender nur rendern, wenn sie nicht bereits aktuell ist (vermeidet Doppel-Rendering bei Autosave)
            preview_already_current = bool(payload.get("preview_already_current", False)) and not bool(save_info.get("merged", False))

            pdf_base64 = None
            web_html = None
            if not preview_already_current and auto_preview:
                pdf_base64, web_html = await state.send_active_preview(
                    merged_doc,
                    respect_auto_preview=False,
                    preview_mode=preview_mode,
                )

            # Synchronisiere alle Co-Autoren (und bei erfolgtem DB-Merge auch den Sender selbst)
            await broadcast_article_sync(
                article_id=merged_doc.id,
                doc=merged_doc,
                sender_session_id=state.session_id,
                author_name=user_label,
                include_sender=bool(save_info.get("merged", False)),
                assets_map=assets_map,
                publish_sync=pub_sync,
            )
            # Aktualisiere auch die Live-Vorschau bei allen Co-Autoren im selben Artikel
            await broadcast_preview_to_coauthors(
                state.session_id,
                merged_doc,
                pre_rendered_pdf_base64=pdf_base64,
                pre_rendered_html=web_html,
            )
        except Exception as exc:
            logger.exception("Fehler beim Speichern des Artikels")
            ui.notification_show(f"Speicherfehler: {exc}", type="error")
