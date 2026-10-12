"""Erkennung von Normzitaten wie "§ 280 Abs. 1 S. 2 BGB" oder "§§ 823, 826 BGB".

Unterstützt werden auch die in Schriftsätzen üblichen Kurzformen:

- Aufzählungen: "§§ 437 Nr. 2, 440, 323 Abs. 1, 346 Abs. 1 BGB"
- weitere Absätze derselben Norm: "§ 346 Abs. 1, Abs. 2 Satz 1 Nr. 1 BGB"
- abgekürzte Absatz- oder Satzfolgen: "§§ 280 Abs. 1, 2, 286 BGB" (Abs. 2), "§ 709 Satz 1 und 2 ZPO"
- Verkettung über "i.V.m.", "und", ",": "§ 280 Abs. 1 i.V.m. § 241 Abs. 2 BGB"
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ABS = r"(?:Abs\.|Absatz|Absatzes|Absätze)"
_SATZ = r"(?:S\.|Satz|Satzes|Sätze)"
_NR = r"(?:Nr\.|Nummer|Nrn\.)"

# Paragraph innerhalb eines Artikels, z. B. "Art. 229 § 6 EGBGB".
_UNTERPARAGRAPH = r"(?:\s*§\s*\d+[a-z]?)?"

# Ein Normziel: Nummer, optional Absatz, Satz, Nummer und "f."/"ff.".
_ZIEL_ROH = (
    rf"\d+[a-z]?{_UNTERPARAGRAPH}"
    rf"(?:\s*{_ABS}\s*\d+[a-z]?)?"
    rf"(?:\s*{_SATZ}\s*\d+)?"
    rf"(?:\s*{_NR}\s*\d+[a-z]?)?"
    r"(?:\s*ff?\.)?"
)
# Eine weitere Stelle derselben Norm ohne Paragraphennummer: ", Abs. 2 Satz 1 Nr. 1".
_TEIL_ROH = (
    rf"(?:{_ABS}\s*\d+[a-z]?|{_SATZ}\s*\d+|{_NR}\s*\d+[a-z]?)"
    rf"(?:\s*{_SATZ}\s*\d+)?"
    rf"(?:\s*{_NR}\s*\d+[a-z]?)?"
)
_TRENNER = r"\s*(?:,|und|bis|-|–)\s*"
_GRUPPE = re.compile(
    r"(?P<zeichen>§§?|Art\.|Artikel)\s*"
    rf"(?P<ziele>{_ZIEL_ROH}(?:{_TRENNER}(?:{_ZIEL_ROH}|{_TEIL_ROH}))*)"
)
_ELEMENT = re.compile(
    rf"(?P<nummer>\d+[a-z]?{_UNTERPARAGRAPH})?"
    rf"(?:\s*{_ABS}\s*(?P<absatz>\d+[a-z]?))?"
    rf"(?:\s*{_SATZ}\s*(?P<satz>\d+))?"
    rf"(?:\s*{_NR}\s*(?P<nr>\d+[a-z]?))?"
)
_GESETZ = re.compile(r"\s*(?P<gesetz>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*[A-ZÄÖÜ](?:\s?[IVX]+)?)\b")
# Zwischen zwei Paragraphengruppen, die sich ein Gesetz teilen: "§ 280 Abs. 1 i.V.m. § 241 Abs. 2 BGB".
_VERBINDER = re.compile(
    r"\s*(?:,|;|und|oder|sowie|bzw\.|i\.\s?V\.\s?m\.|iVm|in Verbindung mit)\s*(?=§|Art\.|Artikel)"
)
# Großgeschriebene Kürzel nach einer Nummer, die keine Gesetze sind.
_KEIN_GESETZ = {"GmbH", "AG", "KG", "OHG", "UG", "AGB", "EUR", "DM", "BGH", "OLG", "LG", "EU"}
# Abgekürzte Folge ("Abs. 1, 2"): kleine Zahl unter der Paragraphennummer gehört zur Norm davor.
_MAX_KURZFOLGE = 20


@dataclass(frozen=True)
class Zitat:
    gesetz: str
    nummer: str
    absatz: str | None = None
    satz: int | None = None
    nr: str | None = None
    zeichen: str = "§"
    fundstelle_im_text: tuple[int, int] | None = None
    # Ganzes Zitat im Text ("§§ 280 Abs. 1, 281 BGB"); bei Aufzählungen für alle Ziele gleich.
    treffer: tuple[int, int] | None = None

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


def _gesetze_zuordnen(text: str, gruppen: list[re.Match]) -> list[tuple[str | None, int]]:
    """Gesetz und Trefferende je Gruppe; eine Gruppe ohne eigenes Gesetz übernimmt das der folgenden."""
    ergebnis: list[tuple[str | None, int]] = [(None, g.end()) for g in gruppen]
    for i in range(len(gruppen) - 1, -1, -1):
        ende = gruppen[i].end()
        g = _GESETZ.match(text, ende)
        if g and g.group("gesetz") not in _KEIN_GESETZ:
            ergebnis[i] = (g.group("gesetz"), g.end())
            continue
        v = _VERBINDER.match(text, ende)
        if v and i + 1 < len(gruppen) and gruppen[i + 1].start() == v.end():
            ergebnis[i] = (ergebnis[i + 1][0], ende)
    return ergebnis


def _elemente(ziele: str, versatz: int) -> list[tuple[dict, tuple[int, int]]]:
    """Zerlegt "280 Abs. 1, 2, 286" in Einzelziele und ergänzt verkürzte Angaben aus dem Vorgänger."""
    ergebnis: list[tuple[dict, tuple[int, int]]] = []
    vorher: dict | None = None
    for m in _ELEMENT.finditer(ziele):
        if not m.group(0).strip():
            continue
        teil = {k: m.group(k) for k in ("nummer", "absatz", "satz", "nr")}
        if vorher is not None:
            if teil["nummer"] is None:
                # ", Abs. 2 Satz 1": dieselbe Norm, höhere Ebenen vom Vorgänger übernehmen.
                teil["nummer"] = vorher["nummer"]
                for ebene in ("absatz", "satz", "nr"):
                    if teil[ebene] is not None:
                        break
                    teil[ebene] = vorher[ebene]
            elif not any(teil[e] for e in ("absatz", "satz", "nr")) and _ist_kurzfolge(teil["nummer"], vorher):
                # "§§ 280 Abs. 1, 2": die 2 ist Abs. 2 von § 280, kein § 2.
                tiefste = next(e for e in ("nr", "satz", "absatz") if vorher[e])
                neu = {**vorher, tiefste: teil["nummer"]}
                for e in ("absatz", "satz", "nr")[("absatz", "satz", "nr").index(tiefste) + 1 :]:
                    neu[e] = None
                teil = neu
        ergebnis.append((teil, (versatz + m.start(), versatz + m.end())))
        vorher = teil
    return ergebnis


def _ist_kurzfolge(nummer: str, vorher: dict) -> bool:
    if not any(vorher[e] for e in ("absatz", "satz", "nr")) or not nummer.isdigit():
        return False
    norm = re.match(r"\d+", vorher["nummer"])
    return int(nummer) <= _MAX_KURZFOLGE and norm is not None and int(nummer) < int(norm.group())


def finde_zitate(text: str) -> list[Zitat]:
    """Findet alle Normzitate in einem Text. "§§ 280, 281 BGB" ergibt zwei Zitate.

    Bereichsangaben ("§§ 194 bis 218 BGB") liefern nur die Grenzen, nicht jeden
    Paragraphen dazwischen. Paragraphen ohne erkennbares Gesetz ("§ 3 des Vertrags")
    werden übergangen.
    """
    gruppen = list(_GRUPPE.finditer(text))
    zitate: list[Zitat] = []
    for m, (gesetz, ende) in zip(gruppen, _gesetze_zuordnen(text, gruppen), strict=True):
        if gesetz is None:
            continue
        zeichen = "Art." if m.group("zeichen").startswith("Art") else "§"
        for teil, spanne in _elemente(m.group("ziele"), m.start("ziele")):
            zitate.append(
                Zitat(
                    gesetz=gesetz,
                    nummer=re.sub(r"\s*§\s*", " § ", teil["nummer"]),
                    absatz=teil["absatz"],
                    satz=int(teil["satz"]) if teil["satz"] else None,
                    nr=teil["nr"],
                    zeichen=zeichen,
                    fundstelle_im_text=spanne,
                    treffer=(m.start(), ende),
                )
            )
    return zitate


def parse_zitat(text: str) -> Zitat:
    """Parst genau ein Zitat, z. B. aus einer Suchanfrage."""
    gefunden = finde_zitate(text.strip())
    if not gefunden:
        raise ValueError(f"Kein Normzitat erkannt: {text!r}")
    return gefunden[0]
