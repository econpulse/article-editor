/**
 * LUKB Static Content Portal - Instant Client-Side Search & Filter Engine
 * Läuft vollständig im Browser ohne Server/Backend.
 */
document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.getElementById("portal-search");
  const filterPills = document.querySelectorAll(".filter-pill");
  const cards = document.querySelectorAll(".article-card");
  const countDisplay = document.getElementById("results-count");
  const emptyState = document.getElementById("portal-empty");

  let currentCategory = "all";
  let currentSearch = "";

  function normalizeText(str) {
    return (str || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();
  }

  function applyFilters() {
    let visibleCount = 0;
    const query = normalizeText(currentSearch);

    cards.forEach(function (card) {
      const cardCategory = card.getAttribute("data-category") || "";
      const searchBlob = normalizeText(card.getAttribute("data-search") || "");

      const matchesCategory = (currentCategory === "all") || (cardCategory === currentCategory);
      const matchesSearch = (!query) || searchBlob.includes(query);

      if (matchesCategory && matchesSearch) {
        card.style.display = "";
        visibleCount++;
      } else {
        card.style.display = "none";
      }
    });

    if (countDisplay) {
      countDisplay.textContent = visibleCount + (visibleCount === 1 ? " Artikel gefunden" : " Artikel gefunden");
    }

    if (emptyState) {
      if (visibleCount === 0) {
        emptyState.style.display = "block";
      } else {
        emptyState.style.display = "none";
      }
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", function (e) {
      currentSearch = e.target.value;
      applyFilters();
    });
  }

  filterPills.forEach(function (pill) {
    pill.addEventListener("click", function () {
      filterPills.forEach(function (p) { p.classList.remove("active"); });
      pill.classList.add("active");
      currentCategory = pill.getAttribute("data-category") || "all";
      applyFilters();
    });
  });

  applyFilters();
});
