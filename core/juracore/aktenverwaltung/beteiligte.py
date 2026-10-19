"""Beteiligtenverzeichnis: alle Personen und Organisationen, die in Akten vorkommen.

Die Rolle (Mandant, Gegner, Gericht …) hängt nicht am Eintrag, sondern an der Beteiligung in einer Akte. Dieselbe Firma
kann so in einer Akte Mandant und in einer anderen Gegner sein; genau das findet die Kollisionsprüfung.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher

_SCHEMA = """
CREATE TABLE IF NOT EXISTS beteiligter (
    id          INTEGER PRIMARY KEY,
    art         TEXT NOT NULL CHECK (art IN ('person', 'organisation')),
    name        TEXT NOT NULL,              -- Anzeigename, z. B. "Dr. Lena Brückner", "Autohaus Rehnfeld GmbH"
    schluessel  TEXT NOT NULL,              -- normalisierter Name für Suche und Kollisionsprüfung
    daten       TEXT NOT NULL,              -- JSON mit den Feldern aus FELDER
    angelegt_am TEXT NOT NULL,
    geaendert_am TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS beteiligter_schluessel ON beteiligter (schluessel);

-- Gesetzliche Vertreter (Geschäftsführer einer GmbH) und verbundene Organisationen (Mutter, Tochter).
CREATE TABLE IF NOT EXISTS beteiligter_beziehung (
    von INTEGER NOT NULL REFERENCES beteiligter(id) ON DELETE CASCADE,
    zu  INTEGER NOT NULL REFERENCES beteiligter(id) ON DELETE CASCADE,
    art TEXT NOT NULL CHECK (art IN ('gesetzlicher_vertreter', 'verbunden')),
    PRIMARY KEY (von, zu, art),
    CHECK (von <> zu)
);
"""

ARTEN = ("person", "organisation")
KATEGORIEN = ("Unternehmen", "Gericht", "Kanzlei", "Behörde", "Versicherung", "Verein / Stiftung", "Sonstige")
BEZIEHUNGEN = {
    "gesetzlicher_vertreter": "Gesetzlicher Vertreter",  # von = Person, zu = Organisation, die sie vertritt
    "verbunden": "Verbundene Organisation",  # Mutter-/Tochtergesellschaft; gilt in beide Richtungen
}

_GEMEINSAM = ["strasse", "plz", "ort", "land", "telefon", "email", "safe_id", "fruehere_namen", "notiz"]
FELDER = {
    "person": ["anrede", "titel", "vorname", "nachname", "geburtsdatum", *_GEMEINSAM],
    "organisation": ["name", "rechtsform", "kategorie", "registergericht", "registernummer", *_GEMEINSAM],
}


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- Namen vergleichen

# Rechtsformzusätze und Anreden tragen zur Unterscheidung nichts bei: "Müller GmbH" und "Müller
# Gesellschaft mit beschränkter Haftung" sind für die Kollisionsprüfung derselbe Name.
_ZUSAETZE = [
    "gesellschaft mit beschraenkter haftung", "gesellschaft mbh", "gesellschaft m b h", "m b h", "haftungsbeschraenkt",
    "aktiengesellschaft", "kommanditgesellschaft",
    "offene handelsgesellschaft", "gesellschaft buergerlichen rechts", "partnerschaftsgesellschaft",
    "eingetragener verein", "eingetragene genossenschaft", "eingetragener kaufmann", "eingetragene kauffrau",
    "gmbh", "mbh", "ag", "kg", "kgaa", "ohg", "ug", "gbr", "se", "partg", "partgmbb", "eg", "ev", "e v", "e k", "ek",
    "co", "und co", "inc", "ltd", "llc", "llp", "plc", "sa", "sarl", "sas", "bv", "nv", "spa", "srl",
    "herr", "frau", "dr", "prof", "dipl", "ing", "med", "jur", "rer", "pol", "nat", "h c", "mult",
    "rechtsanwalt", "rechtsanwaeltin", "ra", "rain",
]
_ZUSATZ_MUSTER = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, _ZUSAETZE), key=len, reverse=True)) + r")\b")


def schluessel(name: str) -> str:
    """Normalisierter Name: klein, ohne Umlaute, Satzzeichen, Rechtsform und Titel; Wörter sortiert.

    Die Sortierung macht "Brückner, Lena" und "Lena Brückner" gleich.
    """
    text = name.casefold().replace("ß", "ss")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " und ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = _ZUSATZ_MUSTER.sub(" ", f" {text} ")
    woerter = [w for w in text.split() if w not in ("und", "der", "die", "das")]
    return " ".join(sorted(woerter))


def aehnlichkeit(a: str, b: str) -> str | None:
    """Vergleicht zwei Schlüssel: "gleich", "aehnlich" oder None.

    Ähnlich ist ein Name mit kleinem Tippfehler oder einer, der den anderen ganz enthält ("Müller Bau GmbH" ↔
    "Müller Bau Holding GmbH"). Ein einzelnes gemeinsames Wort ("Müller") reicht dafür nicht.
    """
    if not a or not b:
        return None
    if a == b:
        return "gleich"
    wa, wb = set(a.split()), set(b.split())
    kleiner = wa if len(wa) <= len(wb) else wb
    if len(kleiner) >= 2 and (wa <= wb or wb <= wa):
        return "aehnlich"
    if SequenceMatcher(None, a, b).ratio() >= 0.88:
        return "aehnlich"
    return None


# --------------------------------------------------------------------------- Einträge


def anzeigename(art: str, daten: dict) -> str:
    if art == "person":
        return " ".join(t for t in (daten.get("titel"), daten.get("vorname"), daten.get("nachname")) if t)
    name = daten.get("name", "")
    rechtsform = daten.get("rechtsform", "")
    if rechtsform and schluessel(rechtsform) == "" and rechtsform.casefold() not in name.casefold():
        return f"{name} {rechtsform}"
    return name


def _bereinige(art: str, daten: dict | None) -> dict:
    if art not in ARTEN:
        raise ValueError(f"Unbekannte Art: {art!r}")
    daten = daten or {}
    ergebnis: dict = {}
    for k in FELDER[art]:
        wert = daten.get(k)
        if k == "fruehere_namen":
            if isinstance(wert, str):
                wert = wert.splitlines()
            werte = [" ".join(str(w).split()) for w in (wert or [])]
            ergebnis[k] = list(dict.fromkeys(w for w in werte if w))
            continue
        text = "" if wert is None else str(wert).strip()
        text = "\n".join(z.strip() for z in text.splitlines() if z.strip()) if k == "notiz" else " ".join(text.split())
        if text and k == "geburtsdatum":
            try:
                date.fromisoformat(text)
            except ValueError as fehler:
                raise ValueError("Geburtsdatum: bitte im Format JJJJ-MM-TT.") from fehler
        if text and k == "kategorie" and text not in KATEGORIEN:
            raise ValueError(f"Kategorie: „{text}“ ist kein zulässiger Wert.")
        ergebnis[k] = text
    if art == "person" and not ergebnis["nachname"]:
        raise ValueError("Bitte mindestens den Nachnamen angeben.")
    if art == "organisation" and not ergebnis["name"]:
        raise ValueError("Bitte den Namen der Organisation angeben.")
    return ergebnis


def _eintrag(z: sqlite3.Row) -> dict:
    return {"id": z["id"], "art": z["art"], "name": z["name"], "daten": json.loads(z["daten"]),
            "geaendert_am": z["geaendert_am"]}


def eintrag(con: sqlite3.Connection, beteiligter_id: int) -> dict:
    z = con.execute("SELECT * FROM beteiligter WHERE id = ?", (beteiligter_id,)).fetchone()
    if z is None:
        raise LookupError(f"Unbekannter Beteiligter: {beteiligter_id}")
    e = _eintrag(z)
    e["beziehungen"] = beziehungen(con, beteiligter_id)
    e["akten"] = [dict(r) for r in con.execute(
        """SELECT b.akte_id, b.rolle, a.name AS akte, a.aktenzeichen FROM akte_beteiligung b
           JOIN akte a ON a.id = b.akte_id WHERE b.beteiligter_id = ? ORDER BY a.id DESC""", (beteiligter_id,))]
    return e


def liste(con: sqlite3.Connection, suche: str = "", art: str | None = None, limit: int = 200) -> list[dict]:
    """Einträge, deren Name (auch ein früherer) die Suchwörter enthält; ohne Suche alle, zuletzt geänderte zuerst."""
    woerter = schluessel(suche).split() if suche.strip() else []
    ergebnis = []
    for z in con.execute("SELECT * FROM beteiligter ORDER BY geaendert_am DESC, id DESC"):
        if art and z["art"] != art:
            continue
        e = _eintrag(z)
        if woerter:
            text = " ".join([z["schluessel"], *(schluessel(n) for n in e["daten"].get("fruehere_namen", []))])
            if not all(any(t.startswith(w) for t in text.split()) for w in woerter):
                continue
        ergebnis.append(e)
        if len(ergebnis) >= limit:
            break
    return ergebnis


def aehnliche(con: sqlite3.Connection, art: str, daten: dict, ausser: int | None = None) -> list[dict]:
    """Vorhandene Einträge mit gleichem oder ähnlichem Namen, damit keine Dubletten entstehen."""
    name = anzeigename(art, daten) if (daten.get("name") or daten.get("nachname")) else ""
    s = schluessel(name)
    treffer = []
    for z in con.execute("SELECT * FROM beteiligter WHERE art = ?", (art,)):
        if z["id"] == ausser:
            continue
        stufe = aehnlichkeit(s, z["schluessel"])
        if stufe:
            treffer.append({**_eintrag(z), "stufe": stufe})
    return sorted(treffer, key=lambda t: t["stufe"] != "gleich")


def speichern(con: sqlite3.Connection, art: str, daten: dict, beteiligter_id: int | None = None) -> dict:
    daten = _bereinige(art, daten)
    name = anzeigename(art, daten)
    jetzt = _jetzt()
    with con:
        if beteiligter_id is None:
            beteiligter_id = con.execute(
                """INSERT INTO beteiligter (art, name, schluessel, daten, angelegt_am, geaendert_am)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (art, name, schluessel(name), json.dumps(daten, ensure_ascii=False), jetzt, jetzt),
            ).lastrowid
        else:
            alt = eintrag(con, beteiligter_id)
            if alt["art"] != art:
                raise ValueError("Die Art (Person oder Organisation) lässt sich nicht ändern.")
            con.execute(
                "UPDATE beteiligter SET name = ?, schluessel = ?, daten = ?, geaendert_am = ? WHERE id = ?",
                (name, schluessel(name), json.dumps(daten, ensure_ascii=False), jetzt, beteiligter_id),
            )
    return eintrag(con, beteiligter_id)


def loeschen(con: sqlite3.Connection, beteiligter_id: int) -> dict:
    e = eintrag(con, beteiligter_id)
    if e["akten"]:
        akten = ", ".join(sorted({a["aktenzeichen"] or a["akte"] for a in e["akten"]}))
        raise ValueError(f"„{e['name']}“ ist an Akten beteiligt ({akten}) und kann nicht gelöscht werden.")
    with con:
        con.execute("DELETE FROM beteiligter WHERE id = ?", (beteiligter_id,))
    return {"geloescht": beteiligter_id}


def beziehungen(con: sqlite3.Connection, beteiligter_id: int) -> list[dict]:
    """Beziehungen aus Sicht dieses Eintrags, z. B. "Gesetzlicher Vertreter von …" oder "vertreten durch …"."""
    ergebnis = []
    for z in con.execute(
        """SELECT r.von, r.zu, r.art, v.name AS von_name, z.name AS zu_name FROM beteiligter_beziehung r
           JOIN beteiligter v ON v.id = r.von JOIN beteiligter z ON z.id = r.zu
           WHERE r.von = ? OR r.zu = ? ORDER BY r.art, r.von, r.zu""", (beteiligter_id, beteiligter_id)):
        eigen = z["von"] == beteiligter_id
        anderer, name = (z["zu"], z["zu_name"]) if eigen else (z["von"], z["von_name"])
        if z["art"] == "gesetzlicher_vertreter":
            text = f"Gesetzlicher Vertreter von {name}" if eigen else f"vertreten durch {name}"
        else:
            text = f"verbunden mit {name}"
        ergebnis.append({"von": z["von"], "zu": z["zu"], "art": z["art"], "anderer": anderer, "name": name,
                         "text": text})
    return ergebnis


def beziehung_setzen(con: sqlite3.Connection, von: int, zu: int, art: str, vorhanden: bool = True) -> dict:
    if art not in BEZIEHUNGEN:
        raise ValueError(f"Unbekannte Beziehung: {art!r}")
    a, b = eintrag(con, von), eintrag(con, zu)
    if art == "gesetzlicher_vertreter" and b["art"] != "organisation":
        raise ValueError("Ein gesetzlicher Vertreter vertritt eine Organisation.")
    if art == "verbunden" and (a["art"], b["art"]) != ("organisation", "organisation"):
        raise ValueError("Verbunden werden nur Organisationen (z. B. Mutter- und Tochtergesellschaft).")
    if art == "verbunden" and von > zu:
        von, zu = zu, von  # ungerichtet: nur einmal speichern
    with con:
        if vorhanden:
            con.execute("INSERT OR IGNORE INTO beteiligter_beziehung (von, zu, art) VALUES (?, ?, ?)", (von, zu, art))
        else:
            con.execute("DELETE FROM beteiligter_beziehung WHERE von = ? AND zu = ? AND art = ?", (von, zu, art))
    return eintrag(con, a["id"])
