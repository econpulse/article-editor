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


def resolve_explicit_legend_columns(block_data: dict[str, Any]) -> int | None:
    """Liefert eine explizit gesetzte Spaltenanzahl (1..6) oder `None` bei 'auto'."""
    user_val = block_data.get("legend_columns")
    if user_val is not None and user_val not in ("", "auto", 0, "none"):
        try:
            val = int(user_val)
            if 1 <= val <= 6:
                return val
        except (ValueError, TypeError):
            pass
    return None


def resolve_show_legend(block_data: dict[str, Any]) -> bool:
    """Ermittelt, ob eine Legende gerendert werden soll (Default: True)."""
    raw = block_data.get("show_legend")
    if raw is not None:
        if raw is False or (isinstance(raw, str) and raw.strip().lower() in ("false", "0", "no", "none", "off")):
            return False
        if raw == 0:
            return False
    leg_pos = str(block_data.get("legend_position") or "").strip().lower()
    if leg_pos == "none":
        return False
    leg_cols = block_data.get("legend_columns")
    if leg_cols is not None and (leg_cols == 0 or (isinstance(leg_cols, str) and leg_cols.strip().lower() == "none")):
        return False
    return True


def compute_legend_item_positions(
    item_widths: list[float],
    max_width: float,
    item_gap: float = 22.0,
    explicit_columns: int | None = None,
) -> list[tuple[float, int]]:
    """
    Berechnet `(x_offset, row_idx)` für horizontale Legendeneinträge.

    - Bei `explicit_columns is None` (Auto): Kompaktes Flow-Wrap anhand der tatsächlichen
      Textbreiten + `item_gap` mit automatischem Zeilenumbruch bei `max_width`.
    - Bei `explicit_columns >= 1`: Feste Spaltenzahl, aber jede Spalte ist nur so breit
      wie ihr längster Eintrag + `item_gap` (vertikal bündig ohne unnötige Leerräume).
    """
    if not item_widths:
        return []

    if explicit_columns is None:
        positions: list[tuple[float, int]] = []
        cur_x = 0.0
        row_idx = 0
        for w in item_widths:
            if cur_x > 0.0 and cur_x + w > max_width:
                row_idx += 1
                cur_x = 0.0
            positions.append((cur_x, row_idx))
            cur_x += w + item_gap
        return positions

    cols = max(1, min(explicit_columns, len(item_widths)))
    if cols == 1:
        return [(0.0, idx) for idx in range(len(item_widths))]

    col_widths = [
        max(item_widths[i] for i in range(c, len(item_widths), cols))
        for c in range(cols)
    ]
    total_w = sum(col_widths) + (cols - 1) * item_gap
    eff_gap = item_gap
    if total_w > max_width and cols > 1:
        avail_for_gaps = max(0.0, max_width - sum(col_widths))
        eff_gap = avail_for_gaps / (cols - 1) if avail_for_gaps > 0.0 else 8.0

    col_x: list[float] = []
    acc = 0.0
    for c in range(cols):
        col_x.append(acc)
        acc += col_widths[c] + eff_gap

    return [(col_x[idx % cols], idx // cols) for idx in range(len(item_widths))]


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


def normalize_y_axis_config(axis_cfg: Any) -> tuple[float | None, float | None, float | None]:
    """Extrahiert (min, max, step) aus einer optionalen Y-Achsen-Konfiguration (dict oder Objekt)."""
    if axis_cfg is None:
        return None, None, None

    def _opt_float(key: str) -> float | None:
        raw = axis_cfg.get(key) if isinstance(axis_cfg, dict) else getattr(axis_cfg, key, None)
        if raw is None or raw == "":
            return None
        try:
            f = float(raw)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None

    c_min = _opt_float("min")
    c_max = _opt_float("max")
    c_step = _opt_float("step")
    if c_step is not None and c_step <= 0:
        c_step = None
    return c_min, c_max, c_step


def _compute_aligned_nice_ticks(
    min_val: float,
    max_val: float,
    interval_count: int,
) -> tuple[list[float], float, float, float]:
    """
    Berechnet schöne Pretty-Break-Ticks mit exakt `interval_count` Intervallen
    (also `interval_count + 1` Ticks), sodass die rechte Y-Achse exakt auf den
    horizontalen Gitterlinien der linken Y-Achse liegt.
    """
    n_int = max(1, int(interval_count))
    if min_val > max_val:
        min_val, max_val = max_val, min_val
    if math.isclose(min_val, max_val, abs_tol=1e-9):
        delta = abs(min_val) * 0.1 if abs(min_val) > 1e-6 else 1.0
        min_val -= delta
        max_val += delta

    span = max(1e-9, max_val - min_val)
    raw_step = span / n_int
    mag = 10.0 ** math.floor(math.log10(raw_step))

    chosen_step = raw_step
    chosen_min = min_val
    for factor in (1.0, 2.0, 2.5, 5.0, 10.0, 20.0, 25.0, 50.0, 100.0):
        cand_step = factor * mag
        cand_min = math.floor(min_val / cand_step) * cand_step
        cand_max = cand_min + n_int * cand_step
        if cand_max >= max_val - cand_step * 1e-6:
            chosen_step = cand_step
            chosen_min = cand_min
            break

    ticks = [round(chosen_min + i * chosen_step, 8) for i in range(n_int + 1)]
    return ticks, ticks[0], ticks[-1], chosen_step


def _resolve_axis_scale(
    raw_min_y: float,
    raw_max_y: float,
    axis_cfg: Any = None,
    target_ticks: int = 5,
    align_intervals: int | None = None,
) -> tuple[list[float], float, float, float]:
    """
    Berechnet (ticks, y_min, y_max, y_step) unter Berücksichtigung optionaler manueller
    Vorgaben für min, max und step. Ist `align_intervals` gesetzt und keine manuelle
    Vorgabe aktiv, werden Pretty-Breaks mit exakt `align_intervals` Intervallen erzeugt.
    """
    c_min, c_max, c_step = normalize_y_axis_config(axis_cfg)
    if c_min is None and c_max is None and c_step is None:
        if align_intervals is not None and align_intervals >= 1:
            return _compute_aligned_nice_ticks(raw_min_y, raw_max_y, align_intervals)
        ticks = _compute_nice_ticks(raw_min_y, raw_max_y, target_ticks=target_ticks)
        y_min = ticks[0]
        y_max = ticks[-1]
        y_step = ticks[1] - ticks[0] if len(ticks) > 1 else 1.0
        return ticks, y_min, y_max, y_step

    eff_min = c_min if c_min is not None else raw_min_y
    eff_max = c_max if c_max is not None else raw_max_y

    if eff_min >= eff_max:
        if c_min is not None and c_max is None:
            eff_max = eff_min + (abs(eff_min) * 0.1 if abs(eff_min) > 1e-6 else 1.0)
        elif c_max is not None and c_min is None:
            eff_min = eff_max - (abs(eff_max) * 0.1 if abs(eff_max) > 1e-6 else 1.0)
        else:
            eff_min, eff_max = raw_min_y, raw_max_y
            if eff_min >= eff_max:
                delta = abs(eff_min) * 0.1 if abs(eff_min) > 1e-6 else 1.0
                eff_min -= delta
                eff_max += delta
            c_min = None
            c_max = None

    span = max(1e-9, eff_max - eff_min)
    step = c_step if c_step is not None else _nice_step(span, target_ticks=target_ticks)
    if step <= 0 or math.isnan(step) or math.isinf(step):
        step = _nice_step(span, target_ticks=target_ticks)

    if span / step > 25.0:
        if c_step is not None:
            mult = math.ceil((span / step) / 20.0)
            step = step * max(1, mult)
        else:
            step = _nice_step(span, target_ticks=target_ticks)

    tick_start = eff_min if c_min is not None else math.floor(eff_min / step) * step
    tick_end = eff_max if c_max is not None else math.ceil(eff_max / step) * step

    ticks: list[float] = []
    curr = tick_start
    safety = 0
    while curr <= tick_end + step * 1e-6 and safety < 30:
        ticks.append(round(curr, 8))
        curr += step
        safety += 1

    if len(ticks) < 2:
        ticks = [round(tick_start, 8), round(tick_end, 8)]

    y_min = eff_min if c_min is not None else ticks[0]
    y_max = eff_max if c_max is not None else ticks[-1]
    if y_min >= y_max:
        y_max = y_min + step
    return ticks, y_min, y_max, step


def _count_needed_decimals(val: float, max_check: int = 6) -> int:
    """Ermittelt die minimale Anzahl an Nachkommastellen für val (bis max_check)."""
    if math.isnan(val) or math.isinf(val) or abs(val) < 1e-9:
        return 0
    for d in range(max_check):
        if abs(val - round(val, d)) < 1e-6:
            return d
    return max_check


def _format_single_ch_number(val: float, decimals: int = 0) -> str:
    """Formatiert eine einzelne Zahl mit fixer Dezimalstellenanzahl im Schweizer Format."""
    if math.isnan(val) or math.isinf(val):
        return ""
    if abs(val) < 1e-9:
        val = 0.0
    if decimals <= 0:
        int_val = int(round(val))
        return f"{int_val:,}".replace(",", "'")
    rounded = round(val, decimals)
    if abs(rounded) < 1e-9:
        rounded = 0.0
    return f"{rounded:,.{decimals}f}".replace(",", "'")


def format_axis_ticks(
    ticks: list[float] | tuple[float, ...],
    step: float | None = None,
) -> list[str]:
    """
    Formatiert eine Liste von Achsenticks einheitlich im Schweizer Zahlenformat:
    - Alle Ticks erhalten dieselbe Anzahl an Nachkommastellen (wie die Zahl, die die meisten benötigt).
    - Berücksichtigt Schweizer Tausendertrenner (') und Vorzeichen.
    """
    if not ticks:
        return []

    needed = [_count_needed_decimals(t) for t in ticks]
    if step is not None and not math.isnan(step) and not math.isinf(step) and step > 0:
        needed.append(_count_needed_decimals(step))
    decimals = max(needed) if needed else 0

    return [_format_single_ch_number(t, decimals=decimals) for t in ticks]


def _format_ch_number(val: float, step: float = 1.0, decimals: int | None = None) -> str:
    """
    Formatiert eine Zahl im Schweizer Zahlenformat.
    Wenn `decimals` angegeben ist, wird diese Nachkommastellenanzahl verwendet.
    Andernfalls wird die benötigte Anzahl anhand von `step` und `val` ermittelt.
    """
    if decimals is not None:
        return _format_single_ch_number(val, decimals=decimals)

    needed = _count_needed_decimals(val)
    if step > 0 and not math.isnan(step) and not math.isinf(step):
        needed = max(needed, _count_needed_decimals(step))
    return _format_single_ch_number(val, decimals=needed)


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

    left_series = [s for s in resolved_series if s.get("y_axis") != "right"]
    right_series = [s for s in resolved_series if s.get("y_axis") == "right"]
    has_left_axis = len(left_series) > 0
    has_right_axis = len(right_series) > 0

    def _compute_series_y_range(series_list: list[dict[str, Any]]) -> tuple[float, float]:
        y_cands: list[float] = []
        for s in series_list:
            if "stacked_bar" not in s["chart_types_set"] or len(s["chart_types_set"]) > 1:
                for _, v in s["points"]:
                    y_cands.append(v)

        stacked = [s for s in series_list if "stacked_bar" in s["chart_types_set"]]
        if stacked:
            stacked_dates = sorted({d for s in stacked for d, _ in s["points"]})
            for dt in stacked_dates:
                pos_sum = sum(
                    s["points_map"][dt]
                    for s in stacked
                    if dt in s["points_map"] and s["points_map"][dt] >= 0
                )
                neg_sum = sum(
                    s["points_map"][dt]
                    for s in stacked
                    if dt in s["points_map"] and s["points_map"][dt] < 0
                )
                y_cands.append(pos_sum)
                if neg_sum < 0:
                    y_cands.append(neg_sum)

        if any(bool(s["chart_types_set"] & {"bar", "stacked_bar"}) for s in series_list):
            y_cands.append(0.0)
        if rebasing == "index_100":
            y_cands.append(100.0)

        return (min(y_cands) if y_cands else 0.0), (max(y_cands) if y_cands else 100.0)

    axis_font_size = 22.5 if is_column_layout else 14.5
    legend_font_size = 20.5 if is_column_layout else 14.0
    show_legend = resolve_show_legend(block_data)
    explicit_leg_cols = resolve_explicit_legend_columns(block_data)
    legend_row_gap = 29.0 if is_column_layout else 22.0
    y_axis_gap = 10.0 if is_column_layout else 9.0

    if has_left_axis:
        raw_min_l, raw_max_l = _compute_series_y_range(left_series)
        y_ticks_left, y_min_left, y_max_left, y_step_left = _resolve_axis_scale(
            raw_min_l, raw_max_l, block_data.get("y_axis_left"), target_ticks=5
        )
        y_span_left = max(1e-9, y_max_left - y_min_left)
        y_tick_labels_left = format_axis_ticks(y_ticks_left, y_step_left)
        max_y_left_w = max(
            (_estimate_label_width_px(lbl, axis_font_size) for lbl in y_tick_labels_left),
            default=16.0,
        )
        y_left_label_right_x = max(12.0, round(max_y_left_w, 1))
        plot_left = y_left_label_right_x + y_axis_gap
    else:
        y_ticks_left, y_min_left, y_max_left, y_step_left = [0.0, 100.0], 0.0, 100.0, 100.0
        y_span_left = 100.0
        y_tick_labels_left = []
        y_left_label_right_x = 0.0
        plot_left = 10.0

    svg_w = 680
    if has_right_axis:
        raw_min_r, raw_max_r = _compute_series_y_range(right_series)
        left_intervals = (len(y_ticks_left) - 1) if (has_left_axis and len(y_ticks_left) >= 2) else None
        y_ticks_right, y_min_right, y_max_right, y_step_right = _resolve_axis_scale(
            raw_min_r,
            raw_max_r,
            block_data.get("y_axis_right"),
            target_ticks=5,
            align_intervals=left_intervals,
        )
        y_span_right = max(1e-9, y_max_right - y_min_right)
        y_tick_labels_right = format_axis_ticks(y_ticks_right, y_step_right)
        max_y_right_w = max(
            (_estimate_label_width_px(lbl, axis_font_size) for lbl in y_tick_labels_right),
            default=16.0,
        )
        y_right_label_left_x = round(svg_w - 2.0 - max(12.0, max_y_right_w), 1)
        plot_right = y_right_label_left_x - y_axis_gap
    else:
        y_ticks_right, y_min_right, y_max_right, y_step_right = [0.0, 100.0], 0.0, 100.0, 100.0
        y_span_right = 100.0
        y_tick_labels_right = []
        y_right_label_left_x = float(svg_w)
        plot_right = 678.0

    _, plot_h = compute_plot_height_px(block_data, is_column_layout)

    plot_top = 18.0
    plot_bottom = plot_top + plot_h
    plot_w = max(40.0, plot_right - plot_left)

    x_axis_label_y = plot_bottom + (31.0 if is_column_layout else 24.0)
    legend_start_y = x_axis_label_y + (34.0 if is_column_layout else 27.0)

    legend_left_x = 0.0
    max_label_chars = 27 if is_column_layout else 34
    icon_w = 24.0 if is_column_layout else 19.0
    icon_h = 13.0 if is_column_layout else 11.0
    icon_text_gap = 8.0
    legend_item_gap = 24.0 if is_column_layout else 18.0

    legend_positions: list[tuple[float, int]] = []
    if show_legend and resolved_series:
        leg_widths = [
            icon_w + icon_text_gap + _estimate_label_width_px(s["label"][:max_label_chars], legend_font_size)
            for s in resolved_series
        ]
        legend_positions = compute_legend_item_positions(
            item_widths=leg_widths,
            max_width=plot_right - legend_left_x,
            item_gap=legend_item_gap,
            explicit_columns=explicit_leg_cols,
        )
        legend_rows = max(r for _, r in legend_positions) + 1
        svg_h = int(round(legend_start_y + (legend_rows - 1) * legend_row_gap + (10.0 if is_column_layout else 8.0)))
    else:
        svg_h = int(round(x_axis_label_y + (12.0 if is_column_layout else 10.0)))

    def x_px(dt: date) -> float:
        return plot_left + ((float(dt.toordinal()) - min_ord) / span_ord) * plot_w

    def y_px_for(axis: str, val: float) -> float:
        if axis == "right" and has_right_axis:
            return plot_bottom - ((val - y_min_right) / y_span_right) * plot_h
        return plot_bottom - ((val - y_min_left) / y_span_left) * plot_h

    def zero_y_for(axis: str) -> float:
        if axis == "right" and has_right_axis:
            return y_px_for("right", 0.0) if (y_min_right <= 0.0 <= y_max_right) else (plot_bottom if y_min_right > 0 else plot_top)
        return y_px_for("left", 0.0) if (y_min_left <= 0.0 <= y_max_left) else (plot_bottom if y_min_left > 0 else plot_top)

    svg_parts = open_svg_document(svg_w, svg_h, embed_fonts=embed_fonts)
    axes_meta_payload = {
        "left": {"min": round(y_min_left, 8), "max": round(y_max_left, 8), "step": round(y_step_left, 8)} if has_left_axis else None,
        "right": {"min": round(y_min_right, 8), "max": round(y_max_right, 8), "step": round(y_step_right, 8)} if has_right_axis else None,
    }
    import json as _json_mod
    axes_meta_attr = html.escape(_json_mod.dumps(axes_meta_payload, separators=(",", ":")))
    svg_parts[0] = svg_parts[0].replace("<svg ", f'<svg data-axes-meta="{axes_meta_attr}" ', 1)
    svg_parts.append(
        f'  <defs><clipPath id="lukb-plot-clip">'
        f'<rect x="{plot_left - 2.0:.1f}" y="{plot_top - 6.0:.1f}" width="{plot_w + 4.0:.1f}" height="{plot_h + 12.0:.1f}"/>'
        f'</clipPath></defs>'
    )

    # Horizontale Gitterlinien (orientiert an primärer/linker Achse, oder rechter Achse falls keine Serie links)
    grid_axis = "left" if has_left_axis else "right"
    grid_ticks = y_ticks_left if has_left_axis else y_ticks_right
    svg_parts.append('  <g stroke="#E2E8F0" stroke-width="1">')
    for tick in grid_ticks:
        ty = y_px_for(grid_axis, tick)
        is_zero = abs(tick) < 1e-9
        stroke_col = "#94A3B8" if is_zero else "#E2E8F0"
        stroke_w = "1.4" if is_zero else "1"
        svg_parts.append(
            f'    <line x1="{plot_left:.1f}" y1="{ty:.1f}" x2="{plot_right:.1f}" y2="{ty:.1f}" '
            f'stroke="{stroke_col}" stroke-width="{stroke_w}"/>'
        )
    svg_parts.append("  </g>")

    if rebasing == "index_100" and has_left_axis and y_min_left < 100.0 < y_max_left:
        y100 = y_px_for("left", 100.0)
        svg_parts.append(
            f'  <line x1="{plot_left:.1f}" y1="{y100:.1f}" x2="{plot_right:.1f}" y2="{y100:.1f}" '
            f'stroke="#64748B" stroke-width="1.1" stroke-dasharray="4,3"/>'
        )

    y_text_offset = 7.0 if is_column_layout else 5.0
    if has_left_axis:
        svg_parts.append(
            f'  <g font-family="{FONT_BODY}" font-weight="{FONT_WEIGHT_BODY}" font-size="{axis_font_size}" fill="#5A687C" text-anchor="end">'
        )
        for tick, raw_lbl in zip(y_ticks_left, y_tick_labels_left):
            ty = y_px_for("left", tick)
            svg_parts.append(
                f'    <text x="{y_left_label_right_x:.1f}" y="{ty + y_text_offset:.1f}">{html.escape(raw_lbl)}</text>'
            )
        svg_parts.append("  </g>")

    if has_right_axis:
        svg_parts.append(
            f'  <g font-family="{FONT_BODY}" font-weight="{FONT_WEIGHT_BODY}" font-size="{axis_font_size}" fill="#5A687C" text-anchor="start">'
        )
        for tick, raw_lbl in zip(y_ticks_right, y_tick_labels_right):
            ty = y_px_for("right", tick)
            svg_parts.append(
                f'    <text x="{y_right_label_left_x:.1f}" y="{ty + y_text_offset:.1f}">{html.escape(raw_lbl)}</text>'
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

    # Daten-Ebenen (geclippt auf Plot-Fläche bei manuellen Min/Max-Grenzen)
    svg_parts.append('  <g clip-path="url(#lukb-plot-clip)">')

    # Ebene 1: AREA
    for s in resolved_series:
        ctypes = s["chart_types_set"]
        if "area" not in ctypes:
            continue
        pts = s["points"]
        if not pts:
            continue
        col = s["color"]
        ax = s.get("y_axis", "left")
        z_y = zero_y_for(ax)
        if len(pts) >= 2:
            if "step" in ctypes:
                d_cmds = [f"M {x_px(pts[0][0]):.1f} {z_y:.1f}", f"V {y_px_for(ax, pts[0][1]):.1f}"]
                for i in range(1, len(pts)):
                    nx, ny = x_px(pts[i][0]), y_px_for(ax, pts[i][1])
                    d_cmds.append(f"H {nx:.1f} V {ny:.1f}")
                d_cmds.append(f"V {z_y:.1f} Z")
                svg_parts.append(f'    <path d="{" ".join(d_cmds)}" fill="{col}" fill-opacity="0.18"/>')
            else:
                poly_coords = [f"{x_px(pts[0][0]):.1f},{z_y:.1f}"]
                line_coords = []
                for d, v in pts:
                    px, py = x_px(d), y_px_for(ax, v)
                    poly_coords.append(f"{px:.1f},{py:.1f}")
                    line_coords.append(f"{px:.1f},{py:.1f}")
                poly_coords.append(f"{x_px(pts[-1][0]):.1f},{z_y:.1f}")
                svg_parts.append(f'    <polygon points="{" ".join(poly_coords)}" fill="{col}" fill-opacity="0.18"/>')
                if "line" not in ctypes and "step" not in ctypes:
                    svg_parts.append(
                        f'    <polyline fill="none" stroke="{col}" stroke-width="2.6" '
                        f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(line_coords)}"/>'
                    )
        else:
            px, py = x_px(pts[0][0]), y_px_for(ax, pts[0][1])
            svg_parts.append(f'    <circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{col}"/>')

    # Ebene 2 & 3: STACKED_BAR & BAR
    stacked_left = [s for s in left_series if "stacked_bar" in s["chart_types_set"]]
    stacked_right = [s for s in right_series if "stacked_bar" in s["chart_types_set"]]
    bar_series = [
        s for s in resolved_series if "bar" in s["chart_types_set"] and "stacked_bar" not in s["chart_types_set"]
    ]
    if stacked_left or stacked_right or bar_series:
        all_bar_series = stacked_left + stacked_right + bar_series
        bar_dates = sorted({d for s in all_bar_series for d, _ in s["points"]})
        if len(bar_dates) >= 2:
            diffs = [
                abs(x_px(bar_dates[i + 1]) - x_px(bar_dates[i]))
                for i in range(len(bar_dates) - 1)
                if abs(x_px(bar_dates[i + 1]) - x_px(bar_dates[i])) > 0.5
            ]
            min_dx = min(diffs) if diffs else 60.0
        else:
            min_dx = 60.0

        slot_count = (1 if stacked_left else 0) + (1 if stacked_right else 0) + len(bar_series)
        cluster_w = max(6.0, min(46.0, min_dx * 0.68))
        single_bar_w = max(3.0, cluster_w / max(1, slot_count))

        for dt in bar_dates:
            cx = x_px(dt)
            cluster_left = cx - (cluster_w / 2.0)
            slot_idx = 0

            for st_axis, st_group in (("left", stacked_left), ("right", stacked_right)):
                if not st_group:
                    continue
                bx = cluster_left + slot_idx * single_bar_w
                pos_cursor = 0.0
                neg_cursor = 0.0
                for s in st_group:
                    val = s["points_map"].get(dt)
                    if val is None or abs(val) < 1e-12:
                        continue
                    if val >= 0:
                        y_start = y_px_for(st_axis, pos_cursor + val)
                        y_end = y_px_for(st_axis, pos_cursor)
                        pos_cursor += val
                    else:
                        y_start = y_px_for(st_axis, neg_cursor)
                        y_end = y_px_for(st_axis, neg_cursor + val)
                        neg_cursor += val
                    rect_h = max(1.0, abs(y_end - y_start))
                    rect_top = min(y_start, y_end)
                    svg_parts.append(
                        f'    <rect x="{bx:.1f}" y="{rect_top:.1f}" width="{max(2.0, single_bar_w - 0.8):.1f}" '
                        f'height="{rect_h:.1f}" fill="{s["color"]}" rx="1"/>'
                    )
                slot_idx += 1

            for s in bar_series:
                val = s["points_map"].get(dt)
                if val is not None:
                    ax = s.get("y_axis", "left")
                    bx = cluster_left + slot_idx * single_bar_w
                    vy = y_px_for(ax, val)
                    z_y = zero_y_for(ax)
                    rect_top = min(vy, z_y)
                    rect_h = max(1.5, abs(z_y - vy))
                    svg_parts.append(
                        f'    <rect x="{bx:.1f}" y="{rect_top:.1f}" width="{max(2.0, single_bar_w - 1.0):.1f}" '
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
        ax = s.get("y_axis", "left")
        if len(pts) >= 2:
            d_cmds = [f"M {x_px(pts[0][0]):.1f} {y_px_for(ax, pts[0][1]):.1f}"]
            for i in range(1, len(pts)):
                nx, ny = x_px(pts[i][0]), y_px_for(ax, pts[i][1])
                d_cmds.append(f"H {nx:.1f} V {ny:.1f}")
            svg_parts.append(
                f'    <path d="{" ".join(d_cmds)}" fill="none" stroke="{col}" '
                f'stroke-width="{stroke_w_main}" stroke-linejoin="round" stroke-linecap="round"/>'
            )
        else:
            px, py = x_px(pts[0][0]), y_px_for(ax, pts[0][1])
            svg_parts.append(f'    <circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{col}"/>')

    # Ebene 5: LINE
    for s in resolved_series:
        if "line" not in s["chart_types_set"]:
            continue
        pts = s["points"]
        if not pts:
            continue
        col = s["color"]
        ax = s.get("y_axis", "left")
        if len(pts) >= 2:
            coords = [f"{x_px(d):.1f},{y_px_for(ax, v):.1f}" for d, v in pts]
            svg_parts.append(
                f'    <polyline fill="none" stroke="{col}" stroke-width="{stroke_w_main}" '
                f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(coords)}"/>'
            )
        else:
            px, py = x_px(pts[0][0]), y_px_for(ax, pts[0][1])
            svg_parts.append(f'    <circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{col}"/>')

    # Ebene 6: DOT
    dot_r = "5.0" if is_column_layout else "4.0"
    for s in resolved_series:
        if "dot" not in s["chart_types_set"]:
            continue
        pts = s["points"]
        col = s["color"]
        ax = s.get("y_axis", "left")
        svg_parts.append(f'    <g fill="{col}" stroke="#FFFFFF" stroke-width="1.4">')
        for d, v in pts:
            svg_parts.append(f'      <circle cx="{x_px(d):.1f}" cy="{y_px_for(ax, v):.1f}" r="{dot_r}"/>')
        svg_parts.append("    </g>")

    svg_parts.append("  </g>")

    # Legende
    if show_legend and legend_positions:
        svg_parts.append(
            f'  <g font-family="{FONT_HEADING}" font-weight="{FONT_WEIGHT_HEADING}" font-size="{legend_font_size}" fill="#1A2433">'
        )
        for idx, s in enumerate(resolved_series):
            x_off, row_num = legend_positions[idx]
            lx = legend_left_x + x_off
            ly = legend_start_y + row_num * legend_row_gap
            col = s["color"]
            ctypes = s["chart_types_set"]
            lbl = html.escape(s["label"][:max_label_chars])

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

            text_x = lx + icon_w + icon_text_gap
            svg_parts.append(f'    <text x="{text_x:.1f}" y="{ly:.1f}">{lbl}</text>')
        svg_parts.append("  </g>")

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)
