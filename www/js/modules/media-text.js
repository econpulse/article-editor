/**
 * LUKB Editor Modul: Kombinierter Media- & Text-Block (Bild / Chart / Tabelle + Text + optionale 3. Spalte)
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function createDefaultBlock() { return E.createDefaultBlock.apply(this, arguments); }
  function createFullLayoutControl() { return E.createFullLayoutControl.apply(this, arguments); }
  function markDirty() { return E.markDirty.apply(this, arguments); }

  const mediaDraftsStore = new WeakMap();

  function createSubMediaDefault(mtype) {
    const sub = createDefaultBlock(mtype);
    sub.layout = "column";
    sub.full_position = "auto";
    if (mtype === "figure") {
      sub.title = "";
      sub.subtitle = "";
      sub.source = "";
    }
    return sub;
  }

  function hideNestedLayoutControl(subContainer) {
    const labels = subContainer.querySelectorAll("label.field-label");
    labels.forEach(function (lbl) {
      if ((lbl.textContent || "").indexOf("Satz-Breite im PDF") !== -1) {
        const col = lbl.parentElement;
        if (col) {
          col.style.display = "none";
          const gridParent = col.parentElement;
          if (gridParent && gridParent.style && gridParent.style.gridTemplateColumns) {
            gridParent.style.gridTemplateColumns = "1fr";
          }
        }
      }
    });
  }

  function buildMediaTextBlockBody(container, blk) {
    if (!blk.media_type) blk.media_type = "figure";
    if (!blk.media_position) blk.media_position = "auto";
    if (!blk.media_width_pct) blk.media_width_pct = 30;
    if (!blk.aside_width_pct) blk.aside_width_pct = 26;
    if (!blk.style_preset) blk.style_preset = "plain";
    if (!blk.media || typeof blk.media !== "object") {
      blk.media = createSubMediaDefault(blk.media_type);
    }
    blk.media.type = blk.media_type;
    blk.media.layout = "column";

    let mediaDrafts = mediaDraftsStore.get(blk);
    if (!mediaDrafts) {
      mediaDrafts = {};
      mediaDraftsStore.set(blk, mediaDrafts);
    }
    mediaDrafts[blk.media_type] = blk.media;

    // Zeile 1: Optionaler Block-Titel & Satz-Breite im PDF
    const topGrid = document.createElement("div");
    topGrid.style.display = "grid";
    topGrid.style.gridTemplateColumns = "1fr 190px";
    topGrid.style.gap = "10px";
    topGrid.style.marginBottom = "10px";

    const titleWrap = document.createElement("div");
    const titleLbl = document.createElement("label");
    titleLbl.className = "field-label";
    titleLbl.textContent = "Optionaler Block-Titel (leer lassen für nahtlose Karten/Zebra-Listen)";
    const titleInp = document.createElement("input");
    titleInp.type = "text";
    titleInp.className = "cms-input font-medium";
    titleInp.placeholder = "z. B. Zentralbanken im Überblick oder Sales-Idee …";
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

    // Zeile 2: Steuerleiste (Medium-Typ, Position, Medien-Breite, Stil-Preset)
    const configGrid = document.createElement("div");
    configGrid.style.display = "grid";
    configGrid.style.gridTemplateColumns = "repeat(auto-fit, minmax(145px, 1fr))";
    configGrid.style.gap = "8px";
    configGrid.style.padding = "8px 10px";
    configGrid.style.background = "#F8FAFC";
    configGrid.style.border = "1px solid #E2E8F0";
    configGrid.style.borderRadius = "4px";
    configGrid.style.marginBottom = "10px";

    function makeSelectField(labelText, options, currentVal, onChange) {
      const wrap = document.createElement("div");
      const lbl = document.createElement("label");
      lbl.className = "field-label";
      lbl.style.fontSize = "11px";
      lbl.textContent = labelText;
      const sel = document.createElement("select");
      sel.className = "cms-select";
      sel.style.fontSize = "12px";
      sel.style.padding = "4px 7px";
      options.forEach(function (o) {
        const opt = document.createElement("option");
        opt.value = String(o.val);
        opt.textContent = o.label;
        if (String(currentVal) === String(o.val)) opt.selected = true;
        sel.appendChild(opt);
      });
      sel.addEventListener("change", function () {
        onChange(sel.value);
        markDirty();
      });
      wrap.appendChild(lbl);
      wrap.appendChild(sel);
      return { wrap: wrap, sel: sel };
    }

    const mediaEditorBox = document.createElement("div");
    mediaEditorBox.style.border = "1px solid #D6DEE8";
    mediaEditorBox.style.borderRadius = "4px";
    mediaEditorBox.style.padding = "10px";
    mediaEditorBox.style.background = "#FFFFFF";
    mediaEditorBox.style.marginBottom = "10px";

    function renderSubMediaEditor() {
      mediaEditorBox.innerHTML = "";
      const subHeader = document.createElement("div");
      subHeader.style.fontSize = "11.5px";
      subHeader.style.fontWeight = "600";
      subHeader.style.color = "#002855";
      subHeader.style.marginBottom = "8px";
      subHeader.textContent =
        blk.media_type === "table"
          ? "Eingebettete Tabelle"
          : blk.media_type === "db_chart"
          ? "Eingebetteter DB-Chart (Zeitreihe)"
          : blk.media_type === "custom_chart"
          ? "Eingebettetes Daten-Diagramm"
          : "Eingebettete Grafik / Foto";
      mediaEditorBox.appendChild(subHeader);

      const subBody = document.createElement("div");
      mediaEditorBox.appendChild(subBody);

      if (blk.media_type === "table" && typeof E.buildTableBlockBody === "function") {
        E.buildTableBlockBody(subBody, blk.media);
      } else if (blk.media_type === "db_chart" && typeof E.buildDbChartBlockBody === "function") {
        E.buildDbChartBlockBody(subBody, blk.media);
      } else if (blk.media_type === "custom_chart" && typeof E.buildCustomChartBlockBody === "function") {
        E.buildCustomChartBlockBody(subBody, blk.media);
      } else if (typeof E.buildFigureBlockBody === "function") {
        E.buildFigureBlockBody(subBody, blk.media);
      }
      hideNestedLayoutControl(subBody);
    }

    const mtypeCtrl = makeSelectField(
      "Medium-Typ",
      [
        { val: "figure", label: "Grafik / Bild (Upload)" },
        { val: "db_chart", label: "DB-Chart (Zeitreihe)" },
        { val: "custom_chart", label: "Daten-Chart (Excel / TSV)" },
        { val: "table", label: "Tabelle (Excel-Paste)" },
      ],
      blk.media_type,
      function (val) {
        mediaDrafts[blk.media_type] = blk.media;
        blk.media_type = val;
        if (mediaDrafts[val]) {
          blk.media = mediaDrafts[val];
        } else {
          blk.media = createSubMediaDefault(val);
          mediaDrafts[val] = blk.media;
        }
        blk.media.type = val;
        blk.media.layout = "column";
        renderSubMediaEditor();
      }
    );

    const widthCtrl = makeSelectField(
      "Medien-Breite (Nebeneinander)",
      [
        { val: 20, label: "20 % (sehr schmal)" },
        { val: 25, label: "25 % (schmales Thumbnail)" },
        { val: 30, label: "30 % (Standard Advisory)" },
        { val: 35, label: "35 % (ausgewogen)" },
        { val: 40, label: "40 % (breites Chart/Tabelle)" },
        { val: 50, label: "50 % (hälftig)" },
      ],
      blk.media_width_pct,
      function (val) {
        blk.media_width_pct = parseInt(val, 10) || 30;
      }
    );

    const posCtrl = makeSelectField(
      "Platzierung Medium / Text",
      [
        { val: "auto", label: "Auto (Breit: links · Schmal: oben)" },
        { val: "left", label: "Medium links · Text rechts" },
        { val: "right", label: "Text links · Medium rechts" },
        { val: "top", label: "Medium oben · Text unten" },
        { val: "bottom", label: "Text oben · Medium unten" },
      ],
      blk.media_position,
      function (val) {
        blk.media_position = val;
        const isVert = val === "top" || val === "bottom";
        widthCtrl.sel.disabled = isVert;
      }
    );
    widthCtrl.sel.disabled = blk.media_position === "top" || blk.media_position === "bottom";

    const styleCtrl = makeSelectField(
      "Darstellungs-Stil",
      [
        { val: "plain", label: "Standard (Transparent)" },
        { val: "zebra", label: "Zebra-Liste (Alternierend)" },
        { val: "card", label: "Karte (Umrahmt)" },
      ],
      blk.style_preset,
      function (val) {
        blk.style_preset = val;
      }
    );

    configGrid.appendChild(mtypeCtrl.wrap);
    configGrid.appendChild(posCtrl.wrap);
    configGrid.appendChild(widthCtrl.wrap);
    configGrid.appendChild(styleCtrl.wrap);
    container.appendChild(configGrid);

    // Zeile 3: Eingebettetes Medium
    renderSubMediaEditor();
    container.appendChild(mediaEditorBox);

    // Zeile 4: Haupttext (RichText)
    const textWrap = document.createElement("div");
    textWrap.className = "field-group";
    const textLbl = document.createElement("label");
    textLbl.className = "field-label";
    textLbl.textContent = "Textblock (Rich-Text inkl. Fett, Links, Glossar & Fussnoten)";
    textWrap.appendChild(textLbl);
    const rtMain = E.createRichTextWidget(blk.html || "<p></p>", function (newHtml) {
      blk.html = newHtml;
      markDirty();
    });
    textWrap.appendChild(rtMain.wrapper);
    container.appendChild(textWrap);

    // Zeile 5: Optionale 3. Spalte (Produkt / ISIN-Link wie in TopChancen)
    const hasAsideInitial = !!(blk.aside_html && blk.aside_html.replace(/<[^>]+>/g, "").trim());
    const asideToggleRow = document.createElement("div");
    asideToggleRow.style.display = "flex";
    asideToggleRow.style.alignItems = "center";
    asideToggleRow.style.justifyContent = "space-between";
    asideToggleRow.style.marginBottom = "6px";

    const asideLabel = document.createElement("label");
    asideLabel.style.display = "inline-flex";
    asideLabel.style.alignItems = "center";
    asideLabel.style.gap = "6px";
    asideLabel.style.fontSize = "12px";
    asideLabel.style.cursor = "pointer";
    asideLabel.style.color = "#002855";
    asideLabel.style.fontWeight = "500";

    const asideCb = document.createElement("input");
    asideCb.type = "checkbox";
    asideCb.checked = hasAsideInitial;

    asideLabel.appendChild(asideCb);
    asideLabel.appendChild(document.createTextNode("Optionale 3. Spalte rechts einblenden (z. B. Produktname / ISIN-Link)"));
    asideToggleRow.appendChild(asideLabel);
    container.appendChild(asideToggleRow);

    const asideWrap = document.createElement("div");
    asideWrap.className = "field-group";
    asideWrap.style.display = hasAsideInitial ? "block" : "none";
    const rtAside = E.createRichTextWidget(blk.aside_html || "<p></p>", function (newHtml) {
      blk.aside_html = asideCb.checked ? newHtml : "";
      markDirty();
    });
    asideWrap.appendChild(rtAside.wrapper);
    container.appendChild(asideWrap);

    asideCb.addEventListener("change", function () {
      asideWrap.style.display = asideCb.checked ? "block" : "none";
      if (!asideCb.checked) {
        blk.aside_html = "";
      } else if (!blk.aside_html) {
        blk.aside_html = "<p>Produktname / ISIN</p>";
        rtAside.editor.innerHTML = blk.aside_html;
      }
      markDirty();
    });
  }

  function createFigureScaleControls(blk) {
    const scaleGrid = document.createElement("div");
    scaleGrid.style.display = "grid";
    scaleGrid.style.gridTemplateColumns = "1fr 1fr";
    scaleGrid.style.gap = "10px";
    scaleGrid.style.marginBottom = "10px";

    const scalePctWrap = document.createElement("div");
    const scalePctLbl = document.createElement("label");
    scalePctLbl.className = "field-label";
    scalePctLbl.textContent = "Grafik-Höhe / Grösse (5 %-Schritte)";
    const scalePctSel = document.createElement("select");
    scalePctSel.className = "cms-select";
    [100, 95, 90, 85, 80, 75].forEach(function (pct) {
      const o = document.createElement("option");
      o.value = String(pct);
      o.textContent = pct === 100 ? "100 % (Original)" : pct + " % (-" + (100 - pct) + " %)";
      scalePctSel.appendChild(o);
    });
    const rawScalePct = parseInt(blk.scale_pct, 10);
    const curScalePct = (!isNaN(rawScalePct) && rawScalePct >= 75 && rawScalePct <= 100)
      ? Math.round(rawScalePct / 5) * 5
      : 100;
    blk.scale_pct = curScalePct;
    scalePctSel.value = String(curScalePct);
    scalePctSel.addEventListener("change", function () {
      blk.scale_pct = parseInt(scalePctSel.value, 10) || 100;
      markDirty();
    });
    scalePctWrap.appendChild(scalePctLbl);
    scalePctWrap.appendChild(scalePctSel);

    const scaleModeWrap = document.createElement("div");
    const scaleModeLbl = document.createElement("label");
    scaleModeLbl.className = "field-label";
    scaleModeLbl.textContent = "Skalierungsmodus";
    const scaleModeSel = document.createElement("select");
    scaleModeSel.className = "cms-select";
    [
      { val: "proportional", label: "Proportional verkleinern (linksbündig, Luft rechts)" },
      { val: "squeeze_y", label: "Vertikal stauchen (100 % Breite beibehalten)" },
      { val: "original", label: "Originalgrösse (falls kleiner als Spalte)" },
    ].forEach(function (opt) {
      const o = document.createElement("option");
      o.value = opt.val;
      o.textContent = opt.label;
      scaleModeSel.appendChild(o);
    });
    const curScaleMode = (blk.scale_mode === "squeeze_y" || blk.scale_mode === "original") ? blk.scale_mode : "proportional";
    blk.scale_mode = curScaleMode;
    scaleModeSel.value = curScaleMode;
    scalePctSel.disabled = (curScaleMode === "original");
    scaleModeSel.addEventListener("change", function () {
      const val = scaleModeSel.value;
      blk.scale_mode = (val === "squeeze_y" || val === "original") ? val : "proportional";
      scalePctSel.disabled = (blk.scale_mode === "original");
      markDirty();
    });
    scaleModeWrap.appendChild(scaleModeLbl);
    scaleModeWrap.appendChild(scaleModeSel);

    scaleGrid.appendChild(scalePctWrap);
    scaleGrid.appendChild(scaleModeWrap);
    return scaleGrid;
  }

  async function tryUploadExcelHtml(htmlText, onFileReady) {
    if (!htmlText || htmlText.toLowerCase().indexOf("<table") === -1) return false;
    try {
      const resp = await fetch("api/excel-html-to-svg", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ html: htmlText }),
      });
      if (!resp.ok) return false;
      const data = await resp.json();
      if (data && data.ok && data.svg) {
        onFileReady(new Blob([data.svg], { type: "image/svg+xml" }));
        return true;
      }
    } catch (err) {
      console.warn("Excel-HTML zu SVG Konvertierung fehlgeschlagen, Fallback auf Bild:", err);
    }
    return false;
  }

  async function pasteFigureFromClipboard(onFileReady, dropzone) {
    if (navigator.clipboard && navigator.clipboard.read) {
      try {
        const items = await navigator.clipboard.read();
        for (const item of items) {
          if (item.types.includes("text/html")) {
            const htmlBlob = await item.getType("text/html");
            if (await tryUploadExcelHtml(await htmlBlob.text(), onFileReady)) return true;
          }
        }
        for (const item of items) {
          const imgType = item.types.find(function (t) { return t.startsWith("image/"); });
          if (imgType) {
            onFileReady(await item.getType(imgType));
            return true;
          }
        }
        if (navigator.clipboard.readText) {
          const trimmed = ((await navigator.clipboard.readText()) || "").trim();
          if (trimmed.startsWith("<svg") && trimmed.includes("</svg>")) {
            onFileReady(new Blob([trimmed], { type: "image/svg+xml" }));
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
    if (dropzone) dropzone.focus();
    return false;
  }

  function handleFigurePasteEvent(e, onFileReady) {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) {
      const hasImage = e.clipboardData && e.clipboardData.items && Array.from(e.clipboardData.items).some(function (item) {
        return item.type.indexOf("image") !== -1;
      });
      const hasText = e.clipboardData && e.clipboardData.getData("text/plain");
      if (hasText && !hasImage) return;
    }

    const cd = e.clipboardData || window.clipboardData;
    if (!cd) return;

    const htmlData = cd.getData ? (cd.getData("text/html") || "") : "";
    let fallbackImageFile = null;

    if (cd.items && cd.items.length > 0) {
      for (let i = 0; i < cd.items.length; i++) {
        if (cd.items[i].type.indexOf("image") !== -1) {
          fallbackImageFile = cd.items[i].getAsFile();
          if (fallbackImageFile) break;
        }
      }
    }
    if (!fallbackImageFile && cd.files && cd.files.length > 0) {
      for (let i = 0; i < cd.files.length; i++) {
        const f = cd.files[i];
        if (f.type.startsWith("image/") || /\.(svg|png|jpe?g)$/i.test(f.name)) {
          fallbackImageFile = f;
          break;
        }
      }
    }

    if (htmlData && htmlData.toLowerCase().indexOf("<table") !== -1) {
      e.preventDefault();
      e.stopPropagation();
      (async () => {
        const converted = await tryUploadExcelHtml(htmlData, onFileReady);
        if (!converted && fallbackImageFile) onFileReady(fallbackImageFile);
      })();
      return;
    }

    if (fallbackImageFile) {
      e.preventDefault();
      e.stopPropagation();
      onFileReady(fallbackImageFile);
      return;
    }

    const textData = cd.getData("text/plain");
    if (textData) {
      const trimmed = textData.trim();
      if (trimmed.startsWith("<svg") && trimmed.includes("</svg>")) {
        e.preventDefault();
        e.stopPropagation();
        onFileReady(new Blob([trimmed], { type: "image/svg+xml" }));
      }
    }
  }

  Object.assign(E, {
    buildMediaTextBlockBody: buildMediaTextBlockBody,
    createFigureScaleControls: createFigureScaleControls,
    pasteFigureFromClipboard: pasteFigureFromClipboard,
    handleFigurePasteEvent: handleFigurePasteEvent,
  });
})();
