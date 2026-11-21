"""
Tests für Etappe 0 (Frontend-Stabilisierung):
- Co-Autoren-Merge erhält Objektreferenz & bestehende DOM-Karten für unveränderte Blöcke
- Konflikterkennung bei paralleler Bearbeitung desselben Felds
- Verspätete Autosave-Bestätigungen (alte editSeq oder falscher Artikel) markieren jüngere Eingaben nicht als gespeichert
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_JS = ROOT / "www" / "js" / "modules" / "state.js"
COLLAB_JS = ROOT / "www" / "js" / "modules" / "collab.js"


def _run_node(script: str) -> dict:
    proc = subprocess.run(
        ["node", "-e", script],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"Node test failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    return json.loads(proc.stdout.strip())


def test_collab_merge_preserves_block_reference_and_detects_conflicts() -> None:
    js = f"""
const assert = require('assert');
const fs = require('fs');

global.window = global;
global.document = {{
  addEventListener: () => {{}},
  getElementById: () => null,
  querySelectorAll: () => [],
}};

eval(fs.readFileSync({json.dumps(str(STATE_JS))}, 'utf8'));
eval(fs.readFileSync({json.dumps(str(COLLAB_JS))}, 'utf8'));

const E = window.LUKBEditor;

// Ausgangsstand: 2 Blöcke
const baseBlocks = [
  {{ id: 'blk1', type: 'richtext', html: '<p>Alt 1</p>' }},
  {{ id: 'blk2', type: 'heading', level: 2, text: 'Alt 2' }},
];
const localBlocks = JSON.parse(JSON.stringify(baseBlocks));
const incomingBlocks = [
  {{ id: 'blk1', type: 'richtext', html: '<p>Von A geändert</p>' }},
  {{ id: 'blk2', type: 'heading', level: 2, text: 'Alt 2' }},
];

// Simuliere einen Event-Handler auf Block 2, der beim Initialbau an localBlocks[1] gebunden wurde
const boundBlock2Ref = localBlocks[1];

E.state.article = {{ id: 'art_1', blocks: localBlocks }};
const mergeRes = E.mergeRemoteBlocks(localBlocks, baseBlocks, incomingBlocks, '', false);
E.state.article.blocks = mergeRes.mergedBlocks;

// 1. Block 1 wurde remote aktualisiert (In-Place auf richtext)
assert.strictEqual(E.state.article.blocks[0].html, '<p>Von A geändert</p>');
// 2. Block 2 ist unverändert: Objektreferenz MUSS identisch zu boundBlock2Ref sein
assert.strictEqual(E.state.article.blocks[1], boundBlock2Ref);

// 3. B tippt über den bestehenden Event-Handler in Block 2 -> ändert aktuelles Artikelmodell!
boundBlock2Ref.text = 'Von B bearbeitet';
assert.strictEqual(E.state.article.blocks[1].text, 'Von B bearbeitet');
assert.strictEqual(E.resolveCurrentBlock('blk2').text, 'Von B bearbeitet');

// 4. Konflikttest: A und B ändern beide dasselbe Feld in blk1
const conflictBase = [{{ id: 'blk1', type: 'heading', level: 2, text: 'Start' }}];
const conflictLocal = [{{ id: 'blk1', type: 'heading', level: 2, text: 'Lokal B' }}];
const conflictIncoming = [{{ id: 'blk1', type: 'heading', level: 2, text: 'Remote A' }}];
const conflictRes = E.mergeRemoteBlocks(conflictLocal, conflictBase, conflictIncoming, 'blk1', true);
assert.strictEqual(conflictRes.mergedBlocks[0].text, 'Lokal B');
assert.strictEqual(conflictRes.conflicts.length, 1);
assert.strictEqual(conflictRes.conflicts[0].blockId, 'blk1');
assert.deepStrictEqual(conflictRes.conflicts[0].fields, ['text']);

console.log(JSON.stringify({{ ok: true }}));
"""
    res = _run_node(js)
    assert res["ok"] is True


def test_delayed_autosave_ack_keeps_newer_edits_dirty() -> None:
    js = f"""
const assert = require('assert');
const fs = require('fs');

const sentEvents = [];
let indicatorState = null;

global.window = global;
global.window.Shiny = {{
  setInputValue: (name, data) => sentEvents.push({{ name, data }}),
}};
global.document = {{
  addEventListener: () => {{}},
  getElementById: (id) => {{
    if (id === 'lukb-autosave-pill') {{
      return {{
        classList: {{
          remove: () => {{}},
          add: (cls) => {{ indicatorState = Object.assign(indicatorState || {{}}, {{ cls }}); }},
        }},
      }};
    }}
    if (id === 'lukb-autosave-text') {{
      return {{
        set textContent(v) {{ indicatorState = Object.assign(indicatorState || {{}}, {{ text: v }}); }},
      }};
    }}
    return null;
  }},
  querySelector: () => null,
}};

eval(fs.readFileSync({json.dumps(str(STATE_JS))}, 'utf8'));

const E = window.LUKBEditor;
E.state.article = {{ id: 'art_1', version: 1, status: 'draft', metadata: {{ title: 'T1' }}, blocks: [] }};
E.state.baseArticle = E.deepClone(E.state.article);
E.state.editSeq = 0;
E.state.isDirty = false;

// 1. Änderung -> editSeq = 1
E.markDirty();
assert.strictEqual(E.state.editSeq, 1);
assert.strictEqual(E.state.isDirty, true);

// 2. Autosave für editSeq = 1 absenden
E.flushAutosave(false);
const lastPayload = sentEvents[sentEvents.length - 1].data;
assert.strictEqual(lastPayload.client_edit_seq, 1);
assert.strictEqual(lastPayload.article_id, 'art_1');

// 3. Nutzer tippt weiter bevor Bestätigung eintrifft -> editSeq = 2
E.markDirty();
assert.strictEqual(E.state.editSeq, 2);
assert.strictEqual(E.state.isDirty, true);

// 4. Verspätete Bestätigung für editSeq = 1 trifft ein -> DARF NICHT als gespeichert markieren!
const settled1 = E.handleAutosaveAck({{
  id: 'art_1',
  client_edit_seq: 1,
  saved_at: '23:00:01',
  article: {{ id: 'art_1', version: 2, status: 'draft', metadata: {{ title: 'T1' }}, blocks: [] }},
}});
assert.strictEqual(settled1, false);
assert.strictEqual(E.state.isDirty, true);
assert.strictEqual(indicatorState.cls, 'status-dirty');
assert.strictEqual(E.state.article.version, 2);

// 5. Verspätete Bestätigung für einen anderen Artikel -> komplett ignorieren!
const settledWrong = E.handleAutosaveAck({{
  id: 'art_other',
  client_edit_seq: 2,
  saved_at: '23:00:02',
  article: {{ id: 'art_other', version: 99, status: 'draft', metadata: {{ title: 'Other' }}, blocks: [] }},
}});
assert.strictEqual(settledWrong, false);
assert.strictEqual(E.state.article.version, 2);
assert.strictEqual(E.state.isDirty, true);

// 6. Bestätigung für aktuellen Stand editSeq = 2 trifft ein -> jetzt gespeichert!
const settled2 = E.handleAutosaveAck({{
  id: 'art_1',
  client_edit_seq: 2,
  saved_at: '23:00:05',
  article: {{ id: 'art_1', version: 3, status: 'draft', metadata: {{ title: 'T1' }}, blocks: [] }},
}});
assert.strictEqual(settled2, true);
assert.strictEqual(E.state.isDirty, false);
assert.strictEqual(indicatorState.cls, 'status-saved');
assert.strictEqual(E.state.lastSavedSeq, 2);

// Timer aufräumen, damit Node sauber beendet
if (E.state.autosaveTimer) clearTimeout(E.state.autosaveTimer);
console.log(JSON.stringify({{ ok: true }}));
"""
    res = _run_node(js)
    assert res["ok"] is True
