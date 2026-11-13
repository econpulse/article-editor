# Posit Connect Deployment Manual — Investment Office CMS

Dieses Handbuch beschreibt die vollständige Konfiguration, Vorbereitung und Bereitstellung des **Investment Office CMS & Publikations-Editors** auf einer **Posit Connect**-Instanz (vormals RStudio Connect) bei einer Bank.

---

## 1. Systemarchitektur & Deployment-Grundlagen

Das System wurde gezielt für Enterprise-Umgebungen und containerisierte Posit Connect-Server entwickelt:

```
                          ┌──────────────────────────────────────────────┐
                          │            Posit Connect Server              │
                          │                                              │
                          │   ┌──────────────────────────────────────┐   │
                          │   │       Shiny for Python App           │   │
                          │   │       (Starlette + ASGI)             │   │
                          │   │                                      │   │
   Browser-Clients ───────┼──►│  • Zero-Build Editor (Vanilla JS)    │   │
  (Autoren / Editoren)    │   │  • Typst 0.15+ (Native Python Wheel) │   │
                          │   │  • Jinja2 HTML5 Web-Engine           │   │
                          │   │  • Static Portal Mount (/portal/)    │   │
                          │   └──────────────────┬───────────────────┘   │
                          │                      │                       │
                          └──────────────────────┼───────────────────────┘
                                                 │ ODBC 18 / 1433
                                                 ▼
                          ┌──────────────────────────────────────────────┐
                          │        Microsoft SQL Server (MSSQL)          │
                          │                                              │
                          │  • io_articles (Artikel & Metadaten)         │
                          │  • io_assets (Grafiken als VARBINARY(MAX))   │
                          │  • io_article_revisions (Snapshots)          │
                          │  • io_published_snapshots (Live-Portal HTML) │
                          │  • ts_db (Zeitreihendaten für DB-Charts)     │
                          └──────────────────────────────────────────────┘
```

### Wichtige Architektur-Eigenschaften für Posit Connect
1. **Redeployment-Sicherheit (Zero Data Loss):**
   Auf Posit Connect laufen Python-Anwendungen in isolierten Prozessen oder Containern mit kurzlebigem (ephemerem) lokalem Dateisystem. Bei jedem App-Neustart oder Redeployment wird das Dateisystem zurückgesetzt. **Daher speichert das System alle Artikel, Revisionshistorien sowie hochgeladene Grafiken direkt im MS SQL Server (Grafiken als `VARBINARY(MAX)` in `io_assets`).** Es gehen beim Redeployment keinerlei Arbeitsstände verloren.
2. **Automatisches Seeding & Wiederherstellung:**
   Beim Starten ruft die Applikation `init_db_and_seed()` und `restore_portal_from_snapshots()` auf:
   - Fehlende Tabellen werden via SQLAlchemy automatisch angelegt (`CREATE TABLE IF NOT EXISTS`).
   - Das statische HTML-Portal wird bei Bedarf blitzschnell aus den in der Datenbank archivierten Snapshots (`io_published_snapshots`) materialisiert.
3. **Keine externen Compiler-Binaries erforderlich:**
   Für den PDF-Satz wird das native Python-Binding `typst` genutzt (in `requirements.txt`). Es muss **kein externes Typst-CLI-Binary** auf dem Posit Connect-Server vorinstalliert oder im System-Pfad hinterlegt werden.

---

## 2. Server-Voraussetzungen (Posit Connect Host)

Bevor die Anwendung auf Posit Connect veröffentlicht wird, müssen folgende Voraussetzungen auf dem Posit Connect-Host bzw. dem Ausführungs-Image erfüllt sein:

| Anforderung | Erforderliche Version / Paket | Bemerkung |
| :--- | :--- | :--- |
| **Python Runtime** | `Python 3.10+` oder `3.11+` | In Posit Connect aktiviert |
| **MSSQL ODBC-Treiber** | `ODBC Driver 18 for SQL Server` (oder Version 17) | Auf Linux-Host via `msodbcsql18` / `msodbcsql17` installiert |
| **ODBC Core Libraries** | `unixodbc`, `unixodbc-dev` | Erforderlich für `pyodbc` C-Bindings |
| **Netzwerkverbindung** | TCP-Port `1433` (MSSQL) freigeschaltet | Zugriff vom Posit Connect Worker-Host zum Datenbankserver |
| **Schriftarten (optional)** | `www/fonts/` im Projektverzeichnis | TTF/OTF-Dateien der Corporate Fonts werden automatisch mitgeliefert |

---

## 3. Umgebungsvariablen (Environment Variables auf Posit Connect)

Die Konfiguration erfolgt nach Best Practice über Umgebungsvariablen im Posit Connect-Dashboard (**Content Item ➜ Settings ➜ Vars**).

### A. Datenbank-Konfiguration (MS SQL Server)

| Variable | Pflicht | Typ | Standardwert | Beschreibung & Praxis-Beispiel |
| :--- | :---: | :---: | :--- | :--- |
| `MSSQL_SERVER` | **Ja** | String | *(keiner)* | Hostname oder FQDN des MSSQL-Datenbankservers.<br>`sql-db01.bank.internal` |
| `MSSQL_PORT` | Nein | Integer | `1433` | Port des MSSQL-Dienstes. |
| `MSSQL_DATABASE` | **Ja** | String | `InvestmentOfficeCMS` | Name der Datenbank auf dem SQL Server. |
| `MSSQL_USER` | **Ja** | String | *(keiner)* | Service-Account / SQL-Login für das CMS.<br>`svc_posit_cms` |
| `MSSQL_PASSWORD` | **Ja** | String | *(keiner)* | Passwort des Service-Accounts. *(Wird in Posit Connect verschlüsselt gespeichert)*. |
| `MSSQL_DRIVER` | Nein | String | `ODBC Driver 18 for SQL Server` | Exakter Name des auf dem Connect-Server installierten ODBC-Treibers. *(Bei älteren Hosts ggf. `ODBC Driver 17 for SQL Server`).* |
| `MSSQL_TRUST_SERVER_CERTIFICATE` | Nein | String | `yes` | In Bank-Intranets mit interner PKI auf `yes` setzen, um SSL-Handshake-Fehler zu vermeiden. |
| `MSSQL_ENCRYPT` | Nein | String | `no` | Verbindungsverschlüsselung (`yes`, `no` oder `optional`). |
| `MSSQL_TRUSTED_CONNECTION` | Nein | String | `no` | Auf `yes` setzen, falls Kerberos / integrierte Windows-Authentifizierung genutzt wird. |
| `DATABASE_URL` | *Alt.* | String | *(keiner)* | **Alternative:** Vollständige SQLAlchemy-Verbindungs-URL. Überschreibt alle `MSSQL_*`-Variablen, falls gesetzt. |

> [!IMPORTANT]
> **Lokaler Entwickler-Fallback:**
> Falls weder `DATABASE_URL` noch `MSSQL_SERVER` gesetzt ist (z. B. auf dem lokalen Entwickler-Laptop), schaltet die Applikation automatisch auf eine lokale SQLite-Datenbank unter `data/local_dev_cms.db` um. Auf Posit Connect **muss** `MSSQL_SERVER` definiert sein, damit Daten persistent bleiben!

---

### B. Rollen- und Berechtigungssteuerung (Workflow-Sicherheit)

Das System verfügt über eine rollenbasierte Rechteprüfung für Freigaben und Löschaktionen:

| Variable | Pflicht | Format | Beschreibung & Praxis-Beispiel |
| :--- | :---: | :--- | :--- |
| `PORTAL_PUBLISHERS` | Nein | Kommagetrennte Liste | Benutzerkürzel von Senior-Editoren, die Publikationen direkt auf dem Portal freigeben und zurückziehen dürfen.<br>`meierh,schmidtj,muellera` |
| `PORTAL_ADMINS` | Nein | Kommagetrennte Liste | Administratoren mit vollen Rechten (inkl. endgültiges Löschen von Artikeln).<br>`admin_user,meierh` |

**Rollen-Verhalten:**
- **Admin (`PORTAL_ADMINS`):** Erstellen, Bearbeiten, Review, Portal-Publikation, Portal-Rückzug, Löschen / Papierkorb leeren.
- **Publisher (`PORTAL_PUBLISHERS`):** Erstellen, Bearbeiten, Review, Portal-Publikation, Portal-Rückzug.
- **Autor (Standard-Benutzer):** Erstellen, Bearbeiten, Autosave, Einreichen zur Prüfung («In Review»).
- *(Hinweis: Bleiben `PORTAL_ADMINS` und `PORTAL_PUBLISHERS` leer, schaltet die App in den Entwicklungsmodus und gewährt allen Nutzern volle Rechte).*

---

### C. Posit Connect Portal-Deployment & API (Optional für Standalone-Portal)

Das System kann Publikationen entweder lokal im gleichen Prozess unter `/portal/` ausliefern oder über die Posit Connect REST API ein eigenständiges, login-freies statisches Content-Item bespielen:

| Variable | Pflicht | Typ | Standardwert | Beschreibung & Praxis-Beispiel |
| :--- | :---: | :---: | :--- | :--- |
| `CONNECT_SERVER` | Nein | URL | *(keiner)* | Basis-URL des Posit Connect Servers.<br>`https://posit-connect.bank.internal` |
| `CONNECT_API_KEY` | Nein | Secret | *(keiner)* | API-Key mit Publisher-Rechten zur automatischen Bundle-Aktualisierung. |
| `CONNECT_PORTAL_GUID` | Nein | String | *(keiner)* | Content-GUID des statischen Portal-Items auf Posit Connect. |
| `CONNECT_PORTAL_URL` | Nein | URL | *(keiner)* | Öffentliche URL des Portals für Autoren.<br>`https://posit-connect.bank.internal/investment-views/` |
| `CONNECT_VERIFY_SSL` | Nein | Boolean | `true` | Bei TLS-Interception (z. B. Zscaler / Banking Proxy) auf `false` setzen. |
| `CONNECT_CA_BUNDLE` | Nein | Pfad | *(keiner)* | Alternativ Pfad zu einem internen Root-CA-Zertifikatsbündel. |

---

### D. Corporate Design & Typografie

| Variable | Pflicht | Standardwert | Beschreibung |
| :--- | :---: | :--- | :--- |
| `LUKB_FONT_LIGHT` | Nein | `Yoga Sans for LUKB Light` | Schriftart für Fließtext, Tabellen und Lead. |
| `LUKB_FONT_MEDIUM` | Nein | `Yoga Sans for LUKB Medium` | Schriftart für H1–H3, Gesamttitel und Tabellenköpfe. |
| `LUKB_FONT_FAMILY_BASE` | Nein | `Yoga Sans for LUKB` | Basisname der Schriftfamilie für SVG-Generatoren. |

---

## 4. Schritt-für-Schritt Deployment-Anleitung

### Methode 1: Deployment via `rsconnect-python` CLI (Empfohlen)

Das CLI-Deployment lässt sich direkt aus dem Positron- / VS-Code-Terminal oder aus CI/CD-Pipelines (z. B. GitLab CI, GitHub Actions, Jenkins) ausführen.

#### Schritt 1: Python-Umgebung aktivieren und CLI installieren
```powershell
# Im Projektverzeichnis
pip install rsconnect-python
```

#### Schritt 2: Deployment-Manifest generieren
Das Manifest erfasst exakt alle Python-Abhängigkeiten aus `requirements.txt` sowie die Projektdateien. Da `rsconnect-python` keine `.rscignore`-Dateien auswertet (dies wird nur vom R-Paket unterstützt), müssen Entwicklungsdatenbanken und der lokale Portal-Build via `--exclude` explizit ausgeschlossen werden:
```powershell
rsconnect write-manifest shiny . --exclude "data/static_portal_dist" --exclude "data/*.db*"
```
*(Es wird eine Datei `manifest.json` erzeugt. Das statische Portal materialisiert sich auf dem Server dank Snapshot-Synchronisation vollautomatisch direkt aus MSSQL).*

#### Schritt 3: Erst-Deployment auf Posit Connect durchführen
```powershell
rsconnect deploy shiny . `
  --exclude "data/static_portal_dist" `
  --exclude "data/*.db*" `
  --server https://posit-connect.bank.internal `
  --api-key <IHR_POSIT_CONNECT_API_KEY> `
  --title "Investment Office CMS"
```

#### Schritt 4: Umgebungsvariablen in Posit Connect konfigurieren
1. Öffnen Sie die Anwendung auf Posit Connect im Browser.
2. Klicken Sie in der rechten Leiste auf **Settings** (Zahnrad) ➜ **Vars**.
3. Erfassen Sie die Variablen:
   - `MSSQL_SERVER` = `ihr-sql-server.bank.internal`
   - `MSSQL_DATABASE` = `InvestmentOfficeCMS`
   - `MSSQL_USER` = `svc_posit_cms`
   - `MSSQL_PASSWORD` = `********`
   - `MSSQL_DRIVER` = `ODBC Driver 18 for SQL Server`
   - `MSSQL_TRUST_SERVER_CERTIFICATE` = `yes`
   - `PORTAL_PUBLISHERS` = `meierh,schmidtj`
   - `PORTAL_ADMINS` = `admin_user`
4. Klicken Sie auf **Apply**. Posit Connect startet den Worker-Prozess neu und übernimmt die Konfiguration.

---

### Methode 2: Git-gestütztes Deployment (Git-Backed Content)

Wenn das Repository in einem bankinternen Git (z. B. GitLab, Bitbucket, GitHub Enterprise) liegt:

1. **Vorbereitung:**
   Stellen Sie sicher, dass eine aktuelle `manifest.json` im Repository eingecheckt ist (`rsconnect write-manifest shiny .` ausführen und `git commit manifest.json`).
2. **In Posit Connect:**
   - Klicken Sie auf **Publish** ➜ **Import from Git**.
   - Hinterlegen Sie die Repository-URL und den Ziel-Branch (z. B. `main` oder `production`).
   - Wählen Sie als Deployment-Typ **Manifest-based Deployment** (`manifest.json`).
3. **Environment Variables setzen:**
   Hinterlegen Sie wie oben beschrieben die `MSSQL_*`-Variablen im Reiter **Vars**.
4. **Automatisches Polling aktivieren:**
   Aktivieren Sie bei Bedarf «Periodic update from Git», damit Releases beim Git-Push automatisch auf Posit Connect ausgerollt werden.

---

## 5. Laufzeit-Konfiguration & Skalierung auf Posit Connect

Für einen reibungslosen Redaktionsbetrieb auf Posit Connect empfehlen sich im Tab **Access & Runtime**:

- **Max Processes:** `3` bis `5` (je nach Anzahl gleichzeitiger Redakteure).
- **Min Processes Running:** `1` (verhindert Kaltstart-Verzögerungen, da die Verbindung zum MSSQL-Server beim ersten Aufruf sofort steht).
- **Max Connections Per Process:** `10` bis `20` (Shiny for Python verarbeitet asynchrone WebSocket-Verbindungen hocheffizient).
- **Load Factor:** `0.7`
- **Access Control:** Auf «Specific users or groups» oder «Anyone with login» einschränken (z. B. AD-Gruppe `GRP_INVESTMENT_OFFICE`).

---

## 6. Deployment-Verifikation & Health-Check

Nach dem Deployment sollte folgende Checkliste überprüft werden:

```
[ ] Top-Header zeigt: "DB: MS SQL Server (ihr-sql-server/InvestmentOfficeCMS)"
    (Falls "DB: SQLite (Dev-Fallback)" erscheint, wurden die MSSQL-Variablen nicht geladen!)
[ ] Status-Pille in der Kopfzeile springt beim Laden auf grün ("Bereit").
[ ] Live-Preview rechts rendert das PDF per Typst fehlerfrei als SVG.
[ ] Klick auf "+ Neue Publikation anlegen" speichert sofort in der Datenbank.
[ ] Bild-Upload in einem Grafik-Block speichert das Asset in `io_assets`.
[ ] Test-Export: Download des druckreifen PDFs via "Export ▾ ➜ PDF Export (Typst)".
```

---

## 7. Fehlerbehebung (Troubleshooting)

### Problem A: `pyodbc.Error: ('01000', "[01000] [unixODBC][Driver Manager]Can't open lib 'ODBC Driver 18 for SQL Server'")`
- **Ursache:** Der Microsoft ODBC-Treiber ist auf dem Linux-Host nicht installiert oder der Name weicht ab.
- **Lösung:** Prüfen Sie via Terminal auf dem Host die Datei `/etc/odbcinst.ini`. Falls dort `ODBC Driver 17 for SQL Server` steht, setzen Sie die Environment-Variable `MSSQL_DRIVER=ODBC Driver 17 for SQL Server`.

### Problem B: `SSL Provider: [error:1416F086:SSL routines:pem_password_cb:certificate verify failed]`
- **Ursache:** Die interne Zertifikatskette der Bank wird vom Linux-Container nicht erkannt.
- **Lösung:** Setzen Sie `MSSQL_TRUST_SERVER_CERTIFICATE=yes` in den Posit Connect Environment Variables.

### Problem C: Sonderzeichen oder Schweizer Umlaute (ä, ö, ü, é) werden verzerrt dargestellt
- **Ursache:** Die Datenbank verwendet `VARCHAR` anstelle von Unicode.
- **Lösung:** Das ORM-Modell nutzt standardmäßig `NVARCHAR` und `NVARCHAR(MAX)`. Bei neuen Datenbanken stellt `init_db_and_seed()` die korrekten Typen automatisch sicher.

### Problem D: Schriften im PDF weichen vom Corporate Design ab
- **Ursache:** Die Schriftart-Dateien sind auf dem Linux-Server nicht systemweit installiert.
- **Lösung:** Kopieren Sie die `.ttf`-Dateien einfach in den Projektordner `www/fonts/`. Typst lädt Schriftarten direkt aus diesem Verzeichnis.
