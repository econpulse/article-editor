"""
Pydantic-Datenmodelle für das LUKB Investment Office CMS.
Validiert und normalisiert Artikel-Metadaten sowie alle Drag-and-Drop Content-Blöcke.
"""

from __future__ import annotations

import math
import uuid
from datetime import date
from typing import Annotated, Any, Literal, Optional, Union
from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

from services.kpi_icons import VALID_KPI_TONES, normalize_kpi_icon_id


def _new_block_id() -> str:
    return f"blk_{uuid.uuid4().hex[:10]}"


LEGACY_LUKB_DISCLAIMER = (
    "Diese Publikation dient ausschliesslich Informations- und Marketingzwecken der "
    "Luzerner Kantonalbank AG (LUKB) und stellt keine Anlageberatung oder Empfehlung dar."
)

DEFAULT_LUKB_DISCLAIMER = (
    "Die in diesem Dokument verwendeten Informationen stammen aus Quellen, welche die Luzerner Kantonalbank als zuverlässig erachtet. "
    "Trotz sorgfältiger Bearbeitung übernimmt die LUKB keine Garantie für die Richtigkeit und Vollständigkeit dieser Veröffentlichung "
    "und der dargestellten Informationen. Die Publikation hat ausschliesslich informativen Charakter und ersetzt keinesfalls die "
    "persönliche Beratung durch unsere Kundenberater vor einem allfälligen Anlage- oder anderen Entscheid. Die Informationen können "
    "sich jederzeit und ohne vorherige Ankündigung ändern."
)


class AuthorItem(BaseModel):
    name: str = Field(default="", description="Vor- und Nachname des Autors")
    role: str = Field(default="", description="Funktion im Investment Office")


class ArticleMetadata(BaseModel):
    title: str = Field(default="Neue Publikation", description="Gesamttitel des Artikels")
    subtitle: str = Field(default="", description="Dachzeile / Untertitel der Publikation")
    lead: str = Field(default="", description="Lead-Text / Management Summary")
    publication_date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="Publikationsdatum (ISO oder Anzeigeformat)",
    )
    category: str = Field(default="", description="Rubrik / Publikationsreihe")
    header_series: str = Field(
        default="Investment Office News",
        description="Kopfzeile oben rechts (Investment Office News oder Finanzanalyse)",
    )
    tags: list[str] = Field(default_factory=list, description="Themen-Tags / Schlagwörter")
    authors: list[AuthorItem] = Field(default_factory=list, description="Autorenliste")
    disclaimer: str = Field(
        default=DEFAULT_LUKB_DISCLAIMER,
        description="Rechtlicher Hinweis im Fussbereich",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags_seq(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, (list, tuple)):
            return [str(t).strip() for t in v if str(t).strip()]
        return []

    @field_validator("authors", mode="before")
    @classmethod
    def validate_authors_seq(cls, v: Any) -> list[Any]:
        if isinstance(v, (list, tuple)):
            return list(v)
        return []

    @field_validator("header_series", mode="before")
    @classmethod
    def validate_header_series(cls, v: Any) -> str:
        if not v or not str(v).strip():
            return "Investment Office News"
        return str(v).strip()


class HeadingBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["heading"] = "heading"
    level: int = Field(default=2, ge=1, le=3)
    text: str = Field(default="")


class RichTextBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["richtext"] = "richtext"
    html: str = Field(default="<p></p>")


class BoxStartBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["box_start"] = "box_start"


class BoxEndBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["box_end"] = "box_end"


FullPositionMode = Literal["auto", "top", "bottom", "inline"]
MediaShareMode = Literal["no", "internal", "external"]


def _normalize_full_position(v: Any) -> str:
    s = str(v or "auto").strip().lower()
    return s if s in ("auto", "top", "bottom", "inline") else "auto"


def _normalize_anchor_to(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() != "auto" else None


def _normalize_share_mode(v: Any) -> str:
    if isinstance(v, bool):
        return "internal" if v else "no"
    s = str(v or "no").strip().lower()
    if s in ("internal", "external"):
        return s
    if s in ("yes", "ja", "true", "1"):
        return "internal"
    return "no"


class MarginAnchorBlockBase(BaseModel):
    """Gemeinsame Basis für Inhaltsblöcke mit Spalten-/Vollbreiten-Layout und Tufte-Verankerung."""

    layout: Literal["column", "full"] = Field(
        default="column",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )
    full_position: FullPositionMode = Field(
        default="auto",
        description="Seitenposition bei 2-spaltigem Layout ('auto', 'top', 'bottom', 'inline')",
    )
    anchor_to: Optional[str] = Field(
        default=None,
        description="Block-ID des Bezugsabsatzes (Hauptspalte), an dem dieses Randelement verankert ist",
    )
    share_in_media_library: MediaShareMode = Field(
        default="no",
        description="Block als eigenständige Vorlage in der Mediathek teilen ('no', 'internal', 'external')",
    )
    shared_media_id: Optional[str] = Field(
        default=None,
        description="ID des verknüpften Mediathek-Eintrags, falls dieser Block geteilt wird",
    )
    source_media_id: Optional[str] = Field(
        default=None,
        description="ID des Mediathek-Eintrags, aus dem dieser Block als Kopie eingefügt wurde",
    )

    @field_validator("full_position", mode="before")
    @classmethod
    def validate_full_pos(cls, v: Any) -> str:
        return _normalize_full_position(v)

    @field_validator("anchor_to", mode="before")
    @classmethod
    def validate_anchor_to(cls, v: Any) -> Optional[str]:
        return _normalize_anchor_to(v)

    @field_validator("share_in_media_library", mode="before")
    @classmethod
    def validate_share_in_media_library(cls, v: Any) -> str:
        return _normalize_share_mode(v)


class ChartYAxisConfig(BaseModel):
    """Optionale manuelle Skalierung für eine Y-Achse (None = Auto)."""

    min: Optional[float] = Field(default=None, description="Manuelles Achsen-Minimum (None = Auto)")
    max: Optional[float] = Field(default=None, description="Manuelles Achsen-Maximum (None = Auto)")
    step: Optional[float] = Field(default=None, description="Manuelle Schrittweite (None = Auto)")

    @field_validator("min", "max", "step", mode="before")
    @classmethod
    def validate_opt_float(cls, v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None

    @field_validator("step", mode="after")
    @classmethod
    def validate_positive_step(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            return None
        return v


class ChartBlockBase(MarginAnchorBlockBase):
    """Gemeinsame Basis für Diagramm-Blöcke (DB-Chart und Custom-Chart)."""

    title: str = Field(default="", description="Grafik-Titel")
    subtitle: str = Field(default="", description="Grafik-Untertitel (z.B. Einheit, Zeitraum)")
    chart_height_mm: int = Field(
        default=36,
        description="Höhe der eigentlichen Chartfläche (Y-Achsenbereich) in Millimeter (2mm-Schritte, Default: 36mm)",
    )
    palette: Literal["lukb_classic", "lukb_blues"] = Field(
        default="lukb_classic",
        description="ID der gewählten Farbpalette ('lukb_classic' oder 'lukb_blues')",
    )
    legend_columns: Optional[int] = Field(
        default=None,
        description="Anzahl Spalten für die Legendeneinträge (None = automatisch/kompakt)",
    )
    show_legend: bool = Field(
        default=True,
        description="Ob die Legende im Chart angezeigt wird",
    )
    y_axis_left: ChartYAxisConfig = Field(
        default_factory=ChartYAxisConfig,
        description="Optionale manuelle Skalierung der linken Y-Achse",
    )
    y_axis_right: ChartYAxisConfig = Field(
        default_factory=ChartYAxisConfig,
        description="Optionale manuelle Skalierung der rechten Y-Achse",
    )
    asset_id: str = Field(default="", description="Gecachtes SVG-Asset in io_assets")

    @field_validator("y_axis_left", "y_axis_right", mode="before")
    @classmethod
    def validate_y_axis_cfg(cls, v: Any) -> Any:
        return {} if v is None else v

    @field_validator("chart_height_mm", mode="before")
    @classmethod
    def validate_chart_height_mm(cls, v: Any) -> int:
        try:
            val = int(round(float(v)))
        except (ValueError, TypeError):
            val = 36
        val = max(20, min(120, val))
        if val % 2 != 0:
            val = int(round(val / 2.0) * 2)
        return val

    @field_validator("palette", mode="before")
    @classmethod
    def validate_palette(cls, v: Any) -> str:
        s = str(v or "lukb_classic").strip()
        return s if s in ("lukb_classic", "lukb_blues") else "lukb_classic"

    @field_validator("legend_columns", mode="before")
    @classmethod
    def validate_legend_columns(cls, v: Any) -> Optional[int]:
        if v is None or v == "" or v == "auto":
            return None
        try:
            n = int(v)
            return max(1, min(6, n))
        except (ValueError, TypeError):
            return None

    @field_validator("show_legend", mode="before")
    @classmethod
    def validate_show_legend(cls, v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return s not in ("false", "0", "no", "none", "off")


class FigureBlock(MarginAnchorBlockBase):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["figure"] = "figure"
    title: str = Field(default="", description="Grafik-Titel")
    subtitle: str = Field(default="", description="Grafik-Untertitel (z.B. Einheit, Zeitraum)")
    source: str = Field(default="Quelle: Luzerner Kantonalbank, LSEG", description="Quellenangabe")
    asset_id: str = Field(default="", description="UUID des hochgeladenen Grafik-Assets in der DB")
    scale_pct: int = Field(default=100, description="Skalierung in 5%-Schritten (75 bis 100 %)")
    scale_mode: Literal["proportional", "squeeze_y", "original"] = Field(
        default="proportional",
        description="Skalierungsmodus ('proportional' = linksbündig mit Luft rechts, 'squeeze_y' = vertikal stauchen, 'original' = Originalgrösse falls kleiner)",
    )

    @field_validator("scale_pct", mode="before")
    @classmethod
    def validate_scale_pct(cls, v: Any) -> int:
        if v is None or v == "":
            return 100
        try:
            num = int(round(float(v) / 5.0) * 5)
        except (TypeError, ValueError):
            return 100
        return max(75, min(100, num))

    @field_validator("scale_mode", mode="before")
    @classmethod
    def validate_scale_mode(cls, v: Any) -> str:
        s = str(v or "proportional").strip().lower()
        if s in ("squeeze_y", "original"):
            return s
        return "proportional"


ChartSeriesType = Literal["line", "step", "dot", "area", "bar", "stacked_bar"]

_VALID_CHART_TYPES = ("line", "step", "dot", "area", "bar", "stacked_bar")


class TimeSeriesItem(BaseModel):
    ticker: str = Field(default="", description="Ticker in der Tabelle ts_db")
    chart_type: ChartSeriesType = Field(default="line", description="Primäre Darstellungsart der Zeitreihe")
    chart_types: list[ChartSeriesType] = Field(
        default_factory=list,
        description="Eine oder mehrere kombinierte Darstellungsarten derselben Zeitreihe (z.B. ['line', 'dot'] oder ['step', 'area'])",
    )
    label: str = Field(default="", description="Optionaler Legenden-Name (überschreibt ts_db.name)")
    y_axis: Literal["left", "right"] = Field(default="left", description="Zugewiesene Y-Achse ('left' oder 'right')")

    @field_validator("y_axis", mode="before")
    @classmethod
    def validate_y_axis(cls, v: Any) -> str:
        return "right" if str(v or "left").strip().lower() == "right" else "left"

    @model_validator(mode="before")
    @classmethod
    def normalize_chart_types(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        raw_types = out.get("chart_types")
        single_type = out.get("chart_type") or "line"
        if single_type not in _VALID_CHART_TYPES:
            single_type = "line"

        cleaned_types: list[str] = []
        if isinstance(raw_types, (list, tuple)):
            for t in raw_types:
                ts = str(t).strip()
                if ts in _VALID_CHART_TYPES and ts not in cleaned_types:
                    cleaned_types.append(ts)

        if not cleaned_types:
            cleaned_types = [single_type]

        out["chart_types"] = cleaned_types
        out["chart_type"] = cleaned_types[0]
        return out


class DbChartBlock(ChartBlockBase):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["db_chart"] = "db_chart"
    source: str = Field(default="Quelle: Luzerner Kantonalbank, LSEG", description="Quellenangabe")
    start_date: str = Field(default="2022-01-01", description="Startdatum im Chart (YYYY-MM-DD)")
    rebasing: Literal["none", "index_100"] = Field(
        default="none",
        description="'none' = Originalwerte, 'index_100' = Indexiert auf 100 am Startdatum",
    )
    series: list[TimeSeriesItem] = Field(
        default_factory=lambda: [
            TimeSeriesItem(ticker="SNB_RATE", chart_type="line", label=""),
            TimeSeriesItem(ticker="ECB_RATE", chart_type="line", label=""),
            TimeSeriesItem(ticker="FED_RATE", chart_type="line", label=""),
        ],
        description="Bis zu 5 Zeitreihen aus ts_db",
    )

    @field_validator("series", mode="before")
    @classmethod
    def validate_series_seq(cls, v: Any) -> list[Any]:
        if isinstance(v, (list, tuple)):
            return list(v)[:5]
        return []


class CustomChartSeriesItem(BaseModel):
    field: str = Field(default="", description="Spaltenname oder Spalten-Index in den Rohdaten")
    label: str = Field(default="", description="Benutzerdefiniertes Label für die Legende")
    chart_type: ChartSeriesType = Field(default="line", description="Darstellungsart für Zeitreihen")
    enabled: bool = Field(default=True, description="Ob die Serie im Chart dargestellt wird")
    y_axis: Literal["left", "right"] = Field(default="left", description="Zugewiesene Y-Achse ('left' oder 'right')")

    @field_validator("y_axis", mode="before")
    @classmethod
    def validate_y_axis(cls, v: Any) -> str:
        return "right" if str(v or "left").strip().lower() == "right" else "left"


class CustomChartBlock(ChartBlockBase):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["custom_chart"] = "custom_chart"
    source: str = Field(default="Quelle: Luzerner Kantonalbank, LSEG", description="Quellenangabe")
    chart_type: Literal["timeseries", "category_bar", "doughnut", "pie"] = Field(
        default="category_bar",
        description="Art des Diagramms: timeseries, category_bar, doughnut, pie",
    )
    has_header: bool = Field(default=True, description="Erste Zeile als Spaltenüberschriften interpretieren")
    x_col: str = Field(default="", description="Name/Index der Spalte für X-Achse / Kategorie / Datum")
    series: list[CustomChartSeriesItem] = Field(default_factory=list, description="Konfigurierte Datenreihen")
    raw_tsv: str = Field(default="", description="Rohdaten aus der Zwischenablage (TSV/CSV)")
    data_columns: list[str] = Field(default_factory=list, description="Erkannte Spaltenköpfe")
    data_rows: list[list[Any]] = Field(default_factory=list, description="Geparste Tabellenzeilen")
    doughnut_hole_pct: int = Field(default=55, ge=0, le=85, description="Lochgrösse bei Doughnut in % (0 = Pie)")
    legend_position: Literal["bottom", "right"] = Field(
        default="bottom",
        description="Position der Legende ('bottom' = unterhalb, 'right' = rechts neben der Grafik)",
    )
    orientation: Literal["vertical", "horizontal"] = Field(
        default="vertical",
        description="Ausrichtung bei Säulen-/Balkendiagrammen ('vertical' = Säulen von unten nach oben, 'horizontal' = Balken von links nach rechts)",
    )
    color_by_category: bool = Field(
        default=False,
        description="Unterschiedliche Farben für jede Kategorie/Balken aus der Palette verwenden",
    )
    bar_mode: Literal["grouped", "stacked"] = Field(default="grouped", description="Säulen-Modus bei Kategorie-Charts")

    @field_validator("legend_position", mode="before")
    @classmethod
    def validate_legend_position(cls, v: Any) -> str:
        s = str(v or "bottom").strip().lower()
        return s if s in ("bottom", "right") else "bottom"

    @field_validator("orientation", mode="before")
    @classmethod
    def validate_orientation(cls, v: Any) -> str:
        s = str(v or "vertical").strip().lower()
        return s if s in ("vertical", "horizontal") else "vertical"

    @field_validator("color_by_category", mode="before")
    @classmethod
    def validate_color_by_category(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        return str(v or "").strip().lower() in ("true", "1", "yes")


def _equal_percentage_widths(n: int) -> list[float]:
    if n <= 0:
        return []
    base = math.floor(1000.0 / n) / 10.0
    extra_tenths = int(round((100.0 - base * n) * 10.0))
    return [
        round(base + (0.1 if idx < extra_tenths else 0.0), 1)
        for idx in range(n)
    ]


class TableColumn(BaseModel):
    field: str
    title: str
    align: Literal["left", "center", "right", "justify"] = "left"
    width: float = Field(default=100.0, ge=0.1, le=100.0, description="Relative Spaltenbreite in Prozent")

    @field_validator("align", mode="before")
    @classmethod
    def validate_align(cls, v: Any) -> str:
        s = str(v or "left").strip().lower()
        return s if s in ("left", "center", "right", "justify") else "left"

    @field_validator("width", mode="before")
    @classmethod
    def validate_width(cls, v: Any) -> float:
        if v is None or v == "":
            return 100.0
        try:
            val = float(v)
        except (TypeError, ValueError):
            return 100.0
        if math.isnan(val) or math.isinf(val) or val <= 0:
            return 100.0
        return max(0.1, min(100.0, round(val, 1)))


class TableMerge(BaseModel):
    row: int = Field(ge=0, description="Startzeile (0-basiert, Tabellen-Body)")
    col: int = Field(ge=0, description="Startspalte (0-basiert)")
    rowspan: int = Field(default=1, ge=1, description="Anzahl verbundener Zeilen")
    colspan: int = Field(default=1, ge=1, description="Anzahl verbundener Spalten")


class TableBlock(MarginAnchorBlockBase):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["table"] = "table"
    title: str = Field(default="", description="Tabellen-Titel")
    subtitle: str = Field(default="", description="Tabellen-Untertitel")
    source: str = Field(default="Quelle: Luzerner Kantonalbank, LSEG", description="Tabellen-Quelle / Fussnote")
    highlight_last_row: bool = Field(default=False, description="Letzte Zeile als Total/Summe hervorheben")
    show_header: bool = Field(default=True, description="Tabellen-Kopfzeile anzeigen")
    table_design: Literal["standard", "lukb_design"] = Field(
        default="lukb_design",
        description="Tabellen-Design (standard = LUKB Navy, lukb_design = LUKB Design gemäss CD)",
    )
    font_size_step: Literal[0, -1, -2] = Field(
        default=0,
        description="Relative Schriftgrösse für Kopfzeile & Body (0 = Standard, -1 = 1 Stufe kleiner, -2 = 2 Stufen kleiner)",
    )
    row_spacing_step: Literal[0, -1, -2] = Field(
        default=0,
        description="Vertikaler Zeilenabstand / Zellen-Padding oben & unten (0 = Standard, -1 = Enger, -2 = Sehr eng)",
    )
    columns: list[TableColumn] = Field(
        default_factory=lambda: [
            TableColumn(field="col_1", title="Anlageklasse", align="left", width=33.4),
            TableColumn(field="col_2", title="Aktuell", align="right", width=33.3),
            TableColumn(field="col_3", title="Veränderung", align="right", width=33.3),
        ]
    )
    rows: list[dict[str, str]] = Field(
        default_factory=lambda: [
            {"col_1": "Liquidität", "col_2": "5.0 %", "col_3": "0.0 %"},
            {"col_1": "Obligationen CHF", "col_2": "28.0 %", "col_3": "-1.5 %"},
            {"col_1": "Aktien Schweiz", "col_2": "22.0 %", "col_3": "+1.5 %"},
        ]
    )
    merges: list[TableMerge] = Field(
        default_factory=list,
        description="Verbundene Zellbereiche im Tabellen-Body",
    )

    @model_validator(mode="after")
    def normalize_table_merges(self) -> "TableBlock":
        if not self.merges:
            return self
        row_count = len(self.rows)
        col_count = len(self.columns)
        if row_count == 0 or col_count == 0:
            self.merges = []
            return self
        occupied: set[tuple[int, int]] = set()
        cleaned: list[TableMerge] = []
        for m in self.merges:
            if m.row < 0 or m.row >= row_count or m.col < 0 or m.col >= col_count:
                continue
            rspan = min(m.rowspan, row_count - m.row)
            cspan = min(m.colspan, col_count - m.col)
            if rspan <= 1 and cspan <= 1:
                continue
            cells = [
                (r, c)
                for r in range(m.row, m.row + rspan)
                for c in range(m.col, m.col + cspan)
            ]
            if any(pos in occupied for pos in cells):
                continue
            occupied.update(cells)
            cleaned.append(TableMerge(row=m.row, col=m.col, rowspan=rspan, colspan=cspan))
        self.merges = cleaned
        return self

    @model_validator(mode="before")
    @classmethod
    def normalize_table_column_widths(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw_cols = data.get("columns")
        if not isinstance(raw_cols, (list, tuple)) or len(raw_cols) == 0:
            return data

        cols_list = list(raw_cols)
        has_any_width = any(isinstance(c, dict) and c.get("width") is not None for c in cols_list)
        if not has_any_width:
            eq_widths = _equal_percentage_widths(len(cols_list))
            out = dict(data)
            new_cols = []
            for idx, c in enumerate(cols_list):
                if isinstance(c, dict):
                    c_copy = dict(c)
                    c_copy["width"] = eq_widths[idx]
                    new_cols.append(c_copy)
                else:
                    new_cols.append(c)
            out["columns"] = new_cols
            return out

        # Falls ältere Daten noch kleine Gewichtungsfaktoren (z.B. 1.4, 1.0, 1.0) haben -> auf 100% normalisieren
        numeric_widths: list[float] = []
        for c in cols_list:
            if isinstance(c, dict) and c.get("width") is not None:
                try:
                    w = float(c["width"])
                    numeric_widths.append(w if w > 0 else 1.0)
                except (TypeError, ValueError):
                    numeric_widths.append(1.0)
            else:
                numeric_widths.append(1.0)
        total_w = sum(numeric_widths)
        if len(cols_list) > 1 and 0 < total_w < 20.0:
            out = dict(data)
            new_cols = []
            running_sum = 0.0
            for idx, c in enumerate(cols_list):
                if isinstance(c, dict):
                    c_copy = dict(c)
                    if idx < len(cols_list) - 1:
                        pct = round((numeric_widths[idx] / total_w) * 100.0, 1)
                        running_sum = round(running_sum + pct, 1)
                    else:
                        pct = round(max(0.1, 100.0 - running_sum), 1)
                    c_copy["width"] = pct
                    new_cols.append(c_copy)
                else:
                    new_cols.append(c)
            out["columns"] = new_cols
            return out
        return data

    @field_validator("table_design", mode="before")
    @classmethod
    def validate_table_design(cls, v: Any) -> str:
        s = str(v or "lukb_design").strip().lower()
        return "standard" if s == "standard" else "lukb_design"

    @field_validator("font_size_step", "row_spacing_step", mode="before")
    @classmethod
    def validate_font_size_step(cls, v: Any) -> int:
        if v is None or v == "":
            return 0
        try:
            step = int(float(v))
        except (TypeError, ValueError):
            return 0
        if step >= 0:
            return 0
        if step <= -2:
            return -2
        return -1

    @field_validator("columns", "rows", mode="before")
    @classmethod
    def validate_table_seqs(cls, v: Any) -> list[Any]:
        if isinstance(v, (list, tuple)):
            return list(v)
        return []


class CalloutBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["callout"] = "callout"
    title: str = Field(default="Kernaussagen", description="Titel der Highlight-Box")
    html: str = Field(
        default="<ul><li>Wichtige Erkenntnis des Investment Office</li></ul>",
        description="Inhalt der Callout-Box",
    )


class SpacerBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["spacer"] = "spacer"
    height_mm: int = Field(
        default=8,
        description="Vertikaler Abstand in Millimeter (in 2mm-Schritten, Default: 8mm)",
    )

    @field_validator("height_mm", mode="before")
    @classmethod
    def validate_height_mm(cls, v: Any) -> int:
        try:
            val = int(round(float(v)))
        except (ValueError, TypeError):
            val = 8
        val = max(2, min(80, val))
        if val % 2 != 0:
            val = int(round(val / 2.0) * 2)
        return val


class ColbreakBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["colbreak"] = "colbreak"
    mode: Literal["column", "page"] = Field(
        default="column",
        description="Umbruch-Art: 'column' (Spaltenumbruch) oder 'page' (Seitenumbruch)",
    )


class QuoteBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["quote"] = "quote"
    quote: str = Field(default="", description="Zitat-Text")
    author: str = Field(default="", description="Urheber / Autor des Zitats")
    source: str = Field(default="", description="Quelle / Kontext / Funktion")
    layout: Literal["column", "full"] = Field(
        default="column",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )


class DividerBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["divider"] = "divider"
    style: Literal["solid", "dashed", "dots"] = Field(
        default="solid",
        description="Darstellungsart der Trennlinie ('solid', 'dashed', 'dots')",
    )


class FootnotesBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["footnotes"] = "footnotes"
    title: str = Field(default="Anmerkungen & Quellen", description="Titel des Fussnotenblocks")
    items: list[dict[str, str]] = Field(
        default_factory=lambda: [
            {"num": "1", "text": "Quelle oder methodische Anmerkung zu den Daten."},
        ],
        description="Liste von Fussnoteneinträgen [{'num': '1', 'text': '...'}]",
    )
    layout: Literal["column", "full"] = Field(
        default="column",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )

    @field_validator("items", mode="before")
    @classmethod
    def validate_footnotes_items(cls, v: Any) -> list[dict[str, str]]:
        if not isinstance(v, (list, tuple)):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, dict):
                cleaned.append({
                    "num": str(item.get("num", "")),
                    "text": str(item.get("text", "")),
                })
        return cleaned


class GlossaryBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["glossary"] = "glossary"
    title: str = Field(default="Glossar & Begriffserklärungen", description="Titel des Glossarblocks")
    auto_collect: bool = Field(default=True, description="Automatisch alle im Artikel markierten Begriffe sammeln")
    custom_items: list[dict[str, str]] = Field(
        default_factory=list,
        description="Manuell definierte Glossar-Einträge [{'term': '...', 'definition': '...'}]",
    )
    layout: Literal["column", "full"] = Field(
        default="column",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )

    @field_validator("custom_items", mode="before")
    @classmethod
    def validate_custom_items(cls, v: Any) -> list[dict[str, str]]:
        if not isinstance(v, (list, tuple)):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, dict):
                cleaned.append({
                    "term": str(item.get("term", "")),
                    "definition": str(item.get("definition", "")),
                })
        return cleaned


class PublicationItem(BaseModel):
    article_id: str = Field(default="")
    title: str = Field(default="")
    subtitle: str = Field(default="")
    date: str = Field(default="")
    category: str = Field(default="")
    url: str = Field(default="", description="Optionale URL / Querverweis auf das Dokument")
    enabled: bool = Field(default=True)


class PublicationsBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["publications"] = "publications"
    title: str = Field(default="Weitere Publikationen", description="Titel des Blocks")
    items: list[dict[str, Any]] = Field(default_factory=list, description="Liste von Publikationseinträgen")
    layout: Literal["column", "full"] = Field(
        default="column",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )

    @field_validator("items", mode="before")
    @classmethod
    def validate_publication_items(cls, v: Any) -> list[dict[str, Any]]:
        if not isinstance(v, (list, tuple)):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, dict):
                cleaned.append({
                    "article_id": str(item.get("article_id", "")),
                    "title": str(item.get("title", "")),
                    "subtitle": str(item.get("subtitle", "")),
                    "date": str(item.get("date", "")),
                    "category": str(item.get("category", "")),
                    "url": str(item.get("url", "")).strip(),
                    "enabled": bool(item.get("enabled", True)),
                })
        return cleaned


MediaPositionMode = Literal["auto", "left", "right", "top", "bottom"]
MediaTextMediaType = Literal["figure", "db_chart", "custom_chart", "table"]
MediaTextStylePreset = Literal["plain", "card", "zebra"]


def _build_default_media_payload(media_type: str) -> dict[str, Any]:
    if media_type == "db_chart":
        return DbChartBlock(layout="column").model_dump()
    if media_type == "custom_chart":
        return CustomChartBlock(layout="column").model_dump()
    if media_type == "table":
        return TableBlock(layout="column").model_dump()
    return FigureBlock(layout="column").model_dump()


def _validate_media_payload(media_type: str, raw_media: Any) -> dict[str, Any]:
    data = dict(raw_media) if isinstance(raw_media, dict) else {}
    data["layout"] = "column"
    if media_type == "db_chart":
        data["type"] = "db_chart"
        return DbChartBlock.model_validate(data).model_dump()
    if media_type == "custom_chart":
        data["type"] = "custom_chart"
        return CustomChartBlock.model_validate(data).model_dump()
    if media_type == "table":
        data["type"] = "table"
        return TableBlock.model_validate(data).model_dump()
    data["type"] = "figure"
    return FigureBlock.model_validate(data).model_dump()


class MediaTextBlock(MarginAnchorBlockBase):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["media_text"] = "media_text"
    layout: Literal["column", "full"] = Field(
        default="full",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )
    full_position: FullPositionMode = Field(
        default="inline",
        description="Seitenposition bei 2-spaltigem Layout ('auto', 'top', 'bottom', 'inline')",
    )
    title: str = Field(default="", description="Optionaler Block-Titel")
    html: str = Field(default="<p></p>", description="Haupttext (RichText-HTML)")
    aside_html: str = Field(
        default="",
        description="Optionale dritte Spalte rechts (z.B. Produktname / ISIN-Link)",
    )
    media_type: MediaTextMediaType = Field(
        default="figure",
        description="Art des eingebetteten Mediums: figure, db_chart, custom_chart, table",
    )
    media_position: MediaPositionMode = Field(
        default="auto",
        description="Position des Mediums relativ zum Text ('auto', 'left', 'right', 'top', 'bottom')",
    )
    media_width_pct: int = Field(
        default=30,
        ge=15,
        le=70,
        description="Breite des Mediums in Prozent bei Nebeneinander-Anordnung",
    )
    aside_width_pct: int = Field(
        default=26,
        ge=15,
        le=45,
        description="Breite der optionalen rechten Zusatzspalte in Prozent",
    )
    style_preset: MediaTextStylePreset = Field(
        default="plain",
        description="Visuelles Preset ('plain', 'card', 'zebra')",
    )
    media: dict[str, Any] = Field(
        default_factory=lambda: _build_default_media_payload("figure"),
        description="Konfiguration des eingebetteten Mediums (figure, db_chart, custom_chart oder table)",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_media_text_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        raw_mtype = str(out.get("media_type") or "figure").strip().lower()
        if raw_mtype not in ("figure", "db_chart", "custom_chart", "table"):
            raw_mtype = "figure"
        out["media_type"] = raw_mtype

        raw_pos = str(out.get("media_position") or "auto").strip().lower()
        if raw_pos not in ("auto", "left", "right", "top", "bottom"):
            raw_pos = "auto"
        out["media_position"] = raw_pos

        raw_style = str(out.get("style_preset") or "plain").strip().lower()
        if raw_style not in ("plain", "card", "zebra"):
            raw_style = "plain"
        out["style_preset"] = raw_style

        if out.get("full_position") is None:
            out["full_position"] = "inline"

        out["media"] = _validate_media_payload(raw_mtype, out.get("media"))
        return out


KpiCardTone = Literal["navy", "blue", "cyan", "gold", "positive", "negative", "berry", "neutral"]
KpiCardsStylePreset = Literal["tint", "card_accent_top", "card_accent_left", "clean"]


class KpiCardItem(BaseModel):
    icon: str = Field(default="trend_up", description="Icon-ID aus dem LUKB Finanz-Icon-Set (leer = ohne Icon)")
    label: str = Field(default="", description="Kurze Dachzeile / Kennzahl-Bezeichnung")
    value: str = Field(default="", description="Dominanter Wert oder kurze Kernaussage")
    subtext: str = Field(default="", description="Optionaler Kontext- oder Delta-Hinweis")
    tone: KpiCardTone = Field(default="navy", description="Dezente Akzentfarbe der Karte")

    @field_validator("icon", mode="before")
    @classmethod
    def validate_icon(cls, v: Any) -> str:
        return normalize_kpi_icon_id(v)

    @field_validator("tone", mode="before")
    @classmethod
    def validate_tone(cls, v: Any) -> str:
        s = str(v or "navy").strip().lower()
        return s if s in VALID_KPI_TONES else "navy"


def _default_kpi_cards() -> list[KpiCardItem]:
    return [
        KpiCardItem(
            icon="central_bank",
            label="SNB Leitzins",
            value="0.50 %",
            subtext="−25 Bp vs. Vorquartal",
            tone="navy",
        ),
        KpiCardItem(
            icon="trend_up",
            label="Aktien Schweiz",
            value="Übergewichten",
            subtext="Attraktive Dividendenrendite",
            tone="cyan",
        ),
        KpiCardItem(
            icon="shield",
            label="Qualitätsfokus",
            value="Defensive Titel",
            subtext="Stabile Margen im Umfeld",
            tone="gold",
        ),
    ]


class KpiCardsBlock(MarginAnchorBlockBase):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["kpi_cards"] = "kpi_cards"
    layout: Literal["column", "full"] = Field(
        default="full",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )
    full_position: FullPositionMode = Field(
        default="inline",
        description="Seitenposition bei 2-spaltigem Layout ('auto', 'top', 'bottom', 'inline')",
    )
    title: str = Field(default="", description="Optionaler Titel über den KPI-Karten")
    subtitle: str = Field(default="", description="Optionaler Untertitel")
    source: str = Field(default="", description="Optionale Quellenangabe unterhalb der Karten")
    columns_count: int = Field(
        default=0,
        ge=0,
        le=4,
        description="Anzahl Spalten (0 = Auto je nach verfügbarer Breite, 1–4 = fixe Obergrenze)",
    )
    style_preset: KpiCardsStylePreset = Field(
        default="tint",
        description="Visueller Kartenstil ('tint', 'card_accent_top', 'card_accent_left', 'clean')",
    )
    cards: list[KpiCardItem] = Field(
        default_factory=_default_kpi_cards,
        description="1 bis 8 KPI-/Dashboard-Karten",
    )

    @field_validator("full_position", mode="before")
    @classmethod
    def validate_kpi_full_pos(cls, v: Any) -> str:
        if v is None or v == "":
            return "inline"
        return _normalize_full_position(v)

    @field_validator("columns_count", mode="before")
    @classmethod
    def validate_columns_count(cls, v: Any) -> int:
        if v is None or v == "" or str(v).strip().lower() == "auto":
            return 0
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            return 0
        return max(0, min(4, n))

    @field_validator("style_preset", mode="before")
    @classmethod
    def validate_style_preset(cls, v: Any) -> str:
        s = str(v or "tint").strip().lower()
        return s if s in ("tint", "card_accent_top", "card_accent_left", "clean") else "tint"

    @field_validator("cards", mode="before")
    @classmethod
    def validate_cards_seq(cls, v: Any) -> list[Any]:
        if isinstance(v, (list, tuple)):
            return list(v)[:8]
        return []


ContentBlock = Union[
    HeadingBlock,
    RichTextBlock,
    FigureBlock,
    DbChartBlock,
    TableBlock,
    CalloutBlock,
    BoxStartBlock,
    BoxEndBlock,
    SpacerBlock,
    ColbreakBlock,
    QuoteBlock,
    DividerBlock,
    FootnotesBlock,
    GlossaryBlock,
    PublicationsBlock,
    CustomChartBlock,
    MediaTextBlock,
    KpiCardsBlock,
]


_KNOWN_BLOCK_TYPES = {
    "heading",
    "richtext",
    "figure",
    "db_chart",
    "custom_chart",
    "table",
    "callout",
    "box_start",
    "box_end",
    "spacer",
    "colbreak",
    "quote",
    "divider",
    "footnotes",
    "glossary",
    "publications",
    "media_text",
    "kpi_cards",
}

_DISCRIMINATED_BLOCK_ADAPTER = TypeAdapter(Annotated[ContentBlock, Field(discriminator="type")])


def parse_block(raw: dict[str, Any]) -> ContentBlock:
    """Parst ein beliebiges Block-Dictionary anhand seines 'type'-Felds via Pydantic-Core Discriminator."""
    btype = raw.get("type")
    if btype in _KNOWN_BLOCK_TYPES:
        return _DISCRIMINATED_BLOCK_ADAPTER.validate_python(raw)
    return RichTextBlock.model_validate(raw)


class ArticleDocument(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = Field(default=1, ge=1)
    template_id: str = Field(default="investment_focus")
    status: Literal["draft", "review", "published", "archived"] = Field(default="draft")
    metadata: ArticleMetadata = Field(default_factory=ArticleMetadata)
    blocks: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("blocks", mode="before")
    @classmethod
    def validate_blocks_list(cls, v: Any) -> list[dict[str, Any]]:
        if not isinstance(v, (list, tuple)):
            return []
        validated: list[dict[str, Any]] = []
        for item in v:
            if isinstance(item, dict):
                blk = parse_block(item)
                validated.append(blk.model_dump())
            elif isinstance(item, BaseModel):
                validated.append(item.model_dump())
        return validated
