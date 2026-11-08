"""
tests/test_portal_publisher.py
==============================
Tests für den entkoppelten Static Site Generator (services/portal_publisher.py).
Prüft:
- Publizieren eines neuen Artikels (HTML + PDF + Portal-Katalog + Suche)
- Überschreiben eines publizierten Artikels
- Zurückziehen / Entfernen (Unpublish)
- Erzeugen des Posit Connect Deployment Bundles (.tar.gz)
"""

from __future__ import annotations

import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

# Projektwurzel in den Suchpfad aufnehmen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas.article import ArticleDocument, ArticleMetadata, AuthorItem, CalloutBlock, RichTextBlock
from services.portal_publisher import (
    create_connect_bundle,
    publish_article,
    rebuild_full_portal,
    unpublish_article,
)


def _build_test_doc(doc_id: str, title: str, status: str = "published") -> ArticleDocument:
    return ArticleDocument(
        id=doc_id,
        template_id="investment_focus",
        status=status,
        metadata=ArticleMetadata(
            title=title,
            subtitle="Strategische Einordnung",
            lead="Dies ist ein einleitender Lead-Absatz für den Testartikel.",
            category="Markteinschätzung & Positionierung",
            publication_date="2026-11-08",
            authors=[
                AuthorItem(name="Marc Häfliger", role="Investment Stratege"),
                AuthorItem(name="Björn Eberhardt", role="Leiter Investment Office"),
            ],
            disclaimer="LUKB Disclaimer Test",
        ),
        blocks=[
            CalloutBlock(
                title="Kernaussagen",
                text="- Erste Erkenntnis\n- Zweite Schlussfolgerung",
            ),
            RichTextBlock(
                html="<h2>Kapitel 1</h2><p>Detaillierter Fließtext für den statischen Portaltest.</p>",
            ),
        ],
    )


def test_portal_publisher_flow() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dist = Path(tmp_dir_str) / "portal_dist"
        tmp_dist.mkdir()

        # -------------------------------------------------------------
        # 1. Ersten Artikel publizieren
        # -------------------------------------------------------------
        doc1 = _build_test_doc("art-001", "US-Midterms: Demokraten sichern Mehrheit")
        res1 = publish_article(doc1, output_dir=tmp_dist)

        assert res1["success"] is True
        assert res1["action"] == "published"
        assert res1["total_published"] == 1
        slug1 = res1["slug"]

        # Prüfe generierte Dateien
        article_dir = tmp_dist / "articles" / slug1
        assert article_dir.exists(), "Artikelverzeichnis muss existieren"
        assert (article_dir / "index.html").exists(), "Artikel index.html muss existieren"
        assert (article_dir / f"{slug1}.pdf").exists(), "Typst-PDF muss generiert sein"

        # Prüfe Portal-Root-Dateien
        assert (tmp_dist / "index.html").exists(), "Portal-Index muss existieren"
        assert (tmp_dist / "search-index.json").exists(), "Such-Index muss existieren"
        assert (tmp_dist / "assets" / "portal.css").exists(), "CSS muss kopiert sein"
        assert (tmp_dist / "assets" / "portal.js").exists(), "JS muss kopiert sein"

        # Prüfe Portal-Index HTML Inhalt
        portal_html = (tmp_dist / "index.html").read_text(encoding="utf-8")
        assert "US-Midterms: Demokraten sichern Mehrheit" in portal_html
        assert "Marc Häfliger" in portal_html
        assert f"articles/{slug1}/index.html" in portal_html
        assert f"articles/{slug1}/{slug1}.pdf" in portal_html

        # Prüfe Artikel-HTML (mit Rücklink & PDF-Download)
        art_html = (article_dir / "index.html").read_text(encoding="utf-8")
        assert "Zurück zur Publikations-Übersicht" in art_html
        assert f"{slug1}.pdf" in art_html

        # Prüfe Suchindex
        search_idx = json.loads((tmp_dist / "search-index.json").read_text(encoding="utf-8"))
        assert len(search_idx) == 1
        assert search_idx[0]["id"] == "art-001"
        assert search_idx[0]["title"] == "US-Midterms: Demokraten sichern Mehrheit"

        # -------------------------------------------------------------
        # 2. Zweites Dokument publizieren
        # -------------------------------------------------------------
        doc2 = _build_test_doc("art-002", "Zinsentscheid der Schweizerischen Nationalbank")
        res2 = publish_article(doc2, output_dir=tmp_dist)
        assert res2["success"] is True
        assert res2["total_published"] == 2

        search_idx2 = json.loads((tmp_dist / "search-index.json").read_text(encoding="utf-8"))
        assert len(search_idx2) == 2

        # -------------------------------------------------------------
        # 3. Artikel 1 überschreiben / aktualisieren
        # -------------------------------------------------------------
        doc1_updated = _build_test_doc("art-001", "US-Midterms: Aktualisierte Analyse")
        doc1_updated.metadata.lead = "Neuer aktualisierter Lead-Text nach Stimmauszählung."
        res1_update = publish_article(doc1_updated, output_dir=tmp_dist)

        assert res1_update["success"] is True
        assert res1_update["total_published"] == 2
        slug1_updated = res1_update["slug"]

        portal_html_updated = (tmp_dist / "index.html").read_text(encoding="utf-8")
        assert "US-Midterms: Aktualisierte Analyse" in portal_html_updated
        assert "US-Midterms: Demokraten sichern Mehrheit" not in portal_html_updated

        # -------------------------------------------------------------
        # 4. Artikel 1 entfernen (Unpublish)
        # -------------------------------------------------------------
        unpub_res = unpublish_article("art-001", output_dir=tmp_dist)
        assert unpub_res["success"] is True
        assert unpub_res["action"] == "unpublished"
        assert unpub_res["total_published"] == 1

        # Verzeichnis von doc1 muss gelöscht sein
        assert not (tmp_dist / "articles" / slug1_updated).exists()

        # doc2 muss weiter existieren
        portal_html_after_unpub = (tmp_dist / "index.html").read_text(encoding="utf-8")
        assert "Zinsentscheid der Schweizerischen Nationalbank" in portal_html_after_unpub
        assert "US-Midterms: Aktualisierte Analyse" not in portal_html_after_unpub

        search_idx_after = json.loads((tmp_dist / "search-index.json").read_text(encoding="utf-8"))
        assert len(search_idx_after) == 1
        assert search_idx_after[0]["id"] == "art-002"

        # -------------------------------------------------------------
        # 5. Connect Bundle schnüren
        # -------------------------------------------------------------
        bundle_file = Path(tmp_dir_str) / "test_connect_bundle.tar.gz"
        created_bundle = create_connect_bundle(output_dir=tmp_dist, bundle_path=bundle_file)
        assert created_bundle.exists()
        assert created_bundle.stat().st_size > 0

        # Prüfe Archiv-Inhalt
        with tarfile.open(created_bundle, "r:gz") as tar:
            names = tar.getnames()
            assert "index.html" in names
            assert "search-index.json" in names
            assert any(n.startswith("assets/portal.css") for n in names)
            assert any(n.startswith(f"articles/{res2['slug']}/index.html") for n in names)
            assert any(n.startswith(f"articles/{res2['slug']}/{res2['slug']}.pdf") for n in names)

        print("All portal publisher tests passed successfully!")


if __name__ == "__main__":
    test_portal_publisher_flow()
