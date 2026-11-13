"""
Dual-Output Rendering Service für das LUKB Investment Office CMS:
1. Kompiliert Artikel-JSON über das native Python-Typst-Binding (`typst`) in-memory
   zu druckfertigen PDFs oder seitenweisen SVGs für die Echtzeit-Vorschau.
2. Materialisiert in der MSSQL-Datenbank gespeicherte Grafik-Assets (`VARBINARY(MAX)`)
   automatisch in ein temporäres Render-Verzeichnis, sodass Typst sie einbetten kann.
3. Rendert Standalone-Web-Publikationen (HTML5 mit eingebetteten Data-URI-Grafiken) via Jinja2.
"""

from __future__ import annotations

import base64
import datetime
import html
import io
import json
import mimetypes
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
import docx
import jinja2
import typst
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt, RGBColor

from config import FONTS_DIR, TEMPLATES_DIR, WWW_DIR
from database.repository import get_asset
from schemas.article import ArticleDocument
from services.chart_generator import generate_db_chart_svg
from services.html_to_typst import escape_typst_text, html_to_typst

LUKB_LOGO_SVG_PATH = WWW_DIR / "img" / "LUKB-Logo.svg"

_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)


def list_available_templates() -> list[dict[str, Any]]:
    registry_path = TEMPLATES_DIR / "registry.json"
    if registry_path.exists():
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        return data.get("templates", [])
    return [
        {"id": "investment_focus", "name": "LUKB Investment Fokus (2-spaltig)", "columns": 2},
        {"id": "investment_tufte", "name": "LUKB Investment Fokus (Tufte-Stil)", "columns": 1},
        {"id": "market_flash", "name": "LUKB Market Flash (1-spaltig)", "columns": 1},
    ]


GERMAN_MONTHS = [
    "",
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def format_publication_date(val: Any) -> str:
    """
    Formatiert das Publikationsdatum für alle LUKB-Templates im offiziellen Format:
    z.B. '8. November 2026'.
    Unterstützt ISO-Strings (YYYY-MM-DD), Date-/Datetime-Objekte sowie bestehende Datumsangaben.
    """
    if not val:
        return ""
    if isinstance(val, (datetime.date, datetime.datetime)):
        return f"{val.day}. {GERMAN_MONTHS[val.month]} {val.year}"

    val_str = str(val).strip()
    if not val_str:
        return ""

    # Bereits deutsches Monatsformat vorhanden?
    for m in GERMAN_MONTHS[1:]:
        if m in val_str:
            return re.sub(r"^0(\d\.)", r"\1", val_str)

    # ISO Format: YYYY-MM-DD oder YYYY-MM-DDTHH:MM:SS
    iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", val_str)
    if iso_match:
        y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        if 1 <= m <= 12:
            return f"{d}. {GERMAN_MONTHS[m]} {y}"

    # Schweizer/Deutsches Format: DD.MM.YYYY (z.B. 08.11.2026 oder 8.11.2026)
    ch_match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", val_str)
    if ch_match:
        d, m, y = int(ch_match.group(1)), int(ch_match.group(2)), int(ch_match.group(3))
        if 1 <= m <= 12:
            return f"{d}. {GERMAN_MONTHS[m]} {y}"

    try:
        dt = datetime.datetime.fromisoformat(val_str)
        return f"{dt.day}. {GERMAN_MONTHS[dt.month]} {dt.year}"
    except Exception:
        pass

    return val_str


def _extension_for_mime(mime_type: str, filename: str) -> str:
    if "svg" in mime_type.lower() or filename.lower().endswith(".svg"):
        return ".svg"
    if "png" in mime_type.lower() or filename.lower().endswith(".png"):
        return ".png"
    if "jpeg" in mime_type.lower() or "jpg" in mime_type.lower():
        return ".jpg"
    ext = Path(filename).suffix
    return ext if ext else (mimetypes.guess_extension(mime_type) or ".png")


def _group_blocks_into_render_items(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Gruppiert eine flache Liste von Inhaltsblöcken anhand von `box_start`- und `box_end`-Marken:
    Alle Blöcke zwischen einer Start-Marke (`box_start`) und einer End-Marke (`box_end`)
    werden zu einem gemeinsamen Container `{"type": "textbox_group", "children": [...]}` zusammengefasst.
    """
    grouped: list[dict[str, Any]] = []
    current_box_children: list[dict[str, Any]] | None = None

    for blk in blocks:
        btype = blk.get("type")
        if btype == "box_start":
            if current_box_children is not None:
                if current_box_children:
                    grouped.append({"type": "textbox_group", "children": current_box_children})
            current_box_children = []
        elif btype == "box_end":
            if current_box_children is not None:
                grouped.append({"type": "textbox_group", "children": current_box_children})
                current_box_children = None
        else:
            if current_box_children is not None:
                current_box_children.append(blk)
            else:
                grouped.append(blk)

    if current_box_children is not None and current_box_children:
        grouped.append({"type": "textbox_group", "children": current_box_children})

    return grouped


def extract_glossary_terms_from_article(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Sucht alle im Fließtext vorkommenden <span class="glossary-term" data-tooltip="...">Begriff</span>
    oder data-tooltip Attribute zusammen und liefert eine deduplizierte, alphabetisch sortierte Liste
    von Glossar-Einträgen: [{'term': 'SNB', 'definition': 'Schweizerische Nationalbank'}, ...]
    """
    pattern = re.compile(
        r'<span[^>]*\bclass=["\'][^"\']*glossary-term[^"\']*["\'][^>]*data-tooltip=["\']([^"\']+)["\'][^>]*>(.*?)</span>',
        re.DOTALL | re.IGNORECASE,
    )
    alt_pattern = re.compile(
        r'<span[^>]*\bdata-tooltip=["\']([^"\']+)["\'][^>]*\bclass=["\'][^"\']*glossary-term[^"\']*["\'][^>]*>(.*?)</span>',
        re.DOTALL | re.IGNORECASE,
    )
    terms_dict: dict[str, str] = {}

    def _scan_text(text: str) -> None:
        if not text:
            return
        for m in pattern.finditer(text):
            tip = html.unescape(m.group(1)).strip()
            term = re.sub(r"<[^>]+>", "", m.group(2))
            term = html.unescape(term).strip()
            if term and tip and term not in terms_dict:
                terms_dict[term] = tip
        for m in alt_pattern.finditer(text):
            tip = html.unescape(m.group(1)).strip()
            term = re.sub(r"<[^>]+>", "", m.group(2))
            term = html.unescape(term).strip()
            if term and tip and term not in terms_dict:
                terms_dict[term] = tip

    for blk in blocks:
        if blk.get("type") in ("richtext", "callout"):
            _scan_text(blk.get("html", ""))
        elif blk.get("type") == "textbox_group":
            for child in blk.get("children", []):
                if child.get("type") in ("richtext", "callout"):
                    _scan_text(child.get("html", ""))

    items = [{"term": k, "definition": v} for k, v in terms_dict.items()]
    items.sort(key=lambda x: x["term"].lower())
    return items


def _resolve_glossary_items(blk: dict[str, Any], all_blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    auto_items = extract_glossary_terms_from_article(all_blocks) if blk.get("auto_collect", True) else []
    custom = blk.get("custom_items", [])
    combined = {item.get("term", "").strip(): item.get("definition", "").strip() for item in auto_items}
    for c in custom:
        t = c.get("term", "").strip()
        if t:
            combined[t] = c.get("definition", "").strip()
    result = [{"term": k, "definition": v} for k, v in combined.items() if k]
    result.sort(key=lambda x: x["term"].lower())
    return result


def _prepare_typst_payload(doc: ArticleDocument, work_dir: Path) -> dict[str, Any]:
    """
    Bereitet das Artikel-Dictionary für Typst auf:
    - Kopiert das offizielle LUKB-Logo (`LUKB-Logo.svg`) in das temporäre Render-Verzeichnis.
    - Konvertiert HTML-Rich-Text-Blöcke in sicheres Typst-Markup.
    - Schreibt benötigte Grafik-Assets aus der MSSQL-Datenbank in `work_dir`
      und trägt den relativen Pfad als `resolved_image` ein.
    - Gruppiert Blöcke zwischen `box_start` und `box_end` zu einer gemeinsamen farblichen Textbox.
    """
    if LUKB_LOGO_SVG_PATH.exists():
        (work_dir / "LUKB-Logo.svg").write_bytes(LUKB_LOGO_SVG_PATH.read_bytes())

    payload = doc.model_dump()
    raw_date = doc.metadata.publication_date
    formatted_date = format_publication_date(raw_date)
    payload["metadata"]["publication_date_raw"] = raw_date
    payload["metadata"]["publication_date_formatted"] = formatted_date
    payload["metadata"]["publication_date"] = formatted_date or raw_date
    payload["metadata"]["lead_typst"] = escape_typst_text(doc.metadata.lead or "")

    enriched_blocks: list[dict[str, Any]] = []
    for blk in payload.get("blocks", []):
        btype = blk.get("type")
        bcopy = dict(blk)

        if btype in ("richtext", "callout"):
            bcopy["typst_markup"] = html_to_typst(blk.get("html", ""))

        elif btype == "figure":
            asset_id = blk.get("asset_id", "")
            resolved_rel_path = ""
            if asset_id:
                asset_record = get_asset(asset_id)
                if asset_record and asset_record.get("data"):
                    ext = _extension_for_mime(
                        asset_record.get("mime_type", ""),
                        asset_record.get("filename", ""),
                    )
                    asset_filename = f"{asset_id}{ext}"
                    asset_file_path = work_dir / asset_filename
                    asset_file_path.write_bytes(asset_record["data"])
                    resolved_rel_path = asset_filename
            bcopy["resolved_image"] = resolved_rel_path

        elif btype == "db_chart":
            svg_markup = generate_db_chart_svg(
                blk,
                embed_fonts=False,
                max_date=doc.metadata.publication_date,
            )
            chart_filename = f"dbchart_{blk.get('id', 'chart')}.svg"
            (work_dir / chart_filename).write_bytes(svg_markup.encode("utf-8"))
            bcopy["resolved_image"] = chart_filename

        elif btype == "quote":
            bcopy["quote_typst"] = escape_typst_text(blk.get("quote", ""))
            bcopy["author_typst"] = escape_typst_text(blk.get("author", ""))
            bcopy["source_typst"] = escape_typst_text(blk.get("source", ""))

        elif btype == "footnotes":
            bcopy["title_typst"] = escape_typst_text(blk.get("title", ""))
            bcopy["items_typst"] = [
                {
                    "num": escape_typst_text(it.get("num", "")),
                    "text": escape_typst_text(it.get("text", "")),
                }
                for it in blk.get("items", [])
            ]

        elif btype == "glossary":
            all_items = _resolve_glossary_items(blk, payload.get("blocks", []))
            bcopy["title_typst"] = escape_typst_text(blk.get("title", "Glossar & Begriffserklärungen"))
            bcopy["items_typst"] = [
                {
                    "term": escape_typst_text(it["term"]),
                    "definition": escape_typst_text(it["definition"]),
                }
                for it in all_items
            ]
            bcopy["all_items"] = all_items

        elif btype == "publications":
            bcopy["title_typst"] = escape_typst_text(blk.get("title", "Weitere Publikationen"))
            items_typst = []
            for it in blk.get("items", []):
                raw_d = it.get("date", "")
                fmt_d = format_publication_date(raw_d)
                raw_t = it.get("title", "").strip()
                clean_t = raw_t.strip('"').strip('«').strip('»')
                items_typst.append({
                    "title": escape_typst_text(clean_t),
                    "subtitle": escape_typst_text(it.get("subtitle", "")),
                    "date": escape_typst_text(fmt_d or raw_d),
                    "formatted_date": escape_typst_text(fmt_d or raw_d),
                    "category": escape_typst_text(it.get("category", "")),
                    "url": str(it.get("url", "")).strip(),
                    "enabled": bool(it.get("enabled", True)),
                })
            bcopy["items_typst"] = items_typst

        enriched_blocks.append(bcopy)

    payload["blocks"] = _group_blocks_into_render_items(enriched_blocks)
    return payload


def _get_template_typ_path(template_id: str) -> Path:
    candidate = TEMPLATES_DIR / template_id / "template.typ"
    if candidate.exists():
        return candidate
    return TEMPLATES_DIR / "investment_focus" / "template.typ"


def _get_font_paths() -> list[Path]:
    paths: list[Path] = []
    if FONTS_DIR.exists():
        paths.append(FONTS_DIR)
    return paths


def render_pdf_bytes(doc: ArticleDocument) -> bytes:
    """Kompiliert ein ArticleDocument mit der aktuellsten Typst-Engine zu einem PDF (bytes)."""
    template_path = _get_template_typ_path(doc.template_id)
    template_code = template_path.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="lukb_typst_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        work_typ = tmp_dir / "document.typ"
        work_typ.write_text(template_code, encoding="utf-8")

        payload = _prepare_typst_payload(doc, tmp_dir)
        pdf_bytes = typst.compile(
            input=work_typ,
            root=tmp_dir,
            font_paths=_get_font_paths(),
            sys_inputs={"article_json": json.dumps(payload, ensure_ascii=False)},
        )
        if isinstance(pdf_bytes, list):
            return pdf_bytes[0]
        return pdf_bytes


def render_preview_svg_pages(doc: ArticleDocument) -> list[str]:
    """
    Kompiliert ein ArticleDocument in-memory zu einer Liste von SVG-Strings (eine SVG pro PDF-Seite).
    Dadurch kann die PDF-Vorschau im Browser verzögerungsfrei und gestochen scharf gerendert werden.
    """
    template_path = _get_template_typ_path(doc.template_id)
    template_code = template_path.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="lukb_typst_svg_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        work_typ = tmp_dir / "document.typ"
        work_typ.write_text(template_code, encoding="utf-8")

        payload = _prepare_typst_payload(doc, tmp_dir)
        compiled = typst.compile(
            input=work_typ,
            root=tmp_dir,
            format="svg",
            font_paths=_get_font_paths(),
            sys_inputs={"article_json": json.dumps(payload, ensure_ascii=False)},
        )
        if isinstance(compiled, bytes):
            pages_bytes = [compiled]
        else:
            pages_bytes = list(compiled)

        return [p.decode("utf-8") for p in pages_bytes]


_ANCHOR_TAG_RE = re.compile(r"<a\b([^>]*)>", re.IGNORECASE)


def _normalize_inline_links_html(html_str: str) -> str:
    """Stellt sicher, dass alle <a>-Links in Textabsätzen target='_blank' und rel='noopener noreferrer' tragen."""
    if not html_str or "<a" not in html_str.lower():
        return html_str

    def _repl(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        if not re.search(r"\btarget\s*=", attrs, re.IGNORECASE):
            attrs += ' target="_blank"'
        else:
            attrs = re.sub(r'\btarget\s*=\s*(["\']).*?\1', 'target="_blank"', attrs, flags=re.IGNORECASE)
        if not re.search(r"\brel\s*=", attrs, re.IGNORECASE):
            attrs += ' rel="noopener noreferrer"'
        return f"<a{attrs}>"

    return _ANCHOR_TAG_RE.sub(_repl, html_str)


def render_web_html(doc: ArticleDocument) -> str:
    """
    Rendert ein ArticleDocument als eigenständiges, responsives HTML5-Dokument
    inkl. eingebetteter Data-URI-Grafiken aus der MSSQL-Datenbank.
    """
    payload = doc.model_dump()
    raw_date = doc.metadata.publication_date
    formatted_date = format_publication_date(raw_date)
    payload["metadata"]["publication_date_raw"] = raw_date
    payload["metadata"]["publication_date_formatted"] = formatted_date
    payload["metadata"]["publication_date"] = formatted_date or raw_date
    for blk in payload.get("blocks", []):
        if blk.get("type") in ("richtext", "callout"):
            blk["html"] = _normalize_inline_links_html(blk.get("html", ""))
        elif blk.get("type") == "figure":
            asset_id = blk.get("asset_id", "")
            data_uri = ""
            if asset_id:
                asset_record = get_asset(asset_id)
                if asset_record and asset_record.get("data"):
                    b64 = base64.b64encode(asset_record["data"]).decode("ascii")
                    mime = asset_record.get("mime_type", "image/svg+xml")
                    data_uri = f"data:{mime};base64,{b64}"
            blk["data_uri"] = data_uri
        elif blk.get("type") == "db_chart":
            svg_markup = generate_db_chart_svg(
                blk,
                embed_fonts=True,
                max_date=doc.metadata.publication_date,
            )
            b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
            blk["data_uri"] = f"data:image/svg+xml;base64,{b64}"
        elif blk.get("type") == "glossary":
            blk["all_items"] = _resolve_glossary_items(blk, payload.get("blocks", []))
        elif blk.get("type") == "publications":
            for it in blk.get("items", []):
                raw_d = it.get("date", "")
                it["formatted_date"] = format_publication_date(raw_d) or raw_d
                raw_t = it.get("title", "").strip()
                it["clean_title"] = raw_t.strip('"').strip('«').strip('»')
                it["url"] = str(it.get("url", "")).strip()

    payload["blocks"] = _group_blocks_into_render_items(payload.get("blocks", []))

    logo_data_uri = ""
    if LUKB_LOGO_SVG_PATH.exists():
        b64_logo = base64.b64encode(LUKB_LOGO_SVG_PATH.read_bytes()).decode("ascii")
        logo_data_uri = f"data:image/svg+xml;base64,{b64_logo}"

    tpl_name = f"{doc.template_id}/template.html.j2"
    try:
        tpl = _jinja_env.get_template(tpl_name)
    except jinja2.TemplateNotFound:
        tpl = _jinja_env.get_template("investment_focus/template.html.j2")

    return tpl.render(article=payload, template_mode=doc.template_id, logo_data_uri=logo_data_uri)


# ============================================================================
# Microsoft Word (.docx) Export Generator im LUKB Corporate Design
# ============================================================================

def _set_docx_cell_background(cell, fill_hex: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>'))


def _set_docx_cell_margins(cell, top: int = 120, bottom: int = 120, left: int = 150, right: int = 150) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def _svg_to_png_bytes(svg_markup: str, ppi: float = 144.0) -> bytes | None:
    """Konvertiert SVG-Vektorgrafiken via temporäre Typst-Kompilierung in druckscharfe PNGs für Word."""
    if not svg_markup or not svg_markup.strip():
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="lukb_svg2png_") as td:
            tdp = Path(td)
            svg_path = tdp / "chart.svg"
            svg_path.write_text(svg_markup, encoding="utf-8")
            typ_path = tdp / "render.typ"
            typ_path.write_text(
                '#set page(width: auto, height: auto, margin: 0pt)\n#image("chart.svg")',
                encoding="utf-8",
            )
            return typst.compile(
                typ_path,
                format="png",
                ppi=ppi,
                font_paths=_get_font_paths(),
            )
    except Exception:
        return None


class _DocxHtmlRunParser(HTMLParser):
    def __init__(self, paragraph) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraph = paragraph
        self.is_bold = False
        self.is_italic = False
        self.is_underline = False
        self.link_stack: list[str] = []
        self.tooltip_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("b", "strong"):
            self.is_bold = True
        elif t in ("i", "em"):
            self.is_italic = True
        elif t == "u":
            self.is_underline = True
        elif t == "br":
            self.paragraph.add_run().add_break()
        elif t == "a":
            href = ""
            for k, v in attrs:
                if k.lower() == "href" and v:
                    href = v.strip()
            self.link_stack.append(href)
        elif t == "span":
            tip = ""
            for k, v in attrs:
                if k.lower() in ("data-tooltip", "title") and v:
                    tip = v.strip()
            self.tooltip_stack.append(tip if tip else None)
        elif t == "footnote":
            r = self.paragraph.add_run(" [")
            r.font.size = Pt(8.0)
            r.font.color.rgb = RGBColor(0x00, 0x9F, 0xE3)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("b", "strong"):
            self.is_bold = False
        elif t in ("i", "em"):
            self.is_italic = False
        elif t == "u":
            self.is_underline = False
        elif t == "a":
            href = self.link_stack.pop() if self.link_stack else ""
            if href:
                r = self.paragraph.add_run(" ↗")
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)
        elif t == "span":
            if self.tooltip_stack:
                tip = self.tooltip_stack.pop()
        elif t == "footnote":
            r = self.paragraph.add_run("]")
            r.font.size = Pt(8.0)
            r.font.color.rgb = RGBColor(0x00, 0x9F, 0xE3)

    def handle_data(self, data: str) -> None:
        if not data:
            return
        run = self.paragraph.add_run(data)
        run.bold = self.is_bold
        run.italic = self.is_italic
        run.underline = self.is_underline
        if self.link_stack and self.link_stack[-1]:
            run.font.color.rgb = RGBColor(0x00, 0x28, 0x55)


def _add_html_runs_to_paragraph(paragraph, html_fragment: str) -> None:
    if not html_fragment:
        return
    parser = _DocxHtmlRunParser(paragraph)
    try:
        parser.feed(html_fragment)
        parser.close()
    except Exception:
        # Fallback auf einfaches unescaping falls fehlerhaftes HTML
        plain = re.sub(r"<[^>]+>", " ", html_fragment).strip()
        paragraph.add_run(html.unescape(plain))


def _render_richtext_into_docx(doc_or_cell, html_content: str) -> None:
    if "<p" not in html_content and "<li" not in html_content:
        p = doc_or_cell.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.15
        _add_html_runs_to_paragraph(p, html_content)
        return

    pattern = re.compile(r"<(p|li)([^>]*)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
    matches = list(pattern.finditer(html_content))
    if not matches:
        plain = re.sub(r"<[^>]+>", " ", html_content).strip()
        p = doc_or_cell.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.add_run(html.unescape(plain))
        return

    for m in matches:
        tag = m.group(1).lower()
        inner = m.group(3)
        if tag == "li":
            p = doc_or_cell.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            _add_html_runs_to_paragraph(p, inner)
        else:
            p = doc_or_cell.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.15
            _add_html_runs_to_paragraph(p, inner)


def render_docx_bytes(doc_model: ArticleDocument) -> bytes:
    """
    Exportiert ein ArticleDocument als druckreifes, sauber formatiertes Microsoft Word Dokument (.docx)
    im offiziellen LUKB Corporate Design (inkl. Tabellen, Callout-Boxen, Vektor-Charts als PNG, Metadaten).
    """
    doc = docx.Document()

    # DIN A4 Seitenränder (oben 2.5cm, unten 2.5cm, links 2.2cm, rechts 2.2cm)
    section = doc.sections[0]
    section.top_margin = Inches(0.98)
    section.bottom_margin = Inches(0.98)
    section.left_margin = Inches(0.86)
    section.right_margin = Inches(0.86)

    # Standard-Schriftart: Calibri / Arial
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)
    style.font.color.rgb = RGBColor(0x1A, 0x24, 0x33)

    meta = doc_model.metadata

    # 1. Kopfbereich: LUKB Logo & Kategorie
    if LUKB_LOGO_SVG_PATH.exists():
        logo_png = _svg_to_png_bytes(LUKB_LOGO_SVG_PATH.read_text(encoding="utf-8"), ppi=200.0)
        if logo_png:
            doc.add_picture(io.BytesIO(logo_png), width=Inches(1.8))

    cat_date_p = doc.add_paragraph()
    cat_date_p.paragraph_format.space_before = Pt(8)
    cat_date_p.paragraph_format.space_after = Pt(2)
    cat_parts = []
    if meta.category:
        cat_parts.append(meta.category.upper())
    formatted_date = format_publication_date(meta.publication_date)
    if formatted_date:
        cat_parts.append(formatted_date)
    elif meta.publication_date:
        cat_parts.append(meta.publication_date)
    if not cat_parts:
        cat_parts.append("LUKB INVESTMENT OFFICE NEWS")
    r_cat = cat_date_p.add_run(" · ".join(cat_parts))
    r_cat.bold = True
    r_cat.font.size = Pt(9.5)
    r_cat.font.color.rgb = RGBColor(0x00, 0x9F, 0xE3)

    # 2. Titel & Untertitel
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(4)
    title_p.paragraph_format.space_after = Pt(2)
    title_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r_t = title_p.add_run(meta.title or "Publikation")
    r_t.bold = True
    r_t.font.size = Pt(22)
    r_t.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

    if meta.subtitle:
        sub_p = doc.add_paragraph()
        sub_p.paragraph_format.space_before = Pt(0)
        sub_p.paragraph_format.space_after = Pt(8)
        sub_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_s = sub_p.add_run(meta.subtitle)
        r_s.font.size = Pt(11.5)
        r_s.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)

    # 3. Lead-Absatz
    if meta.lead:
        lead_p = doc.add_paragraph()
        lead_p.paragraph_format.space_before = Pt(6)
        lead_p.paragraph_format.space_after = Pt(8)
        lead_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_l = lead_p.add_run(meta.lead)
        r_l.bold = True
        r_l.font.size = Pt(10.5)
        r_l.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

    # 4. Autorenzeile
    if meta.authors:
        auth_p = doc.add_paragraph()
        auth_p.paragraph_format.space_before = Pt(0)
        auth_p.paragraph_format.space_after = Pt(6)
        r_albl = auth_p.add_run("Verfasst von: ")
        r_albl.font.size = Pt(8.5)
        r_albl.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)
        for idx, a in enumerate(meta.authors):
            if idx > 0:
                auth_p.add_run(" · ")
            r_aname = auth_p.add_run(a.name)
            r_aname.bold = True
            r_aname.font.size = Pt(8.5)
            if a.role:
                r_arole = auth_p.add_run(f" ({a.role})")
                r_arole.font.size = Pt(8.5)
                r_arole.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)

    # Schlagwörter / Tags
    if meta.tags:
        tags_p = doc.add_paragraph()
        tags_p.paragraph_format.space_before = Pt(2)
        tags_p.paragraph_format.space_after = Pt(10)
        rtlbl = tags_p.add_run("Schlagwörter: ")
        rtlbl.font.size = Pt(8.5)
        rtlbl.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)
        rtlbl.bold = True
        for t_idx, tag in enumerate(meta.tags):
            if t_idx > 0:
                tags_p.add_run("  •  ")
            rtag = tags_p.add_run(tag)
            rtag.font.size = Pt(8.5)
            rtag.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

    # 5. Inhaltsblöcke rendern
    grouped_blocks = _group_blocks_into_render_items(doc_model.model_dump().get("blocks", []))

    def _render_block(container, blk):
        btype = blk.get("type")
        if btype == "heading":
            lvl = int(blk.get("level") or 1)
            p = container.add_paragraph()
            p.paragraph_format.space_before = Pt(14 if lvl == 1 else (10 if lvl == 2 else 8))
            p.paragraph_format.space_after = Pt(3)
            r = p.add_run(blk.get("text", ""))
            r.bold = True
            if lvl == 1:
                r.font.size = Pt(13)
                r.font.color.rgb = RGBColor(0x00, 0x28, 0x55)
            elif lvl == 2:
                r.font.size = Pt(11.5)
                r.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)
            else:
                r.font.size = Pt(10.5)
                r.font.color.rgb = RGBColor(0x1A, 0x24, 0x33)

        elif btype == "richtext":
            _render_richtext_into_docx(container, blk.get("html", ""))

        elif btype == "callout":
            tbl = container.add_table(rows=1, cols=1)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = tbl.rows[0].cells[0]
            _set_docx_cell_background(cell, "EBF3FA")
            _set_docx_cell_margins(cell, top=140, bottom=140, left=180, right=180)
            tcPr = cell._tc.get_or_add_tcPr()
            tcBorders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:top w:val="single" w:sz="4" w:space="0" w:color="D6DEE8"/>'
                f'<w:left w:val="single" w:sz="24" w:space="0" w:color="009FE3"/>'
                f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D6DEE8"/>'
                f'<w:right w:val="single" w:sz="4" w:space="0" w:color="D6DEE8"/>'
                f'</w:tcBorders>'
            )
            tcPr.append(tcBorders)
            c_title = blk.get("title", "").strip()
            if c_title:
                cp = cell.paragraphs[0]
                cp.paragraph_format.space_after = Pt(4)
                cr = cp.add_run(c_title)
                cr.bold = True
                cr.font.size = Pt(10)
                cr.font.color.rgb = RGBColor(0x00, 0x28, 0x55)
            _render_richtext_into_docx(cell, blk.get("html", ""))
            container.add_paragraph().paragraph_format.space_after = Pt(4)

        elif btype in ("figure", "db_chart"):
            g_title = blk.get("title", "").strip()
            if g_title:
                pt = container.add_paragraph()
                pt.paragraph_format.space_before = Pt(12)
                pt.paragraph_format.space_after = Pt(2)
                r = pt.add_run(g_title)
                r.bold = True
                r.font.size = Pt(10.5)
                r.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

            g_sub = blk.get("subtitle", "").strip()
            if g_sub:
                ps = container.add_paragraph()
                ps.paragraph_format.space_before = Pt(0)
                ps.paragraph_format.space_after = Pt(6)
                r = ps.add_run(g_sub)
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)

            img_bytes = None
            if btype == "db_chart":
                svg_code = generate_db_chart_svg(
                    blk,
                    embed_fonts=False,
                    max_date=doc_model.metadata.publication_date,
                )
                img_bytes = _svg_to_png_bytes(svg_code, ppi=144.0)
            else:
                asset_id = blk.get("asset_id", "")
                if asset_id:
                    rec = get_asset(asset_id)
                    if rec and rec.get("data"):
                        data = rec["data"]
                        mime = rec.get("mime_type", "")
                        if "svg" in mime.lower() or rec.get("filename", "").lower().endswith(".svg"):
                            img_bytes = _svg_to_png_bytes(data.decode("utf-8", errors="ignore"), ppi=144.0)
                        else:
                            img_bytes = data
            if img_bytes:
                try:
                    container.add_picture(io.BytesIO(img_bytes), width=Inches(6.0))
                except Exception:
                    pass

            src = blk.get("source", "").strip()
            if src:
                psrc = container.add_paragraph()
                psrc.paragraph_format.space_before = Pt(3)
                psrc.paragraph_format.space_after = Pt(8)
                r = psrc.add_run(src)
                r.font.size = Pt(8.0)
                r.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)
                r.italic = True

        elif btype == "table":
            tbl_title = blk.get("title", "").strip()
            if tbl_title:
                pt = container.add_paragraph()
                pt.paragraph_format.space_before = Pt(12)
                pt.paragraph_format.space_after = Pt(2)
                r = pt.add_run(tbl_title)
                r.bold = True
                r.font.size = Pt(10.5)
                r.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

            cols = blk.get("columns", [])
            rows = blk.get("rows", [])
            show_header = blk.get("show_header", True)
            if cols:
                total_rows = len(rows) + (1 if show_header else 0)
                t = container.add_table(rows=total_rows, cols=len(cols))
                t.alignment = WD_TABLE_ALIGNMENT.CENTER
                t.autofit = False

                fallback_w = 100.0 / max(1, len(cols))
                weights: list[float] = []
                for col in cols:
                    try:
                        w = float(col.get("width") or fallback_w)
                    except (TypeError, ValueError):
                        w = fallback_w
                    weights.append(w if w > 0 else fallback_w)
                total_weight = sum(weights) or 100.0
                total_table_inches = 6.5

                if show_header:
                    hdr_cells = t.rows[0].cells
                    for c_idx, col in enumerate(cols):
                        col_w = Inches(total_table_inches * (weights[c_idx] / total_weight))
                        t.columns[c_idx].width = col_w
                        cell = hdr_cells[c_idx]
                        cell.width = col_w
                        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                        _set_docx_cell_background(cell, "002855")
                        _set_docx_cell_margins(cell, top=130, bottom=130, left=150, right=150)
                        p = cell.paragraphs[0]
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if col.get("align") == "right" else WD_ALIGN_PARAGRAPH.LEFT
                        run = p.add_run(col.get("title", ""))
                        run.bold = True
                        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                        run.font.size = Pt(8.5)

                row_offset = 1 if show_header else 0
                for r_idx, row in enumerate(rows):
                    is_total = blk.get("highlight_last_row") and (r_idx == len(rows) - 1)
                    row_cells = t.rows[r_idx + row_offset].cells
                    bg_hex = "E6EEF7" if is_total else ("F4F7FA" if r_idx % 2 == 1 else "FFFFFF")
                    for c_idx, col in enumerate(cols):
                        col_w = Inches(total_table_inches * (weights[c_idx] / total_weight))
                        if not show_header:
                            t.columns[c_idx].width = col_w
                        cell = row_cells[c_idx]
                        cell.width = col_w
                        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                        _set_docx_cell_background(cell, bg_hex)
                        _set_docx_cell_margins(cell, top=90, bottom=90, left=150, right=150)
                        p = cell.paragraphs[0]
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if col.get("align") == "right" else WD_ALIGN_PARAGRAPH.LEFT
                        val = str(row.get(col.get("field", ""), ""))
                        run = p.add_run(val)
                        run.bold = is_total
                        run.font.color.rgb = RGBColor(0x00, 0x28, 0x55) if is_total else RGBColor(0x1A, 0x24, 0x33)
                        run.font.size = Pt(8.5)

            src = blk.get("source", "").strip()
            if src:
                psrc = container.add_paragraph()
                psrc.paragraph_format.space_before = Pt(3)
                psrc.paragraph_format.space_after = Pt(8)
                r = psrc.add_run(src)
                r.font.size = Pt(8.0)
                r.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)
                r.italic = True

        elif btype == "spacer":
            h_mm = blk.get("height_mm", 8)
            p = container.add_paragraph()
            p.paragraph_format.space_after = Pt(round(h_mm * 2.83465))

        elif btype == "colbreak":
            # Im linearen Word-Dokument dient der Spaltenumbruch als dezenter Abschnittstrenner
            p = container.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(10)

        elif btype == "quote":
            tbl = container.add_table(rows=1, cols=1)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = tbl.rows[0].cells[0]
            _set_docx_cell_background(cell, "F8FAFC")
            _set_docx_cell_margins(cell, top=140, bottom=140, left=200, right=160)
            tcPr = cell._tc.get_or_add_tcPr()
            tcBorders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:left w:val="single" w:sz="24" w:space="0" w:color="009FE3"/>'
                f'<w:top w:val="none"/>'
                f'<w:bottom w:val="none"/>'
                f'<w:right w:val="none"/>'
                f'</w:tcBorders>'
            )
            tcPr.append(tcBorders)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(4)
            quote_text = blk.get("quote", "").strip()
            rq = p.add_run(f"«{quote_text}»" if quote_text else "")
            rq.italic = True
            rq.font.size = Pt(10.5)
            rq.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

            author = blk.get("author", "").strip()
            source = blk.get("source", "").strip()
            if author or source:
                pa = cell.add_paragraph()
                pa.paragraph_format.space_before = Pt(2)
                pa.paragraph_format.space_after = Pt(0)
                if author:
                    ra = pa.add_run(author)
                    ra.bold = True
                    ra.font.size = Pt(8.5)
                    ra.font.color.rgb = RGBColor(0x00, 0x28, 0x55)
                if author and source:
                    rm = pa.add_run(" · ")
                    rm.font.size = Pt(8.5)
                if source:
                    rs = pa.add_run(source)
                    rs.font.size = Pt(8.0)
                    rs.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)
            container.add_paragraph().paragraph_format.space_after = Pt(4)

        elif btype == "divider":
            style = blk.get("style", "solid")
            tbl = container.add_table(rows=1, cols=1)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = tbl.rows[0].cells[0]
            tcPr = cell._tc.get_or_add_tcPr()
            val_border = "dashed" if style == "dashed" else ("dotted" if style == "dots" else "single")
            tcBorders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:top w:val="none"/>'
                f'<w:left w:val="none"/>'
                f'<w:bottom w:val="{val_border}" w:sz="6" w:space="0" w:color="CBD5E1"/>'
                f'<w:right w:val="none"/>'
                f'</w:tcBorders>'
            )
            tcPr.append(tcBorders)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            container.add_paragraph().paragraph_format.space_after = Pt(2)

        elif btype == "footnotes":
            title = blk.get("title", "").strip() or "Anmerkungen & Quellen"
            p = container.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(4)
            rt = p.add_run(title)
            rt.bold = True
            rt.font.size = Pt(11.5)
            rt.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)

            for item in blk.get("items", []):
                num = str(item.get("num", "")).strip()
                text = str(item.get("text", "")).strip()
                pi = container.add_paragraph()
                pi.paragraph_format.space_before = Pt(0)
                pi.paragraph_format.space_after = Pt(2)
                if num:
                    rn = pi.add_run(f"[{num}] ")
                    rn.bold = True
                    rn.font.size = Pt(8.0)
                    rn.font.color.rgb = RGBColor(0x00, 0x9F, 0xE3)
                rtxt = pi.add_run(text)
                rtxt.font.size = Pt(8.0)
                rtxt.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)

        elif btype == "glossary":
            all_items = _resolve_glossary_items(blk, doc_model.model_dump().get("blocks", []))
            if all_items:
                title = blk.get("title", "").strip() or "Glossar & Begriffserklärungen"
                p = container.add_paragraph()
                p.paragraph_format.space_before = Pt(12)
                p.paragraph_format.space_after = Pt(4)
                rt = p.add_run(title)
                rt.bold = True
                rt.font.size = Pt(11.5)
                rt.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)

                for item in all_items:
                    pi = container.add_paragraph()
                    pi.paragraph_format.space_before = Pt(0)
                    pi.paragraph_format.space_after = Pt(3)
                    r_term = pi.add_run(item["term"] + " — ")
                    r_term.bold = True
                    r_term.font.size = Pt(8.5)
                    r_term.font.color.rgb = RGBColor(0x00, 0x28, 0x55)
                    r_def = pi.add_run(item["definition"])
                    r_def.font.size = Pt(8.5)
                    r_def.font.color.rgb = RGBColor(0x1A, 0x24, 0x33)

        elif btype == "publications":
            title = blk.get("title", "").strip() or "Weitere Publikationen"
            p = container.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(4)
            rt = p.add_run(title)
            rt.bold = True
            rt.font.size = Pt(11)
            rt.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)

            for item in blk.get("items", []):
                if not item.get("enabled", True):
                    continue
                pi = container.add_paragraph()
                pi.paragraph_format.space_before = Pt(1)
                pi.paragraph_format.space_after = Pt(2)
                raw_title = item.get("title", "").strip()
                clean_title = raw_title.strip('"').strip('«').strip('»')
                raw_d = item.get("date", "")
                fmt_d = format_publication_date(raw_d) or raw_d
                text_content = f'"{clean_title}"'
                if fmt_d:
                    text_content += f" vom {fmt_d}"
                url = str(item.get("url", "")).strip()
                if url:
                    text_content += " ↗"
                r_item = pi.add_run(text_content)
                r_item.bold = False
                r_item.font.size = Pt(8.5)
                r_item.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

        elif btype == "textbox_group":
            tbl = container.add_table(rows=1, cols=1)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = tbl.rows[0].cells[0]
            _set_docx_cell_background(cell, "F4F7FA")
            _set_docx_cell_margins(cell, top=140, bottom=140, left=180, right=180)
            tcPr = cell._tc.get_or_add_tcPr()
            tcBorders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:top w:val="single" w:sz="6" w:space="0" w:color="002855"/>'
                f'<w:left w:val="single" w:sz="6" w:space="0" w:color="002855"/>'
                f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="002855"/>'
                f'<w:right w:val="single" w:sz="6" w:space="0" w:color="002855"/>'
                f'</w:tcBorders>'
            )
            tcPr.append(tcBorders)
            for child in blk.get("children", []):
                _render_block(cell, child)
            container.add_paragraph().paragraph_format.space_after = Pt(4)

    for item in grouped_blocks:
        _render_block(doc, item)

    out_stream = io.BytesIO()
    doc.save(out_stream)
    return out_stream.getvalue()
