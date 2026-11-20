/**
 * LUKB Editor Modul: RichText-Editor, Popovers (Link, Glossar, Fussnote) & Glossar-Scanner
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function createSimpleLayoutSelect() { return E.createSimpleLayoutSelect.apply(this, arguments); }
  function markDirty() { return E.markDirty.apply(this, arguments); }
  function sanitizeRichTextHtml() { return E.sanitizeRichTextHtml.apply(this, arguments); }
  const state = E.state;

  function scanArticleGlossaryTerms() {
    if (!state.article || !Array.isArray(state.article.blocks)) return [];
    const termsMap = new Map();

    const scanHtml = (htmlStr) => {
      if (!htmlStr || htmlStr.indexOf("glossary-term") === -1) return;
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
      } else if (b.type === "media_text") {
        scanHtml(b.html);
        scanHtml(b.aside_html);
      }
    });

    const res = [];
    termsMap.forEach((definition, term) => {
      res.push({ term: term, definition: definition });
    });
    res.sort((a, b) => a.term.localeCompare(b.term));
    return res;
  }

  let _glossaryPreviewTimer = null;

  function updateGlossaryBlockPreviews() {
    const boxes = document.querySelectorAll(".glossary-auto-detected-box");
    if (!boxes || boxes.length === 0) return;
    const autoTerms = scanArticleGlossaryTerms();
    boxes.forEach(box => {
      const parent = box.closest(".cms-block-card");
      if (parent && parent.dataset.blockId) {
        const blk = (state.article.blocks || []).find(b => b.id === parent.dataset.blockId);
        if (blk && blk.type === "glossary") {
          renderGlossaryDetectedSection(box, blk, autoTerms);
        }
      }
    });
  }

  function scheduleGlossaryBlockPreviewsUpdate(delayMs) {
    if (_glossaryPreviewTimer) clearTimeout(_glossaryPreviewTimer);
    _glossaryPreviewTimer = setTimeout(function () {
      _glossaryPreviewTimer = null;
      updateGlossaryBlockPreviews();
    }, typeof delayMs === "number" ? delayMs : 180);
  }

  function renderGlossaryDetectedSection(container, blk, preScannedTerms) {
    container.innerHTML = "";
    const autoTerms = Array.isArray(preScannedTerms) ? preScannedTerms : scanArticleGlossaryTerms();

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
      row.innerHTML = `<span class="glossary-detected-term">${E.escapeHtml(item.term)}</span> — ` +
        `<span class="glossary-detected-def">${E.escapeHtml(item.definition)}</span>`;
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
    const layoutSel = createSimpleLayoutSelect(blk);
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

  /**
   * Bereinigt aus PDFs oder Dokumenten kopierten Fließtext beim Einfügen:
   * - Entfernt harte, layoutbedingte Zeilenumbrüche mitten im Fließtext.
   * - Führt getrennte Silben (z.B. "Wirtschafts-\nprognose" -> "Wirtschaftsprognose") wieder zusammen.
   * - Bewahrt Ergänzungsstriche ("Ein-\nund Auszahlungen" -> "Ein- und Auszahlungen")
   *   und zusammengesetzte Begriffe ("Online-\nBanking" -> "Online-Banking", "COVID-19").
   * - Bewahrt bewusst gesetzte Zeilenumbrüche:
   *   a) Absatzwechsel (mind. zwei Zeilenumbrüche bzw. Leerzeilen)
   *   b) Aufzählungen & nummerierte Listen (•, -, –, 1., a) etc.)
   *   c) Doppelpunkt-Einleitungen vor Aufzählungen oder Zitaten
   * - Ignoriert Abkürzungen (z. B., u. a.) und Dezimalzahlen (1.5 %), damit diese nicht
   *   fälschlich als Aufzählung interpretiert werden.
   */
  function cleanPdfPastedText(rawText) {
    if (!rawText || typeof rawText !== "string") return "";

    // 1. Zeilenenden vereinheitlichen (Windows \r\n -> \n)
    let t = rawText.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    // 2. Geschützte Leerzeichen & unsichtbare Steuerzeichen normalisieren
    t = t.replace(/\u00A0/g, " ").replace(/\u200B/g, "");

    // 3. Weiche Trennstriche (Soft-Hyphen / &shy;) am Zeilenende oder im Text entfernen
    t = t.replace(/\u00AD\s*\n\s*/g, "");
    t = t.replace(/\u00AD/g, "");

    // 4. In Absatzblöcke trennen (mind. 2 Newlines = bewusster Absatzwechsel)
    const chunks = t.split(/\n[ \t]*\n+/);
    const cleanedChunks = [];

    const bulletRe = /^[•·▪▫■□✦✓✔➔➜→➢►]\s*/;
    const dashBulletRe = /^[–—\-*]\s+/;
    const numberedOrLetterRe = /^(?:\d+[\.\)]|\(\d+\)|\[\d+\]|[a-zA-Z]\)|\([a-zA-Z]\)|\[[a-zA-Z]\]|[ivxIVX]+[\.\)]|\([ivxIVX]+\))\s+/;
    const letterDotRe = /^[a-zA-Z]\.\s+/;
    const abbrevRe = /^(?:z\.\s*B\.|u\.\s*a\.|d\.\s*h\.|e\.\s*g\.|i\.\s*e\.|o\.\s*ä\.|s\.\s*o\.|s\.\s*u\.|v\.\s*a\.)/i;
    const conjunctionRe = /^(?:und|oder|sowie|bzw\.?|respektive|wie|aber|bis|als)\b/i;
    const punctEndRe = /[:.;!?»”\"'\)]\s*$/;

    function isListItemStart(line, prevLine, prevWasList) {
      const trimmed = line.trim();
      if (bulletRe.test(trimmed) || dashBulletRe.test(trimmed)) {
        return true;
      }
      if (numberedOrLetterRe.test(trimmed) || letterDotRe.test(trimmed)) {
        if (abbrevRe.test(trimmed)) {
          return false;
        }
        // Gültige Aufzählung, wenn vorherige Zeile bereits Liste war,
        // oder am Blockanfang, oder die vorherige Zeile mit Satzzeichen endete.
        if (prevWasList || !prevLine || punctEndRe.test(prevLine)) {
          return true;
        }
        return false;
      }
      return false;
    }

    for (let cIdx = 0; cIdx < chunks.length; cIdx++) {
      const chunk = chunks[cIdx];
      const lines = chunk.split("\n");

      if (lines.length <= 1) {
        cleanedChunks.push(lines[0].replace(/[ \t]{2,}/g, " ").trim());
        continue;
      }

      const resultLines = [];
      let currentLine = lines[0].replace(/[ \t]{2,}/g, " ").trim();
      let currIsList = isListItemStart(currentLine, "", false);

      for (let i = 1; i < lines.length; i++) {
        const nextLine = lines[i].replace(/[ \t]{2,}/g, " ").trim();
        if (!nextLine) continue;

        const nextIsList = isListItemStart(nextLine, currentLine, currIsList);
        // Prüfen auf kurze Doppelpunkt-Einzeiler (z.B. "Die Schwerpunkte:", "Hinweis:")
        const isColonHeading =
          /:$/.test(currentLine) &&
          currentLine.length < 80 &&
          !/^[a-zäöüß]/.test(nextLine);

        if (nextIsList || isColonHeading) {
          resultLines.push(currentLine);
          currentLine = nextLine;
          currIsList = nextIsList;
        } else {
          // Zeilenumbruch entfernen und Fließtext zusammenfügen
          const hyphenMatch = currentLine.match(/([a-zA-ZäöüÄÖÜß]+)-$/);
          const dashMatch = currentLine.match(/\s+[-–—]$/);

          if (dashMatch) {
            // Gedankenstrich am Zeilenende
            currentLine = currentLine.replace(/\s+[-–—]$/, " –") + " " + nextLine;
          } else if (hyphenMatch) {
            if (conjunctionRe.test(nextLine)) {
              // Ergänzungsstrich: "Ein- und Auszahlungen"
              currentLine = currentLine + " " + nextLine;
            } else if (/^[A-ZÄÖÜ\d\/]/.test(nextLine)) {
              // Zusammensetzung mit Grossbuchstaben, Zahl oder Slash: "Online-Banking", "COVID-19"
              currentLine = currentLine + nextLine;
            } else if (/^[a-zäöüß]/.test(nextLine)) {
              // Silbentrennung: Bindestrich entfernen ("Wirtschafts- + prognose" -> "Wirtschaftsprognose")
              currentLine = currentLine.slice(0, -1) + nextLine;
            } else {
              currentLine = currentLine + " " + nextLine;
            }
          } else {
            currentLine = currentLine + " " + nextLine;
          }
        }
      }

      if (currentLine) {
        resultLines.push(currentLine);
      }
      cleanedChunks.push(resultLines.join("\n"));
    }

    return cleanedChunks.join("\n\n");
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
      scheduleGlossaryBlockPreviewsUpdate();
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

    // Verhindere fremde Styles und bereinige ungewollte Zeilenumbrüche aus PDFs
    editable.addEventListener("paste", function (e) {
      e.preventDefault();
      const rawText = (e.clipboardData || window.clipboardData).getData("text/plain");
      const text = cleanPdfPastedText(rawText);
      document.execCommand("insertText", false, text);
      onChange(sanitizeRichTextHtml(editable.innerHTML));
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

    const layoutSel = createSimpleLayoutSelect(blk, "180px");

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
    qTextarea.addEventListener("paste", function (e) {
      e.preventDefault();
      const rawText = (e.clipboardData || window.clipboardData).getData("text/plain");
      const cleaned = cleanPdfPastedText(rawText);
      if (!document.execCommand("insertText", false, cleaned)) {
        const start = qTextarea.selectionStart;
        const end = qTextarea.selectionEnd;
        qTextarea.setRangeText(cleaned, start, end, "end");
      }
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
        pb.btn.classList.toggle("active", pb.val === cur);
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


  Object.assign(E, {
    activePopover: activePopover,
    buildCalloutBlockBody: buildCalloutBlockBody,
    buildColbreakBlockBody: buildColbreakBlockBody,
    buildDividerBlockBody: buildDividerBlockBody,
    buildGlossaryBlockBody: buildGlossaryBlockBody,
    buildQuoteBlockBody: buildQuoteBlockBody,
    buildRichTextBlockBody: buildRichTextBlockBody,
    buildSpacerBlockBody: buildSpacerBlockBody,
    cleanPdfPastedText: cleanPdfPastedText,
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
