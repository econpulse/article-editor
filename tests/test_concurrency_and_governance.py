"""
Tests für Punkt 1 (Multi-User-Robustheit & Governance):
- Optimistic Concurrency Control (`version`-Spalte + atomares `WHERE version = ...` + Retry)
- 3-Wege-Merge bei gleichzeitiger Bearbeitung durch zwei Autoren
- Serverseitige Status-Absicherung (`preserve_db_status=True`)
- Thread-sicheres, atomares Portal-Publishing (`_PORTAL_PUBLISH_LOCK`)
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database.repository import (
    create_new_article,
    delete_article,
    get_article,
    init_db_and_seed,
    save_article,
)
from schemas.article import ArticleDocument, ArticleMetadata
from services.portal_publisher import publish_article


def test_optimistic_version_increment_and_concurrent_merge():
    init_db_and_seed()
    doc = create_new_article(template_id="investment_focus", user="Autor A")
    assert doc.version == 1

    # Autor A und Autor B laden denselben Ausgangsstand (v1)
    base_a = get_article(doc.id)
    base_b = get_article(doc.id)
    assert base_a is not None and base_b is not None
    assert base_a.version == 1

    # Autor A ändert den Titel und fügt einen Block hinzu -> v2
    doc_a = base_a.model_copy(deep=True)
    doc_a.metadata.title = "Titel von Autor A"
    doc_a.blocks.append({"id": "blk_a_only", "type": "richtext", "html": "<p>Text A</p>"})
    res_a = save_article(doc_a, user="Autor A", base_doc=base_a)
    assert res_a["version"] == 2
    assert res_a["merged"] is False

    # Autor B ändert unabhängig das Lead und fügt einen anderen Block hinzu (auf Basis v1) -> Merge -> v3
    doc_b = base_b.model_copy(deep=True)
    doc_b.metadata.lead = "Lead von Autor B"
    doc_b.blocks.append({"id": "blk_b_only", "type": "richtext", "html": "<p>Text B</p>"})
    res_b = save_article(doc_b, user="Autor B", base_doc=base_b)
    assert res_b["merged"] is True
    assert res_b["version"] == 3

    final_doc = get_article(doc.id)
    assert final_doc is not None
    assert final_doc.version == 3
    assert final_doc.metadata.title == "Titel von Autor A"
    assert final_doc.metadata.lead == "Lead von Autor B"
    block_ids = {b["id"] for b in final_doc.blocks}
    assert "blk_a_only" in block_ids
    assert "blk_b_only" in block_ids

    assert delete_article(doc.id, force=True) is True


def test_preserve_db_status_blocks_client_status_escalation():
    init_db_and_seed()

    # 1. Neuer Artikel darf über preserve_db_status=True nicht direkt als 'published' angelegt werden
    new_id = str(uuid.uuid4())
    forged_new = ArticleDocument(
        id=new_id,
        status="published",
        metadata=ArticleMetadata(title="Status-Test Neu"),
        blocks=[],
    )
    res_new = save_article(forged_new, user="Normaler Autor", preserve_db_status=True)
    assert res_new["article"]["status"] == "draft"

    # 2. Bestehender Draft darf über Autosave (preserve_db_status=True) nicht auf 'published' gesetzt werden
    loaded = get_article(new_id)
    assert loaded is not None
    assert loaded.status == "draft"

    tampered = loaded.model_copy(deep=True)
    tampered.status = "published"
    tampered.metadata.title = "Geänderter Titel"
    res_upd = save_article(tampered, user="Normaler Autor", base_doc=loaded, preserve_db_status=True)
    assert res_upd["article"]["status"] == "draft"
    assert res_upd["article"]["metadata"]["title"] == "Geänderter Titel"

    reloaded = get_article(new_id)
    assert reloaded is not None
    assert reloaded.status == "draft"
    assert reloaded.metadata.title == "Geänderter Titel"

    assert delete_article(new_id, force=True) is True


def test_concurrent_portal_publish_is_thread_safe(tmp_path: Path):
    init_db_and_seed()
    d1 = ArticleDocument(
        id=f"pub_test_{uuid.uuid4().hex[:8]}",
        status="published",
        metadata=ArticleMetadata(title="Parallele Publikation Eins", publication_date="2026-11-21"),
        blocks=[{"id": "b1", "type": "richtext", "html": "<p>Inhalt Eins</p>"}],
    )
    d2 = ArticleDocument(
        id=f"pub_test_{uuid.uuid4().hex[:8]}",
        status="published",
        metadata=ArticleMetadata(title="Parallele Publikation Zwei", publication_date="2026-11-21"),
        blocks=[{"id": "b2", "type": "richtext", "html": "<p>Inhalt Zwei</p>"}],
    )

    errors: list[Exception] = []
    results: list[dict] = []

    def _run_pub(doc: ArticleDocument):
        try:
            res = publish_article(doc, output_dir=tmp_path, user="Editor", sync_with_db=False)
            results.append(res)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_run_pub, args=(d1,))
    t2 = threading.Thread(target=_run_pub, args=(d2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert len(results) == 2
    assert all(r["success"] for r in results)

    manifest = json.loads((tmp_path / "portal-manifest.json").read_text(encoding="utf-8"))
    assert d1.id in manifest["articles"]
    assert d2.id in manifest["articles"]
    assert not list(tmp_path.rglob("*.tmp"))
