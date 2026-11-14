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


  Object.assign(E, {
    applyPeerFocusDecorations: applyPeerFocusDecorations,
    bindDropdownListeners: bindDropdownListeners,
    bindFocusTrackingListeners: bindFocusTrackingListeners,
    renderPresenceBar: renderPresenceBar,
  });
})();
