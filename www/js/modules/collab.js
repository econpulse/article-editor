/**
 * LUKB Editor Modul: Echtzeit-Co-Authoring Presence & Fokus-Badges
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function notifyFocusTarget() { return E.notifyFocusTarget.apply(this, arguments); }
  const state = E.state;

  // ==========================================================================
  // Multi-User Kollaboration: Präsenz-Anzeige & Block-Fokus-Indikatoren
  // ==========================================================================

  function renderPresenceBar() {
    const bar = document.getElementById("lukb-collab-presence");
    if (!bar) return;
    bar.innerHTML = "";

    const otherPeers = (state.peers || []).filter(function (p) {
      return p.session_id !== state.selfSessionId;
    });

    if (otherPeers.length === 0) {
      bar.style.display = "none";
      return;
    }

    bar.style.display = "inline-flex";
    const label = document.createElement("span");
    label.className = "collab-presence-label";
    label.textContent = "Co-Autoren aktiv:";
    bar.appendChild(label);

    otherPeers.forEach(function (peer) {
      const chip = document.createElement("span");
      chip.className = "collab-peer-chip";
      chip.style.borderColor = peer.color || "#009FE3";
      chip.title = peer.user + " arbeitet ebenfalls an diesem Artikel";

      const dot = document.createElement("span");
      dot.className = "collab-peer-dot";
      dot.style.backgroundColor = peer.color || "#009FE3";

      const name = document.createElement("span");
      name.textContent = peer.user || "Analyst";

      chip.appendChild(dot);
      chip.appendChild(name);
      bar.appendChild(chip);
    });
  }

  function applyPeerFocusDecorations() {
    const otherPeers = (state.peers || []).filter(function (p) {
      return p.session_id !== state.selfSessionId && p.focused_target;
    });

    const peerByTarget = {};
    otherPeers.forEach(function (p) {
      peerByTarget[p.focused_target] = p;
    });

    document.querySelectorAll(".cms-block-card").forEach(function (card) {
      const bid = card.dataset.blockId || "";
      const peer = peerByTarget[bid];
      const badge = card.querySelector(".block-peer-badge");
      if (peer) {
        card.classList.add("block-peer-focused");
        card.style.boxShadow = "0 0 0 2px " + (peer.color || "#009FE3");
        if (badge) {
          badge.style.display = "inline-flex";
          badge.style.backgroundColor = peer.color || "#009FE3";
          badge.textContent = "✏️ " + (peer.user || "Co-Autor") + " bearbeitet …";
        }
      } else {
        card.classList.remove("block-peer-focused");
        card.style.boxShadow = "";
        if (badge) {
          badge.style.display = "none";
          badge.textContent = "";
        }
      }
    });
  }

  function bindFocusTrackingListeners() {
    const pane = document.querySelector(".cms-editor-pane");
    if (!pane) return;

    pane.addEventListener("focusin", function (e) {
      const target = e.target;
      if (!target) return;
      const blockCard = target.closest(".cms-block-card");
      if (blockCard && blockCard.dataset.blockId) {
        notifyFocusTarget(blockCard.dataset.blockId);
        return;
      }
      if (target.id && target.id.startsWith("meta-")) {
        notifyFocusTarget(target.id);
        return;
      }
    });

    pane.addEventListener("focusout", function () {
      setTimeout(function () {
        const active = document.activeElement;
        if (!active || !pane.contains(active)) {
          notifyFocusTarget("");
        }
      }, 120);
    });
  }

  function bindDropdownListeners() {
    document.addEventListener("click", function (ev) {
      const toggle = ev.target.closest(".lukb-dropdown-toggle");
      const dropdown = toggle ? toggle.closest(".lukb-dropdown") : null;

      document.querySelectorAll(".lukb-dropdown.show").forEach(function (d) {
        if (d !== dropdown) {
          d.classList.remove("show");
        }
      });

      if (dropdown) {
        ev.preventDefault();
        ev.stopPropagation();
        dropdown.classList.toggle("show");
        return;
      }

      if (ev.target.closest(".lukb-dropdown-item")) {
        document.querySelectorAll(".lukb-dropdown.show").forEach(function (d) {
          d.classList.remove("show");
        });
      }
    });
  }


  function mergeRemoteBlocks(localBlocks, prevBaseBlocks, incomingBlocks, focusedBlockId, isDirty) {
    const locList = localBlocks || [];
    const localBlocksById = {};
    locList.forEach(function (b) {
      localBlocksById[b.id] = b;
    });
    const prevBaseById = {};
    (prevBaseBlocks || []).forEach(function (b) {
      prevBaseById[b.id] = b;
    });

    const mergedBlocks = [];
    const mergedIdSet = {};
    (incomingBlocks || []).forEach(function (incBlk) {
      const locBlk = localBlocksById[incBlk.id];
      const baseBlk = prevBaseById[incBlk.id];

      // Lokal gelöschten Block respektieren, solange er nicht parallel remote editiert wurde
      if (isDirty && baseBlk && !locBlk && JSON.stringify(incBlk) === JSON.stringify(baseBlk)) {
        return;
      }

      const isLocallyModified =
        locBlk && (!baseBlk || JSON.stringify(locBlk) !== JSON.stringify(baseBlk));

      if (locBlk && (incBlk.id === focusedBlockId || (isDirty && isLocallyModified))) {
        mergedBlocks.push(locBlk);
      } else {
        mergedBlocks.push(incBlk);
      }
      mergedIdSet[incBlk.id] = true;
    });

    // Lokal neu angelegte Blöcke (noch nicht in incomingBlocks) an relativer Position erhalten
    locList.forEach(function (locBlk, locIdx) {
      if (mergedIdSet[locBlk.id]) return;
      const baseBlk = prevBaseById[locBlk.id];
      const isLocalNew = !baseBlk && (isDirty || locBlk.id === focusedBlockId);
      if (!isLocalNew) return;

      let insertPos = mergedBlocks.length;
      if (locIdx === 0) {
        insertPos = 0;
      } else {
        for (let j = locIdx - 1; j >= 0; j--) {
          const prevId = locList[j].id;
          const foundIdx = mergedBlocks.findIndex(function (b) { return b.id === prevId; });
          if (foundIdx !== -1) {
            insertPos = foundIdx + 1;
            break;
          }
          if (j === 0) insertPos = 0;
        }
      }
      mergedBlocks.splice(insertPos, 0, locBlk);
      mergedIdSet[locBlk.id] = true;
    });

    return {
      mergedBlocks: mergedBlocks,
      mergedIdSet: mergedIdSet,
      localBlocksById: localBlocksById,
    };
  }


  function syncRemoteBlocksToCanvas(localBlocks, mergedBlocks, mergedIdSet, localBlocksById, focusedBlockId) {
    const oldOrder = (localBlocks || []).map(function (b) { return b.id; }).join(",");
    const newOrder = mergedBlocks.map(function (b) { return b.id; }).join(",");

    if (oldOrder !== newOrder && !focusedBlockId) {
      if (typeof E.renderBlocksCanvas === "function") E.renderBlocksCanvas();
      return;
    }

    const canvas = document.getElementById("lukb-blocks-canvas");
    if (!canvas) return;

    // Entferne Karten, die remote gelöscht wurden (außer lokal fokussierte)
    Array.from(canvas.querySelectorAll(":scope > .cms-block-card")).forEach(function (card) {
      const cid = card.dataset.blockId || "";
      if (cid && !mergedIdSet[cid] && cid !== focusedBlockId) {
        card.remove();
      }
    });

    let insideBox = false;
    mergedBlocks.forEach(function (blk, idx) {
      if (blk.type === "box_start") insideBox = true;
      const existingCard = canvas.querySelector('[data-block-id="' + blk.id + '"]');
      if (blk.id !== focusedBlockId) {
        const locBlk = localBlocksById[blk.id];
        const isUnchanged = locBlk && JSON.stringify(locBlk) === JSON.stringify(blk);
        let targetCard = existingCard;
        if (!isUnchanged || !existingCard) {
          // Optimierter In-Place Update für Richtext & Callout (vermeidet DOM-Zerstörung)
          if (existingCard && (blk.type === "richtext" || blk.type === "callout") && locBlk && locBlk.type === blk.type) {
            const editable = existingCard.querySelector(".richtext-editable");
            if (editable && editable !== document.activeElement && editable.innerHTML !== blk.html) {
              editable.innerHTML = blk.html || "<p></p>";
              if (blk.type === "callout") {
                const titleInp = existingCard.querySelector(".cms-input");
                if (titleInp && titleInp !== document.activeElement) titleInp.value = blk.title || "";
              }
            }
          } else if (typeof E.buildBlockCardElement === "function") {
            const newCard = E.buildBlockCardElement(blk, idx, insideBox);
            if (existingCard) {
              canvas.replaceChild(newCard, existingCard);
            } else {
              const refNode = canvas.children[idx] || null;
              canvas.insertBefore(newCard, refNode);
            }
            targetCard = newCard;
          }
        }
        if (targetCard && canvas.children[idx] !== targetCard) {
          const refNode = canvas.children[idx] || null;
          if (refNode !== targetCard) {
            canvas.insertBefore(targetCard, refNode);
          }
        }
      }
      if (blk.type === "box_end") insideBox = false;
    });
    if (typeof E.reindexCanvasCards === "function") E.reindexCanvasCards(canvas);
  }


  Object.assign(E, {
    applyPeerFocusDecorations: applyPeerFocusDecorations,
    bindDropdownListeners: bindDropdownListeners,
    bindFocusTrackingListeners: bindFocusTrackingListeners,
    mergeRemoteBlocks: mergeRemoteBlocks,
    renderPresenceBar: renderPresenceBar,
    syncRemoteBlocksToCanvas: syncRemoteBlocksToCanvas,
  });
})();
