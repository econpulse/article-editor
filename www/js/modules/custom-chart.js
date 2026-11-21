/**
 * LUKB Editor Modul: Custom-Chart (Daten-Diagramm aus Zwischenablage / Excel)
 * Unterstützt Wide-Format Daten für:
 * - Doughnut / Pie Chart
 * - Kategorie-Säulen (gruppiert / gestapelt)
 * - Zeitreihen-Diagramm
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function createFullLayoutControl() { return E.createFullLayoutControl.apply(this, arguments); }
  function deepClone() { return E.deepClone.apply(this, arguments); }
  function markDirty() { return E.markDirty.apply(this, arguments); }
  function flushAutosave() { return E.flushAutosave ? E.flushAutosave.apply(this, arguments) : undefined; }
  function escapeHtml(s) { return E.escapeHtml ? E.escapeHtml(s) : String(s || ""); }
  const state = E.state;

  const CUSTOM_CHART_PALETTES = E.CHART_PALETTES;

  function parseClientTsv(text, hasHeader) {
    const raw = String(text || "").trim();
    if (!raw) return { columns: [], rows: [] };

    const firstLine = raw.split(/\r?\n/)[0] || "";
    let delimiter = "\t";
    if (firstLine.indexOf("\t") >= 0) {
      delimiter = "\t";
    } else if (firstLine.indexOf(";") >= 0) {
      delimiter = ";";
    } else if (firstLine.indexOf(",") >= 0) {
      delimiter = ",";
    }

    const parsedLines = E.parseDelimitedText(raw, delimiter);
    if (parsedLines.length === 0) return { columns: [], rows: [] };

    const maxCols = Math.max.apply(null, parsedLines.map(function (r) { return r.length; }));
    const normalizedRows = parsedLines.map(function (r) {
      const copy = r.slice();
      while (copy.length < maxCols) copy.push("");
      return copy;
    });

    let columns = [];
    let rows = [];

    if (hasHeader && normalizedRows.length > 0) {
      const headerRow = normalizedRows[0];
      columns = headerRow.map(function (h, i) { return h ? h : "Spalte " + (i + 1); });
      rows = normalizedRows.slice(1);
    } else {
      for (let i = 0; i < maxCols; i++) {
        columns.push("Spalte " + (i + 1));
      }
      rows = normalizedRows;
    }

    return { columns: columns, rows: rows };
  }

  function detectSuggestedChartType(columns, rows) {
    if (!columns || columns.length === 0 || !rows || rows.length === 0) return "category_bar";

    const sample = rows.slice(0, 10).map(function (r) { return r[0] || ""; });
    const dateRegex = /^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}[-/]?[Qq][1-4]|\d{4})$/;
    let dateMatches = 0;
    sample.forEach(function (v) {
      if (dateRegex.test(v.trim())) dateMatches++;
    });

    if (sample.length > 0 && dateMatches / sample.length >= 0.6) {
      return "timeseries";
    }

    if (columns.length === 2) {
      let sum = 0;
      let count = 0;
      rows.forEach(function (r) {
        const val = parseFloat((r[1] || "").replace(/['\s%]/g, "").replace(",", "."));
        if (!isNaN(val)) {
          sum += val;
          count++;
        }
      });
      if (count >= 2 && sum >= 85 && sum <= 115) {
        return "doughnut";
      }
    }

    return "category_bar";
  }

  function requestCustomChartPreview(blk, immediate) {
    if (!blk || !blk.id || blk.type !== "custom_chart") return;
    if (state.customChartTimers && state.customChartTimers[blk.id]) {
      clearTimeout(state.customChartTimers[blk.id]);
      delete state.customChartTimers[blk.id];
    }
    const sendReq = function () {
      if (window.Shiny && window.Shiny.setInputValue) {
        window.Shiny.setInputValue(
          "lukb_preview_custom_chart",
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
      if (!state.customChartTimers) state.customChartTimers = {};
      state.customChartTimers[blk.id] = setTimeout(sendReq, 220);
    }
  }

  function syncDataFromRawTsv(blk, autoDetectType) {
    const hasHeader = blk.has_header !== false;
    const res = parseClientTsv(blk.raw_tsv, hasHeader);
    blk.data_columns = res.columns;
    blk.data_rows = res.rows;

    if (!blk.x_col || res.columns.indexOf(blk.x_col) === -1) {
      blk.x_col = res.columns.length > 0 ? res.columns[0] : "";
    }

    if (autoDetectType && res.columns.length > 0 && res.rows.length > 0) {
      blk.chart_type = detectSuggestedChartType(res.columns, res.rows);
    }

    // Serien-Konfiguration aktualisieren
    const existingSeriesMap = {};
    if (Array.isArray(blk.series)) {
      blk.series.forEach(function (s) {
        if (s && s.field) existingSeriesMap[s.field] = s;
      });
    }

    const newSeries = [];
    res.columns.forEach(function (col) {
      if (col === blk.x_col) return;
      if (existingSeriesMap[col]) {
        newSeries.push(existingSeriesMap[col]);
      } else {
        newSeries.push({
          field: col,
          label: col,
          chart_type: blk.chart_type === "timeseries" ? "line" : "bar",
          enabled: true,
        });
      }
    });
    blk.series = newSeries;
  }

  function buildCustomChartBlockBody(container, blk) {
    if (!blk.chart_type) blk.chart_type = "category_bar";
    if (blk.has_header === undefined) blk.has_header = true;
    if (!blk.chart_height_mm) blk.chart_height_mm = 36;
    if (!blk.palette) blk.palette = "lukb_classic";
    if (!blk.bar_mode) blk.bar_mode = "grouped";
    if (blk.doughnut_hole_pct === undefined || blk.doughnut_hole_pct === null) blk.doughnut_hole_pct = 55;
    if (!blk.orientation) blk.orientation = "vertical";
    if (blk.color_by_category === undefined) blk.color_by_category = false;
    if (!blk.legend_position) blk.legend_position = "bottom";
    if (blk.legend_columns === undefined) blk.legend_columns = null;
    if (blk.show_legend === undefined) blk.show_legend = true;

    // Sicherstellen, dass data_columns & data_rows initial synchronisiert sind
    if (!blk.data_columns || blk.data_columns.length === 0) {
      syncDataFromRawTsv(blk, false);
    }

    // Zeile 1: Grafik-Titel & Layout-Breite (inkl. Randverankerung)
    const topGrid = document.createElement("div");
    topGrid.style.display = "grid";
    topGrid.style.gridTemplateColumns = "1fr auto";
    topGrid.style.gap = "10px";
    topGrid.style.marginBottom = "10px";

    const titleWrap = document.createElement("div");
    titleWrap.className = "field-group";
    const titleLbl = document.createElement("label");
    titleLbl.className = "field-label";
    titleLbl.textContent = "Grafik-Titel (Corporate Sans Medium)";
    const titleInp = document.createElement("input");
    titleInp.type = "text";
    titleInp.className = "cms-input";
    titleInp.placeholder = "z.B. Asset Allocation oder Marktentwicklung";
    titleInp.value = blk.title || "";
    titleInp.addEventListener("input", function () {
      blk.title = titleInp.value;
      markDirty();
    });
    titleWrap.appendChild(titleLbl);
    titleWrap.appendChild(titleInp);

    const fullCtrl = createFullLayoutControl(blk, function () {
      markDirty();
      requestCustomChartPreview(blk, true);
    });

    topGrid.appendChild(titleWrap);
    topGrid.appendChild(fullCtrl);
    container.appendChild(topGrid);

    // Zeile 2: Grafik-Untertitel
    const subWrap = document.createElement("div");
    subWrap.className = "field-group";
    subWrap.style.marginBottom = "12px";
    const subLbl = document.createElement("label");
    subLbl.className = "field-label";
    subLbl.textContent = "Grafik-Untertitel (z.B. Einheit, Zeitraum)";
    const subInp = document.createElement("input");
    subInp.type = "text";
    subInp.className = "cms-input";
    subInp.placeholder = "z.B. Anteile in Prozent oder Indexiert (Start = 100)";
    subInp.value = blk.subtitle || "";
    subInp.addEventListener("input", function () {
      blk.subtitle = subInp.value;
      markDirty();
    });
    subWrap.appendChild(subLbl);
    subWrap.appendChild(subInp);
    container.appendChild(subWrap);

    // =========================================================================
    // Card: Daten aus Zwischenablage / Excel einfügen
    // =========================================================================
    const dataCard = document.createElement("div");
    dataCard.style.background = "#F8FAFC";
    dataCard.style.border = "1px solid #CBD5E1";
    dataCard.style.borderRadius = "6px";
    dataCard.style.padding = "12px";
    dataCard.style.marginBottom = "14px";

    const dataHeader = document.createElement("div");
    dataHeader.style.display = "flex";
    dataHeader.style.justifyContent = "space-between";
    dataHeader.style.alignItems = "center";
    dataHeader.style.marginBottom = "8px";

    const dataTitle = document.createElement("span");
    dataTitle.style.fontWeight = "600";
    dataTitle.style.fontSize = "13px";
    dataTitle.style.color = "#002855";
    dataTitle.innerHTML = "📋 Tabellendaten aus Zwischenablage (Wide-Format / Excel)";

    const pasteBtn = document.createElement("button");
    pasteBtn.type = "button";
    pasteBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    pasteBtn.innerHTML = "📋 Aus Clipboard einfügen";
    pasteBtn.title = "Daten direkt aus der System-Zwischenablage einlesen";
    pasteBtn.addEventListener("click", function () {
      if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText().then(function (clipText) {
          if (clipText && clipText.trim()) {
            tsvArea.value = clipText;
            blk.raw_tsv = clipText;
            syncDataFromRawTsv(blk, true);
            rebuildConfigSection();
            markDirty();
            requestCustomChartPreview(blk, true);
          }
        }).catch(function (err) {
          alert("Zwischenablage konnte nicht automatisch gelesen werden. Bitte Text mit Ctrl+V in das Textfeld einfügen.");
        });
      } else {
        alert("Bitte Text direkt mit Ctrl+V in das Textfeld einfügen.");
      }
    });

    dataHeader.appendChild(dataTitle);
    dataHeader.appendChild(pasteBtn);
    dataCard.appendChild(dataHeader);

    // Textarea für Rohdaten
    const tsvArea = document.createElement("textarea");
    tsvArea.className = "cms-input";
    tsvArea.rows = 4;
    tsvArea.style.fontFamily = "Consolas, Menlo, Monaco, monospace";
    tsvArea.style.fontSize = "12px";
    tsvArea.style.whiteSpace = "pre";
    tsvArea.style.lineHeight = "1.4";
    tsvArea.placeholder = "Kopieren Sie hier Tabellenzellen aus Microsoft Excel, CSV oder TSV hinein (Ctrl+V)...";
    tsvArea.value = blk.raw_tsv || "";

    tsvArea.addEventListener("change", function () {
      blk.raw_tsv = tsvArea.value;
      syncDataFromRawTsv(blk, true);
      rebuildConfigSection();
      markDirty();
      requestCustomChartPreview(blk, true);
    });

    // Paste-Event direkt im Textarea
    tsvArea.addEventListener("paste", function (e) {
      setTimeout(function () {
        blk.raw_tsv = tsvArea.value;
        syncDataFromRawTsv(blk, true);
        rebuildConfigSection();
        markDirty();
        requestCustomChartPreview(blk, true);
      }, 30);
    });

    dataCard.appendChild(tsvArea);

    // Optionen unter der Textarea: Kopfzeilen-Checkbox & Parse-Button
    const dataOpts = document.createElement("div");
    dataOpts.style.display = "flex";
    dataOpts.style.justifyContent = "space-between";
    dataOpts.style.alignItems = "center";
    dataOpts.style.marginTop = "6px";

    const headerLabel = document.createElement("label");
    headerLabel.style.display = "inline-flex";
    headerLabel.style.alignItems = "center";
    headerLabel.style.gap = "6px";
    headerLabel.style.fontSize = "12px";
    headerLabel.style.color = "#334155";
    headerLabel.style.cursor = "pointer";

    const headerChk = document.createElement("input");
    headerChk.type = "checkbox";
    headerChk.checked = blk.has_header !== false;
    headerChk.addEventListener("change", function () {
      blk.has_header = headerChk.checked;
      syncDataFromRawTsv(blk, false);
      rebuildConfigSection();
      markDirty();
      requestCustomChartPreview(blk, true);
    });
    headerLabel.appendChild(headerChk);
    headerLabel.appendChild(document.createTextNode("Erste Zeile als Spaltenüberschriften interpretieren"));

    const parseBtn = document.createElement("button");
    parseBtn.type = "button";
    parseBtn.className = "btn-lukb btn-lukb-sm";
    parseBtn.textContent = "⚡ Daten analysieren";
    parseBtn.addEventListener("click", function () {
      blk.raw_tsv = tsvArea.value;
      syncDataFromRawTsv(blk, true);
      rebuildConfigSection();
      markDirty();
      requestCustomChartPreview(blk, true);
    });

    dataOpts.appendChild(headerLabel);
    dataOpts.appendChild(parseBtn);
    dataCard.appendChild(dataOpts);

    container.appendChild(dataCard);

    // =========================================================================
    // Card: Diagrammtyp & Spalten-Mapping
    // =========================================================================
    const configContainer = document.createElement("div");
    container.appendChild(configContainer);

    function rebuildConfigSection() {
      configContainer.innerHTML = "";

      const cols = blk.data_columns || [];
      const rows = blk.data_rows || [];

      // Status-Hinweis
      const statusBanner = document.createElement("div");
      statusBanner.style.display = "flex";
      statusBanner.style.justifyContent = "space-between";
      statusBanner.style.alignItems = "center";
      statusBanner.style.background = cols.length > 0 ? "#F0FDF4" : "#FEF2F2";
      statusBanner.style.border = "1px solid " + (cols.length > 0 ? "#BBF7D0" : "#FECACA");
      statusBanner.style.borderRadius = "4px";
      statusBanner.style.padding = "6px 10px";
      statusBanner.style.marginBottom = "10px";
      statusBanner.style.fontSize = "12px";

      if (cols.length > 0) {
        statusBanner.innerHTML =
          '<span style="color:#166534;font-weight:600;">✓ ' +
          cols.length +
          " Spalten erkannt (" +
          rows.length +
          " Datenzeilen)</span>" +
          '<span style="color:#475569;">Typ: <strong>' +
          (blk.chart_type === "doughnut" || blk.chart_type === "pie"
            ? (blk.doughnut_hole_pct === 0 ? "Kuchendiagramm (Pie)" : "Ringdiagramm (Doughnut)")
            : blk.chart_type === "timeseries" ? "Zeitreihen-Diagramm" : "Kategorie-Säulen") +
          "</strong></span>";
      } else {
        statusBanner.innerHTML =
          '<span style="color:#991B1B;">⚠️ Keine Daten erkannt. Fügen Sie oben Tabellendaten ein.</span>';
      }
      configContainer.appendChild(statusBanner);

      if (cols.length === 0) return;

      // 1. Diagrammtyp-Auswahl
      const typeRow = document.createElement("div");
      typeRow.style.marginBottom = "12px";
      const typeLbl = document.createElement("label");
      typeLbl.className = "field-label";
      typeLbl.textContent = "1. Gewünschter Diagrammtyp";
      typeRow.appendChild(typeLbl);

      const typeBtnsWrap = document.createElement("div");
      typeBtnsWrap.style.display = "flex";
      typeBtnsWrap.style.gap = "8px";
      typeBtnsWrap.style.flexWrap = "wrap";

      const chartTypeOptions = [
        { id: "category_bar", label: "📊 Kategorie-Säulen", desc: "Säulendiagramm nach Branchen, Regionen etc." },
        { id: "pie", label: "🍩 / 🥧 Kreis- & Ringdiagramm", desc: "Kuchen- oder Ringdiagramm für Anteile / Asset Allocation (Lochgrösse 0-80%)" },
        { id: "timeseries", label: "📈 Zeitreihen-Diagramm", desc: "Verlauf über Datumsachse (X = Datum)" },
      ];

      chartTypeOptions.forEach(function (opt) {
        const isSelected =
          blk.chart_type === opt.id ||
          (opt.id === "pie" && (blk.chart_type === "pie" || blk.chart_type === "doughnut"));

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className =
          "btn-lukb btn-lukb-ghost btn-lukb-sm custom-chart-type-btn" +
          (isSelected ? " active" : "");
        btn.style.padding = "6px 12px";
        btn.style.fontSize = "12px";
        btn.textContent = opt.label;
        btn.title = opt.desc;

        btn.classList.toggle("active", isSelected);

        btn.addEventListener("click", function () {
          blk.chart_type = opt.id;
          rebuildConfigSection();
          markDirty();
          requestCustomChartPreview(blk, true);
          if (typeof flushAutosave === "function") {
            flushAutosave(false);
          }
        });

        typeBtnsWrap.appendChild(btn);
      });

      typeRow.appendChild(typeBtnsWrap);
      configContainer.appendChild(typeRow);

      // Farbpaletten-Steuerung (LUKB Standard vs. Blau-Abstufung via .db-chart-palette-bar / .db-palette-preset-btn)
      const paletteCtrl = E.createChartPaletteBar(blk, CUSTOM_CHART_PALETTES, function () {
        if (typeof updateSeriesColorDots === "function") {
          updateSeriesColorDots();
        }
        markDirty();
        requestCustomChartPreview(blk, true);
      });
      configContainer.appendChild(paletteCtrl.element);

      // 2. Spalten-Mapping & Diagramm-Optionen
      let updateLegColsOptions = null;
      let updateSeriesColorDots = null;
      const mapGrid = document.createElement("div");
      mapGrid.style.display = "grid";
      mapGrid.style.gridTemplateColumns = "repeat(auto-fit, minmax(200px, 1fr))";
      mapGrid.style.gap = "12px";
      mapGrid.style.marginBottom = "14px";
      mapGrid.style.background = "#F8FAFC";
      mapGrid.style.border = "1px solid #E2E8F0";
      mapGrid.style.borderRadius = "6px";
      mapGrid.style.padding = "10px";

      // Feld 1: X-Achse / Kategorie / Datum
      const xWrap = document.createElement("div");
      const xLbl = document.createElement("label");
      xLbl.className = "field-label";
      xLbl.textContent =
        blk.chart_type === "timeseries"
          ? "2. Datums-Spalte (X-Achse)"
          : "2. Kategorie-Spalte (Labels)";
      const xSel = document.createElement("select");
      xSel.className = "cms-select";
      cols.forEach(function (c) {
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        if (c === blk.x_col) opt.selected = true;
        xSel.appendChild(opt);
      });
      xSel.addEventListener("change", function () {
        blk.x_col = xSel.value;
        syncDataFromRawTsv(blk, false);
        rebuildConfigSection();
        markDirty();
        requestCustomChartPreview(blk, true);
      });
      xWrap.appendChild(xLbl);
      xWrap.appendChild(xSel);
      mapGrid.appendChild(xWrap);

      // Optionen für Kategorie-Charts (Säulen & Balken)
      if (blk.chart_type === "category_bar") {
        // Ausrichtung: Vertikal (Säulen) vs Horizontal (Balken)
        const orientWrap = document.createElement("div");
        const orientLbl = document.createElement("label");
        orientLbl.className = "field-label";
        orientLbl.textContent = "Ausrichtung";
        const orientSel = document.createElement("select");
        orientSel.className = "cms-select";
        orientSel.innerHTML =
          '<option value="vertical">📊 Vertikale Säulen (unten nach oben)</option>' +
          '<option value="horizontal">📋 Horizontale Balken (links nach rechts)</option>';
        orientSel.value = blk.orientation || "vertical";
        orientSel.addEventListener("change", function () {
          blk.orientation = orientSel.value;
          rebuildConfigSection();
          markDirty();
          requestCustomChartPreview(blk, true);
        });
        orientWrap.appendChild(orientLbl);
        orientWrap.appendChild(orientSel);
        mapGrid.appendChild(orientWrap);

        // Farb-Modus: Bunt pro Kategorie vs Einheitlich pro Serie
        const colorModeWrap = document.createElement("div");
        const colorModeLbl = document.createElement("label");
        colorModeLbl.className = "field-label";
        colorModeLbl.textContent = "Balkenfarben";
        const colorModeSel = document.createElement("select");
        colorModeSel.className = "cms-select";
        colorModeSel.innerHTML =
          '<option value="single">🎨 Einheitlich (eine Farbe pro Serie)</option>' +
          '<option value="category">🌈 Bunt (unterschiedliche Farbe pro Kategorie)</option>';
        colorModeSel.value = blk.color_by_category ? "category" : "single";
        colorModeSel.addEventListener("change", function () {
          blk.color_by_category = colorModeSel.value === "category";
          markDirty();
          requestCustomChartPreview(blk, true);
        });
        colorModeWrap.appendChild(colorModeLbl);
        colorModeWrap.appendChild(colorModeSel);
        mapGrid.appendChild(colorModeWrap);

        // Säulen-Modus (nur relevant bei vertikalen Säulen)
        if (blk.orientation !== "horizontal") {
          const barWrap = document.createElement("div");
          const barLbl = document.createElement("label");
          barLbl.className = "field-label";
          barLbl.textContent = "Säulen-Modus";
          const barSel = document.createElement("select");
          barSel.className = "cms-select";
          barSel.innerHTML =
            '<option value="grouped">Gruppierte Säulen (nebeneinander)</option>' +
            '<option value="stacked">Gestapelte Säulen (aufeinander)</option>';
          barSel.value = blk.bar_mode || "grouped";
          barSel.addEventListener("change", function () {
            blk.bar_mode = barSel.value;
            markDirty();
            requestCustomChartPreview(blk, true);
          });
          barWrap.appendChild(barLbl);
          barWrap.appendChild(barSel);
          mapGrid.appendChild(barWrap);
        }
      }

      // Optionen für Kreis- & Ringdiagramm (Doughnut & Pie kombiniert)
      if (blk.chart_type === "doughnut" || blk.chart_type === "pie") {
        // Legende-Position (Unten vs Rechts)
        const legWrap = document.createElement("div");
        const legLbl = document.createElement("label");
        legLbl.className = "field-label";
        legLbl.textContent = "Position der Legende";
        const legSel = document.createElement("select");
        legSel.className = "cms-select";
        legSel.innerHTML =
          '<option value="bottom">Unterhalb der Grafik</option>' +
          '<option value="right">Rechts neben der Grafik</option>';
        legSel.value = blk.legend_position || "bottom";
        legSel.addEventListener("change", function () {
          blk.legend_position = legSel.value;
          if (typeof updateLegColsOptions === "function") {
            updateLegColsOptions();
          }
          markDirty();
          requestCustomChartPreview(blk, true);
          if (typeof flushAutosave === "function") {
            flushAutosave(false);
          }
        });
        legWrap.appendChild(legLbl);
        legWrap.appendChild(legSel);
        mapGrid.appendChild(legWrap);

        // Lochgrösse-Regler (0% = Klassischer Kuchen, >0% = Ringdiagramm)
        const curHole =
          blk.doughnut_hole_pct !== undefined
            ? blk.doughnut_hole_pct
            : (blk.chart_type === "pie" ? 0 : 55);
        blk.doughnut_hole_pct = curHole;

        const holeWrap = document.createElement("div");
        const holeLbl = document.createElement("label");
        holeLbl.className = "field-label";

        const updateHoleLabel = function (val) {
          if (val === 0) {
            holeLbl.innerHTML = "Lochgrösse: <strong>0 % (Kuchendiagramm / Pie)</strong>";
          } else {
            holeLbl.innerHTML = "Lochgrösse: <strong>" + val + " % (Ringdiagramm / Doughnut)</strong>";
          }
        };
        updateHoleLabel(curHole);

        const holeSlider = document.createElement("input");
        holeSlider.type = "range";
        holeSlider.min = "0";
        holeSlider.max = "80";
        holeSlider.step = "5";
        holeSlider.value = curHole;
        holeSlider.style.width = "100%";
        holeSlider.addEventListener("input", function () {
          const val = parseInt(holeSlider.value, 10);
          blk.doughnut_hole_pct = val;
          updateHoleLabel(val);
          markDirty();
          requestCustomChartPreview(blk, false);
        });

        // Schnellwahltasten: Kuchen (0%) vs Ring (55%)
        const holePresetRow = document.createElement("div");
        holePresetRow.style.display = "flex";
        holePresetRow.style.gap = "6px";
        holePresetRow.style.marginTop = "4px";

        const piePresetBtn = document.createElement("button");
        piePresetBtn.type = "button";
        piePresetBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        piePresetBtn.style.padding = "2px 8px";
        piePresetBtn.style.fontSize = "11px";
        piePresetBtn.textContent = "🥧 Kuchen (0%)";
        piePresetBtn.title = "Klassisches Kuchendiagramm ohne Loch";
        piePresetBtn.addEventListener("click", function () {
          blk.doughnut_hole_pct = 0;
          holeSlider.value = 0;
          updateHoleLabel(0);
          markDirty();
          requestCustomChartPreview(blk, true);
          if (typeof flushAutosave === "function") flushAutosave(false);
        });

        const ringPresetBtn = document.createElement("button");
        ringPresetBtn.type = "button";
        ringPresetBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        ringPresetBtn.style.padding = "2px 8px";
        ringPresetBtn.style.fontSize = "11px";
        ringPresetBtn.textContent = "🍩 Ring (55%)";
        ringPresetBtn.title = "Ringdiagramm mit modernem Loch";
        ringPresetBtn.addEventListener("click", function () {
          blk.doughnut_hole_pct = 55;
          holeSlider.value = 55;
          updateHoleLabel(55);
          markDirty();
          requestCustomChartPreview(blk, true);
          if (typeof flushAutosave === "function") flushAutosave(false);
        });

        holePresetRow.appendChild(piePresetBtn);
        holePresetRow.appendChild(ringPresetBtn);

        holeWrap.appendChild(holeLbl);
        holeWrap.appendChild(holeSlider);
        holeWrap.appendChild(holePresetRow);
        mapGrid.appendChild(holeWrap);
      }

      // Legende / Spalten der Legende (für alle Diagrammtypen)
      const legColsWrap = document.createElement("div");
      const legColsLbl = document.createElement("label");
      legColsLbl.className = "field-label";
      legColsLbl.textContent = "Legende";
      const legColsSel = document.createElement("select");
      legColsSel.className = "cms-select";

      updateLegColsOptions = function () {
        const isRight = (blk.chart_type === "doughnut" || blk.chart_type === "pie") && blk.legend_position === "right";
        const autoLabel = isRight ? "Automatisch (1 Spalte)" : "Automatisch (kompakt)";
        const curVal =
          blk.show_legend === false
            ? "none"
            : blk.legend_columns !== undefined && blk.legend_columns !== null
              ? String(blk.legend_columns)
              : "auto";
        legColsSel.innerHTML =
          '<option value="auto">' + autoLabel + '</option>' +
          '<option value="1">1 Spalte</option>' +
          '<option value="2">2 Spalten</option>' +
          '<option value="3">3 Spalten</option>' +
          '<option value="4">4 Spalten</option>' +
          '<option value="none">Keine Legende</option>';
        legColsSel.value = curVal;
      };
      updateLegColsOptions();

      legColsSel.addEventListener("change", function () {
        if (legColsSel.value === "none") {
          blk.show_legend = false;
        } else {
          blk.show_legend = true;
          blk.legend_columns = legColsSel.value === "auto" ? null : parseInt(legColsSel.value, 10);
        }
        markDirty();
        requestCustomChartPreview(blk, true);
        if (typeof flushAutosave === "function") {
          flushAutosave(false);
        }
      });
      legColsWrap.appendChild(legColsLbl);
      legColsWrap.appendChild(legColsSel);
      mapGrid.appendChild(legColsWrap);

      configContainer.appendChild(mapGrid);

      // 3. Wert-Spalten & Serien-Labels konfigurieren
      const seriesCard = document.createElement("div");
      seriesCard.style.border = "1px solid #E2E8F0";
      seriesCard.style.borderRadius = "6px";
      seriesCard.style.padding = "10px";
      seriesCard.style.marginBottom = "12px";
      seriesCard.style.background = "#FFFFFF";

      const seriesCardTitle = document.createElement("div");
      seriesCardTitle.style.fontWeight = "600";
      seriesCardTitle.style.fontSize = "12.5px";
      seriesCardTitle.style.color = "#002855";
      seriesCardTitle.style.marginBottom = "8px";
      seriesCardTitle.textContent = "3. Wert-Spalten auswählen & Datenreihen separat benennen";
      seriesCard.appendChild(seriesCardTitle);

      const seriesList = blk.series || [];
      const seriesColorDots = [];
      const getActivePaletteColors = paletteCtrl.getActiveColors;
      updateSeriesColorDots = function () {
        const activeColors = getActivePaletteColors();
        seriesColorDots.forEach(function (item) {
          item.dot.style.backgroundColor = activeColors[item.idx % activeColors.length];
        });
      };

      if (seriesList.length === 0) {
        const noValMsg = document.createElement("div");
        noValMsg.style.fontSize = "12px";
        noValMsg.style.color = "#64748B";
        noValMsg.textContent = "Keine Wert-Spalten vorhanden. Fügen Sie Daten mit mehreren Spalten ein.";
        seriesCard.appendChild(noValMsg);
      } else {
        seriesList.forEach(function (s, sIdx) {
          const rowEl = document.createElement("div");
          rowEl.style.display = "flex";
          rowEl.style.alignItems = "center";
          rowEl.style.gap = "8px";
          rowEl.style.marginBottom = "6px";
          rowEl.style.padding = "4px 8px";
          rowEl.style.background = s.enabled ? "#F8FAFC" : "#F1F5F9";
          rowEl.style.borderRadius = "4px";

          // Aktiv-Checkbox
          const chk = document.createElement("input");
          chk.type = "checkbox";
          chk.checked = s.enabled !== false;
          chk.title = "Diese Spalte als Datenreihe im Diagramm anzeigen";
          chk.addEventListener("change", function () {
            s.enabled = chk.checked;
            rowEl.style.background = s.enabled ? "#F8FAFC" : "#F1F5F9";
            markDirty();
            requestCustomChartPreview(blk, true);
          });
          rowEl.appendChild(chk);

          // Farbpunkt aus gewählter Palette
          const activeColors = getActivePaletteColors();
          const colorDot = document.createElement("span");
          colorDot.className = "db-series-color-dot";
          colorDot.style.backgroundColor = activeColors[sIdx % activeColors.length];
          colorDot.title = "Farbe der Datenreihe " + (sIdx + 1) + " (aus gewählter Palette)";
          seriesColorDots.push({ dot: colorDot, idx: sIdx });
          rowEl.appendChild(colorDot);

          // Original Spaltenname Badge
          const badge = document.createElement("span");
          badge.style.fontSize = "11.5px";
          badge.style.fontWeight = "600";
          badge.style.color = "#475569";
          badge.style.background = "#E2E8F0";
          badge.style.padding = "2px 6px";
          badge.style.borderRadius = "3px";
          badge.style.minWidth = "85px";
          badge.style.maxWidth = "130px";
          badge.style.overflow = "hidden";
          badge.style.textOverflow = "ellipsis";
          badge.style.whiteSpace = "nowrap";
          badge.textContent = s.field;
          badge.title = "Originale Tabellenspalte: " + s.field;
          rowEl.appendChild(badge);

          // Benutzerdefiniertes Serien-Label (User-Anforderung!)
          const labelInp = document.createElement("input");
          labelInp.type = "text";
          labelInp.className = "cms-input";
          labelInp.style.flex = "1";
          labelInp.style.height = "28px";
          labelInp.style.fontSize = "12px";
          labelInp.placeholder = "Label für die Legende (z.B. " + s.field + ")";
          labelInp.value = s.label || s.field;
          labelInp.addEventListener("input", function () {
            s.label = labelInp.value;
            markDirty();
            requestCustomChartPreview(blk, false);
          });
          rowEl.appendChild(labelInp);

          // Bei Zeitreihen: Darstellungsart wählbar (Linie, Stufen, Balken, Fläche, Punkte)
          if (blk.chart_type === "timeseries") {
            const styleSel = document.createElement("select");
            styleSel.className = "cms-select";
            styleSel.style.width = "110px";
            styleSel.style.height = "28px";
            styleSel.style.fontSize = "11.5px";
            styleSel.innerHTML =
              '<option value="line">Linie</option>' +
              '<option value="area">Fläche</option>' +
              '<option value="step">Stufe</option>' +
              '<option value="bar">Säule</option>' +
              '<option value="dot">Punkte</option>';
            styleSel.value = s.chart_type || "line";
            styleSel.addEventListener("change", function () {
              s.chart_type = styleSel.value;
              markDirty();
              requestCustomChartPreview(blk, true);
            });
            rowEl.appendChild(styleSel);
          }

          seriesCard.appendChild(rowEl);
        });
      }
      configContainer.appendChild(seriesCard);
    }

    rebuildConfigSection();

    // =========================================================================
    // Chartfläche-Höhe (identisch zu DB-Charts: 28, 36, 46, 56 mm)
    // =========================================================================
    const heightBar = E.createChartHeightBar(blk, null, function () {
      markDirty();
      requestCustomChartPreview(blk, true);
      if (typeof flushAutosave === "function") {
        flushAutosave(false);
      }
    });
    container.appendChild(heightBar);

    // =========================================================================
    // Live-SVG-Vorschau
    // =========================================================================
    const previewBox = document.createElement("div");
    previewBox.style.border = "1px solid #CBD5E1";
    previewBox.style.borderRadius = "4px";
    previewBox.style.padding = "8px";
    previewBox.style.background = "#FFFFFF";
    previewBox.style.marginBottom = "12px";

    const previewImg = document.createElement("img");
    previewImg.id = "custom-chart-preview-img-" + blk.id;
    previewImg.style.width = "100%";
    previewImg.style.height = "auto";
    previewImg.style.display = "block";
    previewImg.style.minHeight = "90px";
    previewImg.alt = "Vorschau des benutzerdefinierten Diagramms";

    if (state.assetCache && state.assetCache[blk.id]) {
      previewImg.src = state.assetCache[blk.id];
    } else {
      requestCustomChartPreview(blk, true);
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
    hintSpan.textContent = "LUKB Vektor-SVG (Druck- und Web-konform)";

    const refreshBtn = document.createElement("button");
    refreshBtn.type = "button";
    refreshBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
    refreshBtn.textContent = "↻ Grafik neu berechnen";
    refreshBtn.addEventListener("click", function () {
      requestCustomChartPreview(blk, true);
      markDirty();
    });

    previewFooter.appendChild(hintSpan);
    previewFooter.appendChild(refreshBtn);
    previewBox.appendChild(previewFooter);
    container.appendChild(previewBox);

    // =========================================================================
    // Zeile: Quellenangabe
    // =========================================================================
    const srcWrap = document.createElement("div");
    const srcLbl = document.createElement("label");
    srcLbl.className = "field-label";
    srcLbl.textContent = "Quellenangabe / Fussnote unter der Grafik";
    const srcInp = document.createElement("input");
    srcInp.type = "text";
    srcInp.className = "cms-input";
    srcInp.placeholder = "Quelle: LUKB Investment Office";
    srcInp.value = blk.source || "";
    srcInp.addEventListener("input", function () {
      blk.source = srcInp.value;
      markDirty();
    });
    srcWrap.appendChild(srcLbl);
    srcWrap.appendChild(srcInp);
    container.appendChild(srcWrap);
  }

  // Exportieren an LUKBEditor
  Object.assign(E, {
    buildCustomChartBlockBody: buildCustomChartBlockBody,
    requestCustomChartPreview: requestCustomChartPreview,
    parseClientTsv: parseClientTsv,
    detectSuggestedChartType: detectSuggestedChartType,
    CUSTOM_CHART_PALETTES: CUSTOM_CHART_PALETTES,
  });
})();
