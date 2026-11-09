"""
scripts/deploy_portal.py
========================
Kommandozeilen-Skript zum initialen oder manuellen Deployment des statischen
LUKB Content-Portals auf Posit Connect direkt aus dem Positron Workspace.

Verwendung im Positron Terminal:
    python scripts/deploy_portal.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Projektwurzel in den Suchpfad aufnehmen
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Windows Terminal UTF-8 Encoding sicherstellen
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import (
    CONNECT_API_KEY,
    CONNECT_PORTAL_GUID,
    CONNECT_PORTAL_URL,
    CONNECT_SERVER_URL,
    STATIC_PORTAL_DIR,
)
from database.repository import get_article, list_articles
from services.connect_client import create_content_item, deploy_bundle_to_connect
from services.portal_publisher import create_connect_bundle, publish_article


def main() -> None:
    print("=" * 70)
    print("LUKB Investment Office — Statisches Portal Deployment für Posit Connect")
    print("=" * 70)

    # 1. Sicherstellen, dass das Portal generiert ist
    index_html = STATIC_PORTAL_DIR / "index.html"
    if not index_html.exists():
        print(f"⚠️  Kein lokaler Portal-Build unter {STATIC_PORTAL_DIR} gefunden.")
        print("    Generiere Portal aus bestehenden Artikeln in der Datenbank...")
        articles = list_articles()
        published_count = 0
        for art in articles:
            doc = get_article(art["id"])
            if doc:
                publish_article(doc)
                published_count += 1
        print(f"    ✅ {published_count} Artikel ins Portal generiert.")

    # 2. Bundle (.tar.gz) packen
    print("\n📦 Erzeuge Posit Connect Deployment-Bundle (.tar.gz)...")
    bundle_path = create_connect_bundle()
    bundle_kb = round(bundle_path.stat().st_size / 1024, 1)
    print(f"    ✅ Bundle erstellt: {bundle_path.name} ({bundle_kb} KB)")

    # 3. Posit Connect Konfiguration prüfen
    server = CONNECT_SERVER_URL or os.getenv("CONNECT_SERVER", "").rstrip("/")
    api_key = CONNECT_API_KEY or os.getenv("CONNECT_API_KEY", "").strip()
    guid = CONNECT_PORTAL_GUID or os.getenv("CONNECT_PORTAL_GUID", "").strip()

    print("\n🔍 Posit Connect Konfiguration:")
    print(f"    Server:    {server or '(nicht konfiguriert)'}")
    print(f"    API-Key:   {'*' * 8 + api_key[-4:] if len(api_key) > 4 else '(nicht konfiguriert)'}")
    print(f"    Item-GUID: {guid or '(noch nicht angelegt — wird bei Bedarf erstellt)'}")

    if not server or not api_key:
        print("\n⚠️  HINWEIS: Keine vollständigen Connect-Zugangsdaten konfiguriert.")
        print("    Sie haben zwei einfache Möglichkeiten:")
        print(f"    1. Manuell: Laden Sie '{bundle_path}' direkt im Posit Connect Web-UI hoch:")
        print("       -> 'Publish' -> 'Upload a Bundle'")
        print("    2. Automatisch: Tragen Sie CONNECT_SERVER und CONNECT_API_KEY in Ihre .env ein")
        print("       und führen Sie dieses Skript erneut aus.")
        return

    # 4. Falls noch keine GUID existiert: Neues statisches Content-Item auf Connect anlegen
    if not guid:
        print("\n🚀 Erstelle neues statisches Content-Item auf Posit Connect...")
        try:
            content_info = create_content_item(
                name="lukb-investment-portal",
                title="LUKB Investment Office Portal",
                access_type="all",  # Jeder kann ohne Login zugreifen
            )
            guid = content_info.get("guid")
            dashboard_url = content_info.get("dashboard_url", "")
            print(f"    ✅ Content-Item erfolgreich angelegt! GUID: {guid}")
            print(f"    Dashboard: {dashboard_url}")
            print("\n    👉 WICHTIG: Tragen Sie diese GUID in Ihre .env Datei ein:")
            print(f"       CONNECT_PORTAL_GUID={guid}")
            if dashboard_url:
                print("       (Dort können Sie auch eine Vanity-URL wie /investment-views vergeben)")
        except Exception as exc:
            print(f"    ❌ Fehler beim Erstellen des Content-Items: {exc}")
            return

    # 5. Bundle deployen
    print(f"\n🚀 Deploye Bundle auf Posit Connect (GUID: {guid})...")
    # Temporär GUID setzen falls eben erzeugt
    import services.connect_client as cc

    cc.CONNECT_PORTAL_GUID = guid
    res = deploy_bundle_to_connect(bundle_path)

    if res.get("success") and res.get("deployed"):
        print("    ✅ Deployment erfolgreich abgeschlossen!")
        print(f"    🔗 Ziel-URL: {res.get('url')}")
        print("\nDas statische Portal ist nun auf Posit Connect öffentlich verfügbar.")
    else:
        print(f"    ❌ Deployment fehlgeschlagen: {res.get('error') or res.get('reason')}")


if __name__ == "__main__":
    main()
