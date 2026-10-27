"""Fristen, Termine und Wiedervorlagen einer Akte.

- Frist: endet an einem Tag (Klageerwiderung, Berufungsbegründung …), auf Wunsch mit Vorfrist. Wird sie aus
  Bezugstag und Dauer berechnet, rechnet der Fristenrechner (§§ 187, 188, 193 BGB) und die Berechnung wird mit
  gespeichert, damit sie nachvollziehbar bleibt.
- Termin: Gerichtstermin mit Uhrzeit und Ort.
- Wiedervorlage: Tag, an dem die Akte wieder vorgelegt werden soll.

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
    vorfrist      TEXT,                     -- JJJJ-MM-TT, bei Fristen
    berechnung    TEXT,                     -- JSON: Bezugstag, Dauer, Ergebnis des Fristenrechners
    dokument_id   INTEGER REFERENCES dokument(id) ON DELETE SET NULL,
    fundstelle    TEXT,                     -- JSON: {"abschnitt", "seite", "text"} im Dokument
    notiz         TEXT,
    erledigt_am   TEXT,
    erledigt_vermerk TEXT,
    angelegt_am   TEXT NOT NULL,
    geaendert_am  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS kalender_akte ON kalender (akte_id);
CREATE INDEX IF NOT EXISTS kalender_offen ON kalender (datum) WHERE erledigt_am IS NULL;
"""

ARTEN = {"frist": "Frist", "termin": "Termin", "wiedervorlage": "Wiedervorlage"}
FELDER = ("verfahren_id", "art", "titel", "datum", "uhrzeit", "ort", "vorfrist", "dokument_id", "fundstelle", "notiz")
_UHRZEIT = re.compile(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$")


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
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
    e["art_text"] = ARTEN[e["art"]]
    tage = (date.fromisoformat(e["datum"]) - heute).days
    e["in_tagen"] = tage
    if e["erledigt_am"]:
        e["lage"] = "erledigt"
    elif tage < 0:
        e["lage"] = "abgelaufen"
    elif tage == 0:
        e["lage"] = "heute"
    elif e["vorfrist"] and date.fromisoformat(e["vorfrist"]) <= heute:
        e["lage"] = "vorfrist"
    elif tage <= 7:
        e["lage"] = "bald"
    else:
        e["lage"] = "offen"
    return e


def liste(con: sqlite3.Connection, akte_id: int, heute: date | None = None) -> list[dict]:
    """Alle Einträge der Akte: offene nach Datum, darunter die erledigten (neueste zuerst)."""
    heute = heute or date.today()
    zeilen = con.execute(
        """SELECT k.*, COALESCE(d.titel, d.dateiname) AS dokument FROM kalender k
           LEFT JOIN dokument d ON d.id = k.dokument_id
           WHERE k.akte_id = ? ORDER BY k.erledigt_am IS NOT NULL, k.datum, k.uhrzeit, k.id""", (akte_id,)).fetchall()
    eintraege = [_zeile(z, heute) for z in zeilen]
    offen = [e for e in eintraege if not e["erledigt_am"]]
    erledigt = sorted((e for e in eintraege if e["erledigt_am"]), key=lambda e: e["datum"], reverse=True)
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
    if werte["vorfrist"]:
        werte["vorfrist"] = _datum(werte["vorfrist"], "Vorfrist")
        if werte["vorfrist"] > werte["datum"]:
            raise ValueError("Die Vorfrist muss vor dem Fristende liegen.")
    if werte["art"] != "frist":
        werte["vorfrist"] = None
    if werte["uhrzeit"]:
        m = _UHRZEIT.match(werte["uhrzeit"])
        if not m:
            raise ValueError("Uhrzeit bitte als HH:MM, z. B. 10:30.")
        werte["uhrzeit"] = f"{int(m.group(1)):02d}:{m.group(2)}"
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


def erledigen(con: sqlite3.Connection, eintrag_id: int, erledigt: bool = True, vermerk: str = "",
              heute: date | None = None) -> list[dict]:
    z = con.execute("SELECT akte_id FROM kalender WHERE id = ?", (eintrag_id,)).fetchone()
    if z is None:
        raise LookupError(f"Eintrag {eintrag_id} gibt es nicht.")
    with con:
        con.execute("UPDATE kalender SET erledigt_am = ?, erledigt_vermerk = ?, geaendert_am = ? WHERE id = ?",
                    (_jetzt() if erledigt else None, " ".join(vermerk.split()) or None if erledigt else None,
                     _jetzt(), eintrag_id))
    return liste(con, z["akte_id"], heute)


def loeschen(con: sqlite3.Connection, eintrag_id: int, heute: date | None = None) -> list[dict]:
    z = con.execute("SELECT akte_id FROM kalender WHERE id = ?", (eintrag_id,)).fetchone()
    if z is None:
        raise LookupError(f"Eintrag {eintrag_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM kalender WHERE id = ?", (eintrag_id,))
    return liste(con, z["akte_id"], heute)


def naechste(con: sqlite3.Connection, tage: int | None = None, limit: int = 50,
             heute: date | None = None) -> list[dict]:
    """Offene Einträge aller Akten nach Datum, abgelaufene zuerst; mit ``tage`` nur bis heute + tage."""
    heute = heute or date.today()
    bis = (heute + timedelta(days=tage)).isoformat() if tage is not None else "9999-12-31"
    zeilen = con.execute(
        """SELECT k.*, a.name AS akte, a.aktenzeichen, COALESCE(d.titel, d.dateiname) AS dokument FROM kalender k
           JOIN akte a ON a.id = k.akte_id LEFT JOIN dokument d ON d.id = k.dokument_id
           WHERE k.erledigt_am IS NULL AND k.datum <= ? AND a.status != 'abgeschlossen'
           ORDER BY k.datum, k.uhrzeit, k.id LIMIT ?""", (bis, limit)).fetchall()
    return [_zeile(z, heute) for z in zeilen]


def naechste_je_akte(con: sqlite3.Connection, heute: date | None = None) -> dict[int, dict]:
    """Für die Aktenübersicht: je Akte der früheste offene Eintrag."""
    heute = heute or date.today()
    ergebnis: dict[int, dict] = {}
    for z in con.execute("SELECT * FROM kalender WHERE erledigt_am IS NULL ORDER BY datum, uhrzeit, id"):
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
    und machen aus „Termin vom … aufgehoben“ einen Vorschlag zum Erledigen des passenden Termins.
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
                ergebnis.append({"art": "erledigen", "eintrag_id": passend[0]["id"], "titel": passend[0]["titel"],
                                 "datum": datum, "vermerk": f"Termin {m.group(4)}",
                                 "fundstelle": {"abschnitt": a["nr"], "seite": a.get("seite"),
                                                "text": _satz(text, m.start(), m.end())}})
    # Schon eingetragene (gleiche Art und gleiches Datum) nicht noch einmal vorschlagen.
    belegt = {(e["art"], e["datum"]) for e in vorhandene}
    eindeutig: list[dict] = []
    for v in ergebnis:
        schluessel = (v["art"], v.get("datum"))
        if v["art"] != "erledigen" and v.get("datum") and schluessel in belegt:
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
