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


def _read_manifest(dist_dir: Path) -> dict[str, Any]:
    manifest_path = dist_dir / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Konnte manifest.json nicht lesen ({exc}), erstelle neues Manifest.")
    return {"articles": {}, "last_updated": datetime.now(timezone.utc).isoformat()}


def _write_manifest(dist_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["last_updated"] = datetime.now(timezone.utc).isoformat()
    manifest_path = dist_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


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


def publish_article(doc: ArticleDocument, output_dir: Path | None = None) -> dict[str, Any]:
    """
    Publiziert einen Artikel auf das statische Portal (oder überschreibt einen bestehenden).
    - Rendert die Web-HTML-Ansicht
    - Rendert das druckreife Typst-PDF
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

    manifest["articles"][doc.id] = {
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

    # 4. Manifest speichern & Portal-Index neu bauen
    _write_manifest(dist_dir, manifest)
    _render_portal_index(dist_dir, manifest)

    logger.info(f"Artikel {doc.id} erfolgreich publiziert unter articles/{slug}/index.html")

    return {
        "success": True,
        "action": "published",
        "article_id": doc.id,
        "slug": slug,
        "article_url": f"articles/{slug}/index.html",
        "pdf_url": f"articles/{slug}/{pdf_filename}" if has_pdf else None,
        "total_published": len(manifest["articles"]),
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

    logger.info(f"Artikel {article_id} (slug: {slug}) erfolgreich vom Portal entfernt.")

    return {
        "success": True,
        "action": "unpublished",
        "article_id": article_id,
        "slug": slug,
        "total_published": len(manifest.get("articles", {})),
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
    """
    dist_dir = output_dir or STATIC_PORTAL_DIR
    if not (dist_dir / "index.html").exists():
        raise FileNotFoundError(f"Kann kein Bundle schnüren: {dist_dir / 'index.html'} existiert nicht.")

    target_archive = bundle_path or (dist_dir.parent / "connect_static_portal_bundle.tar.gz")

    with tarfile.open(target_archive, "w:gz") as tar:
        for item in dist_dir.rglob("*"):
            arcname = item.relative_to(dist_dir)
            tar.add(item, arcname=str(arcname))

    logger.info(f"Posit Connect Bundle erstellt: {target_archive} ({target_archive.stat().st_size} Bytes)")
    return target_archive
