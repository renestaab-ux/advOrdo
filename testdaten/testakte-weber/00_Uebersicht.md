# Testakte „Brückner ./. Weber Haustechnik GmbH“

Dritte, vollständig **fiktive** Testakte (21.10.2026, für Stufe 2 der Aktenverwaltung). Wir vertreten die
**Beklagte** Weber Haustechnik GmbH. Die Gegnerin Dr. Lena Brückner ist in der Testakte „Brückner ./. Autohaus
Rehnfeld“ unsere **Mandantin**; daran soll die Kollisionsprüfung anschlagen.

## Fall in drei Sätzen

Die Klägerin verlangt eine Abschlagszahlung von 14.860,00 € für eine abgebrochene Heizungsmodernisierung zurück. Sie
beginnt mit einem Mahnbescheid beim Zentralen Mahngericht Stuttgart; nach unserem Widerspruch wird die Sache an das
Landgericht Freiburg abgegeben (zwei Verfahren in einer Akte). Das Gericht setzt eine Frist zur Klageerwiderung und
lädt zum Termin, der später verlegt wird.

## Dateien (je als `docx/` und `pdf/`)

| Nr. | Datei | Prüft |
|---|---|---|
| 01 | Mahnbescheid AG Stuttgart, 03.06.2026, zugestellt 08.06.2026 | Verfahren 1 (Mahnverfahren), Frist F1 |
| 02 | Unser Widerspruch, 15.06.2026 | erledigt F1 |
| 03 | Abgabe an LG Freiburg, Az. 2 O 233/26 | Verfahren 2 (Klageverfahren, 1. Instanz) |
| 04 | Anspruchsbegründung der Klägerin | **Akte aus Dokument**: Rubrum mit Gericht, Az., Parteien, gesetzlichem Vertreter, Prozessbevollmächtigten, Streitwert |
| 05 | Verfügung mit Frist und Termin, zugestellt 01.09.2026 | Fristvorschlag F2 (29.09.2026), Termin T1 |
| 06 | Terminsverlegung (nennt nur Az. und unser Zeichen) | Posteingang-Zuordnung, Termin T2 ersetzt T1 |

Sollergebnisse maschinenlesbar in `erwartungen.json`.

## So prüfen

1. Akte anlegen → „Dokument wählen …“ → `pdf/04_Anspruchsbegruendung_2026-08-20.pdf`. Erwartet: Landgericht
   Freiburg im Breisgau, 2 O 233/26, Klägerin Dr. Lena Brückner, Beklagte Weber Haustechnik GmbH (vertreten durch den
   Geschäftsführer Markus Weber), Gegenstand und Streitwert 14.860,00 €. „Wir vertreten“: Beklagtenseite.
2. Ist die Testakte Brückner angelegt, meldet die Kollisionsprüfung Dr. Lena Brückner (dort Mandantin).
3. Die übrigen Dokumente einlesen, dann im Reiter „Fristen“ „Vorschläge aus Dokumenten“: Widerspruchsfrist 22.06.2026,
   Erwiderung 29.09.2026, Termin 19.11.2026 10:30 Uhr, Termin 26.11.2026 11:00 Uhr; nach Eintragen des 19.11. schlägt
   das Schreiben vom 05.10.2026 vor, ihn als aufgehoben abzuhaken.
