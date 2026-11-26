"""Tests für die Konvertierung von Excel-HTML-Zwischenablage zu Vektor-SVG."""

from __future__ import annotations

import asyncio
import json

import app as app_module
from services.excel_html_to_svg import convert_excel_html_to_svg, is_excel_html_table

SAMPLE_EXCEL_HTML = """
<html xmlns:x="urn:schemas-microsoft-com:office:excel">
<head>
<style>
<!--
td { font-family: Calibri, sans-serif; font-size: 10.0pt; }
.xl65 {
  color: #FFFFFF;
  font-weight: 700;
  background: #002855;
  text-align: left;
  border-bottom: 1.0pt solid #002855;
}
.xl66 {
  color: #1A2433;
  text-align: right;
  background: #F4F7FA;
  border-bottom: .5pt solid #D6DEE8;
}
-->
</style>
</head>
<body>
<table>
  <tr>
    <td class="xl65" colspan="2">Kennzahlen #1 &amp; *Werte* [CHF]</td>
  </tr>
  <tr>
    <td class="xl66" style="text-align:left;"><b>SMI</b></td>
    <td class="xl66">12'450.5</td>
  </tr>
</table>
</body>
</html>
"""


def test_is_excel_html_table_detection() -> None:
    assert is_excel_html_table(SAMPLE_EXCEL_HTML) is True
    assert is_excel_html_table("<div>Kein Tabelleninhalt</div>") is False
    assert is_excel_html_table('<table><tr><td><img src="file:///tmp/chart.png"/></td></tr></table>') is False


def test_convert_excel_html_to_svg_produces_valid_svg() -> None:
    svg = convert_excel_html_to_svg(SAMPLE_EXCEL_HTML)
    assert svg is not None
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "viewBox=" in svg


def test_excel_html_to_svg_endpoint() -> None:
    route = next(
        (r for r in app_module.app.starlette_app.routes if getattr(r, "path", None) == "/api/excel-html-to-svg"),
        None,
    )
    assert route is not None

    class _DummyReq:
        def __init__(self, body: dict) -> None:
            self._body = body

        async def json(self) -> dict:
            return self._body

    resp = asyncio.run(route.endpoint(_DummyReq({"html": SAMPLE_EXCEL_HTML})))
    assert resp.status_code == 200
    data = json.loads(resp.body.decode("utf-8"))
    assert data["ok"] is True
    assert "<svg" in data["svg"]

    resp_empty = asyncio.run(route.endpoint(_DummyReq({"html": "<div>Nur Text</div>"})))
    assert resp_empty.status_code == 200
    assert json.loads(resp_empty.body.decode("utf-8"))["ok"] is False
