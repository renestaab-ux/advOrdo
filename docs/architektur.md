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

## Akten einlesen

`juracore.dokumente`: `lesen` liest PDF (PDFium über `pypdfium2`), DOCX (Word-XML direkt,
ohne Zusatzbibliothek), TXT und Markdown in Seiten und Zeilen. Seiten ohne Textebene werden
mit 300 dpi gerendert und von Tesseract erkannt (`ocr.py`; eigenständiges Programm,
Seitenbild nur kurz im Temp-Ordner; einziger plattformabhängiger Teil ist die Programmsuche). `aufbereitung`
bildet daraus Abschnitte: Seitenköpfe entfernen, Silbentrennung auflösen, Absätze über
Seitenwechsel fortsetzen, Randnummern erkennen, typische OCR-Fehler bei „§“ korrigieren.

`akte` speichert in `akten.sqlite` (getrennt von der Wissensbasis): `akte` → `dokument`
(SHA-256, Pfad des unverändert abgelegten Originals, Lesart, OCR-Güte) → `seite` (Rohtext)
→ `abschnitt` (Text, Seite, Randnummer, Seitenwechsel) → `normzitat` (Position im Abschnitt,
Prüfstatus, verwendete Fassung). Originale liegen unter `<Datenverzeichnis>/akten/akte-<id>/`.

Die Oberfläche wählt Dateien über den Tauri-Dialog; gelesen wird ausschließlich im Kern.

## Offene Punkte

- Realdaten-Test mit vollständigem BGB/ZPO-XML (Sonderfälle: Tabellen, Anlagen, verschachtelte Listen)
- Kern als Sidecar bündeln, Installer je System
- Rechtsprechungszitate erkennen; Volltextsuche über Akten; Vergleich, Chronologie
- Tesseract für den Installer mitliefern (Windows), damit keine eigene Installation nötig ist
- Provider-Adapter für lokale und externe Modelle mit Warnhinweis
