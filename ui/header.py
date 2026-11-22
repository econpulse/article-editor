from __future__ import annotations

from shiny import ui

from config import DATABASE_BACKEND_LABEL
from services.connect_client import get_portal_target_url


def header_ui() -> ui.Tag:
    """Rendert die Top-Header-Bar des CMS inklusive Schnellaktionen und Dropdowns."""
    return ui.div(
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
            class_="cms-topbar-center",
        ),
        ui.div(
            ui.tags.button(
                "Meilenstein speichern",
                id="btn-manual-snapshot",
                type="button",
                class_="btn-lukb btn-lukb-outline-light",
                title="Speichert sofort und legt einen Revisions-Snapshot in der Datenbank an (Ctrl+S)",
            ),
            # Menü 0: Workflow (Historie, Freigaben, Prüfaufträge, Mediathek, Admin)
            ui.div(
                ui.tags.button(
                    "⚙ Workflow ▾",
                    id="btn-open-workflow-menu",
                    type="button",
                    class_="btn-lukb btn-lukb-outline-light lukb-dropdown-toggle",
                    title="Historie, Freigaben, Prüfaufträge, Mediathek & Admin-Dashboard",
                ),
                ui.div(
                    ui.tags.button(
                        ui.span("🕒", class_="lukb-menu-icon"),
                        ui.span("Historie"),
                        id="btn-open-revisions",
                        type="button",
                        class_="lukb-dropdown-item",
                        title="Gespeicherte Revisionen dieses Artikels anzeigen & wiederherstellen",
                        onclick="if(window.Shiny&&window.Shiny.setInputValue){window.Shiny.setInputValue('lukb_open_revisions',{ts:Date.now()},{priority:'event'});}",
                    ),
                    ui.tags.button(
                        ui.span("👥", class_="lukb-menu-icon"),
                        ui.span("Freigaben"),
                        id="btn-open-share",
                        type="button",
                        class_="lukb-dropdown-item",
                        title="Autoren & Prüfer für diesen Artikel zuweisen",
                        onclick="if(window.Shiny&&window.Shiny.setInputValue){window.Shiny.setInputValue('lukb_open_share_modal',{ts:Date.now()},{priority:'event'});}",
                    ),
                    ui.tags.button(
                        ui.span("📋", class_="lukb-menu-icon"),
                        ui.span("Prüfaufträge"),
                        id="btn-open-reviews",
                        type="button",
                        class_="lukb-dropdown-item",
                        title="Mir zugeteilte Prüfaufträge anzeigen",
                        onclick="if(window.Shiny&&window.Shiny.setInputValue){window.Shiny.setInputValue('lukb_open_review_assignments',{ts:Date.now()},{priority:'event'});}",
                    ),
                    ui.tags.button(
                        ui.span("🖼", class_="lukb-menu-icon"),
                        ui.span("Mediathek"),
                        id="btn-open-media-library",
                        type="button",
                        class_="lukb-dropdown-item",
                        title="Freigegebene Bilder & Charts aus der Mediathek suchen und einfügen",
                        onclick="if(window.Shiny&&window.Shiny.setInputValue){window.Shiny.setInputValue('lukb_open_media_library',{ts:Date.now()},{priority:'event'});}",
                    ),
                    ui.tags.div(class_="lukb-dropdown-divider"),
                    ui.tags.button(
                        ui.span("🛡", class_="lukb-menu-icon"),
                        ui.span("Admin"),
                        id="btn-open-admin",
                        type="button",
                        class_="lukb-dropdown-item",
                        title="Admin-Dashboard (Artikelzuordnungen, Benutzerrollen & Protokoll)",
                        onclick="if(window.Shiny&&window.Shiny.setInputValue){window.Shiny.setInputValue('lukb_open_admin_dashboard',{ts:Date.now()},{priority:'event'});}",
                    ),
                    class_="lukb-dropdown-menu lukb-dropdown-menu-left",
                ),
                class_="lukb-dropdown",
            ),
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
                        onclick="if(window.LUKBEditor&&window.LUKBEditor.submitForReview){window.LUKBEditor.submitForReview();}else if(window.Shiny&&window.Shiny.setInputValue){window.Shiny.setInputValue('lukb_submit_review', Math.random(), {priority: 'event'});}",
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
    )
