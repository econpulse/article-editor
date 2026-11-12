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
            assert "manifest.json" in names
            assert "search-index.json" in names
            assert any(n.startswith("assets/portal.css") for n in names)
            assert any(n.startswith(f"articles/{res2['slug']}/index.html") for n in names)
            assert any(n.startswith(f"articles/{res2['slug']}/{res2['slug']}.pdf") for n in names)

        # -------------------------------------------------------------
        # 6. Bundle-Erstellung bei leerem/neuem Verzeichnis (Auto-Recovery)
        # -------------------------------------------------------------
        empty_dist = Path(tmp_dir_str) / "empty_dist"
        empty_bundle_file = Path(tmp_dir_str) / "empty_bundle.tar.gz"
        empty_bundle = create_connect_bundle(output_dir=empty_dist, bundle_path=empty_bundle_file)
        assert empty_bundle.exists()
        assert empty_bundle.stat().st_size > 0
        with tarfile.open(empty_bundle, "r:gz") as tar:
            empty_names = tar.getnames()
            assert "index.html" in empty_names
            assert "manifest.json" in empty_names

        # -------------------------------------------------------------
        # 7. Prüfe App Download-Button Konfiguration (Import datetime etc.)
        # -------------------------------------------------------------
        import app
        from datetime import datetime
        assert hasattr(app, "datetime"), "app.py muss datetime importiert haben"

        print("All portal publisher tests passed successfully!")


def test_published_snapshots_and_recovery() -> None:
    """
    Testet das revisionssichere Versionierungs- und Snapshot-System in MSSQL:
    1. Publikation von Version 1 (mit Tippfehler im Titel)
    2. Publikation von Version 2 (Korrektur)
    3. Überprüfung der Versionenhistorie (beide Versionen permanent gespeichert)
    4. Simulation eines Posit-Connect-Redeployments (komplettes Löschen des lokalen Portalordners)
    5. Bitgenaue Wiederherstellung aus den MSSQL-Snapshots ohne Neuberechnung
    6. Rollback-Test auf Version 1
    """
    from datetime import date, datetime
    from database.repository import (
        get_active_published_snapshots,
        get_article_snapshot_history,
        query_timeseries_data,
        rollback_to_snapshot,
    )
    from services.portal_publisher import restore_portal_from_snapshots

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        dist_dir = Path(tmp_dir_str) / "portal_dist"
        dist_dir.mkdir()

        import uuid
        art_id = f"test-snap-{uuid.uuid4().hex[:8]}"
        # 1. Version 1 publizieren (mit Typo: 'Merheit')
        doc_v1 = _build_test_doc(art_id, "US-Midterms: Demokraten sichern Merheit")
        res1 = publish_article(doc_v1, output_dir=dist_dir, user="Author A", change_note="Initialversion mit Typo")
        assert res1["success"] is True
        assert res1["version"] == 1
        slug_v1 = res1["slug"]

        # 2. Version 2 publizieren (Typo behoben: 'Mehrheit')
        doc_v2 = _build_test_doc(art_id, "US-Midterms: Demokraten sichern Mehrheit")
        res2 = publish_article(doc_v2, output_dir=dist_dir, user="Senior Editor B", change_note="Tippfehler behoben")
        assert res2["success"] is True
        assert res2["version"] == 2
        slug_v2 = res2["slug"]

        # 3. Revisionshistorie aus MSSQL prüfen
        history = get_article_snapshot_history(art_id)
        assert len(history) == 2, "Es müssen exakt 2 Versionen in der Historie liegen"
        assert history[0]["version"] == 2
        assert history[0]["is_active"] is True
        assert history[0]["title"] == "US-Midterms: Demokraten sichern Mehrheit"
        assert history[0]["change_note"] == "Tippfehler behoben"

        assert history[1]["version"] == 1
        assert history[1]["is_active"] is False
        assert history[1]["title"] == "US-Midterms: Demokraten sichern Merheit"

        # 4. Simulation eines Neu-Deployments auf Posit Connect:
        # Lokaler dist_dir wird restlos gelöscht!
        shutil.rmtree(dist_dir)
        assert not dist_dir.exists(), "Portal-Verzeichnis ist nach Redeployment gelöscht"

        # 5. Schnelle Wiederherstellung aus MSSQL-Snapshots
        restore_res = restore_portal_from_snapshots(output_dir=dist_dir)
        assert restore_res["success"] is True
        assert restore_res["restored_count"] >= 1

        # Prüfe ob Version 2 wiederhergestellt wurde
        assert (dist_dir / "index.html").exists()
        assert (dist_dir / "articles" / slug_v2 / "index.html").exists()
        assert (dist_dir / "articles" / slug_v2 / f"{slug_v2}.pdf").exists()
        restored_html = (dist_dir / "articles" / slug_v2 / "index.html").read_text(encoding="utf-8")
        assert "US-Midterms: Demokraten sichern Mehrheit" in restored_html

        # 6. Rollback auf Version 1 testen
        rb_res = rollback_to_snapshot(art_id, version=1, user="Admin")
        assert rb_res["success"] is True
        assert rb_res["version"] == 1

        # Historie nach Rollback prüfen
        history_after_rb = get_article_snapshot_history(art_id)
        assert history_after_rb[0]["is_active"] is False  # Version 2 ist jetzt inaktiv
        assert history_after_rb[1]["is_active"] is True   # Version 1 ist jetzt aktiv

        # 7. Zeitreihen-Stichtagsbegrenzung (end_date) prüfen
        test_ts = query_timeseries_data(["SNB_RATE"], start_date="2022-01-01", end_date="2023-01-01")
        if "SNB_RATE" in test_ts and test_ts["SNB_RATE"]["points"]:
            pts = test_ts["SNB_RATE"]["points"]
            assert all(d <= datetime(2023, 1, 1).date() for d, _ in pts), "Keine Punkte nach end_date erlaubt"

        print("Published snapshots and recovery tests passed successfully!")


if __name__ == "__main__":
    test_portal_publisher_flow()
    test_published_snapshots_and_recovery()
