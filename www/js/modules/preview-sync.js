/**
 * LUKB Investment Office — Interaktive PDF-Vorschau -> Editor-Fokus-Synchronisation
 */
(function () {
  "use strict";

  const E = (window.LUKBEditor = window.LUKBEditor || {});
  const state = E.state;
  const CMS_LINK_PREFIX = "https://cms-block.invalid/";

  function parseCmsTargetsFromAnnotations(annots) {
    const targets = [];
    if (!Array.isArray(annots)) return targets;
    for (let i = 0; i < annots.length; i++) {
      const ann = annots[i];
      if (
        ann &&
        ann.subtype === "Link" &&
        typeof ann.url === "string" &&
        ann.url.indexOf(CMS_LINK_PREFIX) === 0 &&
        Array.isArray(ann.rect) &&
        ann.rect.length === 4
      ) {
        const rest = ann.url.slice(CMS_LINK_PREFIX.length);
        const slashIdx = rest.indexOf("/");
        if (slashIdx > 0) {
          const kind = rest.slice(0, slashIdx);
          const targetId = decodeURIComponent(rest.slice(slashIdx + 1));
          const x1 = Math.min(ann.rect[0], ann.rect[2]);
          const y1 = Math.min(ann.rect[1], ann.rect[3]);
          const x2 = Math.max(ann.rect[0], ann.rect[2]);
          const y2 = Math.max(ann.rect[1], ann.rect[3]);
          targets.push({
            kind: kind,
            id: targetId,
            rect: [x1, y1, x2, y2],
            area: Math.max(0.01, (x2 - x1) * (y2 - y1)),
          });
        }
      }
    }
    return targets;
  }

  function findCmsTargetAtPoint(pageWrap, clientX, clientY) {
    if (!pageWrap || !Array.isArray(pageWrap._cmsTargets) || pageWrap._cmsTargets.length === 0) {
      return null;
    }
    const unscaled = pageWrap._unscaledViewport;
    const canvas = pageWrap.querySelector("canvas");
    if (!unscaled || !canvas) return null;

    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;

    const normX = ((clientX - rect.left) / rect.width) * unscaled.width;
    const normY = ((clientY - rect.top) / rect.height) * unscaled.height;
    const pdfPt = unscaled.convertToPdfPoint(normX, normY);
    const px = pdfPt[0];
    const py = pdfPt[1];

    const targets = pageWrap._cmsTargets;
    let bestExact = null;
    for (let i = 0; i < targets.length; i++) {
      const t = targets[i];
      const r = t.rect;
      if (px >= r[0] && px <= r[2] && py >= r[1] && py <= r[3]) {
        if (!bestExact || t.area < bestExact.area) {
          bestExact = t;
        }
      }
    }
    if (bestExact) return bestExact;

    const pad = 6;
    let bestNear = null;
    let bestDistSq = Infinity;
    for (let i = 0; i < targets.length; i++) {
      const t = targets[i];
      const r = t.rect;
      if (px >= r[0] - pad && px <= r[2] + pad && py >= r[1] - pad && py <= r[3] + pad) {
        const dx = px < r[0] ? r[0] - px : (px > r[2] ? px - r[2] : 0);
        const dy = py < r[1] ? r[1] - py : (py > r[3] ? py - r[3] : 0);
        const distSq = dx * dx + dy * dy;
        if (distSq < bestDistSq || (distSq === bestDistSq && (!bestNear || t.area < bestNear.area))) {
          bestDistSq = distSq;
          bestNear = t;
        }
      }
    }
    return bestNear;
  }

  function triggerTargetHighlight(el) {
    if (!el) return;
    if (el._cmsHighlightTimer) {
      clearTimeout(el._cmsHighlightTimer);
    }
    el.classList.add("anchor-target-highlight");
    el._cmsHighlightTimer = setTimeout(function () {
      el.classList.remove("anchor-target-highlight");
      el._cmsHighlightTimer = null;
    }, 1600);
  }

  function focusSafe(el) {
    if (!el || typeof el.focus !== "function") return;
    try {
      el.focus({ preventScroll: true });
    } catch (_) {
      el.focus();
    }
  }

  function focusEditorTarget(kind, id) {
    if (!id) return;
    if (kind === "block") {
      const escapedId = typeof CSS !== "undefined" && typeof CSS.escape === "function" ? CSS.escape(id) : id;
      const card = document.querySelector('.cms-block-card[data-block-id="' + escapedId + '"]');
      if (!card) return;
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      triggerTargetHighlight(card);

      const body = card.querySelector(".block-body") || card;
      const focusable = body.querySelector(
        '[contenteditable="true"], textarea:not([disabled]), input:not([type="checkbox"]):not([type="hidden"]):not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      focusSafe(focusable);
    } else if (kind === "meta") {
      const el = document.getElementById(id);
      if (!el) return;
      const details = el.closest("details");
      if (details && !details.open) {
        details.open = true;
      }
      let highlightEl = el;
      let focusEl = el;
      if (id === "meta-tags-container") {
        highlightEl = el.closest(".tags-editor-box") || el;
        focusEl = document.getElementById("meta-tag-input") || el;
      } else if (id === "meta-authors-container") {
        highlightEl = el.closest(".field-group") || el;
        focusEl = el.querySelector("input:not([disabled])") || document.getElementById("btn-add-author") || el;
      }
      highlightEl.scrollIntoView({ behavior: "smooth", block: "center" });
      triggerTargetHighlight(highlightEl);
      focusSafe(focusEl);
    }
  }

  function ensurePdfClickNavigation(pdfContainer) {
    if (!pdfContainer || pdfContainer._hasCmsClickNav) return;
    pdfContainer._hasCmsClickNav = true;

    pdfContainer.addEventListener("mousemove", function (e) {
      const pageWrap = e.target && e.target.closest ? e.target.closest(".typst-pdf-page") : null;
      if (!pageWrap) return;
      const canvas = pageWrap.querySelector("canvas");
      if (!canvas) return;
      const hit = findCmsTargetAtPoint(pageWrap, e.clientX, e.clientY);
      canvas.style.cursor = hit ? "pointer" : "";
    });

    pdfContainer.addEventListener("click", function (e) {
      const pageWrap = e.target && e.target.closest ? e.target.closest(".typst-pdf-page") : null;
      if (!pageWrap) return;
      const hit = findCmsTargetAtPoint(pageWrap, e.clientX, e.clientY);
      if (hit) {
        e.preventDefault();
        focusEditorTarget(hit.kind, hit.id);
      }
    });
  }

  async function extractPageCmsTargets(page, pageWrap, unscaled, isStaleFn) {
    try {
      const annots = await page.getAnnotations({ intent: "display" });
      if (isStaleFn && isStaleFn()) return;
      pageWrap._cmsTargets = parseCmsTargetsFromAnnotations(annots);
      pageWrap._unscaledViewport = unscaled;
    } catch (_) {
      pageWrap._cmsTargets = [];
      pageWrap._unscaledViewport = unscaled;
    }
  }

  function base64ToUint8Array(base64) {
    const raw = window.atob(base64);
    const rawLength = raw.length;
    const array = new Uint8Array(rawLength);
    for (let i = 0; i < rawLength; i++) {
      array[i] = raw.charCodeAt(i);
    }
    return array;
  }

  let _currentPdfRenderSeq = 0;
  let _activeRenderTasks = [];
  let _activeLoadingTask = null;
  let _activePdfDoc = null;
  let _sharedPdfWorker = null;
  let _lastRenderedPdfBase64 = "";
  let _pdfScrollTimer = null;
  let _activeRenderState = null;

  function cancelActivePdfRendering() {
    _currentPdfRenderSeq += 1;
    for (let i = 0; i < _activeRenderTasks.length; i++) {
      try {
        if (_activeRenderTasks[i] && typeof _activeRenderTasks[i].cancel === "function") {
          _activeRenderTasks[i].cancel();
        }
      } catch (_) {}
    }
    _activeRenderTasks = [];
    if (_activeLoadingTask) {
      try {
        _activeLoadingTask.destroy();
      } catch (_) {}
      _activeLoadingTask = null;
    }
  }

  function computeVisiblePageIndices(container, pageWraps) {
    const cRect = container.getBoundingClientRect ? container.getBoundingClientRect() : { top: 0, bottom: 900 };
    const visible = [];
    for (let i = 0; i < pageWraps.length; i++) {
      const r = pageWraps[i].getBoundingClientRect ? pageWraps[i].getBoundingClientRect() : { top: i * 900, bottom: (i + 1) * 900 };
      if (r.bottom >= cRect.top - 120 && r.top <= cRect.bottom + 120) {
        visible.push(i + 1);
      }
    }
    if (visible.length === 0 && pageWraps.length > 0) {
      visible.push(1);
    }
    const minP = Math.max(1, Math.min.apply(null, visible) - 1);
    const maxP = Math.min(pageWraps.length, Math.max.apply(null, visible) + 1);
    const priority = [];
    for (let p = minP; p <= maxP; p++) {
      priority.push(p);
    }
    return { priority: priority, minP: minP, maxP: maxP };
  }

  async function renderVisiblePdfPages(renderSeq) {
    const rs = _activeRenderState;
    if (!rs || renderSeq !== _currentPdfRenderSeq || !rs.pdfDoc) return;
    const { pdfDoc, existingPages, targetWidth, dpr, pdfContainer } = rs;
    const { priority, minP, maxP } = computeVisiblePageIndices(pdfContainer, existingPages);

    // Canvas-Speicher für weit entfernte Seiten (> 3 Seiten Abstand) freigeben
    const keepMargin = 3;
    for (let p = 1; p <= existingPages.length; p++) {
      if (p < minP - keepMargin || p > maxP + keepMargin) {
        const wrap = existingPages[p - 1];
        if (wrap && wrap.dataset.rendered === "1") {
          const oldCanvas = wrap.querySelector("canvas");
          if (oldCanvas) {
            oldCanvas.width = 0;
            oldCanvas.height = 0;
            oldCanvas.remove();
          }
          wrap.dataset.rendered = "0";
        }
      }
    }

    for (let idx = 0; idx < priority.length; idx++) {
      const pageNum = priority[idx];
      if (renderSeq !== _currentPdfRenderSeq) return;
      const pageWrap = existingPages[pageNum - 1];
      if (!pageWrap || pageWrap.dataset.rendered === "1") continue;

      const page = await pdfDoc.getPage(pageNum);
      if (renderSeq !== _currentPdfRenderSeq) return;

      const unscaled = page.getViewport({ scale: 1.0 });
      pageWrap.style.aspectRatio = unscaled.width + " / " + unscaled.height;

      const cssScale = (targetWidth > 0 ? targetWidth : 760) / unscaled.width;
      const renderScale = cssScale * dpr;
      const viewport = page.getViewport({ scale: renderScale });

      let canvas = pageWrap.querySelector("canvas");
      if (!canvas) {
        canvas = document.createElement("canvas");
        pageWrap.innerHTML = "";
        pageWrap.appendChild(canvas);
      }

      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.style.width = "100%";
      canvas.style.height = "auto";
      canvas.style.display = "block";

      const ctx = canvas.getContext("2d", { alpha: false });
      const renderTask = page.render({
        canvasContext: ctx,
        viewport: viewport,
      });
      _activeRenderTasks.push(renderTask);

      try {
        await renderTask.promise;
      } catch (err) {
        if (err && err.name === "RenderingCancelledException") {
          return;
        }
        throw err;
      }

      if (renderSeq !== _currentPdfRenderSeq) return;
      pageWrap.dataset.rendered = "1";
      await extractPageCmsTargets(page, pageWrap, unscaled, function () { return renderSeq !== _currentPdfRenderSeq; });
    }
  }

  function getSharedPdfWorker() {
    if (!window.pdfjsLib || typeof window.pdfjsLib.PDFWorker !== "function") {
      return null;
    }
    if (!_sharedPdfWorker || _sharedPdfWorker.destroyed) {
      _sharedPdfWorker = new window.pdfjsLib.PDFWorker({ name: "lukb_preview_worker" });
    }
    return _sharedPdfWorker;
  }

  async function renderPdfPreview(pdfBase64) {
    if (typeof window !== "undefined" && window.pdfjsLib && !window.pdfjsLib.GlobalWorkerOptions.workerSrc) {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = "js/vendor/pdf.worker.min.js";
    }

    const pdfContainer = document.getElementById("preview-container-pdf");
    const pageBadge = document.getElementById("preview-page-count");
    const refreshBtn = document.getElementById("btn_refresh_preview");
    if (!pdfContainer) return;
    ensurePdfClickNavigation(pdfContainer);

    if (refreshBtn && !refreshBtn._hasPdfResetListener) {
      refreshBtn._hasPdfResetListener = true;
      refreshBtn.addEventListener("click", function () {
        _lastRenderedPdfBase64 = "";
      });
    }

    // Redundantes Neuzeichnen vermeiden, wenn dieser exakte PDF-Stand bereits auf dem Canvas liegt
    if (pdfBase64 && pdfBase64 === _lastRenderedPdfBase64) {
      state.previewPending = false;
      if (refreshBtn) refreshBtn.classList.remove("has-pending-preview");
      return;
    }

    cancelActivePdfRendering();
    const renderSeq = _currentPdfRenderSeq;
    if (_activePdfDoc && typeof _activePdfDoc.destroy === "function") {
      _activePdfDoc.destroy().catch(function () {});
      _activePdfDoc = null;
    }

    if (!window.pdfjsLib) {
      console.error("PDF.js ist nicht geladen.");
      return;
    }

    let pdfDoc = null;
    let loadingTask = null;
    const seqAtRenderStart = state.editSeq;
    try {
      const pdfData = base64ToUint8Array(pdfBase64);
      const docOpts = {
        data: pdfData,
        isEvalSupported: false,
      };
      const sharedWorker = getSharedPdfWorker();
      if (sharedWorker) {
        docOpts.worker = sharedWorker;
      }
      loadingTask = window.pdfjsLib.getDocument(docOpts);
      _activeLoadingTask = loadingTask;
      pdfDoc = await loadingTask.promise;

      if (renderSeq !== _currentPdfRenderSeq) {
        return; // Ein neueres Update hat diesen Render-Vorgang überholt
      }

      const numPages = pdfDoc.numPages;

      // Eventuelle alte SVG-Seiten-Elemente oder Fehlermeldungen abräumen
      const svgPages = pdfContainer.querySelectorAll(":scope > .typst-svg-page, :scope > .preview-error-box");
      if (svgPages.length > 0) {
        svgPages.forEach(function (el) { el.remove(); });
      }

      // Bestehende PDF-Seiten-Container ermitteln
      const existingPages = Array.from(pdfContainer.querySelectorAll(":scope > .typst-pdf-page"));

      // Überzählige Seiten vom Ende entfernen
      while (existingPages.length > numPages) {
        const toRemove = existingPages.pop();
        if (toRemove) toRemove.remove();
      }

      // Fehlende Seiten-Container anhängen
      while (existingPages.length < numPages) {
        const pageWrap = document.createElement("div");
        pageWrap.className = "typst-pdf-page";
        pdfContainer.appendChild(pageWrap);
        existingPages.push(pageWrap);
      }

      const targetWidth = Math.min(
        pdfContainer.clientWidth > 40 ? pdfContainer.clientWidth - 40 : 760,
        760
      );
      const dpr = Math.max(window.devicePixelRatio || 1, 1.5);

      // Seitenverhältnis-Platzhalter aus erster Seite vorbelegen
      const firstPage = await pdfDoc.getPage(1);
      if (renderSeq !== _currentPdfRenderSeq) return;
      const firstUnscaled = firstPage.getViewport({ scale: 1.0 });
      const defaultAspect = firstUnscaled.width + " / " + firstUnscaled.height;
      for (let i = 0; i < existingPages.length; i++) {
        existingPages[i].dataset.rendered = "0";
        if (!existingPages[i].style.aspectRatio) {
          existingPages[i].style.aspectRatio = defaultAspect;
        }
      }

      _activePdfDoc = pdfDoc;
      _activeRenderState = {
        pdfDoc: pdfDoc,
        existingPages: existingPages,
        targetWidth: targetWidth,
        dpr: dpr,
        pdfContainer: pdfContainer,
      };

      if (!pdfContainer._hasViewportScrollListener) {
        pdfContainer._hasViewportScrollListener = true;
        pdfContainer.addEventListener("scroll", function () {
          if (_pdfScrollTimer) clearTimeout(_pdfScrollTimer);
          _pdfScrollTimer = setTimeout(function () {
            renderVisiblePdfPages(_currentPdfRenderSeq).catch(function () {});
          }, 80);
        });
      }

      await renderVisiblePdfPages(renderSeq);
      if (renderSeq !== _currentPdfRenderSeq) return;

      _lastRenderedPdfBase64 = pdfBase64;
      if (seqAtRenderStart > state.lastPreviewedSeq) {
        state.lastPreviewedSeq = seqAtRenderStart;
      }
      state.lastKnownPageCount = numPages;
      state.previewPending = false;
      if (refreshBtn) refreshBtn.classList.remove("has-pending-preview");
      if (pageBadge) {
        const baseLabel =
          numPages + (numPages === 1 ? " PDF-Seite (Typst)" : " PDF-Seiten (Typst)");
        pageBadge.textContent = state.autoPreview ? baseLabel : baseLabel + " · Pausiert";
      }
    } catch (err) {
      if (_sharedPdfWorker && _sharedPdfWorker.destroyed) {
        _sharedPdfWorker = null;
      }
      if (renderSeq !== _currentPdfRenderSeq) return;
      console.error("PDF.js Live-Preview Render-Fehler:", err);
    } finally {
      if (_activeLoadingTask === loadingTask) {
        _activeLoadingTask = null;
      }
    }
  }

  Object.assign(E, {
    cancelActivePdfRendering: cancelActivePdfRendering,
    computeVisiblePageIndices: computeVisiblePageIndices,
    parseCmsTargetsFromAnnotations: parseCmsTargetsFromAnnotations,
    extractPageCmsTargets: extractPageCmsTargets,
    ensurePdfClickNavigation: ensurePdfClickNavigation,
    renderPdfPreview: renderPdfPreview,
    renderVisiblePdfPages: renderVisiblePdfPages,
  });
})();
