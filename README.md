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

Voraussetzungen: Python 3.11+, Node 22, Rust (stable). Unter Linux zusätzlich die
Tauri-Systembibliotheken (`libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev
libayatana-appindicator3-dev`).

```bash
# Analysekern
python3 -m venv .venv
.venv/bin/pip install -e "core[dev]"        # Windows: .venv\Scripts\pip
.venv/bin/pytest core

# Desktop-App im Entwicklungsmodus
cd app
npm install
JURACORE_PYTHON=../.venv/bin/python npm run tauri dev
```

`JURACORE_PYTHON` zeigt auf den Interpreter mit installiertem `juracore`
(Standard: `python3`, unter Windows `python`).

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
