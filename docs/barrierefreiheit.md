# Barrierefreiheit

Stand: 3. November 2026 · Maßstab: **WCAG 2.2, Konformitätsstufe AA**, und **EN 301 549** (Kapitel 5, 10, 11 und 12)

## Grundlage

- **WCAG 2.2** (W3C-Empfehlung vom 5. Oktober 2023), Erfolgskriterien der Stufen A und AA. Das Kriterium 4.1.1
  „Syntaxanalyse“ ist in WCAG 2.2 entfallen.
- **EN 301 549 V3.2.1 (2021-03)**, die harmonisierte Norm zur Barrierefreiheit von IKT. Für advOrdo gelten:
  - Kapitel 11 (Software): Es übernimmt die WCAG-2.1-Kriterien A/AA für Software (11.1–11.4) und ergänzt
    11.5 bis 11.8.
  - Kapitel 10 (Dokumente, die nicht Web sind): Das betrifft die Dateien, die advOrdo erzeugt (docx, pdf, xlsx).
  - Kapitel 5 (allgemeine Anforderungen) und Kapitel 12 (Dokumentation).

  Eine Fassung der EN 301 549 auf Grundlage von WCAG 2.2 ist in Arbeit. Weil WCAG 2.2 AA die Kriterien von 2.1 AA
  einschließt (außer dem entfallenen 4.1.1), deckt die Ausrichtung auf 2.2 AA beide ab.
- advOrdo ist eine Desktop-App (Tauri). Die Oberfläche läuft in der Webansicht des Systems (Windows: WebView2,
  macOS: WKWebView, Linux: WebKitGTK). Hilfsmittel wie die Windows-Sprachausgabe, NVDA oder VoiceOver lesen sie über
  die Barrierefreiheits-Schnittstelle des Systems (EN 301 549, 11.5).

## So wird geprüft

| Prüfung | Wie | Wann |
| --- | --- | --- |
| Automatisch, ohne Kern | `app/src/barrierefreiheit.oberflaeche.test.tsx`: axe-core mit den Regeln für WCAG 2.0/2.1/2.2 A und AA über alle Bereiche der Leiste, alle Reiter der Einstellungen (normal und im barrierefreien Modus) und die Toolbox | bei jedem `npm test`, also auch in der CI |
| Automatisch, Tastaturlogik | `barrierefrei.test.ts`, `lesezeichenLogik.test.ts`: Kürzel, Fokus im Dialog, Trennlinie, Verschieben ohne Ziehen | bei jedem `npm test` |
| Erzeugte PDFs | `core/tests/test_pdf_struktur.py`: Strukturbaum, Sprache, Titel, Artefakte (mit PDFium gelesen) | bei jedem `pytest` |
| Mit echtem Kern und Testakte | axe-core im Browser über alle Bereiche, eine geöffnete Akte mit allen Reitern und alle Dokumentansichten, normal und barrierefrei, hell und dunkel, einschließlich Farbkontrast | einmalig am 1. und 3. November 2026; Ergebnis: keine Befunde |
| Von Hand | Tastatur allein, Windows-Sprachausgabe bzw. NVDA, Kontrastdesign von Windows, Vergrößerung 200 % | 07.11.2026 unter Windows 11: Markieren per Tastatur (Tab), Pfeiltasten statt Ziehen, Schriftgrößen, Sprachausgabe und Kontrastdesign in Ordnung. Im Kontrastdesign sichtbare Platzhalter-Ränder an Leiste und Reitern danach behoben. Ein vollständiger Durchlauf des Ablaufs unter „Offen“ 1 steht noch aus |

Automatische Prüfungen finden erfahrungsgemäß nur einen Teil der Barrieren. Eine Konformitätserklärung setzt deshalb
die Prüfung von Hand voraus. Bis dahin beschreibt diese Seite den Stand und erklärt keine Konformität.

## Was der Nutzer einstellen kann (EN 301 549, 5.2 und 12.1.1)

Einstellungen → Allgemeines → **Barrierefreiheit**. Der Hauptschalter „Barrierefreier Modus“ schaltet alle Hilfen ein
und stellt die Schrift mindestens auf „Sehr groß“. Jede Hilfe lässt sich auch einzeln schalten. Die Einstellung gilt
je Gerät.

- **Hoher Kontrast**: Text mindestens 7 : 1, Ränder und Bedienelemente mindestens 3 : 1, Verweise unterstrichen,
  Ampeln zusätzlich als Form, die Lage einer Frist als Text.
- **Mehr Abstand und größere Klickflächen**: Zeilenabstand 1,6, Knöpfe und Felder mindestens 36 px hoch.
- **Deutlicher Tastaturrahmen**: 3 px breit in Signalfarbe, mit Saum.
- **Bewegung reduzieren**: keine Animationen, kein weiches Blättern.
- **Schriftgröße** (Darstellung): Klein bis „Doppelt“ (200 %).

Immer, ohne Schalter: „Zum Inhalt springen“, **Alt + 1 … 8** für die Bereiche der Leiste, Escape schließt Dialoge,
der Fokus bleibt im offenen Dialog, Fehlermeldungen werden vorgelesen.

Systemeinstellungen (EN 301 549, 11.7), denen advOrdo folgt: Hell/Dunkel („Systemstandard“), Kontrastdesigns von
Windows (erzwungene Farben), „Kontrast erhöhen“ von macOS (schaltet den hohen Kontrast ein), „Animationen aus“ bzw.
„Bewegung reduzieren“.

## Prüfmatrix WCAG 2.2 A/AA (zugleich EN 301 549, 11.1–11.4)

Stand: **erfüllt** = umgesetzt und automatisch bestätigt · **umgesetzt** = umgesetzt, Bestätigung von Hand offen ·
**teilweise** · **offen** · **n. a.** = nicht anwendbar.

| Nr. | Kriterium | Stufe | Stand | Umsetzung, Beleg |
| --- | --- | --- | --- | --- |
| 1.1.1 | Nicht-Text-Inhalt | A | erfüllt | Symbole `aria-hidden` neben Text; Symbolknöpfe mit `aria-label`; Seitenbilder mit `alt` („Seite n von Datei“); axe: keine Befunde |
| 1.2.1–1.2.5 | Zeitbasierte Medien | A/AA | n. a. | advOrdo spielt weder Audio noch Video ab |
| 1.3.1 | Info und Beziehungen | A | erfüllt | Überschriften, Tabellen mit `th`, Reiter `tablist/tab`, Kalenderraster `grid/row/gridcell`, Felder mit `label`; axe |
| 1.3.2 | Bedeutungstragende Reihenfolge | A | umgesetzt | DOM-Reihenfolge = Lesereihenfolge; von Hand mit Sprachausgabe bestätigen |
| 1.3.3 | Sensorische Eigenschaften | A | umgesetzt | Hinweise nennen Namen der Knöpfe, nicht nur Lage oder Farbe |
| 1.3.4 | Ausrichtung | AA | erfüllt | keine Sperre auf Hoch- oder Querformat |
| 1.3.5 | Zweck der Eingabe bestimmen | AA | erfüllt | Eigene Daten: `autocomplete` (given-name, family-name, street-address, postal-code, email …) |
| 1.4.1 | Benutzung von Farbe | A | erfüllt | Status mit Text, Fristlage als Text, Ampeln mit Text (bei hohem Kontrast zusätzlich als Form), Verweise bei hohem Kontrast unterstrichen |
| 1.4.2 | Audio-Steuerung | A | n. a. | kein Ton |
| 1.4.3 | Kontrast (Minimum) | AA | erfüllt | axe mit echtem Kern: keine Befunde, normal und barrierefrei, hell und dunkel; Warnfarbe hell auf #774d00 angehoben |
| 1.4.4 | Textgröße ändern | AA | umgesetzt | Schriftgröße bis „Doppelt“ (200 %) über die Fenstervergrößerung |
| 1.4.5 | Bilder von Text | AA | erfüllt | Text ist Text; Ausnahme: Scans eingelesener Akten (Original des Nutzers), deren Text die Texterkennung liefert |
| 1.4.10 | Umbruch (Reflow) | AA | umgesetzt | Bis 760 CSS-Pixel Breite (z. B. halbes Fenster bei „Doppelt“) ist die Leiste eingeklappt, Kopfband und Reiter brechen um, die Akte steht untereinander (Filter, Liste, Dokument). Die Aktenliste rollt in ihrem eigenen Rahmen seitlich, wie 1.4.10 für Datentabellen erlaubt. Mit Testakte bei 640 × 400 geprüft (08.11.2026): kein Bereich und kein Reiter der Akte rollt waagerecht |
| 1.4.11 | Nicht-Text-Kontrast | AA | erfüllt | Ränder von Feldern und Knöpfen; bei hohem Kontrast mindestens 3 : 1 |
| 1.4.12 | Textabstand | AA | umgesetzt | keine festen Höhen für Text; „Mehr Abstand“ setzt 1,6 Zeilenabstand |
| 1.4.13 | Inhalt bei Hover oder Fokus | AA | umgesetzt | Hinweise sind `title`-Tooltips des Systems; die Vorschau einer Anmerkung schließt mit Escape |
| 2.1.1 | Tastatur | A | umgesetzt | alle Funktionen per Tastatur; Trennlinien mit Pfeiltasten; Reiterleisten mit Pfeiltasten, Pos1 und Ende (08.11.2026); Verschieben von Lesezeichen und Ordnern mit Pfeil hoch/runter. Markieren im Text-Modus nur mit der Tastatur: Der Textrahmen ist per Tab erreichbar, direkt mit Eingabe oder Pfeil runter auf dem Reiter „Text“, und zeigt eine Einfügemarke; Pfeiltasten bewegen sie, Umschalt + Pfeil markiert (mit Strg wortweise bzw. absatzweise), Strg + A wählt den ganzen Text, Tab oder Umschalt + F10 öffnet das Markiermenü, darin Pfeil links/rechts und Escape; danach kehrt der Fokus an die Stelle im Text zurück (08.11.2026). Kommentar-Fenster nimmt beim Öffnen den Fokus an, Escape schließt es (08.11.2026). Im Original (PDF-Bild) ist jede Seite per Tab erreichbar: Pfeiltasten bewegen eine Marke wortweise (hoch/runter zeilenweise, Pos1/Ende an Zeilenanfang/-ende, mit Strg an Seitenanfang/-ende), Umschalt + Pfeil markiert, Strg + A wählt die Seite, Tab oder Umschalt + F10 öffnet das Markiermenü, Escape hebt die Auswahl auf; das gewählte Wort bzw. die Auswahl wird angesagt (09.11.2026) |
| 2.1.2 | Keine Tastaturfalle | A | umgesetzt | Dialoge halten den Fokus, Escape gibt ihn frei |
| 2.1.4 | Tastaturkürzel mit Zeichen | A | erfüllt | Kürzel nur mit Alt bzw. Strg/⌘, keine Einzelzeichen |
| 2.2.1 | Zeitbegrenzungen anpassbar | A | erfüllt | keine Zeitgrenzen |
| 2.2.2 | Pausieren, Beenden, Ausblenden | A | erfüllt | Warteanzeige mit „Abbrechen“; Bewegung abschaltbar |
| 2.3.1 | Dreimaliges Blitzen | A | erfüllt | nichts blinkt |
| 2.4.1 | Blöcke umgehen | A | erfüllt | „Zum Inhalt springen“, Hauptbereich `main#inhalt`, Leiste `nav` |
| 2.4.2 | Seite mit Titel | A | erfüllt | Fenstertitel „advOrdo“, Bereiche mit `h1` |
| 2.4.3 | Fokus-Reihenfolge | A | umgesetzt | DOM-Reihenfolge; Fokus kehrt nach Dialogen zurück; von Hand bestätigen |
| 2.4.4 | Linkzweck (im Kontext) | A | erfüllt | Verweise tragen Dateiname, Fundstelle oder Ziel |
| 2.4.5 | Verschiedene Wege | AA | erfüllt | Leiste, Startseite, Suche, „Zuletzt geöffnet“ |
| 2.4.6 | Überschriften und Beschriftungen | AA | erfüllt | beschreibende Überschriften und Feldnamen |
| 2.4.7 | Fokus sichtbar | AA | erfüllt | Fokusrahmen immer; im Modus 3 px Signalfarbe mit Saum |
| 2.4.11 | Fokus nicht verdeckt (Minimum) | AA | umgesetzt | `scroll-margin` hält Abstand zu klebenden Kopfzeilen und zur Warteanzeige |
| 2.5.1 | Zeigergesten | A | erfüllt | keine Mehrfinger- oder Pfadgesten |
| 2.5.2 | Zeigerabbruch | A | erfüllt | Aktionen beim Loslassen (Klick) |
| 2.5.3 | Beschriftung im Namen | A | erfüllt | `aria-label` beginnt mit der sichtbaren Beschriftung bzw. enthält sie |
| 2.5.4 | Bewegungsaktivierung | A | n. a. | keine Bewegungssteuerung |
| 2.5.7 | Ziehbewegungen | AA | erfüllt | Trennlinien: Klick wechselt Standard/breit, Doppelklick setzt zurück; Lesezeichen und Ordner: Knöpfe ▲ ▼ und Auswahl „In Ordner verschieben“ |
| 2.5.8 | Zielgröße (Minimum) | AA | erfüllt | mindestens 24 × 24 px oder genug Abstand (axe); Trennlinie mit 24 px Greiffläche |
| 3.1.1 | Sprache der Seite | A | erfüllt | `lang="de"` |
| 3.1.2 | Sprache von Teilen | AA | umgesetzt | Normtexte aus EUR-Lex werden auf Deutsch geladen. Die Textansicht erkennt die Sprache eines Dokuments und einzelner Absätze (Deutsch, Englisch, Französisch, Italienisch, Spanisch, Niederländisch, Portugiesisch; Zählung häufiger Wörter, ohne Netz) und setzt `lang`; die Kopfzeile nennt „Sprache … (erkannt)“. Kurze oder gemischte Absätze bleiben in der Sprache des Dokuments (09.11.2026) |
| 3.2.1 | Bei Fokus | A | erfüllt | Fokus löst nichts aus |
| 3.2.2 | Bei Eingabe | A | erfüllt | Auswahlen wirken ohne Seitenwechsel; Einstellungen gelten sofort, wie angekündigt |
| 3.2.3 | Konsistente Navigation | AA | erfüllt | eine Leiste, immer gleich |
| 3.2.4 | Konsistente Erkennung | AA | erfüllt | gleiche Symbole und Namen für gleiche Funktionen |
| 3.2.6 | Konsistente Hilfe | A | n. a. | advOrdo bietet keine Hilfefunktion auf mehreren Seiten an. Kommt eine hinzu, gehört sie an dieselbe Stelle |
| 3.3.1 | Fehlererkennung | A | erfüllt | Meldungen als Text, `role="alert"` |
| 3.3.2 | Beschriftungen oder Anweisungen | A | erfüllt | Felder beschriftet, Beispiele als Platzhalter und Hinweistext |
| 3.3.3 | Fehlerempfehlung | AA | umgesetzt | Meldungen nennen die Ursache (z. B. Aktenzeichen-Schema); nicht alle Meldungen des Kerns schlagen eine Lösung vor |
| 3.3.4 | Fehlervermeidung (rechtlich, finanziell) | AA | umgesetzt | Löschen von Akten und Dokumenten mit Rückfrage; Kostennote und Schriftstücke als Entwurf zum Prüfen |
| 3.3.7 | Redundante Eingabe | A | umgesetzt | „Akte aus Dokument“ und Eigene Daten füllen Angaben vor; im Ablauf wird nichts doppelt abgefragt |
| 3.3.8 | Barrierefreie Authentifizierung (Minimum) | AA | erfüllt | keine Anmeldung; API-Schlüssel für externe KI lassen sich einfügen |
| 4.1.2 | Name, Rolle, Wert | A | erfüllt | native Elemente; Schalter mit `aria-pressed`, Reiter mit `aria-selected`, Trennlinie mit `aria-valuenow`; axe |
| 4.1.3 | Statusmeldungen | AA | erfüllt | `role="status"` für Laden und Warteanzeige (nur Beginn und Ende), `role="alert"` für Fehler |

## EN 301 549, Anforderungen über WCAG hinaus

| Abschnitt | Anforderung | Stand | Umsetzung |
| --- | --- | --- | --- |
| 5.2 | Barrierefreiheitsfunktionen aktivieren | erfüllt | Einstellungen → Allgemeines → Barrierefreiheit, selbst barrierefrei bedienbar |
| 5.3 | Biometrie | n. a. | keine |
| 5.4 | Erhalt von Barrierefreiheitsinformationen bei Konvertierung | erfüllt | Export nach docx mit Überschriftenformaten, nach PDF mit Strukturbaum (siehe 10) |
| 5.5–5.8 | Bedienteile, Tastenwiederholung, Doppelanschlag | n. a. | keine eigene Hardware; Tastatur des Systems |
| 5.9 | Gleichzeitige Benutzeraktionen | erfüllt | Alt + Ziffer ist nur ein Kürzel; jede Funktion geht auch mit einem Klick |
| 10.x | Erzeugte Dokumente | teilweise | **Word (docx):** Sprache de-DE, Titel in den Eigenschaften, echte Formatvorlagen „Title“ und „heading 1–3“. **PDF:** getaggt (`/MarkInfo`, Strukturbaum mit H1–H3 und P, Sprache, Titel, Fußzeile und Linien als Artefakt). Seit 07.11.2026 zusätzlich mit Kennung PDF/A-2a und PDF/UA-1: eingebettete Schrift (Liberation Sans, Teilmenge), XMP-Metadaten mit Titel und Erweiterungsschema für `pdfuaid`, Ausgabebedingung mit sRGB-Profil, Dateikennung. Am 07.11.2026 mit einem Prüfdienst bestätigt: Anmerkungen-Export „erfüllt PDF/A-2a“ und „erfüllt PDF/UA-1“ (die Fassung vorher scheiterte an PDF/A-2b). **Offen:** Excel ohne eigene Prüfung; die „PDF-Kopie mit Markierungen“ ändert das Original des Nutzers und erbt dessen Struktur |
| 11.5 | Zusammenarbeit mit Hilfsmitteln | umgesetzt | Webansicht des Systems stellt die Oberfläche über UI Automation (Windows), NSAccessibility (macOS), AT-SPI (Linux) bereit; von Hand mit NVDA/Sprachausgabe bestätigen |
| 11.6 | Dokumentierte Hilfsmittelnutzung | n. a. | advOrdo ist selbst kein Hilfsmittel |
| 11.7 | Benutzereinstellungen | erfüllt | folgt Hell/Dunkel, Kontrastdesign, „Kontrast erhöhen“, „Bewegung reduzieren“ des Systems. Die Textgröße des Systems wirkt je nach Webansicht; advOrdo hat zusätzlich eine eigene Schriftgröße |
| 11.8 | Autorenwerkzeuge | teilweise | Schriftstücke (Brief, Schriftsatz, Kostennote) entstehen als docx mit Sprache und Formatvorlagen. **Offen:** keine Prüfhilfe, die beim Bearbeiten auf Barrieren hinweist (11.8.4) |
| 12.1.1 | Beschreibung der Barrierefreiheitsfunktionen | erfüllt | diese Seite und die Erklärungen in Einstellungen → Allgemeines |
| 12.1.2 | Barrierefreie Dokumentation | umgesetzt | Dokumentation als Markdown (Text mit Überschriften) |
| 12.2 | Support-Dienste | n. a. | kein Support-Dienst |

## Offen

1. **Prüfung von Hand** (Voraussetzung für eine Konformitätserklärung): Ablauf „Akte anlegen → Dokumente einlesen →
   Dokument lesen → Frist eintragen → Schriftstück erzeugen“ allein mit der Tastatur und mit NVDA bzw. der Windows-
   Sprachausgabe; dasselbe im Kontrastdesign von Windows und bei 200 %.
2. ~~**Markieren und Kommentieren per Tastatur** (2.1.1) im Original (PDF-Bild)~~: erledigt am 09.11.2026.
3. ~~**Sprache von Teilen** (3.1.2) für fremdsprachige Dokumente in einer Akte~~: erledigt am 09.11.2026.
4. ~~**Reflow** (1.4.10) der dreispaltigen Akte bei 200 %~~: umgesetzt am 08.11.2026, Bestätigung von Hand offen.
