"""Terminmodus (Arbeitsfenster Stufe 2): Sitzungsblatt und Terminsnotizen einer Akte.

- Sitzungsblatt: Anträge und Streitpunkte der Akte mit Einschätzung (Ampel) und Fundstellen. Jeder Punkt trägt seine
  Belege (Dokument und Abschnitt); ein Punkt ohne Beleg wird als solcher angezeigt, nicht ergänzt.
- Sitzung: ein Gerichtstermin, der im Arbeitsfenster mitgeschrieben wird. Notizen bekommen die Uhrzeit, zu der sie
  gespeichert wurden. „Termin beenden“ übernimmt auf Wunsch das Protokoll als Aktennotiz, die Dauer in die
  Zeiterfassung und erkannte Fristen in den Kalender; nichts davon geschieht ohne ausdrückliche Auswahl.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime

from .. import zeiterfassung
from ..rechner.feiertage import feiertage
from . import kalender, notizen

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sitzungspunkt (
    id           INTEGER PRIMARY KEY,
    akte_id      INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    art          TEXT NOT NULL,
    text         TEXT NOT NULL,
    ampel        TEXT,
    belege       TEXT NOT NULL DEFAULT '[]',
    herkunft     TEXT NOT NULL DEFAULT 'eigen',
    reihenfolge  INTEGER NOT NULL DEFAULT 0,
    angelegt_am  TEXT NOT NULL,
    geaendert_am TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sitzungspunkt_akte ON sitzungspunkt (akte_id);
CREATE TABLE IF NOT EXISTS sitzung (
    id           INTEGER PRIMARY KEY,
    akte_id      INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    kalender_id  INTEGER REFERENCES kalender(id) ON DELETE SET NULL,
    titel        TEXT NOT NULL,
    beginn       TEXT NOT NULL,
    ende         TEXT,
    uebernommen  TEXT
);
CREATE INDEX IF NOT EXISTS sitzung_akte ON sitzung (akte_id);
CREATE TABLE IF NOT EXISTS sitzung_notiz (
    id           INTEGER PRIMARY KEY,
    sitzung_id   INTEGER NOT NULL REFERENCES sitzung(id) ON DELETE CASCADE,
    zeit         TEXT NOT NULL,
    art          TEXT NOT NULL,
    text         TEXT NOT NULL,
    dokument_id  INTEGER REFERENCES dokument(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS sitzung_notiz_sitzung ON sitzung_notiz (sitzung_id);
"""

PUNKT_ARTEN = {"antrag": "Antrag", "streitpunkt": "Streitpunkt"}
AMPELN = {"rot": "kritisch", "gelb": "offen", "gruen": "günstig"}
NOTIZ_ARTEN = {
    "notiz": "Notiz",
    "hinweis": "Hinweis des Gerichts",
    "vergleich": "Vergleichsvorschlag",
    "zeuge": "Zeugenaussage",
    "auflage": "Frist / Auflage",
}

_ZAHLWORTE = {"ein": 1, "eine": 1, "einen": 1, "einer": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6,
              "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "zwölf": 12, "vierzehn": 14}
_EINHEIT = {"tag": "tage", "tage": "tage", "tagen": "tage", "woche": "wochen", "wochen": "wochen",
            "monat": "monate", "monate": "monate", "monaten": "monate", "monats": "monate"}
_FRIST = re.compile(r"\b(\d{1,3}|" + "|".join(_ZAHLWORTE) + r")\s+(" + "|".join(_EINHEIT) + r")\b", re.IGNORECASE)
_MONATE = {"januar": 1, "jan": 1, "jänner": 1, "februar": 2, "feb": 2, "märz": 3, "mär": 3, "maerz": 3, "april": 4,
           "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
           "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11, "dezember": 12, "dez": 12}
# „15.12.2026“, „15.12.26“, „15.12.“, „15. Dezember 2026“, „15. Dez.“
_DATUM = re.compile(r"(?<![\d.])(\d{1,2})\.\s*(?:(\d{1,2})\.|(" + "|".join(sorted(_MONATE, key=len, reverse=True))
                    + r")\b\.?)\s*(\d{4}|\d{2}(?!\d))?", re.IGNORECASE)
# Fristbeginn durch ein späteres Ereignis: „ab Zustellung des Protokolls“, „nach Zugang des Gutachtens“.
_EREIGNIS = re.compile(r"\b(?:ab|nach|mit|seit|von)\s+(?:der\s+|dem\s+)?"
                       r"((?:Zustellung|Zugang|Erhalt|Eingang|Übersendung|Uebersendung|Bekanntgabe|Vorlage|Mitteilung|Rechtskraft)(?:\s+(?:des|der|dieses|eines|einer)"
                       r"(?:\s+[A-ZÄÖÜ][\wäöüß-]*)?|\s+[A-ZÄÖÜ][\wäöüß-]*)?)", re.IGNORECASE)
_WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    spalten = {z[1] for z in con.execute("PRAGMA table_info(sitzung)")}
    if "person_id" not in spalten:
        # Wer den Termin wahrnimmt (Person aus „Eigene Daten“); der Name bleibt erhalten, falls sie später wegfällt.
        con.execute("ALTER TABLE sitzung ADD COLUMN person_id INTEGER")
        con.execute("ALTER TABLE sitzung ADD COLUMN wahrgenommen_von TEXT")
    con.commit()


def _person_name(con: sqlite3.Connection, person_id: int) -> str:
    try:
        z = con.execute("SELECT daten FROM eigene_person WHERE id = ?", (person_id,)).fetchone()
    except sqlite3.OperationalError:
        z = None
    if z is None:
        raise LookupError("Diese Person gibt es in „Eigene Daten“ nicht.")
    d = json.loads(z["daten"])
    return " ".join(t for t in (d.get("titel"), d.get("vorname"), d.get("nachname")) if t) or "(ohne Namen)"


def _jetzt() -> datetime:
    return datetime.now().replace(microsecond=0)


def _einzeilig(text) -> str:
    return " ".join(str(text or "").split())


def _mehrzeilig(text) -> str:
    return "\n".join(z.rstrip() for z in str(text or "").strip().splitlines())


def _akte_pruefen(con: sqlite3.Connection, akte_id: int) -> None:
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")


# --------------------------------------------------------------------------- Sitzungsblatt


def _belege(con: sqlite3.Connection, akte_id: int, roh) -> list[dict]:
    """Belege eines Punkts: nur Dokumente dieser Akte, mit Abschnitt (aus der Analyse) oder Randnummer (von Hand);
    Bezeichnung wie in der Akte."""
    aus: list[dict] = []
    for b in roh or []:
        dok = con.execute("SELECT id, COALESCE(titel, dateiname) AS name FROM dokument WHERE id = ? AND akte_id = ?",
                          (int(b["dokument_id"]), akte_id)).fetchone()
        if dok is None:
            raise ValueError("Ein Beleg verweist auf ein Dokument, das nicht zu dieser Akte gehört.")
        abschnitt, rn = b.get("abschnitt"), b.get("rn")
        abschnitt = None if abschnitt in (None, "") else int(abschnitt)
        rn = None if rn in (None, "") else int(rn)
        name = _einzeilig(b.get("bezeichnung")) or (dok["name"] + (f", Rn. {rn}" if rn is not None else ""))
        aus.append({"dokument_id": dok["id"], "abschnitt": abschnitt, "rn": rn, "bezeichnung": name})
    return aus


def _punkt(z: sqlite3.Row) -> dict:
    return dict(z) | {"belege": json.loads(z["belege"] or "[]")}


def punkte(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    """Anträge zuerst, dann Streitpunkte, je in der gewählten Reihenfolge."""
    zeilen = con.execute(
        "SELECT * FROM sitzungspunkt WHERE akte_id = ? "
        "ORDER BY CASE art WHEN 'antrag' THEN 0 ELSE 1 END, reihenfolge, id", (akte_id,))
    return [_punkt(z) for z in zeilen]


def punkt_speichern(con: sqlite3.Connection, akte_id: int, daten: dict, punkt_id: int | None = None) -> list[dict]:
    """Legt einen Antrag oder Streitpunkt an oder ändert ihn. ``daten``: art, text, ampel, belege, herkunft."""
    _akte_pruefen(con, akte_id)
    alt = None
    if punkt_id is not None:
        alt = con.execute("SELECT * FROM sitzungspunkt WHERE id = ? AND akte_id = ?", (punkt_id, akte_id)).fetchone()
        if alt is None:
            raise LookupError(f"Punkt {punkt_id} gibt es in dieser Akte nicht.")
    art = daten.get("art", alt["art"] if alt else "streitpunkt")
    if art not in PUNKT_ARTEN:
        raise ValueError("Bitte wählen: Antrag oder Streitpunkt.")
    text = _mehrzeilig(daten.get("text", alt["text"] if alt else ""))
    if not text:
        raise ValueError("Bitte den Antrag bzw. Streitpunkt eintragen.")
    ampel = daten.get("ampel", alt["ampel"] if alt else None) or None
    if ampel is not None and ampel not in AMPELN:
        raise ValueError("Unbekannte Einschätzung.")
    belege = (_belege(con, akte_id, daten["belege"]) if "belege" in daten
              else json.loads(alt["belege"]) if alt else [])
    herkunft = "ki" if daten.get("herkunft", alt["herkunft"] if alt else "eigen") == "ki" else "eigen"
    jetzt = _jetzt().isoformat()
    with con:
        if alt is None:
            reihe = con.execute("SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM sitzungspunkt WHERE akte_id = ? "
                                "AND art = ?", (akte_id, art)).fetchone()[0]
            con.execute("INSERT INTO sitzungspunkt (akte_id, art, text, ampel, belege, herkunft, reihenfolge, "
                        "angelegt_am, geaendert_am) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (akte_id, art, text, ampel, json.dumps(belege, ensure_ascii=False), herkunft, reihe,
                         jetzt, jetzt))
        else:
            con.execute("UPDATE sitzungspunkt SET art = ?, text = ?, ampel = ?, belege = ?, herkunft = ?, "
                        "geaendert_am = ? WHERE id = ?",
                        (art, text, ampel, json.dumps(belege, ensure_ascii=False), herkunft, jetzt, punkt_id))
    return punkte(con, akte_id)


def punkt_loeschen(con: sqlite3.Connection, punkt_id: int) -> list[dict]:
    z = con.execute("SELECT akte_id FROM sitzungspunkt WHERE id = ?", (punkt_id,)).fetchone()
    if z is None:
        raise LookupError(f"Punkt {punkt_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM sitzungspunkt WHERE id = ?", (punkt_id,))
    return punkte(con, z["akte_id"])


def punkt_verschieben(con: sqlite3.Connection, punkt_id: int, richtung: int) -> list[dict]:
    """Einen Punkt innerhalb seiner Art eine Stelle nach oben (-1) oder unten (+1) schieben."""
    z = con.execute("SELECT akte_id, art FROM sitzungspunkt WHERE id = ?", (punkt_id,)).fetchone()
    if z is None:
        raise LookupError(f"Punkt {punkt_id} gibt es nicht.")
    ids = [p["id"] for p in punkte(con, z["akte_id"]) if p["art"] == z["art"]]
    i = ids.index(punkt_id)
    j = i + (1 if richtung > 0 else -1)
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
        with con:
            for n, pid in enumerate(ids, 1):
                con.execute("UPDATE sitzungspunkt SET reihenfolge = ? WHERE id = ?", (n, pid))
    return punkte(con, z["akte_id"])


# --------------------------------------------------------------------------- Sitzung (Termin mitschreiben)


def _sitzung(con: sqlite3.Connection, sitzung_id: int) -> dict:
    z = con.execute("SELECT * FROM sitzung WHERE id = ?", (sitzung_id,)).fetchone()
    if z is None:
        raise LookupError(f"Sitzung {sitzung_id} gibt es nicht.")
    notizen_ = [dict(n) | {"art_text": NOTIZ_ARTEN.get(n["art"], n["art"])} for n in con.execute(
        """SELECT n.*, COALESCE(d.titel, d.dateiname) AS dokument FROM sitzung_notiz n
           LEFT JOIN dokument d ON d.id = n.dokument_id WHERE n.sitzung_id = ? ORDER BY n.zeit, n.id""",
        (sitzung_id,))]
    return dict(z) | {"uebernommen": json.loads(z["uebernommen"]) if z["uebernommen"] else None, "notizen": notizen_}


def aktiv(con: sqlite3.Connection, akte_id: int) -> dict | None:
    """Die laufende Sitzung der Akte (begonnen, nicht beendet), sonst None."""
    z = con.execute("SELECT id FROM sitzung WHERE akte_id = ? AND ende IS NULL ORDER BY beginn DESC LIMIT 1",
                    (akte_id,)).fetchone()
    return _sitzung(con, z["id"]) if z else None


def sitzungen(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    """Alle Sitzungen der Akte, neueste zuerst, mit ihren Notizen."""
    return [_sitzung(con, z["id"]) for z in con.execute(
        "SELECT id FROM sitzung WHERE akte_id = ? ORDER BY beginn DESC, id DESC", (akte_id,))]


def termine_heute(con: sqlite3.Connection, akte_id: int, heute: date | None = None) -> list[dict]:
    """Termine der Akte am heutigen Tag, zur Auswahl beim Beginnen."""
    tag = (heute or date.today()).isoformat()
    return [dict(z) for z in con.execute(
        "SELECT id, titel, datum, uhrzeit, ort FROM kalender WHERE akte_id = ? AND art = 'termin' AND datum = ? "
        "ORDER BY uhrzeit", (akte_id, tag))]


def beginnen(con: sqlite3.Connection, akte_id: int, kalender_id: int | None = None, titel: str = "",
             jetzt: datetime | None = None, person_id: int | None = None) -> dict:
    """Beginnt eine Sitzung; läuft schon eine, bleibt es bei ihr. ``person_id``: wer den Termin wahrnimmt
    (Person aus „Eigene Daten“); ohne Angabe der Sachbearbeiter der Akte."""
    _akte_pruefen(con, akte_id)
    laufend = aktiv(con, akte_id)
    if laufend is not None:
        return laufend
    name = _einzeilig(titel)
    if kalender_id is not None:
        k = con.execute("SELECT titel, ort FROM kalender WHERE id = ? AND akte_id = ?",
                        (kalender_id, akte_id)).fetchone()
        if k is None:
            raise LookupError(f"Termin {kalender_id} gibt es in dieser Akte nicht.")
        name = name or " · ".join(t for t in (k["titel"], k["ort"]) if t)
    person: int | None = None
    wer: str | None = None
    if person_id not in (None, ""):
        person = int(person_id)
        wer = _person_name(con, person)
    else:
        sb = con.execute("SELECT sachbearbeiter_id FROM akte WHERE id = ?", (akte_id,)).fetchone()[0]
        try:
            wer, person = (_person_name(con, sb), sb) if sb is not None else (None, None)
        except LookupError:
            pass
    with con:
        sid = con.execute(
            "INSERT INTO sitzung (akte_id, kalender_id, titel, beginn, person_id, wahrgenommen_von)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (akte_id, kalender_id, name or "Termin", (jetzt or _jetzt()).isoformat(), person, wer)).lastrowid
    return _sitzung(con, sid)


def _offen(con: sqlite3.Connection, sitzung_id: int) -> sqlite3.Row:
    z = con.execute("SELECT * FROM sitzung WHERE id = ?", (sitzung_id,)).fetchone()
    if z is None:
        raise LookupError(f"Sitzung {sitzung_id} gibt es nicht.")
    if z["ende"] is not None:
        raise ValueError("Dieser Termin ist schon beendet.")
    return z


def notiz_anlegen(con: sqlite3.Connection, sitzung_id: int, text: str, art: str = "notiz",
                  dokument_id: int | None = None, jetzt: datetime | None = None) -> dict:
    s = _offen(con, sitzung_id)
    text = _mehrzeilig(text)
    if not text:
        raise ValueError("Die Notiz ist leer.")
    if art not in NOTIZ_ARTEN:
        raise ValueError("Unbekannte Art der Notiz.")
    if dokument_id is not None and con.execute("SELECT 1 FROM dokument WHERE id = ? AND akte_id = ?",
                                               (dokument_id, s["akte_id"])).fetchone() is None:
        raise ValueError("Das Dokument gehört nicht zu dieser Akte.")
    with con:
        con.execute("INSERT INTO sitzung_notiz (sitzung_id, zeit, art, text, dokument_id) VALUES (?, ?, ?, ?, ?)",
                    (sitzung_id, (jetzt or _jetzt()).isoformat(), art, text, dokument_id))
    return _sitzung(con, sitzung_id)


def notiz_aendern(con: sqlite3.Connection, notiz_id: int, text: str, art: str | None = None) -> dict:
    z = con.execute("SELECT sitzung_id, art FROM sitzung_notiz WHERE id = ?", (notiz_id,)).fetchone()
    if z is None:
        raise LookupError(f"Notiz {notiz_id} gibt es nicht.")
    text = _mehrzeilig(text)
    if not text:
        raise ValueError("Die Notiz ist leer.")
    art = art or z["art"]
    if art not in NOTIZ_ARTEN:
        raise ValueError("Unbekannte Art der Notiz.")
    with con:
        con.execute("UPDATE sitzung_notiz SET text = ?, art = ? WHERE id = ?", (text, art, notiz_id))
    return _sitzung(con, z["sitzung_id"])


def notiz_loeschen(con: sqlite3.Connection, notiz_id: int) -> dict:
    z = con.execute("SELECT sitzung_id FROM sitzung_notiz WHERE id = ?", (notiz_id,)).fetchone()
    if z is None:
        raise LookupError(f"Notiz {notiz_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM sitzung_notiz WHERE id = ?", (notiz_id,))
    return _sitzung(con, z["sitzung_id"])


def _uhrzeit(iso: str) -> str:
    return iso[11:16]


def _datum_de(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}"


def protokoll(s: dict, ende: str | None = None) -> str:
    """Terminsnotizen als Text für die Aktennotiz: Kopfzeile, dann je Notiz Uhrzeit, Art und Text."""
    bis = ende or s.get("ende")
    kopf = f"Terminsprotokoll {_datum_de(s['beginn'])}, {_uhrzeit(s['beginn'])}"
    kopf += f"–{_uhrzeit(bis)} Uhr" if bis else " Uhr"
    if s.get("titel"):
        kopf += f" ({s['titel']})"
    if s.get("wahrgenommen_von"):
        kopf += f", wahrgenommen von {s['wahrgenommen_von']}"
    zeilen = [kopf]
    for n in s["notizen"]:
        art = "" if n["art"] == "notiz" else f"{NOTIZ_ARTEN[n['art']]}: "
        bezug = f" [zu {n['dokument']}]" if n.get("dokument") else ""
        text = n["text"].replace("\n", "\n      ")
        zeilen.append(f"{_uhrzeit(n['zeit'])} {art}{text}{bezug}")
    return "\n".join(zeilen)


def _festes_datum(text: str, termintag: date) -> date | None:
    """Erstes Datum im Text, das nach dem Termintag liegt; ohne Jahr das nächste passende nach dem Termin.
    Frühere Daten („Schreiben vom 23.06.2025“) sind keine Fristen."""
    for t in _DATUM.finditer(text):
        tag_, monat = int(t.group(1)), int(t.group(2)) if t.group(2) else _MONATE[t.group(3).lower()]
        jahr_text = t.group(4)
        jahre = ([int(jahr_text) + (2000 if len(jahr_text) == 2 else 0)] if jahr_text
                 else [termintag.year, termintag.year + 1])
        for jahr in jahre:
            try:
                d = date(jahr, monat, tag_)
            except ValueError:
                break
            if d > termintag:
                return d
    return None


def _feiertag(d: date, land: str) -> str | None:
    if d.weekday() >= 5:
        return _WOCHENTAGE[d.weekday()]
    return feiertage(d.year, "BY" if land == "BY-ohne" else land, maria_himmelfahrt_bayern=land != "BY-ohne").get(d)


def fristvorschlaege(s: dict, land: str = "BY") -> list[dict]:
    """Fristen aus den Notizen „Frist / Auflage“ (andere Arten nur mit Stichwort wie „Frist“ oder „Nachlass“).
    Ein festes Datum („bis zum 15.12.2026“) gilt so, wie es dasteht; sonst eine Dauer („drei Wochen“) ab dem Termintag,
    deren Ende der Fristenrechner bestimmt. Nur Vorschläge: Übernommen wird, was im Dialog ausgewählt und
    gegebenenfalls korrigiert wird."""
    aus: list[dict] = []
    tag = s["beginn"][:10]
    for n in s["notizen"]:
        if n["art"] != "auflage" and not re.search(r"frist|nachlass|stellungnahme|auflage", n["text"], re.IGNORECASE):
            continue
        quelle = f"Terminsnotiz {_uhrzeit(n['zeit'])} Uhr vom {_datum_de(tag)}"
        titel = _einzeilig(n["text"])[:120]
        fest = _festes_datum(n["text"], date.fromisoformat(tag))
        if fest is not None:
            aus.append({"notiz_id": n["id"], "titel": titel, "art": "datum", "anzahl": None, "einheit": None,
                        "bezugstag": tag, "datum": fest.isoformat(), "verschoben": False, "grund": None,
                        "kein_werktag": _feiertag(fest, land), "beginn_offen": None, "quelle": quelle})
            continue
        treffer = _FRIST.search(n["text"])
        if not treffer:
            continue
        zahl = treffer.group(1).lower()
        anzahl = int(zahl) if zahl.isdigit() else _ZAHLWORTE[zahl]
        einheit = _EINHEIT[treffer.group(2).lower()]
        ereignis = _EREIGNIS.search(n["text"])
        if ereignis:
            # Beginn hängt an einem Ereignis nach dem Termin: kein Datum raten, das trägt man ein, sobald es feststeht.
            aus.append({"notiz_id": n["id"], "titel": titel, "art": "dauer", "anzahl": anzahl, "einheit": einheit,
                        "bezugstag": None, "datum": None, "verschoben": False, "grund": None, "kein_werktag": None,
                        "beginn_offen": ereignis.group(1), "quelle": quelle})
            continue
        r = kalender.berechne(tag, anzahl, einheit, land)
        aus.append({"notiz_id": n["id"], "titel": titel, "art": "dauer", "anzahl": anzahl, "einheit": einheit,
                    "bezugstag": tag, "datum": r["ende"], "verschoben": r["verschoben"], "grund": r["grund"],
                    "kein_werktag": None, "beginn_offen": None, "quelle": quelle})
    return aus


def beenden(con: sqlite3.Connection, sitzung_id: int, protokoll_uebernehmen: bool = True,
            zeit: dict | None = None, fristen: list[dict] | None = None, jetzt: datetime | None = None) -> dict:
    """Beendet die Sitzung. Auf Wunsch: Protokoll als Aktennotiz, Dauer in die Zeiterfassung (``zeit``: minuten,
    taetigkeit, bearbeiter_id), Fristen in den Kalender (``fristen``: je titel, datum). Erst wird alles geprüft und die
    Zeit gebucht (dort scheitert es am ehesten, etwa ohne Bearbeiter); dann folgen Fristen, Protokoll und das Ende."""
    s = _offen(con, sitzung_id)
    akte_id = s["akte_id"]
    ende = (jetzt or _jetzt()).isoformat()
    voll = _sitzung(con, sitzung_id)
    fristen = [f for f in (fristen or []) if f]
    for f in fristen:
        if not _einzeilig(f.get("titel")):
            raise ValueError("Jede Frist braucht eine Bezeichnung.")
        try:
            date.fromisoformat(str(f.get("datum")))
        except ValueError:
            raise ValueError(f"Datum „{f.get('datum')}“ der Frist bitte als TT.MM.JJJJ.") from None
    ergebnis: dict = {"notiz": False, "zeit": None, "fristen": 0}
    if zeit:
        minuten = int(zeit.get("minuten") or 0)
        zeiterfassung.speichern(con, akte_id, {
            "datum": s["beginn"][:10], "minuten": minuten, "bearbeiter_id": zeit.get("bearbeiter_id"),
            "taetigkeit": _einzeilig(zeit.get("taetigkeit")) or f"Terminwahrnehmung: {s['titel']}"})
        ergebnis["zeit"] = minuten
    for f in fristen:
        kalender.speichern(con, akte_id, {
            "art": "frist", "titel": _einzeilig(f["titel"]), "datum": str(f["datum"]),
            "notiz": f.get("quelle") or f"Aus dem Termin vom {_datum_de(s['beginn'])}"})
        ergebnis["fristen"] += 1
    if protokoll_uebernehmen and voll["notizen"]:
        notizen.speichern(con, akte_id, protokoll(voll, ende))
        ergebnis["notiz"] = True
    with con:
        con.execute("UPDATE sitzung SET ende = ?, uebernommen = ? WHERE id = ?",
                    (ende, json.dumps(ergebnis, ensure_ascii=False), sitzung_id))
    return _sitzung(con, sitzung_id)


def minuten(s: dict, jetzt: datetime | None = None) -> int:
    """Dauer der Sitzung in Minuten (laufend bis jetzt), mindestens eine."""
    beginn = datetime.fromisoformat(s["beginn"])
    bis = datetime.fromisoformat(s["ende"]) if s.get("ende") else (jetzt or _jetzt())
    return max(1, round((bis - beginn).total_seconds() / 60))


def abschluss(con: sqlite3.Connection, sitzung_id: int, land: str = "BY", jetzt: datetime | None = None) -> dict:
    """Was „Termin beenden“ vorschlägt: Protokolltext, Dauer und Fristen. Ändert nichts."""
    s = _sitzung(con, sitzung_id)
    bis = (jetzt or _jetzt()).isoformat()
    bearbeiter = None
    if s.get("person_id") is not None:
        z = con.execute("SELECT id FROM zeit_bearbeiter WHERE person_id = ? AND archiviert_am IS NULL"
                        " ORDER BY id LIMIT 1", (s["person_id"],)).fetchone()
        bearbeiter = z["id"] if z else None
    return {"protokoll": protokoll(s, s["ende"] or bis), "minuten": minuten(s, jetzt),
            "fristen": fristvorschlaege(s, land), "taetigkeit": f"Terminwahrnehmung: {s['titel']}",
            "bearbeiter_id": bearbeiter}
