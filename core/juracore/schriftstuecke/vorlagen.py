"""Eigene Vorlagen der Arbeitsumgebung und das Erzeugen eines Schriftstücks aus einer Vorlage.

Eigene Vorlagen sind Word-Dateien (.docx, .dotx) mit Platzhaltern. JuraBox legt eine Kopie im Ordner ``vorlagen``
der Arbeitsumgebung ab; die Originaldatei bleibt, wo sie ist. Eine Vorlage heißt wie ihre Datei.

Ein erzeugtes Schriftstück kommt als neues Dokument in die Akte (Herkunft „Von JuraBox erzeugt“) und lässt sich
dort über „Bearbeiten“ in Word fertig schreiben, oder es wird nur unter einem gewählten Pfad gespeichert.
"""

from __future__ import annotations

import re
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from ..dokumente import akte as akten
from . import fuellen, grundvorlagen, platzhalter

ENDUNGEN = (".docx", ".dotx")
HERKUNFT = "Von JuraBox erzeugt"
GROESSTE = 20 * 1024 * 1024


def _ordner(umgebung: Path) -> Path:
    return Path(umgebung) / "vorlagen"


def _eigene_datei(umgebung: Path, datei: str) -> Path:
    pfad = _ordner(umgebung) / Path(datei).name
    if pfad.suffix.lower() not in ENDUNGEN or not pfad.is_file():
        raise LookupError(f"Die Vorlage „{datei}“ gibt es nicht (mehr).")
    return pfad


def _pruefung(daten: bytes) -> dict:
    gefunden = fuellen.platzhalter_finden(daten)
    return {"platzhalter": [platzhalter.bekannt(p) or p for p in gefunden],
            "unbekannt": [p for p in gefunden if platzhalter.bekannt(p) is None]}


def liste(umgebung: Path) -> dict:
    """Grundvorlagen und eigene Vorlagen; bei eigenen auch, welche Platzhalter darin stehen."""
    eigene = []
    ordner = _ordner(umgebung)
    for p in sorted(ordner.glob("*"), key=lambda p: (p.stem.casefold(), p.suffix)) if ordner.is_dir() else []:
        if p.suffix.lower() not in ENDUNGEN or p.name.startswith("~$"):
            continue
        eintrag = {"id": f"eigen:{p.name}", "datei": p.name, "titel": p.stem, "art": "eigen"}
        try:
            eintrag |= _pruefung(p.read_bytes())
        except (OSError, ValueError, UnicodeDecodeError) as fehler:
            eintrag |= {"platzhalter": [], "unbekannt": [], "fehler": str(fehler)}
        eigene.append(eintrag)
    grund = [{"id": f"grund:{k}", "titel": v["titel"], "beschreibung": v["beschreibung"], "art": v["art"],
              "platzhalter": _pruefung(grundvorlagen.erzeugen(k))["platzhalter"], "unbekannt": []}
             for k, v in grundvorlagen.GRUNDVORLAGEN.items()]
    return {"grund": grund, "eigene": eigene, "ordner": str(ordner), "logo_hinweis": grundvorlagen.logo_hinweis(
        umgebung)}


def hinzufuegen(umgebung: Path, pfad: str | Path) -> dict:
    quelle = Path(pfad)
    if quelle.suffix.lower() not in ENDUNGEN:
        raise ValueError("Bitte eine Word-Datei (.docx oder .dotx) wählen.")
    if quelle.stat().st_size > GROESSTE:
        raise ValueError("Die Vorlage ist größer als 20 MB.")
    daten = quelle.read_bytes()
    pruefung = _pruefung(daten)  # wirft, wenn es keine Word-Datei ist
    ordner = _ordner(umgebung)
    ordner.mkdir(parents=True, exist_ok=True)
    ziel, n = ordner / quelle.name, 2
    while ziel.exists():
        ziel = ordner / f"{quelle.stem} ({n}){quelle.suffix}"
        n += 1
    ziel.write_bytes(daten)
    return liste(umgebung) | {"neu": ziel.name, "pruefung": pruefung}


def entfernen(umgebung: Path, datei: str) -> dict:
    _eigene_datei(umgebung, datei).unlink()
    return liste(umgebung)


def pfad(umgebung: Path, datei: str) -> Path:
    """Pfad einer eigenen Vorlage, etwa um sie in Word zu bearbeiten."""
    return _eigene_datei(umgebung, datei)


def _vorlage(umgebung: Path, vorlage: str) -> tuple[bytes, str, str]:
    """(Inhalt, Titel, Art) einer Vorlage-ID „grund:brief“ oder „eigen:Datei.docx“."""
    quelle, _, name = vorlage.partition(":")
    if quelle == "grund":
        if name not in grundvorlagen.GRUNDVORLAGEN:
            raise LookupError(f"Unbekannte Grundvorlage: {name!r}")
        g = grundvorlagen.GRUNDVORLAGEN[name]
        return grundvorlagen.erzeugen(name, grundvorlagen.logo_lesen(umgebung)), g["titel"], g["art"]
    if quelle == "eigen":
        p = _eigene_datei(umgebung, name)
        return p.read_bytes(), p.stem, "eigen"
    raise ValueError(f"Unbekannte Vorlage: {vorlage!r}")


def grundvorlage_speichern(umgebung: Path, vorlage: str, ziel: str | Path) -> dict:
    """Die Grundvorlage mit Platzhaltern (ohne Werte) als Ausgangspunkt für eine eigene Vorlage."""
    daten, _, _ = _vorlage(umgebung, vorlage)
    Path(ziel).write_bytes(daten)
    return {"pfad": str(ziel)}


def vorschau(con: sqlite3.Connection, umgebung: Path, akte_id: int, vorlage: str, empfaenger_id: int | None = None,
             verfahren_id: int | None = None, heute: date | None = None) -> dict:
    """Die Platzhalter der Vorlage mit ihren Werten in dieser Akte; fehlende mit dem Ort, wo man sie einträgt."""
    daten, _, _ = _vorlage(umgebung, vorlage)
    w = platzhalter.werte(con, akte_id, empfaenger_id, verfahren_id, heute)
    zeilen = []
    for p in fuellen.platzhalter_finden(daten):
        name = platzhalter.bekannt(p)
        wert = w["werte"].get(name, "") if name else None
        zeilen.append({"platzhalter": name or p, "wert": wert, "bekannt": name is not None,
                       "wo": platzhalter.wo(name) if name and not wert else ""})
    return {"zeilen": zeilen, "hinweise": w["hinweise"] + ([h] if (h := grundvorlagen.logo_hinweis(umgebung))
                                                          and vorlage.startswith("grund:") else [])}


_UNZULAESSIG = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def dateiname(titel: str, w: dict, heute: date) -> str:
    """„2026-10-27 Brief an Autohaus Rehnfeld GmbH.docx“; Zeichen, die Windows nicht erlaubt, fallen weg."""
    if w.get("Empfänger.Name") and titel == "Brief":
        titel = f"Brief an {w['Empfänger.Name']}"
    elif w.get("Mandant.Name") and titel == "Vergütungsvereinbarung":
        titel = f"Vergütungsvereinbarung {w['Mandant.Name']}"
    elif w.get("Gericht.Aktenzeichen") and titel.startswith("Schriftsatz"):
        titel = f"Schriftsatz {w['Gericht.Aktenzeichen']}"
    name = _UNZULAESSIG.sub(" ", f"{heute.isoformat()} {titel}").replace("./.", "gg.")
    return " ".join(name.split())[:120].rstrip(". ") + ".docx"


def erzeugen(con: sqlite3.Connection, wissen: sqlite3.Connection, umgebung: Path, ablage: Path, akte_id: int,
             vorlage: str, empfaenger_id: int | None = None, verfahren_id: int | None = None,
             pfad: str | Path | None = None, in_akte: bool = True, heute: date | None = None) -> dict:
    """Füllt die Vorlage mit den Angaben der Akte; legt das Ergebnis in die Akte und/oder unter ``pfad`` ab."""
    heute = heute or date.today()
    daten, titel, _ = _vorlage(umgebung, vorlage)
    w = platzhalter.werte(con, akte_id, empfaenger_id, verfahren_id, heute)
    werte = w["werte"]
    leer: list[str] = []
    unbekannt: list[str] = []

    def ersatz(roh: str) -> str | None:
        name = platzhalter.bekannt(roh)
        if name is None:
            unbekannt.append(" ".join(roh.split()))
            return None  # bleibt stehen, damit man den Tippfehler in Word sieht
        if not werte.get(name) and name not in platzhalter.OPTIONAL:
            leer.append(name)
        return werte.get(name, "")

    ergebnis = fuellen.fuellen(daten, ersatz)
    name = dateiname(titel, werte, heute)
    antwort: dict = {"dateiname": name, "leer": list(dict.fromkeys(leer)),
                     "unbekannt": list(dict.fromkeys(unbekannt)), "hinweise": w["hinweise"]}
    if pfad:
        Path(pfad).write_bytes(ergebnis)
        antwort["pfad"] = str(pfad)
    if in_akte:
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / name
            datei.write_bytes(ergebnis)
            eingelesen = akten.importiere(con, wissen, akte_id, datei, ablage, ocr=False, herkunft=HERKUNFT)
        antwort["dokument_id"] = eingelesen["dokument_id"]
        antwort["neu"] = eingelesen["neu"]
    return antwort


def ordner_anlegen(umgebung: Path) -> Path:
    ordner = _ordner(umgebung)
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner

