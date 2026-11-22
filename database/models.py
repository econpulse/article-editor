"""
SQLAlchemy ORM-Modelle für MS SQL Server (MSSQL).
Nutzt explizite Unicode-Typen (NVARCHAR / NVARCHAR(MAX)) für korrekte Darstellung
von Schweizer Umlauten und Sonderzeichen in MSSQL sowie VARBINARY(MAX) für Grafik-Assets,
damit Redeployments auf Posit Connect niemals hochgeladene Grafiken oder Artikel überschreiben.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Unicode,
    UnicodeText,
    UniqueConstraint,
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
    category: Mapped[str] = mapped_column(Unicode(200), nullable=False, default="")
    header_series: Mapped[str] = mapped_column(Unicode(200), nullable=False, default="Investment Office News")
    publication_date: Mapped[str] = mapped_column(Unicode(32), nullable=False, default="")
    authors_json: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="[]")
    tags_json: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="[]")
    disclaimer: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="")
    template_id: Mapped[str] = mapped_column(Unicode(100), nullable=False, default="investment_focus")
    status: Mapped[str] = mapped_column(Unicode(32), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    blocks_json: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
    updated_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="Investment Office")

    # Etappe 2: Trennung von Entwurf, Einreichung, Freigabe und Live-Fassung
    submitted_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    approved_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    live_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)

    revisions: Mapped[list["ArticleRevisionModel"]] = relationship(
        "ArticleRevisionModel",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="desc(ArticleRevisionModel.saved_at)",
    )
    published_snapshots: Mapped[list["PublishedSnapshotModel"]] = relationship(
        "PublishedSnapshotModel",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="desc(PublishedSnapshotModel.version)",
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


class PublishedSnapshotModel(Base):
    """
    Revisionssichere, versionierte Publikationshistorie für das Portal.
    Konserviert das exakte HTML und PDF zum Veröffentlichungszeitpunkt (inkl. Charts & Bildern)
    als VARBINARY(MAX) / NVARCHAR(MAX) in der Datenbank.
    Ermöglicht blitzschnelle Wiederherstellung nach Posit Connect Deployments oder Server-Neuinstallationen
    ohne dynamisches Re-Rendering.
    """

    __tablename__ = "io_published_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(
        Unicode(64), ForeignKey("io_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    slug: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    title: Mapped[str] = mapped_column(Unicode(500), nullable=False)
    publication_date: Mapped[str] = mapped_column(Unicode(32), nullable=False)
    metadata_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)

    html_content: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    pdf_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)

    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    published_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="Investment Office")
    change_note: Mapped[str] = mapped_column(Unicode(255), nullable=False, default="")

    revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    html_sha256: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    pdf_sha256: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)

    article: Mapped["ArticleModel"] = relationship("ArticleModel", back_populates="published_snapshots")


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


class ArticlePermissionModel(Base):
    """
    Artikelspezifische Berechtigungen (Etappe 1).
    Bindet eine authentifizierte Connect-Benutzerkennung an einen Artikel mit einer
    expliziten Artikelrolle ('owner', 'editor', 'reviewer', 'viewer').
    """

    __tablename__ = "io_article_permissions"
    __table_args__ = (
        UniqueConstraint("article_id", "user_id", name="uq_io_article_perm_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(
        Unicode(64), ForeignKey("io_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(Unicode(150), nullable=False, index=True)
    role: Mapped[str] = mapped_column(Unicode(32), nullable=False, default="editor")
    granted_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class UserRoleModel(Base):
    """
    Globale Benutzerrollen in der Datenbank (Etappe 1).
    Steuert Admin-Zugriff und Publikationsrecht unabhängig voneinander.
    """

    __tablename__ = "io_user_roles"

    user_id: Mapped[str] = mapped_column(Unicode(150), primary_key=True)
    display_name: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="System")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class AuditLogModel(Base):
    """
    Revisionssicheres Protokoll für Zuweisungs- und Rollenänderungen (Etappe 1+).
    """

    __tablename__ = "io_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user: Mapped[str] = mapped_column(Unicode(150), nullable=False, index=True)
    action: Mapped[str] = mapped_column(Unicode(64), nullable=False, index=True)
    target_user: Mapped[str] = mapped_column(Unicode(150), nullable=True, index=True)
    article_id: Mapped[str] = mapped_column(Unicode(64), nullable=True, index=True)
    details_json: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False, index=True)


class PublicationJobModel(Base):
    """
    Publikations- und Rückzugsaufträge für das Portal (Etappe 2).
    Pro Zielkanal ('target_channel') darf jeweils nur ein aktiver Auftrag laufen.
    """

    __tablename__ = "io_publication_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(
        Unicode(64), ForeignKey("io_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(Unicode(32), nullable=False, default="publish")
    target_channel: Mapped[str] = mapped_column(
        Unicode(64), nullable=False, default="intranet_portal", index=True
    )
    status: Mapped[str] = mapped_column(Unicode(32), nullable=False, default="pending", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    connect_bundle_id: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    connect_task_id: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    html_sha256: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    pdf_sha256: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    requested_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="Investment Office")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MediaEntryModel(Base):
    """
    Mediathek-Eintrag (Etappe 4): Metadaten, Herkunft, Freigabe & Nutzungskanal.
    Die eigentlichen Binärdaten liegen unveränderlich in `io_assets` (via `io_media_versions`).
    """

    __tablename__ = "io_media_entries"

    id: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    title: Mapped[str] = mapped_column(Unicode(300), nullable=False)
    media_type: Mapped[str] = mapped_column(Unicode(32), nullable=False, default="image")  # 'image' | 'chart'
    tags_json: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="[]")
    source_text: Mapped[str] = mapped_column(Unicode(300), nullable=False, default="")
    data_as_of: Mapped[str] = mapped_column(Unicode(64), nullable=False, default="")
    origin_article_id: Mapped[str | None] = mapped_column(Unicode(64), nullable=True, index=True)
    approval_status: Mapped[str] = mapped_column(
        Unicode(32), nullable=False, default="private", index=True
    )  # 'private' | 'pending' | 'approved' | 'revoked'
    usage_channel: Mapped[str] = mapped_column(
        Unicode(32), nullable=False, default="internal", index=True
    )  # 'internal' | 'external'
    requested_by: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class MediaVersionModel(Base):
    """Unveränderliche Dateiversion eines Mediathek-Eintrags, verknüpft mit `io_assets`."""

    __tablename__ = "io_media_versions"
    __table_args__ = (
        UniqueConstraint("media_id", "version", name="uq_io_media_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_id: Mapped[str] = mapped_column(
        Unicode(64), ForeignKey("io_media_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    asset_id: Mapped[str] = mapped_column(Unicode(64), nullable=False, index=True)
    thumbnail_data_uri: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    change_note: Mapped[str] = mapped_column(Unicode(255), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(Unicode(150), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class MediaUsageModel(Base):
    """Nachweis, welcher Artikel und Block welche Mediathek-Version referenziert."""

    __tablename__ = "io_media_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_id: Mapped[str] = mapped_column(
        Unicode(64), ForeignKey("io_media_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    asset_id: Mapped[str] = mapped_column(Unicode(64), nullable=False, index=True)
    article_id: Mapped[str] = mapped_column(
        Unicode(64), ForeignKey("io_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_id: Mapped[str] = mapped_column(Unicode(64), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
