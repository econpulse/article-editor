"""
LUKB Investment Office — Content-Management-System & Publikations-Editor
Einstiegspunkt für Shiny for Python & Posit Connect Deployment.
"""

from __future__ import annotations

import base64
from datetime import datetime
import logging
import re
from typing import Any
from shiny import App, Inputs, Outputs, Session, reactive, render, ui

from config import (
    DATABASE_BACKEND_LABEL,
    WWW_DIR,
    can_delete,
    can_publish,
    get_user_role,
)
from database.repository import (
    create_new_article,
    delete_article,
    duplicate_article,
    get_article,
    get_asset,
    init_db_and_seed,
    list_articles,
    list_available_tickers,
    publish_article_to_portal,
    restore_article,
    save_article,
    save_asset,
    search_tickers,
    unpublish_article_from_portal,
)
from schemas.article import ArticleDocument
from services.chart_generator import generate_db_chart_svg
from services.connect_client import get_portal_target_url
from services.renderer import (
    list_available_templates,
    render_docx_bytes,
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


# ============================================================================
# Shiny UI Definition (3-Spalten-Layout im LUKB Corporate Design)
# ============================================================================

templates_list = list_available_templates()


def _asset_version() -> str:
    try:
        js_m = int((WWW_DIR / "js" / "editor.js").stat().st_mtime)
        css_m = int((WWW_DIR / "css" / "editor.css").stat().st_mtime)
        return f"{max(js_m, css_m)}"
    except Exception:
        return "2"


_ASSET_VER = _asset_version()

app_ui = ui.page_fluid(
    ui.head_content(
        ui.tags.meta(charset="utf-8"),
        ui.tags.meta(name="viewport", content="width=device-width, initial-scale=1"),
        ui.tags.title("LUKB Investment Office — Publikations-Editor & CMS"),
        ui.tags.link(rel="stylesheet", href=f"css/editor.css?v={_ASSET_VER}"),
        ui.tags.script(src="js/vendor/Sortable.min.js"),
        ui.tags.script(src=f"js/editor.js?v={_ASSET_VER}"),
    ),
    # ------------------------------------------------------------------------
    # Top Header Bar
    # ------------------------------------------------------------------------
    ui.div(
        ui.div(
            ui.tags.button(
                "☰ Publikationen",
                id="btn-toggle-sidebar",
                type="button",
                class_="btn-lukb btn-lukb-outline-light btn-lukb-sm",
                title="Linke Publikations-Sidebar ein- oder ausklappen (Ctrl+B)",
                onclick="if(window.lukbToggleSidebar){window.lukbToggleSidebar();}",
            ),
            ui.tags.button(
                "🔍 Alle durchsuchen (Ctrl+K)",
                id="btn-open-pub-modal",
                type="button",
                class_="btn-lukb btn-lukb-outline-light btn-lukb-sm",
                title="Such- & Publikations-Dialog öffnen (Ctrl+K)",
                onclick="if(window.lukbOpenPubModal){window.lukbOpenPubModal();}",
            ),
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
            ui.span(
                "📊 0 Wörter · ~1 Min. · ca. 0.5 Seiten",
                id="lukb-stats-counter",
                class_="editor-stats-badge",
                title="Live-Wortzählung, Lesezeit (~200 WpM) und geschätzter A4-Füllstand",
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
            # Menü 1: Portal (Statische Posit Connect Plattform)
            ui.div(
                ui.tags.button(
                    "🌐 Portal ▾",
                    type="button",
                    class_="btn-lukb btn-lukb-success lukb-dropdown-toggle",
                    title="Aktionen für das statische Content-Portal (Posit Connect)",
                ),
                ui.div(
                    ui.tags.button(
                        "🌐 Auf Portal publizieren",
                        type="button",
                        class_="lukb-dropdown-item",
                        title="Diesen Artikel auf das statische Portal veröffentlichen oder aktualisieren (Senior Editor / Admin)",
                        onclick="Shiny.setInputValue('lukb_publish_portal', Math.random(), {priority: 'event'});",
                    ),
                    ui.tags.button(
                        "📤 Zur Prüfung einreichen",
                        type="button",
                        class_="lukb-dropdown-item",
                        title="Status auf 'In Review' setzen (zur Freigabe durch Senior Editor)",
                        onclick="Shiny.setInputValue('lukb_submit_review', Math.random(), {priority: 'event'});",
                    ),
                    ui.tags.button(
                        "❌ Vom Portal zurückziehen",
                        type="button",
                        class_="lukb-dropdown-item text-danger",
                        title="Artikel vom statischen Portal entfernen (Sicherheitsabfrage)",
                        onclick="Shiny.setInputValue('lukb_unpublish_portal', Math.random(), {priority: 'event'});",
                    ),
                    ui.tags.div(class_="lukb-dropdown-divider"),
                    ui.tags.a(
                        "↗ Portal ansehen",
                        href=get_portal_target_url(),
                        target="_blank",
                        class_="lukb-dropdown-item",
                        title="Öffnet das statische Content-Portal in einem neuen Browser-Tab",
                    ),
                    ui.download_button(
                        "download_portal_bundle",
                        "📦 Portal-Bundle herunterladen (.tar.gz)",
                        class_="lukb-dropdown-item",
                        title="Gesamtes statisches Portal als Posit Connect Deploy-Bundle herunterladen",
                    ),
                    class_="lukb-dropdown-menu",
                ),
                class_="lukb-dropdown",
            ),
            # Menü 2: Export (Dokumentenformate)
            ui.div(
                ui.tags.button(
                    "📥 Export ▾",
                    type="button",
                    class_="btn-lukb btn-lukb-primary lukb-dropdown-toggle",
                    title="Publikation exportieren (PDF, Word, Web-HTML)",
                ),
                ui.div(
                    ui.download_button(
                        "download_pdf",
                        "📄 PDF Export (Typst)",
                        class_="lukb-dropdown-item",
                        title="Druckreifes Typst-PDF im LUKB Corporate Design herunterladen",
                    ),
                    ui.download_button(
                        "download_docx",
                        "📝 Word Export (.docx)",
                        class_="lukb-dropdown-item",
                        title="Microsoft Word Dokument herunterladen",
                    ),
                    ui.download_button(
                        "download_html",
                        "🌐 Web-HTML Export",
                        class_="lukb-dropdown-item",
                        title="Eigenständige Web-HTML-Datei herunterladen",
                    ),
                    class_="lukb-dropdown-menu",
                ),
                class_="lukb-dropdown",
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
        # Linke Spalte: Gruppierte & einklappbare Artikel-Sidebar
        # ====================================================================
        ui.tags.aside(
            ui.div(
                ui.div(
                    ui.div(
                        ui.h2("Publikationen", class_="sidebar-title"),
                        ui.span("0 Artikel", id="sidebar-article-count", class_="sidebar-count-pill"),
                        style="display:flex;align-items:center;gap:8px;",
                    ),
                    ui.div(
                        ui.tags.button(
                            "⤢ Dialog",
                            id="btn-sidebar-open-modal",
                            type="button",
                            class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                            title="Grosses Publikations-Verzeichnis & Suche öffnen (Ctrl+K)",
                            style="padding:3px 8px;font-size:11.5px;",
                            onclick="if(window.lukbOpenPubModal){window.lukbOpenPubModal();}",
                        ),
                        ui.tags.button(
                            "«",
                            id="btn-sidebar-collapse-inner",
                            type="button",
                            class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                            title="Sidebar einklappen (Ctrl+B)",
                            style="padding:3px 8px;font-size:13px;",
                            onclick="if(window.lukbSetSidebarCollapsed){window.lukbSetSidebarCollapsed(true);}",
                        ),
                        style="display:flex;align-items:center;gap:4px;",
                    ),
                    class_="sidebar-title-row",
                ),
                ui.div(
                    ui.input_action_button(
                        "btn_new_article",
                        "+ Neue Publikation anlegen",
                        class_="btn-lukb btn-lukb-navy",
                        style="width:100%;margin-bottom:4px;",
                    ),
                    ui.tags.input(
                        id="sidebar_search",
                        type="search",
                        class_="cms-input",
                        placeholder="Schnellfilter (Titel, Autor, Rubrik) …",
                        oninput="Shiny.setInputValue('sidebar_search_query', this.value, {priority: 'event'})",
                    ),
                    ui.tags.select(
                        ui.tags.option("Alle aktiven Publikationen", value="all"),
                        ui.tags.option("Nur In Bearbeitung (Entwurf & Review)", value="active_work"),
                        ui.tags.option("Status: Entwurf", value="draft"),
                        ui.tags.option("Status: In Review", value="review"),
                        ui.tags.option("Status: Publiziert (Live)", value="published"),
                        ui.tags.option("📦 Papierkorb / Archiv", value="archived"),
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
                    title="Verschiebt den aktuellen Entwurf in den Papierkorb (Soft-Delete)",
                ),
                ui.input_action_button(
                    "btn_restore_article",
                    "Wiederherstellen",
                    class_="btn-lukb btn-lukb-secondary btn-lukb-sm",
                    style="flex:1;",
                    title="Stellt einen archivierten Artikel wieder in den Entwurf-Status her",
                ),
                style="padding:10px 12px;border-top:1px solid #D6DEE8;display:flex;gap:6px;background:#F4F7FA;",
            ),
            id="lukb-sidebar",
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
                # Zeile 5b: Themen-Tags / Schlagwörter
                ui.div(
                    ui.div(
                        ui.tags.label("Themen-Tags / Schlagwörter", class_="field-label", style="margin:0;"),
                        ui.span("Mit Enter oder Komma hinzufügen", style="font-size:11.5px;color:#5A687C;"),
                        style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;",
                    ),
                    ui.div(
                        ui.div(id="meta-tags-container", class_="tags-chips-container"),
                        ui.tags.input(
                            id="meta-tag-input",
                            type="text",
                            class_="cms-input tag-input-field",
                            placeholder="+ Tag eingeben und Enter drücken (z.B. Aktien, SNB, Zinsen, Inflation) …",
                        ),
                        class_="tags-editor-box",
                    ),
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
                        "+ Grafik (Upload)",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "figure"},
                    ),
                    ui.tags.button(
                        "+ DB-Chart (Zeitreihe)",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        style="border-color:#009FE3;background:#F0F9FF;color:#002855;",
                        **{"data-add-block-type": "db_chart"},
                        title="Zeitreihen-Diagramm direkt aus der MSSQL-Tabelle ts_db erstellen (max. 5 Ticker)",
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
                    ui.tags.button(
                        "+ Abstand",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "spacer"},
                        title="Fügt einen einstellbaren vertikalen Abstandhalter (Spacer in mm) ein",
                    ),
                    ui.tags.button(
                        "+ Spaltenumbruch",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        style="border-color:#C59B27;background:#FFFBEB;color:#78350F;",
                        **{"data-add-block-type": "colbreak"},
                        title="Erzwingt an dieser Position den Umbruch in die nächste Spalte (colbreak)",
                    ),
                    ui.tags.button(
                        "+ Zitat",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        style="border-color:#009FE3;background:#F0F9FF;color:#002855;",
                        **{"data-add-block-type": "quote"},
                        title="Fügt ein typografisches Zitat / Pull-Quote mit Autoren- und Quellenzeile ein",
                    ),
                    ui.tags.button(
                        "+ Trennlinie",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "divider"},
                        title="Fügt eine horizontale Trennlinie (durchgezogen, gestrichelt, gepunktet) ein",
                    ),
                    ui.tags.button(
                        "+ Fussnoten",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        **{"data-add-block-type": "footnotes"},
                        title="Fügt einen strukturierten Fussnoten- / Quellenapparat ein",
                    ),
                    ui.tags.button(
                        "+ Glossar",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        style="border-color:#009FE3;background:#EBF5FB;color:#002855;",
                        **{"data-add-block-type": "glossary"},
                        title="Fügt ein Glossar-Verzeichnis am Textende ein (sammelt automatisch alle im Artikel markierten Begriffe)",
                    ),
                    ui.tags.button(
                        "+ Weitere Publikationen",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        style="border-color:#005A9C;background:#F0F5FA;color:#002855;",
                        **{"data-add-block-type": "publications"},
                        title="Fügt eine Box 'Weitere Publikationen' ein (automatisch mit den letzten 5 Publikationen vorbefüllt)",
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
        id="lukb-workspace",
        class_="cms-workspace",
    ),
    # ------------------------------------------------------------------------
    # Such- & Publikations-Dialog (Modal / Command Palette, Ctrl+K)
    # ------------------------------------------------------------------------
    ui.div(
        ui.div(
            # Modal Header
            ui.div(
                ui.div(
                    ui.h2("Publikations-Verzeichnis & Suche", class_="pub-modal-title"),
                    ui.span("0 Publikationen", id="pub-modal-count-badge", class_="sidebar-count-pill"),
                    style="display:flex;align-items:center;gap:10px;",
                ),
                ui.div(
                    ui.tags.button(
                        "+ Neue Publikation",
                        id="btn-modal-new-article",
                        type="button",
                        class_="btn-lukb btn-lukb-navy btn-lukb-sm",
                    ),
                    ui.tags.button(
                        "✕ Schliessen (Esc)",
                        id="btn-close-pub-modal",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        onclick="if(window.lukbClosePubModal){window.lukbClosePubModal();}",
                    ),
                    style="display:flex;align-items:center;gap:8px;",
                ),
                class_="pub-modal-header",
            ),
            # Modal Filter & Search Bar
            ui.div(
                ui.div(
                    ui.tags.input(
                        id="pub-modal-search",
                        type="search",
                        class_="cms-input pub-modal-search-input",
                        placeholder="🔍 Titel, Untertitel, Autor, Rubrik oder Datum durchsuchen …",
                    ),
                    class_="pub-modal-search-row",
                ),
                ui.div(
                    ui.div(
                        ui.tags.button(
                            "Alle",
                            type="button",
                            class_="pub-filter-pill active",
                            **{"data-modal-status": "all"},
                        ),
                        ui.tags.button(
                            "In Bearbeitung",
                            type="button",
                            class_="pub-filter-pill",
                            **{"data-modal-status": "active_work"},
                        ),
                        ui.tags.button(
                            "Entwurf",
                            type="button",
                            class_="pub-filter-pill",
                            **{"data-modal-status": "draft"},
                        ),
                        ui.tags.button(
                            "In Review",
                            type="button",
                            class_="pub-filter-pill",
                            **{"data-modal-status": "review"},
                        ),
                        ui.tags.button(
                            "Publiziert",
                            type="button",
                            class_="pub-filter-pill",
                            **{"data-modal-status": "published"},
                        ),
                        class_="pub-modal-status-pills",
                    ),
                    ui.div(
                        ui.tags.select(
                            ui.tags.option("Alle Templates", value="all"),
                            ui.tags.option("Investment Fokus", value="investment_focus"),
                            ui.tags.option("Market Flash", value="market_flash"),
                            id="pub-modal-template-filter",
                            class_="cms-select pub-modal-select",
                        ),
                        ui.tags.select(
                            ui.tags.option("Alle Rubriken", value="all"),
                            id="pub-modal-category-filter",
                            class_="cms-select pub-modal-select",
                        ),
                        ui.tags.select(
                            ui.tags.option("Sortierung: Zuletzt geändert", value="updated_desc"),
                            ui.tags.option("Sortierung: Publikationsdatum", value="pubdate_desc"),
                            ui.tags.option("Sortierung: Titel (A–Z)", value="title_asc"),
                            id="pub-modal-sort",
                            class_="cms-select pub-modal-select",
                        ),
                        class_="pub-modal-dropdowns",
                    ),
                    class_="pub-modal-filter-bar",
                ),
                class_="pub-modal-controls",
            ),
            # Modal Table Content
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Status", style="width:110px;"),
                            ui.tags.th("Titel & Untertitel"),
                            ui.tags.th("Rubrik & Template", style="width:185px;"),
                            ui.tags.th("Autor(en)", style="width:170px;"),
                            ui.tags.th("Publ.-Datum", style="width:105px;"),
                            ui.tags.th("Zuletzt geändert", style="width:135px;"),
                            ui.tags.th("Aktionen", style="width:155px;text-align:right;"),
                        )
                    ),
                    ui.tags.tbody(id="pub-modal-tbody"),
                    class_="pub-modal-table",
                ),
                class_="pub-modal-table-wrap",
            ),
            # Modal Footer & Pagination
            ui.div(
                ui.span("Tipp: Mit Ctrl+K jederzeit öffnen · Ctrl+B klappt die linke Sidebar ein/aus", class_="pub-modal-hint"),
                ui.div(id="pub-modal-pagination", class_="pub-modal-pagination"),
                class_="pub-modal-footer",
            ),
            class_="pub-modal-dialog",
        ),
        id="lukb-pub-modal-backdrop",
        class_="pub-modal-backdrop",
        style="display:none;",
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
        all_items = (
            items
            if (not search_q.strip() and status_f == "all")
            else list_articles(search_query="", status_filter="all")
        )
        await session.send_custom_message(
            "lukb_update_article_list",
            {
                "articles": items,
                "all_articles": all_items,
                "active_id": active_id,
                "sidebar_search_active": bool(search_q.strip()),
                "sidebar_status_filter": status_f,
            },
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
            {
                "article": doc.model_dump(),
                "assets": assets_map,
                "available_tickers": list_available_tickers(limit=25),
                "self_session_id": session_id,
            },
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

    # Einzelne DB-Chart-Vorschau im Block sofort aktualisieren
    @reactive.effect
    @reactive.event(input.lukb_preview_db_chart)
    async def _on_preview_db_chart() -> None:
        payload = input.lukb_preview_db_chart()
        if not isinstance(payload, dict) or "block" not in payload:
            return
        blk = payload["block"]
        bid = blk.get("id", "")
        if not bid:
            return
        svg_markup = generate_db_chart_svg(blk)
        b64 = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
        await session.send_custom_message(
            "lukb_db_chart_svg",
            {
                "block_id": bid,
                "data_uri": f"data:image/svg+xml;base64,{b64}",
            },
        )

    # Schnelle Ticker-Autovervollständigung für tausende Ticker in ts_db
    @reactive.effect
    @reactive.event(input.lukb_search_tickers)
    async def _on_search_tickers() -> None:
        payload = input.lukb_search_tickers()
        if not isinstance(payload, dict):
            return
        query = str(payload.get("query", ""))
        req_id = payload.get("request_id", 0)
        results = search_tickers(query=query, limit=15)
        await session.send_custom_message(
            "lukb_ticker_suggestions",
            {
                "request_id": req_id,
                "query": query,
                "results": results,
            },
        )

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

            save_info["assets"] = _collect_article_assets_map(merged_doc)
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

    # Artikel löschen (mit Rollenprüfung, Publiziert-Schutz & Sicherheits-Modal)
    @reactive.effect
    @reactive.event(input.btn_delete_article)
    async def _on_delete_article() -> None:
        aid = current_article_id.get()
        doc = current_doc.get()
        if not aid or not doc:
            return

        user = _current_user()
        if not can_delete(user):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf keine Publikationen löschen / archivieren.",
                type="warning",
                duration=5,
            )
            return

        # Schutz: Publizierte Publikationen dürfen NICHT gelöscht werden
        if doc.status == "published":
            ui.modal_show(
                ui.modal(
                    ui.div(
                        ui.p(
                            f"Die Publikation «{doc.metadata.title}» ist aktuell im statischen Portal online geschaltet.",
                            style="font-weight:600;color:#c0392b;font-size:14.5px;margin-bottom:8px;",
                        ),
                        ui.p(
                            "Online geschaltete Dokumente können nicht gelöscht werden, um tote Links und verwaiste PDFs im Intranet zu vermeiden. "
                            "Bitte ziehen Sie die Publikation zuerst über das Menü «🌐 Portal ▾ -> Vom Portal zurückziehen» zurück.",
                            style="color:#5A687C;font-size:13px;line-height:1.5;margin-bottom:0;",
                        ),
                    ),
                    title="Löschen nicht möglich (Publiziert)",
                    footer=ui.modal_button("Verstanden", class_="btn-lukb btn-lukb-primary"),
                    size="m",
                    easy_close=True,
                )
            )
            return

        all_items = list_articles()
        if len(all_items) <= 1:
            ui.notification_show(
                "Der letzte verbleibende Artikel kann nicht gelöscht werden.",
                type="warning",
                duration=4,
            )
            return

        # Sicherheits-Bestätigungsdialog für Soft-Delete
        ui.modal_show(
            ui.modal(
                ui.div(
                    ui.p(
                        f"Möchten Sie die Publikation «{doc.metadata.title}» wirklich löschen?",
                        style="font-size:14.5px;font-weight:600;color:#002855;margin-bottom:10px;",
                    ),
                    ui.p(
                        "Der Artikel wird sicher in das Archiv verschoben (Soft-Delete) und aus der aktiven Übersicht ausgeblendet. "
                        "Er kann jederzeit von einem Administrator wiederhergestellt werden.",
                        style="font-size:13px;color:#5A687C;margin-bottom:0;line-height:1.5;",
                    ),
                ),
                title="Publikation archivieren (Soft-Delete)",
                footer=ui.div(
                    ui.modal_button("Abbrechen", class_="btn-lukb btn-lukb-ghost"),
                    ui.input_action_button(
                        "btn_confirm_delete_article",
                        "In Archiv verschieben",
                        class_="btn-lukb btn-lukb-danger",
                    ),
                    style="display:flex;gap:10px;justify-content:flex-end;width:100%;",
                ),
                size="m",
                easy_close=True,
            )
        )

    # Bestätigung des Soft-Deletes ausführen
    @reactive.effect
    @reactive.event(input.btn_confirm_delete_article)
    async def _on_confirm_delete_article() -> None:
        ui.modal_remove()
        aid = current_article_id.get()
        if not aid:
            return
        delete_article(aid, user=_current_user())
        remaining = list_articles()
        next_id = remaining[0]["id"] if remaining else ""
        if next_id:
            await _load_and_broadcast_article(next_id)
        else:
            await _send_article_list("")
        ui.notification_show("Publikation wurde in das Archiv verschoben (Soft-Delete).", type="message", duration=4)

    # Artikel aus dem Archiv wiederherstellen (Restore)
    @reactive.effect
    @reactive.event(input.btn_restore_article)
    async def _on_restore_article() -> None:
        aid = current_article_id.get()
        if not aid:
            return
        user = _current_user()
        if not can_delete(user):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf keine Publikationen wiederherstellen.",
                type="warning",
                duration=5,
            )
            return
        ok = restore_article(aid, user=user)
        if ok:
            await _load_and_broadcast_article(aid)
            ui.notification_show("Publikation wurde aus dem Archiv wiederhergestellt (Status: Entwurf).", type="message", duration=4)
        else:
            ui.notification_show("Dieser Artikel ist nicht archiviert.", type="info", duration=3)

    # Aktionen direkt aus dem Publikations-Dialog (Modal: Neu, Duplizieren, Löschen)
    @reactive.effect
    @reactive.event(input.lukb_modal_article_action)
    async def _on_modal_article_action() -> None:
        payload = input.lukb_modal_article_action()
        if not isinstance(payload, dict):
            return
        action = payload.get("action", "")
        target_id = payload.get("id", "")
        if action == "create":
            new_doc = create_new_article(user=_current_user())
            await _load_and_broadcast_article(new_doc.id)
            ui.notification_show("Neue Publikation wurde angelegt.", type="message", duration=3)
        elif action == "duplicate" and target_id:
            dup_doc = duplicate_article(target_id, user=_current_user())
            if dup_doc:
                await _load_and_broadcast_article(dup_doc.id)
                ui.notification_show("Publikation wurde dupliziert.", type="message", duration=3)
        elif action == "delete" and target_id:
            user = _current_user()
            if not can_delete(user):
                ui.notification_show("Nur Administratoren oder Senior Editoren dürfen Publikationen löschen.", type="warning", duration=5)
                return
            target_doc = get_article(target_id)
            if target_doc and target_doc.status == "published":
                ui.notification_show("Publizierte Artikel können nicht gelöscht werden. Bitte zuerst zurückziehen.", type="warning", duration=5)
                return
            all_items = list_articles()
            if len(all_items) <= 1:
                ui.notification_show(
                    "Der letzte verbleibende Artikel kann nicht gelöscht werden.",
                    type="warning",
                    duration=4,
                )
                return
            delete_article(target_id, user=user)
            if current_article_id.get() == target_id:
                remaining = list_articles()
                next_id = remaining[0]["id"] if remaining else ""
                await _load_and_broadcast_article(next_id)
            else:
                await _send_article_list(current_article_id.get())
            ui.notification_show("Publikation wurde in das Archiv verschoben (Soft-Delete).", type="message", duration=3)

    # Manueller Preview-Refresh
    @reactive.effect
    @reactive.event(input.btn_refresh_preview)
    async def _on_refresh_preview() -> None:
        doc = current_doc.get()
        if doc is not None:
            await _send_preview(doc)

    # ------------------------------------------------------------------------
    # Freigabe-Workflow: Zur Prüfung einreichen (Autor -> Review)
    # ------------------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.lukb_submit_review)
    async def _on_submit_review() -> None:
        doc = current_doc.get()
        if not doc:
            return
        if doc.status == "published":
            ui.notification_show("Publikation ist bereits im Portal veröffentlicht.", type="info", duration=4)
            return
        doc.status = "review"
        current_doc.set(doc)
        save_article(
            doc,
            user=_current_user(),
            create_revision=True,
            revision_note="Zur Prüfung / Freigabe eingereicht (Status: review)",
        )
        await _send_article_list(doc.id)
        ui.notification_show(
            "✅ Publikation zur Freigabe eingereicht (Status: In Review). Ein Senior Editor kann den Artikel nun prüfen und publizieren.",
            type="message",
            duration=6,
        )

    # ------------------------------------------------------------------------
    # Statisches Content-Portal: Publizieren & Zurückziehen (mit Rollenprüfung & Modal)
    # ------------------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.lukb_publish_portal)
    async def _on_publish_portal() -> None:
        doc = current_doc.get()
        if not doc:
            return
        user = _current_user()
        if not can_publish(user):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf nicht publizieren. Bitte reichen Sie den Artikel 'Zur Prüfung' ein.",
                type="warning",
                duration=6,
            )
            return
        try:
            res = publish_article_to_portal(doc.id, user=user)
            if res.get("success"):
                doc.status = "published"
                current_doc.set(doc)
                await _send_article_list(doc.id)
                count = res.get("total_published", 1)
                connect_info = res.get("connect_deploy")
                if connect_info and connect_info.get("deployed"):
                    ui.notification_show(
                        f"✅ Artikel publiziert & auf Posit Connect bereitgestellt! ({count} online)",
                        type="message",
                        duration=5,
                    )
                elif connect_info and not connect_info.get("success"):
                    ui.notification_show(
                        f"⚠️ Lokal publiziert, aber Connect-Update fehlgeschlagen: {connect_info.get('error')}",
                        type="warning",
                        duration=8,
                    )
                else:
                    ui.notification_show(
                        f"ℹ️ Lokal publiziert ({count} Artikel). Posit Connect nicht gekoppelt (CONNECT_PORTAL_GUID fehlt in Umgebungsvariablen).",
                        type="message",
                        duration=7,
                    )
            else:
                ui.notification_show(f"Publikationsfehler: {res.get('error')}", type="warning", duration=5)
        except Exception as exc:
            ui.notification_show(f"Fehler beim Publizieren: {exc}", type="error", duration=6)

    # Sicherheitsabfrage für "Vom Portal zurückziehen"
    @reactive.effect
    @reactive.event(input.lukb_unpublish_portal)
    async def _on_unpublish_portal() -> None:
        doc = current_doc.get()
        if not doc:
            return
        user = _current_user()
        if not can_publish(user):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf keine Publikationen vom Portal zurückziehen.",
                type="warning",
                duration=6,
            )
            return
        if doc.status != "published":
            ui.notification_show("Dieser Artikel ist aktuell nicht im Portal publiziert.", type="info", duration=4)
            return

        ui.modal_show(
            ui.modal(
                ui.div(
                    ui.p(
                        f"Möchten Sie die Publikation «{doc.metadata.title}» wirklich vom statischen Intranet-Portal entfernen?",
                        style="font-size:14.5px;font-weight:600;color:#002855;margin-bottom:10px;",
                    ),
                    ui.p(
                        "Das Dokument und das zugehörige PDF sind danach für Mitarbeitende im Intranet nicht mehr abrufbar. "
                        "Der Arbeitsstatus im CMS wird wieder auf 'Entwurf' zurückgesetzt. Ihre Texte und Daten bleiben dabei vollständig erhalten.",
                        style="font-size:13px;color:#5A687C;margin-bottom:0;line-height:1.5;",
                    ),
                ),
                title="Publikation vom Portal zurückziehen",
                footer=ui.div(
                    ui.modal_button("Abbrechen", class_="btn-lukb btn-lukb-ghost"),
                    ui.input_action_button(
                        "btn_confirm_unpublish",
                        "Vom Portal zurückziehen",
                        class_="btn-lukb btn-lukb-danger",
                    ),
                    style="display:flex;gap:10px;justify-content:flex-end;width:100%;",
                ),
                size="m",
                easy_close=True,
            )
        )

    # Bestätigung des Zurückziehens ausführen
    @reactive.effect
    @reactive.event(input.btn_confirm_unpublish)
    async def _on_confirm_unpublish() -> None:
        ui.modal_remove()
        doc = current_doc.get()
        if not doc:
            return
        try:
            res = unpublish_article_from_portal(doc.id, user=_current_user(), new_status="draft")
            if res.get("success"):
                doc.status = "draft"
                current_doc.set(doc)
                await _send_article_list(doc.id)
                connect_info = res.get("connect_deploy")
                if connect_info and connect_info.get("deployed"):
                    ui.notification_show(
                        "✅ Artikel vom Portal zurückgezogen & auf Posit Connect entfernt.",
                        type="message",
                        duration=5,
                    )
                elif connect_info and not connect_info.get("success"):
                    ui.notification_show(
                        f"⚠️ Lokal entfernt, aber Connect-Update fehlgeschlagen: {connect_info.get('error')}",
                        type="warning",
                        duration=8,
                    )
                else:
                    ui.notification_show(
                        "Artikel vom Portal zurückgezogen (Status auf 'Entwurf' gesetzt).",
                        type="message",
                        duration=5,
                    )
            else:
                ui.notification_show(f"Fehler: {res.get('error')}", type="warning", duration=5)
        except Exception as exc:
            ui.notification_show(f"Fehler: {exc}", type="error", duration=6)

    # Posit Connect Static Bundle Download (.tar.gz)
    @render.download_button(
        filename=lambda: f"connect_static_portal_{datetime.now().strftime('%Y%m%d_%H%M')}.tar.gz",
        media_type="application/gzip",
    )
    def download_portal_bundle():
        from services.portal_publisher import create_connect_bundle
        bundle_path = create_connect_bundle()
        return str(bundle_path)

    # Word-Export (.docx) via python-docx
    @render.download_button(
        filename=lambda: f"{_slugify_filename(current_doc.get().metadata.title if current_doc.get() else 'Publikation')}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    def download_docx():
        doc = current_doc.get()
        if doc is None:
            return
        yield render_docx_bytes(doc)

    # PDF-Export via Typst
    @render.download_button(
        filename=lambda: f"{_slugify_filename(current_doc.get().metadata.title if current_doc.get() else 'Publikation')}.pdf",
        media_type="application/pdf",
    )
    def download_pdf():
        doc = current_doc.get()
        if doc is None:
            return
        yield render_pdf_bytes(doc)

    # Web-HTML-Export via Jinja2
    @render.download_button(
        filename=lambda: f"{_slugify_filename(current_doc.get().metadata.title if current_doc.get() else 'Publikation')}.html",
        media_type="text/html",
    )
    def download_html():
        doc = current_doc.get()
        if doc is None:
            return
        yield render_web_html(doc).encode("utf-8")


app = App(app_ui, server, static_assets=WWW_DIR)

# Statisches Content-Portal lokal unter /portal/ und /portal mounten (vor der Starlette Catch-All Route!)
try:
    from starlette.staticfiles import StaticFiles
    from starlette.routing import Mount, Route
    from starlette.responses import RedirectResponse
    from config import STATIC_PORTAL_DIR

    STATIC_PORTAL_DIR.mkdir(parents=True, exist_ok=True)

    async def _portal_redirect(request):
        return RedirectResponse(url="/portal/")

    # Am Anfang der Starlette-Routenliste einfügen, damit /portal und /portal/ vor dem WWW_DIR-Catch-All greifen
    app.starlette_app.routes.insert(0, Route("/portal", _portal_redirect))
    app.starlette_app.routes.insert(1, Mount("/portal", StaticFiles(directory=str(STATIC_PORTAL_DIR), html=True), name="portal"))
except Exception:
    pass
