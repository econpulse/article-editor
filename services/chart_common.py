"""
Gemeinsames Chart-Modul für das LUKB Investment Office CMS:
- Corporate-Design-Farbpaletten & SVG-Schriftketten (`Yoga Sans for LUKB`)
- Thread-sicherer LRU-SVG-Cache (`ThreadSafeSvgCache`)
- Zahlen- & Datums-Parser (`parse_number`, `parse_flexible_date`)
- Achsen-, Tick- und Geometrie-Berechnungen
- Einheitliche Timeseries-SVG-Engine (`render_timeseries_svg`) für `db_chart` und `custom_chart`
"""

from __future__ import annotations

import base64
import html
import math
import re
import threading
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from config import (
    FONTS_DIR,
    LUKB_FONT_FAMILY_BASE,
    LUKB_FONT_LIGHT,
    LUKB_FONT_MEDIUM,
)

# Offizielle LUKB 5er-Farbpalette für bis zu 5 Zeitreihen (LUKB Standard)
LUKB_CHART_PALETTE: list[str] = [
    "#037FDA",
    "#9CD4FB",
    "#431231",
    "#BA249D",
    "#F07E2C",
]

CHART_PALETTES: dict[str, dict[str, Any]] = {
    "lukb_classic": {
        "label": "LUKB Standard",
        "colors": list(LUKB_CHART_PALETTE),
    },
    "lukb_blues": {
        "label": "Blau-Abstufung",
        "colors": ["#002855", "#005A9C", "#009FE3", "#5BB8E8", "#9BD3F2"],
    },
}

VALID_CHART_TYPES = ("line", "step", "dot", "area", "bar", "stacked_bar")

FONT_WEIGHT_BODY = "300"
FONT_WEIGHT_HEADING = "500"

_GENERIC_CSS_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"}


class ThreadSafeSvgCache:
    """Thread-sicherer In-Memory-LRU-Cache für generierte Chart-SVGs."""

    def __init__(self, max_size: int = 256) -> None:
        self._max_size = max_size
        self._lock = threading.Lock()
        self._store: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> str | None:
        with self._lock:
            val = self._store.get(key)
            if val is not None:
                self._store.move_to_end(key)
            return val

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._store


def resolve_chart_palette(block_data: dict[str, Any]) -> list[str]:
    """Löst die effektive 5-Farben-Palette eines Chart-Blocks auf."""
    palette_id = str(block_data.get("palette") or "lukb_classic").strip()
    preset = CHART_PALETTES.get(palette_id, CHART_PALETTES["lukb_classic"])
    return list(preset["colors"])


def compute_plot_height_px(block_data: dict[str, Any], is_column: bool) -> tuple[float, float]:
    """Berechnet (chart_height_mm, plot_h_px) aus der konfigurierten Chartfläche-Höhe in 2mm-Schritten."""
    chart_height_mm_raw = block_data.get("chart_height_mm")
    try:
        chart_height_mm = float(chart_height_mm_raw) if chart_height_mm_raw is not None else 36.0
    except (ValueError, TypeError):
        chart_height_mm = 36.0
    chart_height_mm = max(20.0, min(120.0, round(chart_height_mm / 2.0) * 2.0))
    px_per_mm = (680.0 / 87.1778) if is_column else (680.0 / 180.0)
    plot_h = round(chart_height_mm * px_per_mm, 1)
    return chart_height_mm, plot_h


def resolve_legend_columns(
    block_data: dict[str, Any],
    default_columns: int = 2,
) -> int:
    """Ermittelt die Spaltenanzahl für die Legende (1..6) oder liefert `default_columns`."""
    user_val = block_data.get("legend_columns")
    if user_val is not None and user_val not in ("", "auto", 0):
        try:
            val = int(user_val)
            if 1 <= val <= 6:
                return val
        except (ValueError, TypeError):
            pass
    return default_columns


def _quote_svg_font(name: str) -> str:
    """Formatiert einen Font-Namen CSS-/SVG-konform (Mehrwortnamen in einfachen Anführungszeichen)."""
    cleaned = name.strip().strip("'\"").replace('"', "").replace("'", "")
    if not cleaned:
        return ""
    if cleaned.lower() in _GENERIC_CSS_FAMILIES or " " not in cleaned:
        return cleaned
    return f"'{cleaned}'"


def _build_svg_font_stack(*families: str) -> str:
    """Erstellt eine deduplizierte SVG-font-family-Kette analog zu Typst und HTML5."""
    seen: set[str] = set()
    parts: list[str] = []
    for fam in families:
        formatted = _quote_svg_font(fam)
        if not formatted:
            continue
        key = formatted.lower()
        if key not in seen:
            seen.add(key)
            parts.append(formatted)
    return ", ".join(parts)


FONT_BODY = _build_svg_font_stack(
    LUKB_FONT_LIGHT,
    LUKB_FONT_FAMILY_BASE,
    "Calibri Light",
    "Calibri",
    "Arial",
    "sans-serif",
)
FONT_HEADING = _build_svg_font_stack(
    LUKB_FONT_MEDIUM,
    LUKB_FONT_FAMILY_BASE,
    "Calibri",
    "Arial",
    "sans-serif",
)

_FONT_MIME_FORMATS: dict[str, tuple[str, str]] = {
    ".woff2": ("font/woff2", "woff2"),
    ".woff": ("font/woff", "woff"),
    ".otf": ("font/otf", "opentype"),
    ".ttf": ("font/ttf", "truetype"),
}
_FONT_DEFS_CACHE: dict[tuple[str, tuple[tuple[str, int, int], ...]], str] = {}
_FONT_DEFS_LOCK = threading.Lock()


def _infer_corporate_font_faces(stem_lower: str) -> list[tuple[str, str]]:
    """Ordnet eine Corporate-Font-Datei anhand des Dateinamens den passenden CSS-Familien & Schnitten zu."""
    if "light" in stem_lower:
        return [
            (LUKB_FONT_LIGHT, FONT_WEIGHT_BODY),
            (LUKB_FONT_FAMILY_BASE, FONT_WEIGHT_BODY),
        ]
    if "medium" in stem_lower:
        return [
            (LUKB_FONT_MEDIUM, FONT_WEIGHT_HEADING),
            (LUKB_FONT_FAMILY_BASE, FONT_WEIGHT_HEADING),
        ]
    if "bold" in stem_lower:
        return [(LUKB_FONT_FAMILY_BASE, "700")]
    return [(LUKB_FONT_FAMILY_BASE, "400")]


def _build_embedded_font_face_defs(fonts_dir: Path | None = None) -> str:
    """Erzeugt optional einen SVG-<defs><style>-Block mit eingebetteten @font-face-Regeln."""
    target_dir = fonts_dir if fonts_dir is not None else FONTS_DIR
    if not target_dir or not target_dir.exists():
        return ""

    candidates: list[Path] = []
    for path in sorted(target_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _FONT_MIME_FORMATS:
            continue
        stem_low = path.stem.lower()
        if "yoga" in stem_low or "lukb" in stem_low:
            candidates.append(path)

    if not candidates:
        return ""

    sig = tuple(
        (p.name, st.st_mtime_ns, st.st_size)
        for p in candidates
        for st in (p.stat(),)
    )
    cache_key = (str(target_dir.resolve()), sig)
    with _FONT_DEFS_LOCK:
        cached = _FONT_DEFS_CACHE.get(cache_key)
        if cached is not None:
            return cached

    rules: list[str] = []
    for path in candidates:
        mime, fmt = _FONT_MIME_FORMATS[path.suffix.lower()]
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        data_uri = f"data:{mime};base64,{b64}"
        for family_name, weight in _infer_corporate_font_faces(path.stem.lower()):
            rules.append(
                f"      @font-face {{ font-family: '{family_name}'; font-weight: {weight}; "
                f"font-style: normal; src: url(\"{data_uri}\") format(\"{fmt}\"); }}"
            )

    defs_block = (
        "  <defs>\n    <style type=\"text/css\">\n"
        + "\n".join(rules)
        + "\n    </style>\n  </defs>"
    )
    with _FONT_DEFS_LOCK:
        _FONT_DEFS_CACHE[cache_key] = defs_block
    return defs_block


def open_svg_document(svg_w: int, svg_h: int, embed_fonts: bool = True) -> list[str]:
    """Erstellt den gemeinsamen SVG-Kopf inkl. optionaler Font-Definitionen und weissem Hintergrund."""
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}" font-family="{FONT_BODY}">',
    ]
    if embed_fonts:
        font_defs = _build_embedded_font_face_defs()
        if font_defs:
            parts.append(font_defs)
    parts.append(f'  <rect width="{svg_w}" height="{svg_h}" fill="#FFFFFF"/>')
    return parts


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

    s = s.replace("%", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1].strip()
    s = s.replace("'", "").replace("’", "").replace(" ", "").replace("\xa0", "")

    if "," in s and "." in s:
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

    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", s):
        parts = [int(p) for p in s.split("-")]
        try:
            return date(parts[0], parts[1], parts[2])
        except ValueError:
            return None

    if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", s):
        parts = [int(p) for p in s.split(".")]
        try:
            return date(parts[2], parts[1], parts[0])
        except ValueError:
            return None

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

    m_q1 = re.match(r"^(\d{4})[- /]?[Qq]([1-4])$", s)
    if m_q1:
        y, q = int(m_q1.group(1)), int(m_q1.group(2))
        return date(y, (q - 1) * 3 + 1, 1)
    m_q2 = re.match(r"^[Qq]([1-4])[- /]?(\d{4})$", s)
    if m_q2:
        q, y = int(m_q2.group(1)), int(m_q2.group(2))
        return date(y, (q - 1) * 3 + 1, 1)

    if re.match(r"^\d{4}$", s):
        try:
            return date(int(s), 1, 1)
        except ValueError:
            return None

    return None


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
    """Berechnet die Textbreite einer Zahl/Beschriftung in `Yoga Sans for LUKB Light` / `Calibri`."""
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
    if total_days >= 650:
        return dt.strftime("%Y")
    if total_days >= 90:
        return dt.strftime("%m.%Y")
    return dt.strftime("%d.%m.%y")


def _compute_pretty_x_axis_ticks(
    min_date: date,
    max_date: date,
    is_column_layout: bool = True,
) -> list[tuple[date, str]]:
    """Berechnet kalenderbasierte, regelmässige Ticks (Jahre, Quartale, Monate, Tage)."""
    total_days = max(1, (max_date - min_date).days)
    span_years = total_days / 365.25

    if total_days >= 650:
        if span_years <= 6.5:
            step_years = 1
        elif span_years <= 14.0:
            step_years = 2
        elif span_years <= 30.0:
            step_years = 5
        else:
            step_years = 10

        start_y = (min_date.year // step_years) * step_years
        ticks = [
            (date(y, 1, 1), str(y))
            for y in range(start_y, max_date.year + 2, step_years)
            if min_date <= date(y, 1, 1) <= max_date
        ]
        if len(ticks) >= 3 or (len(ticks) >= 2 and span_years < 3.0):
            return ticks
        if step_years > 1:
            ticks = [
                (date(y, 1, 1), str(y))
                for y in range(min_date.year, max_date.year + 2, 1)
                if min_date <= date(y, 1, 1) <= max_date
            ]
            if len(ticks) >= 2:
                return ticks

    if total_days >= 330:
        step_months = 6 if (total_days >= 500 or (is_column_layout and total_days >= 450)) else 3
        candidate_months = [1, 7] if step_months == 6 else [1, 4, 7, 10]
        ticks = []
        for y in range(min_date.year, max_date.year + 1):
            for m in candidate_months:
                dt = date(y, m, 1)
                if min_date <= dt <= max_date:
                    ticks.append((dt, dt.strftime("%m.%Y")))
        if len(ticks) >= 2:
            return ticks

    if total_days >= 90:
        step_m = 2 if (total_days >= 180 or (is_column_layout and total_days >= 140)) else 1
        ticks = []
        for y in range(min_date.year, max_date.year + 1):
            for m in range(1, 13, step_m):
                dt = date(y, m, 1)
                if min_date <= dt <= max_date:
                    ticks.append((dt, dt.strftime("%m.%Y")))
        if len(ticks) >= 2:
            return ticks

    if total_days >= 25:
        ticks = []
        for y in range(min_date.year, max_date.year + 1):
            for m in range(1, 13):
                for d in (1, 15):
                    try:
                        dt = date(y, m, d)
                        if min_date <= dt <= max_date:
                            ticks.append((dt, dt.strftime("%d.%m.%y")))
                    except ValueError:
                        pass
        if len(ticks) >= 2:
            return ticks

    step_d = max(1, total_days // (3 if is_column_layout else 5))
    ticks = []
    curr = min_date
    while curr <= max_date:
        ticks.append((curr, curr.strftime("%d.%m.%y")))
        curr += timedelta(days=step_d)
    if len(ticks) >= 2:
        return ticks

    return [
        (min_date, _format_date_tick(min_date, total_days)),
        (max_date, _format_date_tick(max_date, total_days)),
    ]


def _render_empty_state_svg(message: str, detail: str = "", embed_fonts: bool = True) -> str:
    esc_msg = html.escape(message)
    esc_det = html.escape(detail)
    font_defs = _build_embedded_font_face_defs() if embed_fonts else ""
    defs_part = f"\n{font_defs}" if font_defs else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 320" width="680" height="320" font-family="{FONT_BODY}">{defs_part}
  <rect width="680" height="320" fill="#FFFFFF"/>
  <rect x="2" y="20" width="676" height="280" rx="4" fill="#F4F7FA" stroke="#D6DEE8" stroke-dasharray="5,5"/>
  <text x="340" y="150" font-family="{FONT_HEADING}" font-weight="{FONT_WEIGHT_HEADING}" font-size="14" fill="#002855" text-anchor="middle">{esc_msg}</text>
  <text x="340" y="178" font-family="{FONT_BODY}" font-weight="{FONT_WEIGHT_BODY}" font-size="12.5" fill="#5A687C" text-anchor="middle">{esc_det}</text>
</svg>"""


def render_timeseries_svg(
    resolved_series: list[dict[str, Any]],
    block_data: dict[str, Any],
    is_column_layout: bool,
    embed_fonts: bool = True,
    rebasing: str = "none",
) -> str:
    """
    Gemeinsame Timeseries-SVG-Engine für `db_chart` und `custom_chart` im LUKB Corporate Design.
    Erwartet normalisierte Serien-Dictionaries mit `label`, `color`, `chart_types_set`, `points` und `points_map`.
    """
    all_dates: list[date] = sorted({d for s in resolved_series for d, _ in s["points"]})
    min_date = all_dates[0]
    max_date = all_dates[-1]
    min_ord = float(min_date.toordinal())
    max_ord = float(max_date.toordinal())

    has_bars = any(bool(s["chart_types_set"] & {"bar", "stacked_bar"}) for s in resolved_series)
    if math.isclose(min_ord, max_ord):
        min_ord -= 15.0
        max_ord += 15.0
    elif has_bars:
        pad_days = max(4.0, (max_ord - min_ord) * 0.045)
        min_ord -= pad_days
        max_ord += pad_days

    span_ord = max(1.0, max_ord - min_ord)

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

    axis_font_size = 22.5 if is_column_layout else 14.5
    legend_font_size = 20.5 if is_column_layout else 14.0
    default_leg_cols = 2 if is_column_layout else 3
    items_per_legend_row = resolve_legend_columns(block_data, default_columns=default_leg_cols)

    if len(resolved_series) < items_per_legend_row:
        items_per_legend_row = max(1, len(resolved_series))
    legend_rows = math.ceil(len(resolved_series) / items_per_legend_row)
    legend_row_gap = 29.0 if is_column_layout else 22.0

    y_tick_labels = [_format_ch_number(tick, y_step) for tick in y_ticks]
    max_y_label_w = max(
        (_estimate_label_width_px(lbl, axis_font_size) for lbl in y_tick_labels),
        default=16.0,
    )
    y_label_right_x = max(12.0, round(max_y_label_w, 1))
    y_axis_gap = 10.0 if is_column_layout else 9.0

    _, plot_h = compute_plot_height_px(block_data, is_column_layout)

    svg_w = 680
    plot_left = y_label_right_x + y_axis_gap
    plot_right = 678.0
    plot_top = 18.0
    plot_bottom = plot_top + plot_h
    plot_w = plot_right - plot_left

    x_axis_label_y = plot_bottom + (31.0 if is_column_layout else 24.0)
    legend_start_y = x_axis_label_y + (34.0 if is_column_layout else 27.0)
    svg_h = int(round(legend_start_y + (legend_rows - 1) * legend_row_gap + (10.0 if is_column_layout else 8.0)))

    def x_px(dt: date) -> float:
        return plot_left + ((float(dt.toordinal()) - min_ord) / span_ord) * plot_w

    def y_px(val: float) -> float:
        clamped = max(y_min, min(y_max, val))
        return plot_bottom - ((clamped - y_min) / y_span) * plot_h

    zero_y = y_px(0.0) if (y_min <= 0.0 <= y_max) else (plot_bottom if y_min > 0 else plot_top)

    svg_parts = open_svg_document(svg_w, svg_h, embed_fonts=embed_fonts)

    # Horizontale Gitterlinien & Y-Achsen-Labels
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
        f'  <g font-family="{FONT_BODY}" font-weight="{FONT_WEIGHT_BODY}" font-size="{axis_font_size}" fill="#5A687C" text-anchor="end">'
    )
    for tick, raw_lbl in zip(y_ticks, y_tick_labels):
        ty = y_px(tick)
        svg_parts.append(
            f'    <text x="{y_label_right_x:.1f}" y="{ty + y_text_offset:.1f}">{html.escape(raw_lbl)}</text>'
        )
    svg_parts.append("  </g>")

    # X-Achsen-Labels
    x_ticks_data = _compute_pretty_x_axis_ticks(min_date, max_date, is_column_layout)
    svg_parts.append(
        f'  <g font-family="{FONT_BODY}" font-weight="{FONT_WEIGHT_BODY}" font-size="{axis_font_size}" fill="#5A687C">'
    )
    for idx_t, (dt, lbl_raw) in enumerate(x_ticks_data):
        tx = x_px(dt)
        lbl = html.escape(lbl_raw)
        half_lbl_w = _estimate_label_width_px(lbl_raw, axis_font_size) * 0.5
        if idx_t == 0 and tx - half_lbl_w < 0.0:
            svg_parts.append(
                f'    <text x="{max(0.0, tx - half_lbl_w):.1f}" y="{x_axis_label_y:.1f}" text-anchor="start">{lbl}</text>'
            )
        elif idx_t == len(x_ticks_data) - 1 and tx + half_lbl_w > plot_right:
            svg_parts.append(
                f'    <text x="{plot_right:.1f}" y="{x_axis_label_y:.1f}" text-anchor="end">{lbl}</text>'
            )
        else:
            svg_parts.append(
                f'    <text x="{tx:.1f}" y="{x_axis_label_y:.1f}" text-anchor="middle">{lbl}</text>'
            )
    svg_parts.append("  </g>")

    # Ebene 1: AREA
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
                d_cmds = [f"M {x_px(pts[0][0]):.1f} {zero_y:.1f}", f"V {y_px(pts[0][1]):.1f}"]
                for i in range(1, len(pts)):
                    nx, ny = x_px(pts[i][0]), y_px(pts[i][1])
                    d_cmds.append(f"H {nx:.1f} V {ny:.1f}")
                d_cmds.append(f"V {zero_y:.1f} Z")
                svg_parts.append(f'  <path d="{" ".join(d_cmds)}" fill="{col}" fill-opacity="0.18"/>')
            else:
                poly_coords = [f"{x_px(pts[0][0]):.1f},{zero_y:.1f}"]
                line_coords = []
                for d, v in pts:
                    px, py = x_px(d), y_px(v)
                    poly_coords.append(f"{px:.1f},{py:.1f}")
                    line_coords.append(f"{px:.1f},{py:.1f}")
                poly_coords.append(f"{x_px(pts[-1][0]):.1f},{zero_y:.1f}")
                svg_parts.append(f'  <polygon points="{" ".join(poly_coords)}" fill="{col}" fill-opacity="0.18"/>')
                if "line" not in ctypes and "step" not in ctypes:
                    svg_parts.append(
                        f'  <polyline fill="none" stroke="{col}" stroke-width="2.6" '
                        f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(line_coords)}"/>'
                    )
        else:
            px, py = x_px(pts[0][0]), y_px(pts[0][1])
            svg_parts.append(f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{col}"/>')

    # Ebene 2 & 3: STACKED_BAR & BAR
    bar_series = [
        s for s in resolved_series if "bar" in s["chart_types_set"] and "stacked_bar" not in s["chart_types_set"]
    ]
    if stacked_series or bar_series:
        bar_dates = sorted({d for s in (stacked_series + bar_series) for d, _ in s["points"]})
        if len(bar_dates) >= 2:
            diffs = [
                abs(x_px(bar_dates[i + 1]) - x_px(bar_dates[i]))
                for i in range(len(bar_dates) - 1)
                if abs(x_px(bar_dates[i + 1]) - x_px(bar_dates[i])) > 0.5
            ]
            min_dx = min(diffs) if diffs else 60.0
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

    # Ebene 4: STEP
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

    # Ebene 5: LINE
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

    # Ebene 6: DOT
    dot_r = "5.0" if is_column_layout else "4.0"
    for s in resolved_series:
        if "dot" not in s["chart_types_set"]:
            continue
        pts = s["points"]
        col = s["color"]
        svg_parts.append(f'  <g fill="{col}" stroke="#FFFFFF" stroke-width="1.4">')
        for d, v in pts:
            svg_parts.append(f'    <circle cx="{x_px(d):.1f}" cy="{y_px(v):.1f}" r="{dot_r}"/>')
        svg_parts.append("  </g>")

    # Legende
    legend_left_x = 0.0
    col_step = (plot_right - legend_left_x) / max(1, items_per_legend_row)
    max_label_chars = 27 if is_column_layout else 34

    svg_parts.append(
        f'  <g font-family="{FONT_HEADING}" font-weight="{FONT_WEIGHT_HEADING}" font-size="{legend_font_size}" fill="#1A2433">'
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

        if "bar" in ctypes or "stacked_bar" in ctypes:
            svg_parts.append(
                f'    <rect x="{lx:.1f}" y="{icon_top:.1f}" width="{icon_w - 4:.1f}" height="{icon_h:.1f}" rx="1.5" fill="{col}"/>'
            )
        elif "area" in ctypes:
            svg_parts.append(
                f'    <rect x="{lx:.1f}" y="{icon_top:.1f}" width="{icon_w:.1f}" height="{icon_h:.1f}" '
                f'fill="{col}" fill-opacity="0.24"/>'
            )

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
