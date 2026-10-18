"""Satzzerlegung für Normtexte.

Juristische Fundstellen zählen Sätze innerhalb eines Absatzes ("Abs. 1 S. 2").
Normtexte sind voller Abkürzungen ("Abs.", "Nr.", "z. B.") und Datumsangaben
("1. Januar"), an denen kein Satz endet. Aufzählungen (Nummern) gehören zu dem
Satz, der sie einleitet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Abkürzungen, nach deren Punkt kein Satz endet (kleingeschrieben, ohne Punkt).
ABKUERZUNGEN = {
    "abs",
    "abschn",
    "alt",
    "anh",
    "anl",
    "art",
    "bek",
    "bl",
    "bgbl",
    "bspw",
    "buchst",
    "bzw",
    "ca",
    "dr",
    "einschl",
    "evtl",
    "f",
    "ff",
    "gem",
    "ggf",
    "hs",
    "inkl",
    "kap",
    "lit",
    "mio",
    "mrd",
    "nr",
    "nrn",
    "prof",
    "rn",
    "rdnr",
    "s",
    "sog",
    "st",
    "tit",
    "unterabs",
    "usw",
    "var",
    "vgl",
    "v",
    "z",
    "ziff",
}
MONATE = {
    "januar",
    "februar",
    "märz",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "dezember",
}

# Kandidat für ein Satzende: Satzzeichen, optional schließende Klammer/Anführung, Leerraum.
_ENDE = re.compile(r"[.?!][)\"“”»]?\s+")


@dataclass
class Liste:
    """Aufzählung innerhalb eines Absatzes: [(Nummer, Text), …]."""

    eintraege: list[tuple[str, str]]

    def als_text(self) -> str:
        return "\n".join(
            f"{nr}. {text}" if nr.isdigit() else f"{nr}) {text}" if nr.isalnum() else f"{nr} {text}"
            for nr, text in self.eintraege
        )


@dataclass
class Satz:
    nr: int
    text: str
    nummern: list[tuple[str, str]] = field(default_factory=list)


def zerlege_in_saetze(teile: list[str | Liste], start_nr: int = 1) -> list[Satz]:
    """Zerlegt Absatzteile (Fließtext und Listen) in nummerierte Sätze."""
    saetze: list[Satz] = []
    puffer: list[str] = []
    nummern: list[tuple[str, str]] = []
    nach_liste_abgeschlossen = False

    def abschliessen() -> None:
        nonlocal puffer, nummern
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(puffer)).strip()
        if text:
            saetze.append(Satz(nr=start_nr + len(saetze), text=text, nummern=nummern))
        puffer, nummern = [], []

    for teil in teile:
        if isinstance(teil, Liste):
            puffer.append("\n" + teil.als_text() + "\n")
            nummern.extend(teil.eintraege)
            letzter = teil.eintraege[-1][1] if teil.eintraege else ""
            nach_liste_abgeschlossen = letzter.rstrip().endswith((".", "?", "!"))
            continue
        if nach_liste_abgeschlossen and _beginnt_satz(teil):
            abschliessen()
        nach_liste_abgeschlossen = False
        start = 0
        for pos in satzenden(teil):
            puffer.append(teil[start:pos])
            abschliessen()
            start = pos
        puffer.append(teil[start:])
    abschliessen()
    return saetze


def satzenden(text: str) -> list[int]:
    """Positionen, an denen im Fließtext ein neuer Satz beginnt."""
    enden = []
    for m in _ENDE.finditer(text):
        folge = text[m.end() :]
        if not folge or not _beginnt_satz(folge):
            continue
        if text[m.start()] == "." and not _echtes_punktende(text[: m.start()], folge):
            continue
        enden.append(m.end())
    return enden


def _beginnt_satz(text: str) -> bool:
    t = text.lstrip()
    return bool(t) and (t[0].isupper() or t[0] in "§(")


def _echtes_punktende(davor: str, folge: str) -> bool:
    wort = re.search(r"([\wÄÖÜäöüß]+)$", davor)
    if not wort:
        return True
    w = wort.group(1)
    if w.lower() in ABKUERZUNGEN:
        return False
    if len(w) == 1 and w.isalpha():
        return False  # "a. F.", "i. S. d."
    if w.isdigit():
        naechstes = re.match(r"\s*([\wÄÖÜäöüß]+)", folge)
        if naechstes and naechstes.group(1).lower() in MONATE:
            return False  # "1. Januar"
    return True
