"""
Kuratiertes Finanzmarkt-Icon-Set und Farb-Tones für den KPI-Karten-Block (`kpi_cards`).
Single Source of Truth für Typst-PDF, Web-HTML, DOCX-Export und die Editor-UI.
"""

from __future__ import annotations

import html
from typing import Any

# Dezente, auf das LUKB Corporate Design abgestimmte Farb-Tones
KPI_TONES: dict[str, dict[str, str]] = {
    "navy": {
        "id": "navy",
        "label": "LUKB Navy",
        "accent": "#002855",
        "tint": "#EEF3F8",
        "badge": "#DCE6F2",
        "border": "#C2D1E2",
    },
    "blue": {
        "id": "blue",
        "label": "LUKB Blau",
        "accent": "#005A9C",
        "tint": "#EDF4FA",
        "badge": "#D9E9F7",
        "border": "#B8D2EA",
    },
    "cyan": {
        "id": "cyan",
        "label": "LUKB Cyan",
        "accent": "#009FE3",
        "tint": "#EDF8FD",
        "badge": "#D7F0FC",
        "border": "#AEDFF7",
    },
    "gold": {
        "id": "gold",
        "label": "LUKB Gold",
        "accent": "#C59B27",
        "tint": "#FBF7EC",
        "badge": "#F4E9CA",
        "border": "#E5D29A",
    },
    "positive": {
        "id": "positive",
        "label": "Positiv (Grün)",
        "accent": "#1E7E48",
        "tint": "#EFF8F3",
        "badge": "#D8EFE2",
        "border": "#B4DEC6",
    },
    "negative": {
        "id": "negative",
        "label": "Risiko / Negativ (Rot)",
        "accent": "#B83227",
        "tint": "#FDF1F0",
        "badge": "#F9DCD9",
        "border": "#ECC0BC",
    },
    "neutral": {
        "id": "neutral",
        "label": "Neutral (Grau)",
        "accent": "#5A687C",
        "tint": "#F4F7FA",
        "badge": "#E3E9F0",
        "border": "#D6DEE8",
    },
}

VALID_KPI_TONES = tuple(KPI_TONES.keys())

# 22 einheitliche Monoline-Vektor-Icons (24x24 ViewBox, Stroke-Width 1.75)
KPI_ICONS: list[dict[str, Any]] = [
    # --- Märkte & Performance ---
    {
        "id": "trend_up",
        "label": "Aufwärtstrend",
        "category": "Märkte & Performance",
        "keywords": "wachstum kurs anstieg bulle positiv performance",
        "markup": (
            '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>'
            '<polyline points="16 7 22 7 22 13"/>'
        ),
    },
    {
        "id": "trend_down",
        "label": "Abwärtstrend",
        "category": "Märkte & Performance",
        "keywords": "rückgang verlust bär negativ korrektur",
        "markup": (
            '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/>'
            '<polyline points="16 17 22 17 22 11"/>'
        ),
    },
    {
        "id": "trend_flat",
        "label": "Seitwärts / Stabil",
        "category": "Märkte & Performance",
        "keywords": "neutral seitwärts stabil unverändert",
        "markup": (
            '<line x1="3" y1="12" x2="20" y2="12"/>'
            '<polyline points="15 7 20 12 15 17"/>'
        ),
    },
    {
        "id": "bar_chart",
        "label": "Balkendiagramm",
        "category": "Märkte & Performance",
        "keywords": "balken säulen statistik vergleich rendite",
        "markup": (
            '<line x1="4" y1="20" x2="20" y2="20"/>'
            '<rect x="5.5" y="12" width="3" height="8" rx="0.8"/>'
            '<rect x="10.5" y="6" width="3" height="14" rx="0.8"/>'
            '<rect x="15.5" y="9" width="3" height="11" rx="0.8"/>'
        ),
    },
    {
        "id": "pulse",
        "label": "Volatilität / Puls",
        "category": "Märkte & Performance",
        "keywords": "volatilität vix schwankung risiko dynamik",
        "markup": '<polyline points="2 12 6 12 9 5 14 19 17 12 22 12"/>',
    },
    # --- Makro & Zinsen ---
    {
        "id": "central_bank",
        "label": "Zentralbank",
        "category": "Makro & Zinsen",
        "keywords": "snb fed ezb notenbank institution bank säulen",
        "markup": (
            '<polygon points="12 3 3 8 21 8 12 3"/>'
            '<line x1="5" y1="10" x2="5" y2="17"/>'
            '<line x1="9.6" y1="10" x2="9.6" y2="17"/>'
            '<line x1="14.4" y1="10" x2="14.4" y2="17"/>'
            '<line x1="19" y1="10" x2="19" y2="17"/>'
            '<line x1="3" y1="20" x2="21" y2="20"/>'
            '<line x1="4" y1="17" x2="20" y2="17"/>'
        ),
    },
    {
        "id": "percent",
        "label": "Zins / Prozent",
        "category": "Makro & Zinsen",
        "keywords": "leitzins rendite kupon prozent zinssatz",
        "markup": (
            '<line x1="18" y1="6" x2="6" y2="18"/>'
            '<circle cx="7.5" cy="7.5" r="2.5"/>'
            '<circle cx="16.5" cy="16.5" r="2.5"/>'
        ),
    },
    {
        "id": "globe",
        "label": "Weltwirtschaft",
        "category": "Makro & Zinsen",
        "keywords": "global welt wirtschaft international schwellenländer",
        "markup": (
            '<circle cx="12" cy="12" r="9"/>'
            '<ellipse cx="12" cy="12" rx="4" ry="9"/>'
            '<line x1="3.5" y1="9" x2="20.5" y2="9"/>'
            '<line x1="3.5" y1="15" x2="20.5" y2="15"/>'
        ),
    },
    {
        "id": "gauge",
        "label": "Konjunktur / Ausblick",
        "category": "Makro & Zinsen",
        "keywords": "bip konjunktur tacho pmi sentiment indikator",
        "markup": (
            '<path d="M4 17a8 8 0 1 1 16 0"/>'
            '<line x1="12" y1="15" x2="16.5" y2="10.5"/>'
            '<circle cx="12" cy="15" r="1.5"/>'
        ),
    },
    {
        "id": "inflation",
        "label": "Inflation / Preise",
        "category": "Makro & Zinsen",
        "keywords": "inflation teuerung cpi preis kaufkraft",
        "markup": (
            '<path d="M12 3H5a2 2 0 0 0-2 2v7l8.5 8.5a2 2 0 0 0 2.8 0l5.2-5.2a2 2 0 0 0 0-2.8L12 3z"/>'
            '<circle cx="7.5" cy="7.5" r="1.2"/>'
        ),
    },
    # --- Anlageklassen ---
    {
        "id": "coins",
        "label": "Währung / Liquidität",
        "category": "Anlageklassen",
        "keywords": "chf usd eur währung cash liquidität geld münzen",
        "markup": (
            '<ellipse cx="10" cy="7" rx="6" ry="2.5"/>'
            '<path d="M4 7v4c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5V7"/>'
            '<path d="M4 11v4c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5v-4"/>'
            '<path d="M16 10.5c2.28.4 4 1.35 4 2.5v4c0 1.38-2.69 2.5-6 2.5-1.54 0-2.94-.24-4-.64"/>'
        ),
    },
    {
        "id": "bond",
        "label": "Obligationen / Anleihen",
        "category": "Anlageklassen",
        "keywords": "anleihe obligation bond credit zertifikat laufzeit",
        "markup": (
            '<path d="M7 3h8l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
            '<polyline points="15 3 15 7 19 7"/>'
            '<line x1="9" y1="11" x2="15" y2="11"/>'
            '<line x1="9" y1="15" x2="13" y2="15"/>'
        ),
    },
    {
        "id": "equity",
        "label": "Aktien / Equity",
        "category": "Anlageklassen",
        "keywords": "aktie börse smi dividende unternehmen",
        "markup": (
            '<rect x="3" y="4" width="18" height="16" rx="2"/>'
            '<polyline points="6.5 14.5 10 11 13 13 17.5 8.5"/>'
            '<polyline points="14.5 8.5 17.5 8.5 17.5 11.5"/>'
        ),
    },
    {
        "id": "real_estate",
        "label": "Immobilien",
        "category": "Anlageklassen",
        "keywords": "immobilien fonds realwerte gebäude hypothek",
        "markup": (
            '<rect x="4" y="4" width="9" height="16" rx="1"/>'
            '<path d="M13 9h7v11h-7"/>'
            '<line x1="7" y1="8" x2="10" y2="8"/>'
            '<line x1="7" y1="12" x2="10" y2="12"/>'
            '<line x1="7" y1="16" x2="10" y2="16"/>'
            '<line x1="16" y1="13" x2="17" y2="13"/>'
            '<line x1="16" y1="16" x2="17" y2="16"/>'
        ),
    },
    {
        "id": "gold",
        "label": "Gold / Rohstoffe",
        "category": "Anlageklassen",
        "keywords": "gold rohstoffe edelmetall commodities barren",
        "markup": (
            '<polygon points="6 4 18 4 21 9.5 12 20 3 9.5 6 4"/>'
            '<line x1="3" y1="9.5" x2="21" y2="9.5"/>'
            '<polyline points="8.5 4 12 9.5 15.5 4"/>'
            '<line x1="12" y1="9.5" x2="12" y2="20"/>'
        ),
    },
    # --- Portfolio, Risiko & Strategie ---
    {
        "id": "pie_chart",
        "label": "Allokation / Mix",
        "category": "Portfolio & Strategie",
        "keywords": "diversifikation asset allocation quote portfolio",
        "markup": (
            '<path d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5V12z"/>'
            '<path d="M13 3.2A8.5 8.5 0 0 1 20.8 11H13z"/>'
        ),
    },
    {
        "id": "shield",
        "label": "Absicherung / Risiko",
        "category": "Portfolio & Strategie",
        "keywords": "schutz risiko defensiv qualität absicherung",
        "markup": (
            '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.3-7.5 9.5-4.3-1.2-7.5-4.9-7.5-9.5V6L12 3z"/>'
            '<polyline points="9 12 11.2 14.2 15.2 9.8"/>'
        ),
    },
    {
        "id": "clock",
        "label": "Zeithorizont",
        "category": "Portfolio & Strategie",
        "keywords": "laufzeit horizont dauer quartal jahr zeit",
        "markup": (
            '<circle cx="12" cy="12" r="9"/>'
            '<polyline points="12 7 12 12 15.5 14"/>'
        ),
    },
    {
        "id": "esg_leaf",
        "label": "Nachhaltigkeit / ESG",
        "category": "Portfolio & Strategie",
        "keywords": "esg nachhaltig grün klima stewardship",
        "markup": (
            '<path d="M19 4C11 4 6 8.5 6 15.5a4.5 4.5 0 0 0 4.5 4.5C17 20 20 14 19 4z"/>'
            '<path d="M5 20c2.5-3 6-6 10-8"/>'
        ),
    },
    {
        "id": "target",
        "label": "Fokus / Kursziel",
        "category": "Portfolio & Strategie",
        "keywords": "ziel fokus strategie chance benchmark",
        "markup": (
            '<circle cx="12" cy="12" r="8.5"/>'
            '<circle cx="12" cy="12" r="4.5"/>'
            '<circle cx="12" cy="12" r="1.2"/>'
        ),
    },
    {
        "id": "check_circle",
        "label": "Positiv / Übergewichten",
        "category": "Portfolio & Strategie",
        "keywords": "positiv übergewichten empfehlung ok stark",
        "markup": (
            '<circle cx="12" cy="12" r="9"/>'
            '<polyline points="8.5 12.2 11 14.7 15.8 9.5"/>'
        ),
    },
    {
        "id": "alert_triangle",
        "label": "Vorsicht / Hinweis",
        "category": "Portfolio & Strategie",
        "keywords": "warnung risiko untergewichten achtung volatil",
        "markup": (
            '<path d="M10.4 4.3L3.1 17.2a1.8 1.8 0 0 0 1.6 2.7h14.6a1.8 1.8 0 0 0 1.6-2.7L13.6 4.3a1.8 1.8 0 0 0-3.2 0z"/>'
            '<line x1="12" y1="9.5" x2="12" y2="13.5"/>'
            '<circle cx="12" cy="16.5" r="0.8"/>'
        ),
    },
]

_ICON_BY_ID: dict[str, dict[str, Any]] = {item["id"]: item for item in KPI_ICONS}
VALID_KPI_ICON_IDS: tuple[str, ...] = tuple(_ICON_BY_ID.keys())


def get_kpi_tone_palette(tone: str | None) -> dict[str, str]:
    """Gibt das Farbset (accent, tint, badge, border) für einen Tone zurück."""
    key = str(tone or "navy").strip().lower()
    return dict(KPI_TONES.get(key, KPI_TONES["navy"]))


def normalize_kpi_icon_id(icon_id: str | None) -> str:
    """Normalisiert eine Icon-ID (leerer String = kein Icon)."""
    s = str(icon_id or "").strip().lower()
    if not s or s == "none":
        return ""
    return s if s in _ICON_BY_ID else "trend_up"


def render_kpi_icon_svg(
    icon_id: str | None,
    *,
    stroke_color: str = "#002855",
    size_px: int = 24,
    badge_bg: str | None = None,
) -> str:
    """
    Erzeugt sauberes Monoline-SVG für Typst, HTML und DOCX-PNG-Konvertierung.
    Optional mit abgerundetem Badge-Hintergrund (`badge_bg`) für den DOCX-Export.
    """
    norm_id = normalize_kpi_icon_id(icon_id)
    if not norm_id:
        return ""
    icon_def = _ICON_BY_ID[norm_id]
    safe_stroke = html.escape(str(stroke_color or "#002855"), quote=True)
    markup = icon_def["markup"]

    if badge_bg:
        safe_bg = html.escape(str(badge_bg), quote=True)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size_px}" height="{size_px}" '
            f'viewBox="0 0 36 36" fill="none">'
            f'<rect x="0" y="0" width="36" height="36" rx="7" fill="{safe_bg}"/>'
            f'<g transform="translate(6,6)" stroke="{safe_stroke}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{markup}</g>'
            f"</svg>"
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size_px}" height="{size_px}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{safe_stroke}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{markup}</svg>'
    )


def get_kpi_icons_catalog() -> dict[str, Any]:
    """Exportiert Icons und Farb-Tones als JSON-kompatibles Dictionary für das Frontend."""
    return {
        "icons": KPI_ICONS,
        "tones": list(KPI_TONES.values()),
    }
