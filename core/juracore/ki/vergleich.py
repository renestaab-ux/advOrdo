"""Vergleich der Dokumente einer Akte mit dem Sprachmodell: Zahlen und Daten mit ihrem Bezug, dazu inhaltliche
Widersprüche. Ohne Modell gilt der regelbasierte Abgleich (``abgleich.abgleich``) wie bisher.

Die Regeln kennen nur feste Merkmalswörter („Kaufpreis“, „Übergabe“). Was unter anderen Worten steht oder sich
auf etwas anderes bezieht („Anzahlung von 1.000 €“, „bei Abholung zeigte der Tacho …“), entgeht ihnen oder landet
im falschen Merkmal. Das Modell liest deshalb den Zusammenhang:

1. Je Dokument nennt es jeden Wert (Datum, Monat, Betrag, Kilometerstand, Fehlercode) mit seinem *Bezug*
   („Kilometerstand bei Übergabe“), der Haltung des Verfassers und einem wörtlichen Zitat. Das Zitat wird am
   Originaltext geprüft; den Wert liest die App aus dem gefundenen Zitat, nicht aus der Antwort des Modells. Ein
   Wert, der dort nicht steht, wird verworfen. Bestrittene Werte sind keine eigene Angabe des Verfassers und
   bleiben wie bei den Regeln außen vor.
2. Über alle Dokumente ordnet das Modell gleiche Bezüge zusammen („Kilometerstand bei Übergabe“ und „Tachostand
   bei Auslieferung“). Ob die Werte einer Gruppe abweichen, rechnet die App (``angaben.vereinbar``).
3. Zu jeder Abweichung gibt das Modell eine kurze Einschätzung, auch ob die Werte vielleicht Verschiedenes meinen.
4. Was die Regeln finden und das Modell nicht, kommt dazu, als „Regel“ gekennzeichnet.
5. Inhaltliche Widersprüche ohne Zahl oder Datum (abgelehnt gegen angeboten) liefert ``Analyse.widersprueche``.
"""

from __future__ import annotations

import re

from ..abgleich import abgleich as regeln
from ..abgleich.angaben import (
    _BESTREITEN,
    BETRAG,
    CODE,
    DATUM,
    KM,
    MONAT,
    Wert,
    _ist_verneint,
    anzeige,
    finde_werte,
    saetze,
    vereinbar,
)
from . import belege
from .analyse import BELEGREGEL, HALTUNGEN, Analyse, _einordnung
from .anbieter import KiFehler

AUFGABE = "vergleich"
WERTE = "vergleich_werte"

KI = "ki"
REGEL = "regel"
VERSCHIEDEN = "verschieden"  # Werte weichen ab, meinen laut Modell aber Verschiedenes

# Zeichen Text je Anfrage beim Lesen der Werte; wie bei den Tatsachenangaben unabhängig vom Kontext.
WERTE_STUECK = 10000
# Zeichen je Anfrage beim Zusammenordnen der Bezüge und bei der Einschätzung der Abweichungen.
ORDNEN_BLOCK = 9000

ARTEN_TEXT = {DATUM: "Datum", MONAT: "Datum", BETRAG: "Betrag", KM: "Kilometer", CODE: "Fehlercode"}
# Datum und Monat werden gemeinsam geordnet: „Mitte Juni 2025“ und „15.06.2025“ können dasselbe meinen.
_GRUPPE = {DATUM: DATUM, MONAT: DATUM, BETRAG: BETRAG, KM: KM, CODE: CODE}

SCHEMA_WERTE = {
    "type": "object",
    "properties": {
        "werte": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "wert": {"type": "string"},
                    "bezug": {"type": "string"},
                    "haltung": {"type": "string", "enum": HALTUNGEN},
                    "absatz": {"type": "integer"},
                    "zitat": {"type": "string"},
                },
                "required": ["wert", "bezug", "haltung", "absatz", "zitat"],
            },
        }
    },
    "required": ["werte"],
}

SCHEMA_GRUPPEN = {
    "type": "object",
    "properties": {
        "gruppen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"titel": {"type": "string"}, "bezuege": {"type": "array", "items": {"type": "string"}}},
                "required": ["titel", "bezuege"],
            },
        }
    },
    "required": ["gruppen"],
}

SCHEMA_BEWERTUNG = {
    "type": "object",
    "properties": {
        "bewertungen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kennung": {"type": "string"},
                    "einschaetzung": {"type": "string", "enum": ["abweichung", "verschiedenes"]},
                    "erklaerung": {"type": "string"},
                },
                "required": ["kennung", "einschaetzung", "erklaerung"],
            },
        }
    },
    "required": ["bewertungen"],
}


# --- 1. Werte je Dokument ---------------------------------------------------------------------------------------


def _werte_anweisung(t: belege.Text, stueck: list) -> str:
    teil = "" if len(stueck) == len(t.abschnitte) else f" (Absätze {stueck[0]['nr']} bis {stueck[-1]['nr']})"
    kopf = f"Dokument: {t.dateiname}" + (f" (Beteiligte: {', '.join(t.parteien)})" if t.parteien else "")
    return (
        f"{kopf}{teil}\n\n"
        "Aufgabe: Liste die Werte in diesem Text, die sich mit anderen Dokumenten der Akte vergleichen lassen: "
        "Kalenderdaten, Monatsangaben (z. B. „Mitte Juni 2025“), Geldbeträge, Kilometerstände und Fehlercodes "
        "(z. B. P17BF, auch „kein Eintrag“ im Fehlerspeicher).\n"
        "- wert: der Wert, wie er im Text steht (z. B. 14.900,00 €, 68.400 km, 12.05.2025).\n"
        "- bezug: worauf sich der Wert bezieht, als kurzer Begriff von 2 bis 8 Wörtern, so wie man dieselbe Sache "
        "in jedem Dokument der Akte benennen würde, z. B. „Kaufpreis des Fahrzeugs“, „Kilometerstand bei "
        "Übergabe“, „Datum der ersten Mängelanzeige“, „Frist zur Nacherfüllung“, „Fehlerspeicher beim Auslesen am "
        "27.06.2025“. Unterscheide genau: Kilometerstand bei Übergabe ist nicht der heutige Kilometerstand, eine "
        "Anzahlung ist nicht der Kaufpreis, das Datum eines Schreibens ist nicht das Datum des Ereignisses, von dem "
        "es berichtet („mit Schreiben vom 23.06.2025 gesetzte Frist“: 23.06.2025 ist das Datum des Schreibens, nicht "
        "die Frist), eine eingeklagte Forderung ist nicht der vom Gericht zugesprochene Betrag.\n"
        "- haltung: behauptet (der Verfasser stellt den Wert als zutreffend dar), bestritten (der Verfasser "
        "bestreitet oder verneint genau diesen Wert, z. B. „betrug nicht 64.800 km“, „Bestritten wird, dass … am "
        "12.05.2025 …“), unstreitig, festgestellt (vom Gericht). Was der Verfasser dem Bestrittenen als eigene "
        "Darstellung entgegensetzt („Die Klägerin hat sich erstmals Mitte Juni 2025 gemeldet“), ist behauptet.\n"
        "Nicht aufführen: Aktenzeichen, Geschäftszeichen, Telefonnummern, Postleitzahlen, Paragrafen, Seiten- und "
        "Randnummern, Daten von Gesetzen oder von Entscheidungen anderer Verfahren, Briefdatum im Kopf.\n"
        "Höchstens 40 Werte.\n\n"
        f"{BELEGREGEL} Das Zitat muss den Wert enthalten.\n\n"
        f"Text (jede Zeile ein Absatz, vorn seine Nummer):\n{belege.zeilen(stueck)}"
    )


def _wert_im_fund(t: belege.Text, fund: belege.Fund, wert: str):
    """Der Wert im gefundenen Zitat: der, den das Modell nennt; sonst der einzige dort. ``None``, wenn keiner passt."""
    text = t.nach_nr[fund.abschnitt]
    im_zitat = finde_werte(text[fund.start : fund.ende])
    if not im_zitat:
        return None
    genannt = finde_werte(wert)
    if genannt:
        g = genannt[0]
        for w in im_zitat:
            if (w.art, w.wert) == (g.art, g.wert):
                return w
    ziffern = re.sub(r"\D", "", wert)
    if ziffern:
        for w in im_zitat:
            roh = text[fund.start + w.start : fund.start + w.ende]
            if re.sub(r"\D", "", roh) == ziffern:
                return w
    if wert.strip().casefold() in ("kein eintrag", "keinen eintrag", "keine einträge"):
        for w in im_zitat:
            if w.wert == "kein Eintrag":
                return w
    return im_zitat[0] if len(im_zitat) == 1 else None


def _wert_im_absatz(t: belege.Text, fund: belege.Fund, wert: str):
    """Steht der genannte Wert nicht im (angenähert gefundenen) Zitat, aber genau einmal in dessen Absatz: der."""
    genannt = finde_werte(wert)
    if not genannt:
        return None
    g = genannt[0]
    treffer = [w for w in finde_werte(t.nach_nr[fund.abschnitt]) if (w.art, w.wert) == (g.art, g.wert)]
    return treffer[0] if len(treffer) == 1 else None


def _im_satz(text: str, start: int, wert: Wert) -> tuple[bool, bool]:
    """Ob der Satz um den Wert ein Bestreiten enthält, und ob der Wert in seinem Teilsatz verneint ist."""
    for s, e in saetze(text):
        if s <= start < e:
            satz = text[s:e]
            w = Wert(wert.art, wert.wert, start - s, start - s + (wert.ende - wert.start))
            return bool(_BESTREITEN.search(satz)), wert.wert != "kein Eintrag" and _ist_verneint(satz, w)
    return False, False


def werte(analyse: Analyse, dokument_id: int) -> dict:
    """Die Werte eines Dokuments mit Bezug und Beleg (gespeichert oder neu erfragt)."""
    t = analyse._text(dokument_id)
    return analyse._gespeichert(WERTE, _werte_eingabe(t), lambda: _lies_werte(analyse, t),
                                analyse._akte(dokument_id), dokument_id, ziel=False)


def _werte_eingabe(t: belege.Text) -> list:
    return [t.dateiname, t.parteien, belege.zeilen(t.abschnitte)]


def _lies_werte(analyse: Analyse, t: belege.Text) -> dict:
    stuecke = belege.teile_auf(t.abschnitte, min(analyse.budget, WERTE_STUECK))
    gefunden: list[dict] = []
    verworfen = bestritten = 0
    luecken: list[str] = []
    gesehen: set[tuple] = set()
    offen = list(reversed(stuecke))
    while offen:
        stueck = offen.pop()
        try:
            antwort = analyse._frage(_werte_anweisung(t, stueck), SCHEMA_WERTE)
        except KiFehler as fehler:
            if "JSON" not in str(fehler):
                raise
            if len(stueck) > 1:
                mitte = len(stueck) // 2
                offen += [stueck[mitte:], stueck[:mitte]]
                continue
            luecken.append(str(stueck[0]["nr"]))
            continue
        for w in antwort.get("werte") or []:
            if not isinstance(w, dict) or not str(w.get("bezug") or "").strip():
                continue
            absatz = w.get("absatz") if isinstance(w.get("absatz"), int) else None
            fund = belege.finde(w.get("zitat"), t.nach_nr, absatz) if isinstance(w.get("zitat"), str) else None
            wert, versatz = None, 0
            if fund:
                genannt = str(w.get("wert") or "")
                wert, versatz = _wert_im_fund(t, fund, genannt), fund.start
                if wert is None:
                    wert, versatz = _wert_im_absatz(t, fund, genannt), 0
            if wert is None:
                verworfen += 1
                continue
            start, ende = versatz + wert.start, versatz + wert.ende
            haltung = w.get("haltung") if w.get("haltung") in HALTUNGEN else "behauptet"
            satz_bestritten, satz_verneint = _im_satz(t.nach_nr[fund.abschnitt], start, wert)
            # Bestrittene Werte gibt der Verfasser nur wieder. Mittelgroße Modelle halten aber auch die eigene
            # Gegendarstellung im selben Absatz („Bestritten wird … Die Klägerin hat sich erstmals Mitte Juni
            # gemeldet“) für bestritten; maßgeblich ist deshalb der Satz, in dem der Wert steht.
            if satz_bestritten or (haltung == "bestritten" and satz_verneint):
                bestritten += 1
                continue
            if haltung == "bestritten":
                haltung = "behauptet"
            schluessel = (fund.abschnitt, start, wert.wert)
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            fundstelle = t.fundstelle(belege.Fund(fund.abschnitt, start, ende, fund.treffer))
            gefunden.append({
                "bezug": " ".join(str(w["bezug"]).split())[:100],
                "art": wert.art,
                "wert": wert.wert,
                "haltung": haltung,
                "fundstelle": fundstelle,
            })
    return {"dokument_id": t.dokument_id, "dateiname": t.dateiname, "werte": gefunden, "verworfen": verworfen,
            "bestritten": bestritten, "luecken": luecken}


# --- 2. Bezüge zusammenordnen -----------------------------------------------------------------------------------


def _kurz(dateiname: str) -> str:
    return dateiname.rsplit(".", 1)[0]


def _ordne_bezuege(analyse: Analyse, eintraege: list[dict], luecken: list[int]) -> list[list[int]]:
    """Gruppen gleicher Bezüge als Listen von Indizes in ``eintraege`` (je Eintrag ein Bezug einer Art)."""
    zeilen = []
    for i, e in enumerate(eintraege, 1):
        beispiel = e["beispiel"]
        satz = " ".join(f"{beispiel['davor']}{beispiel['wert']}{beispiel['danach']}".split())[:160]
        zeilen.append(f"[B{i}] {e['bezug']} — {', '.join(e['dokumente'])}: „{satz}“")
    bloecke: list[list[int]] = [[]]
    groesse = 0
    for i, z in enumerate(zeilen):
        if bloecke[-1] and groesse + len(z) + 1 > min(ORDNEN_BLOCK, analyse.budget):
            bloecke.append([])
            groesse = 0
        bloecke[-1].append(i)
        groesse += len(z) + 1
    gruppen: list[list[int]] = []
    vergeben: set[int] = set()
    for b, block in enumerate(bloecke, 1):
        if len(block) < 2:
            continue
        antwort = analyse._frage_oder_luecke(
            b, luecken,
            "Unten stehen Bezüge von Werten (" + ARTEN_TEXT[eintraege[block[0]]["gruppe"]] + ") aus den Dokumenten "
            "einer Akte, je mit Kennung, den Dokumenten und einem Beispielsatz.\n\n"
            "Aufgabe: Fasse die Bezüge zu Gruppen zusammen, die dieselbe Sache meinen (denselben Vorgang, denselben "
            "Zeitpunkt, denselben Gegenstand), auch wenn sie verschieden formuliert sind. So lassen sich die Werte "
            "derselben Sache aus verschiedenen Dokumenten nebeneinanderstellen.\n"
            "- Verschiedene Sachen gehören in verschiedene Gruppen, auch wenn sie ähnlich klingen: Kilometerstand bei "
            "Übergabe und heutiger Kilometerstand; Kaufpreis und Anzahlung; Frist zur Nacherfüllung und Frist zur "
            "Zahlung; Datum eines Schreibens und Datum des Ereignisses, von dem es berichtet; eingeklagte Forderung "
            "und vom Gericht zugesprochener Betrag.\n"
            "- titel: der Bezug in wenigen Wörtern, wie er über der Gegenüberstellung stehen soll.\n"
            "- bezuege: die Kennungen (z. B. B3) der Bezüge dieser Gruppe; jeder Bezug in höchstens einer Gruppe.\n"
            "Bezüge, die zu keinem anderen passen, lässt du weg.\n\n"
            "Bezüge:\n" + "\n".join(zeilen[i] for i in block),
            SCHEMA_GRUPPEN,
        )
        for g in (antwort or {}).get("gruppen") or []:
            if not isinstance(g, dict):
                continue
            nummern = []
            for k in g.get("bezuege") or []:
                nr = str(k).strip().strip("[]").lstrip("Bb")
                if nr.isdigit() and int(nr) - 1 in block and int(nr) - 1 not in vergeben:
                    nummern.append(int(nr) - 1)
            nummern = list(dict.fromkeys(nummern))
            if len(nummern) < 2:
                continue
            vergeben.update(nummern)
            titel = " ".join(str(g.get("titel") or "").split())[:80]
            gruppen.append(nummern)
            for n in nummern:
                eintraege[n]["titel"] = titel or eintraege[nummern[0]]["bezug"]
    gruppen += [[i] for i in range(len(eintraege)) if i not in vergeben]
    return gruppen


def _bezug_schluessel(bezug: str) -> str:
    return " ".join(re.sub(r"[^\wäöüß ]", " ", bezug.casefold()).split())


def _ordne(analyse: Analyse, je_dokument: list[dict]) -> dict:
    """Werte aller Dokumente zu Merkmalen gruppiert, mit Einschätzung der Abweichungen."""
    # Gleich lautende Bezüge einer Art sind ohne Rückfrage dieselbe Sache.
    eintraege: list[dict] = []
    nach_bezug: dict[tuple[str, str], dict] = {}
    for e in je_dokument:
        for w in e["werte"]:
            gruppe = _GRUPPE[w["art"]]
            schluessel = (gruppe, _bezug_schluessel(w["bezug"]))
            eintrag = nach_bezug.get(schluessel)
            if eintrag is None:
                eintrag = {"bezug": w["bezug"], "gruppe": gruppe, "werte": [], "dokumente": [],
                           "beispiel": w["fundstelle"]["ausschnitt"]}
                nach_bezug[schluessel] = eintrag
                eintraege.append(eintrag)
            eintrag["werte"].append(w)
            name = _kurz(w["fundstelle"]["dateiname"])
            if name not in eintrag["dokumente"]:
                eintrag["dokumente"].append(name)
    luecken: list[int] = []
    merkmale: list[dict] = []
    for gruppe in (DATUM, BETRAG, KM, CODE):
        teil = [e for e in eintraege if e["gruppe"] == gruppe]
        if not teil:
            continue
        analyse.fortschritt.melde(f"Ordne die Bezüge ({ARTEN_TEXT[gruppe]})")
        for nummern in _ordne_bezuege(analyse, teil, luecken):
            erste = teil[nummern[0]]
            titel = erste.get("titel") or erste["bezug"]
            werte_ = [w for n in nummern for w in teil[n]["werte"]]
            merkmale.append({"merkmal": f"ki:{len(merkmale) + 1}", "titel": titel, "werte": werte_})
    _bewerte(analyse, merkmale, luecken)
    return {"merkmale": merkmale, "luecken": luecken}


# --- 3. Abweichungen einschätzen --------------------------------------------------------------------------------


def _unvereinbar(werte_: list[dict]) -> bool:
    return any(not vereinbar(a["art"], a["wert"], b["art"], b["wert"])
               for i, a in enumerate(werte_) for b in werte_[i + 1:])


def _bewerte(analyse: Analyse, merkmale: list[dict], luecken: list[int]) -> None:
    abweichend = [m for m in merkmale if _unvereinbar(m["werte"])]
    if not abweichend:
        return
    analyse.fortschritt.melde("Schätze die Abweichungen ein")
    zeilen = []
    for i, m in enumerate(abweichend, 1):
        teile = []
        for w in m["werte"]:
            f = w["fundstelle"]
            herkunft = ", ".join(filter(None, [_kurz(f["dateiname"]), ", ".join(f["parteien"]), w["haltung"]]))
            satz = " ".join(f"{f['ausschnitt']['davor']}{f['ausschnitt']['wert']}{f['ausschnitt']['danach']}".split())
            teile.append(f"  - {anzeige(w['art'], w['wert'])} ({herkunft}): „{satz[:220]}“")
        zeilen.append(f"[M{i}] {m['titel']}\n" + "\n".join(teile))
    bloecke: list[list[int]] = [[]]
    groesse = 0
    for i, z in enumerate(zeilen):
        if bloecke[-1] and groesse + len(z) + 1 > min(ORDNEN_BLOCK, analyse.budget):
            bloecke.append([])
            groesse = 0
        bloecke[-1].append(i)
        groesse += len(z) + 1
    for b, block in enumerate(bloecke, 1):
        antwort = analyse._frage_oder_luecke(
            100 + b, luecken,
            "Unten stehen Werte aus den Dokumenten einer Akte, die sich auf dieselbe Sache beziehen sollen, aber "
            "nicht übereinstimmen. Zu jedem Wert stehen Dokument, Beteiligter, Haltung und der Satz, in dem er "
            "steht.\n\n"
            "Aufgabe: Schätze jede Gruppe ein.\n"
            "- einschaetzung: abweichung (die Dokumente machen zu derselben Sache verschiedene Angaben) oder "
            "verschiedenes (bei genauem Lesen meinen die Werte verschiedene Dinge oder Zeitpunkte, z. B. "
            "Kilometerstand bei Übergabe und bei der späteren Untersuchung).\n"
            "- erklaerung: ein Satz, was abweicht und wer was angibt, bzw. warum es Verschiedenes ist.\n"
            "- kennung: die Kennung der Gruppe (z. B. M2).\n\n"
            "Gruppen:\n" + "\n".join(zeilen[i] for i in block),
            SCHEMA_BEWERTUNG,
        )
        for x in (antwort or {}).get("bewertungen") or []:
            if not isinstance(x, dict):
                continue
            nr = str(x.get("kennung") or "").strip().strip("[]").lstrip("Mm")
            if not nr.isdigit() or int(nr) - 1 not in block:
                continue
            m = abweichend[int(nr) - 1]
            m["erklaerung"] = " ".join(str(x.get("erklaerung") or "").split())[:400]
            m["einschaetzung"] = "verschiedenes" if x.get("einschaetzung") == "verschiedenes" else "abweichung"


# --- Ablauf, Speicher und Zusammenführung mit den Regeln -------------------------------------------------------


def vergleiche(analyse: Analyse, akte_id: int, dokument_ids: list[int] | None = None) -> dict:
    """Werte je Dokument, Gruppen mit Einschätzung und inhaltliche Widersprüche; fertig zusammengeführt."""
    ids = analyse._dokument_ids(akte_id, dokument_ids)
    if not ids:
        raise ValueError("Die Akte enthält noch keine Dokumente.")
    je_dokument = []
    for i, d in enumerate(ids, 1):
        name = analyse.con.execute("SELECT dateiname FROM dokument WHERE id = ?", (d,)).fetchone()[0]
        analyse.fortschritt.melde(f"Lese Zahlen und Daten: {name}", i - 1, len(ids) * 2 + 2)
        je_dokument.append(werte(analyse, d))
    bezug = _bezug(ids, dokument_ids)
    analyse.fortschritt.melde("Ordne die Werte", len(ids), len(ids) * 2 + 2)
    ki_teil = analyse._gespeichert(AUFGABE, _ordnen_eingabe(je_dokument),
                                   lambda: _mit_luecken(_ordne(analyse, je_dokument), je_dokument), akte_id,
                                   bezug=bezug)
    inhaltlich = analyse.widersprueche(akte_id, dokument_ids)
    return zusammenfuehren(analyse.con, akte_id, dokument_ids, ki_teil, inhaltlich)


def gespeichert(analyse: Analyse, akte_id: int, dokument_ids: list[int] | None = None) -> dict | None:
    """Das gespeicherte Ergebnis (zusammengeführt mit den Regeln), ohne das Modell zu fragen; sonst ``None``."""
    ids = analyse._dokument_ids(akte_id, dokument_ids)
    if not ids:
        return None
    je_dokument, angaben = [], []
    for d in ids:
        t = analyse._text(d)
        w = analyse.nur_gespeichert(WERTE, _werte_eingabe(t))
        a = analyse.nur_gespeichert("angaben", [t.dateiname, t.parteien, belege.zeilen(t.abschnitte)])
        if w is None or a is None:
            return None
        je_dokument.append(w)
        angaben.append(a)
    ki_teil = analyse.nur_gespeichert(AUFGABE, _ordnen_eingabe(je_dokument))
    inhaltlich = analyse.nur_gespeichert("widersprueche", [[x["text"] for x in e["angaben"]] for e in angaben])
    if ki_teil is None or inhaltlich is None:
        return None
    ki_teil["gespeichert"] = inhaltlich["gespeichert"] = True
    return zusammenfuehren(analyse.con, akte_id, dokument_ids, ki_teil, inhaltlich)


def _bezug(ids: list[int], dokument_ids: list[int] | None) -> str:
    return ",".join(map(str, ids)) if dokument_ids else ""


def _ordnen_eingabe(je_dokument: list[dict]) -> list:
    return [[(w["bezug"], w["art"], w["wert"], w["fundstelle"]["abschnitt"]) for w in e["werte"]]
            for e in je_dokument]


def _mit_luecken(ergebnis: dict, je_dokument: list[dict]) -> dict:
    """Dokumente mit unbrauchbar beantworteten Absätzen: Ergebnis unvollständig, nicht speichern."""
    ergebnis["luecken_dokumente"] = [{"dateiname": e["dateiname"], "absaetze": e["luecken"]}
                                     for e in je_dokument if e.get("luecken")]
    ergebnis["unvollstaendig"] = bool(ergebnis["luecken"] or ergebnis["luecken_dokumente"])
    ergebnis["dokumente"] = [{"dokument_id": e["dokument_id"], "dateiname": e["dateiname"], "werte": len(e["werte"]),
                              "verworfen": e["verworfen"], "bestritten": e["bestritten"]} for e in je_dokument]
    return ergebnis


def _stelle(f: dict) -> tuple[int, int]:
    return f["dokument_id"], f["abschnitt"]


def _regel_abweichungen_behalten(regel_angaben: list[dict], merkmale: list[dict]) -> list[dict]:
    """Eine Abweichung, die die Regeln sehen, darf durch die KI nicht verschwinden.

    Ordnet das Modell die Werte eines Merkmals der Regeln verschiedenen Bezügen zu (im Urteil „Übergabe am
    18.03.2025“ und „Gefahrübergang am 21.03.2025“), steht die Gegenüberstellung der Regeln zusätzlich da, mit dem
    Hinweis, wie das Modell die Werte verteilt hat. Ob es dasselbe meint, entscheidet der Mensch.
    """
    gruppen: dict[str, dict] = {}
    for a in regel_angaben:
        g = gruppen.setdefault(a["merkmal"], {"titel": a["titel"], "werte": {}})
        regeln.wert_eintrag(g["werte"], a["art"], a["wert"])["fundstellen"].append({**a["fundstelle"], "quelle": REGEL})
    dazu = []
    for schluessel, g in gruppen.items():
        werte_ = list(g["werte"].values())
        if not _unvereinbar(werte_):
            continue
        if any(set(g["werte"]) <= set(m["werte"]) for m in merkmale):
            continue  # eine Karte zeigt die Abweichung schon
        # Wohin das Modell die Werte gelegt hat.
        orte = []
        for w in werte_:
            for m in merkmale:
                if m["quelle"] == KI and w["wert"] in m["werte"] and m["titel"] not in orte:
                    orte.append(m["titel"])
        hinweis = ("Die Regeln sehen hier dasselbe Merkmal; die KI ordnet die Werte verschiedenen Bezügen zu ("
                   + "; ".join(f"„{o}“" for o in orte) + "). Ob es dasselbe meint, zeigen die Fundstellen."
                   if len(orte) > 1 else "")
        dazu.append({"merkmal": f"regel:{schluessel}", "titel": g["titel"], "quelle": REGEL, "werte": g["werte"],
                     "erklaerung": hinweis, "einschaetzung": None})
    return dazu


def zusammenfuehren(con, akte_id: int, dokument_ids: list[int] | None, ki_teil: dict, inhaltlich: dict) -> dict:
    """Ergebnis wie ``abgleich.abgleich``, aus den Gruppen des Modells; was nur die Regeln finden, kommt dazu."""
    anzahl, regel_angaben = regeln.angaben_der_akte(con, akte_id, dokument_ids)
    merkmale: list[dict] = []
    ki_werte: dict[tuple[int, int, str], int] = {}  # (Dokument, Absatz, Wert) → Index des Merkmals
    for m in ki_teil["merkmale"]:
        eintrag = {"merkmal": m["merkmal"], "titel": m["titel"], "quelle": KI, "werte": {},
                   "erklaerung": m.get("erklaerung") or "", "einschaetzung": m.get("einschaetzung")}
        for w in m["werte"]:
            f = {**w["fundstelle"], "bezug": w["bezug"], "haltung": w["haltung"], "quelle": KI}
            regeln.wert_eintrag(eintrag["werte"], w["art"], w["wert"])["fundstellen"].append(f)
            ki_werte.setdefault((*_stelle(f), w["wert"]), len(merkmale))
        merkmale.append(eintrag)

    # Welches Merkmal des Modells einem Merkmal der Regeln entspricht: dort, wo die Regeln denselben Wert an
    # derselben Stelle gefunden haben.
    entspricht: dict[str, dict[int, int]] = {}
    fehlt: list[dict] = []
    for a in regel_angaben:
        i = ki_werte.get((*_stelle(a["fundstelle"]), a["wert"]))
        if i is None:
            fehlt.append(a)
        else:
            stimmen = entspricht.setdefault(a["merkmal"], {})
            stimmen[i] = stimmen.get(i, 0) + 1
    nur_regel: dict[str, dict] = {}
    for a in fehlt:
        stimmen = entspricht.get(a["merkmal"])
        if stimmen:
            ziel = merkmale[max(stimmen, key=lambda k: (stimmen[k], -k))]
        else:
            ziel = nur_regel.setdefault(a["merkmal"], {"merkmal": a["merkmal"], "titel": a["titel"], "quelle": REGEL,
                                                       "werte": {}, "erklaerung": "", "einschaetzung": None})
        regeln.wert_eintrag(ziel["werte"], a["art"], a["wert"])["fundstellen"].append(
            {**a["fundstelle"], "quelle": REGEL})
    merkmale += nur_regel.values()
    merkmale += _regel_abweichungen_behalten(regel_angaben, merkmale)

    ergebnis = []
    for m in merkmale:
        m = regeln.bewerte({**m, "werte": list(m["werte"].values())})
        if m["status"] == regeln.ABWEICHEND and m.get("einschaetzung") == "verschiedenes":
            m["status"] = VERSCHIEDEN
        if m["status"] != regeln.ABWEICHEND:
            m["erklaerung"] = m["erklaerung"] if m["status"] == VERSCHIEDEN else ""
        m.pop("einschaetzung", None)
        ergebnis.append(m)
    rang = {regeln.ABWEICHEND: 0, VERSCHIEDEN: 1, regeln.UEBEREINSTIMMEND: 2, regeln.EINZELN: 3}
    ergebnis.sort(key=lambda m: (rang[m["status"]], m["quelle"] != KI, -m["dokumente"], m["titel"].casefold()))

    for w in inhaltlich.get("widersprueche") or []:
        w.setdefault("einordnung", _einordnung([a["fundstelle"] for a in w["angaben"]]))
    return {
        "dokumente": anzahl,
        "merkmale": ergebnis,
        "zaehlung": {s: sum(1 for m in ergebnis if m["status"] == s) for s in rang},
        "quelle": KI,
        "modell": ki_teil.get("modell"),
        "erstellt_am": ki_teil.get("erstellt_am"),
        "gespeichert": bool(ki_teil.get("gespeichert")),
        "unvollstaendig": bool(ki_teil.get("unvollstaendig") or inhaltlich.get("unvollstaendig")),
        "luecken_dokumente": (ki_teil.get("luecken_dokumente") or []) + (inhaltlich.get("luecken_dokumente") or []),
        "ki_dokumente": ki_teil.get("dokumente") or [],
        "inhaltlich": inhaltlich,
    }
