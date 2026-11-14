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
    isDirty: false,
    autosaveTimer: null,
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

  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
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

  function markDirty() {
    if (!state.article) return;
    state.isDirty = true;
    setAutosaveIndicator("dirty", "Ungespeicherte Änderungen …");
    if (statsDebounceTimer) {
      clearTimeout(statsDebounceTimer);
    }
    statsDebounceTimer = setTimeout(updateLiveStatsCounter, 250);
    if (state.autosaveTimer) {
      clearTimeout(state.autosaveTimer);
    }
    state.autosaveTimer = setTimeout(function () {
      flushAutosave(false);
    }, 1000);
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
      } else if (b.type === "figure" || b.type === "db_chart") {
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
    state.isDirty = false;
    setAutosaveIndicator("saving", "Speichert in Datenbank …");

    if (window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue(
        "lukb_autosave_payload",
        {
          article: state.article,
          base_article: state.baseArticle,
          create_revision: !!createRevision,
          revision_note: revisionNote || "",
          auto_preview: state.autoPreview,
          ts: Date.now(),
        },
        { priority: "event" }
      );
    }
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
        series: [
          { ticker: "SNB_RATE", chart_type: "line", chart_types: ["line"], label: "" },
          { ticker: "ECB_RATE", chart_type: "line", chart_types: ["line"], label: "" },
          { ticker: "FED_RATE", chart_type: "line", chart_types: ["line"], label: "" },
        ],
        asset_id: "",
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
      const currentId = state.article ? state.article.id : "";
      const pool = (state.allArticles || []).filter(function (a) {
        return a.id !== currentId && a.status === "published";
      });
      const initialItems = pool.slice(0, 5).map(function (a) {
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
      return {
        id: uid("blk"),
        type: "publications",
        title: "Weitere Publikationen",
        items: initialItems,
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
      case "table":
        return "Daten-Tabelle";
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
        { type: "figure", label: "Grafik-Upload", icon: "🖼" },
        { type: "table", label: "Tabelle (Excel)", icon: "📊" },
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
      if (onChanged) onChanged();
      markDirty();
    });

    posSel.addEventListener("change", function () {
      blk.full_position = posSel.value;
      if (onChanged) onChanged();
      markDirty();
    });

    posWrap.appendChild(posLbl);
    posWrap.appendChild(posSel);

    layoutWrap.appendChild(layoutLbl);
    layoutWrap.appendChild(layoutSel);
    layoutWrap.appendChild(posWrap);
    return layoutWrap;
  }


  Object.assign(E, {
    BLOCK_TYPE_CATALOG: BLOCK_TYPE_CATALOG,
    MAX_UNDO_STACK: MAX_UNDO_STACK,
    clearUndoStack: clearUndoStack,
    closeFigureContextMenu: closeFigureContextMenu,
    createDefaultBlock: createDefaultBlock,
    createFullLayoutControl: createFullLayoutControl,
    deepClone: deepClone,
    ensureUndoToastContainer: ensureUndoToastContainer,
    escapeHtml: escapeHtml,
    flushAutosave: flushAutosave,
    getActiveFocusedBlockId: getActiveFocusedBlockId,
    getBlockTypeLabel: getBlockTypeLabel,
    hideUndoToast: hideUndoToast,
    markDirty: markDirty,
    notifyFocusTarget: notifyFocusTarget,
    performUndo: performUndo,
    pushUndo: pushUndo,
    sanitizeRichTextHtml: sanitizeRichTextHtml,
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
