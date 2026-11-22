"""
services/media_library.py
=========================
Mediathek für freigegebene Bilder und fertige Charts (Etappe 4).
- Nutzt `io_assets` als unveränderlichen Binärspeicher
- Unterstützt mehrere unveränderliche Dateiversionen pro Mediathek-Eintrag
- Trennt interne vs. externe Nutzungskanäle und prüft diese vor der Publikation
- Lädt bei der Suche nur paginierte Metadaten & kleine Vorschaubilder (kein VARBINARY(MAX))
- Gibt bei der Suche keine Titel oder Links privater Quellartikel aus
"""

from __future__ import annotations

import base64
import html
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, or_, select

from config import can_publish, is_global_admin, normalize_user_id
from database.connection import get_db_session
from database.models import (
    AssetModel,
    MediaEntryModel,
    MediaUsageModel,
    MediaVersionModel,
)
from database.permissions import check_article_permission, get_accessible_article_ids, record_audit_log
from schemas.article import ArticleDocument

logger = logging.getLogger(__name__)

VALID_MEDIA_TYPES = ("image", "chart", "table", "kpi_cards", "media_text")
VALID_CHANNELS = ("internal", "external")
SHAREABLE_BLOCK_TYPES = ("figure", "db_chart", "custom_chart", "table", "media_text", "kpi_cards")
BLOCK_TYPE_TO_MEDIA_TYPE = {
    "figure": "image",
    "db_chart": "chart",
    "custom_chart": "chart",
    "table": "table",
    "kpi_cards": "kpi_cards",
    "media_text": "media_text",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_thumbnail_data_uri(mime_type: str, data: bytes) -> str:
    """Erstellt ein kompaktes Vorschaubild für die Suche (SVGs direkt als Data-URI, Bilder nur wenn klein genug)."""
    if not data:
        return ""
    if mime_type == "image/svg+xml" and len(data) <= 200_000:
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
    if len(data) <= 64_000 and mime_type.startswith("image/"):
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{b64}"
    return ""


def create_media_entry(
    *,
    title: str,
    media_type: str = "image",
    tags: list[str] | None = None,
    source_text: str = "",
    data_as_of: str = "",
    origin_article_id: str | None = None,
    filename: str = "grafik.svg",
    mime_type: str = "image/svg+xml",
    data: bytes = b"",
    user_id: str = "",
    usage_channel: str = "internal",
    thumbnail_data_uri: str | None = None,
) -> dict[str, Any]:
    """Legt einen neuen Mediathek-Eintrag samt erster unveränderlicher Dateiversion (v1) in `io_assets` an."""
    uid = normalize_user_id(user_id) or str(user_id or "system")
    mtype = media_type if media_type in VALID_MEDIA_TYPES else "image"
    channel = usage_channel if usage_channel in VALID_CHANNELS else "internal"
    media_id = f"media_{uuid.uuid4().hex[:12]}"
    asset_id = f"asset_{uuid.uuid4().hex[:12]}"
    thumb = thumbnail_data_uri if thumbnail_data_uri is not None else _build_thumbnail_data_uri(mime_type, data)

    with get_db_session() as session:
        session.add(
            AssetModel(
                id=asset_id,
                article_id=origin_article_id,
                filename=filename,
                mime_type=mime_type,
                data=data,
            )
        )
        session.add(
            MediaEntryModel(
                id=media_id,
                title=title.strip() or filename,
                media_type=mtype,
                tags_json=json.dumps([t.strip() for t in (tags or []) if t and t.strip()], ensure_ascii=False),
                source_text=source_text.strip(),
                data_as_of=data_as_of.strip(),
                origin_article_id=origin_article_id,
                approval_status="private",
                usage_channel=channel,
                created_by=uid,
            )
        )
        session.add(
            MediaVersionModel(
                media_id=media_id,
                version=1,
                asset_id=asset_id,
                thumbnail_data_uri=thumb,
                change_note="Erstversion",
                created_by=uid,
            )
        )
        record_audit_log(
            session,
            actor_user=uid,
            action="media_create",
            article_id=origin_article_id,
            details={"media_id": media_id, "version": 1, "asset_id": asset_id},
        )

    return {
        "success": True,
        "media_id": media_id,
        "version": 1,
        "asset_id": asset_id,
    }


def add_media_version(
    media_id: str,
    *,
    filename: str,
    mime_type: str,
    data: bytes,
    user_id: str,
    change_note: str = "",
    thumbnail_data_uri: str | None = None,
) -> dict[str, Any]:
    """
    Fügt einem Mediathek-Eintrag eine neue unveränderliche Dateiversion hinzu.
    Bestehende Artikelreferenzen bleiben unverändert auf ihrer bisherigen `asset_id`/Version.
    """
    uid = normalize_user_id(user_id)
    new_asset_id = f"asset_{uuid.uuid4().hex[:12]}"
    thumb = thumbnail_data_uri if thumbnail_data_uri is not None else _build_thumbnail_data_uri(mime_type, data)

    with get_db_session() as session:
        entry = session.get(MediaEntryModel, media_id)
        if not entry:
            return {"success": False, "error": "Mediathek-Eintrag nicht gefunden."}
        if entry.origin_article_id and not (
            is_global_admin(uid) or check_article_permission(entry.origin_article_id, uid, "edit")
        ):
            return {"success": False, "error": "Keine Berechtigung zum Aktualisieren dieses Mediathek-Eintrags."}

        max_ver = session.scalar(
            select(func.max(MediaVersionModel.version)).where(MediaVersionModel.media_id == media_id)
        ) or 0
        next_ver = int(max_ver) + 1

        session.add(
            AssetModel(
                id=new_asset_id,
                article_id=entry.origin_article_id,
                filename=filename,
                mime_type=mime_type,
                data=data,
            )
        )
        session.add(
            MediaVersionModel(
                media_id=media_id,
                version=next_ver,
                asset_id=new_asset_id,
                thumbnail_data_uri=thumb,
                change_note=change_note or f"Version {next_ver}",
                created_by=uid,
            )
        )
        entry.updated_at = _utc_now()
        record_audit_log(
            session,
            actor_user=uid,
            action="media_new_version",
            article_id=entry.origin_article_id,
            details={"media_id": media_id, "version": next_ver, "asset_id": new_asset_id},
        )

    return {
        "success": True,
        "media_id": media_id,
        "version": next_ver,
        "asset_id": new_asset_id,
    }


def request_media_release(media_id: str, user_id: str) -> dict[str, Any]:
    """Ein für den Quellartikel Berechtigter stösst die Freigabe für die Mediathek an."""
    uid = normalize_user_id(user_id)
    with get_db_session() as session:
        entry = session.get(MediaEntryModel, media_id)
        if not entry:
            return {"success": False, "error": "Mediathek-Eintrag nicht gefunden."}
        if entry.origin_article_id and not (
            is_global_admin(uid) or check_article_permission(entry.origin_article_id, uid, "edit")
        ):
            return {"success": False, "error": "Keine Berechtigung zum Anstossen der Freigabe."}

        entry.approval_status = "pending"
        entry.requested_by = uid
        entry.updated_at = _utc_now()
        record_audit_log(
            session,
            actor_user=uid,
            action="media_request_release",
            article_id=entry.origin_article_id,
            details={"media_id": media_id},
        )
    return {"success": True, "media_id": media_id, "approval_status": "pending"}


def approve_media_release(
    media_id: str,
    *,
    usage_channel: str,
    user_id: str,
) -> dict[str, Any]:
    """Die dafür vorgesehene Rolle (Publisher/Admin) bestätigt Freigabe und Nutzungskanal."""
    uid = normalize_user_id(user_id)
    if not (can_publish(uid) or is_global_admin(uid)):
        return {"success": False, "error": "Keine Berechtigung zur Mediathek-Freigabe."}
    channel = (usage_channel or "internal").strip().lower()
    if channel not in VALID_CHANNELS:
        return {"success": False, "error": f"Ungültiger Nutzungskanal: {usage_channel}"}

    with get_db_session() as session:
        entry = session.get(MediaEntryModel, media_id)
        if not entry:
            return {"success": False, "error": "Mediathek-Eintrag nicht gefunden."}
        entry.approval_status = "approved"
        entry.usage_channel = channel
        entry.approved_by = uid
        entry.approved_at = _utc_now()
        entry.updated_at = _utc_now()
        record_audit_log(
            session,
            actor_user=uid,
            action="media_approve_release",
            article_id=entry.origin_article_id,
            details={"media_id": media_id, "usage_channel": channel},
        )
    return {"success": True, "media_id": media_id, "approval_status": "approved", "usage_channel": channel}


def revoke_media_release(media_id: str, user_id: str) -> dict[str, Any]:
    """
    Widerruft die Freigabe eines Mediathek-Eintrags:
    - Sperrt neue Verwendungen
    - Liefert alle bestehenden Verwendungen zur Prüfung zurück
    - Bereits ausgelieferte Snapshots bleiben als Nachweis erhalten.
    """
    uid = normalize_user_id(user_id)
    if not (can_publish(uid) or is_global_admin(uid)):
        return {"success": False, "error": "Keine Berechtigung zum Widerrufen einer Freigabe."}

    with get_db_session() as session:
        entry = session.get(MediaEntryModel, media_id)
        if not entry:
            return {"success": False, "error": "Mediathek-Eintrag nicht gefunden."}
        entry.approval_status = "revoked"
        entry.updated_at = _utc_now()

        usages = session.scalars(
            select(MediaUsageModel).where(MediaUsageModel.media_id == media_id)
        ).all()
        usage_list = [
            {
                "article_id": u.article_id,
                "block_id": u.block_id,
                "media_version": u.media_version,
                "asset_id": u.asset_id,
            }
            for u in usages
        ]
        record_audit_log(
            session,
            actor_user=uid,
            action="media_revoke_release",
            article_id=entry.origin_article_id,
            details={"media_id": media_id, "affected_usages": len(usage_list)},
        )

    return {
        "success": True,
        "media_id": media_id,
        "approval_status": "revoked",
        "usages": usage_list,
    }


def search_media_library(
    user_id: str | None,
    *,
    query: str = "",
    media_type: str = "all",
    channel: str = "all",
    page: int = 1,
    page_size: int = 12,
) -> dict[str, Any]:
    """
    Paginierte Metadaten-Suche in der Mediathek (ohne `AssetModel.data` zu laden).
    Gibt niemals Titel oder Links privater Quellartikel an unberechtigte Benutzer aus.
    """
    accessible_aids = get_accessible_article_ids(user_id)
    page_num = max(1, int(page or 1))
    limit = max(1, min(50, int(page_size or 12)))

    with get_db_session() as session:
        stmt = select(MediaEntryModel).order_by(desc(MediaEntryModel.updated_at))
        if media_type in VALID_MEDIA_TYPES:
            stmt = stmt.where(MediaEntryModel.media_type == media_type)
        if channel in VALID_CHANNELS:
            stmt = stmt.where(MediaEntryModel.usage_channel == channel)
        if query and query.strip():
            q = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    MediaEntryModel.title.ilike(q),
                    MediaEntryModel.tags_json.ilike(q),
                    MediaEntryModel.source_text.ilike(q),
                )
            )

        all_entries = session.scalars(stmt).all()
        visible_entries: list[MediaEntryModel] = []
        for e in all_entries:
            if e.approval_status == "approved":
                visible_entries.append(e)
            elif e.origin_article_id and e.origin_article_id in accessible_aids:
                visible_entries.append(e)

        total = len(visible_entries)
        offset = (page_num - 1) * limit
        page_entries = visible_entries[offset : offset + limit]
        mids = [e.id for e in page_entries]

        latest_ver_by_mid: dict[str, MediaVersionModel] = {}
        if mids:
            ver_rows = session.scalars(
                select(MediaVersionModel)
                .where(MediaVersionModel.media_id.in_(mids))
                .order_by(desc(MediaVersionModel.version))
            ).all()
            for vr in ver_rows:
                if vr.media_id not in latest_ver_by_mid:
                    latest_ver_by_mid[vr.media_id] = vr

        items: list[dict[str, Any]] = []
        for e in page_entries:
            lv = latest_ver_by_mid.get(e.id)
            try:
                tags = json.loads(e.tags_json or "[]")
            except Exception:
                tags = []
            # Keine privaten Quellartikel-Referenzen an Unberechtigte leaken
            can_see_origin = bool(e.origin_article_id and e.origin_article_id in accessible_aids)
            items.append(
                {
                    "media_id": e.id,
                    "title": e.title,
                    "media_type": e.media_type,
                    "tags": tags,
                    "source_text": e.source_text,
                    "data_as_of": e.data_as_of,
                    "approval_status": e.approval_status,
                    "usage_channel": e.usage_channel,
                    "origin_article_id": e.origin_article_id if can_see_origin else None,
                    "latest_version": lv.version if lv else 1,
                    "latest_asset_id": lv.asset_id if lv else "",
                    "thumbnail_data_uri": (lv.thumbnail_data_uri or "") if lv else "",
                    "updated_at": e.updated_at.strftime("%d.%m.%Y %H:%M") if e.updated_at else "",
                }
            )

        return {
            "items": items,
            "total": total,
            "page": page_num,
            "page_size": limit,
        }


def sync_article_media_usages(doc: ArticleDocument) -> None:
    """Aktualisiert die Verwendungsnachweise (`io_media_usages`) für einen Artikel."""
    asset_refs: list[tuple[str, str]] = []  # (asset_id, block_id)
    for blk in doc.blocks:
        btype = blk.get("type")
        bid = str(blk.get("id") or "")
        if btype == "figure":
            aid = str(blk.get("asset_id") or "").strip()
            if aid:
                asset_refs.append((aid, bid))
        elif btype == "media_text":
            media = blk.get("media")
            if isinstance(media, dict) and (blk.get("media_type") or media.get("type") or "figure") == "figure":
                aid = str(media.get("asset_id") or "").strip()
                if aid:
                    asset_refs.append((aid, bid))

    with get_db_session() as session:
        old_rows = session.scalars(
            select(MediaUsageModel).where(MediaUsageModel.article_id == doc.id)
        ).all()
        for r in old_rows:
            session.delete(r)

        if not asset_refs:
            return

        aids = [aid for aid, _ in asset_refs]
        ver_rows = session.scalars(
            select(MediaVersionModel).where(MediaVersionModel.asset_id.in_(aids))
        ).all()
        ver_by_asset = {v.asset_id: v for v in ver_rows}

        for aid, bid in asset_refs:
            v = ver_by_asset.get(aid)
            if v is not None:
                session.add(
                    MediaUsageModel(
                        media_id=v.media_id,
                        media_version=v.version,
                        asset_id=aid,
                        article_id=doc.id,
                        block_id=bid,
                    )
                )


def validate_article_media_for_channel(
    doc: ArticleDocument,
    target_channel: str = "intranet_portal",
) -> dict[str, Any]:
    """
    Prüft vor einer Veröffentlichung alle referenzierten Mediathek-Assets:
    - Widerrufene Assets (`revoked`) werden blockiert.
    - Bei externen Zielkanälen (`external`, `external_portal`, `public`) werden
      Assets mit `usage_channel == 'internal'` blockiert.
    """
    is_external = (target_channel or "").strip().lower() in ("external", "external_portal", "public")
    aids: list[str] = []
    for blk in doc.blocks:
        btype = blk.get("type")
        if btype == "figure" and blk.get("asset_id"):
            aids.append(str(blk["asset_id"]).strip())
        elif btype == "media_text":
            media = blk.get("media")
            if isinstance(media, dict) and media.get("asset_id"):
                aids.append(str(media["asset_id"]).strip())

    if not aids:
        return {"valid": True, "errors": []}

    errors: list[str] = []
    with get_db_session() as session:
        ver_rows = session.scalars(
            select(MediaVersionModel).where(MediaVersionModel.asset_id.in_(aids))
        ).all()
        if not ver_rows:
            return {"valid": True, "errors": []}

        mids = {v.media_id for v in ver_rows}
        entries = {
            e.id: e
            for e in session.scalars(select(MediaEntryModel).where(MediaEntryModel.id.in_(mids))).all()
        }
        for v in ver_rows:
            entry = entries.get(v.media_id)
            if not entry:
                continue
            if entry.approval_status == "revoked":
                errors.append(f"Asset «{entry.title}» (v{v.version}) wurde widerrufen und darf nicht publiziert werden.")
            elif is_external and (entry.approval_status != "approved" or entry.usage_channel != "external"):
                errors.append(
                    f"Asset «{entry.title}» (v{v.version}) ist nur für '{entry.usage_channel}' freigegeben "
                    f"(Status: {entry.approval_status}) und darf nicht in eine externe Publikation eingehen."
                )

    return {"valid": len(errors) == 0, "errors": errors}


def get_media_usages(media_id: str) -> list[dict[str, Any]]:
    """Liefert alle bekannten Verwendungen eines Mediathek-Eintrags."""
    with get_db_session() as session:
        rows = session.scalars(
            select(MediaUsageModel).where(MediaUsageModel.media_id == media_id)
        ).all()
        return [
            {
                "media_id": r.media_id,
                "media_version": r.media_version,
                "asset_id": r.asset_id,
                "article_id": r.article_id,
                "block_id": r.block_id,
            }
            for r in rows
        ]


def can_delete_media_version(asset_id: str) -> bool:
    """Prüft vor dem Entfernen einer Dateiversion, ob noch Referenzen existieren."""
    if not asset_id:
        return False
    with get_db_session() as session:
        cnt = session.scalar(
            select(func.count(MediaUsageModel.id)).where(MediaUsageModel.asset_id == asset_id)
        )
        return int(cnt or 0) == 0


def _extract_block_title(block: dict[str, Any]) -> str:
    """Bestimmt einen sprechenden Titel für einen geteilten Inhaltsblock."""
    title = str(block.get("title") or "").strip()
    if title:
        return title
    btype = str(block.get("type") or "").strip()
    if btype == "kpi_cards":
        cards = block.get("cards") or []
        if cards and isinstance(cards[0], dict):
            lbl = str(cards[0].get("label") or cards[0].get("value") or "").strip()
            if lbl:
                return f"KPI: {lbl}"
        return "KPI-Karten"
    labels = {
        "figure": "Abbildung",
        "db_chart": "DB-Chart",
        "custom_chart": "Custom-Chart",
        "table": "Tabelle",
        "media_text": "Media & Text",
    }
    return labels.get(btype, "Vorlage")


def _build_block_preview_svg(block: dict[str, Any]) -> str:
    """Erzeugt ein kompaktes SVG-Vorschaubild für strukturierte Blöcke in der Mediathek."""
    btype = str(block.get("type") or "").strip()
    title = html.escape(_extract_block_title(block)[:34])
    badge_map = {
        "db_chart": ("CHART", "#005A9C", "#EEF3F8"),
        "custom_chart": ("CHART", "#005A9C", "#EEF3F8"),
        "table": ("TABELLE", "#002855", "#EEF3F8"),
        "kpi_cards": ("KPI", "#1B6E4A", "#EAF4EF"),
        "media_text": ("MEDIA", "#6B4E00", "#FAF5E6"),
        "figure": ("BILD", "#002855", "#EEF3F8"),
    }
    badge, accent, bg = badge_map.get(btype, ("BLOCK", "#002855", "#EEF3F8"))
    detail = ""
    if btype == "table":
        rows = block.get("rows") or []
        cols = block.get("columns") or []
        detail = f"{len(cols)} Spalten · {len(rows)} Zeilen"
    elif btype == "kpi_cards":
        cards = block.get("cards") or []
        detail = f"{len(cards)} KPI-Karte(n)"
    elif btype in ("custom_chart", "db_chart"):
        detail = str(block.get("chart_type") or block.get("series_key") or "Diagramm")[:28]
    elif btype == "media_text":
        detail = "Text + Medium"
    detail_esc = html.escape(detail)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="192" height="116" viewBox="0 0 192 116">'
        f'<rect x="1" y="1" width="190" height="114" rx="8" fill="{bg}" stroke="#C2D1E2" stroke-width="1.5"/>'
        f'<rect x="12" y="12" width="64" height="20" rx="4" fill="{accent}"/>'
        f'<text x="44" y="25" text-anchor="middle" font-family="Arial,sans-serif" font-size="10" font-weight="700" fill="#FFFFFF">{badge}</text>'
        f'<text x="12" y="56" font-family="Arial,sans-serif" font-size="12" font-weight="700" fill="#002855">{title}</text>'
        f'<text x="12" y="78" font-family="Arial,sans-serif" font-size="10" fill="#5A687C">{detail_esc}</text>'
        '</svg>'
    )


def _sanitize_shared_block(block: dict[str, Any]) -> dict[str, Any]:
    """Bereitet ein Block-Dict als unabhängige Vorlage ohne Artikel-Bindung auf."""
    clean = json.loads(json.dumps(block, ensure_ascii=False))
    for k in ("id", "anchor_to", "share_in_media_library", "shared_media_id"):
        clean.pop(k, None)
    return clean


def _resolve_block_thumbnail(session: Any, block: dict[str, Any]) -> str:
    """Erstellt das Vorschaubild für einen geteilten Block."""
    btype = str(block.get("type") or "").strip()
    ref_aid = ""
    if btype == "figure":
        ref_aid = str(block.get("asset_id") or "").strip()
    elif btype == "media_text" and isinstance(block.get("media"), dict):
        ref_aid = str(block["media"].get("asset_id") or "").strip()
    if ref_aid:
        ref_asset = session.get(AssetModel, ref_aid)
        if ref_asset and ref_asset.data:
            uri = _build_thumbnail_data_uri(ref_asset.mime_type, ref_asset.data)
            if uri:
                return uri
    svg_bytes = _build_block_preview_svg(block).encode("utf-8")
    return _build_thumbnail_data_uri("image/svg+xml", svg_bytes)


def sync_block_to_media_library(
    article_id: str | None,
    block: dict[str, Any],
    user_id: str = "",
) -> dict[str, Any]:
    """
    Synchronisiert einen einzelnen Block mit der Mediathek:
    - Bei `share_in_media_library` in ('internal', 'external') wird der Block
      direkt als `approved` (für alle sichtbar) angelegt oder aktualisiert.
    - Bei `'no'` wird ein ggf. verknüpfter Mediathek-Eintrag wieder auf `'private'` gesetzt.
    """
    btype = str(block.get("type") or "").strip()
    if btype not in SHAREABLE_BLOCK_TYPES:
        return {"shared": False, "media_id": None}

    share_mode = str(block.get("share_in_media_library") or "no").strip().lower()
    existing_mid = str(block.get("shared_media_id") or "").strip() or None
    uid = normalize_user_id(user_id) or str(user_id or "system")
    now = _utc_now()

    if share_mode not in VALID_CHANNELS:
        if existing_mid:
            with get_db_session() as session:
                entry = session.get(MediaEntryModel, existing_mid)
                if entry and entry.approval_status == "approved":
                    entry.approval_status = "private"
                    entry.updated_at = now
        return {"shared": False, "media_id": existing_mid}

    clean_block = _sanitize_shared_block(block)
    payload_bytes = json.dumps(clean_block, ensure_ascii=False, sort_keys=True).encode("utf-8")
    title = _extract_block_title(block)
    mtype = BLOCK_TYPE_TO_MEDIA_TYPE.get(btype, "chart")
    source_text = str(block.get("source") or "").strip()
    filename = f"block_{btype}.json"

    with get_db_session() as session:
        thumb = _resolve_block_thumbnail(session, block)
        entry = session.get(MediaEntryModel, existing_mid) if existing_mid else None

        if entry is not None:
            entry.title = title
            entry.media_type = mtype
            entry.source_text = source_text
            entry.usage_channel = share_mode
            entry.approval_status = "approved"
            entry.approved_by = uid
            entry.approved_at = now
            entry.updated_at = now

            latest_ver = session.scalars(
                select(MediaVersionModel)
                .where(MediaVersionModel.media_id == entry.id)
                .order_by(desc(MediaVersionModel.version))
            ).first()
            latest_asset = session.get(AssetModel, latest_ver.asset_id) if latest_ver else None
            if latest_asset is not None and latest_asset.data == payload_bytes:
                if thumb and latest_ver is not None:
                    latest_ver.thumbnail_data_uri = thumb
                return {
                    "shared": True,
                    "media_id": entry.id,
                    "version": latest_ver.version if latest_ver else 1,
                    "usage_channel": share_mode,
                }

            next_ver = (int(latest_ver.version) + 1) if latest_ver else 1
            new_aid = f"asset_{uuid.uuid4().hex[:12]}"
            session.add(
                AssetModel(
                    id=new_aid,
                    article_id=article_id,
                    filename=filename,
                    mime_type="application/json",
                    data=payload_bytes,
                )
            )
            session.add(
                MediaVersionModel(
                    media_id=entry.id,
                    version=next_ver,
                    asset_id=new_aid,
                    thumbnail_data_uri=thumb,
                    created_by=uid,
                )
            )
            return {
                "shared": True,
                "media_id": entry.id,
                "version": next_ver,
                "usage_channel": share_mode,
            }

        media_id = f"media_{uuid.uuid4().hex[:12]}"
        asset_id = f"asset_{uuid.uuid4().hex[:12]}"
        session.add(
            AssetModel(
                id=asset_id,
                article_id=article_id,
                filename=filename,
                mime_type="application/json",
                data=payload_bytes,
            )
        )
        session.add(
            MediaEntryModel(
                id=media_id,
                title=title,
                media_type=mtype,
                tags_json=json.dumps([btype], ensure_ascii=False),
                source_text=source_text,
                data_as_of="",
                origin_article_id=article_id,
                approval_status="approved",
                usage_channel=share_mode,
                created_by=uid,
                approved_by=uid,
                approved_at=now,
            )
        )
        session.add(
            MediaVersionModel(
                media_id=media_id,
                version=1,
                asset_id=asset_id,
                thumbnail_data_uri=thumb,
                created_by=uid,
            )
        )
        return {
            "shared": True,
            "media_id": media_id,
            "version": 1,
            "usage_channel": share_mode,
        }


def sync_article_shared_media(doc: ArticleDocument, user_id: str = "") -> list[dict[str, Any]]:
    """Synchronisiert alle zum Teilen markierten Blöcke eines Artikels mit der Mediathek."""
    results: list[dict[str, Any]] = []
    for blk in doc.blocks:
        if not isinstance(blk, dict):
            continue
        btype = str(blk.get("type") or "").strip()
        if btype not in SHAREABLE_BLOCK_TYPES:
            continue
        share_mode = str(blk.get("share_in_media_library") or "no").strip().lower()
        has_shared_id = bool(str(blk.get("shared_media_id") or "").strip())
        if share_mode not in VALID_CHANNELS and not has_shared_id:
            continue
        res = sync_block_to_media_library(doc.id, blk, user_id=user_id)
        if res.get("shared") and res.get("media_id"):
            blk["shared_media_id"] = res["media_id"]
        results.append({"block_id": blk.get("id"), **res})
    return results


def clone_shared_block_for_insert(
    asset_id: str,
    *,
    user_id: str | None = None,
    target_article_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Lädt ein Mediathek-Asset zum Einfügen:
    - Bei `application/json` (geteilte Blöcke) wird eine unabhängige Kopie des
      Block-JSONs erstellt (`share_in_media_library='no'`, ohne `shared_media_id`).
      Referenzierte Bild-Assets (`figure`, `media_text`) werden ebenfalls geklont.
    - Bei klassischen Binär-Assets (PNG/SVG) wird das Asset direkt zurückgegeben.
    """
    if not asset_id:
        return None
    with get_db_session() as session:
        ver = session.scalars(
            select(MediaVersionModel).where(MediaVersionModel.asset_id == asset_id)
        ).first()
        if ver is not None:
            entry = session.get(MediaEntryModel, ver.media_id)
            if entry is not None:
                if entry.approval_status == "revoked":
                    return None
                if entry.approval_status != "approved":
                    accessible = get_accessible_article_ids(user_id)
                    if not (entry.origin_article_id and entry.origin_article_id in accessible):
                        return None
        asset = session.get(AssetModel, asset_id)
        if asset is None or not asset.data:
            return None
        if asset.mime_type != "application/json":
            b64 = base64.b64encode(asset.data).decode("ascii")
            return {
                "kind": "figure_asset",
                "asset_id": asset.id,
                "mime_type": asset.mime_type,
                "data_uri": f"data:{asset.mime_type};base64,{b64}",
            }

        try:
            blk = json.loads(asset.data.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(blk, dict) or not blk.get("type"):
            return None

        blk.pop("id", None)
        blk.pop("anchor_to", None)
        blk.pop("shared_media_id", None)
        blk["share_in_media_library"] = "no"

        assets_map: dict[str, str] = {}

        def _clone_ref_asset(ref_aid: str) -> str:
            ref = session.get(AssetModel, ref_aid)
            if ref is None or not ref.data:
                return ref_aid
            cloned_aid = f"asset_{uuid.uuid4().hex[:12]}"
            session.add(
                AssetModel(
                    id=cloned_aid,
                    article_id=target_article_id,
                    filename=ref.filename,
                    mime_type=ref.mime_type,
                    data=ref.data,
                )
            )
            b64 = base64.b64encode(ref.data).decode("ascii")
            assets_map[cloned_aid] = f"data:{ref.mime_type};base64,{b64}"
            return cloned_aid

        if blk.get("type") == "figure" and blk.get("asset_id"):
            blk["asset_id"] = _clone_ref_asset(str(blk["asset_id"]).strip())
        elif blk.get("type") == "media_text" and isinstance(blk.get("media"), dict) and blk["media"].get("asset_id"):
            blk["media"]["asset_id"] = _clone_ref_asset(str(blk["media"]["asset_id"]).strip())

        return {
            "kind": "block",
            "block": blk,
            "assets": assets_map,
        }
