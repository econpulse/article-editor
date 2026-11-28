"""
LUKB Investment Office — Vorschau-, Diagramm- & Ticker-Handler.
Behandelt DB-Chart-Vorschau, Ticker-Autovervollständigung, Auto-Typst-Toggling und manuelle Preview-Refreshes.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import re
from shiny import Inputs, Outputs, Session, reactive

from database.repository import search_tickers
from schemas.article import ArticleDocument
from server.collab import (
    get_peer_preview_mode,
    is_peer_auto_preview,
    set_peer_auto_preview,
    set_peer_preview_mode,
)
from server.state import SessionState
from services.chart_generator import generate_db_chart_svg
from services.custom_chart_generator import generate_custom_chart_svg

logger = logging.getLogger("lukb_cms.preview_handlers")


def register_preview_handlers(
    input: Inputs,
    output: Outputs,
    session: Session,
    state: SessionState,
) -> None:
    """Registriert alle Vorschau- und Diagramm-Events an der Session."""

    async def _send_single_chart_preview(
        payload: Any,
        message_name: str,
        is_db_chart: bool,
    ) -> None:
        if not isinstance(payload, dict) or "block" not in payload:
            return
        blk = payload["block"]
        bid = blk.get("id", "")
        if not bid:
            return
        if is_db_chart:
            cur_doc = state.current_doc.get()
            max_date = cur_doc.metadata.publication_date if cur_doc else None
            svg_markup = await asyncio.to_thread(generate_db_chart_svg, blk, True, max_date)
        else:
            svg_markup = await asyncio.to_thread(generate_custom_chart_svg, blk, True)
        b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
        axis_defaults = None
        m_axes = re.search(r'data-axes-meta="([^"]+)"', svg_markup[:600])
        if m_axes:
            try:
                axis_defaults = json.loads(html.unescape(m_axes.group(1)))
            except Exception:
                axis_defaults = None
        await session.send_custom_message(
            message_name,
            {
                "block_id": bid,
                "data_uri": f"data:image/svg+xml;base64,{b64}",
                "axis_defaults": axis_defaults,
            },
        )

    # Einzelne DB-Chart-Vorschau im Block sofort aktualisieren
    @reactive.effect
    @reactive.event(input.lukb_preview_db_chart)
    async def _on_preview_db_chart() -> None:
        await _send_single_chart_preview(input.lukb_preview_db_chart(), "lukb_db_chart_svg", True)

    # Einzelne Custom-Chart-Vorschau (Clipboard) im Block sofort aktualisieren
    @reactive.effect
    @reactive.event(input.lukb_preview_custom_chart)
    async def _on_preview_custom_chart() -> None:
        await _send_single_chart_preview(input.lukb_preview_custom_chart(), "lukb_custom_chart_svg", False)

    # Schnelle Ticker-Autovervollständigung für tausende Ticker in ts_db
    @reactive.effect
    @reactive.event(input.lukb_search_tickers)
    async def _on_search_tickers() -> None:
        payload = input.lukb_search_tickers()
        if not isinstance(payload, dict):
            return
        query = str(payload.get("query", ""))
        req_id = payload.get("request_id", 0)
        results = await asyncio.to_thread(search_tickers, query=query, limit=15)
        await session.send_custom_message(
            "lukb_ticker_suggestions",
            {
                "request_id": req_id,
                "query": query,
                "results": results,
            },
        )

    # Entkoppelte Sofort-Vorschau (schneller Debounce ohne DB-Schreiboperation)
    @reactive.effect
    @reactive.event(input.lukb_request_live_preview)
    async def _on_request_live_preview() -> None:
        payload = input.lukb_request_live_preview()
        if not isinstance(payload, dict) or "article" not in payload:
            return
        article_data = payload["article"]
        if not isinstance(article_data, dict):
            return
        preview_mode = str(payload.get("preview_mode", get_peer_preview_mode(state.session_id, default="pdf"))).strip().lower()
        if not is_peer_auto_preview(state.session_id, default=True):
            return

        try:
            doc = ArticleDocument.model_validate(article_data)
            active_aid = state.current_article_id.get()
            if active_aid and doc.id != active_aid:
                return
            client_edit_seq = payload.get("client_edit_seq")
            state.enqueue_preview(
                doc,
                preview_mode=preview_mode,
                client_edit_seq=int(client_edit_seq) if client_edit_seq is not None else None,
            )
        except Exception as exc:
            logger.warning(f"Fehler bei entkoppelter Live-Vorschau: {exc}")

    # Umschalten der kontinuierlichen Typst-Vorschau (Auto-Typst)
    @reactive.effect
    @reactive.event(input.lukb_auto_preview_toggle)
    async def _on_auto_preview_toggle() -> None:
        payload = input.lukb_auto_preview_toggle()
        if not isinstance(payload, dict):
            return
        enabled = bool(payload.get("enabled", True))
        set_peer_auto_preview(state.session_id, enabled)
        if enabled and payload.get("refresh_now"):
            await state.send_active_preview(respect_auto_preview=False)

    # Umschalten des Vorschau-Modus (PDF Typst vs. Web HTML5)
    @reactive.effect
    @reactive.event(input.lukb_preview_mode_change)
    async def _on_preview_mode_change() -> None:
        payload = input.lukb_preview_mode_change()
        if not isinstance(payload, dict):
            return
        mode = str(payload.get("mode", "pdf")).strip().lower()
        set_peer_preview_mode(state.session_id, mode)
        if mode in ("web", "pdf"):
            await state.send_active_preview(
                respect_auto_preview=(mode == "pdf"),
                preview_mode=mode,
            )

    # Manueller Preview-Refresh
    @reactive.effect
    @reactive.event(input.btn_refresh_preview)
    async def _on_refresh_preview() -> None:
        await state.send_active_preview(respect_auto_preview=False)
