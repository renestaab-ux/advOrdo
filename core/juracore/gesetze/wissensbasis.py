"""Import, Suche und Zitatauflösung über der Gesetzes-Datenbank."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from difflib import SequenceMatcher

from .. import db
from . import bayern, eurlex
from .gii import parse_gii_xml
from .quelle import Rohdatei
from .zitate import Zitat, parse_zitat

GII_HINWEIS = "Konsolidierte, nichtamtliche Fassung (Gesetze im Internet)."


def importiere(con: sqlite3.Connection, roh: Rohdatei, abk: str | None = None) -> dict:
    """Übernimmt eine Rohdatei als neue Fassung. Unveränderte Dateien werden übersprungen.

    ``abk`` ist die Abkürzung, unter der das Gesetz zitiert wird (z. B. "EGBGB"). Ohne
    sie gilt die juristische Abkürzung aus der Datei, die bei Gesetze im Internet
    teils abweicht ("BGBEG", "UWG 2004").
    """
    if eurlex.ist_eurlex(roh.xml):
        dokument = eurlex.parse_eurlex_html(roh.xml, abk or roh.abk)
    elif bayern.ist_bayern(roh.xml):
        dokument = bayern.parse_bayern_html(roh.xml, abk or roh.abk)
    else:
        dokument = parse_gii_xml(roh.xml)
    datei_abk = dokument.abk.upper()
    # Eine andere Schreibweise desselben Kürzels („AVB-FernwärmeV“) ergänzt das schon geladene Gesetz.
    abk = db.gesetz_abk(con, abk or datei_abk)
    with con:
        if abk != datei_abk:
            # Frühere Importe legten das Gesetz unter der Datei-Abkürzung ab; samt Fassungen übernehmen.
            con.execute(
                "UPDATE gesetz SET abk = ? WHERE abk = ? AND NOT EXISTS (SELECT 1 FROM gesetz WHERE abk = ?)",
                (abk, datei_abk, abk),
            )
        con.execute(
            """INSERT INTO gesetz (abk, langtitel) VALUES (?, ?)
               ON CONFLICT(abk) DO UPDATE SET langtitel = excluded.langtitel""",
            (abk, dokument.langtitel),
        )
        gesetz_id = con.execute("SELECT id FROM gesetz WHERE abk = ?", (abk,)).fetchone()["id"]
        vorhanden = con.execute(
            "SELECT id FROM fassung WHERE gesetz_id = ? AND sha256 = ?", (gesetz_id, roh.sha256)
        ).fetchone()
        if vorhanden:
            return {"abk": abk, "fassung_id": vorhanden["id"], "neu": False, "normen": None}

        fassung_id = con.execute(
            """INSERT INTO fassung (gesetz_id, sha256, quelle, abgerufen_am, builddate, stand, roharchiv)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                gesetz_id,
                roh.sha256,
                roh.quelle,
                datetime.now(UTC).isoformat(timespec="seconds"),
                dokument.builddate,
                json.dumps(dokument.stand, ensure_ascii=False),
                str(roh.archivpfad) if roh.archivpfad else None,
            ),
        ).lastrowid

        for norm in dokument.normen:
            norm_id = con.execute(
                """INSERT INTO norm (fassung_id, doknr, reihenfolge, bezeichnung, typ, nummer, titel,
                                     gliederung, weggefallen, text, fussnoten)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fassung_id,
                    norm.doknr,
                    norm.reihenfolge,
                    norm.bezeichnung,
                    norm.typ,
                    norm.nummer,
                    norm.titel,
                    json.dumps(norm.gliederung, ensure_ascii=False),
                    int(norm.weggefallen),
                    norm.text,
                    norm.fussnoten,
                ),
            ).lastrowid
            con.execute(
                "INSERT INTO norm_fts (rowid, bezeichnung, titel, text) VALUES (?, ?, ?, ?)",
                (norm_id, norm.bezeichnung, norm.titel or "", norm.text),
            )
            for i, absatz in enumerate(norm.absaetze, start=1):
                absatz_id = con.execute(
                    "INSERT INTO absatz (norm_id, reihenfolge, nr, text) VALUES (?, ?, ?, ?)",
                    (norm_id, i, absatz.nr, absatz.text),
                ).lastrowid
                con.executemany(
                    "INSERT INTO satz (absatz_id, nr, text, nummern) VALUES (?, ?, ?, ?)",
                    [(absatz_id, s.nr, s.text, json.dumps(s.nummern, ensure_ascii=False)) for s in absatz.saetze],
                )
    return {"abk": abk, "fassung_id": fassung_id, "neu": True, "normen": len(dokument.normen)}


def suche(con: sqlite3.Connection, suchtext: str, gesetz: str | None = None, limit: int = 20) -> list[dict]:
    """Volltextsuche über die jeweils neueste Fassung aller (oder eines) Gesetze."""
    abfrage = db.fts_abfrage(suchtext)
    if not abfrage:
        return []
    zeilen = con.execute(
        f"""SELECT n.id, g.abk, n.bezeichnung, n.titel, n.weggefallen, f.id AS fassung_id,
                  snippet(norm_fts, 2, '[', ']', ' … ', 16) AS ausschnitt
           FROM norm_fts
           JOIN norm n ON n.id = norm_fts.rowid
           JOIN fassung f ON f.id = n.fassung_id
           JOIN gesetz g ON g.id = f.gesetz_id
           WHERE norm_fts MATCH ?
             AND f.id = (SELECT MAX(id) FROM fassung WHERE gesetz_id = g.id)
             {"AND g.abk = ?" if gesetz else ""}
           ORDER BY bm25(norm_fts, 5.0, 3.0, 1.0)
           LIMIT ?""",
        (abfrage, *([gesetz.upper()] if gesetz else []), limit),
    ).fetchall()
    return [dict(z) for z in zeilen]


def norm(
    con: sqlite3.Connection, abk: str, nummer: str, fassung_id: int | None = None, typ: str | None = None
) -> dict | None:
    """Eine Norm mit Absätzen, Sätzen und Fassungsstand; ``typ`` ist "paragraph" oder "artikel"."""
    fassung = _fassung(con, abk, fassung_id)
    if fassung is None:
        return None
    typen = (typ,) if typ else ("paragraph", "artikel")
    zeile = con.execute(
        f"""SELECT * FROM norm WHERE fassung_id = ? AND nummer = ? AND typ IN ({", ".join("?" * len(typen))})
            ORDER BY reihenfolge LIMIT 1""",
        (fassung["id"], nummer, *typen),
    ).fetchone()
    if zeile is None:
        return None
    absaetze = []
    for a in con.execute("SELECT * FROM absatz WHERE norm_id = ? ORDER BY reihenfolge", (zeile["id"],)):
        saetze = [
            {"nr": s["nr"], "text": s["text"], "nummern": json.loads(s["nummern"])}
            for s in con.execute("SELECT * FROM satz WHERE absatz_id = ? ORDER BY nr", (a["id"],))
        ]
        absaetze.append({"nr": a["nr"], "text": a["text"], "saetze": saetze})
    return {
        "gesetz": fassung["abk"],
        "langtitel": fassung["langtitel"],
        "bezeichnung": zeile["bezeichnung"],
        "titel": zeile["titel"],
        "gliederung": json.loads(zeile["gliederung"]),
        "weggefallen": bool(zeile["weggefallen"]),
        "absaetze": absaetze,
        "fassung": _fassung_info(fassung),
    }


def loese_zitat(con: sqlite3.Connection, zitat: str | Zitat, fassung_id: int | None = None) -> dict:
    """Löst ein Normzitat zu einem Beleg auf: exakter Wortlaut plus Fassungsstand.

    Ergebnis ``status``: "belegt" (Fundstelle existiert), "nicht_gefunden"
    (Norm, Absatz, Satz oder Nummer fehlt in der Fassung) oder "unbekanntes_gesetz".
    """
    z = parse_zitat(zitat) if isinstance(zitat, str) else zitat
    ergebnis: dict = {"zitat": str(z), "status": "nicht_gefunden", "wortlaut": None, "fassung": None, "hinweis": None,
                      "gemeint": None}
    fassung = _fassung(con, z.gesetz, fassung_id)
    if fassung is None:
        gemeint = gemeintes_gesetz(con, z.gesetz)
        if gemeint and db.schreibweise(gemeint) != db.schreibweise(z.gesetz):
            # Eigene Schreibweise: gegen das gemeinte Gesetz prüfen, die Schreibweise im Text bleibt sichtbar.
            beleg = loese_zitat(con, replace(z, gesetz=gemeint), fassung_id)
            vermerk = f"Im Text steht „{z.gesetz}“; zugeordnet zu {gemeint} (eigene Schreibweise)."
            beleg.update(zitat=str(z), gemeint=gemeint,
                         hinweis=f"{vermerk} {beleg['hinweis']}" if beleg["hinweis"] else vermerk)
            return beleg
        ergebnis.update(status="unbekanntes_gesetz", hinweis=f"{z.gesetz} ist nicht in der Wissensbasis.")
        return ergebnis
    ergebnis["fassung"] = _fassung_info(fassung)

    n = norm(con, z.gesetz, z.nummer, fassung["id"], "artikel" if z.zeichen.startswith("Art") else "paragraph")
    if n is None:
        ergebnis["hinweis"] = f"{z.zeichen} {z.nummer} {z.gesetz} existiert in dieser Fassung nicht."
        return ergebnis
    ergebnis.update(norm=n["bezeichnung"], titel=n["titel"])
    if n["weggefallen"]:
        ergebnis.update(hinweis="Die Norm ist weggefallen.", wortlaut="(weggefallen)")
        return ergebnis

    if z.absatz is None and z.satz is None and z.nr is None:
        teil_text = "\n".join(a["text"] for a in n["absaetze"])
    else:
        if z.absatz is not None:
            absatz = next((a for a in n["absaetze"] if a["nr"] == z.absatz), None)
            if absatz is None:
                ergebnis["hinweis"] = f"{n['bezeichnung']} hat keinen Absatz {z.absatz}."
                return ergebnis
        elif len(n["absaetze"]) == 1:
            # "§ 437 Nr. 4 BGB": Norm ohne Absätze, Satz oder Nummer beziehen sich auf den ganzen Text.
            absatz = n["absaetze"][0]
        elif z.satz is None:
            # Nummer ohne Absatzangabe: in allen Absätzen suchen.
            absatz = {"text": "", "saetze": [s for a in n["absaetze"] for s in a["saetze"]]}
        else:
            ergebnis["hinweis"] = f"{n['bezeichnung']} hat mehrere Absätze; die Satzangabe ist ohne Absatz mehrdeutig."
            return ergebnis
        teil_text = absatz["text"]
        saetze = absatz["saetze"]
        if z.satz is not None:
            satz = next((s for s in saetze if s["nr"] == z.satz), None)
            if satz is None:
                ort = f"Abs. {z.absatz}" if z.absatz else n["bezeichnung"]
                ergebnis["hinweis"] = f"{ort} hat nur {len(saetze)} Satz/Sätze."
                return ergebnis
            teil_text = satz["text"]
            saetze = [satz]
        if z.nr is not None:
            eintrag = next((t for s in saetze for nr, t in s["nummern"] if nr == z.nr), None)
            if eintrag is None:
                art = "Nr." if z.nr[0].isdigit() else "Buchstabe"
                ergebnis["hinweis"] = f"{art} {z.nr} wurde in der Fundstelle nicht gefunden."
                return ergebnis
            teil_text = f"{z.nr}. {eintrag}" if z.nr[0].isdigit() else f"{z.nr}) {eintrag}"
    ergebnis.update(status="belegt", wortlaut=teil_text)
    return ergebnis


# --- Unbekannte Gesetze: Vorschläge und eigene Schreibweisen --------------------------------------------------------


def gemeintes_gesetz(con: sqlite3.Connection, gesetz: str) -> str | None:
    """Gesetz, das eine eigene Schreibweise meint (Vergleich wie bei den Abkürzungen), oder None."""
    gesucht = db.schreibweise(gesetz)
    for von, nach in con.execute("SELECT von, nach FROM schreibweise"):
        if db.schreibweise(von) == gesucht:
            return nach
    return None


def schreibweisen(con: sqlite3.Connection) -> list[dict]:
    return [dict(z) for z in con.execute("SELECT von, nach, angelegt_am FROM schreibweise ORDER BY von COLLATE NOCASE")]


def schreibweise_setzen(con: sqlite3.Connection, von: str, nach: str) -> dict:
    """Merkt sich, dass ``von`` im Text das Gesetz ``nach`` meint; eine frühere Zuordnung derselben Schreibweise
    wird ersetzt."""
    von, nach = " ".join(von.split()), " ".join(nach.split())
    if not von or not nach:
        raise ValueError("Bitte Schreibweise und gemeintes Gesetz angeben.")
    if db.schreibweise(von) == db.schreibweise(nach):
        raise ValueError(f"„{von}“ und „{nach}“ sind dieselbe Abkürzung.")
    if con.execute("SELECT 1 FROM gesetz WHERE abk = ?", (db.gesetz_abk(con, von),)).fetchone():
        raise ValueError(f"{von} ist selbst ein Gesetz der Wissensbasis und kann nicht umgeleitet werden.")
    with con:
        for (alt,) in con.execute("SELECT von FROM schreibweise").fetchall():
            if db.schreibweise(alt) == db.schreibweise(von):
                con.execute("DELETE FROM schreibweise WHERE von = ?", (alt,))
        con.execute("INSERT INTO schreibweise (von, nach, angelegt_am) VALUES (?, ?, ?)",
                    (von, nach, datetime.now(UTC).isoformat(timespec="seconds")))
    return {"von": von, "nach": nach}


def schreibweise_loeschen(con: sqlite3.Connection, von: str) -> None:
    """Löscht die eigene Schreibweise ``von`` (auch bei abweichender Groß- und Kleinschreibung oder Bindestrichen)."""
    with con:
        for (alt,) in con.execute("SELECT von FROM schreibweise").fetchall():
            if db.schreibweise(alt) == db.schreibweise(von):
                con.execute("DELETE FROM schreibweise WHERE von = ?", (alt,))


def vorschlaege(con: sqlite3.Connection, gesetz: str, liste: list[dict], anzahl: int = 3) -> list[dict]:
    """Ähnlich geschriebene Gesetze zu einer unbekannten Abkürzung („Könnte … gemeint sein?“).

    Verglichen wird mit den geladenen Gesetzen und der Gesetzesliste, in der Vergleichsform von
    ``db.schreibweise``. ``geladen`` sagt, ob das Gesetz schon in der Wissensbasis steht."""
    gesucht = db.schreibweise(gesetz)
    if not gesucht:
        return []
    kandidaten: dict[str, dict] = {}
    for g in db.gesetze(con):
        kandidaten[db.schreibweise(g["abk"])] = {"abk": g["abk"], "titel": g["langtitel"], "geladen": True}
    for g in liste:
        kandidaten.setdefault(db.schreibweise(g["abk"]), {"abk": g["abk"], "titel": g.get("titel"), "geladen": False})
    bewertet = []
    for schluessel, k in kandidaten.items():
        if schluessel == gesucht:
            continue
        wert = SequenceMatcher(None, gesucht, schluessel).ratio()
        # Kurze Kürzel unterscheiden sich schon durch einen Buchstaben stark; dort strenger bleiben.
        if wert >= (0.75 if min(len(gesucht), len(schluessel)) <= 4 else 0.7):
            bewertet.append((wert, k))
    bewertet.sort(key=lambda t: (-t[0], not t[1]["geladen"], t[1]["abk"]))
    return [k | {"aehnlichkeit": round(w, 2)} for w, k in bewertet[:anzahl]]


def _fassung(con: sqlite3.Connection, abk: str, fassung_id: int | None) -> sqlite3.Row | None:
    if fassung_id is None:
        return db.aktuelle_fassung(con, abk)
    return con.execute(
        """SELECT f.*, g.abk, g.langtitel FROM fassung f JOIN gesetz g ON g.id = f.gesetz_id
           WHERE f.id = ? AND g.abk = ?""",
        (fassung_id, db.gesetz_abk(con, abk)),
    ).fetchone()


def _fassung_info(f: sqlite3.Row) -> dict:
    return {
        "id": f["id"],
        "quelle": f["quelle"],
        "abgerufen_am": f["abgerufen_am"],
        "builddate": f["builddate"],
        "stand": json.loads(f["stand"] or "[]"),
        "sha256": f["sha256"],
        "hinweis": eurlex.HINWEIS if _ist_amtsblatt(f) else bayern.HINWEIS if _ist_bayern(f) else GII_HINWEIS,
    }


def _ist_bayern(f: sqlite3.Row) -> bool:
    """Landesrecht aus gesetze-bayern.de, geladen oder als gespeicherte Seite importiert (Vollzitat mit GVBl.)."""
    return bayern.HERKUNFT in (f["quelle"] or "") or any("GVBl" in s for s in json.loads(f["stand"] or "[]"))


def _ist_amtsblatt(f: sqlite3.Row) -> bool:
    return any(s.startswith("ABl.") for s in json.loads(f["stand"] or "[]"))
