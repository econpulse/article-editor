"""
Tests für automatische geschützte Leerzeichen (U+00A0) zwischen Zahlen und Einheiten
in Typst- und HTML-Ausgaben (ohne manuelle Eingabe im Editor).
"""

from __future__ import annotations

from schemas.article import ArticleDocument, ArticleMetadata
from services.html_to_typst import (
    bind_number_units,
    bind_number_units_html,
    escape_typst_text,
    html_to_typst,
    table_cell_html_to_typst,
)
from services.renderer import render_pdf_bytes, render_preview_svg_pages, render_web_html


def test_bind_number_units_positive_and_negative_cases():
    # Prozent, Promille, Temperatur, Symbole
    assert bind_number_units("Rendite 10 %") == "Rendite 10\u00a0%"
    assert bind_number_units("0.50 % bis +2,5 %") == "0.50\u00a0% bis +2,5\u00a0%"
    assert bind_number_units("-1,25 %") == "-1,25\u00a0%"
    assert bind_number_units("3,5 ‰") == "3,5\u00a0‰"
    assert bind_number_units("20 °C und 90 °") == "20\u00a0°C und 90\u00a0°"
    assert bind_number_units("100 € oder 50 $") == "100\u00a0€ oder 50\u00a0$"

    # Währungen (vor und nach Zahl) & Grössenordnungen
    assert bind_number_units("CHF 1'250.50") == "CHF\u00a01'250.50"
    assert bind_number_units("USD -2.5") == "USD\u00a0-2.5"
    assert bind_number_units("Fr. 50") == "Fr.\u00a050"
    assert bind_number_units("100 CHF") == "100\u00a0CHF"
    assert bind_number_units("10 Mio. CHF") == "10\u00a0Mio.\u00a0CHF"
    assert bind_number_units("CHF 10 Mio.") == "CHF\u00a010\u00a0Mio."
    assert bind_number_units("1.5 Mrd. EUR") == "1.5\u00a0Mrd.\u00a0EUR"

    # Finanz- und SI-Einheiten
    assert bind_number_units("25 bps bzw. 50 Bp") == "25\u00a0bps bzw. 50\u00a0Bp"
    assert bind_number_units("10 km, 5 m, 20 kg, 24 h, 5 min, 10 kWh, 100 m/s") == (
        "10\u00a0km, 5\u00a0m, 20\u00a0kg, 24\u00a0h, 5\u00a0min, 10\u00a0kWh, 100\u00a0m/s"
    )

    # Ordinalzahlen + Zeit-/Kalenderangaben
    assert bind_number_units("im 3. Quartal 2026") == "im 3.\u00a0Quartal 2026"
    assert bind_number_units("des 3. Quartals") == "des 3.\u00a0Quartals"
    assert bind_number_units("1. Halbjahr und 2. Semester") == "1.\u00a0Halbjahr und 2.\u00a0Semester"
    assert bind_number_units("8. November 2026") == "8.\u00a0November 2026"
    assert bind_number_units("21. Jahrhundert") == "21.\u00a0Jahrhundert"

    # Negative Fälle: normale Wörter und Zeilenumbrüche bleiben unberührt
    assert bind_number_units("10 Jahre später") == "10 Jahre später"
    assert bind_number_units("3. Punkt auf der Liste") == "3. Punkt auf der Liste"
    assert bind_number_units("Artikel 10 mit Bild") == "Artikel 10 mit Bild"
    assert bind_number_units("10 Monate Laufzeit") == "10 Monate Laufzeit"
    assert bind_number_units("10 % und 20 %") == "10\u00a0% und 20\u00a0%"
    assert bind_number_units("100\n%") == "100\n%"

    # Idempotenz
    once = bind_number_units("10 % von CHF 100 Mio.")
    assert bind_number_units(once) == once


def test_bind_number_units_html_preserves_tags_and_attributes():
    raw = '<p style="width: 50 %">Wachstum von <strong>10 %</strong> auf <span data-tooltip="ca. 20 %">CHF 100</span>.</p>'
    out = bind_number_units_html(raw)
    assert 'style="width: 50 %"' in out
    assert 'data-tooltip="ca. 20 %"' in out
    assert "<strong>10\u00a0%</strong>" in out
    assert ">CHF\u00a0100<" in out


def test_typst_converters_insert_nbsp():
    assert "10\u00a0%" in escape_typst_text("Zins 10 %")
    typ = html_to_typst("<p>Rendite von 10 % bei CHF 100.</p>")
    assert "10\u00a0%" in typ
    assert "CHF\u00a0100." in typ
    cell = table_cell_html_to_typst("A & B\n100 % #1")
    assert "100\u00a0%" in cell
    assert "\\\n" in cell


def test_end_to_end_html_and_typst_rendering_with_number_units():
    doc = ArticleDocument(
        id="art_nbsp_test",
        template_id="investment_focus",
        metadata=ArticleMetadata(
            title="Ausblick: 10 % Wachstum erwartet",
            lead="Investitionen von CHF 100 Mio. im Fokus.",
        ),
        blocks=[
            {"type": "heading", "level": 2, "text": "Inflation bei 2.5 %"},
            {"type": "richtext", "html": "<p>Die Rendite stieg auf 10 % (vorher 5 Mio. CHF).</p>"},
            {"type": "callout", "title": "Hinweis: 25 bps", "html": "<p>Zinsschritt um 25 bps.</p>"},
            {
                "type": "table",
                "title": "Kennzahlen in %",
                "columns": [
                    {"field": "name", "title": "Position", "align": "left", "width": 50.0},
                    {"field": "val", "title": "Wert (%)", "align": "right", "width": 50.0},
                ],
                "rows": [{"name": "Portfolio A", "val": "12.5 %"}],
            },
            {
                "type": "kpi_cards",
                "title": "Zahlen im Überblick",
                "cards": [{"label": "Ziel", "value": "10 %", "subtext": "CHF 50 Mio.", "tone": "blue"}],
            },
        ],
    )

    html_out = render_web_html(doc)
    assert "10\u00a0% Wachstum" in html_out
    assert "CHF\u00a0100\u00a0Mio." in html_out
    assert "Inflation bei 2.5\u00a0%" in html_out
    assert "10\u00a0% (vorher 5\u00a0Mio.\u00a0CHF)" in html_out
    assert "25\u00a0bps" in html_out
    assert "12.5\u00a0%" in html_out
    assert "CHF\u00a050\u00a0Mio." in html_out

    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 5000

    svg_pages = render_preview_svg_pages(doc)
    assert len(svg_pages) >= 1
    assert "<svg" in svg_pages[0]
