"""Kanzlei- bzw. Firmenlogo und Kurzbezeichnung für die Oberfläche, je Arbeitsumgebung.

Das Logo liegt als Kopie der gewählten Datei im Ordner der Umgebung (logo.png usw.), die Kurzbezeichnung in
marke.json daneben. Die Oberfläche bekommt das Logo als data-URL, weil sie selbst keine Dateien lesen darf.
"""

from __future__ import annotations

import base64
import json
import shutil
import sqlite3
from pathlib import Path

from . import daten as eigene

FORMATE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
           ".webp": "image/webp"}
GROESSTE = 2 * 1024 * 1024
KURZ_LAENGE = 40


def _logo(ordner: Path) -> Path | None:
    return next((p for p in sorted(ordner.glob("logo.*")) if p.suffix.lower() in FORMATE), None)


def _kurz(ordner: Path) -> str:
    try:
        return json.loads((ordner / "marke.json").read_text(encoding="utf-8")).get("kurzbezeichnung", "")
    except (OSError, ValueError):
        return ""


def lesen(ordner: Path, con: sqlite3.Connection) -> dict:
    """Logo (data-URL oder None), Kurzbezeichnung für die Leiste und der Name aus „Eigene Daten“ für die Startseite."""
    logo = _logo(ordner)
    url = None
    if logo:
        url = f"data:{FORMATE[logo.suffix.lower()]};base64,{base64.b64encode(logo.read_bytes()).decode('ascii')}"
    name = eigene.stand(con, mit_archiv=False)["organisation_name"]
    return {"logo": url, "kurzbezeichnung": _kurz(ordner), "name": name}


def logo_setzen(ordner: Path, con: sqlite3.Connection, pfad: str | Path) -> dict:
    quelle = Path(pfad)
    endung = quelle.suffix.lower()
    if endung not in FORMATE:
        raise ValueError("Bitte ein Bild im Format PNG, JPG, SVG oder WebP wählen.")
    if quelle.stat().st_size > GROESSTE:
        raise ValueError("Das Logo ist größer als 2 MB. Bitte eine kleinere Datei wählen.")
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / f"logo{endung}"
    shutil.copyfile(quelle, ordner / "logo.neu")
    alt = _logo(ordner)
    if alt:
        alt.unlink()
    (ordner / "logo.neu").replace(ziel)
    return lesen(ordner, con)


def logo_entfernen(ordner: Path, con: sqlite3.Connection) -> dict:
    alt = _logo(ordner)
    if alt:
        alt.unlink()
    return lesen(ordner, con)


def kurz_setzen(ordner: Path, con: sqlite3.Connection, text: str) -> dict:
    text = " ".join(text.split())
    if len(text) > KURZ_LAENGE:
        raise ValueError(f"Die Kurzbezeichnung passt mit höchstens {KURZ_LAENGE} Zeichen in die Leiste.")
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "marke.json").write_text(json.dumps({"kurzbezeichnung": text}, ensure_ascii=False), encoding="utf-8")
    return lesen(ordner, con)
