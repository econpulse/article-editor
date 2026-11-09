/**
 * LUKB Investment Office — Interaktiver Drag-and-Drop Block-Editor & Autosave-Engine
 * Arbeitet 100% ohne Node.js/Vite-Build-Server direkt mit Shiny for Python auf Posit Connect.
 */

(function () {
  "use strict";

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
    previewMode: "pdf", // "pdf" (Typst SVG) | "web" (HTML5)
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

  function markDirty() {
    if (!state.article) return;
    state.isDirty = true;
    setAutosaveIndicator("dirty", "Ungespeicherte Änderungen …");
    updateLiveStatsCounter();
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
          ts: Date.now(),
        },
        { priority: "event" }
      );
    }
  }

  // ==========================================================================
  // Metadaten-Formular Synchronisation
  // ==========================================================================

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
      nameInput.placeholder = "Name (z.B. Dr. Reto Krähenbühl)";
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

  // ==========================================================================
  // Block-Fabrik & Drag-and-Drop Canvas
  // ==========================================================================

  function createDefaultBlock(type) {
    if (type === "heading") {
      return {
        id: uid("blk"),
        type: "heading",
        level: 1,
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
        chart_height_mm: 36,
        start_date: "2022-01-01",
        rebasing: "none",
        series: [
          { ticker: "SNB_RATE", chart_type: "step", label: "" },
          { ticker: "ECB_RATE", chart_type: "step", label: "" },
          { ticker: "FED_RATE", chart_type: "step", label: "" },
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
        highlight_last_row: false,
        columns: [
          { field: "col_1", title: "Kennzahl / Sektor", align: "left" },
          { field: "col_2", title: "Aktuell", align: "right" },
          { field: "col_3", title: "Prognose 12M", align: "right" },
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
      default:
        return "Inhaltsblock";
    }
  }

  function renderBlocksCanvas() {
    const canvas = document.getElementById("lukb-blocks-canvas");
    if (!canvas || !state.article) return;

    canvas.innerHTML = "";
    const blocks = state.article.blocks || [];

    let insideBox = false;
    blocks.forEach(function (blk, index) {
      if (blk.type === "box_start") {
        insideBox = true;
      }
      const card = buildBlockCardElement(blk, index, insideBox);
      canvas.appendChild(card);
      if (blk.type === "box_end") {
        insideBox = false;
      }
    });

    initSortable(canvas);
  }

  function initSortable(canvas) {
    if (state.sortableInstance) {
      state.sortableInstance.destroy();
      state.sortableInstance = null;
    }
    if (typeof window.Sortable === "undefined") return;

    state.sortableInstance = window.Sortable.create(canvas, {
      handle: ".block-drag-handle",
      animation: 180,
      ghostClass: "sortable-ghost",
      dragClass: "sortable-drag",
      onEnd: function (evt) {
        if (evt.oldIndex === evt.newIndex) return;
        const moved = state.article.blocks.splice(evt.oldIndex, 1)[0];
        state.article.blocks.splice(evt.newIndex, 0, moved);
        renderBlocksCanvas();
        markDirty();
      },
    });
  }

  function buildBlockCardElement(blk, index, insideBox) {
    const isMarker = blk.type === "box_start" || blk.type === "box_end";
    const card = document.createElement("div");
    card.className =
      "cms-block-card block-type-" +
      blk.type +
      (insideBox && !isMarker ? " block-inside-textbox" : "") +
      (isMarker ? " block-textbox-marker" : "");
    card.dataset.blockId = blk.id;

    // Header Bar
    const header = document.createElement("div");
    header.className = "block-header-bar";

    const headerLeft = document.createElement("div");
    headerLeft.className = "block-header-left";

    const dragHandle = document.createElement("span");
    dragHandle.className = "block-drag-handle";
    dragHandle.title = "Ziehen zum Umsortieren (Drag & Drop)";
    dragHandle.textContent = "⋮⋮";

    const typePill = document.createElement("span");
    typePill.className = "block-type-pill";
    typePill.textContent = (index + 1) + ". " + getBlockTypeLabel(blk.type);

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
    upBtn.className = "btn-icon-only";
    upBtn.title = "Block nach oben schieben";
    upBtn.textContent = "↑";
    upBtn.disabled = index === 0;
    upBtn.addEventListener("click", function () {
      if (index <= 0) return;
      const tmp = state.article.blocks[index - 1];
      state.article.blocks[index - 1] = state.article.blocks[index];
      state.article.blocks[index] = tmp;
      renderBlocksCanvas();
      markDirty();
    });

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "btn-icon-only";
    downBtn.title = "Block nach unten schieben";
    downBtn.textContent = "↓";
    downBtn.disabled = index === state.article.blocks.length - 1;
    downBtn.addEventListener("click", function () {
      if (index >= state.article.blocks.length - 1) return;
      const tmp = state.article.blocks[index + 1];
      state.article.blocks[index + 1] = state.article.blocks[index];
      state.article.blocks[index] = tmp;
      renderBlocksCanvas();
      markDirty();
    });

    const dupBtn = document.createElement("button");
    dupBtn.type = "button";
    dupBtn.className = "btn-icon-only";
    dupBtn.title = "Block duplizieren";
    dupBtn.textContent = "⧉";
    dupBtn.addEventListener("click", function () {
      const clone = JSON.parse(JSON.stringify(blk));
      clone.id = uid("blk");
      state.article.blocks.splice(index + 1, 0, clone);
      renderBlocksCanvas();
      markDirty();
    });

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "btn-icon-only danger";
    delBtn.title = "Block löschen";
    delBtn.textContent = "✕";
    delBtn.addEventListener("click", function () {
      state.article.blocks.splice(index, 1);
      renderBlocksCanvas();
      markDirty();
    });

    headerActions.appendChild(upBtn);
    headerActions.appendChild(downBtn);
    headerActions.appendChild(dupBtn);
    headerActions.appendChild(delBtn);

    header.appendChild(headerLeft);
    header.appendChild(headerActions);
    card.appendChild(header);

    if (isMarker) {
      return card;
    }

    // Body Content per Block Type
    const body = document.createElement("div");
    body.className = "block-body";

    if (blk.type === "heading") {
      buildHeadingBlockBody(body, blk);
    } else if (blk.type === "richtext") {
      buildRichTextBlockBody(body, blk);
    } else if (blk.type === "callout") {
      buildCalloutBlockBody(body, blk);
    } else if (blk.type === "figure") {
      buildFigureBlockBody(body, blk);
    } else if (blk.type === "db_chart") {
      buildDbChartBlockBody(body, blk);
    } else if (blk.type === "table") {
      buildTableBlockBody(body, blk);
    } else if (blk.type === "spacer") {
      buildSpacerBlockBody(body, blk);
    } else if (blk.type === "colbreak") {
      buildColbreakBlockBody(body, blk);
    } else if (blk.type === "quote") {
      buildQuoteBlockBody(body, blk);
    } else if (blk.type === "divider") {
      buildDividerBlockBody(body, blk);
    } else if (blk.type === "footnotes") {
      buildFootnotesBlockBody(body, blk);
    } else if (blk.type === "glossary") {
      buildGlossaryBlockBody(body, blk);
    }

    card.appendChild(body);
    return card;
  }

  // ==========================================================================
  // Spezifische Block-Editoren
  // ==========================================================================

  function buildQuoteBlockBody(container, blk) {
    const topRow = document.createElement("div");
    topRow.style.display = "flex";
    topRow.style.justifyContent = "space-between";
    topRow.style.alignItems = "center";
    topRow.style.marginBottom = "8px";

    const topLbl = document.createElement("label");
    topLbl.className = "field-label";
    topLbl.style.margin = "0";
    topLbl.textContent = "Zitat / Pull-Quote (LUKB Corporate Design)";

    const layoutSel = document.createElement("select");
    layoutSel.className = "cms-select";
    layoutSel.style.width = "180px";
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
    });

    topRow.appendChild(topLbl);
    topRow.appendChild(layoutSel);
    container.appendChild(topRow);

    const qWrap = document.createElement("div");
    qWrap.className = "quote-editor-box";
    qWrap.style.marginBottom = "10px";

    const qTextarea = document.createElement("textarea");
    qTextarea.className = "cms-textarea";
    qTextarea.rows = 3;
    qTextarea.style.fontStyle = "italic";
    qTextarea.style.fontSize = "13.5px";
    qTextarea.placeholder = "Zitattext eingeben (ohne Anführungszeichen, werden automatisch formatiert) …";
    qTextarea.value = blk.quote || "";
    qTextarea.addEventListener("input", function () {
      blk.quote = qTextarea.value;
      markDirty();
    });
    qWrap.appendChild(qTextarea);
    container.appendChild(qWrap);

    const metaGrid = document.createElement("div");
    metaGrid.style.display = "grid";
    metaGrid.style.gridTemplateColumns = "1fr 1fr";
    metaGrid.style.gap = "10px";

    const authWrap = document.createElement("div");
    const authLbl = document.createElement("label");
    authLbl.className = "field-label";
    authLbl.textContent = "Urheber / Zitatgeber (z.B. Name & Titel)";
    const authInp = document.createElement("input");
    authInp.type = "text";
    authInp.className = "cms-input font-medium";
    authInp.placeholder = "z.B. Thomas Grüter";
    authInp.value = blk.author || "";
    authInp.addEventListener("input", function () {
      blk.author = authInp.value;
      markDirty();
    });
    authWrap.appendChild(authLbl);
    authWrap.appendChild(authInp);

    const srcWrap = document.createElement("div");
    const srcLbl = document.createElement("label");
    srcLbl.className = "field-label";
    srcLbl.textContent = "Kontext / Quelle / Funktion";
    const srcInp = document.createElement("input");
    srcInp.type = "text";
    srcInp.className = "cms-input";
    srcInp.placeholder = "z.B. Chief Investment Officer";
    srcInp.value = blk.source || "";
    srcInp.addEventListener("input", function () {
      blk.source = srcInp.value;
      markDirty();
    });
    srcWrap.appendChild(srcLbl);
    srcWrap.appendChild(srcInp);

    metaGrid.appendChild(authWrap);
    metaGrid.appendChild(srcWrap);
    container.appendChild(metaGrid);
  }

  function buildDividerBlockBody(container, blk) {
    if (!blk.style) blk.style = "solid";

    const row = document.createElement("div");
    row.className = "divider-style-selector";

    const lbl = document.createElement("label");
    lbl.className = "field-label";
    lbl.style.margin = "0";
    lbl.textContent = "Stil der Trennlinie:";
    row.appendChild(lbl);

    const btnGroup = document.createElement("div");
    btnGroup.style.display = "flex";
    btnGroup.style.gap = "6px";

    const previewLine = document.createElement("div");
    previewLine.className = "divider-preview-line";

    const updatePreview = () => {
      previewLine.style.borderTop =
        blk.style === "dashed"
          ? "2px dashed #94A3B8"
          : blk.style === "dots"
          ? "2.5px dotted #94A3B8"
          : "1.5px solid #94A3B8";
    };

    [
      { style: "solid", label: "Durchgezogen —" },
      { style: "dashed", label: "Gestrichelt - - -" },
      { style: "dots", label: "Gepunktet · · ·" },
    ].forEach(function (opt) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        "btn-lukb btn-lukb-sm " +
        (blk.style === opt.style ? "btn-lukb-navy" : "btn-lukb-ghost");
      btn.textContent = opt.label;
      btn.addEventListener("click", function () {
        blk.style = opt.style;
        Array.from(btnGroup.children).forEach(b => {
          b.className = "btn-lukb btn-lukb-sm btn-lukb-ghost";
        });
        btn.className = "btn-lukb btn-lukb-sm btn-lukb-navy";
        updatePreview();
        markDirty();
      });
      btnGroup.appendChild(btn);
    });

    row.appendChild(btnGroup);
    container.appendChild(row);
    updatePreview();
    container.appendChild(previewLine);
  }

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
    layoutSel.addEventListener("change", function () {
      blk.layout = layoutSel.value;
      markDirty();
    });
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

  function scanArticleGlossaryTerms() {
    if (!state.article || !Array.isArray(state.article.blocks)) return [];
    const termsMap = new Map();

    const scanHtml = (htmlStr) => {
      if (!htmlStr) return;
      const tmp = document.createElement("div");
      tmp.innerHTML = htmlStr;
      tmp.querySelectorAll(".glossary-term").forEach(el => {
        const term = el.textContent.trim();
        const tip = el.getAttribute("data-tooltip") || "";
        if (term && tip && !termsMap.has(term)) {
          termsMap.set(term, tip);
        }
      });
    };

    state.article.blocks.forEach(b => {
      if (b.type === "richtext" || b.type === "callout") {
        scanHtml(b.html);
      }
    });

    const res = [];
    termsMap.forEach((definition, term) => {
      res.push({ term: term, definition: definition });
    });
    res.sort((a, b) => a.term.localeCompare(b.term));
    return res;
  }

  function updateGlossaryBlockPreviews() {
    document.querySelectorAll(".glossary-auto-detected-box").forEach(box => {
      const parent = box.closest(".cms-block-card");
      if (parent && parent.dataset.blockId) {
        const blk = (state.article.blocks || []).find(b => b.id === parent.dataset.blockId);
        if (blk && blk.type === "glossary") {
          renderGlossaryDetectedSection(box, blk);
        }
      }
    });
  }

  function renderGlossaryDetectedSection(container, blk) {
    container.innerHTML = "";
    const autoTerms = scanArticleGlossaryTerms();

    const header = document.createElement("div");
    header.className = "glossary-detected-header";
    header.innerHTML = `<strong>Automatisch im Text erkannte Begriffe (${autoTerms.length})</strong>` +
      `<span style="font-size:11px;color:#0284C7;font-weight:500;">Live synchronisiert</span>`;
    container.appendChild(header);

    if (autoTerms.length === 0) {
      const hint = document.createElement("div");
      hint.style.fontSize = "12px";
      hint.style.color = "#64748B";
      hint.style.fontStyle = "italic";
      hint.textContent = "Bisher keine Begriffe mit 'ℹ Glossar' im Text markiert. Markieren Sie ein beliebiges Fachwort im Fließtext und klicken Sie in der Textleiste auf 'ℹ Glossar'.";
      container.appendChild(hint);
      return;
    }

    const list = document.createElement("div");
    list.className = "glossary-detected-pills";
    autoTerms.forEach(item => {
      const row = document.createElement("div");
      row.className = "glossary-detected-pill-item";
      row.innerHTML = `<span class="glossary-detected-term">${item.term}</span> — ` +
        `<span class="glossary-detected-def">${item.definition}</span>`;
      list.appendChild(row);
    });
    container.appendChild(list);
  }

  function buildGlossaryBlockBody(container, blk) {
    if (!blk.title) blk.title = "Glossar & Begriffserklärungen";
    if (blk.auto_collect === undefined) blk.auto_collect = true;
    if (!Array.isArray(blk.custom_items)) blk.custom_items = [];

    // Zeile 1: Titel & Satzbreite
    const topGrid = document.createElement("div");
    topGrid.style.display = "grid";
    topGrid.style.gridTemplateColumns = "1fr 180px";
    topGrid.style.gap = "10px";
    topGrid.style.marginBottom = "10px";

    const titleWrap = document.createElement("div");
    const titleLbl = document.createElement("label");
    titleLbl.className = "field-label";
    titleLbl.textContent = "Titel des Glossar-Abschnitts";
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
    layoutSel.addEventListener("change", function () {
      blk.layout = layoutSel.value;
      markDirty();
    });
    layoutWrap.appendChild(layoutLbl);
    layoutWrap.appendChild(layoutSel);

    topGrid.appendChild(titleWrap);
    topGrid.appendChild(layoutWrap);
    container.appendChild(topGrid);

    // Auto-Detected Sektion
    const detectedBox = document.createElement("div");
    detectedBox.className = "glossary-auto-detected-box";
    renderGlossaryDetectedSection(detectedBox, blk);
    container.appendChild(detectedBox);

    // Manuelle Ergänzungen Sektion
    const customWrap = document.createElement("div");
    customWrap.style.marginTop = "10px";

    const customHeader = document.createElement("div");
    customHeader.style.display = "flex";
    customHeader.style.justifyContent = "space-between";
    customHeader.style.alignItems = "center";
    customHeader.style.marginBottom = "6px";

    const customLbl = document.createElement("label");
    customLbl.className = "field-label";
    customLbl.style.margin = "0";
    customLbl.textContent = "Manuelle Glossar-Ergänzungen (optional):";

    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addBtn.textContent = "+ Begriff hinzufügen";

    customHeader.appendChild(customLbl);
    customHeader.appendChild(addBtn);
    customWrap.appendChild(customHeader);

    const customList = document.createElement("div");
    customList.className = "footnotes-items-list";

    function renderCustomItems() {
      customList.innerHTML = "";
      if (blk.custom_items.length === 0) {
        const noCustom = document.createElement("div");
        noCustom.style.fontSize = "11.5px";
        noCustom.style.color = "#94A3B8";
        noCustom.textContent = "Keine manuellen Einträge (alle Begriffe werden automatisch aus dem Text bezogen).";
        customList.appendChild(noCustom);
        return;
      }

      blk.custom_items.forEach(function (cItem, idx) {
        const row = document.createElement("div");
        row.className = "footnote-row-item";
        row.style.gridTemplateColumns = "130px 1fr 32px";

        const termInp = document.createElement("input");
        termInp.type = "text";
        termInp.className = "cms-input font-medium";
        termInp.placeholder = "Begriff (z.B. Duration)";
        termInp.value = cItem.term || "";
        termInp.addEventListener("input", function () {
          cItem.term = termInp.value;
          markDirty();
        });

        const defInp = document.createElement("input");
        defInp.type = "text";
        defInp.className = "cms-input";
        defInp.placeholder = "Definition / Erklärung …";
        defInp.value = cItem.definition || "";
        defInp.addEventListener("input", function () {
          cItem.definition = defInp.value;
          markDirty();
        });

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-icon-only danger";
        delBtn.title = "Begriff entfernen";
        delBtn.textContent = "✕";
        delBtn.addEventListener("click", function () {
          blk.custom_items.splice(idx, 1);
          renderCustomItems();
          markDirty();
        });

        row.appendChild(termInp);
        row.appendChild(defInp);
        row.appendChild(delBtn);
        customList.appendChild(row);
      });
    }

    addBtn.addEventListener("click", function () {
      blk.custom_items.push({ term: "", definition: "" });
      renderCustomItems();
      markDirty();
    });

    renderCustomItems();
    customWrap.appendChild(customList);
    container.appendChild(customWrap);
  }

  function buildSpacerBlockBody(container, blk) {
    if (!blk.height_mm) blk.height_mm = 8;

    const row = document.createElement("div");
    row.className = "db-spacer-editor-row";

    const label = document.createElement("label");
    label.className = "field-label";
    label.style.margin = "0";
    label.style.whiteSpace = "nowrap";
    label.textContent = "Abstandshöhe:";

    const numInp = document.createElement("input");
    numInp.type = "number";
    numInp.className = "cms-input font-medium";
    numInp.style.maxWidth = "70px";
    numInp.style.textAlign = "center";
    numInp.style.padding = "4px 8px";
    numInp.min = "2";
    numInp.max = "80";
    numInp.step = "2";
    numInp.value = blk.height_mm;

    const unit = document.createElement("span");
    unit.style.fontSize = "12.5px";
    unit.style.color = "var(--lukb-navy)";
    unit.style.fontWeight = "500";
    unit.textContent = "mm";

    const previewLine = document.createElement("div");
    previewLine.className = "db-spacer-preview-line";

    const presetButtons = [];

    function updateHeight(val) {
      let num = parseInt(val, 10);
      if (isNaN(num)) num = 8;
      num = Math.max(2, Math.min(80, Math.round(num / 2) * 2));
      blk.height_mm = num;
      numInp.value = num;
      updateVisual();
      updatePresetActive();
      markDirty();
    }

    function updateVisual() {
      const hMm = blk.height_mm || 8;
      const hPx = Math.round(hMm * 3.78);
      previewLine.style.height = Math.max(14, hPx) + "px";
      previewLine.textContent = "↕ " + hMm + " mm vertikaler Leerraum im Satz";
    }

    function updatePresetActive() {
      const cur = blk.height_mm || 8;
      presetButtons.forEach(function (pb) {
        if (pb.val === cur) {
          pb.btn.classList.add("active");
          pb.btn.style.setProperty("background", "var(--lukb-navy)", "important");
          pb.btn.style.setProperty("color", "#FFFFFF", "important");
          pb.btn.style.setProperty("border-color", "var(--lukb-navy)", "important");
        } else {
          pb.btn.classList.remove("active");
          pb.btn.style.removeProperty("background");
          pb.btn.style.removeProperty("color");
          pb.btn.style.removeProperty("border-color");
        }
      });
    }

    numInp.addEventListener("change", function () {
      updateHeight(numInp.value);
    });

    const presetsWrap = document.createElement("div");
    presetsWrap.className = "db-spacer-presets";

    [
      { label: "4 mm", val: 4 },
      { label: "8 mm (Std)", val: 8 },
      { label: "12 mm", val: 12 },
      { label: "16 mm", val: 16 },
      { label: "24 mm", val: 24 },
    ].forEach(function (preset) {
      const pBtn = document.createElement("button");
      pBtn.type = "button";
      pBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm db-height-preset-btn";
      pBtn.style.padding = "3px 8px";
      pBtn.style.fontSize = "11px";
      pBtn.textContent = preset.label;
      pBtn.addEventListener("click", function () {
        updateHeight(preset.val);
      });
      presetsWrap.appendChild(pBtn);
      presetButtons.push({ btn: pBtn, val: preset.val });
    });

    row.appendChild(label);
    row.appendChild(numInp);
    row.appendChild(unit);
    row.appendChild(presetsWrap);

    container.appendChild(row);
    container.appendChild(previewLine);
    updateVisual();
    updatePresetActive();
  }

  function buildColbreakBlockBody(container, blk) {
    const wrap = document.createElement("div");
    wrap.className = "db-colbreak-editor-box";

    const icon = document.createElement("span");
    icon.className = "db-colbreak-icon";
    icon.textContent = "⇥";

    const textWrap = document.createElement("div");
    const title = document.createElement("div");
    title.className = "db-colbreak-title";
    title.textContent = "Manueller Spaltenumbruch";

    const desc = document.createElement("div");
    desc.className = "db-colbreak-desc";
    desc.textContent = "Erzwingt an dieser Position den Wechsel in Spalte 2 (bzw. auf die Folgeseite in Spalte 1).";

    textWrap.appendChild(title);
    textWrap.appendChild(desc);

    wrap.appendChild(icon);
    wrap.appendChild(textWrap);
    container.appendChild(wrap);
  }

  function buildHeadingBlockBody(container, blk) {
    const row = document.createElement("div");
    row.style.display = "grid";
    row.style.gridTemplateColumns = "140px 1fr";
    row.style.gap = "10px";
    row.style.alignItems = "center";

    const select = document.createElement("select");
    select.className = "cms-select font-medium";
    [
      { val: 1, label: "H1 — Haupttitel" },
      { val: 2, label: "H2 — Zwischentitel" },
      { val: 3, label: "H3 — Untertitel" },
    ].forEach(function (opt) {
      const o = document.createElement("option");
      o.value = opt.val;
      o.textContent = opt.label;
      if (Number(blk.level || 1) === opt.val) o.selected = true;
      select.appendChild(o);
    });
    select.addEventListener("change", function () {
      blk.level = parseInt(select.value, 10) || 1;
      markDirty();
    });

    const input = document.createElement("input");
    input.type = "text";
    input.className = "cms-input font-medium";
    input.style.fontSize = "15.5px";
    input.style.color = "#002855";
    input.placeholder = "Überschrift eingeben …";
    input.value = blk.text || "";
    input.addEventListener("input", function () {
      blk.text = input.value;
      markDirty();
    });

    row.appendChild(select);
    row.appendChild(input);
    container.appendChild(row);
  }

  let activePopover = null;

  function closeActivePopover() {
    if (activePopover && activePopover.parentNode) {
      activePopover.parentNode.removeChild(activePopover);
    }
    activePopover = null;
  }

  document.addEventListener("mousedown", function (e) {
    if (activePopover && !activePopover.contains(e.target)) {
      closeActivePopover();
    }
  });

  function openGlossaryTermPopover(targetEl, editable, onChange) {
    closeActivePopover();

    const popover = document.createElement("div");
    popover.className = "lukb-term-popover";

    const header = document.createElement("div");
    header.className = "lukb-popover-header";
    header.innerHTML = "<span>ℹ Glossar-Begriff</span>";
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "btn-icon-only";
    closeBtn.textContent = "✕";
    closeBtn.style.padding = "0 4px";
    closeBtn.addEventListener("click", closeActivePopover);
    header.appendChild(closeBtn);
    popover.appendChild(header);

    const termLbl = document.createElement("label");
    termLbl.className = "field-label";
    termLbl.style.fontSize = "11px";
    termLbl.style.marginBottom = "3px";
    termLbl.textContent = "Begriff im Text:";
    popover.appendChild(termLbl);

    const termInp = document.createElement("input");
    termInp.type = "text";
    termInp.className = "cms-input font-medium";
    termInp.style.marginBottom = "8px";
    termInp.value = targetEl.textContent.trim();
    popover.appendChild(termInp);

    const tipLbl = document.createElement("label");
    tipLbl.className = "field-label";
    tipLbl.style.fontSize = "11px";
    tipLbl.style.marginBottom = "3px";
    tipLbl.textContent = "Erklärung / Tooltip:";
    popover.appendChild(tipLbl);

    const tipInp = document.createElement("textarea");
    tipInp.className = "cms-textarea";
    tipInp.rows = 2;
    tipInp.style.fontSize = "12px";
    tipInp.value = targetEl.getAttribute("data-tooltip") || "";
    popover.appendChild(tipInp);

    const actions = document.createElement("div");
    actions.className = "lukb-popover-actions";

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-lukb btn-lukb-outline-light btn-lukb-sm";
    removeBtn.style.color = "#DC2626";
    removeBtn.style.borderColor = "#FCA5A5";
    removeBtn.textContent = "✕ Markierung entfernen";
    removeBtn.title = "Entfernt die Glossar-Markierung und behält das Wort als normalen Fließtext";
    removeBtn.addEventListener("click", function () {
      const textNode = document.createTextNode(targetEl.textContent);
      targetEl.parentNode.replaceChild(textNode, targetEl);
      closeActivePopover();
      onChange(editable.innerHTML);
      markDirty();
      updateGlossaryBlockPreviews();
    });

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn-lukb btn-lukb-primary btn-lukb-sm";
    saveBtn.textContent = "Übernehmen";
    saveBtn.addEventListener("click", function () {
      targetEl.textContent = termInp.value.trim() || targetEl.textContent;
      targetEl.setAttribute("data-tooltip", tipInp.value.trim());
      closeActivePopover();
      onChange(editable.innerHTML);
      markDirty();
      updateGlossaryBlockPreviews();
    });

    actions.appendChild(removeBtn);
    actions.appendChild(saveBtn);
    popover.appendChild(actions);

    document.body.appendChild(popover);
    activePopover = popover;

    const rect = targetEl.getBoundingClientRect();
    popover.style.top = (rect.bottom + window.scrollY + 6) + "px";
    popover.style.left = Math.max(10, Math.min(window.innerWidth - 340, rect.left + window.scrollX)) + "px";
  }

  function openFootnotePopover(targetEl, editable, onChange) {
    closeActivePopover();

    const popover = document.createElement("div");
    popover.className = "lukb-term-popover";

    const header = document.createElement("div");
    header.className = "lukb-popover-header";
    header.innerHTML = "<span>[¹] Inline-Fussnote</span>";
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "btn-icon-only";
    closeBtn.textContent = "✕";
    closeBtn.style.padding = "0 4px";
    closeBtn.addEventListener("click", closeActivePopover);
    header.appendChild(closeBtn);
    popover.appendChild(header);

    const fnLbl = document.createElement("label");
    fnLbl.className = "field-label";
    fnLbl.style.fontSize = "11px";
    fnLbl.style.marginBottom = "3px";
    fnLbl.textContent = "Fussnotentext für Seitenende:";
    popover.appendChild(fnLbl);

    const fnInp = document.createElement("textarea");
    fnInp.className = "cms-textarea";
    fnInp.rows = 3;
    fnInp.style.fontSize = "12px";
    fnInp.value = targetEl.textContent.trim();
    popover.appendChild(fnInp);

    const actions = document.createElement("div");
    actions.className = "lukb-popover-actions";

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-lukb btn-lukb-outline-light btn-lukb-sm";
    removeBtn.style.color = "#DC2626";
    removeBtn.style.borderColor = "#FCA5A5";
    removeBtn.textContent = "✕ Fussnote löschen";
    removeBtn.title = "Löscht diese Fussnote vollständig";
    removeBtn.addEventListener("click", function () {
      targetEl.parentNode.removeChild(targetEl);
      closeActivePopover();
      onChange(editable.innerHTML);
      markDirty();
    });

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn-lukb btn-lukb-primary btn-lukb-sm";
    saveBtn.textContent = "Übernehmen";
    saveBtn.addEventListener("click", function () {
      targetEl.textContent = fnInp.value.trim();
      closeActivePopover();
      onChange(editable.innerHTML);
      markDirty();
    });

    actions.appendChild(removeBtn);
    actions.appendChild(saveBtn);
    popover.appendChild(actions);

    document.body.appendChild(popover);
    activePopover = popover;

    const rect = targetEl.getBoundingClientRect();
    popover.style.top = (rect.bottom + window.scrollY + 6) + "px";
    popover.style.left = Math.max(10, Math.min(window.innerWidth - 340, rect.left + window.scrollX)) + "px";
  }

  function createRichTextWidget(initialHtml, onChange, extraRightEl) {
    const wrapper = document.createElement("div");

    const toolbar = document.createElement("div");
    toolbar.className = "richtext-toolbar";
    toolbar.style.justifyContent = "space-between";
    toolbar.style.flexWrap = "wrap";

    const btnGroup = document.createElement("div");
    btnGroup.style.display = "flex";
    btnGroup.style.alignItems = "center";
    btnGroup.style.gap = "4px";

    const editable = document.createElement("div");
    editable.className = "richtext-editable";
    editable.contentEditable = "true";
    editable.innerHTML = initialHtml || "<p></p>";

    const commands = [
      { cmd: "bold", label: "B", title: "Fett (Yoga Sans Medium)" },
      { cmd: "italic", label: "I", title: "Kursiv" },
      { cmd: "underline", label: "U", title: "Unterstrichen" },
      { cmd: "insertUnorderedList", label: "• Liste", title: "Aufzählungsliste" },
      { cmd: "insertOrderedList", label: "1. Liste", title: "Nummerierte Liste" },
      { cmd: "removeFormat", label: "Tx", title: "Formatierung entfernen" },
    ];

    commands.forEach(function (c) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "rt-btn";
      btn.textContent = c.label;
      btn.title = c.title;
      btn.addEventListener("mousedown", function (e) {
        e.preventDefault();
        editable.focus();
        document.execCommand(c.cmd, false, null);
        onChange(editable.innerHTML);
      });
      btnGroup.appendChild(btn);
    });

    // Glossar / Begriffserklärung mit Hover-Tooltip (Web) & Glossar-Verzeichnis
    const glossBtn = document.createElement("button");
    glossBtn.type = "button";
    glossBtn.className = "rt-btn";
    glossBtn.textContent = "ℹ Glossar";
    glossBtn.title = "Markierten Begriff mit Hover-Tooltip (Web) & Glossar-Verzeichnis am Textende versehen";
    glossBtn.addEventListener("mousedown", function (e) {
      e.preventDefault();
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return;
      const range = sel.getRangeAt(0);
      const selText = range.toString().trim();
      const tip = prompt("Begriffserklärung für Tooltip & Glossar-Verzeichnis eingeben:", "");
      if (!tip) return;
      const span = document.createElement("span");
      span.className = "glossary-term";
      span.setAttribute("data-tooltip", tip);
      span.textContent = selText || "Begriff";
      range.deleteContents();
      range.insertNode(span);
      onChange(editable.innerHTML);
      markDirty();
      updateGlossaryBlockPreviews();
    });
    btnGroup.appendChild(glossBtn);

    // Inline-Fussnote Button
    const fnBtn = document.createElement("button");
    fnBtn.type = "button";
    fnBtn.className = "rt-btn";
    fnBtn.textContent = "[¹] Fussnote";
    fnBtn.title = "Inline-Fussnote einfügen (wird im PDF am Seitenende platziert)";
    fnBtn.addEventListener("mousedown", function (e) {
      e.preventDefault();
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return;
      const range = sel.getRangeAt(0);
      const fnText = prompt("Fussnotentext für Seitenende eingeben:", "");
      if (!fnText) return;
      const fnTag = document.createElement("footnote");
      fnTag.textContent = fnText;
      range.collapse(false);
      range.insertNode(fnTag);
      onChange(editable.innerHTML);
      markDirty();
    });
    btnGroup.appendChild(fnBtn);

    toolbar.appendChild(btnGroup);
    if (extraRightEl) {
      toolbar.appendChild(extraRightEl);
    }

    editable.addEventListener("input", function () {
      onChange(editable.innerHTML);
      updateGlossaryBlockPreviews();
    });

    editable.addEventListener("click", function (e) {
      const termEl = e.target.closest(".glossary-term");
      if (termEl) {
        e.preventDefault();
        e.stopPropagation();
        openGlossaryTermPopover(termEl, editable, onChange);
        return;
      }
      const fnEl = e.target.closest("footnote");
      if (fnEl) {
        e.preventDefault();
        e.stopPropagation();
        openFootnotePopover(fnEl, editable, onChange);
        return;
      }
    });

    // Verhindere fremde Styles beim Einfügen aus Word/Webseiten
    editable.addEventListener("paste", function (e) {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text);
      onChange(editable.innerHTML);
      updateGlossaryBlockPreviews();
    });

    wrapper.appendChild(toolbar);
    wrapper.appendChild(editable);
    return { wrapper: wrapper, editable: editable };
  }

  function buildRichTextBlockBody(container, blk) {
    const rt = createRichTextWidget(blk.html, function (newHtml) {
      blk.html = newHtml;
      markDirty();
    });
    container.appendChild(rt.wrapper);
  }

  function buildCalloutBlockBody(container, blk) {
    const titleGroup = document.createElement("div");
    titleGroup.className = "field-group";
    const lbl = document.createElement("label");
    lbl.className = "field-label";
    lbl.textContent = "Titel der Highlight- / Kernaussagen-Box";
    const inp = document.createElement("input");
    inp.type = "text";
    inp.className = "cms-input font-medium";
    inp.value = blk.title || "";
    inp.addEventListener("input", function () {
      blk.title = inp.value;
      markDirty();
    });
    titleGroup.appendChild(lbl);
    titleGroup.appendChild(inp);
    container.appendChild(titleGroup);

    const rt = createRichTextWidget(blk.html, function (newHtml) {
      blk.html = newHtml;
      markDirty();
    });
    container.appendChild(rt.wrapper);
  }

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
    layoutSel.addEventListener("change", function () {
      blk.layout = layoutSel.value;
      requestDbChartPreview(blk, true);
      markDirty();
    });
    layoutWrap.appendChild(layoutLbl);
    layoutWrap.appendChild(layoutSel);

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

        if (window.Shiny && window.Shiny.setInputValue) {
          window.Shiny.setInputValue(
            "lukb_upload_asset",
            {
              asset_id: newAssetId,
              article_id: state.article.id,
              filename: fileName,
              mime_type: mimeType,
              base64_data: base64Data,
              ts: Date.now(),
            },
            { priority: "event" }
          );
        }
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

  const LUKB_SERIES_COLORS = ["#002855", "#009FE3", "#C59B27", "#005A9C", "#6482A6"];

  function indexTickerItems(items) {
    if (!Array.isArray(items)) return;
    items.forEach(function (t) {
      if (t && t.ticker) {
        state.tickerNameMap[String(t.ticker).trim().toUpperCase()] = t.name || "";
      }
    });
  }

  function lookupTickerName(tickerStr) {
    if (!tickerStr) return "";
    const upper = String(tickerStr).trim().toUpperCase();
    return state.tickerNameMap[upper] || "";
  }

  // Schneller, leichtgewichtiger Autocomplete-Dialog für tausende Ticker in ts_db
  const tickerSuggest = {
    popoverEl: null,
    activeInput: null,
    onSelectCallback: null,
    items: [],
    activeIndex: -1,
    requestId: 0,
    debounceTimer: null,
  };

  function ensureTickerSuggestPopover() {
    if (tickerSuggest.popoverEl) return tickerSuggest.popoverEl;
    const pop = document.createElement("div");
    pop.id = "lukb-ticker-suggest-popover";
    pop.className = "db-ticker-suggest-popover";
    pop.style.display = "none";
    document.body.appendChild(pop);
    tickerSuggest.popoverEl = pop;

    window.addEventListener(
      "scroll",
      function (ev) {
        if (
          tickerSuggest.popoverEl &&
          tickerSuggest.popoverEl.style.display !== "none" &&
          ev.target !== tickerSuggest.popoverEl
        ) {
          positionTickerSuggestPopover();
        }
      },
      true
    );
    window.addEventListener("resize", function () {
      if (tickerSuggest.popoverEl && tickerSuggest.popoverEl.style.display !== "none") {
        positionTickerSuggestPopover();
      }
    });
    return pop;
  }

  function positionTickerSuggestPopover() {
    const pop = tickerSuggest.popoverEl;
    const inp = tickerSuggest.activeInput;
    if (!pop || !inp || !document.body.contains(inp)) {
      closeTickerSuggestPopover();
      return;
    }
    const rect = inp.getBoundingClientRect();
    pop.style.left = Math.round(rect.left) + "px";
    pop.style.top = Math.round(rect.bottom + 4) + "px";
    pop.style.minWidth = Math.max(290, Math.round(rect.width)) + "px";
  }

  function closeTickerSuggestPopover() {
    if (tickerSuggest.debounceTimer) {
      clearTimeout(tickerSuggest.debounceTimer);
      tickerSuggest.debounceTimer = null;
    }
    if (tickerSuggest.popoverEl) {
      tickerSuggest.popoverEl.style.display = "none";
      tickerSuggest.popoverEl.innerHTML = "";
    }
    tickerSuggest.items = [];
    tickerSuggest.activeIndex = -1;
  }

  function renderTickerSuggestItems(results) {
    const pop = ensureTickerSuggestPopover();
    if (!tickerSuggest.activeInput || document.activeElement !== tickerSuggest.activeInput) {
      closeTickerSuggestPopover();
      return;
    }
    indexTickerItems(results);
    tickerSuggest.items = Array.isArray(results) ? results : [];
    tickerSuggest.activeIndex = tickerSuggest.items.length > 0 ? 0 : -1;
    pop.innerHTML = "";

    if (tickerSuggest.items.length === 0) {
      const emptyEl = document.createElement("div");
      emptyEl.className = "db-ticker-suggest-empty";
      emptyEl.textContent = "Kein passender Ticker in ts_db gefunden";
      pop.appendChild(emptyEl);
      positionTickerSuggestPopover();
      pop.style.display = "block";
      return;
    }

    tickerSuggest.items.forEach(function (item, idx) {
      const rowEl = document.createElement("div");
      rowEl.className =
        "db-ticker-suggest-item" + (idx === tickerSuggest.activeIndex ? " active" : "");

      const codeSpan = document.createElement("span");
      codeSpan.className = "db-ticker-suggest-code";
      codeSpan.textContent = item.ticker;

      const nameSpan = document.createElement("span");
      nameSpan.className = "db-ticker-suggest-name";
      nameSpan.textContent = item.name || "";

      rowEl.appendChild(codeSpan);
      rowEl.appendChild(nameSpan);

      rowEl.addEventListener("mouseenter", function () {
        tickerSuggest.activeIndex = idx;
        updateTickerSuggestHighlight();
      });

      rowEl.addEventListener("mousedown", function (ev) {
        ev.preventDefault(); // Fokus auf Input behalten
        if (tickerSuggest.onSelectCallback) {
          tickerSuggest.onSelectCallback(item);
        }
        closeTickerSuggestPopover();
      });

      pop.appendChild(rowEl);
    });

    positionTickerSuggestPopover();
    pop.style.display = "block";
  }

  function updateTickerSuggestHighlight() {
    if (!tickerSuggest.popoverEl) return;
    const children = tickerSuggest.popoverEl.querySelectorAll(".db-ticker-suggest-item");
    children.forEach(function (el, idx) {
      if (idx === tickerSuggest.activeIndex) {
        el.classList.add("active");
        if (el.scrollIntoView) {
          el.scrollIntoView({ block: "nearest" });
        }
      } else {
        el.classList.remove("active");
      }
    });
  }

  function triggerTickerSuggestQuery(queryStr) {
    const qNorm = String(queryStr || "").trim().toLowerCase();
    if (state.tickerQueryCache[qNorm]) {
      renderTickerSuggestItems(state.tickerQueryCache[qNorm]);
      return;
    }
    if (qNorm === "" && Array.isArray(state.availableTickers) && state.availableTickers.length > 0) {
      const initialSlice = state.availableTickers.slice(0, 15);
      state.tickerQueryCache[""] = initialSlice;
      renderTickerSuggestItems(initialSlice);
      return;
    }
    if (tickerSuggest.debounceTimer) {
      clearTimeout(tickerSuggest.debounceTimer);
    }
    tickerSuggest.debounceTimer = setTimeout(function () {
      const reqId = ++tickerSuggest.requestId;
      if (window.Shiny && window.Shiny.setInputValue) {
        window.Shiny.setInputValue(
          "lukb_search_tickers",
          {
            query: queryStr || "",
            request_id: reqId,
            ts: Date.now(),
          },
          { priority: "event" }
        );
      }
    }, 80);
  }

  function attachTickerAutocomplete(inputEl, onSelect) {
    inputEl.setAttribute("autocomplete", "off");
    inputEl.setAttribute("spellcheck", "false");

    inputEl.addEventListener("focus", function () {
      tickerSuggest.activeInput = inputEl;
      tickerSuggest.onSelectCallback = onSelect;
      triggerTickerSuggestQuery(inputEl.value);
    });

    inputEl.addEventListener("input", function () {
      tickerSuggest.activeInput = inputEl;
      tickerSuggest.onSelectCallback = onSelect;
      triggerTickerSuggestQuery(inputEl.value);
    });

    inputEl.addEventListener("keydown", function (ev) {
      if (!tickerSuggest.popoverEl || tickerSuggest.popoverEl.style.display === "none") {
        if (ev.key === "ArrowDown") {
          tickerSuggest.activeInput = inputEl;
          tickerSuggest.onSelectCallback = onSelect;
          triggerTickerSuggestQuery(inputEl.value);
          ev.preventDefault();
        }
        return;
      }
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        if (tickerSuggest.items.length > 0) {
          tickerSuggest.activeIndex =
            (tickerSuggest.activeIndex + 1) % tickerSuggest.items.length;
          updateTickerSuggestHighlight();
        }
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        if (tickerSuggest.items.length > 0) {
          tickerSuggest.activeIndex =
            (tickerSuggest.activeIndex - 1 + tickerSuggest.items.length) %
            tickerSuggest.items.length;
          updateTickerSuggestHighlight();
        }
      } else if (ev.key === "Enter") {
        if (
          tickerSuggest.activeIndex >= 0 &&
          tickerSuggest.activeIndex < tickerSuggest.items.length
        ) {
          ev.preventDefault();
          const chosen = tickerSuggest.items[tickerSuggest.activeIndex];
          if (onSelect && chosen) {
            onSelect(chosen);
          }
          closeTickerSuggestPopover();
        }
      } else if (ev.key === "Escape" || ev.key === "Tab") {
        closeTickerSuggestPopover();
      }
    });

    inputEl.addEventListener("blur", function () {
      setTimeout(function () {
        if (document.activeElement !== tickerSuggest.activeInput) {
          closeTickerSuggestPopover();
        }
      }, 120);
    });
  }

  function requestDbChartPreview(blk, immediate) {
    if (!blk || !blk.id || blk.type !== "db_chart") return;
    if (state.dbChartTimers[blk.id]) {
      clearTimeout(state.dbChartTimers[blk.id]);
      delete state.dbChartTimers[blk.id];
    }
    const sendReq = function () {
      if (window.Shiny && window.Shiny.setInputValue) {
        window.Shiny.setInputValue(
          "lukb_preview_db_chart",
          {
            block: deepClone(blk),
            ts: Date.now(),
          },
          { priority: "event" }
        );
      }
    };
    if (immediate) {
      sendReq();
    } else {
      state.dbChartTimers[blk.id] = setTimeout(sendReq, 220);
    }
  }

  function buildDbChartBlockBody(container, blk) {
    if (!Array.isArray(blk.series) || blk.series.length === 0) {
      blk.series = [{ ticker: "SMI", chart_type: "line", label: "" }];
    }
    if (!blk.start_date) {
      blk.start_date = "2022-01-01";
    }
    if (!blk.rebasing) {
      blk.rebasing = "none";
    }
    if (!blk.chart_height_mm) {
      blk.chart_height_mm = 36;
    }

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
    titleInp.placeholder = "z.B. Leitzinsentwicklung oder Aktienmarktvergleich";
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
    layoutSel.addEventListener("change", function () {
      blk.layout = layoutSel.value;
      requestDbChartPreview(blk, true);
      markDirty();
    });
    layoutWrap.appendChild(layoutLbl);
    layoutWrap.appendChild(layoutSel);

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
    subInp.placeholder = "z.B. In Prozent oder Indexiert (Start = 100)";
    subInp.value = blk.subtitle || "";
    subInp.addEventListener("input", function () {
      blk.subtitle = subInp.value;
      markDirty();
    });
    subWrap.appendChild(subLbl);
    subWrap.appendChild(subInp);
    container.appendChild(subWrap);

    // Zeile 3: Startdatum & Skalierung (Originalwerte vs. Indexiert 100)
    const configGrid = document.createElement("div");
    configGrid.className = "db-chart-config-bar";

    const dateWrap = document.createElement("div");
    const dateLbl = document.createElement("label");
    dateLbl.className = "field-label";
    dateLbl.textContent = "Startdatum im Chart";
    const dateRow = document.createElement("div");
    dateRow.style.display = "flex";
    dateRow.style.gap = "6px";
    dateRow.style.alignItems = "center";

    const dateInp = document.createElement("input");
    dateInp.type = "date";
    dateInp.className = "cms-input";
    dateInp.style.maxWidth = "155px";
    dateInp.value = blk.start_date || "2022-01-01";
    dateInp.addEventListener("change", function () {
      blk.start_date = dateInp.value || "2022-01-01";
      requestDbChartPreview(blk, true);
      markDirty();
    });
    dateRow.appendChild(dateInp);

    // Schnellwahl-Buttons für Startdatum
    [
      { label: "2021", date: "2021-01-01" },
      { label: "2023", date: "2023-01-01" },
      { label: "2025", date: "2025-01-01" },
    ].forEach(function (preset) {
      const pBtn = document.createElement("button");
      pBtn.type = "button";
      pBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
      pBtn.style.padding = "4px 7px";
      pBtn.style.fontSize = "11px";
      pBtn.textContent = preset.label;
      pBtn.title = "Startdatum auf " + preset.date + " setzen";
      pBtn.addEventListener("click", function () {
        blk.start_date = preset.date;
        dateInp.value = preset.date;
        requestDbChartPreview(blk, true);
        markDirty();
      });
      dateRow.appendChild(pBtn);
    });

    dateWrap.appendChild(dateLbl);
    dateWrap.appendChild(dateRow);

    const rebaseWrap = document.createElement("div");
    const rebaseLbl = document.createElement("label");
    rebaseLbl.className = "field-label";
    rebaseLbl.textContent = "Darstellung / Skalierung";
    const rebaseSel = document.createElement("select");
    rebaseSel.className = "cms-select";
    [
      { val: "none", label: "Originalwerte (Rohdaten aus ts_db)" },
      { val: "index_100", label: "Indexiert auf 100 (am Startdatum = 100)" },
    ].forEach(function (o) {
      const opt = document.createElement("option");
      opt.value = o.val;
      opt.textContent = o.label;
      if ((blk.rebasing || "none") === o.val) opt.selected = true;
      rebaseSel.appendChild(opt);
    });
    rebaseSel.addEventListener("change", function () {
      blk.rebasing = rebaseSel.value;
      requestDbChartPreview(blk, true);
      markDirty();
    });
    rebaseWrap.appendChild(rebaseLbl);
    rebaseWrap.appendChild(rebaseSel);

    configGrid.appendChild(dateWrap);
    configGrid.appendChild(rebaseWrap);
    container.appendChild(configGrid);

    // Zeile 4: Zeitreihen-Builder (maximal 5 Ticker)
    const seriesSection = document.createElement("div");
    seriesSection.className = "db-chart-series-section";

    const seriesHeader = document.createElement("div");
    seriesHeader.className = "db-chart-series-header";

    const seriesTitle = document.createElement("span");
    seriesTitle.className = "field-label";
    seriesTitle.style.margin = "0";

    const addSeriesBtn = document.createElement("button");
    addSeriesBtn.type = "button";
    addSeriesBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addSeriesBtn.textContent = "+ Zeitreihe hinzufügen";

    seriesHeader.appendChild(seriesTitle);
    seriesHeader.appendChild(addSeriesBtn);
    seriesSection.appendChild(seriesHeader);

    const seriesListEl = document.createElement("div");
    seriesListEl.className = "db-chart-series-list";
    seriesSection.appendChild(seriesListEl);

    function renderSeriesRows() {
      seriesListEl.innerHTML = "";
      const count = blk.series.length;
      seriesTitle.textContent =
        "Zeitreihen aus ts_db (" +
        count +
        " / 5 Ticker — pro Reihe auch mehrere Typen wählbar, z.B. Line + Dot oder Step + Area)";
      addSeriesBtn.disabled = count >= 5;

      blk.series.forEach(function (sItem, sIdx) {
        if (!Array.isArray(sItem.chart_types) || sItem.chart_types.length === 0) {
          sItem.chart_types = [sItem.chart_type || "line"];
        }
        sItem.chart_type = sItem.chart_types[0];

        const row = document.createElement("div");
        row.className = "db-chart-series-row";

        const colorDot = document.createElement("span");
        colorDot.className = "db-series-color-dot";
        colorDot.style.backgroundColor = LUKB_SERIES_COLORS[sIdx % LUKB_SERIES_COLORS.length];
        colorDot.title = "Farbe der Zeitreihe " + (sIdx + 1);

        const tickerInp = document.createElement("input");
        tickerInp.type = "text";
        tickerInp.className = "cms-input font-medium";
        tickerInp.placeholder = "Ticker suchen (z.B. SMI)";
        tickerInp.value = sItem.ticker || "";

        const typeTogglesWrap = document.createElement("div");
        typeTogglesWrap.className = "db-series-type-toggles";
        [
          { val: "line", label: "Line", title: "Linie (kombinierbar mit Dot, Area etc.)" },
          { val: "step", label: "Step", title: "Stufenlinie (kombinierbar mit Area, Dot etc.)" },
          { val: "dot", label: "Dot", title: "Datenpunkte (kombinierbar mit Line, Step, Area, Bar)" },
          { val: "area", label: "Area", title: "Fläche (kombinierbar mit Line, Step, Dot)" },
          { val: "bar", label: "Bar", title: "Gruppierte Balken" },
          { val: "stacked_bar", label: "Stacked", title: "Gestapelte Balken" },
        ].forEach(function (optInfo) {
          const tBtn = document.createElement("button");
          tBtn.type = "button";
          const isActive = sItem.chart_types.indexOf(optInfo.val) !== -1;
          tBtn.className = "db-type-toggle-btn" + (isActive ? " active" : "");
          tBtn.textContent = optInfo.label;
          tBtn.title = optInfo.title;
          tBtn.addEventListener("click", function () {
            const cur = Array.isArray(sItem.chart_types)
              ? sItem.chart_types.slice()
              : [sItem.chart_type || "line"];
            const existingIdx = cur.indexOf(optInfo.val);
            if (existingIdx !== -1) {
              // Mindestens ein Typ muss pro Zeitreihe aktiv bleiben
              if (cur.length > 1) {
                cur.splice(existingIdx, 1);
              }
            } else {
              // Bar & Stacked Bar schliessen sich innerhalb derselben Zeitreihe gegenseitig aus
              if (optInfo.val === "bar") {
                const sbIdx = cur.indexOf("stacked_bar");
                if (sbIdx !== -1) cur.splice(sbIdx, 1);
              } else if (optInfo.val === "stacked_bar") {
                const bIdx = cur.indexOf("bar");
                if (bIdx !== -1) cur.splice(bIdx, 1);
              }
              cur.push(optInfo.val);
            }
            sItem.chart_types = cur;
            sItem.chart_type = cur[0];
            renderSeriesRows();
            requestDbChartPreview(blk, true);
            markDirty();
          });
          typeTogglesWrap.appendChild(tBtn);
        });

        const labelInp = document.createElement("input");
        labelInp.type = "text";
        labelInp.className = "cms-input";
        const dbNameHint = lookupTickerName(sItem.ticker);
        labelInp.placeholder = dbNameHint
          ? "Legende: " + dbNameHint
          : "Legenden-Name (optional, sonst ts_db.name)";
        labelInp.value = sItem.label || "";

        tickerInp.addEventListener("input", function () {
          sItem.ticker = tickerInp.value.trim();
          const hint = lookupTickerName(sItem.ticker);
          labelInp.placeholder = hint
            ? "Legende: " + hint
            : "Legenden-Name (optional, sonst ts_db.name)";
          requestDbChartPreview(blk, false);
          markDirty();
        });

        attachTickerAutocomplete(tickerInp, function (chosenItem) {
          if (!chosenItem || !chosenItem.ticker) return;
          tickerInp.value = chosenItem.ticker;
          sItem.ticker = chosenItem.ticker;
          if (chosenItem.name) {
            state.tickerNameMap[String(chosenItem.ticker).toUpperCase()] = chosenItem.name;
          }
          const hint = lookupTickerName(sItem.ticker);
          labelInp.placeholder = hint
            ? "Legende: " + hint
            : "Legenden-Name (optional, sonst ts_db.name)";
          requestDbChartPreview(blk, true);
          markDirty();
        });

        labelInp.addEventListener("input", function () {
          sItem.label = labelInp.value;
          requestDbChartPreview(blk, false);
          markDirty();
        });

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-icon-only danger";
        delBtn.title = "Zeitreihe entfernen";
        delBtn.textContent = "✕";
        delBtn.disabled = blk.series.length <= 1;
        delBtn.addEventListener("click", function () {
          if (blk.series.length <= 1) return;
          blk.series.splice(sIdx, 1);
          renderSeriesRows();
          requestDbChartPreview(blk, true);
          markDirty();
        });

        row.appendChild(colorDot);
        row.appendChild(tickerInp);
        row.appendChild(typeTogglesWrap);
        row.appendChild(labelInp);
        row.appendChild(delBtn);
        seriesListEl.appendChild(row);
      });
    }

    addSeriesBtn.addEventListener("click", function () {
      if (blk.series.length >= 5) return;
      blk.series.push({ ticker: "", chart_type: "line", chart_types: ["line"], label: "" });
      renderSeriesRows();
      markDirty();
    });

    renderSeriesRows();
    container.appendChild(seriesSection);

    // Zeile 5: Eigener Container für Höhe der Chartfläche (Y-Achse in mm)
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

    function updateChartHeight(newVal) {
      let num = parseInt(newVal, 10);
      if (isNaN(num)) num = 36;
      num = Math.max(20, Math.min(100, Math.round(num / 2) * 2));
      blk.chart_height_mm = num;
      heightInp.value = num;
      updatePresetActive();
      requestDbChartPreview(blk, true);
      markDirty();
    }

    function updatePresetActive() {
      const cur = blk.chart_height_mm || 36;
      presetButtons.forEach(function (pb) {
        if (pb.val === cur) {
          pb.btn.classList.add("active");
          pb.btn.style.setProperty("background", "var(--lukb-navy)", "important");
          pb.btn.style.setProperty("color", "#FFFFFF", "important");
          pb.btn.style.setProperty("border-color", "var(--lukb-navy)", "important");
        } else {
          pb.btn.classList.remove("active");
          pb.btn.style.removeProperty("background");
          pb.btn.style.removeProperty("color");
          pb.btn.style.removeProperty("border-color");
        }
      });
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

    [
      { label: "28 mm", val: 28, title: "Kompakt (28 mm)" },
      { label: "36 mm (Standard)", val: 36, title: "Standardhöhe (36 mm)" },
      { label: "46 mm", val: 46, title: "Erweitert (46 mm)" },
      { label: "56 mm", val: 56, title: "Gross (56 mm)" },
    ].forEach(function (preset) {
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
    container.appendChild(heightBar);

    // Zeile 6: Live-SVG-Vorschau im Block
    const previewBox = document.createElement("div");
    previewBox.className = "db-chart-preview-box";

    const previewImg = document.createElement("img");
    previewImg.className = "figure-preview-thumb db-chart-preview-img";
    previewImg.dataset.blockId = blk.id;
    previewImg.alt = blk.title || "DB-Chart Vorschau";
    if (state.assetCache[blk.id]) {
      previewImg.src = state.assetCache[blk.id];
    } else {
      requestDbChartPreview(blk, true);
    }
    previewBox.appendChild(previewImg);

    const previewFooter = document.createElement("div");
    previewFooter.style.display = "flex";
    previewFooter.style.justifyContent = "space-between";
    previewFooter.style.alignItems = "center";
    previewFooter.style.marginTop = "4px";

    const hintSpan = document.createElement("span");
    hintSpan.style.fontSize = "11.5px";
    hintSpan.style.color = "#5A687C";
    hintSpan.textContent = "Direktabfrage aus MSSQL-Tabelle ts_db (LUKB Vektor-SVG)";

    const refreshBtn = document.createElement("button");
    refreshBtn.type = "button";
    refreshBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    refreshBtn.textContent = "↻ Daten aus ts_db neu laden";
    refreshBtn.addEventListener("click", function () {
      requestDbChartPreview(blk, true);
      markDirty();
    });

    previewFooter.appendChild(hintSpan);
    previewFooter.appendChild(refreshBtn);
    previewBox.appendChild(previewFooter);
    container.appendChild(previewBox);

    // Zeile 6: Quellenangabe
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

  function buildTableBlockBody(container, blk) {
    // Zeile 1: Tabellen-Titel & Satz-Breite
    const topGrid = document.createElement("div");
    topGrid.style.display = "grid";
    topGrid.style.gridTemplateColumns = "1fr 190px";
    topGrid.style.gap = "10px";
    topGrid.style.marginBottom = "10px";

    const titleWrap = document.createElement("div");
    const titleLbl = document.createElement("label");
    titleLbl.className = "field-label";
    titleLbl.textContent = "Tabellen-Titel (Yoga Sans Medium)";
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
    layoutSel.addEventListener("change", function () {
      blk.layout = layoutSel.value;
      requestDbChartPreview(blk, true);
      markDirty();
    });
    layoutWrap.appendChild(layoutLbl);
    layoutWrap.appendChild(layoutSel);

    topGrid.appendChild(titleWrap);
    topGrid.appendChild(layoutWrap);
    container.appendChild(topGrid);

    // Zeile 2: Tabellen-Untertitel
    const subWrap = document.createElement("div");
    subWrap.className = "field-group";
    const subLbl = document.createElement("label");
    subLbl.className = "field-label";
    subLbl.textContent = "Tabellen-Untertitel";
    const subInp = document.createElement("input");
    subInp.type = "text";
    subInp.className = "cms-input";
    subInp.value = blk.subtitle || "";
    subInp.addEventListener("input", function () {
      blk.subtitle = subInp.value;
      markDirty();
    });
    subWrap.appendChild(subLbl);
    subWrap.appendChild(subInp);
    container.appendChild(subWrap);

    // Zeile 3: Tabellen-Steuerleiste (+ Zeile, + Spalte, Total-Zeile Checkbox, Excel-Hinweis)
    const controlsBar = document.createElement("div");
    controlsBar.style.display = "flex";
    controlsBar.style.justifyContent = "space-between";
    controlsBar.style.alignItems = "center";
    controlsBar.style.flexWrap = "wrap";
    controlsBar.style.gap = "8px";
    controlsBar.style.marginBottom = "6px";

    const btnGroup = document.createElement("div");
    btnGroup.style.display = "flex";
    btnGroup.style.gap = "6px";
    btnGroup.style.alignItems = "center";

    const addRowBtn = document.createElement("button");
    addRowBtn.type = "button";
    addRowBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addRowBtn.textContent = "+ Zeile";

    const addColBtn = document.createElement("button");
    addColBtn.type = "button";
    addColBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addColBtn.textContent = "+ Spalte";

    const totalToggleWrap = document.createElement("label");
    totalToggleWrap.style.display = "inline-flex";
    totalToggleWrap.style.alignItems = "center";
    totalToggleWrap.style.gap = "5px";
    totalToggleWrap.style.fontSize = "12px";
    totalToggleWrap.style.marginLeft = "8px";
    totalToggleWrap.style.cursor = "pointer";

    const totalCheckbox = document.createElement("input");
    totalCheckbox.type = "checkbox";
    totalCheckbox.checked = !!blk.highlight_last_row;
    totalCheckbox.addEventListener("change", function () {
      blk.highlight_last_row = totalCheckbox.checked;
      markDirty();
    });
    totalToggleWrap.appendChild(totalCheckbox);
    totalToggleWrap.appendChild(document.createTextNode("Letzte Zeile als Total hervorheben"));

    btnGroup.appendChild(addRowBtn);
    btnGroup.appendChild(addColBtn);
    btnGroup.appendChild(totalToggleWrap);

    const excelHint = document.createElement("span");
    excelHint.style.fontSize = "11.5px";
    excelHint.style.color = "#5A687C";
    excelHint.textContent = "Tipp: Bereiche direkt aus Excel kopieren und in eine Zelle einfügen (Ctrl+V)";

    controlsBar.appendChild(btnGroup);
    controlsBar.appendChild(excelHint);
    container.appendChild(controlsBar);

    // Zeile 4: Interaktives Daten-Grid
    const gridScroll = document.createElement("div");
    gridScroll.className = "table-editor-scroll";

    const renderGrid = () => {
      gridScroll.innerHTML = "";
      const tbl = document.createElement("table");
      tbl.className = "cms-grid-editor";

      if (!Array.isArray(blk.columns) || blk.columns.length === 0) {
        blk.columns = [{ field: "col_1", title: "Spalte 1", align: "left" }];
      }
      if (!Array.isArray(blk.rows)) {
        blk.rows = [];
      }

      // THEAD
      const thead = document.createElement("thead");
      const htr = document.createElement("tr");

      blk.columns.forEach(function (col, cIdx) {
        const th = document.createElement("th");
        const ctrl = document.createElement("div");
        ctrl.className = "grid-header-controls";

        const colInp = document.createElement("input");
        colInp.type = "text";
        colInp.className = "grid-col-title-input";
        colInp.value = col.title || "";
        colInp.addEventListener("input", function () {
          col.title = colInp.value;
          markDirty();
        });

        const alignBtn = document.createElement("button");
        alignBtn.type = "button";
        alignBtn.className = "grid-col-align-btn";
        alignBtn.title = "Spaltenausrichtung umschalten (Links / Zentriert / Rechts)";
        alignBtn.textContent = col.align === "right" ? "⇥R" : col.align === "center" ? "↔Z" : "⇤L";
        alignBtn.addEventListener("click", function () {
          col.align = col.align === "left" ? "right" : col.align === "right" ? "center" : "left";
          renderGrid();
          markDirty();
        });

        ctrl.appendChild(colInp);
        ctrl.appendChild(alignBtn);

        if (blk.columns.length > 1) {
          const delColBtn = document.createElement("button");
          delColBtn.type = "button";
          delColBtn.className = "grid-col-align-btn";
          delColBtn.title = "Spalte löschen";
          delColBtn.textContent = "✕";
          delColBtn.addEventListener("click", function () {
            const removedField = col.field;
            blk.columns.splice(cIdx, 1);
            blk.rows.forEach(function (r) {
              delete r[removedField];
            });
            renderGrid();
            markDirty();
          });
          ctrl.appendChild(delColBtn);
        }

        th.appendChild(ctrl);
        htr.appendChild(th);
      });

      const actionTh = document.createElement("th");
      actionTh.style.width = "38px";
      actionTh.style.minWidth = "38px";
      htr.appendChild(actionTh);
      thead.appendChild(htr);
      tbl.appendChild(thead);

      // TBODY
      const tbody = document.createElement("tbody");
      blk.rows.forEach(function (rowObj, rIdx) {
        const tr = document.createElement("tr");

        blk.columns.forEach(function (col, cIdx) {
          const td = document.createElement("td");
          const cellInp = document.createElement("input");
          cellInp.type = "text";
          cellInp.className = "grid-cell-input";
          cellInp.style.textAlign = col.align || "left";
          cellInp.value = rowObj[col.field] != null ? rowObj[col.field] : "";

          cellInp.addEventListener("input", function () {
            rowObj[col.field] = cellInp.value;
            markDirty();
          });

          // Excel Multi-Zellen Copy-Paste Support
          cellInp.addEventListener("paste", function (e) {
            const clipText = (e.clipboardData || window.clipboardData).getData("text/plain");
            if (!clipText || (clipText.indexOf("\t") === -1 && clipText.indexOf("\n") === -1)) {
              return; // Normales Einfügen in einzelne Zelle
            }
            e.preventDefault();
            const pastedRows = clipText
              .replace(/\r\n/g, "\n")
              .replace(/\r/g, "\n")
              .split("\n")
              .filter((line, idx, arr) => !(idx === arr.length - 1 && line === ""));

            pastedRows.forEach(function (line, rOffset) {
              const targetRowIdx = rIdx + rOffset;
              while (blk.rows.length <= targetRowIdx) {
                const emptyRow = {};
                blk.columns.forEach((c) => (emptyRow[c.field] = ""));
                blk.rows.push(emptyRow);
              }
              const cells = line.split("\t");
              cells.forEach(function (cellVal, cOffset) {
                const targetColIdx = cIdx + cOffset;
                if (targetColIdx >= blk.columns.length) {
                  const newField = "col_" + uid("c");
                  blk.columns.push({
                    field: newField,
                    title: "Spalte " + (blk.columns.length + 1),
                    align: "right",
                  });
                }
                const targetField = blk.columns[targetColIdx].field;
                blk.rows[targetRowIdx][targetField] = cellVal.trim();
              });
            });

            renderGrid();
            markDirty();
          });

          td.appendChild(cellInp);
          tr.appendChild(td);
        });

        const delTd = document.createElement("td");
        delTd.style.textAlign = "center";
        const delRowBtn = document.createElement("button");
        delRowBtn.type = "button";
        delRowBtn.className = "btn-icon-only danger";
        delRowBtn.title = "Zeile löschen";
        delRowBtn.textContent = "✕";
        delRowBtn.addEventListener("click", function () {
          blk.rows.splice(rIdx, 1);
          renderGrid();
          markDirty();
        });
        delTd.appendChild(delRowBtn);
        tr.appendChild(delTd);

        tbody.appendChild(tr);
      });

      tbl.appendChild(tbody);
      gridScroll.appendChild(tbl);
    };

    addRowBtn.addEventListener("click", function () {
      const newRow = {};
      blk.columns.forEach(function (c) {
        newRow[c.field] = "";
      });
      blk.rows.push(newRow);
      renderGrid();
      markDirty();
    });

    addColBtn.addEventListener("click", function () {
      const newField = "col_" + uid("f");
      blk.columns.push({
        field: newField,
        title: "Spalte " + (blk.columns.length + 1),
        align: "right",
      });
      blk.rows.forEach(function (r) {
        r[newField] = "";
      });
      renderGrid();
      markDirty();
    });

    renderGrid();
    container.appendChild(gridScroll);

    // Zeile 5: Quellenangabe
    const srcWrap = document.createElement("div");
    const srcLbl = document.createElement("label");
    srcLbl.className = "field-label";
    srcLbl.textContent = "Tabellen-Quelle / Fussnote";
    const srcInp = document.createElement("input");
    srcInp.type = "text";
    srcInp.className = "cms-input";
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
        if (btype === "textbox_pair") {
          state.article.blocks.push(createDefaultBlock("box_start"));
          state.article.blocks.push(createDefaultBlock("box_end"));
        } else {
          const newBlk = createDefaultBlock(btype);
          state.article.blocks.push(newBlk);
        }
        renderBlocksCanvas();
        markDirty();

        // Scrolle sanft zum neuen Block
        const pane = document.querySelector(".cms-editor-pane");
        if (pane) {
          setTimeout(function () {
            pane.scrollTo({ top: pane.scrollHeight, behavior: "smooth" });
          }, 60);
        }
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
      });
    });
  }

  // ==========================================================================
  // Gruppierte & Einklappbare Artikel-Sidebar + Such- & Publikations-Dialog
  // ==========================================================================

  const STATUS_LABELS = {
    draft: "Entwurf",
    review: "In Review",
    published: "Publiziert",
    archived: "Archiviert",
  };

  const TPL_LABELS = {
    investment_focus: "Investment Fokus",
    market_flash: "Market Flash",
  };

  const MONTH_NAMES_DE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
  ];

  function getArchiveMonthInfo(item) {
    const pub = (item.publication_date || "").trim();
    const m = pub.match(/^(\d{4})-(\d{2})/);
    if (m) {
      const year = m[1];
      const monthIdx = parseInt(m[2], 10) - 1;
      const monthLabel =
        (MONTH_NAMES_DE[monthIdx] || m[2]) + " " + year;
      return { key: year + "-" + m[2], label: monthLabel };
    }
    const upd = (item.updated_at || "").trim();
    const m2 = upd.match(/(\d{2})\.(\d{2})\.(\d{4})/);
    if (m2) {
      const year = m2[3];
      const monthIdx = parseInt(m2[2], 10) - 1;
      const monthLabel =
        (MONTH_NAMES_DE[monthIdx] || m2[2]) + " " + year;
      return { key: year + "-" + m2[2], label: monthLabel };
    }
    return { key: "0000-00", label: "Weitere Ausgaben" };
  }

  function selectArticleById(articleId) {
    if (!articleId) return;
    if (state.article && state.article.id === articleId) {
      closePubModal();
      return;
    }
    if (state.isDirty) {
      flushAutosave(false);
    }
    if (window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue(
        "lukb_select_article",
        { id: articleId, ts: Date.now() },
        { priority: "event" }
      );
    }
    closePubModal();
  }

  function buildSidebarArticleCard(item, activeId, compact) {
    const card = document.createElement("div");
    card.className =
      "article-card-item" +
      (compact ? " compact" : "") +
      (item.id === activeId ? " active" : "");

    const top = document.createElement("div");
    top.className = "article-card-top";

    const badge = document.createElement("span");
    badge.className = "status-badge status-" + (item.status || "draft");
    badge.textContent = STATUS_LABELS[item.status] || "Entwurf";

    const tplSpan = document.createElement("span");
    tplSpan.className = "article-card-tpl";
    tplSpan.textContent = TPL_LABELS[item.template_id] || item.template_id;

    top.appendChild(badge);
    top.appendChild(tplSpan);

    const title = document.createElement("div");
    title.className = "article-card-title";
    title.textContent = item.title || "Unbenannte Publikation";

    card.appendChild(top);
    card.appendChild(title);

    if (!compact && item.subtitle) {
      const sub = document.createElement("div");
      sub.className = "article-card-subtitle-line";
      sub.textContent = item.subtitle;
      card.appendChild(sub);
    }

    const metaRow = document.createElement("div");
    metaRow.className = "article-card-meta";

    const authorSpan = document.createElement("span");
    authorSpan.style.overflow = "hidden";
    authorSpan.style.textOverflow = "ellipsis";
    authorSpan.style.whiteSpace = "nowrap";
    authorSpan.textContent = item.authors_summary || "";

    const dateSpan = document.createElement("span");
    dateSpan.style.whiteSpace = "nowrap";
    dateSpan.textContent =
      item.status === "published" && item.publication_date
        ? item.publication_date
        : item.updated_at || "";

    metaRow.appendChild(authorSpan);
    metaRow.appendChild(dateSpan);
    card.appendChild(metaRow);

    card.addEventListener("click", function () {
      selectArticleById(item.id);
    });

    return card;
  }

  function renderArticleList(articles, activeId, searchActive) {
    const listContainer = document.getElementById("lukb-article-list");
    if (!listContainer) return;
    listContainer.innerHTML = "";

    const countBadge = document.getElementById("sidebar-article-count");
    if (countBadge) {
      countBadge.textContent = articles.length + " Artikel";
    }

    if (articles.length === 0) {
      const empty = document.createElement("div");
      empty.style.padding = "24px 12px";
      empty.style.textAlign = "center";
      empty.style.color = "#5A687C";
      empty.textContent = "Keine Artikel für diesen Filter gefunden.";
      listContainer.appendChild(empty);
      return;
    }

    const activeWorkItems = articles.filter(function (a) {
      return a.status === "draft" || a.status === "review";
    });
    const publishedItems = articles.filter(function (a) {
      return a.status === "published";
    });
    const archivedItems = articles.filter(function (a) {
      return a.status === "archived";
    });

    // 1. Sektion: In Bearbeitung (Entwurf & In Review) — immer oben angepinnt
    if (activeWorkItems.length > 0) {
      const workSec = document.createElement("div");
      workSec.className = "sidebar-group-section";

      const hdr = document.createElement("div");
      hdr.className = "sidebar-group-header";
      const hdrTitle = document.createElement("span");
      hdrTitle.textContent = "In Bearbeitung (Entwurf & Review)";
      const hdrCount = document.createElement("span");
      hdrCount.className = "sidebar-group-count";
      hdrCount.textContent = String(activeWorkItems.length);
      hdr.appendChild(hdrTitle);
      hdr.appendChild(hdrCount);
      workSec.appendChild(hdr);

      activeWorkItems.forEach(function (item) {
        workSec.appendChild(buildSidebarArticleCard(item, activeId, false));
      });

      listContainer.appendChild(workSec);
    }

    // 2. Sektion: Publiziert (Live im Portal) — gruppiert nach Monat & Jahr (einklappbar)
    if (publishedItems.length > 0) {
      const pubSec = document.createElement("div");
      pubSec.className = "sidebar-group-section";

      const hdr = document.createElement("div");
      hdr.className = "sidebar-group-header";
      const hdrTitle = document.createElement("span");
      hdrTitle.textContent = "Publiziert (Live im Portal)";
      const hdrCount = document.createElement("span");
      hdrCount.className = "sidebar-group-count";
      hdrCount.textContent = String(publishedItems.length);
      hdr.appendChild(hdrTitle);
      hdr.appendChild(hdrCount);
      pubSec.appendChild(hdr);

      // Gruppiere nach Monat/Jahr
      const groupsMap = {};
      const groupKeys = [];
      publishedItems.forEach(function (item) {
        const info = getArchiveMonthInfo(item);
        if (!groupsMap[info.key]) {
          groupsMap[info.key] = { key: info.key, label: info.label, items: [] };
          groupKeys.push(info.key);
        }
        groupsMap[info.key].items.push(item);
      });

      groupKeys.sort().reverse();

      groupKeys.forEach(function (gKey, idx) {
        const grp = groupsMap[gKey];
        const details = document.createElement("details");
        details.className = "sidebar-archive-month";

        const containsActive = grp.items.some(function (it) {
          return it.id === activeId;
        });
        const shouldOpen =
          searchActive ||
          containsActive ||
          (state.openArchiveMonths[gKey] !== undefined
            ? state.openArchiveMonths[gKey]
            : idx === 0);

        if (shouldOpen) {
          details.setAttribute("open", "open");
        }

        details.addEventListener("toggle", function () {
          state.openArchiveMonths[gKey] = details.open;
        });

        const summary = document.createElement("summary");
        const mLabel = document.createElement("span");
        mLabel.className = "sidebar-archive-month-label";
        mLabel.textContent = grp.label;
        const mCount = document.createElement("span");
        mCount.className = "sidebar-group-count";
        mCount.textContent = String(grp.items.length);
        summary.appendChild(mLabel);
        summary.appendChild(mCount);

        const body = document.createElement("div");
        body.className = "sidebar-archive-month-body";
        grp.items.forEach(function (item) {
          body.appendChild(buildSidebarArticleCard(item, activeId, true));
        });

        details.appendChild(summary);
        details.appendChild(body);
        pubSec.appendChild(details);
      });

      listContainer.appendChild(pubSec);
    }

    // 3. Sektion: Papierkorb / Archiv (Soft-Delete)
    if (archivedItems.length > 0) {
      const archSec = document.createElement("div");
      archSec.className = "sidebar-group-section";

      const hdr = document.createElement("div");
      hdr.className = "sidebar-group-header";
      hdr.style.color = "#7f8c8d";
      const hdrTitle = document.createElement("span");
      hdrTitle.textContent = "📦 Papierkorb / Archiv";
      const hdrCount = document.createElement("span");
      hdrCount.className = "sidebar-group-count";
      hdrCount.textContent = String(archivedItems.length);
      hdr.appendChild(hdrTitle);
      hdr.appendChild(hdrCount);
      archSec.appendChild(hdr);

      archivedItems.forEach(function (item) {
        archSec.appendChild(buildSidebarArticleCard(item, activeId, false));
      });

      listContainer.appendChild(archSec);
    }
  }

  function setSidebarCollapsed(collapsed) {
    state.sidebarCollapsed = !!collapsed;
    const ws =
      document.getElementById("lukb-workspace") ||
      document.querySelector(".cms-workspace");
    const btnTop = document.getElementById("btn-toggle-sidebar");
    if (ws) {
      if (state.sidebarCollapsed) {
        ws.classList.add("sidebar-collapsed");
      } else {
        ws.classList.remove("sidebar-collapsed");
      }
    }
    if (btnTop) {
      btnTop.textContent = state.sidebarCollapsed
        ? "☰ Sidebar einblenden"
        : "☰ Publikationen";
    }
  }

  function toggleSidebar() {
    setSidebarCollapsed(!state.sidebarCollapsed);
  }

  window.lukbToggleSidebar = toggleSidebar;
  window.lukbSetSidebarCollapsed = setSidebarCollapsed;

  // ==========================================================================
  // Such- & Publikations-Dialog (Modal / Command Palette, Ctrl+K)
  // ==========================================================================

  function populateModalCategoryDropdown() {
    const sel = document.getElementById("pub-modal-category-filter");
    if (!sel) return;
    const currentVal = sel.value || "all";
    const categories = [];
    (state.allArticles || []).forEach(function (a) {
      const cat = (a.category || "").trim();
      if (cat && categories.indexOf(cat) === -1) {
        categories.push(cat);
      }
    });
    categories.sort();

    sel.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "all";
    allOpt.textContent = "Alle Rubriken (" + categories.length + ")";
    sel.appendChild(allOpt);

    categories.forEach(function (cat) {
      const opt = document.createElement("option");
      opt.value = cat;
      opt.textContent = cat;
      sel.appendChild(opt);
    });

    if (categories.indexOf(currentVal) !== -1) {
      sel.value = currentVal;
    } else {
      sel.value = "all";
      state.modalFilter.category = "all";
    }
  }

  function updateModalStatusPillCounts() {
    const all = state.allArticles || [];
    const counts = {
      all: all.length,
      active_work: all.filter((a) => a.status !== "published").length,
      draft: all.filter((a) => a.status === "draft").length,
      review: all.filter((a) => a.status === "review").length,
      published: all.filter((a) => a.status === "published").length,
    };
    const baseLabels = {
      all: "Alle",
      active_work: "In Bearbeitung",
      draft: "Entwurf",
      review: "In Review",
      published: "Publiziert",
    };
    document.querySelectorAll("[data-modal-status]").forEach(function (btn) {
      const st = btn.getAttribute("data-modal-status");
      if (baseLabels[st] !== undefined) {
        btn.textContent = baseLabels[st] + " (" + (counts[st] || 0) + ")";
      }
      if (st === state.modalFilter.status) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  function renderPubModalTable() {
    const tbody = document.getElementById("pub-modal-tbody");
    const countBadge = document.getElementById("pub-modal-count-badge");
    const pagContainer = document.getElementById("pub-modal-pagination");
    if (!tbody) return;

    updateModalStatusPillCounts();

    const f = state.modalFilter;
    const q = (f.search || "").trim().toLowerCase();

    let filtered = (state.allArticles || []).filter(function (a) {
      if (f.status === "active_work" && a.status === "published") return false;
      if (
        f.status !== "all" &&
        f.status !== "active_work" &&
        a.status !== f.status
      ) {
        return false;
      }
      if (f.template !== "all" && a.template_id !== f.template) return false;
      if (f.category !== "all" && (a.category || "") !== f.category) return false;

      if (q) {
        const hay = [
          a.title || "",
          a.subtitle || "",
          a.category || "",
          a.authors_summary || "",
          a.publication_date || "",
          a.updated_by || "",
        ]
          .join(" ")
          .toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });

    // Sortierung
    filtered.sort(function (a, b) {
      if (f.sort === "title_asc") {
        return (a.title || "").localeCompare(b.title || "", "de");
      }
      if (f.sort === "pubdate_desc") {
        return (b.publication_date || "").localeCompare(a.publication_date || "");
      }
      return (b.updated_iso || "").localeCompare(a.updated_iso || "");
    });

    if (countBadge) {
      countBadge.textContent =
        filtered.length +
        (filtered.length === 1 ? " Publikation" : " Publikationen");
    }

    const totalPages = Math.max(1, Math.ceil(filtered.length / f.pageSize));
    if (f.page > totalPages) f.page = totalPages;
    if (f.page < 1) f.page = 1;

    const startIdx = (f.page - 1) * f.pageSize;
    const pageItems = filtered.slice(startIdx, startIdx + f.pageSize);

    tbody.innerHTML = "";
    if (pageItems.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.style.textAlign = "center";
      td.style.padding = "32px";
      td.style.color = "#5A687C";
      td.textContent = "Keine Publikationen für die gewählten Such- und Filterkriterien gefunden.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      pageItems.forEach(function (item) {
        const tr = document.createElement("tr");
        if (item.id === state.activeArticleId) {
          tr.className = "active-row";
        }

        // 1. Status
        const tdStatus = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = "status-badge status-" + (item.status || "draft");
        badge.textContent = STATUS_LABELS[item.status] || "Entwurf";
        tdStatus.appendChild(badge);

        // 2. Titel & Untertitel
        const tdTitle = document.createElement("td");
        const titleDiv = document.createElement("div");
        titleDiv.className = "pub-modal-row-title";
        titleDiv.textContent = item.title || "Unbenannte Publikation";
        tdTitle.appendChild(titleDiv);
        if (item.subtitle) {
          const subDiv = document.createElement("div");
          subDiv.className = "pub-modal-row-subtitle";
          subDiv.textContent = item.subtitle;
          tdTitle.appendChild(subDiv);
        }

        // 3. Rubrik & Template
        const tdCat = document.createElement("td");
        const catDiv = document.createElement("div");
        catDiv.style.fontWeight = "500";
        catDiv.style.fontSize = "12.5px";
        catDiv.textContent = item.category || "—";
        const tplDiv = document.createElement("div");
        tplDiv.className = "pub-modal-row-subtitle";
        tplDiv.textContent = TPL_LABELS[item.template_id] || item.template_id;
        tdCat.appendChild(catDiv);
        tdCat.appendChild(tplDiv);

        // 4. Autoren
        const tdAuthors = document.createElement("td");
        tdAuthors.style.fontSize = "12.5px";
        tdAuthors.textContent = item.authors_summary || "Investment Office";

        // 5. Publikationsdatum
        const tdPubDate = document.createElement("td");
        tdPubDate.style.fontSize = "12.5px";
        tdPubDate.style.whiteSpace = "nowrap";
        tdPubDate.textContent = item.publication_date || "—";

        // 6. Zuletzt geändert
        const tdUpdated = document.createElement("td");
        tdUpdated.style.fontSize = "12px";
        tdUpdated.style.color = "#5A687C";
        tdUpdated.textContent = item.updated_at || "—";

        // 7. Aktionen
        const tdActions = document.createElement("td");
        const actWrap = document.createElement("div");
        actWrap.className = "pub-modal-row-actions";

        const openBtn = document.createElement("button");
        openBtn.type = "button";
        openBtn.className = "btn-lukb btn-lukb-navy btn-lukb-sm";
        openBtn.style.padding = "3px 9px";
        openBtn.textContent = "Öffnen";
        openBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          selectArticleById(item.id);
        });

        const dupBtn = document.createElement("button");
        dupBtn.type = "button";
        dupBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        dupBtn.style.padding = "3px 8px";
        dupBtn.title = "Publikation als neuen Entwurf duplizieren";
        dupBtn.textContent = "Kopie";
        dupBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          if (window.Shiny && window.Shiny.setInputValue) {
            window.Shiny.setInputValue(
              "lukb_modal_article_action",
              { action: "duplicate", id: item.id, ts: Date.now() },
              { priority: "event" }
            );
          }
          closePubModal();
        });

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-lukb btn-lukb-danger-ghost btn-lukb-sm";
        delBtn.style.padding = "3px 7px";
        delBtn.title = "Publikation löschen";
        delBtn.textContent = "✕";
        delBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          if (
            window.confirm(
              'Möchten Sie die Publikation "' +
                (item.title || "") +
                '" wirklich löschen?'
            )
          ) {
            if (window.Shiny && window.Shiny.setInputValue) {
              window.Shiny.setInputValue(
                "lukb_modal_article_action",
                { action: "delete", id: item.id, ts: Date.now() },
                { priority: "event" }
              );
            }
          }
        });

        actWrap.appendChild(openBtn);
        actWrap.appendChild(dupBtn);
        actWrap.appendChild(delBtn);
        tdActions.appendChild(actWrap);

        tr.appendChild(tdStatus);
        tr.appendChild(tdTitle);
        tr.appendChild(tdCat);
        tr.appendChild(tdAuthors);
        tr.appendChild(tdPubDate);
        tr.appendChild(tdUpdated);
        tr.appendChild(tdActions);

        tr.addEventListener("click", function () {
          selectArticleById(item.id);
        });

        tbody.appendChild(tr);
      });
    }

    // Pagination Controls
    if (pagContainer) {
      pagContainer.innerHTML = "";
      if (totalPages > 1) {
        const prevBtn = document.createElement("button");
        prevBtn.type = "button";
        prevBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        prevBtn.disabled = f.page <= 1;
        prevBtn.textContent = "« Zurück";
        prevBtn.addEventListener("click", function () {
          if (f.page > 1) {
            f.page--;
            renderPubModalTable();
          }
        });
        pagContainer.appendChild(prevBtn);

        const pageInfo = document.createElement("span");
        pageInfo.style.fontSize = "12px";
        pageInfo.style.color = "#002855";
        pageInfo.style.padding = "0 8px";
        pageInfo.textContent = "Seite " + f.page + " / " + totalPages;
        pagContainer.appendChild(pageInfo);

        const nextBtn = document.createElement("button");
        nextBtn.type = "button";
        nextBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        nextBtn.disabled = f.page >= totalPages;
        nextBtn.textContent = "Weiter »";
        nextBtn.addEventListener("click", function () {
          if (f.page < totalPages) {
            f.page++;
            renderPubModalTable();
          }
        });
        pagContainer.appendChild(nextBtn);
      }
    }
  }

  function openPubModal() {
    const backdrop = document.getElementById("lukb-pub-modal-backdrop");
    if (!backdrop) return;
    state.modalOpen = true;
    populateModalCategoryDropdown();
    renderPubModalTable();
    backdrop.style.display = "flex";
    const searchInput = document.getElementById("pub-modal-search");
    if (searchInput) {
      setTimeout(function () {
        searchInput.focus();
        searchInput.select();
      }, 30);
    }
  }

  function closePubModal() {
    const backdrop = document.getElementById("lukb-pub-modal-backdrop");
    if (!backdrop) return;
    state.modalOpen = false;
    backdrop.style.display = "none";
  }

  window.lukbOpenPubModal = openPubModal;
  window.lukbClosePubModal = closePubModal;

  function bindSidebarAndModalListeners() {
    const btnToggleTop = document.getElementById("btn-toggle-sidebar");
    const btnToggleInner = document.getElementById("btn-sidebar-collapse-inner");
    const btnOpenModalTop = document.getElementById("btn-open-pub-modal");
    const btnOpenModalSidebar = document.getElementById("btn-sidebar-open-modal");
    const btnCloseModal = document.getElementById("btn-close-pub-modal");
    const btnModalNew = document.getElementById("btn-modal-new-article");
    const backdrop = document.getElementById("lukb-pub-modal-backdrop");

    if (btnToggleTop && !btnToggleTop.getAttribute("onclick")) {
      btnToggleTop.addEventListener("click", toggleSidebar);
    }
    if (btnToggleInner && !btnToggleInner.getAttribute("onclick")) {
      btnToggleInner.addEventListener("click", function () {
        setSidebarCollapsed(true);
      });
    }
    if (btnOpenModalTop && !btnOpenModalTop.getAttribute("onclick")) {
      btnOpenModalTop.addEventListener("click", openPubModal);
    }
    if (btnOpenModalSidebar && !btnOpenModalSidebar.getAttribute("onclick")) {
      btnOpenModalSidebar.addEventListener("click", openPubModal);
    }
    if (btnCloseModal && !btnCloseModal.getAttribute("onclick")) {
      btnCloseModal.addEventListener("click", closePubModal);
    }
    if (btnModalNew) {
      btnModalNew.addEventListener("click", function () {
        if (window.Shiny && window.Shiny.setInputValue) {
          window.Shiny.setInputValue(
            "lukb_modal_article_action",
            { action: "create", ts: Date.now() },
            { priority: "event" }
          );
        }
        closePubModal();
      });
    }
    if (backdrop) {
      backdrop.addEventListener("click", function (ev) {
        if (ev.target === backdrop) {
          closePubModal();
        }
      });
    }

    const searchInput = document.getElementById("pub-modal-search");
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        state.modalFilter.search = searchInput.value || "";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    }

    document.querySelectorAll("[data-modal-status]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.modalFilter.status = btn.getAttribute("data-modal-status") || "all";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    });

    const tplSelect = document.getElementById("pub-modal-template-filter");
    if (tplSelect) {
      tplSelect.addEventListener("change", function () {
        state.modalFilter.template = tplSelect.value || "all";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    }

    const catSelect = document.getElementById("pub-modal-category-filter");
    if (catSelect) {
      catSelect.addEventListener("change", function () {
        state.modalFilter.category = catSelect.value || "all";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    }

    const sortSelect = document.getElementById("pub-modal-sort");
    if (sortSelect) {
      sortSelect.addEventListener("change", function () {
        state.modalFilter.sort = sortSelect.value || "updated_desc";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    }

    // Globale Shortcuts: Ctrl+K (Such- & Publikations-Dialog), Ctrl+B (Sidebar ein-/ausklappen), Esc (Schliessen)
    document.addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key && ev.key.toLowerCase() === "k") {
        ev.preventDefault();
        if (state.modalOpen) {
          closePubModal();
        } else {
          openPubModal();
        }
      } else if (
        (ev.ctrlKey || ev.metaKey) &&
        ev.key &&
        ev.key.toLowerCase() === "b" &&
        !ev.target.closest(".richtext-surface")
      ) {
        ev.preventDefault();
        toggleSidebar();
      } else if (ev.key === "Escape" && state.modalOpen) {
        ev.preventDefault();
        closePubModal();
      }
    });
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
      if (Array.isArray(msg.available_tickers)) {
        state.availableTickers = msg.available_tickers;
        indexTickerItems(msg.available_tickers);
      }
      if (msg.assets) {
        Object.keys(msg.assets).forEach(function (k) {
          state.assetCache[k] = msg.assets[k];
        });
      }
      renderMetadataForm();
      renderBlocksCanvas();
      applyPeerFocusDecorations();
      setAutosaveIndicator("saved", "Geladen & synchronisiert");
    });

    // 2. Aktualisiert die Artikel-Liste in der linken Sidebar sowie den Modal-Katalog
    window.Shiny.addCustomMessageHandler("lukb_update_article_list", function (msg) {
      state.sidebarArticles = msg.articles || [];
      state.allArticles = msg.all_articles || msg.articles || [];
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
              const existingCard = canvas.querySelector('[data-block-id="' + blk.id + '"]');
              const newCard = buildBlockCardElement(blk, idx, insideBox);
              if (existingCard) {
                canvas.replaceChild(newCard, existingCard);
              } else {
                canvas.appendChild(newCard);
              }
            }
            if (blk.type === "box_end") insideBox = false;
          });
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

    // 4. Aktualisiert die Live-Preview (Typst SVG Seiten + Web HTML)
    window.Shiny.addCustomMessageHandler("lukb_update_preview", function (msg) {
      const pdfContainer = document.getElementById("preview-container-pdf");
      const webIframe = document.getElementById("preview-iframe-web");
      const pageBadge = document.getElementById("preview-page-count");

      if (pdfContainer && Array.isArray(msg.svg_pages)) {
        pdfContainer.innerHTML = "";
        msg.svg_pages.forEach(function (svgMarkup, idx) {
          const pageWrap = document.createElement("div");
          pageWrap.className = "typst-svg-page";
          pageWrap.innerHTML = svgMarkup;
          pdfContainer.appendChild(pageWrap);
        });
        if (pageBadge) {
          pageBadge.textContent =
            msg.svg_pages.length + (msg.svg_pages.length === 1 ? " PDF-Seite (Typst)" : " PDF-Seiten (Typst)");
        }
      }

      if (webIframe && typeof msg.web_html === "string") {
        webIframe.srcdoc = msg.web_html;
      }
    });
  }

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

  function initEditorApp() {
    if (state._initialized) return;
    state._initialized = true;
    bindMetadataStaticListeners();
    bindAddBlockButtons();
    bindSidebarAndModalListeners();
    bindFocusTrackingListeners();
    bindDropdownListeners();
    registerShinyHandlers();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initEditorApp);
  } else {
    initEditorApp();
  }
})();
