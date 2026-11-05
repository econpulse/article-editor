"""
LUKB Investment Office — Content-Management-System & Publikations-Editor
Einstiegspunkt für Shiny for Python & Posit Connect Deployment.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any
from shiny import App, Inputs, Outputs, Session, reactive, render, ui

from config import DATABASE_BACKEND_LABEL, WWW_DIR
from database.repository import (
    create_new_article,
    delete_article,
    duplicate_article,
    get_article,
    get_asset,
    init_db_and_seed,
    list_articles,
    save_article,
    save_asset,
)
from schemas.article import ArticleDocument
from services.renderer import (
    list_available_templates,
    render_pdf_bytes,
    render_preview_svg_pages,
    render_web_html,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lukb_cms")

# Datenbank-Tabellen & initiale Beispiel-Publikationen beim Start sicherstellen
init_db_and_seed()


def _slugify_filename(title: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß_-]+", "_", title.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:60] or "LUKB_Publikation"


def _collect_article_assets_map(doc: ArticleDocument) -> dict[str, str]:
    """Lädt für alle Grafik-Blöcke eines Artikels die zugehörigen Data-URIs aus der DB."""
    assets_map: dict[str, str] = {}
    for blk in doc.blocks:
        if blk.get("type") == "figure":
            aid = blk.get("asset_id", "")
            if aid and aid not in assets_map:
                rec = get_asset(aid)
                if rec and rec.get("data"):
                    b64 = base64.b64encode(rec["data"]).decode("ascii")
                    mime = rec.get("mime_type", "image/svg+xml")
                    assets_map[aid] = f"data:{mime};base64,{b64}"
    return assets_map


# ============================================================================
# Shiny UI Definition (3-Spalten-Layout im LUKB Corporate Design)
# ============================================================================

templates_list = list_available_templates()

app_ui = ui.page_fluid(
    ui.head_content(
        ui.tags.meta(charset="utf-8"),
        ui.tags.meta(name="viewport", content="width=device-width, initial-scale=1"),
        ui.tags.title("LUKB Investment Office — Publikations-Editor & CMS"),
        ui.tags.link(rel="stylesheet", href="css/editor.css"),
        ui.tags.script(src="js/vendor/Sortable.min.js"),
        ui.tags.script(src="js/editor.js"),
    ),
    # ------------------------------------------------------------------------
    # Top Header Bar
    # ------------------------------------------------------------------------
    ui.div(
        ui.div(
            ui.span("LUKB", class_="cms-brand-badge"),
            ui.span("Investment Office — Publikations-CMS", class_="cms-brand-title"),
            ui.span(f"DB: {DATABASE_BACKEND_LABEL}", class_="cms-brand-subtitle"),
            class_="cms-brand",
        ),
        ui.div(
            ui.div(
                ui.span(class_="autosave-dot"),
                ui.span("Bereit", id="lukb-autosave-text"),
                id="lukb-autosave-pill",
                class_="autosave-pill status-saved",
            ),
            ui.div(
                id="lukb-collab-presence",
                class_="collab-presence-bar",
                style="display:none;",
            ),
            ui.tags.button(
                "Meilenstein speichern",
                id="btn-manual-snapshot",
                type="button",
                class_="btn-lukb btn-lukb-outline-light btn-lukb-sm",
                title="Speichert sofort und legt einen Revisions-Snapshot in der Datenbank an (Ctrl+S)",
            ),
            class_="cms-topbar-center",
        ),
        ui.div(
            ui.download_button(
                "download_html",
                "Web-HTML Export",
                class_="btn-lukb btn-lukb-outline-light",
            ),
            ui.download_button(
                "download_pdf",
                "PDF Export (Typst)",
                class_="btn-lukb btn-lukb-primary",
            ),
            class_="cms-topbar-actions",
        ),
        class_="cms-topbar",
    ),
    # ------------------------------------------------------------------------
    # 3-Spalten Workspace
    # ------------------------------------------------------------------------
    ui.div(
        # ====================================================================
        # Linke Spalte: Artikel-Übersicht & Datenbank-Suche
        # ====================================================================
        ui.tags.aside(
            ui.div(
                ui.div(
                    ui.h2("Publikationen", class_="sidebar-title"),
                    ui.span("0 Artikel", id="sidebar-article-count", style="font-size:11.5px;color:#5A687C;"),
                    class_="sidebar-title-row",
                ),
                ui.div(
                    ui.input_action_button(
                        "btn_new_article",
                        "+ Neue Publikation anlegen",
                        class_="btn-lukb btn-lukb-navy",
                        style="width:100%;margin-bottom:6px;",
                    ),
                    ui.tags.input(
                        id="sidebar_search",
                        type="search",
                        class_="cms-input",
                        placeholder="Artikel, Autor oder Thema suchen …",
                        oninput="Shiny.setInputValue('sidebar_search_query', this.value, {priority: 'event'})",
                    ),
                    ui.tags.select(
                        ui.tags.option("Alle Status anzeigen", value="all"),
                        ui.tags.option("Status: Entwurf", value="draft"),
                        ui.tags.option("Status: In Review", value="review"),
                        ui.tags.option("Status: Publiziert", value="published"),
                        id="sidebar_status_filter",
                        class_="cms-select",
                        onchange="Shiny.setInputValue('sidebar_status_val', this.value, {priority: 'event'})",
                    ),
                    class_="sidebar-filters",
                ),
                class_="sidebar-header",
            ),
            ui.div(id="lukb-article-list", class_="article-list-scroll"),
            ui.div(
                ui.input_action_button(
                    "btn_duplicate_article",
                    "Duplizieren",
                    class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                    style="flex:1;",
                ),
                ui.input_action_button(
                    "btn_delete_article",
                    "Löschen",
                    class_="btn-lukb btn-lukb-danger-ghost btn-lukb-sm",
                    style="flex:1;",
                ),
                style="padding:10px 12px;border-top:1px solid #D6DEE8;display:flex;gap:8px;background:#F4F7FA;",
            ),
            class_="cms-sidebar",
        ),
        # ====================================================================
        # Mittlere Spalte: Dokumenten-Metadaten & Drag-and-Drop Block-Editor
        # ====================================================================
        ui.tags.main(
            # 1. Dokumenten-Kopf & Metadaten-Karte
            ui.div(
                ui.div(
                    ui.h3("Dokumenten-Kopf, Template & Autoren", class_="editor-card-title"),
                    ui.span(
                        "Schriften: Yoga Sans for LUKB Light / Medium",
                        style="font-size:11.5px;color:#5A687C;",
                    ),
                    class_="editor-card-header",
                ),
                # Zeile 1: Template, Status, Publikationsdatum
                ui.div(
                    ui.div(
                        ui.tags.label("Dokumenten-Template (PDF & Web)", class_="field-label", **{"for": "meta-template-id"}),
                        ui.tags.select(
                            *[
                                ui.tags.option(t["name"], value=t["id"])
                                for t in templates_list
                            ],
                            id="meta-template-id",
                            class_="cms-select font-medium",
                        ),
                    ),
                    ui.div(
                        ui.tags.label("Publikations-Status", class_="field-label", **{"for": "meta-status"}),
                        ui.tags.select(
                            ui.tags.option("Entwurf", value="draft"),
                            ui.tags.option("In Review", value="review"),
                            ui.tags.option("Publiziert", value="published"),
                            id="meta-status",
                            class_="cms-select",
                        ),
                    ),
                    ui.div(
                        ui.tags.label("Publikationsdatum", class_="field-label", **{"for": "meta-pub-date"}),
                        ui.tags.input(id="meta-pub-date", type="date", class_="cms-input"),
                    ),
                    class_="meta-grid-3",
                ),
                # Zeile 2: Rubrik & Untertitel / Dachzeile
                ui.div(
                    ui.div(
                        ui.tags.label("Rubrik / Publikationsreihe", class_="field-label", **{"for": "meta-category"}),
                        ui.tags.input(
                            id="meta-category",
                            type="text",
                            class_="cms-input",
                            placeholder="z.B. Anlagepolitik & Märkte",
                        ),
                    ),
                    ui.div(
                        ui.tags.label("Dachzeile / Untertitel", class_="field-label", **{"for": "meta-subtitle"}),
                        ui.tags.input(
                            id="meta-subtitle",
                            type="text",
                            class_="cms-input",
                            placeholder="z.B. Marktausblick 4. Quartal 2026",
                        ),
                    ),
                    class_="meta-grid-2",
                ),
                # Zeile 3: Gesamttitel
                ui.div(
                    ui.tags.label("Gesamttitel der Publikation (Yoga Sans Medium)", class_="field-label", **{"for": "meta-title"}),
                    ui.tags.input(
                        id="meta-title",
                        type="text",
                        class_="cms-input input-title-large",
                        placeholder="Gesamttitel eingeben …",
                    ),
                    class_="field-group",
                ),
                # Zeile 4: Lead-Text
                ui.div(
                    ui.tags.label("Lead / Management Summary", class_="field-label", **{"for": "meta-lead"}),
                    ui.tags.textarea(
                        id="meta-lead",
                        rows="3",
                        class_="cms-textarea",
                        placeholder="Zusammenfassender Einleitungstext der Publikation …",
                    ),
                    class_="field-group",
                ),
                # Zeile 5: Autoren-Verwaltung
                ui.div(
                    ui.div(
                        ui.tags.label("Autoren des Investment Office", class_="field-label", style="margin:0;"),
                        ui.tags.button(
                            "+ Autor hinzufügen",
                            id="btn-add-author",
                            type="button",
                            class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        ),
                        style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;",
                    ),
                    ui.div(id="meta-authors-container", class_="authors-list-container"),
                    class_="field-group",
                ),
                # Zeile 6: Aufklappbarer Disclaimer
                ui.tags.details(
                    ui.tags.summary(
                        "Rechtlicher Hinweis / Fusszeile bearbeiten",
                        style="cursor:pointer;font-size:12px;color:#5A687C;margin-top:6px;",
                    ),
                    ui.tags.textarea(
                        id="meta-disclaimer",
                        rows="2",
                        class_="cms-textarea",
                        style="margin-top:6px;font-size:12px;",
                    ),
                ),
                class_="editor-section-card",
            ),
            # 2. Sticky Block-Einfügeleiste
            ui.div(
                ui.span(
                    "Inhaltsblöcke (per Drag & Drop ⋮⋮ sortierbar):",
                    class_="font-medium",
                    style="color:#002855;font-size:13.5px;",
                ),
                ui.div(
                    ui.tags.button(
                        "+ Überschrift",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "heading"},
                    ),
                    ui.tags.button(
                        "+ Text-Absatz",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "richtext"},
                    ),
                    ui.tags.button(
                        "+ Grafik (inkl. Titel/Untertitel)",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "figure"},
                    ),
                    ui.tags.button(
                        "+ Tabelle (inkl. Excel-Paste)",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "table"},
                    ),
                    ui.tags.button(
                        "+ Kernaussagen-Box",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "callout"},
                    ),
                    ui.tags.button(
                        "+ Farbliche Box (Start & Ende)",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        style="border-color:#002855;background:#EBF3FA;color:#002855;",
                        **{"data-add-block-type": "textbox_pair"},
                        title="Fügt eine Start- und End-Marke für eine farbliche Textbox ein (beliebige Blöcke dazwischen ziehbar)",
                    ),
                    class_="add-block-bar",
                ),
                class_="blocks-toolbar-sticky",
            ),
            # 3. SortableJS Block-Canvas
            ui.div(id="lukb-blocks-canvas", class_="blocks-canvas"),
            class_="cms-editor-pane",
        ),
        # ====================================================================
        # Rechte Spalte: Echtzeit-Vorschau (Typst PDF/SVG & Web HTML5)
        # ====================================================================
        ui.tags.section(
            ui.div(
                ui.div(
                    ui.tags.button(
                        "PDF-Vorschau (Typst)",
                        type="button",
                        class_="preview-tab-btn active",
                        **{"data-preview-mode": "pdf"},
                    ),
                    ui.tags.button(
                        "Web-Vorschau (HTML5)",
                        type="button",
                        class_="preview-tab-btn",
                        **{"data-preview-mode": "web"},
                    ),
                    class_="preview-mode-tabs",
                ),
                ui.div(
                    ui.span(
                        "Typst 0.15",
                        id="preview-page-count",
                        style="font-size:12px;color:#5A687C;margin-right:8px;",
                    ),
                    ui.input_action_button(
                        "btn_refresh_preview",
                        "↻ Vorschau aktualisieren",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                    ),
                    style="display:flex;align-items:center;",
                ),
                class_="preview-toolbar",
            ),
            # Container 1: Typst SVG Seiten-Preview
            ui.div(id="preview-container-pdf", class_="preview-viewport"),
            # Container 2: Web HTML5 Iframe-Preview
            ui.div(
                ui.tags.iframe(id="preview-iframe-web", class_="web-preview-iframe"),
                id="preview-container-web",
                style="display:none;flex:1;padding:16px;height:100%;",
            ),
            class_="cms-preview-pane",
        ),
        class_="cms-workspace",
    ),
)


# ============================================================================
# Kollaborations-Registry für gleichzeitiges Multi-User-Editing
# ============================================================================

_ACTIVE_PEERS: dict[str, dict[str, Any]] = {}


def _get_article_peers(article_id: str) -> list[dict[str, Any]]:
    if not article_id:
        return []
    peers: list[dict[str, Any]] = []
    for sid, info in list(_ACTIVE_PEERS.items()):
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


async def _broadcast_presence(article_id: str) -> None:
    if not article_id:
        return
    peers = _get_article_peers(article_id)
    for sid, info in list(_ACTIVE_PEERS.items()):
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


async def _broadcast_article_sync(
    article_id: str,
    doc: ArticleDocument,
    sender_session_id: str,
    author_name: str,
    include_sender: bool = False,
) -> None:
    assets_map = _collect_article_assets_map(doc)
    for sid, info in list(_ACTIVE_PEERS.items()):
        if info.get("article_id") != article_id:
            continue
        if sid == sender_session_id and not include_sender:
            continue
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
                        "article": doc.model_dump(),
                        "assets": assets_map,
                        "updated_by": author_name,
                        "sender_session_id": sender_session_id,
                    },
                )
            except Exception:
                pass


# ============================================================================
# Shiny Server-Logik
# ============================================================================


_PEER_COLORS = ["#009FE3", "#0D9488", "#C59B27", "#7C3AED", "#E11D48", "#2563EB"]


def server(input: Inputs, output: Outputs, session: Session) -> None:
    current_article_id: reactive.Value[str] = reactive.Value("")
    current_doc: reactive.Value[ArticleDocument | None] = reactive.Value(None)
    session_id = getattr(session, "id", f"sess_{id(session)}")
    peer_color = _PEER_COLORS[abs(hash(session_id)) % len(_PEER_COLORS)]

    def _current_user() -> str:
        # Auf Posit Connect steht der angemeldete Benutzer unter session.user bereit
        user_name = getattr(session, "user", None)
        if user_name:
            return str(user_name)
        return f"Analyst ({session_id[:4]})"

    def _update_local_doc_from_peer(new_doc: ArticleDocument) -> None:
        current_doc.set(new_doc)

    _ACTIVE_PEERS[session_id] = {
        "session": session,
        "user": _current_user(),
        "color": peer_color,
        "article_id": "",
        "focused_target": "",
        "sync_doc_cb": _update_local_doc_from_peer,
    }

    def _cleanup_peer() -> None:
        old_info = _ACTIVE_PEERS.pop(session_id, None)
        if old_info and old_info.get("article_id"):
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_broadcast_presence(old_info["article_id"]))
            except Exception:
                pass

    session.on_ended(_cleanup_peer)

    async def _send_article_list(active_id: str) -> None:
        search_q = ""
        status_f = "all"
        try:
            search_q = input.sidebar_search_query() or ""
        except Exception:
            pass
        try:
            status_f = input.sidebar_status_val() or "all"
        except Exception:
            pass

        items = list_articles(search_query=search_q, status_filter=status_f)
        await session.send_custom_message(
            "lukb_update_article_list",
            {"articles": items, "active_id": active_id},
        )

    async def _send_preview(doc: ArticleDocument) -> None:
        try:
            svg_pages = render_preview_svg_pages(doc)
        except Exception as exc:
            logger.exception("Typst Preview-Fehler")
            err_svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 200">'
                f'<rect width="600" height="200" fill="#FEF2F2"/>'
                f'<text x="24" y="50" fill="#B91C1C" font-size="14">'
                f"Typst Vorschau-Hinweis: {str(exc)[:90]}</text></svg>"
            )
            svg_pages = [err_svg]

        try:
            web_html = render_web_html(doc)
        except Exception as exc:
            logger.exception("Web HTML Preview-Fehler")
            web_html = f"<pre>Fehler beim HTML-Rendering: {exc}</pre>"

        await session.send_custom_message(
            "lukb_update_preview",
            {"svg_pages": svg_pages, "web_html": web_html},
        )

    async def _load_and_broadcast_article(article_id: str) -> None:
        doc = get_article(article_id)
        if doc is None:
            all_items = list_articles()
            if all_items:
                doc = get_article(all_items[0]["id"])
            else:
                doc = create_new_article(user=_current_user())

        if doc is None:
            return

        prev_article_id = _ACTIVE_PEERS.get(session_id, {}).get("article_id", "")
        current_article_id.set(doc.id)
        current_doc.set(doc)

        if session_id in _ACTIVE_PEERS:
            _ACTIVE_PEERS[session_id]["article_id"] = doc.id
            _ACTIVE_PEERS[session_id]["focused_target"] = ""

        assets_map = _collect_article_assets_map(doc)
        await session.send_custom_message(
            "lukb_load_article",
            {"article": doc.model_dump(), "assets": assets_map, "self_session_id": session_id},
        )
        await _send_article_list(doc.id)
        await _send_preview(doc)
        if prev_article_id and prev_article_id != doc.id:
            await _broadcast_presence(prev_article_id)
        await _broadcast_presence(doc.id)

    # Initiales Laden beim Sitzungsstart
    @reactive.effect
    async def _init_session() -> None:
        items = list_articles()
        first_id = items[0]["id"] if items else ""
        await _load_and_broadcast_article(first_id)

    # Filter- oder Sucheingabe in der linken Sidebar
    @reactive.effect
    @reactive.event(input.sidebar_search_query, input.sidebar_status_val)
    async def _on_sidebar_filter() -> None:
        await _send_article_list(current_article_id.get())

    # Klick auf einen anderen Artikel in der Sidebar
    @reactive.effect
    @reactive.event(input.lukb_select_article)
    async def _on_select_article() -> None:
        payload = input.lukb_select_article()
        if not isinstance(payload, dict):
            return
        target_id = payload.get("id", "")
        if target_id:
            await _load_and_broadcast_article(target_id)

    # Upload einer Grafikdatei (SVG, PNG, JPG) in die MSSQL-Datenbank
    @reactive.effect
    @reactive.event(input.lukb_upload_asset)
    async def _on_upload_asset() -> None:
        payload = input.lukb_upload_asset()
        if not isinstance(payload, dict):
            return
        b64_str = payload.get("base64_data", "")
        if not b64_str:
            return
        raw_bytes = base64.b64decode(b64_str)
        save_asset(
            filename=payload.get("filename", "grafik.svg"),
            mime_type=payload.get("mime_type", "image/svg+xml"),
            data=raw_bytes,
            article_id=payload.get("article_id"),
            asset_id=payload.get("asset_id"),
        )
        doc = current_doc.get()
        if doc is not None:
            await _send_preview(doc)

    # Live-Fokus-Meldung eines Autors (welcher Block / welches Feld wird gerade editiert?)
    @reactive.effect
    @reactive.event(input.lukb_collab_focus)
    async def _on_collab_focus() -> None:
        payload = input.lukb_collab_focus()
        if not isinstance(payload, dict):
            return
        target = str(payload.get("target", ""))
        custom_name = str(payload.get("user_name", "")).strip()
        if session_id in _ACTIVE_PEERS:
            _ACTIVE_PEERS[session_id]["focused_target"] = target
            if custom_name:
                _ACTIVE_PEERS[session_id]["user"] = custom_name
            aid = _ACTIVE_PEERS[session_id].get("article_id", "")
            if aid:
                await _broadcast_presence(aid)

    # Debounced Autosave & Manuelles Speichern (inkl. 3-Wege-Block-Merge & Live-Broadcast)
    @reactive.effect
    @reactive.event(input.lukb_autosave_payload)
    async def _on_autosave() -> None:
        payload = input.lukb_autosave_payload()
        if not isinstance(payload, dict) or "article" not in payload:
            return
        try:
            doc = ArticleDocument.model_validate(payload["article"])
            base_doc = None
            if payload.get("base_article"):
                try:
                    base_doc = ArticleDocument.model_validate(payload["base_article"])
                except Exception:
                    base_doc = None

            user_label = _ACTIVE_PEERS.get(session_id, {}).get("user") or _current_user()
            save_info = save_article(
                doc=doc,
                user=user_label,
                create_revision=bool(payload.get("create_revision", False)),
                revision_note=str(payload.get("revision_note", "")),
                base_doc=base_doc,
            )
            merged_doc = ArticleDocument.model_validate(save_info["article"])
            current_article_id.set(merged_doc.id)
            current_doc.set(merged_doc)

            await session.send_custom_message("lukb_autosave_ack", save_info)
            await _send_article_list(merged_doc.id)
            await _send_preview(merged_doc)

            # Synchronisiere alle Co-Autoren (und bei erfolgtem DB-Merge auch den Sender selbst)
            await _broadcast_article_sync(
                article_id=merged_doc.id,
                doc=merged_doc,
                sender_session_id=session_id,
                author_name=user_label,
                include_sender=bool(save_info.get("merged", False)),
            )
            # Aktualisiere auch die Live-Vorschau bei allen Co-Autoren im selben Artikel
            for sid, info in list(_ACTIVE_PEERS.items()):
                if sid != session_id and info.get("article_id") == merged_doc.id:
                    peer_sess: Session | None = info.get("session")
                    if peer_sess is not None:
                        try:
                            svg_pages = render_preview_svg_pages(merged_doc)
                            web_html = render_web_html(merged_doc)
                            await peer_sess.send_custom_message(
                                "lukb_update_preview",
                                {"svg_pages": svg_pages, "web_html": web_html},
                            )
                        except Exception:
                            pass
        except Exception as exc:
            logger.exception("Fehler beim Speichern des Artikels")
            ui.notification_show(f"Speicherfehler: {exc}", type="error")

    # + Neue Publikation anlegen
    @reactive.effect
    @reactive.event(input.btn_new_article)
    async def _on_new_article() -> None:
        new_doc = create_new_article(user=_current_user())
        await _load_and_broadcast_article(new_doc.id)
        ui.notification_show("Neue Publikation wurde angelegt.", type="message", duration=3)

    # Artikel duplizieren
    @reactive.effect
    @reactive.event(input.btn_duplicate_article)
    async def _on_duplicate_article() -> None:
        aid = current_article_id.get()
        if not aid:
            return
        dup_doc = duplicate_article(aid, user=_current_user())
        if dup_doc:
            await _load_and_broadcast_article(dup_doc.id)
            ui.notification_show("Publikation wurde dupliziert.", type="message", duration=3)

    # Artikel löschen
    @reactive.effect
    @reactive.event(input.btn_delete_article)
    async def _on_delete_article() -> None:
        aid = current_article_id.get()
        if not aid:
            return
        all_items = list_articles()
        if len(all_items) <= 1:
            ui.notification_show(
                "Der letzte verbleibende Artikel kann nicht gelöscht werden.",
                type="warning",
                duration=4,
            )
            return
        delete_article(aid)
        remaining = list_articles()
        next_id = remaining[0]["id"] if remaining else ""
        await _load_and_broadcast_article(next_id)
        ui.notification_show("Publikation wurde gelöscht.", type="message", duration=3)

    # Manueller Preview-Refresh
    @reactive.effect
    @reactive.event(input.btn_refresh_preview)
    async def _on_refresh_preview() -> None:
        doc = current_doc.get()
        if doc is not None:
            await _send_preview(doc)

    # PDF-Export via Typst
    @render.download(
        filename=lambda: f"{_slugify_filename(current_doc.get().metadata.title if current_doc.get() else 'Publikation')}.pdf",
        media_type="application/pdf",
    )
    def download_pdf():
        doc = current_doc.get()
        if doc is None:
            return
        yield render_pdf_bytes(doc)

    # Web-HTML-Export via Jinja2
    @render.download(
        filename=lambda: f"{_slugify_filename(current_doc.get().metadata.title if current_doc.get() else 'Publikation')}.html",
        media_type="text/html",
    )
    def download_html():
        doc = current_doc.get()
        if doc is None:
            return
        yield render_web_html(doc).encode("utf-8")


app = App(app_ui, server, static_assets=WWW_DIR)
