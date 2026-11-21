"""
Tests für Etappe 2 (Freigabe, Publikationsaufträge, Connect-Fehlerfälle, Rückzug & Content-Hash).
"""

from __future__ import annotations

import shutil
import sys
import tarfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config
import services.publication_service as pub_svc
from database.connection import get_db_session
from database.models import PublishedSnapshotModel
from database.repository import (
    create_new_article,
    delete_article,
    get_article,
    get_published_sync_status,
    init_db_and_seed,
    save_article,
)


def test_four_eyes_and_failed_then_retry_keeps_live_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db_and_seed()
    author = f"autor.{uuid.uuid4().hex[:6]}@lukb.ch"
    reviewer = f"reviewer.{uuid.uuid4().hex[:6]}@lukb.ch"

    monkeypatch.setattr(config, "FOUR_EYES_TEMPLATES", ["investment_focus"])
    monkeypatch.setattr(pub_svc, "is_connect_configured", lambda: True)

    doc = create_new_article(template_id="investment_focus", user=author)
    try:
        # 1. Einreichen -> speichert konkrete Revision
        sub1 = pub_svc.submit_article_for_review(doc.id, author)
        assert sub1["success"] is True
        rev1_id = sub1["revision_id"]

        # 2. Vier-Augen-Regel: Autor darf nicht selbst freigeben
        self_app = pub_svc.approve_article_revision(doc.id, rev1_id, author)
        assert self_app["success"] is False
        assert "Vier-Augen-Regel" in self_app["error"]

        # 3. Zweites Konto gibt Revision frei
        app1 = pub_svc.approve_article_revision(doc.id, rev1_id, reviewer)
        assert app1["success"] is True

        # 4. Erste Publikation gelingt auf Connect
        monkeypatch.setattr(
            pub_svc,
            "deploy_bundle_to_connect",
            lambda bp: {"success": True, "deployed": True, "state": "succeeded", "bundle_id": "b1", "task_id": "t1"},
        )
        res1 = pub_svc.execute_publish_job(doc.id, reviewer, revision_id=rev1_id)
        assert res1["success"] is True
        snap1_id = res1["snapshot_id"]

        # Content-Hash-Test: Speichern ohne inhaltliche Änderung -> kein "unpublished changes"
        loaded1 = get_article(doc.id)
        assert loaded1 is not None
        save_article(loaded1, user=author, base_doc=loaded1, preserve_db_status=True)
        sync_same = get_published_sync_status(doc.id)
        assert sync_same["is_published"] is True
        assert sync_same["has_unpublished_changes"] is False

        # 5. Entwurf wird geändert, neu eingereicht & freigegeben
        base1 = loaded1.model_copy(deep=True)
        loaded1.metadata.title = "Geänderter Titel v2"
        save_res2 = save_article(loaded1, user=author, base_doc=base1, preserve_db_status=True)
        assert get_published_sync_status(doc.id)["has_unpublished_changes"] is True

        sub2 = pub_svc.submit_article_for_review(doc.id, author)
        rev2_id = sub2["revision_id"]
        assert pub_svc.approve_article_revision(doc.id, rev2_id, reviewer)["success"] is True

        # 6. Zweite Publikation schlägt auf Connect fehl -> alte Live-Fassung S1 bleibt aktiv!
        monkeypatch.setattr(
            pub_svc,
            "deploy_bundle_to_connect",
            lambda bp: {"success": False, "deployed": False, "state": "failed", "bundle_id": "b2", "task_id": "t2", "error": "Deploy error"},
        )
        res2_fail = pub_svc.execute_publish_job(doc.id, reviewer, revision_id=rev2_id)
        assert res2_fail["success"] is False
        fail_job_id = res2_fail["job_id"]

        sync_after_fail = get_published_sync_status(doc.id)
        assert sync_after_fail["live_snapshot_id"] == snap1_id
        with get_db_session() as session:
            s1 = session.get(PublishedSnapshotModel, snap1_id)
            assert s1 is not None and s1.is_active is True

        # 7. Fehlgeschlagenen Auftrag mit derselben Revision wiederholen
        monkeypatch.setattr(
            pub_svc,
            "deploy_bundle_to_connect",
            lambda bp: {"success": True, "deployed": True, "state": "succeeded", "bundle_id": "b3", "task_id": "t3"},
        )
        retry_res = pub_svc.retry_publication_job(fail_job_id, reviewer)
        assert retry_res["success"] is True
        snap2_id = retry_res["snapshot_id"]
        assert snap2_id != snap1_id
        assert get_published_sync_status(doc.id)["live_snapshot_id"] == snap2_id
    finally:
        delete_article(doc.id, force=True)


def test_unknown_connect_task_single_channel_lock_poll_and_unpublish_without_local_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db_and_seed()
    user = f"pub.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "FOUR_EYES_TEMPLATES", [])
    monkeypatch.setattr(pub_svc, "is_connect_configured", lambda: True)

    doc = create_new_article(template_id="market_flash", user=user)
    try:
        # 1. Deploy endet mit unklarem Task-Status
        monkeypatch.setattr(
            pub_svc,
            "deploy_bundle_to_connect",
            lambda bp: {"success": False, "deployed": False, "state": "unknown", "bundle_id": "b_unk", "task_id": "task_unk", "error": "Timeout"},
        )
        res_unk = pub_svc.execute_publish_job(doc.id, user)
        assert res_unk["success"] is False
        assert res_unk["state"] == "unknown"
        job_id = res_unk["job_id"]

        # 2. Während ein Auftrag aktiv/unknown ist, wird ein zweiter Auftrag für denselben Zielkanal blockiert
        blocked = pub_svc.execute_publish_job(doc.id, user)
        assert blocked["success"] is False
        assert "bereits ein aktiver Auftrag" in blocked["error"]

        # 3. Task weiterverfolgen -> Connect meldet jetzt Erfolg
        monkeypatch.setattr(
            pub_svc,
            "poll_connect_task",
            lambda tid, **kw: {"state": "succeeded", "finished": True, "code": 0, "error": None},
        )
        poll_res = pub_svc.poll_publication_job(job_id)
        assert poll_res["success"] is True
        assert get_published_sync_status(doc.id)["is_published"] is True

        # Idempotenz: erneutes Polling dupliziert nicht
        poll_again = pub_svc.poll_publication_job(job_id)
        assert poll_again["success"] is True
        assert poll_again.get("already_completed") is True

        # 4. Lokales Portalverzeichnis komplett löschen -> Rückzug funktioniert trotzdem!
        if config.STATIC_PORTAL_DIR.exists():
            shutil.rmtree(config.STATIC_PORTAL_DIR, ignore_errors=True)
        assert not config.STATIC_PORTAL_DIR.exists()

        captured_bundles: list[list[str]] = []

        def _fake_deploy_unpublish(bp: Path):
            with tarfile.open(bp, "r:gz") as tar:
                captured_bundles.append([m.name.replace("\\", "/") for m in tar.getmembers()])
            return {"success": True, "deployed": True, "state": "succeeded", "bundle_id": "b_unpub", "task_id": "t_unpub"}

        monkeypatch.setattr(pub_svc, "deploy_bundle_to_connect", _fake_deploy_unpublish)
        unpub_res = pub_svc.execute_unpublish_job(doc.id, user)
        assert unpub_res["success"] is True
        assert get_published_sync_status(doc.id)["is_published"] is False
        # Das frische Bundle enthält den zurückgezogenen Artikel nicht mehr
        assert len(captured_bundles) == 1
        assert not any(doc.id in name for name in captured_bundles[0])
    finally:
        delete_article(doc.id, force=True)
