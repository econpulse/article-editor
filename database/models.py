"""
SQLAlchemy ORM-Modelle für MS SQL Server (MSSQL).
Nutzt explizite Unicode-Typen (NVARCHAR / NVARCHAR(MAX)) für korrekte Darstellung
von Schweizer Umlauten und Sonderzeichen in MSSQL sowie VARBINARY(MAX) für Grafik-Assets,
damit Redeployments auf Posit Connect niemals hochgeladene Grafiken oder Artikel überschreiben.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Unicode,
    UnicodeText,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ArticleModel(Base):
    """Haupttabelle für Publikationen / Artikel des Investment Office."""

    __tablename__ = "io_articles"

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    title: Mapped[str] = mapped_column(Unicode(500), nullable=False, default="Neue Publikation")
    subtitle: Mapped[str] = mapped_column(Unicode(500), nullable=False, default="")
    lead: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="")
    category: Mapped[str] = mapped_column(Unicode(200), nullable=False, default="Anlagepolitik & Märkte")
    publication_date: Mapped[str] = mapped_column(Unicode(32), nullable=False, default="")
    authors_json: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="[]")
    disclaimer: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="")
    template_id: Mapped[str] = mapped_column(Unicode(100), nullable=False, default="investment_focus")
    status: Mapped[str] = mapped_column(Unicode(32), nullable=False, default="draft")
    blocks_json: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
    updated_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="Investment Office")

    revisions: Mapped[list["ArticleRevisionModel"]] = relationship(
        "ArticleRevisionModel",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="desc(ArticleRevisionModel.saved_at)",
    )


class ArticleRevisionModel(Base):
    """Revisionshistorie für Artikel-Snapshots (Meilensteine & Wiederherstellung)."""

    __tablename__ = "io_article_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(
        Unicode(64), ForeignKey("io_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    saved_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="Autosave")
    note: Mapped[str] = mapped_column(Unicode(255), nullable=False, default="")

    article: Mapped["ArticleModel"] = relationship("ArticleModel", back_populates="revisions")


class AssetModel(Base):
    """
    Datenbank-gestützter Speicher für hochgeladene Grafiken (SVG, PNG, JPG).
    Durch die Speicherung als VARBINARY(MAX) direkt in der MSSQL-Datenbank sind alle Grafiken
    vollständig geschützt vor Posit-Connect-Redeployments und Container-Neustarts.
    """

    __tablename__ = "io_assets"

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    article_id: Mapped[str] = mapped_column(Unicode(64), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class TimeSeriesModel(Base):
    """
    Zeitreihen-Tabelle `ts_db` im Long-Format (ticker, date, name, value).
    Unterstützt DATE- und DATETIME-Spalten in MS SQL Server sowie SQLite für lokale Tests.
    """

    __tablename__ = "ts_db"

    ticker: Mapped[str] = mapped_column(Unicode(100), primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(Unicode(255), nullable=False, default="")
    value: Mapped[float] = mapped_column(Float, nullable=True)
