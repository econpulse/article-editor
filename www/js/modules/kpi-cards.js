/**
 * LUKB Editor Modul: KPI- / Dashboard-Karten (`kpi_cards`) mit Finanzmarkt-Icon-Picker
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function createFullLayoutControl() { return E.createFullLayoutControl.apply(this, arguments); }
  function markDirty() { return E.markDirty.apply(this, arguments); }

  let _cachedCatalog = null;

  function getCatalog() {
    if (_cachedCatalog) return _cachedCatalog;
    let parsed = { icons: [], tones: [] };
    try {
      const el = document.getElementById("lukb-kpi-icons-data");
      if (el && el.textContent) {
        parsed = JSON.parse(el.textContent);
      }
    } catch (err) {
      console.warn("LUKB KPI Icons konnten nicht geladen werden:", err);
    }
    _cachedCatalog = {
      icons: Array.isArray(parsed.icons) ? parsed.icons : [],
      tones: Array.isArray(parsed.tones) && parsed.tones.length > 0 ? parsed.tones : [
        { id: "navy", label: "LUKB Navy", accent: "#002855", tint: "#EEF3F8", badge: "#DCE6F2", border: "#C2D1E2" },
        { id: "blue", label: "LUKB Blau", accent: "#005A9C", tint: "#EDF4FA", badge: "#D9E9F7", border: "#B8D2EA" },
        { id: "cyan", label: "LUKB Cyan", accent: "#009FE3", tint: "#EDF8FD", badge: "#D7F0FC", border: "#AEDFF7" },
        { id: "gold", label: "LUKB Gold", accent: "#C59B27", tint: "#FBF7EC", badge: "#F4E9CA", border: "#E5D29A" },
        { id: "positive", label: "Positiv (Grün)", accent: "#1E7E48", tint: "#EFF8F3", badge: "#D8EFE2", border: "#B4DEC6" },
        { id: "negative", label: "Risiko / Negativ (Rot)", accent: "#B83227", tint: "#FDF1F0", badge: "#F9DCD9", border: "#ECC0BC" },
        { id: "neutral", label: "Neutral (Grau)", accent: "#5A687C", tint: "#F4F7FA", badge: "#E3E9F0", border: "#D6DEE8" },
      ],
    };
    return _cachedCatalog;
  }

  function findTone(toneId) {
    const cat = getCatalog();
    const key = String(toneId || "navy").toLowerCase();
    return cat.tones.find(function (t) { return t.id === key; }) || cat.tones[0];
  }

  function findIcon(iconId) {
    const cat = getCatalog();
    const key = String(iconId || "").toLowerCase();
    if (!key) return null;
    return cat.icons.find(function (ic) { return ic.id === key; }) || null;
  }

  function renderIconSvgHtml(iconId, strokeColor, sizePx) {
    const icon = findIcon(iconId);
    if (!icon) return '<span style="font-size:11px;color:#94A3B8;">—</span>';
    const sz = sizePx || 18;
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" width="' + sz + '" height="' + sz + '" ' +
      'viewBox="0 0 24 24" fill="none" stroke="' + (strokeColor || "#002855") + '" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
      icon.markup +
      "</svg>"
    );
  }

  let _activePopover = null;

  function closeIconPickerPopover() {
    if (_activePopover && _activePopover.parentNode) {
      _activePopover.parentNode.removeChild(_activePopover);
    }
    _activePopover = null;
  }

  document.addEventListener("click", function (e) {
    if (_activePopover && !e.target.closest(".kpi-icon-picker-popover") && !e.target.closest(".kpi-icon-picker-btn")) {
      closeIconPickerPopover();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeIconPickerPopover();
  });

  function openIconPickerPopover(anchorBtn, card, onPicked) {
    closeIconPickerPopover();
    const cat = getCatalog();
    const tone = findTone(card.tone);

    const pop = document.createElement("div");
    pop.className = "kpi-icon-picker-popover";
    const ownerBlockCard = anchorBtn && anchorBtn.closest ? anchorBtn.closest(".cms-block-card") : null;
    if (ownerBlockCard && ownerBlockCard.dataset && ownerBlockCard.dataset.blockId) {
      pop.dataset.ownerBlockId = ownerBlockCard.dataset.blockId;
    }

    const searchRow = document.createElement("div");
    searchRow.className = "kpi-icon-picker-search-row";
    const searchInp = document.createElement("input");
    searchInp.type = "text";
    searchInp.className = "cms-input";
    searchInp.placeholder = "Icon suchen (z. B. Zins, Aktie, Gold, ESG) …";
    searchInp.style.fontSize = "12px";
    searchInp.style.padding = "5px 8px";

    function focusNoScroll(el) {
      if (!el || typeof el.focus !== "function") return;
      try {
        el.focus({ preventScroll: true });
      } catch (_) {
        el.focus();
      }
    }

    const noneBtn = document.createElement("button");
    noneBtn.type = "button";
    noneBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    noneBtn.textContent = "Ohne Icon";
    noneBtn.style.whiteSpace = "nowrap";
    noneBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      card.icon = "";
      closeIconPickerPopover();
      onPicked();
      focusNoScroll(anchorBtn);
      markDirty();
    });

    searchRow.appendChild(searchInp);
    searchRow.appendChild(noneBtn);
    pop.appendChild(searchRow);

    const listWrap = document.createElement("div");
    listWrap.className = "kpi-icon-picker-scroll";
    pop.appendChild(listWrap);

    function renderIconList(filterText) {
      listWrap.innerHTML = "";
      const q = (filterText || "").trim().toLowerCase();
      const filtered = cat.icons.filter(function (ic) {
        if (!q) return true;
        return (
          ic.label.toLowerCase().indexOf(q) !== -1 ||
          ic.category.toLowerCase().indexOf(q) !== -1 ||
          ic.keywords.toLowerCase().indexOf(q) !== -1 ||
          ic.id.toLowerCase().indexOf(q) !== -1
        );
      });

      if (filtered.length === 0) {
        const empty = document.createElement("div");
        empty.style.padding = "12px";
        empty.style.fontSize = "12px";
        empty.style.color = "#64748B";
        empty.textContent = "Keine passenden Finanz-Icons gefunden.";
        listWrap.appendChild(empty);
        return;
      }

      const byCat = new Map();
      filtered.forEach(function (ic) {
        if (!byCat.has(ic.category)) byCat.set(ic.category, []);
        byCat.get(ic.category).push(ic);
      });

      byCat.forEach(function (iconsList, catName) {
        const catHdr = document.createElement("div");
        catHdr.className = "kpi-icon-cat-title";
        catHdr.textContent = catName;
        listWrap.appendChild(catHdr);

        const grid = document.createElement("div");
        grid.className = "kpi-icon-swatch-grid";
        iconsList.forEach(function (ic) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "kpi-icon-swatch" + (card.icon === ic.id ? " is-active" : "");
          btn.title = ic.label;
          btn.innerHTML =
            '<span class="kpi-icon-swatch-badge" style="background:' + tone.badge + ';">' +
            renderIconSvgHtml(ic.id, tone.accent, 18) +
            "</span>" +
            '<span class="kpi-icon-swatch-lbl"></span>';
          btn.querySelector(".kpi-icon-swatch-lbl").textContent = ic.label;
          btn.addEventListener("click", function (e) {
            e.stopPropagation();
            card.icon = ic.id;
            closeIconPickerPopover();
            onPicked();
            focusNoScroll(anchorBtn);
            markDirty();
          });
          grid.appendChild(btn);
        });
        listWrap.appendChild(grid);
      });
    }

    renderIconList("");
    searchInp.addEventListener("input", function () {
      renderIconList(searchInp.value);
    });

    document.body.appendChild(pop);
    _activePopover = pop;

    const rect = anchorBtn.getBoundingClientRect();
    const popW = Math.min(380, window.innerWidth - 24);
    pop.style.width = popW + "px";
    let left = rect.left + window.scrollX;
    if (left + popW > window.innerWidth - 12) {
      left = Math.max(12, window.innerWidth - popW - 12);
    }
    let top = rect.bottom + window.scrollY + 6;
    const popH = pop.offsetHeight || 320;
    if (rect.bottom + popH > window.innerHeight - 12 && rect.top > popH + 16) {
      top = rect.top + window.scrollY - popH - 6;
    }
    const maxTop = Math.max(12, window.scrollY + window.innerHeight - popH - 12);
    top = Math.min(Math.max(12, top), maxTop);
    pop.style.left = left + "px";
    pop.style.top = top + "px";
    setTimeout(function () { focusNoScroll(searchInp); }, 10);
  }

  function createDefaultKpiCard() {
    return {
      icon: "trend_up",
      label: "Neue Kennzahl",
      value: "0.00 %",
      subtext: "Kurzer Kontext",
      tone: "navy",
    };
  }

  function buildKpiCardsBlockBody(container, blk) {
    if (!blk.layout) blk.layout = "full";
    if (!blk.full_position) blk.full_position = "inline";
    if (blk.columns_count === undefined || blk.columns_count === null) blk.columns_count = 0;
    if (!blk.style_preset) blk.style_preset = "tint";
    if (!Array.isArray(blk.cards) || blk.cards.length === 0) {
      blk.cards = [
        { icon: "central_bank", label: "SNB Leitzins", value: "0.50 %", subtext: "−25 Bp vs. Vorquartal", tone: "navy" },
        { icon: "trend_up", label: "Aktien Schweiz", value: "Übergewichten", subtext: "Attraktive Dividendenrendite", tone: "cyan" },
        { icon: "shield", label: "Qualitätsfokus", value: "Defensive Titel", subtext: "Stabile Margen im Umfeld", tone: "gold" },
      ];
    }

    // Zeile 1: Titel & Satzbreite
    const topGrid = document.createElement("div");
    topGrid.style.display = "grid";
    topGrid.style.gridTemplateColumns = "1fr 195px";
    topGrid.style.gap = "10px";
    topGrid.style.marginBottom = "10px";

    const leftMeta = document.createElement("div");
    const titleLbl = document.createElement("label");
    titleLbl.className = "field-label";
    titleLbl.textContent = "Optionaler Block-Titel";
    const titleInp = document.createElement("input");
    titleInp.type = "text";
    titleInp.className = "cms-input font-medium";
    titleInp.placeholder = "z. B. Makro- & Marktindikatoren auf einen Blick";
    titleInp.value = blk.title || "";
    titleInp.addEventListener("input", function () {
      blk.title = titleInp.value;
      markDirty();
    });

    const subLbl = document.createElement("label");
    subLbl.className = "field-label";
    subLbl.style.marginTop = "8px";
    subLbl.textContent = "Optionaler Untertitel";
    const subInp = document.createElement("input");
    subInp.type = "text";
    subInp.className = "cms-input";
    subInp.placeholder = "z. B. Einschätzung LUKB Investment Office (Stand Q4 2026)";
    subInp.value = blk.subtitle || "";
    subInp.addEventListener("input", function () {
      blk.subtitle = subInp.value;
      markDirty();
    });

    leftMeta.appendChild(titleLbl);
    leftMeta.appendChild(titleInp);
    leftMeta.appendChild(subLbl);
    leftMeta.appendChild(subInp);

    const layoutWrap = createFullLayoutControl(blk);
    topGrid.appendChild(leftMeta);
    topGrid.appendChild(layoutWrap);
    container.appendChild(topGrid);

    // Zeile 2: Steuerleiste (Stil & Spalten)
    const cfgBar = document.createElement("div");
    cfgBar.className = "kpi-config-bar";

    const styleWrap = document.createElement("div");
    const styleLbl = document.createElement("label");
    styleLbl.className = "field-label";
    styleLbl.style.fontSize = "11px";
    styleLbl.textContent = "Karten-Stil";
    const styleSel = document.createElement("select");
    styleSel.className = "cms-select";
    styleSel.style.fontSize = "12px";
    styleSel.style.padding = "4px 7px";
    [
      { val: "tint", label: "Dezent getönt (Dashboard)" },
      { val: "card_accent_top", label: "Weiss + Akzentlinie oben" },
      { val: "card_accent_left", label: "Dezent + Akzentlinie links" },
      { val: "clean", label: "Weiss / Minimalistisch" },
    ].forEach(function (o) {
      const opt = document.createElement("option");
      opt.value = o.val;
      opt.textContent = o.label;
      if (blk.style_preset === o.val) opt.selected = true;
      styleSel.appendChild(opt);
    });
    styleSel.addEventListener("change", function () {
      blk.style_preset = styleSel.value;
      renderCardsEditor();
      markDirty();
    });
    styleWrap.appendChild(styleLbl);
    styleWrap.appendChild(styleSel);

    const colsWrap = document.createElement("div");
    const colsLbl = document.createElement("label");
    colsLbl.className = "field-label";
    colsLbl.style.fontSize = "11px";
    colsLbl.textContent = "Karten pro Zeile";
    const colsSel = document.createElement("select");
    colsSel.className = "cms-select";
    colsSel.style.fontSize = "12px";
    colsSel.style.padding = "4px 7px";
    [
      { val: "0", label: "Auto (1–4 je nach Breite)" },
      { val: "1", label: "1 Spalte (gestapelt)" },
      { val: "2", label: "2 Spalten" },
      { val: "3", label: "3 Spalten" },
      { val: "4", label: "4 Spalten" },
    ].forEach(function (o) {
      const opt = document.createElement("option");
      opt.value = o.val;
      opt.textContent = o.label;
      if (String(blk.columns_count || 0) === o.val) opt.selected = true;
      colsSel.appendChild(opt);
    });
    colsSel.addEventListener("change", function () {
      blk.columns_count = parseInt(colsSel.value, 10) || 0;
      markDirty();
    });
    colsWrap.appendChild(colsLbl);
    colsWrap.appendChild(colsSel);

    const addWrap = document.createElement("div");
    addWrap.style.display = "flex";
    addWrap.style.alignItems = "flex-end";
    addWrap.style.justifyContent = "flex-end";
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    addBtn.textContent = "+ Karte hinzufügen";
    addBtn.addEventListener("click", function () {
      if (blk.cards.length >= 8) return;
      blk.cards.push(createDefaultKpiCard());
      renderCardsEditor();
      markDirty();
    });
    addWrap.appendChild(addBtn);

    cfgBar.appendChild(styleWrap);
    cfgBar.appendChild(colsWrap);
    cfgBar.appendChild(addWrap);
    container.appendChild(cfgBar);

    // Zeile 3: Karten-Liste
    const cardsListEl = document.createElement("div");
    cardsListEl.className = "kpi-cards-editor-list";
    container.appendChild(cardsListEl);

    function renderCardsEditor() {
      cardsListEl.innerHTML = "";
      addBtn.disabled = blk.cards.length >= 8;
      const cat = getCatalog();

      blk.cards.forEach(function (card, idx) {
        const tone = findTone(card.tone);
        const itemEl = document.createElement("div");
        itemEl.className = "kpi-card-editor-item";
        itemEl.style.borderLeft = "3px solid " + tone.accent;
        if (blk.style_preset === "tint") {
          itemEl.style.background = tone.tint;
        }

        // Kopfzeile der Karte (Nummer, Tone-Farbpunkte, Aktionen)
        const itemHdr = document.createElement("div");
        itemHdr.className = "kpi-card-editor-head";

        const badge = document.createElement("span");
        badge.className = "kpi-card-editor-num";
        badge.textContent = "Karte " + (idx + 1);

        const toneBar = document.createElement("div");
        toneBar.className = "kpi-tone-pills";
        cat.tones.forEach(function (t) {
          const dot = document.createElement("button");
          dot.type = "button";
          dot.className = "kpi-tone-dot" + (card.tone === t.id ? " is-active" : "");
          dot.title = t.label;
          dot.style.background = t.accent;
          dot.addEventListener("click", function () {
            card.tone = t.id;
            renderCardsEditor();
            markDirty();
          });
          toneBar.appendChild(dot);
        });

        const actions = document.createElement("div");
        actions.className = "kpi-card-editor-actions";

        const upBtn = document.createElement("button");
        upBtn.type = "button";
        upBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        upBtn.textContent = "↑";
        upBtn.title = "Nach vorne";
        upBtn.disabled = idx === 0;
        upBtn.addEventListener("click", function () {
          const tmp = blk.cards[idx - 1];
          blk.cards[idx - 1] = blk.cards[idx];
          blk.cards[idx] = tmp;
          renderCardsEditor();
          markDirty();
        });

        const downBtn = document.createElement("button");
        downBtn.type = "button";
        downBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        downBtn.textContent = "↓";
        downBtn.title = "Nach hinten";
        downBtn.disabled = idx === blk.cards.length - 1;
        downBtn.addEventListener("click", function () {
          const tmp = blk.cards[idx + 1];
          blk.cards[idx + 1] = blk.cards[idx];
          blk.cards[idx] = tmp;
          renderCardsEditor();
          markDirty();
        });

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        delBtn.textContent = "✕";
        delBtn.title = "Karte entfernen";
        delBtn.disabled = blk.cards.length <= 1;
        delBtn.addEventListener("click", function () {
          if (blk.cards.length <= 1) return;
          blk.cards.splice(idx, 1);
          renderCardsEditor();
          markDirty();
        });

        actions.appendChild(upBtn);
        actions.appendChild(downBtn);
        actions.appendChild(delBtn);

        itemHdr.appendChild(badge);
        itemHdr.appendChild(toneBar);
        itemHdr.appendChild(actions);
        itemEl.appendChild(itemHdr);

        // Felder: Icon-Button + Label + Wert + Untertext
        const fieldsGrid = document.createElement("div");
        fieldsGrid.className = "kpi-card-editor-fields";

        const iconCol = document.createElement("div");
        const iconLbl = document.createElement("label");
        iconLbl.className = "field-label";
        iconLbl.style.fontSize = "11px";
        iconLbl.textContent = "Icon";
        const iconBtn = document.createElement("button");
        iconBtn.type = "button";
        iconBtn.className = "kpi-icon-picker-btn";
        function updateIconBtnVisual() {
          const iconInfo = findIcon(card.icon);
          iconBtn.innerHTML =
            '<span class="kpi-icon-picker-badge" style="background:' + tone.badge + ';">' +
            renderIconSvgHtml(card.icon, tone.accent, 17) +
            "</span>" +
            '<span class="kpi-icon-picker-name"></span>' +
            '<span style="font-size:10px;color:#64748B;">▾</span>';
          iconBtn.querySelector(".kpi-icon-picker-name").textContent = iconInfo ? iconInfo.label : "Ohne Icon";
        }
        updateIconBtnVisual();
        iconBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          openIconPickerPopover(iconBtn, card, updateIconBtnVisual);
        });
        iconCol.appendChild(iconLbl);
        iconCol.appendChild(iconBtn);

        const lblCol = document.createElement("div");
        const lblFieldLbl = document.createElement("label");
        lblFieldLbl.className = "field-label";
        lblFieldLbl.style.fontSize = "11px";
        lblFieldLbl.textContent = "Dachzeile / Label";
        const lblInp = document.createElement("input");
        lblInp.type = "text";
        lblInp.className = "cms-input";
        lblInp.placeholder = "z. B. SNB Leitzins";
        lblInp.value = card.label || "";
        lblInp.addEventListener("input", function () {
          card.label = lblInp.value;
          markDirty();
        });
        lblCol.appendChild(lblFieldLbl);
        lblCol.appendChild(lblInp);

        const valCol = document.createElement("div");
        const valFieldLbl = document.createElement("label");
        valFieldLbl.className = "field-label";
        valFieldLbl.style.fontSize = "11px";
        valFieldLbl.textContent = "Wert / Kernaussage";
        const valInp = document.createElement("input");
        valInp.type = "text";
        valInp.className = "cms-input font-medium";
        valInp.placeholder = "z. B. 0.50 % oder Übergewichten";
        valInp.value = card.value || "";
        valInp.addEventListener("input", function () {
          card.value = valInp.value;
          markDirty();
        });
        valCol.appendChild(valFieldLbl);
        valCol.appendChild(valInp);

        const subCol = document.createElement("div");
        const subFieldLbl = document.createElement("label");
        subFieldLbl.className = "field-label";
        subFieldLbl.style.fontSize = "11px";
        subFieldLbl.textContent = "Untertext / Delta (optional)";
        const subCardInp = document.createElement("input");
        subCardInp.type = "text";
        subCardInp.className = "cms-input";
        subCardInp.placeholder = "z. B. −25 Bp vs. Vorquartal";
        subCardInp.value = card.subtext || "";
        subCardInp.addEventListener("input", function () {
          card.subtext = subCardInp.value;
          markDirty();
        });
        subCol.appendChild(subFieldLbl);
        subCol.appendChild(subCardInp);

        fieldsGrid.appendChild(iconCol);
        fieldsGrid.appendChild(lblCol);
        fieldsGrid.appendChild(valCol);
        fieldsGrid.appendChild(subCol);
        itemEl.appendChild(fieldsGrid);

        cardsListEl.appendChild(itemEl);
      });
    }

    renderCardsEditor();

    // Zeile 4: Optionale Quellenangabe
    const srcWrap = document.createElement("div");
    srcWrap.style.marginTop = "8px";
    const srcLbl = document.createElement("label");
    srcLbl.className = "field-label";
    srcLbl.textContent = "Optionale Quellenangabe";
    const srcInp = document.createElement("input");
    srcInp.type = "text";
    srcInp.className = "cms-input";
    srcInp.placeholder = "z. B. Quelle: Bloomberg, LUKB Investment Office";
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
    buildKpiCardsBlockBody: buildKpiCardsBlockBody,
  });
})();
