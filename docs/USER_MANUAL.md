# Benutzer-Handbuch (User Manual) — Investment Office CMS

Willkommen im webbasierten **Content-Management-System (CMS) & Publikations-Editor** des Investment Office bei einer Bank.

Dieses Handbuch richtet sich an Redakteure, Analysten und Autoren, die Publikationen schnell, professionell und ohne manuellen Layout-Aufwand in Word oder InDesign erstellen möchten.

---

## 1. Was bietet das System?

Traditionell war das Erstellen von Finanzpublikationen mit zeitraubender Formatierung in Word, Excel-Screenshots und manuellem Satz im Corporate Design verbunden. Dieses CMS revolutioniert den Prozess:

- **100 % Corporate Design Konformität:** Sie konzentrieren sich rein auf den Inhalt; das Satzprogramm (**Typst**) sorgt vollautomatisch für makellose Typografie, Spaltenumbrüche und CI-Farben.
- **Interaktiver Block-Editor:** Ihr Dokument besteht aus handlichen Bausteinen (Text, Grafiken, Tabellen, Charts), die Sie intuitiv verschieben, kopieren und formatieren können.
- **Echtzeit-Druckvorschau:** Sie sehen zu jeder Sekunde die exakte PDF-Druckseite (vektorbasiert als SVG) sowie eine responsive Web-Vorschau.
- **Excel-Copy-Paste für Tabellen:** Tabellen aus Excel kopieren und mit `Ctrl+V` direkt in das CMS einfügen — ohne Formatierungsverlust.
- **Direkte Datenbank-Charts:** Zeitreihendiagramme können direkt aus der internen Marktdatenbank generiert werden.
- **Kein Datenverlust (Autosave):** Jede Eingabe wird im Hintergrund automatisch in der Datenbank gesichert.

---

## 2. Die Benutzeroberfläche auf einen Blick

Die Arbeitsfläche ist in drei übersichtliche Hauptbereiche unterteilt:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  ☰ Publikationen  🔍 (Ctrl+K)   [Bank] Investment Office CMS    ● Gespeichert   📊 450 W. · 2 Min.   Meilenstein  │
├─────────────────────┬────────────────────────────────────────────────────────┬───────────────────────────────────┤
│                     │  [ Dokumenten-Kopf: Template, Titel, Lead, Autoren ]   │  [ PDF-Vorschau ] [ Web-Vorschau] │
│  LINKE SPALTE:      │ ────────────────────────────────────────────────────── │ ───────────────────────────────── │
│  Publikations-Liste │  TOOLBAR: [+ Text] [+ Grafik] [+ DB-Chart] [+ Tabelle] │  Typst 0.15          [x] Auto-Typ │
│                     │ ────────────────────────────────────────────────────── │                                   │
│  • Suche & Filter   │  MITTLERE SPALTE:                                      │  RECHTE SPALTE:                   │
│  • + Neuer Artikel  │  Interaktive Inhaltsblöcke                             │  Echtzeit-Druckvorschau           │
│  • Entwürfe / Live  │  (per Drag & Drop ⋮⋮ verschiebbar)                     │  (Seitenweises Vektor-Rendering)  │
│                     │                                                        │                                   │
└─────────────────────┴────────────────────────────────────────────────────────┴───────────────────────────────────┘
```

1. **Kopfzeile (Header-Bar):**
   - **☰ Publikationen (`Ctrl+B`):** Linke Seitenleiste ein- oder ausklappen für maximale Schreibfläche.
   - **🔍 Alle durchsuchen (`Ctrl+K`):** Schnelle Such-Palette über alle Publikationen.
   - **Autosave-Statusanzeige:** Grüner Punkt zeigt sofort, ob alle Änderungen in der Datenbank gespeichert sind.
   - **📊 Live-Statistik:** Wortanzahl, durchschnittliche Lesezeit und geschätzter A4-Füllstand in Echtzeit.
   - **Meilenstein speichern (`Ctrl+S`):** Legt manuell eine gesicherte Revisions-Version an.
   - **🌐 Portal-Menü:** Publikation auf das Web-Portal veröffentlichen oder zur Prüfung einreichen.
   - **📥 Export-Menü:** Download von druckfertigem PDF (Typst), Word (.docx) oder Web-HTML.
2. **Linke Seitenleiste (Publikationen-Navigation):**
   - Wechseln zwischen Artikeln, Filtern nach Status (*Entwurf*, *In Review*, *Publiziert*, *Papierkorb*).
3. **Mittlere Spalte (Der Block-Editor):**
   - Erfassung von Metadaten (Titel, Autoren, Lead) und beliebigen Inhaltsbausteinen.
4. **Rechte Spalte (Live-Preview):**
   - Simultane Vektor-Vorschau des Typst-PDFs oder der HTML5-Webseite.

---

## 3. Publikationen verwalten & Navigation

### Neue Publikation anlegen
Klicken Sie in der linken Seitenleiste oben auf den blauen Button **«+ Neue Publikation anlegen»**. Es wird sofort ein neues Dokument mit Standard-Musterblöcken im Status *Entwurf* angelegt.

### Schnellsuch-Dialog (Command Palette — `Ctrl+K`)
Mit dem Tastenkürzel **`Ctrl+K`** oder einem Klick auf **«🔍 Alle durchsuchen»** öffnen Sie die Vollbild-Suche. Hier können Sie:
- Alle Artikel nach Titel, Untertitel, Autorenname oder Rubrik filtern.
- Nach Status filtern (*In Bearbeitung*, *Entwurf*, *In Review*, *Publiziert*).
- Die Liste nach Aktualisierungsdatum oder Alphabet sortieren.
- Mit den Pfeiltasten oder Klick direkt zum gewünschten Dokument springen.

### Duplizieren & Löschen
Unter der Artikel-Liste finden Sie zwei Schnellaktionen für das aktuell geöffnete Dokument:
- **Duplizieren:** Erstellt eine 1:1-Kopie des Dokuments inklusive aller Blöcke und Bilder (ideal als Vorlage für wiederkehrende Marktberichte).
- **Löschen:** Verschiebt das Dokument in den internen Papierkorb.

---

## 4. Der Dokumenten-Kopf (Metadaten-Karte)

Jede Publikation beginnt mit der Konfigurationskarte für Rahmendaten:

| Feld | Erklärung & Best Practice |
| :--- | :--- |
| **Dokumenten-Template** | **Investment Fokus:** 2-spaltiges A4-Layout für fundierte Fachartikel und Analysen.<br>**Market Flash:** 1-spaltiges A4-Kompaktlayout für schnelle Tageskommentare. |
| **Kopfzeile oben rechts** | Standard-Reihe (z. B. *Investment Office News* oder *Finanzanalyse*). |
| **Publikations-Status** | **Entwurf** *(in Arbeit)* ➜ **In Review** *(zur Freigabe)* ➜ **Publiziert** *(öffentlich)*. |
| **Publikationsdatum** | Das auf der Titelseite gedruckte Ausgabedatum. |
| **Rubrik / Reihe** | Themenbereich (z. B. *Anlagepolitik & Märkte*, *Makroökonomie*, *Aktien Schweiz*). |
| **Dachzeile / Untertitel** | Wird über oder unter dem Gesamttitel dezent hervorgehoben platziert. |
| **Gesamttitel** | Der prägnante Haupttitel der Publikation (wird in Corporate Sans Medium gesetzt). |
| **Lead / Management Summary** | 2 bis 4 einleitende Kernsätze. Wird typografisch hervorgehoben über dem Artikel positioniert. |
| **Autoren** | Verwalten Sie die Verfasser. Über **«+ Autor hinzufügen»** können mehrere Autoren mit Name und Funktion hinzugefügt oder per Drag & Drop sortiert werden. |
| **Themen-Tags** | Schlagwörter zur Filterung (z. B. *SNB, Inflation, Zinsen, Aktien*). Einfach Wort eingeben und mit **Enter** bestätigen. |
| **Rechtlicher Hinweis** | Aufklappbarer Disclaimer für die Fusszeile der letzten Seite. |

---

## 5. Das Herzstück: Der Inhaltsblock-Editor

Ihr Artikel besteht aus modularen Inhaltsblöcken. Sie müssen sich nicht um Ränder, Zeilenabstände oder Schriftgrade sorgen — das System berechnet den perfekten Satz automatisch.

### Allgemeine Bedienung der Blöcke
- **Block verschieben:** Fassen Sie den Block am Griff **`⋮⋮`** ganz links im Blockkopf an und ziehen Sie ihn per Drag & Drop an die gewünschte Position.
- **Block einfügen (Toolbar oben):** Klicken Sie auf einen der Buttons in der Leiste über dem Editor (z. B. *+ Text-Absatz*), um den Block am Ende anzuhängen.
- **Block an exakter Stelle einfügen:** Bewegen Sie die Maus zwischen zwei Blöcke — es erscheint ein dezenter **«+»-Einfügebalken**. Ein Klick öffnet ein Auswahlmenü für die gewünschte Blockart an genau dieser Position.
- **Mehrfachauswahl & Stapel-Aktionen:** 
  - Klicken Sie bei gedrückter **`Ctrl`**-Taste auf mehrere Blöcke (oder aktivieren Sie die Checkbox links oben im Block).
  - Es erscheint eine schwebende Aktionsleiste: Sie können alle markierten Blöcke **gemeinsam duplizieren**, **gemeinsam löschen** oder **in eine farbige Textbox verschieben**.
- **Rückgängig (`Ctrl+Z`):** Aus Versehen einen Block gelöscht? Ein Druck auf **`Ctrl+Z`** (oder Klick auf «Rückgängig») stellt den Zustand sofort wieder her.
- **Autosave:** Sie müssen nicht manuell speichern. Sobald Sie aufhören zu tippen, speichert das System innerhalb einer Sekunde geräuschlos in die Datenbank.

---

## 6. Detaillierte Anleitung aller Inhaltsblöcke

### 1. Überschriften (`+ Überschrift`)
- **Ebenen:** Wählen Sie zwischen **H1** *(Hauptabschnitt)*, **H2** *(Unterkapitel)* und **H3** *(Zwischenüberschrift)*.
- **Verhalten:** H1- und H2-Überschriften werden automatisch im Corporate Font gerendert und verhindern unschöne «Waisenkind-Umbrüche» am Spaltenende.

---

### 2. Text-Absätze (`+ Text-Absatz`)
- Der Standardblock für Fließtext mit integrierter Rich-Text-Toolbar:
  - **B** *(Fett)*, **_I_** *(Kursiv)*, **U** *(Unterstrichen)*
  - **Aufzählungslisten** (Bullets) und **Nummerierte Listen**
  - **Textfarben:** Standard-Dunkelgrau, Navy-Blau oder Akzent-Cyan.
- **Automatisches Glossar:** Markieren Sie einen Fachbegriff (z. B. *Duration* oder *Stagflation*) und klicken Sie auf das Buch-Symbol in der Toolbar — der Begriff wird im Text dezent markiert und am Ende des Dokuments automatisch im Glossar aufgeführt!

---

### 3. Grafik-Upload (`+ Grafik (Upload)`)
- **Unterstützte Formate:** Vektor-Dateien (**SVG**) sowie hochauflösende Rasterbilder (**PNG**, **JPG**).
- **Upload:** Ziehen Sie die Datei einfach per Drag & Drop in das Upload-Feld oder klicken Sie darauf.
- **Einstellungen:**
  - **Grafik-Titel:** Kurze, aussagekräftige Überschrift über der Grafik.
  - **Grafik-Untertitel:** Kontextangabe oder Einheiten.
  - **Quellenangabe:** Verweis auf Datenlieferanten (z. B. *Quelle: Bloomberg, Bank Investment Office*).
  - **Satzbreite:** Wählen Sie zwischen **1-spaltig** *(Standardspalte)* oder **2-spaltig (Seitenbreite)** *(überspannt im Fokus-Template beide Textspalten)*.

---

### 4. DB-Chart (Zeitreihen-Diagramm aus der Datenbank)
Ein Highlight für Finanzberichte: Erstellen Sie druckreife Vektorgrafiken direkt aus der MSSQL-Zeitreihentabelle `ts_db` — ganz ohne Excel oder Grafikprogramm!

```
┌────────────────────────────────────────────────────────────────────────┐
│  DB-CHART: Leitzinsen EZB vs. Fed                                      │
├────────────────────────────────────────────────────────────────────────┤
│  Ticker:  [ US_FED_FUNDS_RATE  ] [ EUR_ECB_DEPO_RATE  ] (+ Ticker)     │
│  Typ:     [ Stufenlinie (step) ] [ Stufenlinie (step) ]                │
│  Palette: [ LUKB Standard ▾    ] (Blautöne, Akzentfarben)              │
│  Datumsbereich: [ 2020-01-01   ] bis [ 2026-10-31   ]                  │
└────────────────────────────────────────────────────────────────────────┘
```

- **Bis zu 5 Zeitreihen simultan:** Geben Sie einfach den Ticker-Code ein (z. B. `SPI_INDEX`, `SWISS_10Y_YIELD`).
- **Flexible Darstellungsformen (pro Zeitreihe kombinierbar):**
  - **Linie (`line`):** Klassischer Kursverlauf.
  - **Stufenlinie (`step`):** Ideal für geldpolitische Zinssätze und diskrete Daten.
  - **Punkte (`dot`):** Markante Datenpunkte.
  - **Fläche (`area`):** Elegante farbliche Schattierung unter der Kurve.
  - **Säulen (`bar`):** Monatliche oder jährliche Balken.
  - **Gestapelte Säulen (`stacked_bar`):** Positive Werte nach oben, negative nach unten.
- **Satzbreite:** Ebenfalls umschaltbar zwischen 1-spaltig und 2-spaltig.

---

### 5. Tabelle mit Microsoft Excel Copy-Paste (`+ Tabelle`)
Vergessen Sie mühsames Abtippen von Zahlenkolonnen!

1. Markieren Sie Ihren Datenbereich in **Microsoft Excel**.
2. Drücken Sie **`Ctrl+C`**.
3. Klicken Sie in das Tabellen-Feld im CMS und drücken Sie **`Ctrl+V`**.
4. Die gesamte Tabellenstruktur mit Zeilen, Spalten und Werten wird in Bruchteilen einer Sekunde sauber übernommen!

**Zusatz-Funktionen der Tabelle:**
- **Tabellentitel & Quelle:** Professionelle Beschriftung ober- und unterhalb der Tabelle.
- **Total-Zeile hervorheben:** Setzt die letzte Zeile automatisch in Fettdruck mit Trennlinie.
- **Ausrichtung:** Zahlen werden im PDF automatisch rechtsbündig formatiert.
- **Breite:** Umschaltbar zwischen 1-spaltig und seitenbreit (2-spaltig).

---

### 6. Kernaussagen-Box (`+ Kernaussagen-Box`)
- Hebt die zentralen Takeaways der Analyse in einer elegant hinterlegten Box mit Akzentlinie hervor.
- Ideal nach der Einleitung oder am Ende jedes Hauptkapitels.

---

### 7. Farbliche Textbox (Start & Ende / `+ Farbliche Box`)
Möchten Sie einen ganzen Abschnitt (bestehend aus mehreren Überschriften, Texten und Grafiken) optisch als Info-Kasten zusammenfassen?
- Klicken Sie auf **«+ Farbliche Box»**.
- Das System fügt zwei Marken ein: **[Box-Start]** und **[Box-Ende]**.
- Alle Blöcke, die Sie per Drag & Drop zwischen diese beiden Marken schieben, werden im PDF und im Web in einen zusammenhängenden graublauen Hintergrundrahmen gesetzt.

---

### 8. Feintypografie-Werkzeuge
- **Abstand (`+ Abstand`):** Fügt einen einstellbaren vertikalen Leerraum in Millimetern ein (z. B. `5 mm` oder `10 mm`), um Umbrüche millimetergenau auszusteuern.
- **Spaltenumbruch (`+ Spaltenumbruch`):** Erzwingt im 2-spaltigen *Investment Fokus* den sofortigen Wechsel in die nächste Spalte.
- **Zitat (`+ Zitat`):** Großes Pull-Quote mit Autoren- und Quellenzeile für Meinungsbeiträge.
- **Trennlinie (`+ Trennlinie`):** Horizontale Schmucklinie (durchgezogen, gestrichelt oder gepunktet).
- **Fussnoten (`+ Fussnoten`):** Nummerierter Anmerkungsapparat am Seitenende.
- **Glossar (`+ Glossar`):** Listet alle im Text markierten Begriffe alphabetisch mit Definition auf.
- **Weitere Publikationen (`+ Weitere Publikationen`):** Zeigt eine kompakte Übersicht der letzten Veröffentlichungen des Investment Office.

---

## 7. Echtzeit-Vorschau (Live-Preview)

Auf der rechten Bildschirmseite sehen Sie sofort die Wirkung Ihrer Eingaben:

- **PDF-Vorschau (Typst):**
  - Rendert das druckreife Dokument seitenweise als gestochen scharfe Vektorgrafik.
  - Zeigt exakt, wo eine Seite endet und wie viele A4-Seiten Ihr Artikel umfasst.
- **Web-Vorschau (HTML5):**
  - Zeigt, wie der Artikel auf dem Online-Portal, im Intranet oder auf mobilen Geräten dargestellt wird.
- **Auto-Typst Schalter:**
  - Standardmäßig aktiv: Jede Textänderung aktualisiert die Vorschau nahtlos im Hintergrund.
  - Bei sehr langen Dokumenten können Sie den Schalter deaktivieren und bei Bedarf manuell auf **«↻ Aktualisieren»** klicken.

---

## 8. Redaktions-Workflow & Portal-Freigabe

Das System unterstützt einen dreistufigen bankinternen Freigabeprozess:

```
┌──────────────┐          ┌──────────────┐          ┌──────────────┐
│   Entwurf    │  ─────►  │  In Review   │  ─────►  │  Publiziert  │
│  (in Arbeit) │          │  (Prüfung)   │          │ (Live/Portal)│
└──────────────┘          └──────────────┘          └──────────────┘
```

1. **Entwurf (Draft):**
   Der Autor erstellt den Artikel. Alle Änderungen werden automatisch und verlustfrei gesichert.
2. **Zur Prüfung einreichen:**
   Klicken Sie oben auf **«🌐 Portal ▾» ➜ «📤 Zur Prüfung einreichen»**. Der Status wechselt auf *In Review*. Das Vier-Augen-Prinzip greift; der Senior Editor wird informiert.
3. **Auf Portal publizieren (Senior Editor / Admin):**
   Nach erfolgreichem Review klickt der freigabeberechtigte Editor auf **«🌐 Portal ▾» ➜ «🌐 Auf Portal publizieren»**.
   - Das System generiert automatisch das finale PDF und das responsive HTML.
   - Ein revisionssicherer Snapshot wird in der Datenbank archiviert.
   - Der Artikel ist sofort auf dem bankinternen Portal sichtbar.
4. **Vom Portal zurückziehen:**
   Muss ein Artikel aktualisiert oder depubliziert werden, klickt der Editor auf **«❌ Vom Portal zurückziehen»**. Der Artikel verschwindet sofort vom Portal, bleibt im CMS jedoch vollständig erhalten.

---

## 9. Export-Möglichkeiten

Über das Dropdown-Menü **«📥 Export ▾»** in der Kopfzeile stehen Ihnen jederzeit folgende Formate zur Verfügung:

1. **📄 PDF Export (Typst):**
   Lädt das druckfertige, hochauflösende Vektor-PDF mit Vektorschriften, Schnittmarken und Farbprofilen herunter. Perfekt für den professionellen Druck oder Kunden-Versand.
2. **📝 Word Export (.docx):**
   Erzeugt eine sauber formatierte Microsoft Word-Datei mit echten Word-Überschriften und Word-Tabellen, falls externe Stellen Kommentare über Word-Änderungsverfolgung erfassen möchten.
3. **🌐 Web-HTML Export:**
   Exportiert eine eigenständige HTML-Datei inklusive aller eingebetteten Vektor-Grafiken zur direkten Weitergabe.

---

## 10. Tastenkombinationen (Tastatur-Kürzel)

| Shortcut | Funktion |
| :--- | :--- |
| **`Ctrl + K`** | Vollbild-Suche & Publikationsverzeichnis öffnen / schliessen |
| **`Ctrl + B`** | Linke Publikations-Sidebar ein- oder ausklappen |
| **`Ctrl + S`** | Meilenstein-Snapshot sofort in der Datenbank speichern |
| **`Ctrl + Z`** | Gelöschten Inhaltsblock rückgängig machen |
| **`Ctrl + Klick`** | Mehrere Inhaltsblöcke für Stapel-Aktionen markieren |
| **`Ctrl + V`** | Excel-Tabelle direkt in den Tabellen-Block einfügen |
| **`Esc`** | Geöffneten Suchdialog oder Menüs schliessen |
