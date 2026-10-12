# Juristischer Datenabgleich

Desktop-App für Windows, macOS und Linux, die Schriftsätze, Schreiben und Urteile
analysiert, vergleicht und zusammenfasst. Grundlage ist eine versionierte
Wissensbasis aus Gesetzen (später auch Rechtsprechung). Leitprinzip: **Beleg vor
Behauptung**. Jede Aussage verweist auf eine Fundstelle im Dokument oder in einer
Rechtsquelle mit Fassungsstand.

Das Produktkonzept liegt im Projektordner (`Konzept.md`), die technische Umsetzung in `docs/architektur.md`.

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `core/` | Analysekern in Python (`juracore`): Gesetzes-Import, Wissensbasis, Einlesen von Akten (PDF, DOCX, OCR), Normzitate; später RAG |
| `app/` | Oberfläche (React + TypeScript, Vite) |
| `app/src-tauri/` | Desktop-Hülle (Tauri 2, Rust); startet den Kern als Kindprozess |
| `docs/` | Architektur und Entscheidungen |

Der Kern öffnet keinen Netzwerkport. Die App spricht mit ihm über JSON-Zeilen auf
stdin/stdout (`core/juracore/rpc.py`, `app/src-tauri/src/kern.rs`).

## Entwicklung

Voraussetzungen: Python 3.11+, Node 22, Rust (stable), Git. Windows 11 ist das
Hauptzielsystem; macOS und Linux werden genauso unterstützt.

### Windows 11 (PowerShell)

Einmalig, in einer PowerShell:

```powershell
winget install Git.Git GitHub.cli Python.Python.3.12 OpenJS.NodeJS.LTS Rustlang.Rustup
winget install Microsoft.VisualStudio.2022.BuildTools --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # erlaubt npm-Skripte
```

Danach eine neue PowerShell öffnen (damit die neuen Programme gefunden werden):

```powershell
gh auth login
gh repo clone renestaab-ux/juristischer-datenabgleich
cd juristischer-datenabgleich
py -3.12 -m venv .venv
.venv\Scripts\pip install -e "core[dev]"
.venv\Scripts\pytest core
cd app
npm install
npm run tauri dev
```

WebView2 bringt Windows 11 bereits mit. Die Daten der App liegen unter
`%APPDATA%\de.juristischer-datenabgleich.app`.

### Linux (Ubuntu/Zorin)

```bash
sudo apt install git gh build-essential pkg-config python3-venv libwebkit2gtk-4.1-dev \
  libgtk-3-dev librsvg2-dev libayatana-appindicator3-dev libssl-dev libxdo-dev
python3 -m venv .venv
.venv/bin/pip install -e "core[dev]"
.venv/bin/pytest core
cd app && npm install && npm run tauri dev
```

Node 22 kommt am einfachsten über NodeSource, Rust über rustup. Die Daten liegen
unter `~/.local/share/de.juristischer-datenabgleich.app`.

### Python-Interpreter

Im Entwicklungsmodus nimmt die App den Interpreter aus `.venv` im Projektordner.
`JURACORE_PYTHON` überschreibt das; ohne beides gilt `python` (Windows) bzw. `python3`.

## Texterkennung für Scans (Tesseract)

PDFs mit Textebene, Word-, Text- und Markdown-Dateien liest die App ohne weitere
Programme. Für eingescannte Seiten (Bild-PDF) braucht sie Tesseract mit den deutschen
Sprachdaten. Tesseract läuft lokal; es wird nichts übertragen.

Windows 11 (PowerShell):

```powershell
winget install --id UB-Mannheim.TesseractOCR
```

Danach die deutschen Sprachdaten in den Programmordner legen. Dafür eine PowerShell
**als Administrator** öffnen (Startmenü, „Terminal“ mit Rechtsklick, „Als Administrator ausführen“):

```powershell
Invoke-WebRequest https://github.com/tesseract-ocr/tessdata/raw/main/deu.traineddata -OutFile "C:\Program Files\Tesseract-OCR\tessdata\deu.traineddata"
```

Prüfen (wieder in einer normalen PowerShell im Projektordner):

```powershell
.venv\Scripts\juracore ocr
```

`"verfuegbar": true` heißt: Scans werden gelesen. Die App findet Tesseract im
Programmordner auch dann, wenn es nicht im Suchpfad steht; ein anderer Ort lässt sich mit
`JURACORE_TESSERACT` angeben.

Linux: `sudo apt install tesseract-ocr tesseract-ocr-deu`. macOS: `brew install tesseract tesseract-lang`.

## Akte: Dokumente einlesen

Im Bereich **Akte** legt man eine Akte an und fügt Schriftsätze, Schreiben und Urteile hinzu
(PDF, DOCX, TXT, MD). Beim Einlesen

- wird die Originaldatei unverändert unter ihrer SHA-256-Prüfsumme im Ordner der Akte abgelegt,
- werden Seitenköpfe („- 2 -“) entfernt, Silbentrennungen aufgelöst und Absätze über Seitenwechsel fortgesetzt,
- werden Randnummern („(4)“) und Seiten als Fundstellen erkannt,
- werden Seiten ohne Text per Texterkennung gelesen (Hinweis und Erkennungsgüte stehen beim Dokument),
- werden Normzitate erkannt („§§ 437 Nr. 2, 440, 323 Abs. 1 BGB“, „§ 280 Abs. 1 i.V.m. § 241 Abs. 2 BGB“,
  „§ 346 Abs. 1, Abs. 2 Satz 1 Nr. 1 BGB“) und gegen die Wissensbasis geprüft:
  - **belegt**: Norm, Absatz, Satz und Nummer gibt es in der geladenen Fassung; ein Klick zeigt den Wortlaut,
  - **existiert nicht**: z. B. „§ 437 Nr. 4 BGB“ (§ 437 hat nur Nr. 1 bis 3),
  - **nicht in Wissensbasis**: das Gesetz ist nicht geladen (z. B. UStG).

Die Prüfung merkt sich die verwendete Fassung. Nach dem Laden weiterer Gesetze prüft
„Zitate neu prüfen“ die ganze Akte erneut. Ohne App:

```bash
juracore lesen pfad/zur/klage.pdf      # Absätze, Fundstellen und geprüfte Zitate als JSON
```

Noch nicht erkannt werden Rechtsprechungszitate (Phase 2), Zitate ohne „§“/„Art.“
(z. B. „Nr. 2300 VV RVG“) und inhaltlich veraltete Zitate einer noch existierenden Norm
(z. B. § 476 BGB als Beweislastumkehr, seit 2022 § 477 BGB). Word-Dateien haben nur dann
Seitenzahlen, wenn sie Seitenumbrüche enthalten; sonst gilt die Randnummer bzw. der
laufende Absatz („Abschn. 12“) als Fundstelle.

### Ordner, Beteiligte und Entfernen

- **Ordner hinzufügen …** liest einen ganzen Ordner samt Unterordnern ein (PDF, DOCX, TXT, MD;
  andere Dateien werden übersprungen und genannt).
- Aus den Namen der Unterordner schlägt die App Tags vor, die zeigen, zu welchem Beteiligten ein
  Dokument gehört: „01_Kläger“ und „Klägerin“ werden zu **Kläger**, „Beklagte“ zu **Beklagter**,
  „Landgericht“ zu **Gericht**, andere Namen bleiben, wie sie sind. Vor dem Einlesen fragt die App,
  ob die Tags übernommen werden sollen; die Vorschläge lassen sich dort ändern oder leeren.
- In der Dokumentliste lassen sich Tags jederzeit von Hand setzen und ändern („+ Tag“ bzw. „ändern“).
  Tags aus dem Ordnernamen sind durchgezogen umrandet, von Hand gesetzte gestrichelt. Über die
  Tag-Leiste filtert man die Liste, z. B. alle Dokumente des Gerichts.
- **entfernen** (je Dokument) und **Akte entfernen …** löschen nach einer Rückfrage den gelesenen
  Text, die Zitate, die Tags und die Kopie, die die App beim Einlesen abgelegt hat. Die
  Originaldatei am ursprünglichen Ort bleibt unverändert.

## Wissensbasis: Gesetze

```bash
juracore import BGB ZPO HGB                  # lädt XML von gesetze-im-internet.de
juracore import GmbHG InsO                   # jedes weitere Bundesgesetz über seine Abkürzung
juracore import-datei pfad/zu/bgb.zip        # offline aus einer heruntergeladenen Datei
juracore zitat "§ 280 Abs. 1 S. 2 BGB"       # Wortlaut mit Fassungsstand
juracore suche "Verjährungsfrist"
juracore liste
```

- Voreingestellt sind 36 Bundesgesetze, die in Zivilrechtsstreitigkeiten typischerweise
  gebraucht werden (`core/juracore/gesetze/voreinstellung.json`, gegliedert nach Gebieten).
  Eine eigene Liste im selben Format unter `<Datenverzeichnis>/gesetze.json` ersetzt sie.
- Weitere Bundesgesetze lädt man über ihre Abkürzung, wie sie in der Adresse auf
  gesetze-im-internet.de steht (z. B. `gmbhg`).
- Jede Quelldatei wird unverändert unter ihrer SHA-256-Prüfsumme im Roharchiv abgelegt.
- Ein erneuter Import legt nur dann eine neue Fassung an, wenn sich die Datei geändert hat.
  Ältere Fassungen bleiben abrufbar, damit frühere Analysen reproduzierbar sind.
- Normen sind bis auf Absatz, Satz und Nummer zerlegt; Zitate werden darauf aufgelöst.
- Die Texte von „Gesetze im Internet“ sind konsolidiert, aber nicht amtlich. Die App zeigt das bei jedem Beleg an.

Die Testdaten unter `core/tests/fixtures/` sind von Hand gekürzte Auszüge im
GII-Format und keine Rechtsquelle.
