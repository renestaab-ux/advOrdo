"""Volltexte der Bundesgerichte von rechtsprechung-im-internet.de.

Je Entscheidung gibt es ein ZIP mit einer XML-Datei (DTD ``rii-dok.dtd``): Kopfdaten (Gericht,
Spruchkörper, Datum, Aktenzeichen, Normen, Vorinstanzen) und die Teile Leitsatz, Tenor,
Tatbestand, Entscheidungsgründe bzw. Gründe. Jeder Absatz ist ein ``<dl>``; die Randnummer
steht im ``<dt>`` als ``<a name="rd_5">5</a>``, der Text im ``<dd>``.

Geladen wird nur die öffentliche Entscheidung über ihre Dokumentnummer; aus der Akte wird nichts
gesendet. Die ZIP-Datei wird unverändert unter ihrer SHA-256-Prüfsumme archiviert.
"""

from __future__ import annotations

import hashlib
import io
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .verzeichnis import USER_AGENT

ADRESSE = "https://www.rechtsprechung-im-internet.de/jportal/docs/bsjrs/jb-{doknr}.zip"
HERKUNFT = "rechtsprechung-im-internet.de"

# Teile der Entscheidung in der Reihenfolge des Dokuments, mit Überschrift für die Anzeige.
TEILE = {
    "leitsatz": "Leitsatz",
    "sonstosatz": "Orientierungssatz",
    "tenor": "Tenor",
    "tatbestand": "Tatbestand",
    "entscheidungsgruende": "Entscheidungsgründe",
    "gruende": "Gründe",
    "abwmeinung": "Abweichende Meinung",
    "sonstlt": "Sonstiger Langtext",
}


@dataclass
class Absatz:
    teil: str
    rn: int | None
    text: str


@dataclass
class Volltext:
    doknr: str
    gericht: str
    spruchkoerper: str | None
    datum: str | None
    aktenzeichen: str
    doktyp: str | None
    normen: str | None
    vorinstanz: list[str]
    titel: str | None
    absaetze: list[Absatz] = field(default_factory=list)

    @property
    def randnummern(self) -> list[int]:
        return [a.rn for a in self.absaetze if a.rn is not None]


def adresse(doknr: str) -> str:
    if not re.fullmatch(r"[A-Z0-9]+", doknr):
        raise ValueError(f"Ungültige Dokumentnummer: {doknr!r}")
    return ADRESSE.format(doknr=doknr)


def lade(doknr: str, timeout: float = 60) -> bytes:
    """Lädt das ZIP einer Entscheidung."""
    anfrage = urllib.request.Request(adresse(doknr), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
        return antwort.read()


def archiviere(daten: bytes, archiv: Path) -> tuple[str, Path]:
    """Legt die Datei unverändert und schreibgeschützt unter ihrer Prüfsumme ab; Vorhandenes bleibt."""
    sha = hashlib.sha256(daten).hexdigest()
    ziel = Path(archiv) / "RECHTSPRECHUNG" / "volltexte" / f"{sha}.zip"
    if not ziel.exists():
        ziel.parent.mkdir(parents=True, exist_ok=True)
        tmp = ziel.with_suffix(".tmp")
        tmp.write_bytes(daten)
        tmp.replace(ziel)
        ziel.chmod(0o444)
    return sha, ziel


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    teile = []
    for t in el.iter():
        if t.tag == "br":
            teile.append("\n")
        if t.text:
            teile.append(t.text)
        if t.tail and t is not el:
            teile.append(t.tail)
    return "\n".join(" ".join(z.split()) for z in "".join(teile).split("\n")).strip()


def _absaetze(teil: str, el: ET.Element) -> list[Absatz]:
    ergebnis = []
    for dl in el.iter("dl"):
        dt, dd = dl.find("dt"), dl.find("dd")
        text = _text(dd)
        if not text:
            continue
        rn_text = _text(dt)
        ergebnis.append(Absatz(teil, int(rn_text) if rn_text.isdigit() else None, text))
    if not ergebnis and (text := _text(el)):
        ergebnis.append(Absatz(teil, None, text))
    return ergebnis


def lies(daten: bytes) -> Volltext:
    """Liest eine Entscheidung (ZIP mit einer XML-Datei oder die XML-Datei selbst)."""
    if daten[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            xmls = [n for n in z.namelist() if n.lower().endswith(".xml")]
            if len(xmls) != 1:
                raise ValueError(f"Erwartet genau eine XML-Datei im Archiv, gefunden: {xmls}")
            daten = z.read(xmls[0])
    try:
        wurzel = ET.fromstring(daten)
    except ET.ParseError as fehler:
        raise ValueError(f"Die Entscheidung ist kein lesbares XML ({fehler}).") from fehler
    if wurzel.tag != "dokument" or not wurzel.findtext("aktenzeichen"):
        raise ValueError("Die Datei ist keine Entscheidung im Format von rechtsprechung-im-internet.de.")

    def feld(name: str) -> str | None:
        return _text(wurzel.find(name)) or None

    gericht = " ".join(filter(None, [feld("gertyp"), feld("gerort")]))
    datum = feld("entsch-datum")
    v = Volltext(
        doknr=feld("doknr") or "",
        gericht=gericht,
        spruchkoerper=feld("spruchkoerper"),
        datum=f"{datum[:4]}-{datum[4:6]}-{datum[6:8]}" if datum and re.fullmatch(r"\d{8}", datum) else None,
        aktenzeichen=feld("aktenzeichen") or "",
        doktyp=feld("doktyp"),
        normen=feld("norm"),
        vorinstanz=[z for z in (feld("vorinstanz") or "").split("\n") if z.strip()],
        titel=feld("titelzeile"),
    )
    for name in TEILE:
        el = wurzel.find(name)
        if el is not None:
            v.absaetze.extend(_absaetze(name, el))
    if not v.absaetze:
        raise ValueError(f"In der Entscheidung {v.aktenzeichen} wurde kein Text gefunden.")
    return v
