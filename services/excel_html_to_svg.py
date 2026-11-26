"""
Konvertiert kopierte Excel-Tabellenbereiche (text/html aus der Zwischenablage)
über Typst in ein verlustfreies Vektor-SVG.
"""

from __future__ import annotations

import re
from typing import Any

import lxml.html
import typst

_NAMED_COLORS: dict[str, str] = {
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#FF0000",
    "green": "#008000",
    "blue": "#0000FF",
    "navy": "#000080",
    "gray": "#808080",
    "grey": "#808080",
    "silver": "#C0C0C0",
    "maroon": "#800000",
    "purple": "#800080",
    "teal": "#008080",
    "aqua": "#00FFFF",
    "cyan": "#00FFFF",
    "yellow": "#FFFF00",
    "orange": "#FFA500",
    "lime": "#00FF00",
    "windowtext": "#1A2433",
    "window": "#FFFFFF",
}

_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
_HEX_COLOR_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_RGB_COLOR_RE = re.compile(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", re.IGNORECASE)
_LENGTH_RE = re.compile(r"([0-9]*\.?[0-9]+)\s*(pt|px)?", re.IGNORECASE)


def _escape_typst_text(text: str) -> str:
    """Escaped Typst-Sonderzeichen innerhalb von Markup-Blöcken [...]."""
    if not text:
        return ""
    replacements = {
        "\\": "\\\\",
        "#": "\\#",
        "$": "\\$",
        "*": "\\*",
        "_": "\\_",
        "`": "\\`",
        "<": "\\<",
        ">": "\\>",
        "@": "\\@",
        "[": "\\[",
        "]": "\\]",
    }
    out: list[str] = []
    for ch in text:
        out.append(replacements.get(ch, ch))
    return "".join(out)


def _parse_color(raw: str | None) -> str | None:
    """Normalisiert CSS-Farbangaben zu '#RRGGBB' oder None."""
    if not raw:
        return None
    val = raw.strip().lower()
    if val in ("none", "transparent", "auto", "initial", "inherit", ""):
        return None
    m_hex = _HEX_COLOR_RE.search(val)
    if m_hex:
        h = m_hex.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return f"#{h.upper()}"
    m_rgb = _RGB_COLOR_RE.search(val)
    if m_rgb:
        r = max(0, min(255, int(m_rgb.group(1))))
        g = max(0, min(255, int(m_rgb.group(2))))
        b = max(0, min(255, int(m_rgb.group(3))))
        return f"#{r:02X}{g:02X}{b:02X}"
    for token in re.split(r"\s+", val):
        if token in _NAMED_COLORS:
            return _NAMED_COLORS[token]
    return None


def _parse_pt(raw: str | None, default: float | None = None) -> float | None:
    if not raw:
        return default
    val = raw.strip().lower()
    if val == "thin":
        return 0.5
    if val == "medium":
        return 1.0
    if val == "thick":
        return 1.5
    m = _LENGTH_RE.search(val)
    if not m:
        return default
    num = float(m.group(1))
    unit = (m.group(2) or "pt").lower()
    if unit == "px":
        num *= 0.75
    return num


def _parse_declarations(decl_str: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for item in decl_str.split(";"):
        if ":" not in item:
            continue
        k, v = item.split(":", 1)
        key = k.strip().lower()
        val = v.strip()
        if key and val:
            props[key] = val
    return props


def _extract_css_rules(html_str: str) -> dict[str, dict[str, str]]:
    """Extrahiert CSS-Regeln aus <style>-Blöcken (inkl. Excel .xl*-Klassen)."""
    rules: dict[str, dict[str, str]] = {}
    for block in _STYLE_BLOCK_RE.findall(html_str):
        cleaned = re.sub(r"<!--|-->", "", block)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
        for sel_group, decls in _CSS_RULE_RE.findall(cleaned):
            parsed = _parse_declarations(decls)
            if not parsed:
                continue
            for sel in sel_group.split(","):
                s = sel.strip().lower()
                if not s:
                    continue
                target = rules.setdefault(s, {})
                target.update(parsed)
    return rules


def _parse_border_side(raw: str | None) -> str | None:
    """Konvertiert eine CSS-Border-Angabe in einen Typst-Stroke-Ausdruck oder 'none'."""
    if not raw:
        return None
    val = raw.strip().lower()
    if val in ("none", "0", "0pt", "0px", "hidden"):
        return "none"

    width_pt = _parse_pt(val, default=0.5)
    if width_pt is not None and width_pt <= 0:
        return "none"
    width_pt = max(0.35, min(3.0, width_pt or 0.5))

    color = _parse_color(val) or "#1A2433"
    dash = None
    if "dashed" in val:
        dash = '"dashed"'
    elif "dotted" in val:
        dash = '"dotted"'

    if dash:
        return f"(paint: rgb(\"{color}\"), thickness: {width_pt:.2f}pt, dash: {dash})"
    return f"{width_pt:.2f}pt + rgb(\"{color}\")"


def _resolve_element_style(
    el: lxml.html.HtmlElement,
    css_rules: dict[str, dict[str, str]],
    inherited: dict[str, str] | None = None,
) -> dict[str, str]:
    style: dict[str, str] = dict(inherited or {})
    tag = str(el.tag).lower()
    if tag in css_rules:
        style.update(css_rules[tag])

    cls_attr = el.get("class") or ""
    for cls_name in cls_attr.split():
        key = f".{cls_name.strip().lower()}"
        if key in css_rules:
            style.update(css_rules[key])
        tag_key = f"{tag}{key}"
        if tag_key in css_rules:
            style.update(css_rules[tag_key])

    # Legacy HTML-Attribute
    if el.get("bgcolor"):
        style["background-color"] = el.get("bgcolor") or ""
    if el.get("align"):
        style["text-align"] = el.get("align") or ""
    if el.get("valign"):
        style["vertical-align"] = el.get("valign") or ""
    if el.get("color"):
        style["color"] = el.get("color") or ""

    inline = el.get("style")
    if inline:
        style.update(_parse_declarations(inline))

    return style


def _render_inline_runs_to_typst(
    el: lxml.html.HtmlElement,
    css_rules: dict[str, dict[str, str]],
    parent_style: dict[str, str],
) -> str:
    """Rendert den Inhalt einer Tabellenzelle inkl. Inline-Formatierungen als Typst-Markup."""
    parts: list[str] = []
    if el.text:
        parts.append(_escape_typst_text(el.text))

    for child in el:
        tag = str(child.tag).lower()
        if tag == "br":
            parts.append(" \\\n")
        else:
            child_style = _resolve_element_style(child, css_rules, {})
            inner = _render_inline_runs_to_typst(child, css_rules, child_style)
            if inner:
                is_bold = tag in ("b", "strong") or _is_bold(child_style)
                is_italic = tag in ("i", "em") or _is_italic(child_style)
                is_under = tag == "u" or ("underline" in child_style.get("text-decoration", "").lower())
                col = _parse_color(child_style.get("color"))
                sz = _parse_pt(child_style.get("font-size"))

                wrapped = inner
                if is_under:
                    wrapped = f"#underline[{wrapped}]"
                text_args: list[str] = []
                if is_bold:
                    text_args.append('weight: "bold"')
                if is_italic:
                    text_args.append('style: "italic"')
                if col:
                    text_args.append(f'fill: rgb("{col}")')
                if sz and 6.0 <= sz <= 24.0:
                    text_args.append(f"size: {sz:.1f}pt")
                if text_args:
                    wrapped = f"#text({', '.join(text_args)})[{wrapped}]"
                parts.append(wrapped)

        if child.tail:
            parts.append(_escape_typst_text(child.tail))

    return "".join(parts).strip()


def _is_bold(style: dict[str, str]) -> bool:
    fw = style.get("font-weight", "").strip().lower()
    if fw in ("bold", "bolder"):
        return True
    try:
        return int(fw) >= 600
    except ValueError:
        return False


def _is_italic(style: dict[str, str]) -> bool:
    fs = style.get("font-style", "").strip().lower()
    return fs in ("italic", "oblique")


_NUMERIC_CELL_RE = re.compile(
    r"^[+\-−]?\s*(?:CHF|EUR|USD|GBP|JPY|%)?\s*\d[\d\s'.,]*\s*(?:%|bp|bps|CHF|EUR|USD)?$"
)


def _parse_dimension_pt(style_val: str | None, attr_val: str | None, min_pt: float, max_pt: float) -> float | None:
    raw = style_val or attr_val
    if not raw:
        return None
    val_pt = _parse_pt(raw)
    if val_pt is None:
        return None
    # HTML width/height-Attribute ohne Einheit sind Pixel -> in pt umrechnen
    if not style_val and attr_val and not re.search(r"[a-zA-Z]", attr_val):
        val_pt *= 0.75
    return max(min_pt, min(max_pt, val_pt))


def _extract_font_families(raw_ff: str | None) -> list[str]:
    if not raw_ff:
        return []
    out: list[str] = []
    for part in raw_ff.split(","):
        cleaned = part.strip().strip('"').strip("'").strip()
        if cleaned and cleaned.lower() not in ("sans-serif", "serif", "monospace", "inherit", "initial"):
            out.append(cleaned)
    return out


def _find_excel_table(doc: lxml.html.HtmlElement) -> lxml.html.HtmlElement | None:
    tables = doc.xpath("descendant-or-self::table")
    if not tables:
        return None
    table = tables[0]
    rows = table.xpath(".//tr")
    if not rows:
        return None
    cells = table.xpath(".//td | .//th")
    if not cells:
        return None
    has_text = any((c.text_content() or "").strip() for c in cells)
    has_img = bool(table.xpath(".//img"))
    if has_img and not has_text:
        return None
    if not has_text:
        return None
    return table


def is_excel_html_table(html_str: str) -> bool:
    """Prüft, ob das HTML aus der Zwischenablage eine einfügbare (Excel-)Tabelle enthält."""
    if not html_str or "<table" not in html_str.lower():
        return False
    try:
        doc = lxml.html.fromstring(html_str)
    except Exception:
        return False
    return _find_excel_table(doc) is not None


def convert_excel_html_to_svg(html_str: str) -> str | None:
    """
    Wandelt eine HTML-Tabelle (z. B. Excel-Clipboard) via Typst in ein
    verlustfreies Vektor-SVG um. Gibt None zurück, falls keine Tabelle vorliegt.
    """
    if not html_str or "<table" not in html_str.lower():
        return None
    try:
        doc = lxml.html.fromstring(html_str)
    except Exception:
        return None

    table_el = _find_excel_table(doc)
    if table_el is None:
        return None

    css_rules = _extract_css_rules(html_str)
    table_style = _resolve_element_style(table_el, css_rules)
    tr_elements = table_el.xpath(".//tr")

    # Spaltenbreiten aus <col> (inkl. span) auslesen
    col_widths_pt: list[float | None] = []
    for col_el in table_el.xpath("./colgroup/col | ./col"):
        try:
            span = max(1, int(col_el.get("span") or 1))
        except ValueError:
            span = 1
        col_style = _resolve_element_style(col_el, css_rules)
        w_pt = _parse_dimension_pt(col_style.get("width"), col_el.get("width"), 12.0, 600.0)
        for _ in range(span):
            col_widths_pt.append(w_pt)

    # Raster-Belegung wegen colspan/rowspan berechnen, um die exakte Spaltenzahl zu ermitteln
    occupied: set[tuple[int, int]] = set()
    parsed_cells: list[dict[str, Any]] = []
    row_heights_pt: list[float | None] = []
    detected_fonts: list[str] = _extract_font_families(table_style.get("font-family"))
    if not detected_fonts and "td" in css_rules:
        detected_fonts = _extract_font_families(css_rules["td"].get("font-family"))
    max_cols = 0
    any_explicit_border = False

    for r_idx, tr in enumerate(tr_elements):
        tr_style = _resolve_element_style(tr, css_rules, table_style)
        row_heights_pt.append(_parse_dimension_pt(tr_style.get("height"), tr.get("height"), 10.0, 200.0))
        c_idx = 0
        for cell_el in tr.xpath("./td | ./th"):
            while (r_idx, c_idx) in occupied:
                c_idx += 1

            try:
                colspan = max(1, int(cell_el.get("colspan") or 1))
            except ValueError:
                colspan = 1
            try:
                rowspan = max(1, int(cell_el.get("rowspan") or 1))
            except ValueError:
                rowspan = 1

            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied.add((r_idx + dr, c_idx + dc))

            max_cols = max(max_cols, c_idx + colspan)

            cell_style = _resolve_element_style(cell_el, css_rules, tr_style)
            if not detected_fonts:
                detected_fonts = _extract_font_families(cell_style.get("font-family"))

            if colspan == 1:
                while len(col_widths_pt) <= c_idx:
                    col_widths_pt.append(None)
                if col_widths_pt[c_idx] is None:
                    col_widths_pt[c_idx] = _parse_dimension_pt(
                        cell_style.get("width"), cell_el.get("width"), 12.0, 600.0
                    )

            is_th = str(cell_el.tag).lower() == "th"
            bg = _parse_color(cell_style.get("background-color") or cell_style.get("background"))
            fg = _parse_color(cell_style.get("color")) or "#1A2433"
            bold = is_th or _is_bold(cell_style)
            italic = _is_italic(cell_style)
            underline = "underline" in cell_style.get("text-decoration", "").lower()
            font_pt = _parse_pt(cell_style.get("font-size"), default=9.0) or 9.0
            font_pt = max(6.0, min(20.0, font_pt))

            h_align_raw = cell_style.get("text-align", "").strip().lower()
            if h_align_raw in ("left", "center", "right"):
                h_align = h_align_raw
            else:
                raw_txt = (cell_el.text_content() or "").strip()
                h_align = "right" if (raw_txt and _NUMERIC_CELL_RE.match(raw_txt)) else "left"
            v_align_raw = cell_style.get("vertical-align", "").strip().lower()
            v_align = "top" if v_align_raw == "top" else ("bottom" if v_align_raw == "bottom" else "horizon")

            # Borders (Shorthand `border` + Einzelseiten)
            base_border = cell_style.get("border")
            sides: dict[str, str] = {}
            for side in ("top", "right", "bottom", "left"):
                raw_side = cell_style.get(f"border-{side}") or base_border
                parsed_side = _parse_border_side(raw_side)
                if parsed_side and parsed_side != "none":
                    any_explicit_border = True
                    sides[side] = parsed_side
                elif parsed_side == "none":
                    sides[side] = "none"

            markup = _render_inline_runs_to_typst(cell_el, css_rules, cell_style)
            parsed_cells.append({
                "colspan": colspan,
                "rowspan": rowspan,
                "bg": bg,
                "fg": fg,
                "bold": bold,
                "italic": italic,
                "underline": underline,
                "font_pt": font_pt,
                "align": f"{h_align} + {v_align}",
                "sides": sides,
                "markup": markup,
            })
            c_idx += colspan

    if max_cols <= 0 or not parsed_cells:
        return None

    default_stroke = 'none' if any_explicit_border else '0.4pt + rgb("#D6DEE8")'
    typst_cells: list[str] = []
    for cell in parsed_cells:
        cell_args: list[str] = [f"align: {cell['align']}"]
        if cell["colspan"] > 1:
            cell_args.append(f"colspan: {cell['colspan']}")
        if cell["rowspan"] > 1:
            cell_args.append(f"rowspan: {cell['rowspan']}")
        if cell["bg"]:
            cell_args.append(f'fill: rgb("{cell["bg"]}")')
        if cell["sides"]:
            side_entries = ", ".join(f"{k}: {v}" for k, v in cell["sides"].items())
            cell_args.append(f"stroke: ({side_entries})")

        content = cell["markup"]
        if content:
            if cell["underline"]:
                content = f"#underline[{content}]"
            txt_args: list[str] = [f"size: {cell['font_pt']:.1f}pt", f'fill: rgb("{cell["fg"]}")']
            if cell["bold"]:
                txt_args.append('weight: "bold"')
            if cell["italic"]:
                txt_args.append('style: "italic"')
            body = f"#text({', '.join(txt_args)})[{content}]"
        else:
            body = ""

        typst_cells.append(f"  table.cell({', '.join(cell_args)})[{body}],")

    col_specs = [
        f"{col_widths_pt[i]:.1f}pt" if (i < len(col_widths_pt) and col_widths_pt[i] is not None) else "auto"
        for i in range(max_cols)
    ]
    cols_spec = "(" + ", ".join(col_specs) + ")"

    table_extra_args: list[str] = []
    if any(h is not None for h in row_heights_pt):
        row_specs = [f"{h:.1f}pt" if h is not None else "auto" for h in row_heights_pt]
        table_extra_args.append(f"  rows: ({', '.join(row_specs)}),")

    font_chain = list(dict.fromkeys([*detected_fonts, "Yoga Sans for LUKB", "Calibri", "Arial"]))
    font_tuple = "(" + ", ".join(f'"{f.replace(chr(34), "")}"' for f in font_chain) + ")"

    typst_src = "\n".join([
        "#set page(width: auto, height: auto, margin: 1pt)",
        f'#set text(font: {font_tuple}, size: 9pt, fill: rgb("#1A2433"))',
        "#table(",
        f"  columns: {cols_spec},",
        *table_extra_args,
        "  inset: (x: 5pt, y: 3.5pt),",
        f"  stroke: {default_stroke},",
        *typst_cells,
        ")",
    ])

    svg_bytes = typst.compile(typst_src.encode("utf-8"), format="svg")
    return svg_bytes.decode("utf-8")
