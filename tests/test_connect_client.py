"""
tests/test_connect_client.py
============================
Tests für den Posit Connect API Client (services/connect_client.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Projektwurzel in den Suchpfad aufnehmen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.connect_client import (
    deploy_bundle_to_connect,
    get_portal_target_url,
    is_connect_configured,
)


def test_connect_client_not_configured() -> None:
    # Ohne Umgebungsvariablen liefert is_connect_configured False
    with patch.dict(os.environ, {"CONNECT_SERVER": "", "CONNECT_API_KEY": "", "CONNECT_PORTAL_GUID": ""}, clear=True):
        from config import CONNECT_API_KEY, CONNECT_PORTAL_GUID, CONNECT_SERVER_URL
        # get_portal_target_url liefert relativen Fallback
        url = get_portal_target_url()
        assert url == "portal/"

        # deploy_bundle_to_connect bricht graceful ab ohne Fehler
        dummy_file = Path(__file__)
        res = deploy_bundle_to_connect(dummy_file)
        assert res["success"] is True
        assert res["deployed"] is False


def test_connect_client_configured_url() -> None:
    with patch("services.connect_client.CONNECT_PORTAL_URL", "https://connect.lukb.ch/investment-views/"):
        assert get_portal_target_url() == "https://connect.lukb.ch/investment-views/"


if __name__ == "__main__":
    test_connect_client_not_configured()
    test_connect_client_configured_url()
    print("All connect client tests passed successfully!")
