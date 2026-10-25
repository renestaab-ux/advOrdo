"""Fragen an eine Akte oder an ein einzelnes Dokument, jede Antwort mit geprüften Fundstellen.

Ablauf („Beleg vor Behauptung“):

1. Die Dokumente gehen als nummerierte Absätze an das Modell, jeder mit
   Dokument- und Absatznummer: „[2.14] …“.
2. Das Modell antwortet mit einzelnen Aussagen. Tatsachen belegt es mit
   Dokument, Absatz und wörtlichem Zitat; rechtliche Würdigungen kennzeichnet es
   als Einschätzung, Fehlanzeigen („steht nicht in der Akte“) als Hinweis.
3. ``belege.finde`` prüft jedes Zitat am gespeicherten Originaltext. Gezeigt
   wird die Fundstelle aus dem Dokument, nie die Wiedergabe des Modells. Eine
   Tatsache ohne auffindbares Zitat heißt „ohne Beleg“.

Kontext: Passt die ganze Akte in das Zeichenbudget des Modells, sieht es alles.
Sonst bekommt es den Kopf jedes Dokuments (die ersten Absätze) und dann die
Absätze, die die meisten Begriffe der Frage enthalten; der Rest des Budgets
wird in Aktenreihenfolge aufgefüllt. Die Antwort nennt, wie viel vorlag.

Der Verlauf wird je Akte bzw. Dokument in ``ki_chat`` gespeichert; die letzten
Fragen und Antworten gehen als Zusammenhang mit in die nächste Anfrage.

Zuschaltbares Zusatzwissen (``wissen.py``): Rechner der Toolbox für Zinsen und
Fristen und Gesetze aus der Wissensbasis.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, date, datetime

from ..abgleich.abgleich import PARTEIEN
from ..rechner.basiszins import Basiszins
from . import belege, gegenueberstellung, wissen
from .analyse import BELEGT, OHNE_BELEG, Analyse, Fortschritt, OhneFortschritt
from .anbieter import ANTWORT_TOKEN, Anbieter, KiFehler

FASSUNG = 3

# Fragen und Antworten aus dem Verlauf, die als Zusammenhang mitgehen.
VERLAUF = 6
# Absätze je Dokument, die bei einer Auswahl immer mitgehen (Kopf: Art, Absender, Datum, Parteien).
KOPF = 2
HOECHSTENS = 12  # Aussagen je Antwort

TATSACHE = "tatsache"
EINSCHAETZUNG = "einschaetzung"
HINWEIS = "hinweis"
BERECHNUNG = "berechnung"

SYSTEM = (
    "Du bist ein sorgfältiger juristischer Assistent in einer deutschen Anwaltskanzlei. Du beantwortest Fragen zu "
    "den vorgelegten Dokumenten einer Akte. Tatsachen entnimmst du ausschließlich dem vorgelegten Text und "
    "erfindest nichts. Rechtliche Würdigungen kennzeichnest du als Einschätzung. Du antwortest nur mit JSON nach "
    "dem vorgegebenen Schema, auf Deutsch."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "aussagen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "art": {"type": "string", "enum": [TATSACHE, EINSCHAETZUNG, HINWEIS]},
                    "belege": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dokument": {"type": "integer"},
                                "absatz": {"type": "integer"},
                                "zitat": {"type": "string"},
                            },
                            "required": ["dokument", "absatz", "zitat"],
                        },
                    },
                },
                "required": ["text", "art", "belege"],
            },
        }
    },
    "required": ["aussagen"],
}

_SCHEMA_DB = """
CREATE TABLE IF NOT EXISTS ki_chat (
    id           INTEGER PRIMARY KEY,
    akte_id      INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    dokument_id  INTEGER REFERENCES dokument(id) ON DELETE CASCADE,  -- leer: Chat mit der ganzen Akte
    rolle        TEXT NOT NULL,          -- frage oder antwort
    inhalt       TEXT NOT NULL,          -- JSON
    erstellt_am  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ki_chat_bezug ON ki_chat (akte_id, dokument_id, id);
"""

# Häufige Wörter, die nichts über die gesuchte Stelle sagen.
_FUELLWOERTER = set(
    "aber alle also auch beim bitte dann dass denn diese dieser dieses doch eine einem einen einer eines etwas "
    "gibt habe haben hast hat hatte nach nicht noch oder seit sich sind über unter warum was welche welcher "
    "welches wenn wer wie wird wurde wurden zum zur zwischen steht stehen akte dokument dokumente".split()
)


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA_DB)


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def verlauf(con: sqlite3.Connection, akte_id: int, dokument_id: int | None = None) -> list[dict]:
    """Fragen und Antworten in zeitlicher Reihenfolge."""
    return [
        {"id": z["id"], "rolle": z["rolle"], "erstellt_am": z["erstellt_am"], **json.loads(z["inhalt"])}
        for z in con.execute(
            "SELECT * FROM ki_chat WHERE akte_id = ? AND dokument_id IS ? ORDER BY id", (akte_id, dokument_id)
        )
    ]


def leeren(con: sqlite3.Connection, akte_id: int, dokument_id: int | None = None) -> dict:
    with con:
        n = con.execute("DELETE FROM ki_chat WHERE akte_id = ? AND dokument_id IS ?", (akte_id, dokument_id)).rowcount
    return {"geloescht": n}


def _begriffe(text: str) -> set[str]:
    """Wortstämme der Frage (die ersten sechs Buchstaben), damit „Mangels“ auch „Mangel“ findet."""
    woerter = re.findall(r"[\wäöüß]{4,}", text.lower())
    zahlen = re.findall(r"\d[\d.,]*\d|\d", text)
    return {w[:6] for w in woerter if w not in _FUELLWOERTER} | {z for z in zahlen if len(z) >= 2}


def _treffer(begriffe: set[str], text: str) -> int:
    klein = text.lower()
    return sum(1 for b in begriffe if b in klein)


def waehle(texte: list[belege.Text], frage: str, budget: int) -> tuple[list[list[sqlite3.Row]], dict]:
    """Die Absätze je Dokument, die dem Modell vorgelegt werden, und eine Beschreibung der Auswahl."""
    groesse = {(i, a["nr"]): len(" ".join(a["text"].split())) + 10 for i, t in enumerate(texte) for a in t.abschnitte}
    alle = sum(groesse.values()) + sum(len(t.dateiname) + 40 for t in texte)
    gesamt = sum(len(t.abschnitte) for t in texte)
    if alle <= budget:
        return [list(t.abschnitte) for t in texte], {"vollstaendig": True, "absaetze": gesamt, "von": gesamt,
                                                     "dokumente": len(texte), "dokumente_von": len(texte)}
    begriffe = _begriffe(frage)
    gewaehlt: set[tuple[int, int]] = set()
    rest = budget - sum(len(t.dateiname) + 40 for t in texte)

    def nimm(schluessel: tuple[int, int]) -> None:
        nonlocal rest
        if schluessel not in gewaehlt and groesse[schluessel] <= rest:
            gewaehlt.add(schluessel)
            rest -= groesse[schluessel]

    for i, t in enumerate(texte):
        for a in t.abschnitte[:KOPF]:
            nimm((i, a["nr"]))
    bewertet = sorted(
        ((_treffer(begriffe, a["text"]), i, a["nr"]) for i, t in enumerate(texte) for a in t.abschnitte),
        key=lambda x: (-x[0], x[1], x[2]),
    )
    for punkte, i, nr in bewertet:
        if punkte > 0:
            nimm((i, nr))
    for i, t in enumerate(texte):
        for a in t.abschnitte:
            nimm((i, a["nr"]))
    auswahl = [[a for a in t.abschnitte if (i, a["nr"]) in gewaehlt] for i, t in enumerate(texte)]
    return auswahl, {
        "vollstaendig": False,
        "absaetze": len(gewaehlt),
        "von": gesamt,
        "dokumente": sum(1 for s in auswahl if s),
        "dokumente_von": len(texte),
    }


def _zusammenhang(eintraege: list[dict]) -> str:
    zeilen = []
    for e in eintraege[-VERLAUF:]:
        if e["rolle"] == "frage":
            zeilen.append(f"Frage: {e['text']}")
        else:
            zeilen.append("Antwort: " + " ".join(a["text"] for a in e.get("aussagen", [])))
    return "\n".join(zeilen)


def frage(
    con: sqlite3.Connection,
    anbieter: Anbieter,
    kontext: int,
    akte_id: int,
    text: str,
    dokument_id: int | None = None,
    fortschritt: Fortschritt | None = None,
    extern: str | None = None,
    rechner: bool = False,
    gesetze: sqlite3.Connection | None = None,
    gesetze_suche: bool = True,
    gesetze_ergaenzt: list[str] | None = None,
    rechtsprechung: str = "aus",
    basiszins: Basiszins | None = None,
    land: str = "BY",
    heute: date | None = None,
) -> dict:
    """Beantwortet eine Frage zur Akte bzw. zum Dokument, speichert Frage und Antwort und gibt die Antwort zurück.

    ``extern``: Name des externen Anbieters, an den die Anfrage geht (wird mit der Antwort vermerkt).
    ``rechner``: Zinsen und Fristen rechnet die App mit den Angaben des Modells (Toolbox).
    ``gesetze``: Verbindung zur Wissensbasis; dann gehen die zitierten Normen mit in die Anfrage und, mit
    ``gesetze_suche``, die zur Frage passenden Treffer der Volltextsuche; ``gesetze_ergaenzt``: vom Nutzer
    ergänzte Normen und Gesetze (siehe ``wissen.waehle_normen``).
    ``rechtsprechung``: ``akte`` legt Leitsätze und zitierte Randnummern der Entscheidungen der Akte vor, ``suche``
    dazu die zur Frage passenden Randnummern (siehe ``wissen.waehle_urteile``); ``aus`` keine.
    ``land``: Bundesland für Feiertage beim Fristenrechner.
    """
    fortschritt = fortschritt or OhneFortschritt()
    einrichten(con)
    text = text.strip()
    if not text:
        raise ValueError("Die Frage ist leer.")
    if dokument_id is not None:
        zeile = con.execute("SELECT akte_id FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
        if zeile is None or zeile[0] != akte_id:
            raise LookupError(f"Dokument {dokument_id} gehört nicht zu Akte {akte_id}.")
        ids = [int(dokument_id)]
    else:
        if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
            raise LookupError(f"Akte {akte_id} gibt es nicht.")
        ids = [z[0] for z in con.execute(
            "SELECT id FROM dokument WHERE akte_id = ? ORDER BY COALESCE(herkunft, ''), dateiname, id", (akte_id,)
        )]
    if not ids:
        raise ValueError("Diese Akte enthält noch keine Dokumente.")
    texte = [belege.lade_text(con, i, PARTEIEN) for i in ids]

    bisher = _zusammenhang(verlauf(con, akte_id, dokument_id))
    rechnen = rechner and wissen.soll_rechnen(text)
    normen: list[dict] = []
    fehlende_normen: list[str] = []
    if gesetze is not None:
        fortschritt.melde("Suche passende Normen in der Wissensbasis")
        zusaetzlich = ["§ 288 BGB", "§ 247 BGB", "§ 187 BGB", "§ 188 BGB", "§ 193 BGB"] if rechnen else []
        normen, fehlende_normen = wissen.waehle_normen(gesetze, con, akte_id, dokument_id, text, zusaetzlich,
                                                       suche=gesetze_suche, ergaenzt=gesetze_ergaenzt)
    urteile: list[dict] = []
    fehlende_urteile: list[str] = []
    mit_rechtsprechung = rechtsprechung in (wissen.RECHTSPRECHUNG_AKTE, wissen.RECHTSPRECHUNG_SUCHE)
    if mit_rechtsprechung and soll_gegenueberstellen(text):
        # „Stützen die zitierten Urteile …?“: je Zitat Schriftsatz und Entscheidung gegenüberstellen, wie im Reiter
        # Rechtsprechung (dieselben gespeicherten Ergebnisse), statt einer freien Antwort über die ganze Akte.
        g = gegenueberstellung.gegenueberstellen(Analyse(con, anbieter, kontext, fortschritt), akte_id, dokument_id)
        g["zitate"] = gegenueberstellung.zur_frage(g["zitate"], text)
        fortschritt.melde("Das Sprachmodell beantwortet die Frage anhand der Gegenüberstellung")
        fortschritt.pruefe()
        ergebnis = {"aussagen": _antwort_aus_gegenueberstellung(anbieter, text, g["zitate"]), "auswahl": None,
                    "modell": anbieter.modell, "extern": extern, "fassung": FASSUNG, "gegenueberstellung": g}
        return _speichere(con, akte_id, dokument_id, text, ergebnis)
    if mit_rechtsprechung:
        fortschritt.melde("Suche passende Stellen in der Rechtsprechung der Akte")
        urteile, fehlende_urteile = wissen.waehle_urteile(
            con, akte_id, dokument_id, text, suche=rechtsprechung == wissen.RECHTSPRECHUNG_SUCHE)

    def baue(normen: list[dict], urteile: list[dict]) -> tuple[str, dict, list[str], dict, str, str]:
        """Anfrage an das Modell: Text, Schema, vorgelegte Dokumente, Auswahl, Gesetzes- und Urteilstext."""
        normtext = wissen.normen_text(normen)
        urteiltext = wissen.urteile_text(urteile)
        zusatz = ((len(wissen.ANWEISUNG_RECHNER) if rechnen else 0) + len(normtext) + (400 if normen else 0)
                  + len(urteiltext) + (500 if urteile else 0))
        # Zeichen für Dokumenttext: Kontext abzüglich Antwort, Anweisung, Verlauf und Zusatzwissen,
        # rund 3 Zeichen je Token.
        budget = max(3000, (kontext - ANTWORT_TOKEN - 1200) * 3 - len(bisher) - len(text) - zusatz)
        stuecke, auswahl = waehle(texte, text + " " + bisher[-300:], budget)

        teile = []
        for nr, (t, abschnitte) in enumerate(zip(texte, stuecke, strict=True), 1):
            if not abschnitte:
                continue
            kopf = f"Dokument {nr}: {t.dateiname}" + (f" (Beteiligte: {', '.join(t.parteien)})" if t.parteien else "")
            zeilen = "\n".join(f"[{nr}.{a['nr']}] " + " ".join(a["text"].split()) for a in abschnitte)
            teile.append(f"{kopf}\n{zeilen}")
        umfang = (
            "Dir liegen die Dokumente vollständig vor."
            if auswahl["vollstaendig"]
            else "Dir liegt nur eine Auswahl der Absätze vor (die zur Frage passendsten). Steht die Antwort nicht "
            "darin, sage das als Hinweis, statt zu raten."
        )
        nutzer = (
            f"{chr(10).join(teile)}\n\n"
            + (f"Gesetze aus der Wissensbasis:\n{normtext}\n\n" if normen else "")
            + (f"Rechtsprechung aus der Akte:\n{urteiltext}\n\n" if urteile else "")
            + (f"Bisheriger Verlauf des Gesprächs:\n{bisher}\n\n" if bisher else "")
            + f"Frage: {text}\n\n"
            f"Aufgabe: Beantworte die Frage in höchstens {HOECHSTENS} kurzen Aussagen, die wichtigste zuerst. "
            f"{umfang}\n"
            "Ordne jede Aussage einer Art zu:\n"
            "- tatsache: was in den Dokumenten steht oder eine Partei dort vorträgt; nenne, wer es sagt\n"
            "- einschaetzung: deine rechtliche oder inhaltliche Würdigung; Normen und Urteile nennst du nur hier, "
            "ohne Aktenzeichen oder Randnummern zu erfinden\n"
            "- hinweis: etwa, dass die Dokumente zu der Frage nichts enthalten\n\n"
            "Belege jede Tatsache mit der Nummer des Dokuments und des Absatzes (die Zahlen in eckigen Klammern, "
            "[Dokument.Absatz]) und einem wörtlichen Zitat aus genau diesem Absatz: eine zusammenhängende Wortfolge "
            "von 4 bis 25 Wörtern, Zeichen für Zeichen abgeschrieben, ohne Auslassungen. Eine Einschätzung belegst du "
            "mit den Stellen, auf die sie sich stützt.\n\n"
            "Fragt die Frage nach einer rechtlichen Prüfung (etwa ob Voraussetzungen erfüllt, ein Anspruch begründet "
            "oder eine Norm anwendbar ist), beginne mit einer Einschätzung, die das Ergebnis nennt. Prüfe danach jede "
            "Voraussetzung einzeln als Einschätzung („Voraussetzung …: erfüllt/nicht erfüllt/offen, weil …“), belegt "
            "mit den Stellen der Akte und, wenn vorgelegt, dem Wortlaut der Norm. Gib den Sachverhalt nicht bloß "
            "wieder."
            + (f"\n\n{wissen.ANWEISUNG_GESETZE}" if normen else "")
            + (f"\n\n{wissen.ANWEISUNG_RECHTSPRECHUNG}" if urteile else "")
            + (f"\n\n{wissen.ANWEISUNG_RECHNER}" if rechnen else "")
        )
        # Zusatzfelder sind Pflicht: Lokale Modelle mit erzwungener JSON-Ausgabe (LM Studio) lassen freiwillige
        # Felder sonst einfach weg.
        schema = SCHEMA
        if normen or urteile or rechnen:
            schema = json.loads(json.dumps(SCHEMA))
            aussage = schema["properties"]["aussagen"]["items"]
            if normen:
                aussage["properties"]["normbelege"] = wissen.SCHEMA_NORMBELEGE
                aussage["required"] = [*aussage["required"], "normbelege"]
            if urteile:
                aussage["properties"]["urteilsbelege"] = wissen.SCHEMA_URTEILSBELEGE
                aussage["required"] = [*aussage["required"], "urteilsbelege"]
            if rechnen:
                schema["properties"]["berechnungen"] = wissen.SCHEMA_BERECHNUNG
                schema["required"] = [*schema["required"], "berechnungen"]
        return nutzer, _begrenzt(schema), teile, auswahl, normtext, urteiltext

    fortschritt.melde("Wähle die passenden Absätze aus")
    nutzer, schema, teile, auswahl, normtext, urteiltext = baue(normen, urteile)

    fortschritt.melde("Das Sprachmodell beantwortet die Frage")
    fortschritt.pruefe()
    gekuerzt = False
    try:
        antwort = anbieter.chat(SYSTEM, nutzer, schema)
    except KiFehler as fehler:
        if _zu_lang(fehler) and (normen or urteile):
            # Der im Programm eingestellte Kontext ist kleiner als angegeben: noch einmal mit weniger Gesetzes-
            # und Urteilstext (zitierte Normen, nur Leitsätze).
            fortschritt.melde("Die Anfrage war zu lang; frage noch einmal mit weniger Gesetzes- und Urteilstext")
            fortschritt.pruefe()
            normen = [n for n in normen if n["herkunft"] == "zitiert"][:3]
            for i, n in enumerate(normen, 1):
                n["nr"] = i
            urteile = wissen.nur_leitsaetze(urteile)
            nutzer, schema, teile, auswahl, normtext, urteiltext = baue(normen, urteile)
            gekuerzt = True
            try:
                antwort = anbieter.chat(SYSTEM, nutzer, schema)
            except KiFehler as noch:
                if not _zu_lang(noch):
                    raise
                raise KiFehler(_zu_lang_text(noch)) from noch
        elif _zu_lang(fehler):
            raise KiFehler(_zu_lang_text(fehler)) from fehler
        elif "JSON" not in str(fehler) or "abgeschnitten" in str(fehler):
            raise
        else:
            fortschritt.pruefe()
            antwort = anbieter.chat(SYSTEM, nutzer, schema)  # ein zweiter Versuch bei unbrauchbarem JSON

    aussagen = []
    gesehen: set[str] = set()
    for a in (antwort.get("aussagen") or [])[:HOECHSTENS]:
        if not isinstance(a, dict) or not str(a.get("text", "")).strip():
            continue
        # Dieselbe Aussage noch einmal (etwa als Tatsache und als Einschätzung) zeigt nur die erste.
        schluessel = re.sub(r"\W+", " ", str(a["text"]).lower()).strip()
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        art = a.get("art") if a.get("art") in (TATSACHE, EINSCHAETZUNG, HINWEIS) else TATSACHE
        fundstellen = []
        for b in a.get("belege") or []:
            if isinstance(b, dict) and (f := _beleg(texte, b.get("dokument"), b.get("absatz"), b.get("zitat"))):
                # Mehrere Zitate aus demselben Absatz ergäben gleiche Fundstellen; die erste genügt.
                if not any(_ort(f) == _ort(x) for x in fundstellen):
                    fundstellen.append(f)
        normbelege = []
        for b in (a.get("normbelege") or []) if normen else []:
            if isinstance(b, dict) and (f := wissen.normbeleg(normen, b.get("norm"), b.get("zitat"))):
                if not any(f["norm"] == x["norm"] for x in normbelege):
                    normbelege.append(f)
        urteilsbelege = []
        for b in (a.get("urteilsbelege") or []) if urteile else []:
            if isinstance(b, dict) and (f := wissen.urteilsbeleg(urteile, b.get("urteil"), b.get("zitat"))):
                if not any((f["urteil_id"], f["stelle"]) == (x["urteil_id"], x["stelle"]) for x in urteilsbelege):
                    urteilsbelege.append(f)
        # Eine Tatsache aus der Akte belegt nur das Dokument, eine Einschätzung auch der Wortlaut einer Norm oder
        # eine Stelle aus einer Entscheidung.
        belegt = fundstellen or ((normbelege or urteilsbelege) and art != TATSACHE)
        status = HINWEIS if art == HINWEIS and not belegt else (BELEGT if belegt else OHNE_BELEG)
        eintrag = {"text": str(a["text"]).strip(), "art": art, "status": status, "fundstellen": fundstellen}
        if normbelege:
            eintrag["normbelege"] = normbelege
        if urteilsbelege:
            eintrag["urteilsbelege"] = urteilsbelege
        aussagen.append(eintrag)

    berechnungen = []
    if rechnen:
        fortschritt.melde("Rechne mit den Rechnern der Toolbox")

        def belegen(dokument: object, absatz: object, zitat: object) -> tuple[dict, str] | None:
            f = _beleg(texte, dokument, absatz, zitat)
            if f is None:
                return None
            t = next(t for t in texte if t.dokument_id == f["dokument_id"])
            return f, t.nach_nr[f["abschnitt"]]

        vorschlaege = antwort.get("berechnungen")
        if not wissen.brauchbar(vorschlaege):
            # Zweiter, schmaler Auftrag nur für die Angaben des Rechners; kleine Modelle übergehen das Feld neben
            # der eigentlichen Antwort gern.
            fortschritt.melde("Das Sprachmodell sucht die Angaben für den Rechner")
            fortschritt.pruefe()
            try:
                vorschlaege = anbieter.chat(SYSTEM, wissen.rechner_auftrag(chr(10).join(teile), text),
                                            wissen.SCHEMA_NUR_BERECHNUNG).get("berechnungen")
            except KiFehler:
                vorschlaege = None
        berechnungen = wissen.berechne(vorschlaege, belegen, text, heute or date.today(), basiszins, land)
    for b in reversed(berechnungen):
        aussagen.insert(0, {"text": b["text"], "art": BERECHNUNG, "status": BELEGT if b["belegt"] else OHNE_BELEG,
                            "fundstellen": [], "berechnung": b})
    if any(b["ergebnis"] for b in berechnungen):
        # Die App hat gerechnet; Hinweise des Modells, es könne nicht rechnen, wären jetzt falsch.
        aussagen = [a for a in aussagen
                    if not (a["art"] == HINWEIS and re.search(r"basiszins|berechn|rechn", a["text"], re.I))]

    ergebnis = {
        "aussagen": aussagen,
        "auswahl": auswahl,
        "modell": anbieter.modell,
        "extern": extern,
        "fassung": FASSUNG,
    }
    if gesetze is not None:
        ergebnis["wissen"] = {
            "gesetze": [f"{n['bezeichnung']} {n['gesetz']}" for n in normen],
            "fehlend": fehlende_normen,
            "zeichen": len(normtext),
            "gekuerzt": gekuerzt,
        }
    if mit_rechtsprechung:
        w = ergebnis.setdefault("wissen", {})
        w["urteile"] = [u["bezeichnung"] for u in urteile]
        w["urteile_fehlend"] = fehlende_urteile
        w["urteile_zeichen"] = len(urteiltext)
        w["gekuerzt"] = w.get("gekuerzt", False) or gekuerzt
    if rechnen:
        ergebnis.setdefault("wissen", {})["rechner"] = True
    return _speichere(con, akte_id, dokument_id, text, ergebnis)


_GEGENUEBER = re.compile(
    r"(stütz|trag|trägt|belegen|deck|gegenüberst|vereinbar|passt|passen|richtig zitiert|zutreffend zitiert)",
    re.I)
_URTEILSWORT = re.compile(r"(urteil|entscheidung|beschluss|rechtsprechung|\bbgh\b|\bolg\b|\blg\b|zitat|zitiert)",
                          re.I)


_ERGEBNIS_TEXT = {
    gegenueberstellung.TRAEGT: "trägt die Aussage",
    gegenueberstellung.TEILWEISE: "trägt die Aussage nur teilweise",
    gegenueberstellung.TRAEGT_NICHT: "trägt die Aussage nicht",
    gegenueberstellung.OFFEN: "an den vorgelegten Stellen nicht beurteilbar",
    gegenueberstellung.NICHT_PRUEFBAR: "nicht prüfbar, Volltext fehlt",
}

SCHEMA_SYNTHESE = {
    "type": "object",
    "properties": {"aussagen": {"type": "array", "maxItems": 8, "items": {
        "type": "object",
        "properties": {"text": {"type": "string", "maxLength": 700},
                       "art": {"type": "string", "enum": [EINSCHAETZUNG, HINWEIS]},
                       "zitate": {"type": "array", "items": {"type": "integer"}, "maxItems": 4}},
        "required": ["text", "art", "zitate"]}}},
    "required": ["aussagen"],
}


def _seite(f: dict) -> str:
    return f" (S. {f['seite']})" if f.get("seite") else ""


def _ausschnitt(f: dict) -> str:
    a = f["ausschnitt"]
    return " ".join(f"{a['davor']}{a['wert']}{a['danach']}".split())


def _antwort_aus_gegenueberstellung(anbieter: Anbieter, frage: str, zitate: list[dict]) -> list[dict]:
    """Beantwortet die Frage aus den geprüften Gegenüberstellungen; jede Aussage übernimmt die Belege der
    Gegenüberstellungen, auf die sie verweist."""
    if not zitate:
        return [{"text": "In diesem Dokument bzw. dieser Akte wurden keine Rechtsprechungszitate erkannt.",
                 "art": HINWEIS, "status": HINWEIS, "fundstellen": []}]
    geprueft = [z for z in zitate if z["ergebnis"] != gegenueberstellung.NICHT_PRUEFBAR]
    hoechstens = 2 if len(geprueft) <= 1 else min(8, len(geprueft) + 2)
    bloecke = []
    for i, z in enumerate(zitate, 1):
        zeilen = [f"[Z{i}] {z['zitat']}" + (f", Rn. {z['rn_zitiert']}" if z["rn_zitiert"] is not None else "")
                  + f" – zitiert in {z['dateiname']}"]
        if z["ergebnis"] == gegenueberstellung.NICHT_PRUEFBAR:
            zeilen.append("Der Volltext liegt nicht vor; nicht geprüft.")
        else:
            zeilen.append(f"Schriftsatz entnimmt der Entscheidung: {z.get('behauptung') or '–'}")
            zeilen += [f"Schriftsatz{_seite(f)}: „{_ausschnitt(f)}“" for f in z.get("schriftsatz_belege") or []]
            zeilen.append(f"Entscheidung dazu: {z.get('entscheidung') or '–'}")
            zeilen += [f"Entscheidung, {f['stelle']}: „{_ausschnitt(f)}“" for f in z.get("urteil_belege") or []]
            zeilen.append(f"Einschätzung der Einzelprüfung: {_ERGEBNIS_TEXT[z['ergebnis']]}"
                          + (f" ({z['begruendung']})" if z.get("begruendung") else "")
                          + ("" if z["status"] == BELEGT else " – ohne geprüftes Zitat aus der Entscheidung"))
        if z.get("hinweis") and z["ergebnis"] != gegenueberstellung.NICHT_PRUEFBAR:
            zeilen.append(f"Hinweis: {z['hinweis']}")
        bloecke.append("\n".join(zeilen))
    nutzer = (
        "Geprüfte Gegenüberstellungen von Schriftsatz und zitierter Entscheidung (Zitate am Originaltext "
        "geprüft):\n\n" + "\n\n".join(bloecke) + f"\n\nFrage: {frage}\n\n"
        f"Aufgabe: Beantworte die Frage nur auf Grundlage dieser Gegenüberstellungen, knapp, in höchstens "
        f"{hoechstens} Aussagen. "
        + ("Die erste Aussage nennt das Ergebnis mit dem tragenden Grund. Eine zweite Aussage nur, wenn es eine "
           "Einschränkung, einen Unterschied im Sachverhalt oder eine Überdehnung gibt."
           if len(geprueft) <= 1 else
           "Die erste Aussage nennt das Ergebnis insgesamt in einem Satz. Danach je Entscheidung genau eine "
           "Aussage: was der Schriftsatz ihr entnimmt, was sie an der Stelle sagt und ob das trägt, mit Grund "
           "(Unterschiede im Sachverhalt, Einschränkungen, Überdehnung).")
        + " Fragt die Frage nach einer bestimmten Entscheidung, behandle nur diese. Gib unter \"zitate\" die "
        "Nummern der Gegenüberstellungen an (die Zahl nach Z), auf die sich die Aussage stützt. Keine Aussage "
        "darf eine andere wiederholen oder nur umformulieren. Was nicht geprüft werden konnte, nennst du in "
        "einem Hinweis."
    )
    try:
        antwort = anbieter.chat(SYSTEM, nutzer, SCHEMA_SYNTHESE)
    except KiFehler:
        antwort = {"aussagen": []}
    aussagen: list[dict] = []
    gesehen: list[set[str]] = []
    for a in (antwort.get("aussagen") or [])[:hoechstens + 1]:
        if not isinstance(a, dict) or not str(a.get("text", "")).strip():
            continue
        # Dieselbe Aussage mit anderen Worten (kleine Modelle wiederholen das Ergebnis gern) nur einmal.
        woerter = set(re.findall(r"\w{4,}", str(a["text"]).lower()))
        if any(_aehnlich(woerter, w) for w in gesehen):
            continue
        gesehen.append(woerter)
        art = HINWEIS if a.get("art") == HINWEIS else EINSCHAETZUNG
        fundstellen: list[dict] = []
        urteilsbelege: list[dict] = []
        for n in a.get("zitate") or []:
            if not isinstance(n, int) or not 1 <= n <= len(zitate):
                continue
            z = zitate[n - 1]
            for f in z.get("schriftsatz_belege") or [z["zitierstelle"]]:
                if not any(_ort(f) == _ort(x) for x in fundstellen):
                    fundstellen.append(f)
            for f in z.get("urteil_belege") or []:
                u = {"urteil_id": z["urteil_id"], "urteil": z["urteil"], **f}
                if not any((u["urteil_id"], u["stelle"]) == (x["urteil_id"], x["stelle"]) for x in urteilsbelege):
                    urteilsbelege.append(u)
        belegt = bool(urteilsbelege) or (art == HINWEIS and bool(fundstellen))
        status = HINWEIS if art == HINWEIS and not belegt else (BELEGT if belegt else OHNE_BELEG)
        eintrag = {"text": str(a["text"]).strip(), "art": art, "status": status, "fundstellen": fundstellen}
        if urteilsbelege:
            eintrag["urteilsbelege"] = urteilsbelege
        aussagen.append(eintrag)
    return aussagen


def _aehnlich(a: set[str], b: set[str]) -> bool:
    return bool(a and b) and len(a & b) / min(len(a), len(b)) >= 0.7


def soll_gegenueberstellen(frage: str) -> bool:
    """Fragt die Frage, ob zitierte Entscheidungen den Vortrag tragen?"""
    return bool(_GEGENUEBER.search(frage) and _URTEILSWORT.search(frage))


def _speichere(con: sqlite3.Connection, akte_id: int, dokument_id: int | None, text: str, ergebnis: dict) -> dict:
    jetzt = _jetzt()
    with con:
        con.execute("INSERT INTO ki_chat (akte_id, dokument_id, rolle, inhalt, erstellt_am) VALUES (?, ?, ?, ?, ?)",
                    (akte_id, dokument_id, "frage", json.dumps({"text": text}, ensure_ascii=False), jetzt))
        cur = con.execute(
            "INSERT INTO ki_chat (akte_id, dokument_id, rolle, inhalt, erstellt_am) VALUES (?, ?, ?, ?, ?)",
            (akte_id, dokument_id, "antwort", json.dumps(ergebnis, ensure_ascii=False), jetzt),
        )
    return {"id": cur.lastrowid, "rolle": "antwort", "erstellt_am": jetzt, **ergebnis}


def _begrenzt(schema: dict) -> dict:
    """Längengrenzen für die Antwort, damit sich ein lokales Modell nicht in endlosen Listen verfängt."""
    schema = json.loads(json.dumps(schema))
    aussagen = schema["properties"]["aussagen"]
    aussagen["maxItems"] = HOECHSTENS
    aussage = aussagen["items"]["properties"]
    aussage["text"]["maxLength"] = 600
    aussage["belege"]["maxItems"] = 3
    aussage["belege"]["items"]["properties"]["zitat"]["maxLength"] = 400
    if "normbelege" in aussage:
        aussage["normbelege"]["maxItems"] = 2
        aussage["normbelege"]["items"]["properties"]["zitat"]["maxLength"] = 400
    if "urteilsbelege" in aussage:
        aussage["urteilsbelege"]["maxItems"] = 2
        aussage["urteilsbelege"]["items"]["properties"]["zitat"]["maxLength"] = 400
    if "berechnungen" in schema["properties"]:
        b = schema["properties"]["berechnungen"]
        b["maxItems"] = wissen.HOECHSTENS_BERECHNUNGEN
        b["items"]["properties"]["angaben"]["maxItems"] = 6
    return schema


def _ort(f: dict) -> tuple:
    return f["dokument_id"], f["abschnitt"], f.get("seite"), f.get("rn")


_ZU_LANG = re.compile(r"context|n_ctx|tokens to keep|too long|exceed", re.I)


def _zu_lang(fehler: Exception) -> bool:
    """Ob das Programm die Anfrage abgelehnt hat, weil sie nicht in seinen Kontext passt."""
    return bool(_ZU_LANG.search(str(fehler)))


def _zu_lang_text(fehler: Exception) -> str:
    return ("Die Anfrage passt nicht in den Kontext, mit dem das Modell im Programm geladen ist. In LM Studio die "
            "„Context Length“ des Modells prüfen (empfohlen 32768, wie unter „Einstellungen“ angegeben) oder weniger "
            f"Gesetze oder Rechtsprechung einbeziehen. Meldung des Programms: {fehler}")


def _beleg(texte: list[belege.Text], dokument: object, absatz: object, zitat: object) -> dict | None:
    """Fundstelle des Zitats: zuerst im genannten Dokument, sonst in den übrigen vorgelegten."""
    if not isinstance(zitat, str):
        return None
    nr = dokument - 1 if isinstance(dokument, int) and 1 <= dokument <= len(texte) else None
    reihenfolge = ([texte[nr]] if nr is not None else []) + [t for i, t in enumerate(texte) if i != nr]
    for t in reihenfolge:
        bevorzugt = absatz if isinstance(absatz, int) and t is reihenfolge[0] and nr is not None else None
        fund = belege.finde(zitat, t.nach_nr, bevorzugt)
        if fund:
            return t.fundstelle(fund)
    return None
