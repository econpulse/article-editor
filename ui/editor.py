from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from shiny import ui

from services.renderer import list_available_templates


@dataclass(frozen=True)
class BlockButtonDef:
    """Deklarative Konfiguration für einen Inhaltsblock-Button in der Toolbar."""
    type_id: str
    label: str
    title: str = ""
    style: str = ""
    custom_class: str = ""


TOOLBAR_BLOCKS: list[BlockButtonDef] = [
    BlockButtonDef("heading", "+ Überschrift"),
    BlockButtonDef("richtext", "+ Text-Absatz"),
    BlockButtonDef("figure", "+ Grafik (Upload)"),
    BlockButtonDef(
        "db_chart",
        "+ DB-Chart (Zeitreihe)",
        title="Zeitreihen-Diagramm direkt aus der MSSQL-Tabelle ts_db erstellen (max. 5 Ticker)",
        style="border-color:#009FE3;background:#F0F9FF;color:#002855;",
    ),
    BlockButtonDef("table", "+ Tabelle (inkl. Excel-Paste)"),
    BlockButtonDef("callout", "+ Kernaussagen-Box"),
    BlockButtonDef(
        "textbox_pair",
        "+ Farbliche Box (Start & Ende)",
        title="Fügt eine Start- und End-Marke für eine farbliche Textbox ein (beliebige Blöcke dazwischen ziehbar)",
        style="border-color:#002855;background:#EBF3FA;color:#002855;",
    ),
    BlockButtonDef(
        "spacer",
        "+ Abstand",
        title="Fügt einen einstellbaren vertikalen Abstandhalter (Spacer in mm) ein",
    ),
    BlockButtonDef(
        "colbreak",
        "+ Spaltenumbruch",
        title="Erzwingt an dieser Position den Umbruch in die nächste Spalte (colbreak)",
        style="border-color:#C59B27;background:#FFFBEB;color:#78350F;",
    ),
    BlockButtonDef(
        "quote",
        "+ Zitat",
        title="Fügt ein typografisches Zitat / Pull-Quote mit Autoren- und Quellenzeile ein",
        style="border-color:#009FE3;background:#F0F9FF;color:#002855;",
    ),
    BlockButtonDef(
        "divider",
        "+ Trennlinie",
        title="Fügt eine horizontale Trennlinie (durchgezogen, gestrichelt, gepunktet) ein",
    ),
    BlockButtonDef(
        "footnotes",
        "+ Fussnoten",
        title="Fügt einen strukturierten Fussnoten- / Quellenapparat ein",
    ),
    BlockButtonDef(
        "glossary",
        "+ Glossar",
        title="Fügt ein Glossar-Verzeichnis am Textende ein (sammelt automatisch alle im Artikel markierten Begriffe)",
        style="border-color:#009FE3;background:#EBF5FB;color:#002855;",
    ),
    BlockButtonDef(
        "publications",
        "+ Weitere Publikationen",
        title="Fügt eine Box 'Weitere Publikationen' ein (automatisch mit den letzten 5 Publikationen vorbefüllt)",
        style="border-color:#005A9C;background:#F0F5FA;color:#002855;",
    ),
]


def document_metadata_card_ui(templates_list: list[dict[str, Any]]) -> ui.Tag:
    """Rendert die Metadaten-Karte (Template, Reihe, Status, Datum, Titel, Lead, Autoren, Tags)."""
    return ui.div(
        ui.div(
            ui.h3("Dokumenten-Kopf, Template & Autoren", class_="editor-card-title"),
            ui.span(
                "Schriften: Yoga Sans for LUKB Light / Medium",
                style="font-size:11.5px;color:#5A687C;",
            ),
            class_="editor-card-header",
        ),
        # Zeile 1: Template & Kopfzeile oben rechts
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
                ui.tags.label("Kopfzeile oben rechts", class_="field-label", **{"for": "meta-header-series"}),
                ui.tags.select(
                    ui.tags.option("Investment Office News", value="Investment Office News", selected="selected"),
                    ui.tags.option("Finanzanalyse", value="Finanzanalyse"),
                    id="meta-header-series",
                    class_="cms-select",
                ),
            ),
            class_="meta-grid-2",
        ),
        # Zeile 2: Status & Publikationsdatum
        ui.div(
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
            class_="meta-grid-2",
        ),
        # Zeile 3: Rubrik & Untertitel / Dachzeile
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
        # Zeile 4: Gesamttitel
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
        # Zeile 5: Lead-Text
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
        # Zeile 6: Autoren-Verwaltung
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
        # Zeile 7: Themen-Tags / Schlagwörter
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
        # Zeile 8: Aufklappbarer Disclaimer
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
    )


def block_toolbar_ui() -> ui.Tag:
    """Rendert die Sticky-Toolbar für das Einfügen neuer Inhaltsblöcke deklarativ."""
    buttons = []
    for btn in TOOLBAR_BLOCKS:
        attrs: dict[str, Any] = {"data-add-block-type": btn.type_id}
        if btn.title:
            attrs["title"] = btn.title
        if btn.style:
            attrs["style"] = btn.style

        cls = "btn-lukb btn-lukb-ghost btn-lukb-sm"
        if btn.custom_class:
            cls = f"{cls} {btn.custom_class}"

        buttons.append(
            ui.tags.button(
                btn.label,
                type="button",
                class_=cls,
                **attrs,
            )
        )

    return ui.div(
        ui.div(
            ui.span(
                "Inhaltsblöcke (per Drag & Drop ⋮⋮ sortierbar):",
                class_="font-medium",
                style="color:#002855;font-size:13.5px;",
            ),
            ui.tags.button(
                ui.span("↩", class_="undo-icon", style="font-size:14px;margin-right:4px;"),
                "Rückgängig",
                id="btn-undo-action",
                type="button",
                class_="btn-lukb btn-lukb-ghost btn-lukb-sm btn-undo-action btn-undo-disabled",
                title="Gelöschten Block rückgängig machen (Ctrl+Z)",
                disabled=True,
                onclick="if(window.lukbPerformUndo){window.lukbPerformUndo();}",
            ),
            class_="blocks-toolbar-left",
            style="display:flex;align-items:center;gap:10px;",
        ),
        ui.div(*buttons, class_="add-block-bar"),
        class_="blocks-toolbar-sticky",
    )


def blocks_canvas_ui() -> ui.Tag:
    """Rendert den Container für das SortableJS Block-Canvas."""
    return ui.div(id="lukb-blocks-canvas", class_="blocks-canvas")


def editor_ui(templates_list: list[dict[str, Any]] | None = None) -> ui.Tag:
    """Rendert die mittlere Spalte mit Metadaten-Kopf, Block-Toolbar und Drag-and-Drop Canvas."""
    if templates_list is None:
        templates_list = list_available_templates()

    return ui.tags.main(
        document_metadata_card_ui(templates_list),
        block_toolbar_ui(),
        blocks_canvas_ui(),
        class_="cms-editor-pane",
    )
