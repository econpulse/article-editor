/**
 * LUKB Editor Modul: DB-Chart (ts_db Zeitreihen-Konfigurator & Ticker-Autocomplete)
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function createFullLayoutControl() { return E.createFullLayoutControl.apply(this, arguments); }
  function deepClone() { return E.deepClone.apply(this, arguments); }
  function flushAutosave() { return E.flushAutosave ? E.flushAutosave.apply(this, arguments) : undefined; }
  function markDirty() { return E.markDirty.apply(this, arguments); }
  const state = E.state;

  const DB_CHART_PALETTES = E.CHART_PALETTES;

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
    if (blk.legend_columns === undefined) {
      blk.legend_columns = null;
    }
    if (blk.show_legend === undefined) {
      blk.show_legend = true;
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

    const layoutWrap = createFullLayoutControl(blk, function () {
      requestDbChartPreview(blk, true);
    });

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

    const dateInp = document.createElement("input");
    dateInp.type = "date";
    dateInp.className = "cms-input";
    dateInp.style.width = "100%";
    dateInp.value = blk.start_date || "2022-01-01";
    dateInp.addEventListener("change", function () {
      blk.start_date = dateInp.value || "2022-01-01";
      requestDbChartPreview(blk, true);
      markDirty();
      if (typeof flushAutosave === "function") flushAutosave(false);
    });

    // Schnellwahl-Buttons für Startdatum (unterhalb des Datumsfeldes, verhindert Überlappung)
    const presetRow = document.createElement("div");
    presetRow.className = "db-chart-date-presets";
    presetRow.style.display = "flex";
    presetRow.style.gap = "4px";
    presetRow.style.marginTop = "5px";
    presetRow.style.alignItems = "center";
    presetRow.style.flexWrap = "wrap";

    const presetLbl = document.createElement("span");
    presetLbl.style.fontSize = "11px";
    presetLbl.style.color = "var(--lukb-muted, #64748B)";
    presetLbl.style.marginRight = "2px";
    presetLbl.textContent = "Start:";
    presetRow.appendChild(presetLbl);

    [
      { label: "2021", date: "2021-01-01" },
      { label: "2023", date: "2023-01-01" },
      { label: "2025", date: "2025-01-01" },
    ].forEach(function (preset) {
      const pBtn = document.createElement("button");
      pBtn.type = "button";
      pBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
      pBtn.style.padding = "2px 7px";
      pBtn.style.fontSize = "11px";
      pBtn.style.lineHeight = "1.2";
      pBtn.textContent = preset.label;
      pBtn.title = "Startdatum auf " + preset.date + " setzen";
      pBtn.addEventListener("click", function () {
        blk.start_date = preset.date;
        dateInp.value = preset.date;
        requestDbChartPreview(blk, true);
        markDirty();
        if (typeof flushAutosave === "function") flushAutosave(false);
      });
      presetRow.appendChild(pBtn);
    });

    dateWrap.appendChild(dateLbl);
    dateWrap.appendChild(dateInp);
    dateWrap.appendChild(presetRow);

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
      if (typeof flushAutosave === "function") flushAutosave(false);
    });
    rebaseWrap.appendChild(rebaseLbl);
    rebaseWrap.appendChild(rebaseSel);

    // Legende / Spalten der Legende
    const legColsWrap = document.createElement("div");
    const legColsLbl = document.createElement("label");
    legColsLbl.className = "field-label";
    legColsLbl.textContent = "Legende";
    const legColsSel = document.createElement("select");
    legColsSel.className = "cms-select";

    const curVal =
      blk.show_legend === false
        ? "none"
        : blk.legend_columns !== undefined && blk.legend_columns !== null
          ? String(blk.legend_columns)
          : "auto";
    legColsSel.innerHTML =
      '<option value="auto">Automatisch (kompakt)</option>' +
      '<option value="1">1 Spalte</option>' +
      '<option value="2">2 Spalten</option>' +
      '<option value="3">3 Spalten</option>' +
      '<option value="4">4 Spalten</option>' +
      '<option value="none">Keine Legende</option>';
    legColsSel.value = curVal;

    legColsSel.addEventListener("change", function () {
      if (legColsSel.value === "none") {
        blk.show_legend = false;
      } else {
        blk.show_legend = true;
        blk.legend_columns =
          legColsSel.value === "auto" ? null : parseInt(legColsSel.value, 10);
      }
      markDirty();
      requestDbChartPreview(blk, true);
      if (typeof flushAutosave === "function") flushAutosave(false);
    });

    legColsWrap.appendChild(legColsLbl);
    legColsWrap.appendChild(legColsSel);

    configGrid.appendChild(dateWrap);
    configGrid.appendChild(rebaseWrap);
    configGrid.appendChild(legColsWrap);
    container.appendChild(configGrid);

    // Zeile 3b: Farbpaletten-Steuerung (LUKB Standard vs. Blau-Abstufung)
    const paletteCtrl = E.createChartPaletteBar(blk, DB_CHART_PALETTES, function () {
      renderSeriesRows();
      requestDbChartPreview(blk, true);
      markDirty();
      if (typeof flushAutosave === "function") flushAutosave(false);
    });
    const getActivePaletteColors = paletteCtrl.getActiveColors;
    container.appendChild(paletteCtrl.element);

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
      const activeColors = getActivePaletteColors();
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
        delete sItem.color;

        const row = document.createElement("div");
        row.className = "db-chart-series-row";

        const colorDot = document.createElement("span");
        colorDot.className = "db-series-color-dot";
        colorDot.style.backgroundColor = activeColors[sIdx % activeColors.length];
        colorDot.title = "Farbe der Zeitreihe " + (sIdx + 1) + " (aus gewählter Palette)";

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

        const axisToggle = E.createSeriesAxisToggle(sItem, function (nextAxis) {
          const fallbackName = lookupTickerName(sItem.ticker) || sItem.ticker;
          E.syncSeriesAxisLegendLabel(sItem, nextAxis, fallbackName, true);
          labelInp.value = sItem.label || "";
          requestDbChartPreview(blk, true);
          markDirty();
          if (typeof flushAutosave === "function") flushAutosave(false);
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
        row.appendChild(axisToggle);
        row.appendChild(labelInp);
        row.appendChild(delBtn);
        seriesListEl.appendChild(row);
      });
    }

    addSeriesBtn.addEventListener("click", function () {
      if (blk.series.length >= 5) return;
      blk.series.push({ ticker: "", chart_type: "line", chart_types: ["line"], label: "", y_axis: "left" });
      renderSeriesRows();
      markDirty();
    });

    renderSeriesRows();
    container.appendChild(seriesSection);

    // Zeile 4b: Y-Achsen-Skalierung (Min, Max, Step für linke & rechte Y-Achse)
    const yAxisBar = E.createChartYAxisControls(blk, function () {
      requestDbChartPreview(blk, true);
      markDirty();
      if (typeof flushAutosave === "function") flushAutosave(false);
    });
    container.appendChild(yAxisBar);

    // Zeile 5: Eigener Container für Höhe der Chartfläche (Y-Achse in mm)
    const heightBar = E.createChartHeightBar(blk, null, function () {
      requestDbChartPreview(blk, true);
      markDirty();
      if (typeof flushAutosave === "function") flushAutosave(false);
    });
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


  Object.assign(E, {
    DB_CHART_PALETTES: DB_CHART_PALETTES,
    attachTickerAutocomplete: attachTickerAutocomplete,
    buildDbChartBlockBody: buildDbChartBlockBody,
    closeTickerSuggestPopover: closeTickerSuggestPopover,
    ensureTickerSuggestPopover: ensureTickerSuggestPopover,
    indexTickerItems: indexTickerItems,
    lookupTickerName: lookupTickerName,
    positionTickerSuggestPopover: positionTickerSuggestPopover,
    renderTickerSuggestItems: renderTickerSuggestItems,
    requestDbChartPreview: requestDbChartPreview,
    tickerSuggest: tickerSuggest,
    triggerTickerSuggestQuery: triggerTickerSuggestQuery,
    updateTickerSuggestHighlight: updateTickerSuggestHighlight,
  });
})();
