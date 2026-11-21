"""
scripts/benchmark_stage0.py
===========================
Reproduzierbare Ausgangsmessung (Etappe 0) für einen Referenzartikel mit 72 Inhaltsblöcken.
Misst lokal die serverseitigen Kernmetriken:
- Autosave-Speicherdauer (SQL-Write)
- PDF-Vorschau (Typst-Renderzeit & Base64-Payload-Grösse)
- Web-Vorschau (HTML5-Renderzeit & Payload-Grösse)
- Portal-Bundle-Packzeit & .tar.gz-Grösse (ohne Duplikate)

Hinweis: Browser-/Citrix-Metriken (Öffnen bis Eingabebereitschaft, Eingabeverzögerung,
erste sichtbare PDF-Seite in PDF.js sowie 1 vs. 5 parallele Sitzungen) werden in der
isolierten Posit-Connect-App in Citrix nach demselben Protokoll ergänzt.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database.repository import delete_article, init_db_and_seed, save_article
from schemas.article import ArticleDocument, ArticleMetadata, AuthorItem
from services.portal_publisher import create_connect_bundle, publish_article
from services.renderer import render_preview_pdf_base64, render_web_html


def build_reference_article_72_blocks(article_id: str) -> ArticleDocument:
    """Erstellt einen synthetischen Referenzartikel mit exakt 72 Inhaltsblöcken (~6 PDF-Seiten)."""
    blocks: list[dict] = []
    for section in range(1, 13):
        blocks.append(
            {
                "id": f"blk_h_{section}",
                "type": "heading",
                "level": 2,
                "text": f"{section}. Marktkommentar & Positionierung",
            }
        )
        blocks.append(
            {
                "id": f"blk_rt1_{section}",
                "type": "richtext",
                "html": (
                    "<p>Die wirtschaftliche Dynamik zeigt im laufenden Quartal eine robuste "
                    "Binnennachfrage bei gleichzeitig nachlassendem Preisdruck. Für die "
                    "Portfolioallokation bedeutet dies eine selektive Übergewichtung von "
                    "Qualitätsaktien sowie eine neutrale Duration im Anleihensegment.</p>"
                ),
            }
        )
        blocks.append(
            {
                "id": f"blk_rt2_{section}",
                "type": "richtext",
                "html": (
                    "<p>Im Vergleich zum Vormonat haben sich die Kreditspreads stabilisiert. "
                    "Währungsseitig bleibt der Schweizer Franken als defensiver Anker "
                    "gefragt, während zyklische Währungen stärker auf Konjunkturdaten reagieren.</p>"
                ),
            }
        )
        if section % 3 == 1:
            blocks.append(
                {
                    "id": f"blk_co_{section}",
                    "type": "callout",
                    "title": f"Kernaussage Abschnitt {section}",
                    "html": "<ul><li>Selektive Chancen bei Qualitätswerten</li><li>Solide Zinsrenditen im Investment-Grade-Bereich</li></ul>",
                }
            )
        elif section % 3 == 2:
            blocks.append(
                {
                    "id": f"blk_tbl_{section}",
                    "type": "table",
                    "title": f"Kennzahlen-Übersicht {section}",
                    "source": "Quelle: LUKB Investment Office",
                    "layout": "column",
                    "headers": ["Anlageklasse", "Gewichtung", "Einschätzung"],
                    "rows": [
                        {"Anlageklasse": "Aktien Schweiz", "Gewichtung": "Übergewichtet", "Einschätzung": "+"},
                        {"Anlageklasse": "Aktien Global", "Gewichtung": "Neutral", "Einschätzung": "="},
                        {"Anlageklasse": "Obligationen CHF", "Gewichtung": "Neutral", "Einschätzung": "="},
                    ],
                }
            )
        else:
            blocks.append(
                {
                    "id": f"blk_chart_{section}",
                    "type": "db_chart",
                    "title": f"Leitzinsvergleich Abschnitt {section}",
                    "subtitle": "In Prozent p.a.",
                    "source": "Quelle: SNB, EZB",
                    "layout": "column",
                    "chart_height_mm": 36,
                    "start_date": "2022-01-01",
                    "rebasing": "none",
                    "palette": "lukb_classic",
                    "show_legend": True,
                    "series": [
                        {"ticker": "SNB_RATE", "chart_type": "line", "chart_types": ["line"], "label": "SNB"},
                        {"ticker": "ECB_RATE", "chart_type": "line", "chart_types": ["line"], "label": "EZB"},
                    ],
                }
            )
        blocks.append(
            {
                "id": f"blk_rt3_{section}",
                "type": "richtext",
                "html": "<p>Weitere Details zur taktischen Umsetzung folgen im monatlichen Anlageausschuss.</p>",
            }
        )
        blocks.append(
            {
                "id": f"blk_div_{section}",
                "type": "divider",
                "style": "solid",
            }
        )

    assert len(blocks) == 72, f"Erwartet 72 Blöcke, erhalten: {len(blocks)}"
    return ArticleDocument(
        id=article_id,
        template_id="investment_focus",
        status="draft",
        metadata=ArticleMetadata(
            title="Referenzartikel Etappe 0 — Makro & Allokation",
            subtitle="Vergleichsmessung mit 72 Inhaltsblöcken",
            lead="Strukturierter Referenzartikel für reproduzierbare Ausgangs- und Verlaufsmessungen.",
            category="Markteinschätzung & Positionierung",
            publication_date="2026-11-21",
            authors=[AuthorItem(name="Benchmark Runner", role="Investment Office")],
            disclaimer="Nur für interne Benchmark-Tests.",
        ),
        blocks=blocks,
    )


def run_benchmark() -> dict:
    init_db_and_seed()
    art_id = f"bench_stage0_{uuid.uuid4().hex[:8]}"
    doc = build_reference_article_72_blocks(art_id)

    try:
        # 1. Autosave (Initial + Update)
        t0 = time.perf_counter()
        save_res = save_article(doc, user="Benchmark", create_revision=False)
        t_save_initial_ms = (time.perf_counter() - t0) * 1000.0

        saved_doc = save_res["doc_obj"]
        saved_doc.blocks[1]["html"] = "<p>Aktualisierter Absatz für Autosave-Messung.</p>"
        t0 = time.perf_counter()
        save_article(saved_doc, user="Benchmark", base_doc=doc, create_revision=False)
        t_save_update_ms = (time.perf_counter() - t0) * 1000.0

        # 2. PDF-Vorschau (Typst)
        t0 = time.perf_counter()
        pdf_b64 = render_preview_pdf_base64(saved_doc)
        t_pdf_ms = (time.perf_counter() - t0) * 1000.0
        pdf_b64_bytes = len(pdf_b64.encode("ascii")) if pdf_b64 else 0

        # 3. Web-HTML-Vorschau
        t0 = time.perf_counter()
        web_html = render_web_html(saved_doc)
        t_web_ms = (time.perf_counter() - t0) * 1000.0
        web_html_bytes = len(web_html.encode("utf-8")) if web_html else 0

        # 4. Portal-Bundle-Packzeit & Grösse
        with tempfile.TemporaryDirectory() as tmp_dir:
            dist_dir = Path(tmp_dir) / "portal_dist"
            dist_dir.mkdir()
            publish_article(saved_doc, output_dir=dist_dir, sync_with_db=False)
            bundle_path = Path(tmp_dir) / "bench_bundle.tar.gz"
            t0 = time.perf_counter()
            create_connect_bundle(output_dir=dist_dir, bundle_path=bundle_path)
            t_bundle_ms = (time.perf_counter() - t0) * 1000.0
            bundle_bytes = bundle_path.stat().st_size

        return {
            "blocks_count": len(doc.blocks),
            "autosave_initial_ms": round(t_save_initial_ms, 1),
            "autosave_update_ms": round(t_save_update_ms, 1),
            "pdf_preview_ms": round(t_pdf_ms, 1),
            "pdf_preview_base64_bytes": pdf_b64_bytes,
            "web_preview_ms": round(t_web_ms, 1),
            "web_preview_html_bytes": web_html_bytes,
            "bundle_pack_ms": round(t_bundle_ms, 1),
            "bundle_tar_gz_bytes": bundle_bytes,
        }
    finally:
        delete_article(art_id, force=True)


if __name__ == "__main__":
    metrics = run_benchmark()
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
