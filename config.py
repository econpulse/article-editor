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


def _resolve_portal_dist_dir() -> Path:
    # 1. Explizit per Env gesetzt?
    env_dir = os.getenv("STATIC_PORTAL_DIR")
    if env_dir:
        return Path(env_dir).resolve()

    # 2. Auf Posit Connect / Workbench oder Server (MSSQL konfiguriert)?
    # Hier läuft die App im Produktionsmodus ohne --reload / WatchFiles.
    if os.getenv("RSTUDIO_CONNECT") or os.getenv("CONNECT_SERVER") or os.getenv("MSSQL_HOST"):
        return (DATA_DIR / "static_portal_dist").resolve()

    # 3. Lokale Entwicklung / lokales Testing:
    # Liegt außerhalb des Watch-Trees (im OS Temp-Verzeichnis), damit WatchFiles (--reload)
    # beim Publizieren oder Zurückziehen von Artikeln KEINEN Server-Reload auslöst
    # und geöffnete Dialoge nicht unterbricht.
    import tempfile
    return (Path(tempfile.gettempdir()) / "lukb_static_portal_dist").resolve()


STATIC_PORTAL_DIR = _resolve_portal_dist_dir()


def _resolve_typst_cache_dir() -> Path:
    env_dir = os.getenv("TYPST_CACHE_DIR")
    if env_dir:
        return Path(env_dir).resolve()

    if os.getenv("RSTUDIO_CONNECT") or os.getenv("CONNECT_SERVER") or os.getenv("MSSQL_HOST") or os.getenv("MSSQL_SERVER"):
        return (DATA_DIR / "typst_cache").resolve()

    # Lokale Entwicklung: ausserhalb des Watch-Trees (OS Temp-Verzeichnis),
    # damit WatchFiles (--reload) beim Materialisieren von Assets/Charts keinen Server-Reload auslöst.
    import tempfile
    return (Path(tempfile.gettempdir()) / "lukb_typst_cache").resolve()


TYPST_CACHE_DIR = _resolve_typst_cache_dir()

# Stelle sicher, dass Arbeitsverzeichnisse existieren
DATA_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_PORTAL_DIR.mkdir(parents=True, exist_ok=True)
TYPST_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Initialisiere lokalen Temp-Portalordner mit bestehendem Portal-Stand (falls vorhanden und Temp-Ordner leer)
if STATIC_PORTAL_DIR != (DATA_DIR / "static_portal_dist").resolve() and (DATA_DIR / "static_portal_dist").exists():
    try:
        if not any(STATIC_PORTAL_DIR.iterdir()):
            import shutil
            shutil.copytree(DATA_DIR / "static_portal_dist", STATIC_PORTAL_DIR, dirs_exist_ok=True)
    except Exception:
        pass


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


def is_mssql_configured() -> bool:
    """
    Prüft, ob ein echter MS SQL Server konfiguriert ist (Posit Connect / Workbench Produktion).
    Liefert False bei lokaler Entwicklung/Testing mit SQLite-Fallback.
    """
    explicit = os.getenv("DATABASE_URL", "").lower()
    if explicit:
        return "mssql" in explicit
    return bool(os.getenv("MSSQL_SERVER", "").strip())


def is_connect_environment() -> bool:
    """
    Prüft, ob die Anwendung in Posit Connect oder Posit Workbench ausgeführt wird.
    """
    if os.getenv("RSTUDIO_PRODUCT", "").upper() == "CONNECT":
        return True
    if bool(os.getenv("CONNECT_SERVER", "").strip() or os.getenv("CONNECT_SERVER_URL", "").strip()):
        return True
    return is_mssql_configured()


def should_sync_portal_on_startup() -> bool:
    """
    Entscheidet, ob beim Anwendungsstart Snapshots automatisch in STATIC_PORTAL_DIR
    synchronisiert werden sollen:
    - Ja (True): Auf Posit Connect / Posit Workbench oder wenn MSSQL konfiguriert ist
          (ephemeres Container-Dateisystem muss initialisiert werden).
    - Nein (False): Bei lokaler Entwicklung / lokalem Testing (ohne MSSQL / SQLite-Fallback),
          sodass lokale Tests sofort starten und WatchFiles (--reload) nicht in eine
          Reload-Schleife gerät.
    - Kann über die Umgebungsvariable SYNC_PORTAL_ON_STARTUP ('true'/'false' / '1'/'0')
      bei Bedarf explizit überschrieben werden.
    """
    forced = os.getenv("SYNC_PORTAL_ON_STARTUP", "").strip().lower()
    if forced in ("1", "true", "yes"):
        return True
    if forced in ("0", "false", "no"):
        return False
    return is_connect_environment()


# ============================================================================
# Posit Connect API & Deployment Konfiguration
# ============================================================================
def _clean_env_val(val: str) -> str:
    val = (val or "").strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()
    return val


def _normalize_connect_url(url: str) -> str:
    url = _clean_env_val(url)
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = f"https://{url}"
    return url.rstrip("/")


CONNECT_SERVER_URL = _normalize_connect_url(os.getenv("CONNECT_SERVER", os.getenv("CONNECT_SERVER_URL", "")))
CONNECT_API_KEY = _clean_env_val(os.getenv("CONNECT_API_KEY", ""))
CONNECT_PORTAL_GUID = _clean_env_val(os.getenv("CONNECT_PORTAL_GUID", os.getenv("CONNECT_PORTAL_CONTENT_GUID", "")))
CONNECT_PORTAL_URL = _normalize_connect_url(os.getenv("CONNECT_PORTAL_URL", ""))
CONNECT_VERIFY_SSL = _clean_env_val(os.getenv("CONNECT_VERIFY_SSL", "true")).lower() not in ("false", "0", "no", "off")
CONNECT_CA_BUNDLE = _clean_env_val(os.getenv("CONNECT_CA_BUNDLE", os.getenv("REQUESTS_CA_BUNDLE", os.getenv("SSL_CERT_FILE", ""))))

# ============================================================================
# Benutzerrollen & Berechtigungssteuerung
# ============================================================================
PORTAL_PUBLISHERS = [
    u.strip().lower()
    for u in _clean_env_val(os.getenv("PORTAL_PUBLISHERS", "")).split(",")
    if u.strip()
]
PORTAL_ADMINS = [
    u.strip().lower()
    for u in _clean_env_val(os.getenv("PORTAL_ADMINS", "")).split(",")
    if u.strip()
]

_TECHNICAL_USER_PREFIXES = ("analyst (", "sess_", "anonymous", "guest")


def normalize_user_id(username: str | None) -> str:
    """Normalisiert eine Benutzerkennung für konsistente Vergleiche und DB-Lookups."""
    return (username or "").strip().lower()


def is_technical_session_user(username: str | None) -> bool:
    """
    Erkennt technische Sitzungsnamen oder leere Identitäten.
    Solche Namen erhalten auf Connect (und bei Rechtedurchsetzung) keinerlei Rechte.
    """
    u = normalize_user_id(username)
    if not u:
        return True
    return any(u.startswith(prefix) for prefix in _TECHNICAL_USER_PREFIXES)


def validate_startup_admin_config(*, raise_on_missing: bool = True) -> list[str]:
    """
    Stellt sicher, dass in der Produktiv-/Connect-Startkonfiguration mindestens ein
    ausdrücklich benanntes Admin-Konto (PORTAL_ADMINS) vorhanden ist.
    """
    admins = [u for u in PORTAL_ADMINS if not is_technical_session_user(u)]
    if not admins and is_connect_environment():
        msg = (
            "Sicherheitsfehler in Startkonfiguration: Auf Posit Connect / MSSQL muss "
            "mindestens ein ausdrücklich benanntes Admin-Konto in PORTAL_ADMINS gesetzt sein."
        )
        if raise_on_missing:
            raise RuntimeError(msg)
    return admins


def _lookup_db_global_rights(user_id: str) -> tuple[bool, bool] | None:
    """Liest explizite globale Rechte (is_admin, can_publish) aus io_user_roles, falls vorhanden."""
    if not user_id or is_technical_session_user(user_id):
        return None
    try:
        from database.repository import get_db_user_global_rights

        return get_db_user_global_rights(user_id)
    except Exception:
        return None


def get_global_rights(username: str | None) -> dict[str, bool]:
    """
    Ermittelt die globalen Rechte {'is_admin': bool, 'can_publish': bool} getrennt.
    Wer beide Funktionen benötigt, erhält beide Rechte ausdrücklich (Env oder DB).
    Technische Sitzungsnamen erhalten niemals Rechte.
    """
    u = normalize_user_id(username)
    if is_technical_session_user(u):
        return {"is_admin": False, "can_publish": False}

    env_admin = u in PORTAL_ADMINS
    env_pub = u in PORTAL_PUBLISHERS
    db_rights = _lookup_db_global_rights(u)

    if env_admin or env_pub or db_rights is not None:
        db_admin = bool(db_rights[0]) if db_rights is not None else False
        db_pub = bool(db_rights[1]) if db_rights is not None else False
        return {
            "is_admin": env_admin or db_admin,
            "can_publish": env_pub or db_pub,
        }

    # Wenn Env-Listen oder Connect-Umgebung aktiv sind, gibt es keinen impliziten Admin-Fallback
    if PORTAL_ADMINS or PORTAL_PUBLISHERS or is_connect_environment():
        return {"is_admin": False, "can_publish": False}

    # Lokale Entwicklung ohne konfigurierte Rollenlisten (und ohne Connect/MSSQL)
    return {"is_admin": True, "can_publish": True}


def get_user_role(username: str) -> str:
    """
    Ermittelt die primäre Anzeige-Rolle des Benutzers: 'admin', 'publisher', 'author' oder 'guest'.
    """
    if is_technical_session_user(username):
        return "guest"
    rights = get_global_rights(username)
    if rights["is_admin"]:
        return "admin"
    if rights["can_publish"]:
        return "publisher"
    return "author"


def is_global_admin(username: str | None) -> bool:
    """Prüft, ob der Benutzer globale Admin-Rechte besitzt."""
    return get_global_rights(username)["is_admin"]


def can_publish(username: str | None) -> bool:
    """Prüft, ob der Benutzer Publikationen freigeben oder vom Portal zurückziehen darf."""
    return get_global_rights(username)["can_publish"]


def can_delete(username: str | None) -> bool:
    """Prüft, ob der Benutzer Publikationen löschen / archivieren darf."""
    rights = get_global_rights(username)
    return rights["is_admin"] or rights["can_publish"]

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
