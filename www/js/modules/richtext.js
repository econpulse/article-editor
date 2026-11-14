/**
 * LUKB Editor Modul: RichText-Editor, Popovers (Link, Glossar, Fussnote) & Glossar-Scanner
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function markDirty() { return E.markDirty.apply(this, arguments); }
  function sanitizeRichTextHtml() { return E.sanitizeRichTextHtml.apply(this, arguments); }
  const state = E.state;

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

  function openLinkPopover(targetOrContext, editable, onChange) {
    closeActivePopover();

    const isExistingAnchor =
      targetOrContext &&
      targetOrContext.nodeType === 1 &&
      targetOrContext.tagName === "A";
    const anchorEl = isExistingAnchor ? targetOrContext : null;
    const savedRange = !isExistingAnchor ? targetOrContext : null;

    const popover = document.createElement("div");
    popover.className = "lukb-term-popover";

    const header = document.createElement("div");
    header.className = "lukb-popover-header";
    header.innerHTML = isExistingAnchor
      ? "<span>🔗 Link bearbeiten</span>"
      : "<span>🔗 Link einfügen</span>";
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "btn-icon-only";
    closeBtn.textContent = "✕";
    closeBtn.style.padding = "0 4px";
    closeBtn.addEventListener("click", closeActivePopover);
    header.appendChild(closeBtn);
    popover.appendChild(header);

    const textLbl = document.createElement("label");
    textLbl.className = "field-label";
    textLbl.style.fontSize = "11px";
    textLbl.style.marginBottom = "3px";
    textLbl.textContent = "Angezeigter Link-Text:";
    popover.appendChild(textLbl);

    const textInp = document.createElement("input");
    textInp.type = "text";
    textInp.className = "cms-input font-medium";
    textInp.style.marginBottom = "8px";
    textInp.placeholder = "z.B. Publikation öffnen";
    textInp.value = anchorEl
      ? anchorEl.textContent.trim()
      : (savedRange ? savedRange.toString().trim() : "");
    popover.appendChild(textInp);

    const urlLbl = document.createElement("label");
    urlLbl.className = "field-label";
    urlLbl.style.fontSize = "11px";
    urlLbl.style.marginBottom = "3px";
    urlLbl.textContent = "Ziel-URL (öffnet im neuen Tab):";
    popover.appendChild(urlLbl);

    const urlInp = document.createElement("input");
    urlInp.type = "url";
    urlInp.className = "cms-input";
    urlInp.placeholder = "https://www.lukb.ch/...";
    urlInp.value = anchorEl ? (anchorEl.getAttribute("href") || "") : "";
    popover.appendChild(urlInp);

    const actions = document.createElement("div");
    actions.className = "lukb-popover-actions";

    if (anchorEl) {
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "btn-lukb btn-lukb-outline-light btn-lukb-sm";
      removeBtn.style.color = "#DC2626";
      removeBtn.style.borderColor = "#FCA5A5";
      removeBtn.textContent = "✕ Link entfernen";
      removeBtn.title = "Entfernt den Link und behält den Text";
      removeBtn.addEventListener("click", function () {
        const textNode = document.createTextNode(anchorEl.textContent);
        anchorEl.parentNode.replaceChild(textNode, anchorEl);
        closeActivePopover();
        onChange(editable.innerHTML);
        markDirty();
      });
      actions.appendChild(removeBtn);
    } else {
      const spacer = document.createElement("span");
      actions.appendChild(spacer);
    }

    const applyLink = function () {
      let href = (urlInp.value || "").trim();
      if (!href) {
        urlInp.focus();
        return;
      }
      if (!/^(https?:\/\/|mailto:)/i.test(href)) {
        href = "https://" + href;
      }
      const linkText = (textInp.value || "").trim() || href;

      if (anchorEl) {
        anchorEl.setAttribute("href", href);
        anchorEl.setAttribute("target", "_blank");
        anchorEl.setAttribute("rel", "noopener noreferrer");
        anchorEl.textContent = linkText;
      } else {
        const a = document.createElement("a");
        a.setAttribute("href", href);
        a.setAttribute("target", "_blank");
        a.setAttribute("rel", "noopener noreferrer");
        a.textContent = linkText;

        if (savedRange) {
          savedRange.deleteContents();
          savedRange.insertNode(a);
          const spaceNode = document.createTextNode("\u00A0");
          if (a.parentNode) {
            a.parentNode.insertBefore(spaceNode, a.nextSibling);
          }
        } else {
          editable.appendChild(a);
        }
      }
      closeActivePopover();
      onChange(editable.innerHTML);
      markDirty();
    };

    urlInp.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        applyLink();
      } else if (ev.key === "Escape") {
        closeActivePopover();
      }
    });

    textInp.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        urlInp.focus();
      } else if (ev.key === "Escape") {
        closeActivePopover();
      }
    });

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn-lukb btn-lukb-primary btn-lukb-sm";
    saveBtn.textContent = "Übernehmen";
    saveBtn.addEventListener("click", applyLink);

    actions.appendChild(saveBtn);
    popover.appendChild(actions);

    document.body.appendChild(popover);
    activePopover = popover;
    popover.addEventListener("mousedown", function (ev) {
      ev.stopPropagation();
    });

    let rect = null;
    if (anchorEl) {
      rect = anchorEl.getBoundingClientRect();
    } else if (savedRange && savedRange.getBoundingClientRect) {
      const r = savedRange.getBoundingClientRect();
      rect = r && (r.width > 0 || r.height > 0) ? r : editable.getBoundingClientRect();
    } else {
      rect = editable.getBoundingClientRect();
    }
    const clampedTop = Math.max(10, Math.min(window.innerHeight - 230, rect.bottom + 6));
    popover.style.position = "fixed";
    popover.style.top = clampedTop + "px";
    popover.style.left = Math.max(10, Math.min(window.innerWidth - 340, rect.left)) + "px";

    setTimeout(function () {
      if (textInp.value.trim()) {
        urlInp.focus();
      } else {
        textInp.focus();
      }
    }, 10);
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

    // Externer Link Button (target="_blank", ohne Unterstreichung, mit Pfeilsymbol)
    const linkBtn = document.createElement("button");
    linkBtn.type = "button";
    linkBtn.className = "rt-btn";
    linkBtn.textContent = "🔗 Link";
    linkBtn.title = "Link einfügen oder bearbeiten (öffnet im neuen Tab mit Pfeilsymbol, ohne Unterstreichung)";
    linkBtn.addEventListener("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const sel = window.getSelection();
      let range = null;
      let existingAnchor = null;
      if (sel && sel.rangeCount > 0) {
        const candidate = sel.getRangeAt(0);
        if (editable.contains(candidate.commonAncestorContainer)) {
          range = candidate.cloneRange();
          const containerEl =
            candidate.commonAncestorContainer.nodeType === 1
              ? candidate.commonAncestorContainer
              : candidate.commonAncestorContainer.parentElement;
          if (containerEl) {
            existingAnchor = containerEl.closest("a");
          }
        }
      }
      if (existingAnchor && editable.contains(existingAnchor)) {
        openLinkPopover(existingAnchor, editable, onChange);
      } else {
        if (!range) {
          range = document.createRange();
          const lastP = editable.querySelector("p:last-of-type");
          range.selectNodeContents(lastP || editable);
          range.collapse(false);
        }
        openLinkPopover(range, editable, onChange);
      }
    });
    btnGroup.appendChild(linkBtn);

    toolbar.appendChild(btnGroup);
    if (extraRightEl) {
      toolbar.appendChild(extraRightEl);
    }

    editable.addEventListener("input", function () {
      onChange(sanitizeRichTextHtml(editable.innerHTML));
      updateGlossaryBlockPreviews();
    });

    editable.addEventListener("blur", function () {
      onChange(sanitizeRichTextHtml(editable.innerHTML));
    });

    editable.addEventListener("click", function (e) {
      const linkEl = e.target.closest("a");
      if (linkEl && editable.contains(linkEl)) {
        e.preventDefault();
        e.stopPropagation();
        openLinkPopover(linkEl, editable, onChange);
        return;
      }
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


  Object.assign(E, {
    activePopover: activePopover,
    buildCalloutBlockBody: buildCalloutBlockBody,
    buildGlossaryBlockBody: buildGlossaryBlockBody,
    buildRichTextBlockBody: buildRichTextBlockBody,
    closeActivePopover: closeActivePopover,
    createRichTextWidget: createRichTextWidget,
    openFootnotePopover: openFootnotePopover,
    openGlossaryTermPopover: openGlossaryTermPopover,
    openLinkPopover: openLinkPopover,
    renderGlossaryDetectedSection: renderGlossaryDetectedSection,
    scanArticleGlossaryTerms: scanArticleGlossaryTerms,
    updateGlossaryBlockPreviews: updateGlossaryBlockPreviews,
  });
})();
