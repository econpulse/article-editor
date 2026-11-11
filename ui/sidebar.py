from __future__ import annotations

from shiny import ui


def sidebar_ui() -> ui.Tag:
    """Rendert die linke einklappbare Publikations-Sidebar (Filter, Suche, Liste, Aktionen)."""
    return ui.tags.aside(
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
    )
