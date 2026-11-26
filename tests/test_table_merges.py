"""
Tests für das Verbinden (Merge) und Teilen von Zellen im Tabellen-Body:
- Schema-Validierung und Normalisierung (`TableMerge`, `TableBlock.merges`)
- HTML-Rendering (`rowspan` / `colspan` und Auslassen überdeckter Zellen)
- Typst-PDF-Rendering (kurze und lange Tabellen mit vertikalen/horizontalen Merges)
- DOCX-Export mit verbundenen Zellen
"""

from __future__ import annotations

import io
import re

import docx

from schemas.article import ArticleDocument, ArticleMetadata, TableBlock
from services.renderer import render_docx_bytes, render_pdf_bytes, render_web_html


def test_table_block_merges_validation_and_normalization():
    tbl = TableBlock(
        columns=[
            {"field": "c1", "title": "A", "align": "left", "width": 33.4},
            {"field": "c2", "title": "B", "align": "right", "width": 33.3},
            {"field": "c3", "title": "C", "align": "right", "width": 33.3},
        ],
        rows=[
            {"c1": "R1", "c2": "1", "c3": "2"},
            {"c1": "R2", "c2": "3", "c3": "4"},
            {"c1": "R3", "c2": "5", "c3": "6"},
        ],
        merges=[
            {"row": 0, "col": 0, "rowspan": 2, "colspan": 1},
            {"row": 1, "col": 0, "rowspan": 1, "colspan": 2},  # überlappt mit (0,0)-(1,0) -> verworfen
            {"row": 2, "col": 1, "rowspan": 1, "colspan": 5},  # colspan wird auf 2 geklemmt
            {"row": 0, "col": 2, "rowspan": 1, "colspan": 1},  # trivial 1x1 -> verworfen
            {"row": 9, "col": 0, "rowspan": 2, "colspan": 2},  # ausserhalb -> verworfen
        ],
    )
    assert len(tbl.merges) == 2
    assert tbl.merges[0].model_dump() == {"row": 0, "col": 0, "rowspan": 2, "colspan": 1}
    assert tbl.merges[1].model_dump() == {"row": 2, "col": 1, "rowspan": 1, "colspan": 2}


def test_render_html_table_with_body_merges():
    doc = ArticleDocument(
        id="art_tbl_merge_html",
        template="investment_focus",
        metadata=ArticleMetadata(title="Merge HTML Test"),
        blocks=[
            {
                "id": "blk_t_merge",
                "type": "table",
                "title": "Tabelle mit Merges",
                "columns": [
                    {"field": "c1", "title": "Region", "align": "left", "width": 34.0},
                    {"field": "c2", "title": "2025", "align": "right", "width": 33.0},
                    {"field": "c3", "title": "2026", "align": "right", "width": 33.0},
                ],
                "rows": [
                    {"c1": "Europa", "c2": "1.2 %", "c3": "1.5 %"},
                    {"c1": "", "c2": "2.0 %", "c3": "2.3 %"},
                    {"c1": "Total", "c2": "3.2 %", "c3": ""},
                ],
                "merges": [
                    {"row": 0, "col": 0, "rowspan": 2, "colspan": 1},
                    {"row": 2, "col": 1, "rowspan": 1, "colspan": 2},
                ],
            }
        ],
    )
    html = render_web_html(doc)
    assert 'rowspan="2"' in html
    assert 'colspan="2"' in html
    tbody_match = re.search(r"<tbody>(.*?)</tbody>", html, flags=re.DOTALL)
    assert tbody_match is not None
    td_count = len(re.findall(r"<td\b", tbody_match.group(1)))
    # 3x3 = 9 Zellen, minus 1 (unter Europa) minus 1 (rechts neben 3.2 %) = 7 <td>-Elemente
    assert td_count == 7


def test_render_pdf_and_docx_table_with_merges():
    rows = [
        {"c1": f"Gruppe {i}", "c2": f"{i}.0 %", "c3": f"{i}.5 %"}
        for i in range(1, 10)
    ]
    rows[1]["c1"] = ""
    rows[8]["c3"] = ""
    doc = ArticleDocument(
        id="art_tbl_merge_pdf",
        template="investment_focus",
        metadata=ArticleMetadata(title="Merge PDF & DOCX Test"),
        blocks=[
            {
                "id": "blk_t_merge_pdf",
                "type": "table",
                "title": "Lange Tabelle mit Merges",
                "source": "Quelle: LUKB",
                "highlight_last_row": True,
                "columns": [
                    {"field": "c1", "title": "Kategorie", "align": "left", "width": 40.0},
                    {"field": "c2", "title": "Wert A", "align": "right", "width": 30.0},
                    {"field": "c3", "title": "Wert B", "align": "right", "width": 30.0},
                ],
                "rows": rows,
                "merges": [
                    {"row": 0, "col": 0, "rowspan": 2, "colspan": 1},
                    {"row": 8, "col": 1, "rowspan": 1, "colspan": 2},
                ],
            }
        ],
    )

    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 5000

    docx_bytes = render_docx_bytes(doc)
    assert len(docx_bytes) > 1000
    parsed = docx.Document(io.BytesIO(docx_bytes))
    assert len(parsed.tables) >= 1
    tbl = parsed.tables[0]
    # Header + 9 Body-Zeilen = 10 Zeilen; (1,0) und (2,0) teilen sich dieselbe verbundene Zelle
    assert tbl.cell(1, 0)._tc is tbl.cell(2, 0)._tc
    assert tbl.cell(1, 0).text.strip() == "Gruppe 1"
    # Letzte Zeile (Index 9): Spalte 1 und 2 verbunden
    assert tbl.cell(9, 1)._tc is tbl.cell(9, 2)._tc
    assert tbl.cell(9, 1).text.strip() == "9.0 %"
