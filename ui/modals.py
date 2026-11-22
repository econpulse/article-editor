from __future__ import annotations

from shiny import ui

from database.permissions import VALID_ARTICLE_ROLES
from services.renderer import list_available_templates

_ADMIN_ROLE_LABELS = {
    "owner": "Verantwortlich (Owner)",
    "editor": "Mitarbeit (Editor)",
    "reviewer": "Prüfung (Reviewer)",
    "viewer": "Lesen (Viewer)",
}


def _short_template_label(tpl: dict) -> str:
    raw = str(tpl.get("name") or tpl.get("id") or "").strip()
    if raw.startswith("LUKB "):
        raw = raw[5:]
    # Kompaktes Label für das Filter-Dropdown
    if "(" in raw and "Tufte" not in raw:
        raw = raw.split("(")[0].strip()
    elif "Tufte" in raw:
        raw = "Investment Fokus (Tufte)"
    return raw


def search_modal_ui() -> ui.Tag:
    """Rendert den Such- & Publikations-Dialog (Command Palette, Ctrl+K)."""
    return ui.div(
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
                            *[
                                ui.tags.option(_short_template_label(tpl), value=tpl["id"])
                                for tpl in list_available_templates()
                            ],
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
    )


def revisions_modal_ui() -> ui.Tag:
    """Rendert den Dialog für die Revisions-Historie & Wiederherstellung."""
    return ui.div(
        ui.div(
            ui.div(
                ui.div(
                    ui.h2("Versionshistorie & Wiederherstellung", class_="pub-modal-title"),
                    ui.span("", id="rev-modal-article-title", class_="sidebar-count-pill"),
                    style="display:flex;align-items:center;gap:10px;min-width:0;",
                ),
                ui.tags.button(
                    "✕ Schliessen (Esc)",
                    id="btn-close-rev-modal",
                    type="button",
                    class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                    onclick="if(window.lukbCloseRevisionsModal){window.lukbCloseRevisionsModal();}",
                ),
                class_="pub-modal-header",
            ),
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Zeitpunkt", style="width:155px;"),
                            ui.tags.th("Autor", style="width:160px;"),
                            ui.tags.th("Notiz / Meilenstein"),
                            ui.tags.th("Umfang", style="width:105px;"),
                            ui.tags.th("Aktion", style="width:140px;text-align:right;"),
                        )
                    ),
                    ui.tags.tbody(id="rev-modal-tbody"),
                    class_="pub-modal-table",
                ),
                class_="pub-modal-table-wrap",
            ),
            ui.div(
                ui.span(
                    "Hinweis: Bei der Wiederherstellung bleibt der aktuelle Workflow-Status erhalten; zuvor wird automatisch ein Sicherungs-Snapshot angelegt.",
                    class_="pub-modal-hint",
                ),
                class_="pub-modal-footer",
            ),
            class_="pub-modal-dialog",
            style="max-width:860px;",
        ),
        id="lukb-rev-modal-backdrop",
        class_="pub-modal-backdrop",
        style="display:none;",
    )


def admin_dashboard_modal_ui() -> ui.Tag:
    """Rendert das persistente Admin-Dashboard als Overlay ohne Bootstrap-Modal-Teardown."""
    return ui.div(
        ui.div(
            ui.div(
                ui.h2("Admin-Dashboard — Artikelrechte, Benutzer & Protokoll", class_="pub-modal-title"),
                ui.tags.button(
                    "✕ Schliessen (Esc)",
                    id="btn-close-admin-modal",
                    type="button",
                    class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                    onclick="if(window.lukbCloseAdminModal){window.lukbCloseAdminModal();}",
                ),
                class_="pub-modal-header",
            ),
            ui.div(
                ui.tags.button(
                    "Artikel und Benutzer",
                    type="button",
                    class_="admin-modal-tab-btn active",
                    **{"data-admin-tab": "articles"},
                    onclick="if(window.lukbSwitchAdminTab){window.lukbSwitchAdminTab('articles');}",
                ),
                ui.tags.button(
                    "Publikationen und Protokoll",
                    type="button",
                    class_="admin-modal-tab-btn",
                    **{"data-admin-tab": "audit"},
                    onclick="if(window.lukbSwitchAdminTab){window.lukbSwitchAdminTab('audit');}",
                ),
                class_="admin-modal-tabs",
            ),
            ui.div(
                ui.div(
                    ui.div(
                        ui.input_text("admin_article_search", "Artikel suchen", value="", placeholder="Titel, Autor, Kategorie…"),
                        ui.input_checkbox("admin_only_orphans", "Nur verwaiste Artikel anzeigen", value=False),
                        ui.input_action_button("btn_admin_refresh", "Filter anwenden", class_="btn-lukb btn-lukb-ghost btn-lukb-sm"),
                        style="display:flex;gap:12px;align-items:flex-end;margin:0 0 10px 0;flex-wrap:wrap;",
                    ),
                    ui.output_ui("admin_articles_table_ui"),
                    ui.div(
                        ui.h6("Artikel zuordnen / Verantwortung übertragen", style="margin:0 0 8px 0;color:#002855;font-weight:600;"),
                        ui.div(
                            ui.input_text("admin_assign_article_id", "Artikel-ID", placeholder="Artikel-ID aus Tabelle wählen…"),
                            ui.input_text("admin_assign_user_id", "Ziel-Benutzerkennung", placeholder="z. B. autor.a@lukb.ch"),
                            ui.input_select(
                                "admin_assign_role",
                                "Aktion / Rolle",
                                choices={
                                    "transfer_owner": "Verantwortung übertragen (Owner)",
                                    **{r: _ADMIN_ROLE_LABELS.get(r, r) for r in VALID_ARTICLE_ROLES},
                                    "revoke": "Zugriff entziehen",
                                },
                            ),
                            style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;",
                        ),
                        ui.tags.script(
                            "setTimeout(function(){var el=document.getElementById('admin_assign_user_id');if(el)el.setAttribute('list','lukb-admin-users-datalist');},0);"
                        ),
                        ui.input_action_button("btn_admin_apply_article_perm", "Zuordnung ausführen", class_="btn-lukb btn-lukb-primary btn-lukb-sm"),
                        style="background:#F4F7FA;padding:10px;border-radius:6px;border:1px solid #D6DEE8;margin-bottom:12px;",
                    ),
                    ui.div(
                        ui.h6("Globale Benutzerrollen & Konten (Admin, Publizieren & Alias)", style="margin:0 0 8px 0;color:#002855;font-weight:600;"),
                        ui.div(
                            ui.input_text("admin_role_user_id", "Benutzerkennung", placeholder="z. B. editor@lukb.ch"),
                            ui.input_text("admin_role_display_name", "Alias / Name", placeholder="z. B. Max Muster"),
                            ui.input_checkbox("admin_role_is_admin", "Admin-Zugriff", value=False),
                            ui.input_checkbox("admin_role_can_publish", "Darf publizieren", value=False),
                            ui.input_action_button("btn_admin_save_user_role", "Rolle speichern", class_="btn-lukb btn-lukb-primary btn-lukb-sm"),
                            style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px;",
                        ),
                        ui.output_ui("admin_users_table_ui"),
                        style="background:#FFFFFF;padding:10px;border-radius:6px;border:1px solid #D6DEE8;",
                    ),
                    id="admin-tab-pane-articles",
                ),
                ui.div(
                    ui.output_ui("admin_publications_audit_ui"),
                    id="admin-tab-pane-audit",
                    style="display:none;",
                ),
                style="padding:16px 22px;overflow-y:auto;flex:1;",
            ),
            ui.div(
                ui.span("Tipp: Mit Escape oder Schliessen-Button beenden", class_="pub-modal-hint"),
                ui.tags.button(
                    "Schliessen",
                    id="btn-footer-close-admin-modal",
                    type="button",
                    class_="btn-lukb btn-lukb-ghost",
                    onclick="if(window.lukbCloseAdminModal){window.lukbCloseAdminModal();}",
                ),
                class_="pub-modal-footer",
            ),
            class_="pub-modal-dialog",
            style="max-width:1200px;max-height:90vh;",
        ),
        id="lukb-admin-modal-backdrop",
        class_="pub-modal-backdrop",
        style="display:none;",
    )
