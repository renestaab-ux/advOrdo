"""Berichte als Datei ausgeben: Markdown, Text, Word, PDF, Excel und HTML zum Drucken.

Ein Bericht ist eine einfache Folge von Bausteinen (Titel, Kopf, Überschrift, Absatz, Eintrag mit Belegen) und
daneben eine Reihe von Tabellen für Excel. Wer etwas ausgibt (z. B. ``juracore.ki.export``), baut den Bericht;
die Schreiber hier kennen nur diese Bausteine. Word, Excel und PDF entstehen ohne Zusatzbibliothek, damit der Kern
auf Windows, macOS und Linux ohne weitere Pakete läuft.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Beleg:
    """Eine Fundstelle: wo (Dokument, Seite, Rn.) und, wenn gewünscht, der Satz aus dem Dokument."""

    ort: str
    zitat: str | None = None
    vorab: str | None = None  # z. B. die Angabe, die belegt wird („Fahrzeug am 27.06.2025 besichtigt (behauptet)“)
    angenaehert: bool = False


@dataclass
class Eintrag:
    titel: str
    nummer: str = ""
    marken: list[str] = field(default_factory=list)  # z. B. „ohne Beleg“, „streitig“
    zeilen: list[str] = field(default_factory=list)
    belege: list[Beleg] = field(default_factory=list)
    kompakt: bool = False  # Listenpunkt statt eigener Überschrift
    dringend: bool = False  # hervorgehoben (fett, rot), z. B. eine Frist kurz vor dem Ablauf


@dataclass
class Ueberschrift:
    text: str
    ebene: int = 1


@dataclass
class Absatz:
    text: str
    leise: bool = False  # Herkunft, Hinweis: kleiner und grau


@dataclass
class Kopf:
    zeilen: list[tuple[str, str]]


@dataclass
class Tabelle:
    name: str
    spalten: list[str]
    zeilen: list[list[str | int | None]]
    breiten: list[int] = field(default_factory=list)  # Zeichen je Spalte


@dataclass
class Bericht:
    titel: str
    bausteine: list[Ueberschrift | Absatz | Kopf | Eintrag] = field(default_factory=list)
    tabellen: list[Tabelle] = field(default_factory=list)


FORMATE = {
    "docx": "Word",
    "pdf": "PDF",
    "xlsx": "Excel",
    "md": "Markdown",
    "txt": "Text",
}


def marken_text(e: Eintrag) -> str:
    return f" [{', '.join(e.marken)}]" if e.marken else ""


def beleg_text(b: Beleg) -> str:
    """„Angabe – Dokument, S. 3: „Zitat““, wie in Text und Markdown."""
    teile = [b.vorab] if b.vorab else []
    ort = b.ort + (" (Zitat angenähert)" if b.angenaehert else "")
    if b.zitat:
        ort += f": „{b.zitat}“"
    teile.append(ort)
    return " – ".join(teile)


def schreiben(bericht: Bericht, art: str) -> bytes:
    """Der Bericht im gewünschten Format als Bytes."""
    from . import docx, html, pdf, text, xlsx

    if art == "md":
        return text.markdown(bericht).encode("utf-8")
    if art == "txt":
        return text.klartext(bericht).encode("utf-8")
    if art == "docx":
        return docx.schreiben(bericht)
    if art == "pdf":
        return pdf.schreiben(bericht)
    if art == "xlsx":
        return xlsx.schreiben(bericht)
    if art == "html":
        return html.seite(bericht).encode("utf-8")
    raise ValueError(f"Unbekanntes Format: {art!r}")
