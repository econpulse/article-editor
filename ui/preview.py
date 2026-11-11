from __future__ import annotations

from shiny import ui


def preview_ui() -> ui.Tag:
    """Rendert die rechte Spalte mit Typst- und Web-Vorschau inklusive Toolbar."""
    return ui.tags.section(
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
                    style="font-size:11.5px;color:#5A687C;",
                ),
                ui.tags.label(
                    ui.tags.input(
                        id="toggle-auto-preview",
                        type="checkbox",
                        checked=True,
                        class_="auto-preview-checkbox",
                    ),
                    ui.span(class_="auto-preview-slider"),
                    ui.span("Auto-Typst", class_="auto-preview-label"),
                    class_="auto-preview-toggle",
                    title="Kontinuierliche Aktualisierung der Typst-Vorschau beim Bearbeiten ein- oder ausschalten",
                ),
                ui.input_action_button(
                    "btn_refresh_preview",
                    "↻ Aktualisieren",
                    class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                    title="Typst- & Web-Vorschau sofort manuell aktualisieren",
                ),
                class_="preview-toolbar-right",
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
    )
