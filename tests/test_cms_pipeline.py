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
from services.renderer import (
    format_publication_date,
    render_docx_bytes,
    render_pdf_bytes,
    render_preview_svg_pages,
    render_web_html,
)
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
    from services.renderer import render_docx_bytes, render_pdf_bytes, render_preview_svg_pages, render_web_html

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

    # Word .docx Export testen
    docx_bytes = render_docx_bytes(doc)
    assert docx_bytes.startswith(b"PK\x03\x04"), "DOCX muss valides ZIP/OpenXML-Archiv sein"
    assert len(docx_bytes) > 8000


def test_smart_cms_features_3a_and_3b():
    """
    Testet alle Anforderungen aus 3A und 3B:
    3A:
      - Zitat / Pull-Quote (quote)
      - Horizontale Trennlinie (divider)
      - Fussnoten- / Endnoten-Apparat (footnotes)
    3B:
      - Themen-Tags / Schlagwörter (tags)
      - Glossar / Infotext-Tooltip (<span data-tooltip="...">) & Inline-Fussnote (<footnote>)
      - PDF-, HTML- und DOCX-Export
    """
    from schemas.article import (
        ArticleDocument,
        ArticleMetadata,
        DividerBlock,
        FootnotesBlock,
        GlossaryBlock,
        QuoteBlock,
    )
    from services.html_to_typst import html_to_typst
    from services.renderer import (
        extract_glossary_terms_from_article,
        render_docx_bytes,
        render_pdf_bytes,
        render_preview_svg_pages,
        render_web_html,
    )

    # 1. Tags Validierung (String und Liste)
    meta1 = ArticleMetadata(tags="Aktien, SNB, Zinsen")
    assert meta1.tags == ["Aktien", "SNB", "Zinsen"]
    meta2 = ArticleMetadata(tags=["Inflation", " Gold "])
    assert meta2.tags == ["Inflation", "Gold"]

    # 2. Block-Validierung
    qb = QuoteBlock(
        quote="Die Schweizer Wirtschaft beweist beachtliche Robustheit.",
        author="Thomas Grüter",
        source="Chief Investment Officer",
        layout="column",
    )
    assert qb.type == "quote"
    assert qb.author == "Thomas Grüter"

    div_solid = DividerBlock(style="solid")
    assert div_solid.style == "solid"
    div_dots = DividerBlock(style="dots")
    assert div_dots.style == "dots"

    fn_blk = FootnotesBlock(
        title="Anmerkungen & Quellen",
        items=[
            {"num": "1", "text": "Quelle: Bloomberg, LUKB Investment Office"},
            {"num": "2", "text": "Berechnungsbasis: Monatliche Renditen in CHF"},
        ],
    )
    assert len(fn_blk.items) == 2
    assert fn_blk.items[0]["num"] == "1"

    gloss_blk = GlossaryBlock(
        title="Glossar & Begriffserklärungen",
        auto_collect=True,
        custom_items=[{"term": "Duration", "definition": "Kennzahl für das Zinsänderungsrisiko einer Anleihe."}],
    )
    assert gloss_blk.type == "glossary"

    # 3. HTML to Typst mit Glossar-Tooltip & Inline-Fussnote
    sample_html = (
        '<p>Die <span class="glossary-term" data-tooltip="Schweizerische Nationalbank">SNB</span> '
        'steuert die Geldpolitik.<footnote>Siehe SNB-Geldpolitikbericht 2026.</footnote></p>'
    )
    typst_code = html_to_typst(sample_html)
    assert "#underline" in typst_code
    # Glossar-Begriff wird im Text dezent unterstrichen, aber erzeugt KEINE Seitenfussnote:
    assert "#footnote[Schweizerische Nationalbank]" not in typst_code
    # Die echte Inline-Fussnote wird wie gewünscht als Fussnote gerendert:
    assert "#footnote[Siehe SNB-Geldpolitikbericht 2026.]" in typst_code

    # Test der Auto-Extraction von Glossarbegriffen aus dem Text
    extracted = extract_glossary_terms_from_article([{"type": "richtext", "html": sample_html}])
    assert len(extracted) == 1
    assert extracted[0]["term"] == "SNB"
    assert extracted[0]["definition"] == "Schweizerische Nationalbank"

    # 4. Gesamtdokument zusammenstellen
    doc = ArticleDocument(
        id="art-3a-3b-complete",
        template_id="investment_focus",
        metadata=ArticleMetadata(
            title="Wirtschaftsausblick Schweiz 2026",
            subtitle="Fokus Zinsen und Währungen",
            lead="Die Teuerung bleibt im Zielband, während die Zentralbanken vor weiteren Weichenstellungen stehen.",
            tags=["Geldpolitik", "SNB", "Franken", "Konjunktur"],
            authors=[{"name": "Dr. Reto Krähenbühl", "role": "Leiter Makroökonomie"}],
        ),
        blocks=[
            {"id": "h1", "type": "heading", "level": 1, "text": "Geldpolitische Lage"},
            {"id": "rt1", "type": "richtext", "html": sample_html},
            qb.model_dump(),
            div_dots.model_dump(),
            {"id": "rt2", "type": "richtext", "html": "<p>Nachfolgend die methodischen Erläuterungen.</p>"},
            fn_blk.model_dump(),
            gloss_blk.model_dump(),
        ],
    )

    # 5. Typst PDF Rendering
    pdf_bytes = render_pdf_bytes(doc)
    assert pdf_bytes.startswith(b"%PDF-"), "Typst PDF muss fehlerfrei kompilieren"
    assert len(pdf_bytes) > 8000

    # 6. Typst SVG Rendering
    svg_pages = render_preview_svg_pages(doc)
    assert len(svg_pages) >= 1
    assert "<svg" in svg_pages[0]

    # 7. HTML Rendering
    html_out = render_web_html(doc)
    assert "blk-quote" in html_out
    assert "Thomas Grüter" in html_out
    assert "blk-divider-dots" in html_out
    assert "blk-footnotes" in html_out
    assert "blk-glossary" in html_out
    assert "article-tag" in html_out
    assert "Geldpolitik" in html_out
    assert "Schweizerische Nationalbank" in html_out
    assert "Duration" in html_out

    # 8. DOCX Rendering
    docx_bytes = render_docx_bytes(doc)
    assert docx_bytes.startswith(b"PK\x03\x04")
    assert len(docx_bytes) > 9000

    # 9. Auch in market_flash (1-spaltig) kompilieren
    doc_flash = ArticleDocument(
        id="art-flash-3a-3b",
        template_id="market_flash",
        metadata=doc.metadata,
        blocks=doc.blocks,
    )
    flash_pdf = render_pdf_bytes(doc_flash)
    assert flash_pdf.startswith(b"%PDF-")


def test_publication_date_and_page_numbering():
    """
    Testet:
    1. Datumsformatierung in '8. November 2026' für Publikationsdatum.
    2. Einbettung des Datums im Titel/Lead-Bereich der ersten Seite in allen Templates.
    3. Seitenzahl-Format '(1/5)' bzw. '(aktuelle/Gesamt)' unten rechts in allen Templates.
    """
    # 1. Format-Prüfung
    assert format_publication_date("2026-11-08") == "8. November 2026"
    assert format_publication_date("2026-11-05") == "5. November 2026"
    assert format_publication_date("2026-01-01") == "1. Januar 2026"
    assert format_publication_date("08.11.2026") == "8. November 2026"
    assert format_publication_date("8. November 2026") == "8. November 2026"

    # 2. Template-Prüfung investment_focus
    from schemas.article import ArticleDocument, ArticleMetadata

    doc_focus = ArticleDocument(
        id="art-test-date-focus",
        template_id="investment_focus",
        metadata=ArticleMetadata(
            title="Wachstumsausblick Schweiz",
            subtitle="Konjunktur & Zinsen",
            lead="Die Schweizer Wirtschaft behauptet sich in einem anspruchsvollen weltwirtschaftlichen Umfeld.",
            publication_date="2026-11-08",
        ),
        blocks=[
            {"id": "b1", "type": "heading", "level": 1, "text": "Stabile Inlandsnachfrage"},
            {
                "id": "b2",
                "type": "richtext",
                "html": "<p>Der private Konsum bleibt der wichtigste Pfeiler der Schweizer Konjunktur.</p>" * 8,
            },
        ],
    )

    pdf_focus = render_pdf_bytes(doc_focus)
    assert pdf_focus.startswith(b"%PDF-")
    assert len(pdf_focus) > 5000

    svg_focus = render_preview_svg_pages(doc_focus)
    assert len(svg_focus) >= 1

    html_focus = render_web_html(doc_focus)
    assert "8. November 2026" in html_focus
    assert "Wachstumsausblick Schweiz" in html_focus
    assert "1/1" in html_focus

    # 3. Template-Prüfung market_flash
    doc_flash = ArticleDocument(
        id="art-test-date-flash",
        template_id="market_flash",
        metadata=ArticleMetadata(
            title="SNB Leitzinsentscheid",
            subtitle="Market Flash",
            lead="Die Schweizerische Nationalbank belässt den Leitzins unverändert.",
            publication_date="2026-11-08",
        ),
        blocks=[
            {"id": "bf1", "type": "heading", "level": 1, "text": "Entscheid im Einklang mit Konsens"},
            {
                "id": "bf2",
                "type": "richtext",
                "html": "<p>Die Inflationsentwicklung verläuft gemäss den Prognosen der Notenbank.</p>" * 8,
            },
        ],
    )

    pdf_flash = render_pdf_bytes(doc_flash)
    assert pdf_flash.startswith(b"%PDF-")
    assert len(pdf_flash) > 5000

    svg_flash = render_preview_svg_pages(doc_flash)
    assert len(svg_flash) >= 1

    html_flash = render_web_html(doc_flash)
    assert "8. November 2026" in html_flash
    assert "SNB Leitzinsentscheid" in html_flash


def test_rbac_and_soft_delete():
    """
    Testet das Rollenmodell (Admin, Publisher, Author), die Schutzregel gegen
    das Löschen publizierter Dokumente sowie Soft-Delete und Wiederherstellung.
    """
    import config
    from database.repository import (
        create_new_article,
        delete_article,
        get_article,
        list_articles,
        restore_article,
        save_article,
    )

    # 1. Rollenprüfung
    orig_admins = config.PORTAL_ADMINS
    orig_pubs = config.PORTAL_PUBLISHERS
    try:
        config.PORTAL_ADMINS = ["admin_user"]
        config.PORTAL_PUBLISHERS = ["senior_editor"]

        assert config.get_user_role("admin_user") == "admin"
        assert config.can_publish("admin_user") is True
        assert config.can_delete("admin_user") is True

        assert config.get_user_role("senior_editor") == "publisher"
        assert config.can_publish("senior_editor") is True
        assert config.can_delete("senior_editor") is True

        assert config.get_user_role("intern_analyst") == "author"
        assert config.can_publish("intern_analyst") is False
        assert config.can_delete("intern_analyst") is False

        # Fallback wenn keine Rollen definiert sind:
        config.PORTAL_ADMINS = []
        config.PORTAL_PUBLISHERS = []
        assert config.can_publish("any_user") is True
        assert config.can_delete("any_user") is True
    finally:
        config.PORTAL_ADMINS = orig_admins
        config.PORTAL_PUBLISHERS = orig_pubs

    # 2. Schutzregel: Publizierte Artikel dürfen NICHT gelöscht werden
    doc = create_new_article(user="Test Author")
    doc.status = "published"
    save_article(doc, user="Test Author")

    assert delete_article(doc.id) is False, "Publizierter Artikel darf nicht gelöscht werden"
    loaded = get_article(doc.id)
    assert loaded is not None
    assert loaded.status == "published"

    # 3. Soft-Delete (Archivierung)
    loaded.status = "draft"
    save_article(loaded, user="Test Author")
    assert delete_article(loaded.id) is True

    # Muss jetzt status 'archived' haben
    archived_doc = get_article(loaded.id)
    assert archived_doc is not None
    assert archived_doc.status == "archived"

    # Aus normaler list_articles() ausgeblendet
    active_list = list_articles(status_filter="all")
    assert not any(a["id"] == loaded.id for a in active_list)

    # In Papierkorb-Filter enthalten
    archived_list = list_articles(status_filter="archived")
    assert any(a["id"] == loaded.id for a in archived_list)

    # 4. Wiederherstellen (Restore)
    assert restore_article(loaded.id, user="Admin") is True
    restored_doc = get_article(loaded.id)
    assert restored_doc is not None
    assert restored_doc.status == "draft"

    active_list_after = list_articles(status_filter="all")
    assert any(a["id"] == loaded.id for a in active_list_after)


def test_publications_block_layout_and_url():
    """
    Testet den Block 'Weitere Publikationen':
    - Layout: '"Titel" vom 9. November 2026' bzw. '"Titel" vom 19. November 2026'
    - Kein separates Feld für den Publikationstyp im Layout
    - Optionale URL öffnet im neuen Tab (target="_blank", rel="noopener noreferrer")
    - Bei URL: kleines Symbol eingeblendet, kein Link-Underline
    - PDF-Kompilierung (Typst) & Web-HTML & Word-Export
    """
    from schemas.article import ArticleDocument, PublicationsBlock, PublicationItem

    # 1. Pydantic Schema Validierung
    block = PublicationsBlock(
        title="Weitere Publikationen",
        items=[
            {
                "title": "Schweizer Dividendentitel vor starker Berichtssaison",
                "subtitle": "Anlagepolitik & Märkte",
                "date": "2026-11-19",
                "url": "https://www.lukb.ch/publikationen/dividendentitel-2026",
                "enabled": True,
            },
            {
                "title": "Zinsentscheid der Schweizerischen Nationalbank",
                "subtitle": "Makroökonomie",
                "date": "09.11.2026",
                "url": "",
                "enabled": True,
            },
        ],
    )
    assert len(block.items) == 2
    assert block.items[0]["url"] == "https://www.lukb.ch/publikationen/dividendentitel-2026"
    assert block.items[1]["url"] == ""

    # 2. Web HTML Rendering
    doc = create_new_article(template_id="investment_focus", user="Test Analyst")
    doc.metadata.title = "Test Artikel für Weitere Publikationen"
    doc.blocks.append(block.model_dump())

    html_out = render_web_html(doc)

    # Prüfe: Format '"Titel" vom 19. November 2026'
    assert '"Schweizer Dividendentitel vor starker Berichtssaison"' in html_out
    assert "vom" in html_out and "19. November 2026" in html_out
    # Prüfe: Format 'vom 9. November 2026' (keine führende Null beim Tag)
    assert '"Zinsentscheid der Schweizerischen Nationalbank"' in html_out
    assert "9. November 2026" in html_out

    # Prüfe: Kein separates Feld für Publikationstyp (weder Untertitel noch Rubrik im Layout)
    assert "Anlagepolitik & Märkte" not in html_out
    assert "Makroökonomie" not in html_out
    assert "pub-subtitle" not in html_out

    # Prüfe: URL mit target="_blank", rel="noopener noreferrer", no underline & Symbol
    assert 'href="https://www.lukb.ch/publikationen/dividendentitel-2026"' in html_out
    assert 'target="_blank"' in html_out
    assert 'rel="noopener noreferrer"' in html_out
    assert "text-decoration: none" in html_out
    assert "pub-link-icon" in html_out

    # 3. Typst PDF & SVG Preview Rendering
    pdf_bytes = render_pdf_bytes(doc)
    assert len(pdf_bytes) > 5000, "PDF muss erfolgreich erzeugt worden sein"

    svg_pages = render_preview_svg_pages(doc)
    assert len(svg_pages) >= 1

    # 4. Market Flash Template Rendering
    doc.template_id = "market_flash"
    pdf_flash = render_pdf_bytes(doc)
    assert len(pdf_flash) > 5000

    # 5. Word DOCX Export Rendering
    docx_bytes = render_docx_bytes(doc)
    assert len(docx_bytes) > 2000

    delete_article(doc.id)


def test_table_column_widths_db_chart_palette_and_paragraph_links():
    """
    Prüft die fünf neuen Anpassungen im Backend, Typst, HTML5 und DOCX:
    1. Tabellen: Relative Spaltenbreiten (TableColumn.width)
    2. DB-Charts: Eigene Farbpaletten-Steuerung (palette, palette_colors, series.color)
    3. Textabsätze: Inline-Links mit target="_blank", ohne Underline, mit Pfeilsymbol (wie Weitere Publikationen)
    4. Typst-Vorschau: 1/3 Bildschirmbreite & an-/ausschaltbare Live-Aktualisierung
    """
    from schemas.article import ArticleDocument, DbChartBlock, TableBlock
    from services.chart_generator import generate_db_chart_svg, resolve_chart_palette

    init_db_and_seed()

    # 1. Tabellen mit prozentualen Spaltenbreiten (Summe = 100%) & vertikaler Ausrichtung 'top'
    default_tbl = TableBlock()
    assert [c.width for c in default_tbl.columns] == [33.4, 33.3, 33.3]
    assert abs(sum(c.width for c in default_tbl.columns) - 100.0) < 0.01

    no_width_tbl = TableBlock(
        columns=[
            {"field": "a", "title": "A", "align": "left"},
            {"field": "b", "title": "B", "align": "right"},
        ]
    )
    assert [c.width for c in no_width_tbl.columns] == [50.0, 50.0]

    legacy_tbl = TableBlock(
        columns=[
            {"field": "a", "title": "A", "align": "left", "width": 1.4},
            {"field": "b", "title": "B", "align": "right", "width": 1.0},
            {"field": "c", "title": "C", "align": "right", "width": 1.0},
        ]
    )
    assert abs(sum(c.width for c in legacy_tbl.columns) - 100.0) < 0.01

    tbl_blk = TableBlock(
        title="Relative Spaltenbreiten Test",
        columns=[
            {"field": "name", "title": "Bezeichnung", "align": "left", "width": 75.0},
            {"field": "val", "title": "Wert", "align": "right", "width": 25.0},
        ],
        rows=[
            {"name": "Aktien Schweiz mit längerem Beschreibungstext für Umbruchtest", "val": "25.0 %"},
            {"name": "Obligationen CHF", "val": "35.0 %"},
        ],
    )
    assert tbl_blk.columns[0].width == 75.0
    assert tbl_blk.columns[1].width == 25.0

    # 2. DB-Chart Palettensteuerung (nur LUKB Standard & Blau-Abstufung) & Default-Typ 'line'
    default_chart = DbChartBlock(title="Default Chart")
    assert all(s.chart_type == "line" for s in default_chart.series)

    legacy_chart = DbChartBlock(title="Legacy Palette", palette="lukb_contrast")
    assert legacy_chart.palette == "lukb_classic"

    chart_blk = DbChartBlock(
        title="Paletten Test Chart",
        palette="lukb_blues",
        series=[
            {"ticker": "SMI", "chart_type": "line", "label": "SMI"},
            {"ticker": "SP500", "chart_type": "line", "label": "S&P 500"},
        ],
    )
    assert chart_blk.palette == "lukb_blues"
    resolved_pal = resolve_chart_palette(chart_blk.model_dump())
    assert resolved_pal == ["#002855", "#005A9C", "#009FE3", "#5BB8E8", "#9BD3F2"]

    chart_svg = generate_db_chart_svg(chart_blk.model_dump())
    assert "#002855" in chart_svg
    assert "#005A9C" in chart_svg

    # 3. Links in Textabsätzen (ohne Underline, target="_blank", Pfeilsymbol)
    raw_link_html = '<p>Siehe auch unsere <a href="https://www.lukb.ch/marktbericht">Marktanalyse 2026</a> für Details.</p>'
    typ_code = html_to_typst(raw_link_html)
    assert '#link("https://www.lukb.ch/marktbericht")' in typ_code
    assert "#sym.arrow.tr" in typ_code
    assert "#underline" not in typ_code

    doc = ArticleDocument(
        id="art-new-features-test",
        template_id="investment_focus",
        blocks=[
            {"id": "rt_link", "type": "richtext", "html": raw_link_html},
            tbl_blk.model_dump(),
            chart_blk.model_dump(),
        ],
    )

    html_out = render_web_html(doc)
    # Tabelle: 75.00% und 25.00%, vertikale Ausrichtung top
    assert "width: 75.00%;" in html_out
    assert "width: 25.00%;" in html_out
    assert "vertical-align: top;" in html_out
    # Link im Textabsatz: target="_blank", no underline CSS, arrow icon CSS
    assert 'href="https://www.lukb.ch/marktbericht"' in html_out
    assert 'target="_blank"' in html_out
    assert ".blk-richtext a" in html_out
    assert "text-decoration: none !important;" in html_out

    # Typst PDF & SVG (beide Templates) & 'top' Zellenausrichtung in render-table-box
    typ_focus_tbl = (ROOT / "templates" / "investment_focus" / "template.typ").read_text(encoding="utf-8").split("#let render-table-box")[1].split("#let render-quote-box")[0]
    typ_flash_tbl = (ROOT / "templates" / "market_flash" / "template.typ").read_text(encoding="utf-8").split("#let render-table-box")[1].split("#let render-quote-box")[0]
    assert "left + top" in typ_focus_tbl and "left + horizon" not in typ_focus_tbl
    assert "left + top" in typ_flash_tbl and "left + horizon" not in typ_flash_tbl

    pdf_focus = render_pdf_bytes(doc)
    assert pdf_focus.startswith(b"%PDF-")
    svgs = render_preview_svg_pages(doc)
    assert len(svgs) >= 1

    doc.template_id = "market_flash"
    pdf_flash = render_pdf_bytes(doc)
    assert pdf_flash.startswith(b"%PDF-")

    # Word DOCX Export
    docx_bytes = render_docx_bytes(doc)
    assert docx_bytes.startswith(b"PK\x03\x04")

    # 4 & 5. CSS 1/3 Breite, Auto-Typst-Toggle, Editor-Zellumbruch & Top-Alignment
    css_text = (ROOT / "www" / "css" / "editor.css").read_text(encoding="utf-8")
    assert "33.333%" in css_text
    assert ".richtext-editable a" in css_text
    assert ".db-chart-palette-bar" in css_text
    assert ".grid-col-width-input" in css_text
    assert "white-space: pre-wrap;" in css_text
    assert "vertical-align: top;" in css_text

    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "toggle-auto-preview" in app_text
    assert "lukb_auto_preview_toggle" in app_text


if __name__ == "__main__":
    test_mssql_url_builder()
    test_html_to_typst_escaping()
    test_shiny_tuple_deserialization_in_pydantic()
    test_textbox_start_end_markers_grouping()
    test_concurrent_multi_author_block_merge()
    test_db_chart_timeseries_block()
    test_layout_elements_spacer_and_colbreak()
    test_smart_cms_features_3a_and_3b()
    test_publication_date_and_page_numbering()
    test_rbac_and_soft_delete()
    test_publications_block_layout_and_url()
    test_table_column_widths_db_chart_palette_and_paragraph_links()
    test_full_cms_workflow()
    from tests.test_portal_publisher import test_portal_publisher_flow
    test_portal_publisher_flow()
    from tests.test_connect_client import test_connect_client_not_configured, test_connect_client_configured_url
    test_connect_client_not_configured()
    test_connect_client_configured_url()
    assert app is not None
    print("ALL TESTS PASSED SUCCESSFULLY!")
