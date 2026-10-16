"""Verzeichnis der Bundesrechtsprechung aus „Rechtsprechung im Internet“ und Prüfung von Zitaten.

Rechtsprechung im Internet (BMJV) veröffentlicht ein Inhaltsverzeichnis aller dort
eingestellten Entscheidungen der Bundesgerichte (``rii-toc.xml``): Gericht mit
Spruchkörper, Entscheidungsdatum, Aktenzeichen und Link. Es wird einmal geladen,
unverändert unter seiner SHA-256-Prüfsumme archiviert und lokal durchsucht. Beim
Prüfen eines Zitats verlässt nichts das Gerät; geladen wird nur die öffentliche
Liste, ohne Bezug zu einer Akte.

Die Prüfung belegt nur, dass es eine Entscheidung dieses Gerichts mit diesem
Aktenzeichen und Datum gibt, nicht, dass sie die zitierte Aussage trägt.
"""

from __future__ import annotations

import hashlib
import io
import re
import sqlite3
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .zitate import UrteilsZitat, normalisiere_az

URL = "https://www.rechtsprechung-im-internet.de/rii-toc.xml"
USER_AGENT = "JuristischerDatenabgleich/0.1 (Rechtsprechungsverzeichnis)"
BUNDESGERICHTE = ("BVerfG", "BGH", "BAG", "BSG", "BFH", "BVerwG", "BPatG", "GmS-OGB")

# Prüfergebnisse, in der Reihenfolge, in der die App sie zeigt.
ABWEICHEND = "abweichend"  # Aktenzeichen bekannt, aber Datum oder Gericht passen nicht
NICHT_GEFUNDEN = "nicht_gefunden"  # Bundesgericht im erfassten Zeitraum, Aktenzeichen unbekannt
BELEGT = "belegt"
AUSSERHALB = "ausserhalb"  # Gericht oder Zeitraum nicht im Verzeichnis
NICHT_PRUEFBAR = "nicht_pruefbar"  # nur Zeitschriftenfundstelle, kein Aktenzeichen
KEIN_VERZEICHNIS = "kein_verzeichnis"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rechtsprechung_stand (
    id              INTEGER PRIMARY KEY,
    sha256          TEXT NOT NULL,
    quelle          TEXT NOT NULL,
    abgerufen_am    TEXT NOT NULL,
    roharchiv       TEXT,
    eintraege       INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS entscheidung (
    id              INTEGER PRIMARY KEY,
    stand_id        INTEGER NOT NULL REFERENCES rechtsprechung_stand(id),
    gericht         TEXT NOT NULL,          -- „BGH“
    spruchkoerper   TEXT,                   -- „8. Zivilsenat“
    datum           TEXT,                   -- ISO
    aktenzeichen    TEXT NOT NULL,
    az_norm         TEXT NOT NULL,
    doknr           TEXT,
    link            TEXT
);
CREATE INDEX IF NOT EXISTS entscheidung_az ON entscheidung (az_norm);
"""


@dataclass
class Eintrag:
    gericht: str
    spruchkoerper: str | None
    datum: str | None
    aktenzeichen: str
    doknr: str | None
    link: str | None


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


# --- Laden -----------------------------------------------------------------------------------------


def lade(archiv: Path, timeout: float = 120) -> tuple[bytes, str, str]:
    """Lädt das Inhaltsverzeichnis; liefert Daten, Prüfsumme und Archivpfad."""
    anfrage = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
        daten = antwort.read()
    return daten, *archiviere(daten, archiv)


def archiviere(daten: bytes, archiv: Path | None) -> tuple[str, str]:
    """Legt die Datei unverändert unter ihrer Prüfsumme ab; vorhandene Dateien bleiben unberührt."""
    sha = hashlib.sha256(daten).hexdigest()
    pfad = ""
    if archiv is not None:
        ziel = archiv / "RECHTSPRECHUNG" / f"{sha}.{'zip' if daten[:2] == b'PK' else 'xml'}"
        if not ziel.exists():
            ziel.parent.mkdir(parents=True, exist_ok=True)
            tmp = ziel.with_suffix(".tmp")
            tmp.write_bytes(daten)
            tmp.replace(ziel)
            ziel.chmod(0o444)
        pfad = str(ziel)
    return sha, pfad


def lies_verzeichnis(daten: bytes) -> Iterator[Eintrag]:
    """Liest die Einträge des Inhaltsverzeichnisses (XML, auch als ZIP)."""
    if daten[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            xmls = [n for n in z.namelist() if n.lower().endswith(".xml")]
            if len(xmls) != 1:
                raise ValueError(f"Erwartet genau eine XML-Datei im Archiv, gefunden: {xmls}")
            daten = z.read(xmls[0])
    for _, el in ET.iterparse(io.BytesIO(daten), events=("end",)):
        if _name(el.tag) != "item":
            continue
        felder = {_name(k.tag): (k.text or "").strip() for k in el}
        el.clear()
        az_text = felder.get("aktenzeichen") or felder.get("az") or ""
        gericht_text = felder.get("gericht") or ""
        if not az_text or not gericht_text:
            continue
        if gericht_text.startswith("Gemeinsamer Senat"):
            gericht, spruchkoerper = "GmS-OGB", ""
        else:
            gericht, _, spruchkoerper = gericht_text.partition(" ")
        link = felder.get("link") or None
        doknr = m.group(1) if link and (m := re.search(r"jb-([A-Z0-9]+)\.zip", link)) else None
        # Verbundene Verfahren: „VIII ZR 103/15, VIII ZR 104/15“.
        for az in re.split(r"\s*[,;]\s*", az_text):
            if az:
                yield Eintrag(gericht, spruchkoerper or None, _datum(felder.get("entsch-datum") or ""), az, doknr, link)


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _datum(text: str) -> str | None:
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    return None


def importiere(con: sqlite3.Connection, daten: bytes, quelle: str, sha: str, archivpfad: str) -> dict:
    """Übernimmt ein Verzeichnis als neuen Stand. Dasselbe Verzeichnis wird nicht doppelt übernommen."""
    einrichten(con)
    alt = stand(con)
    if alt and alt["sha256"] == sha:
        return {**alt, "neu": False}
    eintraege = list(lies_verzeichnis(daten))
    if not eintraege:
        raise ValueError("Das Verzeichnis enthält keine lesbaren Entscheidungen (Format unbekannt?).")
    with con:
        stand_id = con.execute(
            """INSERT INTO rechtsprechung_stand (sha256, quelle, abgerufen_am, roharchiv, eintraege)
               VALUES (?, ?, ?, ?, ?)""",
            (sha, quelle, datetime.now(UTC).isoformat(timespec="seconds"), archivpfad or None, len(eintraege)),
        ).lastrowid
        # Der alte Stand bleibt als Datei im Roharchiv; durchsucht wird nur der neueste.
        con.execute("DELETE FROM entscheidung")
        con.executemany(
            """INSERT INTO entscheidung (stand_id, gericht, spruchkoerper, datum, aktenzeichen, az_norm, doknr, link)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(stand_id, e.gericht, e.spruchkoerper, e.datum, e.aktenzeichen, normalisiere_az(e.aktenzeichen),
              e.doknr, e.link) for e in eintraege],
        )
    return {**stand(con), "neu": True}


def stand(con: sqlite3.Connection) -> dict | None:
    """Der geladene Stand mit Zeitraum je Gericht, oder None."""
    einrichten(con)
    zeile = con.execute("SELECT * FROM rechtsprechung_stand ORDER BY id DESC LIMIT 1").fetchone()
    if zeile is None:
        return None
    gerichte = {
        z["gericht"]: {"anzahl": z["n"], "von": z["von"], "bis": z["bis"]}
        for z in con.execute(
            "SELECT gericht, COUNT(*) AS n, MIN(datum) AS von, MAX(datum) AS bis FROM entscheidung GROUP BY gericht"
        )
    }
    return {k: zeile[k] for k in ("id", "sha256", "quelle", "abgerufen_am", "eintraege")} | {"gerichte": gerichte}


# --- Prüfen ----------------------------------------------------------------------------------------


def dokument_link(doknr: str | None, link: str | None) -> str | None:
    """Adresse der Entscheidung zum Lesen im Browser."""
    if doknr:
        return ("https://www.rechtsprechung-im-internet.de/jportal/?quelle=jlink&docid="
                f"{doknr}&psml=bsjrsprod.psml&max=true")
    return link


def pruefe(con: sqlite3.Connection, z: UrteilsZitat, aktueller_stand: dict | None = None) -> dict:
    """Prüft ein Zitat gegen das Verzeichnis. Liefert Status, Hinweis und die gefundene Entscheidung."""
    s = aktueller_stand if aktueller_stand is not None else stand(con)
    ergebnis = {"status": None, "hinweis": None, "stand_id": s["id"] if s else None, "entscheidung": None}
    if z.aktenzeichen is None:
        return ergebnis | {"status": NICHT_PRUEFBAR,
                           "hinweis": "Nur Zeitschriftenfundstelle, kein Aktenzeichen; nicht automatisch prüfbar."}
    if z.gerichtstyp not in BUNDESGERICHTE:
        return ergebnis | {"status": AUSSERHALB,
                           "hinweis": f"{z.gerichtstyp}-Entscheidungen sind nicht im Verzeichnis der Bundesgerichte."}
    if s is None:
        return ergebnis | {"status": KEIN_VERZEICHNIS,
                           "hinweis": "Das Verzeichnis der Bundesrechtsprechung ist noch nicht geladen."}
    treffer = con.execute(
        "SELECT * FROM entscheidung WHERE az_norm = ? ORDER BY datum", (normalisiere_az(z.aktenzeichen),)
    ).fetchall()
    eigene = [t for t in treffer if t["gericht"] == z.gerichtstyp]
    passend = [t for t in eigene if z.datum is None or t["datum"] == z.datum]
    if passend:
        t = passend[0]
        return ergebnis | {"status": BELEGT, "entscheidung": _info(t),
                           "hinweis": f"{_beschreibung(t)}."}
    if eigene:
        daten = ", ".join(_tag(t["datum"]) for t in eigene)
        return ergebnis | {"status": ABWEICHEND, "entscheidung": _info(eigene[0]),
                           "hinweis": f"Aktenzeichen bekannt, aber vom {daten}, nicht vom {_tag(z.datum)}."}
    if treffer:
        t = treffer[0]
        return ergebnis | {"status": ABWEICHEND, "entscheidung": _info(t),
                           "hinweis": f"Aktenzeichen gehört laut Verzeichnis zu {_beschreibung(t)}."}
    zeitraum = s["gerichte"].get(z.gerichtstyp)
    if zeitraum is None:
        return ergebnis | {"status": AUSSERHALB,
                           "hinweis": f"Das Verzeichnis enthält keine Entscheidungen des {z.gerichtstyp}."}
    if z.datum and zeitraum["von"] and z.datum < zeitraum["von"]:
        return ergebnis | {"status": AUSSERHALB,
                           "hinweis": f"Das Verzeichnis enthält {z.gerichtstyp}-Entscheidungen erst ab "
                                      f"{_tag(zeitraum['von'])}."}
    return ergebnis | {"status": NICHT_GEFUNDEN,
                       "hinweis": f"Keine {z.gerichtstyp}-Entscheidung mit diesem Aktenzeichen im Verzeichnis "
                                  f"(Stand {s['abgerufen_am'][:10]}). Zitat prüfen."}


def _tag(iso: str | None) -> str:
    if not iso:
        return "unbekanntem Datum"
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def _beschreibung(t: sqlite3.Row) -> str:
    return f"{t['gericht']} {t['spruchkoerper'] or ''}, {_tag(t['datum'])} – {t['aktenzeichen']}".replace(" ,", ",")


def _info(t: sqlite3.Row) -> dict:
    return {"gericht": t["gericht"], "spruchkoerper": t["spruchkoerper"], "datum": t["datum"],
            "aktenzeichen": t["aktenzeichen"], "link": dokument_link(t["doknr"], t["link"])}


