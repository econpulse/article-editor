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


def test_confirm_unpublish_handler_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from types import SimpleNamespace

    import server.workflow_handlers as wf_handlers

    init_db_and_seed()
    publisher = f"pub.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "PORTAL_PUBLISHERS", [publisher])

    doc = create_new_article(template_id="market_flash", user=publisher)
    doc.status = "published"
    try:
        effects: dict[str, object] = {}

        class _FakeReactive:
            @staticmethod
            def effect(fn):
                effects[fn.__name__] = fn
                return fn

            @staticmethod
            def event(*args, **kwargs):
                return lambda fn: fn

        class _FakeInput:
            lukb_submit_review = object()
            lukb_publish_portal = object()
            lukb_unpublish_portal = object()
            btn_confirm_unpublish = object()

        class _FakeVar:
            def __init__(self, val):
                self._val = val

            def get(self):
                return self._val

            def set(self, val):
                self._val = val

        notifications: list[tuple[str, str]] = []
        modals_removed = []
        unpublish_calls: list[tuple[str, str, str]] = []

        class _FakeState:
            session_id = "sess_test"
            current_user = publisher
            current_user_id = publisher
            current_doc = _FakeVar(doc)

            def can_access_article(self, article_id: str, action: str, allow_admin_override: bool = False) -> bool:
                return article_id == doc.id and action in ("read", "edit")

            async def send_article_list(self, *_args, **_kwargs) -> None:
                return None

        monkeypatch.setattr(wf_handlers, "reactive", _FakeReactive)
        monkeypatch.setattr(wf_handlers, "can_publish", lambda u: u == publisher)
        monkeypatch.setattr(wf_handlers.ui, "modal_remove", lambda: modals_removed.append(True))
        monkeypatch.setattr(
            wf_handlers.ui,
            "notification_show",
            lambda msg, type="message", **_kw: notifications.append((type, msg)),
        )
        monkeypatch.setattr(
            wf_handlers,
            "execute_unpublish_job",
            lambda aid, uid, new_status="draft": (
                unpublish_calls.append((aid, uid, new_status))
                or {"success": True, "deployed": False, "connect_deploy": {"deployed": False}}
            ),
        )
        monkeypatch.setattr(wf_handlers, "get_published_sync_status", lambda _aid: {"is_published": False})
        async def _noop_async(*_a, **_kw):
            return None

        monkeypatch.setattr(wf_handlers, "broadcast_article_list_to_all", _noop_async)
        monkeypatch.setattr(wf_handlers, "broadcast_article_sync", _noop_async)

        wf_handlers.register_workflow_handlers(_FakeInput(), SimpleNamespace(), SimpleNamespace(), _FakeState())
        confirm_fn = effects["_on_confirm_unpublish"]
        asyncio.run(confirm_fn())

        assert len(modals_removed) == 1
        assert unpublish_calls == [(doc.id, publisher, "draft")]
        assert doc.status == "draft"
        assert not any(t == "error" for t, _ in notifications)
    finally:
        delete_article(doc.id, force=True)


def test_render_exception_and_unpublish_retry_fail_mark_job_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    from database.models import PublicationJobModel

    init_db_and_seed()
    user = f"pub.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "FOUR_EYES_TEMPLATES", [])
    monkeypatch.setattr(pub_svc, "is_connect_configured", lambda: True)

    doc = create_new_article(template_id="market_flash", user=user)
    try:
        # 1. Renderer wirft Exception -> Auftrag darf nicht auf 'rendering' hängen bleiben!
        monkeypatch.setattr(
            pub_svc,
            "render_publication_package",
            lambda _doc: (_ for _ in ()).throw(RuntimeError("Typst crash")),
        )
        fail_render = pub_svc.execute_publish_job(doc.id, user)
        assert fail_render["success"] is False
        assert fail_render["state"] == "failed"
        job1_id = fail_render["job_id"]
        with get_db_session() as session:
            j1 = session.get(PublicationJobModel, job1_id)
            assert j1 is not None and j1.status == "failed"
            assert "Typst crash" in (j1.error_message or "")

        # 2. Kanal ist nicht blockiert; Retry gelingt nach Renderer-Fix
        from services.renderer import render_publication_package as real_render

        monkeypatch.setattr(pub_svc, "render_publication_package", real_render)
        monkeypatch.setattr(
            pub_svc,
            "deploy_bundle_to_connect",
            lambda _bp: {"success": True, "deployed": True, "state": "succeeded", "bundle_id": "b_ok", "task_id": "t_ok"},
        )
        ok_retry = pub_svc.retry_publication_job(job1_id, user)
        assert ok_retry["success"] is True

        # 3. Rückzug schlägt fehl, und Retry schlägt erneut fehl -> Status muss 'failed' sein, nicht 'pending'!
        monkeypatch.setattr(
            pub_svc,
            "deploy_bundle_to_connect",
            lambda _bp: {"success": False, "deployed": False, "state": "failed", "bundle_id": "b_u1", "task_id": "t_u1", "error": "Connect down"},
        )
        unpub_fail = pub_svc.execute_unpublish_job(doc.id, user)
        assert unpub_fail["success"] is False
        unpub_job_id = unpub_fail["job_id"]

        unpub_retry_fail = pub_svc.retry_publication_job(unpub_job_id, user)
        assert unpub_retry_fail["success"] is False
        assert unpub_retry_fail["state"] == "failed"
        with get_db_session() as session:
            ju = session.get(PublicationJobModel, unpub_job_id)
            assert ju is not None and ju.status == "failed"
    finally:
        delete_article(doc.id, force=True)


def test_review_assignments_view_and_approve_for_reviewer_role(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from types import SimpleNamespace

    import server.admin_handlers as admin_handlers
    from database.models import ArticleModel
    from database.permissions import grant_article_permission, list_review_assignments

    init_db_and_seed()
    author = f"autor.{uuid.uuid4().hex[:6]}@lukb.ch"
    reviewer = f"reviewer.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "FOUR_EYES_TEMPLATES", ["investment_focus"])

    doc = create_new_article(template_id="investment_focus", user=author)
    try:
        # Nur reine 'reviewer'-Rolle (ohne 'edit')
        grant_res = grant_article_permission(doc.id, reviewer, "reviewer", author)
        assert grant_res["success"] is True

        sub = pub_svc.submit_article_for_review(doc.id, author)
        assert sub["success"] is True
        rev_id = sub["revision_id"]

        assignments = list_review_assignments(reviewer)
        mine = [a for a in assignments if a["id"] == doc.id]
        assert len(mine) == 1
        assert mine[0]["submitted_revision_id"] == rev_id

        effects: dict[str, object] = {}

        class _FakeReactive:
            @staticmethod
            def effect(fn):
                effects[fn.__name__] = fn
                return fn

            @staticmethod
            def event(*args, **kwargs):
                return lambda fn: fn

        class _FakeInput:
            def __init__(self):
                self._view_payload = {"article_id": doc.id, "revision_id": rev_id}
                self._approve_payload = {"article_id": doc.id, "revision_id": rev_id}

            def __getattr__(self, name: str):
                if name == "lukb_view_review_revision":
                    return lambda: self._view_payload
                if name == "lukb_approve_review_revision":
                    return lambda: self._approve_payload
                return lambda: None

        shown_modals: list[object] = []
        notifications: list[tuple[str, str]] = []

        class _FakeState:
            session_id = "sess_rev"
            is_authenticated = True
            current_user = reviewer
            current_user_id = reviewer

            def can_access_article(self, article_id: str, action: str, allow_admin_override: bool = False) -> bool:
                from database.permissions import check_article_permission

                return check_article_permission(article_id, reviewer, action, allow_admin_override=allow_admin_override)

        monkeypatch.setattr(admin_handlers, "reactive", _FakeReactive)
        monkeypatch.setattr(admin_handlers.ui, "modal_show", lambda m: shown_modals.append(m))
        monkeypatch.setattr(
            admin_handlers.ui,
            "notification_show",
            lambda msg, type="message", **_kw: notifications.append((type, msg)),
        )

        async def _noop_async(*_a, **_kw):
            return None

        monkeypatch.setattr(admin_handlers, "broadcast_article_list_to_all", _noop_async)

        admin_handlers.register_admin_handlers(_FakeInput(), SimpleNamespace(), SimpleNamespace(), _FakeState())

        # 1. Prüfaufträge öffnen -> enthält "Revision ansehen" und "Diese Revision freigeben"
        asyncio.run(effects["_on_open_review_assignments"]())
        modal_html = str(shown_modals[-1])
        assert "Revision ansehen" in modal_html
        assert "Diese Revision freigeben" in modal_html

        # 2. Revision ansehen als reiner Reviewer (ohne edit-Recht)
        asyncio.run(effects["_on_view_review_revision"]())
        view_html = str(shown_modals[-1])
        assert f"Rev #{rev_id}" in view_html

        # 3. Revision direkt freigeben als reiner Reviewer
        asyncio.run(effects["_on_approve_review_revision"]())
        assert any(t == "message" and f"Revision #{rev_id}" in msg for t, msg in notifications)
        with get_db_session() as session:
            art = session.get(ArticleModel, doc.id)
            assert art is not None
            assert art.approved_revision_id == rev_id
            assert art.approved_by == reviewer
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


def test_confirm_unpublish_handler_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from types import SimpleNamespace

    import server.workflow_handlers as wf_handlers

    init_db_and_seed()
    publisher = f"pub.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "PORTAL_PUBLISHERS", [publisher])

    doc = create_new_article(template_id="market_flash", user=publisher)
    doc.status = "published"
    try:
        effects: dict[str, object] = {}

        class _FakeReactive:
            @staticmethod
            def effect(fn):
                effects[fn.__name__] = fn
                return fn

            @staticmethod
            def event(*args, **kwargs):
                return lambda fn: fn

        class _FakeInput:
            lukb_submit_review = object()
            lukb_publish_portal = object()
            lukb_unpublish_portal = object()
            btn_confirm_unpublish = object()

        class _FakeVar:
            def __init__(self, val):
                self._val = val

            def get(self):
                return self._val

            def set(self, val):
                self._val = val

        notifications: list[tuple[str, str]] = []
        modals_removed = []
        unpublish_calls: list[tuple[str, str, str]] = []

        class _FakeState:
            session_id = "sess_test"
            current_user = publisher
            current_user_id = publisher
            current_doc = _FakeVar(doc)

            def can_access_article(self, article_id: str, action: str, allow_admin_override: bool = False) -> bool:
                return article_id == doc.id and action in ("read", "edit")

            async def send_article_list(self, *_args, **_kwargs) -> None:
                return None

        monkeypatch.setattr(wf_handlers, "reactive", _FakeReactive)
        monkeypatch.setattr(wf_handlers, "can_publish", lambda u: u == publisher)
        monkeypatch.setattr(wf_handlers.ui, "modal_remove", lambda: modals_removed.append(True))
        monkeypatch.setattr(
            wf_handlers.ui,
            "notification_show",
            lambda msg, type="message", **_kw: notifications.append((type, msg)),
        )
        monkeypatch.setattr(
            wf_handlers,
            "execute_unpublish_job",
            lambda aid, uid, new_status="draft": (
                unpublish_calls.append((aid, uid, new_status))
                or {"success": True, "deployed": False, "connect_deploy": {"deployed": False}}
            ),
        )
        monkeypatch.setattr(wf_handlers, "get_published_sync_status", lambda _aid: {"is_published": False})
        async def _noop_async(*_a, **_kw):
            return None

        monkeypatch.setattr(wf_handlers, "broadcast_article_list_to_all", _noop_async)
        monkeypatch.setattr(wf_handlers, "broadcast_article_sync", _noop_async)

        wf_handlers.register_workflow_handlers(_FakeInput(), SimpleNamespace(), SimpleNamespace(), _FakeState())
        confirm_fn = effects["_on_confirm_unpublish"]
        asyncio.run(confirm_fn())

        assert len(modals_removed) == 1
        assert unpublish_calls == [(doc.id, publisher, "draft")]
        assert doc.status == "draft"
        assert not any(t == "error" for t, _ in notifications)
    finally:
        delete_article(doc.id, force=True)


def test_render_exception_and_unpublish_retry_fail_mark_job_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    from database.models import PublicationJobModel

    init_db_and_seed()
    user = f"pub.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "FOUR_EYES_TEMPLATES", [])
    monkeypatch.setattr(pub_svc, "is_connect_configured", lambda: True)

    doc = create_new_article(template_id="market_flash", user=user)
    try:
        # 1. Renderer wirft Exception -> Auftrag darf nicht auf 'rendering' hängen bleiben!
        monkeypatch.setattr(
            pub_svc,
            "render_publication_package",
            lambda _doc: (_ for _ in ()).throw(RuntimeError("Typst crash")),
        )
        fail_render = pub_svc.execute_publish_job(doc.id, user)
        assert fail_render["success"] is False
        assert fail_render["state"] == "failed"
        job1_id = fail_render["job_id"]
        with get_db_session() as session:
            j1 = session.get(PublicationJobModel, job1_id)
            assert j1 is not None and j1.status == "failed"
            assert "Typst crash" in (j1.error_message or "")

        # 2. Kanal ist nicht blockiert; Retry gelingt nach Renderer-Fix
        from services.renderer import render_publication_package as real_render

        monkeypatch.setattr(pub_svc, "render_publication_package", real_render)
        monkeypatch.setattr(
            pub_svc,
            "deploy_bundle_to_connect",
            lambda _bp: {"success": True, "deployed": True, "state": "succeeded", "bundle_id": "b_ok", "task_id": "t_ok"},
        )
        ok_retry = pub_svc.retry_publication_job(job1_id, user)
        assert ok_retry["success"] is True

        # 3. Rückzug schlägt fehl, und Retry schlägt erneut fehl -> Status muss 'failed' sein, nicht 'pending'!
        monkeypatch.setattr(
            pub_svc,
            "deploy_bundle_to_connect",
            lambda _bp: {"success": False, "deployed": False, "state": "failed", "bundle_id": "b_u1", "task_id": "t_u1", "error": "Connect down"},
        )
        unpub_fail = pub_svc.execute_unpublish_job(doc.id, user)
        assert unpub_fail["success"] is False
        unpub_job_id = unpub_fail["job_id"]

        unpub_retry_fail = pub_svc.retry_publication_job(unpub_job_id, user)
        assert unpub_retry_fail["success"] is False
        assert unpub_retry_fail["state"] == "failed"
        with get_db_session() as session:
            ju = session.get(PublicationJobModel, unpub_job_id)
            assert ju is not None and ju.status == "failed"
    finally:
        delete_article(doc.id, force=True)


def test_review_assignments_view_and_approve_for_reviewer_role(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from types import SimpleNamespace

    import server.admin_handlers as admin_handlers
    from database.models import ArticleModel
    from database.permissions import grant_article_permission, list_review_assignments

    init_db_and_seed()
    author = f"autor.{uuid.uuid4().hex[:6]}@lukb.ch"
    reviewer = f"reviewer.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "FOUR_EYES_TEMPLATES", ["investment_focus"])

    doc = create_new_article(template_id="investment_focus", user=author)
    try:
        # Nur reine 'reviewer'-Rolle (ohne 'edit')
        grant_res = grant_article_permission(doc.id, reviewer, "reviewer", author)
        assert grant_res["success"] is True

        sub = pub_svc.submit_article_for_review(doc.id, author)
        assert sub["success"] is True
        rev_id = sub["revision_id"]

        assignments = list_review_assignments(reviewer)
        mine = [a for a in assignments if a["id"] == doc.id]
        assert len(mine) == 1
        assert mine[0]["submitted_revision_id"] == rev_id

        effects: dict[str, object] = {}

        class _FakeReactive:
            @staticmethod
            def effect(fn):
                effects[fn.__name__] = fn
                return fn

            @staticmethod
            def event(*args, **kwargs):
                return lambda fn: fn

        class _FakeInput:
            def __init__(self):
                self._view_payload = {"article_id": doc.id, "revision_id": rev_id}
                self._approve_payload = {"article_id": doc.id, "revision_id": rev_id}

            def __getattr__(self, name: str):
                if name == "lukb_view_review_revision":
                    return lambda: self._view_payload
                if name == "lukb_approve_review_revision":
                    return lambda: self._approve_payload
                return lambda: None

        shown_modals: list[object] = []
        notifications: list[tuple[str, str]] = []

        class _FakeState:
            session_id = "sess_rev"
            is_authenticated = True
            current_user = reviewer
            current_user_id = reviewer

            def can_access_article(self, article_id: str, action: str, allow_admin_override: bool = False) -> bool:
                from database.permissions import check_article_permission

                return check_article_permission(article_id, reviewer, action, allow_admin_override=allow_admin_override)

        monkeypatch.setattr(admin_handlers, "reactive", _FakeReactive)
        monkeypatch.setattr(admin_handlers.ui, "modal_show", lambda m: shown_modals.append(m))
        monkeypatch.setattr(
            admin_handlers.ui,
            "notification_show",
            lambda msg, type="message", **_kw: notifications.append((type, msg)),
        )

        async def _noop_async(*_a, **_kw):
            return None

        monkeypatch.setattr(admin_handlers, "broadcast_article_list_to_all", _noop_async)

        admin_handlers.register_admin_handlers(_FakeInput(), SimpleNamespace(), SimpleNamespace(), _FakeState())

        # 1. Prüfaufträge öffnen -> enthält "Revision ansehen" und "Diese Revision freigeben"
        asyncio.run(effects["_on_open_review_assignments"]())
        modal_html = str(shown_modals[-1])
        assert "Revision ansehen" in modal_html
        assert "Diese Revision freigeben" in modal_html

        # 2. Revision ansehen als reiner Reviewer (ohne edit-Recht)
        asyncio.run(effects["_on_view_review_revision"]())
        view_html = str(shown_modals[-1])
        assert f"Rev #{rev_id}" in view_html

        # 3. Revision direkt freigeben als reiner Reviewer
        asyncio.run(effects["_on_approve_review_revision"]())
        assert any(t == "message" and f"Revision #{rev_id}" in msg for t, msg in notifications)
        with get_db_session() as session:
            art = session.get(ArticleModel, doc.id)
            assert art is not None
            assert art.approved_revision_id == rev_id
            assert art.approved_by == reviewer
    finally:
        delete_article(doc.id, force=True)
