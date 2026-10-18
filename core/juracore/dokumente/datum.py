"""Datum eines Dokuments: aus dem Text, sonst aus dem Speicherstand.

Reihenfolge:

1. **Dokument:** die Datumszeile im Text, z. B. „Freiburg, den 23.06.2025“,
   „[ORT 2], 18.11.2025“, „Verkündet am 14.09.2026“ oder „Datum: 1. März 2025“.
   Es zählt die erste solche Zeile; Daten im Fließtext („Schreiben vom …“)
   werden bewusst nicht genommen, weil sie andere Vorgänge bezeichnen.
2. **Word:** bei DOCX der Zeitpunkt des letzten Speicherns aus den
   Dokumenteigenschaften (``docProps/core.xml``, ``dcterms:modified``).
3. **Datei:** das Änderungsdatum der Datei im Dateisystem beim Einlesen.

Jedes Ergebnis nennt seine Herkunft, beim Datum aus dem Text auch den Abschnitt
als Fundstelle.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from ..abgleich.angaben import MONATE

DOKUMENT = "dokument"
WORD = "word"
DATEI = "datei"
UNBEKANNT = "unbekannt"

_MONATSNAME = "|".join(MONATE)
_TAG = rf"(\d{{1,2}})\.\s?(?:(\d{{1,2}})\.\s?|\s*((?i:{_MONATSNAME}))\s+)(\d{{4}})"
# Ort mit Komma vor dem Datum: „Freiburg, den …“, „Freiburg im Breisgau, …“, „Frankfurt a. M., …“, „[ORT 2], …“.
_ORT = r"(?:\[[A-ZÄÖÜ ]+\d*\]|[A-ZÄÖÜ][\wäöüß.\-]+(?:\s+[a-zäöü]{1,3}\.?(?:\s+[A-ZÄÖÜ][\wäöüß.\-]*)?){0,2})"
_DATUMSZEILE = re.compile(
    rf"(?:^|(?<=\s))(?:{_ORT},\s+(?:den\s+)?|(?:Verkündet|Erlassen|Beschlossen)\s+am\s+|(?:Datum|Stand):\s*){_TAG}"
    rf"(?=$|[\s,;)]|\.(?:\s|$))"
)
_WOCHENTAGE = {"montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"}

_CP = "{http://purl.org/dc/terms/}"


def _iso(tag: str, monat: str | None, monatsname: str | None, jahr: str) -> str | None:
    nr = int(monat) if monat else MONATE[monatsname.lower()]
    try:
        return date(int(jahr), nr, int(tag)).isoformat()
    except ValueError:
        return None


def aus_text(abschnitte: Iterable[tuple[int, int | None, str]]) -> dict | None:
    """Erste Datumszeile in ``(Abschnitt-Nr., Seite, Text)``; ``None``, wenn es keine gibt."""
    for nr, seite, text in abschnitte:
        for m in _DATUMSZEILE.finditer(text):
            if m[0].split(",")[0].strip().lower() in _WOCHENTAGE:
                continue  # „Montag, 3.11.2025“ im Fließtext ist kein Ort
            iso = _iso(m[1], m[2], m[3], m[4])
            if iso:
                return {"datum": iso, "quelle": DOKUMENT, "abschnitt": nr, "seite": seite, "text": m[0].strip()}
    return None


def word_gespeichert(pfad: Path) -> str | None:
    """Letztes Speichern laut Word-Dokumenteigenschaften, als ISO-Zeitpunkt in Ortszeit."""
    try:
        with zipfile.ZipFile(pfad) as z:
            xml = z.read("docProps/core.xml")
        wert = ET.fromstring(xml).findtext(f"{_CP}modified")
    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError):
        return None
    if not wert:
        return None
    try:
        zeitpunkt = datetime.fromisoformat(wert.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if zeitpunkt.tzinfo is None:
        return zeitpunkt.isoformat(timespec="seconds")
    return zeitpunkt.astimezone().isoformat(timespec="seconds")


def datei_gespeichert(pfad: Path) -> str | None:
    """Änderungsdatum der Datei im Dateisystem, als ISO-Zeitpunkt in Ortszeit."""
    try:
        return datetime.fromtimestamp(pfad.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except (OSError, ValueError):
        return None


def ermitteln(
    abschnitte: Iterable[tuple[int, int | None, str]],
    fmt: str,
    original: Path | None,
    quelle_datei: Path | None,
) -> dict:
    """Datum mit Herkunft und, soweit bekannt, dem Speicherstand.

    ``original`` ist die unverändert abgelegte Datei (für die Word-Eigenschaften), ``quelle_datei``
    die Datei am ursprünglichen Ort (für das Änderungsdatum; die Kopie in der Ablage trägt den
    Zeitpunkt des Einlesens). Ohne ``quelle_datei`` wird das Dateidatum nicht verwendet.
    """
    gespeichert, gespeichert_quelle = None, None
    if fmt == "docx" and original is not None:
        gespeichert = word_gespeichert(original)
        gespeichert_quelle = WORD if gespeichert else None
    if gespeichert is None and quelle_datei is not None:
        gespeichert = datei_gespeichert(quelle_datei)
        gespeichert_quelle = DATEI if gespeichert else None

    ergebnis = aus_text(abschnitte) or (
        {"datum": gespeichert[:10], "quelle": gespeichert_quelle, "abschnitt": None, "seite": None, "text": None}
        if gespeichert
        else {"datum": None, "quelle": UNBEKANNT, "abschnitt": None, "seite": None, "text": None}
    )
    ergebnis["gespeichert"] = gespeichert
    ergebnis["gespeichert_quelle"] = gespeichert_quelle
    return ergebnis
