"""Import, Suche und Zitatauflösung über der Gesetzes-Datenbank."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from .. import db
from .gii import parse_gii_xml
from .quelle import Rohdatei
from .zitate import Zitat, parse_zitat


def importiere(con: sqlite3.Connection, roh: Rohdatei, abk: str | None = None) -> dict:
    """Übernimmt eine Rohdatei als neue Fassung. Unveränderte Dateien werden übersprungen.

    ``abk`` ist die Abkürzung, unter der das Gesetz zitiert wird (z. B. "EGBGB"). Ohne
    sie gilt die juristische Abkürzung aus der Datei, die bei Gesetze im Internet
    teils abweicht ("BGBEG", "UWG 2004").
    """
    dokument = parse_gii_xml(roh.xml)
    datei_abk = dokument.abk.upper()
    abk = (abk or datei_abk).upper()
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
    ergebnis: dict = {"zitat": str(z), "status": "nicht_gefunden", "wortlaut": None, "fassung": None, "hinweis": None}
    fassung = _fassung(con, z.gesetz, fassung_id)
    if fassung is None:
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

    if z.absatz is None:
        teil_text = "\n".join(a["text"] for a in n["absaetze"])
    else:
        absatz = next((a for a in n["absaetze"] if a["nr"] == z.absatz), None)
        if absatz is None:
            ergebnis["hinweis"] = f"{n['bezeichnung']} hat keinen Absatz {z.absatz}."
            return ergebnis
        teil_text = absatz["text"]
        saetze = absatz["saetze"]
        if z.satz is not None:
            satz = next((s for s in saetze if s["nr"] == z.satz), None)
            if satz is None:
                ergebnis["hinweis"] = f"Abs. {z.absatz} hat nur {len(saetze)} Satz/Sätze."
                return ergebnis
            teil_text = satz["text"]
            saetze = [satz]
        if z.nr is not None:
            eintrag = next((t for s in saetze for nr, t in s["nummern"] if nr == z.nr), None)
            if eintrag is None:
                ergebnis["hinweis"] = f"Nr. {z.nr} wurde in der Fundstelle nicht gefunden."
                return ergebnis
            teil_text = f"{z.nr}. {eintrag}"
    ergebnis.update(status="belegt", wortlaut=teil_text)
    return ergebnis


def _fassung(con: sqlite3.Connection, abk: str, fassung_id: int | None) -> sqlite3.Row | None:
    if fassung_id is None:
        return db.aktuelle_fassung(con, abk)
    return con.execute(
        """SELECT f.*, g.abk, g.langtitel FROM fassung f JOIN gesetz g ON g.id = f.gesetz_id
           WHERE f.id = ? AND g.abk = ?""",
        (fassung_id, abk.upper()),
    ).fetchone()


def _fassung_info(f: sqlite3.Row) -> dict:
    return {
        "id": f["id"],
        "quelle": f["quelle"],
        "abgerufen_am": f["abgerufen_am"],
        "builddate": f["builddate"],
        "stand": json.loads(f["stand"] or "[]"),
        "sha256": f["sha256"],
        "hinweis": "Konsolidierte, nichtamtliche Fassung (Gesetze im Internet).",
    }
