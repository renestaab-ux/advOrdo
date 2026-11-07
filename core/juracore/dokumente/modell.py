"""Datenmodell eines eingelesenen Dokuments.

Ein Dokument besteht aus *Seiten* (Rohtext je Seite, wie er aus der Datei oder
der Texterkennung kam) und *Abschnitten* (aufbereitete Absätze mit Seite und
Randnummer). Abschnitte sind die Einheit für Fundstellen: Jede Aussage über das
Dokument verweist auf einen Abschnitt und darin auf eine Zeichenposition.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Herkunft des Textes einer Seite.
TEXTEBENE = "textebene"  # PDF mit eingebettetem Text
OCR = "ocr"  # Texterkennung auf dem Seitenbild
DATEI = "datei"  # DOCX, TXT, Markdown: Text direkt aus der Datei
LEER = "leer"  # kein Text (Bildseite ohne verfügbare Texterkennung)


@dataclass
class Seite:
    nr: int | None  # 1-basiert; None, wenn die Datei keine Seiten kennt (DOCX ohne Umbrüche, TXT)
    quelle: str
    zeilen: list[str | None]  # None markiert eine Absatzgrenze (Leerzeile, Textblock)
    konfidenz: float | None = None  # mittlere OCR-Konfidenz 0–100
    woerter: list[list] | None = None  # nur OCR: [text, zeile, x, y, b, h], Lage als Anteil der Seite


@dataclass
class Abschnitt:
    nr: int  # laufende Nummer im Dokument, 1-basiert
    text: str
    seite: int | None = None
    seite_bis: int | None = None
    rn: int | None = None  # Randnummer, z. B. "(4)" am Absatzanfang
    art: str = "absatz"  # "absatz", "tabelle", "fussnote", "kopfzeile"
    seitenwechsel: list[tuple[int, int]] = field(default_factory=list)  # [(Zeichenposition, Seite)]


@dataclass
class Dokument:
    format: str  # "pdf", "docx", "txt", "md"
    seiten: list[Seite]
    abschnitte: list[Abschnitt]
    hinweise: list[str] = field(default_factory=list)

    @property
    def lesart(self) -> str:
        """Woher der Text stammt: "textebene", "ocr", "gemischt", "datei" oder "leer"."""
        quellen = {s.quelle for s in self.seiten if s.quelle != LEER}
        if not quellen:
            return LEER
        return quellen.pop() if len(quellen) == 1 else "gemischt"

    @property
    def ocr_konfidenz(self) -> float | None:
        werte = [s.konfidenz for s in self.seiten if s.quelle == OCR and s.konfidenz is not None]
        return round(sum(werte) / len(werte), 1) if werte else None
