/**
 * LUKB Investment Office — Haupt-Orchestrator, Block-Canvas (SortableJS) & Shiny-Handler
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  const BLOCK_TYPE_CATALOG = E.BLOCK_TYPE_CATALOG;
  function applyPeerFocusDecorations() { return E.applyPeerFocusDecorations.apply(this, arguments); }
  function bindDropdownListeners() { return E.bindDropdownListeners.apply(this, arguments); }
  function bindFocusTrackingListeners() { return E.bindFocusTrackingListeners.apply(this, arguments); }
  function bindSidebarAndModalListeners() { return E.bindSidebarAndModalListeners.apply(this, arguments); }
  function buildCalloutBlockBody() { return E.buildCalloutBlockBody.apply(this, arguments); }
  function buildColbreakBlockBody() { return E.buildColbreakBlockBody.apply(this, arguments); }
  function buildCustomChartBlockBody() { return E.buildCustomChartBlockBody.apply(this, arguments); }
  function buildDbChartBlockBody() { return E.buildDbChartBlockBody.apply(this, arguments); }
  function buildDividerBlockBody() { return E.buildDividerBlockBody.apply(this, arguments); }
  function buildGlossaryBlockBody() { return E.buildGlossaryBlockBody.apply(this, arguments); }
  function buildQuoteBlockBody() { return E.buildQuoteBlockBody.apply(this, arguments); }
  function buildRichTextBlockBody() { return E.buildRichTextBlockBody.apply(this, arguments); }
  function buildSpacerBlockBody() { return E.buildSpacerBlockBody.apply(this, arguments); }
  function buildTableBlockBody() { return E.buildTableBlockBody.apply(this, arguments); }
  function cleanPdfPastedText() { return E.cleanPdfPastedText.apply(this, arguments); }
  function clearUndoStack() { return E.clearUndoStack.apply(this, arguments); }
  function closeFigureContextMenu() { return E.closeFigureContextMenu.apply(this, arguments); }
  function createDefaultBlock() { return E.createDefaultBlock.apply(this, arguments); }
  function createFullLayoutControl() { return E.createFullLayoutControl.apply(this, arguments); }
  function deepClone() { return E.deepClone.apply(this, arguments); }
  function flushAutosave() { return E.flushAutosave.apply(this, arguments); }
  function getActiveFocusedBlockId() { return E.getActiveFocusedBlockId.apply(this, arguments); }
  function getBlockTypeLabel() { return E.getBlockTypeLabel.apply(this, arguments); }
  function indexTickerItems() { return E.indexTickerItems.apply(this, arguments); }
  function markDirty() { return E.markDirty.apply(this, arguments); }
  function populateModalCategoryDropdown() { return E.populateModalCategoryDropdown.apply(this, arguments); }
  function pushUndo() { return E.pushUndo.apply(this, arguments); }
  function renderArticleList() { return E.renderArticleList.apply(this, arguments); }
  function renderPresenceBar() { return E.renderPresenceBar.apply(this, arguments); }
  function renderPubModalTable() { return E.renderPubModalTable.apply(this, arguments); }
  function renderTickerSuggestItems() { return E.renderTickerSuggestItems.apply(this, arguments); }
  function setAutosaveIndicator() { return E.setAutosaveIndicator.apply(this, arguments); }
  const state = E.state;
  const tickerSuggest = E.tickerSuggest;
  function uid() { return E.uid.apply(this, arguments); }
  function updateLiveStatsCounter() { return E.updateLiveStatsCounter.apply(this, arguments); }

  function renderMetadataForm() {
    if (!state.article) return;
    const meta = state.article.metadata || {};

    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el && document.activeElement !== el) {
        el.value = val != null ? val : "";
      }
    };

    setVal("meta-template-id", state.article.template_id || "investment_focus");
    setVal("meta-status", state.article.status || "draft");
    setVal("meta-category", meta.category || "");
    setVal("meta-header-series", meta.header_series || "Investment Office News");
    setVal("meta-pub-date", meta.publication_date || "");
    setVal("meta-title", meta.title || "");
    setVal("meta-subtitle", meta.subtitle || "");
    setVal("meta-lead", meta.lead || "");
    setVal("meta-disclaimer", meta.disclaimer || "");

    renderAuthorsList();
    renderTagsList();
    updateLiveStatsCounter();
  }

  function renderTagsList() {
    const container = document.getElementById("meta-tags-container");
    if (!container || !state.article) return;
    container.innerHTML = "";

    if (!Array.isArray(state.article.metadata.tags)) {
      state.article.metadata.tags = [];
    }

    state.article.metadata.tags.forEach(function (tag, idx) {
      const chip = document.createElement("span");
      chip.className = "tag-chip";
      chip.textContent = tag;

      const del = document.createElement("span");
      del.className = "tag-chip-del";
      del.textContent = "✕";
      del.title = "Tag entfernen";
      del.addEventListener("click", function () {
        state.article.metadata.tags.splice(idx, 1);
        renderTagsList();
        markDirty();
      });

      chip.appendChild(del);
      container.appendChild(chip);
    });
  }

  function renderAuthorsList() {
    const container = document.getElementById("meta-authors-container");
    if (!container || !state.article) return;
    container.innerHTML = "";

    const authors = state.article.metadata.authors || [];
    authors.forEach(function (author, idx) {
      const row = document.createElement("div");
      row.className = "author-row-item";

      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.className = "cms-input";
      nameInput.placeholder = "Titel Vorname Name";
      nameInput.value = author.name || "";
      nameInput.addEventListener("input", function () {
        state.article.metadata.authors[idx].name = nameInput.value;
        markDirty();
      });

      const roleInput = document.createElement("input");
      roleInput.type = "text";
      roleInput.className = "cms-input";
      roleInput.placeholder = "Funktion (z.B. Chief Investment Officer)";
      roleInput.value = author.role || "";
      roleInput.addEventListener("input", function () {
        state.article.metadata.authors[idx].role = roleInput.value;
        markDirty();
      });

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "btn-icon-only danger";
      delBtn.title = "Autor entfernen";
      delBtn.innerHTML = "✕";
      delBtn.addEventListener("click", function () {
        state.article.metadata.authors.splice(idx, 1);
        renderAuthorsList();
        markDirty();
      });

      row.appendChild(nameInput);
      row.appendChild(roleInput);
      row.appendChild(delBtn);
      container.appendChild(row);
    });
  }

  function bindMetadataStaticListeners() {
    const bindField = (id, setter) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("input", function () {
        if (!state.article) return;
        setter(el.value);
        markDirty();
      });
    };

    bindField("meta-template-id", (v) => (state.article.template_id = v));
    bindField("meta-status", (v) => (state.article.status = v));
    bindField("meta-category", (v) => (state.article.metadata.category = v));
    bindField("meta-header-series", (v) => (state.article.metadata.header_series = v));
    bindField("meta-pub-date", (v) => (state.article.metadata.publication_date = v));
    bindField("meta-title", (v) => (state.article.metadata.title = v));
    bindField("meta-subtitle", (v) => (state.article.metadata.subtitle = v));
    bindField("meta-lead", (v) => (state.article.metadata.lead = v));
    bindField("meta-disclaimer", (v) => (state.article.metadata.disclaimer = v));

    const addAuthorBtn = document.getElementById("btn-add-author");
    if (addAuthorBtn) {
      addAuthorBtn.addEventListener("click", function () {
        if (!state.article) return;
        if (!Array.isArray(state.article.metadata.authors)) {
          state.article.metadata.authors = [];
        }
        state.article.metadata.authors.push({ name: "", role: "" });
        renderAuthorsList();
        markDirty();
      });
    }

    const tagInput = document.getElementById("meta-tag-input");
    if (tagInput) {
      tagInput.addEventListener("keydown", function (e) {
        if (!state.article) return;
        if (!Array.isArray(state.article.metadata.tags)) {
          state.article.metadata.tags = [];
        }
        if (e.key === "Enter" || e.key === ",") {
          e.preventDefault();
          const val = tagInput.value.replace(/,/g, "").trim();
          if (val && !state.article.metadata.tags.includes(val)) {
            state.article.metadata.tags.push(val);
            tagInput.value = "";
            renderTagsList();
            markDirty();
          }
        } else if (e.key === "Backspace" && !tagInput.value && state.article.metadata.tags.length > 0) {
          state.article.metadata.tags.pop();
          renderTagsList();
          markDirty();
        }
      });
    }
  }

  function getCardCurrentIndex(cardOrId) {
    if (!state.article || !state.article.blocks) return -1;
    const id = typeof cardOrId === "string" ? cardOrId : (cardOrId && cardOrId.dataset ? cardOrId.dataset.blockId : null);
    if (!id) return -1;
    return state.article.blocks.findIndex(function (b) { return b.id === id; });
  }

  function highlightInsertedBlock(id) {
    if (!id) return;
    setTimeout(function () {
      const el = document.querySelector('[data-block-id="' + id + '"]');
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("sortable-ghost");
        setTimeout(function () {
          el.classList.remove("sortable-ghost");
        }, 500);
      }
    }, 50);
  }

  function insertBlockAt(targetIndex, blockType) {
    if (!state.article) return;
    if (!state.article.blocks) state.article.blocks = [];

    const canvas = document.getElementById("lukb-blocks-canvas");
    const existingCards = canvas ? Array.from(canvas.querySelectorAll(":scope > .cms-block-card")) : [];

    // Falls Canvas noch leer ist (Empty-State aktiv) oder noch nicht gerendert wurde: volles Rendering
    if (!canvas || existingCards.length === 0 || existingCards.length !== state.article.blocks.length) {
      const createdIds = [];
      if (blockType === "textbox_pair") {
        const bStart = createDefaultBlock("box_start");
        const bEnd = createDefaultBlock("box_end");
        state.article.blocks.splice(targetIndex, 0, bStart, bEnd);
        createdIds.push(bStart.id, bEnd.id);
      } else {
        const newBlk = createDefaultBlock(blockType);
        state.article.blocks.splice(targetIndex, 0, newBlk);
        createdIds.push(newBlk.id);
      }
      renderBlocksCanvas();
      markDirty();
      highlightInsertedBlock(createdIds[0]);
      return;
    }

    if (targetIndex < 0) targetIndex = 0;
    if (targetIndex > state.article.blocks.length) targetIndex = state.article.blocks.length;

    const refCard = targetIndex < existingCards.length ? existingCards[targetIndex] : null;
    const createdIds = [];

    if (blockType === "textbox_pair") {
      const bStart = createDefaultBlock("box_start");
      const bEnd = createDefaultBlock("box_end");
      state.article.blocks.splice(targetIndex, 0, bStart, bEnd);
      createdIds.push(bStart.id, bEnd.id);

      const cardStart = buildBlockCardElement(bStart, targetIndex, false);
      const cardEnd = buildBlockCardElement(bEnd, targetIndex + 1, true);

      if (refCard) {
        canvas.insertBefore(cardStart, refCard);
        canvas.insertBefore(cardEnd, refCard);
      } else {
        canvas.appendChild(cardStart);
        canvas.appendChild(cardEnd);
      }
    } else {
      const newBlk = createDefaultBlock(blockType);
      state.article.blocks.splice(targetIndex, 0, newBlk);
      createdIds.push(newBlk.id);

      const newCard = buildBlockCardElement(newBlk, targetIndex, false);
      if (refCard) {
        canvas.insertBefore(newCard, refCard);
      } else {
        canvas.appendChild(newCard);
      }
    }

    reindexCanvasCards(canvas);
    markDirty();
    highlightInsertedBlock(createdIds[0]);
  }

  let activePickerPopover = null;

  let activePickerDocClick = null;

  function attachOutsideDismiss(containerEl, triggerEl, onClose, setRef) {
    function onDocClick(e) {
      if (containerEl && !containerEl.contains(e.target) && (!triggerEl || !triggerEl.contains(e.target))) {
        onClose();
      }
    }
    setRef(onDocClick);
    setTimeout(function () { document.addEventListener("pointerdown", onDocClick); }, 15);
  }

  function closeBlockPickerPopup() {
    if (activePickerDocClick) {
      document.removeEventListener("pointerdown", activePickerDocClick);
      activePickerDocClick = null;
    }
    if (activePickerPopover && activePickerPopover.parentNode) {
      activePickerPopover.parentNode.removeChild(activePickerPopover);
    }
    activePickerPopover = null;
    document.querySelectorAll(".block-inline-inserter.is-active").forEach(function (el) {
      el.classList.remove("is-active");
    });
  }

  function openBlockPickerPopup(triggerElement, targetIndex) {
    closeBlockPickerPopup();

    if (typeof targetIndex !== "number" || targetIndex < 0) {
      const card = triggerElement.closest(".cms-block-card");
      if (card && card.parentElement) {
        const cards = Array.from(card.parentElement.querySelectorAll(":scope > .cms-block-card"));
        const idx = cards.indexOf(card);
        targetIndex = idx >= 0 ? idx + 1 : 0;
      } else {
        targetIndex = 0;
      }
    }

    const parentInserter = triggerElement.closest(".block-inline-inserter");
    if (parentInserter) {
      parentInserter.classList.add("is-active");
    }

    const popover = document.createElement("div");
    popover.className = "block-picker-popover";

    const header = document.createElement("div");
    header.className = "block-picker-header";
    header.innerHTML = "<span>Block einfügen (Position " + (targetIndex + 1) + ")</span>";

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "close-btn";
    closeBtn.textContent = "✕";
    closeBtn.title = "Schliessen (Esc)";
    closeBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      closeBlockPickerPopup();
    });
    header.appendChild(closeBtn);
    popover.appendChild(header);

    BLOCK_TYPE_CATALOG.forEach(function (cat) {
      const secTitle = document.createElement("div");
      secTitle.className = "block-picker-section-title";
      secTitle.textContent = cat.group;
      popover.appendChild(secTitle);

      const grid = document.createElement("div");
      grid.className = "block-picker-grid";

      cat.items.forEach(function (item) {
        const itemBtn = document.createElement("button");
        itemBtn.type = "button";
        itemBtn.className = "block-picker-item";
        itemBtn.innerHTML = '<span class="item-icon">' + item.icon + "</span><span>" + item.label + "</span>";
        itemBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          closeBlockPickerPopup();
          insertBlockAt(targetIndex, item.type);
        });
        grid.appendChild(itemBtn);
      });

      popover.appendChild(grid);
    });

    document.body.appendChild(popover);
    activePickerPopover = popover;

    const rect = triggerElement.getBoundingClientRect();
    const popoverWidth = 330;
    let left = rect.left + rect.width / 2 - popoverWidth / 2;
    if (left < 10) left = 10;
    if (left + popoverWidth > window.innerWidth - 10) {
      left = window.innerWidth - popoverWidth - 10;
    }

    let top = rect.bottom + 6;
    if (top + popover.offsetHeight > window.innerHeight - 10) {
      top = rect.top - popover.offsetHeight - 6;
    }

    popover.style.left = left + "px";
    popover.style.top = top + "px";

    attachOutsideDismiss(popover, triggerElement, closeBlockPickerPopup, function (fn) { activePickerDocClick = fn; });
  }

  function createInlineInserterElement(targetIndex, isTop) {
    const wrap = document.createElement("div");
    wrap.className = "block-inline-inserter " + (isTop ? "top-inserter" : "bottom-inserter");
    wrap.dataset.targetIndex = targetIndex;

    const line = document.createElement("div");
    line.className = "inserter-line";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "inserter-btn";
    btn.innerHTML = "+ Block hier einfügen";
    btn.title = "Neuen Block an dieser Stelle einfügen";
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      let idx = parseInt(wrap.dataset.targetIndex, 10);
      if (isNaN(idx)) {
        const parentCard = wrap.closest(".cms-block-card");
        if (parentCard) {
          const cardIdx = getCardCurrentIndex(parentCard);
          idx = isTop ? cardIdx : cardIdx + 1;
        } else {
          idx = 0;
        }
      }
      openBlockPickerPopup(btn, idx);
    });

    wrap.appendChild(line);
    wrap.appendChild(btn);
    return wrap;
  }

  // Multi-Selection State & Helpers
  function toggleBlockSelection(blockId, isShift, currentIndex) {
    if (!state.article || !state.article.blocks) return;
    if (typeof currentIndex !== "number" || currentIndex < 0) {
      currentIndex = getCardCurrentIndex(blockId);
    }

    if (isShift && state.lastSelectedBlockId) {
      const lastIdx = state.article.blocks.findIndex(function (b) {
        return b.id === state.lastSelectedBlockId;
      });
      if (lastIdx !== -1) {
        const start = Math.min(lastIdx, currentIndex);
        const end = Math.max(lastIdx, currentIndex);
        for (let i = start; i <= end; i++) {
          state.selectedBlockIds.add(state.article.blocks[i].id);
        }
      } else {
        state.selectedBlockIds.add(blockId);
      }
    } else {
      if (state.selectedBlockIds.has(blockId)) {
        state.selectedBlockIds.delete(blockId);
      } else {
        state.selectedBlockIds.add(blockId);
      }
      state.lastSelectedBlockId = blockId;
    }

    updateBlockSelectionVisuals();
    updateFloatingSelectionBar();
  }

  function updateBlockSelectionVisuals() {
    const cards = document.querySelectorAll(".cms-block-card");
    cards.forEach(function (card) {
      const bid = card.dataset.blockId;
      const isSelected = state.selectedBlockIds.has(bid);
      card.classList.toggle("is-selected", isSelected);
      card.classList.toggle("sortable-selected", isSelected);
      const cb = card.querySelector(".block-select-checkbox");
      if (cb) cb.checked = isSelected;
    });
  }

  function clearBlockSelection() {
    state.selectedBlockIds.clear();
    state.lastSelectedBlockId = null;
    updateBlockSelectionVisuals();
    updateFloatingSelectionBar();
  }

  function ensureFloatingSelectionBar() {
    let bar = document.getElementById("cms-floating-selection-bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "cms-floating-selection-bar";
      document.body.appendChild(bar);
    }
    return bar;
  }

  function moveSelectedBlocks(direction) {
    if (!state.article || !state.article.blocks) return;
    const blocks = state.article.blocks;
    const selected = [];
    let minIdx = blocks.length;
    let maxIdx = -1;

    blocks.forEach(function (b, idx) {
      if (state.selectedBlockIds.has(b.id)) {
        selected.push(b);
        if (idx < minIdx) minIdx = idx;
        if (idx > maxIdx) maxIdx = idx;
      }
    });

    if (selected.length === 0) return;

    const remaining = blocks.filter(function (b) {
      return !state.selectedBlockIds.has(b.id);
    });

    let targetIdx;
    if (direction === "up") {
      if (minIdx <= 0) return;
      targetIdx = minIdx - 1;
    } else {
      if (maxIdx >= blocks.length - 1) return;
      const nextUnselected = blocks[maxIdx + 1];
      const rIdx = remaining.findIndex(function (b) {
        return b.id === nextUnselected.id;
      });
      targetIdx = rIdx !== -1 ? rIdx + 1 : remaining.length;
    }

    if (targetIdx < 0) targetIdx = 0;
    if (targetIdx > remaining.length) targetIdx = remaining.length;

    remaining.splice(targetIdx, 0, ...selected);
    state.article.blocks = remaining;

    reorderCanvasCardsFromState();
    markDirty();
    updateFloatingSelectionBar();
  }

  function moveSelectedBlocksTo(targetIndex) {
    if (!state.article || !state.article.blocks) return;
    const selected = state.article.blocks.filter(function (b) {
      return state.selectedBlockIds.has(b.id);
    });
    const remaining = state.article.blocks.filter(function (b) {
      return !state.selectedBlockIds.has(b.id);
    });

    if (targetIndex < 0) targetIndex = 0;
    if (targetIndex > remaining.length) targetIndex = remaining.length;

    remaining.splice(targetIndex, 0, ...selected);
    state.article.blocks = remaining;

    reorderCanvasCardsFromState();
    markDirty();
    updateFloatingSelectionBar();
  }

  function duplicateSelectedBlocks() {
    if (!state.article || !state.article.blocks) return;
    const canvas = document.getElementById("lukb-blocks-canvas");
    if (!canvas) return;

    const newBlocks = [];
    const newSelectedIds = new Set();
    const insertions = [];

    state.article.blocks.forEach(function (b) {
      newBlocks.push(b);
      if (state.selectedBlockIds.has(b.id)) {
        const clone = deepClone(b);
        clone.id = uid("blk");
        newBlocks.push(clone);
        newSelectedIds.add(clone.id);
        const newCard = buildBlockCardElement(clone, newBlocks.length - 1, false);
        insertions.push({ origId: b.id, newCard: newCard });
      }
    });

    state.article.blocks = newBlocks;
    state.selectedBlockIds = newSelectedIds;

    insertions.forEach(function (ins) {
      const origCard = canvas.querySelector(':scope > [data-block-id="' + ins.origId + '"]');
      if (origCard && origCard.nextElementSibling) {
        canvas.insertBefore(ins.newCard, origCard.nextElementSibling);
      } else {
        canvas.appendChild(ins.newCard);
      }
    });

    reindexCanvasCards(canvas);
    markDirty();
    updateBlockSelectionVisuals();
    updateFloatingSelectionBar();
  }

  function deleteSelectedBlocks() {
    if (!state.article || !state.article.blocks) return;
    const count = state.selectedBlockIds.size;
    if (count === 0) return;
    if (count > 1 && !confirm(count + " ausgewählte Blöcke wirklich löschen?")) {
      return;
    }

    const canvas = document.getElementById("lukb-blocks-canvas");
    const deletedItems = [];
    const selectedIds = new Set(state.selectedBlockIds);

    state.article.blocks.forEach(function (b, idx) {
      if (selectedIds.has(b.id)) {
        deletedItems.push({ index: idx, block: deepClone(b) });
        if (canvas) {
          const card = canvas.querySelector(':scope > [data-block-id="' + b.id + '"]');
          if (card) card.remove();
        }
      }
    });

    state.article.blocks = state.article.blocks.filter(function (b) {
      return !selectedIds.has(b.id);
    });
    // Clear anchor references to deleted blocks
    state.article.blocks.forEach(function (b) {
      if (b && selectedIds.has(b.anchor_to)) {
        b.anchor_to = null;
      }
    });

    state.selectedBlockIds.clear();
    state.lastSelectedBlockId = null;

    if (state.article.blocks.length === 0) {
      renderBlocksCanvas();
    } else {
      reindexCanvasCards(canvas);
    }

    markDirty();
    updateFloatingSelectionBar();

    if (deletedItems.length > 0) {
      const desc =
        deletedItems.length === 1
          ? `Block «${getBlockTypeLabel(deletedItems[0].block.type)}» gelöscht`
          : `${deletedItems.length} Blöcke gelöscht`;
      pushUndo({
        type: "delete_blocks",
        description: desc,
        items: deletedItems,
      });
    }
  }

  let activeMoveDialogDocClick = null;

  function closeMoveToDialog() {
    if (activeMoveDialogDocClick) {
      document.removeEventListener("pointerdown", activeMoveDialogDocClick);
      activeMoveDialogDocClick = null;
    }
    const existing = document.getElementById("cms-move-to-dialog");
    if (existing && existing.parentNode) {
      existing.parentNode.removeChild(existing);
    }
  }

  function openMoveToDialog(anchorBtn) {
    closeBlockPickerPopup();

    const existingDialog = document.getElementById("cms-move-to-dialog");
    if (existingDialog) {
      closeMoveToDialog();
      return;
    }

    const dialog = document.createElement("div");
    dialog.id = "cms-move-to-dialog";
    dialog.className = "block-picker-popover";
    dialog.style.width = "280px";

    const header = document.createElement("div");
    header.className = "block-picker-header";
    header.innerHTML = "<span>Verschieben an Position…</span>";
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "close-btn";
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      closeMoveToDialog();
    });
    header.appendChild(closeBtn);
    dialog.appendChild(header);

    const list = document.createElement("div");
    list.style.maxHeight = "280px";
    list.style.overflowY = "auto";
    list.style.display = "flex";
    list.style.flexDirection = "column";
    list.style.gap = "4px";

    const topItem = document.createElement("button");
    topItem.type = "button";
    topItem.className = "block-picker-item";
    topItem.innerHTML = '<span class="item-icon">⤒</span><span>1. Ganz an den Anfang</span>';
    topItem.addEventListener("click", function (e) {
      e.stopPropagation();
      closeMoveToDialog();
      moveSelectedBlocksTo(0);
    });
    list.appendChild(topItem);

    const unselected = (state.article.blocks || [])
      .map(function (b, idx) {
        return { block: b, origIndex: idx };
      })
      .filter(function (item) {
        return !state.selectedBlockIds.has(item.block.id);
      });

    unselected.forEach(function (item, uIdx) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "block-picker-item";
      const label = (item.origIndex + 1) + ". " + getBlockTypeLabel(item.block.type);
      btn.innerHTML = '<span class="item-icon">↳</span><span>Nach: ' + E.escapeHtml(label) + "</span>";
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        closeMoveToDialog();
        moveSelectedBlocksTo(uIdx + 1);
      });
      list.appendChild(btn);
    });

    const endItem = document.createElement("button");
    endItem.type = "button";
    endItem.className = "block-picker-item";
    endItem.innerHTML = '<span class="item-icon">⤓</span><span>Ganz ans Ende</span>';
    endItem.addEventListener("click", function (e) {
      e.stopPropagation();
      closeMoveToDialog();
      moveSelectedBlocksTo(unselected.length);
    });
    list.appendChild(endItem);

    dialog.appendChild(list);
    document.body.appendChild(dialog);

    const rect = anchorBtn.getBoundingClientRect();
    dialog.style.left = Math.max(10, rect.left - 40) + "px";
    dialog.style.top = Math.max(10, rect.top - dialog.offsetHeight - 8) + "px";

    attachOutsideDismiss(dialog, anchorBtn, closeMoveToDialog, function (fn) { activeMoveDialogDocClick = fn; });
  }

  function updateFloatingSelectionBar() {
    const bar = ensureFloatingSelectionBar();
    const count = state.selectedBlockIds.size;
    if (count === 0) {
      bar.classList.remove("is-visible");
      bar.innerHTML = "";
      return;
    }

    bar.classList.add("is-visible");
    bar.innerHTML = "";

    const badge = document.createElement("span");
    badge.className = "floating-bar-badge";
    badge.textContent = count + (count === 1 ? " Block ausgewählt" : " Blöcke ausgewählt");
    bar.appendChild(badge);

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "floating-bar-btn";
    upBtn.title = "Ausgewählte Blöcke gemeinsam nach oben verschieben";
    upBtn.innerHTML = "↑ Nach oben";
    upBtn.addEventListener("click", function () {
      moveSelectedBlocks("up");
    });
    bar.appendChild(upBtn);

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "floating-bar-btn";
    downBtn.title = "Ausgewählte Blöcke gemeinsam nach unten verschieben";
    downBtn.innerHTML = "↓ Nach unten";
    downBtn.addEventListener("click", function () {
      moveSelectedBlocks("down");
    });
    bar.appendChild(downBtn);

    const d1 = document.createElement("div");
    d1.className = "floating-bar-divider";
    bar.appendChild(d1);

    const moveToBtn = document.createElement("button");
    moveToBtn.type = "button";
    moveToBtn.className = "floating-bar-btn";
    moveToBtn.title = "Ausgewählte Blöcke an eine bestimmte Position verschieben";
    moveToBtn.innerHTML = "➔ Verschieben nach…";
    moveToBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      openMoveToDialog(moveToBtn);
    });
    bar.appendChild(moveToBtn);

    const dupBtn = document.createElement("button");
    dupBtn.type = "button";
    dupBtn.className = "floating-bar-btn";
    dupBtn.title = "Ausgewählte Blöcke duplizieren";
    dupBtn.innerHTML = "⧉ Duplizieren";
    dupBtn.addEventListener("click", function () {
      duplicateSelectedBlocks();
    });
    bar.appendChild(dupBtn);

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "floating-bar-btn danger";
    delBtn.title = "Ausgewählte Blöcke löschen";
    delBtn.innerHTML = "🗑 Löschen";
    delBtn.addEventListener("click", function () {
      deleteSelectedBlocks();
    });
    bar.appendChild(delBtn);

    const d2 = document.createElement("div");
    d2.className = "floating-bar-divider";
    bar.appendChild(d2);

    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "floating-bar-btn";
    clearBtn.title = "Auswahl aufheben (Esc)";
    clearBtn.innerHTML = "✕";
    clearBtn.addEventListener("click", function () {
      clearBlockSelection();
    });
    bar.appendChild(clearBtn);
  }

  // ==========================================================================
  // Autoscroll-Engine für Drag-and-Drop
  // ==========================================================================

  let autoScrollRaf = null;
  let autoScrollVelocity = 0;
  let autoScrollActive = false;
  let activeAutoScroller = null;

  function startEditorAutoScroll(container) {
    if (!container) return;
    autoScrollActive = true;
    autoScrollVelocity = 0;

    function onPointerMove(e) {
      if (!autoScrollActive) return;
      const rect = container.getBoundingClientRect();
      const threshold = 110;
      const maxSpeed = 30;

      if (e.clientY < rect.top + threshold && e.clientY > rect.top - 60) {
        const intensity = Math.min(1, Math.max(0.15, (rect.top + threshold - e.clientY) / threshold));
        autoScrollVelocity = -Math.round(intensity * maxSpeed);
      } else if (e.clientY > rect.bottom - threshold && e.clientY < rect.bottom + 60) {
        const intensity = Math.min(1, Math.max(0.15, (e.clientY - (rect.bottom - threshold)) / threshold));
        autoScrollVelocity = Math.round(intensity * maxSpeed);
      } else {
        autoScrollVelocity = 0;
      }

      if (autoScrollVelocity !== 0 && !autoScrollRaf) {
        loopScroll();
      }
    }

    function loopScroll() {
      if (!autoScrollActive || autoScrollVelocity === 0) {
        autoScrollRaf = null;
        return;
      }
      container.scrollTop += autoScrollVelocity;
      autoScrollRaf = requestAnimationFrame(loopScroll);
    }

    function onPointerUp() {
      stopEditorAutoScroll();
    }

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerup", onPointerUp, { once: true });
    window.addEventListener("dragend", onPointerUp, { once: true });

    activeAutoScroller = {
      cleanup: function () {
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("pointerup", onPointerUp);
        window.removeEventListener("dragend", onPointerUp);
      },
    };
  }

  function stopEditorAutoScroll() {
    autoScrollActive = false;
    autoScrollVelocity = 0;
    if (autoScrollRaf) {
      cancelAnimationFrame(autoScrollRaf);
      autoScrollRaf = null;
    }
    if (activeAutoScroller) {
      activeAutoScroller.cleanup();
      activeAutoScroller = null;
    }
  }

  // ==========================================================================
  // Block-Canvas Rendering & SortableJS
  // ==========================================================================

  function renderBlocksCanvas() {
    const canvas = document.getElementById("lukb-blocks-canvas");
    if (!canvas || !state.article) return;

    canvas.innerHTML = "";
    const blocks = state.article.blocks || [];

    const currentBlockIds = new Set(blocks.map(function (b) { return b.id; }));
    Array.from(state.selectedBlockIds).forEach(function (id) {
      if (!currentBlockIds.has(id)) state.selectedBlockIds.delete(id);
    });

    if (blocks.length === 0) {
      const emptyState = document.createElement("div");
      emptyState.style.padding = "40px 20px";
      emptyState.style.textAlign = "center";
      emptyState.style.border = "2px dashed var(--lukb-border)";
      emptyState.style.borderRadius = "8px";
      emptyState.style.background = "#FAFCFE";
      emptyState.innerHTML = '<p style="color: var(--lukb-navy); font-weight: 600; margin-bottom: 12px;">Noch keine Inhaltsblöcke vorhanden</p>';
      const addFirstBtn = document.createElement("button");
      addFirstBtn.type = "button";
      addFirstBtn.className = "btn-lukb btn-lukb-primary btn-lukb-sm";
      addFirstBtn.textContent = "+ Ersten Block einfügen";
      addFirstBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        openBlockPickerPopup(addFirstBtn, 0);
      });
      emptyState.appendChild(addFirstBtn);
      canvas.appendChild(emptyState);
      updateFloatingSelectionBar();
      return;
    }

    const frag = document.createDocumentFragment();
    let insideBox = false;
    blocks.forEach(function (blk, index) {
      if (blk.type === "box_start") {
        insideBox = true;
      }
      const card = buildBlockCardElement(blk, index, insideBox);
      frag.appendChild(card);
      if (blk.type === "box_end") {
        insideBox = false;
      }
    });
    canvas.appendChild(frag);

    initSortable(canvas);
    updateFloatingSelectionBar();
  }

  function initSortable(canvas) {
    if (state.sortableInstance) {
      state.sortableInstance.destroy();
      state.sortableInstance = null;
    }
    if (typeof window.Sortable === "undefined") return;

    const editorPane = document.querySelector(".cms-editor-pane") || canvas.parentElement;

    state.sortableInstance = window.Sortable.create(canvas, {
      handle: ".block-drag-handle",
      draggable: ".cms-block-card",
      animation: 180,
      ghostClass: "sortable-ghost",
      dragClass: "sortable-drag",
      selectedClass: "sortable-selected",
      multiDrag: true,
      scroll: editorPane,
      scrollSensitivity: 120,
      scrollSpeed: 24,
      bubbleScroll: true,
      onStart: function () {
        canvas.classList.add("is-sortable-dragging");
        closeBlockPickerPopup();
        startEditorAutoScroll(editorPane);
      },
      onEnd: function () {
        canvas.classList.remove("is-sortable-dragging");
        stopEditorAutoScroll();
        syncBlockOrderFromDOM(canvas);
        markDirty();
        updateFloatingSelectionBar();
      },
    });
  }

  function updateCardAnchorBadges(card, blk, anchorCountMap) {
    const headerLeft = card.querySelector(".block-header-left");
    if (!headerLeft) return;

    // 1. Anchor-Pill auf dem Randelement selbst
    let anchorPill = headerLeft.querySelector(".block-anchor-pill");
    const isMarginType = (blk.type === "figure" || blk.type === "db_chart" || blk.type === "custom_chart" || blk.type === "table") && (blk.layout || "column") === "column";

    if (isMarginType && blk.anchor_to) {
      if (!anchorPill) {
        anchorPill = document.createElement("span");
        anchorPill.className = "block-anchor-pill";
        anchorPill.title = "Dieses Element ist an einen Textabsatz verankert. Klicken, um zum Ziel zu springen.";
        anchorPill.textContent = "⚓ Verankert";

        const getAnchorTargetCard = function () {
          const curBlk = state.article ? state.article.blocks.find(function (b) { return b.id === card.dataset.blockId; }) : blk;
          const targetId = curBlk ? curBlk.anchor_to : blk.anchor_to;
          return targetId ? document.querySelector('[data-block-id="' + targetId + '"]') : null;
        };
        anchorPill.addEventListener("mouseenter", function () {
          const targetCard = getAnchorTargetCard();
          if (targetCard) targetCard.classList.add("anchor-target-highlight");
        });
        anchorPill.addEventListener("mouseleave", function () {
          const targetCard = getAnchorTargetCard();
          if (targetCard) targetCard.classList.remove("anchor-target-highlight");
        });
        anchorPill.addEventListener("click", function (e) {
          e.stopPropagation();
          const targetCard = getAnchorTargetCard();
          if (targetCard) {
            targetCard.scrollIntoView({ behavior: "smooth", block: "center" });
            targetCard.classList.add("anchor-target-highlight");
            setTimeout(function () { targetCard.classList.remove("anchor-target-highlight"); }, 1600);
          }
        });
        headerLeft.appendChild(anchorPill);
      }
    } else {
      if (anchorPill) anchorPill.remove();
    }

    // 2. Target-Pill auf dem Zielabsatz
    let targetPill = headerLeft.querySelector(".block-anchor-target-pill");
    let attachedMarginCount = 0;
    if (anchorCountMap instanceof Map) {
      attachedMarginCount = anchorCountMap.get(blk.id) || 0;
    } else {
      const blocksList = (state.article && state.article.blocks) ? state.article.blocks : [];
      attachedMarginCount = blocksList.filter(function (o) {
        return o && o.anchor_to === blk.id && (o.type === "figure" || o.type === "db_chart" || o.type === "custom_chart" || o.type === "table") && (o.layout || "column") === "column";
      }).length;
    }

    if (attachedMarginCount > 0) {
      if (!targetPill) {
        targetPill = document.createElement("span");
        targetPill.className = "block-anchor-target-pill";
        headerLeft.appendChild(targetPill);
      }
      targetPill.title = attachedMarginCount + " Randelement(e) an diesen Absatz verankert.";
      targetPill.textContent = "⚓ " + attachedMarginCount + " verankert";
    } else {
      if (targetPill) targetPill.remove();
    }
  }

  function reindexCanvasCards(canvas) {
    if (!canvas) canvas = document.getElementById("lukb-blocks-canvas");
    if (!canvas || !state.article || !state.article.blocks) return;

    const anchorCountMap = new Map();
    state.article.blocks.forEach(function (o) {
      if (o && o.anchor_to && (o.type === "figure" || o.type === "db_chart" || o.type === "custom_chart" || o.type === "table") && (o.layout || "column") === "column") {
        anchorCountMap.set(o.anchor_to, (anchorCountMap.get(o.anchor_to) || 0) + 1);
      }
    });

    const cardElements = Array.from(canvas.querySelectorAll(":scope > .cms-block-card"));
    const total = cardElements.length;

    let insideBox = false;
    cardElements.forEach(function (card, index) {
      const blk = state.article.blocks[index];
      if (!blk) return;
      card.dataset.blockIndex = index;

      const isMarker = blk.type === "box_start" || blk.type === "box_end";
      if (blk.type === "box_start") insideBox = true;

      if (insideBox && !isMarker) {
        card.classList.add("block-inside-textbox");
      } else {
        card.classList.remove("block-inside-textbox");
      }

      // Nummerierung im Badge anpassen
      const pill = card.querySelector(".block-type-pill");
      if (pill) {
        pill.textContent = (index + 1) + ". " + getBlockTypeLabel(blk.type);
      }

      // Up/Down Buttons
      const upBtn = card.querySelector(".btn-block-up");
      if (upBtn) upBtn.disabled = (index === 0);
      const downBtn = card.querySelector(".btn-block-down");
      if (downBtn) downBtn.disabled = (index === total - 1);

      // Top-Inserter: Nur an erster Karte führen
      const existingTopInserter = card.querySelector(":scope > .top-inserter");
      if (index === 0) {
        if (!existingTopInserter) {
          card.insertBefore(createInlineInserterElement(0, true), card.firstChild);
        }
      } else {
        if (existingTopInserter) {
          existingTopInserter.remove();
        }
      }

      // Bottom-Inserter Datensatz anpassen
      const bottomInserter = card.querySelector(":scope > .bottom-inserter");
      if (bottomInserter) {
        bottomInserter.dataset.targetIndex = index + 1;
      }

      // Verankerungs-Badges aktualisieren
      updateCardAnchorBadges(card, blk, anchorCountMap);

      if (blk.type === "box_end") insideBox = false;
    });
  }

  function reorderCanvasCardsFromState(canvas) {
    if (!canvas) canvas = document.getElementById("lukb-blocks-canvas");
    if (!canvas || !state.article || !state.article.blocks) return;
    const cardMap = new Map();
    canvas.querySelectorAll(":scope > .cms-block-card").forEach(function (card) {
      if (card.dataset.blockId) cardMap.set(card.dataset.blockId, card);
    });
    const frag = document.createDocumentFragment();
    state.article.blocks.forEach(function (blk) {
      const card = cardMap.get(blk.id);
      if (card) frag.appendChild(card);
    });
    canvas.appendChild(frag);
    reindexCanvasCards(canvas);
  }

  function syncBlockOrderFromDOM(canvas) {
    if (!canvas) canvas = document.getElementById("lukb-blocks-canvas");
    if (!canvas || !state.article || !state.article.blocks) return;

    const cardElements = Array.from(canvas.querySelectorAll(":scope > .cms-block-card"));
    const newOrderIds = cardElements.map(function (el) { return el.dataset.blockId; });
    const blockMap = new Map();
    state.article.blocks.forEach(function (b) { blockMap.set(b.id, b); });

    state.article.blocks = newOrderIds.map(function (id) { return blockMap.get(id); }).filter(Boolean);

    reindexCanvasCards(canvas);
  }

  function buildBlockCardElement(blk, index, insideBox) {
    const isMarker = blk.type === "box_start" || blk.type === "box_end";
    const isSelected = state.selectedBlockIds.has(blk.id);
    const card = document.createElement("div");
    card.className =
      "cms-block-card block-type-" +
      blk.type +
      (insideBox && !isMarker ? " block-inside-textbox" : "") +
      (isMarker ? " block-textbox-marker" : "") +
      (isSelected ? " is-selected sortable-selected" : "");
    card.dataset.blockId = blk.id;
    card.dataset.blockIndex = index;

    card.addEventListener("click", function (e) {
      if (e.ctrlKey || e.metaKey) {
        const tag = e.target.tagName.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "button" || tag === "select" || e.target.isContentEditable) {
          return;
        }
        e.preventDefault();
        e.stopPropagation();
        toggleBlockSelection(blk.id, e.shiftKey, getCardCurrentIndex(card));
      }
    });

    if (index === 0) {
      card.appendChild(createInlineInserterElement(0, true));
    }

    const header = document.createElement("div");
    header.className = "block-header-bar";

    const headerLeft = document.createElement("div");
    headerLeft.className = "block-header-left";

    const selectCb = document.createElement("input");
    selectCb.type = "checkbox";
    selectCb.className = "block-select-checkbox";
    selectCb.title = "Block markieren für Sammelaktionen (oder Ctrl+Klick)";
    selectCb.checked = isSelected;
    selectCb.addEventListener("click", function (e) {
      e.stopPropagation();
      toggleBlockSelection(blk.id, e.shiftKey, getCardCurrentIndex(card));
    });

    const dragHandle = document.createElement("span");
    dragHandle.className = "block-drag-handle";
    dragHandle.title = "Ziehen zum Umsortieren (Drag & Drop)";
    dragHandle.textContent = "⋮⋮";

    const typePill = document.createElement("span");
    typePill.className = "block-type-pill";
    typePill.textContent = (index + 1) + ". " + getBlockTypeLabel(blk.type);

    headerLeft.appendChild(selectCb);
    headerLeft.appendChild(dragHandle);
    headerLeft.appendChild(typePill);

    const peerBadge = document.createElement("span");
    peerBadge.className = "block-peer-badge";
    peerBadge.style.display = "none";
    headerLeft.appendChild(peerBadge);

    const headerActions = document.createElement("div");
    headerActions.className = "block-header-actions";

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "btn-icon-only btn-block-up";
    upBtn.title = "Block nach oben schieben";
    upBtn.textContent = "↑";
    upBtn.disabled = index === 0;
    upBtn.addEventListener("click", function () {
      const currentIdx = getCardCurrentIndex(card);
      if (currentIdx <= 0) return;
      const targetIdx = currentIdx - 1;
      const tmp = state.article.blocks[targetIdx];
      state.article.blocks[targetIdx] = state.article.blocks[currentIdx];
      state.article.blocks[currentIdx] = tmp;

      const canvas = document.getElementById("lukb-blocks-canvas");
      const prevCard = card.previousElementSibling;
      if (prevCard && canvas) {
        canvas.insertBefore(card, prevCard);
      }
      reindexCanvasCards(canvas);
      markDirty();
    });

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "btn-icon-only btn-block-down";
    downBtn.title = "Block nach unten schieben";
    downBtn.textContent = "↓";
    downBtn.disabled = index >= (state.article && state.article.blocks ? state.article.blocks.length - 1 : 0);
    downBtn.addEventListener("click", function () {
      const currentIdx = getCardCurrentIndex(card);
      if (currentIdx < 0 || currentIdx >= state.article.blocks.length - 1) return;
      const targetIdx = currentIdx + 1;
      const tmp = state.article.blocks[targetIdx];
      state.article.blocks[targetIdx] = state.article.blocks[currentIdx];
      state.article.blocks[currentIdx] = tmp;

      const canvas = document.getElementById("lukb-blocks-canvas");
      const nextCard = card.nextElementSibling;
      if (nextCard && canvas) {
        canvas.insertBefore(nextCard, card);
      }
      reindexCanvasCards(canvas);
      markDirty();
    });

    const insertBelowBtn = document.createElement("button");
    insertBelowBtn.type = "button";
    insertBelowBtn.className = "btn-icon-only";
    insertBelowBtn.title = "Neuen Block darunter einfügen (+)";
    insertBelowBtn.textContent = "+";
    insertBelowBtn.style.fontWeight = "bold";
    insertBelowBtn.style.color = "var(--lukb-navy)";
    insertBelowBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      const currentIdx = getCardCurrentIndex(card);
      openBlockPickerPopup(insertBelowBtn, currentIdx !== -1 ? currentIdx + 1 : 0);
    });

    const dupBtn = document.createElement("button");
    dupBtn.type = "button";
    dupBtn.className = "btn-icon-only";
    dupBtn.title = "Block duplizieren";
    dupBtn.textContent = "⧉";
    dupBtn.addEventListener("click", function () {
      const currentIdx = getCardCurrentIndex(card);
      if (currentIdx === -1) return;
      const blkToDup = state.article.blocks[currentIdx];
      const clone = deepClone(blkToDup);
      clone.id = uid("blk");
      state.article.blocks.splice(currentIdx + 1, 0, clone);

      const canvas = document.getElementById("lukb-blocks-canvas");
      const newCard = buildBlockCardElement(clone, currentIdx + 1, false);
      if (card.nextElementSibling) {
        canvas.insertBefore(newCard, card.nextElementSibling);
      } else {
        canvas.appendChild(newCard);
      }

      reindexCanvasCards(canvas);
      markDirty();

      newCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      newCard.classList.add("sortable-ghost");
      setTimeout(function () {
        newCard.classList.remove("sortable-ghost");
      }, 500);
    });

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "btn-icon-only danger";
    delBtn.title = "Block löschen";
    delBtn.textContent = "✕";
    delBtn.addEventListener("click", function () {
      const currentIdx = getCardCurrentIndex(card);
      if (currentIdx === -1) return;
      const blkToDelete = state.article.blocks[currentIdx];
      const deletedBlock = deepClone(blkToDelete);
      const deletedIndex = currentIdx;
      const typeLabel = getBlockTypeLabel(blkToDelete.type);

      state.selectedBlockIds.delete(blkToDelete.id);
      state.article.blocks.splice(currentIdx, 1);
      state.article.blocks.forEach(function (b) {
        if (b && b.anchor_to === blkToDelete.id) {
          b.anchor_to = null;
        }
      });

      card.remove();

      const canvas = document.getElementById("lukb-blocks-canvas");
      if (state.article.blocks.length === 0) {
        renderBlocksCanvas();
      } else {
        reindexCanvasCards(canvas);
      }

      markDirty();
      updateFloatingSelectionBar();

      pushUndo({
        type: "delete_blocks",
        description: `Block «${typeLabel}» gelöscht`,
        items: [{ index: deletedIndex, block: deletedBlock }],
      });
    });

    headerActions.appendChild(upBtn);
    headerActions.appendChild(downBtn);
    headerActions.appendChild(insertBelowBtn);
    headerActions.appendChild(dupBtn);
    headerActions.appendChild(delBtn);

    header.appendChild(headerLeft);
    header.appendChild(headerActions);
    card.appendChild(header);

    // Verankerungs-Badges initialisieren
    updateCardAnchorBadges(card, blk);

    if (isMarker) {
      card.appendChild(createInlineInserterElement(index + 1, false));
      return card;
    }

    // Body Content per Block Type
    const body = document.createElement("div");
    body.className = "block-body";

    const BLOCK_BODY_BUILDERS = {
      heading: buildHeadingBlockBody,
      richtext: buildRichTextBlockBody,
      callout: buildCalloutBlockBody,
      figure: buildFigureBlockBody,
      db_chart: buildDbChartBlockBody,
      custom_chart: buildCustomChartBlockBody,
      table: buildTableBlockBody,
      spacer: buildSpacerBlockBody,
      colbreak: buildColbreakBlockBody,
      quote: buildQuoteBlockBody,
      divider: buildDividerBlockBody,
      footnotes: buildFootnotesBlockBody,
      glossary: buildGlossaryBlockBody,
      publications: buildPublicationsBlockBody,
    };
    const bodyBuilder = BLOCK_BODY_BUILDERS[blk.type];
    if (bodyBuilder) bodyBuilder(body, blk);

    card.appendChild(body);
    card.appendChild(createInlineInserterElement(index + 1, false));
    return card;
  }

  // ==========================================================================
  // Spezifische Block-Editoren (Zitate, Divider, Spacer, Colbreak -> richtext.js)
  // ==========================================================================

  function buildFootnotesBlockBody(container, blk) {
    if (!blk.title) blk.title = "Anmerkungen & Quellen";
    if (!Array.isArray(blk.items)) blk.items = [];

    const topGrid = document.createElement("div");
    topGrid.style.display = "grid";
    topGrid.style.gridTemplateColumns = "1fr 180px";
    topGrid.style.gap = "10px";
    topGrid.style.marginBottom = "8px";

    const titleWrap = document.createElement("div");
    const titleLbl = document.createElement("label");
    titleLbl.className = "field-label";
    titleLbl.textContent = "Titel des Fussnoten- / Endnotenkastens";
    const titleInp = document.createElement("input");
    titleInp.type = "text";
    titleInp.className = "cms-input font-medium";
    titleInp.value = blk.title || "";
    titleInp.addEventListener("input", function () {
      blk.title = titleInp.value;
      markDirty();
    });
    titleWrap.appendChild(titleLbl);
    titleWrap.appendChild(titleInp);

    const layoutWrap = document.createElement("div");
    const layoutLbl = document.createElement("label");
    layoutLbl.className = "field-label";
    layoutLbl.textContent = "Satz-Breite im PDF";
    const layoutSel = E.createSimpleLayoutSelect(blk);
    layoutWrap.appendChild(layoutLbl);
    layoutWrap.appendChild(layoutSel);

    topGrid.appendChild(titleWrap);
    topGrid.appendChild(layoutWrap);
    container.appendChild(topGrid);

    const itemsList = document.createElement("div");
    itemsList.className = "footnotes-items-list";

    function renderItems() {
      itemsList.innerHTML = "";
      blk.items.forEach(function (item, idx) {
        const row = document.createElement("div");
        row.className = "footnote-row-item";

        const numInp = document.createElement("input");
        numInp.type = "text";
        numInp.className = "cms-input font-medium";
        numInp.style.textAlign = "center";
        numInp.placeholder = String(idx + 1);
        numInp.value = item.num || String(idx + 1);
        numInp.addEventListener("input", function () {
          item.num = numInp.value;
          markDirty();
        });

        const txtInp = document.createElement("input");
        txtInp.type = "text";
        txtInp.className = "cms-input";
        txtInp.placeholder = "Quellenangabe, Datenstand oder methodischer Hinweis …";
        txtInp.value = item.text || "";
        txtInp.addEventListener("input", function () {
          item.text = txtInp.value;
          markDirty();
        });

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-icon-only danger";
        delBtn.title = "Eintrag entfernen";
        delBtn.textContent = "✕";
        delBtn.addEventListener("click", function () {
          blk.items.splice(idx, 1);
          renderItems();
          markDirty();
        });

        row.appendChild(numInp);
        row.appendChild(txtInp);
        row.appendChild(delBtn);
        itemsList.appendChild(row);
      });
    }

    renderItems();
    container.appendChild(itemsList);

    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addBtn.style.marginTop = "8px";
    addBtn.textContent = "+ Fussnoten-Eintrag hinzufügen";
    addBtn.addEventListener("click", function () {
      const nextNum = String(blk.items.length + 1);
      blk.items.push({ num: nextNum, text: "" });
      renderItems();
      markDirty();
    });
    container.appendChild(addBtn);
  }

  function buildHeadingBlockBody(container, blk) {
    if (!blk.level) blk.level = 2; // Default ist H2-Titel

    const row = document.createElement("div");
    row.style.display = "grid";
    row.style.gridTemplateColumns = "155px 1fr";
    row.style.gap = "10px";
    row.style.alignItems = "center";

    const select = document.createElement("select");
    select.className = "cms-select font-medium";
    [
      { val: 2, label: "H2 — Zwischentitel (Default)" },
      { val: 1, label: "H1 — Haupttitel (gross + Linie)" },
      { val: 3, label: "H3 — Untertitel" },
    ].forEach(function (opt) {
      const o = document.createElement("option");
      o.value = opt.val;
      o.textContent = opt.label;
      if (Number(blk.level || 2) === opt.val) o.selected = true;
      select.appendChild(o);
    });

    const inputWrap = document.createElement("div");
    inputWrap.style.display = "flex";
    inputWrap.style.flexDirection = "column";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "cms-input font-medium";
    input.placeholder = "Überschrift eingeben …";
    input.value = blk.text || "";

    const h1Rule = document.createElement("div");
    h1Rule.style.height = "2px";
    h1Rule.style.backgroundColor = "#002855";
    h1Rule.style.marginTop = "3px";
    h1Rule.style.marginBottom = "6px";
    h1Rule.style.width = "100%";
    h1Rule.title = "Horizontale Linie über Spaltenbreite";

    function updateHeadingStyles() {
      const lvl = Number(blk.level || 2);
      if (lvl === 1) {
        input.style.fontSize = "17.5px"; // +2pt grösser
        input.style.color = "#002855";
        input.style.fontWeight = "600";
        input.style.borderBottomLeftRadius = "";
        input.style.borderBottomRightRadius = "";
        h1Rule.style.display = "block";
      } else if (lvl === 2) {
        input.style.fontSize = "15.5px";
        input.style.color = "#005A9C";
        input.style.fontWeight = "500";
        input.style.borderBottomLeftRadius = "";
        input.style.borderBottomRightRadius = "";
        h1Rule.style.display = "none";
      } else {
        input.style.fontSize = "14px";
        input.style.color = "#1A2433";
        input.style.fontWeight = "500";
        input.style.borderBottomLeftRadius = "";
        input.style.borderBottomRightRadius = "";
        h1Rule.style.display = "none";
      }
    }

    updateHeadingStyles();

    select.addEventListener("change", function () {
      blk.level = parseInt(select.value, 10) || 2;
      updateHeadingStyles();
      markDirty();
    });

    input.addEventListener("input", function () {
      blk.text = input.value;
      markDirty();
    });

    inputWrap.appendChild(input);
    inputWrap.appendChild(h1Rule);

    row.appendChild(select);
    row.appendChild(inputWrap);
    container.appendChild(row);
  }

  function buildPublicationsBlockBody(container, blk) {
    if (!Array.isArray(blk.items)) {
      blk.items = [];
    }

    // Zeile 1: Titel & Satz-Breite
    const topGrid = document.createElement("div");
    topGrid.style.display = "grid";
    topGrid.style.gridTemplateColumns = "1fr 190px";
    topGrid.style.gap = "10px";
    topGrid.style.marginBottom = "10px";

    const titleWrap = document.createElement("div");
    const titleLbl = document.createElement("label");
    titleLbl.className = "field-label";
    titleLbl.textContent = "Block-Titel";
    const titleInp = document.createElement("input");
    titleInp.type = "text";
    titleInp.className = "cms-input font-medium";
    titleInp.value = blk.title || "Weitere Publikationen";
    titleInp.addEventListener("input", function () {
      blk.title = titleInp.value;
      markDirty();
    });
    titleWrap.appendChild(titleLbl);
    titleWrap.appendChild(titleInp);

    const layoutWrap = document.createElement("div");
    const layoutLbl = document.createElement("label");
    layoutLbl.className = "field-label";
    layoutLbl.textContent = "Satz-Breite im PDF";
    const layoutSel = E.createSimpleLayoutSelect(blk);
    layoutWrap.appendChild(layoutLbl);
    layoutWrap.appendChild(layoutSel);

    topGrid.appendChild(titleWrap);
    topGrid.appendChild(layoutWrap);
    container.appendChild(topGrid);

    // Publikationsliste
    const listWrap = document.createElement("div");
    listWrap.className = "publications-editor-container";

    const listHeader = document.createElement("div");
    listHeader.style.display = "flex";
    listHeader.style.justifyContent = "space-between";
    listHeader.style.alignItems = "center";
    listHeader.style.marginBottom = "8px";

    const listLbl = document.createElement("label");
    listLbl.className = "field-label";
    listLbl.style.margin = "0";
    listLbl.textContent = "Ausgewählte Publikationen (Checkbox zum Ein-/Ausblenden):";

    const refreshBtn = document.createElement("button");
    refreshBtn.type = "button";
    refreshBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    refreshBtn.title = "Lädt die 5 neuesten Publikationen aus dem System";
    refreshBtn.textContent = "🔄 Neueste 5 laden";
    refreshBtn.addEventListener("click", function () {
      blk.items = E.getLatestPublishedItemsForBlock(5);
      renderItems();
      markDirty();
    });

    listHeader.appendChild(listLbl);
    listHeader.appendChild(refreshBtn);
    listWrap.appendChild(listHeader);

    const itemsContainer = document.createElement("div");
    itemsContainer.className = "publications-items-list";

    function renderItems() {
      itemsContainer.innerHTML = "";
      if (!blk.items || blk.items.length === 0) {
        const emptyMsg = document.createElement("div");
        emptyMsg.style.fontSize = "12px";
        emptyMsg.style.color = "#64748B";
        emptyMsg.style.padding = "10px";
        emptyMsg.style.textAlign = "center";
        emptyMsg.style.background = "#F8FAFC";
        emptyMsg.style.borderRadius = "4px";
        emptyMsg.textContent = "Keine Publikationen ausgewählt. Wählen Sie unten eine Publikation aus.";
        itemsContainer.appendChild(emptyMsg);
        updateDropdown();
        return;
      }

      blk.items.forEach(function (item, idx) {
        const row = document.createElement("div");
        row.className = "publication-editor-row";
        if (item.enabled === false) {
          row.classList.add("disabled-pub");
        }

        const check = document.createElement("input");
        check.type = "checkbox";
        check.checked = item.enabled !== false;
        check.title = check.checked ? "Aktiv (wird im Dokument angezeigt)" : "Deaktiviert (abgewählt)";
        check.addEventListener("change", function () {
          item.enabled = check.checked;
          if (item.enabled) {
            row.classList.remove("disabled-pub");
          } else {
            row.classList.add("disabled-pub");
          }
          markDirty();
        });

        const content = document.createElement("div");
        content.className = "pub-content-col";

        const titleInput = document.createElement("input");
        titleInput.type = "text";
        titleInput.className = "cms-input font-medium";
        titleInput.style.fontSize = "13px";
        titleInput.style.padding = "4px 8px";
        titleInput.value = item.title || "";
        titleInput.placeholder = "Titel der Publikation";
        titleInput.addEventListener("input", function () {
          item.title = titleInput.value;
          markDirty();
        });

        const metaRow = document.createElement("div");
        metaRow.style.display = "grid";
        metaRow.style.gridTemplateColumns = "130px 1fr auto";
        metaRow.style.gap = "8px";
        metaRow.style.alignItems = "center";
        metaRow.style.marginTop = "4px";

        const dateInput = document.createElement("input");
        dateInput.type = "text";
        dateInput.className = "cms-input";
        dateInput.style.fontSize = "11.5px";
        dateInput.style.padding = "3px 6px";
        dateInput.placeholder = "Datum (JJJJ-MM-TT)";
        dateInput.title = "Publikationsdatum (Format: 9. November 2026)";
        dateInput.value = item.date || "";
        dateInput.addEventListener("input", function () {
          item.date = dateInput.value;
          markDirty();
        });

        const urlInput = document.createElement("input");
        urlInput.type = "url";
        urlInput.className = "cms-input";
        urlInput.style.fontSize = "11.5px";
        urlInput.style.padding = "3px 6px";
        urlInput.placeholder = "URL / Querverweis zum Dokument (optional)";
        urlInput.title = "Optionale URL: Öffnet in neuem Tab und zeigt im Layout ein kleines Symbol an";
        urlInput.value = item.url || "";
        urlInput.addEventListener("input", function () {
          item.url = urlInput.value.trim();
          testLinkBtn.style.display = item.url ? "inline-flex" : "none";
          if (item.url) testLinkBtn.href = item.url;
          markDirty();
        });

        const testLinkBtn = document.createElement("a");
        testLinkBtn.href = item.url || "#";
        testLinkBtn.target = "_blank";
        testLinkBtn.rel = "noopener noreferrer";
        testLinkBtn.className = "btn-icon-only";
        testLinkBtn.title = "URL in neuem Tab öffnen";
        testLinkBtn.style.textDecoration = "none";
        testLinkBtn.style.fontSize = "13px";
        testLinkBtn.style.fontWeight = "bold";
        testLinkBtn.style.color = "var(--lukb-blue)";
        testLinkBtn.style.display = item.url ? "inline-flex" : "none";
        testLinkBtn.style.alignItems = "center";
        testLinkBtn.style.justifyContent = "center";
        testLinkBtn.innerHTML = "↗";

        metaRow.appendChild(dateInput);
        metaRow.appendChild(urlInput);
        metaRow.appendChild(testLinkBtn);

        content.appendChild(titleInput);
        content.appendChild(metaRow);

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-icon-only";
        delBtn.style.color = "#B91C1C";
        delBtn.title = "Publikation aus Liste entfernen";
        delBtn.innerHTML = "🗑️";
        delBtn.addEventListener("click", function () {
          blk.items.splice(idx, 1);
          renderItems();
          markDirty();
        });

        row.appendChild(check);
        row.appendChild(content);
        row.appendChild(delBtn);
        itemsContainer.appendChild(row);
      });

      updateDropdown();
    }

    listWrap.appendChild(itemsContainer);

    // Hinzufügen-Sektion
    const addSection = document.createElement("div");
    addSection.className = "publications-add-section";
    addSection.style.marginTop = "10px";
    addSection.style.display = "flex";
    addSection.style.gap = "8px";
    addSection.style.alignItems = "center";

    const select = document.createElement("select");
    select.className = "cms-select";
    select.style.flex = "1";
    select.style.fontSize = "12.5px";

    function updateDropdown() {
      select.innerHTML = "";
      const currentSelectedIds = new Set(
        (blk.items || []).map(function (it) { return it.article_id; }).filter(Boolean)
      );
      const currentId = state.article ? state.article.id : "";
      const available = (state.allArticles || []).filter(function (a) {
        return a.id !== currentId && a.status === "published" && !currentSelectedIds.has(a.id);
      });

      if (available.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "Keine weiteren publizierten Artikel im System verfügbar";
        select.appendChild(opt);
        addBtn.disabled = true;
        return;
      }

      addBtn.disabled = false;
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "— Publizierte Publikation auswählen —";
      select.appendChild(placeholder);

      available.forEach(function (a) {
        const opt = document.createElement("option");
        opt.value = a.id;
        const d = a.publication_date || (a.updated_at ? a.updated_at.split("T")[0] : "");
        opt.textContent = (d ? "[" + d + "] " : "") + (a.title || "Ohne Titel");
        select.appendChild(opt);
      });
    }

    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addBtn.textContent = "+ Hinzufügen";
    addBtn.addEventListener("click", function () {
      const artId = select.value;
      if (!artId) return;
      const art = (state.allArticles || []).find(function (a) { return a.id === artId; });
      if (art) {
        blk.items.push({
          article_id: art.id,
          title: art.title || "Ohne Titel",
          subtitle: art.subtitle || "",
          date: art.publication_date || (art.updated_at ? art.updated_at.split("T")[0] : ""),
          category: art.category || "",
          url: art.url || "",
          enabled: true,
        });
        renderItems();
        markDirty();
      }
    });

    const addManualBtn = document.createElement("button");
    addManualBtn.type = "button";
    addManualBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addManualBtn.title = "Einen freien Publikationseintrag manuell anlegen";
    addManualBtn.textContent = "+ Manuell";
    addManualBtn.addEventListener("click", function () {
      blk.items.push({
        article_id: "",
        title: "Neue Publikation",
        subtitle: "",
        date: new Date().toISOString().split("T")[0],
        category: "",
        url: "",
        enabled: true,
      });
      renderItems();
      markDirty();
    });

    addSection.appendChild(select);
    addSection.appendChild(addBtn);
    addSection.appendChild(addManualBtn);

    listWrap.appendChild(addSection);
    container.appendChild(listWrap);

    renderItems();
  }

  function buildFigureBlockBody(container, blk) {
    // Zeile 1: Grafik-Titel & Layout-Breite
    const topGrid = document.createElement("div");
    topGrid.style.display = "grid";
    topGrid.style.gridTemplateColumns = "1fr 190px";
    topGrid.style.gap = "10px";
    topGrid.style.marginBottom = "10px";

    const titleWrap = document.createElement("div");
    const titleLbl = document.createElement("label");
    titleLbl.className = "field-label";
    titleLbl.textContent = "Grafik-Titel (Yoga Sans Medium)";
    const titleInp = document.createElement("input");
    titleInp.type = "text";
    titleInp.className = "cms-input font-medium";
    titleInp.placeholder = "z.B. Leitzinsentwicklung im internationalen Vergleich";
    titleInp.value = blk.title || "";
    titleInp.addEventListener("input", function () {
      blk.title = titleInp.value;
      markDirty();
    });
    titleWrap.appendChild(titleLbl);
    titleWrap.appendChild(titleInp);

    const layoutWrap = createFullLayoutControl(blk);

    topGrid.appendChild(titleWrap);
    topGrid.appendChild(layoutWrap);
    container.appendChild(topGrid);

    // Zeile 2: Grafik-Untertitel
    const subWrap = document.createElement("div");
    subWrap.className = "field-group";
    const subLbl = document.createElement("label");
    subLbl.className = "field-label";
    subLbl.textContent = "Grafik-Untertitel (z.B. Einheit, Indexierung, Zeitraum)";
    const subInp = document.createElement("input");
    subInp.type = "text";
    subInp.className = "cms-input";
    subInp.placeholder = "z.B. In Prozent, 2022 bis 2026 (ab Q4 2025 Prognose LUKB)";
    subInp.value = blk.subtitle || "";
    subInp.addEventListener("input", function () {
      blk.subtitle = subInp.value;
      markDirty();
    });
    subWrap.appendChild(subLbl);
    subWrap.appendChild(subInp);
    container.appendChild(subWrap);

    // Zeile 3: Drag-and-Drop, Zwischenablage & Kontextmenü Grafik-Upload
    const dropzone = document.createElement("div");
    dropzone.className = "figure-upload-zone";
    dropzone.tabIndex = 0;
    dropzone.setAttribute("role", "button");
    dropzone.setAttribute("aria-label", "Grafik hochladen oder aus Zwischenablage einfügen");
    dropzone.title = "Klicken, Grafikdatei hierher ziehen oder Strg+V zum Einfügen aus der Zwischenablage (Rechtsklick für Menü)";

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".svg,.png,.jpg,.jpeg,image/svg+xml,image/png,image/jpeg";
    fileInput.style.display = "none";

    const renderDropzoneInner = () => {
      dropzone.innerHTML = "";
      const cachedUri = blk.asset_id ? state.assetCache[blk.asset_id] : null;
      if (cachedUri) {
        const img = document.createElement("img");
        img.className = "figure-preview-thumb";
        img.src = cachedUri;
        img.alt = blk.title || "Grafik";
        dropzone.appendChild(img);

        const caption = document.createElement("div");
        caption.style.fontSize = "12px";
        caption.style.color = "#5A687C";
        caption.innerHTML = "Klicken, neue Datei hierher ziehen oder <strong>Strg+V</strong> drücken, um Grafik zu ersetzen " +
          "<span style='color:#009FE3;'>(Rechtsklick für Menü)</span>";
        dropzone.appendChild(caption);

        const actionRow = document.createElement("div");
        actionRow.className = "figure-upload-actions";

        const pasteBtn = document.createElement("button");
        pasteBtn.type = "button";
        pasteBtn.className = "figure-action-btn btn-paste";
        pasteBtn.innerHTML = "<span>📋</span> <span>Aus Zwischenablage</span>";
        pasteBtn.title = "Grafik aus Zwischenablage einfügen (Strg+V)";
        pasteBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          pasteFromClipboard();
        });

        const replaceBtn = document.createElement("button");
        replaceBtn.type = "button";
        replaceBtn.className = "figure-action-btn";
        replaceBtn.innerHTML = "<span>📁</span> <span>Datei ersetzen</span>";
        replaceBtn.title = "Neue Datei vom Computer auswählen";
        replaceBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          fileInput.click();
        });

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "figure-action-btn btn-delete";
        removeBtn.innerHTML = "<span>🗑️</span> <span>Entfernen</span>";
        removeBtn.title = "Grafik entfernen";
        removeBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          blk.asset_id = "";
          renderDropzoneInner();
          markDirty();
        });

        actionRow.appendChild(pasteBtn);
        actionRow.appendChild(replaceBtn);
        actionRow.appendChild(removeBtn);
        dropzone.appendChild(actionRow);
      } else {
        const msg = document.createElement("div");
        msg.innerHTML =
          "<div style='font-size:24px;margin-bottom:6px;'>📊</div>" +
          "<strong style='color:#002855;font-size:13.5px;'>Grafikdatei hierher ziehen</strong> oder mit <kbd style='background:#E2E8F0;padding:2px 6px;border-radius:4px;font-family:monospace;font-size:12px;color:#002855;'>Strg + V</kbd> einfügen<br/>" +
          "<span style='font-size:12px;color:#5A687C;margin-top:4px;display:inline-block;'>Unterstützt Screenshots, Vektorgrafiken (SVG) sowie PNG / JPG &bull; <em>Rechtsklick für Menü</em></span>";
        dropzone.appendChild(msg);

        const actionRow = document.createElement("div");
        actionRow.className = "figure-upload-actions";

        const pasteBtn = document.createElement("button");
        pasteBtn.type = "button";
        pasteBtn.className = "figure-action-btn btn-paste";
        pasteBtn.innerHTML = "<span>📋</span> <span>Aus Zwischenablage einfügen</span>";
        pasteBtn.title = "Grafik aus Zwischenablage einfügen (Strg+V)";
        pasteBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          pasteFromClipboard();
        });

        const chooseBtn = document.createElement("button");
        chooseBtn.type = "button";
        chooseBtn.className = "figure-action-btn";
        chooseBtn.innerHTML = "<span>📁</span> <span>Datei auswählen</span>";
        chooseBtn.title = "Datei vom Computer auswählen";
        chooseBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          fileInput.click();
        });

        actionRow.appendChild(pasteBtn);
        actionRow.appendChild(chooseBtn);
        dropzone.appendChild(actionRow);
      }
    };

    const handleFileUpload = (file) => {
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function (ev) {
        const dataUrl = ev.target.result;
        const base64Data = dataUrl.split(",")[1] || "";
        const newAssetId = "asset_" + Math.random().toString(36).substring(2, 12);

        state.assetCache[newAssetId] = dataUrl;
        blk.asset_id = newAssetId;
        renderDropzoneInner();

        const isSvg = (file.type && file.type === "image/svg+xml") || (file.name && file.name.endsWith(".svg"));
        const defaultExt = isSvg ? ".svg" : (file.type === "image/jpeg" ? ".jpg" : ".png");
        const fileName = file.name || ("grafik_" + Date.now() + defaultExt);
        const mimeType = file.type || (isSvg ? "image/svg+xml" : "image/png");

        E.sendShinyEvent("lukb_upload_asset", {
          asset_id: newAssetId,
          article_id: state.article.id,
          filename: fileName,
          mime_type: mimeType,
          base64_data: base64Data,
        });
        markDirty();
      };
      reader.readAsDataURL(file);
    };

    const pasteFromClipboard = async () => {
      if (navigator.clipboard && navigator.clipboard.read) {
        try {
          const items = await navigator.clipboard.read();
          for (const item of items) {
            const imgType = item.types.find(function (t) { return t.startsWith("image/"); });
            if (imgType) {
              const blob = await item.getType(imgType);
              handleFileUpload(blob);
              return true;
            }
          }
          if (navigator.clipboard.readText) {
            const txt = await navigator.clipboard.readText();
            const trimmed = (txt || "").trim();
            if (trimmed.startsWith("<svg") && trimmed.includes("</svg>")) {
              const blob = new Blob([trimmed], { type: "image/svg+xml" });
              handleFileUpload(blob);
              return true;
            }
          }
          alert("Keine Bilddaten oder SVG-Grafik in der Zwischenablage gefunden.");
          return false;
        } catch (err) {
          console.warn("navigator.clipboard.read fehlgeschlagen oder Berechtigung abgelehnt:", err);
        }
      }
      alert("Direktes Lesen der Zwischenablage erfordert Browser-Freigabe oder Tastenkürzel.\nBitte klicken Sie auf die Box und drücken Sie Strg+V (Cmd+V).");
      dropzone.focus();
      return false;
    };

    const handlePasteEvent = function (e) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) {
        const hasImage = e.clipboardData && e.clipboardData.items && Array.from(e.clipboardData.items).some(function (item) {
          return item.type.indexOf("image") !== -1;
        });
        const hasText = e.clipboardData && e.clipboardData.getData("text/plain");
        if (hasText && !hasImage) return;
      }

      const cd = e.clipboardData || window.clipboardData;
      if (!cd) return;

      if (cd.items && cd.items.length > 0) {
        for (let i = 0; i < cd.items.length; i++) {
          const item = cd.items[i];
          if (item.type.indexOf("image") !== -1) {
            e.preventDefault();
            e.stopPropagation();
            const blob = item.getAsFile();
            if (blob) {
              handleFileUpload(blob);
              return;
            }
          }
        }
      }

      if (cd.files && cd.files.length > 0) {
        for (let i = 0; i < cd.files.length; i++) {
          const f = cd.files[i];
          if (f.type.startsWith("image/") || /\.(svg|png|jpe?g)$/i.test(f.name)) {
            e.preventDefault();
            e.stopPropagation();
            handleFileUpload(f);
            return;
          }
        }
      }

      const textData = cd.getData("text/plain");
      if (textData) {
        const trimmed = textData.trim();
        if (trimmed.startsWith("<svg") && trimmed.includes("</svg>")) {
          e.preventDefault();
          e.stopPropagation();
          const blob = new Blob([trimmed], { type: "image/svg+xml" });
          handleFileUpload(blob);
          return;
        }
      }
    };

    dropzone.addEventListener("paste", handlePasteEvent);
    container.addEventListener("paste", handlePasteEvent);

    const openContextMenu = function (clientX, clientY) {
      closeFigureContextMenu();
      const menu = document.createElement("div");
      menu.className = "figure-context-menu";
      menu.id = "active-figure-context-menu";

      const pasteItem = document.createElement("div");
      pasteItem.className = "figure-context-menu-item";
      pasteItem.innerHTML = '<span>📋</span> <span>Aus Zwischenablage einfügen</span> <span class="figure-context-menu-shortcut">Strg+V</span>';
      pasteItem.addEventListener("click", function (ev) {
        ev.stopPropagation();
        closeFigureContextMenu();
        pasteFromClipboard();
      });
      menu.appendChild(pasteItem);

      const uploadItem = document.createElement("div");
      uploadItem.className = "figure-context-menu-item";
      uploadItem.innerHTML = '<span>📁</span> <span>Grafikdatei auswählen...</span>';
      uploadItem.addEventListener("click", function (ev) {
        ev.stopPropagation();
        closeFigureContextMenu();
        fileInput.click();
      });
      menu.appendChild(uploadItem);

      if (blk.asset_id) {
        const divider = document.createElement("div");
        divider.className = "figure-context-menu-divider";
        menu.appendChild(divider);

        const removeItem = document.createElement("div");
        removeItem.className = "figure-context-menu-item danger";
        removeItem.innerHTML = '<span>🗑️</span> <span>Grafik entfernen</span>';
        removeItem.addEventListener("click", function (ev) {
          ev.stopPropagation();
          closeFigureContextMenu();
          blk.asset_id = "";
          renderDropzoneInner();
          markDirty();
        });
        menu.appendChild(removeItem);
      }

      document.body.appendChild(menu);

      const rect = menu.getBoundingClientRect();
      let left = clientX;
      let top = clientY;
      if (left + rect.width > window.innerWidth - 10) {
        left = window.innerWidth - rect.width - 10;
      }
      if (top + rect.height > window.innerHeight - 10) {
        top = window.innerHeight - rect.height - 10;
      }
      menu.style.left = Math.max(10, left) + "px";
      menu.style.top = Math.max(10, top) + "px";
    };

    dropzone.addEventListener("contextmenu", function (e) {
      e.preventDefault();
      e.stopPropagation();
      openContextMenu(e.clientX, e.clientY);
    });

    dropzone.addEventListener("click", function (e) {
      if (e.target.closest("button") || e.target.closest(".figure-action-btn")) {
        return;
      }
      dropzone.focus();
      fileInput.click();
    });

    fileInput.addEventListener("change", function () {
      if (fileInput.files && fileInput.files[0]) {
        handleFileUpload(fileInput.files[0]);
      }
    });

    dropzone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropzone.classList.add("drag-over");
    });
    dropzone.addEventListener("dragleave", function () {
      dropzone.classList.remove("drag-over");
    });
    dropzone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropzone.classList.remove("drag-over");
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });

    renderDropzoneInner();

    container.appendChild(dropzone);
    container.appendChild(fileInput);

    // Zeile 4: Quellenangabe
    const srcWrap = document.createElement("div");
    const srcLbl = document.createElement("label");
    srcLbl.className = "field-label";
    srcLbl.textContent = "Quellenangabe / Fussnote unter der Grafik";
    const srcInp = document.createElement("input");
    srcInp.type = "text";
    srcInp.className = "cms-input";
    srcInp.placeholder = "Quelle: Bloomberg, LUKB Investment Office";
    srcInp.value = blk.source || "";
    srcInp.addEventListener("input", function () {
      blk.source = srcInp.value;
      markDirty();
    });
    srcWrap.appendChild(srcLbl);
    srcWrap.appendChild(srcInp);
    container.appendChild(srcWrap);
  }

  // ==========================================================================
  // Block-Einfüge-Buttons & Globale Aktionen
  // ==========================================================================

  function bindAddBlockButtons() {
    document.querySelectorAll("[data-add-block-type]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!state.article) return;
        const btype = btn.getAttribute("data-add-block-type");
        const blocks = state.article.blocks || [];

        // Falls ein Block markiert ist, füge direkt darunter ein; sonst ans Ende
        let targetIdx = blocks.length;
        if (state.lastSelectedBlockId) {
          const idx = blocks.findIndex(function (b) {
            return b.id === state.lastSelectedBlockId;
          });
          if (idx !== -1) {
            targetIdx = idx + 1;
          }
        }
        insertBlockAt(targetIdx, btype);
      });
    });

    // Manueller Snapshot-Speicherbutton + Ctrl+S Shortcut
    const manualSaveBtn = document.getElementById("btn-manual-snapshot");
    if (manualSaveBtn) {
      manualSaveBtn.addEventListener("click", function () {
        flushAutosave(true, "Manueller Meilenstein");
      });
    }

    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        flushAutosave(true, "Gespeichert per Tastenkürzel (Ctrl+S)");
      }
      if (e.key === "Escape") {
        closeBlockPickerPopup();
        closeMoveToDialog();
        if (state.selectedBlockIds && state.selectedBlockIds.size > 0) {
          clearBlockSelection();
        }
      }
    });

    // Preview-Mode Tabs (PDF Typst vs. Web HTML)
    document.querySelectorAll("[data-preview-mode]").forEach(function (tabBtn) {
      tabBtn.addEventListener("click", function () {
        const mode = tabBtn.getAttribute("data-preview-mode");
        state.previewMode = mode;
        document.querySelectorAll("[data-preview-mode]").forEach(function (b) {
          b.classList.toggle("active", b.getAttribute("data-preview-mode") === mode);
        });
        const pdfContainer = document.getElementById("preview-container-pdf");
        const webContainer = document.getElementById("preview-container-web");
        if (pdfContainer && webContainer) {
          pdfContainer.style.display = mode === "pdf" ? "flex" : "none";
          webContainer.style.display = mode === "web" ? "block" : "none";
        }
        if (mode === "web") {
          const webIframe = document.getElementById("preview-iframe-web");
          if (webIframe && state.pendingWebHtml && webIframe.srcdoc !== state.pendingWebHtml) {
            webIframe.srcdoc = state.pendingWebHtml;
          }
        }
        E.sendShinyEvent("lukb_preview_mode_change", { mode: mode });
      });
    });

    // Sofortiger Autosave bei Fenster-/Tab-Fokusverlust
    window.addEventListener("blur", function () {
      if (state.isDirty && typeof flushAutosave === "function") {
        flushAutosave(false, "Autosave bei Fokusverlust");
      }
    });

    // Kontinuierliche Aktualisierung der Typst-Vorschau an-/ausschalten
    const autoPreviewChk = document.getElementById("toggle-auto-preview");
    try {
      const savedPref = window.localStorage.getItem("lukb_auto_preview");
      if (savedPref === "false") {
        state.autoPreview = false;
      }
    } catch (e) {}

    if (autoPreviewChk) {
      autoPreviewChk.checked = state.autoPreview;
      autoPreviewChk.addEventListener("change", function () {
        state.autoPreview = !!autoPreviewChk.checked;
        try {
          window.localStorage.setItem("lukb_auto_preview", state.autoPreview ? "true" : "false");
        } catch (e) {}

        const pageBadge = document.getElementById("preview-page-count");
        const refreshBtn = document.getElementById("btn_refresh_preview");
        if (!state.autoPreview && pageBadge) {
          pageBadge.textContent =
            (state.lastKnownPageCount > 0 ? state.lastKnownPageCount + " S. · " : "") + "Auto-Typst aus";
        } else if (state.autoPreview && refreshBtn) {
          refreshBtn.classList.remove("has-pending-preview");
        }

        E.sendShinyEvent("lukb_auto_preview_toggle", {
          enabled: state.autoPreview,
          refresh_now: state.autoPreview,
        });
      });
    }
  }

  // ==========================================================================
  // Shiny Custom Message Handlers (Backend -> Frontend)
  // ==========================================================================

  function registerShinyHandlers() {
    if (!window.Shiny) {
      setTimeout(registerShinyHandlers, 100);
      return;
    }

    // 1. Lädt einen kompletten Artikel in den Editor
    window.Shiny.addCustomMessageHandler("lukb_load_article", function (msg) {
      if (state.autosaveTimer) {
        clearTimeout(state.autosaveTimer);
        state.autosaveTimer = null;
      }
      if (msg.self_session_id) {
        state.selfSessionId = msg.self_session_id;
      }
      state.isDirty = false;
      state.article = msg.article;
      state.baseArticle = deepClone(msg.article);
      state.editSeq = 0;
      state.lastPreviewedSeq = 0;
      if (Array.isArray(msg.available_tickers)) {
        state.availableTickers = msg.available_tickers;
        indexTickerItems(msg.available_tickers);
      }
      if (msg.assets) {
        Object.keys(msg.assets).forEach(function (k) {
          state.assetCache[k] = msg.assets[k];
        });
      }
      state.selectedBlockIds.clear();
      state.lastSelectedBlockId = null;
      clearUndoStack();
      if (typeof closeBlockPickerPopup === "function") closeBlockPickerPopup();
      renderMetadataForm();
      renderBlocksCanvas();
      applyPeerFocusDecorations();
      setAutosaveIndicator("saved", "Geladen & synchronisiert");
    });

    // 2. Aktualisiert die Artikel-Liste in der linken Sidebar sowie den Modal-Katalog
    window.Shiny.addCustomMessageHandler("lukb_update_article_list", function (msg) {
      state.sidebarArticles = msg.articles || [];
      state.allArticles = Array.isArray(msg.all_articles)
        ? msg.all_articles
        : (state.allArticles && state.allArticles.length ? state.allArticles : (msg.articles || []));
      state.activeArticleId = msg.active_id || "";
      renderArticleList(
        state.sidebarArticles,
        state.activeArticleId,
        !!msg.sidebar_search_active
      );
      if (state.modalOpen) {
        populateModalCategoryDropdown();
        renderPubModalTable();
      }
    });

    // 3. Bestätigt erfolgreichen Autosave
    window.Shiny.addCustomMessageHandler("lukb_autosave_ack", function (msg) {
      if (msg.assets) {
        Object.keys(msg.assets).forEach(function (k) {
          state.assetCache[k] = msg.assets[k];
          const chartImg = document.querySelector(
            '.db-chart-preview-img[data-block-id="' + k + '"]'
          );
          if (chartImg) {
            chartImg.src = msg.assets[k];
          }
        });
      }
      if (msg.article && !state.isDirty) {
        state.baseArticle = deepClone(msg.article);
      }
      if (!state.isDirty) {
        const suffix = msg.merged ? " (mit Co-Autor zusammengeführt)" : "";
        setAutosaveIndicator("saved", "Gespeichert um " + (msg.saved_at || "") + suffix);
      }
    });

    // 3a. Aktualisiert einzelne DB-Chart-SVG-Vorschau im Block sofort
    window.Shiny.addCustomMessageHandler("lukb_db_chart_svg", function (msg) {
      if (!msg || !msg.block_id || !msg.data_uri) return;
      state.assetCache[msg.block_id] = msg.data_uri;
      const chartImg = document.querySelector(
        '.db-chart-preview-img[data-block-id="' + msg.block_id + '"]'
      );
      if (chartImg) {
        chartImg.src = msg.data_uri;
      }
    });

    // 3a-custom. Aktualisiert einzelne Custom-Chart-SVG-Vorschau im Block sofort
    window.Shiny.addCustomMessageHandler("lukb_custom_chart_svg", function (msg) {
      if (!msg || !msg.block_id || !msg.data_uri) return;
      state.assetCache[msg.block_id] = msg.data_uri;
      const chartImg = document.getElementById("custom-chart-preview-img-" + msg.block_id);
      if (chartImg) {
        chartImg.src = msg.data_uri;
      }
      const iframe = document.getElementById("preview-iframe-web");
      if (iframe && iframe.contentDocument) {
        const iframeImg = iframe.contentDocument.querySelector(
          'img[data-block-id="' + msg.block_id + '"]'
        );
        if (iframeImg) {
          iframeImg.src = msg.data_uri;
        }
      }
    });

    // 3a-bis. Schnelle Ticker-Vorschläge aus dem Backend-Suchindex
    window.Shiny.addCustomMessageHandler("lukb_ticker_suggestions", function (msg) {
      if (!msg || !Array.isArray(msg.results)) return;
      const qNorm = String(msg.query || "").trim().toLowerCase();
      state.tickerQueryCache[qNorm] = msg.results;
      indexTickerItems(msg.results);
      if (msg.request_id && msg.request_id < tickerSuggest.requestId) {
        return; // Veraltete Antwort verwerfen
      }
      renderTickerSuggestItems(msg.results);
    });

    // 3b. Echtzeit-Synchronisation bei Änderungen durch Co-Autoren (ohne Fokus-Verlust!)
    window.Shiny.addCustomMessageHandler("lukb_remote_sync", function (msg) {
      if (!state.article || !msg.article || msg.article.id !== state.article.id) return;
      if (msg.assets) {
        Object.keys(msg.assets).forEach(function (k) {
          state.assetCache[k] = msg.assets[k];
        });
      }

      const focusedBlockId = getActiveFocusedBlockId();
      const activeEl = document.activeElement;
      const incoming = msg.article;
      const prevBase = state.baseArticle || state.article;

      // Metadaten-Felder nur aktualisieren, wenn der lokale Nutzer nicht gerade darin tippt
      state.article.template_id = incoming.template_id;
      state.article.status = incoming.status;
      const metaFields = [
        { key: "category", domId: "meta-category" },
        { key: "header_series", domId: "meta-header-series" },
        { key: "publication_date", domId: "meta-pub-date" },
        { key: "title", domId: "meta-title" },
        { key: "subtitle", domId: "meta-subtitle" },
        { key: "lead", domId: "meta-lead" },
        { key: "disclaimer", domId: "meta-disclaimer" },
      ];
      metaFields.forEach(function (mf) {
        const domNode = document.getElementById(mf.domId);
        if (activeEl !== domNode) {
          state.article.metadata[mf.key] = incoming.metadata[mf.key];
        }
      });
      if (!activeEl || !activeEl.closest("#meta-authors-container")) {
        state.article.metadata.authors = deepClone(incoming.metadata.authors || []);
      }
      if (!activeEl || activeEl.id !== "meta-tag-input") {
        state.article.metadata.tags = deepClone(incoming.metadata.tags || []);
      }
      renderMetadataForm();

      // Inhaltsblöcke selektiv synchronisieren:
      // Falls der Nutzer gerade aktiv in einem Block tippt, bleibt dessen lokaler DOM-Knoten
      // und Block-Inhalt völlig unberührt!
      const localBlocksById = {};
      (state.article.blocks || []).forEach(function (b) {
        localBlocksById[b.id] = b;
      });
      const prevBaseById = {};
      (prevBase.blocks || []).forEach(function (b) {
        prevBaseById[b.id] = b;
      });

      const mergedBlocks = [];
      (incoming.blocks || []).forEach(function (incBlk) {
        const locBlk = localBlocksById[incBlk.id];
        const baseBlk = prevBaseById[incBlk.id];
        const isLocallyModified =
          locBlk && baseBlk && JSON.stringify(locBlk) !== JSON.stringify(baseBlk);

        if (incBlk.id === focusedBlockId || (state.isDirty && isLocallyModified)) {
          mergedBlocks.push(locBlk);
        } else {
          mergedBlocks.push(incBlk);
        }
      });

      // Aktualisiere DOM-Karten nur für Blöcke, die nicht gerade lokal fokussiert sind
      const oldOrder = (state.article.blocks || []).map((b) => b.id).join(",");
      const newOrder = mergedBlocks.map((b) => b.id).join(",");
      state.article.blocks = mergedBlocks;
      state.baseArticle = deepClone(incoming);

      if (oldOrder !== newOrder && !focusedBlockId) {
        renderBlocksCanvas();
      } else {
        const canvas = document.getElementById("lukb-blocks-canvas");
        if (canvas) {
          let insideBox = false;
          mergedBlocks.forEach(function (blk, idx) {
            if (blk.type === "box_start") insideBox = true;
            if (blk.id !== focusedBlockId) {
              const locBlk = localBlocksById[blk.id];
              // Prüfe, ob sich der Block tatsächlich geändert hat
              const isUnchanged = locBlk && JSON.stringify(locBlk) === JSON.stringify(blk);
              if (!isUnchanged) {
                const existingCard = canvas.querySelector('[data-block-id="' + blk.id + '"]');
                // Optimierter In-Place Update für Richtext & Callout (vermeidet DOM-Zerstörung)
                if (existingCard && (blk.type === "richtext" || blk.type === "callout") && locBlk && locBlk.type === blk.type) {
                  const editable = existingCard.querySelector(".richtext-editable");
                  if (editable && editable !== document.activeElement && editable.innerHTML !== blk.html) {
                    editable.innerHTML = blk.html || "<p></p>";
                    if (blk.type === "callout") {
                      const titleInp = existingCard.querySelector(".cms-input");
                      if (titleInp && titleInp !== document.activeElement) titleInp.value = blk.title || "";
                    }
                    if (blk.type === "box_end") insideBox = false;
                    return;
                  }
                }
                const newCard = buildBlockCardElement(blk, idx, insideBox);
                if (existingCard) {
                  canvas.replaceChild(newCard, existingCard);
                } else {
                  canvas.appendChild(newCard);
                }
              }
            }
            if (blk.type === "box_end") insideBox = false;
          });
          reindexCanvasCards(canvas);
        }
      }
      applyPeerFocusDecorations();
      if (!state.isDirty && msg.updated_by) {
        setAutosaveIndicator("saved", "Live aktualisiert von " + msg.updated_by);
      }
    });

    // 3c. Live-Präsenz & Fokus-Anzeige aller aktiven Co-Autoren im selben Artikel
    window.Shiny.addCustomMessageHandler("lukb_collab_presence", function (msg) {
      if (msg.self_session_id) {
        state.selfSessionId = msg.self_session_id;
      }
      state.peers = Array.isArray(msg.peers) ? msg.peers : [];
      renderPresenceBar();
      applyPeerFocusDecorations();
    });

    // 4. PDF.js Live-Preview & Web HTML
    if (typeof window !== "undefined" && window.pdfjsLib) {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = "js/vendor/pdf.worker.min.js";
    }

    function base64ToUint8Array(base64) {
      const raw = window.atob(base64);
      const rawLength = raw.length;
      const array = new Uint8Array(rawLength);
      for (let i = 0; i < rawLength; i++) {
        array[i] = raw.charCodeAt(i);
      }
      return array;
    }

    let _currentPdfRenderSeq = 0;
    let _activeRenderTasks = [];
    let _lastRenderedPdfBase64 = "";

    async function renderPdfPreview(pdfBase64) {
      if (typeof window !== "undefined" && window.pdfjsLib && !window.pdfjsLib.GlobalWorkerOptions.workerSrc) {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = "js/vendor/pdf.worker.min.js";
      }

      const pdfContainer = document.getElementById("preview-container-pdf");
      const pageBadge = document.getElementById("preview-page-count");
      const refreshBtn = document.getElementById("btn_refresh_preview");
      if (!pdfContainer) return;

      if (refreshBtn && !refreshBtn._hasPdfResetListener) {
        refreshBtn._hasPdfResetListener = true;
        refreshBtn.addEventListener("click", function () {
          _lastRenderedPdfBase64 = "";
        });
      }

      // Redundantes Neuzeichnen vermeiden, wenn dieser exakte PDF-Stand bereits auf dem Canvas liegt
      if (pdfBase64 && pdfBase64 === _lastRenderedPdfBase64) {
        state.previewPending = false;
        if (refreshBtn) refreshBtn.classList.remove("has-pending-preview");
        return;
      }

      const renderSeq = ++_currentPdfRenderSeq;

      // Laufende Render-Tasks aus vorherigen Updates abbrechen
      for (let i = 0; i < _activeRenderTasks.length; i++) {
        try {
          if (_activeRenderTasks[i] && typeof _activeRenderTasks[i].cancel === "function") {
            _activeRenderTasks[i].cancel();
          }
        } catch (_) {}
      }
      _activeRenderTasks = [];

      if (!window.pdfjsLib) {
        console.error("PDF.js ist nicht geladen.");
        return;
      }

      let pdfDoc = null;
      const seqAtRenderStart = state.editSeq;
      try {
        const pdfData = base64ToUint8Array(pdfBase64);
        const loadingTask = window.pdfjsLib.getDocument({
          data: pdfData,
          isEvalSupported: false,
        });
        pdfDoc = await loadingTask.promise;

        if (renderSeq !== _currentPdfRenderSeq) {
          return; // Ein neueres Update hat diesen Render-Vorgang überholt
        }

        const numPages = pdfDoc.numPages;

        // Eventuelle alte SVG-Seiten-Elemente oder Fehlermeldungen abräumen
        const svgPages = pdfContainer.querySelectorAll(":scope > .typst-svg-page, :scope > .preview-error-box");
        if (svgPages.length > 0) {
          svgPages.forEach(function (el) { el.remove(); });
        }

        // Bestehende PDF-Seiten-Container ermitteln
        const existingPages = Array.from(pdfContainer.querySelectorAll(":scope > .typst-pdf-page"));

        // Überzählige Seiten vom Ende entfernen
        while (existingPages.length > numPages) {
          const toRemove = existingPages.pop();
          if (toRemove) toRemove.remove();
        }

        // Fehlende Seiten-Container anhängen
        while (existingPages.length < numPages) {
          const pageWrap = document.createElement("div");
          pageWrap.className = "typst-pdf-page";
          pdfContainer.appendChild(pageWrap);
          existingPages.push(pageWrap);
        }

        const targetWidth = Math.min(
          pdfContainer.clientWidth > 40 ? pdfContainer.clientWidth - 40 : 760,
          760
        );
        const dpr = Math.max(window.devicePixelRatio || 1, 1.5);

        for (let pageNum = 1; pageNum <= numPages; pageNum++) {
          if (renderSeq !== _currentPdfRenderSeq) return;

          const page = await pdfDoc.getPage(pageNum);
          if (renderSeq !== _currentPdfRenderSeq) return;

          const pageWrap = existingPages[pageNum - 1];
          if (!pageWrap) continue;

          const unscaled = page.getViewport({ scale: 1.0 });
          pageWrap.style.aspectRatio = unscaled.width + " / " + unscaled.height;

          const cssScale = (targetWidth > 0 ? targetWidth : 760) / unscaled.width;
          const renderScale = cssScale * dpr;
          const viewport = page.getViewport({ scale: renderScale });

          let canvas = pageWrap.querySelector("canvas");
          if (!canvas) {
            canvas = document.createElement("canvas");
            pageWrap.innerHTML = "";
            pageWrap.appendChild(canvas);
          }

          canvas.width = Math.floor(viewport.width);
          canvas.height = Math.floor(viewport.height);
          canvas.style.width = "100%";
          canvas.style.height = "auto";
          canvas.style.display = "block";

          const ctx = canvas.getContext("2d", { alpha: false });
          const renderTask = page.render({
            canvasContext: ctx,
            viewport: viewport,
          });
          _activeRenderTasks.push(renderTask);

          try {
            await renderTask.promise;
          } catch (err) {
            if (err && err.name === "RenderingCancelledException") {
              return;
            }
            throw err;
          }
        }

        _lastRenderedPdfBase64 = pdfBase64;
        if (seqAtRenderStart > state.lastPreviewedSeq) {
          state.lastPreviewedSeq = seqAtRenderStart;
        }
        state.lastKnownPageCount = numPages;
        state.previewPending = false;
        if (refreshBtn) refreshBtn.classList.remove("has-pending-preview");
        if (pageBadge) {
          const baseLabel =
            numPages + (numPages === 1 ? " PDF-Seite (Typst)" : " PDF-Seiten (Typst)");
          pageBadge.textContent = state.autoPreview ? baseLabel : baseLabel + " · Pausiert";
        }
      } catch (err) {
        if (renderSeq !== _currentPdfRenderSeq) return;
        console.error("PDF.js Live-Preview Render-Fehler:", err);
      } finally {
        if (pdfDoc && typeof pdfDoc.destroy === "function") {
          pdfDoc.destroy().catch(function () {});
        }
      }
    }

    // 4. Aktualisiert die Live-Preview (Typst PDF via PDF.js + Web HTML)
    window.Shiny.addCustomMessageHandler("lukb_update_preview", function (msg) {
      const pdfContainer = document.getElementById("preview-container-pdf");
      const webIframe = document.getElementById("preview-iframe-web");
      const pageBadge = document.getElementById("preview-page-count");
      const refreshBtn = document.getElementById("btn_refresh_preview");

      if (msg.error) {
        if (pdfContainer) {
          const escMsg = E.escapeHtml ? E.escapeHtml(msg.error) : msg.error;
          pdfContainer.innerHTML =
            '<div class="preview-error-box" style="margin:20px;padding:16px;background:#FEF2F2;border:1px solid #FCA5A5;border-radius:6px;color:#991B1B;font-family:var(--font-heading);font-size:13px;">' +
            '<strong>Typst Vorschau-Hinweis:</strong>' +
            '<div style="margin-top:6px;font-family:monospace;font-size:12px;white-space:pre-wrap;">' + escMsg + '</div>' +
            '</div>';
        }
      } else if (pdfContainer && typeof msg.pdf_base64 === "string" && msg.pdf_base64) {
        renderPdfPreview(msg.pdf_base64);
      } else if (pdfContainer && Array.isArray(msg.svg_pages)) {
        const existingPages = Array.from(pdfContainer.querySelectorAll(":scope > .typst-svg-page"));

        // Überzählige Seiten vom Ende entfernen
        while (existingPages.length > msg.svg_pages.length) {
          const toRemove = existingPages.pop();
          if (toRemove) toRemove.remove();
        }
        // Fehlende Seiten anhängen
        while (existingPages.length < msg.svg_pages.length) {
          const pageWrap = document.createElement("div");
          pageWrap.className = "typst-svg-page";
          pdfContainer.appendChild(pageWrap);
          existingPages.push(pageWrap);
        }

        // Differenzielles In-Place Update: Nur Seiten anfassen, deren SVG abweicht
        msg.svg_pages.forEach(function (svgMarkup, idx) {
          const pageEl = existingPages[idx];
          if (!pageEl) return;
          if (pageEl._lastSvgMarkup !== svgMarkup) {
            pageEl.innerHTML = svgMarkup;
            pageEl._lastSvgMarkup = svgMarkup;
          }
        });

        state.lastKnownPageCount = msg.svg_pages.length;
        state.previewPending = false;
        if (refreshBtn) {
          refreshBtn.classList.remove("has-pending-preview");
        }
        if (pageBadge) {
          const baseLabel =
            msg.svg_pages.length + (msg.svg_pages.length === 1 ? " PDF-Seite (Typst)" : " PDF-Seiten (Typst)");
          pageBadge.textContent = state.autoPreview ? baseLabel : baseLabel + " · Pausiert";
        }
      } else if (msg.typst_skipped) {
        state.previewPending = true;
        if (refreshBtn) {
          refreshBtn.classList.add("has-pending-preview");
        }
        if (pageBadge) {
          pageBadge.textContent =
            (state.lastKnownPageCount > 0 ? state.lastKnownPageCount + " S. · " : "") + "Typst veraltet (↻)";
        }
      }

      if (typeof msg.web_html === "string" && msg.web_html) {
        state.pendingWebHtml = msg.web_html;
        if (webIframe && state.previewMode === "web") {
          if (webIframe.srcdoc !== msg.web_html) {
            webIframe.srcdoc = msg.web_html;
          }
        }
      }
    });

    if (!state.autoPreview) {
      E.sendShinyEvent("lukb_auto_preview_toggle", { enabled: false, refresh_now: false });
    }
  }

  function initEditorApp() {
    if (state._initialized) return;
    state._initialized = true;
    window.lukbRefreshCanvasDecorations = function () {
      reindexCanvasCards();
    };
    bindMetadataStaticListeners();
    bindAddBlockButtons();
    bindSidebarAndModalListeners();
    bindFocusTrackingListeners();
    bindDropdownListeners();
    registerShinyHandlers();
  }


  Object.assign(E, {
    activeAutoScroller: activeAutoScroller,
    activePickerPopover: activePickerPopover,
    autoScrollActive: autoScrollActive,
    autoScrollRaf: autoScrollRaf,
    autoScrollVelocity: autoScrollVelocity,
    bindAddBlockButtons: bindAddBlockButtons,
    bindMetadataStaticListeners: bindMetadataStaticListeners,
    buildBlockCardElement: buildBlockCardElement,
    buildFigureBlockBody: buildFigureBlockBody,
    buildFootnotesBlockBody: buildFootnotesBlockBody,
    buildHeadingBlockBody: buildHeadingBlockBody,
    buildPublicationsBlockBody: buildPublicationsBlockBody,
    clearBlockSelection: clearBlockSelection,
    closeBlockPickerPopup: closeBlockPickerPopup,
    createInlineInserterElement: createInlineInserterElement,
    deleteSelectedBlocks: deleteSelectedBlocks,
    duplicateSelectedBlocks: duplicateSelectedBlocks,
    ensureFloatingSelectionBar: ensureFloatingSelectionBar,
    getCardCurrentIndex: getCardCurrentIndex,
    initEditorApp: initEditorApp,
    initSortable: initSortable,
    insertBlockAt: insertBlockAt,
    moveSelectedBlocks: moveSelectedBlocks,
    moveSelectedBlocksTo: moveSelectedBlocksTo,
    openBlockPickerPopup: openBlockPickerPopup,
    openMoveToDialog: openMoveToDialog,
    registerShinyHandlers: registerShinyHandlers,
    reindexCanvasCards: reindexCanvasCards,
    reorderCanvasCardsFromState: reorderCanvasCardsFromState,
    renderAuthorsList: renderAuthorsList,
    renderBlocksCanvas: renderBlocksCanvas,
    renderMetadataForm: renderMetadataForm,
    renderTagsList: renderTagsList,
    startEditorAutoScroll: startEditorAutoScroll,
    stopEditorAutoScroll: stopEditorAutoScroll,
    syncBlockOrderFromDOM: syncBlockOrderFromDOM,
    toggleBlockSelection: toggleBlockSelection,
    updateBlockSelectionVisuals: updateBlockSelectionVisuals,
    updateCardAnchorBadges: updateCardAnchorBadges,
    updateFloatingSelectionBar: updateFloatingSelectionBar,
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initEditorApp);
  } else {
    initEditorApp();
  }
})();
