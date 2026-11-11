from __future__ import annotations

from typing import Any
from shiny import ui

from services.renderer import list_available_templates


def editor_ui(templates_list: list[dict[str, Any]] | None = None) -> ui.Tag:
    """Rendert die mittlere Spalte mit Metadaten-Kopf, Block-Toolbar und Drag-and-Drop Canvas."""
    if templates_list is None:
        templates_list = list_available_templates()

    return ui.tags.main(
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
    )
