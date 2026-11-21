"""
LUKB Investment Office — Kollaborations- & Multi-User-Registry.
Verwaltet verbundene Co-Autoren, Presence-Tracking, Cursor-Fokus und Remote-Sync.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any
from shiny import Session

from config import normalize_user_id
from database.permissions import check_article_permission, get_accessible_article_ids
from database.repository import get_assets_by_ids, list_articles
from schemas.article import ArticleDocument
from services.renderer import render_block_chart_svg, render_preview_pdf_base64, render_web_html

logger = logging.getLogger("lukb_cms.collab")

PEER_COLORS = ["#009FE3", "#0D9488", "#C59B27", "#7C3AED", "#E11D48", "#2563EB"]

# Globaler Kollaborations-Speicher für alle aktiven Shiny-Sessions
ACTIVE_PEERS: dict[str, dict[str, Any]] = {}
_ACTIVE_PEERS = ACTIVE_PEERS  # Abwärtskompatibler Alias


def get_peer_color(session_id: str) -> str:
    """Bestimmt eine konsistente Signalfarbe für den Co-Autor anhand der Session-ID."""
    return PEER_COLORS[abs(hash(session_id)) % len(PEER_COLORS)]


def collect_article_assets_map(
    doc: ArticleDocument,
    known_asset_ids: set[str] | list[str] | None = None,
) -> dict[str, str]:
    """Lädt für alle Grafik-, DB-Chart- und Custom-Chart-Blöcke eines Artikels die zugehörigen Data-URIs.
    Überspringt Assets, die in known_asset_ids enthalten sind, um wiederholte Datenübertragungen zu vermeiden.
    """
    known_set = set(known_asset_ids) if known_asset_ids is not None else None
    needed_figure_aids: set[str] = set()
    for blk in doc.blocks:
        btype = blk.get("type")
        if btype == "figure":
            aid = blk.get("asset_id", "")
            if aid and (known_set is None or aid not in known_set):
                needed_figure_aids.add(aid)
        elif btype == "media_text":
            media = blk.get("media")
            if isinstance(media, dict) and media.get("type") == "figure":
                aid = media.get("asset_id", "")
                if aid and (known_set is None or aid not in known_set):
                    needed_figure_aids.add(aid)
    asset_records = get_assets_by_ids(needed_figure_aids) if needed_figure_aids else {}

    assets_map: dict[str, str] = {}
    for blk in doc.blocks:
        btype = blk.get("type")
        if btype == "figure":
            aid = blk.get("asset_id", "")
            if aid and (known_set is None or aid not in known_set) and aid not in assets_map:
                rec = asset_records.get(aid)
                if rec and rec.get("data"):
                    b64 = base64.b64encode(rec["data"]).decode("ascii")
                    mime = rec.get("mime_type", "image/svg+xml")
                    assets_map[aid] = f"data:{mime};base64,{b64}"
        elif btype in ("db_chart", "custom_chart"):
            bid = blk.get("id", "")
            if bid and (known_set is None or bid not in known_set):
                svg_markup = render_block_chart_svg(
                    blk,
                    embed_fonts=True,
                    max_date=doc.metadata.publication_date,
                )
                b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
                assets_map[bid] = f"data:image/svg+xml;base64,{b64}"
        elif btype == "media_text":
            media = blk.get("media")
            if isinstance(media, dict):
                mtype = blk.get("media_type") or media.get("type") or "figure"
                if mtype == "figure":
                    aid = media.get("asset_id", "")
                    if aid and (known_set is None or aid not in known_set) and aid not in assets_map:
                        rec = asset_records.get(aid)
                        if rec and rec.get("data"):
                            b64 = base64.b64encode(rec["data"]).decode("ascii")
                            mime = rec.get("mime_type", "image/svg+xml")
                            assets_map[aid] = f"data:{mime};base64,{b64}"
                elif mtype in ("db_chart", "custom_chart"):
                    mid = media.get("id") or f"{blk.get('id', '')}_media"
                    if mid and (known_set is None or mid not in known_set):
                        svg_markup = render_block_chart_svg(
                            media,
                            embed_fonts=True,
                            max_date=doc.metadata.publication_date,
                        )
                        b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
                        assets_map[mid] = f"data:image/svg+xml;base64,{b64}"
    return assets_map


def register_peer(
    session_id: str,
    session: Session,
    user: str,
    color: str,
    sync_doc_cb: Any,
    revoke_cb: Any = None,
) -> None:
    """Registriert eine neue Autoren-Session in der Kollaborations-Registry."""
    ACTIVE_PEERS[session_id] = {
        "session": session,
        "user": user,
        "color": color,
        "article_id": "",
        "focused_target": "",
        "auto_preview": True,
        "preview_mode": "pdf",
        "sync_doc_cb": sync_doc_cb,
        "revoke_cb": revoke_cb,
    }


async def cleanup_peer(session_id: str) -> None:
    """Entfernt eine beendete Session und informiert andere Co-Autoren."""
    old_info = ACTIVE_PEERS.pop(session_id, None)
    if old_info and old_info.get("article_id"):
        try:
            await broadcast_presence(old_info["article_id"])
        except Exception:
            pass
    try:
        await broadcast_global_presence()
    except Exception:
        pass


def get_active_articles_presence() -> dict[str, list[dict[str, str]]]:
    """Liefert eine Übersicht, welche aktiven Benutzer welchen Artikel geöffnet haben."""
    by_article: dict[str, list[dict[str, str]]] = {}
    for sid, info in list(ACTIVE_PEERS.items()):
        aid = info.get("article_id") or ""
        if not aid:
            continue
        by_article.setdefault(aid, []).append(
            {
                "session_id": sid,
                "user": info.get("user", "Analyst"),
                "color": info.get("color", "#009FE3"),
            }
        )
    return by_article


def filter_presence_by_allowed_articles(
    by_article: dict[str, list[dict[str, str]]],
    allowed_article_ids: set[str],
) -> dict[str, list[dict[str, str]]]:
    """Filtert die globale Präsenz-Map auf Artikel, auf die der Empfänger Leserecht hat."""
    if not allowed_article_ids:
        return {}
    return {aid: peers for aid, peers in by_article.items() if aid in allowed_article_ids}


async def broadcast_global_presence() -> None:
    """Sendet die globale Artikel-Belegung empfängerbezogen gefiltert an alle Sessions."""
    by_article = get_active_articles_presence()
    allowed_cache: dict[str, set[str]] = {}
    for sid, info in list(ACTIVE_PEERS.items()):
        sess: Session | None = info.get("session")
        if sess is None:
            continue
        uid = normalize_user_id(info.get("user"))
        if uid not in allowed_cache:
            allowed_cache[uid] = await asyncio.to_thread(get_accessible_article_ids, uid)
        filtered_presence = filter_presence_by_allowed_articles(by_article, allowed_cache[uid])
        try:
            await sess.send_custom_message(
                "lukb_global_presence",
                {
                    "self_session_id": sid,
                    "active_peers_by_article": filtered_presence,
                },
            )
        except Exception:
            pass


async def broadcast_article_list_to_all(exclude_session_id: str | None = None) -> None:
    """Aktualisiert die Artikelliste bei allen anderen aktiven Sessions (streng gefiltert pro Empfänger)."""
    targets = [
        (sid, info)
        for sid, info in list(ACTIVE_PEERS.items())
        if sid != exclude_session_id and info.get("session") is not None
    ]
    if not targets:
        return

    by_article = get_active_articles_presence()
    items_by_user: dict[str, list[dict[str, Any]]] = {}
    allowed_by_user: dict[str, set[str]] = {}

    for sid, info in targets:
        sess: Session | None = info.get("session")
        if sess is None:
            continue
        uid = normalize_user_id(info.get("user"))
        if uid not in items_by_user:
            user_items = await asyncio.to_thread(
                list_articles,
                search_query="",
                status_filter="all",
                user_id=uid,
            )
            items_by_user[uid] = user_items
            allowed_by_user[uid] = {it["id"] for it in user_items if it.get("id")}
        filtered_presence = filter_presence_by_allowed_articles(by_article, allowed_by_user[uid])
        try:
            await sess.send_custom_message(
                "lukb_global_article_list",
                {
                    "all_articles": items_by_user[uid],
                    "active_id": info.get("article_id", ""),
                    "self_session_id": sid,
                    "active_peers_by_article": filtered_presence,
                },
            )
        except Exception:
            pass


async def enforce_article_access_revoked(article_id: str, target_user: str) -> int:
    """
    Entfernt alle offenen Sessions von `target_user` sofort aus `article_id`,
    leert den serverseitigen Session-Zustand und informiert das Frontend.
    """
    target_uid = normalize_user_id(target_user)
    if not article_id or not target_uid:
        return 0

    affected_sessions: list[tuple[str, dict[str, Any]]] = []
    for sid, info in list(ACTIVE_PEERS.items()):
        if info.get("article_id") == article_id and normalize_user_id(info.get("user")) == target_uid:
            info["article_id"] = ""
            info["focused_target"] = ""
            revoke_cb = info.get("revoke_cb")
            if callable(revoke_cb):
                try:
                    revoke_cb(article_id)
                except Exception:
                    pass
            affected_sessions.append((sid, info))

    for sid, info in affected_sessions:
        sess: Session | None = info.get("session")
        if sess is not None:
            try:
                user_items = await asyncio.to_thread(
                    list_articles, search_query="", status_filter="all", user_id=target_uid
                )
                allowed_ids = {it["id"] for it in user_items if it.get("id")}
                filtered_presence = filter_presence_by_allowed_articles(
                    get_active_articles_presence(), allowed_ids
                )
                await sess.send_custom_message(
                    "lukb_access_revoked",
                    {
                        "article_id": article_id,
                        "message": "Ihr Zugriff auf diesen Artikel wurde entzogen.",
                        "next_article_id": user_items[0]["id"] if user_items else "",
                        "articles": user_items,
                        "active_peers_by_article": filtered_presence,
                    },
                )
            except Exception:
                pass

    if affected_sessions:
        await broadcast_presence(article_id)
        await broadcast_global_presence()

    return len(affected_sessions)


async def transfer_block_lock(requester_session_id: str, block_id: str) -> None:
    """Überträgt den aktiven Bearbeitungs-Fokus (Soft-Lock) eines Blocks an den anfragenden Co-Autor."""
    req_info = ACTIVE_PEERS.get(requester_session_id)
    if not req_info or not block_id:
        return
    article_id = req_info.get("article_id", "")
    req_user = req_info.get("user", "Co-Autor")
    if not article_id:
        return

    for sid, info in list(ACTIVE_PEERS.items()):
        if (
            sid != requester_session_id
            and info.get("article_id") == article_id
            and info.get("focused_target") == block_id
        ):
            info["focused_target"] = ""
            sess: Session | None = info.get("session")
            if sess is not None:
                try:
                    await sess.send_custom_message(
                        "lukb_collab_notice",
                        {
                            "message": f"✏️ {req_user} hat die Bearbeitung des Blocks übernommen.",
                            "block_id": block_id,
                        },
                    )
                except Exception:
                    pass

    req_info["focused_target"] = block_id
    await broadcast_presence(article_id)


def get_article_peers(article_id: str) -> list[dict[str, Any]]:
    """Gibt alle aktiven Co-Autoren für einen bestimmten Artikel zurück."""
    if not article_id:
        return []
    peers: list[dict[str, Any]] = []
    for sid, info in list(ACTIVE_PEERS.items()):
        if info.get("article_id") == article_id:
            peers.append(
                {
                    "session_id": sid,
                    "user": info.get("user", "Analyst"),
                    "color": info.get("color", "#009FE3"),
                    "focused_target": info.get("focused_target", ""),
                }
            )
    return peers


async def broadcast_presence(article_id: str) -> None:
    """Überträgt die Liste anwesender Co-Autoren an alle berechtigten Sessions im selben Artikel."""
    if not article_id:
        return
    peers = get_article_peers(article_id)
    for sid, info in list(ACTIVE_PEERS.items()):
        if info.get("article_id") == article_id:
            if not await asyncio.to_thread(check_article_permission, article_id, info.get("user"), "read"):
                continue
            sess: Session | None = info.get("session")
            if sess is not None:
                try:
                    await sess.send_custom_message(
                        "lukb_collab_presence",
                        {
                            "article_id": article_id,
                            "self_session_id": sid,
                            "peers": peers,
                        },
                    )
                except Exception:
                    pass


async def broadcast_article_sync(
    article_id: str,
    doc: ArticleDocument,
    sender_session_id: str,
    author_name: str,
    include_sender: bool = False,
    assets_map: dict[str, dict[str, Any]] | None = None,
    publish_sync: dict[str, Any] | None = None,
) -> None:
    """Synchronisiert den Dokumenteninhalt mit anderen berechtigten Co-Autoren im selben Artikel."""
    candidates = [
        (sid, info)
        for sid, info in list(ACTIVE_PEERS.items())
        if info.get("article_id") == article_id and (sid != sender_session_id or include_sender)
    ]
    targets = []
    for sid, info in candidates:
        if await asyncio.to_thread(check_article_permission, article_id, info.get("user"), "read"):
            targets.append((sid, info))
    if not targets:
        return

    resolved_assets = assets_map if assets_map is not None else collect_article_assets_map(doc)
    doc_payload = doc.model_dump()
    for sid, info in targets:
        sess: Session | None = info.get("session")
        sync_cb = info.get("sync_doc_cb")
        if callable(sync_cb):
            try:
                sync_cb(doc)
            except Exception:
                pass
        if sess is not None:
            try:
                await sess.send_custom_message(
                    "lukb_remote_sync",
                    {
                        "article": doc_payload,
                        "assets": resolved_assets,
                        "updated_by": author_name,
                        "sender_session_id": sender_session_id,
                        "publish_sync": publish_sync,
                    },
                )
            except Exception:
                pass


async def broadcast_preview_to_coauthors(
    sender_session_id: str,
    doc: ArticleDocument,
    pre_rendered_pdf_base64: str | None = None,
    pre_rendered_html: str | None = None,
    pre_rendered_svg: list[str] | None = None,
) -> None:
    """
    Aktualisiert die Live-Vorschau bei allen anderen Co-Autoren im selben Artikel.
    Wiederverwendet bereits berechnete `pre_rendered_pdf_base64`- und `pre_rendered_html`-Ergebnisse
    bzw. berechnet sie asynchron im Worker-Thread höchstens einmal pro Speichervorgang.
    Rendert HTML nur, falls mindestens ein Co-Autor die Web-Vorschau aktiv betrachtet.
    """
    coauthor_candidates = [
        (sid, info)
        for sid, info in list(ACTIVE_PEERS.items())
        if sid != sender_session_id
        and info.get("article_id") == doc.id
        and info.get("session") is not None
    ]
    coauthor_targets = []
    for sid, info in coauthor_candidates:
        if await asyncio.to_thread(check_article_permission, doc.id, info.get("user"), "read"):
            coauthor_targets.append((sid, info))
    if not coauthor_targets:
        return

    any_peer_needs_web = any(
        info.get("preview_mode", "pdf") == "web"
        for _, info in coauthor_targets
    )
    shared_html = pre_rendered_html
    if any_peer_needs_web and shared_html is None:
        try:
            shared_html = await asyncio.to_thread(render_web_html, doc)
        except Exception as exc:
            shared_html = f"<pre>Fehler beim HTML-Rendering: {exc}</pre>"

    any_peer_needs_typst = any(
        bool(info.get("auto_preview", True)) and info.get("preview_mode", "pdf") == "pdf"
        for _, info in coauthor_targets
    )
    shared_pdf_base64 = pre_rendered_pdf_base64
    if any_peer_needs_typst and shared_pdf_base64 is None:
        try:
            shared_pdf_base64 = await asyncio.to_thread(render_preview_pdf_base64, doc)
        except Exception:
            shared_pdf_base64 = None

    for _sid, info in coauthor_targets:
        peer_sess: Session | None = info.get("session")
        if peer_sess is not None:
            try:
                peer_auto = bool(info.get("auto_preview", True))
                peer_mode = info.get("preview_mode", "pdf")
                await peer_sess.send_custom_message(
                    "lukb_update_preview",
                    {
                        "pdf_base64": shared_pdf_base64 if (peer_auto and peer_mode == "pdf") else None,
                        "web_html": shared_html if peer_mode == "web" else None,
                        "typst_skipped": not (peer_auto and peer_mode == "pdf"),
                        "web_skipped": peer_mode != "web",
                    },
                )
            except Exception:
                pass


def set_peer_article(session_id: str, article_id: str) -> str:
    """Aktualisiert den aktuellen Artikel einer Session und gibt die vorherige Artikel-ID zurück."""
    prev_article_id = ACTIVE_PEERS.get(session_id, {}).get("article_id", "")
    if session_id in ACTIVE_PEERS:
        ACTIVE_PEERS[session_id]["article_id"] = article_id
        ACTIVE_PEERS[session_id]["focused_target"] = ""
    return prev_article_id


def set_peer_focus(session_id: str, focused_target: str, user: str | None = None) -> str:
    """Aktualisiert das aktive Fokus-Feld (Cursor) und optional den Benutzernamen."""
    if session_id in ACTIVE_PEERS:
        ACTIVE_PEERS[session_id]["focused_target"] = focused_target
        if user:
            ACTIVE_PEERS[session_id]["user"] = user
        return ACTIVE_PEERS[session_id].get("article_id", "")
    return ""


def set_peer_auto_preview(session_id: str, auto_preview: bool) -> None:
    """Aktualisiert die Auto-Preview-Einstellung für eine Session."""
    if session_id in ACTIVE_PEERS:
        ACTIVE_PEERS[session_id]["auto_preview"] = auto_preview


def is_peer_auto_preview(session_id: str, default: bool = True) -> bool:
    """Prüft, ob für eine Session die kontinuierliche Vorschau aktiviert ist."""
    return bool(ACTIVE_PEERS.get(session_id, {}).get("auto_preview", default))


def set_peer_preview_mode(session_id: str, preview_mode: str) -> None:
    """Aktualisiert den aktiven Vorschaumodus (pdf vs. web) für eine Session."""
    if session_id in ACTIVE_PEERS:
        ACTIVE_PEERS[session_id]["preview_mode"] = preview_mode


def get_peer_preview_mode(session_id: str, default: str = "pdf") -> str:
    """Gibt den aktiven Vorschaumodus (pdf vs. web) für eine Session zurück."""
    return ACTIVE_PEERS.get(session_id, {}).get("preview_mode", default)


def get_peer_user(session_id: str, fallback: str = "Analyst") -> str:
    """Liefert den Benutzernamen für eine Session."""
    return ACTIVE_PEERS.get(session_id, {}).get("user") or fallback
