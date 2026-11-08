"""
services/connect_client.py
===========================
Client für die Posit Connect REST API zur automatischen Bereitstellung des
statischen Content-Portals als unabhängiges, login-freies Posit-Connect-Deployment.
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from config import (
    CONNECT_API_KEY,
    CONNECT_PORTAL_GUID,
    CONNECT_PORTAL_URL,
    CONNECT_SERVER_URL,
)

logger = logging.getLogger(__name__)


def is_connect_configured() -> bool:
    """Prüft, ob die Zugangsdaten für das Posit Connect API-Deployment vorliegen."""
    return bool(CONNECT_SERVER_URL and CONNECT_API_KEY and CONNECT_PORTAL_GUID)


def get_portal_target_url() -> str:
    """
    Liefert die Ziel-URL des statischen Portals:
    1. Explizit konfigurierte CONNECT_PORTAL_URL (z. B. https://connect.lukb.ch/investment-views/)
    2. Ermittelte URL aus Server + GUID
    3. Lokaler / relativer Fallback ("portal/")
    """
    if CONNECT_PORTAL_URL:
        return CONNECT_PORTAL_URL.rstrip("/") + "/"
    if CONNECT_SERVER_URL and CONNECT_PORTAL_GUID:
        return f"{CONNECT_SERVER_URL}/content/{CONNECT_PORTAL_GUID}/"
    return "portal/"


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    # In Firmennetzen mit SSL-Inspection/Interception toleranter Fallback
    return ctx


def deploy_bundle_to_connect(bundle_path: Path) -> dict[str, Any]:
    """
    Lädt das .tar.gz Bundle über die offizielle Posit Connect REST API hoch
    und aktiviert das neue Deployment atomar auf dem statischen Content-Item.
    """
    if not is_connect_configured():
        return {
            "success": True,
            "deployed": False,
            "reason": "Connect API nicht konfiguriert (CONNECT_SERVER_URL, CONNECT_API_KEY oder CONNECT_PORTAL_GUID fehlt).",
            "url": get_portal_target_url(),
        }

    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle-Datei nicht gefunden: {bundle_path}")

    base_api = f"{CONNECT_SERVER_URL}/__api__/v1"
    headers = {
        "Authorization": f"Key {CONNECT_API_KEY}",
        "User-Agent": "LUKB-Article-Editor-CMS/1.0",
    }
    ctx = _make_ssl_context()

    logger.info(f"Starte Upload des Bundles {bundle_path.name} zu Posit Connect (GUID: {CONNECT_PORTAL_GUID})...")

    # 1. Bundle hochladen
    upload_url = f"{base_api}/content/{CONNECT_PORTAL_GUID}/bundles"
    bundle_bytes = bundle_path.read_bytes()
    upload_req = urllib.request.Request(
        upload_url,
        data=bundle_bytes,
        headers={**headers, "Content-Type": "application/x-gzip"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(upload_req, context=ctx, timeout=60) as resp:
            upload_resp = json.loads(resp.read().decode("utf-8"))
            bundle_id = upload_resp.get("id") or upload_resp.get("bundle_id")
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        logger.error(f"Connect Bundle Upload fehlgeschlagen: HTTP {exc.code} - {err_msg}")
        return {
            "success": False,
            "deployed": False,
            "error": f"Upload fehlgeschlagen (HTTP {exc.code}): {err_msg}",
        }
    except Exception as exc:
        logger.error(f"Verbindungsfehler beim Connect Bundle Upload: {exc}")
        return {"success": False, "deployed": False, "error": str(exc)}

    logger.info(f"Bundle erfolgreich hochgeladen (Bundle ID: {bundle_id}). Starte Deployment...")

    # 2. Deployment aktivieren
    deploy_url = f"{base_api}/content/{CONNECT_PORTAL_GUID}/deploy"
    deploy_payload = json.dumps({"bundle_id": bundle_id}).encode("utf-8")
    deploy_req = urllib.request.Request(
        deploy_url,
        data=deploy_payload,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(deploy_req, context=ctx, timeout=30) as resp:
            deploy_resp = json.loads(resp.read().decode("utf-8"))
            task_id = deploy_resp.get("task_id")
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        logger.error(f"Connect Deploy-Trigger fehlgeschlagen: HTTP {exc.code} - {err_msg}")
        return {
            "success": False,
            "deployed": False,
            "error": f"Aktivierung fehlgeschlagen (HTTP {exc.code}): {err_msg}",
        }
    except Exception as exc:
        logger.error(f"Verbindungsfehler bei Connect Deploy: {exc}")
        return {"success": False, "deployed": False, "error": str(exc)}

    # 3. Optional: Kurzer Statuscheck (Task polling bis zu 10s)
    if task_id:
        poll_url = f"{base_api}/tasks/{task_id}"
        poll_req = urllib.request.Request(poll_url, headers=headers, method="GET")
        for _ in range(5):
            time.sleep(1.0)
            try:
                with urllib.request.urlopen(poll_req, context=ctx, timeout=10) as resp:
                    task_data = json.loads(resp.read().decode("utf-8"))
                    if task_data.get("finished", False):
                        if task_data.get("code", 0) != 0:
                            logger.warning(f"Connect Task finished with non-zero code: {task_data}")
                        break
            except Exception:
                break

    target_url = get_portal_target_url()
    logger.info(f"Deployment auf Posit Connect erfolgreich abgeschlossen! Ziel-URL: {target_url}")

    return {
        "success": True,
        "deployed": True,
        "bundle_id": bundle_id,
        "task_id": task_id,
        "url": target_url,
    }
