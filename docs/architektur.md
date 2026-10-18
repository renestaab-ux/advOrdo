# Architektur (Stand MVP-Grundgerüst)

## Technologieentscheidung

| Schicht | Wahl | Begründung |
| --- | --- | --- |
| Desktop-Hülle | Tauri 2 (Rust) | Eine Codebasis für Windows, macOS, Linux; kleine Installer; restriktives Rechtemodell für das Frontend |
| Oberfläche | React + TypeScript (Vite) | Verbreitet, gut testbar, läuft identisch in allen System-Webviews |
| Analysekern | Python (`juracore`) | Beste Bibliotheken für PDF/DOCX-Parsing, OCR, Embeddings und lokale LLMs |
| Speicher | SQLite mit FTS5 | Eine Datei pro Datenverzeichnis, keine Serverinstallation; Vektorspeicher folgt (sqlite-vec oder LanceDB) |
| Lokale Modelle | Ollama / LM Studio | Über Provider-Adapter, lokal als Voreinstellung |

## Kommunikation App ↔ Kern

Die Tauri-Hülle startet den Kern als Kindprozess und tauscht JSON-Zeilen über
stdin/stdout aus. Es gibt keinen offenen Port, über den andere Programme oder
Webseiten auf Akteninhalte zugreifen könnten. Für die Auslieferung wird der Kern
mit PyInstaller zu einer ausführbaren Datei gebündelt (`core/kern_bauen.py`) und als
Tauri-Sidecar mitgeliefert (`npm run paket`, Konfiguration `tauri.paket.conf.json`). Der Release-Build
startet `juracore` aus dem Ordner der App; fehlt die Datei, nimmt er wie die Entwicklung die `.venv`.

## Wissensbasis Gesetze

`gesetz` → `fassung` (je Quelldatei mit SHA-256, Abrufzeit, Stand) → `norm` →
`absatz` → `satz` (mit Nummern). Suche und Zitatauflösung nutzen standardmäßig
die neueste Fassung; über `fassung_id` lässt sich jede ältere Fassung abfragen.

Quellen: Bundesrecht als GII-XML (`gesetze/gii.py`), Unionsrecht als HTML-Fassung des
Amtsblatts aus EUR-Lex (`gesetze/eurlex.py`, Klassen `oj-ti-art`, `oj-normal` usw., ältere
Rechtsakte ohne `oj-`). Beide Leser liefern dasselbe `GesetzDokument`; `wissensbasis.importiere`
erkennt das Format am Inhalt. Erwägungsgründe stehen als `norm` mit `typ = 'erwaegungsgrund'`.

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

Die Oberfläche wählt Dateien und Ordner über den Tauri-Dialog; gelesen wird ausschließlich im Kern.

Ordner-Import in zwei Schritten: `akten.ordner_pruefen` sammelt die lesbaren Dateien samt
Unterordnern (versteckte Dateien und Word-Sperrdateien `~$…` ausgenommen) und schlägt je
Unterordner Tags vor (`tag_vorschlag`: übliche Beteiligte vereinheitlicht, Nummerierung entfernt).
Erst nach der Rückfrage in der Oberfläche liest `akten.importieren` jede Datei mit den bestätigten
Tags (`tag.quelle = 'ordner'`) und dem Unterordner (`dokument.herkunft`). `akten.tags_setzen`
ersetzt die Tags eines Dokuments; neue erhalten `quelle = 'manuell'`, vorhandene behalten ihre Herkunft.

Löschen (`akten.dokument_loeschen`, `akten.loeschen`) entfernt die Datenbankeinträge per
Kaskade und danach die abgelegte Kopie bzw. den Ordner `akte-<id>`, nur innerhalb der Ablage.
`secure_delete` ist eingeschaltet, damit gelöschte Inhalte nicht in freien Seiten der Datenbank
zurückbleiben. Ältere `akten.sqlite` (Schema 1) werden beim Öffnen um die neuen Spalten ergänzt.

## Abgleich

`juracore.abgleich`: `angaben` erkennt regelbasiert Werte (Datum, Monat, Betrag, Kilometer,
Fehlercode) und ordnet sie einem Merkmal zu (`MERKMALE`: Kaufpreis, Übergabe/Gefahrübergang,
Kilometerstand bei Übergabe, erste Mängelanzeige, Fristen …; dazu „<Name>vertrag vom <Datum>“).
Ein Wert zählt nur mit Merkmalswort in der Nähe und ohne anderen Wert gleicher Art dazwischen;
verneinte („nicht 64.800 km“) und bestrittene Werte bleiben außen vor. `abgleich` setzt die
gespeicherten Abschnitte eines Dokuments zu einem Text zusammen (ein Satz darf über eine
Absatzgrenze laufen), sammelt die Angaben aller Dokumente und stellt je Merkmal die Werte mit
Fundstelle (Dokument, Seite, Randnummer, Satz) gegenüber. Unvereinbare Werte gelten als
*mögliche Abweichung*, eingeordnet nach Ort (selbes Dokument, innerhalb einer Partei, zwischen
den Beteiligten; aus den Tags). Verträge gleichen Namens unter verschiedenen Anlagen werden
getrennt. Der Abgleich wird je Anfrage neu berechnet (`akten.abgleich`, optional
`dokument_ids` für zwei Dokumente) und ändert die Akte nicht. Inhaltliche Aussagen ohne Zahl
oder Datum prüft die Analyse mit dem Sprachmodell.

## Analyse mit lokalem Sprachmodell

`juracore.ki`:

- `anbieter`: Provider-Adapter für Ollama (`/api/chat`) und OpenAI-kompatible lokale Server wie
  LM Studio (`/v1/chat/completions`), nur mit der Standardbibliothek (`urllib`). Im Modus „Nur lokal“
  sind nur Loopback-Adressen erlaubt (`pruefe_lokal`), geprüft beim Speichern, Laden und vor jeder
  Verbindung; Proxy-Variablen des Systems werden umgangen. Der Kern ist dabei nur Client und öffnet
  keinen Port. Antworten kommen als JSON nach Schema (strukturierte Ausgabe), Temperatur 0, fester
  Startwert; bei denkenden Modellen (Ollama meldet `thinking`) wird die Denkphase abgeschaltet.
  Einstellungen in `<Datenverzeichnis>/ki.json`.
- `belege`: legt Dokumente als nummerierte Absätze vor („[12] Text“), teilt lange Dokumente nach
  Zeichenbudget (rund 3 Zeichen je Token, abzüglich Anweisung und Antwort) und prüft Zitate des
  Modells am gespeicherten Abschnittstext: erst im genannten Absatz, dann in den übrigen;
  wörtlich nach Vereinheitlichung (Groß-/Kleinschreibung, Leerraum, Anführungszeichen, Striche,
  weiche Trennstriche; Auslassungen „…“ als Teile in Reihenfolge), sonst angenähert ab 90 %
  übereinstimmender Zeichen. Die Fundstelle (Seite, Randnummer, Ausschnitt) hat denselben Aufbau
  wie beim Abgleich.
- `analyse`: Zusammenfassung je Dokument (Aussagen mit Art: Inhalt, Vortrag, Bestreiten,
  Rechtsansicht, Antrag, Gericht), Verdichtung langer Dokumente und der Akte über Kennungen geprüfter
  Aussagen (bei großen Akten stufenweise), Widersprüche in zwei Schritten: Tatsachenangaben je
  Dokument (mit Haltung: behauptet, bestritten, unstreitig, festgestellt), dann Vergleich aller
  Angaben in einer Anfrage oder, wenn sie nicht passen, in Blöcken, von denen je zwei gemeinsam
  geprüft werden. Einordnung (im Dokument, innerhalb einer Partei, zwischen den Beteiligten) wie
  beim Abgleich aus den Tags.
- `chronologie`: datierte Tatsachenangaben (aus `analyse`, gespeichert) und die Köpfe der Dokumente
  (Anfang bis 700 Zeichen und die letzten beiden Absätze) gehen in eine Anfrage, bei vielen Angaben
  in Blöcke nach Datum. Das Modell ordnet sie zu Ereignissen und Fristen mit Datum und nennt das
  Datum jedes Dokuments. Übernommen wird ein Ereignis nur mit gültiger Kennung; das Datum wird mit
  denselben Regeln wie beim Abgleich in den zitierten Absätzen gesucht (Monatsangaben passen auch zu
  einem Tag im Monat), sonst „Datum ohne Beleg“. Ein Dokumentdatum gilt nur, wenn es im Kopf steht,
  und verweist genau dorthin. „Streitig“ setzt das Modell oder eine bestrittene Angabe.
- `speicher`: Tabelle `ki_ergebnis` in `akten.sqlite`, Schlüssel aus Aufgabe, Anweisungsfassung
  (`FASSUNG`), Modell, Kontext und vorgelegtem Text; Kaskade mit Akte und Dokument.
- `auftraege`: Analysen laufen in einem Hintergrund-Thread mit eigener Datenbankverbindung,
  höchstens einer zugleich; `ki.starten` liefert die Auftragsnummer, `ki.auftrag` Fortschritt und
  Ergebnis, `ki.abbrechen` bricht nach dem laufenden Schritt ab, `ki.laufend` findet einen laufenden
  Auftrag nach einem Wechsel des Bereichs wieder. So bleibt der zeilenweise RPC-Kanal frei.

RPC: `ki.status`, `ki.einstellungen_setzen`, `ki.starten` (`zusammenfassung_dokument`,
`zusammenfassung_akte`, `widersprueche`, `chronologie`), `ki.auftrag`, `ki.abbrechen`, `ki.laufend`,
`ki.ergebnisse`. Kommandozeile: `juracore ki-status`, `juracore ki-pruefen <ordner> [--chronologie]`.
Getestet wird ohne echtes Modell: mit einer Attrappe für die Analyse und einem nachgebauten
Ollama-/LM-Studio-Server auf 127.0.0.1 für die HTTP-Anbindung.

## Rechtsprechung

`juracore.rechtsprechung`: `zitate` erkennt regelbasiert Gericht (Bundesgerichte, EuGH, Instanzgerichte
mit Ort), Entscheidungsart, Datum, Aktenzeichen (`normalisiere_az` vereinheitlicht Leerzeichen und
Schreibweise) oder ersatzweise eine Zeitschriftenfundstelle. `verzeichnis` lädt `rii-toc.xml` von
rechtsprechung-im-internet.de (öffentliche Rechtsquelle, keine Akteninhalte), archiviert es unverändert
unter `archiv/RECHTSPRECHUNG/<sha256>.xml` und importiert es in die Wissensbasis: `rechtsprechung_stand`
(je Abruf) → `entscheidung` (Gericht, Spruchkörper, Datum, Aktenzeichen, Dokumentnummer). Ein unveränderter
Abruf legt keinen neuen Stand an. `pruefe` vergleicht ein Zitat mit dem neuesten Stand und liefert
`belegt`, `abweichend`, `nicht_gefunden`, `ausserhalb`, `nicht_pruefbar` oder `kein_verzeichnis`.

In `akten.sqlite` (Schema 3) speichert `urteilszitat` je Abschnitt Position, Zitat, Status und den
verwendeten Stand; „Zitate neu prüfen“ prüft auch diese erneut. RPC: `akten.rechtsprechung`,
`rechtsprechung.stand`, `rechtsprechung.laden`, `rechtsprechung.laden_datei`. Kommandozeile:
`juracore rechtsprechung-laden [--datei]`, `juracore urteil "<zitat>"`.

Dokumentansicht (`juracore.dokumente.ansicht`): `akten.seitenbild(dokument_id, seite, breite)` rendert eine Seite der
abgelegten PDF-Kopie mit PDFium und gibt sie als PNG-Data-URL zurück (eigener PNG-Kodierer über `zlib`, kein Pillow;
Breite 200 bis 2400 Pixel). Die Oberfläche hat keine Dateirechte; sie fordert nur die Seiten an, die sichtbar werden.
`akten.normen` und `akten.rechtsprechung` nehmen optional `dokument_id`, um nur die Zitate eines Dokuments zu liefern.

Volltextsuche (`juracore.dokumente.suche`, Schema 5): `abschnitt_fts` ist ein FTS5-Index (`unicode61
remove_diacritics 2`) über `abschnitt.text`, gepflegt durch Trigger beim Einfügen, Ändern und Löschen; beim Öffnen
einer älteren Akte wird er einmal mit `rebuild` gefüllt. `akten.suche(text, akte_id=None)` übersetzt die Eingabe in
eine sichere FTS5-Abfrage (Wörter, „Wortfolge“, Wortanfang*), ordnet jeden Treffer über `seitenwechsel` seiner Seite
zu und gibt Dokumente mit Fundstellen (Seite oder Abschnitt, Rang nach BM25, Ausschnitt, gefundene Wortformen) zurück.
`akten.seitenbild(…, begriffe)` sucht diese Wortformen mit PDFium auf der Seite und liefert ihre Rechtecke als
`markierungen` (Anteile der Seitengröße).

Volltexte zur Akte (`juracore.dokumente.urteile`, Schema 4): `urteil` (Gericht, Aktenzeichen, Datum, Quelle
`manuell` oder `rii`, Herkunft wie „juris“, SHA-256, Pfad der unverändert abgelegten Datei) → `urteil_abschnitt`
(Text mit Seite und Randnummer). `akten.rechtsprechung` ordnet jedem Zitat das vorliegende Urteil zu: gleiches Zitat
oder gleiches Gericht und Aktenzeichen. RPC: `akten.urteil_ergaenzen`, `akten.urteile`, `akten.urteil`,
`akten.urteil_entfernen`, `rechtsprechung.eigene`.

`juracore.rechtsprechung.volltext` liest die Entscheidungen von rechtsprechung-im-internet.de (ZIP mit einer XML-Datei
nach `rii-dok.dtd`): Kopf (`gertyp`, `spruchkoerper`, `entsch-datum`, `aktenzeichen`, `doktyp`, `norm`, `vorinstanz`,
`titelzeile`) und die Teile `leitsatz`, `tenor`, `tatbestand`, `entscheidungsgruende`, `gruende` …; jeder Absatz ist ein
`<dl>`, die Randnummer steht im `<dt>` (`<a name="rd_5">5</a>`). Abruf über
`https://www.rechtsprechung-im-internet.de/jportal/docs/bsjrs/jb-<doknr>.zip`, Archiv unter
`RECHTSPRECHUNG/volltexte/<sha256>.zip` (schreibgeschützt). `akten.volltexte_laden` lädt alle belegten, noch nicht
vorliegenden Entscheidungen einer Akte; ein Fehler hält die übrigen nicht auf. Die zitierte Randnummer
(`urteilszitat.rn_zitiert`, erkannt bis Semikolon, Klammer oder Satzende hinter dem Aktenzeichen) wird gegen die
Randnummern des Volltexts geprüft (`rn_vorhanden`).

Online-Quellen (`juracore.rechtsprechung.online`, `bayern`, `neuris`): Zitate, die das Verzeichnis nicht belegt,
prüft `akten.online_pruefen` auf Nutzeraktion live, mit nichts als dem Aktenzeichen. Zuständig ist gesetze-bayern.de
für bayerische Gerichte (`bayern.ist_bayerisch`, Ortsliste) und NeuRIS für Bundesgerichte, wenn es eingeschaltet ist
(`rechtsprechung-quellen.json`, RPC `rechtsprechung.quellen`/`rechtsprechung.quellen_setzen`, Standard aus). Die
Ergebnisse stehen in der Wissensbasis (`rechtsprechung_online`, Schlüssel Quelle + Zitat) und ergänzen beim Prüfen
das Ergebnis des Verzeichnisses (`online.ergaenze`); die Entscheidung trägt dann `quelle` und `doknr`, und
`akten.volltexte_laden` lädt aus dieser Quelle. Bayern: Sitzung mit Cookie, Filter `DOKTYP/rspr`, Formular mit
`__RequestVerificationToken`, `POST /Search` mit `SearchFields.Aktenzeichen`, Trefferliste `p.hltitel`/`p.hlSubTitel`;
Volltext `GET /Content/Zip/<doknr>` (XML mit `metadaten`/`textdaten`, Randnummer `<rd nr="N"/>`), Archiv
`RECHTSPRECHUNG/bayern/`. NeuRIS: `GET /v1/case-law?fileNumber=…` (JSON-LD, `member[].item`), Volltext
`GET /v1/case-law/<documentNumber>.html` (`section#…`, `dl.border-number`), Archiv `RECHTSPRECHUNG/neuris/`. Beide
Formate sind der Funktionsbeschreibung von JuraBox Lite entnommen und müssen an echten Dateien bestätigt werden.

## Toolbox

Die Toolbox ist ein zweites Tauri-Fenster (`src-tauri/src/fenster.rs`, Befehl `toolbox_oeffnen`), das dieselbe
Oberfläche mit `?fenster=toolbox` lädt und über denselben Kernprozess rechnet; die Berechtigungen in
`capabilities/default.json` gelten für beide Fenster. Die Rechner liegen in `juracore/rechner/` (`verzugszinsen`,
`fristen`, `feiertage`, `basiszins`), sind reine Funktionen ohne Netz und Datenbank und rechnen mit `Decimal`. Die
RPC-Methoden heißen `rechner.verzugszinsen`, `rechner.frist` und `rechner.basiszins*`. Selbst eingetragene
Basiszinssätze stehen in `basiszins.json` im Datenverzeichnis und ergänzen die fest hinterlegte Tabelle nur nach
ihrem letzten Eintrag.

## Offene Punkte

- Realdaten-Test mit vollständigem BGB/ZPO-XML (Sonderfälle: Tabellen, Anlagen, verschachtelte Listen)
- Installer über GitHub Actions bauen und signieren (bisher lokal, siehe README)
- Rechtsprechung: weitere Landesportale (z. B. NRWE), EuGH (EUR-Lex); prüfen, ob die zitierte Rn. die Aussage trägt
- Bayern und NeuRIS: Formate an echten Abrufen bestätigen; Suchmaske im Bereich Rechtsprechung; Landesrecht Bayern
- Chronologie exportieren (Word, PDF, Markdown)
- Tesseract für den Installer mitliefern (Windows), damit keine eigene Installation nötig ist
- Externe Anbieter (Modus „Externer Anbieter“) mit Warnhinweis und Schlüsselspeicher
- Modellvergleich auf den Testakten (`juracore ki-pruefen`) auf der RTX-Workstation
