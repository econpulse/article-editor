/**
 * LUKB Editor Modul: Publikations-Sidebar, Monats-Archiv & Such-Dialog (Ctrl+K)
 */
(function () {
  "use strict";
  const E = (window.LUKBEditor = window.LUKBEditor || {});
  function clearUndoStack() { return E.clearUndoStack.apply(this, arguments); }
  function flushAutosave() { return E.flushAutosave.apply(this, arguments); }
  function performUndo() { return E.performUndo.apply(this, arguments); }
  const state = E.state;

  // ==========================================================================
  // Gruppierte & Einklappbare Artikel-Sidebar + Such- & Publikations-Dialog
  // ==========================================================================

  const STATUS_LABELS = {
    draft: "Entwurf",
    review: "In Review",
    published: "Publiziert",
    archived: "Archiviert",
  };

  const TPL_LABELS = {
    investment_focus: "Investment Fokus",
    investment_tufte: "Investment Fokus (Tufte)",
    market_flash: "Market Flash",
  };

  const MONTH_NAMES_DE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
  ];

  function getArchiveMonthInfo(item) {
    const pub = (item.publication_date || "").trim();
    const m = pub.match(/^(\d{4})-(\d{2})/);
    if (m) {
      const year = m[1];
      const monthIdx = parseInt(m[2], 10) - 1;
      const monthLabel =
        (MONTH_NAMES_DE[monthIdx] || m[2]) + " " + year;
      return { key: year + "-" + m[2], label: monthLabel };
    }
    const upd = (item.updated_at || "").trim();
    const m2 = upd.match(/(\d{2})\.(\d{2})\.(\d{4})/);
    if (m2) {
      const year = m2[3];
      const monthIdx = parseInt(m2[2], 10) - 1;
      const monthLabel =
        (MONTH_NAMES_DE[monthIdx] || m2[2]) + " " + year;
      return { key: year + "-" + m2[2], label: monthLabel };
    }
    return { key: "0000-00", label: "Weitere Ausgaben" };
  }

  function selectArticleById(articleId) {
    if (!articleId) return;
    if (state.article && state.article.id === articleId) {
      closePubModal();
      return;
    }
    if (state.isDirty) {
      flushAutosave(false);
    }
    if (window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue(
        "lukb_select_article",
        { id: articleId, ts: Date.now() },
        { priority: "event" }
      );
    }
    closePubModal();
  }

  function buildSidebarArticleCard(item, activeId, compact) {
    const card = document.createElement("div");
    card.className =
      "article-card-item" +
      (compact ? " compact" : "") +
      (item.id === activeId ? " active" : "");

    const top = document.createElement("div");
    top.className = "article-card-top";

    const badge = document.createElement("span");
    badge.className = "status-badge status-" + (item.status || "draft");
    badge.textContent = STATUS_LABELS[item.status] || "Entwurf";

    const tplSpan = document.createElement("span");
    tplSpan.className = "article-card-tpl";
    tplSpan.textContent = TPL_LABELS[item.template_id] || item.template_id;

    top.appendChild(badge);
    top.appendChild(tplSpan);

    const title = document.createElement("div");
    title.className = "article-card-title";
    title.textContent = item.title || "Unbenannte Publikation";

    card.appendChild(top);
    card.appendChild(title);

    if (!compact && item.subtitle) {
      const sub = document.createElement("div");
      sub.className = "article-card-subtitle-line";
      sub.textContent = item.subtitle;
      card.appendChild(sub);
    }

    const metaRow = document.createElement("div");
    metaRow.className = "article-card-meta";

    const authorSpan = document.createElement("span");
    authorSpan.style.overflow = "hidden";
    authorSpan.style.textOverflow = "ellipsis";
    authorSpan.style.whiteSpace = "nowrap";
    authorSpan.textContent = item.authors_summary || "";

    const dateSpan = document.createElement("span");
    dateSpan.style.whiteSpace = "nowrap";
    dateSpan.textContent =
      item.status === "published" && item.publication_date
        ? item.publication_date
        : item.updated_at || "";

    metaRow.appendChild(authorSpan);
    metaRow.appendChild(dateSpan);
    card.appendChild(metaRow);

    card.addEventListener("click", function () {
      selectArticleById(item.id);
    });

    return card;
  }

  function renderArticleList(articles, activeId, searchActive) {
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

    const activeWorkItems = articles.filter(function (a) {
      return a.status === "draft" || a.status === "review";
    });
    const publishedItems = articles.filter(function (a) {
      return a.status === "published";
    });
    const archivedItems = articles.filter(function (a) {
      return a.status === "archived";
    });

    // 1. Sektion: In Bearbeitung (Entwurf & In Review) — immer oben angepinnt
    if (activeWorkItems.length > 0) {
      const workSec = document.createElement("div");
      workSec.className = "sidebar-group-section";

      const hdr = document.createElement("div");
      hdr.className = "sidebar-group-header";
      const hdrTitle = document.createElement("span");
      hdrTitle.textContent = "In Bearbeitung (Entwurf & Review)";
      const hdrCount = document.createElement("span");
      hdrCount.className = "sidebar-group-count";
      hdrCount.textContent = String(activeWorkItems.length);
      hdr.appendChild(hdrTitle);
      hdr.appendChild(hdrCount);
      workSec.appendChild(hdr);

      activeWorkItems.forEach(function (item) {
        workSec.appendChild(buildSidebarArticleCard(item, activeId, false));
      });

      listContainer.appendChild(workSec);
    }

    // 2. Sektion: Publiziert (Live im Portal) — gruppiert nach Monat & Jahr (einklappbar)
    if (publishedItems.length > 0) {
      const pubSec = document.createElement("div");
      pubSec.className = "sidebar-group-section";

      const hdr = document.createElement("div");
      hdr.className = "sidebar-group-header";
      const hdrTitle = document.createElement("span");
      hdrTitle.textContent = "Publiziert (Live im Portal)";
      const hdrCount = document.createElement("span");
      hdrCount.className = "sidebar-group-count";
      hdrCount.textContent = String(publishedItems.length);
      hdr.appendChild(hdrTitle);
      hdr.appendChild(hdrCount);
      pubSec.appendChild(hdr);

      // Gruppiere nach Monat/Jahr
      const groupsMap = {};
      const groupKeys = [];
      publishedItems.forEach(function (item) {
        const info = getArchiveMonthInfo(item);
        if (!groupsMap[info.key]) {
          groupsMap[info.key] = { key: info.key, label: info.label, items: [] };
          groupKeys.push(info.key);
        }
        groupsMap[info.key].items.push(item);
      });

      groupKeys.sort().reverse();

      groupKeys.forEach(function (gKey, idx) {
        const grp = groupsMap[gKey];
        const details = document.createElement("details");
        details.className = "sidebar-archive-month";

        const containsActive = grp.items.some(function (it) {
          return it.id === activeId;
        });
        const shouldOpen =
          searchActive ||
          containsActive ||
          (state.openArchiveMonths[gKey] !== undefined
            ? state.openArchiveMonths[gKey]
            : idx === 0);

        if (shouldOpen) {
          details.setAttribute("open", "open");
        }

        details.addEventListener("toggle", function () {
          state.openArchiveMonths[gKey] = details.open;
        });

        const summary = document.createElement("summary");
        const mLabel = document.createElement("span");
        mLabel.className = "sidebar-archive-month-label";
        mLabel.textContent = grp.label;
        const mCount = document.createElement("span");
        mCount.className = "sidebar-group-count";
        mCount.textContent = String(grp.items.length);
        summary.appendChild(mLabel);
        summary.appendChild(mCount);

        const body = document.createElement("div");
        body.className = "sidebar-archive-month-body";
        grp.items.forEach(function (item) {
          body.appendChild(buildSidebarArticleCard(item, activeId, true));
        });

        details.appendChild(summary);
        details.appendChild(body);
        pubSec.appendChild(details);
      });

      listContainer.appendChild(pubSec);
    }

    // 3. Sektion: Papierkorb / Archiv (Soft-Delete)
    if (archivedItems.length > 0) {
      const archSec = document.createElement("div");
      archSec.className = "sidebar-group-section";

      const hdr = document.createElement("div");
      hdr.className = "sidebar-group-header";
      hdr.style.color = "#7f8c8d";
      const hdrTitle = document.createElement("span");
      hdrTitle.textContent = "📦 Papierkorb / Archiv";
      const hdrCount = document.createElement("span");
      hdrCount.className = "sidebar-group-count";
      hdrCount.textContent = String(archivedItems.length);
      hdr.appendChild(hdrTitle);
      hdr.appendChild(hdrCount);
      archSec.appendChild(hdr);

      archivedItems.forEach(function (item) {
        archSec.appendChild(buildSidebarArticleCard(item, activeId, false));
      });

      listContainer.appendChild(archSec);
    }
  }

  function setSidebarCollapsed(collapsed) {
    state.sidebarCollapsed = !!collapsed;
    const ws =
      document.getElementById("lukb-workspace") ||
      document.querySelector(".cms-workspace");
    const btnTop = document.getElementById("btn-toggle-sidebar");
    if (ws) {
      if (state.sidebarCollapsed) {
        ws.classList.add("sidebar-collapsed");
      } else {
        ws.classList.remove("sidebar-collapsed");
      }
    }
    if (btnTop) {
      btnTop.textContent = state.sidebarCollapsed
        ? "☰ Sidebar einblenden"
        : "☰ Publikationen";
    }
  }

  function toggleSidebar() {
    setSidebarCollapsed(!state.sidebarCollapsed);
  }

  window.lukbToggleSidebar = toggleSidebar;
  window.lukbSetSidebarCollapsed = setSidebarCollapsed;
  window.lukbPerformUndo = performUndo;
  window.lukbClearUndo = clearUndoStack;

  // ==========================================================================
  // Such- & Publikations-Dialog (Modal / Command Palette, Ctrl+K)
  // ==========================================================================

  function populateModalCategoryDropdown() {
    const sel = document.getElementById("pub-modal-category-filter");
    if (!sel) return;
    const currentVal = sel.value || "all";
    const categories = [];
    (state.allArticles || []).forEach(function (a) {
      const cat = (a.category || "").trim();
      if (cat && categories.indexOf(cat) === -1) {
        categories.push(cat);
      }
    });
    categories.sort();

    sel.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "all";
    allOpt.textContent = "Alle Rubriken (" + categories.length + ")";
    sel.appendChild(allOpt);

    categories.forEach(function (cat) {
      const opt = document.createElement("option");
      opt.value = cat;
      opt.textContent = cat;
      sel.appendChild(opt);
    });

    if (categories.indexOf(currentVal) !== -1) {
      sel.value = currentVal;
    } else {
      sel.value = "all";
      state.modalFilter.category = "all";
    }
  }

  function updateModalStatusPillCounts() {
    const all = state.allArticles || [];
    const counts = {
      all: all.length,
      active_work: all.filter((a) => a.status !== "published").length,
      draft: all.filter((a) => a.status === "draft").length,
      review: all.filter((a) => a.status === "review").length,
      published: all.filter((a) => a.status === "published").length,
    };
    const baseLabels = {
      all: "Alle",
      active_work: "In Bearbeitung",
      draft: "Entwurf",
      review: "In Review",
      published: "Publiziert",
    };
    document.querySelectorAll("[data-modal-status]").forEach(function (btn) {
      const st = btn.getAttribute("data-modal-status");
      if (baseLabels[st] !== undefined) {
        btn.textContent = baseLabels[st] + " (" + (counts[st] || 0) + ")";
      }
      if (st === state.modalFilter.status) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  function renderPubModalTable() {
    const tbody = document.getElementById("pub-modal-tbody");
    const countBadge = document.getElementById("pub-modal-count-badge");
    const pagContainer = document.getElementById("pub-modal-pagination");
    if (!tbody) return;

    updateModalStatusPillCounts();

    const f = state.modalFilter;
    const q = (f.search || "").trim().toLowerCase();

    let filtered = (state.allArticles || []).filter(function (a) {
      if (f.status === "active_work" && a.status === "published") return false;
      if (
        f.status !== "all" &&
        f.status !== "active_work" &&
        a.status !== f.status
      ) {
        return false;
      }
      if (f.template !== "all" && a.template_id !== f.template) return false;
      if (f.category !== "all" && (a.category || "") !== f.category) return false;

      if (q) {
        const hay = [
          a.title || "",
          a.subtitle || "",
          a.category || "",
          a.authors_summary || "",
          a.publication_date || "",
          a.updated_by || "",
        ]
          .join(" ")
          .toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });

    // Sortierung
    filtered.sort(function (a, b) {
      if (f.sort === "title_asc") {
        return (a.title || "").localeCompare(b.title || "", "de");
      }
      if (f.sort === "pubdate_desc") {
        return (b.publication_date || "").localeCompare(a.publication_date || "");
      }
      return (b.updated_iso || "").localeCompare(a.updated_iso || "");
    });

    if (countBadge) {
      countBadge.textContent =
        filtered.length +
        (filtered.length === 1 ? " Publikation" : " Publikationen");
    }

    const totalPages = Math.max(1, Math.ceil(filtered.length / f.pageSize));
    if (f.page > totalPages) f.page = totalPages;
    if (f.page < 1) f.page = 1;

    const startIdx = (f.page - 1) * f.pageSize;
    const pageItems = filtered.slice(startIdx, startIdx + f.pageSize);

    tbody.innerHTML = "";
    if (pageItems.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.style.textAlign = "center";
      td.style.padding = "32px";
      td.style.color = "#5A687C";
      td.textContent = "Keine Publikationen für die gewählten Such- und Filterkriterien gefunden.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      pageItems.forEach(function (item) {
        const tr = document.createElement("tr");
        if (item.id === state.activeArticleId) {
          tr.className = "active-row";
        }

        // 1. Status
        const tdStatus = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = "status-badge status-" + (item.status || "draft");
        badge.textContent = STATUS_LABELS[item.status] || "Entwurf";
        tdStatus.appendChild(badge);

        // 2. Titel & Untertitel
        const tdTitle = document.createElement("td");
        const titleDiv = document.createElement("div");
        titleDiv.className = "pub-modal-row-title";
        titleDiv.textContent = item.title || "Unbenannte Publikation";
        tdTitle.appendChild(titleDiv);
        if (item.subtitle) {
          const subDiv = document.createElement("div");
          subDiv.className = "pub-modal-row-subtitle";
          subDiv.textContent = item.subtitle;
          tdTitle.appendChild(subDiv);
        }

        // 3. Rubrik & Template
        const tdCat = document.createElement("td");
        const catDiv = document.createElement("div");
        catDiv.style.fontWeight = "500";
        catDiv.style.fontSize = "12.5px";
        catDiv.textContent = item.category || "—";
        const tplDiv = document.createElement("div");
        tplDiv.className = "pub-modal-row-subtitle";
        tplDiv.textContent = TPL_LABELS[item.template_id] || item.template_id;
        tdCat.appendChild(catDiv);
        tdCat.appendChild(tplDiv);

        // 4. Autoren
        const tdAuthors = document.createElement("td");
        tdAuthors.style.fontSize = "12.5px";
        tdAuthors.textContent = item.authors_summary || "Investment Office";

        // 5. Publikationsdatum
        const tdPubDate = document.createElement("td");
        tdPubDate.style.fontSize = "12.5px";
        tdPubDate.style.whiteSpace = "nowrap";
        tdPubDate.textContent = item.publication_date || "—";

        // 6. Zuletzt geändert
        const tdUpdated = document.createElement("td");
        tdUpdated.style.fontSize = "12px";
        tdUpdated.style.color = "#5A687C";
        tdUpdated.textContent = item.updated_at || "—";

        // 7. Aktionen
        const tdActions = document.createElement("td");
        const actWrap = document.createElement("div");
        actWrap.className = "pub-modal-row-actions";

        const openBtn = document.createElement("button");
        openBtn.type = "button";
        openBtn.className = "btn-lukb btn-lukb-navy btn-lukb-sm";
        openBtn.style.padding = "3px 9px";
        openBtn.textContent = "Öffnen";
        openBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          selectArticleById(item.id);
        });

        const dupBtn = document.createElement("button");
        dupBtn.type = "button";
        dupBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        dupBtn.style.padding = "3px 8px";
        dupBtn.title = "Publikation als neuen Entwurf duplizieren";
        dupBtn.textContent = "Kopie";
        dupBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          if (window.Shiny && window.Shiny.setInputValue) {
            window.Shiny.setInputValue(
              "lukb_modal_article_action",
              { action: "duplicate", id: item.id, ts: Date.now() },
              { priority: "event" }
            );
          }
          closePubModal();
        });

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-lukb btn-lukb-danger-ghost btn-lukb-sm";
        delBtn.style.padding = "3px 7px";
        delBtn.title = "Publikation löschen / archivieren";
        delBtn.textContent = "✕";
        delBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          const isPub = item.status === "published";
          const promptMsg = isPub
            ? 'Die Publikation "' +
              (item.title || "") +
              '" ist aktuell im Portal publiziert.\n\nMöchten Sie diese Publikation vom Portal zurückziehen und in das Archiv verschieben?'
            : 'Möchten Sie die Publikation "' +
              (item.title || "") +
              '" wirklich in das Archiv verschieben?';
          if (window.confirm(promptMsg)) {
            if (window.Shiny && window.Shiny.setInputValue) {
              window.Shiny.setInputValue(
                "lukb_modal_article_action",
                { action: "delete", id: item.id, ts: Date.now() },
                { priority: "event" }
              );
            }
          }
        });

        actWrap.appendChild(openBtn);
        actWrap.appendChild(dupBtn);
        actWrap.appendChild(delBtn);
        tdActions.appendChild(actWrap);

        tr.appendChild(tdStatus);
        tr.appendChild(tdTitle);
        tr.appendChild(tdCat);
        tr.appendChild(tdAuthors);
        tr.appendChild(tdPubDate);
        tr.appendChild(tdUpdated);
        tr.appendChild(tdActions);

        tr.addEventListener("click", function () {
          selectArticleById(item.id);
        });

        tbody.appendChild(tr);
      });
    }

    // Pagination Controls
    if (pagContainer) {
      pagContainer.innerHTML = "";
      if (totalPages > 1) {
        const prevBtn = document.createElement("button");
        prevBtn.type = "button";
        prevBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        prevBtn.disabled = f.page <= 1;
        prevBtn.textContent = "« Zurück";
        prevBtn.addEventListener("click", function () {
          if (f.page > 1) {
            f.page--;
            renderPubModalTable();
          }
        });
        pagContainer.appendChild(prevBtn);

        const pageInfo = document.createElement("span");
        pageInfo.style.fontSize = "12px";
        pageInfo.style.color = "#002855";
        pageInfo.style.padding = "0 8px";
        pageInfo.textContent = "Seite " + f.page + " / " + totalPages;
        pagContainer.appendChild(pageInfo);

        const nextBtn = document.createElement("button");
        nextBtn.type = "button";
        nextBtn.className = "btn-lukb btn-lukb-ghost btn-lukb-sm";
        nextBtn.disabled = f.page >= totalPages;
        nextBtn.textContent = "Weiter »";
        nextBtn.addEventListener("click", function () {
          if (f.page < totalPages) {
            f.page++;
            renderPubModalTable();
          }
        });
        pagContainer.appendChild(nextBtn);
      }
    }
  }

  function openPubModal() {
    const backdrop = document.getElementById("lukb-pub-modal-backdrop");
    if (!backdrop) return;
    state.modalOpen = true;
    populateModalCategoryDropdown();
    renderPubModalTable();
    backdrop.style.display = "flex";
    const searchInput = document.getElementById("pub-modal-search");
    if (searchInput) {
      setTimeout(function () {
        searchInput.focus();
        searchInput.select();
      }, 30);
    }
  }

  function closePubModal() {
    const backdrop = document.getElementById("lukb-pub-modal-backdrop");
    if (!backdrop) return;
    state.modalOpen = false;
    backdrop.style.display = "none";
  }

  window.lukbOpenPubModal = openPubModal;
  window.lukbClosePubModal = closePubModal;

  function bindSidebarAndModalListeners() {
    const btnToggleTop = document.getElementById("btn-toggle-sidebar");
    const btnToggleInner = document.getElementById("btn-sidebar-collapse-inner");
    const btnOpenModalTop = document.getElementById("btn-open-pub-modal");
    const btnOpenModalSidebar = document.getElementById("btn-sidebar-open-modal");
    const btnCloseModal = document.getElementById("btn-close-pub-modal");
    const btnModalNew = document.getElementById("btn-modal-new-article");
    const backdrop = document.getElementById("lukb-pub-modal-backdrop");

    if (btnToggleTop && !btnToggleTop.getAttribute("onclick")) {
      btnToggleTop.addEventListener("click", toggleSidebar);
    }
    if (btnToggleInner && !btnToggleInner.getAttribute("onclick")) {
      btnToggleInner.addEventListener("click", function () {
        setSidebarCollapsed(true);
      });
    }
    if (btnOpenModalTop && !btnOpenModalTop.getAttribute("onclick")) {
      btnOpenModalTop.addEventListener("click", openPubModal);
    }
    if (btnOpenModalSidebar && !btnOpenModalSidebar.getAttribute("onclick")) {
      btnOpenModalSidebar.addEventListener("click", openPubModal);
    }
    if (btnCloseModal && !btnCloseModal.getAttribute("onclick")) {
      btnCloseModal.addEventListener("click", closePubModal);
    }
    if (btnModalNew) {
      btnModalNew.addEventListener("click", function () {
        if (window.Shiny && window.Shiny.setInputValue) {
          window.Shiny.setInputValue(
            "lukb_modal_article_action",
            { action: "create", ts: Date.now() },
            { priority: "event" }
          );
        }
        closePubModal();
      });
    }
    if (backdrop) {
      backdrop.addEventListener("click", function (ev) {
        if (ev.target === backdrop) {
          closePubModal();
        }
      });
    }

    const searchInput = document.getElementById("pub-modal-search");
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        state.modalFilter.search = searchInput.value || "";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    }

    document.querySelectorAll("[data-modal-status]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.modalFilter.status = btn.getAttribute("data-modal-status") || "all";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    });

    const tplSelect = document.getElementById("pub-modal-template-filter");
    if (tplSelect) {
      tplSelect.addEventListener("change", function () {
        state.modalFilter.template = tplSelect.value || "all";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    }

    const catSelect = document.getElementById("pub-modal-category-filter");
    if (catSelect) {
      catSelect.addEventListener("change", function () {
        state.modalFilter.category = catSelect.value || "all";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    }

    const sortSelect = document.getElementById("pub-modal-sort");
    if (sortSelect) {
      sortSelect.addEventListener("change", function () {
        state.modalFilter.sort = sortSelect.value || "updated_desc";
        state.modalFilter.page = 1;
        renderPubModalTable();
      });
    }

    // Globale Shortcuts: Ctrl+K (Such- & Publikations-Dialog), Ctrl+B (Sidebar ein-/ausklappen), Ctrl+Z (Undo), Esc (Schliessen)
    document.addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key && ev.key.toLowerCase() === "k") {
        ev.preventDefault();
        if (state.modalOpen) {
          closePubModal();
        } else {
          openPubModal();
        }
      } else if (
        (ev.ctrlKey || ev.metaKey) &&
        ev.key &&
        ev.key.toLowerCase() === "b" &&
        !ev.target.closest(".richtext-surface")
      ) {
        ev.preventDefault();
        toggleSidebar();
      } else if (
        (ev.ctrlKey || ev.metaKey) &&
        ev.key &&
        ev.key.toLowerCase() === "z" &&
        !ev.shiftKey
      ) {
        // Native Text-Eingaben (Inputs, Textareas, Contenteditable, RichText) behalten ihr natives Browser-Undo
        const target = ev.target;
        const isTextEditing =
          target &&
          (target.tagName === "INPUT" ||
            target.tagName === "TEXTAREA" ||
            target.isContentEditable ||
            target.closest(".richtext-surface"));
        if (!isTextEditing) {
          if (state.undoStack && state.undoStack.length > 0) {
            ev.preventDefault();
            performUndo();
          }
        }
      } else if (ev.key === "Escape" && state.modalOpen) {
        ev.preventDefault();
        closePubModal();
      }
    });
  }


  Object.assign(E, {
    MONTH_NAMES_DE: MONTH_NAMES_DE,
    STATUS_LABELS: STATUS_LABELS,
    TPL_LABELS: TPL_LABELS,
    bindSidebarAndModalListeners: bindSidebarAndModalListeners,
    buildSidebarArticleCard: buildSidebarArticleCard,
    closePubModal: closePubModal,
    getArchiveMonthInfo: getArchiveMonthInfo,
    openPubModal: openPubModal,
    populateModalCategoryDropdown: populateModalCategoryDropdown,
    renderArticleList: renderArticleList,
    renderPubModalTable: renderPubModalTable,
    selectArticleById: selectArticleById,
    setSidebarCollapsed: setSidebarCollapsed,
    toggleSidebar: toggleSidebar,
    updateModalStatusPillCounts: updateModalStatusPillCounts,
  });
})();
