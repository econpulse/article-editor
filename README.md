# Investment Office — Publikations-Editor & CMS bei einer Bank

Modernes, webbasiertes Content-Management-System (CMS) für Publikationen des Investment Office bei einer Bank, entwickelt für **Posit Connect** auf Basis von **Shiny for Python**, **SQLAlchemy (MS SQL Server)**, **Typst (0.15+)** und **Jinja2**.

## Dokumentation & Handbücher

- 📖 **[Benutzer-Handbuch (User Manual)](docs/USER_MANUAL.md)**: Detaillierte Schritt-für-Schritt-Anleitung für Redakteure und Autoren mit Fokus auf den interaktiven Block-Editor, Typst-Live-Preview, Tabellenkalkulation, DB-Charts und Freigabeprozesse.
- 🚀 **[Deployment-Handbuch (Deployment Manual)](docs/DEPLOYMENT_MANUAL.md)**: Vollständige Anleitung für Administratoren und DevOps zum Deployment auf Posit Connect inklusive aller Umgebungsvariablen, MSSQL-Konfiguration, SSL/CA-Handhabung und Rollensteuerung.

---

## Hauptfunktionen

1. **Interaktiver Drag-and-Drop Block-Editor (Zero-Build für Posit Connect)**
   - **Dokumenten-Kopf**: Auswahl des Publikations-Templates (*Investment Fokus* 2-spaltig oder *Market Flash* 1-spaltig), Status (*Entwurf*, *In Review*, *Publiziert*), Rubrik, Datum, Gesamttitel, Untertitel/Dachzeile, Lead-Text und dynamische Autoren-Liste.
   - **Drag-and-Drop Content-Blöcke (SortableJS)**:
     - **Überschriften (`H1`, `H2`, `H3`)** in Corporate Design Schriften
     - **Rich-Text-Absätze** mit Formatierungs-Toolbar (Fett, Kursiv, Unterstrichen, Aufzählungslisten, nummerierte Listen, Textfarben)
     - **Grafik-Container**: Mit Grafik-Titel, Grafik-Untertitel, Quellenangabe, Satzbreite (1-spaltig oder 2-spaltig) sowie **Drag-and-Drop Datei-Upload (SVG, PNG, JPG)**
     - **DB-Chart Container**: Zeitreihen-Visualisierung direkt aus der MSSQL-Datenbank (`ts_db`) mit flexiblen Diagrammtypen (Linien, Stufen, Balken, gestapelte Balken, Punkte, Flächen)
     - **Tabellen-Container**: Mit Tabellen-Titel, Tabellen-Untertitel, Quellenangabe, Satzbreite, Total-Zeilen-Hervorhebung sowie interaktivem Daten-Grid inkl. **Microsoft Excel Copy-Paste Support (`Ctrl+V`)**
     - **Kernaussagen / Callout-Boxen**, Zitate, Textbox-Gruppierungen, Abstände, Spaltenumbrüche und Glossar
2. **Redeployment-sichere MSSQL-Datenhaltung & Autosave**
   - Alle Artikel (`io_articles`), Revisions-Snapshots (`io_article_revisions`) und hochgeladenen Grafiken (`io_assets` als `VARBINARY(MAX)`) werden direkt in der **MS SQL Server Datenbank** gespeichert.
   - Dadurch gehen bei einem **App-Update oder Redeployment auf Posit Connect keinerlei Dokumente oder hochgeladene Grafiken verloren**.
   - **Debounced Autosave**: Jede Änderung im Editor wird automatisch im Hintergrund gespeichert; beim Klick auf einen anderen Artikel in der linken Übersicht wird der aktuelle Stand vor dem Wechsel sofort gesichert.
3. **Dual-Output-Engine (PDF via Typst & Web via HTML5) mit Live-Preview**
   - **PDF-Satz**: Nutzt das offizielle, native Python-Binding `typst` (aktuellste Version direkt in `requirements.txt` enthalten, kein externes CLI-Binary auf Posit Connect nötig).
   - **Echtzeit-Vorschau**: Seitenweises In-Memory-SVG-Rendering aus Typst sowie umschaltbare HTML5-Web-Vorschau.

---

## Corporate Design & Schriften

Die Typst-Templates (`templates/*/template.typ`), die Web-Templates (`templates/*/template.html.j2`) und der Editor (`www/css/editor.css`) verwenden standardmäßig die Typografie des Corporate Designs bei einer Bank:
- **Standard-Schriftart (Fließtext, Lead, Tabellen, Quellen)**: Corporate Sans Light
- **Überschriften & Hervorhebungen (Gesamttitel, H1–H3, Grafik-/Tabellentitel, Tabellenköpfe, Fettdruck)**: Corporate Sans Medium

> **Tipp für Posit Connect Server ohne vorinstallierte System-Fonts:**
> Legen Sie die `.ttf`- oder `.otf`-Dateien der Corporate Fonts einfach im Projektordner `www/fonts/` ab. Der Typst-Compiler bindet das Verzeichnis `www/fonts/` automatisch über `font_paths` ein.

---

## Konfiguration der MS SQL Server Datenbank (Posit Connect)

Hinterlegen Sie in den **Environment Variables** der Applikation auf Posit Connect (oder lokal in einer `.env`-Datei analog zu `.env.example`):

```ini
MSSQL_SERVER=ihr-mssql-server.bank.internal
MSSQL_PORT=1433
MSSQL_DATABASE=InvestmentOfficeCMS
MSSQL_USER=svc_posit_cms
MSSQL_PASSWORD=IhrPasswort
MSSQL_DRIVER=ODBC Driver 18 for SQL Server
MSSQL_TRUST_SERVER_CERTIFICATE=yes
```

Alternativ kann auch direkt eine vollständige SQLAlchemy-URL über `DATABASE_URL` übergeben werden.
*(Hinweis: Falls lokal weder `DATABASE_URL` noch `MSSQL_SERVER` gesetzt ist, nutzt die App für lokale Entwicklertests automatisch eine lokale Fallback-Datenbank unter `data/local_dev_cms.db`.)*

---

## Lokaler Start & Deployment auf Posit Connect

### 1. Lokal starten
```powershell
.\.venv\Scripts\python.exe -m shiny run app.py --reload --port 8000
```

### 2. Automatisierte Tests ausführen
```powershell
.\.venv\Scripts\python.exe tests\test_cms_pipeline.py
```

### 3. Deployment auf Posit Connect
```powershell
pip install rsconnect-python
rsconnect write-manifest shiny .
rsconnect deploy shiny . --server https://posit-connect.bank.internal --api-key <API_KEY> --title "Investment Office CMS"
```
