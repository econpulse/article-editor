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
import json
import mimetypes
import tempfile
from pathlib import Path
from typing import Any
import jinja2
import typst

from config import FONTS_DIR, TEMPLATES_DIR, WWW_DIR
from database.repository import get_asset
from schemas.article import ArticleDocument
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
        {"id": "market_flash", "name": "LUKB Market Flash (1-spaltig)", "columns": 1},
    ]


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


def render_web_html(doc: ArticleDocument) -> str:
    """
    Rendert ein ArticleDocument als eigenständiges, responsives HTML5-Dokument
    inkl. eingebetteter Data-URI-Grafiken aus der MSSQL-Datenbank.
    """
    payload = doc.model_dump()
    for blk in payload.get("blocks", []):
        if blk.get("type") == "figure":
            asset_id = blk.get("asset_id", "")
            data_uri = ""
            if asset_id:
                asset_record = get_asset(asset_id)
                if asset_record and asset_record.get("data"):
                    b64 = base64.b64encode(asset_record["data"]).decode("ascii")
                    mime = asset_record.get("mime_type", "image/svg+xml")
                    data_uri = f"data:{mime};base64,{b64}"
            blk["data_uri"] = data_uri

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
