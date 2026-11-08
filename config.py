"""
Zentrale Konfiguration für das LUKB Investment Office CMS (Article-Editor).
Unterstützt primär MS SQL Server (MSSQL) auf Posit Connect über Umgebungsvariablen
sowie einen lokalen Entwicklungs-Fallback, falls keine MSSQL-Umgebung konfiguriert ist.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Lade .env Datei falls lokal vorhanden
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
WWW_DIR = BASE_DIR / "www"
FONTS_DIR = WWW_DIR / "fonts"
DATA_DIR = BASE_DIR / "data"
STATIC_PORTAL_DIR = Path(os.getenv("STATIC_PORTAL_DIR", str(DATA_DIR / "static_portal_dist"))).resolve()

# Stelle sicher, dass Arbeitsverzeichnisse existieren
DATA_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_PORTAL_DIR.mkdir(parents=True, exist_ok=True)


def build_database_url() -> tuple[str, str]:
    """
    Erzeugt die SQLAlchemy Connection-URL.
    Priorität:
      1. Explizite DATABASE_URL Umgebungsvariable
      2. MSSQL_* Umgebungsvariablen (Posit Connect Standard für MS SQL Server)
      3. Lokaler Entwicklungs-Fallback (nur wenn keine MSSQL-Konfiguration gesetzt ist)

    Returns:
        tuple[str, str]: (connection_url, backend_label)
    """
    explicit_url = os.getenv("DATABASE_URL", "").strip()
    if explicit_url:
        backend = "MSSQL (DATABASE_URL)" if "mssql" in explicit_url.lower() else "Custom DB"
        return explicit_url, backend

    mssql_server = os.getenv("MSSQL_SERVER", "").strip()
    if mssql_server:
        mssql_port = os.getenv("MSSQL_PORT", "1433").strip()
        mssql_db = os.getenv("MSSQL_DATABASE", "InvestmentOfficeCMS").strip()
        mssql_user = os.getenv("MSSQL_USER", "").strip()
        mssql_password = os.getenv("MSSQL_PASSWORD", "").strip()
        mssql_driver = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server").strip()
        trust_cert = os.getenv("MSSQL_TRUST_SERVER_CERTIFICATE", "yes").strip()
        mssql_encrypt = os.getenv("MSSQL_ENCRYPT", "").strip()
        trusted_conn = os.getenv("MSSQL_TRUSTED_CONNECTION", "no").strip().lower() in (
            "yes",
            "true",
            "1",
        )

        host_part = f"{mssql_server}:{mssql_port}" if mssql_port else mssql_server
        query_params = [
            f"driver={quote_plus(mssql_driver)}",
            f"TrustServerCertificate={quote_plus(trust_cert)}",
        ]

        if mssql_encrypt:
            query_params.append(f"Encrypt={quote_plus(mssql_encrypt)}")

        if trusted_conn or not mssql_user:
            query_params.append("Trusted_Connection=yes")
            auth_part = ""
        else:
            auth_part = f"{quote_plus(mssql_user)}:{quote_plus(mssql_password)}@"

        query_str = "&".join(query_params)
        url = f"mssql+pyodbc://{auth_part}{host_part}/{quote_plus(mssql_db)}?{query_str}"
        return url, f"MS SQL Server ({mssql_server}/{mssql_db})"

    # Lokaler Entwicklungs-Fallback (damit die App ohne VPN/MSSQL-Server sofort testbar ist)
    sqlite_rel = os.getenv("LOCAL_FALLBACK_SQLITE_PATH", "data/local_dev_cms.db")
    sqlite_path = (BASE_DIR / sqlite_rel).resolve()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{sqlite_path.as_posix()}", "SQLite (Dev-Fallback — MSSQL bereit)"


DATABASE_URL, DATABASE_BACKEND_LABEL = build_database_url()

# ============================================================================
# Posit Connect API & Deployment Konfiguration
# ============================================================================
CONNECT_SERVER_URL = os.getenv("CONNECT_SERVER", os.getenv("CONNECT_SERVER_URL", "")).rstrip("/")
CONNECT_API_KEY = os.getenv("CONNECT_API_KEY", "").strip()
CONNECT_PORTAL_GUID = os.getenv("CONNECT_PORTAL_GUID", os.getenv("CONNECT_PORTAL_CONTENT_GUID", "")).strip()
CONNECT_PORTAL_URL = os.getenv("CONNECT_PORTAL_URL", "").strip()

# ============================================================================
# LUKB Corporate Design & Typografie
# ============================================================================
LUKB_FONT_LIGHT = os.getenv("LUKB_FONT_LIGHT", "Yoga Sans for LUKB Light")
LUKB_FONT_MEDIUM = os.getenv("LUKB_FONT_MEDIUM", "Yoga Sans for LUKB Medium")
LUKB_FONT_FAMILY_BASE = os.getenv("LUKB_FONT_FAMILY_BASE", "Yoga Sans for LUKB")

LUKB_COLORS = {
    "primary_navy": "#002855",       # LUKB Dunkelblau (Primärfarbe)
    "secondary_blue": "#005A9C",     # LUKB Mittelblau
    "accent_cyan": "#009FE3",        # LUKB Akzent-Cyan
    "warm_gold": "#C59B27",          # Dezenter Akzentton für Highlights
    "text_dark": "#1A2433",          # Fließtext
    "text_muted": "#5A687C",         # Untertitel, Quellen, Fußnoten
    "surface_light": "#F4F7FA",      # Hintergrund für Callouts & Tabellen-Zebrastreifen
    "border_subtle": "#D6DEE8",      # Linien für Tabellen & Grafik-Container
}
