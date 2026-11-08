# Mitarbeit an advOrdo

Danke, dass du advOrdo verbessern möchtest. Diese Anleitung fasst zusammen, worauf es bei Beiträgen ankommt. Wie
du die Entwicklungsumgebung einrichtest, steht im [README](README.md#entwicklung).

Fragen und Vorschläge gehen an **advordo@staab.legal** oder als Issue an das Repository. Sicherheitslücken bitte
nicht als Issue melden, sondern wie in [`SECURITY.md`](SECURITY.md) beschrieben.

## Grundsätze

advOrdo verarbeitet Akten mit vertraulichen Mandatsdaten. Daraus folgen Regeln, die für jeden Beitrag gelten:

- **Keine echten Mandatsdaten.** Echte Schriftsätze, Namen, Aktenzeichen oder Adressen gehören nie ins
  Repository, auch nicht als Testdaten, in Issues oder in Screenshots. Testakten sind erfunden oder vollständig
  anonymisiert.
- **Der Kern öffnet keinen Netzwerkport.** Die Oberfläche spricht mit dem Kern nur über JSON-Zeilen auf
  stdin/stdout.
- **Dokumentinhalte bleiben auf dem Gerät.** Sie gehen nur im ausdrücklich gewählten Modus „Externer Anbieter“
  hinaus. Ohne Rückfrage darf die App nur öffentliche Rechtsquellen aus dem Netz laden. Jede neue Online-Anfrage
  läuft über `urllib` im Kern, damit sie im Netzprotokoll (`core/juracore/netzprotokoll.py`) steht.
- **Beleg vor Behauptung.** Jede Aussage der App führt auf eine Fundstelle zurück: Dokument mit Seite oder
  Randnummer, oder Norm mit Fassung. Fundstellen werden nie erfunden. Fehlt ein Beleg, sagt die App das
  ausdrücklich. Bei Ergebnissen eines Sprachmodells zeigt die App nur Text, der wörtlich im Dokument steht.
- **Rechtsquellen bleiben unverändert.** Sie werden mit SHA-256 archiviert und versioniert. Eine bestehende
  Fassung wird nie überschrieben.
- **Eine Codebasis für Windows, macOS und Linux.** Plattformspezifischer Code nur, wo es technisch nicht anders
  geht, und dann hinter einem Adapter (Beispiel: `core/juracore/schluesselbund.py`).

## Sprache

Oberfläche, Fachbegriffe, Dokumentation, Commit-Nachrichten und Beschreibungen von Pull Requests sind auf
Deutsch. Bezeichner im Code dürfen deutsche Fachbegriffe tragen (`Norm`, `Absatz`, `Fassung`). Texte in der
Oberfläche sprechen die Nutzerin oder den Nutzer mit „du“ an und bleiben sachlich: Ein Hinweis der App ist keine
rechtliche Bewertung.

## Prüfungen vor jedem Commit

Alle fünf Prüfungen müssen durchlaufen. Die CI wiederholt sie auf Windows, macOS und Linux.

| Ordner | Befehl |
| --- | --- |
| `core/` | `pytest` |
| `core/` | `ruff check` |
| `app/` | `npm run build` |
| `app/` | `npm test` |
| `app/src-tauri/` | `cargo test` |

Unter Windows liegen `pytest` und `ruff` in `.venv\Scripts`, unter macOS und Linux in `.venv/bin`.

## Worauf bei Änderungen zu achten ist

- **Tests:** Neue Funktionen bekommen Tests. Tests greifen nicht ins Netz und schreiben nie in den echten
  Schlüsselbund des Systems; `core/tests/conftest.py` schaltet ihn für alle Tests ab. Auszüge aus Rechtsquellen
  in `core/tests/fixtures/` nennen ihre Herkunft.
- **Neue Kernmethoden:** Die Tauri-Hülle reicht nur die Methoden in `app/src-tauri/kern-methoden.txt` an den Kern
  weiter. Nach einer neuen oder umbenannten Methode die Liste mit `python core/kern_methoden.py` neu erzeugen.
- **Datenbanken:** Vorhandene Akten und Wissensbasen müssen nach einem Update weiter funktionieren. Änderungen am
  Schema laufen über die Migration (`_migriere` in `core/juracore/dokumente/akte.py`) und eine höhere
  Schemaversion.
- **Anweisungen an das Sprachmodell:** Wer eine Anweisung ändert, erhöht ihre Fassung in `FASSUNG`
  (`core/juracore/ki/analyse.py`). Sonst liefert der Speicher alte Ergebnisse.
- **Alte Bezeichner:** Interne Namen wie die Tauri-Kennung, die Datenordner oder der Dienstname „JuraBox“ im
  Schlüsselbund bleiben bewusst, damit vorhandene Daten gefunden werden (siehe README).
- **Barrierefreiheit:** Die Oberfläche muss mit Tastatur und Bildschirmleser bedienbar bleiben. Die Ziele stehen
  in [`docs/barrierefreiheit.md`](docs/barrierefreiheit.md).

## Pull Requests

- Ein Pull Request behandelt ein Thema. Kleine Pull Requests lassen sich schneller prüfen.
- Die Beschreibung sagt, was sich ändert und warum, und welche Prüfungen gelaufen sind. Bei Änderungen an der
  Oberfläche hilft ein Screenshot mit erfundenen Daten.
- Neue Abhängigkeiten nur, wenn sie nötig sind. Ihre Lizenz muss mit der EUPL-1.2 vereinbar sein (etwa MIT, BSD,
  Apache-2.0, MPL-2.0); nenne sie in der Beschreibung.

## Lizenz der Beiträge

advOrdo steht unter der EUPL-1.2 (siehe [`LICENSE`](LICENSE)). Mit einem Beitrag erklärst du, dass du ihn selbst
geschaffen hast oder ihn unter einer damit vereinbaren Lizenz einbringen darfst, und dass er unter der EUPL-1.2
veröffentlicht wird.
