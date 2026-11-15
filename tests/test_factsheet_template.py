"""
Test-Suite für das LUKB Factsheet-Template:
- Registry-Registrierung ("factsheet")
- Pre-filled Block-Initialisierung in create_new_article
- Typst-PDF-Rendering (exakt 2 A4-Seiten)
- Typst-SVG-Rendering (exakt 2 SVG-Vorschauseiten)
- Jinja2 Responsive Web-HTML-Rendering
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.repository import create_new_article, get_article, list_articles
from services.renderer import list_available_templates, render_pdf_bytes, render_preview_svg_pages, render_web_html


def test_factsheet_registry():
    templates = list_available_templates()
    fs_entry = next((t for t in templates if t.get("id") == "factsheet"), None)
    assert fs_entry is not None, "Template 'factsheet' fehlt in list_available_templates()"
    assert fs_entry.get("columns") == 2, "Factsheet sollte als 2-spaltiges Layout registriert sein"


def test_factsheet_creation_and_blocks():
    doc = create_new_article(template_id="factsheet", user="Test Analyst")
    assert doc.template_id == "factsheet"
    assert doc.metadata.title == "LUKB Expert-Ertrag"
    assert len(doc.blocks) >= 20, f"Erwartete mindestens 20 Blöcke im Factsheet, erhalten: {len(doc.blocks)}"

    # Typen-Prüfung der enthaltenen Blöcke
    block_types = {b["type"] for b in doc.blocks}
    assert "heading" in block_types
    assert "richtext" in block_types
    assert "table" in block_types
    assert "custom_chart" in block_types
    assert "callout" in block_types
    assert "colbreak" in block_types


def test_factsheet_pdf_and_svg_rendering():
    doc = create_new_article(template_id="factsheet", user="Test Analyst")

    # PDF-Kompilierung
    pdf_bytes = render_pdf_bytes(doc)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 20000, "PDF-Bytes sollten nicht leer sein"

    # SVG-Seiten-Kompilierung (Muss exakt 2 Seiten ergeben)
    svg_pages = render_preview_svg_pages(doc)
    assert len(svg_pages) == 2, f"Factsheet sollte exakt 2 Seiten umfassen, erhalten: {len(svg_pages)}"
    assert "<svg" in svg_pages[0]
    assert "<svg" in svg_pages[1]


def test_factsheet_web_html_rendering():
    doc = create_new_article(template_id="factsheet", user="Test Analyst")
    html_markup = render_web_html(doc)
    assert "lukb-factsheet-grid" in html_markup
    assert "Aus Prinzip nachhaltig" in html_markup
    assert "LUKB Expert-Ertrag" in html_markup
    assert "<!DOCTYPE html>" in html_markup


if __name__ == "__main__":
    test_factsheet_registry()
    print("PASS: test_factsheet_registry")
    test_factsheet_creation_and_blocks()
    print("PASS: test_factsheet_creation_and_blocks")
    test_factsheet_pdf_and_svg_rendering()
    print("PASS: test_factsheet_pdf_and_svg_rendering")
    test_factsheet_web_html_rendering()
    print("PASS: test_factsheet_web_html_rendering")
    print("\nAll Factsheet template tests PASSED successfully!")
