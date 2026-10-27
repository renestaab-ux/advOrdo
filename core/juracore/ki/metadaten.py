"""Metadaten eines Dokuments mit dem Sprachmodell erkennen: Art, Absender, Empfänger, Gegenstand.

Ist ein Modell eingerichtet, gehen seine Vorschläge in „Details“ denen der Texterkennung
(dokumente.metadaten) vor. Jede Angabe muss mit einem wörtlichen Zitat aus dem Dokument belegt sein;
was sich im Text nicht wiederfindet, wird verworfen (Beleg vor Behauptung). Übernommen wird ein
Vorschlag wie bisher erst nach Bestätigung.
"""

from __future__ import annotations

import sqlite3

from ..dokumente import metadaten as regeln
from . import belege, speicher
from .analyse import BELEGREGEL, FASSUNG, Analyse

AUFGABE = "metadaten"

# Kopf und Schluss reichen für Absender, Empfänger und Art; der Rest des Dokuments kostet nur Zeit.
KOPF_ZEICHEN = 5000
SCHLUSS_ABSAETZE = 3

_ANGABE = {
    "type": "object",
    "properties": {
        "kennung": {"type": "string"},
        "name": {"type": "string"},
        "absatz": {"type": "integer"},
        "zitat": {"type": "string"},
    },
    "required": ["kennung", "name", "absatz", "zitat"],
}
_WERT = {
    "type": "object",
    "properties": {"wert": {"type": "string"}, "absatz": {"type": "integer"}, "zitat": {"type": "string"}},
    "required": ["wert", "absatz", "zitat"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "art": _WERT,
        "was": _WERT,
        "absender": _ANGABE,
        "empfaenger": _ANGABE,
        "vertragsparteien": {"type": "array", "items": _ANGABE},
    },
    "required": ["art", "was", "absender", "empfaenger", "vertragsparteien"],
}


def _auszug(t: belege.Text) -> list[sqlite3.Row]:
    kopf, groesse = [], 0
    for a in t.abschnitte:
        if kopf and groesse + len(a["text"]) > KOPF_ZEICHEN:
            break
        kopf.append(a)
        groesse += len(a["text"]) + 8
    schluss = [a for a in t.abschnitte[-SCHLUSS_ABSAETZE:] if a not in kopf]
    return kopf + schluss


def _beteiligte_text(akte_beteiligte: list[dict], eigene_namen: list[str]) -> str:
    zeilen = [f"B{b['id']}: {b['name']} ({b['rolle_text']})" for b in akte_beteiligte]
    eigene = ", ".join(eigene_namen) if eigene_namen else "ohne Namen hinterlegt"
    zeilen.append(f"W: wir selbst, die Kanzlei, die diese Akte führt ({eigene})")
    return "\n".join(zeilen)


def _schluessel(analyse: Analyse, eingabe: object) -> str:
    return speicher.schluessel(AUFGABE, FASSUNG[AUFGABE], type(analyse.anbieter).__name__, analyse.modell,
                               analyse.kontext, eingabe)


def _eingabe(t: belege.Text, akte_beteiligte: list[dict], eigene_namen: list[str]) -> list:
    return [belege.zeilen(_auszug(t)), _beteiligte_text(akte_beteiligte, eigene_namen)]


def gespeichert(analyse: Analyse, dokument_id: int, akte_beteiligte: list[dict],
                eigene_namen: list[str]) -> dict | None:
    """Das gespeicherte Ergebnis, ohne das Modell zu fragen; None, wenn es keines gibt."""
    t = analyse._text(dokument_id)
    alt = speicher.lies(analyse.con, _schluessel(analyse, _eingabe(t, akte_beteiligte, eigene_namen)))
    if alt is not None:
        alt["gespeichert"] = True
    return alt


def erkennen(analyse: Analyse, dokument_id: int, akte_beteiligte: list[dict], eigene_namen: list[str]) -> dict:
    t = analyse._text(dokument_id)
    return analyse._gespeichert(
        AUFGABE, _eingabe(t, akte_beteiligte, eigene_namen),
        lambda: _frage(analyse, t, akte_beteiligte, eigene_namen), analyse._akte(dokument_id), dokument_id,
    )


def _frage(analyse: Analyse, t: belege.Text, akte_beteiligte: list[dict], eigene_namen: list[str]) -> dict:
    analyse.fortschritt.melde(f"Lese Art, Absender und Empfänger von {t.dateiname}")
    antwort = analyse._frage(
        f"Dokument: {t.dateiname}\n\n"
        "Aufgabe: Bestimme für den Dokumenttitel nach dem Schema „Wer schreibt was an wen“:\n"
        f"- art: genau eine von {', '.join(regeln.ARTEN)}.\n"
        "- was: der Gegenstand in einem Wort oder kurzen Begriff, wie man ihn in einen Titel schreibt, z. B. "
        "Kündigung, Zahlungsaufforderung, Mängelrüge, Klageschrift, Klageerwiderung, Widerspruch, "
        "Berufungsbegründung, Kaufvertrag. Bei Urteil, Beschluss oder Verfügung die Art selbst.\n"
        "- absender: wer das Dokument verfasst hat (Briefkopf, Unterschrift; bei Schriftsätzen die einreichende "
        "Kanzlei, bei gerichtlichen Dokumenten das Gericht).\n"
        "- empfaenger: an wen es gerichtet ist (Anschrift, „An das …“).\n"
        "- vertragsparteien: nur bei Verträgen die Parteien, sonst eine leere Liste.\n"
        "Für absender, empfaenger und vertragsparteien: kennung ist die Kennung aus der Liste der Beteiligten "
        "(z. B. B3 oder W), wenn es einer von ihnen ist, sonst leer; name ist der Name, wie er im Dokument steht. "
        "Ist etwas nicht zu erkennen, gib leere Werte und absatz 0 an.\n\n"
        f"Beteiligte der Akte:\n{_beteiligte_text(akte_beteiligte, eigene_namen)}\n\n"
        f"{BELEGREGEL}\n\n"
        f"Text (jede Zeile ein Absatz, vorn seine Nummer; Anfang und Schluss des Dokuments):\n"
        f"{belege.zeilen(_auszug(t))}",
        SCHEMA,
    )
    return auswerten(t, antwort, akte_beteiligte)


def _fund(t: belege.Text, angabe: object) -> dict | None:
    """Fundstelle im Aufbau der Texterkennung, wenn das Zitat im Dokument steht."""
    if not isinstance(angabe, dict):
        return None
    f = Analyse._beleg(t, angabe.get("absatz"), angabe.get("zitat"))
    if f is None:
        return None
    a = f["ausschnitt"]
    return {"abschnitt": f["abschnitt"], "seite": f["seite"], "text": (a["davor"] + a["wert"] + a["danach"]).strip()}


def _person(angabe: object, akte_beteiligte: list[dict]) -> tuple[str, str] | None:
    """(Schlüssel wie in benennung.kurznamen, Kurzname) für eine Angabe des Modells."""
    if not isinstance(angabe, dict):
        return None
    kennung = str(angabe.get("kennung") or "").strip().upper()
    if kennung == "W":
        return regeln.EIGENE, ""
    if kennung.startswith("B") and kennung[1:].isdigit():
        b = next((b for b in akte_beteiligte if b["id"] == int(kennung[1:])), None)
        if b is not None:
            return str(b["id"]), ""
    name = " ".join(str(angabe.get("name") or "").split())
    if not name:
        return None
    gericht = "gericht" in name.casefold()
    kurz = regeln.kurzname({"name": name, "rolle": "gericht" if gericht else "", "art": "organisation"})
    return regeln.FREI + name, kurz


_ALLGEMEIN = {"gmbh", "mbh", "kg", "ohg", "ug", "e.v.", "rechtsanwälte", "rechtsanwalt", "rechtsanwältin", "kanzlei",
              "dr.", "prof.", "frau", "herr", "herrn", "und", "partner", "partg", "mbb", "im", "am", "an", "der", "die",
              "das", "den", "zentrales", "mahngericht", "&"}


def name_passt(name: str, text: str) -> bool:
    """Steht der Name im belegten Absatz? Bei Gerichten muss auch die Gerichtsart stimmen (nicht „Landgericht
    Stuttgart“, wenn dort „Amtsgericht Stuttgart“ steht); sonst genügt ein kennzeichnendes Wort (Nachname)."""
    text = " ".join(text.split()).casefold()
    woerter = [w.strip(",.()–-").casefold() for w in name.split()]
    woerter = [w for w in woerter if len(w) >= 3 and w not in _ALLGEMEIN]
    if not woerter:
        return False
    gerichtsart = [w for w in woerter if w.endswith("gericht") or w.endswith("gerichtshof")]
    if gerichtsart:
        return all(w in text for w in woerter)
    return any(w in text for w in woerter)


def auswerten(t: belege.Text, antwort: dict, akte_beteiligte: list[dict]) -> dict:
    """Prüft die Antwort gegen den Text und bringt sie in die Form der Vorschläge und der Benennung."""
    nach_id = {b["id"]: b for b in akte_beteiligte}
    verworfen = 0
    grund = "erkannt von der KI"

    def belegt(angabe: object) -> dict | None:
        nonlocal verworfen
        if not isinstance(angabe, dict) or not str(angabe.get("zitat") or "").strip():
            return None
        fund = _fund(t, angabe)
        if fund is None:
            verworfen += 1
        return fund

    art = None
    roh_art = antwort.get("art") if isinstance(antwort.get("art"), dict) else {}
    wert = str(roh_art.get("wert") or "").strip()
    if wert in regeln.ARTEN and (fund := belegt(roh_art)):
        art = {"wert": wert, "grund": grund, "fundstelle": fund}

    roh_was = antwort.get("was") if isinstance(antwort.get("was"), dict) else {}
    was = " ".join(str(roh_was.get("wert") or "").split())[:60] or None
    if was and not belegt(roh_was):
        was = None

    kurznamen: dict[str, str] = {}

    def person(angabe: object) -> tuple[str, dict] | None:
        nonlocal verworfen
        if (p := _person(angabe, akte_beteiligte)) is None or (fund := belegt(angabe)) is None:
            return None
        # Der Name muss zum Beleg passen; das Modell verwechselt sonst z. B. Amts- und Landgericht.
        if p[0].isdigit():
            name = nach_id[int(p[0])]["name"]
        else:
            name = p[0].removeprefix(regeln.FREI) if p[0].startswith(regeln.FREI) else ""
        if name and not name_passt(name, t.nach_nr.get(fund["abschnitt"], "")):
            verworfen += 1
            return None
        if p[1]:
            kurznamen[p[0]] = p[1]
        return p[0], fund

    absender = None
    if (p := person(antwort.get("absender"))) is not None:
        schluessel, fund = p
        if schluessel == regeln.EIGENE:
            absender = {"wert": regeln.EIGENE, "name": "Wir (eigene Seite)", "rolle_text": "", "grund": grund,
                        "fundstelle": fund}
        elif schluessel.isdigit():
            b = nach_id[int(schluessel)]
            absender = {"wert": b["id"], "name": b["name"], "rolle_text": b["rolle_text"], "grund": grund,
                        "fundstelle": fund}
        else:
            # Nicht in der Akte, z. B. das Mahngericht: als freier Absender vorgeschlagen.
            absender = regeln.frei(schluessel[len(regeln.FREI):]) | {"grund": grund, "fundstelle": fund}
    empfaenger = [p[0] for p in [person(antwort.get("empfaenger"))] if p]
    parteien = [p[0] for a in (antwort.get("vertragsparteien") or [])[:4] if (p := person(a))]

    slot = "vertrag" if art and art["wert"] == "Vertrag" else "schriftsatz" if art and art["wert"] == "Schriftsatz" \
        else "schreiben"
    return {
        "art": art,
        "absender": absender,
        "benennung": {
            "kurznamen": kurznamen,
            "empfaenger": empfaenger,
            "vertragsparteien": parteien,
            "was": {slot: was} if was else {},
        },
        "verworfen": verworfen,
    }
