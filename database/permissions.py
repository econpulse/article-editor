"""
database/permissions.py
=======================
Zentrale Artikelrechte-, Rollen- und Audit-Logik (Etappe 1).
- Artikelspezifische Rollen: 'owner', 'editor', 'reviewer', 'viewer'
- Globale Rechte: 'is_admin', 'can_publish' (unabhängig voneinander verwaltet)
- Audit-Protokoll für alle Zuweisungs- und Rollenänderungen
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import desc, func, or_, select

from config import (
    PORTAL_ADMINS,
    PORTAL_PUBLISHERS,
    is_global_admin,
    is_technical_session_user,
    normalize_user_id,
)
from database.connection import get_db_session
from database.models import (
    ArticleModel,
    ArticlePermissionModel,
    AuditLogModel,
    UserRoleModel,
)

logger = logging.getLogger(__name__)

ARTICLE_ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "owner": frozenset({"read", "edit", "assign", "review"}),
    "editor": frozenset({"read", "edit"}),
    "reviewer": frozenset({"read", "review"}),
    "viewer": frozenset({"read"}),
}

VALID_ARTICLE_ROLES = tuple(ARTICLE_ROLE_CAPABILITIES.keys())


def record_audit_log(
    session,
    *,
    actor_user: str,
    action: str,
    target_user: str | None = None,
    article_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Schreibt einen Audit-Eintrag innerhalb der laufenden DB-Transaktion."""
    session.add(
        AuditLogModel(
            actor_user=normalize_user_id(actor_user) or str(actor_user or "system"),
            action=action,
            target_user=normalize_user_id(target_user) if target_user else None,
            article_id=article_id,
            details_json=json.dumps(details or {}, ensure_ascii=False),
        )
    )


def get_db_user_global_rights(user_id: str) -> tuple[bool, bool] | None:
    """Liest (is_admin, can_publish) aus io_user_roles, falls der Benutzer dort gepflegt ist."""
    uid = normalize_user_id(user_id)
    if not uid or is_technical_session_user(uid):
        return None
    with get_db_session() as session:
        row = session.get(UserRoleModel, uid)
        if not row:
            return None
        return (bool(row.is_admin), bool(row.can_publish))


def get_user_article_role(article_id: str, user_id: str | None) -> str | None:
    """Gibt die artikelspezifische Rolle ('owner', 'editor', 'reviewer', 'viewer') oder None zurück."""
    uid = normalize_user_id(user_id)
    if not article_id or not uid or is_technical_session_user(uid):
        return None
    with get_db_session() as session:
        role = session.scalar(
            select(ArticlePermissionModel.role).where(
                ArticlePermissionModel.article_id == article_id,
                ArticlePermissionModel.user_id == uid,
            )
        )
        return str(role) if role in ARTICLE_ROLE_CAPABILITIES else None


def check_article_permission(
    article_id: str,
    user_id: str | None,
    action: str,
    *,
    allow_admin_override: bool = False,
) -> bool:
    """
    Zentrale Rechteprüfung für einen konkreten Artikel.
    Technische Sitzungsnamen erhalten niemals Zugriff.
    """
    uid = normalize_user_id(user_id)
    if not article_id or not uid or is_technical_session_user(uid):
        return False

    if allow_admin_override and is_global_admin(uid):
        return True

    role = get_user_article_role(article_id, uid)
    if not role:
        return False
    return action in ARTICLE_ROLE_CAPABILITIES.get(role, frozenset())


def get_accessible_article_ids(user_id: str | None) -> set[str]:
    """Liefert alle Artikel-IDs, auf die der Benutzer mindestens Leserecht hat."""
    uid = normalize_user_id(user_id)
    if not uid or is_technical_session_user(uid):
        return set()
    with get_db_session() as session:
        rows = session.scalars(
            select(ArticlePermissionModel.article_id).where(ArticlePermissionModel.user_id == uid)
        ).all()
        return {str(aid) for aid in rows if aid}


def list_article_permissions(article_id: str) -> list[dict[str, Any]]:
    """Listet alle Benutzer-Zuordnungen eines Artikels."""
    if not article_id:
        return []
    with get_db_session() as session:
        rows = session.scalars(
            select(ArticlePermissionModel)
            .where(ArticlePermissionModel.article_id == article_id)
            .order_by(ArticlePermissionModel.granted_at.asc())
        ).all()
        return [
            {
                "article_id": r.article_id,
                "user_id": r.user_id,
                "role": r.role,
                "granted_by": r.granted_by,
                "granted_at": r.granted_at.strftime("%d.%m.%Y %H:%M") if r.granted_at else "",
            }
            for r in rows
        ]


def grant_article_permission(
    article_id: str,
    target_user: str,
    role: str,
    actor_user: str,
    *,
    allow_system: bool = False,
) -> dict[str, Any]:
    """
    Vergibt oder aktualisiert eine Artikelrolle für `target_user`.
    Erfordert `assign`-Recht auf dem Artikel oder globale Admin-Rechte (ausser allow_system=True).
    """
    actor = normalize_user_id(actor_user)
    target = normalize_user_id(target_user)
    clean_role = (role or "editor").strip().lower()

    if clean_role not in ARTICLE_ROLE_CAPABILITIES:
        return {"success": False, "error": f"Ungültige Artikelrolle: {role}"}
    if not article_id or not target or is_technical_session_user(target):
        return {"success": False, "error": "Ungültige Ziel-Benutzerkennung."}
    if not allow_system:
        if not actor or is_technical_session_user(actor):
            return {"success": False, "error": "Nicht authentifiziert."}
        if not check_article_permission(article_id, actor, "assign", allow_admin_override=True):
            return {"success": False, "error": "Keine Berechtigung zum Zuweisen dieses Artikels."}

    with get_db_session() as session:
        art = session.get(ArticleModel, article_id)
        if not art:
            return {"success": False, "error": "Artikel nicht gefunden."}

        existing = session.scalars(
            select(ArticlePermissionModel).where(
                ArticlePermissionModel.article_id == article_id,
                ArticlePermissionModel.user_id == target,
            )
        ).first()
        old_role = existing.role if existing else None
        if existing:
            existing.role = clean_role
            existing.granted_by = actor or "system"
        else:
            session.add(
                ArticlePermissionModel(
                    article_id=article_id,
                    user_id=target,
                    role=clean_role,
                    granted_by=actor or "system",
                )
            )
        record_audit_log(
            session,
            actor_user=actor or "system",
            action="grant_permission",
            target_user=target,
            article_id=article_id,
            details={"old_role": old_role, "new_role": clean_role},
        )

    return {"success": True, "article_id": article_id, "user_id": target, "role": clean_role}


def revoke_article_permission(
    article_id: str,
    target_user: str,
    actor_user: str,
) -> dict[str, Any]:
    """
    Entzieht `target_user` den Zugriff auf `article_id`.
    Erfordert `assign`-Recht auf dem Artikel oder globale Admin-Rechte.
    """
    actor = normalize_user_id(actor_user)
    target = normalize_user_id(target_user)

    if not actor or is_technical_session_user(actor):
        return {"success": False, "error": "Nicht authentifiziert."}
    if not check_article_permission(article_id, actor, "assign", allow_admin_override=True):
        return {"success": False, "error": "Keine Berechtigung zum Entziehen von Zugriffsrechten."}
    if not target:
        return {"success": False, "error": "Ungültige Benutzerkennung."}

    with get_db_session() as session:
        existing = session.scalars(
            select(ArticlePermissionModel).where(
                ArticlePermissionModel.article_id == article_id,
                ArticlePermissionModel.user_id == target,
            )
        ).first()
        if not existing:
            return {"success": False, "error": "Keine bestehende Zuordnung gefunden."}

        # Mindestens ein Verantwortlicher oder Admin-Eingriff bleibt gewahrt:
        # Falls der letzte Owner entzogen werden soll, nur erlauben wenn ein Admin handelt oder ein anderer Owner existiert
        if existing.role == "owner" and not is_global_admin(actor):
            other_owners = session.scalar(
                select(func.count(ArticlePermissionModel.id)).where(
                    ArticlePermissionModel.article_id == article_id,
                    ArticlePermissionModel.role == "owner",
                    ArticlePermissionModel.user_id != target,
                )
            )
            if not other_owners:
                return {
                    "success": False,
                    "error": "Der letzte Verantwortliche kann nicht ohne Übertragung entfernt werden.",
                }

        old_role = existing.role
        session.delete(existing)
        record_audit_log(
            session,
            actor_user=actor,
            action="revoke_permission",
            target_user=target,
            article_id=article_id,
            details={"old_role": old_role},
        )

    return {"success": True, "article_id": article_id, "user_id": target, "revoked": True}


def transfer_article_ownership(
    article_id: str,
    new_owner: str,
    actor_user: str,
) -> dict[str, Any]:
    """Überträgt die Verantwortung ('owner') für einen Artikel (auch für verwaiste Artikel durch Admin)."""
    actor = normalize_user_id(actor_user)
    target = normalize_user_id(new_owner)
    if not actor or is_technical_session_user(actor):
        return {"success": False, "error": "Nicht authentifiziert."}
    if not target or is_technical_session_user(target):
        return {"success": False, "error": "Ungültige Ziel-Benutzerkennung."}
    if not check_article_permission(article_id, actor, "assign", allow_admin_override=True):
        return {"success": False, "error": "Keine Berechtigung zum Übertragen der Verantwortung."}

    with get_db_session() as session:
        art = session.get(ArticleModel, article_id)
        if not art:
            return {"success": False, "error": "Artikel nicht gefunden."}

        perms = session.scalars(
            select(ArticlePermissionModel).where(ArticlePermissionModel.article_id == article_id)
        ).all()
        target_perm = None
        for p in perms:
            if p.user_id == target:
                p.role = "owner"
                p.granted_by = actor
                target_perm = p
            elif p.role == "owner":
                p.role = "editor"

        if target_perm is None:
            session.add(
                ArticlePermissionModel(
                    article_id=article_id,
                    user_id=target,
                    role="owner",
                    granted_by=actor,
                )
            )

        record_audit_log(
            session,
            actor_user=actor,
            action="transfer_ownership",
            target_user=target,
            article_id=article_id,
            details={"new_owner": target},
        )

    return {"success": True, "article_id": article_id, "new_owner": target}


def set_global_user_role(
    target_user: str,
    *,
    is_admin: bool,
    can_publish: bool,
    actor_user: str,
    display_name: str = "",
) -> dict[str, Any]:
    """Setzt globale Rechte (Admin und Publizieren getrennt) für einen Benutzer und protokolliert dies."""
    actor = normalize_user_id(actor_user)
    target = normalize_user_id(target_user)
    if not actor or not is_global_admin(actor):
        return {"success": False, "error": "Nur Administratoren dürfen globale Rollen ändern."}
    if not target or is_technical_session_user(target):
        return {"success": False, "error": "Ungültige Benutzerkennung."}

    with get_db_session() as session:
        row = session.get(UserRoleModel, target)
        old_state = (
            {"is_admin": bool(row.is_admin), "can_publish": bool(row.can_publish)}
            if row
            else None
        )
        if row:
            row.is_admin = bool(is_admin)
            row.can_publish = bool(can_publish)
            if display_name:
                row.display_name = display_name.strip()
            row.updated_by = actor
        else:
            session.add(
                UserRoleModel(
                    user_id=target,
                    display_name=(display_name or target).strip(),
                    is_admin=bool(is_admin),
                    can_publish=bool(can_publish),
                    updated_by=actor,
                )
            )
        record_audit_log(
            session,
            actor_user=actor,
            action="set_user_role",
            target_user=target,
            details={
                "old": old_state,
                "new": {"is_admin": bool(is_admin), "can_publish": bool(can_publish)},
            },
        )
    return {
        "success": True,
        "user_id": target,
        "is_admin": bool(is_admin),
        "can_publish": bool(can_publish),
    }


def list_known_users() -> list[dict[str, Any]]:
    """Liefert alle bekannten Benutzerkennungen aus DB-Rollen, Artikelzuordnungen und Env-Konfiguration."""
    users_map: dict[str, dict[str, Any]] = {}
    for uid in PORTAL_ADMINS:
        if not is_technical_session_user(uid):
            users_map[uid] = {
                "user_id": uid,
                "display_name": uid,
                "is_admin": True,
                "can_publish": uid in PORTAL_PUBLISHERS,
                "source": "env",
            }
    for uid in PORTAL_PUBLISHERS:
        if not is_technical_session_user(uid):
            entry = users_map.setdefault(
                uid,
                {
                    "user_id": uid,
                    "display_name": uid,
                    "is_admin": False,
                    "can_publish": True,
                    "source": "env",
                },
            )
            entry["can_publish"] = True

    with get_db_session() as session:
        for r in session.scalars(select(UserRoleModel)).all():
            entry = users_map.setdefault(
                r.user_id,
                {
                    "user_id": r.user_id,
                    "display_name": r.display_name or r.user_id,
                    "is_admin": False,
                    "can_publish": False,
                    "source": "db",
                },
            )
            entry["is_admin"] = bool(entry["is_admin"] or r.is_admin)
            entry["can_publish"] = bool(entry["can_publish"] or r.can_publish)
            if r.display_name:
                entry["display_name"] = r.display_name

        perm_users = session.scalars(select(ArticlePermissionModel.user_id).distinct()).all()
        for uid in perm_users:
            if uid and not is_technical_session_user(uid) and uid not in users_map:
                users_map[uid] = {
                    "user_id": uid,
                    "display_name": uid,
                    "is_admin": False,
                    "can_publish": False,
                    "source": "article_perm",
                }

    return sorted(users_map.values(), key=lambda x: x["user_id"])


def list_review_assignments(user_id: str | None) -> list[dict[str, Any]]:
    """
    Liefert für Prüfberechtigte die ihnen zugeteilten Artikel mit Stand und Status.
    """
    uid = normalize_user_id(user_id)
    if not uid or is_technical_session_user(uid):
        return []

    with get_db_session() as session:
        stmt = (
            select(
                ArticleModel.id,
                ArticleModel.title,
                ArticleModel.status,
                ArticleModel.template_id,
                ArticleModel.version,
                ArticleModel.updated_at,
                ArticleModel.updated_by,
                ArticleModel.submitted_revision_id,
                ArticleModel.submitted_by,
                ArticleModel.approved_revision_id,
                ArticleModel.approved_by,
                ArticlePermissionModel.role,
            )
            .join(ArticlePermissionModel, ArticlePermissionModel.article_id == ArticleModel.id)
            .where(
                ArticlePermissionModel.user_id == uid,
                ArticlePermissionModel.role.in_(["reviewer", "owner"]),
                ArticleModel.status != "archived",
            )
            .order_by(desc(ArticleModel.updated_at))
        )
        rows = session.execute(stmt).all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "template_id": r.template_id,
                "version": int(r.version or 1),
                "article_role": r.role,
                "updated_at": r.updated_at.strftime("%d.%m.%Y %H:%M") if r.updated_at else "",
                "updated_by": r.updated_by or "",
                "submitted_revision_id": r.submitted_revision_id,
                "submitted_by": r.submitted_by or "",
                "approved_revision_id": r.approved_revision_id,
                "approved_by": r.approved_by or "",
            }
            for r in rows
        ]


def list_admin_articles(
    search_query: str = "",
    *,
    only_orphans: bool = False,
) -> list[dict[str, Any]]:
    """
    Liefert für das Admin-Dashboard alle Artikel inklusive Zuordnungsstatus ('is_orphan')
    und zugewiesenen Benutzern.
    """
    with get_db_session() as session:
        stmt = select(ArticleModel).order_by(desc(ArticleModel.updated_at))
        if search_query and search_query.strip():
            q = f"%{search_query.strip()}%"
            stmt = stmt.where(
                or_(
                    ArticleModel.title.ilike(q),
                    ArticleModel.subtitle.ilike(q),
                    ArticleModel.category.ilike(q),
                    ArticleModel.updated_by.ilike(q),
                )
            )
        articles = session.scalars(stmt).all()
        aids = [a.id for a in articles]

        perms_by_aid: dict[str, list[dict[str, str]]] = {}
        if aids:
            perm_rows = session.scalars(
                select(ArticlePermissionModel).where(ArticlePermissionModel.article_id.in_(aids))
            ).all()
            for p in perm_rows:
                perms_by_aid.setdefault(p.article_id, []).append(
                    {"user_id": p.user_id, "role": p.role}
                )

        res: list[dict[str, Any]] = []
        for a in articles:
            perms = perms_by_aid.get(a.id, [])
            is_orphan = len(perms) == 0
            if only_orphans and not is_orphan:
                continue
            res.append(
                {
                    "id": a.id,
                    "title": a.title,
                    "status": a.status,
                    "version": int(a.version or 1),
                    "updated_at": a.updated_at.strftime("%d.%m.%Y %H:%M") if a.updated_at else "",
                    "updated_by": a.updated_by or "",
                    "permissions": perms,
                    "is_orphan": is_orphan,
                }
            )
        return res


def list_audit_log(limit: int = 100) -> list[dict[str, Any]]:
    """Liefert die jüngsten Audit-Einträge (Zuweisungs- und Rollenänderungen)."""
    with get_db_session() as session:
        rows = session.scalars(
            select(AuditLogModel).order_by(desc(AuditLogModel.created_at), desc(AuditLogModel.id)).limit(limit)
        ).all()
        res: list[dict[str, Any]] = []
        for r in rows:
            try:
                details = json.loads(r.details_json or "{}")
            except Exception:
                details = {}
            res.append(
                {
                    "id": r.id,
                    "created_at": r.created_at.strftime("%d.%m.%Y %H:%M:%S") if r.created_at else "",
                    "actor_user": r.actor_user,
                    "action": r.action,
                    "target_user": r.target_user or "",
                    "article_id": r.article_id or "",
                    "details": details,
                }
            )
        return res
