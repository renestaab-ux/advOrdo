"""Basiszinssatz nach § 247 BGB.

Die Historie ist fest hinterlegt (Quelle: Deutsche Bundesbank, Stand der Tabelle unten). Neuere Sätze trägt der
Nutzer selbst ein; sie liegen in ``basiszins.json`` im Datenverzeichnis und ergänzen die Tabelle, ersetzen sie aber
nicht.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

QUELLE = "Deutsche Bundesbank, Basiszinssatz nach § 247 BGB"
STAND = "25.09.2026"

_TABELLE = [
    ("2002-07-01", "2.47"), ("2003-01-01", "1.97"), ("2003-07-01", "1.22"), ("2004-01-01", "1.14"),
    ("2004-07-01", "1.13"), ("2005-01-01", "1.21"), ("2005-07-01", "1.17"), ("2006-01-01", "1.37"),
    ("2006-07-01", "1.95"), ("2007-01-01", "2.70"), ("2007-07-01", "3.19"), ("2008-01-01", "3.32"),
    ("2008-07-01", "3.19"), ("2009-01-01", "1.62"), ("2009-07-01", "0.12"), ("2010-01-01", "0.12"),
    ("2010-07-01", "0.12"), ("2011-01-01", "0.12"), ("2011-07-01", "0.37"), ("2012-01-01", "0.12"),
    ("2012-07-01", "0.12"), ("2013-01-01", "-0.13"), ("2013-07-01", "-0.38"), ("2014-01-01", "-0.63"),
    ("2014-07-01", "-0.73"), ("2015-01-01", "-0.83"), ("2015-07-01", "-0.83"), ("2016-01-01", "-0.83"),
    ("2016-07-01", "-0.88"),
    *((f"{j}-{m}-01", "-0.88") for j in range(2017, 2023) for m in ("01", "07")),
    ("2023-01-01", "1.62"), ("2023-07-01", "3.12"), ("2024-01-01", "3.62"), ("2024-07-01", "3.37"),
    ("2025-01-01", "2.27"), ("2025-07-01", "1.27"), ("2026-01-01", "1.27"), ("2026-07-01", "1.52"),
]
HINTERLEGT: list[tuple[date, Decimal]] = [(date.fromisoformat(d), Decimal(s)) for d, s in _TABELLE]


class Basiszins:
    """Sätze nach Gültigkeitsbeginn; ``eigene`` sind vom Nutzer eingetragene neuere Sätze."""

    def __init__(self, eigene: list[tuple[date, Decimal]] | None = None):
        saetze = dict(HINTERLEGT)
        for ab, satz in eigene or []:
            saetze.setdefault(ab, satz)  # die hinterlegte Tabelle geht vor
        self.saetze = sorted(saetze.items())
        self.eigene = sorted(eigene or [])

    def satz(self, tag: date) -> Decimal:
        """Satz mit dem spätesten Gültigkeitsbeginn ≤ Tag; vor dem ersten Eintrag gilt der erste."""
        gueltig = self.saetze[0][1]
        for ab, satz in self.saetze:
            if ab > tag:
                break
            gueltig = satz
        return gueltig

    def stichtage(self) -> list[date]:
        """Die Tage, an denen sich der Basiszinssatz ändern kann (1. Januar und 1. Juli, § 247 Abs. 1 S. 2 BGB)."""
        return [ab for ab, _ in self.saetze]

    def letzter(self) -> tuple[date, Decimal]:
        return self.saetze[-1]

    @staticmethod
    def bekannt_bis(letzter: date) -> date:
        """Der letzte Tag, für den der Satz feststeht: bis zum nächsten Stichtag (1.1. bzw. 1.7.)."""
        if letzter.month < 7:
            return date(letzter.year, 6, 30)
        return date(letzter.year, 12, 31)


def lade(datei: Path) -> Basiszins:
    try:
        roh = json.loads(Path(datei).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        roh = []
    return Basiszins([(date.fromisoformat(e["ab"]), Decimal(e["satz"])) for e in roh])


def eintragen(datei: Path, ab: str, satz: str) -> dict:
    """Einen neueren Satz ergänzen (nur zum 1.1. oder 1.7., nur nach dem letzten hinterlegten)."""
    tag = date.fromisoformat(ab)
    if (tag.month, tag.day) not in ((1, 1), (7, 1)):
        raise ValueError("Der Basiszinssatz ändert sich nur zum 1. Januar und 1. Juli (§ 247 Abs. 1 S. 2 BGB).")
    if tag <= HINTERLEGT[-1][0]:
        raise ValueError(f"Für {tag:%d.%m.%Y} ist der Satz bereits hinterlegt.")
    wert = Decimal(str(satz).replace(",", "."))
    eigene = {ab_: s for ab_, s in lade(datei).eigene}
    eigene[tag] = wert
    Path(datei).parent.mkdir(parents=True, exist_ok=True)
    Path(datei).write_text(json.dumps([{"ab": d.isoformat(), "satz": str(s)} for d, s in sorted(eigene.items())],
                                      indent=2), encoding="utf-8")
    return stand(datei)


def entfernen(datei: Path, ab: str) -> dict:
    tag = date.fromisoformat(ab)
    eigene = [(d, s) for d, s in lade(datei).eigene if d != tag]
    Path(datei).write_text(json.dumps([{"ab": d.isoformat(), "satz": str(s)} for d, s in eigene], indent=2),
                           encoding="utf-8")
    return stand(datei)


def stand(datei: Path) -> dict:
    b = lade(datei)
    ab, satz = b.letzter()
    return {
        "quelle": QUELLE, "stand": STAND,
        "saetze": [{"ab": d.isoformat(), "satz": str(s), "eigen": (d, s) in b.eigene} for d, s in b.saetze],
        "aktuell": {"ab": ab.isoformat(), "satz": str(satz)},
        "bekannt_bis": Basiszins.bekannt_bis(ab).isoformat(),
    }
