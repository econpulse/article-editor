"""
LUKB Investment Office — Vorschau-, Diagramm- & Ticker-Handler.
Behandelt DB-Chart-Vorschau, Ticker-Autovervollständigung, Auto-Typst-Toggling und manuelle Preview-Refreshes.
"""

from __future__ import annotations

import base64
import logging
from shiny import Inputs, Outputs, Session, reactive

from database.repository import search_tickers
from server.collab import set_peer_auto_preview
from server.state import SessionState
from services.chart_generator import generate_db_chart_svg

logger = logging.getLogger("lukb_cms.preview_handlers")


def register_preview_handlers(
    input: Inputs,
    output: Outputs,
    session: Session,
    state: SessionState,
) -> None:
    """Registriert alle Vorschau- und Diagramm-Events an der Session."""

    # Einzelne DB-Chart-Vorschau im Block sofort aktualisieren
    @reactive.effect
    @reactive.event(input.lukb_preview_db_chart)
    async def _on_preview_db_chart() -> None:
        payload = input.lukb_preview_db_chart()
        if not isinstance(payload, dict) or "block" not in payload:
            return
        blk = payload["block"]
        bid = blk.get("id", "")
        if not bid:
            return
        svg_markup = generate_db_chart_svg(blk)
        b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
        await session.send_custom_message(
            "lukb_db_chart_svg",
            {
                "block_id": bid,
                "data_uri": f"data:image/svg+xml;base64,{b64}",
            },
        )

    # Schnelle Ticker-Autovervollständigung für tausende Ticker in ts_db
    @reactive.effect
    @reactive.event(input.lukb_search_tickers)
    async def _on_search_tickers() -> None:
        payload = input.lukb_search_tickers()
        if not isinstance(payload, dict):
            return
        query = str(payload.get("query", ""))
        req_id = payload.get("request_id", 0)
        results = search_tickers(query=query, limit=15)
        await session.send_custom_message(
            "lukb_ticker_suggestions",
            {
                "request_id": req_id,
                "query": query,
                "results": results,
            },
        )

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
            doc = state.current_doc.get()
            if doc is not None:
                await state.send_preview(doc, include_typst=True)

    # Manueller Preview-Refresh
    @reactive.effect
    @reactive.event(input.btn_refresh_preview)
    async def _on_refresh_preview() -> None:
        doc = state.current_doc.get()
        if doc is not None:
            await state.send_preview(doc, include_typst=True)
