"""
Tests für Rich-Text-Formatierung (Bold, Links, Zeilenumbrüche) in Tabellenzellen:
- HTML-zu-Typst-Konvertierung (`table_cell_html_to_typst`)
- Typst-Payload-Aufbereitung für `table` und `media_text` (`table`)
- End-to-End PDF/SVG-Kompilierung mit Typst (inkl. langer Tabelle > 8 Zeilen)
- DOCX-Export mit formatierten Runs in Tabellenzellen
"""

from __future__ import annotations

import io
from pathlib import Path

import docx
import pytest

from schemas.article import ArticleDocument, ArticleMetadata
from services.html_to_typst import table_cell_html_to_typst
from services.renderer import _prepare_typst_payload, render_docx_bytes, render_pdf_bytes


def test_table_cell_html_to_typst_plaintext_and_html():
    # Plaintext mit Sonderzeichen & Zeilenumbruch bleibt sicher escaped
    plain = table_cell_html_to_typst("A & B < C\n100 % #1")
    assert "\\<" in plain
    assert "\\#" in plain
    assert "\\\n" in plain

    # Bold & Italic
    bold_typst = table_cell_html_to_typst("<b>Aktien</b> und <em>Renten</em>")
    assert "#strong[Aktien]" in bold_typst
    assert "#emph[Renten]" in bold_typst

    # Link
    link_typst = table_cell_html_to_typst(
        'Mehr unter <a href="https://www.lukb.ch/news" target="_blank">LUKB News</a>'
    )
    assert '#link("https://www.lukb.ch/news")' in link_typst
    assert "LUKB News" in link_typst

    # Kombination mit <br> und ohne #block(breakable: false)
    combo = table_cell_html_to_typst(
        '<strong>CHF</strong><br><a href="https://lukb.ch">Details</a>'
    )
    assert "#block(" not in combo
    assert "#strong[CHF]" in combo
    assert '#link("https://lukb.ch")' in combo


def test_prepare_typst_payload_populates_rows_typst_for_table_and_media_text():
    doc = ArticleDocument(
        id="art_tbl_rt_1",
        template="investment_focus",
        metadata=ArticleMetadata(title="Tabellen-Test"),
        blocks=[
            {
                "id": "blk_t1",
                "type": "table",
                "title": "Testtabelle",
                "columns": [
                    {"field": "col_1", "title": "Titel", "align": "left", "width": 50.0},
                    {"field": "col_2", "title": "Link", "align": "right", "width": 50.0},
                ],
                "rows": [
                    {
                        "col_1": "<b>Fett</b>",
                        "col_2": '<a href="https://www.lukb.ch">LUKB</a>',
                    }
                ],
            },
            {
                "id": "blk_mt1",
                "type": "media_text",
                "html": "<p>Text</p>",
                "media_type": "table",
                "media": {
                    "type": "table",
                    "columns": [
                        {"field": "col_1", "title": "Name", "align": "left", "width": 100.0},
                    ],
                    "rows": [{"col_1": "<strong>Inline</strong>"}],
                },
            },
        ],
    )
    payload = _prepare_typst_payload(doc, Path("."))
    tbl_blk = payload["blocks"][0]
    assert "rows_typst" in tbl_blk
    assert "#strong[Fett]" in tbl_blk["rows_typst"][0]["col_1"]
    assert '#link("https://www.lukb.ch")' in tbl_blk["rows_typst"][0]["col_2"]

    mt_media = payload["blocks"][1]["media"]
    assert "rows_typst" in mt_media
    assert "#strong[Inline]" in mt_media["rows_typst"][0]["col_1"]


def test_render_pdf_with_richtext_table_cells_and_long_table():
    rows = [
        {
            "col_1": f"<b>Zeile {i}</b>",
            "col_2": '<a href="https://www.lukb.ch">Link</a>' if i % 2 == 0 else "Plain 100%",
        }
        for i in range(1, 11)
    ]
    doc = ArticleDocument(
        id="art_tbl_pdf_1",
        template="investment_focus",
        metadata=ArticleMetadata(title="PDF Tabellen-RichText"),
        blocks=[
            {
                "id": "blk_t_pdf",
                "type": "table",
                "title": "Lange formatierte Tabelle",
                "source": "Quelle: LUKB",
                "highlight_last_row": True,
                "columns": [
                    {"field": "col_1", "title": "Kategorie", "align": "left", "width": 50.0},
                    {"field": "col_2", "title": "Info", "align": "right", "width": 50.0},
                ],
                "rows": rows,
            }
        ],
    )
    pdf_bytes = render_pdf_bytes(doc)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_render_docx_with_richtext_table_cells():
    doc = ArticleDocument(
        id="art_tbl_docx_1",
        template="investment_focus",
        metadata=ArticleMetadata(title="DOCX Tabellen-RichText"),
        blocks=[
            {
                "id": "blk_t_docx",
                "type": "table",
                "title": "DOCX Tabelle",
                "columns": [
                    {"field": "col_1", "title": "Asset", "align": "left", "width": 50.0},
                    {"field": "col_2", "title": "Link", "align": "left", "width": 50.0},
                ],
                "rows": [
                    {
                        "col_1": "Normal und <b>Fett</b>",
                        "col_2": '<a href="https://www.lukb.ch">LUKB Portal</a>',
                    }
                ],
            }
        ],
    )
    docx_bytes = render_docx_bytes(doc)
    parsed = docx.Document(io.BytesIO(docx_bytes))
    assert len(parsed.tables) >= 1
    tbl = parsed.tables[0]
    cell_0_runs = tbl.rows[1].cells[0].paragraphs[0].runs
    assert any(r.text == "Fett" and r.bold for r in cell_0_runs)
    cell_1_text = tbl.rows[1].cells[1].paragraphs[0].text
    assert "LUKB Portal" in cell_1_text
    assert "↗" in cell_1_text
