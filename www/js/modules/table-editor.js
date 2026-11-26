/**
 * LUKB Editor Modul: Interaktiver Tabellen-Editor (Excel Copy/Paste & Grid-Auswahl)
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function createFullLayoutControl() { return E.createFullLayoutControl.apply(this, arguments); }
  function escapeHtml() { return E.escapeHtml.apply(this, arguments); }
  function markDirty() { return E.markDirty.apply(this, arguments); }
  function openLinkPopover() { return E.openLinkPopover.apply(this, arguments); }
  function parseDelimitedText() { return E.parseDelimitedText.apply(this, arguments); }
  function sanitizeRichTextHtml() { return E.sanitizeRichTextHtml.apply(this, arguments); }
  function uid() { return E.uid.apply(this, arguments); }

  const TABLE_CELL_HTML_TAG_RE = /<\/?(?:b|strong|i|em|u|sub|sup|a|br|p|div|span)\b/i;

  function sanitizeTableCellHtml(htmlStr) {
    if (!htmlStr) return "";
    let s = sanitizeRichTextHtml(String(htmlStr));
    s = s.replace(/<\/p>\s*<p>/gi, "<br>");
    s = s.replace(/<p\b[^>]*>/gi, "").replace(/<\/p>/gi, "<br>");
    s = s.trim();
    while (true) {
      const next = s.replace(/^(?:<br\s*\/?>|&nbsp;|\s)/i, "");
      if (next === s) break;
      s = next;
    }
    while (true) {
      const next = s.replace(/(?:<br\s*\/?>|&nbsp;|\s)$/i, "");
      if (next === s) break;
      s = next;
    }
    const plainCheck = s.replace(/<br\s*\/?>/gi, "").replace(/&nbsp;/gi, "").trim();
    if (!plainCheck) return "";
    return s.trim();
  }

  function normalizeTableCellForEditor(val) {
    const raw = val != null ? String(val) : "";
    if (!raw) return "";
    if (TABLE_CELL_HTML_TAG_RE.test(raw)) {
      return sanitizeTableCellHtml(raw);
    }
    return escapeHtml(raw).replace(/\r\n|\n|\r/g, "<br>");
  }

  function tableCellToPlainText(val) {
    const raw = val != null ? String(val) : "";
    if (!raw) return "";
    if (!TABLE_CELL_HTML_TAG_RE.test(raw)) {
      return raw;
    }
    const tmp = document.createElement("div");
    tmp.innerHTML = raw
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/(?:p|div)>/gi, "\n");
    return (tmp.textContent || tmp.innerText || "").replace(/\u00A0/g, " ").replace(/\n+$/, "");
  }

  const CELL_FORMAT_SPECS = {
    bold: { tag: "b", selector: "b, strong", aliases: ["B", "STRONG"] },
    italic: { tag: "i", selector: "i, em", aliases: ["I", "EM"] },
    underline: { tag: "u", selector: "u", aliases: ["U"] },
  };

  function unwrapTagSelector(root, selector) {
    root.querySelectorAll(selector).forEach(function (el) {
      const parent = el.parentNode;
      if (!parent) return;
      while (el.firstChild) {
        parent.insertBefore(el.firstChild, el);
      }
      parent.removeChild(el);
    });
  }

  function hasAncestorTag(node, root, aliases) {
    let cur = node && node.parentNode;
    while (cur && cur !== root) {
      if (cur.nodeType === 1 && aliases.indexOf(cur.tagName.toUpperCase()) !== -1) {
        return true;
      }
      cur = cur.parentNode;
    }
    return false;
  }

  function isCellHtmlFullyFormatted(val, cmd) {
    const spec = CELL_FORMAT_SPECS[cmd];
    if (!spec) return false;
    const html = normalizeTableCellForEditor(val);
    if (!html) return false;
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    const walker = document.createTreeWalker(tmp, NodeFilter.SHOW_TEXT, null);
    let hasText = false;
    let node;
    while ((node = walker.nextNode())) {
      const txt = (node.nodeValue || "").replace(/\u00A0/g, " ").trim();
      if (!txt) continue;
      hasText = true;
      if (!hasAncestorTag(node, tmp, spec.aliases)) {
        return false;
      }
    }
    return hasText;
  }

  function applyFormatToCellHtml(val, cmd, shouldEnable) {
    const html = normalizeTableCellForEditor(val);
    if (!html) return "";
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    if (!(tmp.textContent || "").replace(/\u00A0/g, " ").trim()) {
      return sanitizeTableCellHtml(tmp.innerHTML);
    }
    if (cmd === "removeFormat") {
      unwrapTagSelector(tmp, "b, strong, i, em, u, sub, sup, span");
      return sanitizeTableCellHtml(tmp.innerHTML);
    }
    const spec = CELL_FORMAT_SPECS[cmd];
    if (!spec) return sanitizeTableCellHtml(tmp.innerHTML);
    unwrapTagSelector(tmp, spec.selector);
    if (shouldEnable) {
      const wrapper = document.createElement(spec.tag);
      while (tmp.firstChild) {
        wrapper.appendChild(tmp.firstChild);
      }
      tmp.appendChild(wrapper);
    }
    return sanitizeTableCellHtml(tmp.innerHTML);
  }

  function isCellInputEl(el) {
    return !!(el && (el.tagName === "TEXTAREA" || el.tagName === "INPUT" || (el.classList && el.classList.contains("grid-cell-input"))));
  }

  function hasInnerTextSelection(el) {
    if (!el) return false;
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      return el.selectionStart !== el.selectionEnd;
    }
    if (el.classList && el.classList.contains("grid-cell-input")) {
      const sel = window.getSelection();
      return !!(sel && !sel.isCollapsed && el.contains(sel.anchorNode));
    }
    return false;
  }

  const tableEditorState = {
    active: null,
    drag: null,
  };

  function normalizeTableCellRange(a, b) {
    return {
      minRow: Math.min(a.row, b.row),
      maxRow: Math.max(a.row, b.row),
      minCol: Math.min(a.col, b.col),
      maxCol: Math.max(a.col, b.col),
    };
  }

  function getTableMerges(blk) {
    if (!blk || !Array.isArray(blk.merges)) return [];
    const rowCount = Array.isArray(blk.rows) ? blk.rows.length : 0;
    const colCount = Array.isArray(blk.columns) ? blk.columns.length : 0;
    return blk.merges.filter(function (m) {
      return (
        m &&
        typeof m.row === "number" &&
        typeof m.col === "number" &&
        m.row >= 0 &&
        m.col >= 0 &&
        m.row < rowCount &&
        m.col < colCount &&
        ((m.rowspan || 1) > 1 || (m.colspan || 1) > 1)
      );
    }).map(function (m) {
      return {
        row: m.row,
        col: m.col,
        rowspan: Math.min(m.rowspan || 1, rowCount - m.row),
        colspan: Math.min(m.colspan || 1, colCount - m.col),
      };
    }).filter(function (m) {
      return m.rowspan > 1 || m.colspan > 1;
    });
  }

  function findMergeAtCell(blk, r, c) {
    const merges = getTableMerges(blk);
    for (let i = 0; i < merges.length; i++) {
      const m = merges[i];
      if (r >= m.row && r < m.row + m.rowspan && c >= m.col && c < m.col + m.colspan) {
        return {
          merge: m,
          isOrigin: r === m.row && c === m.col,
        };
      }
    }
    return null;
  }

  function rangesIntersect(a, b) {
    return !(a.maxRow < b.minRow || a.minRow > b.maxRow || a.maxCol < b.minCol || a.minCol > b.maxCol);
  }

  function expandRangeToMerges(blk, range) {
    if (!range) return null;
    const merges = getTableMerges(blk);
    if (!merges.length) return range;
    const res = {
      minRow: range.minRow,
      maxRow: range.maxRow,
      minCol: range.minCol,
      maxCol: range.maxCol,
    };
    let changed = true;
    while (changed) {
      changed = false;
      for (let i = 0; i < merges.length; i++) {
        const m = merges[i];
        const mRange = {
          minRow: m.row,
          maxRow: m.row + m.rowspan - 1,
          minCol: m.col,
          maxCol: m.col + m.colspan - 1,
        };
        if (rangesIntersect(res, mRange)) {
          if (mRange.minRow < res.minRow) { res.minRow = mRange.minRow; changed = true; }
          if (mRange.maxRow > res.maxRow) { res.maxRow = mRange.maxRow; changed = true; }
          if (mRange.minCol < res.minCol) { res.minCol = mRange.minCol; changed = true; }
          if (mRange.maxCol > res.maxCol) { res.maxCol = mRange.maxCol; changed = true; }
        }
      }
    }
    return res;
  }

  function isTableCellInRange(r, c, range, rowspan, colspan) {
    if (!range) return false;
    const rEnd = r + (rowspan || 1) - 1;
    const cEnd = c + (colspan || 1) - 1;
    return !(rEnd < range.minRow || r > range.maxRow || cEnd < range.minCol || c > range.maxCol);
  }

  function closeTableContextMenu() {
    const existing = document.getElementById("active-table-context-menu");
    if (existing && existing.parentNode) {
      existing.parentNode.removeChild(existing);
    }
  }

  function clearTableSelection() {
    const active = tableEditorState.active;
    if (!active) return;
    active.range = null;
    active.lead = null;
    if (active.gridScroll && active.gridScroll.isConnected) {
      active.applySelectionStyles();
      active.updateSelectionUI();
    } else {
      tableEditorState.active = null;
    }
  }

  function formatTsvCell(val) {
    const s = val != null ? String(val) : "";
    if (/[\t\n\r"]/.test(s)) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }

  function getTableRangeTsv(blk, range) {
    const lines = [];
    for (let r = range.minRow; r <= range.maxRow && r < blk.rows.length; r++) {
      const rowObj = blk.rows[r] || {};
      const cols = [];
      for (let c = range.minCol; c <= range.maxCol && c < blk.columns.length; c++) {
        cols.push(formatTsvCell(tableCellToPlainText(rowObj[blk.columns[c].field])));
      }
      lines.push(cols.join("\t"));
    }
    return lines.join("\n");
  }

  function getTableRangeHtml(blk, range) {
    const rowsHtml = [];
    for (let r = range.minRow; r <= range.maxRow && r < blk.rows.length; r++) {
      const rowObj = blk.rows[r] || {};
      const cellsHtml = [];
      for (let c = range.minCol; c <= range.maxCol && c < blk.columns.length; c++) {
        const val = rowObj[blk.columns[c].field] != null ? String(rowObj[blk.columns[c].field]) : "";
        cellsHtml.push("<td>" + normalizeTableCellForEditor(val) + "</td>");
      }
      rowsHtml.push("<tr>" + cellsHtml.join("") + "</tr>");
    }
    return "<table><tbody>" + rowsHtml.join("") + "</tbody></table>";
  }

  function parseClipboardTsv(clipText, delimiter) {
    return parseDelimitedText(clipText, delimiter || "\t");
  }

  function copyViaHiddenTextarea(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.top = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_err) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  function writeTableSelectionToClipboard(text, html, onDone) {
    if (navigator.clipboard && typeof navigator.clipboard.write === "function" && typeof window.ClipboardItem === "function") {
      try {
        const item = new window.ClipboardItem({
          "text/plain": new Blob([text], { type: "text/plain" }),
          "text/html": new Blob([html], { type: "text/html" }),
        });
        navigator.clipboard.write([item]).then(
          function () { if (onDone) onDone(true); },
          function () {
            const ok = copyViaHiddenTextarea(text);
            if (onDone) onDone(ok);
          }
        );
        return;
      } catch (_err) {
        // Fallback below
      }
    }
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      navigator.clipboard.writeText(text).then(
        function () { if (onDone) onDone(true); },
        function () {
          const ok = copyViaHiddenTextarea(text);
          if (onDone) onDone(ok);
        }
      );
      return;
    }
    const ok = copyViaHiddenTextarea(text);
    if (onDone) onDone(ok);
  }

  document.addEventListener("mousemove", function (e) {
    const drag = tableEditorState.drag;
    const active = tableEditorState.active;
    if (!drag || !drag.active || !active || active.blockId !== drag.blockId) return;
    if (!drag.tbl || !drag.tbl.isConnected) {
      drag.active = false;
      return;
    }

    const hit = document.elementFromPoint(e.clientX, e.clientY) || e.target;
    const td = hit && hit.closest ? hit.closest("td[data-row-idx][data-col-idx]") : null;
    if (!td || !drag.tbl.contains(td)) return;

    const r = parseInt(td.dataset.rowIdx, 10);
    const c = parseInt(td.dataset.colIdx, 10);
    if (isNaN(r) || isNaN(c)) return;

    if (r !== drag.anchor.row || c !== drag.anchor.col) {
      if (!drag.movedOut) {
        drag.movedOut = true;
        drag.tbl.classList.add("is-selecting-cells");
        if (window.getSelection) {
          const sel = window.getSelection();
          if (sel) sel.removeAllRanges();
        }
        if (document.activeElement && drag.tbl.contains(document.activeElement) && isCellInputEl(document.activeElement)) {
          document.activeElement.blur();
        }
        drag.gridScroll.focus({ preventScroll: true });
      }
    }

    if (drag.movedOut) {
      active.lead = { row: r, col: c };
      active.range = expandRangeToMerges(active.blk, normalizeTableCellRange(drag.anchor, active.lead));
      active.applySelectionStyles();
      active.updateSelectionUI();
    }
  });

  document.addEventListener("mouseup", function () {
    const drag = tableEditorState.drag;
    if (!drag || !drag.active) return;
    if (drag.tbl) {
      drag.tbl.classList.remove("is-selecting-cells");
    }
    if (drag.movedOut && drag.gridScroll && drag.gridScroll.isConnected) {
      drag.gridScroll.focus({ preventScroll: true });
      if (tableEditorState.active && tableEditorState.active.blockId === drag.blockId) {
        tableEditorState.active.updateSelectionUI();
      }
    }
    drag.active = false;
  });

  document.addEventListener("mousedown", function (e) {
    const active = tableEditorState.active;
    if (!active || !active.range) return;
    if (e.target.closest && (e.target.closest("#active-table-context-menu") || e.target.closest(".table-selection-actions"))) {
      return;
    }
    if (active.gridScroll && active.gridScroll.isConnected && active.gridScroll.contains(e.target)) {
      return;
    }
    clearTableSelection();
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("#active-table-context-menu")) {
      closeTableContextMenu();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeTableContextMenu();
      if (tableEditorState.active && tableEditorState.active.range) {
        clearTableSelection();
      }
    }
  });

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

    const layoutWrap = createFullLayoutControl(blk);

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

    // Zeile 3: Tabellen-Steuerleiste (+ Zeile, + Spalte, 1. Zeile -> Kopfzeile, Total-Zeile Checkbox, Excel-Hinweis)
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
    btnGroup.style.flexWrap = "wrap";

    const addRowBtn = document.createElement("button");
    addRowBtn.type = "button";
    addRowBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addRowBtn.textContent = "+ Zeile";

    const addColBtn = document.createElement("button");
    addColBtn.type = "button";
    addColBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addColBtn.textContent = "+ Spalte";

    const useFirstRowHeaderBtn = document.createElement("button");
    useFirstRowHeaderBtn.type = "button";
    useFirstRowHeaderBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    useFirstRowHeaderBtn.textContent = "↥ 1. Zeile → Kopfzeile";
    useFirstRowHeaderBtn.title = "Erste Datenzeile als Kopfzeilenwerte übernehmen und danach aus den Datenzeilen löschen";

    const eqWidthBtn = document.createElement("button");
    eqWidthBtn.type = "button";
    eqWidthBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    eqWidthBtn.textContent = "⚖ Gleich verteilen";
    eqWidthBtn.title = "Alle Spaltenbreiten gleichmässig auf 100 % aufteilen";

    const widthSumBadge = document.createElement("span");
    widthSumBadge.className = "table-width-sum-badge";
    widthSumBadge.title = "Summe der Spaltenbreiten (sollte 100 % ergeben)";

    const headerToggleWrap = document.createElement("label");
    headerToggleWrap.style.display = "inline-flex";
    headerToggleWrap.style.alignItems = "center";
    headerToggleWrap.style.gap = "5px";
    headerToggleWrap.style.fontSize = "12px";
    headerToggleWrap.style.marginLeft = "8px";
    headerToggleWrap.style.cursor = "pointer";

    const headerCheckbox = document.createElement("input");
    headerCheckbox.type = "checkbox";
    headerCheckbox.checked = blk.show_header !== false;
    headerCheckbox.addEventListener("change", function () {
      blk.show_header = headerCheckbox.checked;
      renderGrid();
      markDirty();
    });
    headerToggleWrap.appendChild(headerCheckbox);
    headerToggleWrap.appendChild(document.createTextNode("Kopfzeile einblenden"));

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

    const fontSizeWrap = document.createElement("label");
    fontSizeWrap.style.display = "inline-flex";
    fontSizeWrap.style.alignItems = "center";
    fontSizeWrap.style.gap = "5px";
    fontSizeWrap.style.fontSize = "12px";
    fontSizeWrap.style.marginLeft = "8px";
    fontSizeWrap.appendChild(document.createTextNode("Schriftgrösse:"));

    const fontSizeSelect = document.createElement("select");
    fontSizeSelect.className = "cms-select";
    fontSizeSelect.style.width = "auto";
    fontSizeSelect.style.minWidth = "130px";
    fontSizeSelect.style.height = "26px";
    fontSizeSelect.style.padding = "2px 6px";
    fontSizeSelect.style.fontSize = "12px";
    fontSizeSelect.title = "Schriftgrösse für Kopfzeile und Tabellen-Body relativ zur Standardgrösse";
    [
      { value: "0", label: "Standard" },
      { value: "-1", label: "-1 (Kleiner)" },
      { value: "-2", label: "-2 (Sehr klein)" },
    ].forEach(function (opt) {
      const o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      fontSizeSelect.appendChild(o);
    });
    const curFontStep = (blk.font_size_step === -1 || blk.font_size_step === -2) ? blk.font_size_step : 0;
    blk.font_size_step = curFontStep;
    fontSizeSelect.value = String(curFontStep);
    fontSizeSelect.addEventListener("change", function () {
      const parsed = parseInt(fontSizeSelect.value, 10);
      blk.font_size_step = (parsed === -1 || parsed === -2) ? parsed : 0;
      markDirty();
    });
    fontSizeWrap.appendChild(fontSizeSelect);

    const designWrap = document.createElement("label");
    designWrap.style.display = "inline-flex";
    designWrap.style.alignItems = "center";
    designWrap.style.gap = "5px";
    designWrap.style.fontSize = "12px";
    designWrap.style.marginLeft = "8px";
    designWrap.appendChild(document.createTextNode("Design:"));

    const designSelect = document.createElement("select");
    designSelect.className = "cms-select";
    designSelect.style.width = "auto";
    designSelect.style.minWidth = "135px";
    designSelect.style.height = "26px";
    designSelect.style.padding = "2px 6px";
    designSelect.style.fontSize = "12px";
    designSelect.title = "Tabellen-Design auswählen";
    [
      { value: "standard", label: "Standard (Navy)" },
      { value: "lukb_design", label: "LUKB Design" },
    ].forEach(function (opt) {
      const o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      designSelect.appendChild(o);
    });
    const curDesign = blk.table_design === "standard" ? "standard" : "lukb_design";
    blk.table_design = curDesign;
    designSelect.value = curDesign;
    designSelect.addEventListener("change", function () {
      blk.table_design = designSelect.value === "standard" ? "standard" : "lukb_design";
      markDirty();
    });
    designWrap.appendChild(designSelect);

    btnGroup.appendChild(addRowBtn);
    btnGroup.appendChild(addColBtn);
    btnGroup.appendChild(useFirstRowHeaderBtn);
    btnGroup.appendChild(eqWidthBtn);
    btnGroup.appendChild(widthSumBadge);
    btnGroup.appendChild(headerToggleWrap);
    btnGroup.appendChild(totalToggleWrap);
    btnGroup.appendChild(fontSizeWrap);
    btnGroup.appendChild(designWrap);

    const excelHint = document.createElement("span");
    excelHint.style.fontSize = "11.5px";
    excelHint.style.color = "#5A687C";
    excelHint.textContent = "Tipp: Excel-Bereiche einfügen (Ctrl+V) · Zellen ziehen / Shift+Klick markieren · Rechtsklick für Zeilen/Spalten";

    controlsBar.appendChild(btnGroup);
    controlsBar.appendChild(excelHint);
    container.appendChild(controlsBar);

    // Aktionsleiste für markierte Zellbereiche
    const selectionBar = document.createElement("div");
    selectionBar.className = "table-selection-actions";

    const selLeft = document.createElement("div");
    selLeft.className = "table-selection-actions-left";

    const selBadge = document.createElement("span");
    selBadge.className = "table-selection-badge";

    const copySelBtn = document.createElement("button");
    copySelBtn.type = "button";
    copySelBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    copySelBtn.textContent = "📋 Kopieren (Ctrl+C)";
    copySelBtn.title = "Markierte Zellen als Tabelle in die Zwischenablage kopieren";

    const mergeSelBtn = document.createElement("button");
    mergeSelBtn.type = "button";
    mergeSelBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    mergeSelBtn.textContent = "⊞ Zellen verbinden";
    mergeSelBtn.title = "Markierte Zellen zu einer Zelle verbinden";
    mergeSelBtn.style.display = "none";

    const unmergeSelBtn = document.createElement("button");
    unmergeSelBtn.type = "button";
    unmergeSelBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    unmergeSelBtn.textContent = "⊟ Zellen teilen";
    unmergeSelBtn.title = "Zellverbindung im markierten Bereich aufheben";
    unmergeSelBtn.style.display = "none";

    const clearSelValuesBtn = document.createElement("button");
    clearSelValuesBtn.type = "button";
    clearSelValuesBtn.className = "btn-lukb btn-lukb-danger-ghost btn-lukb-sm";
    clearSelValuesBtn.textContent = "🧹 Werte entfernen (Entf)";
    clearSelValuesBtn.title = "Inhalte der markierten Zellen leeren";

    const deselectBtn = document.createElement("button");
    deselectBtn.type = "button";
    deselectBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    deselectBtn.textContent = "✕ Auswahl";
    deselectBtn.title = "Zellmarkierung aufheben (Esc)";

    selLeft.appendChild(selBadge);
    selLeft.appendChild(copySelBtn);
    selLeft.appendChild(mergeSelBtn);
    selLeft.appendChild(unmergeSelBtn);
    selLeft.appendChild(clearSelValuesBtn);
    selLeft.appendChild(deselectBtn);

    const selHint = document.createElement("span");
    selHint.className = "table-selection-hint";
    selHint.textContent = "Tipp: Mit Shift+Pfeiltasten oder Maus ziehen erweitern";

    selectionBar.appendChild(selLeft);
    selectionBar.appendChild(selHint);
    container.appendChild(selectionBar);

    // Formatierungsleiste für aktive Tabellenzelle (Bold, Italic, Underline, Link)
    const formatBar = document.createElement("div");
    formatBar.className = "table-format-toolbar";

    const fmtBtnGroup = document.createElement("div");
    fmtBtnGroup.style.display = "flex";
    fmtBtnGroup.style.alignItems = "center";
    fmtBtnGroup.style.gap = "4px";

    let focusedCellCtx = null;

    const cellFmtCommands = [
      { cmd: "bold", label: "B", title: "Fett (Ctrl+B)" },
      { cmd: "italic", label: "I", title: "Kursiv (Ctrl+I)" },
      { cmd: "underline", label: "U", title: "Unterstrichen (Ctrl+U)" },
      { cmd: "removeFormat", label: "Tx", title: "Formatierung entfernen" },
    ];

    function applyFormatToSelectedRange(cmd) {
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return false;
      const range = active.range;
      const minR = Math.max(0, range.minRow);
      const maxR = Math.min(blk.rows.length - 1, range.maxRow);
      const minC = Math.max(0, range.minCol);
      const maxC = Math.min(blk.columns.length - 1, range.maxCol);
      if (maxR < minR || maxC < minC) return false;

      const targets = [];
      for (let r = minR; r <= maxR; r++) {
        for (let c = minC; c <= maxC; c++) {
          const mInfo = findMergeAtCell(blk, r, c);
          if (mInfo && !mInfo.isOrigin) continue;
          targets.push({ r: r, c: c, field: blk.columns[c].field });
        }
      }
      if (!targets.length) return false;

      let shouldEnable = true;
      if (cmd !== "removeFormat") {
        let hasNonEmpty = false;
        let allFormatted = true;
        for (let i = 0; i < targets.length; i++) {
          const t = targets[i];
          const val = blk.rows[t.r][t.field];
          if (tableCellToPlainText(val).trim()) {
            hasNonEmpty = true;
            if (!isCellHtmlFullyFormatted(val, cmd)) {
              allFormatted = false;
              break;
            }
          }
        }
        shouldEnable = !(hasNonEmpty && allFormatted);
      }

      let changed = false;
      targets.forEach(function (t) {
        const prev = blk.rows[t.r][t.field] != null ? String(blk.rows[t.r][t.field]) : "";
        const next = applyFormatToCellHtml(prev, cmd, shouldEnable);
        if (prev !== next) {
          blk.rows[t.r][t.field] = next;
          changed = true;
        }
        if (tblRef) {
          const td = tblRef.querySelector('td[data-row-idx="' + t.r + '"][data-col-idx="' + t.c + '"]');
          if (td) {
            const cellEl = td.querySelector(".grid-cell-input");
            if (cellEl) {
              cellEl.innerHTML = normalizeTableCellForEditor(next);
            }
          }
        }
      });

      if (changed) {
        markDirty();
      }
      return true;
    }

    cellFmtCommands.forEach(function (c) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "rt-btn";
      btn.textContent = c.label;
      btn.title = c.title;
      btn.addEventListener("mousedown", function (e) {
        e.preventDefault();
        const active = tableEditorState.active;
        const hasRange = !!(active && active.blockId === blk.id && active.range);
        const hasSingleCellInnerSel = !!(
          focusedCellCtx &&
          focusedCellCtx.cellEl &&
          focusedCellCtx.cellEl.isConnected &&
          hasInnerTextSelection(focusedCellCtx.cellEl)
        );
        if (hasSingleCellInnerSel && (!hasRange || (active.range.minRow === active.range.maxRow && active.range.minCol === active.range.maxCol))) {
          focusedCellCtx.cellEl.focus();
          document.execCommand(c.cmd, false, null);
          focusedCellCtx.onChange();
          return;
        }
        if (hasRange) {
          applyFormatToSelectedRange(c.cmd);
          gridScroll.focus({ preventScroll: true });
          return;
        }
        if (!focusedCellCtx || !focusedCellCtx.cellEl || !focusedCellCtx.cellEl.isConnected) return;
        focusedCellCtx.cellEl.focus();
        document.execCommand(c.cmd, false, null);
        focusedCellCtx.onChange();
      });
      fmtBtnGroup.appendChild(btn);
    });

    const cellLinkBtn = document.createElement("button");
    cellLinkBtn.type = "button";
    cellLinkBtn.className = "rt-btn";
    cellLinkBtn.textContent = "🔗 Link";
    cellLinkBtn.title = "Link in aktueller Tabellenzelle einfügen oder bearbeiten";
    cellLinkBtn.addEventListener("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (!focusedCellCtx || !focusedCellCtx.cellEl || !focusedCellCtx.cellEl.isConnected) return;
      const cellEl = focusedCellCtx.cellEl;
      const onCellChange = focusedCellCtx.onChange;
      const sel = window.getSelection();
      let range = null;
      let existingAnchor = null;
      if (sel && sel.rangeCount > 0) {
        const candidate = sel.getRangeAt(0);
        if (cellEl.contains(candidate.commonAncestorContainer)) {
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
      if (existingAnchor && cellEl.contains(existingAnchor)) {
        openLinkPopover(existingAnchor, cellEl, onCellChange);
      } else {
        if (!range) {
          range = document.createRange();
          range.selectNodeContents(cellEl);
          range.collapse(false);
        }
        openLinkPopover(range, cellEl, onCellChange);
      }
    });
    cellLinkBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
    });
    fmtBtnGroup.appendChild(cellLinkBtn);

    const fmtHint = document.createElement("span");
    fmtHint.className = "table-format-hint";
    fmtHint.textContent = "Zelle(n) markieren oder Text in Zelle markieren für Fett / Kursiv / Unterstrichen / Link";

    formatBar.appendChild(fmtBtnGroup);
    formatBar.appendChild(fmtHint);
    container.appendChild(formatBar);

    // Zeile 4: Interaktives Daten-Grid
    const gridScroll = document.createElement("div");
    gridScroll.className = "table-editor-scroll";
    gridScroll.tabIndex = -1;

    let tblRef = null;
    let copyFeedbackTimer = null;

    function distributeEqualColumnWidths(columns) {
      if (!Array.isArray(columns) || columns.length === 0) return;
      const n = columns.length;
      const base = Math.floor(1000 / n) / 10;
      const extraTenths = Math.round((100 - base * n) * 10);
      columns.forEach(function (c, idx) {
        c.width = Math.round((base + (idx < extraTenths ? 0.1 : 0)) * 10) / 10;
      });
    }

    function ensurePercentageWidths(columns) {
      if (!Array.isArray(columns) || columns.length === 0) return;
      const missing = columns.some(function (c) {
        return c.width == null || isNaN(parseFloat(c.width)) || parseFloat(c.width) <= 0;
      });
      if (missing) {
        distributeEqualColumnWidths(columns);
        return;
      }
      const total = columns.reduce(function (acc, c) {
        return acc + parseFloat(c.width);
      }, 0);
      if (columns.length > 1 && total > 0 && total < 20) {
        let running = 0;
        columns.forEach(function (c, idx) {
          if (idx < columns.length - 1) {
            const pct = Math.round((parseFloat(c.width) / total) * 1000) / 10;
            running = Math.round((running + pct) * 10) / 10;
            c.width = pct;
          } else {
            c.width = Math.round(Math.max(0.1, 100 - running) * 10) / 10;
          }
        });
      }
    }

    function autoResizeCellTextarea() {
      // contentEditable div wächst automatisch mit dem Inhalt
    }

    function autoResizeAllGridCells() {
      // contentEditable div wächst automatisch mit dem Inhalt
    }

    function getSelectionMergeInfo(range) {
      if (!range || !blk.rows.length || !blk.columns.length) {
        return { canMerge: false, canUnmerge: false };
      }
      const minR = Math.max(0, range.minRow);
      const maxR = Math.min(blk.rows.length - 1, range.maxRow);
      const minC = Math.max(0, range.minCol);
      const maxC = Math.min(blk.columns.length - 1, range.maxCol);
      if (maxR < minR || maxC < minC) {
        return { canMerge: false, canUnmerge: false };
      }
      const merges = getTableMerges(blk);
      const normRange = { minRow: minR, maxRow: maxR, minCol: minC, maxCol: maxC };
      const overlapping = merges.filter(function (m) {
        return rangesIntersect(normRange, {
          minRow: m.row,
          maxRow: m.row + m.rowspan - 1,
          minCol: m.col,
          maxCol: m.col + m.colspan - 1,
        });
      });
      const isSingleExistingMerge =
        overlapping.length === 1 &&
        overlapping[0].row === minR &&
        overlapping[0].col === minC &&
        overlapping[0].row + overlapping[0].rowspan - 1 === maxR &&
        overlapping[0].col + overlapping[0].colspan - 1 === maxC;
      const isMultiCell = maxR > minR || maxC > minC;
      return {
        canMerge: isMultiCell && !isSingleExistingMerge,
        canUnmerge: overlapping.length > 0,
      };
    }

    function applySelectionStyles() {
      if (!tblRef) return;
      const active = tableEditorState.active;
      const range = active && active.blockId === blk.id ? active.range : null;
      tblRef.querySelectorAll("td[data-row-idx][data-col-idx]").forEach(function (td) {
        const r = parseInt(td.dataset.rowIdx, 10);
        const c = parseInt(td.dataset.colIdx, 10);
        const rspan = td.rowSpan || 1;
        const cspan = td.colSpan || 1;
        const selected = isTableCellInRange(r, c, range, rspan, cspan);
        td.classList.toggle("is-cell-selected", selected);
        td.classList.toggle("sel-top", selected && r === range.minRow);
        td.classList.toggle("sel-bottom", selected && (r + rspan - 1) === range.maxRow);
        td.classList.toggle("sel-left", selected && c === range.minCol);
        td.classList.toggle("sel-right", selected && (c + cspan - 1) === range.maxCol);
      });
    }

    function updateSelectionUI() {
      const active = tableEditorState.active;
      const range = active && active.blockId === blk.id ? active.range : null;
      if (!range || !blk.rows.length || !blk.columns.length) {
        selectionBar.classList.remove("is-visible");
        mergeSelBtn.style.display = "none";
        unmergeSelBtn.style.display = "none";
        return;
      }
      const rowCount = Math.min(range.maxRow, blk.rows.length - 1) - range.minRow + 1;
      const colCount = Math.min(range.maxCol, blk.columns.length - 1) - range.minCol + 1;
      if (rowCount <= 0 || colCount <= 0) {
        selectionBar.classList.remove("is-visible");
        mergeSelBtn.style.display = "none";
        unmergeSelBtn.style.display = "none";
        return;
      }
      const mergeInfo = getSelectionMergeInfo(range);
      mergeSelBtn.style.display = mergeInfo.canMerge ? "" : "none";
      unmergeSelBtn.style.display = mergeInfo.canUnmerge ? "" : "none";
      const cellTotal = rowCount * colCount;
      selBadge.textContent =
        cellTotal === 1
          ? "Markiert: 1 Zelle"
          : "Markiert: " + rowCount + " × " + colCount + " Zellen (" + cellTotal + ")";
      selectionBar.classList.add("is-visible");
    }

    function ensureActiveTableState() {
      if (tableEditorState.active && tableEditorState.active.blockId !== blk.id) {
        clearTableSelection();
      }
      if (!tableEditorState.active || tableEditorState.active.blockId !== blk.id) {
        tableEditorState.active = {
          blockId: blk.id,
          blk: blk,
          gridScroll: gridScroll,
          tbl: tblRef,
          anchor: null,
          lead: null,
          range: null,
          applySelectionStyles: applySelectionStyles,
          updateSelectionUI: updateSelectionUI,
        };
      } else {
        tableEditorState.active.tbl = tblRef;
        tableEditorState.active.gridScroll = gridScroll;
      }
      return tableEditorState.active;
    }

    function resetTableSelectionForStructuralChange() {
      if (tableEditorState.active && tableEditorState.active.blockId === blk.id) {
        tableEditorState.active.range = null;
        tableEditorState.active.anchor = null;
        tableEditorState.active.lead = null;
      }
      updateSelectionUI();
    }

    function flashCopiedButtonFeedback() {
      if (copyFeedbackTimer) {
        clearTimeout(copyFeedbackTimer);
      }
      copySelBtn.textContent = "✓ Kopiert!";
      copyFeedbackTimer = setTimeout(function () {
        copySelBtn.textContent = "📋 Kopieren (Ctrl+C)";
        copyFeedbackTimer = null;
      }, 1500);
    }

    function copySelectedRange() {
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return;
      const tsv = getTableRangeTsv(blk, active.range);
      const html = getTableRangeHtml(blk, active.range);
      writeTableSelectionToClipboard(tsv, html, function (ok) {
        if (ok) {
          flashCopiedButtonFeedback();
        }
        gridScroll.focus({ preventScroll: true });
      });
    }

    function clearSelectedRangeValues() {
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return;
      const range = active.range;
      let changed = false;
      for (let r = range.minRow; r <= range.maxRow && r < blk.rows.length; r++) {
        for (let c = range.minCol; c <= range.maxCol && c < blk.columns.length; c++) {
          const field = blk.columns[c].field;
          if (blk.rows[r][field] !== "") {
            blk.rows[r][field] = "";
            changed = true;
          }
          if (tblRef) {
            const td = tblRef.querySelector('td[data-row-idx="' + r + '"][data-col-idx="' + c + '"]');
            if (td) {
              const cellEl = td.querySelector(".grid-cell-input");
              if (cellEl) {
                cellEl.innerHTML = "";
              }
            }
          }
        }
      }
      if (changed) {
        markDirty();
      }
      gridScroll.focus({ preventScroll: true });
    }

    function mergeSelectedRange() {
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return;
      const expanded = expandRangeToMerges(blk, active.range);
      const minR = Math.max(0, expanded.minRow);
      const maxR = Math.min(blk.rows.length - 1, expanded.maxRow);
      const minC = Math.max(0, expanded.minCol);
      const maxC = Math.min(blk.columns.length - 1, expanded.maxCol);
      if (maxR < minR || maxC < minC || (maxR === minR && maxC === minC)) return;

      const normRange = { minRow: minR, maxRow: maxR, minCol: minC, maxCol: maxC };
      const existingMerges = getTableMerges(blk);
      const remainingMerges = existingMerges.filter(function (m) {
        return !rangesIntersect(normRange, {
          minRow: m.row,
          maxRow: m.row + m.rowspan - 1,
          minCol: m.col,
          maxCol: m.col + m.colspan - 1,
        });
      });

      const parts = [];
      for (let r = minR; r <= maxR; r++) {
        for (let c = minC; c <= maxC; c++) {
          const field = blk.columns[c].field;
          const val = blk.rows[r][field] != null ? String(blk.rows[r][field]).trim() : "";
          if (val) parts.push(val);
          blk.rows[r][field] = "";
        }
      }
      const originField = blk.columns[minC].field;
      blk.rows[minR][originField] = parts.join(" ");

      remainingMerges.push({
        row: minR,
        col: minC,
        rowspan: maxR - minR + 1,
        colspan: maxC - minC + 1,
      });
      blk.merges = remainingMerges;

      active.anchor = { row: minR, col: minC };
      active.lead = { row: maxR, col: maxC };
      active.range = normRange;
      renderGrid();
      markDirty();
      gridScroll.focus({ preventScroll: true });
    }

    function unmergeSelectedRange() {
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return;
      const range = active.range;
      const existingMerges = getTableMerges(blk);
      const nextMerges = existingMerges.filter(function (m) {
        return !rangesIntersect(range, {
          minRow: m.row,
          maxRow: m.row + m.rowspan - 1,
          minCol: m.col,
          maxCol: m.col + m.colspan - 1,
        });
      });
      if (nextMerges.length === existingMerges.length) return;
      blk.merges = nextMerges;
      renderGrid();
      markDirty();
      gridScroll.focus({ preventScroll: true });
    }

    function adjustMergesOnRowInsert(insertIdx) {
      const merges = getTableMerges(blk);
      if (!merges.length) return;
      blk.merges = merges.map(function (m) {
        if (m.row >= insertIdx) {
          return { row: m.row + 1, col: m.col, rowspan: m.rowspan, colspan: m.colspan };
        }
        if (m.row < insertIdx && m.row + m.rowspan > insertIdx) {
          return { row: m.row, col: m.col, rowspan: m.rowspan + 1, colspan: m.colspan };
        }
        return m;
      });
    }

    function adjustMergesOnRowsDelete(from, to) {
      const merges = getTableMerges(blk);
      if (!merges.length) return;
      const removeCount = to - from + 1;
      blk.merges = merges.map(function (m) {
        const mEnd = m.row + m.rowspan - 1;
        if (mEnd < from) return m;
        if (m.row > to) {
          return { row: m.row - removeCount, col: m.col, rowspan: m.rowspan, colspan: m.colspan };
        }
        const overlapStart = Math.max(m.row, from);
        const overlapEnd = Math.min(mEnd, to);
        const overlapCount = Math.max(0, overlapEnd - overlapStart + 1);
        const newRow = m.row < from ? m.row : from;
        const newRowspan = m.rowspan - overlapCount;
        if (newRowspan < 1 || (newRowspan === 1 && m.colspan === 1)) return null;
        return { row: newRow, col: m.col, rowspan: newRowspan, colspan: m.colspan };
      }).filter(Boolean);
    }

    function adjustMergesOnColInsert(insertIdx) {
      const merges = getTableMerges(blk);
      if (!merges.length) return;
      blk.merges = merges.map(function (m) {
        if (m.col >= insertIdx) {
          return { row: m.row, col: m.col + 1, rowspan: m.rowspan, colspan: m.colspan };
        }
        if (m.col < insertIdx && m.col + m.colspan > insertIdx) {
          return { row: m.row, col: m.col, rowspan: m.rowspan, colspan: m.colspan + 1 };
        }
        return m;
      });
    }

    function adjustMergesOnColsDelete(from, to) {
      const merges = getTableMerges(blk);
      if (!merges.length) return;
      const removeCount = to - from + 1;
      blk.merges = merges.map(function (m) {
        const mEnd = m.col + m.colspan - 1;
        if (mEnd < from) return m;
        if (m.col > to) {
          return { row: m.row, col: m.col - removeCount, rowspan: m.rowspan, colspan: m.colspan };
        }
        const overlapStart = Math.max(m.col, from);
        const overlapEnd = Math.min(mEnd, to);
        const overlapCount = Math.max(0, overlapEnd - overlapStart + 1);
        const newCol = m.col < from ? m.col : from;
        const newColspan = m.colspan - overlapCount;
        if (newColspan < 1 || (m.rowspan === 1 && newColspan === 1)) return null;
        return { row: m.row, col: newCol, rowspan: m.rowspan, colspan: newColspan };
      }).filter(Boolean);
    }

    function insertRowAt(insertIdx) {
      const newRow = {};
      blk.columns.forEach(function (c) {
        newRow[c.field] = "";
      });
      blk.rows.splice(insertIdx, 0, newRow);
      adjustMergesOnRowInsert(insertIdx);
      resetTableSelectionForStructuralChange();
      renderGrid();
      markDirty();
    }

    function insertColumnAt(insertIdx) {
      const newField = "col_" + uid("c");
      blk.columns.splice(insertIdx, 0, {
        field: newField,
        title: "Spalte " + (blk.columns.length + 1),
        align: insertIdx === 0 ? "left" : "right",
        width: 100,
      });
      distributeEqualColumnWidths(blk.columns);
      blk.rows.forEach(function (r) {
        r[newField] = "";
      });
      adjustMergesOnColInsert(insertIdx);
      resetTableSelectionForStructuralChange();
      renderGrid();
      markDirty();
    }

    function deleteColumnAt(colIdx) {
      deleteColumnsRange(colIdx, colIdx);
    }

    function deleteColumnsRange(startCol, endCol) {
      const from = Math.max(0, startCol);
      const to = Math.min(blk.columns.length - 1, endCol);
      const removeCount = to - from + 1;
      if (removeCount <= 0 || blk.columns.length - removeCount < 1) return;
      const removedCols = blk.columns.splice(from, removeCount);
      removedCols.forEach(function (col) {
        blk.rows.forEach(function (r) {
          delete r[col.field];
        });
      });
      adjustMergesOnColsDelete(from, to);
      distributeEqualColumnWidths(blk.columns);
      resetTableSelectionForStructuralChange();
      renderGrid();
      markDirty();
    }

    function deleteRowAt(rowIdx) {
      deleteRowsRange(rowIdx, rowIdx);
    }

    function deleteRowsRange(startRow, endRow) {
      const from = Math.max(0, startRow);
      const to = Math.min(blk.rows.length - 1, endRow);
      if (to < from) return;
      blk.rows.splice(from, to - from + 1);
      adjustMergesOnRowsDelete(from, to);
      resetTableSelectionForStructuralChange();
      renderGrid();
      markDirty();
    }

    function promoteFirstRowToHeader() {
      if (!Array.isArray(blk.rows) || blk.rows.length === 0) return;
      const confirmed =
        typeof window.confirm === "function"
          ? window.confirm(
              "Erste Datenzeile als Kopfzeilenwerte übernehmen?\n" +
                "Die bisherigen Spaltenüberschriften werden überschrieben und die erste Zeile anschliessend aus den Datenzeilen gelöscht."
            )
          : true;
      if (!confirmed) return;
      const firstRow = blk.rows[0];
      blk.columns.forEach(function (col) {
        const val = firstRow[col.field];
        col.title = val != null ? tableCellToPlainText(val).replace(/\n+/g, " ").trim() : "";
      });
      blk.rows.shift();
      adjustMergesOnRowsDelete(0, 0);
      resetTableSelectionForStructuralChange();
      renderGrid();
      markDirty();
    }

    function pasteTsvAtCell(startRowIdx, startColIdx, clipText) {
      const prevColCount = blk.columns.length;
      const pastedRows = parseClipboardTsv(clipText);
      if (!pastedRows.length) return;

      pastedRows.forEach(function (cells, rOffset) {
        const targetRowIdx = startRowIdx + rOffset;
        while (blk.rows.length <= targetRowIdx) {
          const emptyRow = {};
          blk.columns.forEach(function (c) { emptyRow[c.field] = ""; });
          blk.rows.push(emptyRow);
        }
        cells.forEach(function (cellVal, cOffset) {
          const targetColIdx = startColIdx + cOffset;
          if (targetColIdx >= blk.columns.length) {
            const newField = "col_" + uid("c");
            blk.columns.push({
              field: newField,
              title: "Spalte " + (blk.columns.length + 1),
              align: "right",
              width: 100,
            });
          }
          const targetField = blk.columns[targetColIdx].field;
          blk.rows[targetRowIdx][targetField] = String(cellVal).trim();
        });
      });

      if (blk.columns.length !== prevColCount) {
        distributeEqualColumnWidths(blk.columns);
      }
      resetTableSelectionForStructuralChange();
      renderGrid();
      markDirty();
    }

    function openTableCellContextMenu(clientX, clientY, rIdx, cIdx) {
      closeTableContextMenu();
      const menu = document.createElement("div");
      menu.className = "figure-context-menu";
      menu.id = "active-table-context-menu";

      function addMenuItem(icon, label, shortcut, isDanger, onClick) {
        const item = document.createElement("div");
        item.className = "figure-context-menu-item" + (isDanger ? " danger" : "");
        const iconSpan = document.createElement("span");
        iconSpan.textContent = icon;
        const lblSpan = document.createElement("span");
        lblSpan.textContent = label;
        item.appendChild(iconSpan);
        item.appendChild(lblSpan);
        if (shortcut) {
          const scSpan = document.createElement("span");
          scSpan.className = "figure-context-menu-shortcut";
          scSpan.textContent = shortcut;
          item.appendChild(scSpan);
        }
        item.addEventListener("click", function (ev) {
          ev.stopPropagation();
          closeTableContextMenu();
          onClick();
        });
        menu.appendChild(item);
      }

      function addDivider() {
        const div = document.createElement("div");
        div.className = "figure-context-menu-divider";
        menu.appendChild(div);
      }

      const active = tableEditorState.active;
      const range = active && active.blockId === blk.id ? active.range : null;
      const mergeInfo = getSelectionMergeInfo(range);

      addMenuItem("📋", "Markierte Zellen kopieren", "Ctrl+C", false, copySelectedRange);
      addMenuItem("🧹", "Werte entfernen", "Entf", true, clearSelectedRangeValues);
      if (mergeInfo.canMerge || mergeInfo.canUnmerge) {
        addDivider();
        if (mergeInfo.canMerge) {
          addMenuItem("⊞", "Zellen verbinden", "", false, mergeSelectedRange);
        }
        if (mergeInfo.canUnmerge) {
          addMenuItem("⊟", "Zellverbindung aufheben", "", false, unmergeSelectedRange);
        }
      }
      addDivider();
      addMenuItem("↑", "Zeile oberhalb einfügen", "", false, function () { insertRowAt(rIdx); });
      addMenuItem("↓", "Zeile unterhalb einfügen", "", false, function () { insertRowAt(rIdx + 1); });
      addMenuItem("←", "Spalte links einfügen", "", false, function () { insertColumnAt(cIdx); });
      addMenuItem("→", "Spalte rechts einfügen", "", false, function () { insertColumnAt(cIdx + 1); });
      addDivider();
      const hasMultiRowSel = !!(range && range.maxRow > range.minRow && rIdx >= range.minRow && rIdx <= range.maxRow);
      if (hasMultiRowSel) {
        const rowCount = Math.min(range.maxRow, blk.rows.length - 1) - Math.max(0, range.minRow) + 1;
        addMenuItem("✕", rowCount + " markierte Zeilen löschen", "", true, function () {
          deleteRowsRange(range.minRow, range.maxRow);
        });
      } else {
        addMenuItem("✕", "Zeile löschen", "", true, function () {
          deleteRowAt(rIdx);
        });
      }

      const hasMultiColSel = !!(range && range.maxCol > range.minCol && cIdx >= range.minCol && cIdx <= range.maxCol);
      if (hasMultiColSel) {
        const colCount = Math.min(range.maxCol, blk.columns.length - 1) - Math.max(0, range.minCol) + 1;
        if (blk.columns.length - colCount >= 1) {
          addMenuItem("✕", colCount + " markierte Spalten löschen", "", true, function () {
            deleteColumnsRange(range.minCol, range.maxCol);
          });
        }
      } else if (blk.columns.length > 1) {
        addMenuItem("✕", "Spalte löschen", "", true, function () {
          deleteColumnAt(cIdx);
        });
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
    }

    const renderGrid = () => {
      gridScroll.innerHTML = "";
      const tbl = document.createElement("table");
      tbl.className = "cms-grid-editor";
      tblRef = tbl;

      if (!Array.isArray(blk.columns) || blk.columns.length === 0) {
        blk.columns = [{ field: "col_1", title: "Spalte 1", align: "left", width: 100 }];
      }
      if (!Array.isArray(blk.rows)) {
        blk.rows = [];
      }
      ensurePercentageWidths(blk.columns);
      useFirstRowHeaderBtn.disabled = blk.rows.length === 0;

      function updateWidthSumBadge() {
        const sum = blk.columns.reduce(function (acc, c) {
          const w = parseFloat(c.width);
          return acc + (!isNaN(w) && w > 0 ? w : 0);
        }, 0);
        const rounded = Math.round(sum * 10) / 10;
        widthSumBadge.textContent = "Σ " + rounded + "%";
        widthSumBadge.classList.toggle("is-mismatch", Math.abs(rounded - 100) > 0.2);
      }

      // THEAD
      const thead = document.createElement("thead");
      const isHeaderHidden = blk.show_header === false;
      if (isHeaderHidden) {
        thead.className = "is-header-hidden";
      }
      const htr = document.createElement("tr");

      blk.columns.forEach(function (col, cIdx) {
        const th = document.createElement("th");
        const ctrl = document.createElement("div");
        ctrl.className = "grid-header-controls";

        const colInp = document.createElement("input");
        colInp.type = "text";
        colInp.className = "grid-col-title-input";
        colInp.value = col.title || "";
        if (isHeaderHidden) {
          colInp.title = "Kopfzeile ist ausgeblendet (wird im PDF/HTML nicht gerendert)";
          colInp.placeholder = "(ausgeblendet)";
        }
        colInp.addEventListener("input", function () {
          col.title = colInp.value;
          markDirty();
        });

        const alignBtn = document.createElement("button");
        alignBtn.type = "button";
        alignBtn.className = "grid-col-align-btn";
        alignBtn.title =
          col.align === "justify"
            ? "Spaltenausrichtung: Blocksatz (Klicken zum Umschalten: Zentriert)"
            : col.align === "center"
            ? "Spaltenausrichtung: Zentriert (Klicken zum Umschalten: Rechtsbündig)"
            : col.align === "right"
            ? "Spaltenausrichtung: Rechtsbündig (Klicken zum Umschalten: Linksbündig)"
            : "Spaltenausrichtung: Linksbündig (Klicken zum Umschalten: Blocksatz)";
        alignBtn.textContent =
          col.align === "justify"
            ? "≡B"
            : col.align === "right"
            ? "⇥R"
            : col.align === "center"
            ? "↔Z"
            : "⇤L";
        alignBtn.addEventListener("click", function () {
          if (col.align === "left") {
            col.align = "justify";
          } else if (col.align === "justify") {
            col.align = "center";
          } else if (col.align === "center") {
            col.align = "right";
          } else {
            col.align = "left";
          }
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
            deleteColumnAt(cIdx);
          });
          ctrl.appendChild(delColBtn);
        }

        const widthRow = document.createElement("div");
        widthRow.className = "grid-header-width-row";
        widthRow.title = "Spaltenbreite in Prozent (Summe = 100 %)";

        const widthLbl = document.createElement("span");
        widthLbl.textContent = "Breite:";

        const widthInp = document.createElement("input");
        widthInp.type = "number";
        widthInp.className = "grid-col-width-input";
        widthInp.min = "0.1";
        widthInp.max = "100";
        widthInp.step = "0.1";
        widthInp.value = col.width;
        widthInp.addEventListener("input", function () {
          const parsed = parseFloat(widthInp.value);
          if (!isNaN(parsed) && parsed > 0) {
            col.width = Math.max(0.1, Math.min(100, Math.round(parsed * 10) / 10));
            updateWidthSumBadge();
            markDirty();
          }
        });
        widthInp.addEventListener("blur", function () {
          const parsed = parseFloat(widthInp.value);
          if (isNaN(parsed) || parsed <= 0) {
            widthInp.value = col.width;
          }
        });

        const pctSpan = document.createElement("span");
        pctSpan.className = "grid-col-width-pct";
        pctSpan.textContent = "%";

        widthRow.appendChild(widthLbl);
        widthRow.appendChild(widthInp);
        widthRow.appendChild(pctSpan);

        th.appendChild(ctrl);
        th.appendChild(widthRow);
        htr.appendChild(th);
      });

      updateWidthSumBadge();

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
          const mergeInfo = findMergeAtCell(blk, rIdx, cIdx);
          if (mergeInfo && !mergeInfo.isOrigin) {
            return;
          }

          const td = document.createElement("td");
          td.dataset.rowIdx = String(rIdx);
          td.dataset.colIdx = String(cIdx);
          if (mergeInfo && mergeInfo.isOrigin) {
            if (mergeInfo.merge.rowspan > 1) td.rowSpan = mergeInfo.merge.rowspan;
            if (mergeInfo.merge.colspan > 1) td.colSpan = mergeInfo.merge.colspan;
            td.classList.add("is-merged-cell");
          }

          const cellInp = document.createElement("div");
          cellInp.className = "grid-cell-input";
          cellInp.contentEditable = "true";
          cellInp.style.textAlign = col.align || "left";
          cellInp.innerHTML = normalizeTableCellForEditor(rowObj[col.field]);

          const commitCell = function (rawHtml) {
            const nextVal = sanitizeTableCellHtml(rawHtml !== undefined ? rawHtml : cellInp.innerHTML);
            if (rowObj[col.field] !== nextVal) {
              rowObj[col.field] = nextVal;
              markDirty();
            }
          };

          cellInp.addEventListener("input", function () {
            commitCell();
          });

          cellInp.addEventListener("blur", function () {
            commitCell();
          });

          cellInp.addEventListener("focus", function () {
            const active = ensureActiveTableState();
            if (!tableEditorState.drag || !tableEditorState.drag.active) {
              active.anchor = { row: rIdx, col: cIdx };
            }
            focusedCellCtx = {
              cellEl: cellInp,
              rowObj: rowObj,
              col: col,
              onChange: function (updatedHtml) {
                commitCell(updatedHtml);
              },
            };
          });

          cellInp.addEventListener("click", function (e) {
            const linkEl = e.target.closest ? e.target.closest("a") : null;
            if (linkEl && cellInp.contains(linkEl)) {
              e.preventDefault();
              e.stopPropagation();
              openLinkPopover(linkEl, cellInp, function (updatedHtml) {
                commitCell(updatedHtml);
              });
            }
          });

          // Excel Multi-Zellen Copy-Paste Support (Single-Cell Paste fügt Plaintext ohne fremde Styles ein)
          cellInp.addEventListener("paste", function (e) {
            const clipText = (e.clipboardData || window.clipboardData).getData("text/plain");
            if (!clipText || (clipText.indexOf("\t") === -1 && clipText.indexOf("\n") === -1 && clipText.indexOf("\r") === -1)) {
              e.preventDefault();
              e.stopPropagation();
              document.execCommand("insertText", false, clipText || "");
              commitCell();
              return;
            }
            e.preventDefault();
            e.stopPropagation();
            pasteTsvAtCell(rIdx, cIdx, clipText);
          });

          td.appendChild(cellInp);
          tr.appendChild(td);
        });

        const delTd = document.createElement("td");
        delTd.style.textAlign = "center";
        delTd.style.verticalAlign = "top";
        delTd.style.paddingTop = "3px";
        const delRowBtn = document.createElement("button");
        delRowBtn.type = "button";
        delRowBtn.className = "btn-icon-only danger";
        delRowBtn.title = "Zeile löschen";
        delRowBtn.textContent = "✕";
        delRowBtn.addEventListener("click", function () {
          deleteRowAt(rIdx);
        });
        delTd.appendChild(delRowBtn);
        tr.appendChild(delTd);

        tbody.appendChild(tr);
      });

      tbl.appendChild(tbody);

      // Mehrzellige Markierung per Maus-Ziehen & Shift+Klick
      tbl.addEventListener("mousedown", function (e) {
        if (e.button !== 0) return;
        const td = e.target.closest("td[data-row-idx][data-col-idx]");
        if (!td || !tbl.contains(td)) return;

        const rIdx = parseInt(td.dataset.rowIdx, 10);
        const cIdx = parseInt(td.dataset.colIdx, 10);
        if (isNaN(rIdx) || isNaN(cIdx)) return;

        const active = ensureActiveTableState();

        if (e.shiftKey && active.anchor) {
          e.preventDefault();
          active.lead = { row: rIdx, col: cIdx };
          active.range = expandRangeToMerges(blk, normalizeTableCellRange(active.anchor, active.lead));
          applySelectionStyles();
          updateSelectionUI();
          gridScroll.focus({ preventScroll: true });
          return;
        }

        if (active.range) {
          active.range = null;
          active.lead = null;
          applySelectionStyles();
          updateSelectionUI();
        }
        active.anchor = { row: rIdx, col: cIdx };
        tableEditorState.drag = {
          active: true,
          movedOut: false,
          blockId: blk.id,
          tbl: tbl,
          gridScroll: gridScroll,
          anchor: { row: rIdx, col: cIdx },
        };
      });

      tbl.addEventListener("contextmenu", function (e) {
        const td = e.target.closest("td[data-row-idx][data-col-idx]");
        if (!td || !tbl.contains(td)) return;
        const rIdx = parseInt(td.dataset.rowIdx, 10);
        const cIdx = parseInt(td.dataset.colIdx, 10);
        if (isNaN(rIdx) || isNaN(cIdx)) return;

        e.preventDefault();
        const active = ensureActiveTableState();
        if (!active.range || !isTableCellInRange(rIdx, cIdx, active.range, td.rowSpan || 1, td.colSpan || 1)) {
          active.anchor = { row: rIdx, col: cIdx };
          active.lead = { row: rIdx, col: cIdx };
          active.range = expandRangeToMerges(blk, { minRow: rIdx, maxRow: rIdx, minCol: cIdx, maxCol: cIdx });
          applySelectionStyles();
          updateSelectionUI();
          gridScroll.focus({ preventScroll: true });
        }
        openTableCellContextMenu(e.clientX, e.clientY, rIdx, cIdx);
      });

      gridScroll.appendChild(tbl);
      if (tableEditorState.active && tableEditorState.active.blockId === blk.id) {
        tableEditorState.active.tbl = tbl;
        applySelectionStyles();
      }
      updateSelectionUI();
      requestAnimationFrame(autoResizeAllGridCells);
    };

    gridScroll.addEventListener("copy", function (e) {
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return;
      const ae = document.activeElement;
      if (isCellInputEl(ae) && gridScroll.contains(ae)) {
        if (hasInnerTextSelection(ae)) return;
      }
      e.preventDefault();
      e.stopPropagation();
      if (e.clipboardData) {
        e.clipboardData.setData("text/plain", getTableRangeTsv(blk, active.range));
        e.clipboardData.setData("text/html", getTableRangeHtml(blk, active.range));
      }
      flashCopiedButtonFeedback();
    });

    gridScroll.addEventListener("cut", function (e) {
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return;
      const ae = document.activeElement;
      if (isCellInputEl(ae) && gridScroll.contains(ae)) {
        if (hasInnerTextSelection(ae)) return;
      }
      e.preventDefault();
      e.stopPropagation();
      if (e.clipboardData) {
        e.clipboardData.setData("text/plain", getTableRangeTsv(blk, active.range));
        e.clipboardData.setData("text/html", getTableRangeHtml(blk, active.range));
      }
      clearSelectedRangeValues();
    });

    gridScroll.addEventListener("paste", function (e) {
      if (isCellInputEl(e.target)) return;
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return;
      const clipText = (e.clipboardData || window.clipboardData).getData("text/plain");
      if (!clipText) return;
      e.preventDefault();
      e.stopPropagation();

      if (clipText.indexOf("\t") === -1 && clipText.indexOf("\n") === -1 && clipText.indexOf("\r") === -1) {
        const val = clipText.trim();
        let changed = false;
        for (let r = active.range.minRow; r <= active.range.maxRow && r < blk.rows.length; r++) {
          for (let c = active.range.minCol; c <= active.range.maxCol && c < blk.columns.length; c++) {
            const field = blk.columns[c].field;
            if (blk.rows[r][field] !== val) {
              blk.rows[r][field] = val;
              changed = true;
            }
          }
        }
        if (changed) {
          renderGrid();
          markDirty();
        }
        gridScroll.focus({ preventScroll: true });
        return;
      }
      pasteTsvAtCell(active.range.minRow, active.range.minCol, clipText);
    });

    gridScroll.addEventListener("keydown", function (e) {
      const active = tableEditorState.active;
      if (!active || active.blockId !== blk.id || !active.range) return;
      if (isCellInputEl(e.target)) return;

      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
        const k = e.key.toLowerCase();
        if (k === "b" || k === "i" || k === "u") {
          e.preventDefault();
          const cmd = k === "b" ? "bold" : k === "i" ? "italic" : "underline";
          applyFormatToSelectedRange(cmd);
          return;
        }
      }

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
        if (!blk.rows.length || !blk.columns.length) return;
        e.preventDefault();
        active.anchor = { row: 0, col: 0 };
        active.lead = { row: blk.rows.length - 1, col: blk.columns.length - 1 };
        active.range = normalizeTableCellRange(active.anchor, active.lead);
        applySelectionStyles();
        updateSelectionUI();
        return;
      }

      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        clearSelectedRangeValues();
        return;
      }

      if (e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown" || e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        if (!blk.rows.length || !blk.columns.length) return;
        e.preventDefault();
        const lead = active.lead || { row: active.range.maxRow, col: active.range.maxCol };
        let nextRow = lead.row;
        let nextCol = lead.col;
        if (e.key === "ArrowUp") nextRow = Math.max(0, nextRow - 1);
        if (e.key === "ArrowDown") nextRow = Math.min(blk.rows.length - 1, nextRow + 1);
        if (e.key === "ArrowLeft") nextCol = Math.max(0, nextCol - 1);
        if (e.key === "ArrowRight") nextCol = Math.min(blk.columns.length - 1, nextCol + 1);
        active.lead = { row: nextRow, col: nextCol };
        active.range = expandRangeToMerges(blk, normalizeTableCellRange(active.anchor || lead, active.lead));
        applySelectionStyles();
        updateSelectionUI();
      }
    });

    copySelBtn.addEventListener("click", copySelectedRange);
    mergeSelBtn.addEventListener("click", mergeSelectedRange);
    unmergeSelBtn.addEventListener("click", unmergeSelectedRange);
    clearSelValuesBtn.addEventListener("click", clearSelectedRangeValues);
    deselectBtn.addEventListener("click", clearTableSelection);

    useFirstRowHeaderBtn.addEventListener("click", promoteFirstRowToHeader);

    eqWidthBtn.addEventListener("click", function () {
      distributeEqualColumnWidths(blk.columns);
      renderGrid();
      markDirty();
    });

    addRowBtn.addEventListener("click", function () {
      insertRowAt(blk.rows.length);
    });

    addColBtn.addEventListener("click", function () {
      insertColumnAt(blk.columns.length);
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


  Object.assign(E, {
    buildTableBlockBody: buildTableBlockBody,
    clearTableSelection: clearTableSelection,
    closeTableContextMenu: closeTableContextMenu,
    copyViaHiddenTextarea: copyViaHiddenTextarea,
    formatTsvCell: formatTsvCell,
    getTableRangeHtml: getTableRangeHtml,
    getTableRangeTsv: getTableRangeTsv,
    isTableCellInRange: isTableCellInRange,
    normalizeTableCellRange: normalizeTableCellRange,
    parseClipboardTsv: parseClipboardTsv,
    tableEditorState: tableEditorState,
    writeTableSelectionToClipboard: writeTableSelectionToClipboard,
  });
})();
