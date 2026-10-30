"""Anmerkungen an Dokumenten einer Akte: Markierungen in Farbe, Unterstreichungen und Kommentare.

Eine Markierung hängt an einer Textstelle des gelesenen Dokuments. Gespeichert werden die Lage im Text (Zeichen-
positionen über alle Abschnitte, verbunden mit Zeilenumbruch), der markierte Wortlaut und etwas Text davor und danach.
Ändert sich der Text (neue Fassung, erneutes Einlesen), wird die Stelle über Wortlaut und Umgebung neu gesucht wie in
JuraBox Lite. Findet sie sich nicht mehr, bleibt die Anmerkung mit dem Status „nicht_gefunden“ erhalten und wird
nicht gelöscht.

Farben tragen eine Bedeutung (Gelb = Wichtig …), die sich je Arbeitsumgebung ändern lässt.

Das Modell ist für weitere Arten vorbereitet: ``art`` unterscheidet Textmarkierungen von späteren Lesezeichen und
Freihandzeichnungen; diese verankern über ``seite`` und ``form`` (Koordinaten als JSON) statt über den Text.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime

from . import akte

_SCHEMA = """
CREATE TABLE IF NOT EXISTS anmerkung (
    id           INTEGER PRIMARY KEY,
    dokument_id  INTEGER NOT NULL REFERENCES dokument(id) ON DELETE CASCADE,
    art          TEXT NOT NULL DEFAULT 'markierung',  -- markierung; später lesezeichen, freihand
    farbe        TEXT NOT NULL,                       -- gelb, gruen, blau, rot
    stil         TEXT NOT NULL DEFAULT 'flaeche',     -- flaeche, unterstrichen, durchgestrichen
    start        INTEGER,                             -- Lage im Text (Abschnitte mit Zeilenumbruch verbunden)
    ende         INTEGER,
    zitat        TEXT,                                -- markierter Wortlaut
    davor        TEXT NOT NULL DEFAULT '',            -- Umgebung zum Wiederfinden
    danach       TEXT NOT NULL DEFAULT '',
    seite        INTEGER,                             -- Seite der Stelle (bei Freihand die Seite der Zeichnung)
    form         TEXT,                                -- später: Koordinaten (Freihand, Punkt auf der Seite) als JSON
    kommentar    TEXT,                                -- Markdown; NULL = ohne Kommentar
    status       TEXT NOT NULL DEFAULT 'gefunden',    -- gefunden, nicht_gefunden
    textstand    TEXT,                                -- Prüfsumme des Texts, gegen den die Lage zuletzt geprüft wurde
    angelegt_am  TEXT NOT NULL,
    geaendert_am TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS anmerkung_dokument ON anmerkung (dokument_id, start);

-- Bedeutung der Farben je Arbeitsumgebung; fehlt eine Zeile, gilt die Vorgabe.
CREATE TABLE IF NOT EXISTS anmerkung_farbe (
    farbe        TEXT PRIMARY KEY,
    bedeutung    TEXT NOT NULL
);
"""

FARBEN = ("gelb", "gruen", "blau", "rot")
STILE = ("flaeche", "unterstrichen", "durchgestrichen")
BEDEUTUNG_VORGABE = {"gelb": "Wichtig", "gruen": "Erledigt", "blau": "Beweis", "rot": "Streitig"}
UMGEBUNG = 40  # Zeichen davor und danach zum Wiederfinden
MAX_KOMMENTAR = 20000


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    con.commit()


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def bedeutungen(con: sqlite3.Connection) -> dict[str, str]:
    werte = dict(BEDEUTUNG_VORGABE)
    werte.update({z["farbe"]: z["bedeutung"] for z in con.execute("SELECT farbe, bedeutung FROM anmerkung_farbe")})
    return werte


def bedeutungen_setzen(con: sqlite3.Connection, werte: dict[str, str]) -> dict[str, str]:
    with con:
        for farbe, bedeutung in werte.items():
            if farbe not in FARBEN:
                raise ValueError(f"Unbekannte Farbe: {farbe}")
            text = " ".join(str(bedeutung or "").split())[:40]
            if not text:
                raise ValueError("Jede Farbe braucht eine Bedeutung.")
            con.execute("INSERT INTO anmerkung_farbe (farbe, bedeutung) VALUES (?, ?) "
                        "ON CONFLICT (farbe) DO UPDATE SET bedeutung = excluded.bedeutung", (farbe, text))
    return bedeutungen(con)


# --- Text des Dokuments ----------------------------------------------------------------------------------------------

class _Text:
    """Text eines Dokuments als eine Zeichenkette mit den Grenzen der Abschnitte."""

    def __init__(self, con: sqlite3.Connection, dokument_id: int):
        self.abschnitte = con.execute(
            "SELECT nr, seite, rn, seitenwechsel, text FROM abschnitt WHERE dokument_id = ? ORDER BY nr",
            (dokument_id,)).fetchall()
        self.beginn: list[int] = []
        pos = 0
        for a in self.abschnitte:
            self.beginn.append(pos)
            pos += len(a["text"]) + 1
        self.text = "\n".join(a["text"] for a in self.abschnitte)
        self.stand = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]

    def abschnitt_an(self, pos: int) -> int:
        """Index des Abschnitts, in dem ``pos`` liegt."""
        i = 0
        for k, b in enumerate(self.beginn):
            if b <= pos:
                i = k
        return i

    def ort(self, pos: int) -> dict:
        """Abschnitt, Seite und Randnummer an Position ``pos``."""
        if not self.abschnitte:
            return {"abschnitt": None, "seite": None, "rn": None}
        i = self.abschnitt_an(pos)
        a = self.abschnitte[i]
        seite = akte._seite_an(a["seite"], json.loads(a["seitenwechsel"]), pos - self.beginn[i])
        return {"abschnitt": a["nr"], "seite": seite, "rn": a["rn"]}

    def stuecke_auf_seite(self, start: int, ende: int, seite: int) -> list[tuple[str, float]]:
        """Teile von ``start``–``ende``, die auf ``seite`` stehen, mit ihrer ungefähren Lage im Seitentext (0–1)."""
        teile: list[tuple[int, int]] = []  # Positionen im Gesamttext
        seitentext: list[tuple[int, int]] = []
        for i, a in enumerate(self.abschnitte):
            b = self.beginn[i]
            grenzen = [(0, a["seite"])] + [(p, s) for p, s in json.loads(a["seitenwechsel"])]
            for k, (von, s) in enumerate(grenzen):
                bis = grenzen[k + 1][0] if k + 1 < len(grenzen) else len(a["text"])
                if s != seite or bis <= von:
                    continue
                seitentext.append((b + von, b + bis))
                lo, hi = max(b + von, start), min(b + bis, ende)
                if lo < hi:
                    teile.append((lo, hi))
        gesamt = sum(hi - lo for lo, hi in seitentext) or 1
        ergebnis = []
        for lo, hi in teile:
            vorher = sum(min(bis, lo) - von for von, bis in seitentext if von < lo)
            ergebnis.append((self.text[lo:hi], vorher / gesamt))
        return ergebnis


def _normal(text: str) -> str:
    return " ".join(text.split())


def _umgebung(text: str, start: int, ende: int) -> tuple[str, str]:
    return text[max(0, start - UMGEBUNG):start], text[ende:ende + UMGEBUNG]


def _gemeinsam_ende(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _gemeinsam_anfang(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def wiederfinden(text: str, zitat: str, davor: str, danach: str, start: int | None) -> tuple[int, int] | None:
    """Sucht den Wortlaut ``zitat`` in ``text``; bei mehreren Funden zählt die passende Umgebung, dann die alte Lage.

    Leerraum wird dabei nicht verglichen (Zeilenumbrüche können sich beim erneuten Einlesen ändern).
    """
    teile = zitat.split()
    if not teile:
        return None
    muster = re.compile(r"\s+".join(re.escape(t) for t in teile))
    funde = [(m.start(), m.end()) for m in muster.finditer(text)]
    if not funde:
        return None
    vor_n, nach_n = _normal(davor), _normal(danach)

    def guete(f: tuple[int, int]):
        v, n = _umgebung(text, *f)
        passend = _gemeinsam_ende(_normal(v), vor_n) + _gemeinsam_anfang(_normal(n), nach_n)
        return (-passend, abs(f[0] - start) if start is not None else 0)

    return min(funde, key=guete)


def _pruefen(con: sqlite3.Connection, dokument_id: int, t: _Text | None = None) -> _Text:
    """Prüft die Lage aller Markierungen des Dokuments, deren Text sich seit der letzten Prüfung geändert hat."""
    t = t or _Text(con, dokument_id)
    offen = con.execute(
        "SELECT id, start, ende, zitat, davor, danach FROM anmerkung "
        "WHERE dokument_id = ? AND art = 'markierung' AND (textstand IS NULL OR textstand != ?)",
        (dokument_id, t.stand)).fetchall()
    if not offen:
        return t
    with con:
        for z in offen:
            if z["zitat"] and t.text[z["start"]:z["ende"]] == z["zitat"]:
                lage = (z["start"], z["ende"])
            else:
                lage = wiederfinden(t.text, z["zitat"] or "", z["davor"], z["danach"], z["start"])
            if lage is None:
                con.execute("UPDATE anmerkung SET status = 'nicht_gefunden', textstand = ? WHERE id = ?",
                            (t.stand, z["id"]))
                continue
            davor, danach = _umgebung(t.text, *lage)
            con.execute(
                "UPDATE anmerkung SET start = ?, ende = ?, zitat = ?, davor = ?, danach = ?, seite = ?, "
                "status = 'gefunden', textstand = ? WHERE id = ?",
                (lage[0], lage[1], t.text[lage[0]:lage[1]], davor, danach, t.ort(lage[0])["seite"], t.stand, z["id"]))
    return t


# --- Lesen und Ändern ------------------------------------------------------------------------------------------------

def _info(z: sqlite3.Row, t: _Text | None) -> dict:
    d = {k: z[k] for k in ("id", "dokument_id", "art", "farbe", "stil", "start", "ende", "zitat", "seite",
                           "kommentar", "status", "angelegt_am", "geaendert_am")}
    ort = t.ort(z["start"]) if t is not None and z["start"] is not None and z["status"] == "gefunden" else {}
    d["abschnitt"] = ort.get("abschnitt")
    d["rn"] = ort.get("rn")
    for k in ("dokument", "dateiname"):
        if k in z.keys():
            d[k] = z[k]
    return d


def liste(con: sqlite3.Connection, akte_id: int | None = None, dokument_id: int | None = None) -> list[dict]:
    """Anmerkungen eines Dokuments oder einer ganzen Akte in Lesereihenfolge; die Lage ist vorher geprüft."""
    if dokument_id is None and akte_id is None:
        raise ValueError("Akte oder Dokument angeben.")
    dokumente = [dokument_id] if dokument_id is not None else [
        z["dokument_id"] for z in con.execute(
            "SELECT DISTINCT a.dokument_id FROM anmerkung a JOIN dokument d ON d.id = a.dokument_id "
            "WHERE d.akte_id = ?", (akte_id,))]
    texte = {d: _pruefen(con, d) for d in dokumente}
    zeilen = con.execute(
        """SELECT a.*, COALESCE(d.titel, d.dateiname) AS dokument, d.dateiname FROM anmerkung a
           JOIN dokument d ON d.id = a.dokument_id
           WHERE (? IS NULL OR a.dokument_id = ?) AND (? IS NULL OR d.akte_id = ?)
           ORDER BY d.datum, d.id, a.status = 'nicht_gefunden', a.start, a.id""",
        (dokument_id, dokument_id, akte_id, akte_id)).fetchall()
    return [_info(z, texte.get(z["dokument_id"])) for z in zeilen]


def anlegen(con: sqlite3.Connection, dokument_id: int, start: int, ende: int, farbe: str = "gelb",
            stil: str = "flaeche", kommentar: str | None = None) -> dict:
    """Markiert ``start``–``ende`` im Text des Dokuments (Positionen wie in ``_Text``)."""
    _pruefe_werte(farbe, stil)
    t = _Text(con, dokument_id)
    if not t.abschnitte:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht oder es hat keinen Text.")
    start, ende = max(0, int(start)), min(int(ende), len(t.text))
    # Leerraum am Rand der Auswahl gehört nicht zur Markierung.
    while start < ende and t.text[start].isspace():
        start += 1
    while ende > start and t.text[ende - 1].isspace():
        ende -= 1
    if not 0 <= start < ende <= len(t.text):
        raise ValueError("Die Auswahl enthält keinen Text.")
    # Angeschnittene Wörter ganz nehmen: Mit der Maus trifft man den Wortanfang selten genau.
    while start > 0 and t.text[start - 1].isalnum() and t.text[start].isalnum():
        start -= 1
    while ende < len(t.text) and t.text[ende].isalnum() and t.text[ende - 1].isalnum():
        ende += 1
    davor, danach = _umgebung(t.text, start, ende)
    jetzt = _jetzt()
    with con:
        cur = con.execute(
            "INSERT INTO anmerkung (dokument_id, farbe, stil, start, ende, zitat, davor, danach, seite, kommentar, "
            "textstand, angelegt_am, geaendert_am) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dokument_id, farbe, stil, start, ende, t.text[start:ende], davor, danach, t.ort(start)["seite"],
             _kommentar(kommentar), t.stand, jetzt, jetzt))
    return _eine(con, cur.lastrowid)


def aendern(con: sqlite3.Connection, anmerkung_id: int, farbe: str | None = None, stil: str | None = None,
            kommentar: str | None = None, ohne_kommentar: bool = False) -> dict:
    """Ändert Farbe, Stil oder Kommentar; ``ohne_kommentar`` entfernt den Kommentar."""
    z = con.execute("SELECT * FROM anmerkung WHERE id = ?", (anmerkung_id,)).fetchone()
    if z is None:
        raise LookupError(f"Anmerkung {anmerkung_id} gibt es nicht.")
    farbe, stil = farbe or z["farbe"], stil or z["stil"]
    _pruefe_werte(farbe, stil)
    neu_kommentar = None if ohne_kommentar else (z["kommentar"] if kommentar is None else _kommentar(kommentar))
    with con:
        con.execute("UPDATE anmerkung SET farbe = ?, stil = ?, kommentar = ?, geaendert_am = ? WHERE id = ?",
                    (farbe, stil, neu_kommentar, _jetzt(), anmerkung_id))
    return _eine(con, anmerkung_id)


def loeschen(con: sqlite3.Connection, anmerkung_id: int) -> dict:
    z = con.execute("SELECT dokument_id FROM anmerkung WHERE id = ?", (anmerkung_id,)).fetchone()
    if z is None:
        raise LookupError(f"Anmerkung {anmerkung_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM anmerkung WHERE id = ?", (anmerkung_id,))
    return {"geloescht": anmerkung_id, "dokument_id": z["dokument_id"]}


def _eine(con: sqlite3.Connection, anmerkung_id: int) -> dict:
    z = con.execute("SELECT a.*, COALESCE(d.titel, d.dateiname) AS dokument, d.dateiname FROM anmerkung a "
                    "JOIN dokument d ON d.id = a.dokument_id WHERE a.id = ?", (anmerkung_id,)).fetchone()
    return _info(z, _Text(con, z["dokument_id"]))


def _pruefe_werte(farbe: str, stil: str) -> None:
    if farbe not in FARBEN:
        raise ValueError(f"Unbekannte Farbe: {farbe}")
    if stil not in STILE:
        raise ValueError(f"Unbekannte Darstellung: {stil}")


def _kommentar(text: str | None) -> str | None:
    if text is None:
        return None
    text = "\n".join(z.rstrip() for z in str(text).strip().splitlines())
    if len(text) > MAX_KOMMENTAR:
        raise ValueError(f"Der Kommentar ist zu lang (höchstens {MAX_KOMMENTAR} Zeichen).")
    return text or None


def zahlen(con: sqlite3.Connection, akte_id: int) -> dict[int, int]:
    """Zahl der Anmerkungen je Dokument der Akte (für die Dokumentliste)."""
    return {z[0]: z[1] for z in con.execute(
        "SELECT a.dokument_id, COUNT(*) FROM anmerkung a JOIN dokument d ON d.id = a.dokument_id "
        "WHERE d.akte_id = ? GROUP BY a.dokument_id", (akte_id,))}


# --- Suche -----------------------------------------------------------------------------------------------------------

def _vergleichbar(text: str) -> str:
    """Klein, ohne Akzente und Umlautpunkte, damit "rucktritt" auch "Rücktritt" findet (wie die Volltextsuche)."""
    zerlegt = unicodedata.normalize("NFKD", text.casefold())
    return "".join(z for z in zerlegt if not unicodedata.combining(z))


def suche(con: sqlite3.Connection, suchtext: str, akte_id: int | None = None) -> list[dict]:
    """Anmerkungen, deren Wortlaut, Kommentar oder Farbbedeutung alle Suchwörter enthält."""
    woerter = [_vergleichbar(w) for w in suchtext.replace('"', " ").replace("*", " ").split()]
    if not woerter:
        return []
    bedeutung = bedeutungen(con)
    # Erst die Lage prüfen, damit Wortlaut und Fundstelle zum aktuellen Text passen.
    texte = {z[0]: _pruefen(con, z[0]) for z in con.execute(
        "SELECT DISTINCT a.dokument_id FROM anmerkung a JOIN dokument d ON d.id = a.dokument_id "
        "WHERE ? IS NULL OR d.akte_id = ?", (akte_id, akte_id))}
    zeilen = con.execute(
        """SELECT a.*, COALESCE(d.titel, d.dateiname) AS dokument, d.dateiname, d.akte_id, d.format,
                  d.seiten, k.name AS akte
           FROM anmerkung a JOIN dokument d ON d.id = a.dokument_id JOIN akte k ON k.id = d.akte_id
           WHERE ? IS NULL OR d.akte_id = ? ORDER BY k.name, d.datum, d.id, a.start""",
        (akte_id, akte_id)).fetchall()
    ergebnis = []
    for z in zeilen:
        heu = _vergleichbar(" ".join([z["zitat"] or "", z["kommentar"] or "", bedeutung.get(z["farbe"], "")]))
        if all(w in heu for w in woerter):
            ergebnis.append(_info(z, texte.get(z["dokument_id"])) | {
                "akte_id": z["akte_id"], "akte": z["akte"], "format": z["format"], "seiten": z["seiten"]})
    return ergebnis


# --- Originalansicht -------------------------------------------------------------------------------------------------

def auf_seite(con: sqlite3.Connection, dokument_id: int, nr: int) -> list[dict]:
    """Markierungen auf Seite ``nr`` des Original-PDFs mit ihren Rechtecken (Anteile der Seite, wie Suchtreffer)."""
    import pypdfium2 as pdfium

    from . import ansicht

    t = _pruefen(con, dokument_id)
    zeilen = con.execute(
        "SELECT * FROM anmerkung WHERE dokument_id = ? AND art = 'markierung' AND status = 'gefunden' ORDER BY start",
        (dokument_id,)).fetchall()
    stuecke = [(z, t.stuecke_auf_seite(z["start"], z["ende"], nr)) for z in zeilen]
    stuecke = [(z, s) for z, s in stuecke if s]
    if not stuecke:
        return []
    d = con.execute("SELECT format, original FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if d["format"] != "pdf":
        return []
    seite = con.execute("SELECT quelle, woerter FROM seite WHERE dokument_id = ? AND nr = ?",
                        (dokument_id, nr)).fetchone()
    if seite is not None and seite["quelle"] == "ocr" and seite["woerter"]:
        woerter = json.loads(seite["woerter"])
    else:
        pdf = pdfium.PdfDocument(d["original"])
        try:
            if not 1 <= nr <= len(pdf):
                return []
            woerter = ansicht.woerter_textebene(pdf[nr - 1])
        finally:
            pdf.close()
    ergebnis = []
    for z, teile in stuecke:
        rechtecke = [r for text, lage in teile for r in ansicht.rechtecke_fuer_stelle(woerter, text, lage)]
        if rechtecke:
            ergebnis.append(_info(z, t) | {"rechtecke": rechtecke})
    return ergebnis
