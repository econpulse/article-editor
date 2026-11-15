"""
LUKB Corporate Design SVG-Generator für den Inhaltsblock `custom_chart` (Daten-Diagramm aus Zwischenablage).
Erzeugt verzögerungsfrei und ohne externe Plotting-Abhängigkeiten druckfertige Vektor-SVGs
mit `Yoga Sans for LUKB` für Typst-PDF und Web-HTML5.

Unterstützt Wide-Format-Daten aus Excel / Zwischenablage:
1. `doughnut` & `pie` : Kuchen- & Ringdiagramme mit Prozentangaben und Legende
2. `category_bar`     : Kategorie-Säulendiagramme (gruppiert oder gestapelt) mit Legende
3. `timeseries`       : Zeitreihen-Visualisierungen mit Datumsachse und variablen Serien-Stilen
"""

from __future__ import annotations

import csv
import html
import io
import math
import re
from datetime import date, datetime
from typing import Any

from services.chart_generator import (
    FONT_BODY,
    FONT_HEADING,
    LUKB_CHART_PALETTE,
    _build_embedded_font_face_defs,
    _compute_nice_ticks,
    _compute_pretty_x_axis_ticks,
    _estimate_label_width_px,
    _format_ch_number,
    _render_empty_state_svg,
    resolve_chart_palette,
)


def parse_number(val: Any) -> float | None:
    """
    Normalisiert und parst Zahlenwerte aus Excel / TSV / CSV:
    - Unterstützt Schweizer Tausendertrenner (') und Leerzeichen (1'250.50 oder 1 250,50)
    - Unterstützt Prozentangaben (12.5% oder 12,5 %) -> 12.5
    - Unterstützt Buchhaltungs-Minus in Klammern (120.5) -> -120.5
    - Erkennt Komma vs. Punkt als Dezimaltrenner
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)

    s = str(val).strip()
    if not s or s in ("-", "–", "—", "n/a", "N/A", "null", "None"):
        return None

    # Prozentzeichen entfernen
    s = s.replace("%", "").strip()

    # Klammern für negative Werte: (123.45) -> -123.45
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1].strip()

    # Apostrophe und Leerzeichen entfernen (Schweizer Format 1'000.00 / 1 000,00)
    s = s.replace("'", "").replace("’", "").replace(" ", "").replace("\xa0", "")

    # Komma vs. Punkt behandeln
    if "," in s and "." in s:
        # z.B. 1,234.56 vs 1.234,56
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        f = float(s)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def parse_flexible_date(val: Any) -> date | None:
    """Parst Datumsangaben in gängigen Schweizer-, ISO- und Finanz-Formaten."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val

    s = str(val).strip()
    if not s:
        return None

    # ISO Format: YYYY-MM-DD
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", s):
        parts = [int(p) for p in s.split("-")]
        try:
            return date(parts[0], parts[1], parts[2])
        except ValueError:
            return None

    # CH/DE Format: DD.MM.YYYY oder D.M.YYYY
    if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", s):
        parts = [int(p) for p in s.split(".")]
        try:
            return date(parts[2], parts[1], parts[0])
        except ValueError:
            return None

    # Schrägstrich Format: YYYY/MM/DD oder DD/MM/YYYY
    if re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", s):
        parts = [int(p) for p in s.split("/")]
        try:
            return date(parts[0], parts[1], parts[2])
        except ValueError:
            return None
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", s):
        parts = [int(p) for p in s.split("/")]
        try:
            return date(parts[2], parts[1], parts[0])
        except ValueError:
            return None

    # Monat/Jahr: MM.YYYY oder MM/YYYY oder YYYY-MM
    m_my = re.match(r"^(\d{1,2})[./](\d{4})$", s)
    if m_my:
        try:
            return date(int(m_my.group(2)), int(m_my.group(1)), 1)
        except ValueError:
            return None

    m_ym = re.match(r"^(\d{4})-(\d{1,2})$", s)
    if m_ym:
        try:
            return date(int(m_ym.group(1)), int(m_ym.group(2)), 1)
        except ValueError:
            return None

    # Quartal: 2024-Q1, Q1 2024, 2024 Q1
    m_q1 = re.match(r"^(\d{4})[- /]?[Qq]([1-4])$", s)
    if m_q1:
        y, q = int(m_q1.group(1)), int(m_q1.group(2))
        return date(y, (q - 1) * 3 + 1, 1)
    m_q2 = re.match(r"^[Qq]([1-4])[- /]?(\d{4})$", s)
    if m_q2:
        q, y = int(m_q2.group(1)), int(m_q2.group(2))
        return date(y, (q - 1) * 3 + 1, 1)

    # Reines Jahr: 2020..2040
    if re.match(r"^\d{4}$", s):
        try:
            return date(int(s), 1, 1)
        except ValueError:
            return None

    return None


def parse_wide_tsv_data(raw_text: str, has_header: bool = True) -> tuple[list[str], list[list[str]]]:
    """
    Parst Tabellendaten im Wide-Format (Zwischenablage, TSV, CSV).
    Liefert (columns, rows).
    """
    text = (raw_text or "").strip()
    if not text:
        return [], []

    # Delimiter ermitteln (Tab, Semikolon oder Komma)
    first_line = text.split("\n")[0]
    if "\t" in first_line:
        delimiter = "\t"
    elif ";" in first_line:
        delimiter = ";"
    elif "," in first_line:
        delimiter = ","
    else:
        delimiter = "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows: list[list[str]] = []
    for row in reader:
        # Leere Zeilen überspringen
        if not row or all(not str(c).strip() for c in row):
            continue
        all_rows.append([str(c).strip() for c in row])

    if not all_rows:
        return [], []

    # Maximale Spaltenbreite ermitteln
    max_cols = max(len(r) for r in all_rows)
    # Alle Zeilen auf max_cols auffüllen
    normalized_rows = [r + [""] * (max_cols - len(r)) for r in all_rows]

    if has_header and len(normalized_rows) > 0:
        header_row = normalized_rows[0]
        data_rows = normalized_rows[1:]
        columns = [
            header_row[i] if header_row[i] else f"Spalte {i+1}"
            for i in range(max_cols)
        ]
    else:
        columns = [f"Spalte {i+1}" for i in range(max_cols)]
        data_rows = normalized_rows

    return columns, data_rows


def infer_chart_configuration(columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
    """
    Analysiert Spalten und Werte, um intelligente Defaults vorzuschlagen:
    - Spalte 1 = Datum -> 'timeseries'
    - 2 Spalten und Werte summiert ~100% -> 'doughnut'
    - Textspalte gefolgt von Werten -> 'category_bar'
    """
    if not columns or not rows:
        return {
            "chart_type": "category_bar",
            "x_col": "",
            "series": [],
        }

    x_col = columns[0]
    sample_col0 = [r[0] for r in rows[:15] if len(r) > 0 and r[0]]
    date_matches = sum(1 for v in sample_col0 if parse_flexible_date(v) is not None)
    is_timeseries = len(sample_col0) > 0 and (date_matches / len(sample_col0)) >= 0.6

    value_cols = columns[1:] if len(columns) > 1 else []

    if is_timeseries:
        chart_type = "timeseries"
    elif len(columns) == 2:
        # Prüfen ob Anteile/Summe ~ 100
        sample_vals = [parse_number(r[1]) for r in rows if len(r) > 1]
        valid_vals = [v for v in sample_vals if v is not None]
        total = sum(valid_vals)
        if len(valid_vals) >= 2 and (90.0 <= total <= 110.0 or 0.90 <= total <= 1.10):
            chart_type = "doughnut"
        else:
            chart_type = "category_bar"
    else:
        chart_type = "category_bar"

    series_items = [
        {
            "field": col,
            "label": col,
            "chart_type": "line" if chart_type == "timeseries" else "bar",
            "enabled": True,
        }
        for col in value_cols
    ]

    return {
        "chart_type": chart_type,
        "x_col": x_col,
        "series": series_items,
    }


def resolve_legend_columns(
    block_data: dict[str, Any],
    default_columns: int = 2,
) -> int:
    """
    Ermittelt die Anzahl der Spalten für die Legendeneinträge:
    - Benutzerdefiniert, falls konfiguriert (1..6)
    - Fallback: default_columns (1 bei Legende rechts, 2 bei Legende unterhalb)
    """
    user_val = block_data.get("legend_columns")
    if user_val is not None and user_val not in ("", "auto", 0):
        try:
            val = int(user_val)
            if 1 <= val <= 6:
                return val
        except (ValueError, TypeError):
            pass
    return default_columns


def _render_doughnut_pie_svg(
    block_data: dict[str, Any],
    columns: list[str],
    rows: list[list[str]],
    embed_fonts: bool = True,
) -> str:
    """Rendert ein Kuchen- oder Ringdiagramm (Pie/Doughnut) im LUKB Corporate Design."""
    # Loch-Prozentzahl berechnen: 0 = Klassischer Kuchen / Pie, >0 = Ringdiagramm / Doughnut
    raw_hole = block_data.get("doughnut_hole_pct")
    if raw_hole is not None:
        try:
            hole_pct = int(raw_hole)
        except (ValueError, TypeError):
            hole_pct = 0 if block_data.get("chart_type") == "pie" else 55
    else:
        hole_pct = 0 if block_data.get("chart_type") == "pie" else 55
    hole_pct = max(0, min(85, hole_pct))

    layout_mode = str(block_data.get("layout") or "column").strip()
    is_column = layout_mode != "full"
    active_palette = resolve_chart_palette(block_data)

    x_col = str(block_data.get("x_col") or (columns[0] if columns else "")).strip()
    x_idx = columns.index(x_col) if x_col in columns else 0

    # Wert-Spalte identifizieren (entweder erste aktivierte Serie oder Spalte nach X)
    val_idx = 1
    series_cfg = block_data.get("series") or []
    for s in series_cfg:
        field = s.get("field") if isinstance(s, dict) else getattr(s, "field", "")
        enabled = s.get("enabled", True) if isinstance(s, dict) else getattr(s, "enabled", True)
        if enabled and field in columns:
            val_idx = columns.index(field)
            break
    if val_idx == x_idx:
        val_idx = 1 if len(columns) > 1 else 0

    slices_raw: list[tuple[str, float]] = []
    for r in rows:
        if len(r) <= max(x_idx, val_idx):
            continue
        cat_label = str(r[x_idx]).strip()
        num_val = parse_number(r[val_idx])
        if num_val is not None and num_val > 0:
            slices_raw.append((cat_label if cat_label else "–", num_val))

    if not slices_raw:
        return _render_empty_state_svg(
            "Keine positiven Zahlenwerte für Kreisdiagramm gefunden",
            f"Spalte '{columns[val_idx] if val_idx < len(columns) else 'Wert'}' enthält keine positiven Zahlen.",
            embed_fonts=embed_fonts,
        )

    total_sum = sum(v for _, v in slices_raw)
    if total_sum <= 1e-9:
        total_sum = 1.0

    # Bis zu 7 Segmente direkt darstellen, Rest in "Übrige" zusammenfassen
    max_segments = 7
    if len(slices_raw) > max_segments:
        sorted_slices = sorted(slices_raw, key=lambda x: x[1], reverse=True)
        top_slices = sorted_slices[: max_segments - 1]
        other_sum = sum(v for _, v in sorted_slices[max_segments - 1 :])
        slices = top_slices + [("Übrige", other_sum)]
    else:
        slices = slices_raw

    svg_w = 680

    legend_pos = str(block_data.get("legend_position") or ("right" if not is_column else "bottom")).strip().lower()
    is_legend_right = legend_pos == "right"
    legend_cols = resolve_legend_columns(block_data, default_columns=1 if is_legend_right else 2)

    # Typografie abgestimmt auf Corporate Design: Legende darf nicht kleiner sein als Untertitel/Quelle (mind. 20.5 im Column-Layout)
    font_size_cat = 20.5 if is_column else 14.0
    font_size_val = 19.5 if is_column else 13.5
    row_height = 29.0 if is_column else 24.0

    # Höhe der Chartfläche aus Blockdaten auslesen und skalieren
    chart_height_mm_raw = block_data.get("chart_height_mm")
    try:
        chart_height_mm = float(chart_height_mm_raw) if chart_height_mm_raw is not None else 36.0
    except (ValueError, TypeError):
        chart_height_mm = 36.0
    chart_height_mm = max(20.0, min(120.0, round(chart_height_mm / 2.0) * 2.0))

    px_per_mm = (680.0 / 87.1778) if is_column else (680.0 / 180.0)
    target_plot_h = round(chart_height_mm * px_per_mm, 1)

    # Geometrie & Positionierung
    if is_legend_right:
        # Für jede Spalte die maximale Breite berechnen
        col_needed_widths = []
        for c in range(legend_cols):
            c_items = [slices[i] for i in range(c, len(slices), legend_cols)]
            if c_items:
                max_c_w = max(
                    _estimate_label_width_px(f"{l} ({(v / total_sum) * 100.0:.1f} %)", font_size_cat)
                    for l, v in c_items
                )
                col_needed_widths.append(max_c_w + 28.0)
            else:
                col_needed_widths.append(40.0)

        legend_needed_w = sum(col_needed_widths) + max(0, legend_cols - 1) * 16.0
        left_pad = 16.0
        circle_gap = 20.0
        right_pad = 28.0

        max_circle_w = max(80.0, svg_w - left_pad - circle_gap - right_pad - legend_needed_w)
        max_r_from_w = max_circle_w / 2.0
        max_r_from_h = (target_plot_h - 24.0) / 2.0
        r_outer = round(max(35.0, min(max_r_from_h, max_r_from_w)), 1)

        cx = round(left_pad + r_outer, 1)
        lx = round(cx + r_outer + circle_gap, 1)

        total_legend_rows = math.ceil(len(slices) / legend_cols)
        legend_total_h = total_legend_rows * row_height
        plot_h = max(target_plot_h, 2.0 * r_outer + 24.0, legend_total_h + 24.0)
        top_pad = 18.0
        center_y = top_pad + plot_h / 2.0

        cy = round(center_y, 1)
        legend_start_y = round(center_y - (legend_total_h / 2.0) + (row_height * 0.42), 1)
        svg_h = int(round(top_pad + plot_h + 16.0))
    else:
        # Kreis zentriert, Legende unterhalb
        cx = 340.0
        r_outer = round(max(50.0, min(220.0, (target_plot_h - 30.0) / 2.0)), 1)
        cy = round(20.0 + r_outer, 1)
        legend_start_y = round(cy + r_outer + 35.0, 1)

        total_legend_rows = math.ceil(len(slices) / legend_cols)
        legend_total_h = total_legend_rows * row_height
        margin = 16.0
        usable_w = svg_w - 2 * margin
        col_w = usable_w / legend_cols
        svg_h = int(round(max(legend_start_y + legend_total_h + 16.0, target_plot_h + legend_total_h + 40.0)))

    r_inner = r_outer * (hole_pct / 100.0)

    # Segmente berechnen
    current_angle = -math.pi / 2.0  # Start oben bei 12 Uhr
    paths: list[str] = []

    for idx, (label, val) in enumerate(slices):
        fraction = val / total_sum
        sweep_angle = fraction * 2.0 * math.pi
        start_angle = current_angle
        end_angle = current_angle + sweep_angle
        current_angle = end_angle

        # Punkte auf Außen- und Innenkreis
        x1_out = cx + r_outer * math.cos(start_angle)
        y1_out = cy + r_outer * math.sin(start_angle)
        x2_out = cx + r_outer * math.cos(end_angle)
        y2_out = cy + r_outer * math.sin(end_angle)

        large_arc = 1 if sweep_angle > math.pi else 0
        color = active_palette[idx % len(active_palette)]

        if math.isclose(fraction, 1.0, abs_tol=1e-5):
            # Voller Kreis
            if r_inner > 0:
                d = (
                    f"M {cx} {cy - r_outer} "
                    f"A {r_outer} {r_outer} 0 1 1 {cx} {cy + r_outer} "
                    f"A {r_outer} {r_outer} 0 1 1 {cx} {cy - r_outer} "
                    f"M {cx} {cy - r_inner} "
                    f"A {r_inner} {r_inner} 0 1 0 {cx} {cy + r_inner} "
                    f"A {r_inner} {r_inner} 0 1 0 {cx} {cy - r_inner} Z"
                )
            else:
                d = (
                    f"M {cx} {cy - r_outer} "
                    f"A {r_outer} {r_outer} 0 1 1 {cx} {cy + r_outer} "
                    f"A {r_outer} {r_outer} 0 1 1 {cx} {cy - r_outer} Z"
                )
        else:
            if r_inner > 0:
                x1_in = cx + r_inner * math.cos(start_angle)
                y1_in = cy + r_inner * math.sin(start_angle)
                x2_in = cx + r_inner * math.cos(end_angle)
                y2_in = cy + r_inner * math.sin(end_angle)
                d = (
                    f"M {x1_in:.2f} {y1_in:.2f} "
                    f"L {x1_out:.2f} {y1_out:.2f} "
                    f"A {r_outer} {r_outer} 0 {large_arc} 1 {x2_out:.2f} {y2_out:.2f} "
                    f"L {x2_in:.2f} {y2_in:.2f} "
                    f"A {r_inner} {r_inner} 0 {large_arc} 0 {x1_in:.2f} {y1_in:.2f} Z"
                )
            else:
                d = (
                    f"M {cx:.2f} {cy:.2f} "
                    f"L {x1_out:.2f} {y1_out:.2f} "
                    f"A {r_outer} {r_outer} 0 {large_arc} 1 {x2_out:.2f} {y2_out:.2f} Z"
                )

        paths.append(
            f'    <path d="{d}" fill="{color}" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round"/>'
        )

    # Legende berechnen
    legend_elements: list[str] = []

    if is_legend_right:
        for idx, (label, val) in enumerate(slices):
            color = active_palette[idx % len(active_palette)]
            c_idx = idx % legend_cols
            r_idx = idx // legend_cols
            col_offset = sum(col_needed_widths[k] + 16.0 for k in range(c_idx))
            item_lx = lx + col_offset
            ly = legend_start_y + r_idx * row_height
            pct_str = f"{(val / total_sum) * 100.0:.1f} %"
            safe_lbl = html.escape(label)

            legend_elements.append(
                f'    <rect x="{item_lx:.1f}" y="{ly - 13:.1f}" width="14" height="14" rx="2" fill="{color}"/>'
            )
            legend_elements.append(
                f'    <text x="{item_lx + 22:.1f}" y="{ly:.1f}" font-size="{font_size_cat}" fill="#002855" font-family="{FONT_HEADING}">'
                f'{safe_lbl} <tspan font-family="{FONT_BODY}" fill="#5A687C">({pct_str})</tspan></text>'
            )
        svg_h = max(svg_h, int(round(cy + r_outer + 25.0)), int(round(legend_start_y + total_legend_rows * row_height + 20.0)))
    else:
        for idx, (label, val) in enumerate(slices):
            color = active_palette[idx % len(active_palette)]
            r_idx = idx // legend_cols
            c_idx = idx % legend_cols
            clx = margin + c_idx * col_w
            ly = legend_start_y + r_idx * row_height
            pct_str = f"{(val / total_sum) * 100.0:.1f} %"
            safe_lbl = html.escape(label)

            legend_elements.append(
                f'    <rect x="{clx:.1f}" y="{ly - 13:.1f}" width="14" height="14" rx="2" fill="{color}"/>'
            )
            legend_elements.append(
                f'    <text x="{clx + 22:.1f}" y="{ly:.1f}" font-size="{font_size_cat}" fill="#002855" font-family="{FONT_HEADING}">'
                f'{safe_lbl} <tspan font-family="{FONT_BODY}" fill="#5A687C">({pct_str})</tspan></text>'
            )
        svg_h = max(svg_h, int(round(legend_start_y + total_legend_rows * row_height + 15.0)))

    # SVG assembeln (Kein Text im Loch des Pie/Doughnut)
    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}" font-family="{FONT_BODY}">',
    ]
    if embed_fonts:
        defs = _build_embedded_font_face_defs()
        if defs:
            svg_parts.append(defs)
    svg_parts.append(f'  <rect width="{svg_w}" height="{svg_h}" fill="#FFFFFF"/>')
    svg_parts.extend(paths)
    svg_parts.extend(legend_elements)
    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _split_long_category_word(word: str, max_w: float, font_size: float) -> list[str]:
    """Teilt ein überlanges Wort mit Trennstrichen auf, sodass Teilstücke max_w nicht überschreiten."""
    if _estimate_label_width_px(word, font_size) <= max_w:
        return [word]
    if "-" in word:
        parts = word.split("-")
        res: list[str] = []
        curr = ""
        for i, p in enumerate(parts):
            suffix = "-" if i < len(parts) - 1 else ""
            test_str = curr + p + suffix
            if curr and _estimate_label_width_px(test_str, font_size) > max_w:
                res.append(curr)
                curr = p + suffix
            else:
                curr = test_str
        if curr:
            res.append(curr)
        return res

    chunks: list[str] = []
    curr = ""
    for ch in word:
        if curr and _estimate_label_width_px(curr + ch + "-", font_size) > max_w:
            chunks.append(curr + "-")
            curr = ch
        else:
            curr += ch
    if curr:
        chunks.append(curr)
    return chunks


def _wrap_category_label(text: str, max_width_px: float, font_size: float, max_lines: int = 3) -> list[str]:
    """
    Bricht überlange Kategorienbeschriftungen intelligent auf mehrere Zeilen um.
    Verhindert Abschneiden mit Auslassungspunkten und nutzt verfügbare Zeilenbreite.
    """
    text = text.strip()
    if not text:
        return []
    if _estimate_label_width_px(text, font_size) <= max_width_px:
        return [text]

    raw_words = text.split()
    atomic_tokens: list[str] = []
    for w in raw_words:
        if _estimate_label_width_px(w, font_size) > max_width_px:
            atomic_tokens.extend(_split_long_category_word(w, max_width_px, font_size))
        else:
            atomic_tokens.append(w)

    lines: list[str] = []
    curr = ""
    for tok in atomic_tokens:
        sep = "" if curr.endswith("-") else (" " if curr else "")
        test_str = curr + sep + tok
        if curr and _estimate_label_width_px(test_str, font_size) > max_width_px:
            lines.append(curr)
            curr = tok
        else:
            curr = test_str
    if curr:
        lines.append(curr)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip("- ") + "…"

    return lines


def _render_vertical_category_bar_svg(
    block_data: dict[str, Any],
    columns: list[str],
    rows: list[list[str]],
    embed_fonts: bool = True,
) -> str:
    """Rendert ein vertikales Kategorie-Säulendiagramm (gruppiert oder gestapelt) mit Legende."""
    layout_mode = str(block_data.get("layout") or "column").strip()
    is_column = layout_mode != "full"
    bar_mode = str(block_data.get("bar_mode") or "grouped").strip()
    color_by_cat = bool(block_data.get("color_by_category", False))
    active_palette = resolve_chart_palette(block_data)

    x_col = str(block_data.get("x_col") or (columns[0] if columns else "")).strip()
    x_idx = columns.index(x_col) if x_col in columns else 0

    # Aktive Serien ermitteln
    series_cfg = block_data.get("series") or []
    active_series: list[dict[str, Any]] = []

    if series_cfg:
        for idx, s in enumerate(series_cfg):
            field = s.get("field") if isinstance(s, dict) else getattr(s, "field", "")
            enabled = s.get("enabled", True) if isinstance(s, dict) else getattr(s, "enabled", True)
            label = s.get("label") if isinstance(s, dict) else getattr(s, "label", "")
            if enabled and field in columns and field != x_col:
                active_series.append(
                    {
                        "field": field,
                        "col_idx": columns.index(field),
                        "label": label if label else field,
                        "color": active_palette[len(active_series) % len(active_palette)],
                    }
                )

    if not active_series:
        # Fallback: alle Spalten ausser X
        for col_i, col in enumerate(columns):
            if col_i != x_idx:
                active_series.append(
                    {
                        "field": col,
                        "col_idx": col_i,
                        "label": col,
                        "color": active_palette[len(active_series) % len(active_palette)],
                    }
                )

    if not active_series:
        return _render_empty_state_svg(
            "Keine Wert-Spalten ausgewählt",
            "Bitte wählen Sie mindestens eine Spalte für die Werte aus.",
            embed_fonts=embed_fonts,
        )

    # Daten extrahieren: [{category: "Aktien", values: [10.0, 15.0]}, ...]
    categories: list[dict[str, Any]] = []
    for r in rows:
        if len(r) <= x_idx:
            continue
        cat_name = str(r[x_idx]).strip()
        if not cat_name:
            continue
        vals: list[float] = []
        for s in active_series:
            c_idx = s["col_idx"]
            val_f = parse_number(r[c_idx]) if len(r) > c_idx else None
            vals.append(val_f if val_f is not None else 0.0)
        categories.append({"category": cat_name, "values": vals})

    if not categories:
        return _render_empty_state_svg(
            "Keine Datenzeilen vorhanden",
            "Fügen Sie Tabellendaten mit Kategorien und Werten ein.",
            embed_fonts=embed_fonts,
        )

    # Y-Wertebereich ermitteln
    y_candidates: list[float] = [0.0]
    if bar_mode == "stacked":
        for cat in categories:
            pos_sum = sum(v for v in cat["values"] if v >= 0)
            neg_sum = sum(v for v in cat["values"] if v < 0)
            y_candidates.append(pos_sum)
            if neg_sum < 0:
                y_candidates.append(neg_sum)
    else:
        for cat in categories:
            for v in cat["values"]:
                y_candidates.append(v)

    raw_min_y = min(y_candidates)
    raw_max_y = max(y_candidates)
    y_ticks = _compute_nice_ticks(raw_min_y, raw_max_y, target_ticks=5)
    y_min = y_ticks[0]
    y_max = y_ticks[-1]
    y_span = max(1e-9, y_max - y_min)
    y_step = y_ticks[1] - y_ticks[0] if len(y_ticks) > 1 else 1.0

    # Geometrie & Typografie
    axis_font_size = 20.5 if is_column else 14.0
    legend_font_size = 20.5 if is_column else 14.0

    y_tick_labels = [_format_ch_number(tick, y_step) for tick in y_ticks]
    max_y_label_w = max(
        (_estimate_label_width_px(lbl, axis_font_size) for lbl in y_tick_labels),
        default=16.0,
    )
    y_label_right_x = max(12.0, round(max_y_label_w, 1))
    y_axis_gap = 10.0 if is_column else 8.0

    chart_height_mm_raw = block_data.get("chart_height_mm")
    try:
        chart_height_mm = float(chart_height_mm_raw) if chart_height_mm_raw is not None else 36.0
    except (ValueError, TypeError):
        chart_height_mm = 36.0
    chart_height_mm = max(20.0, min(120.0, round(chart_height_mm / 2.0) * 2.0))

    px_per_mm = (680.0 / 87.1778) if is_column else (680.0 / 180.0)
    plot_h = round(chart_height_mm * px_per_mm, 1)

    svg_w = 680
    plot_left = y_label_right_x + y_axis_gap
    plot_right = 676.0
    plot_top = 18.0
    plot_bottom = plot_top + plot_h
    plot_w = plot_right - plot_left

    def y_px(val: float) -> float:
        clamped = max(y_min, min(y_max, val))
        return plot_bottom - ((clamped - y_min) / y_span) * plot_h

    zero_y = y_px(0.0)

    # Säulen-Geometrie
    n_cats = len(categories)
    cat_width = plot_w / max(1, n_cats)
    bar_padding = cat_width * 0.22
    usable_cat_w = cat_width - bar_padding * 2.0

    # Kategorienbeschriftung & Zeilenumbruch vorbereiten
    max_label_w = max(40.0, min(cat_width * 0.82, cat_width - 24.0))
    cat_label_font_size = axis_font_size - 1.0  # z.B. 19.5px in column, 13.0px in full
    label_line_h = round(cat_label_font_size * 1.15, 1)

    wrapped_categories: list[list[str]] = [
        _wrap_category_label(cat["category"], max_label_w, cat_label_font_size, max_lines=3)
        for cat in categories
    ]
    max_label_lines = max((len(lines) for lines in wrapped_categories), default=1)
    first_label_y = plot_bottom + 23.0
    axis_labels_bottom_y = first_label_y + (max_label_lines - 1) * label_line_h + 5.0

    bar_elements: list[str] = []
    x_axis_labels: list[str] = []

    for c_idx, cat in enumerate(categories):
        cx_left = plot_left + c_idx * cat_width + bar_padding
        center_x = cx_left + usable_cat_w / 2.0

        # Kategorien-Beschriftung (mit mehrzeiligem Umbruch statt Abschneiden)
        lines = wrapped_categories[c_idx]
        for l_idx, line_txt in enumerate(lines):
            line_y = first_label_y + l_idx * label_line_h
            safe_line = html.escape(line_txt)
            x_axis_labels.append(
                f'    <text x="{center_x:.1f}" y="{line_y:.1f}" text-anchor="middle" '
                f'font-size="{cat_label_font_size}" fill="#002855" font-family="{FONT_HEADING}">{safe_line}</text>'
            )

        if bar_mode == "stacked":
            pos_base_y = zero_y
            neg_base_y = zero_y
            for s_idx, s in enumerate(active_series):
                v = cat["values"][s_idx]
                if abs(v) < 1e-9:
                    continue
                color = active_palette[c_idx % len(active_palette)] if color_by_cat else s["color"]
                v_y = y_px(v)
                b_h = abs(zero_y - v_y)
                if v >= 0:
                    by = pos_base_y - b_h
                    pos_base_y = by
                else:
                    by = neg_base_y
                    neg_base_y = by + b_h
                bar_elements.append(
                    f'    <rect x="{cx_left:.1f}" y="{by:.1f}" width="{usable_cat_w:.1f}" height="{b_h:.1f}" '
                    f'fill="{color}" rx="1"/>'
                )
        else:
            # Gruppierte Säulen
            n_series = len(active_series)
            single_bar_w = usable_cat_w / max(1, n_series)
            for s_idx, s in enumerate(active_series):
                v = cat["values"][s_idx]
                color = active_palette[c_idx % len(active_palette)] if color_by_cat else s["color"]
                bx = cx_left + s_idx * single_bar_w
                b_h = abs(zero_y - y_px(v))
                by = y_px(v) if v >= 0 else zero_y
                bar_elements.append(
                    f'    <rect x="{bx:.1f}" y="{by:.1f}" width="{max(2.0, single_bar_w - 2.0):.1f}" height="{max(1.0, b_h):.1f}" '
                    f'fill="{color}" rx="2"/>'
                )

    # Legende (exakt vertikal zentriert zwischen Achsenbeschriftung und Quellenangabe)
    legend_elements: list[str] = []
    legend_rows = 0
    items_per_legend_row = resolve_legend_columns(block_data, default_columns=2)
    legend_row_gap = 28.0 if is_column else 22.0

    if color_by_cat and len(active_series) == 1:
        legend_rows = math.ceil(len(categories) / items_per_legend_row)
    elif len(active_series) > 1:
        legend_rows = math.ceil(len(active_series) / items_per_legend_row)

    if legend_rows > 0:
        desired_gap = 32.0 if is_column else 22.0
        external_gap = 12.0 if is_column else 8.0
        legend_top = axis_labels_bottom_y + desired_gap
        legend_start_y = round(legend_top + 13.0, 1)

        if color_by_cat and len(active_series) == 1:
            col_w = plot_w / items_per_legend_row
            for idx, cat in enumerate(categories):
                r_idx = idx // items_per_legend_row
                c_idx = idx % items_per_legend_row
                lx = plot_left + c_idx * col_w
                ly = legend_start_y + r_idx * legend_row_gap
                cat_color = active_palette[idx % len(active_palette)]
                safe_lbl = html.escape(cat["category"])
                legend_elements.append(
                    f'    <rect x="{lx:.1f}" y="{ly - 12:.1f}" width="14" height="14" rx="2" fill="{cat_color}"/>'
                )
                legend_elements.append(
                    f'    <text x="{lx + 22:.1f}" y="{ly:.1f}" font-size="{legend_font_size}" fill="#002855" font-family="{FONT_HEADING}">'
                    f'{safe_lbl}</text>'
                )
        elif len(active_series) > 1:
            col_w = plot_w / items_per_legend_row
            for idx, s in enumerate(active_series):
                r_idx = idx // items_per_legend_row
                c_idx = idx % items_per_legend_row
                lx = plot_left + c_idx * col_w
                ly = legend_start_y + r_idx * legend_row_gap
                safe_lbl = html.escape(s["label"])

                legend_elements.append(
                    f'    <rect x="{lx:.1f}" y="{ly - 12:.1f}" width="14" height="14" rx="2" fill="{s["color"]}"/>'
                )
                legend_elements.append(
                    f'    <text x="{lx + 22:.1f}" y="{ly:.1f}" font-size="{legend_font_size}" fill="#002855" font-family="{FONT_HEADING}">'
                    f'{safe_lbl}</text>'
                )

        legend_bottom = legend_start_y + (legend_rows - 1) * legend_row_gap + 4.0
        internal_bottom_pad = max(10.0, desired_gap - external_gap)
        svg_h = int(round(legend_bottom + internal_bottom_pad))
    else:
        svg_h = int(round(axis_labels_bottom_y + (20.0 if is_column else 14.0)))

    # SVG assembeln
    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}" font-family="{FONT_BODY}">',
    ]
    if embed_fonts:
        defs = _build_embedded_font_face_defs()
        if defs:
            svg_parts.append(defs)
    svg_parts.append(f'  <rect width="{svg_w}" height="{svg_h}" fill="#FFFFFF"/>')

    # Gitterlinien & Y-Achsen-Ticks
    for tick, lbl in zip(y_ticks, y_tick_labels):
        yp = y_px(tick)
        is_zero = math.isclose(tick, 0.0, abs_tol=1e-6)
        line_col = "#002855" if is_zero else "#E2E8F0"
        stroke_w = "1.5" if is_zero else "1.0"

        svg_parts.append(
            f'  <line x1="{plot_left:.1f}" y1="{yp:.1f}" x2="{plot_right:.1f}" y2="{yp:.1f}" stroke="{line_col}" stroke-width="{stroke_w}"/>'
        )
        svg_parts.append(
            f'  <text x="{y_label_right_x:.1f}" y="{yp + 6:.1f}" text-anchor="end" font-size="{axis_font_size}" fill="#5A687C">{lbl}</text>'
        )

    # Säulen & X-Labels
    svg_parts.extend(bar_elements)
    svg_parts.extend(x_axis_labels)
    svg_parts.extend(legend_elements)
    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _render_horizontal_bar_svg(
    block_data: dict[str, Any],
    columns: list[str],
    rows: list[list[str]],
    embed_fonts: bool = True,
) -> str:
    """Rendert ein horizontales Balkendiagramm (Balken von links nach rechts) mit Legende."""
    layout_mode = str(block_data.get("layout") or "column").strip()
    is_column = layout_mode != "full"
    color_by_cat = bool(block_data.get("color_by_category", False))
    active_palette = resolve_chart_palette(block_data)

    x_col = str(block_data.get("x_col") or (columns[0] if columns else "")).strip()
    x_idx = columns.index(x_col) if x_col in columns else 0

    # Aktive Serien ermitteln
    series_cfg = block_data.get("series") or []
    active_series: list[dict[str, Any]] = []

    if series_cfg:
        for idx, s in enumerate(series_cfg):
            field = s.get("field") if isinstance(s, dict) else getattr(s, "field", "")
            enabled = s.get("enabled", True) if isinstance(s, dict) else getattr(s, "enabled", True)
            label = s.get("label") if isinstance(s, dict) else getattr(s, "label", "")
            if enabled and field in columns and field != x_col:
                active_series.append(
                    {
                        "field": field,
                        "col_idx": columns.index(field),
                        "label": label if label else field,
                        "color": active_palette[len(active_series) % len(active_palette)],
                    }
                )

    if not active_series:
        for col_i, col in enumerate(columns):
            if col_i != x_idx:
                active_series.append(
                    {
                        "field": col,
                        "col_idx": col_i,
                        "label": col,
                        "color": active_palette[len(active_series) % len(active_palette)],
                    }
                )

    if not active_series:
        return _render_empty_state_svg(
            "Keine Wert-Spalten ausgewählt",
            "Bitte wählen Sie mindestens eine Spalte für die Werte aus.",
            embed_fonts=embed_fonts,
        )

    categories: list[dict[str, Any]] = []
    for r in rows:
        if len(r) <= x_idx:
            continue
        cat_name = str(r[x_idx]).strip()
        if not cat_name:
            continue
        vals: list[float] = []
        for s in active_series:
            c_idx = s["col_idx"]
            val_f = parse_number(r[c_idx]) if len(r) > c_idx else None
            vals.append(val_f if val_f is not None else 0.0)
        categories.append({"category": cat_name, "values": vals})

    if not categories:
        return _render_empty_state_svg(
            "Keine Datenzeilen vorhanden",
            "Fügen Sie Tabellendaten mit Kategorien und Werten ein.",
            embed_fonts=embed_fonts,
        )

    x_candidates: list[float] = [0.0]
    for cat in categories:
        for v in cat["values"]:
            x_candidates.append(v)

    raw_min_x = min(x_candidates)
    raw_max_x = max(x_candidates)
    x_ticks = _compute_nice_ticks(raw_min_x, raw_max_x, target_ticks=5)
    x_min = x_ticks[0]
    x_max = x_ticks[-1]
    x_span = max(1e-9, x_max - x_min)
    x_step = x_ticks[1] - x_ticks[0] if len(x_ticks) > 1 else 1.0

    axis_font_size = 20.0 if is_column else 14.0
    legend_font_size = 20.5 if is_column else 14.0

    # Breitenabschätzung der Kategorienamen auf der linken Seite
    max_cat_w = max(
        (_estimate_label_width_px(cat["category"], axis_font_size) for cat in categories),
        default=40.0,
    )
    plot_left = max(70.0, min(260.0, round(max_cat_w, 1) + 14.0))
    plot_right = 672.0
    plot_w = plot_right - plot_left
    plot_top = 18.0

    n_cats = max(1, len(categories))
    chart_height_mm_raw = block_data.get("chart_height_mm")
    try:
        chart_height_mm = float(chart_height_mm_raw) if chart_height_mm_raw is not None else 36.0
    except (ValueError, TypeError):
        chart_height_mm = 36.0
    chart_height_mm = max(20.0, min(120.0, round(chart_height_mm / 2.0) * 2.0))

    px_per_mm = (680.0 / 87.1778) if is_column else (680.0 / 180.0)
    target_plot_h = round(chart_height_mm * px_per_mm, 1)

    min_needed_h = n_cats * (24.0 if is_column else 18.0)
    plot_h = max(target_plot_h, min_needed_h)
    row_band_h = plot_h / n_cats
    plot_bottom = plot_top + plot_h

    def x_px(val: float) -> float:
        clamped = max(x_min, min(x_max, val))
        return plot_left + ((clamped - x_min) / x_span) * plot_w

    zero_x = x_px(0.0)
    svg_w = 680

    bar_elements: list[str] = []
    y_axis_labels: list[str] = []

    for c_idx, cat in enumerate(categories):
        band_top = plot_top + c_idx * row_band_h
        cat_center_y = band_top + row_band_h / 2.0
        safe_cat = html.escape(cat["category"])

        y_axis_labels.append(
            f'    <text x="{plot_left - 10:.1f}" y="{cat_center_y + 6:.1f}" text-anchor="end" '
            f'font-size="{axis_font_size}" fill="#002855" font-family="{FONT_HEADING}">{safe_cat}</text>'
        )

        n_series = len(active_series)
        single_bar_h = max(5.0, (row_band_h * 0.72) / max(1, n_series))

        for s_idx, s in enumerate(active_series):
            v = cat["values"][s_idx]
            color = active_palette[c_idx % len(active_palette)] if color_by_cat else s["color"]
            bx = min(zero_x, x_px(v))
            bw = abs(x_px(v) - zero_x)
            by = band_top + (row_band_h - n_series * single_bar_h) / 2.0 + s_idx * single_bar_h
            bar_elements.append(
                f'    <rect x="{bx:.1f}" y="{by:.1f}" width="{max(1.0, bw):.1f}" height="{max(2.0, single_bar_h - 2.0):.1f}" '
                f'fill="{color}" rx="2"/>'
            )

    # Legende (exakt vertikal zentriert zwischen Achsenbeschriftung und Quellenangabe)
    legend_elements: list[str] = []
    legend_rows = 0
    items_per_legend_row = resolve_legend_columns(block_data, default_columns=2)
    legend_row_gap = 28.0 if is_column else 22.0

    if color_by_cat and len(active_series) == 1:
        legend_rows = math.ceil(len(categories) / items_per_legend_row)
    elif len(active_series) > 1:
        legend_rows = math.ceil(len(active_series) / items_per_legend_row)

    if legend_rows > 0:
        desired_gap = 32.0 if is_column else 22.0
        external_gap = 12.0 if is_column else 8.0
        axis_labels_bottom_y = plot_bottom + 28.0
        legend_top = axis_labels_bottom_y + desired_gap
        legend_start_y = round(legend_top + 13.0, 1)

        if color_by_cat and len(active_series) == 1:
            col_w = plot_w / items_per_legend_row
            for idx, cat in enumerate(categories):
                r_idx = idx // items_per_legend_row
                c_idx = idx % items_per_legend_row
                lx = plot_left + c_idx * col_w
                ly = legend_start_y + r_idx * legend_row_gap
                cat_color = active_palette[idx % len(active_palette)]
                safe_lbl = html.escape(cat["category"])
                legend_elements.append(
                    f'    <rect x="{lx:.1f}" y="{ly - 12:.1f}" width="14" height="14" rx="2" fill="{cat_color}"/>'
                )
                legend_elements.append(
                    f'    <text x="{lx + 22:.1f}" y="{ly:.1f}" font-size="{legend_font_size}" fill="#002855" font-family="{FONT_HEADING}">'
                    f'{safe_lbl}</text>'
                )
        elif len(active_series) > 1:
            col_w = plot_w / items_per_legend_row
            for idx, s in enumerate(active_series):
                r_idx = idx // items_per_legend_row
                c_idx = idx % items_per_legend_row
                lx = plot_left + c_idx * col_w
                ly = legend_start_y + r_idx * legend_row_gap
                safe_lbl = html.escape(s["label"])
                legend_elements.append(
                    f'    <rect x="{lx:.1f}" y="{ly - 12:.1f}" width="14" height="14" rx="2" fill="{s["color"]}"/>'
                )
                legend_elements.append(
                    f'    <text x="{lx + 22:.1f}" y="{ly:.1f}" font-size="{legend_font_size}" fill="#002855" font-family="{FONT_HEADING}">'
                    f'{safe_lbl}</text>'
                )

        legend_bottom = legend_start_y + (legend_rows - 1) * legend_row_gap + 4.0
        internal_bottom_pad = max(10.0, desired_gap - external_gap)
        svg_h = int(round(legend_bottom + internal_bottom_pad))
    else:
        svg_h = int(round(plot_bottom + (42.0 if is_column else 32.0)))

    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}" font-family="{FONT_BODY}">',
    ]
    if embed_fonts:
        defs = _build_embedded_font_face_defs()
        if defs:
            svg_parts.append(defs)
    svg_parts.append(f'  <rect width="{svg_w}" height="{svg_h}" fill="#FFFFFF"/>')

    # Vertikale Gitterlinien & X-Ticks
    for tick in x_ticks:
        xp = x_px(tick)
        lbl = _format_ch_number(tick, x_step)
        is_zero = math.isclose(tick, 0.0, abs_tol=1e-6)
        line_col = "#002855" if is_zero else "#E2E8F0"
        stroke_w = "1.5" if is_zero else "1.0"
        svg_parts.append(
            f'  <line x1="{xp:.1f}" y1="{plot_top:.1f}" x2="{xp:.1f}" y2="{plot_bottom:.1f}" stroke="{line_col}" stroke-width="{stroke_w}"/>'
        )
        svg_parts.append(
            f'  <text x="{xp:.1f}" y="{plot_bottom + 23:.1f}" text-anchor="middle" font-size="{axis_font_size - 1.5}" fill="#5A687C">{lbl}</text>'
        )

    svg_parts.extend(bar_elements)
    svg_parts.extend(y_axis_labels)
    svg_parts.extend(legend_elements)
    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _render_category_bar_svg(
    block_data: dict[str, Any],
    columns: list[str],
    rows: list[list[str]],
    embed_fonts: bool = True,
) -> str:
    """Rendert ein Kategorie-Diagramm (vertikal als Säulen oder horizontal als Balken) mit Legende."""
    orientation = str(block_data.get("orientation") or "vertical").strip().lower()
    if orientation == "horizontal":
        return _render_horizontal_bar_svg(block_data, columns, rows, embed_fonts=embed_fonts)
    return _render_vertical_category_bar_svg(block_data, columns, rows, embed_fonts=embed_fonts)


def _render_timeseries_svg(
    block_data: dict[str, Any],
    columns: list[str],
    rows: list[list[str]],
    embed_fonts: bool = True,
) -> str:
    """Rendert ein Zeitreihendiagramm aus Wide-Format-Daten mit LUKB Vektorgrafik."""
    layout_mode = str(block_data.get("layout") or "column").strip()
    is_column = layout_mode != "full"
    active_palette = resolve_chart_palette(block_data)

    x_col = str(block_data.get("x_col") or (columns[0] if columns else "")).strip()
    x_idx = columns.index(x_col) if x_col in columns else 0

    # Aktive Serien ermitteln
    series_cfg = block_data.get("series") or []
    configured_series: list[dict[str, Any]] = []

    if series_cfg:
        for s in series_cfg:
            field = s.get("field") if isinstance(s, dict) else getattr(s, "field", "")
            enabled = s.get("enabled", True) if isinstance(s, dict) else getattr(s, "enabled", True)
            label = s.get("label") if isinstance(s, dict) else getattr(s, "label", "")
            ctype = s.get("chart_type") if isinstance(s, dict) else getattr(s, "chart_type", "line")
            if enabled and field in columns and field != x_col:
                configured_series.append(
                    {
                        "field": field,
                        "col_idx": columns.index(field),
                        "label": label if label else field,
                        "chart_type": ctype if ctype in ("line", "step", "dot", "area", "bar") else "line",
                        "color": active_palette[len(configured_series) % len(active_palette)],
                    }
                )

    if not configured_series:
        for col_i, col in enumerate(columns):
            if col_i != x_idx:
                configured_series.append(
                    {
                        "field": col,
                        "col_idx": col_i,
                        "label": col,
                        "chart_type": "line",
                        "color": active_palette[len(configured_series) % len(active_palette)],
                    }
                )

    if not configured_series:
        return _render_empty_state_svg(
            "Keine Zeitreihen-Spalten ausgewählt",
            "Wählen Sie mindestens eine Spalte für die Zeitreihe aus.",
            embed_fonts=embed_fonts,
        )

    # Datenpunkte nach Datum sortiert aufbauen: {field: [(date, val), ...]}
    series_points: dict[str, list[tuple[date, float]]] = {s["field"]: [] for s in configured_series}
    all_dates_set: set[date] = set()

    for r in rows:
        if len(r) <= x_idx:
            continue
        d_val = parse_flexible_date(r[x_idx])
        if not d_val:
            continue
        all_dates_set.add(d_val)
        for s in configured_series:
            c_idx = s["col_idx"]
            val_f = parse_number(r[c_idx]) if len(r) > c_idx else None
            if val_f is not None:
                series_points[s["field"]].append((d_val, val_f))

    # Sortieren
    for fld in series_points:
        series_points[fld].sort(key=lambda x: x[0])

    all_dates = sorted(all_dates_set)
    if len(all_dates) < 2:
        return _render_empty_state_svg(
            "Nicht genügend Datums-Punkte vorhanden",
            f"Spalte '{x_col}' muss mindestens 2 gültige Datumsangaben enthalten.",
            embed_fonts=embed_fonts,
        )

    min_date = all_dates[0]
    max_date = all_dates[-1]
    min_ord = float(min_date.toordinal())
    max_ord = float(max_date.toordinal())
    if math.isclose(min_ord, max_ord):
        min_ord -= 15.0
        max_ord += 15.0
    span_ord = max(1.0, max_ord - min_ord)

    # Y-Wertebereich
    y_candidates: list[float] = []
    for s in configured_series:
        for _, v in series_points[s["field"]]:
            y_candidates.append(v)

    if not y_candidates:
        return _render_empty_state_svg(
            "Keine numerischen Werte in den Zeitreihen",
            "Bitte prüfen Sie das Zahlenformat in den ausgewählten Wert-Spalten.",
            embed_fonts=embed_fonts,
        )

    raw_min_y = min(y_candidates)
    raw_max_y = max(y_candidates)
    y_ticks = _compute_nice_ticks(raw_min_y, raw_max_y, target_ticks=5)
    y_min = y_ticks[0]
    y_max = y_ticks[-1]
    y_span = max(1e-9, y_max - y_min)
    y_step = y_ticks[1] - y_ticks[0] if len(y_ticks) > 1 else 1.0

    # Geometrie
    axis_font_size = 22.5 if is_column else 14.5
    legend_font_size = 20.5 if is_column else 14.0

    y_tick_labels = [_format_ch_number(tick, y_step) for tick in y_ticks]
    max_y_label_w = max(
        (_estimate_label_width_px(lbl, axis_font_size) for lbl in y_tick_labels),
        default=16.0,
    )
    y_label_right_x = max(12.0, round(max_y_label_w, 1))
    y_axis_gap = 10.0 if is_column else 9.0

    chart_height_mm_raw = block_data.get("chart_height_mm")
    try:
        chart_height_mm = float(chart_height_mm_raw) if chart_height_mm_raw is not None else 36.0
    except (ValueError, TypeError):
        chart_height_mm = 36.0
    chart_height_mm = max(20.0, min(120.0, round(chart_height_mm / 2.0) * 2.0))

    px_per_mm = (680.0 / 87.1778) if is_column else (680.0 / 180.0)
    plot_h = round(chart_height_mm * px_per_mm, 1)

    svg_w = 680
    plot_left = y_label_right_x + y_axis_gap
    plot_right = 678.0
    plot_top = 18.0
    plot_bottom = plot_top + plot_h
    plot_w = plot_right - plot_left

    def x_px(dt: date) -> float:
        return plot_left + ((float(dt.toordinal()) - min_ord) / span_ord) * plot_w

    def y_px(val: float) -> float:
        clamped = max(y_min, min(y_max, val))
        return plot_bottom - ((clamped - y_min) / y_span) * plot_h

    zero_y = y_px(0.0)

    # Pfade rendern
    chart_paths: list[str] = []
    for s in configured_series:
        pts = series_points[s["field"]]
        if not pts:
            continue
        color = s["color"]
        ctype = s["chart_type"]

        # Fläche
        if ctype == "area":
            area_coords = [f"{x_px(d):.1f},{y_px(v):.1f}" for d, v in pts]
            first_x = x_px(pts[0][0])
            last_x = x_px(pts[-1][0])
            d_area = f"M {first_x:.1f},{zero_y:.1f} L " + " L ".join(area_coords) + f" L {last_x:.1f},{zero_y:.1f} Z"
            chart_paths.append(
                f'    <path d="{d_area}" fill="{color}" fill-opacity="0.18" stroke="none"/>'
            )

        # Linie oder Stufe
        if ctype in ("line", "area"):
            line_coords = [f"{x_px(d):.1f},{y_px(v):.1f}" for d, v in pts]
            d_line = "M " + " L ".join(line_coords)
            chart_paths.append(
                f'    <path d="{d_line}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        elif ctype == "step":
            step_segments: list[str] = [f"M {x_px(pts[0][0]):.1f},{y_px(pts[0][1]):.1f}"]
            for i in range(1, len(pts)):
                prev_d, prev_v = pts[i - 1]
                curr_d, curr_v = pts[i]
                step_segments.append(f"L {x_px(curr_d):.1f},{y_px(prev_v):.1f}")
                step_segments.append(f"L {x_px(curr_d):.1f},{y_px(curr_v):.1f}")
            chart_paths.append(
                f'    <path d="{" ".join(step_segments)}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="square"/>'
            )
        elif ctype == "bar":
            bar_w = max(2.5, min(24.0, (plot_w / len(pts)) * 0.65))
            for d, v in pts:
                xp = x_px(d) - bar_w / 2.0
                yp = y_px(v)
                bh = abs(zero_y - yp)
                by = yp if v >= 0 else zero_y
                chart_paths.append(
                    f'    <rect x="{xp:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{max(1.0, bh):.1f}" fill="{color}" rx="1"/>'
                )

        # Datenpunkte
        if ctype in ("dot", "line", "step") and len(pts) <= 30:
            for d, v in pts:
                chart_paths.append(
                    f'    <circle cx="{x_px(d):.1f}" cy="{y_px(v):.1f}" r="3.2" fill="{color}" stroke="#FFFFFF" stroke-width="1.2"/>'
                )

    # X-Achsen Ticks
    x_ticks_data = _compute_pretty_x_axis_ticks(min_date, max_date, is_column)
    x_axis_labels: list[str] = []
    x_label_y = plot_bottom + (31.0 if is_column else 24.0)

    for t_dt, lbl in x_ticks_data:
        xp = x_px(t_dt)
        svg_parts_tick = (
            f'    <line x1="{xp:.1f}" y1="{plot_bottom:.1f}" x2="{xp:.1f}" y2="{plot_bottom + 5:.1f}" stroke="#002855" stroke-width="1.0"/>'
            f'    <text x="{xp:.1f}" y="{x_label_y:.1f}" text-anchor="middle" font-size="{axis_font_size}" fill="#002855">{lbl}</text>'
        )
        x_axis_labels.append(svg_parts_tick)

    # Legende
    items_per_legend_row = resolve_legend_columns(block_data, default_columns=2)
    legend_rows = math.ceil(len(configured_series) / items_per_legend_row)
    legend_row_gap = 29.0 if is_column else 22.0
    legend_start_y = x_label_y + (34.0 if is_column else 27.0)

    legend_elements: list[str] = []
    col_w = plot_w / items_per_legend_row

    for idx, s in enumerate(configured_series):
        r_idx = idx // items_per_legend_row
        c_idx = idx % items_per_legend_row
        lx = plot_left + c_idx * col_w
        ly = legend_start_y + r_idx * legend_row_gap
        safe_lbl = html.escape(s["label"])

        # Legendensymbol passend zur Darstellungsart
        ctype = s["chart_type"]
        if ctype in ("line", "step", "area"):
            legend_elements.append(
                f'    <line x1="{lx:.1f}" y1="{ly - 5:.1f}" x2="{lx + 20:.1f}" y2="{ly - 5:.1f}" stroke="{s["color"]}" stroke-width="3" stroke-linecap="round"/>'
            )
            text_x = lx + 28
        else:
            legend_elements.append(
                f'    <rect x="{lx:.1f}" y="{ly - 12:.1f}" width="14" height="14" rx="2" fill="{s["color"]}"/>'
            )
            text_x = lx + 22

        legend_elements.append(
            f'    <text x="{text_x:.1f}" y="{ly:.1f}" font-size="{legend_font_size}" fill="#002855" font-family="{FONT_HEADING}">'
            f'{safe_lbl}</text>'
        )

    svg_h = int(round(legend_start_y + (legend_rows - 1) * legend_row_gap + (12.0 if is_column else 8.0)))

    # SVG assembeln
    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}" font-family="{FONT_BODY}">',
    ]
    if embed_fonts:
        defs = _build_embedded_font_face_defs()
        if defs:
            svg_parts.append(defs)
    svg_parts.append(f'  <rect width="{svg_w}" height="{svg_h}" fill="#FFFFFF"/>')

    # Y-Gitterlinien
    for tick, lbl in zip(y_ticks, y_tick_labels):
        yp = y_px(tick)
        is_zero = math.isclose(tick, 0.0, abs_tol=1e-6)
        line_col = "#002855" if is_zero else "#E2E8F0"
        stroke_w = "1.5" if is_zero else "1.0"
        svg_parts.append(
            f'  <line x1="{plot_left:.1f}" y1="{yp:.1f}" x2="{plot_right:.1f}" y2="{yp:.1f}" stroke="{line_col}" stroke-width="{stroke_w}"/>'
        )
        svg_parts.append(
            f'  <text x="{y_label_right_x:.1f}" y="{yp + 6:.1f}" text-anchor="end" font-size="{axis_font_size}" fill="#5A687C">{lbl}</text>'
        )

    # Pfade & Beschriftung
    svg_parts.extend(chart_paths)
    svg_parts.extend(x_axis_labels)
    svg_parts.extend(legend_elements)
    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def generate_custom_chart_svg(
    block_data: dict[str, Any],
    embed_fonts: bool = True,
) -> str:
    """
    Haupteinstiegspunkt: Generiert ein druckfertiges LUKB Corporate Design Vektor-SVG
    aus den Wide-Format-Daten eines `custom_chart`-Blocks.
    """
    raw_tsv = str(block_data.get("raw_tsv") or "").strip()
    has_header = bool(block_data.get("has_header", True))

    # Daten parsen (entweder neu aus raw_tsv oder aus vorab gespeicherten Feldern)
    if raw_tsv:
        columns, rows = parse_wide_tsv_data(raw_tsv, has_header=has_header)
    else:
        columns = list(block_data.get("data_columns") or [])
        rows = list(block_data.get("data_rows") or [])

    if not columns or not rows:
        return _render_empty_state_svg(
            "Keine Diagrammdaten vorhanden",
            "Kopieren Sie Daten aus Excel oder einer Tabelle in den Zwischenablagen-Bereich.",
            embed_fonts=embed_fonts,
        )

    chart_type = str(block_data.get("chart_type") or "category_bar").strip().lower()

    if chart_type in ("doughnut", "pie"):
        return _render_doughnut_pie_svg(block_data, columns, rows, embed_fonts=embed_fonts)
    elif chart_type == "timeseries":
        return _render_timeseries_svg(block_data, columns, rows, embed_fonts=embed_fonts)
    else:
        # category_bar (Standard)
        return _render_category_bar_svg(block_data, columns, rows, embed_fonts=embed_fonts)
