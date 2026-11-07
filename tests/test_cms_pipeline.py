"""
End-to-End Tests für das LUKB Investment Office CMS:
- Datenbank-Initialisierung, Artikel-CRUD, Autosave & Revisions-Historie
- DB-basierte Grafik-Speicherung (VARBINARY(MAX) Schutz bei Posit Connect Redeployments)
- Typst 0.15 PDF- & SVG-Rendering für beide Templates (investment_focus & market_flash)
- Jinja2 Web-HTML-Rendering
- Shiny App-Initialisierung
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import build_database_url
from database.repository import (
    create_new_article,
    delete_article,
    duplicate_article,
    get_article,
    get_asset,
    init_db_and_seed,
    list_articles,
    save_article,
    save_asset,
)
from services.html_to_typst import html_to_typst
from services.renderer import render_pdf_bytes, render_preview_svg_pages, render_web_html
from app import app


def test_mssql_url_builder(monkeypatch_env=None):
    import os

    os.environ["MSSQL_SERVER"] = "sql-lukb-prod.internal"
    os.environ["MSSQL_DATABASE"] = "InvestmentOfficeCMS"
    os.environ["MSSQL_USER"] = "svc_posit_cms"
    os.environ["MSSQL_PASSWORD"] = "Secret#123"
    url, label = build_database_url()
    assert url.startswith("mssql+pyodbc://svc_posit_cms:")
    assert "sql-lukb-prod.internal:1433/InvestmentOfficeCMS" in url
    assert "MS SQL Server" in label
    # Cleanup env
    del os.environ["MSSQL_SERVER"]
    del os.environ["MSSQL_DATABASE"]
    del os.environ["MSSQL_USER"]
    del os.environ["MSSQL_PASSWORD"]


def test_full_cms_workflow():
    init_db_and_seed()
    articles = list_articles()
    assert len(articles) >= 2, "Seed muss mindestens 2 Beispielartikel anlegen"

    # Prüfe Suche & Status-Filter (inkl. "active_work" für Entwurf & Review)
    filtered = list_articles(search_query="Zinswende")
    assert len(filtered) >= 1
    assert "Zinswende" in filtered[0]["title"]
    assert "updated_iso" in filtered[0]

    active_work = list_articles(status_filter="active_work")
    assert all(a["status"] in ("draft", "review") for a in active_work)

    # Neuen Artikel anlegen, Blöcke ergänzen (Heading, RichText, Figure, Table, Callout) & speichern
    new_doc = create_new_article(template_id="investment_focus", user="Test Analyst")
    new_doc.metadata.title = "Ausblick Schweizer Immobilienmarkt 2027"
    new_doc.metadata.subtitle = "Immobilien & Hypotheken"

    # Eigenes SVG-Asset hochladen und in DB speichern
    custom_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="80"><rect width="200" height="80" fill="#002855"/></svg>'
    asset_id = save_asset("immo_chart.svg", "image/svg+xml", custom_svg, article_id=new_doc.id)
    loaded_asset = get_asset(asset_id)
    assert loaded_asset is not None
    assert loaded_asset["data"] == custom_svg

    new_doc.blocks.append(
        {
            "id": "blk_test_fig",
            "type": "figure",
            "title": "Immobilienpreisindex Zentralschweiz",
            "subtitle": "Indexiert (2020 = 100)",
            "source": "Quelle: LUKB Immobilienanalyse",
            "asset_id": asset_id,
            "layout": "full",
        }
    )
    new_doc.blocks.append(
        {
            "id": "blk_test_tbl",
            "type": "table",
            "title": "Regionale Renditekennzahlen",
            "subtitle": "Nettoanfangsrenditen nach Segment",
            "source": "Quelle: LUKB Investment Office",
            "layout": "column",
            "highlight_last_row": True,
            "columns": [
                {"field": "seg", "title": "Segment", "align": "left"},
                {"field": "yield", "title": "Rendite", "align": "right"},
            ],
            "rows": [
                {"seg": "Wohnen Luzern", "yield": "3.1 %"},
                {"seg": "Geschäftsliegenschaften", "yield": "4.2 %"},
                {"seg": "Durchschnitt Portfolio", "yield": "3.5 %"},
            ],
        }
    )

    save_res = save_article(new_doc, user="Test Analyst", create_revision=True, revision_note="Unit-Test")
    assert save_res["id"] == new_doc.id

    reloaded = get_article(new_doc.id)
    assert reloaded is not None
    assert reloaded.metadata.title == "Ausblick Schweizer Immobilienmarkt 2027"
    assert len(reloaded.blocks) == 4

    # Typst PDF & SVG-Preview prüfen
    pdf_bytes = render_pdf_bytes(reloaded)
    assert pdf_bytes.startswith(b"%PDF-"), "Typst muss valides PDF erzeugen"
    assert len(pdf_bytes) > 5000

    svg_pages = render_preview_svg_pages(reloaded)
    assert len(svg_pages) >= 1
    assert "<svg" in svg_pages[0]

    # Web HTML prüfen
    html_out = render_web_html(reloaded)
    assert "<!DOCTYPE html>" in html_out
    assert "Yoga Sans for LUKB Light" in html_out
    assert "Yoga Sans for LUKB Medium" in html_out
    assert "Investment Office News" in html_out
    assert "data:image/svg+xml;base64," in html_out
    assert "Immobilienpreisindex Zentralschweiz" in html_out
    assert "Regionale Renditekennzahlen" in html_out

    # Duplizieren & Löschen prüfen
    dup = duplicate_article(new_doc.id, user="Test Analyst")
    assert dup is not None
    assert "(Kopie)" in dup.metadata.title

    assert delete_article(dup.id) is True
    assert delete_article(new_doc.id) is True


def test_html_to_typst_escaping():
    sample = "<p>Rendite von <strong>+4.5 %</strong> bei $100 &amp; #1 Rating <em>(Prognose)</em></p>"
    typ = html_to_typst(sample)
    assert "#strong[+4.5 %]" in typ
    assert "\\$100" in typ
    assert "\\#1" in typ
    assert "#emph[(Prognose)]" in typ


def test_shiny_tuple_deserialization_in_pydantic():
    """
    Shiny for Python konvertiert eingehende JSON-Arrays aus `Shiny.setInputValue`
    via `object_hook=_utils.lists_to_tuples` in Python-Tupel `(...)`.
    Stellt sicher, dass `ArticleDocument.model_validate` niemals Blöcke, Autoren oder
    Tabellenzeilen verwirft, wenn Listen als Tupel übergeben werden.
    """
    from schemas.article import ArticleDocument

    shiny_like_payload = {
        "id": "art-tuple-test",
        "template_id": "investment_focus",
        "status": "draft",
        "metadata": {
            "title": "Tuple Test",
            "authors": ({"name": "Max Muster", "role": "Analyst"},),
        },
        "blocks": (
            {"id": "b1", "type": "heading", "level": 1, "text": "Titel"},
            {"id": "b2", "type": "richtext", "html": "<p><strong>Fett</strong> und Text</p>"},
            {
                "id": "b3",
                "type": "table",
                "title": "Tabelle",
                "columns": ({"field": "c1", "title": "Spalte", "align": "left"},),
                "rows": ({"c1": "Wert"},),
            },
        ),
    }
    doc = ArticleDocument.model_validate(shiny_like_payload)
    assert len(doc.blocks) == 3
    assert len(doc.metadata.authors) == 1
    assert doc.blocks[1]["html"] == "<p><strong>Fett</strong> und Text</p>"
    assert len(doc.blocks[2]["columns"]) == 1
    assert len(doc.blocks[2]["rows"]) == 1


def test_textbox_start_end_markers_grouping():
    """
    Prüft, dass `box_start` und `box_end` beliebige Blöcke (Überschrift, Text, Tabelle, Grafik)
    in eine gemeinsame farbliche Textbox einschliessen und in Typst sowie HTML fehlerfrei rendern.
    """
    from schemas.article import ArticleDocument

    doc = ArticleDocument(
        id="art-box-marker-test",
        template_id="market_flash",
        blocks=[
            {"id": "m1", "type": "box_start"},
            {"id": "h1", "type": "heading", "level": 2, "text": "Überschrift in der Box"},
            {"id": "p1", "type": "richtext", "html": "<p>Erster Absatz in der Box.</p>"},
            {"id": "t1", "type": "table", "title": "Mini-Tabelle in der Box"},
            {"id": "m2", "type": "box_end"},
            {"id": "p2", "type": "richtext", "html": "<p>Absatz ausserhalb der Box.</p>"},
        ],
    )
    svgs = render_preview_svg_pages(doc)
    assert len(svgs) >= 1
    assert "<svg" in svgs[0]

    html = render_web_html(doc)
    assert "blk-richtext-textbox" in html
    assert "Überschrift in der Box" in html
    assert "Mini-Tabelle in der Box" in html


def test_concurrent_multi_author_block_merge():
    """
    Prüft das zeitgleiche Bearbeiten desselben Artikels durch zwei Autoren (3-Wege-Merge):
    - Autor A ändert Block 1 (Text) und den Untertitel.
    - Autor B ändert gleichzeitig Block 2 (Tabelle), fügt Block 3 hinzu und ändert den Lead.
    Beide Speicherungen müssen verlustfrei zusammengeführt werden.
    """
    from schemas.article import ArticleDocument

    base_doc = create_new_article(template_id="investment_focus", user="Autor A")
    base_snapshot = ArticleDocument.model_validate(base_doc.model_dump())

    # Autor A editiert Block 0 (Überschrift) und den Untertitel und speichert zuerst
    doc_author_a = ArticleDocument.model_validate(base_snapshot.model_dump())
    doc_author_a.metadata.subtitle = "Neuer Untertitel von Autor A"
    doc_author_a.blocks[0]["text"] = "Geänderte Überschrift von Autor A"
    res_a = save_article(doc_author_a, user="Autor A", base_doc=base_snapshot)
    assert res_a["merged"] is False

    # Autor B hatte noch den alten `base_snapshot`, ändert gleichzeitig Block 1 (RichText),
    # den Lead-Text und hängt einen neuen Block an
    doc_author_b = ArticleDocument.model_validate(base_snapshot.model_dump())
    doc_author_b.metadata.lead = "Neuer Lead-Text von Autor B"
    doc_author_b.blocks[1]["html"] = "<p>Neuer Analysetext von <strong>Autor B</strong>.</p>"
    doc_author_b.blocks.append(
        {"id": "blk_added_by_b", "type": "heading", "level": 2, "text": "Zusatzkapitel von Autor B"}
    )
    res_b = save_article(doc_author_b, user="Autor B", base_doc=base_snapshot)
    assert res_b["merged"] is True

    # Prüfe, dass SOWOHL die Änderungen von Autor A ALS AUCH von Autor B in der DB erhalten sind
    final_doc = get_article(base_doc.id)
    assert final_doc is not None
    assert final_doc.metadata.subtitle == "Neuer Untertitel von Autor A"
    assert final_doc.metadata.lead == "Neuer Lead-Text von Autor B"
    assert final_doc.blocks[0]["text"] == "Geänderte Überschrift von Autor A"
    assert "Autor B" in final_doc.blocks[1]["html"]
    assert any(b["id"] == "blk_added_by_b" for b in final_doc.blocks)

    delete_article(base_doc.id)


def test_db_chart_timeseries_block():
    """
    Prüft den Inhaltsblock `db_chart` (Grafik aus Datenbank `ts_db`):
    - Abfrage verfügbarer Ticker aus `ts_db`
    - Kombination aller 6 Chart-Typen (line, step, dot, area, bar, stacked_bar) mit max. 5 Tickern
    - Originalwerte (`rebasing="none"`) sowie Indexierung auf 100 (`rebasing="index_100"`)
    - Nahtloses Typst-PDF-, SVG-Preview- und Web-HTML5-Rendering
    """
    from database.repository import list_available_tickers, query_timeseries_data, search_tickers
    from schemas.article import ArticleDocument
    from services.chart_generator import generate_db_chart_svg

    init_db_and_seed()
    tickers = list_available_tickers()
    assert len(tickers) >= 5
    ticker_codes = {t["ticker"] for t in tickers}
    assert {"SMI", "SP500", "SNB_RATE", "ECB_RATE", "EPS_CH", "EPS_US"}.issubset(ticker_codes)

    # Schnelle Ticker-Suche prüfen (Prefix -> Substring Ticker -> Substring Name, mit Limit)
    prefix_hits = search_tickers("EPS", limit=5)
    assert len(prefix_hits) >= 3
    assert all(h["ticker"].startswith("EPS") for h in prefix_hits[:3])
    name_hits = search_tickers("Leitzins", limit=5)
    assert any(h["ticker"] == "SNB_RATE" for h in name_hits)

    ts_data = query_timeseries_data(["SMI", "snb_rate"], start_date="2023-01-01")
    assert "SMI" in ts_data
    assert "SNB_RATE" in ts_data
    assert len(ts_data["SMI"]["points"]) >= 4

    # 1. Kombination aus Stacked Bar, Bar, Step, Line und Dot
    combo_block = {
        "id": "blk_dbchart_combo",
        "type": "db_chart",
        "title": "Kombinierter Datenbank-Chart",
        "subtitle": "Gewinnbeiträge und Leitzinsen seit 2022",
        "source": "Quelle: ts_db, LUKB Investment Office",
        "layout": "column",
        "start_date": "2022-01-01",
        "rebasing": "none",
        # Übergabe als Tupel wie aus Shiny.setInputValue (6 Elemente -> wird auf max. 5 begrenzt)
        "series": (
            {"ticker": "EPS_CH", "chart_type": "stacked_bar", "label": "EPS Schweiz"},
            {"ticker": "EPS_US", "chart_type": "stacked_bar", "label": "EPS USA"},
            {"ticker": "EPS_EU", "chart_type": "bar", "label": "EPS Europa"},
            {"ticker": "FED_RATE", "chart_type": "step", "label": "Fed Funds Rate"},
            {"ticker": "ECB_RATE", "chart_type": "dot", "label": ""},
            {"ticker": "SNB_RATE", "chart_type": "line", "label": "Wird auf 5 gekürzt"},
        ),
    }

    # 2. Indexierter Vergleich (Startdatum = 100) mit Mehrfach-Typen pro Zeitreihe (z.B. step+area und line+dot)
    indexed_block = {
        "id": "blk_dbchart_idx",
        "type": "db_chart",
        "title": "Aktienmärkte im Vergleich (Indexiert = 100)",
        "subtitle": "Relative Wertentwicklung seit 2022",
        "source": "Quelle: Bloomberg, LUKB Investment Office",
        "layout": "full",
        "start_date": "2022-01-01",
        "rebasing": "index_100",
        "series": [
            {"ticker": "SMI", "chart_types": ("step", "area"), "label": "SMI (CHF)"},
            {"ticker": "SP500", "chart_types": ["line", "dot"], "label": "S&P 500"},
            {"ticker": "STOXX600", "chart_type": "dot", "label": "STOXX Europe 600"},
        ],
    }

    svg_combo = generate_db_chart_svg(combo_block)
    assert svg_combo.startswith("<svg")
    assert "EPS Schweiz" in svg_combo
    assert "EZB Einlagesatz (EUR)" in svg_combo  # Automatischer Name aus ts_db
    assert 'font-size="22.5"' in svg_combo  # Vergrösserte Achsenschrift im 1-spaltigen Format

    # Steuerbare Höhe der eigentlichen Chartfläche (Y-Achse):
    # Standard: 36mm. Erhöhung um 10mm (z.B. auf 46mm) muss die Gesamthöhe des SVGs
    # ausschliesslich über die Höhe der Y-Achse vergrössern (Schriftgrössen unverändert).
    import re

    h_match_default = re.search(r'height="(\d+)"', svg_combo)
    assert h_match_default is not None
    svg_h_36 = int(h_match_default.group(1))

    taller_combo_block = dict(combo_block, chart_height_mm=46)
    svg_taller = generate_db_chart_svg(taller_combo_block)
    h_match_taller = re.search(r'height="(\d+)"', svg_taller)
    assert h_match_taller is not None
    svg_h_46 = int(h_match_taller.group(1))

    # Differenz in SVG-Pixel entspricht exakt (46 - 36) mm * (680 / 87.1778) px/mm = 78 px
    expected_diff = round(10.0 * (680.0 / 87.1778))
    actual_diff = svg_h_46 - svg_h_36
    assert abs(actual_diff - expected_diff) <= 1, f"Erwartete Höhendifferenz ~{expected_diff}px, erhalten: {actual_diff}px"
    # Schriftgrössen und Legenden-Schriftgrössen müssen absolut identisch geblieben sein
    assert 'font-size="22.5"' in svg_taller
    assert 'font-size="20.5"' in svg_taller

    svg_idx = generate_db_chart_svg(indexed_block)
    assert svg_idx.startswith("<svg")
    assert 'font-size="14.5"' in svg_idx  # Achsenschrift im 2-spaltigen Format ('full')
    assert "stroke-dasharray=\"4,3\"" in svg_idx  # 100er-Referenzlinie
    assert 'fill-opacity="0.18"' in svg_idx  # Step + Area Fläche

    doc = ArticleDocument(
        id="art-dbchart-test",
        template_id="investment_focus",
        blocks=[combo_block, indexed_block],
    )
    assert len(doc.blocks[0]["series"]) == 5, "Maximal 5 Ticker pro DB-Chart erlaubt"
    assert doc.blocks[1]["series"][0]["chart_types"] == ["step", "area"]
    assert doc.blocks[1]["series"][1]["chart_types"] == ["line", "dot"]

    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes.startswith(b"%PDF-")

    svg_pages = render_preview_svg_pages(doc)
    assert len(svg_pages) >= 1

    html_out = render_web_html(doc)
    assert "Kombinierter Datenbank-Chart" in html_out
    assert "Aktienmärkte im Vergleich (Indexiert = 100)" in html_out
    assert "data:image/svg+xml;base64," in html_out


def test_layout_elements_spacer_and_colbreak():
    """
    Prüft die Layout-Elemente 'Vertikaler Abstand' (spacer) und 'Manueller Spaltenumbruch' (colbreak):
    - Pydantic-Schema & 2mm-Schritt-Validierung
    - Nahtlose Typst-PDF-Kompilierung (beide Templates: investment_focus und market_flash)
    - Typst-SVG-Seitenrendering
    - Web-HTML5-Rendering
    """
    from schemas.article import ArticleDocument, ColbreakBlock, SpacerBlock
    from services.renderer import render_pdf_bytes, render_preview_svg_pages, render_web_html

    sp1 = SpacerBlock(height_mm=12)
    assert sp1.height_mm == 12
    sp_odd = SpacerBlock(height_mm=15)
    assert sp_odd.height_mm == 16, "Ungerade Werte müssen auf 2mm-Schritte gerundet werden"
    cb = ColbreakBlock()
    assert cb.type == "colbreak"

    doc = ArticleDocument(
        id="art-layout-test",
        template_id="investment_focus",
        blocks=[
            {"id": "h1", "type": "heading", "level": 1, "text": "Erste Spalte"},
            {"id": "rt1", "type": "richtext", "html": "<p>Inhalt vor dem Abstandhalter.</p>"},
            {"id": "sp1", "type": "spacer", "height_mm": 14},
            {"id": "rt2", "type": "richtext", "html": "<p>Inhalt nach dem Abstandhalter.</p>"},
            {"id": "cb1", "type": "colbreak"},
            {"id": "h2", "type": "heading", "level": 1, "text": "Zweite Spalte oben"},
            {"id": "rt3", "type": "richtext", "html": "<p>Dieser Inhalt muss zwingend in Spalte 2 beginnen.</p>"},
        ],
    )

    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes.startswith(b"%PDF-"), "Typst muss mit spacer und colbreak valides PDF kompilieren"
    assert len(pdf_bytes) > 5000

    svg_pages = render_preview_svg_pages(doc)
    assert len(svg_pages) >= 1
    assert "<svg" in svg_pages[0]

    html_out = render_web_html(doc)
    assert "blk-spacer" in html_out
    assert "14mm" in html_out
    assert "blk-colbreak" in html_out

    # Auch im market_flash Template testen
    doc_flash = ArticleDocument(
        id="art-flash-test",
        template_id="market_flash",
        blocks=doc.blocks,
    )
    flash_pdf = render_pdf_bytes(doc_flash)
    assert flash_pdf.startswith(b"%PDF-")


if __name__ == "__main__":
    test_mssql_url_builder()
    test_html_to_typst_escaping()
    test_shiny_tuple_deserialization_in_pydantic()
    test_textbox_start_end_markers_grouping()
    test_concurrent_multi_author_block_merge()
    test_db_chart_timeseries_block()
    test_layout_elements_spacer_and_colbreak()
    test_full_cms_workflow()
    assert app is not None
    print("ALL TESTS PASSED SUCCESSFULLY!")
