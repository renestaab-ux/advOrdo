"""Stammdaten einer Akte: eigenes Aktenzeichen, Gegenstand, Status und die Beteiligten mit ihrer Rolle.

Aktenzeichen folgen dem Schema Nummer/Jahr (102/26): laufende Nummer je Kalenderjahr, Jahr zweistellig. Ein einmal
vergebenes Aktenzeichen bleibt vergeben, auch wenn die Akte gelöscht wird, damit es auf Schreiben eindeutig bleibt.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from . import beteiligte

_SCHEMA = """
CREATE TABLE IF NOT EXISTS akte_beteiligung (
    id                     INTEGER PRIMARY KEY,
    akte_id                INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    -- genau einer der drei Verweise: ein Eintrag im Beteiligtenverzeichnis oder (Rechtsabteilung) eine
    -- Konzerngesellschaft bzw. ein Anwalt aus „Eigene Daten“
    beteiligter_id         INTEGER REFERENCES beteiligter(id),
    eigene_organisation_id INTEGER REFERENCES eigene_organisation(id),
    eigene_person_id       INTEGER REFERENCES eigene_person(id),
    rolle                  TEXT NOT NULL,
    aktenzeichen           TEXT,            -- z. B. das gerichtliche Az. beim Gericht oder das der Gegenseite
    angelegt_am            TEXT NOT NULL,
    CHECK ((beteiligter_id IS NOT NULL) + (eigene_organisation_id IS NOT NULL) + (eigene_person_id IS NOT NULL) = 1)
);
CREATE INDEX IF NOT EXISTS akte_beteiligung_akte ON akte_beteiligung (akte_id);
CREATE INDEX IF NOT EXISTS akte_beteiligung_beteiligter ON akte_beteiligung (beteiligter_id);

-- Jedes je vergebene Aktenzeichen, auch das einer gelöschten Akte: es wird nie ein zweites Mal vergeben.
CREATE TABLE IF NOT EXISTS aktenzeichen_vergeben (
    aktenzeichen TEXT PRIMARY KEY COLLATE NOCASE,
    jahr         INTEGER NOT NULL,
    nummer       INTEGER NOT NULL,
    akte_id      INTEGER,
    vergeben_am  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS akten_einstellung (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT NOT NULL                -- JSON
);
"""

# Neue Spalten der Tabelle akte (dokumente/akte.py); bestehende Akten bekommen sie leer bzw. mit Status „laufend“.
_AKTE_SPALTEN = {
    "aktenzeichen": "TEXT", "az_jahr": "INTEGER", "az_nummer": "INTEGER", "gegenstand": "TEXT", "sachgebiet": "TEXT",
    "eigene_rolle": "TEXT", "status": "TEXT NOT NULL DEFAULT 'laufend'", "sachbearbeiter_id": "INTEGER",
    "mandat_seit": "TEXT", "gegenstandswert": "TEXT", "notiz": "TEXT", "geaendert_am": "TEXT",
    "geoeffnet_am": "TEXT",
}  # fmt: skip

ROLLEN = {
    "mandant": ("eigene", "Mandant"),
    "vertretender_anwalt": ("eigene", "Vertretender Anwalt"),
    "gegner": ("gegen", "Gegner"),
    "bevollmaechtigter_gegner": ("gegen", "Prozessbevollmächtigter des Gegners"),
    "versicherer_gegner": ("gegen", "Haftpflichtversicherer des Gegners"),
    "gericht": ("neutral", "Gericht"),
    "sachverstaendiger": ("neutral", "Sachverständiger"),
    "zeuge": ("neutral", "Zeuge"),
    "streitverkuendeter": ("neutral", "Streitverkündeter"),
    "sonstiger": ("neutral", "Sonstiger Beteiligter"),
}
SEITEN = {"eigene": "Eigene Seite", "gegen": "Gegenseite", "neutral": "Neutral / Dritte"}
# Gruppen der Beteiligtenliste: wie die Seiten, nur steht das Gericht für sich.
GRUPPEN = {"eigene": "Eigene Seite", "gegen": "Gegenseite", "gericht": "Gericht", "neutral": "Neutral / Dritte"}
STATUS = {"laufend": "laufend", "ruhend": "ruhend", "abgeschlossen": "abgeschlossen"}
EIGENE_ROLLEN = (
    "Prozessbevollmächtigter des Klägers", "Prozessbevollmächtigter des Beklagten", "Außergerichtliche Vertretung",
    "Beratung", "Zeugenbeistand", "Sonstiges",
)
SACHGEBIETE = (
    "Allgemeines Zivilrecht", "Kaufrecht", "Werkvertrags- und Baurecht", "Mietrecht", "Arbeitsrecht",
    "Handels- und Gesellschaftsrecht", "Verkehrsrecht", "Versicherungsrecht", "Erbrecht", "Familienrecht",
    "Verwaltungsrecht", "Sonstiges",
)
FELDER = ("name", "gegenstand", "sachgebiet", "eigene_rolle", "status", "sachbearbeiter_id", "mandat_seit",
          "gegenstandswert", "notiz")  # fmt: skip

_BETRAG_TAUSENDER = re.compile(r"^\d{1,3}(\.\d{3})+$")


def betrag(text: str) -> str:
    """Gegenstandswert in Euro als "250000.00"; liest deutsche Schreibweisen wie "250.000", "18.450,50 €"."""
    t = re.sub(r"[\s€']|EUR", "", str(text or ""), flags=re.IGNORECASE)
    if not t:
        return ""
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif _BETRAG_TAUSENDER.match(t):
        t = t.replace(".", "")
    try:
        wert = Decimal(t)
    except InvalidOperation as fehler:
        raise ValueError(f"Gegenstandswert: „{text}“ ist kein Betrag, z. B. 18.450,00.") from fehler
    if wert < 0 or not wert.is_finite():
        raise ValueError("Gegenstandswert: bitte einen Betrag ab 0 angeben.")
    return f"{wert.quantize(Decimal('0.01')):f}"


_AZ = re.compile(r"^\s*(\d{1,6})\s*/\s*(\d{2})\s*(.*)$")


def einrichten(con: sqlite3.Connection) -> None:
    vorhanden = {z["name"] for z in con.execute("PRAGMA table_info(akte)")}
    for spalte, typ in _AKTE_SPALTEN.items():
        if spalte not in vorhanden:
            con.execute(f"ALTER TABLE akte ADD COLUMN {spalte} {typ}")
    con.executescript(_SCHEMA)
    # Frühere Freitext-Gegenstandswerte ("250.000") in die Zahlform bringen; was sich nicht lesen lässt, bleibt.
    for z in con.execute("SELECT id, gegenstandswert FROM akte WHERE gegenstandswert IS NOT NULL").fetchall():
        try:
            neu = betrag(z["gegenstandswert"]) or None
        except ValueError:
            continue
        if neu != z["gegenstandswert"]:
            con.execute("UPDATE akte SET gegenstandswert = ? WHERE id = ?", (neu, z["id"]))
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS akte_aktenzeichen ON akte (aktenzeichen COLLATE NOCASE) "
                "WHERE aktenzeichen IS NOT NULL")
    con.commit()


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- Einstellungen

VORGABEN = {"aktenzeichen_zusatz": "", "naechste_nummer": {}, "kollision_ausgenommen": []}


def einstellungen(con: sqlite3.Connection) -> dict:
    werte = json.loads(json.dumps(VORGABEN))  # tiefe Kopie, die Vorgaben bleiben unverändert
    for z in con.execute("SELECT schluessel, wert FROM akten_einstellung"):
        if z["schluessel"] in werte:
            werte[z["schluessel"]] = json.loads(z["wert"])
    return werte


def einstellungen_setzen(con: sqlite3.Connection, aktenzeichen_zusatz: str | None = None,
                         naechste_nummer: int | None = None, jahr: int | None = None,
                         kollision_ausgenommen: list[str] | None = None, heute: date | None = None) -> dict:
    """``naechste_nummer`` gilt für ``jahr`` (Standard: das laufende Jahr), z. B. für eine bisherige Zählung."""
    neu: dict = {}
    if aktenzeichen_zusatz is not None:
        zusatz = " ".join(str(aktenzeichen_zusatz).split())
        if len(zusatz) > 12 or "/" in zusatz:
            raise ValueError("Der Zusatz darf höchstens 12 Zeichen haben und keinen Schrägstrich enthalten.")
        neu["aktenzeichen_zusatz"] = zusatz
    if naechste_nummer is not None:
        jahr = int(jahr or (heute or date.today()).year)
        nummer = int(naechste_nummer)
        hoechste = _hoechste(con, jahr)
        if nummer < 1:
            raise ValueError("Die nächste Nummer muss mindestens 1 sein.")
        if nummer <= hoechste:
            raise ValueError(f"Für {jahr} ist schon die Nummer {hoechste} vergeben; die nächste muss größer sein.")
        nummern = einstellungen(con)["naechste_nummer"]
        nummern[str(jahr)] = nummer
        neu["naechste_nummer"] = nummern
    if kollision_ausgenommen is not None:
        neu["kollision_ausgenommen"] = sorted({str(u) for u in kollision_ausgenommen})
    with con:
        for k, v in neu.items():
            con.execute("INSERT OR REPLACE INTO akten_einstellung (schluessel, wert) VALUES (?, ?)",
                        (k, json.dumps(v, ensure_ascii=False)))
    return einstellungen(con)


# --------------------------------------------------------------------------- Aktenzeichen


def _hoechste(con: sqlite3.Connection, jahr: int) -> int:
    return con.execute("SELECT COALESCE(MAX(nummer), 0) FROM aktenzeichen_vergeben WHERE jahr = ?",
                       (jahr,)).fetchone()[0]


def formatiere(nummer: int, jahr: int, zusatz: str = "") -> str:
    az = f"{nummer}/{jahr % 100:02d}"
    return f"{az} {zusatz}" if zusatz else az


def vorschlag(con: sqlite3.Connection, heute: date | None = None) -> dict:
    """Die nächste freie Nummer im laufenden Jahr."""
    jahr = (heute or date.today()).year
    e = einstellungen(con)
    nummer = max(_hoechste(con, jahr) + 1, int(e["naechste_nummer"].get(str(jahr), 1)))
    return {"aktenzeichen": formatiere(nummer, jahr, e["aktenzeichen_zusatz"]), "nummer": nummer, "jahr": jahr}


def zerlege(aktenzeichen: str, heute: date | None = None) -> tuple[int, int, str]:
    """"102/26 RS" → (102, 2026, "RS"). Das Jahrhundert ergibt sich aus dem laufenden Jahr."""
    m = _AZ.match(aktenzeichen or "")
    if not m:
        raise ValueError("Bitte das Aktenzeichen im Schema Nummer/Jahr angeben, z. B. 102/26.")
    nummer, jj, zusatz = int(m.group(1)), int(m.group(2)), " ".join(m.group(3).split())
    if nummer < 1:
        raise ValueError("Die Nummer des Aktenzeichens muss mindestens 1 sein.")
    jetzt = (heute or date.today()).year
    jahr = jetzt - jetzt % 100 + jj
    if jahr > jetzt + 1:
        jahr -= 100
    return nummer, jahr, zusatz


def vergeben(con: sqlite3.Connection, akte_id: int, aktenzeichen: str | None = None,
             heute: date | None = None) -> dict:
    """Gibt der Akte ein Aktenzeichen: das vorgeschlagene oder ein von Hand eingegebenes, solange es frei ist."""
    akte = _akte(con, akte_id)
    if akte["aktenzeichen"]:
        raise ValueError(f"Die Akte hat schon das Aktenzeichen {akte['aktenzeichen']}.")
    if aktenzeichen and aktenzeichen.strip():
        nummer, jahr, zusatz = zerlege(aktenzeichen, heute)
        az = formatiere(nummer, jahr, zusatz)
    else:
        v = vorschlag(con, heute)
        nummer, jahr, az = v["nummer"], v["jahr"], v["aktenzeichen"]
    belegt = con.execute(
        "SELECT akte_id FROM aktenzeichen_vergeben WHERE jahr = ? AND nummer = ?", (jahr, nummer)
    ).fetchone()
    if belegt:
        raise ValueError(f"Die Nummer {nummer}/{jahr % 100:02d} ist schon vergeben und wird nicht erneut vergeben.")
    with con:
        con.execute("INSERT INTO aktenzeichen_vergeben (aktenzeichen, jahr, nummer, akte_id, vergeben_am) "
                    "VALUES (?, ?, ?, ?, ?)", (az, jahr, nummer, akte_id, _jetzt()))
        con.execute("UPDATE akte SET aktenzeichen = ?, az_jahr = ?, az_nummer = ?, geaendert_am = ? WHERE id = ?",
                    (az, jahr, nummer, _jetzt(), akte_id))
    return stammdaten(con, akte_id)


# --------------------------------------------------------------------------- Akte


def _akte(con: sqlite3.Connection, akte_id: int) -> dict:
    z = con.execute("SELECT * FROM akte WHERE id = ?", (akte_id,)).fetchone()
    if z is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    return dict(z)


def _eigene_name(con: sqlite3.Connection, tabelle: str, eintrag_id: int) -> str:
    z = con.execute(f"SELECT daten FROM {tabelle} WHERE id = ?", (eintrag_id,)).fetchone()
    if z is None:
        return "(gelöscht)"
    d = json.loads(z["daten"])
    if tabelle == "eigene_person":
        return " ".join(t for t in (d.get("titel"), d.get("vorname"), d.get("nachname")) if t)
    return d.get("name", "")


def beteiligungen(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    ergebnis = []
    for z in con.execute(
        """SELECT b.*, t.name AS t_name, t.art AS t_art FROM akte_beteiligung b
           LEFT JOIN beteiligter t ON t.id = b.beteiligter_id WHERE b.akte_id = ? ORDER BY b.id""", (akte_id,)):
        seite, rolle_text = ROLLEN.get(z["rolle"], ("neutral", z["rolle"]))
        if z["beteiligter_id"] is not None:
            name, quelle = z["t_name"], "verzeichnis"
        elif z["eigene_organisation_id"] is not None:
            name, quelle = _eigene_name(con, "eigene_organisation", z["eigene_organisation_id"]), "eigene_organisation"
        else:
            name, quelle = _eigene_name(con, "eigene_person", z["eigene_person_id"]), "eigene_person"
        ergebnis.append({
            "id": z["id"], "rolle": z["rolle"], "rolle_text": rolle_text, "seite": seite, "name": name,
            "gruppe": "gericht" if z["rolle"] == "gericht" else seite,
            "quelle": quelle, "beteiligter_id": z["beteiligter_id"], "art": z["t_art"],
            "eigene_organisation_id": z["eigene_organisation_id"], "eigene_person_id": z["eigene_person_id"],
            "aktenzeichen": z["aktenzeichen"] or "",
        })
    reihenfolge = list(ROLLEN)
    return sorted(ergebnis, key=lambda b: (reihenfolge.index(b["rolle"]) if b["rolle"] in reihenfolge else 99,
                                           b["id"]))


def stammdaten(con: sqlite3.Connection, akte_id: int) -> dict:
    a = _akte(con, akte_id)
    a["beteiligte"] = beteiligungen(con, akte_id)
    a["dokumente"] = con.execute("SELECT COUNT(*) FROM dokument WHERE akte_id = ?", (akte_id,)).fetchone()[0]
    return a


def speichern(con: sqlite3.Connection, akte_id: int, daten: dict) -> dict:
    _akte(con, akte_id)
    werte: dict = {}
    for k in FELDER:
        if k not in daten:
            continue
        v = daten[k]
        if k == "sachbearbeiter_id":
            werte[k] = None if v in (None, "") else int(v)
            continue
        text = "" if v is None else str(v).strip()
        text = "\n".join(z.strip() for z in text.splitlines() if z.strip()) if k == "notiz" else " ".join(text.split())
        if k == "name" and not text:
            raise ValueError("Die Akte braucht eine Kurzbezeichnung.")
        if k == "status" and text not in STATUS:
            raise ValueError(f"Unbekannter Status: {text!r}")
        if k == "gegenstandswert":
            text = betrag(text)
        if k == "mandat_seit" and text:
            try:
                date.fromisoformat(text)
            except ValueError as fehler:
                raise ValueError("Mandat seit: bitte ein Datum im Format JJJJ-MM-TT.") from fehler
        werte[k] = text or (None if k != "status" else "laufend")
    if werte:
        werte["geaendert_am"] = _jetzt()
        with con:
            con.execute(f"UPDATE akte SET {', '.join(f'{k} = ?' for k in werte)} WHERE id = ?",
                        (*werte.values(), akte_id))
    return stammdaten(con, akte_id)


def beteiligung_hinzufuegen(con: sqlite3.Connection, akte_id: int, rolle: str, beteiligter_id: int | None = None,
                            eigene_organisation_id: int | None = None, eigene_person_id: int | None = None,
                            aktenzeichen: str = "") -> dict:
    _akte(con, akte_id)
    if rolle not in ROLLEN:
        raise ValueError(f"Unbekannte Rolle: {rolle!r}")
    verweise = [v for v in (beteiligter_id, eigene_organisation_id, eigene_person_id) if v is not None]
    if len(verweise) != 1:
        raise ValueError("Bitte genau einen Beteiligten wählen.")
    if beteiligter_id is not None:
        beteiligte.eintrag(con, beteiligter_id)
    elif eigene_organisation_id is not None:
        z = con.execute("SELECT art FROM eigene_organisation WHERE id = ?", (eigene_organisation_id,)).fetchone()
        if z is None or z["art"] != "konzerngesellschaft" or rolle != "mandant":
            raise ValueError("Aus „Eigene Daten“ kann nur eine Konzerngesellschaft Mandant sein.")
    elif rolle != "vertretender_anwalt":
        raise ValueError("Personen aus „Eigene Daten“ können nur vertretender Anwalt sein.")
    doppelt = con.execute(
        """SELECT 1 FROM akte_beteiligung WHERE akte_id = ? AND rolle = ? AND beteiligter_id IS ?
           AND eigene_organisation_id IS ? AND eigene_person_id IS ?""",
        (akte_id, rolle, beteiligter_id, eigene_organisation_id, eigene_person_id),
    ).fetchone()
    if doppelt:
        raise ValueError("Dieser Beteiligte ist in dieser Rolle schon eingetragen.")
    with con:
        con.execute(
            """INSERT INTO akte_beteiligung (akte_id, beteiligter_id, eigene_organisation_id, eigene_person_id, rolle,
                                             aktenzeichen, angelegt_am) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (akte_id, beteiligter_id, eigene_organisation_id, eigene_person_id, rolle,
             " ".join(str(aktenzeichen or "").split()) or None, _jetzt()),
        )
        con.execute("UPDATE akte SET geaendert_am = ? WHERE id = ?", (_jetzt(), akte_id))
    return stammdaten(con, akte_id)


def beteiligung_aendern(con: sqlite3.Connection, beteiligung_id: int, rolle: str | None = None,
                        aktenzeichen: str | None = None) -> dict:
    z = con.execute("SELECT * FROM akte_beteiligung WHERE id = ?", (beteiligung_id,)).fetchone()
    if z is None:
        raise LookupError(f"Unbekannte Beteiligung: {beteiligung_id}")
    if rolle is not None and rolle not in ROLLEN:
        raise ValueError(f"Unbekannte Rolle: {rolle!r}")
    if rolle is not None and rolle != z["rolle"] and (z["eigene_organisation_id"] or z["eigene_person_id"]):
        raise ValueError("Die Rolle eines Eintrags aus „Eigene Daten“ lässt sich nicht ändern.")
    with con:
        con.execute("UPDATE akte_beteiligung SET rolle = COALESCE(?, rolle), aktenzeichen = COALESCE(?, aktenzeichen) "
                    "WHERE id = ?", (rolle, None if aktenzeichen is None else " ".join(aktenzeichen.split()),
                                     beteiligung_id))
        con.execute("UPDATE akte SET geaendert_am = ? WHERE id = ?", (_jetzt(), z["akte_id"]))
    return stammdaten(con, z["akte_id"])


def beteiligung_entfernen(con: sqlite3.Connection, beteiligung_id: int) -> dict:
    z = con.execute("SELECT akte_id FROM akte_beteiligung WHERE id = ?", (beteiligung_id,)).fetchone()
    if z is None:
        raise LookupError(f"Unbekannte Beteiligung: {beteiligung_id}")
    with con:
        con.execute("DELETE FROM akte_beteiligung WHERE id = ?", (beteiligung_id,))
        con.execute("UPDATE akte SET geaendert_am = ? WHERE id = ?", (_jetzt(), z["akte_id"]))
    return stammdaten(con, z["akte_id"])


def uebersicht(con: sqlite3.Connection) -> list[dict]:
    """Alle Akten mit Aktenzeichen, Mandant, Gegner und Gericht; Grundlage für Auswahl und Aktenübersicht."""
    akten = [dict(z) for z in con.execute(
        """SELECT a.*, (SELECT COUNT(*) FROM dokument d WHERE d.akte_id = a.id) AS dokumente
           FROM akte a ORDER BY a.id DESC""")]
    for a in akten:
        bet = beteiligungen(con, a["id"])
        a["mandanten"] = [b["name"] for b in bet if b["rolle"] == "mandant"]
        a["gegner"] = [b["name"] for b in bet if b["rolle"] == "gegner"]
        a["gerichte"] = [{"name": b["name"], "aktenzeichen": b["aktenzeichen"]} for b in bet if b["rolle"] == "gericht"]
        sb = a["sachbearbeiter_id"]
        a["sachbearbeiter"] = _eigene_name(con, "eigene_person", sb) if sb else None
    return akten


def geoeffnet(con: sqlite3.Connection, akte_id: int) -> dict:
    """Merkt, wann die Akte zuletzt geöffnet wurde (für „Zuletzt geöffnet“); ändert nicht „bearbeitet“."""
    _akte(con, akte_id)
    with con:
        con.execute("UPDATE akte SET geoeffnet_am = ? WHERE id = ?", (_jetzt(), akte_id))
    return {"akte_id": akte_id}
