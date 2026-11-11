"""
LUKB Investment Office — UI Package.
Modularer Aufbau der Benutzeroberfläche: Header, Sidebar, Editor, Preview und Modals.
"""

from __future__ import annotations

from shiny import ui

from config import WWW_DIR
from services.renderer import list_available_templates
from ui.editor import editor_ui
from ui.header import header_ui
from ui.modals import search_modal_ui
from ui.preview import preview_ui
from ui.sidebar import sidebar_ui


def get_asset_version() -> str:
    """Ermittelt den mtime-basierten Cache-Busting-Hash für editor.js und editor.css."""
    try:
        js_m = int((WWW_DIR / "js" / "editor.js").stat().st_mtime)
        css_m = int((WWW_DIR / "css" / "editor.css").stat().st_mtime)
        return f"{max(js_m, css_m)}"
    except Exception:
        return "2"


def build_app_ui() -> ui.Tag:
    """Assembliert das 3-Spalten-Layout im LUKB Corporate Design."""
    asset_ver = get_asset_version()
    templates = list_available_templates()

    return ui.page_fluid(
        ui.head_content(
            ui.tags.meta(charset="utf-8"),
            ui.tags.meta(name="viewport", content="width=device-width, initial-scale=1"),
            ui.tags.title("LUKB Investment Office — Publikations-Editor & CMS"),
            ui.tags.link(rel="stylesheet", href=f"css/editor.css?v={asset_ver}"),
            ui.tags.script(src="js/vendor/Sortable.min.js"),
            ui.tags.script(src=f"js/editor.js?v={asset_ver}"),
        ),
        header_ui(),
        ui.div(
            sidebar_ui(),
            editor_ui(templates),
            preview_ui(),
            id="lukb-workspace",
            class_="cms-workspace",
        ),
        search_modal_ui(),
    )


app_ui = build_app_ui()

__all__ = [
    "app_ui",
    "build_app_ui",
    "get_asset_version",
    "header_ui",
    "sidebar_ui",
    "editor_ui",
    "preview_ui",
    "search_modal_ui",
]
