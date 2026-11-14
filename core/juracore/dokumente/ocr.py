"""Texterkennung (OCR) über Tesseract.

Tesseract ist quelloffen, läuft auf Windows, macOS und Linux und erkennt
Deutsch zuverlässig. Es wird als eigenständiges Programm aufgerufen; das
Seitenbild liegt dafür kurz im Temp-Ordner, der Text kommt über stdout zurück.
Es wird nichts übertragen.

Der einzige plattformabhängige Teil ist die Suche nach dem Programm:
``JURACORE_TESSERACT``, unter Windows dann die üblichen Installationsorte, danach
``tesseract`` im Suchpfad und unter macOS die Homebrew-Orte.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SPRACHE = "deu"


class OcrNichtVerfuegbar(RuntimeError):
    """Tesseract oder die deutschen Sprachdaten fehlen."""


def _kandidaten() -> list[Path]:
    pfade = []
    if env := os.environ.get("JURACORE_TESSERACT"):
        pfade.append(Path(env))
    if sys.platform == "win32":
        # Erst die Installationsordner: shutil.which sucht unter Windows auch im aktuellen Ordner.
        for basis in (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if basis:
                pfade.append(Path(basis) / "Tesseract-OCR" / "tesseract.exe")
                pfade.append(Path(basis) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
    if gefunden := shutil.which("tesseract"):
        pfade.append(Path(gefunden))
    if sys.platform == "darwin":
        # Aus dem Finder gestartete Apps kennen den Homebrew-Pfad nicht.
        pfade += [Path("/opt/homebrew/bin/tesseract"), Path("/usr/local/bin/tesseract")]
    return pfade


def _ausfuehren(befehl: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    # Unter Windows kein Konsolenfenster je Seite aufblitzen lassen.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(befehl, capture_output=True, timeout=timeout, creationflags=flags)


@dataclass
class Tesseract:
    programm: Path
    version: str

    @classmethod
    def finden(cls) -> Tesseract:
        for pfad in _kandidaten():
            if pfad.is_file():
                try:
                    ausgabe = _ausfuehren([str(pfad), "--version"], timeout=20)
                except (OSError, subprocess.SubprocessError):
                    continue
                text = (ausgabe.stdout or ausgabe.stderr).decode("utf-8", "replace")
                version = text.splitlines()[0].strip() if text else "tesseract"
                return cls(pfad, version)
        raise OcrNichtVerfuegbar(
            "Tesseract wurde nicht gefunden. Scans ohne Textebene können erst gelesen werden, "
            "wenn Tesseract installiert ist (siehe README, Abschnitt Texterkennung)."
        )

    def sprachen(self) -> list[str]:
        ausgabe = _ausfuehren([str(self.programm), "--list-langs"], timeout=20)
        zeilen = (ausgabe.stdout or ausgabe.stderr).decode("utf-8", "replace").splitlines()
        return [z.strip() for z in zeilen[1:] if z.strip()]

    def pruefe_sprache(self) -> None:
        if SPRACHE not in self.sprachen():
            raise OcrNichtVerfuegbar(
                f"Tesseract ist installiert ({self.programm}), aber die deutschen Sprachdaten "
                f"({SPRACHE}.traineddata) fehlen (siehe README, Abschnitt Texterkennung)."
            )

    def erkenne(self, bild: bytes) -> tuple[list[str], float | None]:
        """Erkennt Text auf einem Seitenbild (PNM/PNG). Ergebnis: Zeilen und mittlere Konfidenz."""
        zeilen, konfidenz, _ = self.erkenne_mit_woertern(bild)
        return zeilen, konfidenz

    def erkenne_mit_woertern(self, bild: bytes) -> tuple[list[str], float | None, list[list]]:
        """Wie ``erkenne``, zusätzlich die Wörter mit ihrer Lage auf der Seite (siehe ``lies_woerter``)."""
        # Das Seitenbild geht über eine kurzlebige Datei im Temp-Ordner, nicht über stdin: Das Lesen von
        # stdin ist bei den Windows-Builds von Tesseract nicht verlässlich. Die Datei wird sofort gelöscht.
        with tempfile.TemporaryDirectory(prefix="juracore-ocr-") as ordner:
            datei = Path(ordner) / "seite.pgm"
            datei.write_bytes(bild)
            try:
                ausgabe = _ausfuehren([str(self.programm), str(datei), "stdout", "-l", SPRACHE, "tsv"])
            except (OSError, subprocess.SubprocessError) as fehler:
                raise OcrNichtVerfuegbar(f"Texterkennung fehlgeschlagen: {fehler}") from fehler
        if ausgabe.returncode != 0:
            fehler = ausgabe.stderr.decode("utf-8", "replace").strip()
            raise OcrNichtVerfuegbar(f"Texterkennung fehlgeschlagen: {fehler}")
        tsv = ausgabe.stdout.decode("utf-8", "replace")
        return (*lies_tsv(tsv), lies_woerter(tsv))


# Tesseract liest das Paragraphenzeichen oft als „8“, „8&“, „$“ oder „&“, das doppelte als „88“ oder „$$“.
_FALSCH_EINFACH = {"8", "8&", "&", "$", "8S", "S8", "%"}
_FALSCH_DOPPELT = {"88", "$$", "8§", "§8", "&&", "88&", "8&8"}
_NUMMER = re.compile(r"^\d{1,4}[a-z]?[.,;:)]?$")
_ZUSATZ = re.compile(r"^(?:Abs\.?|Nr\.?|S\.|Satz|Halbs\.?|ff?\.)$")
_GESETZ = re.compile(r"^[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*[A-Z][A-Za-z]*[.,;:)]?$")  # BGB, ZPO, BauGB, AktG
_EINHEITEN = {"Monate", "Monaten", "Monat", "Wochen", "Woche", "Tage", "Tagen", "Jahre", "Jahren", "Jahr", "Stunden",
              "Euro", "EUR", "Prozent", "Uhr", "Stück", "Seiten", "Personen", "Mal"}
_DAVOR = {"nach", "gem.", "gemäß", "gemaß", "des", "der", "dem", "den", "im", "vgl.", "i.V.m.", "iVm", "und", "bzw.",
          "oder", "sowie", "aus", "Verstoß", "gegen", "i.S.d.", "(", "Anwendung"}


def paragraphen_nachbessern(woerter: list[str]) -> list[str]:
    """Setzt in den Wörtern einer Zeile das Paragraphenzeichen wieder ein, wo die Texterkennung es verlesen hat:
    „8& 1 Leistungen“ → „§ 1 Leistungen“, „nach 8 309 Nr. 7 BGB“ → „nach § 309 Nr. 7 BGB“, „88 305“ → „§§ 305“.

    Nur in eindeutiger Umgebung: Auf das Zeichen folgt eine Nummer und darauf eine Überschrift (Zeilenanfang), ein
    „Abs.“/„Nr.“ oder ein Gesetzeskürzel; oder vor dem Zeichen steht „nach“, „gemäß“, „des“ u. ä. Eine Zahl wie
    „8 Monate“ bleibt."""
    aus = list(woerter)
    for i, w in enumerate(aus[:-1]):
        doppelt = w in _FALSCH_DOPPELT
        if not (doppelt or w in _FALSCH_EINFACH) or not _NUMMER.match(aus[i + 1]):
            continue
        danach = aus[i + 2] if i + 2 < len(aus) else ""
        bezug = bool(_ZUSATZ.match(danach) or _GESETZ.match(danach))  # „Abs.“, „Nr.“ oder ein Gesetz
        am_anfang = i == 0 and (bezug or danach[:1].isupper() and danach.rstrip(".,") not in _EINHEITEN)
        nach_wort = i > 0 and aus[i - 1] in _DAVOR
        reihe = doppelt and danach in ("bis", "und", "ff.", "f.")  # „§§ 305 bis 310“
        # „8“ allein ist meist wirklich eine Acht: nur vor „Abs.“/Gesetz oder als Überschrift am Zeilenanfang.
        if w == "8" and not (am_anfang or bezug):
            continue
        if not (am_anfang or bezug or nach_wort or reihe):
            continue
        aus[i] = "§§" if doppelt else "§"
    return aus


def lies_tsv(tsv: str) -> tuple[list[str], float | None]:
    """Setzt die Wortliste der TSV-Ausgabe wieder zu Zeilen zusammen."""
    zeilen: dict[tuple[int, int, int], list[str]] = {}
    konfidenzen: list[float] = []
    for zeile in tsv.splitlines()[1:]:
        spalten = zeile.split("\t")
        if len(spalten) < 12 or spalten[0] != "5":
            continue
        wort = spalten[11].strip()
        if not wort:
            continue
        schluessel = (int(spalten[2]), int(spalten[3]), int(spalten[4]))  # Block, Absatz, Zeile
        zeilen.setdefault(schluessel, []).append(wort)
        if float(spalten[10]) >= 0:
            konfidenzen.append(float(spalten[10]))
    text = [" ".join(paragraphen_nachbessern(woerter)) for _, woerter in sorted(zeilen.items())]
    konfidenz = round(sum(konfidenzen) / len(konfidenzen), 1) if konfidenzen else None
    return text, konfidenz


def lies_woerter(tsv: str) -> list[list]:
    """Wörter der TSV-Ausgabe mit ihrer Lage: ``[text, zeile, x, y, b, h]``.

    ``zeile`` zählt die Zeilen der Seite in Lesereihenfolge (wie bei ``lies_tsv``), ``x``, ``y``, ``b`` und ``h``
    sind Anteile von Breite und Höhe des Seitenbilds (0 bis 1), damit sie unabhängig von der Auflösung gelten.
    """
    breite = hoehe = 0
    roh: list[tuple[tuple[int, int, int], int, list]] = []
    for zeile in tsv.splitlines()[1:]:
        spalten = zeile.split("\t")
        if len(spalten) < 12:
            continue
        if spalten[0] == "1":
            breite, hoehe = int(spalten[8]), int(spalten[9])
            continue
        if spalten[0] != "5" or not spalten[11].strip():
            continue
        lage = [int(spalten[6]), int(spalten[7]), int(spalten[8]), int(spalten[9])]
        roh.append(((int(spalten[2]), int(spalten[3]), int(spalten[4])), int(spalten[5]), [spalten[11].strip(), *lage]))
    if not breite or not hoehe:
        return []
    zeilennummer = {k: i for i, k in enumerate(sorted({k for k, _, _ in roh}))}
    roh.sort(key=lambda r: (r[0], r[1]))
    # Paragraphenzeichen je Zeile wie in ``lies_tsv`` nachbessern, damit Wörter und Text übereinstimmen.
    for k in zeilennummer:
        stellen = [i for i, r in enumerate(roh) if r[0] == k]
        for i, neu in zip(stellen, paragraphen_nachbessern([roh[i][2][0] for i in stellen]), strict=True):
            roh[i][2][0] = neu
    woerter = []
    for schluessel, _, (text, x, y, b, h) in roh:
        woerter.append([text, zeilennummer[schluessel], round(x / breite, 5), round(y / hoehe, 5),
                        round(b / breite, 5), round(h / hoehe, 5)])
    return woerter


def status() -> dict:
    """Für die Oberfläche: Ist Texterkennung verfügbar, und wenn nicht, warum?"""
    try:
        t = Tesseract.finden()
        t.pruefe_sprache()
    except (OcrNichtVerfuegbar, OSError, subprocess.SubprocessError) as fehler:
        return {"verfuegbar": False, "hinweis": str(fehler)}
    return {"verfuegbar": True, "programm": str(t.programm), "version": t.version, "sprache": SPRACHE}
