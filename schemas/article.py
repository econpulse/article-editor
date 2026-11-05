"""
Pydantic-Datenmodelle für das LUKB Investment Office CMS.
Validiert und normalisiert Artikel-Metadaten sowie alle Drag-and-Drop Content-Blöcke.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal, Union
from pydantic import BaseModel, Field, field_validator


def _new_block_id() -> str:
    return f"blk_{uuid.uuid4().hex[:10]}"


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
    authors: list[AuthorItem] = Field(default_factory=list, description="Autorenliste")
    disclaimer: str = Field(
        default=(
            "Diese Publikation dient ausschliesslich Informations- und Marketingzwecken der "
            "Luzerner Kantonalbank AG (LUKB) und stellt keine Anlageberatung oder Empfehlung dar."
        ),
        description="Rechtlicher Hinweis im Fussbereich",
    )

    @field_validator("authors", mode="before")
    @classmethod
    def validate_authors_seq(cls, v: Any) -> list[Any]:
        if isinstance(v, (list, tuple)):
            return list(v)
        return []


class HeadingBlock(BaseModel):
    id: str = Field(default_factory=_new_block_id)
    type: Literal["heading"] = "heading"
    level: int = Field(default=1, ge=1, le=3)
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


class TableColumn(BaseModel):
    field: str
    title: str
    align: Literal["left", "center", "right"] = "left"


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
            TableColumn(field="col_1", title="Anlageklasse", align="left"),
            TableColumn(field="col_2", title="Aktuell", align="right"),
            TableColumn(field="col_3", title="Veränderung", align="right"),
        ]
    )
    rows: list[dict[str, str]] = Field(
        default_factory=lambda: [
            {"col_1": "Liquidität", "col_2": "5.0 %", "col_3": "0.0 %"},
            {"col_1": "Obligationen CHF", "col_2": "28.0 %", "col_3": "-1.5 %"},
            {"col_1": "Aktien Schweiz", "col_2": "22.0 %", "col_3": "+1.5 %"},
        ]
    )

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


ContentBlock = Union[
    HeadingBlock,
    RichTextBlock,
    FigureBlock,
    TableBlock,
    CalloutBlock,
    BoxStartBlock,
    BoxEndBlock,
]


def parse_block(raw: dict[str, Any]) -> ContentBlock:
    """Parst ein beliebiges Block-Dictionary anhand seines 'type'-Felds."""
    btype = raw.get("type", "richtext")
    if btype == "heading":
        return HeadingBlock.model_validate(raw)
    if btype == "figure":
        return FigureBlock.model_validate(raw)
    if btype == "table":
        return TableBlock.model_validate(raw)
    if btype == "callout":
        return CalloutBlock.model_validate(raw)
    if btype == "box_start":
        return BoxStartBlock.model_validate(raw)
    if btype == "box_end":
        return BoxEndBlock.model_validate(raw)
    return RichTextBlock.model_validate(raw)


class ArticleDocument(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template_id: str = Field(default="investment_focus")
    status: Literal["draft", "review", "published"] = Field(default="draft")
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
