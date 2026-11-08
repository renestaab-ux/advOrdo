"""Gerichtsverzeichnis aus der XJustiz-Codeliste „GDS.Gerichte“.

Die Bund-Länder-Kommission (AG IT-Standards in der Justiz) veröffentlicht in XRepository
die Codeliste aller Gerichte, Staatsanwaltschaften und Justizbehörden mit ihrem
XJustiz-Schlüssel (z. B. ``B2402`` → „Amtsgericht Biberach an der Riß“). Die Liste wird
erst auf Wunsch geladen, unverändert unter ihrer SHA-256-Prüfsumme archiviert und dient
als Vorschlagsliste für das Feld „Gericht“. Ins Netz geht nur der Abruf der öffentlichen
Liste, ohne Bezug zu einer Akte.

Die Codeliste enthält nur Schlüssel und Namen, keine Anschriften und keine Zuständigkeiten.
Dafür verweist die App auf die Suchseite des Orts- und Gerichtsverzeichnisses der Justiz (justizadressen.nrw.de).
"""

from __future__ import annotations

import hashlib
import io
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from . import programme

KENNUNG = "urn:xoev-de:xjustiz:codeliste:gds.gerichte"
VERSION_URL = f"https://www.xrepository.de/api/codeliste/{KENNUNG}/gueltigeVersion"
# Rückfall, falls die Abfrage der gültigen Version scheitert; Stand 2026-02-18.
VERSION_RUECKFALL = f"{KENNUNG}_3.7"
ORTS_UND_GERICHTSVERZEICHNIS = "https://www.justizadressen.nrw.de/de/justiz/suche"
USER_AGENT = "advOrdo/0.1 (Gerichtsverzeichnis; advordo@staab.legal)"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gerichtsverzeichnis_stand (
    id              INTEGER PRIMARY KEY,
    sha256          TEXT NOT NULL,
    quelle          TEXT NOT NULL,
    version         TEXT,
    abgerufen_am    TEXT NOT NULL,
    roharchiv       TEXT,
    eintraege       INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS gerichtsverzeichnis (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    art             TEXT NOT NULL       -- gericht, staatsanwaltschaft, sonstige
);
"""


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


def art(name: str) -> str:
    """Grobe Einordnung nach dem Namen; die Codeliste selbst hat keine Spalte dafür."""
    n = name.lower()
    if "staatsanwalt" in n or "amtsanwalt" in n:
        return "staatsanwaltschaft"
    # Grundbuchämter laufen zwar unter dem Amtsgericht, sind aber kein Spruchkörper für ein Verfahren.
    if "gericht" in n and "grundbuchamt" not in n:
        return "gericht"
    return "sonstige"


# --- Laden -----------------------------------------------------------------------------------------


Oeffnen = Callable[..., object]


def _abruf(url: str, oeffnen: Oeffnen, timeout: float) -> bytes:
    anfrage = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with oeffnen(anfrage, timeout=timeout) as antwort:
        return antwort.read()


def gueltige_version(oeffnen: Oeffnen = urllib.request.urlopen, timeout: float = 30) -> str:
    """Kennung der gültigen Version, z. B. ``…gds.gerichte_3.7``; bei Fehlern die zuletzt bekannte."""
    try:
        daten = _abruf(VERSION_URL, oeffnen, timeout)
    except OSError:
        return VERSION_RUECKFALL
    m = re.search(rb"<(?:\w+:)?kennung>\s*(" + re.escape(KENNUNG.encode()) + rb"_[\w.]+)\s*<", daten)
    return m.group(1).decode() if m else VERSION_RUECKFALL


def genericode_url(version_kennung: str) -> str:
    return f"https://www.xrepository.de/api/xrepository/{version_kennung}/genericode"


def lade(oeffnen: Oeffnen = urllib.request.urlopen, timeout: float = 60) -> tuple[bytes, str]:
    """Lädt die gültige Fassung der Codeliste; liefert Daten und Quelle (Adresse)."""
    url = genericode_url(gueltige_version(oeffnen))
    return _abruf(url, oeffnen, timeout), url


def archiviere(daten: bytes, archiv: Path | None) -> tuple[str, str]:
    """Legt die Datei unverändert unter ihrer Prüfsumme ab; vorhandene Dateien bleiben unberührt."""
    sha = hashlib.sha256(daten).hexdigest()
    pfad = ""
    if archiv is not None:
        ziel = archiv / "GERICHTE" / f"{sha}.xml"
        if not ziel.exists():
            ziel.parent.mkdir(parents=True, exist_ok=True)
            tmp = ziel.with_suffix(".tmp")
            tmp.write_bytes(daten)
            tmp.replace(ziel)
            ziel.chmod(0o444)
        pfad = str(ziel)
    return sha, pfad


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def lies(daten: bytes) -> tuple[str | None, list[tuple[str, str]]]:
    """Liest Version und Zeilen (Schlüssel, Name) einer Codeliste im Format genericode."""
    wurzel = ET.parse(io.BytesIO(daten)).getroot()
    if _name(wurzel.tag) != "CodeList":
        raise ValueError("Keine Codeliste im Format genericode.")
    version = next((el.text for el in wurzel.iter() if _name(el.tag) == "Version"), None)
    spalten = [el.get("Id") for el in wurzel.iter() if _name(el.tag) == "Column"]
    zeilen: list[tuple[str, str]] = []
    for row in (el for el in wurzel.iter() if _name(el.tag) == "Row"):
        werte: dict[str, str] = {}
        for i, value in enumerate(v for v in row if _name(v.tag) == "Value"):
            # Ohne ColumnRef gilt die Reihenfolge der Spalten.
            spalte = value.get("ColumnRef") or (spalten[i] if i < len(spalten) else str(i))
            werte[spalte] = "".join(s.text or "" for s in value if _name(s.tag) == "SimpleValue").strip()
        code, wert = werte.get("code", ""), werte.get("wert", "")
        if code and wert:
            zeilen.append((code, wert))
    return (version.strip() if version else None), zeilen


def importiere(con: sqlite3.Connection, daten: bytes, quelle: str, sha: str, archivpfad: str) -> dict:
    """Übernimmt eine Codeliste als neuen Stand. Dieselbe Datei wird nicht doppelt übernommen."""
    einrichten(con)
    alt = stand(con)
    if alt and alt["sha256"] == sha:
        return {**alt, "neu": False}
    version, zeilen = lies(daten)
    if not zeilen:
        raise ValueError("Die Codeliste enthält keine lesbaren Einträge (Spalten „code“ und „wert“ erwartet).")
    with con:
        con.execute(
            """INSERT INTO gerichtsverzeichnis_stand (sha256, quelle, version, abgerufen_am, roharchiv, eintraege)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sha, quelle, version, datetime.now(UTC).isoformat(timespec="seconds"), archivpfad or None, len(zeilen)),
        )
        # Ältere Stände bleiben als Datei im Roharchiv; vorgeschlagen wird nur der neueste.
        con.execute("DELETE FROM gerichtsverzeichnis")
        con.executemany(
            "INSERT OR REPLACE INTO gerichtsverzeichnis (code, name, art) VALUES (?, ?, ?)",
            [(c, n, art(n)) for c, n in zeilen],
        )
    return {**stand(con), "neu": True}


def stand(con: sqlite3.Connection) -> dict | None:
    """Der geladene Stand mit Anzahl je Art, oder None."""
    einrichten(con)
    zeile = con.execute("SELECT * FROM gerichtsverzeichnis_stand ORDER BY id DESC LIMIT 1").fetchone()
    if zeile is None:
        return None
    arten = {z["art"]: z["n"] for z in con.execute("SELECT art, COUNT(*) AS n FROM gerichtsverzeichnis GROUP BY art")}
    return {k: zeile[k] for k in ("sha256", "quelle", "version", "abgerufen_am", "eintraege")} | {"arten": arten}


def namen(con: sqlite3.Connection, arten: tuple[str, ...] = ("gericht",)) -> list[str]:
    """Namen für die Vorschlagsliste, alphabetisch."""
    einrichten(con)
    platz = ",".join("?" * len(arten))
    return [z["name"] for z in con.execute(
        f"SELECT name FROM gerichtsverzeichnis WHERE art IN ({platz}) ORDER BY name COLLATE NOCASE", arten)]


def verzeichnis_oeffnen(oeffnen: Callable[[str], object] = programme.im_browser_oeffnen) -> dict:
    """Öffnet das Orts- und Gerichtsverzeichnis der Justiz im Browser (Anschrift, Zuständigkeit)."""
    oeffnen(ORTS_UND_GERICHTSVERZEICHNIS)
    return {"url": ORTS_UND_GERICHTSVERZEICHNIS}
