"""
services/publication_service.py
===============================
Orchestrierung von Einreichung, Freigabe (inkl. Vier-Augen-Regel), Publikationsaufträgen,
Connect-Task-Verfolgung, Retry und Rückzug (Etappe 2).
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select, update

from config import STATIC_PORTAL_DIR, normalize_user_id, requires_four_eyes
from database.connection import get_db_session
from database.models import (
    ArticleModel,
    ArticleRevisionModel,
    PublicationJobModel,
    PublishedSnapshotModel,
)
from database.permissions import record_audit_log
from database.repository import (
    _row_to_document,
    compute_article_content_hash,
)
from schemas.article import ArticleDocument
from services.connect_client import (
    deploy_bundle_to_connect,
    is_connect_configured,
    poll_connect_task,
)
from services.portal_publisher import (
    _PORTAL_PUBLISH_LOCK,
    _ensure_portal_assets,
    _inject_portal_nav,
    _make_article_slug,
    _render_portal_index,
    _write_bytes_if_changed,
    _write_connect_manifest,
    _write_manifest,
    _write_text_if_changed,
    create_connect_bundle,
)
from services.renderer import format_publication_date, render_publication_package

logger = logging.getLogger(__name__)

ACTIVE_JOB_STATUSES = ("pending", "rendering", "uploading", "deploying", "unknown")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_bytes(data: bytes | None) -> str | None:
    if data is None:
        return None
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def submit_article_for_review(article_id: str, user_id: str) -> dict[str, Any]:
    """
    Speichert eine konkrete Revision und markiert den Artikel als zur Prüfung eingereicht.
    """
    uid = normalize_user_id(user_id) or str(user_id)
    now = _utc_now()
    with get_db_session() as session:
        row = session.get(ArticleModel, article_id)
        if not row:
            return {"success": False, "error": "Artikel nicht gefunden."}

        doc = _row_to_document(row)
        doc.status = "review"
        row.status = "review"
        row.version = int(row.version or 1) + 1
        row.content_hash = compute_article_content_hash(doc)
        row.updated_at = now
        row.updated_by = user_id

        doc.version = row.version
        rev = ArticleRevisionModel(
            article_id=article_id,
            snapshot_json=doc.model_dump_json(),
            saved_at=now,
            saved_by=uid,
            note="Zur Prüfung / Freigabe eingereicht (Status: review)",
        )
        session.add(rev)
        session.flush()

        row.submitted_revision_id = rev.id
        row.submitted_by = uid

        record_audit_log(
            session,
            actor_user=uid,
            action="submit_review",
            article_id=article_id,
            details={"revision_id": rev.id, "version": row.version},
        )
        return {
            "success": True,
            "article_id": article_id,
            "revision_id": rev.id,
            "doc": doc,
        }


def approve_article_revision(
    article_id: str,
    revision_id: int,
    user_id: str,
) -> dict[str, Any]:
    """
    Gibt eine konkrete Revision frei. Bei Formaten mit Vier-Augen-Regel prüft der Server
    die Kontentrennung zwischen Einreicher/Autor und Freigeber.
    """
    approver = normalize_user_id(user_id)
    now = _utc_now()
    with get_db_session() as session:
        row = session.get(ArticleModel, article_id)
        if not row:
            return {"success": False, "error": "Artikel nicht gefunden."}
        rev = session.get(ArticleRevisionModel, revision_id)
        if not rev or rev.article_id != article_id:
            return {"success": False, "error": f"Revision #{revision_id} nicht gefunden."}

        if requires_four_eyes(row.template_id):
            submitter = normalize_user_id(getattr(row, "submitted_by", None) or rev.saved_by)
            if submitter and submitter == approver:
                return {
                    "success": False,
                    "error": (
                        f"Vier-Augen-Regel: Format '{row.template_id}' erfordert eine Freigabe "
                        "durch ein zweites Konto (getrennt vom Einreicher/Autor)."
                    ),
                }

        row.approved_revision_id = rev.id
        row.approved_by = approver
        row.approved_at = now
        record_audit_log(
            session,
            actor_user=approver,
            action="approve_revision",
            article_id=article_id,
            details={"revision_id": rev.id},
        )
        return {
            "success": True,
            "article_id": article_id,
            "revision_id": rev.id,
            "approved_by": approver,
        }


def build_portal_directory_from_snapshots(
    target_dir: Path,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Baut ein vollständiges statisches Portalverzeichnis in `target_dir` ausschliesslich
    aus der übergebenen Liste von Snapshots auf (ohne Rückgriff auf alte lokale Dateien).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    _ensure_portal_assets(target_dir)

    manifest: dict[str, Any] = {
        "articles": {},
        "last_updated": _utc_now().isoformat(),
    }

    for snap in snapshots:
        slug = snap.get("slug")
        if not slug:
            continue
        article_dir = target_dir / "articles" / slug
        article_dir.mkdir(parents=True, exist_ok=True)

        _write_text_if_changed(article_dir / "index.html", snap.get("html_content") or "", encoding="utf-8")

        has_pdf = False
        pdf_bytes = snap.get("pdf_bytes")
        if pdf_bytes:
            _write_bytes_if_changed(article_dir / f"{slug}.pdf", pdf_bytes)
            has_pdf = True

        meta = dict(snap.get("metadata") or {})
        meta["id"] = snap.get("article_id")
        meta["slug"] = slug
        meta["title"] = snap.get("title")
        meta["has_pdf"] = has_pdf
        manifest["articles"][snap["article_id"]] = meta

    _write_manifest(target_dir, manifest)
    _render_portal_index(target_dir, manifest)
    _write_connect_manifest(target_dir)
    return manifest


def _load_active_snapshots_for_bundle(
    session,
    *,
    include_snapshot_id: int | None = None,
    exclude_article_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Lädt die vorgesehenen Snapshots für den frischen Portal-Build:
    - Alle aktuell aktiven Snapshots (ausser `exclude_article_id` und ggf. älterer Snapshot
      des neu zu publizierenden Artikels)
    - Plus optional `include_snapshot_id` (der neu gerenderte Staging-Snapshot).
    """
    rows = session.scalars(
        select(PublishedSnapshotModel)
        .where(PublishedSnapshotModel.is_active == True)
        .order_by(desc(PublishedSnapshotModel.publication_date), desc(PublishedSnapshotModel.published_at))
    ).all()

    include_row: PublishedSnapshotModel | None = None
    include_aid: str | None = None
    if include_snapshot_id is not None:
        include_row = session.get(PublishedSnapshotModel, include_snapshot_id)
        if include_row:
            include_aid = include_row.article_id

    selected: list[PublishedSnapshotModel] = []
    for r in rows:
        if exclude_article_id and r.article_id == exclude_article_id:
            continue
        if include_aid and r.article_id == include_aid:
            continue
        selected.append(r)

    if include_row is not None:
        selected.insert(0, include_row)

    result: list[dict[str, Any]] = []
    for r in selected:
        try:
            meta = json.loads(r.metadata_json or "{}")
        except Exception:
            meta = {}
        result.append(
            {
                "id": r.id,
                "article_id": r.article_id,
                "version": r.version,
                "slug": r.slug,
                "title": r.title,
                "publication_date": r.publication_date,
                "metadata": meta,
                "html_content": r.html_content,
                "pdf_bytes": r.pdf_bytes,
            }
        )
    return result


def _sync_local_portal_dir(snapshots: list[dict[str, Any]]) -> None:
    """Aktualisiert `STATIC_PORTAL_DIR` atomar/frisch auf Basis bestätigter Snapshots."""
    with _PORTAL_PUBLISH_LOCK:
        if STATIC_PORTAL_DIR.exists():
            shutil.rmtree(STATIC_PORTAL_DIR, ignore_errors=True)
        build_portal_directory_from_snapshots(STATIC_PORTAL_DIR, snapshots)


def _finalize_publish_success(job_id: int) -> dict[str, Any]:
    """Verbucht den Wechsel auf 'Live' erst nach bestätigtem Connect-Erfolg (idempotent)."""
    now = _utc_now()
    with get_db_session() as session:
        job = session.get(PublicationJobModel, job_id)
        if not job:
            return {"success": False, "error": "Auftrag nicht gefunden."}
        if job.status == "succeeded":
            return {"success": True, "already_completed": True, "job_id": job.id, "snapshot_id": job.snapshot_id}

        snap = session.get(PublishedSnapshotModel, job.snapshot_id) if job.snapshot_id else None
        if not snap:
            return {"success": False, "error": "Zugehöriger Snapshot fehlt."}

        # Vorherige aktive Snapshots dieses Artikels deaktivieren und neuen aktivieren
        session.execute(
            update(PublishedSnapshotModel)
            .where(
                PublishedSnapshotModel.article_id == job.article_id,
                PublishedSnapshotModel.id != snap.id,
                PublishedSnapshotModel.is_active == True,
            )
            .values(is_active=False)
        )
        snap.is_active = True

        art = session.get(ArticleModel, job.article_id)
        if art:
            art.live_snapshot_id = snap.id
            art.status = "published"

        job.status = "succeeded"
        job.error_message = None
        job.completed_at = now

        snapshots_for_local = _load_active_snapshots_for_bundle(session)
        record_audit_log(
            session,
            actor_user=job.requested_by,
            action="publish_succeeded",
            article_id=job.article_id,
            details={"job_id": job.id, "snapshot_id": snap.id, "revision_id": job.revision_id},
        )

    _sync_local_portal_dir(snapshots_for_local)
    return {
        "success": True,
        "deployed": is_connect_configured(),
        "job_id": job_id,
        "snapshot_id": snap.id,
        "total_published": len(snapshots_for_local),
    }


def _finalize_unpublish_success(job_id: int, new_status: str = "draft") -> dict[str, Any]:
    """Verbucht den Rückzug erst nach bestätigtem Connect-Erfolg (idempotent)."""
    now = _utc_now()
    with get_db_session() as session:
        job = session.get(PublicationJobModel, job_id)
        if not job:
            return {"success": False, "error": "Auftrag nicht gefunden."}
        if job.status == "succeeded":
            return {"success": True, "already_completed": True, "job_id": job.id}

        session.execute(
            update(PublishedSnapshotModel)
            .where(
                PublishedSnapshotModel.article_id == job.article_id,
                PublishedSnapshotModel.is_active == True,
            )
            .values(is_active=False)
        )
        art = session.get(ArticleModel, job.article_id)
        if art:
            art.live_snapshot_id = None
            art.status = new_status

        job.status = "succeeded"
        job.error_message = None
        job.completed_at = now

        snapshots_for_local = _load_active_snapshots_for_bundle(session)
        record_audit_log(
            session,
            actor_user=job.requested_by,
            action="unpublish_succeeded",
            article_id=job.article_id,
            details={"job_id": job.id},
        )

    _sync_local_portal_dir(snapshots_for_local)
    return {
        "success": True,
        "deployed": is_connect_configured(),
        "job_id": job_id,
        "total_published": len(snapshots_for_local),
    }


def _has_active_job_for_channel(session, target_channel: str, exclude_job_id: int | None = None) -> PublicationJobModel | None:
    stmt = select(PublicationJobModel).where(
        PublicationJobModel.target_channel == target_channel,
        PublicationJobModel.status.in_(ACTIVE_JOB_STATUSES),
    )
    if exclude_job_id is not None:
        stmt = stmt.where(PublicationJobModel.id != exclude_job_id)
    return session.scalars(stmt).first()


def _run_publish_job_internal(job_id: int) -> dict[str, Any]:
    """Führt Rendering, Staging-Snapshot, frischen Bundle-Build und optionales Connect-Deployment für `job_id` aus."""
    with get_db_session() as session:
        job = session.get(PublicationJobModel, job_id)
        if not job:
            return {"success": False, "error": "Auftrag nicht gefunden."}
        rev = session.get(ArticleRevisionModel, job.revision_id) if job.revision_id else None
        if not rev:
            job.status = "failed"
            job.error_message = f"Revision #{job.revision_id} nicht gefunden."
            return {"success": False, "error": job.error_message, "job_id": job.id}

        rev_doc = ArticleDocument.model_validate_json(rev.snapshot_json)
        job.status = "rendering"

    # Rendern mit identischem Marktdatenstand für PDF und HTML
    pdf_bytes, base_html = render_publication_package(rev_doc)
    slug = _make_article_slug(rev_doc)
    has_pdf = bool(pdf_bytes)
    full_html = _inject_portal_nav(base_html, slug, has_pdf)
    html_sha = _sha256_text(full_html)
    pdf_sha = _sha256_bytes(pdf_bytes)
    c_hash = compute_article_content_hash(rev_doc)

    date_display = (
        format_publication_date(rev_doc.metadata.publication_date)
        or rev_doc.metadata.publication_date
        or "Aktuell"
    )
    authors_str = " · ".join([a.name for a in rev_doc.metadata.authors])
    tags_list = [str(t).strip() for t in (rev_doc.metadata.tags or []) if str(t).strip()]
    meta_entry = {
        "id": rev_doc.id,
        "slug": slug,
        "title": rev_doc.metadata.title,
        "subtitle": rev_doc.metadata.subtitle,
        "lead": rev_doc.metadata.lead,
        "category": rev_doc.metadata.category or "",
        "template_id": rev_doc.template_id,
        "publication_date": rev_doc.metadata.publication_date,
        "date_display": date_display,
        "authors": [a.model_dump() for a in rev_doc.metadata.authors],
        "authors_str": authors_str,
        "tags": tags_list,
        "tags_str": ", ".join(tags_list),
        "published_at": _utc_now().isoformat(),
        "has_pdf": has_pdf,
    }

    with get_db_session() as session:
        job = session.get(PublicationJobModel, job_id)
        max_ver = session.scalars(
            select(PublishedSnapshotModel.version)
            .where(PublishedSnapshotModel.article_id == job.article_id)
            .order_by(desc(PublishedSnapshotModel.version))
            .limit(1)
        ).first() or 0
        next_ver = int(max_ver) + 1

        snap = PublishedSnapshotModel(
            article_id=job.article_id,
            version=next_ver,
            is_active=False,  # Erst nach bestätigtem Connect-Erfolg aktiv!
            slug=slug,
            title=rev_doc.metadata.title,
            publication_date=rev_doc.metadata.publication_date or "",
            metadata_json=json.dumps(meta_entry, ensure_ascii=False),
            html_content=full_html,
            pdf_bytes=pdf_bytes if has_pdf else None,
            published_by=job.requested_by,
            change_note=f"Auftrag #{job.id} (Revision #{job.revision_id})",
            revision_id=job.revision_id,
            content_hash=c_hash,
            html_sha256=html_sha,
            pdf_sha256=pdf_sha,
        )
        session.add(snap)
        session.flush()

        job.snapshot_id = snap.id
        job.html_sha256 = html_sha
        job.pdf_sha256 = pdf_sha
        job.status = "uploading"

        bundle_snapshots = _load_active_snapshots_for_bundle(session, include_snapshot_id=snap.id)

    # Frisches Verzeichnis für Bundle-Erstellung verwenden
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        fresh_dir = Path(tmp_dir_str) / "fresh_portal"
        build_portal_directory_from_snapshots(fresh_dir, bundle_snapshots)
        bundle_path = Path(tmp_dir_str) / "portal_bundle.tar.gz"
        create_connect_bundle(output_dir=fresh_dir, bundle_path=bundle_path)

        if not is_connect_configured():
            return _finalize_publish_success(job_id)

        deploy_res = deploy_bundle_to_connect(bundle_path)

    state_str = deploy_res.get("state") or ("succeeded" if deploy_res.get("deployed") else "failed")
    bundle_id = deploy_res.get("bundle_id")
    task_id = deploy_res.get("task_id")

    if state_str == "succeeded" and deploy_res.get("deployed"):
        with get_db_session() as session:
            job = session.get(PublicationJobModel, job_id)
            if job:
                job.connect_bundle_id = str(bundle_id) if bundle_id else None
                job.connect_task_id = str(task_id) if task_id else None
        res = _finalize_publish_success(job_id)
        res["connect_deploy"] = deploy_res
        return res

    with get_db_session() as session:
        job = session.get(PublicationJobModel, job_id)
        if job:
            job.connect_bundle_id = str(bundle_id) if bundle_id else None
            job.connect_task_id = str(task_id) if task_id else None
            job.status = "unknown" if state_str == "unknown" else "failed"
            job.error_message = deploy_res.get("error") or "Connect Deployment nicht bestätigt."

    return {
        "success": False,
        "deployed": False,
        "state": state_str,
        "job_id": job_id,
        "error": deploy_res.get("error") or "Connect Deployment nicht bestätigt.",
        "connect_deploy": deploy_res,
    }


def execute_publish_job(
    article_id: str,
    user_id: str,
    *,
    revision_id: int | None = None,
    target_channel: str = "intranet_portal",
    change_note: str = "",
) -> dict[str, Any]:
    """
    Startet und führt einen Publikationsauftrag aus:
    - Erzwingt höchstens einen aktiven Auftrag pro `target_channel`
    - Prüft Freigabe / Vier-Augen-Regel
    - Rendert aus konkreter Revision, archiviert Prüfsummen und bestätigt Live erst nach Connect-Erfolg.
    """
    uid = normalize_user_id(user_id) or str(user_id)
    with get_db_session() as session:
        active = _has_active_job_for_channel(session, target_channel)
        if active is not None:
            return {
                "success": False,
                "error": f"Für Zielkanal '{target_channel}' läuft bereits ein aktiver Auftrag (#{active.id}, Status: {active.status}).",
                "active_job_id": active.id,
            }

        row = session.get(ArticleModel, article_id)
        if not row:
            return {"success": False, "error": f"Artikel {article_id} nicht gefunden."}

        target_rev_id = revision_id or getattr(row, "approved_revision_id", None)
        if target_rev_id is None:
            # Falls direkt publiziert wird: aktuelle Version als Revision sichern
            doc = _row_to_document(row)
            rev = ArticleRevisionModel(
                article_id=article_id,
                snapshot_json=doc.model_dump_json(),
                saved_at=_utc_now(),
                saved_by=uid,
                note=change_note or "Publikations-Revision",
            )
            session.add(rev)
            session.flush()
            target_rev_id = rev.id

        rev = session.get(ArticleRevisionModel, target_rev_id)
        if not rev or rev.article_id != article_id:
            return {"success": False, "error": f"Revision #{target_rev_id} nicht gefunden."}

        # Vier-Augen-Prüfung auch bei direkter Publikation durchsetzen
        if requires_four_eyes(row.template_id):
            approved_by = normalize_user_id(getattr(row, "approved_by", None))
            submitter = normalize_user_id(getattr(row, "submitted_by", None) or rev.saved_by)
            if getattr(row, "approved_revision_id", None) != target_rev_id:
                if submitter and submitter == uid:
                    return {
                        "success": False,
                        "error": (
                            f"Vier-Augen-Regel: Format '{row.template_id}' erfordert eine Freigabe "
                            "durch ein zweites Konto vor der Publikation."
                        ),
                    }
                row.approved_revision_id = target_rev_id
                row.approved_by = uid
                row.approved_at = _utc_now()
            elif approved_by and submitter and approved_by == submitter:
                return {
                    "success": False,
                    "error": f"Vier-Augen-Regel verletzt: Einreicher und Freigeber sind identisch ({approved_by}).",
                }

        job = PublicationJobModel(
            article_id=article_id,
            revision_id=target_rev_id,
            action="publish",
            target_channel=target_channel,
            status="pending",
            attempt=1,
            requested_by=uid,
        )
        session.add(job)
        session.flush()
        job_id = job.id

    return _run_publish_job_internal(job_id)


def execute_unpublish_job(
    article_id: str,
    user_id: str,
    *,
    target_channel: str = "intranet_portal",
    new_status: str = "draft",
) -> dict[str, Any]:
    """
    Zieht einen Artikel vom Portal zurück, indem ein frisches Bundle ohne `article_id`
    aufgebaut und an Connect ausgeliefert wird. Funktioniert auch bei fehlendem lokalem Index.
    """
    uid = normalize_user_id(user_id) or str(user_id)
    with get_db_session() as session:
        active = _has_active_job_for_channel(session, target_channel)
        if active is not None:
            return {
                "success": False,
                "error": f"Für Zielkanal '{target_channel}' läuft bereits ein aktiver Auftrag (#{active.id}, Status: {active.status}).",
                "active_job_id": active.id,
            }
        job = PublicationJobModel(
            article_id=article_id,
            action="unpublish",
            target_channel=target_channel,
            status="uploading",
            attempt=1,
            requested_by=uid,
        )
        session.add(job)
        session.flush()
        job_id = job.id
        bundle_snapshots = _load_active_snapshots_for_bundle(session, exclude_article_id=article_id)

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        fresh_dir = Path(tmp_dir_str) / "fresh_portal"
        build_portal_directory_from_snapshots(fresh_dir, bundle_snapshots)
        bundle_path = Path(tmp_dir_str) / "portal_bundle.tar.gz"
        create_connect_bundle(output_dir=fresh_dir, bundle_path=bundle_path)

        if not is_connect_configured():
            return _finalize_unpublish_success(job_id, new_status=new_status)

        deploy_res = deploy_bundle_to_connect(bundle_path)

    state_str = deploy_res.get("state") or ("succeeded" if deploy_res.get("deployed") else "failed")
    bundle_id = deploy_res.get("bundle_id")
    task_id = deploy_res.get("task_id")

    if state_str == "succeeded" and deploy_res.get("deployed"):
        with get_db_session() as session:
            job = session.get(PublicationJobModel, job_id)
            if job:
                job.connect_bundle_id = str(bundle_id) if bundle_id else None
                job.connect_task_id = str(task_id) if task_id else None
        res = _finalize_unpublish_success(job_id, new_status=new_status)
        res["connect_deploy"] = deploy_res
        return res

    with get_db_session() as session:
        job = session.get(PublicationJobModel, job_id)
        if job:
            job.connect_bundle_id = str(bundle_id) if bundle_id else None
            job.connect_task_id = str(task_id) if task_id else None
            job.status = "unknown" if state_str == "unknown" else "failed"
            job.error_message = deploy_res.get("error") or "Connect Rückzug nicht bestätigt."

    return {
        "success": False,
        "deployed": False,
        "state": state_str,
        "job_id": job_id,
        "error": deploy_res.get("error") or "Connect Rückzug nicht bestätigt.",
        "connect_deploy": deploy_res,
    }


def poll_publication_job(job_id: int) -> dict[str, Any]:
    """
    Verfolgt einen offenen/unklaren Auftrag anhand derselben `connect_task_id` weiter.
    Idempotent: abgeschlossene Aufträge werden nicht erneut verbucht.
    """
    with get_db_session() as session:
        job = session.get(PublicationJobModel, job_id)
        if not job:
            return {"success": False, "error": "Auftrag nicht gefunden."}
        if job.status == "succeeded":
            return {"success": True, "already_completed": True, "job_id": job.id}
        if not job.connect_task_id:
            return {"success": False, "error": "Auftrag besitzt keine Connect Task-ID."}
        task_id = job.connect_task_id
        action = job.action

    task_res = poll_connect_task(task_id, max_polls=3, interval_sec=0.5)
    if task_res["state"] == "succeeded":
        if action == "unpublish":
            return _finalize_unpublish_success(job_id)
        return _finalize_publish_success(job_id)

    if task_res["state"] == "failed":
        with get_db_session() as session:
            job = session.get(PublicationJobModel, job_id)
            if job and job.status != "succeeded":
                job.status = "failed"
                job.error_message = task_res.get("error")
        return {"success": False, "state": "failed", "job_id": job_id, "error": task_res.get("error")}

    return {"success": False, "state": "unknown", "job_id": job_id, "error": task_res.get("error")}


def retry_publication_job(job_id: int, user_id: str) -> dict[str, Any]:
    """Wiederholt einen fehlgeschlagenen Publikationsauftrag mit derselben Revision."""
    uid = normalize_user_id(user_id) or str(user_id)
    with get_db_session() as session:
        job = session.get(PublicationJobModel, job_id)
        if not job:
            return {"success": False, "error": "Auftrag nicht gefunden."}
        if job.status != "failed":
            return {"success": False, "error": f"Nur fehlgeschlagene Aufträge können wiederholt werden (Status: {job.status})."}
        active = _has_active_job_for_channel(session, job.target_channel, exclude_job_id=job.id)
        if active is not None:
            return {"success": False, "error": f"Für '{job.target_channel}' läuft bereits Auftrag #{active.id}."}

        job.attempt = int(job.attempt or 1) + 1
        job.status = "pending"
        job.error_message = None
        job.connect_bundle_id = None
        job.connect_task_id = None
        job.requested_by = uid
        action = job.action
        article_id = job.article_id

    if action == "unpublish":
        with get_db_session() as session:
            bundle_snapshots = _load_active_snapshots_for_bundle(session, exclude_article_id=article_id)
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            fresh_dir = Path(tmp_dir_str) / "fresh_portal"
            build_portal_directory_from_snapshots(fresh_dir, bundle_snapshots)
            bundle_path = Path(tmp_dir_str) / "portal_bundle.tar.gz"
            create_connect_bundle(output_dir=fresh_dir, bundle_path=bundle_path)
            if not is_connect_configured():
                return _finalize_unpublish_success(job_id)
            deploy_res = deploy_bundle_to_connect(bundle_path)
        if deploy_res.get("state") == "succeeded" and deploy_res.get("deployed"):
            return _finalize_unpublish_success(job_id)
        return {"success": False, "job_id": job_id, "error": deploy_res.get("error")}

    return _run_publish_job_internal(job_id)


def list_publication_jobs(limit: int = 40) -> list[dict[str, Any]]:
    """Liefert die jüngsten Publikations- und Rückzugsaufträge für das Admin-Dashboard."""
    with get_db_session() as session:
        rows = session.scalars(
            select(PublicationJobModel).order_by(desc(PublicationJobModel.id)).limit(limit)
        ).all()
        return [
            {
                "id": j.id,
                "article_id": j.article_id,
                "revision_id": j.revision_id,
                "snapshot_id": j.snapshot_id,
                "action": j.action,
                "target_channel": j.target_channel,
                "status": j.status,
                "attempt": j.attempt,
                "connect_bundle_id": j.connect_bundle_id or "",
                "connect_task_id": j.connect_task_id or "",
                "html_sha256": j.html_sha256 or "",
                "pdf_sha256": j.pdf_sha256 or "",
                "error_message": j.error_message or "",
                "requested_by": j.requested_by,
                "created_at": j.created_at.strftime("%d.%m.%Y %H:%M:%S") if j.created_at else "",
            }
            for j in rows
        ]


def get_admin_publication_overview() -> list[dict[str, Any]]:
    """
    Liefert pro Artikel: Entwurfsstand, freigegebene Revision, Live-Fassung,
    Hinweis auf neuere Entwürfe (via content_hash) und jüngsten Auftrag.
    """
    with get_db_session() as session:
        articles = session.scalars(
            select(ArticleModel).where(ArticleModel.status != "archived").order_by(desc(ArticleModel.updated_at))
        ).all()
        snaps = session.scalars(
            select(PublishedSnapshotModel).where(PublishedSnapshotModel.is_active == True)
        ).all()
        live_by_aid = {s.article_id: s for s in snaps}

        jobs = session.scalars(select(PublicationJobModel).order_by(desc(PublicationJobModel.id))).all()
        latest_job_by_aid: dict[str, PublicationJobModel] = {}
        for j in jobs:
            if j.article_id not in latest_job_by_aid:
                latest_job_by_aid[j.article_id] = j

        res: list[dict[str, Any]] = []
        for a in articles:
            live_snap = live_by_aid.get(a.id)
            j = latest_job_by_aid.get(a.id)
            art_hash = getattr(a, "content_hash", None) or compute_article_content_hash(_row_to_document(a))
            has_newer_draft = bool(
                live_snap and live_snap.content_hash and art_hash != live_snap.content_hash
            )
            res.append(
                {
                    "article_id": a.id,
                    "title": a.title,
                    "draft_version": int(a.version or 1),
                    "status": a.status,
                    "submitted_revision_id": getattr(a, "submitted_revision_id", None),
                    "approved_revision_id": getattr(a, "approved_revision_id", None),
                    "live_snapshot_id": getattr(a, "live_snapshot_id", None) or (live_snap.id if live_snap else None),
                    "live_version": live_snap.version if live_snap else None,
                    "has_newer_draft": has_newer_draft,
                    "latest_job_id": j.id if j else None,
                    "latest_job_status": j.status if j else "",
                    "latest_job_action": j.action if j else "",
                    "latest_job_error": j.error_message if j else "",
                }
            )
        return res
