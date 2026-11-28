"""
LUKB Corporate Design SVG-Generator für den Inhaltsblock `db_chart` (Grafik aus Datenbank `ts_db`).
Erzeugt verzögerungsfrei und ohne externe Plotting-Abhängigkeiten druckfertige Vektor-SVGs
mit `Yoga Sans for LUKB` für Typst-PDF und Web-HTML5.

Unterstützte Zeitreihen-Darstellungen (auch mehrfach pro Zeitreihe kombinierbar, z.B. `line` + `dot`
oder `step` + `area`, sowie über bis zu 5 Zeitreihen hinweg):
- `line`        : Klassische Linie
- `step`        : Stufenlinie (Step-After, z.B. für Leitzinsen)
- `dot`         : Datenpunkte (Dots / Scatter)
- `area`        : Gefüllte Fläche (linear oder als Stufenfläche bei Kombination mit `step`)
- `bar`         : Gruppierte Säulen / Balken
- `stacked_bar` : Gestapelte Säulen / Balken (positiv ab 0 nach oben, negativ ab 0 nach unten)
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import time
from datetime import date
from typing import Any, Iterator

from database.repository import query_timeseries_data
from services.chart_common import (
    CHART_PALETTES,
    FONT_BODY,
    FONT_HEADING,
    FONT_WEIGHT_BODY,
    FONT_WEIGHT_HEADING,
    LUKB_CHART_PALETTE,
    VALID_CHART_TYPES,
    ThreadSafeSvgCache,
    _build_embedded_font_face_defs,
    _build_svg_font_stack,
    _compute_nice_ticks,
    _compute_pretty_x_axis_ticks,
    _estimate_label_width_px,
    _format_ch_number,
    _format_date_tick,
    _infer_corporate_font_faces,
    _nice_step,
    _quote_svg_font,
    _render_empty_state_svg,
    compute_plot_height_px,
    format_axis_ticks,
    normalize_y_axis_config,
    render_timeseries_svg,
    resolve_chart_palette,
    resolve_legend_columns,
    resolve_show_legend,
)


def _extract_series_chart_types(item: Any) -> list[str]:
    if isinstance(item, dict):
        raw_multi = item.get("chart_types")
        single = str(item.get("chart_type") or "line").strip()
    else:
        raw_multi = getattr(item, "chart_types", None)
        single = str(getattr(item, "chart_type", "line") or "line").strip()

    cleaned: list[str] = []
    if isinstance(raw_multi, (list, tuple)):
        for t in raw_multi:
            ts = str(t).strip()
            if ts in VALID_CHART_TYPES and ts not in cleaned:
                cleaned.append(ts)

    if not cleaned:
        cleaned = [single if single in VALID_CHART_TYPES else "line"]
    return cleaned


_DB_CHART_SVG_CACHE = ThreadSafeSvgCache(max_size=256)
_PREVIEW_CACHE_TTL_SEC = 60
_DB_CHART_DATA_REVISION = 0
_TS_PACKAGE_CACHE_VAR: contextvars.ContextVar[dict[str, dict[str, Any]] | None] = contextvars.ContextVar(
    "_TS_PACKAGE_CACHE_VAR", default=None
)


def invalidate_db_chart_cache() -> int:
    """Erhöht die Datenrevision und leert den DB-Chart-Vorschau-Cache."""
    global _DB_CHART_DATA_REVISION
    _DB_CHART_DATA_REVISION += 1
    _DB_CHART_SVG_CACHE.clear()
    return _DB_CHART_DATA_REVISION


@contextlib.contextmanager
def publication_timeseries_snapshot() -> Iterator[dict[str, dict[str, Any]]]:
    """
    Kontextmanager für Paket-Rendering (PDF + HTML):
    Hält die frisch geladenen Zeitreihen für beide Ausgabeformate konsistent,
    sodass PDF und HTML garantiert denselben Marktdatenstand verwenden.
    """
    snapshot: dict[str, dict[str, Any]] = {}
    token = _TS_PACKAGE_CACHE_VAR.set(snapshot)
    try:
        yield snapshot
    finally:
        _TS_PACKAGE_CACHE_VAR.reset(token)


def clear_db_chart_cache() -> None:
    """Leert den In-Memory-SVG-Cache für DB-Charts."""
    _DB_CHART_SVG_CACHE.clear()


def _compute_db_chart_cache_key(
    block_data: dict[str, Any],
    embed_fonts: bool,
    max_date: str | date | None,
) -> str:
    raw_series = block_data.get("series") or []
    normalized_series = []
    for item in list(raw_series)[:5]:
        if isinstance(item, dict):
            t_str = str(item.get("ticker") or "").strip()
            lbl = str(item.get("label") or "").strip()
            y_ax = "right" if str(item.get("y_axis") or "left").strip().lower() == "right" else "left"
        else:
            t_str = str(getattr(item, "ticker", "") or "").strip()
            lbl = str(getattr(item, "label", "") or "").strip()
            y_ax = "right" if str(getattr(item, "y_axis", "left") or "left").strip().lower() == "right" else "left"
        normalized_series.append(
            {
                "ticker": t_str,
                "label": lbl,
                "chart_types": _extract_series_chart_types(item),
                "y_axis": y_ax,
            }
        )

    leg_cols = resolve_legend_columns(block_data, default_columns=0)
    key_payload = {
        "series": normalized_series,
        "start_date": str(block_data.get("start_date") or "2022-01-01").strip(),
        "end_date": str(block_data.get("end_date") or "").strip(),
        "rebasing": str(block_data.get("rebasing") or "none").strip(),
        "layout": str(block_data.get("layout") or "column").strip(),
        "chart_height_mm": str(block_data.get("chart_height_mm") or "36").strip(),
        "palette": resolve_chart_palette(block_data),
        "legend_columns": str(leg_cols) if leg_cols > 0 else "auto",
        "show_legend": resolve_show_legend(block_data),
        "y_axis_left": normalize_y_axis_config(block_data.get("y_axis_left")),
        "y_axis_right": normalize_y_axis_config(block_data.get("y_axis_right")),
        "embed_fonts": bool(embed_fonts),
        "max_date": str(max_date or "").strip(),
        "data_revision": _DB_CHART_DATA_REVISION,
        "ttl_bucket": int(time.monotonic() // _PREVIEW_CACHE_TTL_SEC),
    }
    raw_json = json.dumps(key_payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


def generate_db_chart_svg(
    block_data: dict[str, Any],
    embed_fonts: bool = True,
    max_date: str | date | None = None,
) -> str:
    """
    Zieht die konfigurierten Zeitreihen (bis zu 5 Ticker) ab `start_date` aus `ts_db`
    und rendert ein publikationsreifes SVG im LUKB Corporate Design.
    """
    pkg_ts_cache = _TS_PACKAGE_CACHE_VAR.get()
    cache_key = _compute_db_chart_cache_key(block_data, embed_fonts, max_date)
    if pkg_ts_cache is None:
        cached_svg = _DB_CHART_SVG_CACHE.get(cache_key)
        if cached_svg is not None:
            return cached_svg

    raw_series = block_data.get("series") or []
    start_date_str = str(block_data.get("start_date") or "2022-01-01").strip()
    rebasing = str(block_data.get("rebasing") or "none").strip()
    layout_mode = str(block_data.get("layout") or "column").strip()
    is_column_layout = layout_mode != "full"

    active_palette = resolve_chart_palette(block_data)

    configured_items: list[dict[str, Any]] = []
    for raw_idx, item in enumerate(list(raw_series)[:5]):
        if isinstance(item, dict):
            t_str = str(item.get("ticker") or "").strip()
            lbl = str(item.get("label") or "").strip()
            y_ax = "right" if str(item.get("y_axis") or "left").strip().lower() == "right" else "left"
        else:
            t_str = str(getattr(item, "ticker", "") or "").strip()
            lbl = str(getattr(item, "label", "") or "").strip()
            y_ax = "right" if str(getattr(item, "y_axis", "left") or "left").strip().lower() == "right" else "left"
        if t_str:
            ctypes = _extract_series_chart_types(item)
            configured_items.append(
                {
                    "ticker": t_str,
                    "chart_types": ctypes,
                    "chart_type": ctypes[0],
                    "label": lbl,
                    "y_axis": y_ax,
                    "color": active_palette[raw_idx % len(active_palette)],
                }
            )

    if not configured_items:
        return _render_empty_state_svg(
            "Keine Zeitreihe ausgewählt",
            "Bitte geben Sie im DB-Chart-Block mindestens einen Ticker aus ts_db ein (z.B. SMI, SNB_RATE).",
            embed_fonts=embed_fonts,
        )

    requested_tickers = [it["ticker"] for it in configured_items]
    end_date_limit = max_date or block_data.get("end_date")
    if pkg_ts_cache is not None:
        ts_key = json.dumps(
            {
                "tickers": [t.upper() for t in requested_tickers],
                "start": start_date_str,
                "end": str(end_date_limit or ""),
            },
            sort_keys=True,
        )
        if ts_key not in pkg_ts_cache:
            pkg_ts_cache[ts_key] = query_timeseries_data(
                requested_tickers, start_date=start_date_str, end_date=end_date_limit
            )
        db_data = pkg_ts_cache[ts_key]
    else:
        db_data = query_timeseries_data(requested_tickers, start_date=start_date_str, end_date=end_date_limit)

    resolved_series: list[dict[str, Any]] = []
    for it in configured_items:
        req_t = it["ticker"]
        entry = db_data.get(req_t) or db_data.get(req_t.upper())
        if not entry or not entry.get("points"):
            continue

        pts: list[tuple[date, float]] = list(entry["points"])
        if rebasing == "index_100" and pts:
            base_val = pts[0][1]
            if abs(base_val) > 1e-12:
                pts = [(d, (v / base_val) * 100.0) for d, v in pts]

        display_label = it["label"] if it["label"] else (entry.get("name") or entry.get("ticker") or req_t)
        resolved_series.append(
            {
                "ticker": entry.get("ticker", req_t),
                "label": display_label,
                "chart_type": it["chart_types"][0],
                "chart_types": it["chart_types"],
                "chart_types_set": set(it["chart_types"]),
                "y_axis": it["y_axis"],
                "color": it["color"],
                "points": pts,
                "points_map": {d: v for d, v in pts},
            }
        )

    if not resolved_series:
        tickers_joined = ", ".join(requested_tickers)
        return _render_empty_state_svg(
            f"Keine Datenpunkte in ts_db gefunden ({tickers_joined})",
            f"Geprüfter Zeitraum ab Startdatum {start_date_str}",
            embed_fonts=embed_fonts,
        )

    result_svg = render_timeseries_svg(
        resolved_series,
        block_data,
        is_column_layout=is_column_layout,
        embed_fonts=embed_fonts,
        rebasing=rebasing,
    )
    _DB_CHART_SVG_CACHE.set(cache_key, result_svg)
    return result_svg
