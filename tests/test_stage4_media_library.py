"""
Tests für Etappe 4 (Mediathek: Versionierung, Datenschutz bei Suche, Kanalprüfung & Widerruf).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

import config
from database.repository import (
    create_new_article,
    delete_article,
    get_asset,
    get_assets_by_ids,
    init_db_and_seed,
    save_article,
    save_asset,
)
from services.media_library import (
    add_media_version,
    approve_media_release,
    can_delete_media_version,
    create_media_entry,
    get_media_usages,
    request_media_release,
    revoke_media_release,
    search_media_library,
    validate_article_media_for_channel,
)


def test_media_library_privacy_versioning_channel_and_revoke(monkeypatch) -> None:
    init_db_and_seed()
    user_a = f"autor.a.{uuid.uuid4().hex[:6]}@lukb.ch"
    user_b = f"autor.b.{uuid.uuid4().hex[:6]}@lukb.ch"
    publisher = f"pub.{uuid.uuid4().hex[:6]}@lukb.ch"
    monkeypatch.setattr(config, "PORTAL_PUBLISHERS", [publisher])

    art_a = create_new_article(user=user_a)
    art_b = create_new_article(user=user_b)
    try:
        # 1. A legt eine Grafik in seinem Artikel an -> zunächst privat
        svg_v1 = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><rect width="100" height="40" fill="#002855"/></svg>'
        created = create_media_entry(
            title=f"LUKB Zinskurve {uuid.uuid4().hex[:4]}",
            media_type="chart",
            tags=["Zinsen", "SNB"],
            source_text="Bloomberg",
            data_as_of="2026-11-21",
            origin_article_id=art_a.id,
            filename="zinskurve_v1.svg",
            mime_type="image/svg+xml",
            data=svg_v1,
            user_id=user_a,
        )
        assert created["success"] is True
        media_id = created["media_id"]
        asset_v1 = created["asset_id"]

        # Private Grafik erscheint für A, aber NICHT für B
        res_a_priv = search_media_library(user_a, query="Zinskurve")
        assert any(it["media_id"] == media_id for it in res_a_priv["items"])
        res_b_priv = search_media_library(user_b, query="Zinskurve")
        assert not any(it["media_id"] == media_id for it in res_b_priv["items"])

        # 2. A stösst Freigabe an, Publisher gibt für 'internal' frei
        assert request_media_release(media_id, user_a)["success"] is True
        assert approve_media_release(media_id, usage_channel="internal", user_id=publisher)["success"] is True

        # B findet die Grafik jetzt in der Suche, aber sieht NICHT den privaten Quellartikel art_a.id!
        res_b_pub = search_media_library(user_b, query="Zinskurve")
        found_for_b = [it for it in res_b_pub["items"] if it["media_id"] == media_id]
        assert len(found_for_b) == 1
        assert found_for_b[0]["origin_article_id"] is None
        assert found_for_b[0]["latest_asset_id"] == asset_v1

        # 3. B fügt v1 in art_b ein und speichert -> Verwendung wird getrackt
        base_b = art_b.model_copy(deep=True)
        art_b.blocks.append(
            {
                "id": "blk_fig_b",
                "type": "figure",
                "title": "Zinskurve",
                "asset_id": asset_v1,
                "layout": "column",
            }
        )
        save_article(art_b, user=user_b, base_doc=base_b)
        assert can_delete_media_version(asset_v1) is False
        assert any(u["article_id"] == art_b.id and u["asset_id"] == asset_v1 for u in get_media_usages(media_id))

        # 4. A lädt Version 2 hoch -> bestehende Referenz in art_b bleibt auf asset_v1!
        svg_v2 = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><rect width="100" height="40" fill="#009FE3"/></svg>'
        ver2 = add_media_version(
            media_id,
            filename="zinskurve_v2.svg",
            mime_type="image/svg+xml",
            data=svg_v2,
            user_id=user_a,
            change_note="Aktualisierte Daten",
        )
        assert ver2["success"] is True
        assert ver2["version"] == 2
        assert ver2["asset_id"] != asset_v1
        assert art_b.blocks[-1]["asset_id"] == asset_v1

        # 5. Nutzungskanalprüfung vor externer Publikation: 'internal' wird für 'external' blockiert!
        chk_ext_fail = validate_article_media_for_channel(art_b, target_channel="external")
        assert chk_ext_fail["valid"] is False
        assert len(chk_ext_fail["errors"]) == 1

        # Nach Freigabe für 'external' ist es zulässig
        assert approve_media_release(media_id, usage_channel="external", user_id=publisher)["success"] is True
        chk_ext_ok = validate_article_media_for_channel(art_b, target_channel="external")
        assert chk_ext_ok["valid"] is True

        # 6. Widerruf zeigt bestehende Verwendungen an und blockiert Publikation
        rev_res = revoke_media_release(media_id, user_id=publisher)
        assert rev_res["success"] is True
        assert any(u["article_id"] == art_b.id for u in rev_res["usages"])
        assert validate_article_media_for_channel(art_b, target_channel="internal")["valid"] is False
    finally:
        delete_article(art_a.id, force=True)
        delete_article(art_b.id, force=True)


def test_private_asset_binding_blocks_cross_article_overwrite_and_read() -> None:
    init_db_and_seed()
    user_a = f"autor.a.{uuid.uuid4().hex[:6]}@lukb.ch"
    user_b = f"autor.b.{uuid.uuid4().hex[:6]}@lukb.ch"
    art_a = create_new_article(user=user_a)
    art_b = create_new_article(user=user_b)
    try:
        orig_svg = b'<svg xmlns="http://www.w3.org/2000/svg"><text>Private A</text></svg>'
        asset_a = save_asset(
            filename="private_a.svg",
            mime_type="image/svg+xml",
            data=orig_svg,
            article_id=art_a.id,
        )

        # User B darf Asset von Artikel A nicht über Artikel B überschreiben
        with pytest.raises(PermissionError):
            save_asset(
                filename="hijacked.svg",
                mime_type="image/svg+xml",
                data=b"<svg/>",
                article_id=art_b.id,
                asset_id=asset_a,
            )

        # Ursprungs-Asset bleibt unverändert an Artikel A gebunden
        own_loaded = get_asset(asset_a, article_id=art_a.id, user_id=user_a)
        assert own_loaded is not None
        assert own_loaded["data"] == orig_svg
        assert own_loaded["article_id"] == art_a.id

        # User B / Artikel B darf das private Asset weder einzeln noch per Batch lesen
        assert get_asset(asset_a, article_id=art_b.id, user_id=user_b) is None
        assert get_asset(asset_a, user_id=user_b) is None
        assert get_assets_by_ids([asset_a], article_id=art_b.id) == {}
    finally:
        delete_article(art_a.id, force=True)
        delete_article(art_b.id, force=True)
