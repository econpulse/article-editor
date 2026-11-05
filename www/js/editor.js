/**
 * LUKB Investment Office — Interaktiver Drag-and-Drop Block-Editor & Autosave-Engine
 * Arbeitet 100% ohne Node.js/Vite-Build-Server direkt mit Shiny for Python auf Posit Connect.
 */

(function () {
  "use strict";

  const state = {
    article: null,
    baseArticle: null, // Snapshot für 3-Wege-Merge bei gleichzeitigem Editieren
    assetCache: {}, // asset_id -> data_uri
    isDirty: false,
    autosaveTimer: null,
    sortableInstance: null,
    previewMode: "pdf", // "pdf" (Typst SVG) | "web" (HTML5)
    selfSessionId: "",
    peers: [], // Aktive Co-Autoren im selben Artikel
    currentFocusedTarget: "",
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
    if (state.autosaveTimer) {
      clearTimeout(state.autosaveTimer);
    }
    state.autosaveTimer = setTimeout(function () {
      flushAutosave(false);
    }, 1000);
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
        return "Grafik-Container";
      case "table":
        return "Daten-Tabelle";
      case "callout":
        return "Kernaussagen / Callout";
      case "box_start":
        return "▼ START: Farbliche Textbox (alle Blöcke bis ENDE liegen in dieser Box)";
      case "box_end":
        return "▲ ENDE: Farbliche Textbox";
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
    } else if (blk.type === "table") {
      buildTableBlockBody(body, blk);
    }

    card.appendChild(body);
    return card;
  }

  // ==========================================================================
  // Spezifische Block-Editoren
  // ==========================================================================

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

    toolbar.appendChild(btnGroup);
    if (extraRightEl) {
      toolbar.appendChild(extraRightEl);
    }

    editable.addEventListener("input", function () {
      onChange(editable.innerHTML);
    });

    // Verhindere fremde Styles beim Einfügen aus Word/Webseiten
    editable.addEventListener("paste", function (e) {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text);
      onChange(editable.innerHTML);
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

    // Zeile 3: Drag-and-Drop Grafik-Upload & Vorschau
    const dropzone = document.createElement("div");
    dropzone.className = "figure-upload-zone";

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
        caption.textContent = "Klicken oder neue Grafikdatei (SVG / PNG / JPG) hierher ziehen, um Grafik zu ersetzen";
        dropzone.appendChild(caption);
      } else {
        const msg = document.createElement("div");
        msg.innerHTML =
          "<strong style='color:#002855;'>Grafikdatei hierher ziehen (Drag & Drop)</strong> oder klicken zum Auswählen<br/>" +
          "<span style='font-size:12px;color:#5A687C;'>Unterstützt Vektorgrafiken (SVG) sowie hochauflösende PNG / JPG (wird sicher in der MSSQL-DB gespeichert)</span>";
        dropzone.appendChild(msg);
      }
    };

    renderDropzoneInner();

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

        if (window.Shiny && window.Shiny.setInputValue) {
          window.Shiny.setInputValue(
            "lukb_upload_asset",
            {
              asset_id: newAssetId,
              article_id: state.article.id,
              filename: file.name,
              mime_type: file.type || (file.name.endsWith(".svg") ? "image/svg+xml" : "image/png"),
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

    dropzone.addEventListener("click", function () {
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
  // Artikel-Liste in der linken Sidebar (1-Klick-Wechsel)
  // ==========================================================================

  function renderArticleList(articles, activeId) {
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

    const statusLabels = {
      draft: "Entwurf",
      review: "In Review",
      published: "Publiziert",
    };

    const tplLabels = {
      investment_focus: "Investment Fokus",
      market_flash: "Market Flash",
    };

    articles.forEach(function (item) {
      const card = document.createElement("div");
      card.className = "article-card-item" + (item.id === activeId ? " active" : "");

      const top = document.createElement("div");
      top.className = "article-card-top";

      const badge = document.createElement("span");
      badge.className = "status-badge status-" + (item.status || "draft");
      badge.textContent = statusLabels[item.status] || "Entwurf";

      const tplSpan = document.createElement("span");
      tplSpan.className = "article-card-tpl";
      tplSpan.textContent = tplLabels[item.template_id] || item.template_id;

      top.appendChild(badge);
      top.appendChild(tplSpan);

      const title = document.createElement("div");
      title.className = "article-card-title";
      title.textContent = item.title || "Unbenannte Publikation";

      const metaRow = document.createElement("div");
      metaRow.className = "article-card-meta";

      const authorSpan = document.createElement("span");
      authorSpan.style.overflow = "hidden";
      authorSpan.style.textOverflow = "ellipsis";
      authorSpan.style.whiteSpace = "nowrap";
      authorSpan.textContent = item.authors_summary || "";

      const dateSpan = document.createElement("span");
      dateSpan.style.whiteSpace = "nowrap";
      dateSpan.textContent = item.updated_at || "";

      metaRow.appendChild(authorSpan);
      metaRow.appendChild(dateSpan);

      card.appendChild(top);
      card.appendChild(title);
      card.appendChild(metaRow);

      card.addEventListener("click", function () {
        if (state.article && state.article.id === item.id) return;
        // Falls ungespeicherte Änderungen vorliegen, sofort vor dem Wechsel speichern!
        if (state.isDirty) {
          flushAutosave(false);
        }
        if (window.Shiny && window.Shiny.setInputValue) {
          window.Shiny.setInputValue(
            "lukb_select_article",
            { id: item.id, ts: Date.now() },
            { priority: "event" }
          );
        }
      });

      listContainer.appendChild(card);
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

    // 2. Aktualisiert die Artikel-Liste in der linken Sidebar
    window.Shiny.addCustomMessageHandler("lukb_update_article_list", function (msg) {
      renderArticleList(msg.articles || [], msg.active_id || "");
    });

    // 3. Bestätigt erfolgreichen Autosave
    window.Shiny.addCustomMessageHandler("lukb_autosave_ack", function (msg) {
      if (msg.article && !state.isDirty) {
        state.baseArticle = deepClone(msg.article);
      }
      if (!state.isDirty) {
        const suffix = msg.merged ? " (mit Co-Autor zusammengeführt)" : "";
        setAutosaveIndicator("saved", "Gespeichert um " + (msg.saved_at || "") + suffix);
      }
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

  document.addEventListener("DOMContentLoaded", function () {
    bindMetadataStaticListeners();
    bindAddBlockButtons();
    bindFocusTrackingListeners();
    registerShinyHandlers();
  });
})();
