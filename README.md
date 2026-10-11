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
| `core/` | Analysekern in Python (`juracore`): Gesetzes-Import, Wissensbasis, später Ingestion, OCR, RAG |
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

## Wissensbasis: Gesetze

```bash
juracore import BGB ZPO HGB                  # lädt XML von gesetze-im-internet.de
juracore import GmbHG InsO                   # jedes weitere Bundesgesetz über seine Abkürzung
juracore import-datei pfad/zu/bgb.zip        # offline aus einer heruntergeladenen Datei
juracore zitat "§ 280 Abs. 1 S. 2 BGB"       # Wortlaut mit Fassungsstand
juracore suche "Verjährungsfrist"
juracore liste
```

- Voreingestellt sind 35 Bundesgesetze, die in Zivilrechtsstreitigkeiten typischerweise
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
