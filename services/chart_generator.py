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

import html
import math
from datetime import date
from typing import Any

from database.repository import query_timeseries_data

# Offizielle LUKB 5er-Farbpalette für bis zu 5 Zeitreihen
LUKB_CHART_PALETTE: list[str] = [
    "#002855",  # 1. LUKB Navy
    "#009FE3",  # 2. LUKB Cyan
    "#C59B27",  # 3. LUKB Gold
    "#005A9C",  # 4. LUKB Blue
    "#6482A6",  # 5. LUKB Slate
]

VALID_CHART_TYPES = ("line", "step", "dot", "area", "bar", "stacked_bar")

FONT_BODY = "Yoga Sans for LUKB Light, Calibri, Arial, sans-serif"
FONT_HEADING = "Yoga Sans for LUKB Medium, Calibri, Arial, sans-serif"


def _nice_step(span: float, target_ticks: int = 5) -> float:
    if span <= 0 or math.isnan(span) or math.isinf(span):
        return 1.0
    raw = span / max(1, target_ticks)
    mag = 10.0 ** math.floor(math.log10(raw))
    residual = raw / mag
    if residual <= 1.0:
        nice = 1.0
    elif residual <= 2.0:
        nice = 2.0
    elif residual <= 2.5:
        nice = 2.5
    elif residual <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    return nice * mag


def _compute_nice_ticks(min_val: float, max_val: float, target_ticks: int = 5) -> list[float]:
    if min_val > max_val:
        min_val, max_val = max_val, min_val
    if math.isclose(min_val, max_val, abs_tol=1e-9):
        delta = abs(min_val) * 0.1 if abs(min_val) > 1e-6 else 1.0
        min_val -= delta
        max_val += delta

    span = max_val - min_val
    step = _nice_step(span, target_ticks=target_ticks)
    nice_min = math.floor(min_val / step) * step
    nice_max = math.ceil(max_val / step) * step

    ticks: list[float] = []
    curr = nice_min
    safety = 0
    while curr <= nice_max + step * 0.05 and safety < 20:
        ticks.append(round(curr, 8))
        curr += step
        safety += 1

    if len(ticks) < 2:
        ticks = [min_val, max_val]
    return ticks


def _format_ch_number(val: float, step: float) -> str:
    if abs(val) < 1e-9:
        val = 0.0
    if step >= 1.0 and abs(val - round(val)) < 1e-6:
        int_val = int(round(val))
        return f"{int_val:,}".replace(",", "'")
    elif step >= 0.25:
        s = f"{val:,.2f}".replace(",", "'")
        if s.endswith(".00"):
            return s[:-3]
        if s.endswith("0") and "." in s:
            return s[:-1]
        return s
    elif step >= 0.05:
        return f"{val:,.2f}".replace(",", "'")
    else:
        return f"{val:,.3f}".replace(",", "'")


def _estimate_label_width_px(label: str, font_size: float) -> float:
    """
    Berechnet die präzise Textbreite einer Y-Achsen-Zahl in `Yoga Sans for LUKB Light` / `Calibri`,
    damit die linke Kante der längsten Y-Achsen-Zahl exakt bei `x = 0` (bündig mit Titel/Untertitel) liegt.
    """
    total = 0.0
    for ch in label:
        if ch in ".,' ":
            total += 0.27 * font_size
        elif ch == "-":
            total += 0.40 * font_size
        elif ch == "1":
            total += 0.48 * font_size
        else:
            total += 0.56 * font_size
    return total


def _format_date_tick(dt: date, total_days: int) -> str:
    if total_days > 365 * 3:
        return dt.strftime("%m.%Y") if total_days < 365 * 5 else dt.strftime("%Y")
    if total_days > 120:
        return dt.strftime("%m.%Y")
    return dt.strftime("%d.%m.%y")


def _render_empty_state_svg(message: str, detail: str = "") -> str:
    esc_msg = html.escape(message)
    esc_det = html.escape(detail)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 320" width="680" height="320">
  <rect width="680" height="320" fill="#FFFFFF"/>
  <rect x="2" y="20" width="676" height="280" rx="4" fill="#F4F7FA" stroke="#D6DEE8" stroke-dasharray="5,5"/>
  <text x="340" y="150" font-family="{FONT_HEADING}" font-size="14" fill="#002855" text-anchor="middle">{esc_msg}</text>
  <text x="340" y="178" font-family="{FONT_BODY}" font-size="12.5" fill="#5A687C" text-anchor="middle">{esc_det}</text>
</svg>"""


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


def generate_db_chart_svg(block_data: dict[str, Any]) -> str:
    """
    Zieht die konfigurierten Zeitreihen (bis zu 5 Ticker) ab `start_date` aus `ts_db`
    und rendert ein publikationsreifes SVG im LUKB Corporate Design.
    - Linke Kante der längsten Y-Achsen-Zahl schliesst exakt bei `x = 0` bündig mit Titel/Untertitel ab.
    - Schriftgrössen für Achsen und Legende passen sich an `layout` ('column' vs. 'full') an.
    """
    raw_series = block_data.get("series") or []
    start_date_str = str(block_data.get("start_date") or "2022-01-01").strip()
    rebasing = str(block_data.get("rebasing") or "none").strip()
    layout_mode = str(block_data.get("layout") or "column").strip()
    is_column_layout = layout_mode != "full"

    configured_items: list[dict[str, Any]] = []
    for item in list(raw_series)[:5]:
        if isinstance(item, dict):
            t_str = str(item.get("ticker") or "").strip()
            lbl = str(item.get("label") or "").strip()
        else:
            t_str = str(getattr(item, "ticker", "") or "").strip()
            lbl = str(getattr(item, "label", "") or "").strip()
        if t_str:
            ctypes = _extract_series_chart_types(item)
            configured_items.append(
                {
                    "ticker": t_str,
                    "chart_types": ctypes,
                    "chart_type": ctypes[0],
                    "label": lbl,
                }
            )

    if not configured_items:
        return _render_empty_state_svg(
            "Keine Zeitreihe ausgewählt",
            "Bitte geben Sie im DB-Chart-Block mindestens einen Ticker aus ts_db ein (z.B. SMI, SNB_RATE).",
        )

    requested_tickers = [it["ticker"] for it in configured_items]
    db_data = query_timeseries_data(requested_tickers, start_date=start_date_str)

    resolved_series: list[dict[str, Any]] = []
    for idx, it in enumerate(configured_items):
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
        color = LUKB_CHART_PALETTE[idx % len(LUKB_CHART_PALETTE)]
        ctypes_set = set(it["chart_types"])
        resolved_series.append(
            {
                "ticker": entry.get("ticker", req_t),
                "label": display_label,
                "chart_type": it["chart_types"][0],
                "chart_types": it["chart_types"],
                "chart_types_set": ctypes_set,
                "color": color,
                "points": pts,
                "points_map": {d: v for d, v in pts},
            }
        )

    if not resolved_series:
        tickers_joined = ", ".join(requested_tickers)
        return _render_empty_state_svg(
            f"Keine Datenpunkte in ts_db gefunden ({tickers_joined})",
            f"Geprüfter Zeitraum ab Startdatum {start_date_str}",
        )

    # 1. Datumsbereich (X-Achse) ermitteln
    all_dates: list[date] = sorted({d for s in resolved_series for d, _ in s["points"]})
    min_date = all_dates[0]
    max_date = all_dates[-1]
    min_ord = float(min_date.toordinal())
    max_ord = float(max_date.toordinal())

    has_bars = any(
        bool(s["chart_types_set"] & {"bar", "stacked_bar"}) for s in resolved_series
    )
    if math.isclose(min_ord, max_ord):
        min_ord -= 15.0
        max_ord += 15.0
    elif has_bars:
        pad_days = max(4.0, (max_ord - min_ord) * 0.045)
        min_ord -= pad_days
        max_ord += pad_days

    span_ord = max(1.0, max_ord - min_ord)

    # 2. Wertebereich (Y-Achse) ermitteln (inkl. Stacked-Bar-Summen)
    y_candidates: list[float] = []
    for s in resolved_series:
        if "stacked_bar" not in s["chart_types_set"] or len(s["chart_types_set"]) > 1:
            for _, v in s["points"]:
                y_candidates.append(v)

    stacked_series = [s for s in resolved_series if "stacked_bar" in s["chart_types_set"]]
    if stacked_series:
        stacked_dates = sorted({d for s in stacked_series for d, _ in s["points"]})
        for dt in stacked_dates:
            pos_sum = sum(
                s["points_map"][dt]
                for s in stacked_series
                if dt in s["points_map"] and s["points_map"][dt] >= 0
            )
            neg_sum = sum(
                s["points_map"][dt]
                for s in stacked_series
                if dt in s["points_map"] and s["points_map"][dt] < 0
            )
            y_candidates.append(pos_sum)
            if neg_sum < 0:
                y_candidates.append(neg_sum)

    if has_bars:
        y_candidates.append(0.0)
    if rebasing == "index_100":
        y_candidates.append(100.0)

    raw_min_y = min(y_candidates) if y_candidates else 0.0
    raw_max_y = max(y_candidates) if y_candidates else 100.0

    y_ticks = _compute_nice_ticks(raw_min_y, raw_max_y, target_ticks=5)
    y_min = y_ticks[0]
    y_max = y_ticks[-1]
    y_span = max(1e-9, y_max - y_min)
    y_step = y_ticks[1] - y_ticks[0] if len(y_ticks) > 1 else 1.0

    # 3. Schriftgrössen & Plot-Geometrie
    # Im 1-spaltigen Satz (~247pt Spaltenbreite, Skalierungsfaktor ~0.363) entsprechen
    # 22.5px im SVG rund 8.2pt im Druck (und 20.5px für die Legende rund 7.5pt im Druck).
    axis_font_size = 22.5 if is_column_layout else 14.5
    legend_font_size = 20.5 if is_column_layout else 14.0
    items_per_legend_row = 2 if is_column_layout else 3
    if len(resolved_series) < items_per_legend_row:
        items_per_legend_row = max(1, len(resolved_series))
    legend_rows = math.ceil(len(resolved_series) / items_per_legend_row)
    legend_row_gap = 29.0 if is_column_layout else 22.0

    # Berechne die Breite der längsten Zahl auf der Y-Achse:
    # Die linke Kante der längsten Y-Achsen-Zahl liegt exakt bei x = 0 (bündig mit Titel/Untertitel).
    y_tick_labels = [_format_ch_number(tick, y_step) for tick in y_ticks]
    max_y_label_w = max(
        (_estimate_label_width_px(lbl, axis_font_size) for lbl in y_tick_labels),
        default=16.0,
    )
    y_label_right_x = max(12.0, round(max_y_label_w, 1))
    y_axis_gap = 10.0 if is_column_layout else 9.0

    svg_w = 680
    plot_left = y_label_right_x + y_axis_gap
    plot_right = 678.0
    plot_top = 18.0
    plot_bottom = 228.0 if is_column_layout else 238.0
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    x_axis_label_y = plot_bottom + (31.0 if is_column_layout else 24.0)
    legend_start_y = x_axis_label_y + (34.0 if is_column_layout else 27.0)
    svg_h = int(round(legend_start_y + (legend_rows - 1) * legend_row_gap + 14.0))

    def x_px(dt: date) -> float:
        return plot_left + ((float(dt.toordinal()) - min_ord) / span_ord) * plot_w

    def y_px(val: float) -> float:
        clamped = max(y_min, min(y_max, val))
        return plot_bottom - ((clamped - y_min) / y_span) * plot_h

    zero_y = y_px(0.0) if (y_min <= 0.0 <= y_max) else (plot_bottom if y_min > 0 else plot_top)

    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="#FFFFFF"/>',
    ]

    # 4. Horizontale Gitterlinien & Y-Achsen-Labels (bündig links bei x=0 für die längste Zahl)
    svg_parts.append('  <g stroke="#E2E8F0" stroke-width="1">')
    for tick in y_ticks:
        ty = y_px(tick)
        is_zero = abs(tick) < 1e-9
        stroke_col = "#94A3B8" if is_zero else "#E2E8F0"
        stroke_w = "1.4" if is_zero else "1"
        svg_parts.append(
            f'    <line x1="{plot_left:.1f}" y1="{ty:.1f}" x2="{plot_right:.1f}" y2="{ty:.1f}" '
            f'stroke="{stroke_col}" stroke-width="{stroke_w}"/>'
        )
    svg_parts.append("  </g>")

    if rebasing == "index_100" and y_min < 100.0 < y_max:
        y100 = y_px(100.0)
        svg_parts.append(
            f'  <line x1="{plot_left:.1f}" y1="{y100:.1f}" x2="{plot_right:.1f}" y2="{y100:.1f}" '
            f'stroke="#64748B" stroke-width="1.1" stroke-dasharray="4,3"/>'
        )

    y_text_offset = 7.0 if is_column_layout else 5.0
    svg_parts.append(
        f'  <g font-family="{FONT_BODY}" font-size="{axis_font_size}" fill="#5A687C" text-anchor="end">'
    )
    for tick, raw_lbl in zip(y_ticks, y_tick_labels):
        ty = y_px(tick)
        lbl_str = html.escape(raw_lbl)
        svg_parts.append(
            f'    <text x="{y_label_right_x:.1f}" y="{ty + y_text_offset:.1f}">{lbl_str}</text>'
        )
    svg_parts.append("  </g>")

    # 5. X-Achsen-Labels (letztes Label rechtsbündig am rechten Chart-Rand, damit nichts abgeschnitten wird)
    total_days = max(1, (max_date - min_date).days)
    max_x_ticks = 5 if is_column_layout else 6
    num_x_ticks = min(max_x_ticks, len(all_dates)) if len(all_dates) <= max_x_ticks else max_x_ticks
    x_tick_dates: list[date] = []
    if len(all_dates) <= max_x_ticks:
        x_tick_dates = all_dates
    else:
        for i in range(num_x_ticks):
            t_ord = int(round(min_date.toordinal() + (i / (num_x_ticks - 1)) * total_days))
            x_tick_dates.append(date.fromordinal(t_ord))

    svg_parts.append(
        f'  <g font-family="{FONT_BODY}" font-size="{axis_font_size}" fill="#5A687C">'
    )
    for idx_t, dt in enumerate(x_tick_dates):
        tx = x_px(dt)
        lbl = html.escape(_format_date_tick(dt, total_days))
        half_lbl_w = _estimate_label_width_px(lbl, axis_font_size) * 0.5
        if idx_t == 0 and tx - half_lbl_w < 0.0:
            svg_parts.append(
                f'    <text x="{max(0.0, tx - half_lbl_w):.1f}" y="{x_axis_label_y:.1f}" text-anchor="start">{lbl}</text>'
            )
        elif idx_t == len(x_tick_dates) - 1 and tx + half_lbl_w > plot_right:
            svg_parts.append(
                f'    <text x="{plot_right:.1f}" y="{x_axis_label_y:.1f}" text-anchor="end">{lbl}</text>'
            )
        else:
            svg_parts.append(
                f'    <text x="{tx:.1f}" y="{x_axis_label_y:.1f}" text-anchor="middle">{lbl}</text>'
            )
    svg_parts.append("  </g>")

    # 6. Z-Order Rendering der 6 Chart-Typen (auch mehrfach pro Zeitreihe!)
    # ------------------------------------------------------------------
    # Ebene 1: AREA (Linear-Fläche oder Stufen-Fläche, falls mit `step` kombiniert)
    # ------------------------------------------------------------------
    for s in resolved_series:
        ctypes = s["chart_types_set"]
        if "area" not in ctypes:
            continue
        pts = s["points"]
        if not pts:
            continue
        col = s["color"]
        if len(pts) >= 2:
            if "step" in ctypes:
                d_cmds = [
                    f"M {x_px(pts[0][0]):.1f} {zero_y:.1f}",
                    f"V {y_px(pts[0][1]):.1f}",
                ]
                for i in range(1, len(pts)):
                    nx, ny = x_px(pts[i][0]), y_px(pts[i][1])
                    d_cmds.append(f"H {nx:.1f} V {ny:.1f}")
                d_cmds.append(f"V {zero_y:.1f} Z")
                svg_parts.append(
                    f'  <path d="{" ".join(d_cmds)}" fill="{col}" fill-opacity="0.18"/>'
                )
            else:
                poly_coords = [f"{x_px(pts[0][0]):.1f},{zero_y:.1f}"]
                line_coords = []
                for d, v in pts:
                    px, py = x_px(d), y_px(v)
                    poly_coords.append(f"{px:.1f},{py:.1f}")
                    line_coords.append(f"{px:.1f},{py:.1f}")
                poly_coords.append(f"{x_px(pts[-1][0]):.1f},{zero_y:.1f}")
                svg_parts.append(
                    f'  <polygon points="{" ".join(poly_coords)}" fill="{col}" fill-opacity="0.18"/>'
                )
                if "line" not in ctypes and "step" not in ctypes:
                    svg_parts.append(
                        f'  <polyline fill="none" stroke="{col}" stroke-width="2.6" '
                        f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(line_coords)}"/>'
                    )
        else:
            px, py = x_px(pts[0][0]), y_px(pts[0][1])
            svg_parts.append(f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{col}"/>')

    # ------------------------------------------------------------------
    # Ebene 2 & 3: STACKED_BAR & BAR (kombiniert oder einzeln)
    # ------------------------------------------------------------------
    bar_series = [
        s
        for s in resolved_series
        if "bar" in s["chart_types_set"] and "stacked_bar" not in s["chart_types_set"]
    ]
    if stacked_series or bar_series:
        bar_dates = sorted(
            {d for s in (stacked_series + bar_series) for d, _ in s["points"]}
        )
        if len(bar_dates) >= 2:
            min_dx = min(
                abs(x_px(bar_dates[i + 1]) - x_px(bar_dates[i]))
                for i in range(len(bar_dates) - 1)
                if abs(x_px(bar_dates[i + 1]) - x_px(bar_dates[i])) > 0.5
            )
        else:
            min_dx = 60.0

        slot_count = (1 if stacked_series else 0) + len(bar_series)
        cluster_w = max(6.0, min(46.0, min_dx * 0.68))
        single_bar_w = max(3.0, cluster_w / max(1, slot_count))

        for dt in bar_dates:
            cx = x_px(dt)
            cluster_left = cx - (cluster_w / 2.0)
            slot_idx = 0

            if stacked_series:
                bx = cluster_left + slot_idx * single_bar_w
                pos_cursor = 0.0
                neg_cursor = 0.0
                for s in stacked_series:
                    val = s["points_map"].get(dt)
                    if val is None or abs(val) < 1e-12:
                        continue
                    if val >= 0:
                        y_start = y_px(pos_cursor + val)
                        y_end = y_px(pos_cursor)
                        pos_cursor += val
                    else:
                        y_start = y_px(neg_cursor)
                        y_end = y_px(neg_cursor + val)
                        neg_cursor += val
                    rect_h = max(1.0, abs(y_end - y_start))
                    rect_top = min(y_start, y_end)
                    svg_parts.append(
                        f'  <rect x="{bx:.1f}" y="{rect_top:.1f}" width="{max(2.0, single_bar_w - 0.8):.1f}" '
                        f'height="{rect_h:.1f}" fill="{s["color"]}" rx="1"/>'
                    )
                slot_idx += 1

            for s in bar_series:
                val = s["points_map"].get(dt)
                if val is not None:
                    bx = cluster_left + slot_idx * single_bar_w
                    vy = y_px(val)
                    rect_top = min(vy, zero_y)
                    rect_h = max(1.5, abs(zero_y - vy))
                    svg_parts.append(
                        f'  <rect x="{bx:.1f}" y="{rect_top:.1f}" width="{max(2.0, single_bar_w - 1.0):.1f}" '
                        f'height="{rect_h:.1f}" fill="{s["color"]}" rx="1"/>'
                    )
                slot_idx += 1

    # ------------------------------------------------------------------
    # Ebene 4: STEP (Stufenlinie)
    # ------------------------------------------------------------------
    stroke_w_main = "3.2" if is_column_layout else "2.6"
    for s in resolved_series:
        if "step" not in s["chart_types_set"]:
            continue
        pts = s["points"]
        if not pts:
            continue
        col = s["color"]
        if len(pts) >= 2:
            d_cmds = [f"M {x_px(pts[0][0]):.1f} {y_px(pts[0][1]):.1f}"]
            for i in range(1, len(pts)):
                nx, ny = x_px(pts[i][0]), y_px(pts[i][1])
                d_cmds.append(f"H {nx:.1f} V {ny:.1f}")
            svg_parts.append(
                f'  <path d="{" ".join(d_cmds)}" fill="none" stroke="{col}" '
                f'stroke-width="{stroke_w_main}" stroke-linejoin="round" stroke-linecap="round"/>'
            )
        else:
            px, py = x_px(pts[0][0]), y_px(pts[0][1])
            svg_parts.append(f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{col}"/>')

    # ------------------------------------------------------------------
    # Ebene 5: LINE (Klassische Linie)
    # ------------------------------------------------------------------
    for s in resolved_series:
        if "line" not in s["chart_types_set"]:
            continue
        pts = s["points"]
        if not pts:
            continue
        col = s["color"]
        if len(pts) >= 2:
            coords = [f"{x_px(d):.1f},{y_px(v):.1f}" for d, v in pts]
            svg_parts.append(
                f'  <polyline fill="none" stroke="{col}" stroke-width="{stroke_w_main}" '
                f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(coords)}"/>'
            )
        else:
            px, py = x_px(pts[0][0]), y_px(pts[0][1])
            svg_parts.append(f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{col}"/>')

    # ------------------------------------------------------------------
    # Ebene 6: DOT (Punkte / Scatter — auch kombinierbar mit Line, Step, Area, Bar)
    # ------------------------------------------------------------------
    dot_r = "5.0" if is_column_layout else "4.0"
    for s in resolved_series:
        if "dot" not in s["chart_types_set"]:
            continue
        pts = s["points"]
        col = s["color"]
        svg_parts.append(f'  <g fill="{col}" stroke="#FFFFFF" stroke-width="1.4">')
        for d, v in pts:
            px, py = x_px(d), y_px(v)
            svg_parts.append(f'    <circle cx="{px:.1f}" cy="{py:.1f}" r="{dot_r}"/>')
        svg_parts.append("  </g>")

    # 7. Legende am unteren Rand (ebenfalls linksbündig bei x = 0 startend)
    legend_left_x = 0.0
    col_step = (plot_right - legend_left_x) / max(1, items_per_legend_row)
    max_label_chars = 27 if is_column_layout else 34

    svg_parts.append(
        f'  <g font-family="{FONT_HEADING}" font-size="{legend_font_size}" fill="#1A2433">'
    )
    for idx, s in enumerate(resolved_series):
        row_num = idx // items_per_legend_row
        col_num = idx % items_per_legend_row
        lx = legend_left_x + col_num * col_step
        ly = legend_start_y + row_num * legend_row_gap
        col = s["color"]
        ctypes = s["chart_types_set"]
        lbl = html.escape(s["label"][:max_label_chars])

        icon_w = 24.0 if is_column_layout else 19.0
        icon_h = 13.0 if is_column_layout else 11.0
        icon_top = ly - icon_h + 1.0

        # 1. Fläche oder Balken im Legenden-Icon
        if "bar" in ctypes or "stacked_bar" in ctypes:
            svg_parts.append(
                f'    <rect x="{lx:.1f}" y="{icon_top:.1f}" width="{icon_w - 4:.1f}" height="{icon_h:.1f}" rx="1.5" fill="{col}"/>'
            )
        elif "area" in ctypes:
            svg_parts.append(
                f'    <rect x="{lx:.1f}" y="{icon_top:.1f}" width="{icon_w:.1f}" height="{icon_h:.1f}" '
                f'fill="{col}" fill-opacity="0.24"/>'
            )

        # 2. Linie oder Stufe im Legenden-Icon
        if "step" in ctypes:
            mid_x = lx + icon_w * 0.5
            svg_parts.append(
                f'    <path d="M {lx:.1f} {ly - 2:.1f} H {mid_x:.1f} V {icon_top + 1:.1f} H {lx + icon_w:.1f}" '
                f'fill="none" stroke="{col}" stroke-width="2.8"/>'
            )
        elif "line" in ctypes or ("area" in ctypes and "bar" not in ctypes and "stacked_bar" not in ctypes):
            line_y = (icon_top + 1.0) if ("area" in ctypes and "line" not in ctypes) else (ly - 5.5)
            svg_parts.append(
                f'    <line x1="{lx:.1f}" y1="{line_y:.1f}" x2="{lx + icon_w:.1f}" y2="{line_y:.1f}" '
                f'stroke="{col}" stroke-width="3.0" stroke-linecap="round"/>'
            )

        # 3. Punkt im Legenden-Icon (falls `dot` ausgewählt ist)
        if "dot" in ctypes:
            cx_icon = lx + icon_w * 0.5
            cy_icon = ly - 5.5
            svg_parts.append(
                f'    <circle cx="{cx_icon:.1f}" cy="{cy_icon:.1f}" r="4.6" fill="{col}" stroke="#FFFFFF" stroke-width="1.2"/>'
            )

        text_x = lx + icon_w + 8.0
        svg_parts.append(f'    <text x="{text_x:.1f}" y="{ly:.1f}">{lbl}</text>')
    svg_parts.append("  </g>")

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)
