"""Fristen, Termine und Wiedervorlagen einer Akte.

- Frist: endet an einem Tag (Klageerwiderung, Berufungsbegründung …), auf Wunsch mit Vorfrist. Wird sie aus
  Bezugstag und Dauer berechnet, rechnet der Fristenrechner (§§ 187, 188, 193 BGB) und die Berechnung wird mit
  gespeichert, damit sie nachvollziehbar bleibt. Eine Frist ist offen, bis sie erledigt wird; sie läuft nie still
  ab. Wird sie verlängert, bleibt das alte Fristende im Verlauf.
- Termin: Gerichtstermin mit Uhrzeit und Ort. Termine werden nicht erledigt: nach dem Termintag gelten sie als
  stattgefunden, vorher können sie aufgehoben oder verlegt werden. Beim Verlegen entsteht ein Folgetermin, der auf
  den alten verweist (``verlegt_von``).
- Wiedervorlage: Tag, an dem die Akte wieder vorgelegt werden soll; wird erledigt oder verschoben.

JuraBox schlägt Fristen und Termine aus Dokumenten nur vor (mit Fundstelle); eingetragen wird erst nach Bestätigung.
Ein Vorschlag ersetzt nie die eigene Fristenkontrolle.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta

from ..rechner import fristen as fristenrechner

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kalender (
    id            INTEGER PRIMARY KEY,
    akte_id       INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    verfahren_id  INTEGER REFERENCES verfahren(id) ON DELETE SET NULL,
    art           TEXT NOT NULL CHECK (art IN ('frist', 'termin', 'wiedervorlage')),
    titel         TEXT NOT NULL,
    datum         TEXT NOT NULL,            -- Fristende, Termin- bzw. Wiedervorlagetag (JJJJ-MM-TT)
    uhrzeit       TEXT,                     -- HH:MM, bei Terminen
    ort           TEXT,                     -- z. B. "Saal 104"
    vorfrist      TEXT,                     -- JJJJ-MM-TT, bei Fristen (erste Vorfrist)
    berechnung    TEXT,                     -- JSON: Bezugstag, Dauer, Ergebnis des Fristenrechners
    dokument_id   INTEGER REFERENCES dokument(id) ON DELETE SET NULL,
    fundstelle    TEXT,                     -- JSON: {"abschnitt", "seite", "text"} im Dokument
    notiz         TEXT,
    erledigt_am   TEXT,                     -- abgeschlossen am: erledigt, aufgehoben oder verlegt
    erledigt_vermerk TEXT,
    angelegt_am   TEXT NOT NULL,
    geaendert_am  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS kalender_akte ON kalender (akte_id);
CREATE INDEX IF NOT EXISTS kalender_offen ON kalender (datum) WHERE erledigt_am IS NULL;
"""

ARTEN = {"frist": "Frist", "termin": "Termin", "wiedervorlage": "Wiedervorlage"}
# Abschluss eines Eintrags. Fristen und Wiedervorlagen werden erledigt; Termine finden statt (von selbst nach dem
# Termintag), werden aufgehoben oder verlegt.
ZUSTAENDE = {"erledigt": "erledigt", "stattgefunden": "stattgefunden", "aufgehoben": "aufgehoben", "verlegt": "verlegt"}
TERMIN_ZUSTAENDE = ("geplant", "stattgefunden", "aufgehoben", "verlegt")
FELDER = ("verfahren_id", "art", "titel", "datum", "uhrzeit", "bis_uhrzeit", "ort", "vorfrist", "vorfrist2",
          "dokument_id", "fundstelle", "notiz")
_UHRZEIT = re.compile(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$")
_NEUE_SPALTEN = (("zustand", "TEXT"), ("bis_uhrzeit", "TEXT"), ("verlauf", "TEXT"), ("vorfrist2", "TEXT"),
                 ("verlegt_von", "INTEGER REFERENCES kalender(id) ON DELETE SET NULL"))


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    vorhanden = {z[1] for z in con.execute("PRAGMA table_info(kalender)")}
    for spalte, typ in _NEUE_SPALTEN:
        if spalte not in vorhanden:
            con.execute(f"ALTER TABLE kalender ADD COLUMN {spalte} {typ}")
    # Einträge aus Versionen, die nur „erledigt“ kannten: Termine bekommen ihren eigentlichen Zustand.
    con.execute("""UPDATE kalender SET zustand = CASE
                       WHEN art != 'termin' THEN 'erledigt'
                       WHEN lower(COALESCE(erledigt_vermerk, '')) LIKE '%aufgehoben%' THEN 'aufgehoben'
                       WHEN lower(COALESCE(erledigt_vermerk, '')) LIKE '%verlegt%' THEN 'verlegt'
                       ELSE 'stattgefunden' END
                   WHERE zustand IS NULL AND erledigt_am IS NOT NULL""")
    con.execute("CREATE INDEX IF NOT EXISTS kalender_verlegt ON kalender (verlegt_von)")
    con.commit()


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _datum(text: str, feld: str) -> str:
    try:
        return date.fromisoformat(str(text).strip()).isoformat()
    except ValueError as fehler:
        raise ValueError(f"{feld}: bitte ein Datum im Format JJJJ-MM-TT.") from fehler


def _zeile(z: sqlite3.Row, heute: date) -> dict:
    e = dict(z)
    e["berechnung"] = json.loads(e["berechnung"]) if e["berechnung"] else None
    e["fundstelle"] = json.loads(e["fundstelle"]) if e["fundstelle"] else None
    e["verlauf"] = json.loads(e["verlauf"]) if e.get("verlauf") else []
    e["art_text"] = ARTEN[e["art"]]
    tage = (date.fromisoformat(e["datum"]) - heute).days
    e["in_tagen"] = tage
    # Welche der beiden Vorfristen zuletzt erreicht ist (1 oder 2); bei Erinnerungen zählt jede einzeln.
    e["vorfrist_erreicht"] = next((n for n, k in ((2, "vorfrist2"), (1, "vorfrist"))
                                   if e.get(k) and date.fromisoformat(e[k]) <= heute), None)
    if e["erledigt_am"]:
        e["lage"] = e["zustand"] or "erledigt"
    elif e["art"] == "termin" and tage < 0:
        e["lage"] = "stattgefunden"
    elif tage < 0:
        e["lage"] = "abgelaufen"
    elif tage == 0:
        e["lage"] = "heute"
    elif e["vorfrist_erreicht"]:
        e["lage"] = "vorfrist"
    elif tage <= 7:
        e["lage"] = "bald"
    else:
        e["lage"] = "offen"
    # Abgeschlossen: erledigt, aufgehoben, verlegt oder ein Termin, dessen Tag vorbei ist.
    e["abgeschlossen"] = e["lage"] in (*ZUSTAENDE, "stattgefunden")
    return e


def _verknuepfen(con: sqlite3.Connection, eintraege: list[dict]) -> list[dict]:
    """Ergänzt bei verlegten Terminen den Folgetermin (``verlegt_auf``) und beim Folgetermin den alten Termin."""
    ids = [e["id"] for e in eintraege]
    if not ids:
        return eintraege
    platz = ", ".join("?" for _ in ids)
    folge = {z["verlegt_von"]: dict(z) for z in con.execute(
        f"SELECT id, datum, uhrzeit, verlegt_von FROM kalender WHERE verlegt_von IN ({platz}) ORDER BY id", ids)}
    alt_ids = [e["verlegt_von"] for e in eintraege if e.get("verlegt_von")]
    alt = {z["id"]: dict(z) for z in con.execute(
        f"SELECT id, datum, uhrzeit FROM kalender WHERE id IN ({', '.join('?' for _ in alt_ids)})", alt_ids)} \
        if alt_ids else {}
    for e in eintraege:
        f = folge.get(e["id"])
        e["verlegt_auf"] = {"id": f["id"], "datum": f["datum"], "uhrzeit": f["uhrzeit"]} if f else None
        e["verlegt_von_termin"] = alt.get(e["verlegt_von"]) if e.get("verlegt_von") else None
    return eintraege


def liste(con: sqlite3.Connection, akte_id: int, heute: date | None = None) -> list[dict]:
    """Alle Einträge der Akte: offene nach Datum, darunter die abgeschlossenen (neueste zuerst)."""
    heute = heute or date.today()
    zeilen = con.execute(
        """SELECT k.*, COALESCE(d.titel, d.dateiname) AS dokument FROM kalender k
           LEFT JOIN dokument d ON d.id = k.dokument_id
           WHERE k.akte_id = ? ORDER BY k.erledigt_am IS NOT NULL, k.datum, k.uhrzeit, k.id""", (akte_id,)).fetchall()
    eintraege = _verknuepfen(con, [_zeile(z, heute) for z in zeilen])
    offen = [e for e in eintraege if not e["abgeschlossen"]]
    erledigt = sorted((e for e in eintraege if e["abgeschlossen"]), key=lambda e: e["datum"], reverse=True)
    return offen + erledigt


def berechne(bezugstag: str, anzahl: int, einheit: str, land: str = "BY", beginn: str = "ereignis") -> dict:
    """Fristende über den Fristenrechner; ``land`` "BY-ohne" = Bayern ohne Mariä Himmelfahrt."""
    ergebnis = fristenrechner.berechne(date.fromisoformat(_datum(bezugstag, "Bezugstag")), int(anzahl), einheit,
                                       beginn=beginn, land="BY" if land == "BY-ohne" else land,
                                       maria_himmelfahrt_bayern=land != "BY-ohne")
    return {"bezugstag": ergebnis["bezugstag"], "anzahl": int(anzahl), "einheit": einheit, "beginn": beginn,
            "land": ergebnis["land"], "ende": ergebnis["ende"], "wochentag": ergebnis["wochentag"],
            "verschoben": ergebnis["verschoben"], "grund": ergebnis["grund"], "grundlagen": ergebnis["grundlagen"],
            "hinweise": ergebnis["hinweise"]}


def speichern(con: sqlite3.Connection, akte_id: int, daten: dict, eintrag_id: int | None = None,
              heute: date | None = None) -> list[dict]:
    """Legt einen Eintrag an oder ändert ihn. Mit ``daten["berechnung"]`` = {bezugstag, anzahl, einheit, land}
    rechnet der Fristenrechner das Fristende aus; ein von Hand eingegebenes Datum gilt dann nicht."""
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    alt: dict = {}
    if eintrag_id is not None:
        z = con.execute("SELECT * FROM kalender WHERE id = ? AND akte_id = ?", (eintrag_id, akte_id)).fetchone()
        if z is None:
            raise LookupError(f"Eintrag {eintrag_id} gibt es in dieser Akte nicht.")
        alt = dict(z)
    werte = {k: alt.get(k) for k in FELDER}
    werte["berechnung"] = alt.get("berechnung")
    for k in FELDER:
        if k not in daten:
            continue
        v = daten[k]
        if k in ("verfahren_id", "dokument_id"):
            werte[k] = None if v in (None, "") else int(v)
        elif k == "fundstelle":
            werte[k] = json.dumps(v, ensure_ascii=False) if v else None
        elif k == "notiz":
            werte[k] = "\n".join(t.strip() for t in str(v or "").splitlines() if t.strip()) or None
        else:
            werte[k] = " ".join(str(v or "").split()) or None
    if werte["art"] not in ARTEN:
        raise ValueError("Bitte wählen: Frist, Termin oder Wiedervorlage.")
    if not werte["titel"]:
        raise ValueError("Bitte angeben, worum es geht (z. B. Klageerwiderung).")
    if "berechnung" in daten:
        b = daten["berechnung"]
        if b:
            r = berechne(b["bezugstag"], b["anzahl"], b["einheit"], b.get("land", "BY"), b.get("beginn", "ereignis"))
            werte["datum"] = r["ende"]
            werte["berechnung"] = json.dumps(r, ensure_ascii=False)
        else:
            werte["berechnung"] = None
    if not werte["datum"]:
        raise ValueError("Bitte ein Datum angeben oder die Frist berechnen lassen.")
    werte["datum"] = _datum(werte["datum"], "Datum")
    vorfristen = sorted({_datum(werte[k], "Vorfrist") for k in ("vorfrist", "vorfrist2") if werte[k]})
    if any(v >= werte["datum"] for v in vorfristen):
        raise ValueError("Die Vorfrist muss vor dem Fristende liegen.")
    if werte["art"] != "frist":
        vorfristen = []
    # Die frühere Vorfrist ist immer die erste.
    werte["vorfrist"], werte["vorfrist2"] = (vorfristen + [None, None])[:2]
    if werte["art"] != "termin":
        werte["uhrzeit"] = werte["bis_uhrzeit"] = werte["ort"] = None
    werte["uhrzeit"] = _uhrzeit(werte["uhrzeit"])
    werte["bis_uhrzeit"] = _uhrzeit(werte["bis_uhrzeit"])
    if werte["bis_uhrzeit"] and (not werte["uhrzeit"] or werte["bis_uhrzeit"] <= werte["uhrzeit"]):
        raise ValueError("Das Ende des Termins muss nach dem Beginn liegen.")
    if werte["verfahren_id"] is not None and con.execute(
            "SELECT 1 FROM verfahren WHERE id = ? AND akte_id = ?",
            (werte["verfahren_id"], akte_id)).fetchone() is None:
        raise ValueError("Das Verfahren gehört nicht zu dieser Akte.")
    if werte["dokument_id"] is not None and con.execute(
            "SELECT 1 FROM dokument WHERE id = ? AND akte_id = ?", (werte["dokument_id"], akte_id)).fetchone() is None:
        raise ValueError("Das Dokument gehört nicht zu dieser Akte.")
    spalten = (*FELDER, "berechnung")
    jetzt = _jetzt()
    with con:
        if eintrag_id is None:
            con.execute(f"INSERT INTO kalender (akte_id, {', '.join(spalten)}, angelegt_am, geaendert_am) "
                        f"VALUES (?, {', '.join('?' for _ in spalten)}, ?, ?)",
                        (akte_id, *(werte[k] for k in spalten), jetzt, jetzt))
        else:
            con.execute(f"UPDATE kalender SET {', '.join(f'{k} = ?' for k in spalten)}, geaendert_am = ? WHERE id = ?",
                        (*(werte[k] for k in spalten), jetzt, eintrag_id))
    return liste(con, akte_id, heute)


def _uhrzeit(text: str | None) -> str | None:
    if not text:
        return None
    m = _UHRZEIT.match(text)
    if not m:
        raise ValueError("Uhrzeit bitte als HH:MM, z. B. 10:30.")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _eintrag(con: sqlite3.Connection, eintrag_id: int) -> sqlite3.Row:
    z = con.execute("SELECT * FROM kalender WHERE id = ?", (eintrag_id,)).fetchone()
    if z is None:
        raise LookupError(f"Eintrag {eintrag_id} gibt es nicht.")
    return z


def erledigen(con: sqlite3.Connection, eintrag_id: int, erledigt: bool = True, vermerk: str = "",
              heute: date | None = None) -> list[dict]:
    """Frist oder Wiedervorlage erledigen bzw. wieder öffnen. Termine werden nicht erledigt (``termin_zustand``)."""
    z = _eintrag(con, eintrag_id)
    if z["art"] == "termin":
        raise ValueError("Termine werden nicht erledigt: Sie finden statt, werden aufgehoben oder verlegt.")
    with con:
        con.execute("UPDATE kalender SET erledigt_am = ?, erledigt_vermerk = ?, zustand = ?, geaendert_am = ? "
                    "WHERE id = ?",
                    (_jetzt() if erledigt else None, " ".join(vermerk.split()) or None if erledigt else None,
                     "erledigt" if erledigt else None, _jetzt(), eintrag_id))
    return liste(con, z["akte_id"], heute)


def termin_zustand(con: sqlite3.Connection, eintrag_id: int, zustand: str, vermerk: str = "",
                   neu: dict | None = None, heute: date | None = None) -> list[dict]:
    """Termin aufheben, verlegen oder wieder als geplant führen.

    Beim Verlegen nennt ``neu`` den neuen Termin ({datum, uhrzeit, bis_uhrzeit, ort, dokument_id, fundstelle});
    JuraBox legt ihn als Folgetermin an, der auf den alten verweist. Titel, Verfahren und Notiz werden übernommen,
    Uhrzeit und Ort, wenn ``neu`` keine nennt.
    """
    z = _eintrag(con, eintrag_id)
    if z["art"] != "termin":
        raise ValueError("Nur Termine werden aufgehoben oder verlegt; Fristen werden erledigt oder verlängert.")
    if zustand not in TERMIN_ZUSTAENDE:
        raise ValueError("Bitte wählen: geplant, stattgefunden, aufgehoben oder verlegt.")
    vermerk = " ".join(vermerk.split())
    if zustand == "verlegt":
        if not neu or not neu.get("datum"):
            raise ValueError("Bitte das neue Datum des Termins angeben.")
        daten = {"art": "termin", "titel": z["titel"], "verfahren_id": z["verfahren_id"], "notiz": z["notiz"],
                 "datum": neu["datum"], "uhrzeit": neu.get("uhrzeit", z["uhrzeit"]),
                 "bis_uhrzeit": neu.get("bis_uhrzeit"), "ort": neu.get("ort") or z["ort"],
                 "dokument_id": neu.get("dokument_id"), "fundstelle": neu.get("fundstelle")}
        if _datum(daten["datum"], "Neues Datum") == z["datum"] and _uhrzeit(daten["uhrzeit"]) == z["uhrzeit"]:
            raise ValueError("Der neue Termin ist derselbe wie der alte.")
        speichern(con, z["akte_id"], daten, heute=heute)
        neu_id = con.execute("SELECT max(id) FROM kalender WHERE akte_id = ?", (z["akte_id"],)).fetchone()[0]
        with con:
            con.execute("UPDATE kalender SET verlegt_von = ? WHERE id = ?", (eintrag_id, neu_id))
    abgeschlossen = zustand != "geplant"
    with con:
        con.execute("UPDATE kalender SET zustand = ?, erledigt_am = ?, erledigt_vermerk = ?, geaendert_am = ? "
                    "WHERE id = ?",
                    (zustand if abgeschlossen else None, _jetzt() if abgeschlossen else None,
                     (vermerk or None) if abgeschlossen else None, _jetzt(), eintrag_id))
    return liste(con, z["akte_id"], heute)


def verlaengern(con: sqlite3.Connection, eintrag_id: int, datum: str, vermerk: str = "",
                dokument_id: int | None = None, fundstelle: dict | None = None,
                heute: date | None = None) -> list[dict]:
    """Neues Ende einer Frist (Fristverlängerung) bzw. neuer Tag einer Wiedervorlage.

    Das alte Datum, die alte Berechnung und der Beleg bleiben im Verlauf; die Vorfristen rücken um denselben Abstand
    mit.
    """
    z = _eintrag(con, eintrag_id)
    if z["art"] == "termin":
        raise ValueError("Termine werden verlegt, nicht verlängert.")
    if z["erledigt_am"]:
        raise ValueError("Der Eintrag ist erledigt; bitte zuerst wieder öffnen.")
    neu = _datum(datum, "Neues Datum")
    if neu == z["datum"]:
        raise ValueError("Das neue Datum ist dasselbe wie das bisherige.")
    abstand = date.fromisoformat(neu) - date.fromisoformat(z["datum"])
    vorfristen = [v for v in ((date.fromisoformat(z[k]) + abstand).isoformat() for k in ("vorfrist", "vorfrist2")
                              if z[k]) if v < neu] + [None, None]
    if dokument_id is not None and con.execute("SELECT 1 FROM dokument WHERE id = ? AND akte_id = ?",
                                               (dokument_id, z["akte_id"])).fetchone() is None:
        raise ValueError("Das Dokument gehört nicht zu dieser Akte.")
    was = ("verschoben" if z["art"] == "wiedervorlage" else "verlängert" if abstand.days > 0 else "verkürzt")
    verlauf = json.loads(z["verlauf"]) if z["verlauf"] else []
    verlauf.append({"am": _jetzt(), "was": was, "alt": z["datum"], "neu": neu,
                    "alt_vorfristen": [v for v in (z["vorfrist"], z["vorfrist2"]) if v],
                    "alt_berechnung": json.loads(z["berechnung"]) if z["berechnung"] else None,
                    "vermerk": " ".join(vermerk.split()) or None, "dokument_id": dokument_id,
                    "fundstelle": fundstelle or None})
    with con:
        con.execute("UPDATE kalender SET datum = ?, vorfrist = ?, vorfrist2 = ?, berechnung = NULL, verlauf = ?, "
                    "geaendert_am = ? WHERE id = ?",
                    (neu, *vorfristen[:2], json.dumps(verlauf, ensure_ascii=False), _jetzt(), eintrag_id))
    return liste(con, z["akte_id"], heute)


def loeschen(con: sqlite3.Connection, eintrag_id: int, heute: date | None = None) -> list[dict]:
    z = _eintrag(con, eintrag_id)
    with con:
        con.execute("DELETE FROM kalender WHERE id = ?", (eintrag_id,))
    return liste(con, z["akte_id"], heute)


def naechste(con: sqlite3.Connection, tage: int | None = None, limit: int = 50,
             heute: date | None = None) -> list[dict]:
    """Offene Einträge aller Akten nach Datum, abgelaufene zuerst; mit ``tage`` nur bis heute + tage.
    Vergangene Termine haben stattgefunden und gehören nicht dazu."""
    heute = heute or date.today()
    bis = (heute + timedelta(days=tage)).isoformat() if tage is not None else "9999-12-31"
    zeilen = con.execute(
        """SELECT k.*, a.name AS akte, a.aktenzeichen, COALESCE(d.titel, d.dateiname) AS dokument FROM kalender k
           JOIN akte a ON a.id = k.akte_id LEFT JOIN dokument d ON d.id = k.dokument_id
           WHERE k.erledigt_am IS NULL AND k.datum <= ? AND a.status != 'abgeschlossen'
             AND NOT (k.art = 'termin' AND k.datum < ?)
           ORDER BY k.datum, k.uhrzeit, k.id LIMIT ?""", (bis, heute.isoformat(), limit)).fetchall()
    return _verknuepfen(con, [_zeile(z, heute) for z in zeilen])


def naechste_je_akte(con: sqlite3.Connection, heute: date | None = None) -> dict[int, dict]:
    """Für die Aktenübersicht: je Akte der früheste offene Eintrag."""
    heute = heute or date.today()
    ergebnis: dict[int, dict] = {}
    for z in con.execute("SELECT * FROM kalender WHERE erledigt_am IS NULL AND NOT (art = 'termin' AND datum < ?) "
                         "ORDER BY datum, uhrzeit, id", (heute.isoformat(),)):
        if z["akte_id"] not in ergebnis:
            e = _zeile(z, heute)
            ergebnis[z["akte_id"]] = {k: e[k] for k in ("id", "art", "art_text", "titel", "datum", "uhrzeit",
                                                         "in_tagen", "lage")}
    return ergebnis


# --------------------------------------------------------------------------- Vorschläge aus einem Dokument

_ZAHLWORT = {"einer": 1, "einem": 1, "ein": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6,
             "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "vierzehn": 14,
             "einundzwanzig": 21, "dreißig": 30}
_EINHEIT = {"tag": "tage", "woche": "wochen", "monat": "monate", "jahr": "jahre"}
_DAUER = re.compile(
    r"\b(?:binnen|innerhalb|in)\s+(?:einer\s+(?:\w+\s+)?Frist\s+von\s+)?"
    r"(?P<anzahl>\d{1,3}|" + "|".join(_ZAHLWORT) + r")\s+"
    r"(?P<einheit>Tag|Woche|Monat|Jahr)(?:en|es|e|n|s)?\s+"
    r"(?:nach|seit|ab)\s+(?:der\s+|dem\s+)?(?P<bezug>Zustellung|Zugang|Erhalt|Verkündung)",
    re.IGNORECASE)
_DATUM = r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})"
_BIS = re.compile(r"\b(?:bis zum|bis spätestens|spätestens bis zum|spätestens am|bis)\s+" + _DATUM)
_ZUGESTELLT = re.compile(r"\bzugestellt\s+am\s+" + _DATUM, re.IGNORECASE)
_TERMIN = re.compile(
    r"(?:(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),?\s+)?(?:den\s+)?" + _DATUM +
    r",?\s+(?:um\s+)?(\d{1,2})[:.](\d{2})\s*Uhr(?:,?\s*(?:im\s+)?((?:Sitzungs)?[Ss]aal\s*[\w./-]+|Raum\s*[\w./-]+))?")
_AUFGEHOBEN = re.compile(r"Termin\s+(?:vom|am)\s+" + _DATUM + r"[^.]{0,120}?\b(aufgehoben|verlegt)")
_FRIST_WORTE = re.compile(r"Frist|Gelegenheit|aufgegeben|erwidern|Stellungnahme|nachzureichen|einzureichen|"
                          r"vorzulegen|zu begleichen|widersprechen", re.IGNORECASE)


def _iso(m: re.Match, start: int = 1) -> str | None:
    try:
        return date(int(m.group(start + 2)), int(m.group(start + 1)), int(m.group(start))).isoformat()
    except ValueError:
        return None


def _titel_frist(satz: str) -> str:
    s = satz.casefold()
    if "widersprechen" in s or "widerspruch" in s:
        return "Widerspruchsfrist" + (" (Mahnbescheid)" if "bescheid" in s else "")
    if "einspruch" in s:
        return "Einspruchsfrist"
    if "berufung" in s and "begründ" in s:
        return "Berufungsbegründungsfrist"
    if "berufung" in s:
        return "Berufungsfrist"
    if "verteidigungsbereitschaft" in s or "verteidigen" in s:
        return "Anzeige der Verteidigungsbereitschaft"
    if "anspruchsbegründung" in s and "erwider" in s:
        return "Erwiderung auf die Anspruchsbegründung"
    if "klage" in s and "erwider" in s:
        return "Klageerwiderung"
    if "erwider" in s:
        return "Erwiderung"
    if "stellungnahme" in s or "stellung zu nehmen" in s:
        return "Stellungnahme"
    return "Frist laut Dokument"


def _titel_termin(kontext: str) -> str:
    s = kontext.casefold()
    if "güteverhandlung" in s and "frühen ersten termin" in s:
        return "Güteverhandlung und früher erster Termin"
    if "güteverhandlung" in s:
        return "Güteverhandlung"
    if "verkündung" in s:
        return "Verkündungstermin"
    if "beweisaufnahme" in s:
        return "Beweisaufnahme"
    if "haupttermin" in s:
        return "Haupttermin"
    if "mündliche" in s and "verhandlung" in s:
        return "Mündliche Verhandlung"
    return "Gerichtstermin"


# Satzende: Punkt, danach ein Großbuchstabe; „Abs. 2“, „Nr. 3“ oder „S. 4“ enden keinen Satz.
_SATZENDE = re.compile(r"(?<!\bAbs)(?<!\bNr)(?<!\bS)(?<!\bArt)(?<!\bvgl)(?<!\bDr)(?<!\bz\.B)\.\s+(?=[A-ZÄÖÜ„])")


def _satz(text: str, start: int, ende: int) -> str:
    """Der Satz um die Fundstelle, für die Anzeige gekürzt."""
    links = max([m.end() for m in _SATZENDE.finditer(text, 0, start)] + [text.rfind("\n", 0, start) + 1, 0])
    rechts = next((m.start() + 1 for m in _SATZENDE.finditer(text, ende)), len(text))
    satz = text[links:rechts].strip()
    return satz if len(satz) <= 320 else satz[:317] + " …"


def vorschlaege(abschnitte: list[dict], dokument_datum: str | None = None, land: str = "BY",
                vorhandene: list[dict] | None = None) -> list[dict]:
    """Fristen und Termine, die ein Dokument nennt, als Vorschläge mit Fundstelle.

    ``abschnitte``: [{"nr", "seite", "text"}] in Dokumentreihenfolge. Fristen „binnen zwei Wochen nach Zustellung“
    werden ab dem Zustellungsdatum berechnet, wenn das Dokument eines nennt („zugestellt am …“); sonst bleibt der
    Bezugstag offen und muss eingetragen werden. ``vorhandene`` (Einträge der Akte) verhindern doppelte Vorschläge
    und machen aus „Termin vom … aufgehoben“ einen Vorschlag, den passenden Termin aufzuheben bzw. (mit dem neuen
    Termin aus dem Dokument) zu verlegen.
    """
    vorhandene = vorhandene or []
    zustellung = None
    for a in abschnitte:
        if m := _ZUGESTELLT.search(a["text"]):
            zustellung = {"datum": _iso(m), "fundstelle": {"abschnitt": a["nr"], "seite": a.get("seite"),
                                                            "text": _satz(a["text"], m.start(), m.end())}}
    ergebnis: list[dict] = []
    for i, a in enumerate(abschnitte):
        text = a["text"]
        for m in _DAUER.finditer(text):
            anzahl_text = m.group("anzahl").casefold()
            anzahl = int(anzahl_text) if anzahl_text.isdigit() else _ZAHLWORT[anzahl_text]
            einheit = _EINHEIT[m.group("einheit").casefold()]
            satz = _satz(text, m.start(), m.end())
            v = {"art": "frist", "titel": _titel_frist(satz),
                 "fundstelle": {"abschnitt": a["nr"], "seite": a.get("seite"), "text": satz},
                 "dauer": {"anzahl": anzahl, "einheit": einheit, "bezug": m.group("bezug")}}
            if zustellung and zustellung["datum"] and m.group("bezug").casefold() in ("zustellung", "zugang", "erhalt"):
                r = berechne(zustellung["datum"], anzahl, einheit, land)
                v["berechnung"] = r
                v["datum"] = r["ende"]
                v["bezug_fundstelle"] = zustellung["fundstelle"]
                if (einheit != "tage" or anzahl >= 14) and (date.fromisoformat(r["ende"]) - timedelta(days=7)) > \
                        date.fromisoformat(r["bezugstag"]):
                    v["vorfrist"] = (date.fromisoformat(r["ende"]) - timedelta(days=7)).isoformat()
            else:
                v["datum"] = None
                v["hinweis"] = (f"Bezugstag ({m.group('bezug')}) steht nicht im Dokument; bitte eintragen, "
                                "dann rechnet JuraBox das Fristende.")
            ergebnis.append(v)
        for m in _BIS.finditer(text):
            datum = _iso(m)
            satz = _satz(text, m.start(), m.end())
            if not datum or not _FRIST_WORTE.search(satz) or (dokument_datum and datum < dokument_datum):
                continue  # z. B. eine im Schriftsatz geschilderte, längst abgelaufene Frist
            ergebnis.append({"art": "frist", "titel": _titel_frist(satz), "datum": datum,
                             "fundstelle": {"abschnitt": a["nr"], "seite": a.get("seite"), "text": satz}})
        kontext = " ".join(x["text"] for x in abschnitte[max(0, i - 1): i + 1])
        for m in _TERMIN.finditer(text):
            datum = _iso(m, 2)
            if not datum or "termin" not in kontext.casefold() or (dokument_datum and datum < dokument_datum):
                continue
            satz = _satz(text, m.start(), m.end())
            if "termin" not in satz.casefold() and i > 0:
                satz = f"{abschnitte[i - 1]['text'].strip()} {satz}"  # „Termin … wird bestimmt auf“ steht davor
            ergebnis.append({"art": "termin", "titel": _titel_termin(kontext), "datum": datum,
                             "uhrzeit": f"{int(m.group(5)):02d}:{m.group(6)}", "ort": m.group(7) or "",
                             "fundstelle": {"abschnitt": a["nr"], "seite": a.get("seite"), "text": satz}})
        for m in _AUFGEHOBEN.finditer(text):
            datum = _iso(m)
            passend = [e for e in vorhandene if e["art"] == "termin" and e["datum"] == datum and not e["erledigt_am"]]
            if passend:
                ergebnis.append({"art": "zustand", "zustand": m.group(4), "eintrag_id": passend[0]["id"],
                                 "titel": passend[0]["titel"], "datum": datum, "vermerk": f"Termin {m.group(4)}",
                                 "fundstelle": {"abschnitt": a["nr"], "seite": a.get("seite"),
                                                "text": _satz(text, m.start(), m.end())}})
    # Nennt das Dokument nach der Aufhebung einen neuen Termin, ist der alte verlegt: beides wird ein Vorschlag.
    for i, v in enumerate(ergebnis):
        if v["art"] != "zustand":
            continue
        neu = next((w for w in ergebnis[i + 1:] if w["art"] == "termin" and w["datum"] > v["datum"]), None)
        if neu:
            ergebnis.remove(neu)
            v["zustand"] = "verlegt"
            v["neu"] = {k: neu[k] for k in ("titel", "datum", "uhrzeit", "ort", "fundstelle")}
    # Schon eingetragene (gleiche Art und gleiches Datum) nicht noch einmal vorschlagen.
    belegt = {(e["art"], e["datum"]) for e in vorhandene}
    eindeutig: list[dict] = []
    for v in ergebnis:
        schluessel = (v["art"], v.get("datum"))
        if v["art"] != "zustand" and v.get("datum") and schluessel in belegt:
            continue
        if any((w["art"], w.get("datum"), w["fundstelle"]["abschnitt"]) == (*schluessel, v["fundstelle"]["abschnitt"])
               for w in eindeutig):
            continue
        eindeutig.append(v)
    return eindeutig


def dokument_vorschlaege(con: sqlite3.Connection, dokument_id: int, land: str = "BY") -> dict:
    d = con.execute("SELECT id, akte_id, dateiname, datum FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if d is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    abschnitte = [dict(z) for z in con.execute(
        "SELECT nr, seite, text FROM abschnitt WHERE dokument_id = ? ORDER BY nr", (dokument_id,))]
    vorhandene = [dict(z) for z in con.execute("SELECT * FROM kalender WHERE akte_id = ?", (d["akte_id"],))]
    vorschlag = vorschlaege(abschnitte, d["datum"], land, vorhandene)
    for v in vorschlag:
        v["dokument_id"] = dokument_id
    return {"dokument_id": dokument_id, "dateiname": d["dateiname"], "vorschlaege": vorschlag}
