"""Fristenbuch und Kalenderdatei: Fristen, Vorfristen, Termine und Wiedervorlagen eines Zeitraums ausgeben.

- Fristenbuch (Word, PDF, Excel, Markdown, Text oder Druck) für die Fristenkontrolle. Oben stehen immer die
  abgelaufenen, nicht erledigten Fristen und Wiedervorlagen, auch wenn sie vor dem Zeitraum liegen, danach unter
  „Dringend“ die offenen Fristen, die in den nächsten Tagen ablaufen (hervorgehoben). Es folgen je Art ein eigener
  Abschnitt (Termine, Fristen, Vorfristen, Wiedervorlagen), darin nach Tagen; Excel bekommt je Abschnitt ein Blatt.
- Kalenderdatei (.ics, iCalendar nach RFC 5545) zum Einlesen in Outlook, Apple- oder Google-Kalender. JuraBox
  schreibt nur die Datei; ein Abgleich über das Netz findet nicht statt.

Der Filter entspricht dem des Kalenders in der App (app/src/kalenderLogik.ts): Arten, Zustand, Akte, Gericht, nur
abgelaufene. Vorfristen stehen an ihrem eigenen Tag, solange die Frist offen ist.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .. import ausgabe
from ..ausgabe import Absatz, Bericht, Eintrag, Kopf, Tabelle, Ueberschrift
from . import kalender

POSTEN = {"frist": "Frist", "vorfrist": "Vorfrist", "termin": "Termin", "wiedervorlage": "Wiedervorlage"}
ZUSTAND_TEXT = {"alle": "offen und abgeschlossen", "offen": "nur offen", "abgeschlossen": "nur erledigt und vergangen"}
WOCHENTAG = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
ABSCHNITTE = (("termin", "Termine"), ("frist", "Fristen"), ("vorfrist", "Vorfristen"),
              ("wiedervorlage", "Wiedervorlagen"))
DRINGEND_TAGE = 3  # offene Fristen, die heute oder in den nächsten drei Tagen ablaufen
_SPALTEN = ("Tag", "Uhrzeit", "Art", "Worum", "Aktenzeichen", "Akte", "Gericht", "Ort", "Fristende", "Stand", "Beleg")


def _tag(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{WOCHENTAG[d.weekday()]}, {d:%d.%m.%Y}"


def _filter(f: dict | None) -> dict:
    f = dict(f or {})
    arten = [a for a in f.get("arten") or POSTEN if a in POSTEN]
    zustand = f.get("zustand") if f.get("zustand") in ZUSTAND_TEXT else "alle"
    return {"arten": arten, "zustand": zustand, "akte_id": f.get("akteId", f.get("akte_id")),
            "gericht": f.get("gericht") or "", "nur_abgelaufen": bool(f.get("nurAbgelaufen", f.get("nur_abgelaufen")))}


def posten(eintraege: list[dict], filter: dict | None, von: str, bis: str) -> list[dict]:
    """Wie ``posten`` in app/src/kalenderLogik.ts: je Eintrag sein Tag, bei offenen Fristen dazu die Vorfristen."""
    f = _filter(filter)
    liste: list[dict] = []
    for e in eintraege:
        if f["akte_id"] is not None and e["akte_id"] != f["akte_id"]:
            continue
        if f["gericht"] and (e.get("gericht") or "") != f["gericht"]:
            continue
        if (f["zustand"] == "offen" and e["abgeschlossen"]) or (f["zustand"] == "abgeschlossen" and
                                                                not e["abgeschlossen"]):
            continue
        if f["nur_abgelaufen"] and e["lage"] != "abgelaufen":
            continue
        if e["art"] in f["arten"] and von <= e["datum"] <= bis:
            liste.append({"tag": e["datum"], "typ": e["art"], "nr": None, "eintrag": e})
        if e["art"] == "frist" and not e["abgeschlossen"] and not f["nur_abgelaufen"] and "vorfrist" in f["arten"]:
            for nr, v in ((1, e["vorfrist"]), (2, e["vorfrist2"])):
                if v and von <= v <= bis:
                    liste.append({"tag": v, "typ": "vorfrist", "nr": nr, "eintrag": e})
    return sorted(liste, key=lambda p: (p["tag"], p["eintrag"]["uhrzeit"] or "", p["eintrag"]["id"]))


def _art(p: dict) -> str:
    return "2. Vorfrist" if p["typ"] == "vorfrist" and p["nr"] == 2 else POSTEN[p["typ"]]


def _zeit(e: dict) -> str:
    if not e["uhrzeit"]:
        return ""
    return f"{e['uhrzeit']}–{e['bis_uhrzeit']} Uhr" if e["bis_uhrzeit"] else f"{e['uhrzeit']} Uhr"


def _stand(e: dict) -> str:
    """„offen“, „erledigt am 03.11.2026: Schriftsatz eingereicht“, „verlegt auf 09.12.2026“ usw."""
    if e["erledigt_am"]:
        wort = e["zustand"] or "erledigt"
        if e.get("verlegt_auf"):
            text = f"verlegt auf {_tag(e['verlegt_auf']['datum'])}"
        else:
            text = f"{wort} am {date.fromisoformat(e['erledigt_am'][:10]):%d.%m.%Y}"
        return f"{text}: {e['erledigt_vermerk']}" if e["erledigt_vermerk"] else text
    if e["lage"] == "stattgefunden":
        return "stattgefunden"
    if e["lage"] == "abgelaufen":
        return f"abgelaufen seit {-e['in_tagen']} {'Tag' if e['in_tagen'] == -1 else 'Tagen'}, nicht erledigt"
    return "offen"


def _dringend(p: dict) -> str:
    """„läuft heute ab“, „läuft morgen ab“, „läuft in 3 Tagen ab“ für offene Fristen kurz vor dem Ablauf, sonst ""."""
    e = p["eintrag"]
    if p["typ"] != "frist" or e["abgeschlossen"] or not 0 <= e["in_tagen"] <= DRINGEND_TAGE:
        return ""
    return {0: "läuft heute ab", 1: "läuft morgen ab"}.get(e["in_tagen"], f"läuft in {e['in_tagen']} Tagen ab")


def _beleg(e: dict) -> str:
    if not e["dokument"]:
        return ""
    f = e.get("fundstelle") or {}
    stelle = ", ".join(x for x in (f"S. {f['seite']}" if f.get("seite") else "",
                                   f"Abschnitt {f['abschnitt']}" if f.get("abschnitt") else "") if x)
    return f"{e['dokument']}, {stelle}" if stelle else e["dokument"]


def _akte(e: dict) -> str:
    return " ".join(x for x in (e.get("aktenzeichen"), e.get("akte")) if x)


def _zeilen(p: dict) -> list[str]:
    e = p["eintrag"]
    zeilen = [_akte(e)]
    if e.get("gericht"):
        zeilen.append(e["gericht"] + (f", {e['gericht_aktenzeichen']}" if e.get("gericht_aktenzeichen") else ""))
    if p["typ"] == "vorfrist":
        zeilen.append(f"Fristende: {_tag(e['datum'])}")
    elif e["art"] == "frist" and (e["vorfrist"] or e["vorfrist2"]):
        zeilen.append("Vorfristen: " + " und ".join(_tag(v) for v in (e["vorfrist"], e["vorfrist2"]) if v))
    if e["ort"]:
        zeilen.append(f"Ort: {e['ort']}")
    if e.get("verlegt_von_termin"):
        zeilen.append(f"Verlegt vom {_tag(e['verlegt_von_termin']['datum'])}")
    for v in e["verlauf"]:
        zeilen.append(f"{v['was'].capitalize()} vom {_tag(v['alt'])} auf {_tag(v['neu'])}"
                      + (f" ({v['vermerk']})" if v.get("vermerk") else ""))
    if p["typ"] != "vorfrist":
        zeilen.append(f"Stand: {_stand(e)}")
    if b := _beleg(e):
        zeilen.append(f"Beleg: {b}")
    return zeilen


def _tabellenzeile(p: dict) -> list[str]:
    e = p["eintrag"]
    return [_tag(p["tag"]), _zeit(e) if p["typ"] == "termin" else "", _art(p), e["titel"],
            e.get("aktenzeichen") or "", e.get("akte") or "", e.get("gericht") or "", e["ort"] or "",
            _tag(e["datum"]) if e["art"] == "frist" else "",
            ", ".join(x for x in (_stand(e), _dringend(p)) if x) if p["typ"] != "vorfrist" else "Vorfrist",
            _beleg(e)]


def _eintrag(p: dict, mit_tag: bool = False) -> Eintrag:
    e = p["eintrag"]
    zeit = (_zeit(e) or "ganztägig") if p["typ"] == "termin" else ""
    nummer = " ".join(x for x in (_tag(p["tag"]) if mit_tag else "", zeit) if x)
    marken = [m for m in (e["zustand"] if e["zustand"] in ("aufgehoben", "verlegt") else "",
                          "abgelaufen" if e["lage"] == "abgelaufen" and p["typ"] != "vorfrist" else "",
                          _dringend(p)) if m]
    return Eintrag(f"{_art(p)}: {e['titel']}", nummer=nummer, marken=marken, zeilen=_zeilen(p), kompakt=True,
                   dringend=bool(_dringend(p) or (e["lage"] == "abgelaufen" and p["typ"] != "vorfrist")))


def _nach_tagen(liste: list[dict]) -> list:
    bausteine: list = []
    tag = None
    for p in liste:
        if p["tag"] != tag:
            tag = p["tag"]
            bausteine.append(Ueberschrift(_tag(tag), ebene=2))
        bausteine.append(_eintrag(p))
    return bausteine


_BREITEN = [16, 13, 13, 36, 11, 30, 26, 14, 16, 30, 36]


def bericht(con: sqlite3.Connection, von: str, bis: str, filter: dict | None = None,
            heute: date | None = None, jetzt: datetime | None = None) -> Bericht:
    heute = heute or date.today()
    f = _filter(filter)
    liste = posten(kalender.zeitraum(con, von, bis, heute), f, von, bis)
    ueberfaellig = [p for p in posten(kalender.naechste(con, tage=0, limit=500, heute=heute), {**f, "zustand": "offen"},
                                      "0000-01-01", (heute - timedelta(days=1)).isoformat())
                    if p["typ"] != "vorfrist" and p["eintrag"]["lage"] == "abgelaufen" and p["tag"] < von]
    dringend = [] if f["nur_abgelaufen"] else [
        p for p in posten(kalender.zeitraum(con, heute.isoformat(), (heute + timedelta(days=DRINGEND_TAGE)).isoformat(),
                                            heute), {**f, "zustand": "offen"}, heute.isoformat(), "9999-12-31")
        if _dringend(p)]
    auswahl = [", ".join(POSTEN[a] for a in f["arten"]) or "keine Art", ZUSTAND_TEXT[f["zustand"]]]
    if f["akte_id"] is not None:
        a = con.execute("SELECT name, aktenzeichen FROM akte WHERE id = ?", (f["akte_id"],)).fetchone()
        if a:
            auswahl.append("Akte " + " ".join(x for x in (a["aktenzeichen"], a["name"]) if x))
    if f["gericht"]:
        auswahl.append(f["gericht"])
    if f["nur_abgelaufen"]:
        auswahl.append("nur abgelaufene")
    bausteine: list = [Kopf([("Zeitraum", f"{_tag(von)} bis {_tag(bis)}"), ("Auswahl", "; ".join(auswahl)),
                             ("Einträge", str(len(liste))),
                             ("Erstellt am", (jetzt or datetime.now()).strftime("%d.%m.%Y %H:%M"))])]
    if ueberfaellig:
        bausteine.append(Ueberschrift("Abgelaufen und nicht erledigt (vor dem Zeitraum)"))
        bausteine += [_eintrag(p, mit_tag=True) for p in ueberfaellig]
    if dringend:
        bausteine.append(Ueberschrift(f"Dringend: Fristablauf heute und in den nächsten {DRINGEND_TAGE} Tagen"))
        bausteine += [_eintrag(p, mit_tag=True) for p in dringend]
    tabellen: list[Tabelle] = []
    if ueberfaellig:
        tabellen.append(Tabelle("Abgelaufen", list(_SPALTEN), [_tabellenzeile(p) for p in ueberfaellig], _BREITEN))
    if dringend:
        tabellen.append(Tabelle("Dringend", list(_SPALTEN), [_tabellenzeile(p) for p in dringend], _BREITEN))
    for typ, ueberschrift in ABSCHNITTE:
        if typ not in f["arten"]:
            continue
        teil = [p for p in liste if p["typ"] == typ]
        bausteine.append(Ueberschrift(ueberschrift))
        bausteine += _nach_tagen(teil) or [Absatz(f"Keine {ueberschrift} im Zeitraum.", leise=True)]
        tabellen.append(Tabelle(ueberschrift, list(_SPALTEN), [_tabellenzeile(p) for p in teil], _BREITEN))
    if not f["arten"]:
        bausteine.append(Absatz("Keine Art ausgewählt.", leise=True))
    bausteine.append(Absatz("Erstellt mit JuraBox aus den eingetragenen Fristen, Terminen und Wiedervorlagen. "
                            "Vorschläge aus Dokumenten sind nur enthalten, soweit sie eingetragen wurden; die "
                            "eigene Fristenkontrolle ersetzt das Fristenbuch nicht.", leise=True))
    return Bericht(f"Fristenbuch {von[8:10]}.{von[5:7]}.{von[:4]} bis {bis[8:10]}.{bis[5:7]}.{bis[:4]}",
                   bausteine, tabellen)


def dateiname(von: str, bis: str) -> str:
    return f"Fristenbuch {von} bis {bis}"


def schreiben(con: sqlite3.Connection, pfad: str | Path, von: str, bis: str, filter: dict | None = None,
              umgebung: str = "standard") -> dict:
    """Fristenbuch speichern; das Format folgt der Endung (docx, pdf, xlsx, md, txt) bzw. ``.ics``."""
    ziel = Path(pfad)
    art = ziel.suffix.lower().lstrip(".")
    if art == "ics":
        text = ics(con, von, bis, filter, umgebung=umgebung)
        ziel.write_bytes(text.encode("utf-8"))
        return {"pfad": str(ziel), "format": art, "anzahl": text.count("BEGIN:VEVENT")}
    if art not in ausgabe.FORMATE:
        raise ValueError(f"Format „.{art}“ wird nicht unterstützt; möglich: "
                         f"{', '.join('.' + k for k in (*ausgabe.FORMATE, 'ics'))}.")
    daten = ausgabe.schreiben(bericht(con, von, bis, filter), art)
    ziel.write_bytes(daten)
    return {"pfad": str(ziel), "format": art, "groesse": len(daten)}


def druckansicht(con: sqlite3.Connection, von: str, bis: str, filter: dict | None = None) -> dict:
    from ..ausgabe import html

    b = bericht(con, von, bis, filter)
    return {"titel": b.titel, "html": html.fragment(b), "stil": html.STIL}


# --------------------------------------------------------------------------- iCalendar (RFC 5545)


def _ics_text(text: str) -> str:
    return re.sub(r"([\\;,])", r"\\\1", text).replace("\r\n", "\n").replace("\n", "\\n")


def _falten(zeile: str) -> list[str]:
    """Zeilen über 75 Oktetten werden umbrochen; die Folgezeile beginnt mit einem Leerzeichen (RFC 5545, 3.1)."""
    teile, rest, grenze = [], zeile, 75
    while len(rest.encode("utf-8")) > grenze:
        n = grenze
        while len(rest[:n].encode("utf-8")) > grenze:
            n -= 1
        teile.append(rest[:n])
        rest, grenze = " " + rest[n:], 75
    return [*teile, rest]


def ics(con: sqlite3.Connection, von: str, bis: str, filter: dict | None = None, heute: date | None = None,
        jetzt: datetime | None = None, umgebung: str = "standard") -> str:
    """Kalenderdatei: Termine mit Uhrzeit (Ortszeit, ohne Zeitzone; ohne Ende eine Stunde), Fristen, Vorfristen,
    Wiedervorlagen und Termine ohne Uhrzeit als ganztägige Einträge. Aufgehobene und verlegte Termine sind
    abgesagt (STATUS:CANCELLED). Die UID bleibt je Eintrag gleich, damit ein erneuter Import aktualisiert; sie
    enthält die Arbeitsumgebung, weil jede Umgebung ihre Einträge eigenständig nummeriert."""
    kennung = re.sub(r"[^a-z0-9-]+", "-", umgebung.casefold()).strip("-") or "standard"
    stempel = (jetzt or datetime.now()).strftime("%Y%m%dT%H%M%S")
    zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JuraBox//Kalender//DE", "CALSCALE:GREGORIAN",
              "METHOD:PUBLISH", "X-WR-CALNAME:JuraBox Fristen und Termine"]
    for p in posten(kalender.zeitraum(con, von, bis, heute), filter, von, bis):
        e = p["eintrag"]
        tag = date.fromisoformat(p["tag"])
        akte = _akte(e)
        zeilen += ["BEGIN:VEVENT", f"UID:jurabox-{kennung}-{e['id']}-{p['typ']}{p['nr'] or ''}@jurabox",
                   f"DTSTAMP:{stempel}"]
        if p["typ"] == "termin" and e["uhrzeit"]:
            beginn = datetime.combine(tag, datetime.strptime(e["uhrzeit"], "%H:%M").time())
            ende = (datetime.combine(tag, datetime.strptime(e["bis_uhrzeit"], "%H:%M").time()) if e["bis_uhrzeit"]
                    else beginn + timedelta(hours=1))
            zeilen += [f"DTSTART:{beginn:%Y%m%dT%H%M%S}", f"DTEND:{ende:%Y%m%dT%H%M%S}"]
        else:
            zeilen += [f"DTSTART;VALUE=DATE:{tag:%Y%m%d}", f"DTEND;VALUE=DATE:{tag + timedelta(days=1):%Y%m%d}",
                       "TRANSP:TRANSPARENT"]
        titel = f"{_art(p)}: {e['titel']}" + (f" ({akte})" if akte else "")
        zeilen.append(f"SUMMARY:{_ics_text(titel)}")
        if e["ort"] and p["typ"] == "termin":
            zeilen.append(f"LOCATION:{_ics_text(e['ort'])}")
        zeilen.append(f"DESCRIPTION:{_ics_text(chr(10).join(_zeilen(p)))}")
        zeilen.append("CATEGORIES:" + _ics_text(POSTEN[p["typ"]]))
        if e["zustand"] in ("aufgehoben", "verlegt"):
            zeilen.append("STATUS:CANCELLED")
        zeilen.append("END:VEVENT")
    zeilen.append("END:VCALENDAR")
    return "".join(t + "\r\n" for z in zeilen for t in _falten(z))
