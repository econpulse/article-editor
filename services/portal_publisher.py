"""
services/portal_publisher.py
=============================
Entkoppelter Static Site Generator & Publisher Service für das LUKB Investment Office.

Erzeugt und verwaltet ein 100% statisches, durchsuchbares Magazin-Portal für Posit Connect
(ohne Shiny-Server-Prozesse, ohne Named-User-Lizenzen, login-frei zugänglich).

Hauptfunktionen:
- publish_article: Veröffentlicht oder überschreibt einen Artikel (HTML + druckreifes Typst-PDF).
- unpublish_article: Entfernt einen Artikel aus dem Portal und aktualisiert den Index.
- rebuild_full_portal: Baut das gesamte Portal aus allen publizierten Artikeln neu auf.
- create_connect_bundle: Packt die statische Distribution in ein Posit Connect Deploy-Bundle (.tar.gz).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from config import BASE_DIR, STATIC_PORTAL_DIR, WWW_DIR
from schemas.article import ArticleDocument
from services.renderer import format_publication_date, render_pdf_bytes, render_web_html

logger = logging.getLogger(__name__)

PORTAL_TEMPLATES_DIR = BASE_DIR / "templates" / "portal"
LUKB_LOGO_SRC = WWW_DIR / "img" / "LUKB-Logo.svg"
if not LUKB_LOGO_SRC.exists():
    LUKB_LOGO_SRC = BASE_DIR / "templates" / "investment_focus" / "LUKB-Logo.svg"


def _slugify(text: str) -> str:
    """Erzeugt einen sauberen, URL-freundlichen Slug."""
    text = (text or "").strip().lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")[:65] or "publikation"


def _make_article_slug(doc: ArticleDocument) -> str:
    """Generiert einen eindeutigen Slug aus Publikationsdatum, Titel und ID-Suffix."""
    date_part = (doc.metadata.publication_date or "2026-01-01").replace("/", "-")
    title_part = _slugify(doc.metadata.title)
    short_id = doc.id[:8]
    return f"{date_part}-{title_part}-{short_id}"


def _get_portal_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(PORTAL_TEMPLATES_DIR)),
        autoescape=True,
    )


def _ensure_portal_assets(dist_dir: Path) -> None:
    """Kopiert statische Assets (CSS, JS, Logo) in das Ausgabeverzeichnis."""
    assets_dist = dist_dir / "assets"
    assets_dist.mkdir(parents=True, exist_ok=True)

    src_assets = PORTAL_TEMPLATES_DIR / "assets"
    if src_assets.exists():
        for asset_file in src_assets.glob("*"):
            if asset_file.is_file():
                shutil.copy2(asset_file, assets_dist / asset_file.name)

    # Logo kopieren
    if LUKB_LOGO_SRC.exists():
        shutil.copy2(LUKB_LOGO_SRC, assets_dist / "LUKB-Logo.svg")


def _write_connect_manifest(dist_dir: Path) -> None:
    """Schreibt das offizielle Posit Connect manifest.json für statischen Content."""
    connect_manifest = {
        "version": 1,
        "locale": "de_CH",
        "metadata": {
            "appmode": "static",
            "primary_html": "index.html",
        },
    }
    (dist_dir / "manifest.json").write_text(json.dumps(connect_manifest, indent=2), encoding="utf-8")


def _read_manifest(dist_dir: Path) -> dict[str, Any]:
    # Primär: portal-manifest.json
    p_manifest = dist_dir / "portal-manifest.json"
    if p_manifest.exists():
        try:
            return json.loads(p_manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Konnte portal-manifest.json nicht lesen ({exc}), erstelle neues Manifest.")

    # Abwärtskompatibilität: altes manifest.json mit "articles" Schlüssel
    legacy_manifest = dist_dir / "manifest.json"
    if legacy_manifest.exists():
        try:
            data = json.loads(legacy_manifest.read_text(encoding="utf-8"))
            if "articles" in data:
                return data
        except Exception:
            pass

    return {"articles": {}, "last_updated": datetime.now(timezone.utc).isoformat()}


def _write_manifest(dist_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["last_updated"] = datetime.now(timezone.utc).isoformat()
    (dist_dir / "portal-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_connect_manifest(dist_dir)


def _render_portal_index(dist_dir: Path, manifest: dict[str, Any]) -> None:
    """Rendert die statische Magazin-Übersichtsseite (index.html) und search-index.json."""
    env = _get_portal_jinja_env()
    template = env.get_template("portal_index.html.j2")

    articles_list = list(manifest.get("articles", {}).values())
    # Sortiere nach Publikationsdatum absteigend, dann nach ID
    articles_list.sort(key=lambda a: (a.get("publication_date", ""), a.get("published_at", "")), reverse=True)

    # Kategorien zählen
    categories: dict[str, int] = {}
    for art in articles_list:
        cat = art.get("category", "Anlagepolitik & Märkte")
        categories[cat] = categories.get(cat, 0) + 1

    build_date = datetime.now().strftime("%d. %B %Y")
    rendered_html = template.render(
        articles=articles_list,
        categories=categories,
        build_date=build_date,
    )

    (dist_dir / "index.html").write_text(rendered_html, encoding="utf-8")

    # Such-Index für schnellen Client-Side-Download
    search_index = [
        {
            "id": a.get("id"),
            "slug": a.get("slug"),
            "title": a.get("title"),
            "subtitle": a.get("subtitle"),
            "lead": a.get("lead"),
            "category": a.get("category"),
            "date": a.get("publication_date"),
            "date_display": a.get("date_display"),
            "authors": a.get("authors_str"),
            "url": f"articles/{a.get('slug')}/index.html",
            "pdf_url": f"articles/{a.get('slug')}/{a.get('slug')}.pdf" if a.get("has_pdf") else "",
        }
        for a in articles_list
    ]
    (dist_dir / "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _inject_portal_nav(article_html: str, slug: str, has_pdf: bool) -> str:
    """Fügt in die generierte Artikel-HTML-Seite eine dezente Portal-Navigationsleiste ein."""
    nav_bar = f"""
  <header class="article-nav-header">
    <div class="article-nav-container">
      <a href="../../index.html" class="article-back-link">
        <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
        Zurück zur Publikations-Übersicht
      </a>
      <div class="article-nav-actions">
        {"<a href='" + slug + ".pdf' download class='btn-nav-pdf'><svg width='16' height='16' fill='none' stroke='currentColor' viewBox='0 0 24 24'><path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4'></path></svg> PDF Dokument</a>" if has_pdf else ""}
      </div>
    </div>
  </header>
"""
    # Link zu portal.css in head einfügen
    head_css = '<link rel="stylesheet" href="../../assets/portal.css">\n'

    if "<head>" in article_html:
        article_html = article_html.replace("<head>", f"<head>\n{head_css}", 1)
    if "<body>" in article_html:
        article_html = article_html.replace("<body>", f"<body>\n{nav_bar}", 1)
    else:
        article_html = nav_bar + article_html

    return article_html


def publish_article(
    doc: ArticleDocument,
    output_dir: Path | None = None,
    user: str = "Investment Office",
    change_note: str = "",
) -> dict[str, Any]:
    """
    Publiziert einen Artikel auf das statische Portal (oder überschreibt einen bestehenden).
    - Rendert die Web-HTML-Ansicht
    - Rendert das druckreife Typst-PDF
    - Speichert den fertigen Snapshot versioniert in MSSQL (io_published_snapshots)
    - Schreibt Dateien in `dist/articles/<slug>/`
    - Aktualisiert `manifest.json`, `index.html` und `search-index.json`.
    """
    dist_dir = output_dir or STATIC_PORTAL_DIR
    dist_dir.mkdir(parents=True, exist_ok=True)
    _ensure_portal_assets(dist_dir)

    manifest = _read_manifest(dist_dir)
    existing_entry = manifest.get("articles", {}).get(doc.id)

    slug = _make_article_slug(doc)

    # Falls der Artikel bereits unter einem anderen Slug publiziert war: alten Ordner aufräumen
    if existing_entry and existing_entry.get("slug") and existing_entry.get("slug") != slug:
        old_dir = dist_dir / "articles" / existing_entry["slug"]
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)

    article_dir = dist_dir / "articles" / slug
    article_dir.mkdir(parents=True, exist_ok=True)

    # 1. Typst PDF rendern
    pdf_filename = f"{slug}.pdf"
    pdf_path = article_dir / pdf_filename
    has_pdf = False
    pdf_bytes = None
    try:
        pdf_bytes = render_pdf_bytes(doc)
        pdf_path.write_bytes(pdf_bytes)
        has_pdf = True
    except Exception as exc:
        logger.error(f"Fehler beim Rendern des PDFs für {doc.id}: {exc}", exc_info=True)

    # 2. Web HTML rendern & Portal-Navigation einbetten
    base_html = render_web_html(doc)
    full_html = _inject_portal_nav(base_html, slug, has_pdf)
    (article_dir / "index.html").write_text(full_html, encoding="utf-8")

    # 3. Metadaten für das Portal aufbereiten
    date_display = format_publication_date(doc.metadata.publication_date) or doc.metadata.publication_date or "Aktuell"
    authors_str = " · ".join([a.name for a in doc.metadata.authors])

    meta_entry = {
        "id": doc.id,
        "slug": slug,
        "title": doc.metadata.title,
        "subtitle": doc.metadata.subtitle,
        "lead": doc.metadata.lead,
        "category": doc.metadata.category or "Anlagepolitik & Märkte",
        "template_id": doc.template_id,
        "publication_date": doc.metadata.publication_date,
        "date_display": date_display,
        "authors": [a.model_dump() for a in doc.metadata.authors],
        "authors_str": authors_str,
        "tags_str": "",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "has_pdf": has_pdf,
    }
    manifest["articles"][doc.id] = meta_entry

    # 3.5. Revisionssicheren Snapshot in MSSQL versioniert abspeichern
    snapshot_version = 1
    try:
        from database.repository import save_published_snapshot

        snapshot_version = save_published_snapshot(
            article_id=doc.id,
            slug=slug,
            title=doc.metadata.title,
            publication_date=doc.metadata.publication_date or "",
            metadata_dict=meta_entry,
            html_content=full_html,
            pdf_bytes=pdf_bytes if has_pdf else None,
            user=user,
            change_note=change_note,
        )
    except Exception as exc:
        logger.warning(f"Snapshot für Artikel {doc.id} konnte nicht in MSSQL gespeichert werden: {exc}")

    # 4. Manifest speichern & Portal-Index neu bauen
    _write_manifest(dist_dir, manifest)
    _render_portal_index(dist_dir, manifest)

    logger.info(
        f"Artikel {doc.id} erfolgreich publiziert unter articles/{slug}/index.html (Version {snapshot_version})"
    )

    # 5. Optional: Automatisches Deployment auf Posit Connect (falls API konfiguriert)
    connect_deploy = None
    try:
        from services.connect_client import deploy_bundle_to_connect, is_connect_configured

        if is_connect_configured():
            bundle_path = create_connect_bundle(output_dir=dist_dir)
            connect_deploy = deploy_bundle_to_connect(bundle_path)
    except Exception as exc:
        logger.error(f"Fehler beim Posit Connect API Deployment: {exc}")
        connect_deploy = {"success": False, "error": str(exc)}

    return {
        "success": True,
        "action": "published",
        "article_id": doc.id,
        "version": snapshot_version,
        "slug": slug,
        "article_url": f"articles/{slug}/index.html",
        "pdf_url": f"articles/{slug}/{pdf_filename}" if has_pdf else None,
        "total_published": len(manifest["articles"]),
        "connect_deploy": connect_deploy,
    }


def unpublish_article(article_id: str, output_dir: Path | None = None) -> dict[str, Any]:
    """
    Entfernt einen publizierten Artikel vollständig vom statischen Portal.
    Löscht den Artikel-Ordner und aktualisiert die Übersichtsseite und den Suchindex.
    """
    dist_dir = output_dir or STATIC_PORTAL_DIR
    if not dist_dir.exists():
        return {"success": True, "action": "unpublish_noop", "message": "Portalverzeichnis existiert nicht."}

    manifest = _read_manifest(dist_dir)
    existing_entry = manifest.get("articles", {}).pop(article_id, None)

    if not existing_entry:
        return {
            "success": True,
            "action": "not_found",
            "message": f"Artikel {article_id} war nicht im Portal publiziert.",
            "total_published": len(manifest.get("articles", {})),
        }

    slug = existing_entry.get("slug")
    if slug:
        article_dir = dist_dir / "articles" / slug
        if article_dir.exists():
            shutil.rmtree(article_dir, ignore_errors=True)

    _write_manifest(dist_dir, manifest)
    _render_portal_index(dist_dir, manifest)

    # Snapshot in MSSQL deaktivieren (bleibt für Audit-Historie erhalten)
    try:
        from database.repository import deactivate_published_snapshot

        deactivate_published_snapshot(article_id)
    except Exception as exc:
        logger.warning(f"Snapshot-Deaktivierung für {article_id} in MSSQL fehlgeschlagen: {exc}")

    logger.info(f"Artikel {article_id} (slug: {slug}) erfolgreich vom Portal entfernt.")

    # Automatisches Deployment auf Posit Connect nach Entfernen
    connect_deploy = None
    try:
        from services.connect_client import deploy_bundle_to_connect, is_connect_configured
        if is_connect_configured():
            bundle_path = create_connect_bundle(output_dir=dist_dir)
            connect_deploy = deploy_bundle_to_connect(bundle_path)
    except Exception as exc:
        logger.error(f"Fehler beim Posit Connect API Deployment nach Unpublish: {exc}")
        connect_deploy = {"success": False, "error": str(exc)}

    return {
        "success": True,
        "action": "unpublished",
        "article_id": article_id,
        "slug": slug,
        "total_published": len(manifest.get("articles", {})),
        "connect_deploy": connect_deploy,
    }


def restore_portal_from_snapshots(output_dir: Path | None = None) -> dict[str, Any]:
    """
    Stellt das gesamte Portal blitzschnell aus den in der MSSQL-Datenbank gespeicherten
    Snapshots (io_published_snapshots) wieder her.
    Es findet KEIN dynamisches Re-Rendering von Typst oder Charts statt!
    Konserviert exakt die historischen HTML- und PDF-Dateien zum Veröffentlichungszeitpunkt.
    """
    dist_dir = output_dir or STATIC_PORTAL_DIR
    dist_dir.mkdir(parents=True, exist_ok=True)
    _ensure_portal_assets(dist_dir)

    from database.repository import get_active_published_snapshots

    active_snaps = get_active_published_snapshots()

    # Fallback/Migration: Falls noch keine Snapshots vorhanden sind, aber Artikel als 'published' markiert sind
    if not active_snaps:
        try:
            from database.repository import get_article, list_articles

            published_items = list_articles(status_filter="published")
            if published_items:
                logger.info(
                    f"Keine Snapshots gefunden, initialisiere Snapshots für {len(published_items)} bestehende publizierte Artikel..."
                )
                for item in published_items:
                    doc = get_article(item["id"])
                    if doc:
                        publish_article(doc, output_dir=dist_dir)
                active_snaps = get_active_published_snapshots()
        except Exception as exc:
            logger.warning(f"Initial-Migration für Snapshots fehlgeschlagen: {exc}")

    manifest: dict[str, Any] = {"articles": {}, "last_updated": datetime.now(timezone.utc).isoformat()}

    for snap in active_snaps:
        slug = snap.get("slug")
        if not slug:
            continue
        article_dir = dist_dir / "articles" / slug
        article_dir.mkdir(parents=True, exist_ok=True)

        # 1. Gespeichertes Original-HTML schreiben
        (article_dir / "index.html").write_text(snap.get("html_content") or "", encoding="utf-8")

        # 2. Gespeichertes Original-PDF schreiben
        has_pdf = False
        pdf_bytes = snap.get("pdf_bytes")
        if pdf_bytes:
            pdf_path = article_dir / f"{slug}.pdf"
            pdf_path.write_bytes(pdf_bytes)
            has_pdf = True

        # 3. Metadaten für Manifest & Suchindex übernehmen
        meta = dict(snap.get("metadata") or {})
        meta["id"] = snap.get("article_id")
        meta["slug"] = slug
        meta["title"] = snap.get("title")
        meta["has_pdf"] = has_pdf
        manifest["articles"][snap["article_id"]] = meta

    _write_manifest(dist_dir, manifest)
    _render_portal_index(dist_dir, manifest)

    logger.info(
        f"Portal erfolgreich aus {len(manifest['articles'])} MSSQL-Snapshots wiederhergestellt (Verzeichnis: {dist_dir})."
    )
    return {
        "success": True,
        "restored_count": len(manifest["articles"]),
        "dist_dir": str(dist_dir),
    }


def rebuild_full_portal(
    articles: list[ArticleDocument] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Baut das gesamte Portal von Grund auf neu auf (z. B. nach Template-Änderungen).
    """
    dist_dir = output_dir or STATIC_PORTAL_DIR
    dist_dir.mkdir(parents=True, exist_ok=True)
    _ensure_portal_assets(dist_dir)

    manifest: dict[str, Any] = {"articles": {}}

    docs_to_publish = articles or []
    for doc in docs_to_publish:
        res = publish_article(doc, output_dir=dist_dir)
        logger.info(f"Rebuild: {doc.id} -> {res.get('slug')}")

    manifest = _read_manifest(dist_dir)
    _render_portal_index(dist_dir, manifest)

    return {
        "success": True,
        "total_published": len(manifest.get("articles", {})),
        "dist_dir": str(dist_dir),
    }


def create_connect_bundle(
    output_dir: Path | None = None,
    bundle_path: Path | None = None,
) -> Path:
    """
    Schnürt ein Posit-Connect-kompatibles .tar.gz Deployment-Archiv des statischen Portals.
    Stellt sicher, dass alle publizierten Artikel aus den MSSQL-Snapshots enthalten sind.
    """
    import tempfile

    dist_dir = output_dir or STATIC_PORTAL_DIR
    dist_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sicherstellen, dass das Portal aus den aktiven MSSQL-Snapshots vollständig befüllt ist
    if not (dist_dir / "index.html").exists():
        try:
            restore_portal_from_snapshots(output_dir=dist_dir)
        except Exception as exc:
            logger.warning(f"Wiederherstellung aus MSSQL-Snapshots fehlgeschlagen ({exc}), erstelle leere Grundstruktur.")
            _ensure_portal_assets(dist_dir)
            manifest = _read_manifest(dist_dir)
            _render_portal_index(dist_dir, manifest)
            _write_manifest(dist_dir, manifest)

    # Posit Connect manifest.json sicherstellen
    _write_connect_manifest(dist_dir)

    # 2. Zielpfad bestimmen (mit Fallback auf tempfile bei schreibgeschützten Deployment-Systemen)
    if bundle_path:
        target_archive = bundle_path
    else:
        try:
            target_archive = dist_dir.parent / "connect_static_portal_bundle.tar.gz"
            # Prüfen ob im Ordner geschrieben werden darf
            target_archive.touch(exist_ok=True)
        except (PermissionError, OSError):
            target_archive = Path(tempfile.gettempdir()) / "connect_static_portal_bundle.tar.gz"

    # 3. Archiv packen
    with tarfile.open(target_archive, "w:gz") as tar:
        for item in dist_dir.rglob("*"):
            arcname = item.relative_to(dist_dir)
            tar.add(item, arcname=str(arcname))

    logger.info(f"Posit Connect Bundle erstellt: {target_archive} ({target_archive.stat().st_size} Bytes)")
    return target_archive
