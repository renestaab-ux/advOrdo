# JuraBox

Desktop-App für Windows, macOS und Linux, die Schriftsätze, Schreiben und Urteile
analysiert, vergleicht und zusammenfasst. Grundlage ist eine versionierte
Wissensbasis aus Gesetzen (später auch Rechtsprechung). Leitprinzip: **Beleg vor
Behauptung**. Jede Aussage verweist auf eine Fundstelle im Dokument oder in einer
Rechtsquelle mit Fassungsstand.

Das Produktkonzept liegt im Projektordner (`Konzept.md`), die technische Umsetzung in `docs/architektur.md`.

Die App hieß früher „Juristischer Datenabgleich“. Interne Bezeichner tragen den alten
Namen bewusst weiter (Tauri-Kennung `de.juristischer-datenabgleich.app`, Paketnamen,
Datenverzeichnisse), damit vorhandene Akten, Gesetze und Einstellungen an ihrem Ort bleiben.

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `core/` | Analysekern in Python (`juracore`): Gesetzes-Import, Wissensbasis, Einlesen von Akten (PDF, DOCX, OCR), Normzitate, Abgleich von Angaben, Analyse und Chat mit lokalem Sprachmodell (externe Anbieter nur nach Freischaltung); später RAG |
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

## Installer bauen (lokal, ohne GitHub Actions)

Der Installer enthält die App und den Analysekern als eigenständiges Programm. Auf dem
Zielrechner sind dann weder Python noch Node oder Rust nötig. Gebaut wird auf dem System,
für das der Installer gedacht ist (Windows-Installer unter Windows, Linux-Pakete unter Linux).

Windows 11 (PowerShell, im Projektordner):

```powershell
.venv\Scripts\pip install -e "core[paket]"
.venv\Scripts\python core\kern_bauen.py
cd app
npm install
npm run paket
```

Die Installer liegen danach unter `app\src-tauri\target\release\bundle\`: `nsis\JuraBox_0.1.0_x64-setup.exe`
und `msi\JuraBox_0.1.0_x64_en-US.msi`. Beim ersten Bau lädt Tauri die Werkzeuge NSIS und WiX selbst
herunter. Der Installer ist nicht signiert; Windows SmartScreen fragt deshalb einmal nach
(„Weitere Informationen“, „Trotzdem ausführen“).

Linux: `.venv/bin/pip install -e "core[paket]"`, `.venv/bin/python core/kern_bauen.py`, dann
`cd app && npm install && npm run paket`. Ergebnis: `.deb`, `.rpm` und `.AppImage` unter
`app/src-tauri/target/release/bundle/`.

`core/kern_bauen.py` bündelt den Kern mit PyInstaller nach `app/src-tauri/binaries/`; `npm run paket`
legt ihn als `juracore` neben die App. Die installierte App nutzt dasselbe Datenverzeichnis wie
die Entwicklungsversion, vorhandene Akten und Gesetze bleiben also sichtbar. Tesseract und das
lokale Sprachmodell werden wie bisher separat installiert.

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

## Startbildschirm und Toolbox

Die App öffnet mit einem Startbildschirm: **Akte anlegen** (öffnet in den Akten das Feld für eine neue Akte),
**Akten**, **Eigene Daten**, **Toolbox**, die **zuletzt geöffneten Akten** und **Ihr Arbeitsbereich** mit Modus
(eigener Rechner, lokales Netzwerk oder externer Anbieter) und Arbeitsumgebung. Über „Start“ in der Navigation geht es jederzeit zurück.

Die Navigation links zeigt Symbole und Namen; **Einklappen** (unten) lässt nur die Symbole stehen, mit dem Namen als
Tooltip. Die App merkt sich die Wahl auf diesem Gerät. Vergleich und Analyse sind Reiter in der geöffneten Akte.

Die **Toolbox** öffnet ein eigenes Fenster mit den Rechnern aus JuraBox Lite. Gerechnet wird im Kern, ohne Netz:

- **Verzugszinsen** (§§ 288, 247 BGB): Hauptforderung, erster Zinstag und Ende; Verbraucher (+ 5 Punkte),
  Entgeltforderung (+ 9, bei Verzugsbeginn vor dem 29.07.2014 + 8), Dauerschuldverhältnis, eigene Punkte oder fester
  Satz; weitere Forderungen, Teilzahlungen und monatliche Raten (wirken ab dem Folgetag, Verrechnung nach § 367 BGB
  oder § 497 Abs. 3 BGB); Zinsmethoden act/act, act/360, act/365, act/365,25, act/366 und 30E/360; Pauschale nach
  § 288 Abs. 5 BGB. Ergebnis als Zinsstaffel, ungerundet gerechnet (Zeilen mit vier Nachkommastellen,
  nur die Endbeträge auf den Cent gerundet, wie bei basiszinssatz.de), druckbar. Die Basiszinssätze seit
  01.07.2002 sind hinterlegt (Deutsche Bundesbank); einen neuen Satz zum 1.1. oder 1.7. trägt man unter
  „Basiszinssatz“ selbst nach, hinterlegte Sätze werden nie überschrieben.
- **Fristen** (§§ 187, 188, 193 BGB): Ereignis- oder Tagesbeginnfrist in Tagen, Wochen, Monaten oder Jahren,
  Monatsende nach § 188 Abs. 3 BGB, Verschiebung über Wochenende und landesweite Feiertage des gewählten Bundeslands;
  alle Daten mit Wochentag. In Bayern zählt Mariä Himmelfahrt (15. August) standardmäßig mit (überwiegend
  katholische Gemeinden); hängt das Fristende davon ab, nennt ein Hinweis auch das Ende für die übrigen Gemeinden.
  Nur Vorwärtsfristen.
- **Prozesskosten** (GKG, RVG): Gerichts- und Anwaltskosten aus dem Streitwert für erste Instanz, Berufung und
  Revision; je Rechtszug Ende durch Urteil, Vergleich (ermäßigte Gerichtsgebühr, Einigungsgebühr) oder Rücknahme,
  mit oder ohne Termin; mehrere Auftraggeber (Nr. 1008 VV RVG), vorgerichtliche Geschäftsgebühr mit Anrechnung
  (Vorbem. 3 Abs. 4 VV RVG), Auslagenpauschale, Umsatzsteuer abschaltbar, gegnerische Anwaltskosten als Kostenrisiko.
  Gebührenrecht seit 01.06.2025 (KostBRÄG 2025) und vom 01.01.2021 bis 31.05.2025 wählbar; die Wertgebühren
  entsprechen Anlage 2 GKG und Anlage 2 RVG.

## Akten: Übersicht und geöffnete Akte

Der Bereich **Akten** zeigt zuerst die **Aktenübersicht**: Suche über Aktenzeichen, Kurzbezeichnung, Mandant, Gegner,
Gegenstand, Gericht und gerichtliches Aktenzeichen; Filter nach Status (Vorgabe: laufend), Frist, Sachgebiet,
Sachbearbeiter und Gericht; darüber die zuletzt geöffneten Akten. Ein Klick auf einen Spaltenkopf sortiert, ein
zweiter kehrt die Reihenfolge um; die Wahl bleibt gespeichert (Vorgabe: zuletzt bearbeitet, Öffnen allein zählt
nicht als Bearbeiten; Aktenzeichen nach Jahr und Nummer). Das Beteiligtenverzeichnis lässt sich ebenso sortieren
und nach Art, Kategorie und Rolle filtern (Geschäftsführer zählen zur Seite ihrer Firma). Akten ohne Aktenzeichen tragen die Marke **Aktenzeichen fehlt**; ein Klick darauf
öffnet die Stammdaten. **+ Neue Akte** (wie die Kachel „Akte anlegen“ auf der
Startseite) öffnet eine eigene Seite: Kurzbezeichnung und Aktenzeichen (leer: Vorschlag), danach geht es mit den
Stammdaten und den Beteiligten der neuen Akte weiter.

Ein Klick auf eine Zeile öffnet die Akte. Der Kopf zeigt Aktenzeichen, Gegenstand, Kurzbezeichnung, Gericht mit
Aktenzeichen und wen wir vertreten; **← Akten** führt zurück, **Stammdaten** öffnet Aktenzeichen, Gegenstand,
Sachgebiet, Status usw. Darunter die Reiter **Dokumente**, **Beteiligte**, **Vergleich**, **Analyse**, **Normen**,
**Rechtsprechung** und **Chat mit der Akte**. Im Reiter Dokumente stehen drei Spalten nebeneinander: Filter (Ordner,
Partei und Tags, Zitate nicht belegt, Beteiligte), die Dokumentliste und das geöffnete Dokument. Die Filterspalte
lässt sich einklappen; auch das merkt sich die App.

## Akte: Dokumente einlesen

Im Reiter **Dokumente** einer Akte fügt man Schriftsätze, Schreiben und Urteile hinzu
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

Noch nicht erkannt werden Zitate ohne „§“/„Art.“
(z. B. „Nr. 2300 VV RVG“) und inhaltlich veraltete Zitate einer noch existierenden Norm
(z. B. § 476 BGB als Beweislastumkehr, seit 2022 § 477 BGB). Word-Dateien haben nur dann
Seitenzahlen, wenn sie Seitenumbrüche enthalten; sonst gilt die Randnummer bzw. der
laufende Absatz („Abschn. 12“) als Fundstelle.

### Datum der Dokumente

Die Dokumentliste zeigt zu jedem Dokument ein Datum und darunter, woher es stammt:

1. **aus dem Dokument**: die Datumszeile im Text, z. B. „Freiburg, den 23.06.2025“, „Denzlingen, 30.06.2025“
   oder „Verkündet am 14.09.2026“. Es zählt die erste solche Zeile; Daten im Fließtext („Schreiben vom …“)
   nimmt die App nicht, weil sie andere Vorgänge bezeichnen. Ein Klick auf das Datum öffnet das Dokument an
   der Datumszeile.
2. **zuletzt gespeichert**: Word-Datei ohne Datumszeile, etwa ein Entwurf. Das Datum stammt aus den
   Dokumenteigenschaften, die Word beim Speichern schreibt.
3. **Dateidatum**: sonst das Änderungsdatum der Datei beim Einlesen.

Fährt man mit der Maus über das Datum, nennt die App die Fundstelle und den letzten Speicherstand. Ein Klick
auf die Spalte „Datum“ ordnet die Liste zeitlich, älteste zuerst. Bei Dokumenten, die vor dieser Version
eingelesen wurden, ergänzt die App das Datum beim Start aus dem gespeicherten Text; das Dateidatum am
ursprünglichen Ort kennt sie dafür nicht mehr.

### Dokumentansicht

Ein geöffnetes Dokument lässt sich auf fünf Arten zeigen:

- **Text**: der gelesene Text mit Fundstellen und markierten Zitaten; ein Klick auf ein Normzitat zeigt den Wortlaut.
- **Original** (nur PDF): die Seiten der abgelegten Originaldatei, wie sie gedruckt aussehen. Der Kern rendert sie
  auf dem Gerät mit PDFium; nichts verlässt den Rechner. Wurde vorher ein Zitat gewählt, springt die Ansicht auf
  dessen Seite, und der Wortlaut bleibt daneben stehen.
- **Normen** und **Rechtsprechung**: wie die Reiter „Normen“ und „Rechtsprechung“ der Akte, aber nur mit den
  Zitaten aus diesem Dokument. Volltexte laden und Urteile ergänzen geht auch hier.
- **Chat**: Fragen an dieses eine Dokument (siehe „Chat mit Akte und Dokument“).

### In anderen Programmen öffnen und bearbeiten (Fassungen)

Unter der Leiste des geöffneten Dokuments:

- **Öffnen** übergibt eine schreibgeschützte Kopie an das PDF-Programm (PDF) bzw. die Textverarbeitung (Word, TXT,
  MD). Die abgelegte Datei der Akte wird nie verändert.
- **Bearbeiten** legt eine Arbeitskopie an und öffnet sie; eine vorhandene Arbeitskopie wird weiterverwendet. Nach dem
  Speichern im anderen Programm fragt JuraBox, sobald man zur App zurückkehrt: **Als Fassung 2 übernehmen** legt die
  Datei unverändert ab und liest Text, Normzitate und Datum neu ein; Tags, Chat und Fassung 1 bleiben. Gespeicherte
  Ergebnisse des Sprachmodells zu dieser Akte werden dabei verworfen, weil sie auf dem alten Text beruhen. **Später**
  fragt erst nach dem nächsten Speichern wieder; **Arbeitskopie verwerfen** entfernt die Kopie.
- **Fassung n** zeigt alle Fassungen mit Datum; jede lässt sich schreibgeschützt öffnen. In der Dokumentliste steht
  „Fassung 2“ bzw. „in Bearbeitung“ beim Dokument.
- **Im Ordner zeigen** öffnet den Dateimanager bei der Arbeitskopie bzw. einer Kopie zum Ansehen.

Welche Programme das sind, steht in **Einstellungen › Programme**: Voreinstellung ist das Standardprogramm des
Systems; alternativ wählt man eine Programmdatei (LibreOffice, Microsoft Word, Okular, PDF-XChange …) und optional
Aufrufparameter („{datei}“ steht für die Datei). JuraBox übergibt nur die Datei, unter Windows, macOS und Linux gleich.

### Ordner, Beteiligte und Entfernen

- **Ordner hinzufügen …** liest einen ganzen Ordner samt Unterordnern ein (PDF, DOCX, TXT, MD;
  andere Dateien werden übersprungen und genannt).
- Aus den Namen der Unterordner schlägt die App Tags vor, die zeigen, zu welchem Beteiligten ein
  Dokument gehört: „01_Kläger“ und „Klägerin“ werden zu **Kläger**, „Beklagte“ zu **Beklagter**,
  „Landgericht“ zu **Gericht**, andere Namen bleiben, wie sie sind. Vor dem Einlesen fragt die App,
  ob die Tags übernommen werden sollen; die Vorschläge lassen sich dort ändern oder leeren.
- In der Dokumentliste lassen sich Tags jederzeit von Hand setzen und ändern („+ Tag“ bzw. „Tags ändern“, sichtbar
  beim Zeigen auf die Zeile). Tags aus dem Ordnernamen sind durchgezogen umrandet, von Hand gesetzte gestrichelt.
  Über die Filterspalte filtert man die Liste, z. B. alle Dokumente des Gerichts.
- **entfernen** (je Dokument) und **Akte entfernen …** (in den Stammdaten) löschen nach einer Rückfrage den gelesenen
  Text, die Zitate, die Tags und die Kopie, die die App beim Einlesen abgelegt hat. Die
  Originaldatei am ursprünglichen Ort bleibt unverändert.

### Stammdaten, Beteiligte und Kollisionsprüfung

Konzept: „Aktenverwaltung“ vom 19.10.2026, Stufe 1. In der Akte öffnen **Stammdaten** (Knopf im Kopf) und der Reiter
**Beteiligte**; ungespeicherte Eingaben in den Stammdaten werden beim Verlassen gespeichert:

- **Aktenzeichen** nach dem Schema Nummer/Jahr (102/26): Neue Akten bekommen die nächste freie Nummer des laufenden
  Jahres; beim Anlegen lässt sich auch ein eigenes eintragen. Ein vergebenes Aktenzeichen wird nie ein zweites Mal
  vergeben, auch nicht nach dem Löschen der Akte. Unter **Einstellungen → Akten** stellt man die nächste Nummer ein
  (für eine bisherige Zählung) und einen Zusatz wie ein Kürzel (102/26 RS). Bestehende Akten behalten ihre Daten und
  bekommen ihr Aktenzeichen dort nachträglich.
- **Stammdaten**: Kurzbezeichnung, Gegenstand, Sachgebiet, eigene Rolle, Status (laufend, ruhend, abgeschlossen),
  Sachbearbeiter aus „Eigene Daten“, Mandat seit, Gegenstandswert, Notiz.
- **Beteiligte** mit Rolle und Seite: Mandant, Gegner, Prozessbevollmächtigter und Versicherer des Gegners, Gericht
  (mit gerichtlichem Aktenzeichen), Sachverständiger, Zeuge, Streitverkündeter. Personen und Organisationen stehen
  einmal im **Beteiligtenverzeichnis** und werden in jeder Akte wiederverwendet; beim Anlegen weist die App auf
  gleiche oder ähnliche Namen hin. Zu einem Eintrag lassen sich frühere Namen, gesetzliche Vertreter und verbundene
  Organisationen (Mutter, Tochter) erfassen; gesetzliche Vertreter mit Anrede, Titel und Funktion („vertreten durch
  Frau Dr. Mira Lenz (Geschäftsführerin)“) auch direkt beim Anlegen der Organisation. Bei einer Rechtsabteilung ist
  die Konzerngesellschaft aus „Eigene Daten“ der Mandant, dazu kommt der vertretende Anwalt.
- Der Bereich **Beteiligte** in der linken Leiste zeigt das ganze Verzeichnis mit Suche und der Rolle je Eintrag (z. B.
  „Mandant“, „Gegner · 2 Akten“, „Geschäftsführerin von …“): Einträge bearbeiten, neu
  anlegen, löschen (nur ohne Akte) und von dort in die Akten springen, an denen jemand beteiligt ist.
- **Kollisionsprüfung** (§ 43a Abs. 4 BRAO, § 3 BORA): Sobald Mandant oder Gegner eingetragen werden, sucht die App in
  allen Akten, auch abgeschlossenen, ob dieselbe Partei anderswo auf der anderen Seite steht. Verglichen werden Namen
  ohne Rechtsform und Titel (auch frühere Namen), Geburtsdatum bzw. Registernummer, gesetzliche Vertreter und
  verbundene Organisationen. **Rot**: dieselbe Partei; **Gelb**: ähnlicher Name (auch Nachname allein oder ein
  Tippfehler), Vertreter, verbundene Organisation oder (Rechtsabteilung) eine eigene Konzerngesellschaft als Gegner.
  Schon die Suchtreffer beim Hinzufügen zeigen einen möglichen Konflikt, bevor jemand eingetragen ist. Die anderen Arbeitsumgebungen auf dem Gerät
  durchsucht die App mit, aber nur lesend, etwa bei Doppelzulassung; Testumgebungen lassen sich unter Einstellungen
  ausnehmen. Ob ein Konflikt besteht, entscheidet der Anwalt; Prüfung, Treffer und Entscheidung mit Begründung
  bleiben in der Akte dokumentiert.

### Verfahren, Fristen, Notizen und Akte aus Dokument (Stufe 2)

- **Verfahren** (unter Stammdaten): Mahnverfahren, Klageverfahren, Berufung, einstweiliger Rechtsschutz usw. mit
  **Instanz**, Gericht, Spruchkörper und gerichtlichem Aktenzeichen. Eine Akte kann mehrere Verfahren nacheinander
  haben; das jüngste laufende steht im Kopf der Akte und in der Übersicht. Das Gericht wird dabei auch als
  Beteiligter (Rolle Gericht, mit Aktenzeichen) eingetragen.
- Reiter **Fristen**: Fristen, Termine und Wiedervorlagen. Fristen rechnet der Fristenrechner der Toolbox (§§ 187, 188,
  193 BGB, Feiertage des dort gewählten Landes) aus Bezugstag und Dauer; die Berechnung bleibt beim Eintrag sichtbar.
  Dazu Vorfrist, Verfahren und Notiz; erledigte Einträge bleiben nachvollziehbar.
  **Vorschläge aus Dokumenten** sucht in den Dokumenten der Akte nach Fristen („binnen vier Wochen nach Zustellung“,
  berechnet ab einem „zugestellt am …“ im Dokument), Terminen mit Uhrzeit und Saal und aufgehobenen Terminen. Jeder
  Vorschlag zeigt den Satz mit Fundstelle und wird erst nach Prüfung eingetragen; er ersetzt nicht die eigene
  Fristenkontrolle.
- **Nächste Fristen**: auf der Startseite die offenen Einträge der nächsten 14 Tage aus allen Akten (abgelaufene
  zuerst), in der Aktenübersicht die Spalte „Nächste Frist“ und der Filter „Frist in 7 Tagen“, im Kopf der Akte die
  nächste Frist.
- **Erinnerungen**: Solange JuraBox läuft, meldet das Betriebssystem fällige Fristen (bei erreichter Vorfrist, am
  Vortag, am Tag des Ablaufs, einmal nach Ablauf), Termine (Vortag und Tag) und Wiedervorlagen, beim Start und dann
  alle zehn Minuten; jede Stufe nur einmal. Beim ersten Mal fragt das System, ob JuraBox Mitteilungen zeigen darf.
  Abschalten und Probe-Erinnerung unter Einstellungen → Akten. Ist die App geschlossen, erinnert sie nicht.
- Reiter **Notizen**: kurze Vermerke zur Akte oder zu einem Dokument, wichtige oben angeheftet.
- **Akte aus Dokument**: Beim Anlegen ein Dokument wählen (Klage, Anspruchsbegründung, Mahnbescheid, Verfügung). Die
  App liest Gericht, Aktenzeichen, Parteien mit Anschrift und gesetzlichem Vertreter, Prozessbevollmächtigte,
  Gegenstand und Streitwert aus dem Rubrum und zeigt alles mit Fundstelle zur Prüfung, dazu vorhandene Einträge im
  Beteiligtenverzeichnis. Welche Seite wir vertreten, leitet sie aus „Eigene Daten“ ab (eigene Kanzlei als
  Prozessbevollmächtigte, Konzerngesellschaft als Partei) oder fragt. Erst „Akte anlegen“ übernimmt die Auswahl, liest
  das Dokument ein und startet die Kollisionsprüfung.
- Testakte: `testdaten/testakte-weber` (fiktiv; Mahnverfahren, Abgabe an das Landgericht, Verfügung mit Frist und Termin,
  Terminsverlegung; die Gegnerin ist in der Testakte Brückner Mandantin).

## Suche: Volltext über alle Akten

Der Bereich **Suche** durchsucht den gelesenen Text der Dokumente einer Akte oder aller Akten, nach dem Vorbild von „PDF Search“
für macOS. Die Treffer erscheinen schon beim Tippen:

- links je Dokument Akte, Seitenzahl und Anzahl der Treffer; darunter die Fundstellen (Seite, bei Word- und
  Textdateien Randnummer oder Abschnitt) mit Rang und Textausschnitt,
- rechts das Dokument: bei PDFs das Original mit gelb markierten Fundstellen, sonst der Text mit markierten Wörtern,
- ▲ und ▼ springen zur vorigen oder nächsten Fundstelle,
- das Auswahlfeld neben dem Suchfeld legt fest, wo gesucht wird: in der gewählten Akte (Standard) oder in allen Akten.

Groß- und Kleinschreibung und Akzente spielen keine Rolle („rucktritt“ findet „Rücktritt“). Mehrere Wörter müssen
alle vorkommen; eine genaue Wortfolge steht in Anführungszeichen („"Frist bis zum"“); ein Wortanfang endet auf *
(„Nachbesser*“). Ohne * findet die Suche nur ganze Wörter. Der Suchindex liegt in `akten.sqlite` und wird beim
Einlesen und Entfernen von Dokumenten mitgeführt; Akten aus älteren Versionen werden beim ersten Start einmalig
aufgenommen. Wörter, die im PDF über eine Silbentrennung laufen, findet die Suche im Text, markiert sie im Original
aber nicht.

## Vergleich: Angaben abgleichen

Der Reiter **Vergleich** einer Akte stellt dieselben Angaben aus den
Dokumenten einer Akte nebeneinander, entweder aus allen Dokumenten oder aus zwei gewählten:

- erkannt werden Daten, Beträge, Kilometerstände und Fehlercodes mit ihrem Bezug, z. B.
  Kaufpreis, Übergabe/Gefahrübergang, Kilometerstand bei Übergabe, erste Mängelanzeige,
  Frist zur Nacherfüllung, Zahlungsfrist, Reparaturkosten, Streitwert, Fehlerspeicher und
  das Datum eines Vertrags („Kaufvertrag vom 14.03.2025“),
- jede Angabe steht mit Fundstelle (Dokument, Seite, Randnummer) und dem Satz, aus dem sie stammt;
  ein Klick öffnet das Dokument an dieser Stelle,
- **mögliche Abweichungen** stehen oben, eingeordnet nach Ort: im selben Dokument, innerhalb einer
  Partei oder zwischen den Beteiligten (nach den Tags der Dokumente),
- übereinstimmende Angaben und Angaben aus nur einem Dokument lassen sich aufklappen.

Erkannt wird bewusst zurückhaltend: Werte, die im Text verneint („betrug nicht 64.800 km“) oder
bestritten werden, zählen nicht als eigene Angabe. „Mitte Juni 2025“ passt zu jedem Datum im
Juni. Eine Abweichung ist ein Hinweis, keine Bewertung. Aussagen ohne Zahl oder Datum (etwa ob
eine Nachbesserung angeboten oder abgelehnt wurde) prüft der Reiter **Analyse**.

## Analyse: lokales Sprachmodell

Der Reiter **Analyse** einer Akte fasst Dokumente und die ganze Akte zusammen und sucht inhaltliche
Widersprüche, auch solche ohne Zahl oder Datum („Nachbesserung abgelehnt“ gegenüber „Nachbesserung
angeboten“). Dafür läuft ein Sprachmodell über Ollama oder LM Studio, auf diesem Gerät oder auf einem
anderen Rechner im eigenen Netzwerk. Die App spricht nur mit Adressen auf diesem Gerät (`localhost`,
`127.0.0.1`) oder im eigenen Netz (private Adressen wie `192.168.x.x`, `10.x.x.x`, Rechnernamen ohne
Punkt oder mit `.local`, `.lan`, `.fritz.box`); ein Name muss beim Verbinden auf eine private Adresse
zeigen. Andere Adressen lehnt sie ab. Die Navigation zeigt „KI-Modus: Eigener Rechner“ oder
„KI-Modus: Lokales Netzwerk“. Auf dem anderen Rechner muss das Programm Verbindungen aus dem Netz
annehmen (LM Studio: „Serve on Local Network“, Ollama: `OLLAMA_HOST=0.0.0.0`) und die Firewall den
Port freigeben.

**Beleg vor Behauptung:** Das Modell muss zu jeder Aussage den Absatz und ein wörtliches Zitat
nennen. Die App sucht das Zitat im gespeicherten Originaltext und zeigt die Fundstelle (Seite,
Randnummer, Ausschnitt) aus dem Dokument, nicht die Wiedergabe des Modells. Steht das Zitat nicht
im Dokument, heißt die Aussage „ohne Beleg“; Tatsachenangaben ohne Beleg nimmt die
Widerspruchssuche gar nicht erst auf. Ein Widerspruch zählt nur, wenn er auf mindestens zwei
belegte Angaben verweist. Die Erklärung dazu ist eine Einschätzung des Modells; maßgeblich sind die
Fundstellen.

**Chronologie:** „Chronologie erstellen“ ordnet die datierten Tatsachenangaben (dieselben wie bei
der Widerspruchssuche, sie werden nicht neu erhoben) und das Datum jedes Dokuments zu einer
Zeitleiste: Ereignisse, Fristen und Dokumente, jeweils mit Fundstellen. Ein Ereignis heißt
„streitig“, wenn eine Seite es bestreitet. Die App prüft, ob das Datum in einem der zitierten
Absätze steht; sonst heißt der Eintrag „Datum ohne Beleg“. Das Datum eines Dokuments übernimmt sie
nur, wenn es am Anfang oder Schluss des Dokuments steht.

Ergebnisse werden in der Akte gespeichert und beim nächsten Öffnen gezeigt; die Analyse läuft im
Hintergrund und lässt sich abbrechen.

### Ollama unter Windows 11 einrichten

In einer PowerShell:

```powershell
winget install Ollama.Ollama
```

Ollama startet danach im Hintergrund (Symbol unten rechts in der Taskleiste). Dann ein Modell laden,
einmalig, rund 9 GB:

```powershell
ollama pull qwen3:14b
```

Qwen3 14B passt mit 16.384 Token Kontext in 16 GB Grafikspeicher (RTX 5070 Ti) und schreibt gut
Deutsch. Danach in der App unter **Einstellungen** „Erneut prüfen“, das Modell wählen und speichern.
Prüfen ohne App, im Projektordner:

```powershell
.venv\Scripts\juracore ki-status
```

Linux: `curl -fsSL https://ollama.com/install.sh | sh`, macOS: `brew install ollama`. LM Studio
geht genauso: dort den lokalen Server starten und in den Einstellungen „LM Studio“ wählen.

### Probelauf mit der Testakte

```powershell
.venv\Scripts\juracore ki-pruefen "Pfad\zu\Brückner_gegen_Autohaus" --erwartungen "Pfad\zu\erwartungen.json" --zusammenfassung
```

liest den Ordner in eine eigene Akte im Unterordner `ki-pruefen-daten` des aktuellen Verzeichnisses
(die Akten der App bleiben unberührt), sucht
Widersprüche, gibt sie mit Fundstellen aus und zählt, welche der erwarteten (W1 bis W8) gefunden
wurden. Mit `--modell gemma3:12b` lässt sich ein anderes Modell vergleichen, mit
`--anbieter lmstudio` nimmt der Probelauf LM Studio statt Ollama (ohne `--modell` das erste
geladene Modell), mit `--kontext 32768` einen größeren Kontext (bei LM Studio denselben Wert dort
beim Laden des Modells einstellen). Mit `--chronologie` erstellt der Probelauf zusätzlich die
Chronologie und vergleicht sie mit den erwarteten Ereignissen aus `erwartungen.json`.
`juracore ki-status` kennt dieselben Optionen.

Die Antworten des Modells bleiben in `ki-pruefen-daten` gespeichert, solange sich die Testakte nicht
ändert und Modell und Kontext gleich bleiben. Ein abgebrochener Lauf setzt dadurch beim nächsten Mal
dort fort, wo er stehen geblieben ist. Für einen Neuanfang den Ordner löschen.

## Chat mit Akte und Dokument

In einer geöffneten Akte stellt der Reiter **Chat mit der Akte** Fragen an alle Dokumente der Akte, der
Modus **Chat** eines geöffneten Dokuments nur an dieses. Die Antwort besteht aus einzelnen Aussagen:

- **Aus der Akte**: eine Tatsache mit Fundstelle. Das Modell nennt Dokument, Absatz und ein wörtliches
  Zitat; die App prüft das Zitat am Originaltext und zeigt die gefundene Stelle (Klick öffnet das
  Dokument daneben). Steht das Zitat so nicht im Dokument, heißt die Aussage „ohne Beleg“.
- **Einschätzung des Modells**: rechtliche oder inhaltliche Würdigung, gegebenenfalls mit den Stellen,
  auf die sie sich stützt.
- **Hinweis**: etwa, dass die Dokumente zur Frage nichts enthalten.

Die Fundstellen stehen zunächst eingeklappt als kurze Quellenangabe unter der Aussage (das Zitat zeigt
der Tooltip). „Zitate einblenden“ zeigt die Sätze aus den Dokumenten; dasselbe gilt in „Analyse“ und
„Vergleich“.

Passt die Akte in den Kontext des Modells, sieht es alle Dokumente vollständig. Sonst bekommt es den
Kopf jedes Dokuments (die ersten zwei Absätze) und die Absätze mit den meisten Begriffen der Frage; der
Rest des Platzes wird in Aktenreihenfolge aufgefüllt. Unter jeder Antwort steht, was vorlag. Die
letzten drei Fragen und Antworten gehen als Zusammenhang mit. Der Verlauf bleibt je Akte bzw. Dokument
gespeichert, bis man ihn leert oder die Akte entfernt.

## Externe KI (nur ausnahmsweise)

Voreingestellt arbeitet die App nur lokal. Unter „Einstellungen“ → „Externe KI“ lassen sich Anthropic
Claude, OpenAI, Google Gemini, Mistral oder ein anderer Dienst mit OpenAI-kompatibler Schnittstelle
(nur HTTPS) anbinden. Das geht erst, nachdem der Schalter **Externe KI einbinden** eingeschaltet und der
Hinweis auf Datenschutz- und Berufsrecht bestätigt wurde. Danach API-Schlüssel und Modell eintragen,
„Speichern“ (fragt beim Anbieter nur die Modellliste ab) und unter „Analyse und Chat verwenden“ den
externen Anbieter wählen. Solange er gewählt ist, steht links unten „KI-Modus: Externer Anbieter“, und
Analyse und Chat weisen darauf hin, dass Dokumenttexte das Gerät verlassen. Schalter aus stellt sofort
wieder auf lokal.

Die Schlüssel liegen in `ki-schluessel.json` im Datenverzeichnis der App (Linux/macOS: nur für den
Benutzer lesbar), getrennt von `ki.json`, und werden nie wieder angezeigt. Die Kommandozeile
(`ki-status`, `ki-pruefen`) arbeitet immer lokal.

## Diagnose

Einstellungen → **Diagnose öffnen** → „Prüfung starten“ prüft nacheinander: Kern und Datenordner (beschreibbar,
freier Speicher), die Datenbanken (`PRAGMA quick_check`), das Archiv der Rechtsquellen (jede Datei gegen ihre
SHA-256-Prüfsumme), Texterkennung, externe Programme, Mitteilungen des Systems, das lokale Sprachmodell, die externe
KI (nur wenn eingebunden; abgefragt wird die Modellliste) und die Rechtsquellen im Internet (Gesetze im Internet,
EUR-Lex, Rechtsprechung im Internet, gesetze-bayern.de, NeuRIS wenn eingeschaltet; jeweils nur die ersten Bytes).
Jeder Fehler kommt mit einer verständlichen Meldung und einem Hinweis „Was tun“. „Bericht kopieren“ legt das Ergebnis
als Text in die Zwischenablage; er enthält keine Dokumentinhalte und keine Schlüssel.

## Rechtsprechung: Urteilszitate prüfen

Beim Einlesen erkennt die App auch Rechtsprechungszitate („BGH, Urteil vom 12.10.2016 – VIII ZR 103/15“,
„BAG, Urt. v. 20.2.2019 – 2 AZR 746/14“, „OLG Hamm, Beschl. v. …“, „EuGH, C-497/13“) und prüft sie gegen
das Verzeichnis der Bundesgerichte von rechtsprechung-im-internet.de (BVerfG, BGH, BVerwG, BFH, BAG, BSG,
BPatG, GmS-OGB). Das Verzeichnis lädt man einmal in den **Einstellungen → Rechtsquellen** („Verzeichnis laden“); es ist
eine öffentliche Liste und wird wie die Gesetze unverändert unter seiner SHA-256-Prüfsumme archiviert.
Danach zeigt die Akte im Reiter **Rechtsprechung der Akte**:

- **belegt**: Gericht, Aktenzeichen und Datum stimmen mit einer Entscheidung im Verzeichnis überein;
  der Link führt zum Volltext beim Bund,
- **Angaben weichen ab**: das Aktenzeichen gibt es, aber mit anderem Datum oder bei einem anderen Gericht,
- **nicht auffindbar**: keine Entscheidung dieses Bundesgerichts mit dem Aktenzeichen, Zitat prüfen,
- **nicht im Verzeichnis**: Instanzgerichte, EuGH, ältere Entscheidungen vor Beginn des Verzeichnisses,
- **nicht prüfbar**: Zitat nur mit Zeitschriftenfundstelle (z. B. „BGH NJW 2017, 1093“).

Geprüft wird nur, ob es die Entscheidung gibt, nicht, ob sie die zitierte Aussage trägt.

**Urteile selbst ergänzen:** Bei jedem Zitat lässt sich eine eigene Datei als Volltext ablegen („Urteil selbst
ergänzen …“), z. B. ein PDF-Ausdruck aus juris oder beck-online für ein OLG-Urteil, das nicht im Verzeichnis steht.
Gericht, Aktenzeichen und Datum werden aus dem Zitat vorgeschlagen, die Quelle aus dem Dateinamen. Die Datei wird
unverändert bei der Akte abgelegt (`akten/akte-<id>/urteile/`) und gelesen; Randnummern werden erkannt. Das ergänzte
Urteil gilt auch für andere Zitate der Akte mit demselben Gericht und Aktenzeichen. Der Reiter
**Einstellungen → Rechtsquellen** zeigt alle Quellen und wie viele Entscheidungen selbst ergänzt wurden.

**Volltexte laden und Randnummern prüfen:** „Volltexte laden“ im Reiter „Rechtsprechung der Akte“ holt die belegten
Entscheidungen der Bundesgerichte von rechtsprechung-im-internet.de (Leitsatz, Tenor, Tatbestand, Gründe mit
Randnummern). Gesendet wird nur die Nummer der Entscheidung; die Datei wird unverändert unter ihrer SHA-256-Prüfsumme
im Roharchiv abgelegt (`RECHTSPRECHUNG/volltexte/`) und bleibt dort, auch wenn man das Urteil aus der Akte entfernt.
Zitiert ein Schriftsatz „…, Rn. 36“, zeigt die App, ob es diese Randnummer gibt, und springt per Klick dorthin;
„Rn. 84“ bei einer Entscheidung mit 67 Randnummern wird als Fehler markiert. Das gilt auch für selbst ergänzte Urteile,
sofern ihre Randnummern erkannt werden. „Alle Volltexte laden“ holt alle auf einmal, „Volltext laden“ beim einzelnen
Zitat nur diese Entscheidung. Die Breite der Volltext-Leiste lässt sich mit der Trennlinie verschieben (Doppelklick:
zurück auf Standard).

**Bayern und NeuRIS online prüfen:** Für Zitate, die das Verzeichnis nicht belegen kann, gibt es im Reiter
„Rechtsprechung der Akte“ den Knopf **„Online prüfen“**:

- Zitate **bayerischer Gerichte** (OLG München, LG Traunstein, BayObLG, VGH München …) sucht die App beim
  Bürgerservice BAYERN.RECHT (gesetze-bayern.de). Das Portal hat kein Verzeichnis; gesucht wird live, nur auf
  Knopfdruck und nur mit dem Aktenzeichen. Dort stehen nur zur Veröffentlichung bestimmte Entscheidungen; fehlt
  eine, bleibt das Zitat „nicht im Verzeichnis“ mit einem Hinweis.
- Zitate der **Bundesgerichte**, die im Verzeichnis fehlen (z. B. ganz neue Entscheidungen), sucht die App bei
  **NeuRIS**, dem Rechtsinformationsportal des Bundes. NeuRIS ist noch in der Testphase und deshalb zunächst aus;
  einschalten in den **Einstellungen → Rechtsquellen** („NeuRIS-Rechtsprechung nutzen“).

Was online gefunden wird, gilt als belegt (die Quelle steht im Hinweis), und „Volltext laden“ holt die
Entscheidung dann aus dieser Quelle: bei Bayern das ZIP (Archiv `RECHTSPRECHUNG/bayern/`), bei NeuRIS das HTML
(`RECHTSPRECHUNG/neuris/`), jeweils unverändert unter der SHA-256-Prüfsumme. Die Ergebnisse der Online-Prüfung
sind öffentliche Angaben ohne Bezug zur Akte und liegen in der Wissensbasis; ein Zitat wird nur einmal abgefragt.

**Sammlung im Bereich „Rechtsprechung“:** Dort stehen alle gespeicherten Entscheidungen aus allen Akten, je Datei
einmal, mit Quelle und den Akten, denen sie zugeordnet sind, oder „nicht zugeordnet“. Filter nach Zuordnung und
Quelle, ein Feld zum Eingrenzen (Gericht, Aktenzeichen, Akte) und eine Volltextsuche im Text aller gespeicherten
Entscheidungen (Treffer mit Randnummer, Klick springt dorthin). Ein Klick auf die Karte öffnet den Volltext rechts;
die Trennlinie dazwischen lässt sich verschieben (Doppelklick: zurück auf Standard), „Volltext schließen“ steht oben
in der Volltextleiste. **Eigene Datei hinzufügen …** legt eine Entscheidung
ohne Akte ab (`<Ablage>/rechtsprechung/`); Gericht, Aktenzeichen, Datum, Art und Quelle schlägt die App dabei aus dem
Kopf des Dokuments vor (beschriftete Felder wie bei juris und openJur, Zitierzeile wie bei beck-online oder Kopf einer
Ausfertigung mit „Verkündet am …“), jeweils mit Fundstelle zum Prüfen; **Akte zuordnen …** ordnet sie einer oder mehreren Akten zu, das × an
einer Akte löst die Zuordnung (die Entscheidung bleibt in der Sammlung), **Entscheidung entfernen** nimmt sie ganz heraus, auch
aus allen Akten. Wird eine Akte gelöscht, verschwinden ihre Zuordnungen; die anderen bleiben. In der Akte stehen
zugeordnete Entscheidungen, die in ihren Dokumenten nicht zitiert sind, im Reiter „Rechtsprechung“ unter **Zur
weiteren Bearbeitung zugeordnet** (mit Volltext und „Zuordnung lösen“); Chat und Gegenüberstellung beziehen sie mit
ein.

**Online suchen** (im Bereich „Rechtsprechung“, wie in JuraBox Lite): je Quelle eine eigene Maske.
rechtsprechung-im-internet.de: Gericht, Aktenzeichen und Zeitraum sucht die App im geladenen Verzeichnis, ohne Netz;
mit Volltext, Norm (z. B. „§ 476 BGB“) oder ECLI fragt sie die Suche der Seite ab (25 Treffer je Seite, „Weitere
Treffer laden“, höchstens 200). Gerichtsentscheidungen Bayern: Gerichtsbarkeit, Aktenzeichen, Volltext, Zeitraum
(erste Trefferseite; für mehr die Suche eingrenzen). NeuRIS (nur wenn unter Einstellungen → Rechtsquellen
eingeschaltet): Gericht, Aktenzeichen, Suchbegriff, Zeitraum. Gesucht wird erst auf „Suchen“; an die Quelle gehen nur
die eingegebenen Begriffe. Ein Treffer öffnet sich rechts, ohne gespeichert zu werden; **In die Sammlung** übernimmt
ihn (unverändert im Roharchiv, SHA-256), **In die Sammlung und Akte zuordnen …** ordnet ihn zugleich einer Akte zu.
Schon gespeicherte Treffer tragen „in der Sammlung“.

Nutzung: Nach den Nutzungshinweisen von gesetze-bayern.de dürfen Vorschriften und Entscheidungen uneingeschränkt
weiterverwendet werden; die redaktionellen Leitsätze (C.H.Beck) sind urheberrechtlich geschützt, die Datenbank
nach §§ 87a ff. UrhG. Gerichtsentscheidungen sind amtliche Werke (§ 5 UrhG). Die App ruft deshalb nur einzelne
Entscheidungen ab, nie den ganzen Bestand.

Ohne App:

```bash
juracore rechtsprechung-laden                       # Verzeichnis abrufen (oder --datei rii-toc.xml)
juracore urteil "BGH, Urteil vom 12.10.2016 – VIII ZR 103/15"
juracore urteil "BGH, VIII ZR 103/15" --volltext  # lädt den Volltext und zeigt Leitsatz und Randnummern
juracore urteil "OLG München, Urteil vom 14.03.2023 – 7 U 1234/22" --online --volltext  # Bayern bzw. NeuRIS
```

## Wissensbasis: Gesetze

```bash
juracore import BGB ZPO HGB                  # lädt XML von gesetze-im-internet.de
juracore import GmbHG InsO                   # jedes weitere Bundesgesetz über seine Abkürzung
juracore import-datei pfad/zu/bgb.zip        # offline aus einer heruntergeladenen Datei
juracore zitat "§ 280 Abs. 1 S. 2 BGB"       # Wortlaut mit Fassungsstand
juracore suche "Verjährungsfrist"
juracore liste
```

- Voreingestellt sind 36 Bundesgesetze und vier EU-Verordnungen, die in Zivilrechtsstreitigkeiten typischerweise
  gebraucht werden (`core/juracore/gesetze/voreinstellung.json`, gegliedert nach Gebieten).
  Eine eigene Liste im selben Format unter `<Datenverzeichnis>/gesetze.json` ersetzt sie.
- Weitere Bundesgesetze lädt man über ihre Abkürzung, wie sie in der Adresse auf
  gesetze-im-internet.de steht (z. B. `gmbhg`).
- Jede Quelldatei wird unverändert unter ihrer SHA-256-Prüfsumme im Roharchiv abgelegt.
- Ein erneuter Import legt nur dann eine neue Fassung an, wenn sich die Datei geändert hat.
  Ältere Fassungen bleiben abrufbar, damit frühere Analysen reproduzierbar sind.
- Normen sind bis auf Absatz, Satz und Nummer zerlegt; Zitate werden darauf aufgelöst.
- Die Texte von „Gesetze im Internet“ sind konsolidiert, aber nicht amtlich. Die App zeigt das bei jedem Beleg an.

### Unionsrecht aus EUR-Lex

```bash
juracore import DSGVO EuGVVO                 # lädt die HTML-Fassung von eur-lex.europa.eu
juracore import-datei DSGVO.html             # im Browser gespeicherte EUR-Lex-Seite
juracore zitat "Art. 6 Abs. 1 lit. f DSGVO"
```

- Voreingestellt (Gruppe „Unionsrecht“) sind DSGVO, EuGVVO, Rom I-VO und Rom II-VO. In
  `voreinstellung.json` ist das Kürzel dann die CELEX-Nummer (DSGVO: `32016R0679`).
- Gespeichert wird die Fassung des Amtsblatts, ohne spätere Änderungen und Berichtigungen.
  Die App nennt das bei jedem Beleg; Quelle © Europäische Union, Weiterverwendung mit
  Quellenangabe erlaubt (Beschluss 2011/833/EU).
- Zitate mit Buchstaben („lit. f“, „Buchst. f“), Unterabsatz („UAbs. 1“, wird übergangen) und
  den Schreibweisen „DS-GVO“, „Rom I“ oder „Rom-II-VO“ werden erkannt. Die Erwägungsgründe sind als eigene Einträge
  durchsuchbar.
- Liefert EUR-Lex statt des Rechtstexts eine leere Prüfseite (Bot-Abwehr, HTTP 202), holt der Kern denselben
  Text aus Cellar, dem Datenarchiv des Amtsblatts (`publications.europa.eu/resource/celex/…`). Scheitert auch das,
  die Seite im Browser öffnen, als „Webseite, nur HTML“ (Safari: „Seitenquelle“) speichern und mit `import-datei`
  einlesen; die Abkürzung wird an der CELEX-Nummer erkannt.

Die Testdaten unter `core/tests/fixtures/` sind von Hand gekürzte Auszüge im
GII-Format und keine Rechtsquelle.
