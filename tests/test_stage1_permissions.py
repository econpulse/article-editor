"""
Tests für Etappe 1 (Artikelrechte, globale Rollen, verwaiste Artikel, Präsenz-Filter & Audit-Log).
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config
from database.connection import get_db_session
from database.models import ArticleModel
from database.permissions import (
    check_article_permission,
    get_accessible_article_ids,
    get_user_article_role,
    grant_article_permission,
    list_admin_articles,
    list_audit_log,
    list_review_assignments,
    revoke_article_permission,
    set_global_user_role,
    transfer_article_ownership,
)
from database.repository import (
    create_new_article,
    delete_article,
    get_first_article_id,
    init_db_and_seed,
    list_articles,
)
from server.collab import (
    ACTIVE_PEERS,
    enforce_article_access_revoked,
    filter_presence_by_allowed_articles,
    get_active_articles_presence,
    register_peer,
    set_peer_article,
)


class _DummySession:
    def __init__(self, sid: str, user: str):
        self.id = sid
        self.user = user
        self.messages: list[tuple[str, dict]] = []

    async def send_custom_message(self, name: str, payload: dict) -> None:
        self.messages.append((name, payload))


def test_article_permissions_isolation_grant_and_live_revoke() -> None:
    init_db_and_seed()
    user_a = f"autor.a.{uuid.uuid4().hex[:6]}@lukb.ch"
    user_b = f"autor.b.{uuid.uuid4().hex[:6]}@lukb.ch"

    doc_a = create_new_article(user=user_a)
    try:
        # 1. Ersteller ist automatisch Owner
        assert get_user_article_role(doc_a.id, user_a) == "owner"
        assert check_article_permission(doc_a.id, user_a, "read") is True
        assert check_article_permission(doc_a.id, user_a, "edit") is True
        assert check_article_permission(doc_a.id, user_a, "assign") is True
        assert check_article_permission(doc_a.id, user_a, "review") is True

        # 2. A sieht den Artikel, B sieht ihn weder in Liste noch Suche noch first_id
        a_ids = {it["id"] for it in list_articles(user_id=user_a)}
        b_ids = {it["id"] for it in list_articles(user_id=user_b)}
        b_search = {it["id"] for it in list_articles(search_query="Investment", user_id=user_b)}
        assert doc_a.id in a_ids
        assert doc_a.id not in b_ids
        assert doc_a.id not in b_search
        assert check_article_permission(doc_a.id, user_b, "read") is False
        assert get_first_article_id(user_id=user_b) != doc_a.id

        # 3. Präsenz-Filter leakt doc_a.id nicht an B
        sid_a = f"sess_a_{uuid.uuid4().hex[:6]}"
        sid_b = f"sess_b_{uuid.uuid4().hex[:6]}"
        sess_a = _DummySession(sid_a, user_a)
        sess_b = _DummySession(sid_b, user_b)
        revoked_calls: list[str] = []
        register_peer(sid_a, sess_a, user_a, "#009FE3", lambda d: None)
        register_peer(sid_b, sess_b, user_b, "#0D9488", lambda d: None, revoke_cb=lambda aid: revoked_calls.append(aid))
        set_peer_article(sid_a, doc_a.id)

        raw_presence = get_active_articles_presence()
        filtered_for_b = filter_presence_by_allowed_articles(raw_presence, get_accessible_article_ids(user_b))
        assert doc_a.id not in filtered_for_b

        # 4. Zuweisung an B als 'editor' -> erscheint für B, B darf lesen & bearbeiten, aber nicht zuweisen
        grant_res = grant_article_permission(doc_a.id, user_b, "editor", actor_user=user_a)
        assert grant_res["success"] is True
        assert doc_a.id in {it["id"] for it in list_articles(user_id=user_b)}
        assert check_article_permission(doc_a.id, user_b, "read") is True
        assert check_article_permission(doc_a.id, user_b, "edit") is True
        assert check_article_permission(doc_a.id, user_b, "assign") is False

        # B öffnet den Artikel in aktiver Session
        set_peer_article(sid_b, doc_a.id)
        assert ACTIVE_PEERS[sid_b]["article_id"] == doc_a.id

        # 5. Entzug beendet Zugriff auch in der offenen Sitzung von B
        rev_res = revoke_article_permission(doc_a.id, user_b, actor_user=user_a)
        assert rev_res["success"] is True
        count_kicked = asyncio.run(enforce_article_access_revoked(doc_a.id, user_b))
        assert count_kicked == 1
        assert ACTIVE_PEERS[sid_b]["article_id"] == ""
        assert revoked_calls == [doc_a.id]
        assert any(name == "lukb_access_revoked" and payload["article_id"] == doc_a.id for name, payload in sess_b.messages)
        assert check_article_permission(doc_a.id, user_b, "read") is False
    finally:
        ACTIVE_PEERS.pop(sid_a, None)
        ACTIVE_PEERS.pop(sid_b, None)
        delete_article(doc_a.id, force=True)


def test_technical_session_names_and_connect_startup_admin_check(monkeypatch: pytest.MonkeyPatch) -> None:
    assert config.is_technical_session_user("Analyst (1234)") is True
    assert config.is_technical_session_user("") is True
    assert config.get_user_role("Analyst (1234)") == "guest"
    assert config.can_publish("Analyst (1234)") is False
    assert config.is_global_admin("Analyst (1234)") is False
    assert list_articles(user_id="Analyst (1234)") == []

    monkeypatch.setattr(config, "PORTAL_ADMINS", [])
    monkeypatch.setattr(config, "is_connect_environment", lambda: True)
    with pytest.raises(RuntimeError):
        config.validate_startup_admin_config(raise_on_missing=True)


def test_orphan_articles_global_roles_review_assignments_and_audit_log(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db_and_seed()
    admin_user = f"admin.{uuid.uuid4().hex[:6]}@lukb.ch"
    editor_user = f"editor.{uuid.uuid4().hex[:6]}@lukb.ch"
    reviewer_user = f"reviewer.{uuid.uuid4().hex[:6]}@lukb.ch"

    monkeypatch.setattr(config, "PORTAL_ADMINS", [admin_user])
    monkeypatch.setattr(config, "PORTAL_PUBLISHERS", [])

    # Simuliere einen Bestandsartikel ohne Zuordnung in io_article_permissions (verwaister Artikel)
    orphan_id = f"orphan_{uuid.uuid4().hex[:8]}"
    with get_db_session() as session:
        session.add(
            ArticleModel(
                id=orphan_id,
                title="Altbestand ohne Zuordnung",
                status="review",
                updated_by="Alt-Autor",
                blocks_json="[]",
            )
        )

    try:
        orphans = list_admin_articles(only_orphans=True)
        assert any(a["id"] == orphan_id and a["is_orphan"] is True for a in orphans)

        # Admin überträgt Verantwortung an editor_user
        tr_res = transfer_article_ownership(orphan_id, editor_user, actor_user=admin_user)
        assert tr_res["success"] is True
        assert get_user_article_role(orphan_id, editor_user) == "owner"

        orphans_after = list_admin_articles(only_orphans=True)
        assert not any(a["id"] == orphan_id for a in orphans_after)

        # Prüfberechtigten zuweisen -> erscheint in Prüfaufträgen
        gr_rev = grant_article_permission(orphan_id, reviewer_user, "reviewer", actor_user=editor_user)
        assert gr_rev["success"] is True
        assignments = list_review_assignments(reviewer_user)
        assert any(it["id"] == orphan_id and it["article_role"] == "reviewer" for it in assignments)

        # Globale Rollen getrennt vergeben: nur Publizieren, kein Admin
        role_res = set_global_user_role(
            reviewer_user,
            is_admin=False,
            can_publish=True,
            actor_user=admin_user,
        )
        assert role_res["success"] is True
        assert config.is_global_admin(reviewer_user) is False
        assert config.can_publish(reviewer_user) is True

        # Audit-Log enthält alle Änderungen mit Actor & Zeitpunkt
        logs = list_audit_log(limit=30)
        actions_for_orphan = {l["action"] for l in logs if l["article_id"] == orphan_id}
        assert "transfer_ownership" in actions_for_orphan
        assert "grant_permission" in actions_for_orphan
        assert any(
            l["action"] == "set_user_role"
            and l["target_user"] == reviewer_user
            and l["actor_user"] == admin_user
            for l in logs
        )
    finally:
        delete_article(orphan_id, force=True)


def test_local_dev_session_user_fallback_without_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    import server.state as state_mod

    init_db_and_seed()
    sess = _DummySession(f"sess_local_{uuid.uuid4().hex[:6]}", user=None)
    sess.on_ended = lambda _cb: None

    # 1. Ohne Connect-Umgebung: Session erhält LOCAL_DEV_USER und ist authentifiziert + arbeitsfähig
    monkeypatch.setattr(state_mod, "is_connect_environment", lambda: False)
    st_local = state_mod.SessionState(sess, None)
    assert st_local.current_user == config.LOCAL_DEV_USER
    assert st_local.is_authenticated is True
    assert len(list_articles(user_id=st_local.current_user_id)) > 0

    # 2. Mit Connect-Umgebung ohne session.user: technischer Sitzungsname ohne Rechte
    monkeypatch.setattr(state_mod, "is_connect_environment", lambda: True)
    st_connect = state_mod.SessionState(sess, None)
    assert st_connect.current_user.startswith("Analyst (")
    assert st_connect.is_authenticated is False
    assert list_articles(user_id=st_connect.current_user_id) == []

    ACTIVE_PEERS.pop(sess.id, None)


def test_broadcast_article_list_does_not_hang_on_stalled_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    import server.collab as collab_mod

    init_db_and_seed()
    monkeypatch.setattr(collab_mod, "_PEER_SEND_TIMEOUT_SECONDS", 0.05)

    class _StalledSession(_DummySession):
        async def send_custom_message(self, name: str, payload: dict) -> None:
            await asyncio.sleep(10.0)

    sid_stalled = f"sess_stalled_{uuid.uuid4().hex[:6]}"
    sid_healthy = f"sess_healthy_{uuid.uuid4().hex[:6]}"
    sess_stalled = _StalledSession(sid_stalled, "stalled.user@lukb.ch")
    sess_healthy = _DummySession(sid_healthy, "healthy.user@lukb.ch")

    register_peer(sid_stalled, sess_stalled, "stalled.user@lukb.ch", "#009FE3", lambda d: None)
    register_peer(sid_healthy, sess_healthy, "healthy.user@lukb.ch", "#0D9488", lambda d: None)
    try:
        asyncio.run(collab_mod.broadcast_article_list_to_all())
        assert sid_stalled not in ACTIVE_PEERS
        assert sid_healthy in ACTIVE_PEERS
        assert any(name == "lukb_global_article_list" for name, _ in sess_healthy.messages)
    finally:
        ACTIVE_PEERS.pop(sid_stalled, None)
        ACTIVE_PEERS.pop(sid_healthy, None)


def test_user_alias_deactivate_and_delete_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    from database.connection import get_db_session
    from database.models import PublishedSnapshotModel, UserRoleModel
    from database.permissions import (
        delete_user_account,
        is_user_active,
        list_article_permissions,
        list_known_users,
        set_global_user_role,
        set_user_active_status,
    )

    init_db_and_seed()
    admin_uid = f"admin.ctrl.{uuid.uuid4().hex[:6]}@lukb.ch"
    typo_uid = f"typo.usr.{uuid.uuid4().hex[:6]}@lukb.ch"
    assigned_uid = f"assigned.usr.{uuid.uuid4().hex[:6]}@lukb.ch"
    pub_uid = f"pub.usr.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "PORTAL_ADMINS", [admin_uid])

    doc = create_new_article(template_id="investment_focus", user=admin_uid)
    snap_id = None
    try:
        # 1. Alias/Name speichern & in list_known_users + list_article_permissions prüfen
        res_typo = set_global_user_role(
            typo_uid,
            is_admin=False,
            can_publish=True,
            actor_user=admin_uid,
            display_name="Max Tippfehler",
        )
        assert res_typo["success"] is True
        assert res_typo["display_name"] == "Max Tippfehler"
        users = {u["user_id"]: u for u in list_known_users()}
        assert users[typo_uid]["display_name"] == "Max Tippfehler"
        assert users[typo_uid]["is_active"] is True
        assert users[typo_uid]["can_delete"] is True

        # 2. User ohne zugewiesene/publizierte Artikel kann gelöscht werden
        del_ok = delete_user_account(typo_uid, admin_uid)
        assert del_ok["success"] is True
        users_after = {u["user_id"]: u for u in list_known_users()}
        assert typo_uid not in users_after

        # 3. User mit zugewiesenem Artikel: Deaktivieren möglich & entzieht Zugriff, Löschen blockiert
        set_global_user_role(
            assigned_uid,
            is_admin=False,
            can_publish=False,
            actor_user=admin_uid,
            display_name="Anna Editor",
        )
        assert grant_article_permission(doc.id, assigned_uid, "editor", admin_uid)["success"] is True
        perms = list_article_permissions(doc.id)
        assert any(p["user_id"] == assigned_uid and p["display_name"] == "Anna Editor" for p in perms)

        del_assigned = delete_user_account(assigned_uid, admin_uid)
        assert del_assigned["success"] is False
        assert "zugewiesene Artikel" in del_assigned["error"]

        deact = set_user_active_status(assigned_uid, is_active=False, actor_user=admin_uid)
        assert deact["success"] is True
        assert is_user_active(assigned_uid) is False
        assert check_article_permission(doc.id, assigned_uid, "read") is False
        assert doc.id not in get_accessible_article_ids(assigned_uid)

        # Reaktivieren stellt aktiven Status wieder her
        react = set_user_active_status(assigned_uid, is_active=True, actor_user=admin_uid)
        assert react["success"] is True
        assert is_user_active(assigned_uid) is True
        assert check_article_permission(doc.id, assigned_uid, "read") is True

        # 4. User mit aktivem publiziertem Snapshot auf dem Portal: nur deaktivierbar, nicht löschbar
        set_global_user_role(
            pub_uid,
            is_admin=False,
            can_publish=True,
            actor_user=admin_uid,
            display_name="Paul Publizist",
        )
        with get_db_session() as s:
            snap = PublishedSnapshotModel(
                article_id=doc.id,
                version=1,
                is_active=True,
                slug="delete-guard-test",
                title="Delete Guard Test",
                publication_date="2026-11-22",
                metadata_json="{}",
                html_content="<p>ok</p>",
                published_by=pub_uid,
            )
            s.add(snap)
            s.flush()
            snap_id = snap.id

        del_pub = delete_user_account(pub_uid, admin_uid)
        assert del_pub["success"] is False
        assert "publizierte Artikel" in del_pub["error"]
        assert set_user_active_status(pub_uid, is_active=False, actor_user=admin_uid)["success"] is True
    finally:
        with get_db_session() as s:
            if snap_id is not None:
                snap_obj = s.get(PublishedSnapshotModel, snap_id)
                if snap_obj:
                    s.delete(snap_obj)
            for uid in (typo_uid, assigned_uid, pub_uid):
                ur = s.get(UserRoleModel, uid)
                if ur:
                    s.delete(ur)
        delete_article(doc.id, force=True)
