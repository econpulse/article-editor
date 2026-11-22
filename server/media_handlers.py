"""
LUKB Investment Office — Mediathek-Handler (Etappe 4).
Paginierte Suche mit Vorschaubildern, Einfügen konkreter Asset-Versionen in den Editor,
Freigabe-Anstoss, Freigabe-Bestätigung (internal/external) und Widerruf.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from shiny import Inputs, Outputs, Session, reactive, ui

from config import can_publish, is_global_admin
from database.repository import get_asset
from server.state import SessionState
from services.media_library import (
    approve_media_release,
    clone_shared_block_for_insert,
    request_media_release,
    revoke_media_release,
    search_media_library,
    sync_block_to_media_library,
)

logger = logging.getLogger("lukb_cms.media_handlers")


def register_media_handlers(
    input: Inputs,
    output: Outputs,
    session: Session,
    state: SessionState,
) -> None:
    """Registriert alle Mediathek-Dialog- und Einfüge-Events."""

    async def _show_media_modal(page: int = 1) -> None:
        query = ""
        mtype = "all"
        channel = "all"
        try:
            query = input.media_search_query() or ""
        except Exception:
            pass
        try:
            mtype = input.media_filter_type() or "all"
        except Exception:
            pass
        try:
            channel = input.media_filter_channel() or "all"
        except Exception:
            pass

        res = await asyncio.to_thread(
            search_media_library,
            state.current_user_id,
            query=query,
            media_type=mtype,
            channel=channel,
            page=page,
            page_size=8,
        )
        can_approve = await asyncio.to_thread(
            lambda: can_publish(state.current_user_id) or is_global_admin(state.current_user_id)
        )

        cards = []
        for it in res["items"]:
            thumb_el = (
                ui.tags.img(
                    src=it["thumbnail_data_uri"],
                    style="max-width:96px;max-height:58px;object-fit:contain;border:1px solid #D6DEE8;border-radius:4px;background:#fff;",
                )
                if it["thumbnail_data_uri"]
                else ui.div(it["media_type"].upper(), style="width:96px;height:58px;display:flex;align-items:center;justify-content:center;background:#F4F7FA;border:1px solid #D6DEE8;border-radius:4px;font-size:11px;color:#5A687C;")
            )

            btns = []
            if it["approval_status"] != "revoked":
                btns.append(
                    ui.tags.button(
                        f"Einfügen (v{it['latest_version']})",
                        type="button",
                        class_="btn-lukb btn-lukb-primary btn-lukb-sm",
                        onclick=f"Shiny.setInputValue('lukb_media_insert', {{asset_id: '{it['latest_asset_id']}', title: {repr(it['title'])}, source: {repr(it['source_text'])}, ts: Date.now()}}, {{priority:'event'}});",
                    )
                )
            if it["approval_status"] == "private":
                btns.append(
                    ui.tags.button(
                        "Zur Freigabe",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        onclick=f"Shiny.setInputValue('lukb_media_request_release', '{it['media_id']}', {{priority:'event'}});",
                    )
                )
            if can_approve and it["approval_status"] in ("pending", "private"):
                btns.append(
                    ui.tags.button(
                        "Freigeben (Intern)",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        onclick=f"Shiny.setInputValue('lukb_media_approve', {{media_id: '{it['media_id']}', channel: 'internal', ts: Date.now()}}, {{priority:'event'}});",
                    )
                )
                btns.append(
                    ui.tags.button(
                        "Freigeben (Extern)",
                        type="button",
                        class_="btn-lukb btn-lukb-success btn-lukb-sm",
                        onclick=f"Shiny.setInputValue('lukb_media_approve', {{media_id: '{it['media_id']}', channel: 'external', ts: Date.now()}}, {{priority:'event'}});",
                    )
                )
            if can_approve and it["approval_status"] == "approved":
                btns.append(
                    ui.tags.button(
                        "Widerrufen",
                        type="button",
                        class_="btn-lukb btn-lukb-danger btn-lukb-sm",
                        onclick=f"Shiny.setInputValue('lukb_media_revoke', '{it['media_id']}', {{priority:'event'}});",
                    )
                )

            cards.append(
                ui.div(
                    thumb_el,
                    ui.div(
                        ui.div(it["title"], style="font-weight:600;color:#002855;font-size:13.5px;"),
                        ui.div(
                            f"Typ: {it['media_type']} · Kanal: {it['usage_channel']} · Status: {it['approval_status']} · v{it['latest_version']}",
                            style="font-size:11.5px;color:#5A687C;margin-top:2px;",
                        ),
                        ui.div(
                            f"Quelle: {it['source_text'] or '—'} · Stand: {it['data_as_of'] or '—'}",
                            style="font-size:11.5px;color:#5A687C;",
                        ),
                        style="flex:1;min-width:0;",
                    ),
                    ui.div(*btns, style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;"),
                    style="display:flex;gap:12px;align-items:center;padding:8px 10px;border:1px solid #D6DEE8;border-radius:6px;margin-bottom:8px;background:#fff;",
                )
            )

        if not cards:
            cards.append(
                ui.div("Keine passenden Mediathek-Einträge gefunden.", style="padding:18px;text-align:center;color:#5A687C;")
            )

        ui.modal_show(
            ui.modal(
                ui.div(
                    ui.div(
                        ui.input_text("media_search_query", "Suche", value=query, placeholder="Titel, Schlagwort, Quelle…"),
                        ui.input_select(
                            "media_filter_type",
                            "Typ",
                            choices={
                                "all": "Alle",
                                "image": "Bilder",
                                "chart": "Charts",
                                "table": "Tabellen",
                                "kpi_cards": "KPI-Karten",
                                "media_text": "Media & Text",
                            },
                            selected=mtype,
                        ),
                        ui.input_select("media_filter_channel", "Kanal", choices={"all": "Alle", "internal": "Intern", "external": "Extern"}, selected=channel),
                        ui.input_action_button("btn_media_search", "Suchen", class_="btn-lukb btn-lukb-primary btn-lukb-sm"),
                        style="display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:8px;align-items:end;margin-bottom:12px;",
                    ),
                    ui.div(*cards, style="max-height:380px;overflow-y:auto;"),
                    ui.div(
                        f"Seite {res['page']} · {res['total']} Treffer",
                        style="font-size:12px;color:#5A687C;margin-top:6px;",
                    ),
                ),
                title="Mediathek — Freigegebene Bilder & Charts",
                size="xl",
                easy_close=True,
                footer=ui.modal_button("Schliessen", class_="btn-lukb btn-lukb-ghost"),
            )
        )

    @reactive.effect
    @reactive.event(input.lukb_open_media_library)
    async def _on_open_media_library() -> None:
        await _show_media_modal(1)

    @reactive.effect
    @reactive.event(input.btn_media_search)
    async def _on_media_search() -> None:
        await _show_media_modal(1)

    @reactive.effect
    @reactive.event(input.lukb_media_request_release)
    async def _on_media_request_release() -> None:
        mid = str(input.lukb_media_request_release() or "").strip()
        if not mid:
            return
        res = await asyncio.to_thread(request_media_release, mid, state.current_user_id)
        if not res.get("success"):
            ui.notification_show(res.get("error", "Fehler"), type="warning", duration=4)
            return
        await _show_media_modal(1)
        ui.notification_show("Freigabe für Mediathek-Eintrag angefordert.", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.lukb_media_approve)
    async def _on_media_approve() -> None:
        payload = input.lukb_media_approve()
        if not isinstance(payload, dict):
            return
        mid = str(payload.get("media_id", "")).strip()
        channel = str(payload.get("channel", "internal")).strip()
        res = await asyncio.to_thread(approve_media_release, mid, usage_channel=channel, user_id=state.current_user_id)
        if not res.get("success"):
            ui.notification_show(res.get("error", "Fehler"), type="warning", duration=4)
            return
        await _show_media_modal(1)
        ui.notification_show(f"Mediathek-Eintrag für Kanal '{channel}' freigegeben.", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.lukb_media_revoke)
    async def _on_media_revoke() -> None:
        mid = str(input.lukb_media_revoke() or "").strip()
        if not mid:
            return
        res = await asyncio.to_thread(revoke_media_release, mid, state.current_user_id)
        if not res.get("success"):
            ui.notification_show(res.get("error", "Fehler"), type="warning", duration=4)
            return
        usages = res.get("usages") or []
        await _show_media_modal(1)
        ui.notification_show(
            f"Freigabe widerrufen. {len(usages)} bestehende Verwendung(en) zur Prüfung markiert.",
            type="warning",
            duration=6,
        )

    @reactive.effect
    @reactive.event(input.lukb_media_insert)
    async def _on_media_insert() -> None:
        payload = input.lukb_media_insert()
        if not isinstance(payload, dict):
            return
        aid = str(payload.get("asset_id", "")).strip()
        if not aid:
            return
        res = await asyncio.to_thread(
            clone_shared_block_for_insert,
            aid,
            user_id=state.current_user_id,
            target_article_id=state.current_article_id.get(),
        )
        if not res:
            ui.notification_show("Asset konnte nicht geladen werden.", type="warning", duration=4)
            return
        ui.modal_remove()
        if res.get("kind") == "block":
            await session.send_custom_message(
                "lukb_insert_media_block",
                {
                    "block": res["block"],
                    "assets": res.get("assets") or {},
                },
            )
            return
        await session.send_custom_message(
            "lukb_insert_media_figure",
            {
                "asset_id": res["asset_id"],
                "data_uri": res["data_uri"],
                "title": str(payload.get("title", "") or ""),
                "source": str(payload.get("source", "") or ""),
            },
        )

    @reactive.effect
    @reactive.event(input.lukb_sync_block_share)
    async def _on_sync_block_share() -> None:
        payload = input.lukb_sync_block_share()
        if not isinstance(payload, dict) or not state.current_user_id:
            return
        block = payload.get("block")
        if not isinstance(block, dict):
            return
        article_id = str(payload.get("article_id") or state.current_article_id.get() or "").strip() or None
        if article_id and not await asyncio.to_thread(state.can_access_article, article_id, "edit"):
            return
        res = await asyncio.to_thread(
            sync_block_to_media_library,
            article_id,
            block,
            state.current_user_id,
        )
        await session.send_custom_message(
            "lukb_block_share_ack",
            {
                "block_id": block.get("id"),
                "shared_media_id": res.get("media_id"),
                "share_in_media_library": block.get("share_in_media_library", "no"),
            },
        )
        if res.get("shared"):
            ch_lbl = "Extern" if res.get("usage_channel") == "external" else "Intern"
            ui.notification_show(
                f"In Mediathek geteilt ({ch_lbl}, direkt für alle sichtbar).",
                type="message",
                duration=3,
            )
        else:
            ui.notification_show("Mediathek-Freigabe für diesen Block deaktiviert.", type="message", duration=3)
