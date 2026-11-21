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
