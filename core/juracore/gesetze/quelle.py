"""Abruf von Bundesrecht aus "Gesetze im Internet" und revisionssicheres Roharchiv.

Jede Quelldatei wird unverändert unter ihrer SHA-256-Prüfsumme abgelegt.
Der Abruf ist bedingt (ETag / Last-Modified), damit unveränderte Gesetze
nicht erneut übertragen werden. Es werden ausschließlich Normtexte geladen,
keine Dokumentinhalte des Nutzers übertragen.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

BASIS_URL = "https://www.gesetze-im-internet.de"
USER_AGENT = "JuraBox/0.1 (Wissensbasis-Import)"

# Voreingestellte Gesetze (Zivilrecht) stehen in voreinstellung.json. Jedes andere
# Bundesgesetz lässt sich über sein Kürzel laden (meist die kleingeschriebene
# Abkürzung, z. B. "GmbHG" -> "gmbhg").
_VOREINSTELLUNG = Path(__file__).with_name("voreinstellung.json")


def voreinstellung(eigene_liste: Path | None = None) -> list[dict]:
    """Gesetzesliste; eine eigene Datei (gleiches Format) ersetzt die mitgelieferte."""
    pfad = eigene_liste if eigene_liste is not None and eigene_liste.exists() else _VOREINSTELLUNG
    gesetze = json.loads(pfad.read_text(encoding="utf-8"))["gesetze"]
    for g in gesetze:
        if not _KUERZEL.match(g["abk"]) or not _KUERZEL.match(g["kuerzel"]):
            raise ValueError(f"Ungültiger Eintrag in {pfad.name}: {g}")
    return gesetze


_KUERZEL = re.compile(r"^[A-Za-z0-9_]{1,40}$")


@dataclass
class Rohdatei:
    abk: str
    quelle: str
    sha256: str
    xml: bytes
    archivpfad: Path | None


class NichtGeaendert(Exception):
    """Der Server meldet keine Änderung seit dem letzten Abruf (HTTP 304)."""


def lade_gesetz(abk: str, archiv: Path, timeout: float = 60, gesetze: list[dict] | None = None) -> Rohdatei:
    """Lädt die XML-Fassung eines Gesetzes und legt das ZIP im Roharchiv ab."""
    abk, kuerzel = pfadkuerzel(abk, gesetze)
    url = f"{BASIS_URL}/{kuerzel}/xml.zip"
    meta_pfad = archiv / abk / "abruf.json"
    meta = json.loads(meta_pfad.read_text(encoding="utf-8")) if meta_pfad.exists() else {}

    anfrage = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if meta.get("etag"):
        anfrage.add_header("If-None-Match", meta["etag"])
    if meta.get("last_modified"):
        anfrage.add_header("If-Modified-Since", meta["last_modified"])
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            daten = antwort.read()
            kopf = antwort.headers
    except urllib.error.HTTPError as fehler:
        if fehler.code == 304:
            raise NichtGeaendert(abk) from None
        if fehler.code == 404:
            raise ValueError(
                f"{abk} wurde auf gesetze-im-internet.de nicht gefunden (Kürzel {kuerzel!r}). "
                "Bitte die Abkürzung aus der Adresse des Gesetzes verwenden."
            ) from None
        raise

    roh = archiviere(abk, daten, url, archiv)
    meta_pfad.write_text(
        json.dumps({"etag": kopf.get("ETag"), "last_modified": kopf.get("Last-Modified"), "sha256": roh.sha256}),
        encoding="utf-8",
    )
    return roh


def pfadkuerzel(abk: str, gesetze: list[dict] | None = None) -> tuple[str, str]:
    """Normalisierte Abkürzung und Pfadkürzel; lehnt alles ab, was kein Kürzel sein kann."""
    abk = abk.strip()
    if not _KUERZEL.match(abk):
        raise ValueError(f"Ungültige Gesetzesabkürzung: {abk!r}")
    bekannt = {g["abk"].upper(): g["kuerzel"] for g in (gesetze if gesetze is not None else voreinstellung())}
    return abk.upper(), bekannt.get(abk.upper(), abk.lower())


def lies_datei(pfad: Path, archiv: Path | None, abk: str | None = None) -> Rohdatei:
    """Liest eine lokal vorliegende GII-Datei (.xml oder .zip), z. B. für Offline-Importe."""
    daten = pfad.read_bytes()
    return archiviere(abk or pfad.stem.upper(), daten, str(pfad), archiv)


def archiviere(abk: str, daten: bytes, quelle: str, archiv: Path | None) -> Rohdatei:
    sha = hashlib.sha256(daten).hexdigest()
    ist_zip = daten[:2] == b"PK"
    archivpfad = None
    if archiv is not None:
        archivpfad = archiv / abk.upper() / f"{sha}.{'zip' if ist_zip else 'xml'}"
        if not archivpfad.exists():
            archivpfad.parent.mkdir(parents=True, exist_ok=True)
            tmp = archivpfad.with_suffix(".tmp")
            tmp.write_bytes(daten)
            tmp.replace(archivpfad)
            archivpfad.chmod(0o444)
    return Rohdatei(
        abk=abk.upper(), quelle=quelle, sha256=sha, xml=_xml_aus(daten) if ist_zip else daten, archivpfad=archivpfad
    )


def _xml_aus(zipdaten: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zipdaten)) as z:
        xmls = [n for n in z.namelist() if n.lower().endswith(".xml") and "/" not in n.strip("/")]
        if len(xmls) != 1:
            raise ValueError(f"Erwartet genau eine XML-Datei im Archiv, gefunden: {xmls}")
        return z.read(xmls[0])
