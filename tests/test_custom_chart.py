"""
Unit- und Integrationstests für das Custom-Chart-Tool (Clipboard / Wide-Format).
Testet:
- Wide-Format TSV/CSV-Parsing & Datenbereinigung (Schweizer Tausendertrenner, Kommas, Prozente, Datumsangaben)
- Automatische Diagrammtyp-Erkennung
- SVG-Vektorgrafik-Generierung für:
  * Pie / Doughnut (Kuchen / Ring mit Legende & Prozentangaben)
  * Kategorie-Säulen (gruppiert & gestapelt mit Legende)
  * Zeitreihen (Datumsachse, benutzerdefinierte Serien-Labels, verschiedene Stile)
- Pydantic-Schema & Validierung
- Typst-PDF & Jinja2-Web-HTML Dual-Output-Rendering
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.article import ArticleDocument, CustomChartBlock, CustomChartSeriesItem, parse_block
from services.chart_common import (
    _count_needed_decimals,
    _format_ch_number,
    _format_single_ch_number,
    format_axis_ticks,
)
from services.chart_generator import _estimate_label_width_px, generate_db_chart_svg
from services.custom_chart_generator import (
    generate_custom_chart_svg,
    infer_chart_configuration,
    parse_flexible_date,
    parse_number,
    parse_wide_tsv_data,
)
from services.renderer import render_docx_bytes, render_pdf_bytes, render_web_html


def test_parsing_helpers():
    # 1. Zahlen-Parsing
    assert parse_number("1234.56") == 1234.56
    assert parse_number("1'250.50") == 1250.50
    assert parse_number("1 250,50") == 1250.50
    assert parse_number("12.5 %") == 12.5
    assert parse_number("-3.4%") == -3.4
    assert parse_number("(100.5)") == -100.5
    assert parse_number("-") is None
    assert parse_number("n/a") is None
    assert parse_number(None) is None

    # 2. Datums-Parsing
    assert parse_flexible_date("2024-05-15") == date(2024, 5, 15)
    assert parse_flexible_date("15.05.2024") == date(2024, 5, 15)
    assert parse_flexible_date("5.1.2024") == date(2024, 1, 5)
    assert parse_flexible_date("2024/05/15") == date(2024, 5, 15)
    assert parse_flexible_date("05.2024") == date(2024, 5, 1)
    assert parse_flexible_date("2024-Q2") == date(2024, 4, 1)
    assert parse_flexible_date("Q3 2024") == date(2024, 7, 1)
    assert parse_flexible_date("2024") == date(2024, 1, 1)
    assert parse_flexible_date("invalid") is None

    # 3. Wide-Format TSV Parsing
    tsv_content = (
        "Anlageklasse\tAktuell\tBenchmark\n"
        "Aktien Schweiz\t1'250.50\t1'200.00\n"
        "Obligationen CHF\t850.00\t900.00\n"
    )
    cols, rows = parse_wide_tsv_data(tsv_content, has_header=True)
    assert cols == ["Anlageklasse", "Aktuell", "Benchmark"]
    assert len(rows) == 2
    assert rows[0] == ["Aktien Schweiz", "1'250.50", "1'200.00"]
    assert rows[1] == ["Obligationen CHF", "850.00", "900.00"]

    # Ohne Header
    cols_no_hdr, rows_no_hdr = parse_wide_tsv_data(tsv_content, has_header=False)
    assert len(cols_no_hdr) == 3
    assert len(rows_no_hdr) == 3


def test_auto_detection():
    # Zeitreihen-Erkennung
    tsv_ts = (
        "Datum\tSMI\tSP500\n"
        "2024-01-01\t11150\t4750\n"
        "2024-02-01\t11300\t4900\n"
        "2024-03-01\t11600\t5100\n"
    )
    cols_ts, rows_ts = parse_wide_tsv_data(tsv_ts, has_header=True)
    cfg_ts = infer_chart_configuration(cols_ts, rows_ts)
    assert cfg_ts["chart_type"] == "timeseries"
    assert cfg_ts["x_col"] == "Datum"
    assert len(cfg_ts["series"]) == 2

    # Doughnut-Erkennung bei 2 Spalten und Anteilen ~100%
    tsv_pie = (
        "Asset\tAnteil\n"
        "Aktien\t40%\n"
        "Bonds\t35%\n"
        "Cash\t25%\n"
    )
    cols_pie, rows_pie = parse_wide_tsv_data(tsv_pie, has_header=True)
    cfg_pie = infer_chart_configuration(cols_pie, rows_pie)
    assert cfg_pie["chart_type"] == "doughnut"
    assert cfg_pie["x_col"] == "Asset"


def test_doughnut_and_pie_svg():
    tsv_alloc = (
        "Kategorie\tAnteil\n"
        "Aktien Schweiz\t35.0%\n"
        "Aktien Ausland\t25.0%\n"
        "Obligationen\t30.0%\n"
        "Liquidität\t10.0%\n"
    )
    # 1. Doughnut mit Legende unten (KEIN Wert im Loch!)
    blk_doughnut_bottom = {
        "id": "blk_donut_1",
        "type": "custom_chart",
        "chart_type": "doughnut",
        "doughnut_hole_pct": 55,
        "legend_position": "bottom",
        "raw_tsv": tsv_alloc,
        "palette": "lukb_classic",
        "layout": "column",
    }
    svg_donut = generate_custom_chart_svg(blk_doughnut_bottom, embed_fonts=False)
    assert "<svg" in svg_donut
    assert "Aktien Schweiz" in svg_donut
    assert "35.0 %" in svg_donut
    # Anforderung: beim Pie/Doughnut KEIN Wert im Loch anzeigen
    assert 'text-anchor="middle"' not in svg_donut

    # 2. Doughnut mit Legende rechts
    blk_doughnut_right = {
        "id": "blk_donut_2",
        "type": "custom_chart",
        "chart_type": "doughnut",
        "legend_position": "right",
        "raw_tsv": tsv_alloc,
        "palette": "lukb_classic",
        "layout": "column",
    }
    svg_donut_right = generate_custom_chart_svg(blk_doughnut_right, embed_fonts=False)
    assert "<svg" in svg_donut_right
    assert "Aktien Ausland" in svg_donut_right

    # 3. Pie (ohne Loch via hole_pct=0) mit Legende rechts und grosser Chartfläche (64mm)
    blk_pie = {
        "id": "blk_pie_1",
        "type": "custom_chart",
        "chart_type": "pie",
        "doughnut_hole_pct": 0,
        "chart_height_mm": 64,
        "legend_position": "right",
        "raw_tsv": tsv_alloc,
        "palette": "lukb_blues",
        "layout": "column",
    }
    svg_pie = generate_custom_chart_svg(blk_pie, embed_fonts=False)
    assert "<svg" in svg_pie
    assert "Aktien Ausland" in svg_pie
    assert "25.0 %" in svg_pie

    # Sicherstellen, dass die Legende rechts auch bei 64mm nicht über 680px hinausragt
    # und dass die Schriftgrösse nicht kleiner ist als Quelle/Untertitel (>= 20.5px in Spalten-Layout)
    import re
    text_matches = re.findall(r'<text x="([0-9.]+)" y="([0-9.]+)" font-size="([0-9.]+)".*?>(.*?)</text>', svg_pie)
    assert len(text_matches) > 0
    for x_str, y_str, fs_str, content in text_matches:
        x_val = float(x_str)
        fs_val = float(fs_str)
        assert fs_val >= 20.5, f"Legend font-size {fs_val} must not be smaller than source/subtitle font size (20.5px)"
        # Reiner Text ohne XML-Tags
        clean_content = re.sub(r'<[^>]+>', '', content)
        est_right_edge = x_val + _estimate_label_width_px(clean_content, fs_val)
        assert est_right_edge <= 680.0, f"Legend text '{clean_content}' exceeds SVG width: {est_right_edge} > 680"

    # 4. Benutzerdefinierte Spaltenanzahl für Legende (1 Spalte vs 2 Spalten)
    blk_donut_2cols = dict(blk_doughnut_bottom)
    blk_donut_2cols["legend_columns"] = 2
    svg_2cols = generate_custom_chart_svg(blk_donut_2cols, embed_fonts=False)
    assert "<svg" in svg_2cols

    blk_donut_1col = dict(blk_doughnut_bottom)
    blk_donut_1col["legend_columns"] = 1
    svg_1col = generate_custom_chart_svg(blk_donut_1col, embed_fonts=False)
    assert "<svg" in svg_1col


def test_category_bar_svg():
    tsv_bar = (
        "Sektor\t2023\t2024\n"
        "Technologie\t15.2\t18.4\n"
        "Gesundheit\t12.0\t11.5\n"
        "Finanzen\t-4.5\t6.2\n"
    )
    # 1. Gruppierte vertikale Säulen mit separaten Labels
    blk_grouped = {
        "id": "blk_bar_1",
        "type": "custom_chart",
        "chart_type": "category_bar",
        "orientation": "vertical",
        "bar_mode": "grouped",
        "color_by_category": False,
        "raw_tsv": tsv_bar,
        "series": [
            {"field": "2023", "label": "Vorjahr 2023", "chart_type": "bar", "enabled": True},
            {"field": "2024", "label": "Laufendes Jahr 2024", "chart_type": "bar", "enabled": True},
        ],
        "layout": "column",
    }
    svg_grouped = generate_custom_chart_svg(blk_grouped, embed_fonts=False)
    assert "<svg" in svg_grouped
    assert "Technologie" in svg_grouped
    assert "Vorjahr 2023" in svg_grouped
    assert "Laufendes Jahr 2024" in svg_grouped

    # 2. Gestapelte vertikale Säulen
    blk_stacked = dict(blk_grouped)
    blk_stacked["bar_mode"] = "stacked"
    svg_stacked = generate_custom_chart_svg(blk_stacked, embed_fonts=False)
    assert "<svg" in svg_stacked
    assert "Finanzen" in svg_stacked

    # 3. Bunte Säulen (unterschiedliche Balkenfarben pro Kategorie)
    tsv_single = (
        "Asset\tPerformance\n"
        "Aktien\t15.0\n"
        "Bonds\t3.5\n"
        "Gold\t22.0\n"
    )
    blk_bunt = {
        "id": "blk_bar_bunt",
        "type": "custom_chart",
        "chart_type": "category_bar",
        "orientation": "vertical",
        "color_by_category": True,
        "raw_tsv": tsv_single,
        "palette": "lukb_classic",
    }
    svg_bunt = generate_custom_chart_svg(blk_bunt, embed_fonts=False)
    assert "<svg" in svg_bunt
    # LUKB Classic Farben müssen als fill vorkommen (#037FDA, #9CD4FB, #431231)
    assert 'fill="#037FDA"' in svg_bunt
    assert 'fill="#9CD4FB"' in svg_bunt
    assert 'fill="#431231"' in svg_bunt

    # 4. Horizontales Balkendiagramm (Balken von links nach rechts)
    blk_horizontal = {
        "id": "blk_bar_horiz",
        "type": "custom_chart",
        "chart_type": "category_bar",
        "orientation": "horizontal",
        "color_by_category": True,
        "raw_tsv": tsv_single,
        "palette": "lukb_classic",
    }
    svg_horiz = generate_custom_chart_svg(blk_horizontal, embed_fonts=False)
    assert "<svg" in svg_horiz
    assert "Aktien" in svg_horiz
    assert "Bonds" in svg_horiz
    assert "Gold" in svg_horiz

    # 5. User-Szenario: Mehrzeiliger Umbruch der Achsenbeschriftung & vertikal zentrierte Legende
    tsv_user = (
        "Kategorie\tAktuell\tVorjahr\n"
        "Aktien Schweiz\t14.5\t12.0\n"
        "Aktien Global\t18.2\t15.5\n"
        "Obligationen CHF\t2.5\t1.8\n"
        "Liquidität\t0.5\t0.2\n"
    )
    blk_user = {
        "id": "blk_user_cat",
        "type": "custom_chart",
        "chart_type": "category_bar",
        "orientation": "vertical",
        "raw_tsv": tsv_user,
        "layout": "column",
    }
    svg_user = generate_custom_chart_svg(blk_user, embed_fonts=False)
    assert "<svg" in svg_user
    # Zeilenumbruch: Wörter sollen separat vorkommen und KEINE Ellipsis (…) enthalten
    assert "Aktien" in svg_user
    assert "Schweiz" in svg_user
    assert "Global" in svg_user
    assert "Obligationen" in svg_user
    assert "CHF" in svg_user
    assert "Liquidität" in svg_user
    assert "Aktien Schw…" not in svg_user
    assert "Aktien Glob…" not in svg_user
    assert "Obligatione…" not in svg_user

    # Zentrierung der Legende prüfen
    import re
    # Finde die maximale y-Position der Achsentexte (text-anchor="middle")
    axis_y_matches = [float(y) for y in re.findall(r'<text [^>]*y="([0-9.]+)" [^>]*text-anchor="middle"', svg_user)]
    assert len(axis_y_matches) > 0
    max_axis_y = max(axis_y_matches)

    # Finde die y-Position der Legendenboxen
    legend_rect_matches = [float(y) for y in re.findall(r'<rect [^>]*y="([0-9.]+)" [^>]*width="14"', svg_user)]
    assert len(legend_rect_matches) > 0
    legend_top = min(legend_rect_matches)
    legend_bottom = max(legend_rect_matches) + 14.0

    svg_h_val = float(re.findall(r'<svg [^>]*height="([0-9.]+)"', svg_user)[0])

    # Abstand zwischen Achsenbeschriftung und Legende
    gap_above = legend_top - max_axis_y
    # Abstand zwischen Legende und Quellenangabe (unter dem SVG + ca. 12px externer Typst/HTML-Abstand)
    gap_below = (svg_h_val - legend_bottom) + 12.0

    # Legende darf nicht zu nah an der Achse kleben
    assert gap_above >= 25.0, f"Gap above legend too cramped: {gap_above} < 25px"
    # Und muss vertikal in der Mitte platziert sein (Abstand oben und unten nahezu identisch)
    assert abs(gap_above - gap_below) <= 5.0, f"Legend not vertically centered: gap_above={gap_above}, gap_below={gap_below}"


def test_timeseries_svg():
    tsv_ts = (
        "Datum\tSMI\tSP500\n"
        "2023-01-01\t11000\t3900\n"
        "2023-06-01\t11250\t4400\n"
        "2024-01-01\t11150\t4750\n"
        "2024-06-01\t12000\t5400\n"
    )
    blk_ts = {
        "id": "blk_ts_1",
        "type": "custom_chart",
        "chart_type": "timeseries",
        "raw_tsv": tsv_ts,
        "series": [
            {"field": "SMI", "label": "Swiss Market Index (SMI)", "chart_type": "line", "enabled": True},
            {"field": "SP500", "label": "S&P 500 Index (USA)", "chart_type": "area", "enabled": True},
        ],
        "layout": "column",
    }
    svg_ts = generate_custom_chart_svg(blk_ts, embed_fonts=False)
    assert "<svg" in svg_ts
    assert "Swiss Market Index (SMI)" in svg_ts
    assert "S&amp;P 500 Index (USA)" in svg_ts


def test_pydantic_schema_validation():
    raw_blk = {
        "id": "blk_cust_test",
        "type": "custom_chart",
        "title": "Vermögensaufteilung",
        "subtitle": "Stand Ende Q3 2024",
        "source": "Quelle: LUKB Asset Management",
        "chart_type": "doughnut",
        "doughnut_hole_pct": 60,
        "raw_tsv": "Klasse\tAnteil\nAktien\t50%\nBonds\t50%\n",
        "series": [
            {"field": "Anteil", "label": "Allokation", "chart_type": "line", "enabled": True}
        ],
    }
    parsed = parse_block(raw_blk)
    assert isinstance(parsed, CustomChartBlock)
    assert parsed.chart_type == "doughnut"
    assert parsed.doughnut_hole_pct == 60
    assert parsed.series[0].label == "Allokation"
    assert parsed.legend_columns is None

    # Test legend_columns int und "auto" String Normalisierung
    raw_blk["legend_columns"] = 3
    parsed3 = parse_block(raw_blk)
    assert parsed3.legend_columns == 3

    raw_blk["legend_columns"] = "auto"
    parsed_auto = parse_block(raw_blk)
    assert parsed_auto.legend_columns is None


def test_chart_height_scaling():
    import re

    # 1. Doughnut / Pie
    blk_donut = {
        "type": "custom_chart",
        "chart_type": "doughnut",
        "chart_height_mm": 28,
        "raw_tsv": "Kategorie\tAnteil\nA\t40\nB\t60",
    }
    svg_d28 = generate_custom_chart_svg(blk_donut)
    blk_donut["chart_height_mm"] = 64
    svg_d64 = generate_custom_chart_svg(blk_donut)
    h_d28 = int(re.findall(r'height="(\d+)"', svg_d28)[0])
    h_d64 = int(re.findall(r'height="(\d+)"', svg_d64)[0])
    assert h_d64 > h_d28 + 150, f"Doughnut SVG height should scale with chart_height_mm: {h_d28} vs {h_d64}"

    # 2. Horizontal Bar
    blk_hbar = {
        "type": "custom_chart",
        "chart_type": "category_bar",
        "orientation": "horizontal",
        "chart_height_mm": 28,
        "raw_tsv": "Branche\tPerformance\nFinanzen\t12\nTech\t18",
    }
    svg_h28 = generate_custom_chart_svg(blk_hbar)
    blk_hbar["chart_height_mm"] = 64
    svg_h64 = generate_custom_chart_svg(blk_hbar)
    h_h28 = int(re.findall(r'height="(\d+)"', svg_h28)[0])
    h_h64 = int(re.findall(r'height="(\d+)"', svg_h64)[0])
    assert h_h64 > h_h28 + 150, f"Horizontal bar SVG height should scale with chart_height_mm: {h_h28} vs {h_h64}"

    # 3. Vertical Bar
    blk_vbar = {
        "type": "custom_chart",
        "chart_type": "category_bar",
        "orientation": "vertical",
        "chart_height_mm": 28,
        "raw_tsv": "Branche\tPerformance\nFinanzen\t12\nTech\t18",
    }
    svg_v28 = generate_custom_chart_svg(blk_vbar)
    blk_vbar["chart_height_mm"] = 64
    svg_v64 = generate_custom_chart_svg(blk_vbar)
    h_v28 = int(re.findall(r'height="(\d+)"', svg_v28)[0])
    h_v64 = int(re.findall(r'height="(\d+)"', svg_v64)[0])
    assert h_v64 > h_v28 + 150, f"Vertical bar SVG height should scale with chart_height_mm: {h_v28} vs {h_v64}"


def test_dual_output_typst_and_web_rendering():
    # Artikel mit custom_chart erstellen und via Typst (PDF) & HTML rendern
    doc = ArticleDocument(
        template_id="investment_focus",
        status="draft",
        blocks=[
            {
                "id": "blk_h1",
                "type": "heading",
                "level": 2,
                "text": "Asset Allocation Q4",
            },
            {
                "id": "blk_txt_1",
                "type": "richtext",
                "html": "<p>Die Schweizer Wirtschaft zeigt sich weiterhin robust mit solider Binnennachfrage.</p>",
            },
            {
                "id": "blk_chart_donut",
                "type": "custom_chart",
                "title": "Aktuelle Portfoliostruktur",
                "subtitle": "In Prozent der Gesamtanlagen",
                "source": "Quelle: LUKB Investment Office",
                "layout": "column",
                "chart_type": "doughnut",
                "doughnut_hole_pct": 55,
                "raw_tsv": "Kategorie\tAnteil\nAktien Schweiz\t35%\nAktien Welt\t25%\nObligationen CHF\t30%\nLiquidität\t10%\n",
            },
        ],
    )

    # 1. Web HTML Rendering
    html_out = render_web_html(doc)
    assert "Aktuelle Portfoliostruktur" in html_out
    assert "data:image/svg+xml;base64," in html_out

    # 2. Typst PDF Rendering
    pdf_bytes = render_pdf_bytes(doc)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes[:5] == b"%PDF-"

    # 3. Word DOCX Rendering
    docx_bytes = render_docx_bytes(doc)
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 1000

    # 4. JS Modulprüfung: Farbpaletten & Höhen-Presets identisch zu DB-Chart (gemeinsam über state.js)
    state_src = (ROOT / "www" / "js" / "modules" / "state.js").read_text(encoding="utf-8")
    js_src = (ROOT / "www" / "js" / "modules" / "custom-chart.js").read_text(encoding="utf-8")
    combined_js = state_src + "\n" + js_src
    assert 'label: "28 mm", val: 28' in combined_js
    assert 'label: "36 mm (Standard)", val: 36' in combined_js
    assert 'label: "46 mm", val: 46' in combined_js
    assert 'label: "56 mm", val: 56' in combined_js
    assert "db-chart-palette-bar" in combined_js
    assert "db-palette-preset-btn" in combined_js
    assert "db-series-color-dot" in combined_js


def test_custom_chart_svg_cache():
    from services.custom_chart_generator import (
        _CUSTOM_CHART_SVG_CACHE,
        clear_custom_chart_cache,
        generate_custom_chart_svg,
    )

    clear_custom_chart_cache()
    assert len(_CUSTOM_CHART_SVG_CACHE) == 0

    blk = {
        "id": "cache_test_blk",
        "type": "custom_chart",
        "chart_type": "category_bar",
        "raw_tsv": "Kategorie\tWert\nAktien\t45\nBonds\t55\n",
    }
    svg1 = generate_custom_chart_svg(blk)
    assert isinstance(svg1, str) and "<svg" in svg1
    assert len(_CUSTOM_CHART_SVG_CACHE) == 1

    svg2 = generate_custom_chart_svg(blk)
    assert svg2 is svg1
    assert len(_CUSTOM_CHART_SVG_CACHE) == 1

    blk_changed = dict(blk, chart_height_mm=46)
    svg3 = generate_custom_chart_svg(blk_changed)
    assert svg3 != svg1
    assert len(_CUSTOM_CHART_SVG_CACHE) == 2

    svg_plain1 = generate_custom_chart_svg(blk, embed_fonts=False)
    svg_plain2 = generate_custom_chart_svg(blk, embed_fonts=False)
    assert svg_plain2 is svg_plain1
    assert svg_plain1 != svg1 or len(_CUSTOM_CHART_SVG_CACHE) == 3
    assert len(_CUSTOM_CHART_SVG_CACHE) == 3

    clear_custom_chart_cache()
    assert len(_CUSTOM_CHART_SVG_CACHE) == 0


def test_consistent_axis_tick_decimals():
    """
    Stellt sicher, dass an Achsen (Zeitreihen & Kategoriebalken) immer einheitlich viele
    Nachkommastellen dargestellt werden (entsprechend der Zahl, die die meisten benötigt).
    Beispiel: 100.0, 97.5, 95.0 statt 100, 97.5, 95.
    """
    # 1. Nachkommastellen-Erkennung
    assert _count_needed_decimals(100.0) == 0
    assert _count_needed_decimals(97.5) == 1
    assert _count_needed_decimals(95.0) == 0
    assert _count_needed_decimals(0.25) == 2
    assert _count_needed_decimals(0.005) == 3
    assert _count_needed_decimals(0.0) == 0

    # 2. Einheitliche Formatierung mit format_axis_ticks
    # Schrittweite 2.5: 97.5 benötigt 1 Dezimalstelle -> alle Ticks erhalten 1 Dezimalstelle
    ticks_25 = [90.0, 92.5, 95.0, 97.5, 100.0, 102.5]
    res_25 = format_axis_ticks(ticks_25, step=2.5)
    assert res_25 == ["90.0", "92.5", "95.0", "97.5", "100.0", "102.5"]
    assert "100.0" in res_25
    assert "97.5" in res_25
    assert "95.0" in res_25

    # Ticks direkt: 100, 97.5, 95 -> 100.0, 97.5, 95.0
    res_direct = format_axis_ticks([100.0, 97.5, 95.0])
    assert res_direct == ["100.0", "97.5", "95.0"]

    # Ganze Zahlen: Schrittweite 1.0 -> 0 Nachkommastellen
    ticks_int = [95.0, 96.0, 97.0, 98.0, 99.0, 100.0]
    assert format_axis_ticks(ticks_int, step=1.0) == ["95", "96", "97", "98", "99", "100"]

    # Schrittweite 0.25 -> 2 Nachkommastellen für alle Ticks
    ticks_025 = [0.0, 0.25, 0.5, 0.75, 1.0]
    assert format_axis_ticks(ticks_025, step=0.25) == ["0.00", "0.25", "0.50", "0.75", "1.00"]

    # Grosse Zahlen mit Tausendertrenner
    ticks_k = [1000.0, 1500.0, 2000.0]
    assert format_axis_ticks(ticks_k, step=500.0) == ["1'000", "1'500", "2'000"]
    ticks_k_dec = [997.5, 1000.0, 1002.5]
    assert format_axis_ticks(ticks_k_dec, step=2.5) == ["997.5", "1'000.0", "1'002.5"]

    # 3. _format_ch_number Einzelaufruf
    assert _format_ch_number(100.0, step=2.5) == "100.0"
    assert _format_ch_number(97.5, step=2.5) == "97.5"
    assert _format_ch_number(95.0, step=2.5) == "95.0"
    assert _format_ch_number(100.0, step=1.0) == "100"

    # 4. Daten-Chart (Custom Chart Timeseries): SVG-Verifikation
    tsv_ts = (
        "Datum\tIndex\n"
        "2024-01-01\t91.0\n"
        "2024-02-01\t96.2\n"
        "2024-03-01\t101.5\n"
    )
    blk_custom_ts = {
        "id": "blk_test_ts_decimals",
        "type": "custom_chart",
        "chart_type": "timeseries",
        "raw_tsv": tsv_ts,
    }
    svg_custom_ts = generate_custom_chart_svg(blk_custom_ts, embed_fonts=False)
    # Ticks müssen 100.0, 97.5, 95.0 sein
    assert ">100.0<" in svg_custom_ts
    assert ">97.5<" in svg_custom_ts
    assert ">95.0<" in svg_custom_ts
    assert ">100<" not in svg_custom_ts
    assert ">95<" not in svg_custom_ts

    # 5. Daten-Chart (Custom Chart Category Bar horizontal): X-Achsen-Verifikation mit Dezimal-Ticks
    tsv_bar_horiz = (
        "Branche\tPerformance\n"
        "Banken\t0.5\n"
        "Pharma\t1.2\n"
        "Tech\t2.5\n"
    )
    blk_custom_horiz = {
        "id": "blk_test_horiz_decimals",
        "type": "custom_chart",
        "chart_type": "category_bar",
        "orientation": "horizontal",
        "raw_tsv": tsv_bar_horiz,
    }
    svg_custom_horiz = generate_custom_chart_svg(blk_custom_horiz, embed_fonts=False)
    # Ticks müssen einheitlich 1 Dezimalstelle aufweisen (0.0, 0.5, 1.0, 1.5, 2.0, 2.5)
    assert ">0.0<" in svg_custom_horiz
    assert ">0.5<" in svg_custom_horiz
    assert ">1.0<" in svg_custom_horiz
    assert ">2.0<" in svg_custom_horiz
    assert ">0<" not in svg_custom_horiz
    assert ">1<" not in svg_custom_horiz
    assert ">2<" not in svg_custom_horiz

    # 6. DB-Chart Timeseries: SVG-Verifikation mit Leitzinsen (SNB_RATE mit 0.5er Schritten)
    blk_db_chart = {
        "id": "blk_test_db_decimals",
        "type": "db_chart",
        "series": [{"ticker": "SNB_RATE", "chart_type": "line", "label": "SNB"}],
        "start_date": "2022-01-01",
    }
    svg_db_chart = generate_db_chart_svg(blk_db_chart, embed_fonts=False)
    # Alle Ticks müssen mit 1 Dezimalstelle vorliegen (-1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0)
    assert ">0.0<" in svg_db_chart
    assert ">0.5<" in svg_db_chart
    assert ">1.0<" in svg_db_chart
    assert ">1.5<" in svg_db_chart
    assert ">2.0<" in svg_db_chart
    assert ">0<" not in svg_db_chart
    assert ">1<" not in svg_db_chart
    assert ">2<" not in svg_db_chart


def test_compact_legend_and_no_legend():
    """Prüft kompakte Legendeneinträge (Textbreite + kleiner Abstand) und Option 'show_legend=False'."""
    import re
    from services.chart_generator import generate_db_chart_svg

    # 1. Kompakte Legende bei kurzen Labels (SNB, EZB, Fed) in 1 Zeile ohne riesige Lücken
    blk_short = {
        "id": "blk_leg_short",
        "type": "db_chart",
        "layout": "column",
        "start_date": "2022-01-01",
        "series": [
            {"ticker": "SNB_RATE", "chart_type": "step", "label": "SNB"},
            {"ticker": "ECB_RATE", "chart_type": "step", "label": "EZB"},
            {"ticker": "FED_RATE", "chart_type": "step", "label": "Fed"},
        ],
    }
    svg_short = generate_db_chart_svg(blk_short, embed_fonts=False)
    leg_matches = re.findall(r'<text x="([0-9.]+)" y="([0-9.]+)">(SNB|EZB|Fed)</text>', svg_short)
    assert len(leg_matches) == 3
    x_snb, y_snb, _ = leg_matches[0]
    x_ezb, y_ezb, _ = leg_matches[1]
    x_fed, y_fed, _ = leg_matches[2]
    assert float(y_snb) == float(y_ezb) == float(y_fed), "Alle 3 kurzen Einträge müssen in 1 Zeile passen"
    assert float(x_ezb) - float(x_snb) < 120.0, f"Abstand SNB->EZB zu gross: {float(x_ezb) - float(x_snb)}"
    assert float(x_fed) - float(x_ezb) < 120.0, f"Abstand EZB->Fed zu gross: {float(x_fed) - float(x_ezb)}"

    # 2. Längerer mittlerer Text: nachfolgender Eintrag rückt dynamisch nach
    blk_long_mid = {
        "id": "blk_leg_mid",
        "type": "db_chart",
        "layout": "column",
        "start_date": "2022-01-01",
        "series": [
            {"ticker": "SNB_RATE", "chart_type": "step", "label": "SNB"},
            {"ticker": "ECB_RATE", "chart_type": "step", "label": "EZB mit langem Text"},
            {"ticker": "FED_RATE", "chart_type": "step", "label": "Fed"},
        ],
    }
    svg_long_mid = generate_db_chart_svg(blk_long_mid, embed_fonts=False)
    fed_match = re.search(r'<text x="([0-9.]+)" y="([0-9.]+)">Fed</text>', svg_long_mid)
    assert fed_match is not None
    x_fed_shifted = float(fed_match.group(1))
    assert x_fed_shifted > float(x_fed) + 80.0
    assert x_fed_shifted < 500.0

    # 3. Explizite Spaltenanzahl (2 Spalten, 4 Einträge): Spalten sind kompakt & vertikal bündig
    tsv_4 = (
        "Datum\tA\tB\tC\tD\n"
        "2023-01-01\t1\t2\t3\t4\n"
        "2024-01-01\t2\t3\t4\t5\n"
    )
    blk_2col = {
        "id": "blk_leg_2col",
        "type": "custom_chart",
        "chart_type": "timeseries",
        "layout": "column",
        "legend_columns": 2,
        "raw_tsv": tsv_4,
        "series": [
            {"field": "A", "label": "Alpha", "chart_type": "line", "enabled": True},
            {"field": "B", "label": "Beta", "chart_type": "line", "enabled": True},
            {"field": "C", "label": "Gamma", "chart_type": "line", "enabled": True},
            {"field": "D", "label": "Delta", "chart_type": "line", "enabled": True},
        ],
    }
    svg_2col = generate_custom_chart_svg(blk_2col, embed_fonts=False)
    m_alpha = re.search(r'<text x="([0-9.]+)" y="([0-9.]+)">Alpha</text>', svg_2col)
    m_beta = re.search(r'<text x="([0-9.]+)" y="([0-9.]+)">Beta</text>', svg_2col)
    m_gamma = re.search(r'<text x="([0-9.]+)" y="([0-9.]+)">Gamma</text>', svg_2col)
    m_delta = re.search(r'<text x="([0-9.]+)" y="([0-9.]+)">Delta</text>', svg_2col)
    assert m_alpha and m_beta and m_gamma and m_delta
    assert float(m_alpha.group(1)) == float(m_gamma.group(1))
    assert float(m_beta.group(1)) == float(m_delta.group(1))
    assert float(m_beta.group(1)) - float(m_alpha.group(1)) < 140.0

    # 4. Option 'show_legend=False' blendet Legende komplett aus & spart Höhe
    blk_no_leg_db = dict(blk_short, show_legend=False)
    svg_no_leg_db = generate_db_chart_svg(blk_no_leg_db, embed_fonts=False)
    assert "SNB" not in svg_no_leg_db
    assert "EZB" not in svg_no_leg_db
    assert "Fed" not in svg_no_leg_db
    h_with = int(re.search(r'height="([0-9]+)"', svg_short).group(1))
    h_without = int(re.search(r'height="([0-9]+)"', svg_no_leg_db).group(1))
    assert h_without < h_with

    # Auch für Custom Category Bar und Doughnut
    blk_cat_no_leg = {
        "id": "blk_cat_noleg",
        "type": "custom_chart",
        "chart_type": "category_bar",
        "raw_tsv": "Kat\tWert1\tWert2\nA\t10\t20\nB\t15\t25\n",
        "show_legend": False,
    }
    svg_cat_no_leg = generate_custom_chart_svg(blk_cat_no_leg, embed_fonts=False)
    assert "Wert1" not in svg_cat_no_leg
    assert "Wert2" not in svg_cat_no_leg

    blk_donut_no_leg = {
        "id": "blk_donut_noleg",
        "type": "custom_chart",
        "chart_type": "doughnut",
        "raw_tsv": "Kat\tAnteil\nAktien\t60\nObligationen\t40\n",
        "show_legend": False,
    }
    svg_donut_no_leg = generate_custom_chart_svg(blk_donut_no_leg, embed_fonts=False)
    assert "Aktien" not in svg_donut_no_leg
    assert "Obligationen" not in svg_donut_no_leg


def test_dual_y_axis_and_manual_scale():
    """Prüft linke/rechte Y-Achse sowie manuelle min/max/step-Skalierung bei Zeitreihencharts."""
    from services.chart_common import _resolve_axis_scale
    from services.custom_chart_generator import _compute_custom_chart_cache_key

    # 1. Tick-Berechnung mit manuellen Grenzen & Schrittweite
    ticks, y_min, y_max, y_step = _resolve_axis_scale(1.2, 4.8, {"min": 0, "max": 6, "step": 2})
    assert ticks == [0.0, 2.0, 4.0, 6.0]
    assert y_min == 0.0
    assert y_max == 6.0
    assert y_step == 2.0

    # Nur min gesetzt
    ticks_min, y_min2, y_max2, _ = _resolve_axis_scale(1.2, 4.8, {"min": 0})
    assert y_min2 == 0.0
    assert ticks_min[0] == 0.0
    assert y_max2 >= 4.8

    # Ungültiges min >= max fällt sauber auf Rohdaten zurück
    ticks_inv, y_min_inv, y_max_inv, _ = _resolve_axis_scale(10.0, 20.0, {"min": 50, "max": 10})
    assert y_min_inv <= 10.0
    assert y_max_inv >= 20.0
    assert len(ticks_inv) >= 2

    # 2. Custom Timeseries Chart mit zwei unterschiedlichen Skalen (SMI vs. Leitzins %)
    tsv_dual = (
        "Datum\tSMI\tSNB\n"
        "2024-01-01\t11000\t1.75\n"
        "2024-06-01\t12000\t1.25\n"
        "2024-12-01\t11500\t0.50\n"
    )
    blk_dual = {
        "id": "blk_dual_y",
        "type": "custom_chart",
        "chart_type": "timeseries",
        "raw_tsv": tsv_dual,
        "series": [
            {"field": "SMI", "label": "SMI", "chart_type": "line", "enabled": True, "y_axis": "left"},
            {"field": "SNB", "label": "SNB (r. Achse)", "chart_type": "step", "enabled": True, "y_axis": "right"},
        ],
        "y_axis_left": {"min": 10000, "max": 13000, "step": 1000},
        "y_axis_right": {"min": 0, "max": 2.5, "step": 0.5},
    }
    svg_dual = generate_custom_chart_svg(blk_dual, embed_fonts=False)
    assert "<clipPath id=\"lukb-plot-clip\">" in svg_dual
    assert 'text-anchor="start"' in svg_dual  # rechte Y-Achsen-Labels
    assert "10&#x27;000" in svg_dual
    assert "13&#x27;000" in svg_dual
    assert "2.5" in svg_dual
    assert "SNB (r. Achse)" in svg_dual

    # Cache-Key ändert sich bei Änderung der Y-Achse oder Skalierung
    key_1 = _compute_custom_chart_cache_key(blk_dual, embed_fonts=False)
    blk_dual_mod = dict(blk_dual, y_axis_right={"min": 0, "max": 3.0, "step": 0.5})
    key_2 = _compute_custom_chart_cache_key(blk_dual_mod, embed_fonts=False)
    assert key_1 != key_2

    # 3. Schema-Validierung für CustomChartBlock und DbChartBlock
    parsed_custom = parse_block(blk_dual)
    assert isinstance(parsed_custom, CustomChartBlock)
    assert parsed_custom.series[1].y_axis == "right"
    assert parsed_custom.y_axis_left.min == 10000.0
    assert parsed_custom.y_axis_right.step == 0.5

    parsed_db = parse_block(
        {
            "id": "blk_db_dual",
            "type": "db_chart",
            "series": [
                {"ticker": "SMI", "chart_type": "line", "y_axis": "left"},
                {"ticker": "SNB_RATE", "chart_type": "step", "y_axis": "right", "label": "SNB (r. Achse)"},
            ],
            "y_axis_left": {"min": 9000, "max": 13000, "step": 1000},
            "y_axis_right": {"min": 0, "max": 3, "step": 1},
        }
    )
    assert parsed_db.series[1].y_axis == "right"
    assert parsed_db.y_axis_right.max == 3.0

    # 4. Auto-Modus auf rechter Y-Achse richtet Pretty-Breaks exakt auf die linken Gridlines aus
    blk_dual_auto = {
        "id": "blk_dual_auto",
        "type": "custom_chart",
        "chart_type": "timeseries",
        "raw_tsv": tsv_dual,
        "series": [
            {"field": "SMI", "label": "SMI", "chart_type": "line", "enabled": True, "y_axis": "left"},
            {"field": "SNB", "label": "SNB (r. Achse)", "chart_type": "step", "enabled": True, "y_axis": "right"},
        ],
    }
    svg_auto = generate_custom_chart_svg(blk_dual_auto, embed_fonts=False)
    import html as _html
    import json as _json
    import re as _re
    m_meta = _re.search(r'data-axes-meta="([^"]+)"', svg_auto)
    assert m_meta is not None
    axes_meta = _json.loads(_html.unescape(m_meta.group(1)))
    assert axes_meta["left"] is not None and axes_meta["right"] is not None
    left_n_int = round((axes_meta["left"]["max"] - axes_meta["left"]["min"]) / axes_meta["left"]["step"])
    right_n_int = round((axes_meta["right"]["max"] - axes_meta["right"]["min"]) / axes_meta["right"]["step"])
    assert left_n_int == right_n_int


if __name__ == "__main__":
    test_parsing_helpers()
    test_auto_detection()
    test_doughnut_and_pie_svg()
    test_category_bar_svg()
    test_timeseries_svg()
    test_chart_height_scaling()
    test_pydantic_schema_validation()
    test_dual_output_typst_and_web_rendering()
    test_custom_chart_svg_cache()
    test_consistent_axis_tick_decimals()
    test_compact_legend_and_no_legend()
    print("ALL CUSTOM CHART TESTS PASSED SUCCESSFULLY!")
