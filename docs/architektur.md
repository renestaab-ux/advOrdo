# Architektur (Stand MVP-Grundgerüst)

## Technologieentscheidung

| Schicht | Wahl | Begründung |
| --- | --- | --- |
| Desktop-Hülle | Tauri 2 (Rust) | Eine Codebasis für Windows, macOS, Linux; kleine Installer; restriktives Rechtemodell für das Frontend |
| Oberfläche | React + TypeScript (Vite) | Verbreitet, gut testbar, läuft identisch in allen System-Webviews |
| Analysekern | Python (`juracore`) | Beste Bibliotheken für PDF/DOCX-Parsing, OCR, Embeddings und lokale LLMs |
| Speicher | SQLite mit FTS5 | Eine Datei pro Datenverzeichnis, keine Serverinstallation; Vektorspeicher folgt (sqlite-vec oder LanceDB) |
| Lokale Modelle | Ollama / LM Studio (folgt) | Über Provider-Adapter, lokal als Voreinstellung |

## Kommunikation App ↔ Kern

Die Tauri-Hülle startet den Kern als Kindprozess und tauscht JSON-Zeilen über
stdin/stdout aus. Es gibt keinen offenen Port, über den andere Programme oder
Webseiten auf Akteninhalte zugreifen könnten. Für die Auslieferung wird der Kern
mit PyInstaller zu einer ausführbaren Datei gebündelt und als Tauri-Sidecar
mitgeliefert (offen).

## Wissensbasis Gesetze

`gesetz` → `fassung` (je Quelldatei mit SHA-256, Abrufzeit, Stand) → `norm` →
`absatz` → `satz` (mit Nummern). Suche und Zitatauflösung nutzen standardmäßig
die neueste Fassung; über `fassung_id` lässt sich jede ältere Fassung abfragen.

## Offene Punkte

- Realdaten-Test mit vollständigem BGB/ZPO-XML (Sonderfälle: Tabellen, Anlagen, verschachtelte Listen)
- Kern als Sidecar bündeln, Installer je System
- Ingestion-Pipeline (PDF, DOCX, OCR) für Akten
- Provider-Adapter für lokale und externe Modelle mit Warnhinweis
