"""
LUKB Investment Office — Content-Management-System & Publikations-Editor
Einstiegspunkt für Shiny for Python & Posit Connect Deployment.
"""

from __future__ import annotations

from datetime import datetime
import logging
from shiny import App, Inputs, Outputs, Session

from config import WWW_DIR, should_sync_portal_on_startup
from database.repository import init_db_and_seed
from server import (
    ACTIVE_PEERS,
    PEER_COLORS,
    SessionState,
    broadcast_article_sync,
    broadcast_presence,
    broadcast_preview_to_coauthors,
    cleanup_peer,
    collect_article_assets_map,
    get_article_peers,
    get_peer_color,
    get_peer_user,
    is_peer_auto_preview,
    register_all_handlers,
    register_download_handlers,
    register_peer,
    set_peer_article,
    set_peer_auto_preview,
    set_peer_focus,
    slugify_filename,
)
from ui import app_ui, get_asset_version

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lukb_cms")

# Datenbank-Tabellen & initiale Beispiel-Publikationen beim Start sicherstellen
init_db_and_seed()

# Statisches Content-Portal beim Start:
# Auf Posit Connect / Workbench (MSSQL) werden alle veröffentlichten Snapshots
# beim Hochfahren des Containers automatisch in das ephemere Dateisystem materialisiert.
# Bei lokaler Entwicklung / lokalem Testing (ohne MSSQL) existiert die MSSQL-Datenbank nicht;
# hier wird der Snapshot-Sync beim Start übersprungen, sodass WatchFiles (--reload) nicht in
# eine Reload-Schleife gerät und lokale Tests sofort und reibungslos starten.
if should_sync_portal_on_startup():
    try:
        from config import STATIC_PORTAL_DIR
        from services.portal_publisher import restore_portal_from_snapshots

        logger.info("Synchronisiere aktiven Portal-Stand aus MSSQL-Snapshots...")
        _restore_res = restore_portal_from_snapshots(STATIC_PORTAL_DIR)
        logger.info(f"Portal-Wiederherstellung abgeschlossen: {_restore_res.get('restored_count', 0)} Artikel online.")
    except Exception as exc:
        logger.warning(f"Automatische Portal-Wiederherstellung beim Start übersprungen: {exc}")
else:
    logger.info("Lokale Entwicklungsumgebung aktiv (SQLite-Fallback) — MSSQL-Snapshot-Sync beim Start übersprungen.")

# Cache-Busting Version für statische Assets
_ASSET_VER = get_asset_version()

# Abwärtskompatible Aliase für etwaige externe Zugriffe
_slugify_filename = slugify_filename
_collect_article_assets_map = collect_article_assets_map
_ACTIVE_PEERS = ACTIVE_PEERS
_PEER_COLORS = PEER_COLORS
_get_article_peers = get_article_peers
_broadcast_presence = broadcast_presence
_broadcast_article_sync = broadcast_article_sync


def server(input: Inputs, output: Outputs, session: Session) -> None:
    """
    Zentrale Server-Logik für Shiny for Python.
    Die Event- und Workflow-Handler sind thematisch modularisiert:
    - input.lukb_auto_preview_toggle und toggle-auto-preview -> server.preview_handlers
    - input.lukb_autosave_payload, input.lukb_upload_asset -> server.editor_handlers
    - input.lukb_select_article, input.btn_new_article -> server.article_handlers
    - input.lukb_publish_portal, input.lukb_submit_review -> server.workflow_handlers
    - download_pdf, download_docx, download_html, download_portal_bundle -> server.downloads
    """
    register_all_handlers(input, output, session)


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
