"""Erkennung von Normzitaten wie "§ 280 Abs. 1 S. 2 BGB" oder "§§ 823, 826 BGB"."""

from __future__ import annotations

import re
from dataclasses import dataclass

_ABS = r"(?:Abs\.|Absatz|Absatzes|Absätze)"
_SATZ = r"(?:S\.|Satz|Satzes|Sätze)"
_NR = r"(?:Nr\.|Nummer|Nrn\.)"

# Paragraph innerhalb eines Artikels, z. B. "Art. 229 § 6 EGBGB".
_UNTERPARAGRAPH = r"(?:\s*§\s*\d+[a-z]?)?"

# Ein einzelnes Normziel: Nummer, optional Absatz, Satz, Nummer und "f."/"ff.".
_ZIEL_ROH = (
    rf"\d+[a-z]?{_UNTERPARAGRAPH}"
    rf"(?:\s*{_ABS}\s*\d+[a-z]?)?"
    rf"(?:\s*{_SATZ}\s*\d+)?"
    rf"(?:\s*{_NR}\s*\d+[a-z]?)?"
    r"(?:\s*ff?\.)?"
)
_ZIEL = (
    rf"(?P<nummer>\d+[a-z]?{_UNTERPARAGRAPH})"
    rf"(?:\s*{_ABS}\s*(?P<absatz>\d+[a-z]?))?"
    rf"(?:\s*{_SATZ}\s*(?P<satz>\d+))?"
    rf"(?:\s*{_NR}\s*(?P<nr>\d+[a-z]?))?"
)
_ZITAT = re.compile(
    r"(?P<zeichen>§§?|Art\.|Artikel)\s*"
    rf"(?P<ziele>{_ZIEL_ROH}(?:\s*(?:,|und|bis|-|–)\s*{_ZIEL_ROH})*)"
    r"\s+(?P<gesetz>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*[A-ZÄÖÜ](?:\s?[IVX]+)?)\b"
)
_EINZELZIEL = re.compile(_ZIEL)


@dataclass(frozen=True)
class Zitat:
    gesetz: str
    nummer: str
    absatz: str | None = None
    satz: int | None = None
    nr: str | None = None
    zeichen: str = "§"
    fundstelle_im_text: tuple[int, int] | None = None

    def __str__(self) -> str:
        teile = [f"{self.zeichen} {self.nummer}"]
        if self.absatz:
            teile.append(f"Abs. {self.absatz}")
        if self.satz:
            teile.append(f"S. {self.satz}")
        if self.nr:
            teile.append(f"Nr. {self.nr}")
        teile.append(self.gesetz)
        return " ".join(teile)


def finde_zitate(text: str) -> list[Zitat]:
    """Findet alle Normzitate in einem Text. "§§ 280, 281 BGB" ergibt zwei Zitate.

    Bereichsangaben ("§§ 194 bis 218 BGB") liefern nur die Grenzen, nicht jeden
    Paragraphen dazwischen.
    """
    zitate: list[Zitat] = []
    for m in _ZITAT.finditer(text):
        zeichen = "Art." if m.group("zeichen").startswith("Art") else "§"
        gesetz = m.group("gesetz")
        start = m.start("ziele")
        for z in _EINZELZIEL.finditer(m.group("ziele")):
            zitate.append(
                Zitat(
                    gesetz=gesetz,
                    nummer=re.sub(r"\s*§\s*", " § ", z.group("nummer")),
                    absatz=z.group("absatz"),
                    satz=int(z.group("satz")) if z.group("satz") else None,
                    nr=z.group("nr"),
                    zeichen=zeichen,
                    fundstelle_im_text=(start + z.start(), start + z.end()),
                )
            )
    return zitate


def parse_zitat(text: str) -> Zitat:
    """Parst genau ein Zitat, z. B. aus einer Suchanfrage."""
    gefunden = finde_zitate(text.strip())
    if not gefunden:
        raise ValueError(f"Kein Normzitat erkannt: {text!r}")
    return gefunden[0]
