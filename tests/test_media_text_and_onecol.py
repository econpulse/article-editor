"""
Tests für das einspaltige Advisory-Template (`advisory_onecol`), den kombinierten
`MediaTextBlock` (`media_text`) über alle Rendering-Kanäle (Typst-PDF, SVG, Web-HTML, DOCX)
sowie die neue Kopfzeilen-Option 'Asset Management Advisory'.
"""

from __future__ import annotations

from schemas.article import ArticleDocument, ArticleMetadata, MediaTextBlock, parse_block
from services.renderer import (
    extract_glossary_terms_from_article,
    list_available_templates,
    render_docx_bytes,
    render_pdf_bytes,
    render_preview_svg_pages,
    render_web_html,
)
from ui.editor import TOOLBAR_BLOCKS, document_metadata_card_ui


def test_advisory_onecol_registered_and_header_series_option_present():
    templates = list_available_templates()
    ids = [t["id"] for t in templates]
    assert "advisory_onecol" in ids

    ui_html = str(document_metadata_card_ui(templates))
    assert "Asset Management Advisory" in ui_html

    toolbar_types = [b.type_id for b in TOOLBAR_BLOCKS]
    assert "media_text" in toolbar_types


def test_media_text_block_schema_normalization():
    blk_table = parse_block({
        "type": "media_text",
        "media_type": "table",
        "media_position": "right",
        "style_preset": "card",
        "html": "<p><strong>Zentralbanken:</strong> Erwartung für 2026.</p>",
        "media": {
            "columns": [
                {"field": "col_1", "title": "Notenbank", "align": "left"},
                {"field": "col_2", "title": "Prognose", "align": "right"},
            ],
            "rows": [
                {"col_1": "SNB", "col_2": "0.25 %"},
                {"col_1": "EZB", "col_2": "2.00 %"},
            ],
        },
    })
    assert isinstance(blk_table, MediaTextBlock)
    assert blk_table.layout == "full"
    assert blk_table.full_position == "inline"
    assert blk_table.media["type"] == "table"
    assert blk_table.media["layout"] == "column"
    assert len(blk_table.media["columns"]) == 2
    assert blk_table.media["columns"][0]["width"] == 50.0


def test_media_text_glossary_extraction():
    blocks = [
        MediaTextBlock(
            html='<p>Fokus auf <span class="glossary-term" data-tooltip="Exchange Traded Fund">ETF</span>-Lösungen.</p>',
            aside_html='<p><span class="glossary-term" data-tooltip="International Securities Identification Number">ISIN</span>: IE00B4L5Y983</p>',
        ).model_dump()
    ]
    terms = extract_glossary_terms_from_article(blocks)
    term_names = {t["term"] for t in terms}
    assert "ETF" in term_names
    assert "ISIN" in term_names


def _build_sample_advisory_doc(template_id: str = "advisory_onecol") -> ArticleDocument:
    return ArticleDocument(
        template_id=template_id,
        metadata=ArticleMetadata(
            title="Top Chancen 2026",
            subtitle="Anlageideen",
            lead="Ausgewählte Anlageklassen und Sektoren bieten attraktive Chancen.",
            header_series="Asset Management Advisory",
            publication_date="2026-10-28",
        ),
        blocks=[
            {
                "type": "richtext",
                "html": "<p>Eine durchdachte Diversifikation bleibt entscheidend.</p>",
            },
            {
                "type": "media_text",
                "media_type": "figure",
                "media_position": "auto",
                "media_width_pct": 25,
                "style_preset": "zebra",
                "html": "<p><strong>EUR Staatsanleihen</strong> mit hoher Bonität bieten ein über dem CHF liegendes Renditeniveau.</p>",
                "aside_html": '<p>iShares Core € Govt Bond ETF<br><a href="https://www.lukb.ch">IE00BMFJGP26</a></p>',
                "media": {"type": "figure", "asset_id": ""},
            },
            {
                "type": "media_text",
                "media_type": "table",
                "media_position": "left",
                "media_width_pct": 40,
                "style_preset": "zebra",
                "html": "<p><strong>Zentralbanken:</strong> Wir erwarten eine ruhige Zinsentwicklung in der Schweiz.</p>",
                "aside_html": "",
                "media": {
                    "type": "table",
                    "title": "Leitzins-Prognose",
                    "subtitle": "In Prozent",
                    "source": "Quelle: LUKB",
                    "columns": [
                        {"field": "c1", "title": "Bank", "align": "left", "width": 50},
                        {"field": "c2", "title": "12M", "align": "right", "width": 50},
                    ],
                    "rows": [
                        {"c1": "SNB", "c2": "0.25 %"},
                        {"c1": "Fed", "c2": "3.50 %"},
                    ],
                },
            },
            {
                "type": "media_text",
                "media_type": "custom_chart",
                "media_position": "top",
                "style_preset": "card",
                "title": "Sektor-Allokation",
                "html": "<p>Gesundheitswesen und Finanzwesen bleiben übergewichtet.</p>",
                "media": {
                    "type": "custom_chart",
                    "title": "Renditeerwartung",
                    "chart_type": "category_bar",
                    "x_col": "Sektor",
                    "series": [{"field": "Erwartung", "label": "Erwartung", "chart_type": "bar", "enabled": True}],
                    "data_columns": ["Sektor", "Erwartung"],
                    "data_rows": [["Health Care", "8.2"], ["Financials", "7.4"]],
                },
            },
        ],
    )


def test_advisory_onecol_renders_all_outputs():
    doc = _build_sample_advisory_doc("advisory_onecol")

    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 5000

    svg_pages = render_preview_svg_pages(doc)
    assert len(svg_pages) >= 1
    assert "<svg" in svg_pages[0]

    html_out = render_web_html(doc)
    assert "Asset Management Advisory" in html_out
    assert "blk-media-text" in html_out
    assert "style-zebra" in html_out
    assert "zebra-even" in html_out
    assert "zebra-odd" in html_out
    assert "blk-media-text-aside" in html_out
    assert "IE00BMFJGP26" in html_out

    docx_bytes = render_docx_bytes(doc)
    assert docx_bytes.startswith(b"PK")
    assert len(docx_bytes) > 5000


def test_two_column_investment_focus_with_inline_full_media_text():
    doc = _build_sample_advisory_doc("investment_focus")
    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 5000
