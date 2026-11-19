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
from services.chart_generator import _estimate_label_width_px
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
    print("ALL CUSTOM CHART TESTS PASSED SUCCESSFULLY!")
