"""KI-Leistungstest der Diagnose: Geschwindigkeit und ein kleiner Satz Prüffragen mit bekannter Antwort.

Der Test schickt nur feste, für diesen Zweck geschriebene Texte an das gewählte Modell, nie Akteninhalte. Die
Antworten wertet advOrdo selbst nach festen Regeln aus (Datum, Auswahl, wörtliches Zitat); eine zweite KI als
Richter gibt es nicht. Jede erwartete Antwort nennt ihre Fundstelle. Ein Dutzend Fragen ist eine Stichprobe und
kein Benchmark: Es zeigt typische Schwächen (Fristen, Zuständigkeit, erfundene Normen, Zitate), mehr nicht.

Fundstellen geprüft am 13.11.2026 auf gesetze-im-internet.de. Fristen aus dem Jahr 2026; in den genannten
Zeiträumen liegt kein bundesweiter Feiertag.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .. import db
from ..gesetze import wissensbasis
from ..rechner import fristen
from . import belege
from .anbieter import KiFehler
from .wissen import _dauer

AUFGABE = "leistungstest"
STAND_FUNDSTELLEN = "13.11.2026"

SYSTEM = ("Du bist ein juristischer Assistent für deutsches Recht. Beantworte die Frage knapp und genau. Antworte "
          "ausschließlich mit einem JSON-Objekt nach dem vorgegebenen Schema.")

# --------------------------------------------------------------------------- Geschwindigkeit

_KURZ_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}

# Alle Freitextfelder haben Längengrenzen: Ein lokales Modell, das sich in einer Wiederholung verfängt, schreibt sonst
# bis zur Antwortgrenze weiter und überschreitet die Wartezeit (wie beim Chat, siehe ki.chat). Externe Anbieter
# bekommen die Grenzen nicht (anbieter._streng).

# Erfundener Sachverhalt für die längere Anfrage; ähnelt einer echten Aufgabe (Zusammenfassung).
SACHVERHALT = (
    "Die Klägerin, die Muster Bau GmbH, verlangt von der Beklagten, Frau Erika Beispiel, Restwerklohn in Höhe von "
    "18.400 Euro für den Umbau eines Einfamilienhauses in Musterstadt. Die Parteien schlossen am 3. Februar 2026 einen "
    "Bauvertrag über die Sanierung des Bades, den Einbau neuer Fenster und die Dämmung des Dachgeschosses zu einem "
    "Pauschalpreis von 62.000 Euro. Die Beklagte zahlte drei Abschläge über insgesamt 43.600 Euro. Nach Fertigstellung "
    "am 28. Mai 2026 forderte die Klägerin zur Abnahme auf. Die Beklagte verweigerte die Abnahme mit Schreiben vom "
    "4. Juni 2026 und rügte, zwei Fenster im Obergeschoss seien undicht, im Bad fehle das Gefälle zum Bodenablauf und "
    "die Dämmung sei an der Giebelwand unvollständig. Die Klägerin hält die Mängel für unerheblich, bestreitet das "
    "fehlende Gefälle und verweist auf ein Abnahmeprotokoll ihres Bauleiters, das die Beklagte nicht unterschrieben "
    "hat. Ein von der Beklagten beauftragter Sachverständiger bestätigte am 20. Juni 2026 die Undichtigkeit der "
    "Fenster und bezifferte die Kosten der Nachbesserung auf rund 2.900 Euro; zum Gefälle im Bad äußerte er sich "
    "nicht. Die "
    "Beklagte erklärte daraufhin die Aufrechnung mit einem Vorschuss für die Mängelbeseitigung und behielt den Rest "
    "des Werklohns zurück."
)
_LANG_SCHEMA = {"type": "object", "properties": {"saetze": {"type": "array", "maxItems": 8,
                                                                 "items": {"type": "string", "maxLength": 400}}},
                "required": ["saetze"]}


# --------------------------------------------------------------------------- Prüffragen

@dataclass(frozen=True)
class Frage:
    id: str
    bereich: str
    frage: str  # an das Modell
    schema: dict
    erwartet: str  # für Menschen
    fundstelle: str
    pruefe: Callable[[dict], tuple[bool, str]]  # (richtig, Antwort für die Anzeige)


_DATUM_SCHEMA = {"type": "object", "properties": {
    "datum": {"type": "string", "maxLength": 40, "description": "Letzter Tag der Frist im Format JJJJ-MM-TT"},
    "begruendung": {"type": "string", "maxLength": 400}}, "required": ["datum", "begruendung"]}


def lies_datum(text: object) -> str | None:
    """JJJJ-MM-TT aus einer Antwort, auch wenn das Modell TT.MM.JJJJ schreibt."""
    s = str(text or "")
    if m := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
        j, mo, t = m.groups()
    elif m := re.search(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})", s):
        t, mo, j = m.groups()
    else:
        return None
    return f"{int(j):04d}-{int(mo):02d}-{int(t):02d}"


def _datum_text(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


FRIST_SCHLUSS = " Nenne den letzten Tag der Frist."


def _frist(id_: str, frage: str, soll: str, fundstelle: str) -> Frage:
    def pruefe(a: dict) -> tuple[bool, str]:
        ist = lies_datum(a.get("datum"))
        return ist == soll, _datum_text(ist) if ist else f"kein Datum ({str(a.get('datum') or '')[:40]})"
    return Frage(id_, "Fristen", frage + FRIST_SCHLUSS, _DATUM_SCHEMA,
                 f"Fristende {_datum_text(soll)}", fundstelle, pruefe)


GERICHTE = ["Amtsgericht", "Landgericht", "Oberlandesgericht", "Arbeitsgericht", "Verwaltungsgericht",
            "Sozialgericht", "Finanzgericht"]
_GERICHT_SCHEMA = {"type": "object", "properties": {
    "gericht": {"type": "string", "enum": GERICHTE}, "norm": {"type": "string", "maxLength": 200}},
    "required": ["gericht", "norm"]}


def _gericht(id_: str, frage: str, soll: str, fundstelle: str) -> Frage:
    def pruefe(a: dict) -> tuple[bool, str]:
        ist = str(a.get("gericht") or "").strip()
        return ist.casefold() == soll.casefold(), ist or "keine Angabe"
    return Frage(id_, "Zuständigkeit", frage + " Welches Gericht ist im ersten Rechtszug zuständig?",
                 _GERICHT_SCHEMA, soll, fundstelle, pruefe)


_NORM_SCHEMA = {"type": "object", "properties": {
    "existiert": {"type": "boolean"},
    "inhalt": {"type": "string", "maxLength": 300, "description": "Kurz, was die Norm regelt"}},
    "required": ["existiert", "inhalt"]}


_VERNEINT = re.compile(r"nicht vorhanden|existiert nicht|gibt es nicht|nicht existent|keinen? (§|Absatz)", re.I)


def _norm(id_: str, frage: str, soll: bool, erwartet: str, fundstelle: str) -> Frage:
    def pruefe(a: dict) -> tuple[bool, str]:
        ist = a.get("existiert")
        if not isinstance(ist, bool):
            return False, "keine Angabe"
        inhalt = str(a.get("inhalt") or "").strip()
        if ist and _VERNEINT.search(inhalt):
            # Feld und Text widersprechen sich; maßgeblich ist das Feld, mit dem advOrdo weiterarbeiten würde.
            return ist == soll, f"widersprüchlich: Feld „existiert“, Text sagt „{inhalt[:120]}“"
        return ist == soll, ("existiert" if ist else "existiert nicht") + (f": {inhalt[:120]}" if ist and inhalt
                                                                            else "")
    return Frage(id_, "Erfundene Normen", frage, _NORM_SCHEMA, erwartet, fundstelle, pruefe)


THEMEN_626 = ["Fristlose Kündigung aus wichtigem Grund", "Minderung der Miete", "Verjährung von Mängelansprüchen",
              "Rücktritt vom Kaufvertrag"]
_THEMA_SCHEMA = {"type": "object", "properties": {
    "existiert": {"type": "boolean"}, "thema": {"type": "string", "enum": THEMEN_626}},
    "required": ["existiert", "thema"]}


def _pruefe_626(a: dict) -> tuple[bool, str]:
    thema = str(a.get("thema") or "") or "kein Thema"
    existiert = a.get("existiert")
    if existiert is not True:
        # Etwa „existiert nicht“, aber trotzdem ein Thema genannt: Das zeigt die Anzeige ausdrücklich.
        angabe = "existiert nicht" if existiert is False else f"„existiert“ ohne gültige Angabe ({existiert!r})"
        return False, f"{angabe}, Thema: {thema}"
    return thema == THEMEN_626[0], f"existiert: {thema}"


# Erfundenes Schreiben für die Fragen zur Zitattreue. Ein Kaufpreis kommt darin absichtlich nicht vor.
SCHREIBEN = (
    "Sehr geehrte Damen und Herren, wir nehmen Bezug auf den Kaufvertrag über den Gabelstapler Typ GX 25. Das Gerät "
    "wurde unserer Mandantin am 12. Mai 2026 in Musterstadt übergeben. Bereits beim ersten Einsatz am 18. Mai 2026 "
    "fiel die Hydraulik aus, sodass keine Lasten mehr gehoben werden konnten. Wir fordern Sie auf, den Mangel bis zum "
    "15. Juni 2026 zu beseitigen. Mit freundlichen Grüßen"
)
_ZITAT_SCHEMA = {"type": "object", "properties": {"zitat": {"type": "string", "maxLength": 400}},
                 "required": ["zitat"]}
_NICHT_SCHEMA = {"type": "object", "properties": {
    "im_text": {"type": "boolean"},
    "zitat": {"type": "string", "maxLength": 400, "description": "Wörtliches Zitat oder leer"}},
    "required": ["im_text", "zitat"]}


def _woertlich(zitat: str) -> bool:
    gesucht = belege.normalisiere(zitat)[0].strip(" .\"„“")
    return len(gesucht) >= 15 and gesucht in belege.normalisiere(SCHREIBEN)[0]


def _pruefe_zitat(a: dict) -> tuple[bool, str]:
    zitat = str(a.get("zitat") or "").strip()
    if not _woertlich(zitat):
        return False, f"nicht wörtlich im Text: „{zitat[:120]}“" if zitat else "kein Zitat"
    return "12. Mai 2026" in zitat, f"„{zitat[:160]}“"


def _pruefe_nicht_im_text(a: dict) -> tuple[bool, str]:
    if a.get("im_text") is False:
        return True, "steht nicht im Text"
    zitat = str(a.get("zitat") or "").strip()
    return False, f"behauptet, es stehe im Text: „{zitat[:120]}“" if zitat else "behauptet, es stehe im Text"


GII = f"gesetze-im-internet.de, Stand {STAND_FUNDSTELLEN}"

FRAGEN: list[Frage] = [
    _frist("berufung_wochenende",
           "Ein Urteil des Landgerichts in vollständiger Form wurde am Mittwoch, 12.08.2026, zugestellt. Bis wann "
           "läuft die Berufungsfrist?", "2026-09-14",
           f"§ 517 ZPO (ein Monat ab Zustellung), § 222 Abs. 1 ZPO i. V. m. § 188 Abs. 2 BGB; Fristende fiele auf "
           f"Samstag, 12.09.2026, daher § 222 Abs. 2 ZPO: Montag; {GII}"),
    _frist("berufung_monatsende",
           "Ein Urteil des Landgerichts in vollständiger Form wurde am Dienstag, 31.03.2026, zugestellt. Bis wann "
           "läuft die Berufungsfrist?", "2026-04-30",
           f"§ 517 ZPO, § 222 Abs. 1 ZPO i. V. m. § 188 Abs. 2 und 3 BGB (der April hat keinen 31.); {GII}"),
    _frist("berufung_strafrecht",
           "Ein Urteil des Amtsgerichts in einer Strafsache wurde am Dienstag, 03.11.2026, in Anwesenheit des "
           "Angeklagten verkündet. Bis wann kann er Berufung einlegen?", "2026-11-10",
           f"§ 314 Abs. 1 StPO (eine Woche nach Verkündung), § 43 Abs. 1 StPO; {GII}"),
    _frist("kschg",
           "Einer Arbeitnehmerin ist die schriftliche Kündigung am Freitag, 02.10.2026, zugegangen. Bis wann muss "
           "sie Kündigungsschutzklage erheben?", "2026-10-23",
           f"§ 4 Satz 1 KSchG (drei Wochen nach Zugang), § 188 Abs. 2 BGB; {GII}"),
    _frist("einspruch_vu",
           "Ein Versäumnisurteil des Amtsgerichts wurde dem Beklagten am Freitag, 20.11.2026, zugestellt. Bis wann "
           "kann er Einspruch einlegen?", "2026-12-04",
           f"§ 339 Abs. 1 ZPO (zwei Wochen ab Zustellung), § 222 Abs. 1 ZPO i. V. m. § 188 Abs. 2 BGB; {GII}"),
    _frist("verjaehrung",
           "Ein Kaufpreisanspruch ist am 15.06.2023 entstanden; der Gläubiger kannte Anspruch und Schuldner von "
           "Anfang an. Es gilt die regelmäßige Verjährung, ohne Hemmung. Mit Ablauf welchen Tages verjährt er?",
           "2026-12-31", f"§ 195 BGB (drei Jahre), § 199 Abs. 1 BGB (Beginn mit Schluss des Jahres 2023); {GII}"),
    _gericht("raeumung",
             "Ein Vermieter will den Mieter einer Wohnung auf Räumung verklagen; der Streitwert beträgt 30.000 Euro.",
             "Amtsgericht",
             f"§ 23 Nr. 2 Buchst. a GVG (Wohnraummiete ohne Rücksicht auf den Streitwert, ausschließlich), "
             f"§ 29a Abs. 1 ZPO; {GII}"),
    _gericht("zahlung",
             "Eine GmbH verklagt einen Kunden auf Zahlung des Kaufpreises von 50.000 Euro für gelieferte Maschinen.",
             "Landgericht", f"§ 71 Abs. 1 GVG, § 23 Nr. 1 GVG (Amtsgericht nur bis 10.000 Euro); {GII}"),
    _gericht("kuendigungsschutz", "Ein Arbeitnehmer will gegen die Kündigung seines Arbeitsverhältnisses klagen.",
             "Arbeitsgericht", f"§ 2 Abs. 1 Nr. 3 Buchst. b ArbGG, § 4 Satz 1 KSchG; {GII}"),
    _gericht("baugenehmigung",
             "Eine Nachbarin will die Baugenehmigung anfechten, die die Bauaufsichtsbehörde für das Nachbargrundstück "
             "erteilt hat.", "Verwaltungsgericht", f"§ 40 Abs. 1 Satz 1 VwGO; {GII}"),
    _norm("bgb_312z", "Gibt es im BGB einen § 312z? Wenn ja, was regelt er?", False, "existiert nicht",
          f"Inhaltsverzeichnis des BGB: nach § 312 folgen §§ 312a bis 312m, dann § 313; {GII}"),
    _norm("bgb_823_4", "Gibt es einen § 823 Abs. 4 BGB? Wenn ja, was regelt er?", False, "existiert nicht",
          f"§ 823 BGB hat zwei Absätze; {GII}"),
    _norm("mandaktg",
          "Gibt es im deutschen Bundesrecht ein „Gesetz über elektronische Mandatsakten (MandAktG)“? Wenn ja, was "
          "regelt es?", False, "existiert nicht",
          "Name und Abkürzung sind für diesen Test erfunden; ein solches Gesetz steht nicht in der Sammlung des "
          f"Bundesrechts ({GII})"),
    Frage("bgb_626", "Erfundene Normen",
          "Gibt es einen § 626 BGB? Wenn ja, welches Thema regelt er?", _THEMA_SCHEMA,
          f"existiert: {THEMEN_626[0]} (Gegenprobe zu den erfundenen Normen)",
          f"§ 626 BGB „Fristlose Kündigung aus wichtigem Grund“; {GII}", _pruefe_626),
    Frage("zitat", "Zitattreue",
          f"Text:\n{SCHREIBEN}\n\nZitiere wörtlich den Satz aus dem Text, der den Tag der Übergabe nennt.",
          _ZITAT_SCHEMA, "wörtliches Zitat mit „12. Mai 2026“",
          "Der Satz steht im erfundenen Testschreiben; advOrdo vergleicht das Zitat Zeichen für Zeichen",
          _pruefe_zitat),
    Frage("nicht_im_text", "Zitattreue",
          f"Text:\n{SCHREIBEN}\n\nNennt der Text einen Kaufpreis? Wenn ja, zitiere die Stelle wörtlich.",
          _NICHT_SCHEMA, "Kein Kaufpreis im Text",
          "Das erfundene Testschreiben nennt absichtlich keinen Kaufpreis", _pruefe_nicht_im_text),
]


# --------------------------------------------------------------------------- Durchgang „mit Gesetzen“

# Normen, die im zweiten Durchgang aus der Wissensbasis mitgehen: (Gesetz, Nummer, Fehlen melden). Bei den Fragen
# nach erfundenen Normen gehört das Fehlen zur Auskunft der Sammlung („nicht enthalten“); bei echten Normen, deren
# Gesetz nur nicht geladen ist, würde dieselbe Auskunft das Modell in die Irre führen, sie fehlen dann stillschweigend.
NORMEN: dict[str, list[tuple[str, str | None, bool]]] = {
    "berufung_wochenende": [("ZPO", "517", False), ("ZPO", "222", False), ("BGB", "187", False),
                            ("BGB", "188", False)],
    "berufung_monatsende": [("ZPO", "517", False), ("ZPO", "222", False), ("BGB", "187", False),
                            ("BGB", "188", False)],
    "berufung_strafrecht": [("StPO", "314", False), ("StPO", "43", False)],
    "kschg": [("KSchG", "4", False), ("BGB", "187", False), ("BGB", "188", False)],
    "einspruch_vu": [("ZPO", "339", False), ("ZPO", "222", False), ("BGB", "187", False), ("BGB", "188", False)],
    "verjaehrung": [("BGB", "195", False), ("BGB", "199", False)],
    "raeumung": [("GVG", "23", False), ("ZPO", "29a", False)],
    "zahlung": [("GVG", "23", False), ("GVG", "71", False)],
    "kuendigungsschutz": [("ArbGG", "2", False), ("KSchG", "4", False)],
    "baugenehmigung": [("VwGO", "40", False)],
    "bgb_312z": [("BGB", "312z", True)],
    "bgb_823_4": [("BGB", "823", False)],
    "mandaktg": [("MandAktG", None, True)],
    "bgb_626": [("BGB", "626", False)],
}
NORM_ZEICHEN = 2500  # je Norm; § 2 ArbGG etwa ist lang

SYSTEM_GESETZE = (SYSTEM + " Vor der Frage steht ein Auszug aus der Gesetzessammlung der App im Wortlaut der genannten "
                  "Fassung. Stütze dich darauf, soweit die Normen einschlägig sind.")


def _normtext(n: dict) -> str:
    f = n["fassung"]
    stand = "; ".join(f.get("stand") or []) or f"abgerufen {str(f.get('abgerufen_am', ''))[:10]}"
    text = "\n".join(" ".join(a["text"].split()) for a in n["absaetze"])
    if len(text) > NORM_ZEICHEN:
        text = text[:NORM_ZEICHEN].rsplit(" ", 1)[0] + " …"
    kopf = f"{n['bezeichnung']} {n['gesetz']}" + (f" – {n['titel']}" if n.get("titel") else "")
    return f"{kopf} (Fassung: {stand})\n{text}"


# --------------------------------------------------------------------------- Fristenrechner

# Wie im Chat mit „Rechner (Zinsen, Fristen)“ (ki.wissen): Das Modell nennt nur Bezugstag und Dauer, das Datum rechnet
# der Fristenrechner der App. Geprüft wird damit, ob das Modell die Frist richtig erkennt, nicht seine Datumsrechnung.
RECHNER_SCHLUSS = (" Rechne das Fristende nicht selbst. Nenne den Tag des Ereignisses oder Zeitpunkts, an den die "
                   "Frist anknüpft, und die Dauer der Frist.")
SYSTEM_RECHNER = (" Fristen rechnet der Fristenrechner der App nach §§ 187, 188, 193 BGB einschließlich Wochenenden "
                  "und Feiertagen; du lieferst nur seine Eingaben.")
_RECHNER_SCHEMA = {"type": "object", "properties": {
    "bezugstag": {"type": "string", "maxLength": 40, "description": "TT.MM.JJJJ"},
    "dauer": {"type": "string", "maxLength": 40, "description": "z. B. \"2 Wochen\", \"1 Monat\", \"3 Jahre\""},
    "begruendung": {"type": "string", "maxLength": 400}}, "required": ["bezugstag", "dauer", "begruendung"]}


def mit_fristenrechner(f: Frage, antwort: dict) -> tuple[bool, str]:
    """Rechnet aus Bezugstag und Dauer des Modells das Fristende (Fristenrechner der App) und prüft es."""
    tag = lies_datum(antwort.get("bezugstag"))
    dauer = _dauer(str(antwort.get("dauer") or ""))
    eingabe = f"Bezugstag {_datum_text(tag) if tag else str(antwort.get('bezugstag') or '–')[:40]}, " \
              f"Dauer {str(antwort.get('dauer') or '–')[:40]}"
    if tag is None or dauer is None:
        return False, f"keine verwertbaren Angaben für den Fristenrechner ({eingabe})"
    try:
        ende = fristen.berechne(date.fromisoformat(tag), dauer[0], dauer[1])["ende"]
    except ValueError as e:
        return False, f"Fristenrechner: {e} ({eingabe})"
    richtig, _ = f.pruefe({"datum": ende})
    return richtig, f"{_datum_text(ende)} (Fristenrechner aus: {eingabe})"


def gesetze_zur_frage(wb: sqlite3.Connection, frage_id: str) -> tuple[str, list[str], list[str]]:
    """Auszug aus der Wissensbasis zur Frage; dazu die mitgegebenen und die fehlenden Normen (für die Anzeige)."""
    teile, mit, fehlend = [], [], []
    for gesetz, nummer, melden in NORMEN.get(frage_id, []):
        bezeichnung = f"§ {nummer} {gesetz}" if nummer else gesetz
        if db.aktuelle_fassung(wb, gesetz) is None:
            if melden:
                teile.append(f"{gesetz}: Ein Gesetz mit dieser Abkürzung ist in der Gesetzessammlung der App nicht "
                             "enthalten.")
                mit.append(f"{bezeichnung} (nicht enthalten)")
            else:
                fehlend.append(gesetz)
            continue
        n = wissensbasis.norm(wb, gesetz, nummer, typ="paragraph") if nummer else None
        if n is None or n["weggefallen"]:
            if melden:
                teile.append(f"{bezeichnung}: In der Gesetzessammlung der App ({gesetz}) nicht vorhanden.")
                mit.append(f"{bezeichnung} (nicht vorhanden)")
            else:
                fehlend.append(bezeichnung)
            continue
        teile.append(_normtext(n))
        mit.append(bezeichnung)
    return "\n\n".join(teile), mit, fehlend


# --------------------------------------------------------------------------- Ablauf

class _Messung:
    def __init__(self, modell: Any):
        self.modell = modell
        self.json_fehler = 0
        self.denkphase = 0

    def frage(self, nutzer: str, schema: dict, system: str = SYSTEM) -> tuple[dict | None, float, dict | None,
                                                                              str | None]:
        """Antwort, Dauer in Sekunden, gemeldete Token und Fehler (ohne Ausnahme bei JSON-Fehlern)."""
        try:
            self.modell.verbrauch = None
            self.modell.denkphase = 0
        except AttributeError:
            pass
        beginn = time.monotonic()
        try:
            antwort: dict | None = self.modell.chat(system, nutzer, schema)
            fehler = None
        except KiFehler as f:
            text = str(f)
            if "JSON" not in text and "leer" not in text:
                raise  # nicht erreichbar, Schlüssel ungültig usw.: dann bricht der Test ab
            antwort, fehler = None, text
            self.json_fehler += 1
        dauer = time.monotonic() - beginn
        self.denkphase = max(self.denkphase, int(getattr(self.modell, "denkphase", 0) or 0))
        return antwort, dauer, getattr(self.modell, "verbrauch", None), fehler


def _sekunden(s: float) -> str:
    return f"{s:.1f} s".replace(".", ",")


def _wert(titel: str, wert: str, stand: str, hinweis: str | None = None) -> dict:
    return {"titel": titel, "wert": wert, "stand": stand, "hinweis": hinweis}


def geschwindigkeit(m: _Messung, auftrag: Any) -> list[dict]:
    werte = []
    auftrag.melde("Erste Anfrage (das Modell wird ggf. geladen) …", 1, 3 + len(FRAGEN))
    _, erste, _, _ = m.frage('Gib {"ok": true} zurück.', _KURZ_SCHEMA, "Antworte nur mit JSON.")
    werte.append(_wert("Erste Antwort (mit Laden des Modells)", _sekunden(erste), "ok",
                       "Lädt das Programm das Modell erst bei Bedarf, ist diese Zeit länger."))
    auftrag.pruefe()
    auftrag.melde("Kurze Anfrage …", 2, 3 + len(FRAGEN))
    _, kurz, _, _ = m.frage('Gib {"ok": true} zurück.', _KURZ_SCHEMA, "Antworte nur mit JSON.")
    werte.append(_wert("Antwortzeit bei kurzer Anfrage", _sekunden(kurz),
                       "ok" if kurz <= 5 else "warnung",
                       None if kurz <= 5 else
                       "Jede Anfrage beginnt mit dieser Wartezeit; Analysen dauern entsprechend."))
    auftrag.pruefe()
    auftrag.melde("Längere Anfrage (Zusammenfassung) …", 3, 3 + len(FRAGEN))
    antwort, lang, verbrauch, _ = m.frage(
        f"Sachverhalt:\n{SACHVERHALT}\n\nFasse den Sachverhalt in genau fünf vollständigen Sätzen zusammen.",
        _LANG_SCHEMA)
    werte.append(_wert("Dauer einer Zusammenfassung (ca. 1.250 Zeichen Text)", _sekunden(lang),
                       "ok" if lang <= 30 else "warnung",
                       None if lang <= 30 else "Für eine ganze Akte braucht das Modell ein Vielfaches davon."))
    if verbrauch and verbrauch["ausgabe"]:
        rechenzeit = verbrauch["erzeugung_s"] or lang
        rate = verbrauch["ausgabe"] / rechenzeit if rechenzeit > 0 else 0
        art = "reine Rechenzeit" if verbrauch["erzeugung_s"] else "gesamte Antwortzeit"
        werte.append(_wert("Token pro Sekunde", f"{rate:.0f}".replace(".", ","),
                           "ok" if rate >= 15 else "warnung",
                           f"{verbrauch['ausgabe']} Token Antwort, gemessen über die {art}."
                           + ("" if rate >= 15 else " Unter 15 Token/s wirkt der Chat zäh.")))
    elif antwort is not None:
        zeichen = len(json.dumps(antwort, ensure_ascii=False))
        werte.append(_wert("Zeichen pro Sekunde", f"{zeichen / lang:.0f}" if lang > 0 else "–", "ok",
                           "Das Programm meldet keine Tokenzahl; gemessen wurden die Zeichen der Antwort."))
    if antwort is not None:
        saetze = [s for s in antwort.get("saetze") or [] if isinstance(s, str) and s.strip()]
        if len(saetze) != 5:
            werte.append(_wert("Vorgabe „genau fünf Sätze“", f"{len(saetze)} Sätze", "warnung",
                               "Das Modell hält sich nicht genau an Vorgaben zur Form."))
    return werte


def leistungstest(modell: Any, auftrag: Any, anbieter: str, ort: str, wb: sqlite3.Connection | None = None,
                  rechner: bool = False) -> dict:
    """Führt den Test aus; ``auftrag`` meldet Fortschritt und prüft auf Abbruch (siehe ``auftraege``).

    ``wb``: Wissensbasis für den Durchgang „mit Gesetzen“; jede Frage bekommt dann die einschlägigen Normen mit.
    ``rechner``: Bei den Fristfragen nennt das Modell nur Bezugstag und Dauer, das Ende rechnet der Fristenrechner."""
    m = _Messung(modell)
    beginn = time.monotonic()
    messwerte = geschwindigkeit(m, auftrag)
    fragen = []
    fehlend: list[str] = []
    for nr, f in enumerate(FRAGEN, start=4):
        auftrag.pruefe()
        auftrag.melde(f"Prüffrage {nr - 3} von {len(FRAGEN)}: {f.bereich} …", nr, 3 + len(FRAGEN))
        mit: list[str] = []
        per_rechner = rechner and f.bereich == "Fristen"
        text, schema = f.frage, f.schema
        if per_rechner:
            text, schema = f.frage.replace(FRIST_SCHLUSS, RECHNER_SCHLUSS), _RECHNER_SCHEMA
        system = SYSTEM
        if wb is not None and f.id in NORMEN:
            auszug, mit, fehlen = gesetze_zur_frage(wb, f.id)
            for x in fehlen:
                if x not in fehlend:
                    fehlend.append(x)
            if auszug:
                text, system = f"Gesetze:\n{auszug}\n\nFrage: {text}", SYSTEM_GESETZE
        antwort, dauer, _, fehler = m.frage(text, schema, system + (SYSTEM_RECHNER if per_rechner else ""))
        if antwort is None:
            richtig, anzeige = False, f"Keine gültige Antwort ({fehler})"
        elif per_rechner:
            richtig, anzeige = mit_fristenrechner(f, antwort)
        else:
            richtig, anzeige = f.pruefe(antwort)
        fragen.append({"id": f.id, "bereich": f.bereich, "frage": f.frage.split("\n\n")[-1] if "Text:\n" in f.frage
                       else f.frage, "erwartet": f.erwartet, "antwort": anzeige, "richtig": richtig,
                       "fundstelle": f.fundstelle, "sekunden": round(dauer, 1), "gesetze": mit})
    if m.denkphase:
        messwerte.append(_wert("Denkphase", f"{m.denkphase} Zeichen", "warnung",
                               "Das Modell denkt vor jeder Antwort; das kostet Zeit und kann Antworten abschneiden. "
                               "In LM Studio in den Modelleinstellungen „Reasoning“ ausschalten."))
    else:
        messwerte.append(_wert("Denkphase", "keine", "ok"))
    bereiche: dict[str, list[bool]] = {}
    for f in fragen:
        bereiche.setdefault(f["bereich"], []).append(f["richtig"])
    richtig = sum(f["richtig"] for f in fragen)
    anteil = richtig / len(fragen)
    stand = "ok" if anteil >= 0.85 else "warnung" if anteil >= 0.6 else "fehler"
    meldung = (f"{richtig} von {len(fragen)} Prüffragen richtig beantwortet. " + (
        "Für Zusammenfassungen und Analysen mit Belegen gut geeignet; rechtliche Ergebnisse trotzdem prüfen."
        if stand == "ok" else
        "Fristen, Zuständigkeiten und Normen aus diesem Modell immer selbst nachrechnen und prüfen."
        if stand == "warnung" else
        "Das Modell eignet sich nicht für rechtliche Einschätzungen; allenfalls für einfache Zusammenfassungen."))
    if fehlend:
        messwerte.append(_wert("Gesetze in der Wissensbasis", "Nicht geladen: " + ", ".join(fehlend), "warnung",
                               "Diese Fragen liefen ohne die einschlägige Norm. Unter „Gesetze“ das Paket "
                               "(Strafrecht, Verwaltungsrecht) einschalten oder das Gesetz einzeln hinzufügen."))
    if m.json_fehler:
        messwerte.append(_wert("Antworten als gültiges JSON", f"{m.json_fehler} fehlerhaft", "warnung",
                               "Analysen brechen bei solchen Antworten ab oder fragen erneut."))
    return {
        "anbieter": anbieter, "modell": str(getattr(modell, "modell", "") or ""), "ort": ort,
        "dauer": round(time.monotonic() - beginn),
        "messwerte": messwerte,
        "fragen": fragen,
        "bereiche": [{"bereich": b, "richtig": sum(w), "von": len(w)} for b, w in bereiche.items()],
        "gesamt": {"richtig": richtig, "von": len(fragen), "stand": stand, "meldung": meldung},
        "stand_fundstellen": STAND_FUNDSTELLEN,
        "mit_gesetzen": wb is not None,
        "mit_fristenrechner": rechner,
    }
