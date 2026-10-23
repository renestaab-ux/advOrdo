"""Chronologie einer Akte: datierte Ereignisse, Fristen und Dokumente, jedes mit Fundstelle.

Grundlage sind die geprüften Tatsachenangaben je Dokument (dieselben wie bei der
Widerspruchssuche, sie werden nicht neu erhoben) und der Kopf jedes Dokuments.
Das Modell ordnet die datierten Angaben zu Ereignissen und nennt je Ereignis ein
Datum. Die App übernimmt ein Ereignis nur mit gültiger Kennung und prüft, ob das
genannte Datum in einem der zitierten Absätze tatsächlich steht; sonst heißt das
Ereignis „Datum ohne Beleg“. Das Datum eines Dokuments wird nur übernommen, wenn
es im Kopf des Dokuments steht, und verweist genau auf diese Stelle.
"""

from __future__ import annotations

from collections.abc import Callable

from ..abgleich.angaben import DATUM, MONAT, Wert, anzeige, finde_werte
from . import belege

ARTEN = ("ereignis", "frist", "dokument")
BELEGT = "belegt"
OHNE_BELEG = "ohne_beleg"
KOPF_ZEICHEN = 700  # so viel Text vom Anfang eines Dokuments
SCHLUSS_ZEICHEN = 400  # und so viel vom Schluss

SCHEMA = {
    "type": "object",
    "properties": {
        "ereignisse": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "datum": {"type": "string"},
                    "art": {"type": "string", "enum": ["ereignis", "frist"]},
                    "ereignis": {"type": "string"},
                    "streitig": {"type": "boolean"},
                    "angaben": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["datum", "art", "ereignis", "streitig", "angaben"],
            },
        },
        "dokumente": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kennung": {"type": "string"},
                    "bezeichnung": {"type": "string"},
                    "datum": {"type": "string"},
                },
                "required": ["kennung", "bezeichnung", "datum"],
            },
        },
    },
    "required": ["ereignisse", "dokumente"],
}

ANWEISUNG = (
    "Unten stehen Tatsachenangaben aus den Dokumenten einer Akte, jede mit Kennung (A…), Dokument, Beteiligtem "
    "(falls bekannt) und Haltung des Verfassers.{koepfe}\n\n"
    "Aufgabe: Erstelle eine Chronologie.\n"
    "- ereignisse: jedes datierte Geschehen einmal. datum: TT.MM.JJJJ; ist nur ein Monat genannt (etwa „Mitte "
    "Juni 2025“), dann so wie im Text. Nimm das Datum des Geschehens, nicht das Datum des Schreibens, das davon "
    "berichtet. art: ereignis (etwas geschah oder wurde erklärt) oder frist (ein Termin, bis zu dem etwas geschehen "
    "soll). ereignis: wenige Wörter, sachlich, ohne Wertung. streitig: true, wenn eine Seite das Ereignis bestreitet "
    "oder anders darstellt. angaben: die Kennungen aller Angaben aus allen Dokumenten, die dieses Ereignis nennen.\n"
    "- Eine Angabe kann zu mehreren Ereignissen gehören, etwa ein Rücktritt mit gesetzter Zahlungsfrist.\n"
    "- Erfinde kein Datum; Angaben ohne Datum lässt du weg.\n"
    "{dokumente}\n"
    "Angaben:\n{zeilen}"
)
ANWEISUNG_DOKUMENTE = (
    "- dokumente: für jeden Dokumentkopf (D…) das Datum des Dokuments selbst und eine kurze Bezeichnung (etwa "
    "Klageschrift, Schreiben des Autohauses, Urteil). Ohne erkennbares Datum weglassen.\n"
)


def _daten(text: str) -> list[Wert]:
    return [w for w in finde_werte(text) if w.art in (DATUM, MONAT)]


def datiert(angabe: dict) -> bool:
    return bool(_daten(angabe["text"]))


def lies_datum(text: object) -> Wert | None:
    """Das erste Datum oder der erste Monat in der Antwort des Modells."""
    daten = _daten(str(text or ""))
    return daten[0] if daten else None


def im_text(gesucht: Wert, text: str) -> Wert | None:
    """Die Stelle, an der das Datum im Text steht. Ein Monat passt auch zu einem Tag in diesem Monat."""
    for w in _daten(text):
        im_monat = gesucht.art == MONAT and w.art == DATUM and w.wert.startswith(gesucht.wert + "-")
        if w.wert == gesucht.wert or im_monat:
            return w
    return None


def kopf(t: belege.Text) -> list:
    """Anfang und Schluss eines Dokuments; dort stehen Ort und Datum eines Schreibens."""
    auswahl, zeichen = [], 0
    for a in t.abschnitte:
        if zeichen >= KOPF_ZEICHEN:
            break
        auswahl.append(a)
        zeichen += len(a["text"])
    # Vom Schluss so viele Absätze, bis SCHLUSS_ZEICHEN erreicht sind: Nach Ort und Datum folgen oft noch
    # Unterschriften, Anlagenvermerke und Fußzeilen.
    schluss, zeichen = [], 0
    for a in reversed(t.abschnitte):
        if zeichen >= SCHLUSS_ZEICHEN:
            break
        schluss.insert(0, a)
        zeichen += len(a["text"])
    schon = {a["nr"] for a in auswahl}
    return auswahl + [a for a in schluss if a["nr"] not in schon]


def _herkunft(a: dict) -> str:
    f = a["fundstelle"]
    return " · ".join(filter(None, [f["dateiname"], ", ".join(f["parteien"]), a["haltung"]]))


def erstelle(
    frage: Callable[[int, list[int], str, dict], dict | None],
    budget: int,
    je_dokument: list[dict],
    texte: dict[int, belege.Text],
    melde: Callable[[str], None] = lambda text: None,
) -> dict:
    alle = [a for e in je_dokument for a in e["angaben"] if datiert(a)]
    alle.sort(key=lambda a: _daten(a["text"])[0].wert)  # Blöcke enthalten dann benachbarte Daten
    zeilen = [f"[A{i}] {_herkunft(a)}: {a['text']}" for i, a in enumerate(alle, 1)]
    koepfe = list(texte.values())
    kopf_text = "\n\n".join(
        f"[D{j}] {t.dateiname}\n{belege.zeilen(kopf(t))}" for j, t in enumerate(koepfe, 1)
    )

    # Alle Angaben in einer Anfrage, wenn sie passen; sonst Blöcke, die Dokumentköpfe nur im ersten.
    bloecke: list[list[int]] = [[]]
    groesse = len(kopf_text)
    for i, z in enumerate(zeilen):
        if bloecke[-1] and groesse + len(z) + 1 > budget:
            bloecke.append([])
            groesse = 0
        bloecke[-1].append(i)
        groesse += len(z) + 1

    ereignisse: list[dict] = []
    verworfen = 0
    luecken: list[int] = []  # Teile, für die das Modell auch beim zweiten Versuch unbrauchbar antwortete
    for b, block in enumerate(bloecke):
        if len(bloecke) > 1:
            melde(f"Ordne die Ereignisse (Teil {b + 1} von {len(bloecke)})")
        mit_koepfen = b == 0
        antwort = frage(
            b + 1, luecken,
            ANWEISUNG.format(
                koepfe=(" Danach folgen Anfang und Schluss jedes Dokuments (Kennung D…)." if mit_koepfen else ""),
                dokumente=ANWEISUNG_DOKUMENTE if mit_koepfen else "- dokumente: leere Liste.\n",
                zeilen="\n".join(zeilen[i] for i in block)
                + (f"\n\nDokumentköpfe:\n{kopf_text}" if mit_koepfen else ""),
            ),
            SCHEMA,
        ) or {}
        for e in antwort.get("ereignisse") or []:
            neu = _ereignis(e, block, alle, texte)
            if neu is None:
                verworfen += 1
            else:
                ereignisse.append(neu)
        if mit_koepfen:
            for d in antwort.get("dokumente") or []:
                neu = _dokument(d, koepfe)
                if neu is None:
                    verworfen += 1
                else:
                    ereignisse.append(neu)

    ergebnis = sortiere(_fasse_zusammen(ereignisse))
    for e in ergebnis:
        del e["nummern"]
    return {
        "dokumente": [{"dokument_id": t.dokument_id, "dateiname": t.dateiname} for t in koepfe],
        "unvollstaendig": bool(luecken) or any(e.get("luecken") for e in je_dokument),
        "luecken_dokumente": [{"dateiname": e["dateiname"], "absaetze": e["luecken"]}
                              for e in je_dokument if e.get("luecken")],  # wie analyse._luecken_dokumente
        "angaben": len(alle),
        "verworfen": verworfen,
        "teile": len(bloecke),
        "luecken": luecken,
        "ereignisse": ergebnis,
    }


def _ereignis(e: object, block: list[int], alle: list[dict], texte: dict[int, belege.Text]) -> dict | None:
    if not isinstance(e, dict):
        return None
    datum = lies_datum(e.get("datum"))
    nummern = set()
    for k in e.get("angaben") or []:
        nr = str(k).strip().lstrip("[A").rstrip("]")
        if nr.isdigit() and int(nr) - 1 in block:
            nummern.add(int(nr) - 1)
    if datum is None or not nummern:
        return None
    quellen = [alle[n] for n in sorted(nummern)]
    fund = None
    for a in quellen:
        f = a["fundstelle"]
        absatz = texte[f["dokument_id"]].nach_nr.get(f["abschnitt"], "")
        if (w := im_text(datum, absatz)) is not None:
            fund = absatz[w.start : w.ende]
            break
    return {
        "datum": datum.wert,
        "anzeige": _anzeige(datum, fund),
        "art": e.get("art") if e.get("art") in ("ereignis", "frist") else "ereignis",
        "ereignis": str(e.get("ereignis") or "").strip() or "Ereignis",
        "streitig": bool(e.get("streitig")) or any(a["haltung"] == "bestritten" for a in quellen),
        "status": BELEGT if fund else OHNE_BELEG,
        "quellen": quellen,
        "nummern": nummern,
    }


def _dokument(d: object, koepfe: list[belege.Text]) -> dict | None:
    if not isinstance(d, dict):
        return None
    nr = str(d.get("kennung", "")).strip().lstrip("[D").rstrip("]")
    datum = lies_datum(d.get("datum"))
    if not nr.isdigit() or not 1 <= int(nr) <= len(koepfe) or datum is None:
        return None
    t = koepfe[int(nr) - 1]
    for a in kopf(t):
        if (w := im_text(datum, a["text"])) is not None:
            fundstelle = t.fundstelle(belege.Fund(a["nr"], w.start, w.ende, belege.WOERTLICH))
            bezeichnung = str(d.get("bezeichnung") or "").strip() or t.dateiname
            return {
                "datum": datum.wert,
                "anzeige": _anzeige(datum, a["text"][w.start : w.ende]),
                "art": "dokument",
                "ereignis": bezeichnung,
                "streitig": False,
                "status": BELEGT,
                "quellen": [{"text": bezeichnung, "haltung": "", "fundstelle": fundstelle}],
                "nummern": {("D", t.dokument_id)},
            }
    return None  # Datum steht nicht im Kopf des Dokuments


_REIHENFOLGE = {"dokument": 2, "frist": 1, "ereignis": 0}
# Wo ein Eintrag mit nur einem Monat zwischen den Tagen steht: „Mitte Februar 2026“ nach dem 14.02.,
# „Ende Februar 2026“ nach dem letzten Tag; ohne Zusatz und bei „Anfang“ vor dem 01.
_IM_MONAT = (("ende", "32"), ("mitte", "15"), ("anfang", "00"), ("beginn", "00"))


def _sortierdatum(e: dict) -> str:
    datum = e["datum"]
    if len(datum) != 7:  # schon ein Tag (JJJJ-MM-TT)
        return datum
    text = e.get("anzeige", "").lower()
    tag = next((t for wort, t in _IM_MONAT if text.startswith(wort)), "00")
    return f"{datum}-{tag}"


def sortiere(ereignisse: list[dict]) -> list[dict]:
    """Zeitlich ordnen; am selben Tag Ereignisse vor Fristen vor Dokumenten."""
    return sorted(ereignisse, key=lambda e: (_sortierdatum(e), _REIHENFOLGE.get(e.get("art"), 0)))


def _anzeige(datum: Wert, im_original: str | None) -> str:
    # Monatsangaben so, wie sie im Dokument stehen („Mitte Juni 2025“), Tage einheitlich.
    if datum.art == MONAT and im_original and _daten(im_original)[0].art == MONAT:
        return " ".join(im_original.split())
    return anzeige(datum.art, datum.wert)


def _fasse_zusammen(ereignisse: list[dict]) -> list[dict]:
    """Dasselbe Ereignis aus mehreren Blöcken (gleiches Datum, gleiche Art, gemeinsame Angabe) wird ein Eintrag."""
    ergebnis: list[dict] = []
    for e in ereignisse:
        gleich = next((x for x in ergebnis if x["datum"] == e["datum"] and x["art"] == e["art"]
                       and x["nummern"] & e["nummern"]), None)
        if gleich is None:
            ergebnis.append(e)
            continue
        neue = [q for q in e["quellen"] if q not in gleich["quellen"]]
        gleich["quellen"] += neue
        gleich["nummern"] |= e["nummern"]
        gleich["streitig"] = gleich["streitig"] or e["streitig"]
        if gleich["status"] == OHNE_BELEG:
            gleich["status"], gleich["anzeige"] = e["status"], e["anzeige"]
    return ergebnis
