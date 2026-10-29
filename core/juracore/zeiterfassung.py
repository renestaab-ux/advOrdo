"""Zeiterfassung je Akte: Zeiten per Timer oder von Hand, Stundensätze je Stufe, Taktung, Übernahme in die Kostennote.

Ein Stundenhonorar setzt eine Vergütungsvereinbarung in Textform voraus (§ 3a Abs. 1 S. 1 RVG); die Kostennote
weist den Zeitaufwand dann als eigenen Abschnitt aus. Getaktet wird je Eintrag auf den nächsten vollen Takt
aufgerundet (z. B. 6 Minuten = 0,1 Std.). Ob und wie getaktet werden darf, regelt die Vereinbarung; die
Taktung ist deshalb einstellbar.

Grenzen der Taktung: Eine vorformulierte 15-Minuten-Zeittaktklausel benachteiligt einen Verbraucher als Mandanten
unangemessen und ist unwirksam (BGH, Urt. v. 13.02.2020 – IX ZR 140/19); abrechenbar ist dann nur die tatsächlich
aufgewandte Zeit, die konkret darzulegen ist (welcher Schriftsatz, welche Recherche, welches Gespräch mit wem).
Die App erfasst deshalb immer minutengenau und taktet erst bei der Anzeige und Abrechnung; ab 15 Minuten Taktung
und bei Einträgen ohne konkrete Tätigkeit weist sie darauf hin.

Jeder Eintrag merkt sich Bearbeiter, Stufe und Stundensatz zum Zeitpunkt der Erfassung; eine spätere Änderung der
Sätze wirkt nur auf neue Einträge. Eine Kostennote (nicht ein Vorschuss) kennzeichnet die übernommenen Einträge als
abgerechnet; ein Storno gibt sie wieder frei. Es läuft höchstens ein Timer je Arbeitsumgebung; er steht in der
Datenbank und läuft deshalb auch nach einem Neustart der App weiter.

Vergütungsvereinbarung je Mandant: Taktung (Vorrang vor der allgemeinen), Datum der Vereinbarung und ob die
RVG-Mindestvergütung vereinbart ist; sie gilt für alle Akten des Mandanten. Je Akte kommt eine Kostenschätzung
hinzu, mit der die erfassten Zeiten verglichen werden. Die Zeiten einer Akte lassen sich als Excel, CSV, PDF oder
Word ausgeben.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .eigene import daten as eigene

_SCHEMA = """
CREATE TABLE IF NOT EXISTS zeit_stufe (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    satz         TEXT NOT NULL,             -- Euro je Stunde, netto, mit Punkt
    reihenfolge  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS zeit_bearbeiter (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    stufe_id     INTEGER REFERENCES zeit_stufe(id) ON DELETE SET NULL,
    person_id    INTEGER,                   -- Person aus Eigene Daten, falls von dort übernommen
    archiviert_am TEXT
);
CREATE TABLE IF NOT EXISTS zeit_einstellung (
    schluessel   TEXT PRIMARY KEY,
    wert         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS zeit_eintrag (
    id            INTEGER PRIMARY KEY,
    akte_id       INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    bearbeiter_id INTEGER,
    bearbeiter    TEXT NOT NULL,
    stufe         TEXT NOT NULL DEFAULT '',
    satz          TEXT,                     -- Euro je Stunde bei Erfassung; leer: kein Satz hinterlegt
    datum         TEXT NOT NULL,
    minuten       INTEGER NOT NULL DEFAULT 0,
    laeuft_seit   TEXT,                     -- Timer läuft seit (ISO-Zeitpunkt)
    taetigkeit    TEXT NOT NULL DEFAULT '',
    abrechenbar   INTEGER NOT NULL DEFAULT 1,
    kostennote_id INTEGER,                  -- abgerechnet mit dieser Kostennote
    angelegt_am   TEXT NOT NULL,
    geaendert_am  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS zeit_eintrag_akte ON zeit_eintrag(akte_id);
-- Vergütungsvereinbarung je Mandant; gilt für alle Akten, in denen er Mandant ist.
CREATE TABLE IF NOT EXISTS zeit_vereinbarung (
    mandant           TEXT PRIMARY KEY,     -- "b:<beteiligter_id>" oder (Rechtsabteilung) "o:<eigene_organisation_id>"
    taktung           INTEGER,              -- leer: Taktung aus den Einstellungen
    vereinbart_am     TEXT,                 -- Datum der Vereinbarung in Textform; leer: keine vermerkt
    mindestverguetung INTEGER NOT NULL DEFAULT 0,
    notiz             TEXT NOT NULL DEFAULT '',
    geaendert_am      TEXT NOT NULL
);
-- Kostenschätzung je Akte (Budget), mit der die erfassten Zeiten verglichen werden.
CREATE TABLE IF NOT EXISTS zeit_akte (
    akte_id           INTEGER PRIMARY KEY REFERENCES akte(id) ON DELETE CASCADE,
    kostenschaetzung  TEXT
);
"""

TAKTUNGEN = (1, 5, 6, 10, 15, 30, 60)
TAKTUNG_VORGABE = 6
# Über 6 Minuten: Literatur und Rechtsprechung sehen 5- oder 6-Minuten-Takte als Höchstgrenze einer zulässigen
# Pauschalierung (Schneider in: Lützenkirchen, Anwalts-Handbuch Mietrecht, 7. Aufl. 2025, N.; Deckenbrock, NJW 2020,
# 1776; IWW Institut, FMP 2021, 171, dort auch LG Karlsruhe: 5-Minuten-Takt formularmäßig wirksam).
TAKTUNG_EMPFOHLEN = 6
QUELLE_EMPFOHLEN = ("Schneider in: Lützenkirchen, Anwalts-Handbuch Mietrecht, 7. Aufl. 2025, N.; "
                    "Deckenbrock, NJW 2020, 1776")
# Ab 15 Minuten: BGH IX ZR 140/19 (vorformuliert, Verbraucher).
TAKTUNG_GRENZE = 15
BGH_ZEITTAKT = "BGH, Urt. v. 13.02.2020 – IX ZR 140/19"
# Weniger Wörter gelten als pauschale Angabe („Aktenbearbeitung“, „Telefonat“).
TAETIGKEIT_MIN_WOERTER = 3
# Kostenschätzung: Hinweis, sobald dieser Anteil erreicht ist.
BUDGET_WARNUNG = Decimal("0.8")

# Beispielstufen für den Anfang; Namen und Sätze sind frei änderbar (Einstellungen → Zeiterfassung).
STUFEN_VORGABE = (
    ("Equity Partner", "450.00"),
    ("Partner", "380.00"),
    ("Senior Associate", "300.00"),
    ("Associate", "250.00"),
    ("Paralegal", "120.00"),
    ("Rechtsanwaltsfachangestellte", "90.00"),
)


def _jetzt() -> datetime:
    return datetime.now().replace(microsecond=0)


def _wert(con: sqlite3.Connection, schluessel: str) -> str | None:
    z = con.execute("SELECT wert FROM zeit_einstellung WHERE schluessel = ?", (schluessel,)).fetchone()
    return z["wert"] if z else None


def _setze(con: sqlite3.Connection, schluessel: str, wert: str | None) -> None:
    if wert is None:
        con.execute("DELETE FROM zeit_einstellung WHERE schluessel = ?", (schluessel,))
    else:
        con.execute("INSERT INTO zeit_einstellung (schluessel, wert) VALUES (?, ?) "
                    "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert", (schluessel, wert))


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    # Beispielstufen nur beim ersten Mal; wer sie löscht, bekommt sie nicht wieder.
    if _wert(con, "stufen_angelegt") is None:
        for i, (name, satz) in enumerate(STUFEN_VORGABE):
            con.execute("INSERT INTO zeit_stufe (name, satz, reihenfolge) VALUES (?, ?, ?)", (name, satz, i))
        _setze(con, "stufen_angelegt", "1")
    con.commit()


# --------------------------------------------------------------------------- Hilfen


def _betrag(wert, feld: str) -> Decimal:
    """Deutsche oder englische Schreibweise: „1.234,50“, „1.000“, „1234,5“, „1234.50“."""
    t = str(wert).strip().replace(" ", "").replace("€", "")
    if "," in t or re.fullmatch(r"\d{1,3}(\.\d{3})+", t):  # „1.000“ sind tausend Euro, nicht einer
        t = t.replace(".", "").replace(",", ".")
    try:
        d = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"{feld}: „{wert}“ ist keine Zahl.") from None
    if d < 0:
        raise ValueError(f"{feld} darf nicht negativ sein.")
    return d


def _text_satz(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01")))


def getaktet(minuten: int, takt: int) -> int:
    """Auf den nächsten vollen Takt aufgerundet; 0 bleibt 0."""
    if minuten <= 0:
        return 0
    return -(-minuten // takt) * takt


def stunden_text(minuten: int) -> str:
    """6 Min. → „0,1“; 100 Min. → „1:40“ (wenn es als Dezimalzahl nicht aufgeht)."""
    if (minuten * 100) % 60 == 0:
        d = (Decimal(minuten) / 60).normalize()
        return format(d, "f").replace(".", ",")
    return f"{minuten // 60}:{minuten % 60:02d}"


def _datum(text, feld: str = "Datum") -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        raise ValueError(f"{feld}: „{text}“ ist kein Datum (JJJJ-MM-TT).") from None


def _minuten_aus(daten: dict) -> int:
    """Dauer als Minuten, „1:30“, „1,5“ (Stunden) oder von–bis."""
    if daten.get("von") and daten.get("bis"):
        def m(t: str) -> int:
            try:
                h, mi = str(t).strip().split(":")
                return int(h) * 60 + int(mi)
            except ValueError:
                raise ValueError(f"Uhrzeit „{t}“ bitte als HH:MM.") from None
        dauer = m(daten["bis"]) - m(daten["von"])
        if dauer <= 0:
            raise ValueError("„bis“ liegt nicht nach „von“.")
        return dauer
    if daten.get("minuten") not in (None, ""):
        return int(daten["minuten"])
    roh = str(daten.get("dauer") or "").strip()
    if not roh:
        return 0
    if ":" in roh:
        h, _, mi = roh.partition(":")
        try:
            return int(h or 0) * 60 + int(mi or 0)
        except ValueError:
            raise ValueError(f"Dauer „{roh}“ bitte als H:MM oder in Stunden (z. B. 1,5).") from None
    return int((_betrag(roh, "Dauer") * 60).to_integral_value())


# --------------------------------------------------------------------------- Einstellungen


def taktung(con: sqlite3.Connection) -> int:
    t = _wert(con, "taktung")
    return int(t) if t and t.isdigit() and int(t) in TAKTUNGEN else TAKTUNG_VORGABE


def _stufen(con: sqlite3.Connection) -> list[dict]:
    return [dict(z) for z in con.execute("SELECT * FROM zeit_stufe ORDER BY reihenfolge, id")]


def _bearbeiter(con: sqlite3.Connection, mit_archiv: bool = True) -> list[dict]:
    zeilen = con.execute(
        """SELECT b.id, b.name, b.stufe_id, b.person_id, b.archiviert_am, s.name AS stufe, s.satz
           FROM zeit_bearbeiter b LEFT JOIN zeit_stufe s ON s.id = b.stufe_id
           ORDER BY b.archiviert_am IS NOT NULL, COALESCE(s.reihenfolge, 999), b.name COLLATE NOCASE""")
    aus = []
    for z in zeilen:
        if z["archiviert_am"] and not mit_archiv:
            continue
        aus.append({"id": z["id"], "name": z["name"], "stufe_id": z["stufe_id"], "stufe": z["stufe"] or "",
                    "satz": z["satz"], "person_id": z["person_id"], "archiviert": z["archiviert_am"] is not None})
    return aus


def taktung_hinweis(takt: int) -> str | None:
    if takt <= TAKTUNG_EMPFOHLEN:
        return None
    if takt < TAKTUNG_GRENZE:
        return (f"{takt} Minuten liegen über der Höchstgrenze von 5 bis 6 Minuten, die Literatur und Rechtsprechung "
                f"für eine zulässige Pauschalierung sehen ({QUELLE_EMPFOHLEN}); das wird auch für Unternehmer als "
                "Mandanten empfohlen. Erfasst wird weiter minutengenau.")
    return (f"Vorsicht bei {takt}-Minuten-Taktung: Vorformuliert gegenüber einem Verbraucher ist schon eine "
            f"15-Minuten-Zeittaktklausel unwirksam ({BGH_ZEITTAKT}); dann ist nur die tatsächliche Zeit abrechenbar. "
            f"Empfohlen sind höchstens 5 bis 6 Minuten, auch bei Unternehmern ({QUELLE_EMPFOHLEN}). Die minutengenauen "
            "Zeiten bleiben erhalten.")


def _mandant_natuerliche_person(con: sqlite3.Connection, akte_id: int) -> bool:
    z = con.execute("""SELECT 1 FROM akte_beteiligung b JOIN beteiligter t ON t.id = b.beteiligter_id
                       WHERE b.akte_id = ? AND b.rolle = 'mandant' AND t.art = 'person' LIMIT 1""",
                    (akte_id,)).fetchone()
    return z is not None


def akte_hinweise(con: sqlite3.Connection, akte_id: int, takt: int) -> list[str]:
    """Hinweise zur Taktung in dieser Akte: Mandant ist eine natürliche Person (womöglich Verbraucher)."""
    if takt <= TAKTUNG_EMPFOHLEN or not _mandant_natuerliche_person(con, akte_id):
        return []
    if takt >= TAKTUNG_GRENZE:
        return [f"Der Mandant ist eine natürliche Person und womöglich Verbraucher. Eine vorformulierte Taktung von "
                f"{takt} Minuten wäre ihm gegenüber unwirksam ({BGH_ZEITTAKT}); dann gilt nur die tatsächliche "
                "Zeit (Spalte „Dauer“). Für diese Akte besser minutengenau oder mit höchstens 6 Minuten abrechnen."]
    return [f"Der Mandant ist eine natürliche Person und womöglich Verbraucher. {takt} Minuten liegen über den 5 bis "
            f"6 Minuten, die als zulässige Höchstgrenze gelten ({QUELLE_EMPFOHLEN})."]


# --------------------------------------------------------------------------- Vereinbarung je Mandant


def _mandanten(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    """Mandanten der Akte in der Reihenfolge der Beteiligtenliste."""
    aus = []
    for z in con.execute("""SELECT b.beteiligter_id, b.eigene_organisation_id, t.name, t.art, o.daten AS org
                            FROM akte_beteiligung b
                            LEFT JOIN beteiligter t ON t.id = b.beteiligter_id
                            LEFT JOIN eigene_organisation o ON o.id = b.eigene_organisation_id
                            WHERE b.akte_id = ? AND b.rolle = 'mandant' ORDER BY b.id""", (akte_id,)):
        if z["beteiligter_id"] is not None:
            aus.append({"schluessel": f"b:{z['beteiligter_id']}", "name": z["name"], "person": z["art"] == "person"})
        elif z["eigene_organisation_id"] is not None:
            name = json.loads(z["org"] or "{}").get("name") or "Konzerngesellschaft"
            aus.append({"schluessel": f"o:{z['eigene_organisation_id']}", "name": name, "person": False})
    return aus


def _vereinbarung_zeile(con: sqlite3.Connection, schluessel: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM zeit_vereinbarung WHERE mandant = ?", (schluessel,)).fetchone()


def _akten_des_mandanten(con: sqlite3.Connection, schluessel: str) -> int:
    art, _, nr = schluessel.partition(":")
    spalte = "beteiligter_id" if art == "b" else "eigene_organisation_id"
    return con.execute(f"SELECT COUNT(DISTINCT akte_id) FROM akte_beteiligung WHERE rolle = 'mandant' "
                       f"AND {spalte} = ?", (int(nr),)).fetchone()[0]


def akte_taktung(con: sqlite3.Connection, akte_id: int) -> int:
    """Taktung der Akte: die aus der Vereinbarung mit dem (ersten) Mandanten, sonst die allgemeine."""
    mandanten = _mandanten(con, akte_id)
    z = _vereinbarung_zeile(con, mandanten[0]["schluessel"]) if mandanten else None
    return z["taktung"] if z is not None and z["taktung"] in TAKTUNGEN else taktung(con)


def _kostenschaetzung(con: sqlite3.Connection, akte_id: int) -> str | None:
    z = con.execute("SELECT kostenschaetzung FROM zeit_akte WHERE akte_id = ?", (akte_id,)).fetchone()
    return z["kostenschaetzung"] if z and z["kostenschaetzung"] else None


def vereinbarung(con: sqlite3.Connection, akte_id: int) -> dict:
    """Was für die Akte vereinbart ist: Vereinbarung mit dem (ersten) Mandanten, wirksame Taktung, Kostenschätzung
    der Akte."""
    mandanten = _mandanten(con, akte_id)
    m = mandanten[0] if mandanten else None
    z = _vereinbarung_zeile(con, m["schluessel"]) if m else None
    allgemein = taktung(con)
    eigen = z["taktung"] if z is not None and z["taktung"] in TAKTUNGEN else None
    hinweise = []
    andere = [x["name"] for x in mandanten[1:] if _vereinbarung_zeile(con, x["schluessel"]) is not None]
    if andere:
        hinweise.append(f"Die Akte hat mehrere Mandanten. Maßgeblich ist hier die Vereinbarung mit {m['name']}; die "
                        f"mit {', '.join(andere)} gilt in dieser Akte nicht.")
    return {"mandant": m | {"akten": _akten_des_mandanten(con, m["schluessel"])} if m else None,
            "vermerkt": z is not None, "taktung": eigen or allgemein, "taktung_eigen": eigen,
            "taktung_allgemein": allgemein, "vereinbart_am": z["vereinbart_am"] if z is not None else None,
            "mindestverguetung": bool(z["mindestverguetung"]) if z is not None else False,
            "notiz": z["notiz"] if z is not None else "", "kostenschaetzung": _kostenschaetzung(con, akte_id),
            "hinweise": hinweise}


def vereinbarung_speichern(con: sqlite3.Connection, akte_id: int, daten: dict) -> dict:
    """Speichert die Vereinbarung mit dem Mandanten der Akte (taktung, vereinbart_am, mindestverguetung, notiz)
    und die Kostenschätzung der Akte; liefert die Liste der Akte."""
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    mandanten = _mandanten(con, akte_id)
    felder = ("taktung", "vereinbart_am", "mindestverguetung", "notiz")
    jetzt = _jetzt().isoformat()
    with con:
        if "kostenschaetzung" in daten:
            roh = daten.get("kostenschaetzung")
            k = _text_satz(_betrag(roh, "Kostenschätzung")) if roh not in (None, "") else None
            con.execute("INSERT INTO zeit_akte (akte_id, kostenschaetzung) VALUES (?, ?) ON CONFLICT(akte_id) "
                        "DO UPDATE SET kostenschaetzung = excluded.kostenschaetzung", (akte_id, k))
        if any(f in daten for f in felder):
            if not mandanten:
                raise ValueError("Der Akte ist noch kein Mandant zugeordnet. Die Vereinbarung gilt je Mandant; bitte "
                                 "zuerst unter „Beteiligte“ den Mandanten eintragen.")
            alt = _vereinbarung_zeile(con, mandanten[0]["schluessel"])
            takt = daten.get("taktung", alt["taktung"] if alt is not None else None)
            if takt in ("", None):
                takt = None
            elif int(takt) not in TAKTUNGEN:
                raise ValueError(f"Taktung {takt} Minuten gibt es nicht; möglich: {', '.join(map(str, TAKTUNGEN))}.")
            else:
                takt = int(takt)
            am = daten.get("vereinbart_am", alt["vereinbart_am"] if alt is not None else None)
            am = _datum(am, "Vereinbart am").isoformat() if am else None
            mindest = int(bool(daten.get("mindestverguetung", alt["mindestverguetung"] if alt is not None else 0)))
            notiz = str(daten.get("notiz", alt["notiz"] if alt is not None else "") or "").strip()
            con.execute("""INSERT INTO zeit_vereinbarung (mandant, taktung, vereinbart_am, mindestverguetung, notiz,
                               geaendert_am) VALUES (?, ?, ?, ?, ?, ?)
                           ON CONFLICT(mandant) DO UPDATE SET taktung = excluded.taktung,
                               vereinbart_am = excluded.vereinbart_am, mindestverguetung = excluded.mindestverguetung,
                               notiz = excluded.notiz, geaendert_am = excluded.geaendert_am""",
                        (mandanten[0]["schluessel"], takt, am, mindest, notiz, jetzt))
    return liste(con, akte_id)


def _budget_hinweis(kostenschaetzung: str | None, betrag: Decimal) -> tuple[int | None, str | None]:
    if not kostenschaetzung or Decimal(kostenschaetzung) <= 0:
        return None, None
    k = Decimal(kostenschaetzung)
    anteil = int((betrag * 100 / k).to_integral_value())
    if betrag < k * BUDGET_WARNUNG:
        return anteil, None
    wort = "überschreiten" if betrag > k else "erreichen"
    return anteil, (f"Die erfassten Zeiten ({_euro(betrag)}) {wort} {anteil} % der Kostenschätzung "
                    f"({_euro(k)}). Bitte den Mandanten rechtzeitig unterrichten, wenn sich eine Überschreitung "
                    "abzeichnet.")


def _euro(d: Decimal) -> str:
    t = f"{d.quantize(Decimal('0.01')):,.2f}"
    return t.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _keine_vereinbarung(v: dict) -> str | None:
    if v["mandant"] is None or v["vereinbart_am"]:
        return None
    return (f"Für {v['mandant']['name']} ist keine Vergütungsvereinbarung vermerkt. Ein Zeithonorar setzt eine "
            "Vereinbarung in Textform voraus (§ 3a Abs. 1 S. 1 RVG); ohne sie kann nur die gesetzliche Vergütung "
            "verlangt werden (§ 4b S. 1 RVG). Eine Vorlage gibt es unter „Schriftstücke“.")


def einstellungen(con: sqlite3.Connection) -> dict:
    standard = _wert(con, "standard_bearbeiter")
    takt = taktung(con)
    return {"taktung": takt, "taktungen": list(TAKTUNGEN), "taktung_hinweis": taktung_hinweis(takt),
            "stufen": _stufen(con), "bearbeiter": _bearbeiter(con),
            "standard_bearbeiter_id": int(standard) if standard else None}


def taktung_setzen(con: sqlite3.Connection, minuten: int) -> dict:
    if int(minuten) not in TAKTUNGEN:
        raise ValueError(f"Taktung {minuten} Minuten gibt es nicht; möglich: {', '.join(map(str, TAKTUNGEN))}.")
    with con:
        _setze(con, "taktung", str(int(minuten)))
    return einstellungen(con)


def stufe_speichern(con: sqlite3.Connection, name: str, satz, stufe_id: int | None = None) -> dict:
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("Bitte einen Namen für die Stufe angeben.")
    s = _text_satz(_betrag(satz, "Stundensatz"))
    with con:
        if stufe_id is None:
            r = con.execute("SELECT COALESCE(MAX(reihenfolge), -1) + 1 FROM zeit_stufe").fetchone()[0]
            con.execute("INSERT INTO zeit_stufe (name, satz, reihenfolge) VALUES (?, ?, ?)", (name, s, r))
        else:
            if con.execute("UPDATE zeit_stufe SET name = ?, satz = ? WHERE id = ?", (name, s, stufe_id)).rowcount == 0:
                raise LookupError(f"Stufe {stufe_id} gibt es nicht.")
    return einstellungen(con)


def stufe_loeschen(con: sqlite3.Connection, stufe_id: int) -> dict:
    """Bearbeiter dieser Stufe verlieren ihren Satz; erfasste Zeiten behalten den Satz der Erfassung."""
    with con:
        con.execute("DELETE FROM zeit_stufe WHERE id = ?", (stufe_id,))
    return einstellungen(con)


def stufe_verschieben(con: sqlite3.Connection, stufe_id: int, richtung: int) -> dict:
    ids = [s["id"] for s in _stufen(con)]
    if stufe_id not in ids:
        raise LookupError(f"Stufe {stufe_id} gibt es nicht.")
    i = ids.index(stufe_id)
    j = max(0, min(len(ids) - 1, i + (1 if richtung > 0 else -1)))
    ids[i], ids[j] = ids[j], ids[i]
    with con:
        for n, sid in enumerate(ids):
            con.execute("UPDATE zeit_stufe SET reihenfolge = ? WHERE id = ?", (n, sid))
    return einstellungen(con)


def bearbeiter_speichern(con: sqlite3.Connection, name: str, stufe_id: int | None = None,
                         bearbeiter_id: int | None = None, archiviert: bool | None = None) -> dict:
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("Bitte einen Namen angeben.")
    if stufe_id is not None and con.execute("SELECT 1 FROM zeit_stufe WHERE id = ?", (stufe_id,)).fetchone() is None:
        raise LookupError(f"Stufe {stufe_id} gibt es nicht.")
    with con:
        if bearbeiter_id is None:
            con.execute("INSERT INTO zeit_bearbeiter (name, stufe_id) VALUES (?, ?)", (name, stufe_id))
        else:
            archiv = None if archiviert is None else (_jetzt().isoformat() if archiviert else "")
            n = con.execute("UPDATE zeit_bearbeiter SET name = ?, stufe_id = ?, "
                            "archiviert_am = CASE WHEN ? IS NULL THEN archiviert_am ELSE NULLIF(?, '') END "
                            "WHERE id = ?", (name, stufe_id, archiv, archiv, bearbeiter_id)).rowcount
            if n == 0:
                raise LookupError(f"Bearbeiter {bearbeiter_id} gibt es nicht.")
    return einstellungen(con)


def bearbeiter_loeschen(con: sqlite3.Connection, bearbeiter_id: int) -> dict:
    """Ohne erfasste Zeiten wird gelöscht, sonst nur archiviert (die Zeiten nennen ihn weiter)."""
    with con:
        if con.execute("SELECT 1 FROM zeit_eintrag WHERE bearbeiter_id = ? LIMIT 1", (bearbeiter_id,)).fetchone():
            con.execute("UPDATE zeit_bearbeiter SET archiviert_am = ? WHERE id = ?",
                        (_jetzt().isoformat(), bearbeiter_id))
        else:
            con.execute("DELETE FROM zeit_bearbeiter WHERE id = ?", (bearbeiter_id,))
        if _wert(con, "standard_bearbeiter") == str(bearbeiter_id):
            _setze(con, "standard_bearbeiter", None)
    return einstellungen(con)


def standard_setzen(con: sqlite3.Connection, bearbeiter_id: int | None) -> dict:
    with con:
        _setze(con, "standard_bearbeiter", None if bearbeiter_id is None else str(int(bearbeiter_id)))
    return einstellungen(con)


def aus_eigenen_daten(con: sqlite3.Connection) -> dict:
    """Übernimmt die eigene Person und die Berufsträger aus Eigene Daten als Bearbeiter (ohne Stufe)."""
    s = eigene.stand(con, mit_archiv=False)
    personen = []
    if s.get("inhaber"):
        personen.append(s["inhaber"])
    personen += [b for b in s.get("berufstraeger") or [] if not b.get("archiviert")]
    vorhanden = {z["person_id"] for z in con.execute("SELECT person_id FROM zeit_bearbeiter")}
    neu = 0
    with con:
        for p in personen:
            if p["id"] in vorhanden:
                continue
            name = eigene.anzeigename(p["daten"], "person_anwalt")
            if not name:
                continue
            con.execute("INSERT INTO zeit_bearbeiter (name, person_id) VALUES (?, ?)", (name, p["id"]))
            vorhanden.add(p["id"])
            neu += 1
        if neu and s.get("inhaber") and _wert(con, "standard_bearbeiter") is None:
            z = con.execute("SELECT id FROM zeit_bearbeiter WHERE person_id = ?", (s["inhaber"]["id"],)).fetchone()
            if z:
                _setze(con, "standard_bearbeiter", str(z["id"]))
    return einstellungen(con) | {"neu": neu}


# --------------------------------------------------------------------------- Einträge


def _bearbeiter_von(con: sqlite3.Connection, bearbeiter_id: int | None) -> dict:
    if bearbeiter_id is None:
        standard = _wert(con, "standard_bearbeiter")
        bearbeiter_id = int(standard) if standard else None
    if bearbeiter_id is None:
        raise ValueError("Bitte einen Bearbeiter wählen (Einstellungen → Zeiterfassung).")
    b = next((x for x in _bearbeiter(con) if x["id"] == int(bearbeiter_id)), None)
    if b is None:
        raise LookupError(f"Bearbeiter {bearbeiter_id} gibt es nicht.")
    return b


def _mit_stufe(con: sqlite3.Connection, b: dict, stufe_id) -> dict:
    """Abweichende Stufe für einen einzelnen Eintrag, z. B. „Reisezeit“: Name und Satz kommen dann von ihr."""
    if stufe_id in (None, ""):
        return b
    z = con.execute("SELECT name, satz FROM zeit_stufe WHERE id = ?", (int(stufe_id),)).fetchone()
    if z is None:
        raise LookupError(f"Stufe {stufe_id} gibt es nicht.")
    return b | {"stufe": z["name"], "satz": z["satz"]}


def _laufzeit(laeuft_seit: str, jetzt: datetime) -> int:
    """Minuten seit dem Start, kaufmännisch gerundet, mindestens eine."""
    sekunden = (jetzt - datetime.fromisoformat(laeuft_seit)).total_seconds()
    return max(1, int((sekunden + 30) // 60))


def _eintrag(z: sqlite3.Row, takt: int, jetzt: datetime | None = None) -> dict:
    minuten = z["minuten"]
    if z["laeuft_seit"]:
        minuten += _laufzeit(z["laeuft_seit"], jetzt or _jetzt())
    g = getaktet(minuten, takt) if z["abrechenbar"] else 0
    betrag = (Decimal(g) * Decimal(z["satz"]) / 60).quantize(Decimal("0.01")) if z["satz"] and g else None
    return {"id": z["id"], "akte_id": z["akte_id"], "bearbeiter_id": z["bearbeiter_id"], "bearbeiter": z["bearbeiter"],
            "stufe": z["stufe"], "satz": z["satz"], "datum": z["datum"], "minuten": minuten, "getaktet": g,
            "betrag": None if betrag is None else str(betrag), "laeuft_seit": z["laeuft_seit"],
            "taetigkeit": z["taetigkeit"], "abrechenbar": bool(z["abrechenbar"]),
            "kostennote_id": z["kostennote_id"], "kostennote": z["kostennote"] if "kostennote" in z.keys() else None}


_AUSWAHL = """SELECT e.*, k.nummer AS kostennote FROM zeit_eintrag e
              LEFT JOIN kostennote k ON k.id = e.kostennote_id"""


def liste(con: sqlite3.Connection, akte_id: int) -> dict:
    """Einträge der Akte (neueste zuerst) mit Summen je Bearbeiter, dem gerade laufenden Timer, der Vereinbarung mit
    dem Mandanten und dem Stand gegenüber der Kostenschätzung."""
    v = vereinbarung(con, akte_id)
    takt = v["taktung"]
    jetzt = _jetzt()
    eintraege = [_eintrag(z, takt, jetzt) for z in con.execute(
        _AUSWAHL + " WHERE e.akte_id = ? ORDER BY e.datum DESC, e.id DESC", (akte_id,))]
    summen: dict[tuple, dict] = {}
    gesamt = {"minuten": 0, "getaktet": 0, "betrag": Decimal(0), "offen": Decimal(0), "offen_minuten": 0}
    for e in eintraege:
        s = summen.setdefault((e["bearbeiter"], e["stufe"]), {"bearbeiter": e["bearbeiter"], "stufe": e["stufe"],
                                                               "minuten": 0, "getaktet": 0, "betrag": Decimal(0)})
        s["minuten"] += e["minuten"]
        s["getaktet"] += e["getaktet"]
        gesamt["minuten"] += e["minuten"]
        gesamt["getaktet"] += e["getaktet"]
        if e["betrag"]:
            s["betrag"] += Decimal(e["betrag"])
            gesamt["betrag"] += Decimal(e["betrag"])
            if not e["kostennote_id"]:
                gesamt["offen"] += Decimal(e["betrag"])
        if e["abrechenbar"] and not e["kostennote_id"]:
            gesamt["offen_minuten"] += e["getaktet"]
    for s in summen.values():
        s["betrag"] = str(s["betrag"])
    anteil, budget = _budget_hinweis(v["kostenschaetzung"], gesamt["betrag"])
    gesamt["budget_anteil"] = anteil
    for k in ("betrag", "offen"):
        gesamt[k] = str(gesamt[k])
    hinweise = v["hinweise"] + akte_hinweise(con, akte_id, takt)
    if any(e["satz"] and e["abrechenbar"] for e in eintraege) and (h := _keine_vereinbarung(v)):
        hinweise.append(h)
    if budget:
        hinweise.append(budget)
    return {"eintraege": eintraege, "summen": list(summen.values()), "gesamt": gesamt, "taktung": takt,
            "laufend": laufend(con), "vereinbarung": v, "hinweise": hinweise}


def _pruefe_offen(con: sqlite3.Connection, eintrag_id: int) -> sqlite3.Row:
    z = con.execute(_AUSWAHL + " WHERE e.id = ?", (eintrag_id,)).fetchone()
    if z is None:
        raise LookupError(f"Zeiteintrag {eintrag_id} gibt es nicht.")
    if z["kostennote_id"]:
        raise ValueError(f"Dieser Eintrag ist mit Rechnung {z['kostennote']} abgerechnet und lässt sich nicht mehr "
                         "ändern. Erst die Rechnung stornieren.")
    return z


def speichern(con: sqlite3.Connection, akte_id: int, daten: dict, eintrag_id: int | None = None) -> dict:
    """Legt einen Eintrag von Hand an oder ändert ihn. ``daten``: datum, dauer | minuten | von+bis, bearbeiter_id,
    taetigkeit, abrechenbar, wahlweise stufe_id (abweichende Stufe nur für diesen Eintrag, z. B. Reisezeit) und satz
    (sonst der Satz der Stufe)."""
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    tag = _datum(daten.get("datum") or date.today().isoformat())
    alt = _pruefe_offen(con, eintrag_id) if eintrag_id is not None else None
    # Bei laufendem Timer bleibt die bisher gestoppte Zeit; die laufende kommt beim Anhalten hinzu.
    minuten = alt["minuten"] if alt is not None and alt["laeuft_seit"] else _minuten_aus(daten)
    if minuten <= 0 and not (alt is not None and alt["laeuft_seit"]):
        raise ValueError("Bitte eine Dauer angeben.")
    if minuten > 24 * 60:
        raise ValueError("Ein Eintrag kann höchstens 24 Stunden umfassen.")
    if alt is not None and daten.get("bearbeiter_id") in (None, alt["bearbeiter_id"]):
        b = {"id": alt["bearbeiter_id"], "name": alt["bearbeiter"], "stufe": alt["stufe"], "satz": alt["satz"]}
    else:
        b = _bearbeiter_von(con, daten.get("bearbeiter_id"))
    b = _mit_stufe(con, b, daten.get("stufe_id"))
    satz = _text_satz(_betrag(daten["satz"], "Stundensatz")) if daten.get("satz") not in (None, "") else b["satz"]
    taetigkeit = " ".join(str(daten.get("taetigkeit") or "").split())
    abrechenbar = int(bool(daten.get("abrechenbar", True)))
    jetzt = _jetzt().isoformat()
    with con:
        if alt is None:
            con.execute("INSERT INTO zeit_eintrag (akte_id, bearbeiter_id, bearbeiter, stufe, satz, datum, minuten, "
                        "taetigkeit, abrechenbar, angelegt_am, geaendert_am) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (akte_id, b["id"], b["name"], b["stufe"] or "", satz, tag.isoformat(), minuten, taetigkeit,
                         abrechenbar, jetzt, jetzt))
        else:
            con.execute("UPDATE zeit_eintrag SET bearbeiter_id = ?, bearbeiter = ?, stufe = ?, satz = ?, datum = ?, "
                        "minuten = ?, taetigkeit = ?, abrechenbar = ?, geaendert_am = ? WHERE id = ?",
                        (b["id"], b["name"], b["stufe"] or "", satz, tag.isoformat(), minuten,
                         taetigkeit, abrechenbar, jetzt, eintrag_id))
    return liste(con, akte_id)


def loeschen(con: sqlite3.Connection, eintrag_id: int) -> dict:
    z = _pruefe_offen(con, eintrag_id)
    with con:
        con.execute("DELETE FROM zeit_eintrag WHERE id = ?", (eintrag_id,))
    return liste(con, z["akte_id"])


# --------------------------------------------------------------------------- Timer


def laufend(con: sqlite3.Connection) -> dict | None:
    """Der laufende Timer der Umgebung mit Aktenname, oder None."""
    z = con.execute(
        """SELECT e.*, NULL AS kostennote, a.name AS akte, a.aktenzeichen FROM zeit_eintrag e
           JOIN akte a ON a.id = e.akte_id WHERE e.laeuft_seit IS NOT NULL ORDER BY e.laeuft_seit DESC LIMIT 1"""
    ).fetchone()
    if z is None:
        return None
    jetzt = _jetzt()
    sekunden = int((jetzt - datetime.fromisoformat(z["laeuft_seit"])).total_seconds()) + z["minuten"] * 60
    return _eintrag(z, akte_taktung(con, z["akte_id"]), jetzt) | {"akte": z["akte"], "aktenzeichen": z["aktenzeichen"],
                                                "sekunden": max(0, sekunden)}


def _anhalten(con: sqlite3.Connection, jetzt: datetime) -> None:
    for z in con.execute("SELECT id, minuten, laeuft_seit FROM zeit_eintrag WHERE laeuft_seit IS NOT NULL").fetchall():
        con.execute("UPDATE zeit_eintrag SET minuten = ?, laeuft_seit = NULL, geaendert_am = ? WHERE id = ?",
                    (z["minuten"] + _laufzeit(z["laeuft_seit"], jetzt), jetzt.isoformat(), z["id"]))


def starten(con: sqlite3.Connection, akte_id: int, bearbeiter_id: int | None = None, taetigkeit: str = "",
            eintrag_id: int | None = None, jetzt: datetime | None = None, stufe_id: int | None = None) -> dict:
    """Startet einen Timer; ein anderer laufender wird dabei angehalten. Mit ``eintrag_id`` läuft ein offener
    Eintrag weiter (Fortsetzen)."""
    jetzt = jetzt or _jetzt()
    if eintrag_id is not None:
        z = _pruefe_offen(con, eintrag_id)
        if z["laeuft_seit"]:
            return liste(con, z["akte_id"])
        akte_id = z["akte_id"]
    elif con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    b = _mit_stufe(con, _bearbeiter_von(con, bearbeiter_id), stufe_id) if eintrag_id is None else None
    with con:
        _anhalten(con, jetzt)
        if eintrag_id is not None:
            con.execute("UPDATE zeit_eintrag SET laeuft_seit = ?, geaendert_am = ? WHERE id = ?",
                        (jetzt.isoformat(), jetzt.isoformat(), eintrag_id))
        else:
            con.execute("INSERT INTO zeit_eintrag (akte_id, bearbeiter_id, bearbeiter, stufe, satz, datum, minuten, "
                        "laeuft_seit, taetigkeit, abrechenbar, angelegt_am, geaendert_am) "
                        "VALUES (?,?,?,?,?,?,0,?,?,1,?,?)",
                        (akte_id, b["id"], b["name"], b["stufe"] or "", b["satz"], jetzt.date().isoformat(),
                         jetzt.isoformat(), " ".join(str(taetigkeit or "").split()), jetzt.isoformat(),
                         jetzt.isoformat()))
    return liste(con, akte_id)


def stoppen(con: sqlite3.Connection, jetzt: datetime | None = None) -> dict | None:
    """Hält den laufenden Timer an; liefert die Liste seiner Akte (oder None, wenn keiner lief)."""
    z = con.execute("SELECT akte_id FROM zeit_eintrag WHERE laeuft_seit IS NOT NULL LIMIT 1").fetchone()
    if z is None:
        return None
    with con:
        _anhalten(con, jetzt or _jetzt())
    return liste(con, z["akte_id"])


# --------------------------------------------------------------------------- Kostennote


def fuer_kostennote(con: sqlite3.Connection, akte_id: int) -> dict:
    """Offene, abrechenbare Zeiten der Akte als Posten „Stunden × Satz“, je Bearbeiter, Stufe und Satz; dazu, ob mit
    dem Mandanten die RVG-Mindestvergütung vereinbart ist (None: keine Vereinbarung vermerkt)."""
    v = vereinbarung(con, akte_id)
    takt = v["taktung"]
    gruppen: dict[tuple, dict] = {}
    hinweise: list[str] = []
    tage: list[str] = []
    ohne_satz = 0
    zeilen = con.execute("SELECT *, NULL AS kostennote FROM zeit_eintrag WHERE akte_id = ? AND kostennote_id IS NULL "
                         "AND abrechenbar = 1 ORDER BY datum, id", (akte_id,)).fetchall()
    for z in zeilen:
        if z["laeuft_seit"]:
            hinweise.append("Ein Timer läuft noch; seine Zeit ist nicht enthalten. Erst anhalten.")
            continue
        if not z["satz"]:
            ohne_satz += 1
            continue
        g = gruppen.setdefault((z["bearbeiter"], z["stufe"], z["satz"]),
                               {"bearbeiter": z["bearbeiter"], "stufe": z["stufe"], "satz": z["satz"], "minuten": 0,
                                "ids": []})
        g["minuten"] += getaktet(z["minuten"], takt)
        g["ids"].append(z["id"])
        tage.append(z["datum"])
    knapp = sum(1 for z in zeilen if not z["laeuft_seit"] and z["satz"]
                and len(z["taetigkeit"].split()) < TAETIGKEIT_MIN_WOERTER)
    if knapp:
        hinweise.append(f"{knapp} Eintrag/Einträge ohne konkrete Tätigkeit. Pauschale Angaben wie „Aktenbearbeitung“ "
                        f"oder „Telefonat“ reichen als Nachweis nicht; zu nennen ist, welcher Schriftsatz, welche "
                        f"Recherche, welches Gespräch mit wem ({BGH_ZEITTAKT}). Bitte im Reiter „Zeiten“ ergänzen.")
    hinweise += v["hinweise"] + akte_hinweise(con, akte_id, takt)
    if gruppen and (h := _keine_vereinbarung(v)):
        hinweise.append(h)
    if ohne_satz:
        hinweise.append(f"{ohne_satz} Eintrag/Einträge ohne Stundensatz bleiben offen; bitte dem Bearbeiter eine Stufe "
                        "zuordnen oder den Satz im Eintrag ergänzen.")
    posten = []
    for g in gruppen.values():
        wer = f"{g['bearbeiter']} ({g['stufe']})" if g["stufe"] else g["bearbeiter"]
        posten.append({"typ": "stunden", "text": wer, "minuten": g["minuten"],
                       "stunden": str((Decimal(g["minuten"]) / 60).quantize(Decimal("0.01"))),
                       "stundensatz": g["satz"], "quelle": g["ids"]})
    zeitraum = ""
    if tage:
        von, bis = date.fromisoformat(min(tage)), date.fromisoformat(max(tage))
        zeitraum = (von.strftime("%d.%m.%Y") if von == bis
                    else f"{von.strftime('%d.%m.%Y')} bis {bis.strftime('%d.%m.%Y')}")
    return {"posten": posten, "leistungszeitraum": zeitraum, "taktung": takt,
            "mindestverguetung": v["mindestverguetung"] if v["vermerkt"] else None,
            "hinweise": list(dict.fromkeys(hinweise))}


def nachweis(con: sqlite3.Connection, ids: list[int]) -> list[dict]:
    """Tätigkeitsnachweis zu übernommenen Zeiten: jede Einheit mit Datum, Bearbeiter, Tätigkeit und Dauer, wie es
    die Rechtsprechung zur Darlegung von Stundenhonoraren verlangt (IWW Institut, FMP 2022, 89; Krumscheid in:
    Heidel/Pauly, AnwaltFormulare, § 57)."""
    if not ids:
        return []
    marken = ",".join("?" * len(ids))
    zeilen = con.execute(f"SELECT *, NULL AS kostennote FROM zeit_eintrag WHERE id IN ({marken}) "
                         "ORDER BY datum, id", [int(i) for i in ids]).fetchall()
    takte: dict[int, int] = {}
    return [_eintrag(z, takte.setdefault(z["akte_id"], akte_taktung(con, z["akte_id"]))) for z in zeilen]


def abrechnen(con: sqlite3.Connection, akte_id: int, ids: list[int], kostennote_id: int) -> None:
    """Kennzeichnet Einträge als abgerechnet (innerhalb der Transaktion des Aufrufers)."""
    for i in ids:
        z = con.execute("SELECT akte_id, kostennote_id, laeuft_seit FROM zeit_eintrag WHERE id = ?", (i,)).fetchone()
        if z is None or z["akte_id"] != akte_id:
            raise ValueError("Ein übernommener Zeiteintrag gehört nicht (mehr) zu dieser Akte.")
        if z["kostennote_id"] is not None:
            raise ValueError("Ein übernommener Zeiteintrag ist schon abgerechnet. Bitte „Zeiten übernehmen“ neu "
                             "ausführen.")
        if z["laeuft_seit"]:
            raise ValueError("Ein übernommener Zeiteintrag läuft noch als Timer.")
    con.executemany("UPDATE zeit_eintrag SET kostennote_id = ? WHERE id = ?", [(kostennote_id, i) for i in ids])


def pruefe_quellen(con: sqlite3.Connection, akte_id: int, ids: list[int]) -> None:
    """Wie ``abrechnen``, aber ohne zu schreiben: vor dem Erzeugen der Datei."""
    for i in ids:
        z = con.execute("SELECT akte_id, kostennote_id, laeuft_seit FROM zeit_eintrag WHERE id = ?", (i,)).fetchone()
        if z is None or z["akte_id"] != akte_id or z["kostennote_id"] is not None or z["laeuft_seit"]:
            raise ValueError("Die übernommenen Zeiten sind nicht mehr offen (schon abgerechnet, gelöscht oder Timer "
                             "läuft). Bitte „Zeiten übernehmen“ neu ausführen.")


def freigeben(con: sqlite3.Connection, kostennote_id: int) -> None:
    """Nach einem Storno sind die Zeiten wieder offen (innerhalb der Transaktion des Aufrufers)."""
    con.execute("UPDATE zeit_eintrag SET kostennote_id = NULL WHERE kostennote_id = ?", (kostennote_id,))


# --------------------------------------------------------------------------- Export

EXPORT_FORMATE = {"xlsx": "Excel", "csv": "CSV", "pdf": "PDF", "docx": "Word"}
_SPALTEN = ("Datum", "Bearbeiter", "Stufe", "Tätigkeit", "Dauer (Min.)", "Getaktet (Std.)", "Stundensatz (€)",
            "Betrag (€)", "Abrechenbar", "Rechnung")


def _de(text: str | None) -> str:
    return (text or "").replace(".", ",")


def _tag(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def _export_daten(con: sqlite3.Connection, akte_id: int, nur_offen: bool) -> tuple[dict, list[dict], dict]:
    akte = con.execute("SELECT name, aktenzeichen FROM akte WHERE id = ?", (akte_id,)).fetchone()
    if akte is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    stand = liste(con, akte_id)
    eintraege = [e for e in reversed(stand["eintraege"]) if not nur_offen or not e["kostennote_id"]]
    return dict(akte), eintraege, stand


def als_csv(eintraege: list[dict]) -> str:
    """CSV mit Semikolon und Dezimalkomma, wie es Excel in deutscher Einstellung erwartet."""
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow(_SPALTEN)
    for e in eintraege:
        w.writerow(_zeile(e, text=True))
    return puffer.getvalue()


def _zeile(e: dict, text: bool) -> list:
    stunden = Decimal(e["getaktet"]) / 60
    stunden_wert = _de(str(stunden.quantize(Decimal("0.01")))) if text else float(stunden)
    satz = (_de(e["satz"]) if text else float(e["satz"])) if e["satz"] else ""
    betrag = (_de(e["betrag"]) if text else float(e["betrag"])) if e["betrag"] else ""
    taetigkeit = e["taetigkeit"] + (" (Timer läuft)" if e["laeuft_seit"] else "")
    return [_tag(e["datum"]), e["bearbeiter"], e["stufe"], taetigkeit, e["minuten"], stunden_wert, satz, betrag,
            "ja" if e["abrechenbar"] else "nein", e["kostennote"] or ""]


def _bericht(akte: dict, eintraege: list[dict], stand: dict, nur_offen: bool):
    from .ausgabe import Absatz, Bericht, Eintrag, Kopf, Tabelle, Ueberschrift

    v = stand["vereinbarung"]
    minuten = sum(e["minuten"] for e in eintraege)
    getaktet = sum(e["getaktet"] for e in eintraege)
    betrag = sum((Decimal(e["betrag"]) for e in eintraege if e["betrag"]), Decimal(0))
    tage = [e["datum"] for e in eintraege]
    zeitraum = (f"{_tag(min(tage))} bis {_tag(max(tage))}" if tage and min(tage) != max(tage)
                else _tag(tage[0]) if tage else "–")
    kopf = [("Akte", akte["name"]), ("Aktenzeichen", akte["aktenzeichen"] or "–")]
    if v["mandant"]:
        kopf.append(("Mandant", v["mandant"]["name"]))
    kopf += [("Zeitraum", zeitraum), ("Auswahl", "nur offene Zeiten" if nur_offen else "alle Zeiten"),
             ("Taktung", "minutengenau" if v["taktung"] == 1 else f"{v['taktung']} Minuten"),
             ("Erfasst", f"{stunden_text(minuten)} Std. ({minuten} Min.)"),
             ("Abrechenbar (getaktet)", f"{stunden_text(getaktet)} Std."), ("Betrag netto", _euro(betrag)),
             ("Erstellt am", _jetzt().strftime("%d.%m.%Y %H:%M"))]
    bausteine: list = [Kopf(kopf), Ueberschrift("Tätigkeitsnachweis")]
    for e in eintraege:
        wer = f"{e['bearbeiter']} ({e['stufe']})" if e["stufe"] else e["bearbeiter"]
        teile = [wer, f"{stunden_text(e['minuten'])} Std."]
        if e["abrechenbar"] and e["getaktet"] != e["minuten"]:
            teile.append(f"getaktet {stunden_text(e['getaktet'])} Std.")
        if not e["abrechenbar"]:
            teile.append("nicht abrechenbar")
        if e["betrag"]:
            teile.append(_euro(Decimal(e["betrag"])))
        if e["kostennote"]:
            teile.append(f"Rechnung {e['kostennote']}")
        bausteine.append(Eintrag(" · ".join(teile), nummer=_tag(e["datum"]), kompakt=True,
                                 zeilen=[e["taetigkeit"] or "(ohne Tätigkeit)"]))
    if not eintraege:
        bausteine.append(Absatz("Keine Zeiten erfasst."))
    tabelle = Tabelle("Zeiten", list(_SPALTEN), [_zeile(e, text=False) for e in eintraege],
                      [11, 22, 18, 60, 12, 16, 15, 12, 11, 14])
    return Bericht(f"Zeitnachweis {akte['name']}", bausteine, [tabelle])


def exportieren(con: sqlite3.Connection, akte_id: int, pfad: str, nur_offen: bool = False) -> dict:
    """Zeiten der Akte als Excel, CSV, PDF oder Word; das Format folgt der Endung."""
    from . import ausgabe

    ziel = Path(pfad)
    art = ziel.suffix.lower().lstrip(".")
    if art not in EXPORT_FORMATE:
        raise ValueError(f"Format „.{art}“ wird nicht unterstützt; möglich: "
                         f"{', '.join('.' + k for k in EXPORT_FORMATE)}.")
    akte, eintraege, stand = _export_daten(con, akte_id, nur_offen)
    if art == "csv":
        # Mit BOM, damit Excel unter Windows die Umlaute richtig liest; newline="" lässt die CSV-Zeilenenden
        # (\r\n) unverändert, sonst macht Windows daraus \r\r\n und jede zweite Zeile ist leer.
        ziel.write_text(als_csv(eintraege), encoding="utf-8-sig", newline="")
    else:
        ziel.write_bytes(ausgabe.schreiben(_bericht(akte, eintraege, stand, nur_offen), art))
    return {"pfad": str(ziel), "anzahl": len(eintraege)}
