"""
Tests für Etappe 3 (Vorschau-Begrenzung, Auto-Pause, Viewport-PDF.js & Chart-Datenrevision).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database.connection import get_db_session
from database.models import TimeSeriesModel
from database.repository import init_db_and_seed
from schemas.article import ArticleDocument, ArticleMetadata
from server.collab import ACTIVE_PEERS, set_peer_auto_preview
from server.state import SessionState
from services.chart_generator import (
    clear_db_chart_cache,
    generate_db_chart_svg,
    invalidate_db_chart_cache,
    publication_timeseries_snapshot,
)


class _DummyInputs:
    def __getattr__(self, name):
        return lambda: ""


class _DummySession:
    def __init__(self, sid: str, user: str):
        self.id = sid
        self.user = user
        self.messages: list[tuple[str, dict]] = []

    def on_ended(self, cb) -> None:
        pass

    async def send_custom_message(self, name: str, payload: dict) -> None:
        self.messages.append((name, payload))


def test_auto_preview_paused_skips_typst_and_enqueue_coalesces(monkeypatch) -> None:
    sid = f"sess_s3_{uuid.uuid4().hex[:6]}"
    sess = _DummySession(sid, "autor.s3@lukb.ch")
    st = SessionState(sess, _DummyInputs())
    try:
        doc = ArticleDocument(
            id=f"art_s3_{uuid.uuid4().hex[:6]}",
            metadata=ArticleMetadata(title="Preview Test"),
            blocks=[],
        )
        st._active_article_id_plain = doc.id
        st.current_article_id.set(doc.id)
        st.current_doc.set(doc)
        set_peer_auto_preview(sid, False)

        called = []
        monkeypatch.setattr("server.state.render_preview_pdf_base64", lambda d: (called.append(d.id), "JVBERi0=")[1])

        # 1. Bei pausierter Vorschau startet kein Typst-Auftrag
        asyncio.run(st.send_active_preview(doc, respect_auto_preview=True, client_edit_seq=1))
        assert called == []
        assert any(name == "lukb_update_preview" and payload.get("typst_skipped") is True for name, payload in sess.messages)

        # 2. Enqueue mit Coalescing (nur jüngster wartender Auftrag bleibt)
        async def _test_coalesce():
            st._preview_running = True  # Simuliere laufenden Auftrag
            st.enqueue_preview(doc, preview_mode="pdf", client_edit_seq=2)
            st.enqueue_preview(doc, preview_mode="pdf", client_edit_seq=3)
            st.enqueue_preview(doc, preview_mode="pdf", client_edit_seq=4)
            assert st._preview_pending_job is not None
            assert st._preview_pending_job["client_edit_seq"] == 4
            st._preview_running = False
            await st._run_preview_worker()

        asyncio.run(_test_coalesce())
        assert len(called) == 1
        assert any(
            name == "lukb_update_preview" and payload.get("client_edit_seq") == 4 and payload.get("article_id") == doc.id
            for name, payload in sess.messages
        )
    finally:
        ACTIVE_PEERS.pop(sid, None)


def test_chart_cache_invalidation_and_final_render_fresh_timeseries() -> None:
    init_db_and_seed()
    clear_db_chart_cache()
    ticker = f"TST_{uuid.uuid4().hex[:6].upper()}"
    with get_db_session() as session:
        session.add(TimeSeriesModel(ticker=ticker, date=date(2025, 1, 31), name="Test Series", value=100.0))
        session.add(TimeSeriesModel(ticker=ticker, date=date(2025, 6, 30), name="Test Series", value=120.0))

    blk = {
        "id": "blk_c1",
        "type": "db_chart",
        "start_date": "2025-01-01",
        "rebasing": "none",
        "series": [{"ticker": ticker, "chart_types": ["line"], "label": "T"}],
    }
    svg1 = generate_db_chart_svg(blk, embed_fonts=True)
    assert "<svg" in svg1

    # Zeitreihenwert korrigieren
    with get_db_session() as session:
        row = session.get(TimeSeriesModel, (ticker, date(2025, 6, 30)))
        assert row is not None
        row.value = 185.0

    # Finalrender mit publication_timeseries_snapshot liest frisch aus ts_db (trotz Preview-Cache!)
    with publication_timeseries_snapshot():
        svg_final_1 = generate_db_chart_svg(blk, embed_fonts=False)
        svg_final_2 = generate_db_chart_svg(blk, embed_fonts=True)
    assert svg_final_1 != svg1
    assert "<svg" in svg_final_2

    # Nach Cache-Invalidierung sieht auch der Preview-Cache den neuen Stand
    invalidate_db_chart_cache()
    svg_after_inv = generate_db_chart_svg(blk, embed_fonts=True)
    assert svg_after_inv != svg1


def test_pdfjs_visible_page_prioritization_in_node() -> None:
    preview_sync_js = ROOT / "www" / "js" / "modules" / "preview-sync.js"
    js = f"""
const assert = require('assert');
const fs = require('fs');
global.window = global;
global.document = {{ addEventListener: () => {{}} }};
eval(fs.readFileSync({json.dumps(str(preview_sync_js))}, 'utf8'));

const E = window.LUKBEditor;
const container = {{ getBoundingClientRect: () => ({{ top: 100, bottom: 700 }}) }};
const pageWraps = [
  {{ getBoundingClientRect: () => ({{ top: -900, bottom: -300 }}) }}, // Seite 1 (weit oben)
  {{ getBoundingClientRect: () => ({{ top: 150, bottom: 650 }}) }},  // Seite 2 (sichtbar)
  {{ getBoundingClientRect: () => ({{ top: 750, bottom: 1250 }}) }}, // Seite 3 (direkter Nachbar)
  {{ getBoundingClientRect: () => ({{ top: 1300, bottom: 1800 }}) }},// Seite 4
  {{ getBoundingClientRect: () => ({{ top: 1900, bottom: 2400 }}) }},// Seite 5
  {{ getBoundingClientRect: () => ({{ top: 2500, bottom: 3000 }}) }},// Seite 6
];
const res = E.computeVisiblePageIndices(container, pageWraps);
assert.deepStrictEqual(res.priority, [1, 2, 3, 4]);
console.log(JSON.stringify({{ ok: true }}));
"""
    proc = subprocess.run(["node", "-e", js], cwd=str(ROOT), capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip())["ok"] is True
