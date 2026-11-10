"""
Pydantic-Datenmodelle für das LUKB Investment Office CMS.
Validiert und normalisiert Artikel-Metadaten sowie alle Drag-and-Drop Content-Blöcke.
"""

from __future__ import annotations

import math
import uuid
from datetime import date
from typing import Any, Literal, Union
from pydantic import BaseModel, Field, field_validator, model_validator


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
    category: str = Field(default="Anlagepolitik & Märkte", description="Rubrik / Publikationsreihe")
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


class FigureBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["figure"] = "figure"
    title: str = Field(default="", description="Grafik-Titel")
    subtitle: str = Field(default="", description="Grafik-Untertitel (z.B. Einheit, Zeitraum)")
    source: str = Field(default="Quelle: Bloomberg, LUKB Investment Office", description="Quellenangabe")
    asset_id: str = Field(default="", description="UUID des hochgeladenen Grafik-Assets in der DB")
    layout: Literal["column", "full"] = Field(
        default="column",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )


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


class DbChartBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["db_chart"] = "db_chart"
    title: str = Field(default="", description="Grafik-Titel")
    subtitle: str = Field(default="", description="Grafik-Untertitel (z.B. Einheit, Zeitraum)")
    source: str = Field(default="Quelle: Bloomberg, LUKB Investment Office", description="Quellenangabe")
    layout: Literal["column", "full"] = Field(
        default="column",
        description="Spaltenbreite ('column') oder gesamte Seitenbreite ('full')",
    )
    chart_height_mm: int = Field(
        default=36,
        description="Höhe der eigentlichen Chartfläche (Y-Achsenbereich) in Millimeter (2mm-Schritte, Default: 36mm)",
    )
    start_date: str = Field(default="2022-01-01", description="Startdatum im Chart (YYYY-MM-DD)")
    rebasing: Literal["none", "index_100"] = Field(
        default="none",
        description="'none' = Originalwerte, 'index_100' = Indexiert auf 100 am Startdatum",
    )
    palette: Literal["lukb_classic", "lukb_blues"] = Field(
        default="lukb_classic",
        description="ID der gewählten Farbpalette ('lukb_classic' oder 'lukb_blues')",
    )
    series: list[TimeSeriesItem] = Field(
        default_factory=lambda: [
            TimeSeriesItem(ticker="SNB_RATE", chart_type="line", label=""),
            TimeSeriesItem(ticker="ECB_RATE", chart_type="line", label=""),
            TimeSeriesItem(ticker="FED_RATE", chart_type="line", label=""),
        ],
        description="Bis zu 5 Zeitreihen aus ts_db",
    )
    asset_id: str = Field(default="", description="Gecachtes SVG-Asset in io_assets")

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

    @field_validator("series", mode="before")
    @classmethod
    def validate_series_seq(cls, v: Any) -> list[Any]:
        if isinstance(v, (list, tuple)):
            return list(v)[:5]
        return []


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
    align: Literal["left", "center", "right"] = "left"
    width: float = Field(default=100.0, ge=0.1, le=100.0, description="Relative Spaltenbreite in Prozent")

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


class TableBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["table"] = "table"
    title: str = Field(default="", description="Tabellen-Titel")
    subtitle: str = Field(default="", description="Tabellen-Untertitel")
    source: str = Field(default="Quelle: LUKB Investment Office", description="Tabellen-Quelle / Fussnote")
    layout: Literal["column", "full"] = Field(default="column")
    highlight_last_row: bool = Field(default=False, description="Letzte Zeile als Total/Summe hervorheben")
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
]


def parse_block(raw: dict[str, Any]) -> ContentBlock:
    """Parst ein beliebiges Block-Dictionary anhand seines 'type'-Felds."""
    btype = raw.get("type", "richtext")
    if btype == "heading":
        return HeadingBlock.model_validate(raw)
    if btype == "figure":
        return FigureBlock.model_validate(raw)
    if btype == "db_chart":
        return DbChartBlock.model_validate(raw)
    if btype == "table":
        return TableBlock.model_validate(raw)
    if btype == "callout":
        return CalloutBlock.model_validate(raw)
    if btype == "box_start":
        return BoxStartBlock.model_validate(raw)
    if btype == "box_end":
        return BoxEndBlock.model_validate(raw)
    if btype == "spacer":
        return SpacerBlock.model_validate(raw)
    if btype == "colbreak":
        return ColbreakBlock.model_validate(raw)
    if btype == "quote":
        return QuoteBlock.model_validate(raw)
    if btype == "divider":
        return DividerBlock.model_validate(raw)
    if btype == "footnotes":
        return FootnotesBlock.model_validate(raw)
    if btype == "glossary":
        return GlossaryBlock.model_validate(raw)
    if btype == "publications":
        return PublicationsBlock.model_validate(raw)
    return RichTextBlock.model_validate(raw)


class ArticleDocument(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
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
