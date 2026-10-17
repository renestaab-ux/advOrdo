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

Noch nicht erkannt werden Zitate ohne „§“/„Art.“
(z. B. „Nr. 2300 VV RVG“) und inhaltlich veraltete Zitate einer noch existierenden Norm
(z. B. § 476 BGB als Beweislastumkehr, seit 2022 § 477 BGB). Word-Dateien haben nur dann
Seitenzahlen, wenn sie Seitenumbrüche enthalten; sonst gilt die Randnummer bzw. der
laufende Absatz („Abschn. 12“) als Fundstelle.

### Dokumentansicht

Ein geöffnetes Dokument lässt sich auf fünf Arten zeigen:

- **Text**: der gelesene Text mit Fundstellen und markierten Zitaten; ein Klick auf ein Normzitat zeigt den Wortlaut.
- **Original** (nur PDF): die Seiten der abgelegten Originaldatei, wie sie gedruckt aussehen. Der Kern rendert sie
  auf dem Gerät mit PDFium; nichts verlässt den Rechner. Wurde vorher ein Zitat gewählt, springt die Ansicht auf
  dessen Seite, und der Wortlaut bleibt daneben stehen.
- **Normen** und **Rechtsprechung**: wie die Reiter „Normen der Akte“ und „Rechtsprechung der Akte“, aber nur mit den
  Zitaten aus diesem Dokument. Volltexte laden und Urteile ergänzen geht auch hier.
- **Chat**: Fragen an dieses eine Dokument (siehe „Chat mit Akte und Dokument“).

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

Der Bereich **Vergleich** (oder **Abgleichen** in der Akte) stellt dieselben Angaben aus den
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
eine Nachbesserung angeboten oder abgelehnt wurde) prüft der Bereich **Analyse**.

## Analyse: lokales Sprachmodell

Der Bereich **Analyse** fasst Dokumente und die ganze Akte zusammen und sucht inhaltliche
Widersprüche, auch solche ohne Zahl oder Datum („Nachbesserung abgelehnt“ gegenüber „Nachbesserung
angeboten“). Dafür läuft ein Sprachmodell auf diesem Gerät, über Ollama oder LM Studio. Die App
spricht nur mit Adressen auf diesem Gerät (`localhost`, `127.0.0.1`); andere lehnt sie ab.

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

Im Bereich „Akte“ stellt der Reiter **Chat mit der Akte** Fragen an alle Dokumente der Akte, der
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
externen Anbieter wählen. Solange er gewählt ist, steht links unten „Modus: Externer Anbieter“, und
Analyse und Chat weisen darauf hin, dass Dokumenttexte das Gerät verlassen. Schalter aus stellt sofort
wieder auf lokal.

Die Schlüssel liegen in `ki-schluessel.json` im Datenverzeichnis der App (Linux/macOS: nur für den
Benutzer lesbar), getrennt von `ki.json`, und werden nie wieder angezeigt. Die Kommandozeile
(`ki-status`, `ki-pruefen`) arbeitet immer lokal.

## Rechtsprechung: Urteilszitate prüfen

Beim Einlesen erkennt die App auch Rechtsprechungszitate („BGH, Urteil vom 12.10.2016 – VIII ZR 103/15“,
„BAG, Urt. v. 20.2.2019 – 2 AZR 746/14“, „OLG Hamm, Beschl. v. …“, „EuGH, C-497/13“) und prüft sie gegen
das Verzeichnis der Bundesgerichte von rechtsprechung-im-internet.de (BVerfG, BGH, BVerwG, BFH, BAG, BSG,
BPatG, GmS-OGB). Das Verzeichnis lädt man einmal im Bereich **Rechtsprechung** („Verzeichnis laden“); es ist
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
Urteil gilt auch für andere Zitate der Akte mit demselben Gericht und Aktenzeichen. Der Bereich **Rechtsprechung**
zeigt alle Quellen und wie viele Entscheidungen selbst ergänzt wurden.

**Volltexte laden und Randnummern prüfen:** „Volltexte laden“ im Reiter „Rechtsprechung der Akte“ holt die belegten
Entscheidungen der Bundesgerichte von rechtsprechung-im-internet.de (Leitsatz, Tenor, Tatbestand, Gründe mit
Randnummern). Gesendet wird nur die Nummer der Entscheidung; die Datei wird unverändert unter ihrer SHA-256-Prüfsumme
im Roharchiv abgelegt (`RECHTSPRECHUNG/volltexte/`) und bleibt dort, auch wenn man das Urteil aus der Akte entfernt.
Zitiert ein Schriftsatz „…, Rn. 36“, zeigt die App, ob es diese Randnummer gibt, und springt per Klick dorthin;
„Rn. 84“ bei einer Entscheidung mit 67 Randnummern wird als Fehler markiert. Das gilt auch für selbst ergänzte Urteile,
sofern ihre Randnummern erkannt werden. „Alle Volltexte laden“ holt alle auf einmal, „Volltext laden“ beim einzelnen
Zitat nur diese Entscheidung. Die Breite der Volltext-Leiste lässt sich mit der Trennlinie verschieben (Doppelklick:
zurück auf Standard).

Ohne App:

```bash
juracore rechtsprechung-laden                       # Verzeichnis abrufen (oder --datei rii-toc.xml)
juracore urteil "BGH, Urteil vom 12.10.2016 – VIII ZR 103/15"
juracore urteil "BGH, VIII ZR 103/15" --volltext  # lädt den Volltext und zeigt Leitsatz und Randnummern
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
