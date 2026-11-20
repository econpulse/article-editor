/**
 * LUKB Editor Modul: Zentraler State, Undo-Stack, Autosave & Block-Katalog
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function renderBlocksCanvas() { return E.renderBlocksCanvas.apply(this, arguments); }
  function updateFloatingSelectionBar() { return E.updateFloatingSelectionBar.apply(this, arguments); }

  function sanitizeRichTextHtml(htmlStr) {
    if (!htmlStr) return "";
    let s = String(htmlStr);
    s = s.replace(/<!--[\s\S]*?-->/g, "");
    s = s.replace(/<(script|style|iframe|object|embed|meta|link)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, "");
    s = s.replace(/<(script|style|iframe|object|embed|meta|link)\b[^>]*\/?>/gi, "");
    s = s.replace(/<div\b[^>]*>/gi, "<p>").replace(/<\/div\s*>/gi, "</p>");
    s = s.replace(/<p>\s*<p>/gi, "<p>").replace(/<\/p>\s*<\/p>/gi, "</p>");
    return s.trim();
  }

  const state = {
    article: null,
    baseArticle: null, // Snapshot für 3-Wege-Merge bei gleichzeitigem Editieren
    assetCache: {}, // asset_id / block_id -> data_uri
    availableTickers: [], // Initiale Top-Ticker [{ticker, name}, ...] aus ts_db
    tickerNameMap: {}, // O(1) Lookup: UPPERCASE_TICKER -> Name
    tickerQueryCache: {}, // Schneller Client-Cache: queryLower -> [{ticker, name}, ...]
    dbChartTimers: {}, // block_id -> timeoutId
    customChartTimers: {}, // block_id -> timeoutId
    isDirty: false,
    autosaveTimer: null,
    editSeq: 0,
    lastPreviewedSeq: -1,
    sortableInstance: null,
    selectedBlockIds: new Set(),
    lastSelectedBlockId: null,
    undoStack: [],
    previewMode: "pdf", // "pdf" (Typst SVG) | "web" (HTML5)
    autoPreview: true, // Kontinuierliche Aktualisierung der Typst-Vorschau
    previewPending: false,
    lastKnownPageCount: 0,
    selfSessionId: "",
    peers: [], // Aktive Co-Autoren im selben Artikel
    currentFocusedTarget: "",
    sidebarArticles: [],
    allArticles: [],
    activeArticleId: "",
    sidebarCollapsed: false,
    openArchiveMonths: {}, // monthKey -> boolean
    modalOpen: false,
    modalFilter: {
      search: "",
      status: "all",
      template: "all",
      category: "all",
      sort: "updated_desc",
      page: 1,
      pageSize: 15,
    },
  };

  function deepClone(obj) {
    return obj ? JSON.parse(JSON.stringify(obj)) : null;
  }

  function sendShinyEvent(inputName, payload) {
    if (!window.Shiny || !window.Shiny.setInputValue) return false;
    const data = Object.assign({}, payload || {});
    if (data.ts === undefined) {
      data.ts = Date.now();
    }
    window.Shiny.setInputValue(inputName, data, { priority: "event" });
    return true;
  }

  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function parseDelimitedText(text, delimiter) {
    const delim = delimiter || "\t";
    const normalized = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const rows = [];
    let currentRow = [];
    let currentCell = "";
    let inQuotes = false;

    for (let i = 0; i < normalized.length; i++) {
      const ch = normalized[i];
      if (inQuotes) {
        if (ch === '"') {
          if (i + 1 < normalized.length && normalized[i + 1] === '"') {
            currentCell += '"';
            i++;
          } else {
            inQuotes = false;
          }
        } else {
          currentCell += ch;
        }
      } else {
        if (ch === '"' && currentCell === "") {
          inQuotes = true;
        } else if (ch === delim) {
          currentRow.push(currentCell);
          currentCell = "";
        } else if (ch === "\n") {
          currentRow.push(currentCell);
          rows.push(currentRow);
          currentRow = [];
          currentCell = "";
        } else {
          currentCell += ch;
        }
      }
    }

    if (currentCell !== "" || currentRow.length > 0) {
      currentRow.push(currentCell);
      rows.push(currentRow);
    }

    return rows;
  }

  const CHART_PALETTES = [
    {
      id: "lukb_classic",
      label: "LUKB Standard",
      colors: ["#037FDA", "#9CD4FB", "#431231", "#BA249D", "#F07E2C"],
    },
    {
      id: "lukb_blues",
      label: "Blau-Abstufung",
      colors: ["#002855", "#005A9C", "#009FE3", "#5BB8E8", "#9BD3F2"],
    },
  ];

  const DEFAULT_CHART_HEIGHT_PRESETS = [
    { label: "28 mm", val: 28, title: "Kompakt (28 mm)" },
    { label: "36 mm (Standard)", val: 36, title: "Standardhöhe (36 mm)" },
    { label: "46 mm", val: 46, title: "Erweitert (46 mm)" },
    { label: "56 mm", val: 56, title: "Gross (56 mm)" },
  ];

  function createChartPaletteBar(blk, palettes, onChange) {
    const paletteList = Array.isArray(palettes) && palettes.length > 0 ? palettes : CHART_PALETTES;
    if (blk.palette !== "lukb_classic" && blk.palette !== "lukb_blues") {
      blk.palette = "lukb_classic";
    }
    delete blk.palette_colors;

    const paletteBar = document.createElement("div");
    paletteBar.className = "db-chart-palette-bar";

    const paletteTop = document.createElement("div");
    paletteTop.className = "db-chart-palette-top";

    const paletteLbl = document.createElement("span");
    paletteLbl.className = "field-label";
    paletteLbl.style.margin = "0";
    paletteLbl.textContent = "Farbpalette:";

    const palettePresetsWrap = document.createElement("div");
    palettePresetsWrap.className = "db-palette-presets";

    function getActiveColors() {
      const found =
        paletteList.find(function (p) { return p.id === blk.palette; }) ||
        paletteList[0];
      return found.colors;
    }

    function renderPaletteControls() {
      palettePresetsWrap.innerHTML = "";
      paletteList.forEach(function (preset) {
        const pBtn = document.createElement("button");
        pBtn.type = "button";
        pBtn.className = "db-palette-preset-btn" + (blk.palette === preset.id ? " active" : "");
        pBtn.title = "Farbpalette «" + preset.label + "» anwenden";

        const swatches = document.createElement("span");
        swatches.className = "db-palette-mini-swatches";
        preset.colors.forEach(function (hex) {
          const sw = document.createElement("span");
          sw.className = "db-palette-mini-swatch";
          sw.style.backgroundColor = hex;
          swatches.appendChild(sw);
        });

        const lblSpan = document.createElement("span");
        lblSpan.textContent = preset.label;

        pBtn.appendChild(swatches);
        pBtn.appendChild(lblSpan);
        pBtn.addEventListener("click", function () {
          blk.palette = preset.id;
          renderPaletteControls();
          if (typeof onChange === "function") {
            onChange(preset.id);
          }
        });
        palettePresetsWrap.appendChild(pBtn);
      });
    }

    paletteTop.appendChild(paletteLbl);
    paletteTop.appendChild(palettePresetsWrap);
    paletteBar.appendChild(paletteTop);
    renderPaletteControls();

    return {
      element: paletteBar,
      getActiveColors: getActiveColors,
      render: renderPaletteControls,
    };
  }

  function createChartHeightBar(blk, presets, onChange) {
    const heightPresetList =
      Array.isArray(presets) && presets.length > 0 ? presets : DEFAULT_CHART_HEIGHT_PRESETS;

    const heightBar = document.createElement("div");
    heightBar.className = "db-chart-height-bar";

    const heightLeft = document.createElement("div");
    heightLeft.className = "db-chart-height-left";

    const heightLbl = document.createElement("label");
    heightLbl.className = "field-label";
    heightLbl.style.margin = "0";
    heightLbl.style.whiteSpace = "nowrap";
    heightLbl.textContent = "Höhe Chartfläche (Y-Achse):";

    const heightInp = document.createElement("input");
    heightInp.type = "number";
    heightInp.className = "cms-input font-medium";
    heightInp.style.maxWidth = "70px";
    heightInp.style.textAlign = "center";
    heightInp.style.padding = "4px 8px";
    heightInp.min = "20";
    heightInp.max = "100";
    heightInp.step = "2";
    heightInp.value = blk.chart_height_mm || 36;

    const presetButtons = [];

    function updatePresetActive() {
      const cur = blk.chart_height_mm || 36;
      presetButtons.forEach(function (pb) {
        pb.btn.classList.toggle("active", pb.val === cur);
      });
    }

    function updateChartHeight(newVal) {
      let num = parseInt(newVal, 10);
      if (isNaN(num)) num = 36;
      num = Math.max(20, Math.min(100, Math.round(num / 2) * 2));
      blk.chart_height_mm = num;
      heightInp.value = num;
      updatePresetActive();
      if (typeof onChange === "function") {
        onChange(num);
      }
    }

    heightInp.addEventListener("change", function () {
      updateChartHeight(heightInp.value);
    });

    heightLeft.appendChild(heightLbl);
    heightLeft.appendChild(heightInp);

    const heightPresets = document.createElement("div");
    heightPresets.className = "db-chart-height-presets";

    const stepDownBtn = document.createElement("button");
    stepDownBtn.type = "button";
    stepDownBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    stepDownBtn.style.padding = "4px 8px";
    stepDownBtn.textContent = "− 2 mm";
    stepDownBtn.title = "Höhe um 2 mm verringern";
    stepDownBtn.addEventListener("click", function () {
      updateChartHeight((blk.chart_height_mm || 36) - 2);
    });
    heightPresets.appendChild(stepDownBtn);

    const stepUpBtn = document.createElement("button");
    stepUpBtn.type = "button";
    stepUpBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    stepUpBtn.style.padding = "4px 8px";
    stepUpBtn.textContent = "+ 2 mm";
    stepUpBtn.title = "Höhe um 2 mm vergrössern";
    stepUpBtn.addEventListener("click", function () {
      updateChartHeight((blk.chart_height_mm || 36) + 2);
    });
    heightPresets.appendChild(stepUpBtn);

    heightPresetList.forEach(function (preset) {
      const pBtn = document.createElement("button");
      pBtn.type = "button";
      pBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm db-height-preset-btn";
      pBtn.style.padding = "4px 9px";
      pBtn.style.fontSize = "11.5px";
      pBtn.textContent = preset.label;
      pBtn.title = preset.title;
      pBtn.addEventListener("click", function () {
        updateChartHeight(preset.val);
      });
      heightPresets.appendChild(pBtn);
      presetButtons.push({ btn: pBtn, val: preset.val });
    });

    updatePresetActive();
    heightBar.appendChild(heightLeft);
    heightBar.appendChild(heightPresets);
    return heightBar;
  }

  function createSimpleLayoutSelect(blk, widthPx, onChange) {
    const layoutSel = document.createElement("select");
    layoutSel.className = "cms-select";
    if (widthPx) {
      layoutSel.style.width = widthPx;
    }
    [
      { val: "column", label: "1-spaltig (Spaltenbreite)" },
      { val: "full", label: "2-spaltig (Seitenbreite)" },
    ].forEach(function (o) {
      const opt = document.createElement("option");
      opt.value = o.val;
      opt.textContent = o.label;
      if ((blk.layout || "column") === o.val) opt.selected = true;
      layoutSel.appendChild(opt);
    });
    layoutSel.addEventListener("change", function () {
      blk.layout = layoutSel.value;
      markDirty();
      if (typeof onChange === "function") {
        onChange(blk.layout);
      }
    });
    return layoutSel;
  }

  function getLatestPublishedItemsForBlock(maxItems) {
    const limit = typeof maxItems === "number" && maxItems > 0 ? maxItems : 5;
    const currentId = state.article ? state.article.id : "";
    const pool = (state.allArticles || []).filter(function (a) {
      return a.id !== currentId && a.status === "published";
    });
    return pool.slice(0, limit).map(function (a) {
      return {
        article_id: a.id,
        title: a.title || "Ohne Titel",
        subtitle: a.subtitle || "",
        date: a.publication_date || (a.updated_at ? a.updated_at.split("T")[0] : ""),
        category: a.category || "",
        url: a.url || "",
        enabled: true,
      };
    });
  }

  // ==========================================================================
  // Undo-Stack & Interaktive Toast-Notification
  // ==========================================================================

  const MAX_UNDO_STACK = 25;
  let undoToastTimer = null;

  function pushUndo(entry) {
    if (!state.undoStack) state.undoStack = [];
    state.undoStack.push(entry);
    if (state.undoStack.length > MAX_UNDO_STACK) {
      state.undoStack.shift();
    }
    updateUndoUi();
    showUndoToast(entry);
  }

  function clearUndoStack() {
    state.undoStack = [];
    updateUndoUi();
    hideUndoToast();
  }

  function updateUndoUi() {
    const btn = document.getElementById("btn-undo-action");
    if (!btn) return;
    const count = state.undoStack ? state.undoStack.length : 0;
    if (count > 0) {
      btn.disabled = false;
      btn.classList.remove("btn-undo-disabled");
      btn.classList.add("btn-undo-active");
      const last = state.undoStack[state.undoStack.length - 1];
      btn.innerHTML = `<span class="undo-icon" style="font-size:14px;margin-right:4px;">↩</span>Rückgängig <span class="undo-count-badge">${count}</span>`;
      btn.title = `«${last.description}» rückgängig machen (Ctrl+Z)`;
    } else {
      btn.disabled = true;
      btn.classList.add("btn-undo-disabled");
      btn.classList.remove("btn-undo-active");
      btn.innerHTML = `<span class="undo-icon" style="font-size:14px;margin-right:4px;">↩</span>Rückgängig`;
      btn.title = "Keine Aktionen zum Rückgängig machen vorhanden (Ctrl+Z)";
    }
  }

  function performUndo() {
    if (!state.undoStack || state.undoStack.length === 0) {
      return false;
    }
    if (!state.article) return false;
    if (!Array.isArray(state.article.blocks)) state.article.blocks = [];

    const entry = state.undoStack.pop();
    updateUndoUi();

    if (entry.type === "delete_blocks") {
      // Sortiere aufsteigend nach ursprünglichem Index, damit das Einfügen an korrekten Stellen erfolgt
      const sorted = entry.items.slice().sort(function (a, b) {
        return a.index - b.index;
      });
      const restoredIds = [];
      sorted.forEach(function (item) {
        const targetIdx = Math.min(Math.max(0, item.index), state.article.blocks.length);
        state.article.blocks.splice(targetIdx, 0, deepClone(item.block));
        restoredIds.push(item.block.id);
      });

      renderBlocksCanvas();
      markDirty();
      updateFloatingSelectionBar();

      // Zum ersten wiederhergestellten Block scrollen und dezent hervorheben
      if (restoredIds.length > 0) {
        setTimeout(function () {
          const firstEl = document.querySelector('[data-block-id="' + restoredIds[0] + '"]');
          if (firstEl) {
            firstEl.scrollIntoView({ behavior: "smooth", block: "center" });
            firstEl.classList.add("block-restored-highlight");
            setTimeout(function () {
              firstEl.classList.remove("block-restored-highlight");
            }, 1800);
          }
        }, 60);
      }

      const countRemaining = state.undoStack ? state.undoStack.length : 0;
      const countRestored = restoredIds.length;
      const label = countRestored === 1 ? "Block wiederhergestellt" : `${countRestored} Blöcke wiederhergestellt`;
      showRestoredToast(label, countRemaining);
      return true;
    }
    return false;
  }

  function ensureUndoToastContainer() {
    let container = document.getElementById("cms-undo-toast");
    if (!container) {
      container = document.createElement("div");
      container.id = "cms-undo-toast";
      container.className = "cms-undo-toast";
      document.body.appendChild(container);
    }
    return container;
  }

  function hideUndoToast() {
    if (undoToastTimer) {
      clearTimeout(undoToastTimer);
      undoToastTimer = null;
    }
    const container = document.getElementById("cms-undo-toast");
    if (container) {
      container.classList.remove("is-visible");
    }
  }

  function showUndoToast(entry) {
    const container = ensureUndoToastContainer();
    if (undoToastTimer) {
      clearTimeout(undoToastTimer);
      undoToastTimer = null;
    }

    const DURATION = 9000; // 9 Sekunden Anzeigedauer

    container.innerHTML = `
      <div class="cms-undo-toast-inner">
        <div class="cms-undo-toast-content">
          <span class="cms-undo-toast-icon">🗑️</span>
          <span class="cms-undo-toast-message">${escapeHtml(entry.description || "Inhaltsblock gelöscht")}</span>
        </div>
        <div class="cms-undo-toast-actions">
          <button type="button" class="btn-undo-toast-action" id="btn-toast-undo-click">
            ↩ Rückgängig <kbd>Ctrl+Z</kbd>
          </button>
          <button type="button" class="btn-undo-toast-close" title="Schliessen" id="btn-toast-undo-dismiss">✕</button>
        </div>
        <div class="cms-undo-toast-progress-track">
          <div class="cms-undo-toast-progress-bar" id="cms-undo-progress-bar"></div>
        </div>
      </div>
    `;

    const undoBtn = container.querySelector("#btn-toast-undo-click");
    if (undoBtn) {
      undoBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        performUndo();
      });
    }

    const closeBtn = container.querySelector("#btn-toast-undo-dismiss");
    if (closeBtn) {
      closeBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        hideUndoToast();
      });
    }

    container.classList.add("is-visible");

    const bar = container.querySelector("#cms-undo-progress-bar");
    if (bar) {
      bar.style.width = "100%";
      bar.style.transition = `width ${DURATION}ms linear`;
      void bar.offsetWidth; // Reflow erzwingen
      bar.style.width = "0%";
    }

    undoToastTimer = setTimeout(function () {
      hideUndoToast();
    }, DURATION);
  }

  function showRestoredToast(message, countRemaining) {
    const container = ensureUndoToastContainer();
    if (undoToastTimer) {
      clearTimeout(undoToastTimer);
      undoToastTimer = null;
    }

    let extraHtml = "";
    if (countRemaining > 0) {
      extraHtml = `
        <div class="cms-undo-toast-actions">
          <button type="button" class="btn-undo-toast-action" id="btn-toast-undo-next">
            Nochmals rückgängig (${countRemaining})
          </button>
        </div>
      `;
    }

    container.innerHTML = `
      <div class="cms-undo-toast-inner cms-undo-toast-success">
        <div class="cms-undo-toast-content">
          <span class="cms-undo-toast-icon">✓</span>
          <span class="cms-undo-toast-message">${escapeHtml(message)}</span>
        </div>
        ${extraHtml}
      </div>
    `;

    const nextBtn = container.querySelector("#btn-toast-undo-next");
    if (nextBtn) {
      nextBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        performUndo();
      });
    }

    container.classList.add("is-visible");

    undoToastTimer = setTimeout(function () {
      hideUndoToast();
    }, countRemaining > 0 ? 5000 : 2200);
  }

  function getActiveFocusedBlockId() {
    const active = document.activeElement;
    if (!active) return "";
    const card = active.closest(".cms-block-card");
    return card && card.dataset && card.dataset.blockId ? card.dataset.blockId : "";
  }

  function notifyFocusTarget(targetId) {
    if (state.currentFocusedTarget === targetId) return;
    state.currentFocusedTarget = targetId;
    if (window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue(
        "lukb_collab_focus",
        { target: targetId, ts: Date.now() },
        { priority: "event" }
      );
    }
  }

  function uid(prefix) {
    return (prefix || "blk") + "_" + Math.random().toString(36).substring(2, 10);
  }

  function setAutosaveIndicator(mode, text) {
    const pill = document.getElementById("lukb-autosave-pill");
    const label = document.getElementById("lukb-autosave-text");
    if (!pill || !label) return;
    pill.classList.remove("status-dirty", "status-saving", "status-saved");
    if (mode === "dirty") {
      pill.classList.add("status-dirty");
    } else if (mode === "saving") {
      pill.classList.add("status-saving");
    } else {
      pill.classList.add("status-saved");
    }
    label.textContent = text;
  }

  let statsDebounceTimer = null;
  let previewDebounceTimer = null;

  function markDirty() {
    if (!state.article) return;
    state.isDirty = true;
    state.editSeq += 1;
    setAutosaveIndicator("dirty", "Ungespeicherte Änderungen …");
    if (statsDebounceTimer) {
      clearTimeout(statsDebounceTimer);
    }
    statsDebounceTimer = setTimeout(updateLiveStatsCounter, 500);

    // 1. Schneller Live-Preview Debounce (350 ms): Entkoppelt von DB-Speicherung für sofortiges PDF-Feedback
    if (state.autoPreview) {
      if (previewDebounceTimer) {
        clearTimeout(previewDebounceTimer);
      }
      previewDebounceTimer = setTimeout(function () {
        previewDebounceTimer = null;
        requestLivePreview();
      }, 350);
    }

    // 2. Ruhiger DB-Autosave Debounce (3000 ms): Persistiert im Hintergrund in die SQL-Datenbank
    if (state.autosaveTimer) {
      clearTimeout(state.autosaveTimer);
    }
    state.autosaveTimer = setTimeout(function () {
      flushAutosave(false);
    }, 3000);
  }

  function requestLivePreview() {
    if (!state.article || !state.autoPreview) return;
    if (previewDebounceTimer) {
      clearTimeout(previewDebounceTimer);
      previewDebounceTimer = null;
    }
    state.lastPreviewedSeq = state.editSeq;
    const currentMode = state.previewMode || "pdf";
    sendShinyEvent("lukb_request_live_preview", {
      article: state.article,
      preview_mode: currentMode,
    });
  }

  function updateLiveStatsCounter() {
    const counterEl = document.getElementById("lukb-stats-counter");
    if (!counterEl || !state.article) return;

    let totalWords = 0;
    const countText = (str) => {
      if (!str) return;
      const clean = String(str).replace(/<[^>]+>/g, " ").trim();
      if (!clean) return;
      const words = clean.split(/\s+/).filter(Boolean);
      totalWords += words.length;
    };

    const meta = state.article.metadata || {};
    countText(meta.title);
    countText(meta.subtitle);
    countText(meta.lead);

    let estPages = 0;
    const blocks = state.article.blocks || [];
    blocks.forEach((b) => {
      if (b.type === "heading") {
        countText(b.text);
      } else if (b.type === "richtext") {
        countText(b.html);
      } else if (b.type === "callout") {
        countText(b.title);
        countText(b.html);
        estPages += 0.12;
      } else if (b.type === "quote") {
        countText(b.quote);
        countText(b.author);
        countText(b.source);
        estPages += (b.layout === "full" ? 0.2 : 0.12);
      } else if (b.type === "table") {
        countText(b.title);
        countText(b.subtitle);
        (b.rows || []).forEach(r => Object.values(r).forEach(v => countText(String(v))));
        estPages += (b.layout === "full" ? 0.38 : 0.22);
      } else if (b.type === "figure" || b.type === "db_chart" || b.type === "custom_chart") {
        countText(b.title);
        countText(b.subtitle);
        estPages += (b.layout === "full" ? 0.45 : 0.25);
      } else if (b.type === "spacer") {
        estPages += ((b.height_mm || 8) / 250);
      } else if (b.type === "footnotes") {
        countText(b.title);
        (b.items || []).forEach(it => countText(it.text));
        estPages += 0.12;
      } else if (b.type === "glossary") {
        countText(b.title);
        (b.custom_items || []).forEach(it => {
          countText(it.term);
          countText(it.definition);
        });
        estPages += (b.layout === "full" ? 0.25 : 0.15);
      }
    });

    estPages += (totalWords / 500);

    const readingTimeMin = Math.max(1, Math.round((totalWords / 200) * 10) / 10);
    const pagesFormatted = (Math.max(0.4, Math.round(estPages * 10) / 10)).toFixed(1);

    counterEl.textContent = `📊 ${totalWords} Wörter · ~${readingTimeMin} Min. · ca. ${pagesFormatted} A4-Seiten`;
  }

  function flushAutosave(createRevision, revisionNote) {
    if (!state.article) return;
    if (state.autosaveTimer) {
      clearTimeout(state.autosaveTimer);
      state.autosaveTimer = null;
    }
    if (previewDebounceTimer) {
      clearTimeout(previewDebounceTimer);
      previewDebounceTimer = null;
    }
    state.isDirty = false;
    setAutosaveIndicator("saving", "Speichert in Datenbank …");

    const knownAssets = Object.keys(state.assetCache || {});
    const currentMode = state.previewMode || "pdf";
    const previewAlreadyCurrent = state.lastPreviewedSeq === state.editSeq;

    sendShinyEvent("lukb_autosave_payload", {
      article: state.article,
      base_article: state.baseArticle,
      create_revision: !!createRevision,
      revision_note: revisionNote || "",
      auto_preview: state.autoPreview,
      preview_mode: currentMode,
      preview_already_current: previewAlreadyCurrent,
      known_asset_ids: knownAssets,
    });
  }

  // ==========================================================================
  // Metadaten-Formular Synchronisation
  // ==========================================================================


  // ==========================================================================
  // Block-Fabrik & Drag-and-Drop Canvas
  // ==========================================================================

  function createDefaultBlock(type) {
    if (type === "heading") {
      return {
        id: uid("blk"),
        type: "heading",
        level: 2,
        text: "Neue Zwischenüberschrift",
      };
    }
    if (type === "figure") {
      return {
        id: uid("blk"),
        type: "figure",
        title: "Titel der Grafik",
        subtitle: "Untertitel / Einheit / Zeitraum",
        source: "Quelle: Bloomberg, LUKB Investment Office",
        asset_id: "",
        layout: "column",
        full_position: "auto",
      };
    }
    if (type === "db_chart") {
      return {
        id: uid("blk"),
        type: "db_chart",
        title: "Zeitreihen-Vergleich",
        subtitle: "Entwicklung seit Startdatum",
        source: "Quelle: Bloomberg, LUKB Investment Office",
        layout: "column",
        full_position: "auto",
        chart_height_mm: 36,
        start_date: "2022-01-01",
        rebasing: "none",
        palette: "lukb_classic",
        legend_columns: null,
        series: [
          { ticker: "SNB_RATE", chart_type: "line", chart_types: ["line"], label: "" },
          { ticker: "ECB_RATE", chart_type: "line", chart_types: ["line"], label: "" },
          { ticker: "FED_RATE", chart_type: "line", chart_types: ["line"], label: "" },
        ],
        asset_id: "",
      };
    }
    if (type === "custom_chart") {
      return {
        id: uid("blk"),
        type: "custom_chart",
        title: "Titel der Grafik",
        subtitle: "Untertitel / Einheit / Zeitraum",
        source: "Quelle: LUKB Investment Office",
        layout: "column",
        full_position: "auto",
        chart_height_mm: 36,
        palette: "lukb_classic",
        chart_type: "category_bar",
        has_header: true,
        x_col: "Kategorie",
        series: [
          { field: "Aktuell", label: "Aktuell", chart_type: "bar", enabled: true },
          { field: "Vorjahr", label: "Vorjahr", chart_type: "bar", enabled: true },
        ],
        raw_tsv: "Kategorie\tAktuell\tVorjahr\nAktien Schweiz\t14.5\t12.0\nAktien Global\t18.2\t15.5\nObligationen CHF\t2.5\t1.8\nLiquidität\t0.5\t0.2",
        data_columns: ["Kategorie", "Aktuell", "Vorjahr"],
        data_rows: [
          ["Aktien Schweiz", "14.5", "12.0"],
          ["Aktien Global", "18.2", "15.5"],
          ["Obligationen CHF", "2.5", "1.8"],
          ["Liquidität", "0.5", "0.2"],
        ],
        doughnut_hole_pct: 55,
        bar_mode: "grouped",
      };
    }
    if (type === "table") {
      return {
        id: uid("blk"),
        type: "table",
        title: "Titel der Tabelle",
        subtitle: "Untertitel / Einheit",
        source: "Quelle: LUKB Investment Office",
        layout: "column",
        full_position: "auto",
        show_header: true,
        highlight_last_row: false,
        font_size_step: 0,
        columns: [
          { field: "col_1", title: "Kennzahl / Sektor", align: "left", width: 33.4 },
          { field: "col_2", title: "Aktuell", align: "right", width: 33.3 },
          { field: "col_3", title: "Prognose 12M", align: "right", width: 33.3 },
        ],
        rows: [
          { col_1: "Position A", col_2: "10.0 %", col_3: "11.5 %" },
          { col_1: "Position B", col_2: "15.0 %", col_3: "16.0 %" },
        ],
      };
    }
    if (type === "media_text") {
      return {
        id: uid("blk"),
        type: "media_text",
        title: "",
        layout: "full",
        full_position: "inline",
        media_type: "figure",
        media_position: "auto",
        media_width_pct: 30,
        aside_width_pct: 26,
        style_preset: "plain",
        html: "<p><strong>Kernaussage:</strong> Beschreibender Text neben oder unter dem Medium …</p>",
        aside_html: "",
        media: {
          id: uid("blk"),
          type: "figure",
          title: "",
          subtitle: "",
          source: "",
          asset_id: "",
          layout: "column",
          full_position: "auto",
        },
      };
    }
    if (type === "callout") {
      return {
        id: uid("blk"),
        type: "callout",
        title: "Kernaussagen",
        html: "<ul><li>Erste zentrale Erkenntnis für Anlegerinnen und Anleger</li><li>Zweite Schlussfolgerung</li></ul>",
      };
    }
    if (type === "box_start") {
      return {
        id: uid("blk"),
        type: "box_start",
      };
    }
    if (type === "box_end") {
      return {
        id: uid("blk"),
        type: "box_end",
      };
    }
    if (type === "spacer") {
      return {
        id: uid("blk"),
        type: "spacer",
        height_mm: 8,
      };
    }
    if (type === "colbreak") {
      return {
        id: uid("blk"),
        type: "colbreak",
      };
    }
    if (type === "quote") {
      return {
        id: uid("blk"),
        type: "quote",
        quote: "Die Schweizer Wirtschaft beweist trotz globalem Gegenwind beachtliche Robustheit.",
        author: "Thomas Grüter",
        source: "Chief Investment Officer",
        layout: "column",
      };
    }
    if (type === "divider") {
      return {
        id: uid("blk"),
        type: "divider",
        style: "solid",
      };
    }
    if (type === "footnotes") {
      return {
        id: uid("blk"),
        type: "footnotes",
        title: "Anmerkungen & Quellen",
        items: [
          { num: "1", text: "Quelle: Bloomberg, LUKB Investment Office" },
        ],
        layout: "column",
      };
    }
    if (type === "glossary") {
      return {
        id: uid("blk"),
        type: "glossary",
        title: "Glossar & Begriffserklärungen",
        auto_collect: true,
        custom_items: [],
        layout: "column",
      };
    }
    if (type === "publications") {
      return {
        id: uid("blk"),
        type: "publications",
        title: "Weitere Publikationen",
        items: getLatestPublishedItemsForBlock(5),
        layout: "column",
      };
    }
    return {
      id: uid("blk"),
      type: "richtext",
      html: "<p>Neuer Textabsatz …</p>",
    };
  }

  function getBlockTypeLabel(type) {
    switch (type) {
      case "heading":
        return "Überschrift";
      case "richtext":
        return "Text-Absatz";
      case "figure":
        return "Grafik-Container (Upload)";
      case "db_chart":
        return "DB-Chart (Zeitreihe aus ts_db)";
      case "custom_chart":
        return "Daten-Diagramm (Excel / Zwischenablage)";
      case "table":
        return "Daten-Tabelle";
      case "media_text":
        return "Media & Text (Kombi-Block)";
      case "callout":
        return "Kernaussagen / Callout";
      case "box_start":
        return "▼ START: Farbliche Textbox (alle Blöcke bis ENDE liegen in dieser Box)";
      case "box_end":
        return "▲ ENDE: Farbliche Textbox";
      case "spacer":
        return "Vertikaler Abstand (Spacer)";
      case "colbreak":
        return "Manueller Spaltenumbruch";
      case "quote":
        return "Zitat / Pull-Quote";
      case "divider":
        return "Horizontale Trennlinie";
      case "footnotes":
        return "Fussnoten- & Quellenapparat";
      case "glossary":
        return "Glossar-Verzeichnis";
      case "publications":
        return "Weitere Publikationen";
      default:
        return "Inhaltsblock";
    }
  }

  // ==========================================================================
  // Block-Katalog, Inline-Inserter & Multi-Select Logik
  // ==========================================================================

  const BLOCK_TYPE_CATALOG = [
    {
      group: "Text & Inhalt",
      items: [
        { type: "richtext", label: "Text-Absatz", icon: "📝" },
        { type: "heading", label: "Überschrift", icon: "🔤" },
        { type: "callout", label: "Kernaussagen", icon: "💡" },
        { type: "quote", label: "Zitat / Pull-Quote", icon: "💬" },
      ],
    },
    {
      group: "Daten & Grafiken",
      items: [
        { type: "db_chart", label: "DB-Chart (Zeitreihe)", icon: "📈" },
        { type: "custom_chart", label: "Daten-Chart (Excel / TSV)", icon: "📊" },
        { type: "figure", label: "Grafik-Upload", icon: "🖼" },
        { type: "table", label: "Tabelle (Excel)", icon: "📋" },
        { type: "media_text", label: "Media & Text (Kombi)", icon: "📰" },
      ],
    },
    {
      group: "Layout & Struktur",
      items: [
        { type: "textbox_pair", label: "Farbliche Textbox", icon: "📦" },
        { type: "spacer", label: "Abstand (Spacer)", icon: "↕" },
        { type: "colbreak", label: "Spaltenumbruch", icon: "⇥" },
        { type: "divider", label: "Trennlinie", icon: "➖" },
      ],
    },
    {
      group: "Verzeichnisse & Anhänge",
      items: [
        { type: "footnotes", label: "Fussnoten & Quellen", icon: "📑" },
        { type: "glossary", label: "Glossar", icon: "📖" },
        { type: "publications", label: "Weitere Publikationen", icon: "📰" },
      ],
    },
  ];


  function closeFigureContextMenu() {
    const existing = document.getElementById("active-figure-context-menu");
    if (existing && existing.parentNode) {
      existing.parentNode.removeChild(existing);
    }
  }

  // Kontextmenü schliessen bei Klick ausserhalb oder Esc
  document.addEventListener("click", function (e) {
    if (!e.target.closest("#active-figure-context-menu")) {
      closeFigureContextMenu();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeFigureContextMenu();
    }
  });

  function createFullLayoutControl(blk, onChanged) {
    if (!blk.full_position) {
      blk.full_position = "auto";
    }
    const layoutWrap = document.createElement("div");
    const layoutLbl = document.createElement("label");
    layoutLbl.className = "field-label";
    layoutLbl.textContent = "Satz-Breite im PDF";

    const layoutSel = document.createElement("select");
    layoutSel.className = "cms-select";
    [
      { val: "column", label: "1-spaltig (Spaltenbreite)" },
      { val: "full", label: "2-spaltig (Seitenbreite)" },
    ].forEach(function (o) {
      const opt = document.createElement("option");
      opt.value = o.val;
      opt.textContent = o.label;
      if ((blk.layout || "column") === o.val) opt.selected = true;
      layoutSel.appendChild(opt);
    });

    const posWrap = document.createElement("div");
    posWrap.style.marginTop = "6px";
    posWrap.style.display = (blk.layout || "column") === "full" ? "block" : "none";

    const posLbl = document.createElement("label");
    posLbl.className = "field-label";
    posLbl.style.fontSize = "11px";
    posLbl.textContent = "Position (2-spaltig)";

    const posSel = document.createElement("select");
    posSel.className = "cms-select";
    posSel.style.fontSize = "12px";
    posSel.style.padding = "4px 7px";
    [
      { val: "auto", label: "Auto (S.1 unten / S.2+ oben)" },
      { val: "bottom", label: "Seitenende (Unten)" },
      { val: "top", label: "Seitenanfang (Oben)" },
      { val: "inline", label: "Im Textfluss (Inline)" },
    ].forEach(function (o) {
      const opt = document.createElement("option");
      opt.value = o.val;
      opt.textContent = o.label;
      if ((blk.full_position || "auto") === o.val) opt.selected = true;
      posSel.appendChild(opt);
    });

    layoutSel.addEventListener("change", function () {
      blk.layout = layoutSel.value;
      posWrap.style.display = blk.layout === "full" ? "block" : "none";
      anchorWrap.style.display = blk.layout === "column" ? "block" : "none";
      if (onChanged) onChanged();
      markDirty();
      if (typeof window.lukbRefreshCanvasDecorations === "function") {
        window.lukbRefreshCanvasDecorations();
      }
    });

    posSel.addEventListener("change", function () {
      blk.full_position = posSel.value;
      if (onChanged) onChanged();
      markDirty();
    });

    posWrap.appendChild(posLbl);
    posWrap.appendChild(posSel);

    const anchorWrap = document.createElement("div");
    anchorWrap.style.marginTop = "6px";
    anchorWrap.style.display = (blk.layout || "column") === "column" ? "block" : "none";

    const anchorLbl = document.createElement("label");
    anchorLbl.className = "field-label";
    anchorLbl.style.fontSize = "11px";
    anchorLbl.textContent = "⚓ Verankerung (Tufte-Randspalte)";

    const anchorSel = document.createElement("select");
    anchorSel.className = "cms-select";
    anchorSel.style.fontSize = "12px";
    anchorSel.style.padding = "4px 7px";

    function populateAnchorOptions() {
      anchorSel.innerHTML = "";
      const defaultOpt = document.createElement("option");
      defaultOpt.value = "";
      defaultOpt.textContent = "Automatisch (Vorhergehender Absatz)";
      anchorSel.appendChild(defaultOpt);

      const allBlocks = (state.article && state.article.blocks) ? state.article.blocks : [];
      let foundMatch = false;
      allBlocks.forEach(function (b, bIdx) {
        if (!b || b.id === blk.id) return;
        if (b.type === "spacer" || b.type === "colbreak" || b.type === "divider" || b.type === "box_start" || b.type === "box_end") return;
        if ((b.type === "figure" || b.type === "db_chart" || b.type === "custom_chart" || b.type === "table" || b.type === "media_text") && (b.layout || "column") === "column") return;

        let label = (bIdx + 1) + ". ";
        if (b.type === "heading") {
          const txt = (b.text || "").trim();
          label += "Überschrift: " + (txt.length > 28 ? txt.slice(0, 28) + "…" : (txt || "(leer)"));
        } else if (b.type === "richtext") {
          const txt = (b.html || "")
            .replace(/<[^>]+>/g, " ")
            .replace(/&nbsp;/gi, " ")
            .replace(/\s+/g, " ")
            .trim();
          label += "Absatz: " + (txt.length > 28 ? txt.slice(0, 28) + "…" : (txt || "(leer)"));
        } else if (b.type === "callout") {
          const txt = (b.title || "").trim();
          label += "Kernaussagen: " + (txt.length > 22 ? txt.slice(0, 22) + "…" : (txt || "Box"));
        } else if (b.type === "quote") {
          const txt = (b.quote || "").trim();
          label += "Zitat: " + (txt.length > 22 ? txt.slice(0, 22) + "…" : (txt || "Zitat"));
        } else {
          label += (b.type || "Block");
        }

        const opt = document.createElement("option");
        opt.value = b.id;
        opt.textContent = label;
        if (blk.anchor_to === b.id) {
          opt.selected = true;
          foundMatch = true;
        }
        anchorSel.appendChild(opt);
      });

      if (!blk.anchor_to || !foundMatch) {
        defaultOpt.selected = true;
      }
    }

    populateAnchorOptions();

    anchorSel.addEventListener("change", function () {
      blk.anchor_to = anchorSel.value || null;
      if (onChanged) onChanged();
      markDirty();
      if (typeof window.lukbRefreshCanvasDecorations === "function") {
        window.lukbRefreshCanvasDecorations();
      }
    });

    anchorWrap.appendChild(anchorLbl);
    anchorWrap.appendChild(anchorSel);

    layoutWrap.appendChild(layoutLbl);
    layoutWrap.appendChild(layoutSel);
    layoutWrap.appendChild(posWrap);
    layoutWrap.appendChild(anchorWrap);
    return layoutWrap;
  }


  Object.assign(E, {
    BLOCK_TYPE_CATALOG: BLOCK_TYPE_CATALOG,
    CHART_PALETTES: CHART_PALETTES,
    DEFAULT_CHART_HEIGHT_PRESETS: DEFAULT_CHART_HEIGHT_PRESETS,
    MAX_UNDO_STACK: MAX_UNDO_STACK,
    clearUndoStack: clearUndoStack,
    closeFigureContextMenu: closeFigureContextMenu,
    createChartHeightBar: createChartHeightBar,
    createChartPaletteBar: createChartPaletteBar,
    createDefaultBlock: createDefaultBlock,
    createFullLayoutControl: createFullLayoutControl,
    createSimpleLayoutSelect: createSimpleLayoutSelect,
    deepClone: deepClone,
    ensureUndoToastContainer: ensureUndoToastContainer,
    escapeHtml: escapeHtml,
    flushAutosave: flushAutosave,
    getActiveFocusedBlockId: getActiveFocusedBlockId,
    getBlockTypeLabel: getBlockTypeLabel,
    getLatestPublishedItemsForBlock: getLatestPublishedItemsForBlock,
    hideUndoToast: hideUndoToast,
    markDirty: markDirty,
    notifyFocusTarget: notifyFocusTarget,
    parseDelimitedText: parseDelimitedText,
    performUndo: performUndo,
    pushUndo: pushUndo,
    requestLivePreview: requestLivePreview,
    sanitizeRichTextHtml: sanitizeRichTextHtml,
    sendShinyEvent: sendShinyEvent,
    setAutosaveIndicator: setAutosaveIndicator,
    showRestoredToast: showRestoredToast,
    showUndoToast: showUndoToast,
    state: state,
    statsDebounceTimer: statsDebounceTimer,
    uid: uid,
    undoToastTimer: undoToastTimer,
    updateLiveStatsCounter: updateLiveStatsCounter,
    updateUndoUi: updateUndoUi,
  });
})();
