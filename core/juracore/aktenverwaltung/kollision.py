"""Kollisionsprüfung: Steht eine Partei dieser Akte in einer anderen Akte auf der anderen Seite?

Ein Anwalt darf nicht tätig werden, wenn er in derselben Rechtssache eine andere Partei im widerstreitenden Interesse
schon beraten oder vertreten hat (§ 43a Abs. 4 BRAO, § 3 BORA). Ob das so ist, entscheidet der Anwalt; JuraBox legt
die Treffer vor und dokumentiert Prüfung und Entscheidung in der Akte.

Verglichen werden Mandanten und Gegner, ihre gesetzlichen Vertreter und verbundene Organisationen, auch frühere Namen,
in allen Akten der aktiven Arbeitsumgebung (auch abgeschlossenen) und, nur lesend, in den anderen Umgebungen auf diesem
Gerät. Rot: dieselbe Partei steht anderswo auf der anderen Seite. Gelb: ähnlicher Name, ein Vertreter oder eine
verbundene Organisation; bei einer Rechtsabteilung auch eine Konzerngesellschaft auf der Gegenseite.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

from . import beteiligte
from .stammdaten import ROLLEN

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kollisionspruefung (
    id             INTEGER PRIMARY KEY,
    akte_id        INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    zeitpunkt      TEXT NOT NULL,
    ampel          TEXT NOT NULL,           -- gruen, gelb, rot
    treffer        TEXT NOT NULL,           -- JSON-Liste
    umgebungen     TEXT NOT NULL,           -- JSON-Liste der durchsuchten Umgebungen
    entscheidung   TEXT,                    -- kein_konflikt, konflikt; NULL = noch offen
    begruendung    TEXT,
    entschieden_am TEXT
);
CREATE INDEX IF NOT EXISTS kollisionspruefung_akte ON kollisionspruefung (akte_id, id);
"""

PARTEIROLLEN = ("mandant", "gegner")
ENTSCHEIDUNGEN = {"kein_konflikt": "Kein Interessenkonflikt", "konflikt": "Interessenkonflikt – Mandat nicht annehmen"}


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


def _hat_tabelle(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _register(daten: dict) -> str:
    nummer = re.sub(r"\s+", "", daten.get("registernummer", "")).upper()
    return f"{beteiligte.schluessel(daten.get('registergericht', ''))}|{nummer}" if nummer else ""


def _person_aus(name: str, daten: dict, **weiter) -> dict:
    schluessel = [beteiligte.schluessel(name), *(beteiligte.schluessel(n) for n in daten.get("fruehere_namen", []))]
    return {"name": name, "schluessel": [s for s in schluessel if s], "geburt": daten.get("geburtsdatum", ""),
            "register": _register(daten), **weiter}


def _mit_umfeld(con: sqlite3.Connection, t: sqlite3.Row, basis: dict) -> list[dict]:
    """Ein Eintrag des Beteiligtenverzeichnisses samt gesetzlicher Vertreter und verbundener Organisationen."""
    ergebnis = [_person_aus(t["name"], json.loads(t["daten"]), beteiligter_id=t["id"], via=None, **basis)]
    for r in con.execute(
        """SELECT b.*, r.art AS r_art FROM beteiligter_beziehung r JOIN beteiligter b
           ON b.id = CASE WHEN r.von = ? THEN r.zu ELSE r.von END
           WHERE (r.art = 'gesetzlicher_vertreter' AND r.zu = ?)
              OR (r.art = 'verbunden' AND ? IN (r.von, r.zu))""",
        (t["id"], t["id"], t["id"]),
    ):
        via = (f"gesetzlicher Vertreter von {t['name']}" if r["r_art"] == "gesetzlicher_vertreter"
               else f"verbunden mit {t['name']}")
        ergebnis.append(_person_aus(r["name"], json.loads(r["daten"]), beteiligter_id=r["id"], via=via, **basis))
    return ergebnis


def _parteien(con: sqlite3.Connection, akte_id: int | None = None) -> list[dict]:
    """Mandanten und Gegner (einer oder aller Akten) samt gesetzlicher Vertreter und verbundener Organisationen."""
    if not _hat_tabelle(con, "akte_beteiligung"):
        return []
    sql = "SELECT * FROM akte_beteiligung WHERE rolle IN ('mandant', 'gegner')"
    zeilen = con.execute(sql + (" AND akte_id = ?" if akte_id is not None else ""),
                         (() if akte_id is None else (akte_id,))).fetchall()
    ergebnis = []
    for z in zeilen:
        basis = {"akte_id": z["akte_id"], "rolle": z["rolle"], "seite": ROLLEN[z["rolle"]][0]}
        if z["beteiligter_id"] is not None:
            t = con.execute("SELECT * FROM beteiligter WHERE id = ?", (z["beteiligter_id"],)).fetchone()
            if t is not None:
                ergebnis += _mit_umfeld(con, t, basis)
        elif z["eigene_organisation_id"] is not None:
            o = con.execute("SELECT daten FROM eigene_organisation WHERE id = ?",
                            (z["eigene_organisation_id"],)).fetchone()
            if o is None:
                continue
            daten = json.loads(o["daten"])
            ergebnis.append(_person_aus(daten.get("name", ""), daten, beteiligter_id=None, via=None, **basis))
    return ergebnis


def _vergleiche(a: dict, b: dict, gleiche_db: bool) -> str | None:
    if gleiche_db and a["beteiligter_id"] is not None and a["beteiligter_id"] == b["beteiligter_id"]:
        return "gleich"
    if a["geburt"] and b["geburt"] and a["geburt"] != b["geburt"]:
        return None  # gleichnamige, aber verschiedene Personen
    if a["register"] and b["register"]:
        if a["register"] == b["register"]:
            return "gleich"
        return None  # verschiedene Registereinträge, verschiedene Gesellschaften
    beste = None
    for x in a["schluessel"]:
        for y in b["schluessel"]:
            stufe = beteiligte.aehnlichkeit(x, y)
            if stufe == "gleich":
                return "gleich"
            beste = beste or stufe
    return beste


def _akten_info(con: sqlite3.Connection) -> dict[int, dict]:
    spalten = {z["name"] for z in con.execute("PRAGMA table_info(akte)")}
    return {z["id"]: {"akte": z["name"], "aktenzeichen": z["aktenzeichen"] if "aktenzeichen" in spalten else None,
                      "status": z["status"] if "status" in spalten else "laufend"}
            for z in con.execute("SELECT * FROM akte")}


def _beschreibe(p: dict) -> dict:
    return {"name": p["name"], "rolle": p["rolle"], "rolle_text": ROLLEN[p["rolle"]][1], "via": p["via"]}


def _treffer(con: sqlite3.Connection, akte_id: int, hier: list[dict],
             quellen: list[tuple[str, sqlite3.Connection, bool]], umgebung: str) -> list[dict]:
    treffer: list[dict] = []
    for name, quelle, gleiche_db in quellen:
        info = _akten_info(quelle)
        for dort in _parteien(quelle):
            if dort["seite"] == "neutral":
                continue
            fuer_dieselbe_akte = gleiche_db and dort["akte_id"] == akte_id
            for p in hier:
                if p["seite"] == dort["seite"]:
                    continue
                if fuer_dieselbe_akte and p["seite"] == "gegen" and not p.get("vorab"):
                    continue  # innerhalb der Akte jedes Paar nur einmal, aus Sicht der eigenen Seite
                stufe = _vergleiche(p, dort, gleiche_db)
                if not stufe:
                    continue
                ampel = "rot" if stufe == "gleich" and not p["via"] and not dort["via"] else "gelb"
                a = info.get(dort["akte_id"], {})
                treffer.append({
                    "ampel": ampel, "stufe": stufe, "hier": _beschreibe(p),
                    "dort": {**_beschreibe(dort), "umgebung": name, "akte_id": dort["akte_id"],
                             "akte": a.get("akte", ""), "aktenzeichen": a.get("aktenzeichen"),
                             "status": a.get("status", "laufend"), "dieselbe_akte": fuer_dieselbe_akte,
                             "andere_umgebung": not gleiche_db},
                })
    # Rechtsabteilung: Streit zweier Konzerngesellschaften gegeneinander ist einen Hinweis wert.
    if _hat_tabelle(con, "eigene_profil"):
        form = con.execute("SELECT form FROM eigene_profil WHERE id = 1").fetchone()
        if form and form["form"] == "rechtsabteilung":
            for o in con.execute("SELECT id, daten FROM eigene_organisation WHERE art = 'konzerngesellschaft' "
                                 "AND archiviert_am IS NULL"):
                daten = json.loads(o["daten"])
                gesellschaft = _person_aus(daten.get("name", ""), daten, beteiligter_id=None, via=None,
                                           akte_id=None, rolle="mandant", seite="eigene")
                for p in hier:
                    if p["rolle"] == "gegner" and _vergleiche(p, gesellschaft, False):
                        treffer.append({"ampel": "gelb", "stufe": "konzern", "hier": _beschreibe(p), "dort": {
                            "name": gesellschaft["name"], "rolle_text": "Konzerngesellschaft (Eigene Daten)",
                            "umgebung": umgebung, "akte_id": None, "akte": "", "aktenzeichen": None,
                            "status": "", "dieselbe_akte": False, "andere_umgebung": False, "via": None}})
    for t in treffer:
        t["text"] = _text(t)
    treffer.sort(key=lambda t: (t["ampel"] != "rot", t["dort"]["andere_umgebung"], t["text"]))
    return treffer


def _ampel(treffer: list[dict]) -> str:
    return "rot" if any(t["ampel"] == "rot" for t in treffer) else "gelb" if treffer else "gruen"


def ermitteln(con: sqlite3.Connection, akte_id: int, andere: list[tuple[str, sqlite3.Connection]] | None = None,
              umgebung: str = "diese Umgebung") -> dict:
    """Treffer für eine Akte, ohne zu speichern. ``andere``: (Name, Verbindung) weiterer Umgebungen, nur lesend."""
    hier = _parteien(con, akte_id)
    quellen = [(umgebung, con, True), *((n, c, False) for n, c in (andere or []))]
    treffer = _treffer(con, akte_id, hier, quellen, umgebung)
    return {"ampel": _ampel(treffer), "treffer": treffer, "umgebungen": [q[0] for q in quellen],
            "parteien": len([p for p in hier if not p["via"]])}


def vorab(con: sqlite3.Connection, akte_id: int, rolle: str, beteiligter_ids: list[int],
          andere: list[tuple[str, sqlite3.Connection]] | None = None, umgebung: str = "diese Umgebung") -> dict:
    """Was die Prüfung meldete, wenn ein Eintrag in dieser Rolle hinzukäme; je Eintrag Ampel und Treffertexte.

    Damit zeigen die Suchtreffer einen möglichen Konflikt, bevor jemand als Mandant oder Gegner eingetragen ist.
    """
    if rolle not in PARTEIROLLEN:
        return {}
    quellen = [(umgebung, con, True), *((n, c, False) for n, c in (andere or []))]
    basis = {"akte_id": akte_id, "rolle": rolle, "seite": ROLLEN[rolle][0], "vorab": True}
    ergebnis = {}
    for bid in beteiligter_ids:
        t = con.execute("SELECT * FROM beteiligter WHERE id = ?", (bid,)).fetchone()
        if t is None:
            continue
        treffer = _treffer(con, akte_id, _mit_umfeld(con, t, basis), quellen, umgebung)
        if treffer:
            ergebnis[str(bid)] = {"ampel": _ampel(treffer), "texte": [x["text"] for x in treffer]}
    return ergebnis


def _text(t: dict) -> str:
    h, d = t["hier"], t["dort"]
    wer = h["name"] + (f" ({h['via']})" if h["via"] else "")
    if t["stufe"] == "konzern":
        return f"{wer} ist Gegner und zugleich eine eigene Konzerngesellschaft."
    gleich = "" if t["stufe"] == "gleich" else "ähnlicher Name: "
    if d["dieselbe_akte"]:
        ort = "in dieser Akte"
    else:
        akte = d["aktenzeichen"] or f"„{d['akte']}“"
        ort = f"in Akte {akte}" + (f" (Umgebung {d['umgebung']})" if d["andere_umgebung"] else "")
        if d["status"] and d["status"] != "laufend":
            ort += f", {d['status']}"
    dort = d["name"] + (f" ({d['via']})" if d["via"] else "")
    return f"{wer} ist hier {h['rolle_text']}; {gleich}{dort} ist {ort} {d['rolle_text']}."


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _eintrag(z: sqlite3.Row) -> dict:
    return {"id": z["id"], "akte_id": z["akte_id"], "zeitpunkt": z["zeitpunkt"], "ampel": z["ampel"],
            "treffer": json.loads(z["treffer"]), "umgebungen": json.loads(z["umgebungen"]),
            "entscheidung": z["entscheidung"], "entscheidung_text": ENTSCHEIDUNGEN.get(z["entscheidung"] or ""),
            "begruendung": z["begruendung"], "entschieden_am": z["entschieden_am"]}


def letzte(con: sqlite3.Connection, akte_id: int) -> dict | None:
    z = con.execute("SELECT * FROM kollisionspruefung WHERE akte_id = ? ORDER BY id DESC LIMIT 1",
                    (akte_id,)).fetchone()
    return _eintrag(z) if z else None


def verlauf(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    return [_eintrag(z) for z in con.execute("SELECT * FROM kollisionspruefung WHERE akte_id = ? ORDER BY id DESC",
                                             (akte_id,))]


def pruefen(con: sqlite3.Connection, akte_id: int, andere: list[tuple[str, sqlite3.Connection]] | None = None,
            umgebung: str = "diese Umgebung") -> dict:
    """Prüft und dokumentiert. Ein unverändertes Ergebnis wird nicht erneut gespeichert; die Entscheidung bleibt."""
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    e = ermitteln(con, akte_id, andere, umgebung)
    vorher = letzte(con, akte_id)
    if vorher and vorher["treffer"] == e["treffer"] and vorher["umgebungen"] == e["umgebungen"]:
        return vorher
    with con:
        con.execute(
            "INSERT INTO kollisionspruefung (akte_id, zeitpunkt, ampel, treffer, umgebungen) VALUES (?, ?, ?, ?, ?)",
            (akte_id, _jetzt(), e["ampel"], json.dumps(e["treffer"], ensure_ascii=False),
             json.dumps(e["umgebungen"], ensure_ascii=False)),
        )
    return letzte(con, akte_id)


def entscheiden(con: sqlite3.Connection, pruefung_id: int, entscheidung: str, begruendung: str = "") -> dict:
    z = con.execute("SELECT * FROM kollisionspruefung WHERE id = ?", (pruefung_id,)).fetchone()
    if z is None:
        raise LookupError(f"Unbekannte Prüfung: {pruefung_id}")
    if entscheidung not in ENTSCHEIDUNGEN:
        raise ValueError(f"Unbekannte Entscheidung: {entscheidung!r}")
    begruendung = "\n".join(t.strip() for t in str(begruendung or "").splitlines() if t.strip())
    if entscheidung == "kein_konflikt" and z["ampel"] != "gruen" and not begruendung:
        raise ValueError("Bei Treffern bitte kurz begründen, warum kein Konflikt besteht.")
    with con:
        con.execute("UPDATE kollisionspruefung SET entscheidung = ?, begruendung = ?, entschieden_am = ? WHERE id = ?",
                    (entscheidung, begruendung or None, _jetzt(), pruefung_id))
    return _eintrag(con.execute("SELECT * FROM kollisionspruefung WHERE id = ?", (pruefung_id,)).fetchone())
