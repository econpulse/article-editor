"""
LUKB Investment Office — Export- & Download-Handler.
Bereitstellung von Typst-PDF, Word (DOCX), Web-HTML und Posit Connect Deploy-Bundle (.tar.gz).
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Callable
from shiny import Outputs, render

from schemas.article import ArticleDocument
from services.portal_publisher import create_connect_bundle
from services.renderer import (
    render_docx_bytes,
    render_pdf_bytes,
    render_web_html,
)


def slugify_filename(title: str) -> str:
    """Bereinigt einen Artikel-Titel für die Verwendung als Dateiname."""
    cleaned = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß_-]+", "_", title.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:60] or "LUKB_Publikation"


def register_download_handlers(
    output: Outputs,
    get_current_doc: Callable[[], ArticleDocument | None],
) -> None:
    """Registriert alle Export-Download-Buttons an der Shiny-Session."""

    # Posit Connect Static Bundle Download (.tar.gz)
    @render.download_button(
        filename=lambda: f"connect_static_portal_{datetime.now().strftime('%Y%m%d_%H%M')}.tar.gz",
        media_type="application/gzip",
    )
    def download_portal_bundle():
        bundle_path = create_connect_bundle()
        return str(bundle_path)

    # Word-Export (.docx) via python-docx
    @render.download_button(
        filename=lambda: f"{slugify_filename(get_current_doc().metadata.title if get_current_doc() else 'Publikation')}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    def download_docx():
        doc = get_current_doc()
        if doc is None:
            return
        yield render_docx_bytes(doc)

    # PDF-Export via Typst
    @render.download_button(
        filename=lambda: f"{slugify_filename(get_current_doc().metadata.title if get_current_doc() else 'Publikation')}.pdf",
        media_type="application/pdf",
    )
    def download_pdf():
        doc = get_current_doc()
        if doc is None:
            return
        yield render_pdf_bytes(doc)

    # Web-HTML-Export via Jinja2
    @render.download_button(
        filename=lambda: f"{slugify_filename(get_current_doc().metadata.title if get_current_doc() else 'Publikation')}.html",
        media_type="text/html",
    )
    def download_html():
        doc = get_current_doc()
        if doc is None:
            return
        yield render_web_html(doc).encode("utf-8")
