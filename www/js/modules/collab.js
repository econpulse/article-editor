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
        card.classList.add("block-peer-focused", "block-peer-locked");
        card.dataset.peerLocked = "1";
        card.style.boxShadow = "0 0 0 2px " + (peer.color || "#009FE3");

        // Soft-Lock: Eingabefelder & Editables im gesperrten Block schreibschützen
        card.querySelectorAll("input, select, textarea, button").forEach(function (ctrl) {
          if (ctrl.classList.contains("block-lock-takeover-btn")) return;
          if (!ctrl.disabled) {
            ctrl.disabled = true;
            ctrl.dataset.peerDisabled = "1";
          }
        });
        card.querySelectorAll('[contenteditable="true"]').forEach(function (ed) {
          ed.setAttribute("contenteditable", "false");
          ed.dataset.peerCe = "1";
        });

        if (badge) {
          badge.style.display = "inline-flex";
          badge.style.backgroundColor = peer.color || "#009FE3";
          badge.innerHTML = "";
          const txt = document.createElement("span");
          txt.textContent = "🔒 " + (peer.user || "Co-Autor") + " bearbeitet …";
          const takeBtn = document.createElement("button");
          takeBtn.type = "button";
          takeBtn.className = "block-lock-takeover-btn";
          takeBtn.textContent = "Übernehmen";
          takeBtn.title = "Bearbeitung dieses Blocks von " + (peer.user || "Co-Autor") + " übernehmen";
          takeBtn.addEventListener("click", function (ev) {
            ev.stopPropagation();
            if (E.sendShinyEvent) {
              E.sendShinyEvent("lukb_request_block_lock", { block_id: bid });
            }
          });
          badge.appendChild(txt);
          badge.appendChild(takeBtn);
        }
      } else {
        card.classList.remove("block-peer-focused", "block-peer-locked");
        if (card.dataset.peerLocked === "1") {
          delete card.dataset.peerLocked;
          card.querySelectorAll('[data-peer-disabled="1"]').forEach(function (ctrl) {
            ctrl.disabled = false;
            delete ctrl.dataset.peerDisabled;
          });
          card.querySelectorAll('[data-peer-ce="1"]').forEach(function (ed) {
            ed.setAttribute("contenteditable", "true");
            delete ed.dataset.peerCe;
          });
        }
        card.style.boxShadow = "";
        if (badge) {
          badge.style.display = "none";
          badge.innerHTML = "";
        }
      }
    });
  }

  function renderPublishSyncBanner(publishSync) {
    state.publishSync = publishSync || null;
    const banner = document.getElementById("lukb-publish-sync-banner");
    const textEl = document.getElementById("lukb-publish-sync-text");
    if (!banner || !textEl) return;

    if (publishSync && publishSync.is_published && publishSync.has_unpublished_changes) {
      const verLabel = publishSync.snapshot_version ? "v" + publishSync.snapshot_version : "Live-Stand";
      textEl.textContent =
        "⚠️ Live-Stand (Portal " +
        verLabel +
        ") weicht vom aktuellen Entwurf ab — Änderungen sind noch nicht auf dem Portal publiziert.";
      banner.style.display = "flex";
    } else {
      banner.style.display = "none";
      textEl.textContent = "";
    }
  }

  function closeRevisionsModal() {
    const backdrop = document.getElementById("lukb-rev-modal-backdrop");
    if (backdrop) backdrop.style.display = "none";
  }

  function openRevisionsModal(msg) {
    const backdrop = document.getElementById("lukb-rev-modal-backdrop");
    const tbody = document.getElementById("rev-modal-tbody");
    const titlePill = document.getElementById("rev-modal-article-title");
    if (!backdrop || !tbody) return;

    if (titlePill) {
      titlePill.textContent = (msg && msg.title) ? msg.title : "Publikation";
    }
    tbody.innerHTML = "";

    const revs = (msg && Array.isArray(msg.revisions)) ? msg.revisions : [];
    if (revs.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.style.textAlign = "center";
      td.style.padding = "24px";
      td.style.color = "#5A687C";
      td.textContent = "Noch keine gespeicherten Revisionen für diesen Artikel vorhanden.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      revs.forEach(function (rev, idx) {
        const tr = document.createElement("tr");

        const tdTime = document.createElement("td");
        tdTime.textContent = rev.saved_at || "";

        const tdBy = document.createElement("td");
        tdBy.textContent = rev.saved_by || "";

        const tdNote = document.createElement("td");
        tdNote.textContent = rev.note || "Snapshot";

        const tdCount = document.createElement("td");
        tdCount.textContent = String(rev.block_count || 0) + " Blöcke";

        const tdAct = document.createElement("td");
        tdAct.style.textAlign = "right";
        if (idx === 0) {
          const curSpan = document.createElement("span");
          curSpan.className = "sidebar-count-pill";
          curSpan.textContent = "Neuester Stand";
          tdAct.appendChild(curSpan);
        } else {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
          btn.textContent = "↺ Wiederherstellen";
          btn.addEventListener("click", function () {
            if (E.sendShinyEvent) {
              E.sendShinyEvent("lukb_restore_revision", { revision_id: rev.id });
            }
            closeRevisionsModal();
          });
          tdAct.appendChild(btn);
        }

        tr.appendChild(tdTime);
        tr.appendChild(tdBy);
        tr.appendChild(tdNote);
        tr.appendChild(tdCount);
        tr.appendChild(tdAct);
        tbody.appendChild(tr);
      });
    }

    backdrop.style.display = "flex";
  }

  window.lukbCloseRevisionsModal = closeRevisionsModal;

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


  function registerCollabMessageHandlers() {
    if (!window.Shiny || !window.Shiny.addCustomMessageHandler) return;

    window.Shiny.addCustomMessageHandler("lukb_global_presence", function (msg) {
      if (msg.self_session_id) state.selfSessionId = msg.self_session_id;
      if (msg.active_peers_by_article) {
        state.activePeersByArticle = msg.active_peers_by_article;
        if (typeof E.renderArticleList === "function") {
          E.renderArticleList(state.sidebarArticles || [], state.activeArticleId, false);
        }
      }
    });

    window.Shiny.addCustomMessageHandler("lukb_global_article_list", function (msg) {
      if (msg.self_session_id) state.selfSessionId = msg.self_session_id;
      if (msg.active_peers_by_article) state.activePeersByArticle = msg.active_peers_by_article;
      if (Array.isArray(msg.all_articles)) {
        state.allArticles = msg.all_articles;
        const searchInp = document.getElementById("sidebar-search-input");
        const activeFilterBtn = document.querySelector(".sidebar-filter-btn.active");
        const hasFilter = (searchInp && searchInp.value.trim()) || (activeFilterBtn && activeFilterBtn.dataset.status !== "all");
        if (!hasFilter) {
          state.sidebarArticles = msg.all_articles;
        }
        if (typeof E.renderArticleList === "function") {
          E.renderArticleList(state.sidebarArticles || [], state.activeArticleId, !!hasFilter);
        }
        if (state.modalOpen) {
          if (typeof E.populateModalCategoryDropdown === "function") E.populateModalCategoryDropdown();
          if (typeof E.renderPubModalTable === "function") E.renderPubModalTable();
        }
      }
    });

    window.Shiny.addCustomMessageHandler("lukb_revisions_list", function (msg) {
      openRevisionsModal(msg);
    });

    window.Shiny.addCustomMessageHandler("lukb_collab_notice", function (msg) {
      if (msg && msg.message && typeof E.setAutosaveIndicator === "function") {
        E.setAutosaveIndicator("saved", msg.message);
      }
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") {
        const backdrop = document.getElementById("lukb-rev-modal-backdrop");
        if (backdrop && backdrop.style.display !== "none") {
          closeRevisionsModal();
        }
      }
    });
  }


  Object.assign(E, {
    applyPeerFocusDecorations: applyPeerFocusDecorations,
    bindDropdownListeners: bindDropdownListeners,
    bindFocusTrackingListeners: bindFocusTrackingListeners,
    closeRevisionsModal: closeRevisionsModal,
    mergeRemoteBlocks: mergeRemoteBlocks,
    openRevisionsModal: openRevisionsModal,
    registerCollabMessageHandlers: registerCollabMessageHandlers,
    renderPresenceBar: renderPresenceBar,
    renderPublishSyncBanner: renderPublishSyncBanner,
    syncRemoteBlocksToCanvas: syncRemoteBlocksToCanvas,
  });
})();
