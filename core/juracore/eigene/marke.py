"""Kanzlei- bzw. Firmenlogo und Kurzbezeichnung für die Oberfläche, je Arbeitsumgebung.

Das Logo liegt als Kopie der gewählten Datei im Ordner der Umgebung (logo.png usw.), Kurzbezeichnung und
Hintergrund des Logos (weiß oder im Farbakzent) in marke.json daneben. Die Oberfläche bekommt das Logo als
data-URL, weil sie selbst keine Dateien lesen darf.

Word kann SVG und WebP nicht in den Briefkopf übernehmen. Für solche Logos rendert die Oberfläche ein PNG
(``druckbild_setzen``), das als logo-druck.png neben dem Logo liegt und mit ihm ersetzt oder entfernt wird.
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
DRUCKBILD = "logo-druck.png"
KURZ_LAENGE = 40
# Fläche hinter dem Logo in Leiste und Startseite: weißer Rahmen (Vorgabe) oder der eingestellte Farbakzent.
HINTERGRUENDE = ("weiss", "akzent")


def _logo(ordner: Path) -> Path | None:
    return next((p for p in sorted(ordner.glob("logo.*")) if p.suffix.lower() in FORMATE), None)


def _einstellungen(ordner: Path) -> dict:
    try:
        roh = json.loads((ordner / "marke.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return roh if isinstance(roh, dict) else {}


def _speichern(ordner: Path, **werte: str) -> None:
    """Ändert einzelne Werte in marke.json und lässt die übrigen stehen."""
    ordner.mkdir(parents=True, exist_ok=True)
    neu = {**_einstellungen(ordner), **werte}
    (ordner / "marke.json").write_text(json.dumps(neu, ensure_ascii=False), encoding="utf-8")


def _kurz(ordner: Path) -> str:
    wert = _einstellungen(ordner).get("kurzbezeichnung", "")
    return wert if isinstance(wert, str) else ""


def _hintergrund(ordner: Path) -> str:
    wert = _einstellungen(ordner).get("hintergrund")
    return wert if wert in HINTERGRUENDE else HINTERGRUENDE[0]


def lesen(ordner: Path, con: sqlite3.Connection) -> dict:
    """Logo (data-URL oder None), Kurzbezeichnung für die Leiste und der Name aus „Eigene Daten“ für die Startseite."""
    logo = _logo(ordner)
    url = None
    if logo:
        url = f"data:{FORMATE[logo.suffix.lower()]};base64,{base64.b64encode(logo.read_bytes()).decode('ascii')}"
    name = eigene.stand(con, mit_archiv=False)["organisation_name"]
    druckbild = logo is not None and (logo.suffix.lower() in (".png", ".jpg", ".jpeg")
                                      or (ordner / DRUCKBILD).is_file())
    return {"logo": url, "kurzbezeichnung": _kurz(ordner), "name": name, "druckbild": druckbild,
            "hintergrund": _hintergrund(ordner)}


def druckbild_setzen(ordner: Path, con: sqlite3.Connection, png_base64: str) -> dict:
    """PNG-Fassung eines SVG- oder WebP-Logos für Word (von der Oberfläche gerendert)."""
    daten = base64.b64decode(png_base64.split(",", 1)[-1], validate=True)
    if daten[:8] != b"\x89PNG\r\n\x1a\n" or len(daten) > GROESSTE:
        raise ValueError("Das Druckbild des Logos ist kein PNG bis 2 MB.")
    if _logo(ordner) is None:
        raise ValueError("Es ist kein Logo eingestellt.")
    (ordner / DRUCKBILD).write_bytes(daten)
    return lesen(ordner, con)


def _druckbild_entfernen(ordner: Path) -> None:
    (ordner / DRUCKBILD).unlink(missing_ok=True)


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
    _druckbild_entfernen(ordner)
    (ordner / "logo.neu").replace(ziel)
    return lesen(ordner, con)


def logo_entfernen(ordner: Path, con: sqlite3.Connection) -> dict:
    alt = _logo(ordner)
    if alt:
        alt.unlink()
    _druckbild_entfernen(ordner)
    return lesen(ordner, con)


def kurz_setzen(ordner: Path, con: sqlite3.Connection, text: str) -> dict:
    text = " ".join(text.split())
    if len(text) > KURZ_LAENGE:
        raise ValueError(f"Die Kurzbezeichnung passt mit höchstens {KURZ_LAENGE} Zeichen in die Leiste.")
    _speichern(ordner, kurzbezeichnung=text)
    return lesen(ordner, con)


def hintergrund_setzen(ordner: Path, con: sqlite3.Connection, hintergrund: str) -> dict:
    """Hintergrund des Logos: „weiss“ (weißer Rahmen) oder „akzent“ (Farbakzent aus Einstellungen → Allgemeines)."""
    if hintergrund not in HINTERGRUENDE:
        raise ValueError("Der Hintergrund des Logos ist entweder weiß oder im Farbakzent.")
    _speichern(ordner, hintergrund=hintergrund)
    return lesen(ordner, con)
