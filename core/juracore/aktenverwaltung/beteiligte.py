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
    funktion TEXT,                          -- beim gesetzlichen Vertreter, z. B. "Geschäftsführerin"
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
# Vorschläge für die Funktion eines gesetzlichen Vertreters; freie Eingabe bleibt möglich.
FUNKTIONEN = (
    "Geschäftsführer", "Geschäftsführerin", "Vorstand", "Vorstandsvorsitzender", "Vorstandsvorsitzende",
    "Inhaber", "Inhaberin", "Komplementär", "Vorsitzender", "Vorsitzende", "Liquidator", "Insolvenzverwalter",
)

_GEMEINSAM = ["strasse", "plz", "ort", "land", "telefon", "email", "safe_id", "fruehere_namen", "notiz"]
FELDER = {
    "person": ["anrede", "titel", "vorname", "nachname", "geburtsdatum", *_GEMEINSAM],
    "organisation": ["name", "rechtsform", "kategorie", "registergericht", "registernummer", *_GEMEINSAM],
}


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    if "funktion" not in {z[1] for z in con.execute("PRAGMA table_info(beteiligter_beziehung)")}:
        con.execute("ALTER TABLE beteiligter_beziehung ADD COLUMN funktion TEXT")
        con.commit()


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


def _wort_passt(w: str, v: str) -> bool:
    """Gleiches Wort oder ein kleiner Tippfehler darin ("joanas" ↔ "jonas"); kurze Wörter nur exakt."""
    return w == v or (min(len(w), len(v)) >= 4 and SequenceMatcher(None, w, v).ratio() >= 0.8)


def aehnlichkeit(a: str, b: str) -> str | None:
    """Vergleicht zwei Schlüssel: "gleich", "aehnlich" oder None.

    Ähnlich ist ein Name mit kleinem Tippfehler oder einer, dessen Wörter alle im anderen vorkommen: "Reiter" ↔
    "Jonas Reiter", "Müller Bau GmbH" ↔ "Müller Bau Holding GmbH". Zwei vollständige Namen, die nur ein Wort teilen
    ("Anna Reiter" ↔ "Jonas Reiter"), gelten nicht als ähnlich.
    """
    if not a or not b:
        return None
    if a == b:
        return "gleich"
    wa, wb = a.split(), b.split()
    kleiner, groesser = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if all(any(_wort_passt(w, v) for v in groesser) for w in kleiner):
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


def briefname(daten: dict) -> str:
    """Person mit Anrede und Titel, wie in einem Schreiben: "Frau Dr. Mira Lenz"."""
    return " ".join(t for t in (daten.get("anrede"), daten.get("titel"), daten.get("vorname"), daten.get("nachname"))
                    if t)


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


def _suchwort_passt(w: str, t: str) -> bool:
    """Wortanfang ("Reit" findet "Reiter") oder ein Tippfehler im Wort ("Joanas" findet "Jonas")."""
    return t.startswith(w) or (len(w) >= 4 and SequenceMatcher(None, w, t[: len(w) + 1]).ratio() >= 0.8)


def liste(con: sqlite3.Connection, suche: str = "", art: str | None = None, limit: int = 200) -> list[dict]:
    """Einträge, deren Name (auch ein früherer) die Suchwörter enthält, auch mit kleinem Tippfehler; genaue Treffer
    zuerst. Ohne Suche alle, zuletzt geänderte zuerst."""
    woerter = schluessel(suche).split() if suche.strip() else []
    genau, ungefaehr = [], []
    for z in con.execute("SELECT * FROM beteiligter ORDER BY geaendert_am DESC, id DESC"):
        if art and z["art"] != art:
            continue
        e = _eintrag(z)
        if woerter:
            text = " ".join([z["schluessel"], *(schluessel(n) for n in e["daten"].get("fruehere_namen", []))]).split()
            if all(any(t.startswith(w) for t in text) for w in woerter):
                genau.append(e)
            elif all(any(_suchwort_passt(w, t) for t in text) for w in woerter):
                ungefaehr.append(e)
            continue
        genau.append(e)
        if len(genau) >= limit:
            break
    return (genau + ungefaehr)[:limit]


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


def speichern(con: sqlite3.Connection, art: str, daten: dict, beteiligter_id: int | None = None,
              vertreter: list[dict] | None = None) -> dict:
    """Legt einen Eintrag an oder ändert ihn.

    ``vertreter`` (nur Organisationen): gesetzliche Vertreter, die gleich mit verknüpft werden, je als
    {"beteiligter_id": …} für einen vorhandenen Eintrag oder mit Personenfeldern für einen neuen.
    """
    daten = _bereinige(art, daten)
    vertreter = [v for v in (vertreter or []) if v]
    if vertreter and art != "organisation":
        raise ValueError("Gesetzliche Vertreter gibt es nur bei einer Organisation.")
    neue_personen = [_bereinige("person", v) for v in vertreter if not v.get("beteiligter_id")]
    vorhandene = [int(v["beteiligter_id"]) for v in vertreter if v.get("beteiligter_id")]
    # Reihenfolge wie unten: erst die vorhandenen, dann die neu angelegten Personen.
    funktionen = [_funktion(v.get("funktion")) for v in vertreter if v.get("beteiligter_id")]
    funktionen += [_funktion(v.get("funktion")) for v in vertreter if not v.get("beteiligter_id")]
    for vid in vorhandene:
        if eintrag(con, vid)["art"] != "person":
            raise ValueError("Ein gesetzlicher Vertreter ist eine Person.")
    name = anzeigename(art, daten)
    jetzt = _jetzt()
    with con:
        if beteiligter_id is None:
            beteiligter_id = _einfuegen(con, art, name, daten, jetzt)
        else:
            alt = eintrag(con, beteiligter_id)
            if alt["art"] != art:
                raise ValueError("Die Art (Person oder Organisation) lässt sich nicht ändern.")
            con.execute(
                "UPDATE beteiligter SET name = ?, schluessel = ?, daten = ?, geaendert_am = ? WHERE id = ?",
                (name, schluessel(name), json.dumps(daten, ensure_ascii=False), jetzt, beteiligter_id),
            )
        for p in neue_personen:
            vorhandene.append(_einfuegen(con, "person", anzeigename("person", p), p, jetzt))
        for vid, funktion in zip(vorhandene, funktionen, strict=True):
            _verknuepfen(con, vid, beteiligter_id, "gesetzlicher_vertreter", funktion)
    return eintrag(con, beteiligter_id)


def _einfuegen(con: sqlite3.Connection, art: str, name: str, daten: dict, jetzt: str) -> int:
    return con.execute(
        """INSERT INTO beteiligter (art, name, schluessel, daten, angelegt_am, geaendert_am)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (art, name, schluessel(name), json.dumps(daten, ensure_ascii=False), jetzt, jetzt),
    ).lastrowid


def loeschen(con: sqlite3.Connection, beteiligter_id: int) -> dict:
    e = eintrag(con, beteiligter_id)
    if e["akten"]:
        akten = ", ".join(sorted({a["aktenzeichen"] or a["akte"] for a in e["akten"]}))
        raise ValueError(f"„{e['name']}“ ist an Akten beteiligt ({akten}) und kann nicht gelöscht werden.")
    with con:
        con.execute("DELETE FROM beteiligter WHERE id = ?", (beteiligter_id,))
    return {"geloescht": beteiligter_id}


def _funktion(text: str | None) -> str | None:
    return " ".join(str(text or "").split()) or None


def _verknuepfen(con: sqlite3.Connection, von: int, zu: int, art: str, funktion: str | None,
                 ueberschreiben: bool = False) -> None:
    """Legt die Beziehung an; eine bestehende behält ihre Funktion, außer ``ueberschreiben``."""
    neu = "excluded.funktion" if ueberschreiben else "COALESCE(excluded.funktion, funktion)"
    con.execute(f"""INSERT INTO beteiligter_beziehung (von, zu, art, funktion) VALUES (?, ?, ?, ?)
                    ON CONFLICT (von, zu, art) DO UPDATE SET funktion = {neu}""", (von, zu, art, funktion))


def beziehungen(con: sqlite3.Connection, beteiligter_id: int) -> list[dict]:
    """Beziehungen aus Sicht dieses Eintrags, z. B. "Geschäftsführerin von …" oder "vertreten durch Frau Dr. …"."""
    ergebnis = []
    for z in con.execute(
        """SELECT r.von, r.zu, r.art, r.funktion, v.name AS von_name, v.daten AS von_daten, z.name AS zu_name
           FROM beteiligter_beziehung r JOIN beteiligter v ON v.id = r.von JOIN beteiligter z ON z.id = r.zu
           WHERE r.von = ? OR r.zu = ? ORDER BY r.art, r.von, r.zu""", (beteiligter_id, beteiligter_id)):
        eigen = z["von"] == beteiligter_id
        anderer, name = (z["zu"], z["zu_name"]) if eigen else (z["von"], z["von_name"])
        if z["art"] == "gesetzlicher_vertreter":
            if eigen:
                text = f"{z['funktion'] or 'Gesetzlicher Vertreter'} von {name}"
            else:
                text = f"vertreten durch {briefname(json.loads(z['von_daten'])) or name}"
                text += f" ({z['funktion']})" if z["funktion"] else ""
        else:
            text = f"verbunden mit {name}"
        ergebnis.append({"von": z["von"], "zu": z["zu"], "art": z["art"], "anderer": anderer, "name": name,
                         "funktion": z["funktion"] or "", "text": text})
    return ergebnis


def beziehung_setzen(con: sqlite3.Connection, von: int, zu: int, art: str, vorhanden: bool = True,
                     funktion: str | None = None) -> dict:
    """Setzt oder löscht eine Beziehung; ``funktion`` (z. B. "Geschäftsführerin") nur beim gesetzlichen Vertreter.

    Eine schon bestehende Beziehung behält ihre Funktion, wenn keine neue angegeben ist; "" löscht sie.
    """
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
        if not vorhanden:
            con.execute("DELETE FROM beteiligter_beziehung WHERE von = ? AND zu = ? AND art = ?", (von, zu, art))
        else:
            neu = _funktion(funktion) if art == "gesetzlicher_vertreter" else None
            _verknuepfen(con, von, zu, art, neu, ueberschreiben=funktion is not None)
    return eintrag(con, a["id"])
