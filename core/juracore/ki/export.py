"""Gespeicherte KI-Ergebnisse einer Akte ausgeben: Widersprüche, Chronologie, Zusammenfassungen, je mit Fundstellen.

Ausgegeben wird genau, was die App zeigt (``speicher.ergebnisse`` für das aktive Modell), nichts wird neu
berechnet. Jede Aussage behält ihre Fundstellen (Dokument, Seite bzw. Randnummer, auf Wunsch der Satz aus dem
Dokument). Aussagen ohne auffindbares Zitat bleiben drin und heißen „ohne Beleg“, damit der Ausdruck nicht
belastbarer wirkt als das Ergebnis in der App. Kopf mit Akte, Aktenzeichen, Parteien und Verfahren.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from .. import ausgabe
from ..aktenverwaltung import stammdaten, verfahren
from ..ausgabe import Absatz, Beleg, Bericht, Eintrag, Kopf, Tabelle, Ueberschrift
from . import speicher

TEILE = {
    "widersprueche": "Widersprüche",
    "chronologie": "Chronologie",
    "zusammenfassung_akte": "Zusammenfassung der Akte",
    "dokumente": "Zusammenfassungen der Dokumente",
}

# Wie in der App (app/src/kern.ts).
ART_TEXT = {
    "tatsache": "Inhalt", "vortrag": "Vortrag", "bestreiten": "Bestreiten", "rechtsansicht": "Rechtsansicht",
    "antrag": "Antrag", "entscheidung": "Gericht", "sonstiges": "Sonstiges", "gegenstand": "Gegenstand",
    "verlauf": "Verlauf", "streitig": "Streitig", "offen": "Offen",
}
HALTUNG_TEXT = {"behauptet": "behauptet", "bestritten": "bestreitet", "unstreitig": "unstreitig",
                "festgestellt": "festgestellt"}
EINORDNUNG_TEXT = {"im_dokument": "im selben Dokument", "innerhalb_partei": "innerhalb einer Partei",
                   "zwischen_parteien": "zwischen den Beteiligten",
                   "partei_unbekannt": "Beteiligte unbekannt (Dokumente ohne Tag)"}
EREIGNIS_ART_TEXT = {"ereignis": "Ereignis", "frist": "Frist", "dokument": "Dokument"}

HINWEIS = (
    "Erstellt mit einem Sprachmodell. Jede Aussage verweist auf ihre Fundstelle (Dokument, Seite bzw. Randnummer); "
    "die App hat geprüft, dass das Zitat dort im Originaltext steht. „ohne Beleg“ heißt: Für diese Aussage wurde "
    "kein Zitat im Dokument gefunden. Die Einschätzungen des Modells sind Hinweise, keine Bewertung; maßgeblich "
    "sind die Fundstellen."
)


def ort(f: dict) -> str:
    """„05_Klageschrift.docx, S. 3, Rn. 12 (Kläger)“, wie die Fundstelle in der App."""
    teile = []
    if f.get("seite") is not None:
        teile.append(f"S. {f['seite']}")
    if f.get("rn") is not None:
        teile.append(f"Rn. {f['rn']}")
    if not teile:
        teile.append(f"Abschn. {f.get('abschnitt', '?')}")
    parteien = f" ({', '.join(f['parteien'])})" if f.get("parteien") else ""
    return f"{f['dateiname']}, {', '.join(teile)}{parteien}"


def _stelle(f: dict) -> str:
    return ort({**f, "dateiname": "", "parteien": []}).lstrip(", ")


def _zitat(f: dict) -> str:
    return " ".join(((f.get("ausschnitt") or {}).get("wert") or "").split())


def _beleg(f: dict, zitate: bool, vorab: str | None = None) -> Beleg:
    return Beleg(ort(f), _zitat(f) if zitate else None, vorab, f.get("treffer") == "angenaehert")


def _zeit(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d.%m.%Y, %H:%M")
    except (TypeError, ValueError):
        return str(iso)


def _veraltet(ergebnis: dict, dokument_ids: set[int]) -> bool:
    damals = ergebnis.get("dokumente")
    if not isinstance(damals, list):
        return False
    return {d["dokument_id"] for d in damals} != dokument_ids


def _herkunft(ergebnis: dict, text: str, dokument_ids: set[int]) -> list[Absatz]:
    aus = [Absatz(f"Erstellt {_zeit(ergebnis.get('erstellt_am', ''))} mit {ergebnis.get('modell', '?')} · {text}",
                  leise=True)]
    if _veraltet(ergebnis, dokument_ids):
        aus.append(Absatz("Achtung: Die Dokumente der Akte haben sich seitdem geändert. Das Ergebnis berücksichtigt "
                          "den heutigen Stand nicht vollständig; in der App neu berechnen.", leise=True))
    return aus


def _anzahl(n: int, eins: str, mehr: str) -> str:
    return f"{n} {eins if n == 1 else mehr}"


def _zaehlung(z: dict) -> str:
    belegt, ohne = z["zaehlung"]["belegt"], z["zaehlung"]["ohne_beleg"]
    return _anzahl(belegt, "belegte Aussage", "belegte Aussagen") + (f", {ohne} ohne Beleg" if ohne else "")


# --- Bausteine je Teil ----------------------------------------------------------------------------------------


def _widersprueche(w: dict, zitate: bool, ids: set[int]) -> tuple[list, Tabelle]:
    liste = w["widersprueche"]
    text = (_anzahl(len(liste), "möglicher Widerspruch", "mögliche Widersprüche")
            + f" aus {w['angaben']} belegten Tatsachenangaben"
            + (f" ({_anzahl(w['verworfen'], 'Angabe', 'Angaben')} ohne auffindbares Zitat verworfen)"
               if w.get("verworfen") else ""))
    bausteine: list = [Ueberschrift(TEILE["widersprueche"]), *_herkunft(w, text, ids)]
    if not liste:
        bausteine.append(Absatz("Keine inhaltlichen Widersprüche gefunden."))
    zeilen = []
    for i, x in enumerate(liste, start=1):
        art = "Widerspruch" if x["art"] == "widerspruch" else "Spannung"
        einordnung = [EINORDNUNG_TEXT.get(e, e) for e in x.get("einordnung", [])]
        bausteine.append(Eintrag(
            x["thema"], f"{i}.", [art, *einordnung],
            [f"Einschätzung des Modells: {x['erklaerung']}"] if x.get("erklaerung") else [],
            [_beleg(a["fundstelle"], zitate, f"{a['text']} ({HALTUNG_TEXT.get(a['haltung'], a['haltung'])})")
             for a in x["angaben"]]))
        for a in x["angaben"]:
            f = a["fundstelle"]
            zeilen.append([i, x["thema"], art, ", ".join(einordnung), x.get("erklaerung", ""), a["text"],
                           HALTUNG_TEXT.get(a["haltung"], a["haltung"]), f["dateiname"], _stelle(f),
                           ", ".join(f.get("parteien", [])), *([_zitat(f)] if zitate else [])])
    bausteine.append(Absatz("Daten, Beträge und Kilometerstände gleicht der Bereich „Vergleich“ regelbasiert ab. "
                            "Das Modell kann Widersprüche übersehen oder Angaben falsch verstehen; maßgeblich sind "
                            "die Fundstellen.", leise=True))
    spalten = ["Nr.", "Thema", "Art", "Einordnung", "Einschätzung des Modells", "Angabe", "Haltung", "Dokument",
               "Fundstelle", "Beteiligte"]
    breiten = [5, 30, 12, 22, 50, 50, 12, 32, 14, 14]
    return bausteine, _tabelle("Widersprüche", spalten, zeilen, breiten, zitate)


def _chronologie(c: dict, zitate: bool, ids: set[int]) -> tuple[list, Tabelle]:
    ereignisse = c["ereignisse"]
    streitig = sum(1 for e in ereignisse if e.get("streitig"))
    ohne = sum(1 for e in ereignisse if e.get("status") == "ohne_beleg")
    text = ", ".join(t for t in (
        _anzahl(len(ereignisse), "Eintrag", "Einträge") + f" aus {c['angaben']} datierten Angaben",
        f"{streitig} streitig" if streitig else "", f"{ohne} mit Datum ohne Beleg" if ohne else "") if t)
    bausteine: list = [Ueberschrift(TEILE["chronologie"]), *_herkunft(c, text, ids)]
    if not ereignisse:
        bausteine.append(Absatz("Das Modell hat keine datierten Ereignisse geliefert."))
    zeilen = []
    for e in ereignisse:
        art = "" if e["art"] == "ereignis" else f"{EREIGNIS_ART_TEXT.get(e['art'], e['art'])}: "
        marken = (["streitig"] if e.get("streitig") else []) + (
            ["Datum ohne Beleg"] if e.get("status") == "ohne_beleg" else [])
        belege = []
        for q in e["quellen"]:
            haltung = HALTUNG_TEXT.get(q.get("haltung") or "", q.get("haltung") or "")
            belege.append(_beleg(q["fundstelle"], zitate, f"{q['text']} ({haltung})" if haltung else q["text"]))
            f = q["fundstelle"]
            zeilen.append([e["datum"], e["anzeige"], EREIGNIS_ART_TEXT.get(e["art"], e["art"]), e["ereignis"],
                           "ja" if e.get("streitig") else "", "nein" if e.get("status") == "ohne_beleg" else "ja",
                           q["text"], haltung, f["dateiname"], _stelle(f), ", ".join(f.get("parteien", [])),
                           *([_zitat(f)] if zitate else [])])
        bausteine.append(Eintrag(f"{e['anzeige']} – {art}{e['ereignis']}", "", marken, [], belege, kompakt=True))
    bausteine.append(Absatz("Die Daten stammen aus den belegten Tatsachenangaben und den Köpfen der Dokumente. "
                            "„Datum ohne Beleg“ heißt: Das Modell nennt ein Datum, das in keinem der zitierten "
                            "Absätze steht. Ereignisse ohne Datum fehlen; maßgeblich sind die Fundstellen.",
                            leise=True))
    spalten = ["Datum (sortierbar)", "Datum", "Art", "Ereignis", "Streitig", "Datum belegt", "Angabe", "Haltung",
               "Dokument", "Fundstelle", "Beteiligte"]
    breiten = [12, 16, 10, 50, 9, 9, 50, 12, 32, 14, 14]
    return bausteine, _tabelle("Chronologie", spalten, zeilen, breiten, zitate)


def _aussagen(z: dict, zitate: bool) -> tuple[list, list[list]]:
    bausteine: list = []
    zeilen = []
    if not z["aussagen"]:
        bausteine.append(Absatz("Das Modell hat keine Aussagen geliefert."))
    for i, a in enumerate(z["aussagen"], start=1):
        art = ART_TEXT.get(a["art"], a["art"])
        ohne = a["status"] == "ohne_beleg"
        bausteine.append(Eintrag(f"{art}: {a['text']}", f"{i}.", ["ohne Beleg"] if ohne else [], [],
                                 [_beleg(f, zitate) for f in a["fundstellen"]], kompakt=True))
        for f in a["fundstellen"] or [None]:
            zeilen.append([i, art, a["text"], "nein" if ohne else "ja",
                           *(([f["dateiname"], _stelle(f), ", ".join(f.get("parteien", []))]
                              + ([_zitat(f)] if zitate else [])) if f else [])])
    return bausteine, zeilen


_AUSSAGE_SPALTEN = ["Nr.", "Art", "Aussage", "Belegt", "Dokument", "Fundstelle", "Beteiligte"]
_AUSSAGE_BREITEN = [5, 14, 70, 8, 32, 14, 14]


def _zusammenfassung_akte(z: dict, zitate: bool, ids: set[int]) -> tuple[list, Tabelle]:
    bausteine, zeilen = _aussagen(z, zitate)
    return ([Ueberschrift(TEILE["zusammenfassung_akte"]), *_herkunft(z, _zaehlung(z), ids), *bausteine],
            _tabelle("Zusammenfassung Akte", _AUSSAGE_SPALTEN, zeilen, _AUSSAGE_BREITEN, zitate))


def _dokumente(con: sqlite3.Connection, akte_id: int, je_dokument: dict, zitate: bool) -> tuple[list, Tabelle]:
    bausteine: list = [Ueberschrift(TEILE["dokumente"])]
    zeilen = []
    for d in con.execute("SELECT id, dateiname FROM dokument WHERE akte_id = ? ORDER BY COALESCE(herkunft, ''), "
                         "dateiname", (akte_id,)):
        z = je_dokument.get(str(d["id"]))
        if z is None:
            continue
        teil, z_zeilen = _aussagen(z, zitate)
        bausteine += [Ueberschrift(d["dateiname"], 2), *_herkunft(z, _zaehlung(z), set()), *teil]
        zeilen += [[d["dateiname"], *zeile] for zeile in z_zeilen]
    return bausteine, _tabelle("Zusammenfassungen Dokumente", ["Zusammengefasstes Dokument", *_AUSSAGE_SPALTEN],
                               zeilen, [32, *_AUSSAGE_BREITEN], zitate)


def _tabelle(name: str, spalten: list[str], zeilen: list[list], breiten: list[int], zitate: bool) -> Tabelle:
    if zitate:
        return Tabelle(name, [*spalten, "Zitat aus dem Dokument"], zeilen, [*breiten, 70])
    return Tabelle(name, spalten, zeilen, breiten)


# --- Bericht ------------------------------------------------------------------------------------------------------


def aktenkopf(con: sqlite3.Connection, akte_id: int, modelle: list[str], jetzt: datetime) -> Kopf:
    """Kopf eines Berichts: Akte, Aktenzeichen, Gegenstand, Parteien, Verfahren, Ausgabezeit."""
    a = stammdaten.stammdaten(con, akte_id)
    zeilen = [("Akte", a["name"])]
    if a.get("aktenzeichen"):
        zeilen.append(("Aktenzeichen", a["aktenzeichen"]))
    if a.get("gegenstand"):
        zeilen.append(("Gegenstand", a["gegenstand"]))
    for rolle, titel in (("mandant", "Mandant"), ("gegner", "Gegner")):
        namen = [b["name"] for b in a["beteiligte"] if b["rolle"] == rolle and b["name"]]
        if namen:
            zeilen.append((titel, "; ".join(namen)))
    aktuell = verfahren.aktuelles(verfahren.liste(con, akte_id))
    if aktuell:
        zeilen.append(("Verfahren", aktuell["bezeichnung"]))
    zeilen.append(("Dokumente", str(a["dokumente"])))
    if modelle:
        zeilen.append(("Sprachmodell", ", ".join(modelle)))
    zeilen.append(("Ausgegeben am", jetzt.strftime("%d.%m.%Y, %H:%M")))
    return Kopf(zeilen)


def bericht(con: sqlite3.Connection, akte_id: int, modell: str, teile: list[str] | None = None, zitate: bool = True,
            jetzt: datetime | None = None) -> Bericht:
    """Bericht aus den gespeicherten Ergebnissen; ``teile`` aus ``TEILE``, ohne Angabe alle vorhandenen."""
    unbekannt = [t for t in teile or [] if t not in TEILE]
    if unbekannt:
        raise ValueError(f"Unbekannter Teil: {', '.join(unbekannt)}")
    gewaehlt = [t for t in TEILE if teile is None or t in teile]
    ergebnisse = speicher.ergebnisse(con, akte_id, modell)
    vorhanden = [t for t in gewaehlt if (ergebnisse[t] if t != "dokumente" else ergebnisse["dokumente"])]
    if not vorhanden:
        raise ValueError("Für diese Auswahl gibt es mit dem aktiven Sprachmodell noch keine Ergebnisse.")
    jetzt = jetzt or datetime.now().astimezone()
    ids = {z["id"] for z in con.execute("SELECT id FROM dokument WHERE akte_id = ?", (akte_id,))}
    # Der Name, mit dem das Ergebnis entstand (bei LM Studio z. B. mit Anbieterpräfix), nicht die Einstellung.
    teile_ergebnisse = [ergebnisse[t] for t in vorhanden if t != "dokumente"]
    if "dokumente" in vorhanden:
        teile_ergebnisse += list(ergebnisse["dokumente"].values())
    modelle = list(dict.fromkeys(e.get("modell") or modell for e in teile_ergebnisse))
    kopf = aktenkopf(con, akte_id, [m for m in modelle if m], jetzt)
    b = Bericht(f"KI-Auswertung: {kopf.zeilen[0][1]}", [kopf, Absatz(HINWEIS, leise=True)])
    for t in vorhanden:
        if t == "widersprueche":
            bausteine, tabelle = _widersprueche(ergebnisse[t], zitate, ids)
        elif t == "chronologie":
            bausteine, tabelle = _chronologie(ergebnisse[t], zitate, ids)
        elif t == "zusammenfassung_akte":
            bausteine, tabelle = _zusammenfassung_akte(ergebnisse[t], zitate, ids)
        else:
            bausteine, tabelle = _dokumente(con, akte_id, ergebnisse["dokumente"], zitate)
        b.bausteine += bausteine
        b.tabellen.append(tabelle)
    return b


def dateiname(con: sqlite3.Connection, akte_id: int, jetzt: datetime | None = None,
              vorne: str = "KI-Auswertung") -> str:
    """Vorschlag ohne Endung, z. B. „KI-Auswertung Brückner gg. Autohaus 2026-10-23“."""
    a = stammdaten.stammdaten(con, akte_id)
    name = a.get("aktenzeichen") or a["name"]
    name = re.sub(r"\s*\./\.\s*", " gg. ", f"{vorne} {name}")  # „./.“ darf nicht in einen Dateinamen
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", name)
    return " ".join(name.split())[:120] + f" {(jetzt or datetime.now()).strftime('%Y-%m-%d')}"


def schreiben(con: sqlite3.Connection, akte_id: int, modell: str, format: str, pfad: str | Path,
              teile: list[str] | None = None, zitate: bool = True) -> dict:
    if format not in ausgabe.FORMATE:
        raise ValueError(f"Unbekanntes Format: {format!r}")
    ziel = Path(pfad)
    if ziel.suffix.lower() != f".{format}":
        ziel = ziel.with_name(ziel.name + f".{format}")
    daten = ausgabe.schreiben(bericht(con, akte_id, modell, teile, zitate), format)
    ziel.write_bytes(daten)
    return {"pfad": str(ziel), "format": format, "groesse": len(daten)}


def druckansicht(con: sqlite3.Connection, akte_id: int, modell: str, teile: list[str] | None = None,
                 zitate: bool = True) -> dict:
    """HTML für die Druckansicht der App; der Stil gilt nur innerhalb des Berichts."""
    from ..ausgabe import html

    b = bericht(con, akte_id, modell, teile, zitate)
    return {"titel": b.titel, "html": html.fragment(b), "stil": html.STIL}
