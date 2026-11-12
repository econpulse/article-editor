"""
Repository-Layer für CRUD-Operationen, Debounced Autosave, Revisions-Snapshots
und Datenbank-Asset-Speicherung (MSSQL / SQLAlchemy).
"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any
from sqlalchemy import desc, func, or_, select

logger = logging.getLogger(__name__)

from database.connection import Base, engine, get_db_session
from database.models import ArticleModel, ArticleRevisionModel, AssetModel, TimeSeriesModel
from schemas.article import (
    DEFAULT_LUKB_DISCLAIMER,
    LEGACY_LUKB_DISCLAIMER,
    ArticleDocument,
    ArticleMetadata,
    AuthorItem,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_document(row: ArticleModel) -> ArticleDocument:
    try:
        authors_raw = json.loads(row.authors_json or "[]")
    except Exception:
        authors_raw = []

    try:
        blocks_raw = json.loads(row.blocks_json or "[]")
    except Exception:
        blocks_raw = []

    raw_disclaimer = (row.disclaimer or "").strip()
    if not raw_disclaimer or raw_disclaimer == LEGACY_LUKB_DISCLAIMER:
        resolved_disclaimer = DEFAULT_LUKB_DISCLAIMER
    else:
        resolved_disclaimer = raw_disclaimer

    metadata = ArticleMetadata(
        title=row.title or "Unbenannte Publikation",
        subtitle=row.subtitle or "",
        lead=row.lead or "",
        publication_date=row.publication_date or "",
        category=row.category or "Anlagepolitik & Märkte",
        header_series=getattr(row, "header_series", None) or "Investment Office News",
        authors=[AuthorItem.model_validate(a) for a in authors_raw if isinstance(a, dict)],
        disclaimer=resolved_disclaimer,
    )
    return ArticleDocument(
        id=row.id,
        template_id=row.template_id or "investment_focus",
        status=row.status if row.status in ("draft", "review", "published", "archived") else "draft",
        metadata=metadata,
        blocks=blocks_raw,
    )


def list_articles(
    search_query: str = "",
    status_filter: str = "all",
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """
    Liefert eine kompakte Übersicht aller Artikel in der Datenbank (sortiert nach Änderungsdatum).
    Standardmässig werden archivierte Artikel (Soft-Delete) ausgeblendet.
    """
    with get_db_session() as session:
        stmt = select(
            ArticleModel.id,
            ArticleModel.title,
            ArticleModel.subtitle,
            ArticleModel.category,
            ArticleModel.template_id,
            ArticleModel.status,
            ArticleModel.authors_json,
            ArticleModel.publication_date,
            ArticleModel.updated_at,
            ArticleModel.created_at,
            ArticleModel.updated_by,
        ).order_by(desc(ArticleModel.updated_at))
        if status_filter == "all":
            if not include_archived:
                stmt = stmt.where(ArticleModel.status != "archived")
        elif status_filter == "all_with_archived":
            pass  # alle Status inkl. archiviert
        elif status_filter == "archived":
            stmt = stmt.where(ArticleModel.status == "archived")
        elif status_filter == "active_work":
            stmt = stmt.where(ArticleModel.status.in_(["draft", "review"]))
        elif status_filter:
            stmt = stmt.where(ArticleModel.status == status_filter)
        if search_query and search_query.strip():
            q = f"%{search_query.strip()}%"
            stmt = stmt.where(
                or_(
                    ArticleModel.title.ilike(q),
                    ArticleModel.subtitle.ilike(q),
                    ArticleModel.lead.ilike(q),
                    ArticleModel.authors_json.ilike(q),
                    ArticleModel.category.ilike(q),
                )
            )
        rows = session.execute(stmt).all()
        result: list[dict[str, Any]] = []
        for r in rows:
            try:
                authors = json.loads(r.authors_json or "[]")
                author_names = ", ".join(a.get("name", "") for a in authors if a.get("name"))
            except Exception:
                author_names = ""
            updated_dt = r.updated_at or r.created_at
            updated_str = updated_dt.strftime("%d.%m.%Y %H:%M") if updated_dt else ""
            updated_iso = updated_dt.isoformat() if updated_dt else ""
            result.append(
                {
                    "id": r.id,
                    "title": r.title,
                    "subtitle": r.subtitle or "",
                    "category": r.category or "",
                    "template_id": r.template_id,
                    "status": r.status,
                    "authors_summary": author_names or "Investment Office",
                    "publication_date": r.publication_date or "",
                    "updated_at": updated_str,
                    "updated_iso": updated_iso,
                    "updated_by": r.updated_by or "",
                }
            )
        return result


def get_article(article_id: str) -> ArticleDocument | None:
    """Lädt einen einzelnen Artikel als validiertes ArticleDocument."""
    if not article_id:
        return None
    with get_db_session() as session:
        row = session.get(ArticleModel, article_id)
        if not row:
            return None
        return _row_to_document(row)


def _merge_concurrent_documents(
    base_doc: ArticleDocument,
    incoming_doc: ArticleDocument,
    db_doc: ArticleDocument,
) -> ArticleDocument:
    """
    Führt einen 3-Wege-Merge (Base vs. Incoming vs. DB) auf Metadaten- und Block-Ebene durch,
    sodass mehrere Autoren gleichzeitig an verschiedenen Blöcken oder Metadaten-Feldern
    desselben Artikels arbeiten können, ohne sich gegenseitig zu überschreiben.
    """
    base_d = base_doc.model_dump()
    inc_d = incoming_doc.model_dump()
    db_d = db_doc.model_dump()

    # 1. Top-Level Felder (template_id, status)
    merged_template = (
        inc_d["template_id"]
        if inc_d["template_id"] != base_d["template_id"]
        else db_d["template_id"]
    )
    merged_status = (
        inc_d["status"] if inc_d["status"] != base_d["status"] else db_d["status"]
    )

    # 2. Metadaten-Felder einzeln mergen
    merged_meta: dict[str, Any] = {}
    for k in (
        "title",
        "subtitle",
        "lead",
        "publication_date",
        "category",
        "authors",
        "disclaimer",
    ):
        if inc_d["metadata"].get(k) != base_d["metadata"].get(k):
            merged_meta[k] = inc_d["metadata"].get(k)
        else:
            merged_meta[k] = db_d["metadata"].get(k)

    # 3. Inhaltsblöcke (ID-basiertes 3-Wege-Merging)
    base_blocks_by_id = {b["id"]: b for b in base_d.get("blocks", []) if "id" in b}
    inc_blocks_by_id = {b["id"]: b for b in inc_d.get("blocks", []) if "id" in b}
    db_blocks_by_id = {b["id"]: b for b in db_d.get("blocks", []) if "id" in b}

    base_order = [b["id"] for b in base_d.get("blocks", []) if "id" in b]
    inc_order = [b["id"] for b in inc_d.get("blocks", []) if "id" in b]
    db_order = [b["id"] for b in db_d.get("blocks", []) if "id" in b]

    # Wurde die Reihenfolge / Struktur vom aktuellen Client verändert?
    inc_structure_changed = inc_order != base_order

    # Welche Blöcke wurden explizit gelöscht?
    deleted_by_inc = set(base_order) - set(inc_order)
    deleted_by_db = set(base_order) - set(db_order)
    all_deleted = deleted_by_inc | deleted_by_db

    # Bestimme die kombinierte Reihenfolge der Block-IDs
    primary_order = inc_order if inc_structure_changed else db_order
    secondary_order = db_order if inc_structure_changed else inc_order

    combined_ids: list[str] = []
    for bid in primary_order:
        if bid not in all_deleted and bid not in combined_ids:
            combined_ids.append(bid)

    # Falls im anderen Stand neue Blöcke hinzugekommen sind, an passender Stelle einfügen
    for idx, bid in enumerate(secondary_order):
        if bid not in all_deleted and bid not in combined_ids:
            if idx == 0:
                combined_ids.insert(0, bid)
            else:
                prev_id = secondary_order[idx - 1]
                if prev_id in combined_ids:
                    insert_pos = combined_ids.index(prev_id) + 1
                    combined_ids.insert(insert_pos, bid)
                else:
                    combined_ids.append(bid)

    # Inhalt jedes einzelnen Blocks zusammenführen
    merged_blocks: list[dict[str, Any]] = []
    for bid in combined_ids:
        b_base = base_blocks_by_id.get(bid)
        b_inc = inc_blocks_by_id.get(bid)
        b_db = db_blocks_by_id.get(bid)

        if b_inc and b_db and b_base:
            # Existierte in allen 3 Ständen: Hat Incoming diesen Block editiert?
            if b_inc != b_base:
                if b_db != b_base and b_db != b_inc:
                    # Beide haben denselben Block editiert -> Feld-genauer Merge innerhalb des Blocks
                    merged_blk = dict(b_db)
                    for fk, fv in b_inc.items():
                        if fv != b_base.get(fk):
                            merged_blk[fk] = fv
                    merged_blocks.append(merged_blk)
                else:
                    merged_blocks.append(b_inc)
            else:
                # Incoming hat diesen Block nicht angefasst -> behalte DB-Änderung von Kollege!
                merged_blocks.append(b_db)
        elif b_inc and not b_base:
            # Neu von Incoming angelegt
            merged_blocks.append(b_inc)
        elif b_db and not b_base:
            # Neu in DB von Kollege angelegt
            merged_blocks.append(b_db)
        elif b_inc:
            merged_blocks.append(b_inc)
        elif b_db:
            merged_blocks.append(b_db)

    return ArticleDocument.model_validate(
        {
            "id": incoming_doc.id,
            "template_id": merged_template,
            "status": merged_status,
            "metadata": merged_meta,
            "blocks": merged_blocks,
        }
    )


def save_article(
    doc: ArticleDocument,
    user: str = "Investment Office",
    create_revision: bool = False,
    revision_note: str = "",
    base_doc: ArticleDocument | None = None,
) -> dict[str, Any]:
    """
    Speichert oder aktualisiert einen Artikel (UPSERT) in der MSSQL-Datenbank.
    Falls `base_doc` übergeben wird und der Datenbankstand zwischenzeitlich durch
    einen anderen Autor verändert wurde, führt `save_article` automatisch einen
    3-Wege-Merge auf Block- und Metadaten-Ebene durch.
    """
    now = _utc_now()
    merged_from_other = False
    with get_db_session() as session:
        row = session.get(ArticleModel, doc.id)

        if row is not None and base_doc is not None:
            current_db_doc = _row_to_document(row)
            if current_db_doc.model_dump() != base_doc.model_dump():
                doc = _merge_concurrent_documents(base_doc, doc, current_db_doc)
                merged_from_other = True

        authors_serialized = json.dumps(
            [a.model_dump() for a in doc.metadata.authors], ensure_ascii=False
        )
        blocks_serialized = json.dumps(doc.blocks, ensure_ascii=False)

        if row is None:
            row = ArticleModel(
                id=doc.id,
                title=doc.metadata.title,
                subtitle=doc.metadata.subtitle,
                lead=doc.metadata.lead,
                category=doc.metadata.category,
                header_series=doc.metadata.header_series or "Investment Office News",
                publication_date=doc.metadata.publication_date,
                authors_json=authors_serialized,
                disclaimer=doc.metadata.disclaimer,
                template_id=doc.template_id,
                status=doc.status,
                blocks_json=blocks_serialized,
                created_at=now,
                updated_at=now,
                updated_by=user,
            )
            session.add(row)
        else:
            row.title = doc.metadata.title
            row.subtitle = doc.metadata.subtitle
            row.lead = doc.metadata.lead
            row.category = doc.metadata.category
            row.header_series = doc.metadata.header_series or "Investment Office News"
            row.publication_date = doc.metadata.publication_date
            row.authors_json = authors_serialized
            row.disclaimer = doc.metadata.disclaimer
            row.template_id = doc.template_id
            row.status = doc.status
            row.blocks_json = blocks_serialized
            row.updated_at = now
            row.updated_by = user

        if create_revision:
            rev = ArticleRevisionModel(
                article_id=doc.id,
                snapshot_json=doc.model_dump_json(),
                saved_at=now,
                saved_by=user,
                note=revision_note or "Manueller Snapshot",
            )
            session.add(rev)

    return {
        "id": doc.id,
        "saved_at": now.strftime("%H:%M:%S"),
        "saved_date": now.strftime("%d.%m.%Y %H:%M:%S"),
        "merged": merged_from_other,
        "article": doc.model_dump(),
    }


def create_new_article(
    template_id: str = "investment_focus",
    user: str = "Investment Office",
) -> ArticleDocument:
    """Erstellt einen neuen Artikel mit einer strukturierten Start-Vorlage."""
    new_doc = ArticleDocument(
        id=str(uuid.uuid4()),
        template_id=template_id,
        status="draft",
        metadata=ArticleMetadata(
            title="Neue Investment-Publikation",
            subtitle="Markteinschätzung & Positionierung",
            lead=(
                "Fassen Sie hier die wichtigsten Erkenntnisse (Management Summary) in zwei bis drei "
                "prägnanten Sätzen für die Leserinnen und Leser zusammen."
            ),
            category="Anlagepolitik & Märkte",
            authors=[AuthorItem(name="Titel Vorname Name", role="Funktion / Rolle")],
        ),
        blocks=[
            {
                "id": f"blk_{uuid.uuid4().hex[:8]}",
                "type": "heading",
                "level": 2,
                "text": "Makroökonomischer Ausblick",
            },
            {
                "id": f"blk_{uuid.uuid4().hex[:8]}",
                "type": "richtext",
                "html": (
                    "<p>Beginnen Sie hier mit Ihrem Analysetext. Sie können Absätze beliebig per "
                    "<strong>Drag-and-Drop</strong> umsortieren sowie neue Grafiken und Tabellen einfügen.</p>"
                ),
            },
        ],
    )
    save_article(new_doc, user=user, create_revision=True, revision_note="Initiale Erstellung")
    return new_doc


def duplicate_article(article_id: str, user: str = "Investment Office") -> ArticleDocument | None:
    """Dupliziert einen bestehenden Artikel als neuen Entwurf."""
    orig = get_article(article_id)
    if not orig:
        return None
    orig.id = str(uuid.uuid4())
    orig.status = "draft"
    orig.metadata.title = f"{orig.metadata.title} (Kopie)"
    save_article(orig, user=user, create_revision=True, revision_note="Kopie erstellt")
    return orig


def delete_article(
    article_id: str,
    user: str = "Investment Office",
    force: bool = False,
) -> bool:
    """
    Löscht einen Artikel bzw. archiviert ihn sicher im Papierkorb (Soft-Delete).
    Schutzregel: Ein Artikel, der im Portal 'published' ist, darf NICHT gelöscht werden.
    Er muss zuerst explizit vom Portal zurückgezogen werden.
    """
    doc = get_article(article_id)
    if not doc:
        return False

    # Schutz vor Löschung publizierter Dokumente
    if doc.status == "published":
        logger.warning(
            f"Löschversuch für publizierten Artikel {article_id} abgelehnt. Artikel muss zuerst zurückgezogen werden."
        )
        return False

    if force:
        try:
            from services.portal_publisher import unpublish_article
            unpublish_article(article_id)
        except Exception:
            pass

        with get_db_session() as session:
            row = session.get(ArticleModel, article_id)
            if not row:
                return False
            session.delete(row)
            return True

    # Standard: Soft-Delete (Status auf 'archived' setzen, Revision ablegen)
    doc.status = "archived"
    save_article(
        doc,
        user=user,
        create_revision=True,
        revision_note="Publikation archiviert (Soft-Delete / Papierkorb)",
    )
    return True


def restore_article(article_id: str, user: str = "Investment Office") -> bool:
    """Stellt einen archivierten Artikel wieder in den Arbeitsstatus 'draft' her."""
    doc = get_article(article_id)
    if not doc or doc.status != "archived":
        return False
    doc.status = "draft"
    save_article(
        doc,
        user=user,
        create_revision=True,
        revision_note="Publikation aus Archiv wiederhergestellt",
    )
    return True


def publish_article_to_portal(article_id: str, user: str = "Investment Office") -> dict[str, Any]:
    """
    Publiziert einen Artikel auf das statische Content-Portal:
    - Setzt status auf 'published'
    - Rendert HTML & druckreifes Typst-PDF
    - Aktualisiert Portal-Übersicht & Volltext-Suchindex
    """
    doc = get_article(article_id)
    if not doc:
        return {"success": False, "error": f"Artikel {article_id} nicht gefunden"}

    doc.status = "published"
    save_article(doc, user=user, create_revision=True, revision_note="Auf statischem Portal publiziert")
    from services.portal_publisher import publish_article
    return publish_article(doc)


def unpublish_article_from_portal(
    article_id: str,
    user: str = "Investment Office",
    new_status: str = "draft",
) -> dict[str, Any]:
    """
    Zieht einen publizierten Artikel vom statischen Portal zurück:
    - Setzt den Datenbankstatus zurück auf 'draft' (oder 'review')
    - Entfernt die statischen Dateien und aktualisiert Portal-Übersicht & Suchindex
    """
    doc = get_article(article_id)
    if doc:
        doc.status = new_status
        save_article(doc, user=user, create_revision=True, revision_note="Vom statischen Portal zurückgezogen")
    from services.portal_publisher import unpublish_article
    return unpublish_article(article_id)


def save_asset(
    filename: str,
    mime_type: str,
    data: bytes,
    article_id: str | None = None,
    asset_id: str | None = None,
) -> str:
    """Speichert eine Grafik als Binärobjekt (VARBINARY(MAX)) in der Datenbank."""
    aid = asset_id or f"asset_{uuid.uuid4().hex[:12]}"
    with get_db_session() as session:
        existing = session.get(AssetModel, aid)
        if existing:
            existing.filename = filename
            existing.mime_type = mime_type
            existing.data = data
            existing.article_id = article_id
        else:
            session.add(
                AssetModel(
                    id=aid,
                    article_id=article_id,
                    filename=filename,
                    mime_type=mime_type,
                    data=data,
                )
            )
    return aid


def get_asset(asset_id: str) -> dict[str, Any] | None:
    """Lädt ein Grafik-Asset aus der Datenbank."""
    if not asset_id:
        return None
    with get_db_session() as session:
        row = session.get(AssetModel, asset_id)
        if not row:
            return None
        return {
            "id": row.id,
            "filename": row.filename,
            "mime_type": row.mime_type,
            "data": row.data,
        }


# ============================================================================
# Zeitreihen-Abfragen für `ts_db` (DB-Chart Inhaltsblock)
# ============================================================================


def _coerce_to_date(val: Any) -> date | None:
    """Konvertiert DATE, DATETIME oder ISO-String sicher in ein `datetime.date`-Objekt."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            for fmt in ("%d.%m.%Y", "%Y/%m/%d", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s[:10], fmt).date()
                except ValueError:
                    pass
    return None


_TICKER_CATALOG_CACHE: list[dict[str, str]] | None = None
_TICKER_CACHE_TS: float = 0.0
_TICKER_CACHE_TTL_SEC: float = 900.0  # 15 Minuten In-Memory-Cache für Tausende Ticker


def _get_cached_ticker_catalog(force_refresh: bool = False) -> list[dict[str, str]]:
    """
    Lädt das Verzeichnis eindeutiger `(ticker, name)`-Paare aus `ts_db` einmalig in den
    Server-Speicher (ohne teure MIN/MAX-Datumsaggregation über Millionen Zeilen).
    Dadurch antwortet die Ticker-Autovervollständigung auch bei Tausenden Tickern in < 1 ms.
    """
    global _TICKER_CATALOG_CACHE, _TICKER_CACHE_TS
    now_ts = time.monotonic()
    if (
        not force_refresh
        and _TICKER_CATALOG_CACHE is not None
        and (now_ts - _TICKER_CACHE_TS) < _TICKER_CACHE_TTL_SEC
    ):
        return _TICKER_CATALOG_CACHE

    try:
        with get_db_session() as session:
            stmt = select(TimeSeriesModel.ticker, TimeSeriesModel.name).distinct()
            rows = session.execute(stmt).all()
            by_upper: dict[str, dict[str, str]] = {}
            for r in rows:
                if not r.ticker:
                    continue
                t_clean = str(r.ticker).strip()
                if not t_clean:
                    continue
                u_key = t_clean.upper()
                n_clean = str(r.name or "").strip()
                if u_key not in by_upper or (not by_upper[u_key]["name"] and n_clean):
                    by_upper[u_key] = {
                        "ticker": t_clean,
                        "name": n_clean or t_clean,
                        "_t_upper": u_key,
                        "_n_upper": (n_clean or t_clean).upper(),
                    }
            catalog = sorted(by_upper.values(), key=lambda x: x["_t_upper"])
            _TICKER_CATALOG_CACHE = catalog
            _TICKER_CACHE_TS = now_ts
            return catalog
    except Exception:
        return _TICKER_CATALOG_CACHE or []


def search_tickers(query: str = "", limit: int = 15) -> list[dict[str, str]]:
    """
    Durchsucht den In-Memory-Ticker-Katalog nach Ticker-Kürzel oder Zeitreihen-Namen
    und gibt maximal `limit` Treffer zurück (Präfix-Treffer zuerst, dann Teilstring-Treffer).
    """
    catalog = _get_cached_ticker_catalog()
    q = (query or "").strip().upper()
    max_items = max(1, min(50, int(limit or 15)))

    if not q:
        return [{"ticker": it["ticker"], "name": it["name"]} for it in catalog[:max_items]]

    prefix_matches: list[dict[str, str]] = []
    ticker_sub_matches: list[dict[str, str]] = []
    name_sub_matches: list[dict[str, str]] = []

    for it in catalog:
        tu = it["_t_upper"]
        nu = it["_n_upper"]
        if tu.startswith(q):
            prefix_matches.append({"ticker": it["ticker"], "name": it["name"]})
            if len(prefix_matches) >= max_items:
                break
        elif q in tu:
            if len(prefix_matches) + len(ticker_sub_matches) < max_items:
                ticker_sub_matches.append({"ticker": it["ticker"], "name": it["name"]})
        elif q in nu:
            if len(prefix_matches) + len(ticker_sub_matches) + len(name_sub_matches) < max_items:
                name_sub_matches.append({"ticker": it["ticker"], "name": it["name"]})

    combined = prefix_matches + ticker_sub_matches + name_sub_matches
    return combined[:max_items]


def list_available_tickers(limit: int | None = None) -> list[dict[str, Any]]:
    """
    Liefert Ticker samt Namen aus dem schnellen Katalog-Cache.
    """
    catalog = _get_cached_ticker_catalog()
    items = catalog if limit is None else catalog[: max(1, int(limit))]
    return [{"ticker": it["ticker"], "name": it["name"]} for it in items]


def query_timeseries_data(
    tickers: list[str],
    start_date: str | date | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Liest Zeitreihen aus `ts_db` (Spalten: ticker, date, name, value) im Long-Format.
    Gibt ein Dictionary zurück, indiziert über den angefragten Ticker (Case-Insensitive Match):
    `{ "SMI": {"ticker": "SMI", "name": "Swiss Market Index (SMI)", "points": [(date, float), ...]} }`
    """
    cleaned = [t.strip() for t in tickers if t and str(t).strip()]
    if not cleaned:
        return {}

    upper_map = {t.upper(): t for t in cleaned}
    start_dt = _coerce_to_date(start_date)

    result: dict[str, dict[str, Any]] = {}
    with get_db_session() as session:
        stmt = select(
            TimeSeriesModel.ticker,
            TimeSeriesModel.date,
            TimeSeriesModel.name,
            TimeSeriesModel.value,
        ).where(func.upper(TimeSeriesModel.ticker).in_(list(upper_map.keys())))

        if start_dt is not None:
            stmt = stmt.where(TimeSeriesModel.date >= start_dt)

        stmt = stmt.order_by(TimeSeriesModel.date.asc())
        rows = session.execute(stmt).all()

        by_upper: dict[str, dict[date, float]] = {}
        meta_by_upper: dict[str, tuple[str, str]] = {}

        for r in rows:
            if not r.ticker or r.value is None:
                continue
            try:
                fval = float(r.value)
                if math.isnan(fval) or math.isinf(fval):
                    continue
            except (TypeError, ValueError):
                continue

            dt = _coerce_to_date(r.date)
            if dt is None:
                continue
            if start_dt is not None and dt < start_dt:
                continue

            u_key = str(r.ticker).strip().upper()
            if u_key not in by_upper:
                by_upper[u_key] = {}
                meta_by_upper[u_key] = (str(r.ticker).strip(), str(r.name or "").strip())
            elif not meta_by_upper[u_key][1] and r.name:
                meta_by_upper[u_key] = (meta_by_upper[u_key][0], str(r.name).strip())

            by_upper[u_key][dt] = fval

        for u_key, req_ticker in upper_map.items():
            if u_key in by_upper and by_upper[u_key]:
                db_ticker, db_name = meta_by_upper[u_key]
                sorted_pts = sorted(by_upper[u_key].items(), key=lambda x: x[0])
                result[req_ticker] = {
                    "ticker": db_ticker,
                    "name": db_name or db_ticker,
                    "points": sorted_pts,
                }
                result[u_key] = result[req_ticker]

    return result


def _seed_sample_timeseries() -> None:
    """Befüllt `ts_db` mit realistischen Beispiel-Zeitreihen, falls die Tabelle noch leer ist."""
    with get_db_session() as session:
        existing_row = session.execute(select(TimeSeriesModel.ticker).limit(1)).first()
        if existing_row is not None:
            return

        # Quartals-Stichtage von Q1 2021 bis Q4 2026 (24 Quartale)
        quarter_dates = [
            date(2021, 3, 31), date(2021, 6, 30), date(2021, 9, 30), date(2021, 12, 31),
            date(2022, 3, 31), date(2022, 6, 30), date(2022, 9, 30), date(2022, 12, 31),
            date(2023, 3, 31), date(2023, 6, 30), date(2023, 9, 30), date(2023, 12, 31),
            date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31),
            date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31),
            date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30), date(2026, 11, 5),
        ]

        series_catalog = [
            (
                "SNB_RATE",
                "SNB Leitzins (CHF)",
                [
                    -0.75, -0.75, -0.75, -0.75,
                    -0.75, -0.25, 0.50, 1.00,
                    1.50, 1.75, 1.75, 1.75,
                    1.50, 1.25, 1.00, 0.50,
                    0.25, 0.00, 0.00, 0.00,
                    0.00, 0.00, 0.00, 0.00,
                ],
            ),
            (
                "ECB_RATE",
                "EZB Einlagesatz (EUR)",
                [
                    -0.50, -0.50, -0.50, -0.50,
                    -0.50, -0.50, 0.75, 2.00,
                    3.00, 3.50, 4.00, 4.00,
                    4.00, 3.75, 3.50, 3.00,
                    2.50, 2.25, 2.00, 2.00,
                    1.75, 1.75, 1.75, 1.75,
                ],
            ),
            (
                "FED_RATE",
                "US Fed Funds Rate (USD)",
                [
                    0.25, 0.25, 0.25, 0.25,
                    0.50, 1.75, 3.25, 4.50,
                    5.00, 5.25, 5.50, 5.50,
                    5.50, 5.50, 5.00, 4.50,
                    4.25, 4.00, 3.75, 3.50,
                    3.25, 3.25, 3.00, 3.00,
                ],
            ),
            (
                "SMI",
                "Swiss Market Index (SMI)",
                [
                    11047, 11942, 11642, 12875,
                    12161, 10741, 10267, 10729,
                    11106, 11280, 10963, 11138,
                    11730, 11993, 12168, 11850,
                    12340, 12580, 12410, 12790,
                    13020, 13180, 13350, 13490,
                ],
            ),
            (
                "SP500",
                "S&P 500 Index",
                [
                    3972, 4297, 4307, 4766,
                    4530, 3785, 3585, 3839,
                    4109, 4450, 4288, 4769,
                    5254, 5460, 5762, 5910,
                    6020, 6150, 6080, 6290,
                    6410, 6520, 6610, 6695,
                ],
            ),
            (
                "STOXX600",
                "STOXX Europe 600",
                [
                    429, 452, 454, 487,
                    455, 407, 387, 424,
                    457, 461, 450, 479,
                    512, 511, 522, 515,
                    534, 546, 540, 558,
                    569, 575, 582, 588,
                ],
            ),
            (
                "CH_10Y",
                "Eidgenossen 10J Rendite (%)",
                [
                    -0.28, -0.22, -0.15, -0.13,
                    0.62, 1.18, 1.24, 1.58,
                    1.19, 0.96, 1.09, 0.70,
                    0.68, 0.58, 0.42, 0.35,
                    0.44, 0.48, 0.45, 0.50,
                    0.52, 0.55, 0.54, 0.56,
                ],
            ),
            (
                "CH_CPI",
                "Inflation Schweiz YoY (%)",
                [
                    -0.2, 0.6, 0.9, 1.5,
                    2.4, 3.4, 3.3, 2.8,
                    2.9, 1.7, 1.7, 1.7,
                    1.0, 1.3, 0.8, 0.7,
                    0.6, 0.7, 0.8, 0.8,
                    0.9, 0.8, 0.8, 0.7,
                ],
            ),
            (
                "CH_GDP",
                "BIP-Wachstum Schweiz QoQ (%)",
                [
                    -0.3, 1.8, 1.5, 0.4,
                    0.5, 0.3, 0.2, 0.0,
                    0.3, -0.1, 0.3, 0.3,
                    0.5, 0.7, 0.4, 0.3,
                    0.4, 0.5, 0.4, 0.5,
                    0.4, 0.5, 0.4, 0.5,
                ],
            ),
            (
                "EPS_CH",
                "Gewinnbeitrag Schweiz (CHF Mrd.)",
                [
                    12.4, 13.8, 13.2, 14.1,
                    13.5, 12.9, 12.4, 13.0,
                    13.8, 14.2, 14.0, 14.5,
                    15.1, 15.6, 15.8, 16.2,
                    16.5, 17.0, 16.8, 17.4,
                    17.9, 18.3, 18.6, 19.0,
                ],
            ),
            (
                "EPS_US",
                "Gewinnbeitrag USA (CHF Mrd.)",
                [
                    18.0, 19.5, 20.1, 21.4,
                    20.2, 18.8, 18.1, 19.0,
                    20.4, 21.6, 22.0, 23.1,
                    24.5, 25.4, 26.2, 27.0,
                    27.8, 28.5, 28.1, 29.4,
                    30.2, 31.0, 31.8, 32.5,
                ],
            ),
            (
                "EPS_EU",
                "Gewinnbeitrag Europa (CHF Mrd.)",
                [
                    9.2, 10.4, 10.1, 10.8,
                    10.0, 9.1, 8.6, 9.3,
                    9.9, 10.2, 9.8, 10.3,
                    10.8, 11.1, 11.0, 11.4,
                    11.7, 12.1, 11.9, 12.4,
                    12.8, 13.1, 13.3, 13.6,
                ],
            ),
        ]

        rows_to_add: list[TimeSeriesModel] = []
        for ticker, name, values in series_catalog:
            for dt, val in zip(quarter_dates, values):
                rows_to_add.append(
                    TimeSeriesModel(
                        ticker=ticker,
                        date=dt,
                        name=name,
                        value=float(val),
                    )
                )
        session.add_all(rows_to_add)


# ============================================================================
# Initialisierung & Beispiel-Publikationen (Seed Data)
# ============================================================================

SAMPLE_SVG_RATES = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 320" width="680" height="320">
  <rect width="680" height="320" fill="#FFFFFF"/>
  <!-- Grid lines -->
  <g stroke="#E2E8F0" stroke-width="1">
    <line x1="55" y1="35" x2="650" y2="35"/>
    <line x1="55" y1="90" x2="650" y2="90"/>
    <line x1="55" y1="145" x2="650" y2="145"/>
    <line x1="55" y1="200" x2="650" y2="200"/>
    <line x1="55" y1="255" x2="650" y2="255"/>
  </g>
  <!-- Y-Axis Labels -->
  <g font-family="Yoga Sans for LUKB Light, Calibri, Arial, sans-serif" font-size="11" fill="#5A687C" text-anchor="end">
    <text x="46" y="39">5.0 %</text>
    <text x="46" y="94">3.75 %</text>
    <text x="46" y="149">2.50 %</text>
    <text x="46" y="204">1.25 %</text>
    <text x="46" y="259">0.00 %</text>
  </g>
  <!-- X-Axis Labels -->
  <g font-family="Yoga Sans for LUKB Light, Calibri, Arial, sans-serif" font-size="11" fill="#5A687C" text-anchor="middle">
    <text x="80" y="280">2022</text>
    <text x="215" y="280">2023</text>
    <text x="350" y="280">2024</text>
    <text x="485" y="280">2025</text>
    <text x="620" y="280">2026 (P)</text>
  </g>
  <!-- Forecast Shaded Area -->
  <rect x="485" y="35" width="165" height="220" fill="#F4F7FA" opacity="0.75"/>
  <line x1="485" y1="35" x2="485" y2="255" stroke="#002855" stroke-dasharray="4,4" stroke-width="1"/>
  <text x="567" y="52" font-family="Yoga Sans for LUKB Medium, Calibri, Arial, sans-serif" font-size="10" fill="#002855" text-anchor="middle">LUKB Prognose</text>
  <!-- Fed Line (Navy) -->
  <polyline fill="none" stroke="#002855" stroke-width="3" points="80,235 150,140 215,50 290,42 350,55 420,95 485,125 555,142 620,152"/>
  <!-- ECB Line (Cyan) -->
  <polyline fill="none" stroke="#009FE3" stroke-width="3" points="80,255 150,190 215,90 290,78 350,105 420,145 485,168 555,178 620,182"/>
  <!-- SNB Line (Gold) -->
  <polyline fill="none" stroke="#C59B27" stroke-width="3" points="80,268 150,230 215,180 290,178 350,200 420,222 485,238 555,244 620,244"/>
  <!-- Legend -->
  <g transform="translate(80, 302)" font-family="Yoga Sans for LUKB Medium, Calibri, Arial, sans-serif" font-size="11" fill="#1A2433">
    <line x1="0" y1="-4" x2="22" y2="-4" stroke="#002855" stroke-width="3"/>
    <text x="28" y="0">US Fed Funds Rate</text>
    <line x1="170" y1="-4" x2="192" y2="-4" stroke="#009FE3" stroke-width="3"/>
    <text x="198" y="0">EZB Einlagesatz</text>
    <line x1="330" y1="-4" x2="352" y2="-4" stroke="#C59B27" stroke-width="3"/>
    <text x="358" y="0">SNB Leitzins (CHF)</text>
  </g>
</svg>"""

SAMPLE_SVG_EQUITY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 300" width="680" height="300">
  <rect width="680" height="300" fill="#FFFFFF"/>
  <g stroke="#E2E8F0" stroke-width="1">
    <line x1="60" y1="30" x2="640" y2="30"/>
    <line x1="60" y1="85" x2="640" y2="85"/>
    <line x1="60" y1="140" x2="640" y2="140"/>
    <line x1="60" y1="195" x2="640" y2="195"/>
    <line x1="60" y1="250" x2="640" y2="250"/>
  </g>
  <g font-family="Yoga Sans for LUKB Light, Calibri, Arial, sans-serif" font-size="11" fill="#5A687C" text-anchor="end">
    <text x="50" y="34">125</text>
    <text x="50" y="89">115</text>
    <text x="50" y="144">105</text>
    <text x="50" y="199">95</text>
    <text x="50" y="254">85</text>
  </g>
  <!-- Bar chart sectors -->
  <g font-family="Yoga Sans for LUKB Medium, Calibri, Arial, sans-serif" font-size="11" fill="#1A2433" text-anchor="middle">
    <rect x="95" y="62" width="65" height="188" fill="#002855" rx="2"/>
    <text x="127" y="54" fill="#002855">+14.2 %</text>
    <text x="127" y="272">Industrie CH</text>

    <rect x="205" y="84" width="65" height="166" fill="#005A9C" rx="2"/>
    <text x="237" y="76" fill="#005A9C">+11.8 %</text>
    <text x="237" y="272">Finanzwerte</text>

    <rect x="315" y="98" width="65" height="152" fill="#009FE3" rx="2"/>
    <text x="347" y="90" fill="#009FE3">+9.6 %</text>
    <text x="347" y="272">Gesundheit</text>

    <rect x="425" y="125" width="65" height="125" fill="#6482A6" rx="2"/>
    <text x="457" y="117" fill="#5A687C">+6.4 %</text>
    <text x="457" y="272">Basiskonsum</text>

    <rect x="535" y="75" width="65" height="175" fill="#C59B27" rx="2"/>
    <text x="567" y="67" fill="#9A7615">+12.9 %</text>
    <text x="567" y="272">SMI Dividenden</text>
  </g>
</svg>"""


def _ensure_schema_columns() -> None:
    """Ergänzt nachträglich hinzugekommene Spalten in bestehenden Datenbanken (SQLite & MSSQL)."""
    try:
        from sqlalchemy import inspect, text

        with engine.connect() as conn:
            inspector = inspect(conn)
            if "io_articles" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("io_articles")}
                if "header_series" not in cols:
                    if engine.dialect.name == "sqlite":
                        conn.execute(
                            text(
                                "ALTER TABLE io_articles ADD COLUMN header_series VARCHAR(200) NOT NULL DEFAULT 'Investment Office News'"
                            )
                        )
                    else:
                        conn.execute(
                            text(
                                "ALTER TABLE io_articles ADD header_series NVARCHAR(200) NOT NULL DEFAULT 'Investment Office News'"
                            )
                        )
                    conn.commit()
    except Exception as exc:
        logger.warning("Schema-Migration io_articles.header_series übersprungen: %s", exc)


def init_db_and_seed() -> None:
    """Erstellt alle MSSQL/SQLAlchemy-Tabellen und legt initiale Beispielartikel an, falls leer."""
    Base.metadata.create_all(bind=engine)
    _ensure_schema_columns()
    _seed_sample_timeseries()

    # Lege Beispiel-Assets an
    save_asset(
        filename="lukb_leitzinsen_vergleich.svg",
        mime_type="image/svg+xml",
        data=SAMPLE_SVG_RATES.encode("utf-8"),
        asset_id="asset_sample_rates",
    )
    save_asset(
        filename="lukb_schweizer_sektoren.svg",
        mime_type="image/svg+xml",
        data=SAMPLE_SVG_EQUITY.encode("utf-8"),
        asset_id="asset_sample_equity",
    )

    existing = list_articles()
    if existing:
        # Selbstheilung für Artikel, deren Blöcke durch den früheren Tuple-Bug geleert wurden,
        # sowie Aktualisierung des Standard-Disclaimers auf die aktuelle LUKB-Fassung
        with get_db_session() as session:
            for item in existing:
                row = session.get(ArticleModel, item["id"])
                if not row:
                    continue
                if not row.disclaimer or row.disclaimer.strip() == LEGACY_LUKB_DISCLAIMER:
                    row.disclaimer = DEFAULT_LUKB_DISCLAIMER
                if not row.blocks_json or row.blocks_json.strip() == "[]":
                    for rev in row.revisions:
                        try:
                            snap = json.loads(rev.snapshot_json)
                            if snap.get("blocks"):
                                row.blocks_json = json.dumps(snap["blocks"], ensure_ascii=False)
                                break
                        except Exception:
                            pass
        return

    # Beispiel-Artikel 1: Investment Focus (2-spaltiges Flaggschiff-Layout)
    art1 = ArticleDocument(
        id="art-lukb-focus-2026-q4",
        template_id="investment_focus",
        status="published",
        metadata=ArticleMetadata(
            title="Zinswende und Schweizer Qualitätsaktien im Fokus",
            subtitle="Anlagepolitik & Marktausblick — 4. Quartal 2026",
            lead=(
                "Das globale Wachstum stabilisiert sich auf moderatem Niveau, während das tiefere Zinsumfeld "
                "in der Schweiz dividendenstarke Qualitätsaktien und erstklassige Unternehmensanleihen "
                "gegenüber Liquidität deutlich begünstigt."
            ),
            publication_date="2026-11-05",
            category="Anlagepolitik & Märkte",
            authors=[
                AuthorItem(name="Titel Vorname Name", role="Chief Investment Officer"),
                AuthorItem(name="Sabine Lustenberger, CFA", role="Leiterin Aktienanalyse"),
            ],
        ),
        blocks=[
            {
                "id": "blk_intro_callout",
                "type": "callout",
                "title": "Kernaussagen des Anlageausschusses",
                "html": (
                    "<ul>"
                    "<li><strong>Geldpolitik:</strong> Die Schweizerische Nationalbank (SNB) hält das Zinsniveau "
                    "nahe null, wodurch reale Renditen auf Kontoguthaben negativ bleiben.</li>"
                    "<li><strong>Aktienquote:</strong> Wir bestätigen unser Übergewicht in Schweizer Qualitäts- "
                    "und Dividendentiteln mit hoher Preissetzungsmacht.</li>"
                    "<li><strong>Obligationen:</strong> Mittlere Laufzeiten (5 bis 7 Jahre) bieten das attraktivste "
                    "Risiko-Ertrags-Profil in Schweizer Franken.</li>"
                    "</ul>"
                ),
            },
            {
                "id": "blk_h1_macro",
                "type": "heading",
                "level": 1,
                "text": "Geldpolitisches Umfeld: Stabilisierung auf tieferem Niveau",
            },
            {
                "id": "blk_p1_macro",
                "type": "richtext",
                "html": (
                    "<p>Nach dem ausgeprägten Zinssenkungszyklus der vergangenen Quartale befinden sich die "
                    "grossen Notenbanken in einer Phase der geldpolitischen Feinjustierung. In der Schweiz liegt "
                    "die Teuerung weiterhin komfortabel im Zielband der SNB unterhalb von 1,0 Prozent. Für "
                    "Anlegerinnen und Anleger bedeutet dies, dass kurzfristige Geldmarktanlagen kaum noch "
                    "nominale Erträge abwerfen.</p>"
                    "<p>In den USA und der Eurozone nähern sich die Leitzinsen schrittweise dem neutralen "
                    "Gleichgewichtszins an. Davon profitieren insbesondere Unternehmen mit solider Bilanzstruktur "
                    "und planbaren Cashflows.</p>"
                ),
            },
            {
                "id": "blk_fig_rates",
                "type": "figure",
                "title": "Leitzinsentwicklung im internationalen Vergleich",
                "subtitle": "Leitzinsen von Fed, EZB und SNB in Prozent (ab Q4 2025 Prognose LUKB)",
                "source": "Quelle: Bloomberg, SNB, LUKB Investment Office",
                "asset_id": "asset_sample_rates",
                "layout": "column",
            },
            {
                "id": "blk_h1_alloc",
                "type": "heading",
                "level": 1,
                "text": "Taktische Positionierung im Portfolio",
            },
            {
                "id": "blk_p2_alloc",
                "type": "richtext",
                "html": (
                    "<p>Im Rahmen unserer jüngsten Sitzung des Anlageausschusses haben wir die "
                    "Übergewichtung in Schweizer Aktien zulasten der Liquiditätsquote um weitere 1,5 Prozentpunkte "
                    "ausgebaut. Zyklische Industriewerte mit globaler Nischenführerschaft sowie defensive "
                    "Dividendentitel weisen für 2027 ein attraktives Gewinnwachstum von rund 8 Prozent auf.</p>"
                ),
            },
            {
                "id": "blk_tbl_taa",
                "type": "table",
                "title": "Taktische Asset Allocation (Ausgewogenes Mandat CHF)",
                "subtitle": "Aktuelle Gewichtung im Vergleich zur strategischen Benchmark",
                "source": "Quelle: LUKB Anlageausschuss, Stand November 2026",
                "layout": "full",
                "highlight_last_row": True,
                "columns": [
                    {"field": "asset", "title": "Anlageklasse", "align": "left"},
                    {"field": "saa", "title": "Strategisch (SAA)", "align": "right"},
                    {"field": "taa", "title": "Taktisch (TAA)", "align": "right"},
                    {"field": "diff", "title": "Abweichung", "align": "right"},
                    {"field": "view", "title": "Einschätzung", "align": "center"},
                ],
                "rows": [
                    {
                        "asset": "Liquidität & Geldmarkt",
                        "saa": "5.0 %",
                        "taa": "2.5 %",
                        "diff": "-2.5 %",
                        "view": "Untergewicht",
                    },
                    {
                        "asset": "Obligationen CHF & Global (Hedged)",
                        "saa": "38.0 %",
                        "taa": "37.5 %",
                        "diff": "-0.5 %",
                        "view": "Neutral",
                    },
                    {
                        "asset": "Aktien Schweiz",
                        "saa": "22.0 %",
                        "taa": "25.0 %",
                        "diff": "+3.0 %",
                        "view": "Übergewicht",
                    },
                    {
                        "asset": "Aktien Welt (Industrie- & Schwellenländer)",
                        "saa": "23.0 %",
                        "taa": "23.0 %",
                        "diff": "0.0 %",
                        "view": "Neutral",
                    },
                    {
                        "asset": "Immobilien Schweiz & Alternative Anlagen",
                        "saa": "12.0 %",
                        "taa": "12.0 %",
                        "diff": "0.0 %",
                        "view": "Neutral",
                    },
                    {
                        "asset": "Gesamtportfolio Mandat Ausgewogen",
                        "saa": "100.0 %",
                        "taa": "100.0 %",
                        "diff": "0.0 %",
                        "view": "Investiert",
                    },
                ],
            },
        ],
    )
    save_article(art1, user="Dr. Reto Krähenbühl", create_revision=True, revision_note="Erstpublikation Q4")

    # Beispiel-Artikel 2: Market Flash (Kompakter 1-Seiter)
    art2 = ArticleDocument(
        id="art-lukb-flash-ch-equities",
        template_id="market_flash",
        status="review",
        metadata=ArticleMetadata(
            title="Schweizer Dividendentitel vor starker Berichtssaison",
            subtitle="Market Flash — Fokus Aktien Schweiz",
            lead=(
                "Trotz eines starken Schweizer Frankens überzeugen heimische Qualitätsunternehmen "
                "mit steigenden operativen Margen und nachhaltigen Ausschüttungsrenditen von über 3,2 Prozent."
            ),
            publication_date="2026-11-04",
            category="Market Flash",
            authors=[
                AuthorItem(name="Sabine Lustenberger, CFA", role="Leiterin Aktienanalyse"),
            ],
        ),
        blocks=[
            {
                "id": "blk_f2_h1",
                "type": "heading",
                "level": 1,
                "text": "Hohe Preissetzungsmacht schützt operative Margen",
            },
            {
                "id": "blk_f2_p1",
                "type": "richtext",
                "html": (
                    "<p>Schweizer Unternehmen aus den Bereichen Spezialchemie, Medizintechnik und "
                    "Versicherungen profitieren von ihrer ausgeprägten Innovationskraft. Währungseffekte "
                    "werden durch globale Produktionsstandorte natürlich abgesichert.</p>"
                ),
            },
            {
                "id": "blk_f2_fig",
                "type": "figure",
                "title": "Gesamtrendite Schweizer Aktiensektoren (Laufendes Jahr)",
                "subtitle": "Indexierte Performance inkl. reinvestierter Dividenden in CHF",
                "source": "Quelle: SIX Swiss Exchange, LUKB Investment Office",
                "asset_id": "asset_sample_equity",
                "layout": "full",
            },
        ],
    )
    save_article(art2, user="Sabine Lustenberger, CFA", create_revision=True, revision_note="Entwurf zur Prüfung")
