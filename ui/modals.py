from __future__ import annotations

from shiny import ui


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
    )
