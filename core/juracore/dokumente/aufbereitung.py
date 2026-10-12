"""Aus Seitenzeilen werden Absätze mit Seite und Randnummer.

Schriftsätze haben typische Eigenheiten, die das Lesen stören:

- Seitenköpfe wie "- 2 -" unterbrechen Sätze mitten im Absatz,
- Blocksatz mit Silbentrennung ("Kilome-" / "terstand"),
- Normzitate über den Zeilenumbruch ("§" am Zeilenende),
- Randnummern "(4)" am Absatzanfang, auf die sich Fundstellen beziehen.

Die Aufbereitung entfernt Seitenköpfe, fügt getrennte Wörter zusammen und
setzt Absätze über Seitengrenzen fort. Welche Seite zu welcher Textstelle
gehört, bleibt in ``Abschnitt.seitenwechsel`` erhalten.
"""

from __future__ import annotations

import re

from ..gesetze.zitate import finde_zitate
from .modell import OCR, Abschnitt, Seite

_SEITENKOPF = re.compile(r"^(?:[-–—]\s*\d{1,4}\s*[-–—]|Seite\s+\d{1,4}(?:\s*(?:von|/)\s*\d{1,4})?)$", re.IGNORECASE)
_RANDNUMMER = re.compile(r"^\((\d{1,4})\)\s")
_GLIEDERUNG = re.compile(r"^(?:[A-H]|[IVX]{1,6}|\d{1,2}|[a-z]{1,2})[.)]\s")
_BEWEIS = re.compile(r"^Beweis\s*:")
_SATZENDE = re.compile(r"[.:;!?)“”\"]$")
_WEICHER_TRENNER = ("\x02", "­")  # PDFium bzw. Unicode markieren Silbentrennung so
_KEINE_TRENNUNG = {"und", "oder", "bzw.", "sowie", "bis"}  # "Getriebe- und Motorschaden"

# Typische Verwechslungen der Texterkennung bei Paragraphenzeichen: "$ 331", "$8 437", "§8§ 286".
_OCR_SICHER = [
    (re.compile(r"\$(?=\s*[\d§$])"), "§"),  # zuerst "$" → "§", dann Doppelzeichen vereinheitlichen
    (re.compile(r"§8§|§§§|§8(?=\s*\d)"), "§§"),
]
# Mehrdeutig ("83 293, 295 BGB", "8 433 BGB"): nur ersetzen, wenn danach ein vollständiges Normzitat steht.
_OCR_UNSICHER = re.compile(r"(?<![\w.,§])(?P<z>88|83|8§|SS|S8|8|S)(?=\s+\d)")


def korrigiere_ocr(zeile: str) -> str:
    for muster, ersatz in _OCR_SICHER:
        zeile = muster.sub(ersatz, zeile)

    def ersetze(m: re.Match) -> str:
        ersatz = "§" if len(m.group("z")) == 1 else "§§"
        probe = ersatz + zeile[m.end() :]
        z = finde_zitate(probe)
        return ersatz if z and z[0].treffer and z[0].treffer[0] == 0 else m.group(0)

    return _OCR_UNSICHER.sub(ersetze, zeile)


def entferne_seitenkoepfe(seite: Seite) -> list[str | None]:
    """Entfernt Seitenköpfe und -füße wie "- 2 -" oder "Seite 2 von 5" am Seitenrand."""
    zeilen = list(seite.zeilen)
    textzeilen = [i for i, z in enumerate(zeilen) if z is not None and z.strip()]
    if not textzeilen:
        return zeilen
    # Entfernte Zeilen werden gelöscht, nicht durch eine Absatzgrenze ersetzt: Der Absatz läuft weiter.
    weg = {i for i in {textzeilen[0], textzeilen[-1]} if _SEITENKOPF.match(zeilen[i].strip())}
    if seite.quelle == OCR and (seite.nr or 1) > 1:
        # Die Texterkennung liest "- 2 -" gern als Kürzel wie "Dis" oder "-2".
        erste = zeilen[textzeilen[0]].strip()
        if len(erste) <= 4 and not _GLIEDERUNG.match(erste + " "):
            weg.add(textzeilen[0])
    return [z for i, z in enumerate(zeilen) if i not in weg]


def _uebliche_laenge(zeilen: list[str]) -> int:
    laengen = sorted(len(z) for z in zeilen if len(z) >= 15)
    if len(laengen) < 5:
        return 70
    return laengen[int(len(laengen) * 0.8)]


def _verbinde(links: str, rechts: str) -> str:
    """Fügt zwei Zeilen eines Absatzes zusammen und löst Silbentrennung auf."""
    if links.endswith(_WEICHER_TRENNER):
        return links[:-1] + rechts
    if re.search(r"[A-Za-zÄÖÜäöüß]-$", links):
        erstes_wort = rechts.split(" ", 1)[0]
        if rechts[:1].islower() and erstes_wort not in _KEINE_TRENNUNG:
            return links[:-1] + rechts  # "Kilome-" + "terstand"
        if rechts[:1].isupper():
            return links + rechts  # "Kfz-" + "Technik"
    return f"{links} {rechts}"


def _neuer_absatz(absatz: str, vorher: str, zeile: str, uebliche_laenge: int) -> bool:
    """Beginnt mit ``zeile`` ein neuer Absatz? ``vorher`` ist die letzte Zeile des laufenden ``absatz``."""
    if _RANDNUMMER.match(zeile):
        return True
    if vorher.endswith(_WEICHER_TRENNER) or vorher.endswith("-"):
        return False
    if len(vorher) < 0.7 * uebliche_laenge:
        return True  # Nur die letzte Zeile eines Absatzes ist deutlich kürzer als die übrigen.
    if _GLIEDERUNG.match(zeile) or _BEWEIS.match(zeile):
        # Beweiszeilen enden ohne Satzzeichen ("… Anlage K 6"), die nächste Überschrift beginnt trotzdem neu.
        return bool(_SATZENDE.search(vorher) or _BEWEIS.match(absatz))
    return False


def _bereinige(text: str) -> str:
    for trenner in _WEICHER_TRENNER:
        text = text.replace(trenner, "")
    return re.sub(r"\s+", " ", text).strip()


def abschnitte_bilden(seiten: list[Seite]) -> list[Abschnitt]:
    """Bildet Absätze über alle Seiten. ``None`` in den Zeilen erzwingt eine Absatzgrenze."""
    abschnitte: list[Abschnitt] = []
    puffer = ""
    letzte_zeile = ""
    laenge_vorher = 70  # übliche Zeilenlänge der Seite, auf der die letzte Zeile stand
    start_seite: int | None = None
    aktuelle_seite: int | None = None
    wechsel: list[tuple[int, int]] = []
    aus_ocr = False

    def abschliessen() -> None:
        nonlocal puffer, wechsel, letzte_zeile, aus_ocr
        text = _bereinige(puffer)
        if aus_ocr:
            # Erst nach dem Zusammenfügen korrigieren: "§" steht oft am Zeilenende, die Nummer in der nächsten Zeile.
            text = korrigiere_ocr(text)
        if text:
            # Positionen der Seitenwechsel auf den bereinigten Text umrechnen.
            umgerechnet = [(len(_bereinige(puffer[:pos])) + 1, nr) for pos, nr in wechsel]
            rn = _RANDNUMMER.match(text)
            abschnitte.append(
                Abschnitt(
                    nr=len(abschnitte) + 1,
                    text=text,
                    seite=start_seite,
                    seite_bis=aktuelle_seite if aktuelle_seite != start_seite else None,
                    rn=int(rn.group(1)) if rn else None,
                    seitenwechsel=[(min(pos, len(text)), nr) for pos, nr in umgerechnet],
                )
            )
        puffer, wechsel, letzte_zeile, aus_ocr = "", [], "", False

    for seite in seiten:
        zeilen = entferne_seitenkoepfe(seite)
        uebliche_laenge = _uebliche_laenge([z.strip() for z in zeilen if z])
        for roh in zeilen:
            if roh is None or not roh.strip():
                if roh is None:
                    abschliessen()
                continue
            zeile = roh.strip()
            if puffer and _neuer_absatz(puffer, letzte_zeile, zeile, laenge_vorher):
                abschliessen()
            if not puffer:
                puffer, start_seite = zeile, seite.nr
            else:
                if seite.nr != aktuelle_seite:
                    wechsel.append((len(puffer), seite.nr))
                puffer = _verbinde(puffer, zeile)
            aktuelle_seite = seite.nr
            aus_ocr = aus_ocr or seite.quelle == OCR
            letzte_zeile, laenge_vorher = zeile, uebliche_laenge
    abschliessen()
    return abschnitte
