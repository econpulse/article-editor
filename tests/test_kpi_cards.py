"""
Tests für den KPI-/Dashboard-Karten-Block (`kpi_cards`) sowie das Finanzmarkt-Icon-Set
über Schema-Validierung, UI-Registrierung und alle Rendering-Kanäle (Typst-PDF, SVG, Web-HTML, DOCX).
"""

from __future__ import annotations

import pytest

from schemas.article import ArticleDocument, ArticleMetadata, KpiCardItem, KpiCardsBlock, parse_block
from services.kpi_icons import (
    KPI_ICONS,
    KPI_TONES,
    VALID_KPI_ICON_IDS,
    get_kpi_icons_catalog,
    get_kpi_tone_palette,
    normalize_kpi_icon_id,
    render_kpi_icon_svg,
)
from services.renderer import (
    render_docx_bytes,
    render_pdf_bytes,
    render_preview_svg_pages,
    render_web_html,
)
from ui import build_app_ui
from ui.editor import TOOLBAR_BLOCKS


def test_kpi_icons_catalog_and_svg_generation():
    assert len(KPI_ICONS) >= 20
    assert len(VALID_KPI_ICON_IDS) == len(KPI_ICONS)
    assert set(KPI_TONES.keys()) == {"navy", "blue", "cyan", "gold", "positive", "negative", "berry", "neutral"}
    tone_keys = list(KPI_TONES.keys())
    assert tone_keys.index("negative") < tone_keys.index("berry") < tone_keys.index("neutral")
    assert get_kpi_tone_palette("berry")["accent"] == "#480C34"

    for icon in KPI_ICONS:
        svg = render_kpi_icon_svg(icon["id"], stroke_color="#005A9C", size_px=24)
        assert svg.startswith("<svg ")
        assert 'stroke="#005A9C"' in svg
        assert "</svg>" in svg

        badge_svg = render_kpi_icon_svg(
            icon["id"],
            stroke_color="#002855",
            size_px=36,
            badge_bg="#DCE6F2",
        )
        assert "<rect " in badge_svg
        assert 'fill="#DCE6F2"' in badge_svg

    assert render_kpi_icon_svg("") == ""
    assert normalize_kpi_icon_id("none") == ""
    assert normalize_kpi_icon_id("unknown_icon") == "trend_up"
    assert get_kpi_tone_palette("gold")["accent"] == "#C59B27"
    assert get_kpi_tone_palette("invalid")["id"] == "navy"

    cat = get_kpi_icons_catalog()
    assert len(cat["icons"]) == len(KPI_ICONS)
    assert len(cat["tones"]) == len(KPI_TONES)


def test_kpi_cards_schema_validation_and_normalization():
    blk = parse_block({
        "type": "kpi_cards",
        "title": "Markt-Dashboard",
        "columns_count": "auto",
        "style_preset": "card_accent_top",
        "cards": [
            {"icon": "central_bank", "label": "SNB", "value": "0.50 %", "subtext": "−25 Bp", "tone": "navy"},
            {"icon": "", "label": "Ohne Icon", "value": "Neutral", "tone": "unknown_tone"},
        ],
    })
    assert isinstance(blk, KpiCardsBlock)
    assert blk.layout == "full"
    assert blk.full_position == "inline"
    assert blk.columns_count == 0
    assert blk.style_preset == "card_accent_top"
    assert len(blk.cards) == 2
    assert isinstance(blk.cards[0], KpiCardItem)
    assert blk.cards[1].icon == ""
    assert blk.cards[1].tone == "navy"

    # Max 8 Karten und gültige Spaltengrenzen
    many = KpiCardsBlock(
        columns_count=9,
        style_preset="invalid_style",
        cards=[{"label": f"K{i}", "value": f"{i}%"} for i in range(12)],
    )
    assert many.columns_count == 4
    assert many.style_preset == "tint"
    assert len(many.cards) == 8


def test_kpi_cards_registered_in_toolbar_and_ui():
    toolbar_types = [b.type_id for b in TOOLBAR_BLOCKS]
    assert "kpi_cards" in toolbar_types

    rendered = build_app_ui().render()
    heads_html = "\n".join(str(getattr(dep, "head", "") or "") for dep in rendered["dependencies"])
    assert "lukb-kpi-icons-data" in heads_html
    assert "js/modules/kpi-cards.js" in heads_html


def _build_kpi_doc(template_id: str = "advisory_onecol", style_preset: str = "tint") -> ArticleDocument:
    return ArticleDocument(
        template_id=template_id,
        metadata=ArticleMetadata(
            title="Makro-Update & Markteinschätzung",
            subtitle="LUKB Dashboard-Test",
            lead="Kompakte Übersicht zentraler Zins- und Marktindikatoren.",
            publication_date="2026-11-21",
        ),
        blocks=[
            {
                "type": "richtext",
                "html": "<p>Einleitender Absatz zur geldpolitischen Lage in der Schweiz und Europa.</p>",
            },
            {
                "type": "kpi_cards",
                "title": "Zentrale Marktindikatoren",
                "subtitle": "Aktuelle Stände und LUKB-Positionierung",
                "source": "Quelle: Bloomberg, LUKB Investment Office",
                "layout": "full",
                "full_position": "inline",
                "columns_count": 0,
                "style_preset": style_preset,
                "cards": [
                    {
                        "icon": "central_bank",
                        "label": "SNB Leitzins",
                        "value": "0.50 %",
                        "subtext": "−25 Bp vs. Vorquartal",
                        "tone": "navy",
                    },
                    {
                        "icon": "trend_up",
                        "label": "Aktien Schweiz",
                        "value": "Übergewichten",
                        "subtext": "Dividendenrendite ~3.2 %",
                        "tone": "positive",
                    },
                    {
                        "icon": "inflation",
                        "label": "Inflation CH #1",
                        "value": "0.9 %",
                        "subtext": "Zielband 0–2 % ($ stabil)",
                        "tone": "cyan",
                    },
                    {
                        "icon": "alert_triangle",
                        "label": "US-Staatsanleihen",
                        "value": "Untergewichten",
                        "subtext": "Fiskalrisiken im Fokus",
                        "tone": "gold",
                    },
                ],
            },
            {
                "type": "kpi_cards",
                "title": "Rand-Kennzahl",
                "layout": "column",
                "style_preset": "card_accent_left",
                "cards": [
                    {
                        "icon": "esg_leaf",
                        "label": "ESG-Rating",
                        "value": "AA",
                        "subtext": "Über Benchmark",
                        "tone": "blue",
                    }
                ],
            },
            {
                "type": "richtext",
                "html": "<p>Abschliessender Absatz mit Einordnung der Portfolioallokation.</p>",
            },
        ],
    )


@pytest.mark.parametrize(
    "template_id",
    ["advisory_onecol", "investment_focus", "investment_tufte", "market_flash", "factsheet"],
)
def test_kpi_cards_render_all_templates_and_formats(template_id: str):
    doc = _build_kpi_doc(template_id=template_id)

    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 5000

    svg_pages = render_preview_svg_pages(doc)
    assert len(svg_pages) >= 1
    assert "<svg" in svg_pages[0]

    html_out = render_web_html(doc)
    assert "blk-kpi-cards" in html_out
    assert "kpi-card-icon-badge" in html_out
    assert "SNB Leitzins" in html_out
    assert "0.50\u00a0%" in html_out
    assert "Inflation CH #1" in html_out

    docx_bytes = render_docx_bytes(doc)
    assert docx_bytes.startswith(b"PK")
    assert len(docx_bytes) > 5000


@pytest.mark.parametrize("style_preset", ["tint", "card_accent_top", "card_accent_left", "clean"])
def test_kpi_cards_all_style_presets_render_cleanly(style_preset: str):
    doc = _build_kpi_doc(template_id="advisory_onecol", style_preset=style_preset)
    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes.startswith(b"%PDF")
    html_out = render_web_html(doc)
    assert f"kpi-style-{style_preset}" in html_out
