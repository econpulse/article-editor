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
import hashlib
import html
import io
import json
import logging
import mimetypes
import re
import tempfile
import threading
from collections import OrderedDict
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

from config import DATA_DIR, FONTS_DIR, TEMPLATES_DIR, TYPST_CACHE_DIR, WWW_DIR
from database.repository import get_assets_by_ids
from schemas.article import ArticleDocument
from services.chart_generator import generate_db_chart_svg, publication_timeseries_snapshot
from services.custom_chart_generator import generate_custom_chart_svg
from services.html_to_typst import escape_typst_text, html_to_typst, sanitize_richtext_html, table_cell_html_to_typst
from services.kpi_icons import get_kpi_tone_palette, render_kpi_icon_svg

logger = logging.getLogger("lukb_cms.renderer")

LUKB_LOGO_SVG_PATH = WWW_DIR / "img" / "LUKB-Logo.svg"
TYPST_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_COMPILER_CACHE: dict[str, typst.Compiler] = {}
_COMPILER_LOCK = threading.Lock()
_LOGO_PNG_CACHE: bytes | None = None
_LOGO_DATA_URI_CACHE: str | None = None
_SVG_PNG_CACHE: OrderedDict[str, bytes] = OrderedDict()
_SVG_PNG_CACHE_LOCK = threading.Lock()
_SVG_PNG_CACHE_MAX_SIZE = 128

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
        {"id": "investment_focus", "name": "LUKB Investment Fokus (2-spaltiger Report)", "columns": 2},
        {"id": "investment_tufte", "name": "LUKB Investment Fokus (Tufte-Stil)", "columns": 1},
        {"id": "market_flash", "name": "LUKB Market Flash (Kompakter Fokus-Bericht)", "columns": 2},
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
    current_box_id: str = ""

    for blk in blocks:
        btype = blk.get("type")
        if btype == "box_start":
            if current_box_children is not None:
                if current_box_children:
                    grouped.append({"type": "textbox_group", "id": current_box_id, "children": current_box_children})
            current_box_children = []
            current_box_id = str(blk.get("id", "") or "")
        elif btype == "box_end":
            if current_box_children is not None:
                grouped.append({"type": "textbox_group", "id": current_box_id, "children": current_box_children})
                current_box_children = None
                current_box_id = ""
        else:
            if current_box_children is not None:
                current_box_children.append(blk)
            else:
                grouped.append(blk)

    if current_box_children is not None and current_box_children:
        grouped.append({"type": "textbox_group", "id": current_box_id, "children": current_box_children})

    return grouped


_GLOSSARY_TERM_RE = re.compile(
    r'<span[^>]*\bclass=["\'][^"\']*glossary-term[^"\']*["\'][^>]*data-tooltip=["\']([^"\']+)["\'][^>]*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
_GLOSSARY_ALT_RE = re.compile(
    r'<span[^>]*\bdata-tooltip=["\']([^"\']+)["\'][^>]*\bclass=["\'][^"\']*glossary-term[^"\']*["\'][^>]*>(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)


def extract_glossary_terms_from_article(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Sucht alle im Fließtext vorkommenden <span class="glossary-term" data-tooltip="...">Begriff</span>
    oder data-tooltip Attribute zusammen und liefert eine deduplizierte, alphabetisch sortierte Liste
    von Glossar-Einträgen: [{'term': 'SNB', 'definition': 'Schweizerische Nationalbank'}, ...]
    """
    terms_dict: dict[str, str] = {}

    def _scan_text(text: str) -> None:
        if not text or "glossary-term" not in text:
            return
        for m in _GLOSSARY_TERM_RE.finditer(text):
            tip = html.unescape(m.group(1)).strip()
            term = re.sub(r"<[^>]+>", "", m.group(2))
            term = html.unescape(term).strip()
            if term and tip and term not in terms_dict:
                terms_dict[term] = tip
        for m in _GLOSSARY_ALT_RE.finditer(text):
            tip = html.unescape(m.group(1)).strip()
            term = re.sub(r"<[^>]+>", "", m.group(2))
            term = html.unescape(term).strip()
            if term and tip and term not in terms_dict:
                terms_dict[term] = tip

    for blk in blocks:
        if blk.get("type") in ("richtext", "callout"):
            _scan_text(blk.get("html", ""))
        elif blk.get("type") == "media_text":
            _scan_text(blk.get("html", ""))
            _scan_text(blk.get("aside_html", ""))
        elif blk.get("type") == "textbox_group":
            for child in blk.get("children", []):
                if child.get("type") in ("richtext", "callout"):
                    _scan_text(child.get("html", ""))
                elif child.get("type") == "media_text":
                    _scan_text(child.get("html", ""))
                    _scan_text(child.get("aside_html", ""))

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


def _reorder_blocks_for_anchors(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalisiert die Blockreihenfolge für Randelemente mit explizitem `anchor_to`:
    Falls ein Randelement (figure, db_chart, table mit layout='column') an einen
    bestimmten Block (anchor_to) verankert ist und sich vor oder nach diesem Block
    im Daten-Array befindet, wird es unmittelbar hinter dem Anker-Block einsortiert.
    Dadurch fliessen Textabsatz und Randelement in allen Rendering-Kanälen (Typst, Web, DOCX)
    garantiert synchron.
    """
    if not blocks:
        return []

    has_anchors = any(
        isinstance(b, dict)
        and b.get("anchor_to")
        and b.get("type") in ("figure", "db_chart", "custom_chart", "table", "media_text")
        and b.get("layout", "column") == "column"
        for b in blocks
    )
    if not has_anchors:
        return blocks

    anchored_map: dict[str, list[dict[str, Any]]] = {}
    remaining_blocks: list[dict[str, Any]] = []
    known_ids = {b.get("id") for b in blocks if isinstance(b, dict) and b.get("id")}

    for blk in blocks:
        if not isinstance(blk, dict):
            remaining_blocks.append(blk)
            continue
        aid = blk.get("anchor_to")
        is_margin = (
            blk.get("type") in ("figure", "db_chart", "custom_chart", "table", "media_text")
            and blk.get("layout", "column") == "column"
        )
        if is_margin and aid and aid in known_ids and aid != blk.get("id"):
            anchored_map.setdefault(aid, []).append(blk)
        else:
            remaining_blocks.append(blk)

    reordered: list[dict[str, Any]] = []
    for blk in remaining_blocks:
        reordered.append(blk)
        if isinstance(blk, dict) and blk.get("id") in anchored_map:
            reordered.extend(anchored_map[blk.get("id")])

    return reordered


def _prepare_common_article_payload(doc: ArticleDocument) -> dict[str, Any]:
    """
    Zentrale Voraufbereitung des Artikel-Payloads für alle Ausgabekanäle (Typst-PDF/SVG, Web-HTML, Word-DOCX):
    - Formatiert das Publikationsdatum einheitlich im LUKB-Standardformat.
    - Normalisiert die Reihenfolge verankerter Randelemente (`anchor_to`).
    - Löst Glossar-Begriffe (`all_items`) und Querverweise (`publications`) zentral einmalig auf.
    """
    payload = doc.model_dump()
    raw_date = doc.metadata.publication_date
    formatted_date = format_publication_date(raw_date)
    payload["metadata"]["publication_date_raw"] = raw_date
    payload["metadata"]["publication_date_formatted"] = formatted_date
    payload["metadata"]["publication_date"] = formatted_date or raw_date
    payload["metadata"]["lead_typst"] = escape_typst_text(doc.metadata.lead or "")

    raw_blocks = _reorder_blocks_for_anchors(payload.get("blocks", []))
    payload["blocks"] = raw_blocks
    zebra_counter = 0
    for idx, blk in enumerate(raw_blocks):
        btype = blk.get("type")
        if btype == "media_text" and blk.get("style_preset") == "zebra":
            blk["_zebra_index"] = zebra_counter
            next_blk = raw_blocks[idx + 1] if idx + 1 < len(raw_blocks) else None
            blk["_zebra_last"] = not (
                isinstance(next_blk, dict)
                and next_blk.get("type") == "media_text"
                and next_blk.get("style_preset") == "zebra"
            )
            zebra_counter += 1
        else:
            zebra_counter = 0
        if btype == "glossary":
            blk["all_items"] = _resolve_glossary_items(blk, raw_blocks)
        elif btype == "publications":
            for it in blk.get("items", []):
                raw_d = it.get("date", "")
                fmt_d = format_publication_date(raw_d)
                it["formatted_date"] = fmt_d or raw_d
                raw_t = it.get("title", "").strip()
                it["clean_title"] = raw_t.strip('"').strip('«').strip('»')
                it["url"] = str(it.get("url", "")).strip()
    return payload


def _fetch_doc_asset_records(
    blocks: list[dict[str, Any]],
    *,
    article_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Lädt alle in `figure`- und `media_text`-Blöcken referenzierten Asset-Datensätze gebündelt aus der DB."""
    figure_aids: set[str] = set()
    for blk in blocks:
        if blk.get("type") == "figure" and blk.get("asset_id"):
            figure_aids.add(blk["asset_id"])
        elif blk.get("type") == "media_text":
            media = blk.get("media")
            if isinstance(media, dict) and media.get("type") == "figure" and media.get("asset_id"):
                figure_aids.add(media["asset_id"])
    return get_assets_by_ids(figure_aids, article_id=article_id) if figure_aids else {}


def render_block_chart_svg(
    blk: dict[str, Any],
    *,
    embed_fonts: bool,
    max_date: str | datetime.date | None = None,
) -> str:
    """Einheitlicher Chart-SVG-Renderer für `db_chart` und `custom_chart` über alle Ausgabekanäle."""
    if blk.get("type") == "db_chart":
        return generate_db_chart_svg(blk, embed_fonts=embed_fonts, max_date=max_date)
    return generate_custom_chart_svg(blk, embed_fonts=embed_fonts)


def _materialize_svg_asset(work_dir: Path, svg_markup: str, prefix: str = "chart_") -> str:
    """Schreibt SVG-Markup unter deterministischem Content-Hash in `work_dir` (thread-safe)."""
    svg_bytes = svg_markup.encode("utf-8")
    digest = hashlib.sha256(svg_bytes).hexdigest()[:16]
    filename = f"{prefix}{digest}.svg"
    file_path = work_dir / filename
    if not file_path.exists():
        file_path.write_bytes(svg_bytes)
    return filename


def _materialize_chart_svg(work_dir: Path, svg_markup: str) -> str:
    """Schreibt Chart-SVG unter deterministischem Content-Hash in `work_dir` (thread-safe, kein Überschreiben)."""
    return _materialize_svg_asset(work_dir, svg_markup, prefix="chart_")


def _prepare_table_typst_rows(tbl_blk: dict[str, Any]) -> list[dict[str, str]]:
    """Konvertiert alle Tabellenzellen eines Table-Blocks in sicheres Typst-Markup."""
    cols = tbl_blk.get("columns", [])
    rows = tbl_blk.get("rows", [])
    col_fields = [c.get("field", "") for c in cols if isinstance(c, dict) and c.get("field")]
    typst_rows: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            typst_rows.append({})
            continue
        r_out: dict[str, str] = {}
        for field in col_fields:
            r_out[field] = table_cell_html_to_typst(str(row.get(field, "")))
        # Auch eventuelle Zusatzfelder übernehmen
        for k, v in row.items():
            if k not in r_out:
                r_out[k] = table_cell_html_to_typst(str(v))
        typst_rows.append(r_out)
    return typst_rows


def _prepare_typst_payload(
    doc: ArticleDocument,
    work_dir: Path,
    interactive_links: bool = False,
) -> dict[str, Any]:
    """
    Bereitet das Artikel-Dictionary für Typst auf:
    - Konvertiert HTML-Rich-Text-Blöcke in sicheres Typst-Markup.
    - Schreibt benötigte Grafik-Assets aus der MSSQL-Datenbank in `work_dir`
      und trägt den relativen Pfad als `resolved_image` ein.
    - Gruppiert Blöcke zwischen `box_start` und `box_end` zu einer gemeinsamen farblichen Textbox.
    """
    payload = _prepare_common_article_payload(doc)
    payload["interactive_links"] = bool(interactive_links)
    raw_blocks = payload.get("blocks", [])
    asset_cache = _fetch_doc_asset_records(raw_blocks, article_id=doc.id)

    # Gliederungshierarchie für Acrobat / PDF-Bookmarks (H1, H2, H3) berechnen:
    # Falls keine H1 im Dokument existiert, wird H2 zur höchsten Ebene (Level 1 in der PDF-Outline).
    heading_lvls = [
        int(blk.get("level", 2))
        for blk in raw_blocks
        if blk.get("type") == "heading" and str(blk.get("text", "")).strip()
    ]
    min_heading_lvl = min(heading_lvls) if heading_lvls else 1
    level_offset = min_heading_lvl - 1 if min_heading_lvl > 1 else 0

    enriched_blocks: list[dict[str, Any]] = []
    for blk in raw_blocks:
        btype = blk.get("type")
        bcopy = dict(blk)

        if btype == "heading":
            lvl = int(blk.get("level", 2))
            bcopy["outline_level"] = max(1, lvl - level_offset)

        elif btype in ("richtext", "callout"):
            bcopy["typst_markup"] = html_to_typst(blk.get("html", ""))

        elif btype == "figure":
            asset_id = blk.get("asset_id", "")
            resolved_rel_path = ""
            if asset_id:
                asset_record = asset_cache.get(asset_id)
                if asset_record and asset_record.get("data"):
                    ext = _extension_for_mime(
                        asset_record.get("mime_type", ""),
                        asset_record.get("filename", ""),
                    )
                    asset_filename = f"{asset_id}{ext}"
                    asset_file_path = work_dir / asset_filename
                    asset_bytes = asset_record["data"]
                    if not asset_file_path.exists() or asset_file_path.read_bytes() != asset_bytes:
                        asset_file_path.write_bytes(asset_bytes)
                    resolved_rel_path = asset_filename
            bcopy["resolved_image"] = resolved_rel_path

        elif btype in ("db_chart", "custom_chart"):
            svg_markup = render_block_chart_svg(
                blk,
                embed_fonts=False,
                max_date=doc.metadata.publication_date,
            )
            bcopy["resolved_image"] = _materialize_chart_svg(work_dir, svg_markup)

        elif btype == "table":
            bcopy["rows_typst"] = _prepare_table_typst_rows(bcopy)

        elif btype == "media_text":
            bcopy["title_typst"] = escape_typst_text(blk.get("title", ""))
            bcopy["typst_markup"] = html_to_typst(blk.get("html", ""))
            aside_raw = blk.get("aside_html", "")
            bcopy["aside_typst_markup"] = (
                html_to_typst(aside_raw) if aside_raw and str(aside_raw).strip() else ""
            )
            media_raw = blk.get("media") if isinstance(blk.get("media"), dict) else {}
            media_copy = dict(media_raw)
            mtype = blk.get("media_type") or media_copy.get("type") or "figure"
            media_copy["type"] = mtype
            if mtype == "figure":
                asset_id = media_copy.get("asset_id", "")
                resolved_rel_path = ""
                if asset_id:
                    asset_record = asset_cache.get(asset_id)
                    if asset_record and asset_record.get("data"):
                        ext = _extension_for_mime(
                            asset_record.get("mime_type", ""),
                            asset_record.get("filename", ""),
                        )
                        asset_filename = f"{asset_id}{ext}"
                        asset_file_path = work_dir / asset_filename
                        asset_bytes = asset_record["data"]
                        if not asset_file_path.exists() or asset_file_path.read_bytes() != asset_bytes:
                            asset_file_path.write_bytes(asset_bytes)
                        resolved_rel_path = asset_filename
                media_copy["resolved_image"] = resolved_rel_path
            elif mtype in ("db_chart", "custom_chart"):
                svg_markup = render_block_chart_svg(
                    media_copy,
                    embed_fonts=False,
                    max_date=doc.metadata.publication_date,
                )
                media_copy["resolved_image"] = _materialize_chart_svg(work_dir, svg_markup)
            elif mtype == "table":
                media_copy["rows_typst"] = _prepare_table_typst_rows(media_copy)
            bcopy["media"] = media_copy

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
            all_items = bcopy.get("all_items") or []
            bcopy["title_typst"] = escape_typst_text(blk.get("title", "Glossar & Begriffserklärungen"))
            bcopy["items_typst"] = [
                {
                    "term": escape_typst_text(it["term"]),
                    "definition": escape_typst_text(it["definition"]),
                }
                for it in all_items
            ]

        elif btype == "publications":
            bcopy["title_typst"] = escape_typst_text(blk.get("title", "Weitere Publikationen"))
            items_typst = []
            for it in blk.get("items", []):
                fmt_d = it.get("formatted_date") or it.get("date", "")
                clean_t = it.get("clean_title") or it.get("title", "").strip().strip('"').strip('«').strip('»')
                items_typst.append({
                    "title": escape_typst_text(clean_t),
                    "subtitle": escape_typst_text(it.get("subtitle", "")),
                    "date": escape_typst_text(fmt_d),
                    "formatted_date": escape_typst_text(fmt_d),
                    "category": escape_typst_text(it.get("category", "")),
                    "url": str(it.get("url", "")).strip(),
                    "enabled": bool(it.get("enabled", True)),
                })
            bcopy["items_typst"] = items_typst

        elif btype == "kpi_cards":
            enriched_cards: list[dict[str, Any]] = []
            for card in blk.get("cards", []):
                if not isinstance(card, dict):
                    continue
                pal = get_kpi_tone_palette(card.get("tone"))
                icon_id = str(card.get("icon", "") or "").strip()
                resolved_icon = ""
                if icon_id:
                    icon_svg = render_kpi_icon_svg(icon_id, stroke_color=pal["accent"], size_px=24)
                    if icon_svg:
                        resolved_icon = _materialize_svg_asset(work_dir, icon_svg, prefix="kpi_icon_")
                enriched_cards.append({
                    "icon": icon_id,
                    "resolved_icon": resolved_icon,
                    "label": str(card.get("label", "") or ""),
                    "value": str(card.get("value", "") or ""),
                    "subtext": str(card.get("subtext", "") or ""),
                    "tone": pal["id"],
                    "accent_hex": pal["accent"],
                    "tint_hex": pal["tint"],
                    "badge_hex": pal["badge"],
                    "border_hex": pal["border"],
                })
            bcopy["cards"] = enriched_cards

        enriched_blocks.append(bcopy)

    payload["blocks"] = _group_blocks_into_render_items(enriched_blocks)
    return payload


def _get_template_typ_path(template_id: str) -> Path:
    candidate = TEMPLATES_DIR / template_id / "template.typ"
    if candidate.exists():
        return candidate
    return TEMPLATES_DIR / "investment_focus" / "template.typ"


def _ensure_typst_workspace(template_id: str) -> tuple[Path, Path]:
    """
    Synchronisiert gemeinsame Typst-Basismodule (`templates/_common/*.typ`), das
    angeforderte Template sowie das LUKB-Logo in das persistente Arbeitsverzeichnis `TYPST_CACHE_DIR`.
    Kopiert Dateien nur, wenn sie nicht existieren oder sich die Quell-mtime geändert hat,
    und invalidiert bei Template-Änderungen den `typst.Compiler`-Cache.
    Gibt (work_typ, TYPST_CACHE_DIR) zurück.
    """
    TYPST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common_changed = False
    tpl_changed = False

    common_src = TEMPLATES_DIR / "_common"
    if common_src.exists():
        common_dst = TYPST_CACHE_DIR / "_common"
        common_dst.mkdir(parents=True, exist_ok=True)
        for src_file in common_src.glob("*.typ"):
            dst_file = common_dst / src_file.name
            if not dst_file.exists() or src_file.stat().st_mtime > dst_file.stat().st_mtime:
                dst_file.write_bytes(src_file.read_bytes())
                common_changed = True

    template_path = _get_template_typ_path(template_id)
    tpl_folder_name = template_path.parent.name
    tpl_dst_dir = TYPST_CACHE_DIR / tpl_folder_name
    tpl_dst_dir.mkdir(parents=True, exist_ok=True)
    work_typ = tpl_dst_dir / "document.typ"
    if not work_typ.exists() or template_path.stat().st_mtime > work_typ.stat().st_mtime:
        work_typ.write_bytes(template_path.read_bytes())
        tpl_changed = True

    if LUKB_LOGO_SVG_PATH.exists():
        logo_dst = TYPST_CACHE_DIR / "LUKB-Logo.svg"
        if not logo_dst.exists() or LUKB_LOGO_SVG_PATH.stat().st_mtime > logo_dst.stat().st_mtime:
            logo_dst.write_bytes(LUKB_LOGO_SVG_PATH.read_bytes())

    if common_changed:
        invalidate_compiler_cache()
    elif tpl_changed:
        invalidate_compiler_cache(template_id)

    return work_typ, TYPST_CACHE_DIR


def _get_font_paths() -> list[Path]:
    paths: list[Path] = []
    if FONTS_DIR.exists():
        paths.append(FONTS_DIR)
    return paths


def invalidate_compiler_cache(template_id: str | None = None) -> None:
    """Invalidiert den Typst.Compiler-Cache für ein Template oder alle Templates."""
    with _COMPILER_LOCK:
        if template_id:
            _COMPILER_CACHE.pop(template_id, None)
        else:
            _COMPILER_CACHE.clear()


def _get_or_create_compiler(template_id: str, work_typ: Path, root_dir: Path) -> typst.Compiler:
    """Holt eine wiederverwendbare Typst.Compiler-Instanz aus dem Cache oder initialisiert sie."""
    with _COMPILER_LOCK:
        compiler = _COMPILER_CACHE.get(template_id)
        if compiler is None:
            compiler = typst.Compiler(
                input=work_typ,
                root=root_dir,
                font_paths=_get_font_paths(),
            )
            _COMPILER_CACHE[template_id] = compiler
        return compiler


def _compile_typst(
    doc: ArticleDocument,
    output_format: str,
    interactive_links: bool = False,
) -> bytes | list[bytes]:
    """Gemeinsame Typst-Kompilierungspipeline für PDF (`pdf`) und Seiten-SVGs (`svg`)."""
    work_typ, work_dir = _ensure_typst_workspace(doc.template_id)
    payload = _prepare_typst_payload(doc, work_dir, interactive_links=interactive_links)
    article_json_str = json.dumps(payload, ensure_ascii=False)

    try:
        compiler = _get_or_create_compiler(doc.template_id, work_typ, work_dir)
        with _COMPILER_LOCK:
            return compiler.compile(
                format=output_format,
                sys_inputs={"article_json": article_json_str},
            )
    except Exception as exc:
        logger.warning(
            f"Fehler im Typst.Compiler-Cache für {output_format.upper()} ({exc}), Fallback auf Einmal-Kompilierung."
        )
        invalidate_compiler_cache(doc.template_id)
        return typst.compile(
            input=work_typ,
            root=work_dir,
            format=output_format,
            font_paths=_get_font_paths(),
            sys_inputs={"article_json": article_json_str},
        )


def render_pdf_bytes(doc: ArticleDocument, interactive_links: bool = False) -> bytes:
    """Kompiliert ein ArticleDocument mit der aktuellsten Typst-Engine zu einem PDF (bytes)."""
    pdf_bytes = _compile_typst(doc, "pdf", interactive_links=interactive_links)
    if isinstance(pdf_bytes, list):
        return pdf_bytes[0]
    return pdf_bytes


def render_publication_package(doc: ArticleDocument) -> tuple[bytes | None, str]:
    """
    Rendert PDF und Web-HTML für einen Publikationsauftrag unter Verwendung
    desselben Marktdatenstands für beide Ausgabeformate.
    """
    with publication_timeseries_snapshot():
        pdf_bytes: bytes | None = None
        try:
            pdf_bytes = render_pdf_bytes(doc)
        except Exception:
            pdf_bytes = None
        web_html = render_web_html(doc)
    return pdf_bytes, web_html


def render_preview_pdf_base64(doc: ArticleDocument) -> str:
    """Kompiliert ein ArticleDocument in-memory zu einem interaktiven Vorschau-PDF (Base64)."""
    pdf_bytes = render_pdf_bytes(doc, interactive_links=True)
    return base64.b64encode(pdf_bytes).decode("ascii")


def render_preview_svg_pages(doc: ArticleDocument) -> list[str]:
    """
    Kompiliert ein ArticleDocument in-memory zu einer Liste von SVG-Strings (eine SVG pro PDF-Seite).
    Nutzt eine langlebige `typst.Compiler`-Instanz mit persistentem Rust-Cache für maximale Geschwindigkeit.
    """
    compiled = _compile_typst(doc, "svg")
    pages_bytes = [compiled] if isinstance(compiled, bytes) else list(compiled)
    return [p.decode("utf-8") for p in pages_bytes]


_ANCHOR_TAG_RE = re.compile(r"<a\b([^>]*)>", re.IGNORECASE)
_INLINE_FOOTNOTE_RE = re.compile(r"<footnote\b[^>]*>(.*?)</footnote\s*>", re.IGNORECASE | re.DOTALL)


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


def _transform_web_inline_footnotes(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Ersetzt Inline-`<footnote>...</footnote>`-Tags in RichText- und Callout-Blöcken durch
    nummerierte, klickbare Hochzahlen (`<sup class="lukb-fn-ref" id="fnref-1"><a href="#fn-1">[1]</a></sup>`)
    und sammelt die Fussnotentexte chronologisch ein.
    Falls ein `footnotes`-Block im Artikel existiert, werden die Inline-Fussnoten dort ergänzt;
    andernfalls werden sie als `auto_footnotes` am Artikelende ausgegeben.
    """
    collected: list[dict[str, str]] = []
    counter = 0

    def _replace_in_html(raw_html: str) -> str:
        nonlocal counter
        if not raw_html or "<footnote" not in raw_html.lower():
            return raw_html

        def _fn_repl(m: re.Match[str]) -> str:
            nonlocal counter
            counter += 1
            inner_raw = m.group(1) or ""
            plain_text = html.unescape(re.sub(r"<[^>]+>", " ", inner_raw)).strip()
            num_str = str(counter)
            collected.append({"num": num_str, "text": plain_text})
            esc_title = html.escape(plain_text, quote=True)
            return (
                f'<sup class="lukb-fn-ref" id="fnref-{num_str}">'
                f'<a href="#fn-{num_str}" title="{esc_title}">[{num_str}]</a>'
                f"</sup>"
            )

        return _INLINE_FOOTNOTE_RE.sub(_fn_repl, raw_html)

    has_footnotes_block = False
    for blk in blocks:
        btype = blk.get("type")
        if btype in ("richtext", "callout"):
            blk["html"] = _replace_in_html(sanitize_richtext_html(blk.get("html", "")))
        elif btype == "media_text":
            blk["html"] = _replace_in_html(sanitize_richtext_html(blk.get("html", "")))
            if blk.get("aside_html"):
                blk["aside_html"] = _replace_in_html(sanitize_richtext_html(blk.get("aside_html", "")))
        elif btype == "footnotes":
            has_footnotes_block = True

    if not collected:
        return []

    if has_footnotes_block:
        for blk in blocks:
            if blk.get("type") == "footnotes":
                existing_items = list(blk.get("items") or [])
                existing_texts = {str(it.get("text") or "").strip() for it in existing_items}
                for fn in collected:
                    if fn["text"] and fn["text"] not in existing_texts:
                        existing_items.append(fn)
                        existing_texts.add(fn["text"])
                blk["items"] = existing_items
                break
        return []

    return collected


def render_web_html(doc: ArticleDocument) -> str:
    """
    Rendert ein ArticleDocument als eigenständiges, responsives HTML5-Dokument
    inkl. eingebetteter Data-URI-Grafiken aus der MSSQL-Datenbank.
    """
    payload = _prepare_common_article_payload(doc)
    raw_blocks = payload.get("blocks", [])
    payload["auto_footnotes"] = _transform_web_inline_footnotes(raw_blocks)
    asset_records = _fetch_doc_asset_records(raw_blocks, article_id=doc.id)
    asset_uri_cache: dict[str, str] = {}
    for blk in raw_blocks:
        if blk.get("type") in ("richtext", "callout"):
            blk["html"] = _normalize_inline_links_html(blk.get("html", ""))
        elif blk.get("type") == "figure":
            asset_id = blk.get("asset_id", "")
            data_uri = ""
            if asset_id:
                if asset_id not in asset_uri_cache:
                    asset_record = asset_records.get(asset_id)
                    if asset_record and asset_record.get("data"):
                        b64 = base64.b64encode(asset_record["data"]).decode("ascii")
                        mime = asset_record.get("mime_type", "image/svg+xml")
                        asset_uri_cache[asset_id] = f"data:{mime};base64,{b64}"
                    else:
                        asset_uri_cache[asset_id] = ""
                data_uri = asset_uri_cache[asset_id]
            blk["data_uri"] = data_uri
        elif blk.get("type") in ("db_chart", "custom_chart"):
            svg_markup = render_block_chart_svg(
                blk,
                embed_fonts=True,
                max_date=doc.metadata.publication_date,
            )
            b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
            blk["data_uri"] = f"data:image/svg+xml;base64,{b64}"
        elif blk.get("type") == "media_text":
            blk["html"] = _normalize_inline_links_html(blk.get("html", ""))
            if blk.get("aside_html"):
                blk["aside_html"] = _normalize_inline_links_html(blk.get("aside_html", ""))
            media = blk.get("media") if isinstance(blk.get("media"), dict) else {}
            mtype = blk.get("media_type") or media.get("type") or "figure"
            media["type"] = mtype
            if mtype == "figure":
                asset_id = media.get("asset_id", "")
                data_uri = ""
                if asset_id:
                    if asset_id not in asset_uri_cache:
                        asset_record = asset_records.get(asset_id)
                        if asset_record and asset_record.get("data"):
                            b64 = base64.b64encode(asset_record["data"]).decode("ascii")
                            mime = asset_record.get("mime_type", "image/svg+xml")
                            asset_uri_cache[asset_id] = f"data:{mime};base64,{b64}"
                        else:
                            asset_uri_cache[asset_id] = ""
                    data_uri = asset_uri_cache[asset_id]
                media["data_uri"] = data_uri
            elif mtype in ("db_chart", "custom_chart"):
                svg_markup = render_block_chart_svg(
                    media,
                    embed_fonts=True,
                    max_date=doc.metadata.publication_date,
                )
                b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
                media["data_uri"] = f"data:image/svg+xml;base64,{b64}"
            blk["media"] = media
        elif blk.get("type") == "kpi_cards":
            web_cards: list[dict[str, Any]] = []
            for card in blk.get("cards", []):
                if not isinstance(card, dict):
                    continue
                pal = get_kpi_tone_palette(card.get("tone"))
                icon_id = str(card.get("icon", "") or "").strip()
                icon_svg = render_kpi_icon_svg(icon_id, stroke_color=pal["accent"], size_px=20) if icon_id else ""
                web_cards.append({
                    **card,
                    "tone": pal["id"],
                    "palette": pal,
                    "icon_svg": icon_svg,
                })
            blk["cards"] = web_cards

    payload["blocks"] = _group_blocks_into_render_items(payload.get("blocks", []))

    global _LOGO_DATA_URI_CACHE
    if _LOGO_DATA_URI_CACHE is None and LUKB_LOGO_SVG_PATH.exists():
        b64_logo = base64.b64encode(LUKB_LOGO_SVG_PATH.read_bytes()).decode("ascii")
        _LOGO_DATA_URI_CACHE = f"data:image/svg+xml;base64,{b64_logo}"
    logo_data_uri = _LOGO_DATA_URI_CACHE or ""

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
    """Konvertiert SVG-Vektorgrafiken via temporäre Typst-Kompilierung in druckscharfe PNGs für Word (mit LRU-Cache)."""
    if not svg_markup or not svg_markup.strip():
        return None
    cache_key = f"{ppi}:{hashlib.sha256(svg_markup.encode('utf-8')).hexdigest()}"
    with _SVG_PNG_CACHE_LOCK:
        cached = _SVG_PNG_CACHE.get(cache_key)
        if cached is not None:
            _SVG_PNG_CACHE.move_to_end(cache_key)
            return cached
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
            png_bytes = typst.compile(
                typ_path,
                format="png",
                ppi=ppi,
                font_paths=_get_font_paths(),
            )
            if isinstance(png_bytes, list):
                png_bytes = png_bytes[0]
            if png_bytes:
                with _SVG_PNG_CACHE_LOCK:
                    _SVG_PNG_CACHE[cache_key] = png_bytes
                    _SVG_PNG_CACHE.move_to_end(cache_key)
                    while len(_SVG_PNG_CACHE) > _SVG_PNG_CACHE_MAX_SIZE:
                        _SVG_PNG_CACHE.popitem(last=False)
            return png_bytes
    except Exception:
        return None


class _DocxHtmlRunParser(HTMLParser):
    def __init__(self, paragraph, footnote_collector: list[dict[str, str]] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraph = paragraph
        self.footnote_collector = footnote_collector
        self.is_bold = False
        self.is_italic = False
        self.is_underline = False
        self.in_footnote = False
        self.current_footnote_parts: list[str] = []
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
            if not self.in_footnote:
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
            self.in_footnote = True
            self.current_footnote_parts = []

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
            if href and not self.in_footnote:
                r = self.paragraph.add_run(" ↗")
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)
        elif t == "span":
            if self.tooltip_stack:
                self.tooltip_stack.pop()
        elif t == "footnote":
            self.in_footnote = False
            fn_text = "".join(self.current_footnote_parts).strip()
            self.current_footnote_parts = []
            if self.footnote_collector is not None:
                fn_num = len(self.footnote_collector) + 1
                self.footnote_collector.append({"num": str(fn_num), "text": fn_text})
                r = self.paragraph.add_run(f"[{fn_num}]")
                r.font.superscript = True
                r.font.bold = True
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(0x00, 0x9F, 0xE3)
            elif fn_text:
                r = self.paragraph.add_run(f" [{fn_text}]")
                r.font.size = Pt(8.0)
                r.font.color.rgb = RGBColor(0x00, 0x9F, 0xE3)

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self.in_footnote:
            self.current_footnote_parts.append(data)
            return
        run = self.paragraph.add_run(data)
        run.bold = self.is_bold
        run.italic = self.is_italic
        run.underline = self.is_underline
        if self.link_stack and self.link_stack[-1]:
            run.font.color.rgb = RGBColor(0x00, 0x28, 0x55)


_DOCX_BLOCK_SPLIT_RE = re.compile(r"<(p|li)([^>]*)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)


def _add_html_runs_to_paragraph(
    paragraph,
    html_fragment: str,
    footnote_collector: list[dict[str, str]] | None = None,
    already_sanitized: bool = False,
) -> None:
    if not html_fragment:
        return
    parser = _DocxHtmlRunParser(paragraph, footnote_collector=footnote_collector)
    try:
        frag = html_fragment if already_sanitized else sanitize_richtext_html(html_fragment)
        parser.feed(frag)
        parser.close()
    except Exception:
        # Fallback auf einfaches unescaping falls fehlerhaftes HTML
        plain = re.sub(r"<[^>]+>", " ", html_fragment).strip()
        paragraph.add_run(html.unescape(plain))


def _render_richtext_into_docx(
    doc_or_cell,
    html_content: str,
    footnote_collector: list[dict[str, str]] | None = None,
) -> None:
    sanitized = sanitize_richtext_html(html_content)
    if "<p" not in sanitized and "<li" not in sanitized:
        p = doc_or_cell.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.15
        _add_html_runs_to_paragraph(p, sanitized, footnote_collector=footnote_collector, already_sanitized=True)
        return

    matches = list(_DOCX_BLOCK_SPLIT_RE.finditer(sanitized))
    if not matches:
        plain = re.sub(r"<[^>]+>", " ", sanitized).strip()
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
            _add_html_runs_to_paragraph(p, inner, footnote_collector=footnote_collector, already_sanitized=True)
        else:
            p = doc_or_cell.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.15
            _add_html_runs_to_paragraph(p, inner, footnote_collector=footnote_collector, already_sanitized=True)


def _get_cached_logo_png_bytes() -> bytes | None:
    """Rendert das statische LUKB-Logo einmalig als PNG für den Word-Export und cached es im Speicher."""
    global _LOGO_PNG_CACHE
    if _LOGO_PNG_CACHE is None and LUKB_LOGO_SVG_PATH.exists():
        _LOGO_PNG_CACHE = _svg_to_png_bytes(
            LUKB_LOGO_SVG_PATH.read_text(encoding="utf-8"), ppi=200.0
        )
    return _LOGO_PNG_CACHE


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
    logo_png = _get_cached_logo_png_bytes()
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
    common_payload = _prepare_common_article_payload(doc_model)
    raw_common_blocks = common_payload.get("blocks", [])
    docx_asset_records = _fetch_doc_asset_records(raw_common_blocks, article_id=doc_model.id)
    grouped_blocks = _group_blocks_into_render_items(raw_common_blocks)
    docx_inline_footnotes: list[dict[str, str]] = []
    docx_has_footnotes_block = False

    def _render_block(container, blk):
        nonlocal docx_has_footnotes_block
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
            _render_richtext_into_docx(container, blk.get("html", ""), footnote_collector=docx_inline_footnotes)

        elif btype == "callout":
            tbl = container.add_table(rows=1, cols=1)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = tbl.rows[0].cells[0]
            _set_docx_cell_background(cell, "E4F4FE")
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
            _render_richtext_into_docx(cell, blk.get("html", ""), footnote_collector=docx_inline_footnotes)
            container.add_paragraph().paragraph_format.space_after = Pt(4)

        elif btype in ("figure", "db_chart", "custom_chart"):
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
            if btype in ("db_chart", "custom_chart"):
                svg_code = render_block_chart_svg(
                    blk,
                    embed_fonts=False,
                    max_date=doc_model.metadata.publication_date,
                )
                img_bytes = _svg_to_png_bytes(svg_code, ppi=144.0)
            else:
                asset_id = blk.get("asset_id", "")
                if asset_id:
                    rec = docx_asset_records.get(asset_id)
                    if rec and rec.get("data"):
                        data = rec["data"]
                        mime = rec.get("mime_type", "")
                        if "svg" in mime.lower() or rec.get("filename", "").lower().endswith(".svg"):
                            img_bytes = _svg_to_png_bytes(data.decode("utf-8", errors="ignore"), ppi=144.0)
                        else:
                            img_bytes = data
            src = blk.get("source", "").strip()
            if img_bytes:
                try:
                    p_pic = container.add_paragraph()
                    p_pic.paragraph_format.space_before = Pt(4)
                    p_pic.paragraph_format.space_after = Pt(2)
                    if src:
                        p_pic.paragraph_format.keep_with_next = True
                    r_pic = p_pic.add_run()
                    scale_pct = max(75, min(100, int(blk.get("scale_pct") or 100)))
                    scale_mode = blk.get("scale_mode") or "proportional"
                    if btype == "figure" and scale_mode == "original":
                        pic = r_pic.add_picture(io.BytesIO(img_bytes))
                        max_w = Inches(6.0)
                        if pic.width > max_w:
                            ratio = max_w / pic.width
                            pic.width = max_w
                            pic.height = int(pic.height * ratio)
                    elif btype == "figure" and scale_pct < 100 and scale_mode == "squeeze_y":
                        pic = r_pic.add_picture(io.BytesIO(img_bytes), width=Inches(6.0))
                        pic.height = int(pic.height * (scale_pct / 100.0))
                    elif btype == "figure" and scale_pct < 100:
                        r_pic.add_picture(io.BytesIO(img_bytes), width=Inches(6.0 * (scale_pct / 100.0)))
                    else:
                        r_pic.add_picture(io.BytesIO(img_bytes), width=Inches(6.0))
                except Exception:
                    pass

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
            raw_font_step = blk.get("font_size_step", 0)
            try:
                font_step = max(-2, min(0, int(raw_font_step or 0)))
            except (TypeError, ValueError):
                font_step = 0
            table_font_pt = max(5.0, 8.5 + font_step * 0.7)
            raw_row_step = blk.get("row_spacing_step", 0)
            try:
                row_step = max(-2, min(0, int(raw_row_step or 0)))
            except (TypeError, ValueError):
                row_step = 0
            hdr_pad_y = 45 if row_step == -2 else (85 if row_step == -1 else 130)
            body_pad_y = 25 if row_step == -2 else (55 if row_step == -1 else 90)
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

                is_lukb_design = blk.get("table_design", "lukb_design") != "standard"
                if show_header:
                    hdr_cells = t.rows[0].cells
                    for c_idx, col in enumerate(cols):
                        col_w = Inches(total_table_inches * (weights[c_idx] / total_weight))
                        t.columns[c_idx].width = col_w
                        cell = hdr_cells[c_idx]
                        cell.width = col_w
                        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                        _set_docx_cell_background(cell, "FFFFFF" if is_lukb_design else "002855")
                        _set_docx_cell_margins(cell, top=hdr_pad_y, bottom=hdr_pad_y, left=150, right=150)
                        p = cell.paragraphs[0]
                        c_align = col.get("align")
                        p.alignment = (
                            WD_ALIGN_PARAGRAPH.RIGHT if c_align == "right"
                            else WD_ALIGN_PARAGRAPH.CENTER if c_align == "center"
                            else WD_ALIGN_PARAGRAPH.JUSTIFY if c_align == "justify"
                            else WD_ALIGN_PARAGRAPH.LEFT
                        )
                        run = p.add_run(col.get("title", ""))
                        run.bold = True
                        run.font.color.rgb = RGBColor(0x1A, 0x24, 0x33) if is_lukb_design else RGBColor(0xFF, 0xFF, 0xFF)
                        run.font.size = Pt(table_font_pt)

                src = blk.get("source", "").strip()
                row_offset = 1 if show_header else 0
                for r_idx, row in enumerate(rows):
                    is_total = blk.get("highlight_last_row") and (r_idx == len(rows) - 1)
                    is_last_row = (r_idx == len(rows) - 1)
                    row_cells = t.rows[r_idx + row_offset].cells
                    if is_lukb_design:
                        bg_hex = "BCE2FE" if is_total else "FFFFFF"
                    else:
                        bg_hex = "E6EEF7" if is_total else ("F4F7FA" if r_idx % 2 == 1 else "FFFFFF")
                    for c_idx, col in enumerate(cols):
                        col_w = Inches(total_table_inches * (weights[c_idx] / total_weight))
                        if not show_header:
                            t.columns[c_idx].width = col_w
                        cell = row_cells[c_idx]
                        cell.width = col_w
                        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                        _set_docx_cell_background(cell, bg_hex)
                        _set_docx_cell_margins(cell, top=body_pad_y, bottom=body_pad_y, left=150, right=150)
                        p = cell.paragraphs[0]
                        c_align = col.get("align")
                        p.alignment = (
                            WD_ALIGN_PARAGRAPH.RIGHT if c_align == "right"
                            else WD_ALIGN_PARAGRAPH.CENTER if c_align == "center"
                            else WD_ALIGN_PARAGRAPH.JUSTIFY if c_align == "justify"
                            else WD_ALIGN_PARAGRAPH.LEFT
                        )
                        if is_last_row and src:
                            p.paragraph_format.keep_with_next = True
                        val = str(row.get(col.get("field", ""), ""))
                        cell_color = (
                            RGBColor(0x1A, 0x24, 0x33) if is_lukb_design
                            else (RGBColor(0x00, 0x28, 0x55) if is_total else RGBColor(0x1A, 0x24, 0x33))
                        )
                        if re.search(r"</?(?:b|strong|i|em|u|sub|sup|a|br|p|div|span)\b", val, re.IGNORECASE):
                            norm_val = val.replace("\r\n", "\n").replace("\n", "<br>")
                            norm_val = re.sub(r"</(?:p|div)>\s*<(?:p|div)\b[^>]*>", "<br>", norm_val, flags=re.IGNORECASE)
                            norm_val = re.sub(r"</?(?:p|div)\b[^>]*>", "", norm_val, flags=re.IGNORECASE)
                            _add_html_runs_to_paragraph(p, norm_val, footnote_collector=docx_inline_footnotes)
                            for run in p.runs:
                                run.font.size = Pt(table_font_pt)
                                if is_total:
                                    run.bold = True
                                if run.font.color.rgb is None:
                                    run.font.color.rgb = cell_color
                        else:
                            run = p.add_run(val)
                            run.bold = is_total
                            run.font.color.rgb = cell_color
                            run.font.size = Pt(table_font_pt)

                for m in blk.get("merges") or []:
                    try:
                        r0 = int(m.get("row", 0))
                        c0 = int(m.get("col", 0))
                        rspan = int(m.get("rowspan", 1))
                        cspan = int(m.get("colspan", 1))
                    except (TypeError, ValueError):
                        continue
                    if r0 < 0 or c0 < 0 or r0 >= len(rows) or c0 >= len(cols):
                        continue
                    r1 = min(len(rows) - 1, r0 + max(1, rspan) - 1)
                    c1 = min(len(cols) - 1, c0 + max(1, cspan) - 1)
                    if r1 == r0 and c1 == c0:
                        continue
                    for rr in range(r0, r1 + 1):
                        for cc in range(c0, c1 + 1):
                            if rr != r0 or cc != c0:
                                t.cell(rr + row_offset, cc).text = ""
                    t.cell(r0 + row_offset, c0).merge(t.cell(r1 + row_offset, c1))

            if src:
                psrc = container.add_paragraph()
                psrc.paragraph_format.space_before = Pt(3)
                psrc.paragraph_format.space_after = Pt(8)
                r = psrc.add_run(src)
                r.font.size = Pt(8.0)
                r.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)
                r.italic = True

        elif btype == "media_text":
            mt_title = blk.get("title", "").strip()
            if mt_title:
                pt = container.add_paragraph()
                pt.paragraph_format.space_before = Pt(10)
                pt.paragraph_format.space_after = Pt(4)
                r = pt.add_run(mt_title)
                r.bold = True
                r.font.size = Pt(10.5)
                r.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

            media = blk.get("media") if isinstance(blk.get("media"), dict) else {}
            mtype = blk.get("media_type") or media.get("type") or "figure"
            media_copy = dict(media)
            media_copy["type"] = mtype
            pos = blk.get("media_position", "auto")
            aside_html = (blk.get("aside_html") or "").strip()
            style_preset = blk.get("style_preset", "plain")

            def _render_mt_media(target_container, img_width_in: float):
                if mtype == "table":
                    _render_block(target_container, media_copy)
                else:
                    img_bytes = None
                    if mtype in ("db_chart", "custom_chart"):
                        svg_code = render_block_chart_svg(
                            media_copy,
                            embed_fonts=False,
                            max_date=doc_model.metadata.publication_date,
                        )
                        img_bytes = _svg_to_png_bytes(svg_code, ppi=144.0)
                    else:
                        aid = media_copy.get("asset_id", "")
                        if aid:
                            rec = docx_asset_records.get(aid)
                            if rec and rec.get("data"):
                                data = rec["data"]
                                mime = rec.get("mime_type", "")
                                if "svg" in mime.lower() or rec.get("filename", "").lower().endswith(".svg"):
                                    img_bytes = _svg_to_png_bytes(data.decode("utf-8", errors="ignore"), ppi=144.0)
                                else:
                                    img_bytes = data
                    if img_bytes:
                        try:
                            p_pic = target_container.add_paragraph()
                            p_pic.paragraph_format.space_before = Pt(2)
                            p_pic.paragraph_format.space_after = Pt(2)
                            p_pic.add_run().add_picture(io.BytesIO(img_bytes), width=Inches(img_width_in))
                        except Exception:
                            pass

            if pos in ("top", "bottom"):
                if pos == "top":
                    _render_mt_media(container, 5.8)
                    _render_richtext_into_docx(container, blk.get("html", ""), footnote_collector=docx_inline_footnotes)
                else:
                    _render_richtext_into_docx(container, blk.get("html", ""), footnote_collector=docx_inline_footnotes)
                    _render_mt_media(container, 5.8)
                if aside_html:
                    _render_richtext_into_docx(container, aside_html, footnote_collector=docx_inline_footnotes)
            else:
                num_cols = 3 if aside_html else 2
                tbl = container.add_table(rows=1, cols=num_cols)
                tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                tbl.autofit = False
                total_w = 6.5
                m_pct = float(blk.get("media_width_pct") or 30) / 100.0
                a_pct = float(blk.get("aside_width_pct") or 26) / 100.0 if aside_html else 0.0
                t_pct = max(0.2, 1.0 - m_pct - a_pct)
                if pos == "right":
                    col_specs = [("text", t_pct), ("media", m_pct)]
                else:
                    col_specs = [("media", m_pct), ("text", t_pct)]
                if aside_html:
                    col_specs.append(("aside", a_pct))

                bg_hex = None
                if style_preset == "zebra" and (blk.get("_zebra_index", 0) % 2 == 0):
                    bg_hex = "F4F7FA"
                elif style_preset == "card":
                    bg_hex = "FFFFFF"

                for c_idx, (kind, pct) in enumerate(col_specs):
                    cw = Inches(total_w * pct)
                    tbl.columns[c_idx].width = cw
                    cell = tbl.rows[0].cells[c_idx]
                    cell.width = cw
                    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                    if bg_hex:
                        _set_docx_cell_background(cell, bg_hex)
                    _set_docx_cell_margins(cell, top=110, bottom=110, left=120, right=120)
                    tcPr = cell._tc.get_or_add_tcPr()
                    border_col = "D6DEE8" if style_preset == "card" else "FFFFFF"
                    border_val = "single" if style_preset == "card" else "none"
                    tcPr.append(parse_xml(
                        f'<w:tcBorders {nsdecls("w")}>'
                        f'<w:top w:val="{border_val}" w:sz="4" w:space="0" w:color="{border_col}"/>'
                        f'<w:left w:val="{border_val}" w:sz="4" w:space="0" w:color="{border_col}"/>'
                        f'<w:bottom w:val="{border_val}" w:sz="4" w:space="0" w:color="{border_col}"/>'
                        f'<w:right w:val="{border_val}" w:sz="4" w:space="0" w:color="{border_col}"/>'
                        f'</w:tcBorders>'
                    ))
                    if kind == "media":
                        _render_mt_media(cell, max(1.2, total_w * pct - 0.25))
                    elif kind == "text":
                        _render_richtext_into_docx(cell, blk.get("html", ""), footnote_collector=docx_inline_footnotes)
                    else:
                        _render_richtext_into_docx(cell, aside_html, footnote_collector=docx_inline_footnotes)
                container.add_paragraph().paragraph_format.space_after = Pt(2)

        elif btype == "spacer":
            h_mm = blk.get("height_mm", 8)
            p = container.add_paragraph()
            p.paragraph_format.space_after = Pt(round(h_mm * 2.83465))

        elif btype == "colbreak":
            if blk.get("mode", "column") == "page" and hasattr(container, "add_page_break"):
                container.add_page_break()
            else:
                # Im linearen Word-Dokument dient der Spaltenumbruch als dezenter Abschnittstrenner
                p = container.add_paragraph()
                p.paragraph_format.space_before = Pt(10)
                p.paragraph_format.space_after = Pt(10)

        elif btype == "kpi_cards":
            kpi_title = str(blk.get("title", "") or "").strip()
            kpi_sub = str(blk.get("subtitle", "") or "").strip()
            if kpi_title:
                pt = container.add_paragraph()
                pt.paragraph_format.space_before = Pt(10)
                pt.paragraph_format.space_after = Pt(2 if kpi_sub else 5)
                r = pt.add_run(kpi_title)
                r.bold = True
                r.font.size = Pt(10.5)
                r.font.color.rgb = RGBColor(0x00, 0x28, 0x55)
            if kpi_sub:
                ps = container.add_paragraph()
                ps.paragraph_format.space_before = Pt(0)
                ps.paragraph_format.space_after = Pt(5)
                r = ps.add_run(kpi_sub)
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)

            cards = [c for c in (blk.get("cards") or []) if isinstance(c, dict)]
            if cards:
                req_cols = int(blk.get("columns_count") or 0)
                is_col = blk.get("layout", "full") == "column"
                max_cols = 2 if is_col else 4
                n_cols = min(len(cards), req_cols if req_cols > 0 else max_cols, max_cols)
                n_cols = max(1, n_cols)
                n_rows = (len(cards) + n_cols - 1) // n_cols
                style_preset = blk.get("style_preset", "tint")

                tbl = container.add_table(rows=n_rows, cols=n_cols)
                tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                tbl.autofit = False
                col_w = Inches(6.5 / n_cols)

                for r_idx in range(n_rows):
                    for c_idx in range(n_cols):
                        card_idx = r_idx * n_cols + c_idx
                        cell = tbl.rows[r_idx].cells[c_idx]
                        cell.width = col_w
                        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                        if card_idx >= len(cards):
                            tcPr = cell._tc.get_or_add_tcPr()
                            tcPr.append(parse_xml(
                                f'<w:tcBorders {nsdecls("w")}>'
                                f'<w:top w:val="none"/><w:left w:val="none"/>'
                                f'<w:bottom w:val="none"/><w:right w:val="none"/>'
                                f'</w:tcBorders>'
                            ))
                            continue

                        card = cards[card_idx]
                        pal = get_kpi_tone_palette(card.get("tone"))
                        accent_hex = pal["accent"].lstrip("#")
                        tint_hex = pal["tint"].lstrip("#")
                        border_hex = pal["border"].lstrip("#")

                        if style_preset == "tint":
                            bg_hex = tint_hex
                            top_b, left_b, bot_b, right_b = (
                                f'w:val="single" w:sz="6" w:color="{border_hex}"',
                                f'w:val="single" w:sz="6" w:color="{border_hex}"',
                                f'w:val="single" w:sz="6" w:color="{border_hex}"',
                                f'w:val="single" w:sz="6" w:color="{border_hex}"',
                            )
                        elif style_preset == "card_accent_top":
                            bg_hex = "FFFFFF"
                            top_b = f'w:val="single" w:sz="16" w:color="{accent_hex}"'
                            left_b = right_b = bot_b = 'w:val="single" w:sz="4" w:color="D6DEE8"'
                        elif style_preset == "card_accent_left":
                            bg_hex = "FAFBFD"
                            left_b = f'w:val="single" w:sz="20" w:color="{accent_hex}"'
                            top_b = right_b = bot_b = 'w:val="single" w:sz="4" w:color="D6DEE8"'
                        else:
                            bg_hex = "FFFFFF"
                            top_b = left_b = right_b = bot_b = 'w:val="single" w:sz="4" w:color="D6DEE8"'

                        _set_docx_cell_background(cell, bg_hex)
                        _set_docx_cell_margins(cell, top=hdr_pad_y, bottom=hdr_pad_y, left=150, right=150)
                        tcPr = cell._tc.get_or_add_tcPr()
                        tcPr.append(parse_xml(
                            f'<w:tcBorders {nsdecls("w")}>'
                            f'<w:top {top_b} w:space="0"/>'
                            f'<w:left {left_b} w:space="0"/>'
                            f'<w:bottom {bot_b} w:space="0"/>'
                            f'<w:right {right_b} w:space="0"/>'
                            f'</w:tcBorders>'
                        ))

                        p_head = cell.paragraphs[0]
                        p_head.paragraph_format.space_before = Pt(0)
                        p_head.paragraph_format.space_after = Pt(3)
                        icon_id = str(card.get("icon", "") or "").strip()
                        if icon_id:
                            badge_svg = render_kpi_icon_svg(
                                icon_id,
                                stroke_color=pal["accent"],
                                size_px=36,
                                badge_bg=pal["badge"],
                            )
                            png_bytes = _svg_to_png_bytes(badge_svg, ppi=144.0) if badge_svg else None
                            if png_bytes:
                                try:
                                    p_head.add_run().add_picture(io.BytesIO(png_bytes), width=Inches(0.24))
                                    p_head.add_run("  ")
                                except Exception:
                                    pass
                        lbl_txt = str(card.get("label", "") or "").strip()
                        if lbl_txt:
                            r_lbl = p_head.add_run(lbl_txt)
                            r_lbl.bold = True
                            r_lbl.font.size = Pt(8.0)
                            r_lbl.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)

                        val_txt = str(card.get("value", "") or "").strip()
                        if val_txt:
                            p_val = cell.add_paragraph()
                            p_val.paragraph_format.space_before = Pt(0)
                            p_val.paragraph_format.space_after = Pt(5)
                            r_val = p_val.add_run(val_txt)
                            r_val.bold = True
                            r_val.font.size = Pt(13.0)
                            r_val.font.color.rgb = RGBColor(0x00, 0x28, 0x55)

                        sub_txt = str(card.get("subtext", "") or "").strip()
                        if sub_txt:
                            p_sub = cell.add_paragraph()
                            p_sub.paragraph_format.space_before = Pt(0)
                            p_sub.paragraph_format.space_after = Pt(0)
                            r_sub = p_sub.add_run(sub_txt)
                            r_sub.font.size = Pt(8.0)
                            r_sub.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)

            kpi_src = str(blk.get("source", "") or "").strip()
            if kpi_src:
                psrc = container.add_paragraph()
                psrc.paragraph_format.space_before = Pt(3)
                psrc.paragraph_format.space_after = Pt(6)
                r = psrc.add_run(kpi_src)
                r.font.size = Pt(8.0)
                r.font.color.rgb = RGBColor(0x5A, 0x68, 0x7C)
                r.italic = True
            else:
                container.add_paragraph().paragraph_format.space_after = Pt(4)

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
            docx_has_footnotes_block = True
            title = blk.get("title", "").strip() or "Anmerkungen & Quellen"
            p = container.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(4)
            rt = p.add_run(title)
            rt.bold = True
            rt.font.size = Pt(11.5)
            rt.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)

            combined_fn = list(blk.get("items", []))
            existing_fn_texts = {str(it.get("text", "")).strip() for it in combined_fn}
            for inf in docx_inline_footnotes:
                if inf["text"] and inf["text"] not in existing_fn_texts:
                    combined_fn.append(inf)
                    existing_fn_texts.add(inf["text"])

            for item in combined_fn:
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
            all_items = blk.get("all_items") or _resolve_glossary_items(blk, common_payload.get("blocks", []))
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
                pi.paragraph_format.left_indent = Pt(14)
                pi.paragraph_format.first_line_indent = Pt(-14)
                r_dash = pi.add_run("– ")
                r_dash.bold = False
                r_dash.font.size = Pt(8.5)
                r_dash.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)
                clean_title = item.get("clean_title") or item.get("title", "").strip().strip('"').strip('«').strip('»')
                fmt_d = item.get("formatted_date") or format_publication_date(item.get("date", "")) or item.get("date", "")
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
            _set_docx_cell_background(cell, "BCE2FE")
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

    if docx_inline_footnotes and not docx_has_footnotes_block:
        _render_block(
            doc,
            {
                "type": "footnotes",
                "title": "Anmerkungen & Quellen",
                "items": docx_inline_footnotes,
            },
        )

    out_stream = io.BytesIO()
    doc.save(out_stream)
    return out_stream.getvalue()
