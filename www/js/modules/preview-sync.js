/**
 * LUKB Investment Office — Interaktive PDF-Vorschau -> Editor-Fokus-Synchronisation
 */
(function () {
  "use strict";

  const E = (window.LUKBEditor = window.LUKBEditor || {});
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

  Object.assign(E, {
    parseCmsTargetsFromAnnotations: parseCmsTargetsFromAnnotations,
    extractPageCmsTargets: extractPageCmsTargets,
    ensurePdfClickNavigation: ensurePdfClickNavigation,
  });
})();
