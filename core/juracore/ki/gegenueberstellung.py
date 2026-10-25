"""Gegenüberstellung: trägt die zitierte Entscheidung die Aussage, für die der Schriftsatz sie zitiert?

Je Urteilszitat eines Dokuments legt die App dem Modell nur zwei Dinge vor: die zitierende Stelle im Schriftsatz
(mit dem Absatz davor) und die passenden Stellen aus dem Volltext der Entscheidung, die der Akte vorliegt – die
zitierte Randnummer mit ihren Nachbarn, sonst die Leitsätze und die Randnummern mit den meisten gemeinsamen
Begriffen. So bleibt jede Anfrage klein, auch für ein lokales Modell.

„Beleg vor Behauptung“: Das Modell gibt wieder, was der Schriftsatz der Entscheidung entnimmt und was die
Entscheidung an den vorgelegten Stellen sagt, beides mit wörtlichen Zitaten. Die App prüft jedes Zitat am
gespeicherten Text. Das Ergebnis („trägt“, „trägt teilweise“, „trägt nicht“) ist eine Einschätzung des Modells; ohne
geprüftes Zitat aus der Entscheidung heißt es „ohne Beleg“. Ohne Volltext prüft die App nichts und sagt das.
Jedes Ergebnis wird gespeichert; ein neuer Lauf fragt nur Zitate, deren Text sich geändert hat.
"""

from __future__ import annotations

import re
import sqlite3
from typing import TYPE_CHECKING

from ..rechtsprechung.zitate import az_kern
from . import belege, speicher

if TYPE_CHECKING:
    from .analyse import Analyse

AUFGABE = "gegenueberstellung"
FASSUNG = 3  # 2: Zitat vorrangig aus der zitierten Randnummer; 3: zweiter Blick in die übrigen Stellen

TRAEGT = "traegt"
TEILWEISE = "traegt_teilweise"
TRAEGT_NICHT = "traegt_nicht"
OFFEN = "nicht_beurteilbar"  # die vorgelegten Stellen sagen zur Aussage nichts
NICHT_PRUEFBAR = "nicht_pruefbar"  # kein Volltext: die App hat nicht gefragt
ERGEBNISSE = [TRAEGT, TEILWEISE, TRAEGT_NICHT, OFFEN]

URTEIL_ZEICHEN = 6000  # Text der Entscheidung je Anfrage
ABSATZ_ZEICHEN = 1500
SCHRIFTSATZ_ZEICHEN = 2500
NACHBARN = 1  # Randnummern vor und nach der zitierten
TREFFER = 4  # Randnummern zu den Begriffen der zitierenden Stelle, wenn keine Rn. zitiert ist
_LEITSAETZE = ("leitsatz", "sonstosatz")

_BELEG = {
    "type": "object",
    "properties": {"nr": {"type": "integer"}, "zitat": {"type": "string", "maxLength": 400}},
    "required": ["nr", "zitat"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "behauptung": {"type": "string", "maxLength": 500},
        "schriftsatz_belege": {"type": "array", "items": _BELEG, "maxItems": 2},
        "entscheidung": {"type": "string", "maxLength": 600},
        "urteil_belege": {"type": "array", "items": _BELEG, "maxItems": 2},
        "ergebnis": {"type": "string", "enum": ERGEBNISSE},
        "begruendung": {"type": "string", "maxLength": 800},
    },
    "required": ["behauptung", "schriftsatz_belege", "entscheidung", "urteil_belege", "ergebnis", "begruendung"],
}

_FUELL = set("aber auch dass diese dieser dieses durch einer eines einem einen nicht nach oder sein seine sind "
             "unter wenn werden wurde wird zwischen sowie bereits insbesondere urteil entscheidung beschluss "
             "klägers kläger klägerin beklagte beklagten".split())


def _woerter(text: str) -> list[str]:
    gesehen: list[str] = []
    for w in re.findall(r"[a-zäöüß]{6,}", text.lower()):
        if w not in _FUELL and w[:7] not in gesehen:
            gesehen.append(w[:7])
    return gesehen[:20]


def _kurz(text: str, zeichen: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= zeichen else text[:zeichen].rsplit(" ", 1)[0] + " …"


def _stelle(a: dict) -> str:
    if a["rn"] is not None:
        return f"Rn. {a['rn']}"
    if a["teil"] in _LEITSAETZE:
        return "Leitsatz"
    return f"Abschn. {a['nr']}" + (f", S. {a['seite']}" if a.get("seite") else "")


def _bezeichnung(u: sqlite3.Row) -> str:
    datum = u["datum"]
    wann = f" vom {datum[8:10]}.{datum[5:7]}.{datum[:4]}" if datum and len(datum) >= 10 else ""
    return f"{u['gericht']}, Entscheidung{wann}" + (f" – {u['aktenzeichen']}" if u["aktenzeichen"] else "")


def _urteil_zu(urteile: list[sqlite3.Row], z: sqlite3.Row) -> sqlite3.Row | None:
    for u in urteile:
        if u["zitat"] == z["zitat"]:
            return u
    for u in urteile:
        if (z["aktenzeichen"] and u["aktenzeichen"] and az_kern(u["aktenzeichen"]) == az_kern(z["aktenzeichen"])
                and u["gericht"].casefold() == z["gericht"].casefold()):
            return u
    return None


def zitate(con: sqlite3.Connection, akte_id: int, dokument_id: int | None = None) -> list[dict]:
    """Die Urteilszitate der Akte bzw. des Dokuments, je zitierende Stelle einmal, mit der vorliegenden
    Entscheidung (oder ``None``)."""
    zeilen = con.execute(
        """SELECT z.*, a.nr AS abschnitt, d.id AS dokument_id, d.dateiname FROM urteilszitat z
           JOIN abschnitt a ON a.id = z.abschnitt_id JOIN dokument d ON d.id = a.dokument_id
           WHERE d.akte_id = ? AND (? IS NULL OR d.id = ?) ORDER BY d.dateiname, d.id, a.nr, z.start""",
        (akte_id, dokument_id, dokument_id)).fetchall()
    urteile = con.execute("SELECT * FROM urteil WHERE akte_id = ? ORDER BY id", (akte_id,)).fetchall()
    aus: list[dict] = []
    gesehen: set[tuple] = set()
    for z in zeilen:
        u = _urteil_zu(urteile, z)
        schluessel = (z["dokument_id"], z["abschnitt"], u["id"] if u else z["zitat"], z["rn_zitiert"])
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        aus.append({"zeile": z, "urteil": u})
    return aus


def _schriftsatz(t: belege.Text, nr: int) -> list[dict]:
    """Die zitierende Stelle und der Absatz davor (dort steht oft die Aussage, die belegt werden soll)."""
    nummern = sorted(t.nach_nr)
    i = nummern.index(nr)
    teile = [nummern[i - 1]] if i > 0 else []
    teile.append(nr)
    rest = SCHRIFTSATZ_ZEICHEN
    aus = []
    for n in reversed(teile):  # die zitierende Stelle zuerst ins Budget
        text = _kurz(t.nach_nr[n], rest)
        if len(text) < 20 and n != nr:
            continue
        rest -= len(text)
        aus.insert(0, {"nr": n, "text": text})
    return aus


def _urteilsstellen(con: sqlite3.Connection, urteil_id: int, rn: int | None, bezug: str,
                    ohne: set[int] | frozenset[int] = frozenset()) -> tuple[list[dict], bool]:
    """Stellen der Entscheidung für die Anfrage und ob die zitierte Randnummer im Volltext vorkommt. ``ohne``:
    Abschnitte (außer Leitsätzen), die schon vorgelegt waren."""
    alle = [dict(a) for a in con.execute(
        "SELECT nr, seite, rn, text, teil FROM urteil_abschnitt WHERE urteil_id = ? ORDER BY nr", (urteil_id,))
        if a["teil"] in _LEITSAETZE or a["nr"] not in ohne]
    gewaehlt: list[dict] = []
    rn_da = rn is not None and any(a["rn"] == rn for a in alle)
    if rn_da:
        gewaehlt = [a for a in alle if a["rn"] is not None and abs(a["rn"] - rn) <= NACHBARN]
    leit = [a for a in alle if a["teil"] in _LEITSAETZE][:3]
    if not rn_da:
        woerter = _woerter(bezug)
        bewertet = sorted(((sum(1 for w in woerter if w in a["text"].lower()), a["nr"], a) for a in alle
                           if a["teil"] not in _LEITSAETZE), key=lambda x: (-x[0], x[1]))
        gewaehlt = [a for punkte, _, a in bewertet[:TREFFER] if punkte > 0]
        if not leit and not gewaehlt:
            gewaehlt = alle[:2]
    stellen = []
    rest = URTEIL_ZEICHEN
    for a in leit + [a for a in gewaehlt if a not in leit]:
        text = _kurz(a["text"], min(ABSATZ_ZEICHEN, rest))
        if len(text) < 20:
            break
        rest -= len(text)
        stellen.append({**a, "text": text})
    reihenfolge = {id(a): i for i, a in enumerate(stellen)}
    stellen.sort(key=lambda a: (a["teil"] not in _LEITSAETZE, a["nr"], reihenfolge[id(a)]))
    for i, a in enumerate(stellen, 1):
        a["u"] = i
        a["stelle"] = _stelle(a)
    return stellen, rn_da


def _anweisung(t: belege.Text, schrift: list[dict], zitierend: int, zitat: str, rn: int | None, urteil: str,
               stellen: list[dict], zweiter_blick: bool = False) -> str:
    s = "\n".join(f"[S{a['nr']}]{' (zitierende Stelle)' if a['nr'] == zitierend else ''} {a['text']}"
                  for a in schrift)
    zitiert = next((a for a in stellen if rn is not None and a["rn"] == rn), None)
    u = "\n".join(f"[U{a['u']} {a['stelle']}]{' (zitierte Stelle)' if a is zitiert else ''} {a['text']}"
                  for a in stellen)
    return (
        f"Schriftsatz: {t.dateiname}" + (f" (Beteiligte: {', '.join(t.parteien)})" if t.parteien else "") + "\n"
        f"{s}\n\n"
        f"Zitiert wird: {zitat}" + (f", Rn. {rn}" if rn is not None else "") + "\n\n"
        f"Vorgelegte Stellen aus dem Volltext ({urteil}):\n{u}\n\n"
        + (f"Die zitierte Rn. {rn} trägt die Aussage nicht. Prüfe, ob eine dieser anderen Stellen sie trägt.\n\n"
           if zweiter_blick else "")
        + 
        "Aufgabe: Prüfe, ob die vorgelegten Stellen der Entscheidung die Aussage tragen, für die der Schriftsatz "
        "sie zitiert.\n"
        "1. behauptung: Was entnimmt der Schriftsatz der Entscheidung? Ein Satz, mit wem es vorträgt. Belege es "
        "unter schriftsatz_belege mit der Nummer nach S und einem wörtlichen Zitat aus diesem Absatz.\n"
        "2. entscheidung: Was sagt die Entscheidung an den vorgelegten Stellen dazu? Ein bis zwei Sätze. Belege es "
        "unter urteil_belege mit der Nummer nach U und einem wörtlichen Zitat aus dieser Stelle."
        + (f" Zitiere zuerst aus der zitierten Stelle [U{zitiert['u']} {zitiert['stelle']}]; den Leitsatz nur "
           "zusätzlich, wenn er etwas anderes oder mehr sagt." if zitiert else "") + "\n"
        "3. ergebnis: traegt (die Stelle sagt das so), traegt_teilweise (nur mit Einschränkung, unter anderen "
        "Voraussetzungen oder weniger weit), traegt_nicht (die Stelle sagt etwas anderes oder das Gegenteil), "
        "nicht_beurteilbar (die vorgelegten Stellen enthalten dazu nichts).\n"
        "4. begruendung: ein bis drei Sätze; nenne Unterschiede im Sachverhalt, Einschränkungen oder ob der "
        "Schriftsatz mehr behauptet, als die Entscheidung sagt.\n"
        f"{belege_regel()}"
    )


def belege_regel() -> str:
    return ("Wörtliche Zitate: eine zusammenhängende Wortfolge von 4 bis 25 Wörtern, Zeichen für Zeichen "
            "abgeschrieben, ohne Auslassungen. Erfinde keine Randnummern und keine anderen Entscheidungen.")


def _urteilsbeleg(stellen: list[dict], nr: object, zitat: object) -> dict | None:
    if not isinstance(zitat, str):
        return None
    fund = belege.finde(zitat, {a["u"]: a["text"] for a in stellen}, nr if isinstance(nr, int) else None)
    if fund is None:
        return None
    a = next(a for a in stellen if a["u"] == fund.abschnitt)
    text = a["text"]
    von, bis = max(0, fund.start - belege.UMFELD), min(len(text), fund.ende + belege.UMFELD)
    return {
        "stelle": a["stelle"], "rn": a["rn"], "treffer": fund.treffer,
        "ausschnitt": {
            "davor": ("… " if von > 0 else "") + text[von:fund.start].lstrip(),
            "wert": text[fund.start:fund.ende],
            "danach": text[fund.ende:bis].rstrip() + (" …" if bis < len(text) else ""),
        },
    }


def _pruefe(analyse: Analyse, t: belege.Text, eintrag: dict, nur_gespeichert: bool) -> dict | None:
    z, u = eintrag["zeile"], eintrag["urteil"]
    rn = z["rn_zitiert"]
    zitierstelle = t.fundstelle(belege.Fund(z["abschnitt"], z["start"], z["ende"], belege.WOERTLICH))
    basis = {
        "zitat": z["zitat"], "gericht": z["gericht"], "aktenzeichen": z["aktenzeichen"], "rn_zitiert": rn,
        "dokument_id": t.dokument_id, "dateiname": t.dateiname, "abschnitt": z["abschnitt"],
        "zitierstelle": zitierstelle, "urteil_id": u["id"] if u else None,
        "urteil": _bezeichnung(u) if u else None,
    }
    if u is None:
        return {**basis, "ergebnis": NICHT_PRUEFBAR, "status": NICHT_PRUEFBAR, "stellen": [],
                "hinweis": "Der Volltext liegt der Akte nicht vor. Lade ihn im Reiter Rechtsprechung oder ergänze "
                           "ihn als eigene Datei; erst dann lässt sich gegenüberstellen."}
    schrift = _schriftsatz(t, z["abschnitt"])
    stellen, rn_da = _urteilsstellen(analyse.con, u["id"], rn, " ".join(a["text"] for a in schrift))
    hinweis = (f"Rn. {rn} gibt es im vorliegenden Volltext nicht; vorgelegt wurden die Leitsätze und die Stellen "
               "mit den meisten gemeinsamen Begriffen." if rn is not None and not rn_da else None)
    nutzer = _anweisung(t, schrift, z["abschnitt"], z["zitat"], rn, basis["urteil"], stellen)
    key = speicher.schluessel(AUFGABE, FASSUNG, type(analyse.anbieter).__name__, analyse.modell, nutzer)
    gespeichert = speicher.lies(analyse.con, key)
    if gespeichert is not None and not analyse.neu:
        return {**gespeichert, "gespeichert": True}
    if nur_gespeichert:
        return None
    aus = _auswerten(analyse, t, schrift, stellen, rn, rn_da, analyse._frage(nutzer, SCHEMA))
    if rn_da and aus["ergebnis"] in (TRAEGT_NICHT, OFFEN):
        # Vielleicht steht die Aussage nur an einer anderen Stelle (falsche Randnummer): ein zweiter Blick auf die
        # Stellen mit den meisten gemeinsamen Begriffen.
        weitere, _ = _urteilsstellen(analyse.con, u["id"], None, " ".join(a["text"] for a in schrift),
                                     ohne={a["nr"] for a in stellen})
        if any(a["teil"] not in _LEITSAETZE for a in weitere):
            analyse.fortschritt.pruefe()
            zweit = _auswerten(analyse, t, schrift, weitere, None, False, analyse._frage(
                _anweisung(t, schrift, z["abschnitt"], z["zitat"], rn, basis["urteil"], weitere, True), SCHEMA))
            andere = ", ".join(a["stelle"] for a in weitere if a["teil"] not in _LEITSAETZE)
            if zweit["ergebnis"] in (TRAEGT, TEILWEISE) and any(f["stelle"] != "Leitsatz"
                                                                 for f in zweit["urteil_belege"]):
                aus = {**zweit, "hinweis": f"Die zitierte Rn. {rn} trägt die Aussage nicht; sie findet sich aber "
                                           f"in {', '.join(f['stelle'] for f in zweit['urteil_belege'])}. "
                                           "Die Randnummer im Schriftsatz ist wohl falsch."}
            else:
                aus["hinweis"] = f"Auch die übrigen passenden Stellen ({andere}) tragen die Aussage nicht."
    aus = {**basis, **aus, "hinweis": aus.get("hinweis") or hinweis}
    speicher.schreibe(analyse.con, key, AUFGABE, analyse.modell, aus, analyse._akte(t.dokument_id), t.dokument_id,
                      bezug=f"zitat:{z['id']}")
    return {**aus, "gespeichert": False}


def _ohne_marken(text: object, stellen: list[dict]) -> str:
    """Die Kennungen der Anfrage ([S25], [U3 Rn. 67], U2) durch lesbare Stellen ersetzen bzw. streichen."""
    text = str(text or "").strip()
    nach_u = {a["u"]: a["stelle"] for a in stellen}
    text = re.sub(r"\[U(\d+)(?:\s+[^\]]*)?\]", lambda m: nach_u.get(int(m.group(1)), ""), text)
    text = re.sub(r"\bU(\d+)\b", lambda m: nach_u.get(int(m.group(1)), m.group(0)), text)
    text = re.sub(r"\s+in\s+\[S\d+\]", "", text)
    text = re.sub(r"\s*\(?\[S\d+\]\)?|\s*\(S\d+\)", "", text)
    return re.sub(r"\s+([,.;:])", r"\1", re.sub(r"  +", " ", text)).strip()


def _auswerten(analyse: Analyse, t: belege.Text, schrift: list[dict], stellen: list[dict], rn: int | None,
               rn_da: bool, antwort: dict) -> dict:
    """Prüft die Zitate einer Antwort an Schriftsatz und Entscheidung."""

    schriftsatz_belege = []
    for b in antwort.get("schriftsatz_belege") or []:
        if isinstance(b, dict) and (f := analyse._beleg(
                belege.Text(t.dokument_id, t.dateiname, t.parteien,
                            [a for a in t.abschnitte if a["nr"] in {s["nr"] for s in schrift}]),
                b.get("nr"), b.get("zitat"))):
            if not any(f["abschnitt"] == x["abschnitt"] and f["ausschnitt"] == x["ausschnitt"]
                       for x in schriftsatz_belege):
                schriftsatz_belege.append(f)
    urteil_belege = []
    for b in antwort.get("urteil_belege") or []:
        if isinstance(b, dict) and (f := _urteilsbeleg(stellen, b.get("nr"), b.get("zitat"))):
            if not any(f["stelle"] == x["stelle"] for x in urteil_belege):
                urteil_belege.append(f)
    hinweis = None
    if rn_da:
        # Die zitierte Randnummer zuerst; fehlt ein Zitat aus ihr, sagt die App das.
        urteil_belege.sort(key=lambda f: f["rn"] != rn)
        if urteil_belege and urteil_belege[0]["rn"] != rn:
            hinweis = (f"Belegt nur mit {', '.join(f['stelle'] for f in urteil_belege)}, nicht mit der zitierten "
                       f"Rn. {rn}.")
    ergebnis = antwort.get("ergebnis") if antwort.get("ergebnis") in ERGEBNISSE else OFFEN
    # „Trägt nicht“ und „nicht beurteilbar“ dürfen ohne Zitat stehen (es fehlt ja gerade die Stelle); „trägt“
    # braucht ein geprüftes Zitat aus der Entscheidung.
    status = "belegt" if urteil_belege or ergebnis in (TRAEGT_NICHT, OFFEN) else "ohne_beleg"
    return {
        "ergebnis": ergebnis, "status": status, "hinweis": hinweis,
        "stellen": [a["stelle"] for a in stellen],
        "behauptung": _ohne_marken(antwort.get("behauptung"), stellen),
        "entscheidung": _ohne_marken(antwort.get("entscheidung"), stellen),
        "begruendung": _ohne_marken(antwort.get("begruendung"), stellen),
        "schriftsatz_belege": schriftsatz_belege,
        "urteil_belege": urteil_belege,
    }


def gegenueberstellen(analyse: Analyse, akte_id: int, dokument_id: int | None = None,
                      nur_gespeichert: bool = False) -> dict:
    """Prüft jedes Urteilszitat der Akte bzw. des Dokuments. ``nur_gespeichert``: ohne Modell, nur die schon
    gespeicherten Ergebnisse (offene Zitate fehlen dann)."""
    from ..abgleich.abgleich import PARTEIEN

    eintraege = zitate(analyse.con, akte_id, dokument_id)
    texte: dict[int, belege.Text] = {}
    zeilen = []
    offen = 0
    for i, e in enumerate(eintraege, 1):
        did = e["zeile"]["dokument_id"]
        t = texte.get(did) or texte.setdefault(did, belege.lade_text(analyse.con, did, PARTEIEN))
        if not nur_gespeichert and e["urteil"] is not None:
            analyse.fortschritt.melde(f"Stelle {e['zeile']['zitat']} gegenüber", i, len(eintraege))
        z = _pruefe(analyse, t, e, nur_gespeichert)
        if z is None:
            offen += 1
            continue
        zeilen.append(z)
    return {"zitate": zeilen, "offen": offen, "anzahl": len(eintraege), "modell": analyse.modell}


def zur_frage(zeilen: list[dict], frage: str) -> list[dict]:
    """Nennt die Frage ein Aktenzeichen, nur die Zitate dieser Entscheidung; sonst alle."""
    genannt = [z for z in zeilen if z["aktenzeichen"] and az_kern(z["aktenzeichen"]).replace(" ", "").lower()
               in re.sub(r"\s+", "", frage).lower()]
    return genannt or zeilen
