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

from database.repository import get_asset
from schemas.article import ArticleDocument
from services.chart_generator import generate_db_chart_svg
from services.renderer import render_preview_svg_pages, render_web_html

logger = logging.getLogger("lukb_cms.collab")

PEER_COLORS = ["#009FE3", "#0D9488", "#C59B27", "#7C3AED", "#E11D48", "#2563EB"]

# Globaler Kollaborations-Speicher für alle aktiven Shiny-Sessions
ACTIVE_PEERS: dict[str, dict[str, Any]] = {}
_ACTIVE_PEERS = ACTIVE_PEERS  # Abwärtskompatibler Alias


def get_peer_color(session_id: str) -> str:
    """Bestimmt eine konsistente Signalfarbe für den Co-Autor anhand der Session-ID."""
    return PEER_COLORS[abs(hash(session_id)) % len(PEER_COLORS)]


def collect_article_assets_map(doc: ArticleDocument) -> dict[str, str]:
    """Lädt für alle Grafik- und DB-Chart-Blöcke eines Artikels die zugehörigen Data-URIs."""
    assets_map: dict[str, str] = {}
    for blk in doc.blocks:
        btype = blk.get("type")
        if btype == "figure":
            aid = blk.get("asset_id", "")
            if aid and aid not in assets_map:
                rec = get_asset(aid)
                if rec and rec.get("data"):
                    b64 = base64.b64encode(rec["data"]).decode("ascii")
                    mime = rec.get("mime_type", "image/svg+xml")
                    assets_map[aid] = f"data:{mime};base64,{b64}"
        elif btype == "db_chart":
            bid = blk.get("id", "")
            if bid:
                svg_markup = generate_db_chart_svg(blk)
                b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
                assets_map[bid] = f"data:image/svg+xml;base64,{b64}"
    return assets_map


def register_peer(
    session_id: str,
    session: Session,
    user: str,
    color: str,
    sync_doc_cb: Any,
) -> None:
    """Registriert eine neue Autoren-Session in der Kollaborations-Registry."""
    ACTIVE_PEERS[session_id] = {
        "session": session,
        "user": user,
        "color": color,
        "article_id": "",
        "focused_target": "",
        "auto_preview": True,
        "sync_doc_cb": sync_doc_cb,
    }


async def cleanup_peer(session_id: str) -> None:
    """Entfernt eine beendete Session und informiert andere Co-Autoren."""
    old_info = ACTIVE_PEERS.pop(session_id, None)
    if old_info and old_info.get("article_id"):
        try:
            await broadcast_presence(old_info["article_id"])
        except Exception:
            pass


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
    """Überträgt die Liste anwesender Co-Autoren an alle Sessions im selben Artikel."""
    if not article_id:
        return
    peers = get_article_peers(article_id)
    for sid, info in list(ACTIVE_PEERS.items()):
        if info.get("article_id") == article_id:
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
) -> None:
    """Synchronisiert den Dokumenteninhalt mit anderen aktiven Co-Autoren im selben Artikel."""
    targets = [
        (sid, info)
        for sid, info in list(ACTIVE_PEERS.items())
        if info.get("article_id") == article_id and (sid != sender_session_id or include_sender)
    ]
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
                    },
                )
            except Exception:
                pass


async def broadcast_preview_to_coauthors(
    sender_session_id: str,
    doc: ArticleDocument,
    pre_rendered_svg: list[str] | None = None,
    pre_rendered_html: str | None = None,
) -> None:
    """
    Aktualisiert die Live-Vorschau bei allen anderen Co-Autoren im selben Artikel.
    Wiederverwendet bereits berechnete `pre_rendered_svg`- und `pre_rendered_html`-Ergebnisse
    bzw. berechnet sie höchstens einmal pro Speichervorgang für alle Co-Autoren gemeinsam.
    """
    coauthor_targets = [
        (sid, info)
        for sid, info in list(ACTIVE_PEERS.items())
        if sid != sender_session_id
        and info.get("article_id") == doc.id
        and info.get("session") is not None
    ]
    if not coauthor_targets:
        return

    shared_html = pre_rendered_html
    if shared_html is None:
        try:
            shared_html = render_web_html(doc)
        except Exception as exc:
            shared_html = f"<pre>Fehler beim HTML-Rendering: {exc}</pre>"

    any_peer_needs_typst = any(bool(info.get("auto_preview", True)) for _, info in coauthor_targets)
    shared_svg = pre_rendered_svg
    if any_peer_needs_typst and shared_svg is None:
        try:
            shared_svg = render_preview_svg_pages(doc)
        except Exception:
            shared_svg = None

    for _sid, info in coauthor_targets:
        peer_sess: Session | None = info.get("session")
        if peer_sess is not None:
            try:
                peer_auto = bool(info.get("auto_preview", True))
                await peer_sess.send_custom_message(
                    "lukb_update_preview",
                    {
                        "svg_pages": shared_svg if peer_auto else None,
                        "web_html": shared_html,
                        "typst_skipped": not peer_auto,
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


def get_peer_user(session_id: str, fallback: str = "Analyst") -> str:
    """Liefert den Benutzernamen für eine Session."""
    return ACTIVE_PEERS.get(session_id, {}).get("user") or fallback
