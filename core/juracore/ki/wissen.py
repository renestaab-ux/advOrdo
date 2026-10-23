"""Zusatzwissen für den KI-Chat: Rechner der Toolbox und Gesetze aus der Wissensbasis, beides zuschaltbar.

Rechner („Beleg vor Behauptung“): Das Modell rechnet nicht selbst. Es nennt nur die Angaben, die der Rechner
braucht (etwa Hauptforderung, Zinsbeginn, Zinssatz), jede mit Dokument, Absatz und wörtlichem Zitat. Die App prüft
das Zitat am Originaltext und, ob der Wert in diesem Absatz wirklich steht, und rechnet dann mit dem
Verzugszinsen- bzw. Fristenrechner der Toolbox. Angaben ohne Beleg werden so gekennzeichnet.

Gesetze: Die in der Akte zitierten Normen und die zur Frage passenden Treffer der Wissensbasis gehen mit Wortlaut
und Fassung in die Anfrage, begrenzt auf ``GESETZE_ZEICHEN``. Zitiert das Modell daraus, prüft die App das Zitat am
gespeicherten Wortlaut der Norm.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from ..abgleich.angaben import BETRAG, DATUM, finde_werte
from ..gesetze import wissensbasis
from ..gesetze.zitate import finde_zitate
from ..rechner import fristen, verzugszinsen
from ..rechner.basiszins import Basiszins
from . import belege

# Zeichen für Gesetzestexte in der Anfrage (rund 4.000 Token), damit bei 32k Kontext genug Platz für die Akte bleibt.
GESETZE_ZEICHEN = 12000
NORM_ZEICHEN = 3000  # je Norm; längere Normen werden gekürzt
SUCHTREFFER = 4  # Normen aus der Volltextsuche zusätzlich zu den zitierten
HOECHSTENS_BERECHNUNGEN = 2

ZINSEN = "zinsen"
FRIST = "frist"

# Fragen, bei denen der Rechner angeboten wird.
_RECHNEN = re.compile(r"zins|frist|rechn|berechn|wie\s+viel|wieviel|ablauf|läuft\s+ab|endet", re.I)

FELDER = {
    ZINSEN: {
        "hauptbetrag": "Hauptforderung",
        "zinsbeginn": "Zinsbeginn",
        "zinssatz": "Zinssatz",
        "bis": "Zinsen bis",
    },
    FRIST: {
        "bezugstag": "Fristauslösendes Ereignis",
        "dauer": "Fristdauer",
    },
}
PFLICHT = {ZINSEN: ("hauptbetrag", "zinsbeginn", "zinssatz"), FRIST: ("bezugstag", "dauer")}

SCHEMA_BERECHNUNG = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "rechner": {"type": "string", "enum": [ZINSEN, FRIST]},
            "angaben": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "feld": {"type": "string"},
                        "wert": {"type": "string"},
                        "dokument": {"type": "integer"},
                        "absatz": {"type": "integer"},
                        "zitat": {"type": "string"},
                    },
                    "required": ["feld", "wert", "dokument", "absatz", "zitat"],
                },
            },
        },
        "required": ["rechner", "angaben"],
    },
}

SCHEMA_NORMBELEGE = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"norm": {"type": "integer"}, "zitat": {"type": "string"}},
        "required": ["norm", "zitat"],
    },
}

ANWEISUNG_RECHNER = (
    "Rechnen: Rechne Zinsen oder Fristen nicht selbst und sage auch nicht, dass ein Basiszinssatz fehlt; das "
    "erledigt der Rechner der App. Verlangt die Frage eine solche Berechnung, trage unter \"berechnungen\" die "
    "Angaben aus den Dokumenten ein, jede mit Dokument, Absatz und wörtlichem Zitat, in dem der Wert steht:\n"
    "- rechner \"zinsen\": Felder \"hauptbetrag\" (z. B. \"12.500,00 €\"), \"zinsbeginn\" (TT.MM.JJJJ), "
    "\"zinssatz\" (wörtlich, z. B. \"5 Prozentpunkte über dem Basiszinssatz\" oder \"4 %\"), optional \"bis\" "
    "(TT.MM.JJJJ; ohne Angabe rechnet die App bis heute)\n"
    "- rechner \"frist\": Felder \"bezugstag\" (Tag des Ereignisses, das die Frist auslöst, TT.MM.JJJJ) und "
    "\"dauer\" (z. B. \"2 Wochen\", \"1 Monat\")\n"
    "Steht ein Wert nur in der Frage, nimm dokument 0 und absatz 0 und als Zitat die Stelle aus der Frage. "
    "Sonst lass \"berechnungen\" leer."
)


def soll_rechnen(frage: str) -> bool:
    return bool(_RECHNEN.search(frage))


# --- Rechner --------------------------------------------------------------------------------------

_ZAHLWOERTER = {
    "ein": 1, "einen": 1, "eine": 1, "einem": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6,
    "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "vierzehn": 14, "einundzwanzig": 21,
    "dreißig": 30,
}  # fmt: skip
_DAUER = re.compile(
    rf"(\d+|{'|'.join(_ZAHLWOERTER)})\s*-?\s*(tag|tage|tagen|woche|wochen|monat|monate|monaten|monats|jahr|jahre|jahren)\b",
    re.I,
)
_EINHEIT = {"tag": "tage", "woch": "wochen", "mona": "monate", "jahr": "jahre"}
_PROZENT = re.compile(r"(\d+(?:,\d+)?)\s*(?:%|prozent)", re.I)


def _dauer(text: str) -> tuple[int, str] | None:
    m = _DAUER.search(text)
    if not m:
        return None
    zahl = int(m[1]) if m[1].isdigit() else _ZAHLWOERTER[m[1].lower()]
    einheit = next(v for k, v in _EINHEIT.items() if m[2].lower().startswith(k))
    return zahl, einheit


def _datum(text: str) -> date | None:
    for w in finde_werte(text):
        if w.art == DATUM:
            return date.fromisoformat(w.wert)
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


def _betrag(text: str) -> Decimal | None:
    for w in finde_werte(text if re.search(r"€|EUR|Euro", text) else text + " €"):
        if w.art == BETRAG:
            return Decimal(w.wert)
    try:
        return verzugszinsen.betrag(text)
    except ValueError:
        return None


def _zinssatz(text: str) -> tuple[str, Decimal] | None:
    """("dynamisch", Prozentpunkte über dem Basiszinssatz) oder ("fest", Prozent)."""
    m = re.search(r"(\d+(?:,\d+)?)\s*(?:%-?\s*punkte|prozentpunkte|punkte|%|prozent)", text, re.I)
    if not m:
        return None
    zahl = Decimal(m[1].replace(",", "."))
    return ("dynamisch", zahl) if re.search(r"basiszins", text, re.I) else ("fest", zahl)


def _wert(rechner: str, feld: str, wert: str):
    """Der Wert in der Form, die der Rechner braucht, oder None, wenn er sich nicht lesen lässt."""
    if feld in ("zinsbeginn", "bis", "bezugstag"):
        return _datum(wert)
    if feld == "hauptbetrag":
        return _betrag(wert)
    if feld == "zinssatz":
        return _zinssatz(wert)
    if feld == "dauer":
        return _dauer(wert)
    return None


def _steht_im_text(feld: str, wert, text: str) -> bool:
    """Ob der gelesene Wert in dem Absatz steht, aus dem das Zitat stammt."""
    if wert is None:
        return False
    if feld in ("zinsbeginn", "bis", "bezugstag"):
        return any(w.art == DATUM and w.wert == wert.isoformat() for w in finde_werte(text))
    if feld == "hauptbetrag":
        return any(w.art == BETRAG and Decimal(w.wert) == wert for w in finde_werte(text))
    if feld == "zinssatz":
        art, zahl = wert
        zahlen = {Decimal(z.replace(",", ".")) for z in re.findall(r"\d+(?:,\d+)?", text)}
        zahlen |= {Decimal(_ZAHLWOERTER[w.lower()]) for w in re.findall(r"[a-zäöüß]+", text, re.I)
                   if w.lower() in _ZAHLWOERTER}
        return zahl in zahlen and (art == "fest" or bool(re.search(r"basiszins", text, re.I)))
    if feld == "dauer":
        return any(_dauer(m[0]) == wert for m in _DAUER.finditer(text))
    return False


def _anzeige(feld: str, wert) -> str:
    if feld in ("zinsbeginn", "bis", "bezugstag"):
        return f"{wert:%d.%m.%Y}"
    if feld == "hauptbetrag":
        return _euro(wert)
    if feld == "zinssatz":
        art, zahl = wert
        z = f"{zahl:f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{z} Prozentpunkte über dem Basiszinssatz" if art == "dynamisch" else f"{z} % (fester Satz)"
    if feld == "dauer":
        zahl, einheit = wert
        namen = {"tage": ("Tag", "Tage"), "wochen": ("Woche", "Wochen"), "monate": ("Monat", "Monate"),
                 "jahre": ("Jahr", "Jahre")}[einheit]
        return f"{zahl} {namen[0] if zahl == 1 else namen[1]}"
    return str(wert)


def _euro(betrag: Decimal | str) -> str:
    text = f"{Decimal(betrag):,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


# Beleg im Dokument: (Fundstelle, Text des Absatzes) oder None.
Belegen = Callable[[object, object, object], "tuple[dict, str] | None"]


def berechne(
    vorschlaege: object,
    belegen: Belegen,
    frage: str,
    heute: date,
    basiszins: Basiszins | None = None,
    land: str = "BY",
) -> list[dict]:
    """Prüft die Angaben des Modells und rechnet mit den Rechnern der Toolbox. Ergebnis je Berechnung."""
    ergebnisse = []
    for v in (vorschlaege if isinstance(vorschlaege, list) else [])[:HOECHSTENS_BERECHNUNGEN]:
        if not isinstance(v, dict) or v.get("rechner") not in FELDER:
            continue
        rechner = v["rechner"]
        felder = FELDER[rechner]
        eingaben: dict[str, dict] = {}
        for a in v.get("angaben") or []:
            if not isinstance(a, dict) or a.get("feld") not in felder or a["feld"] in eingaben:
                continue
            feld, roh = a["feld"], str(a.get("wert", "")).strip()
            wert = _wert(rechner, feld, roh)
            if wert is None and isinstance(a.get("zitat"), str):
                wert = _wert(rechner, feld, a["zitat"])
            if wert is None:
                continue
            eintrag = {"feld": feld, "titel": felder[feld], "wert": _anzeige(feld, wert), "_wert": wert,
                       "status": "ohne_beleg", "fundstelle": None, "quelle": None}
            if a.get("dokument") == 0:
                if _steht_im_text(feld, wert, frage):
                    eintrag.update(status="belegt", quelle="frage")
            elif (gefunden := belegen(a.get("dokument"), a.get("absatz"), a.get("zitat"))) is not None:
                fundstelle, absatztext = gefunden
                eintrag["fundstelle"] = fundstelle
                if _steht_im_text(feld, wert, absatztext):
                    eintrag["status"] = "belegt"
            eingaben[feld] = eintrag
        if rechner == ZINSEN and "bis" not in eingaben:
            eingaben["bis"] = {"feld": "bis", "titel": felder["bis"], "wert": f"{heute:%d.%m.%Y} (heute)",
                               "_wert": heute, "status": "belegt", "fundstelle": None, "quelle": "heute"}
        fehlt = [felder[f] for f in PFLICHT[rechner] if f not in eingaben]
        ergebnis: dict = {"rechner": rechner, "fehlt": fehlt, "ergebnis": None, "fehler": None}
        if not fehlt:
            try:
                ergebnis["ergebnis"] = _rechne(rechner, {k: e["_wert"] for k, e in eingaben.items()},
                                               basiszins, land)
            except (ValueError, ArithmeticError) as f:
                ergebnis["fehler"] = str(f)
        ergebnis["eingaben"] = [{k: x for k, x in e.items() if k != "_wert"}
                                for f in felder if (e := eingaben.get(f))]
        ergebnis["belegt"] = all(e["status"] == "belegt" for e in ergebnis["eingaben"])
        ergebnis["text"] = _satz(rechner, ergebnis, eingaben)
        if any(_gleich(ergebnis, x) for x in ergebnisse):
            continue
        ergebnisse.append(ergebnis)
    return ergebnisse


def _gleich(a: dict, b: dict) -> bool:
    return a["rechner"] == b["rechner"] and [e["wert"] for e in a["eingaben"]] == [e["wert"] for e in b["eingaben"]]


def _rechne(rechner: str, w: dict, basiszins: Basiszins | None, land: str) -> dict:
    if rechner == ZINSEN:
        art, zahl = w["zinssatz"]
        e = verzugszinsen.Eingabe(
            hauptbetrag=w["hauptbetrag"], beginn=w["zinsbeginn"], ende=w["bis"], art=art,
            punkte=zahl, fester_satz=zahl,
        )
        return verzugszinsen.berechne(e, basiszins)
    anzahl, einheit = w["dauer"]
    return fristen.berechne(w["bezugstag"], anzahl, einheit, land=land)


def _satz(rechner: str, ergebnis: dict, eingaben: dict[str, dict]) -> str:
    if ergebnis["fehlt"]:
        return ("Für die Berechnung fehlt in den Dokumenten: " + ", ".join(ergebnis["fehlt"]) + ".")
    if ergebnis["fehler"]:
        return f"Der Rechner konnte nicht rechnen: {ergebnis['fehler']}"
    r = ergebnis["ergebnis"]
    if rechner == ZINSEN:
        return (f"Zinsen auf {eingaben['hauptbetrag']['wert']} vom {eingaben['zinsbeginn']['wert']} bis "
                f"{eingaben['bis']['_wert']:%d.%m.%Y} ({eingaben['zinssatz']['wert']}): "
                f"{_euro(r['summe_zinsen'])}; Hauptforderung und Zinsen zusammen {_euro(r['gesamt'])}.")
    ende = date.fromisoformat(r["ende"])
    return (f"Frist von {eingaben['dauer']['wert']} ab {eingaben['bezugstag']['wert']}: Ende am "
            f"{r['wochentag']}, {ende:%d.%m.%Y}" + (f" (verschoben wegen {r['grund']})" if r["verschoben"] else "")
            + ".")


# --- Gesetze --------------------------------------------------------------------------------------

_FUELL = set("aber alle also auch bitte dann dass diese kannst kann können mir mich heute heutigen tag ausrechnen "
             "rechnen berechnen bitte welche welcher welches wann warum wurde wurden werden nach noch oder sind "
             "steht stehen akte dokument dokumente gilt".split())


def _suchwoerter(frage: str) -> list[str]:
    woerter = []
    for w in re.findall(r"[\wäöüß]{5,}", frage.lower()):
        if w not in _FUELL and not w.isdigit() and w[:6] not in woerter:
            woerter.append(w[:6])
    return woerter[:8]


def _norm_zeile(wb: sqlite3.Connection, norm_id: int) -> dict | None:
    z = wb.execute(
        """SELECT n.*, g.abk FROM norm n JOIN fassung f ON f.id = n.fassung_id JOIN gesetz g ON g.id = f.gesetz_id
           WHERE n.id = ?""", (norm_id,)).fetchone()
    if z is None or z["weggefallen"]:
        return None
    return wissensbasis.norm(wb, z["abk"], z["nummer"], z["fassung_id"], z["typ"])


def waehle_normen(
    wb: sqlite3.Connection, akten: sqlite3.Connection, akte_id: int, dokument_id: int | None, frage: str,
    zusaetzlich: list[str] | None = None, budget: int = GESETZE_ZEICHEN,
) -> tuple[list[dict], list[str]]:
    """Normen für die Anfrage: zuerst ``zusaetzlich`` (etwa § 288, § 247 BGB beim Zinsrechner), dann die in der
    Akte zitierten (häufigste zuerst), dann Treffer der Volltextsuche. Zweite Liste: zitierte Normen, die die
    Wissensbasis nicht enthält."""
    kandidaten: list[tuple[str, str, str]] = []  # Gesetz, Nummer, Typ
    fehlend: list[str] = []

    def dazu(zitat: str) -> None:
        for z in finde_zitate(zitat):
            schluessel = (z.gesetz.upper(), z.nummer, "artikel" if z.zeichen.startswith("Art") else "paragraph")
            if schluessel not in kandidaten:
                kandidaten.append(schluessel)

    for z in zusaetzlich or []:
        dazu(z)
    for z in akten.execute(
        """SELECT z.zitat, COUNT(*) AS n FROM normzitat z JOIN abschnitt a ON a.id = z.abschnitt_id
           JOIN dokument d ON d.id = a.dokument_id
           WHERE d.akte_id = ? AND (? IS NULL OR d.id = ?) AND z.status = 'belegt'
           GROUP BY z.zitat ORDER BY n DESC, z.zitat""", (akte_id, dokument_id, dokument_id)):
        dazu(z["zitat"])

    normen: list[dict] = []
    rest = budget

    def nimm(n: dict | None, herkunft: str) -> None:
        nonlocal rest
        if n is None or any(x["gesetz"] == n["gesetz"] and x["bezeichnung"] == n["bezeichnung"] for x in normen):
            return
        absaetze, laenge = [], 0
        for a in n["absaetze"]:
            text = " ".join(a["text"].split())
            if laenge + len(text) > NORM_ZEICHEN:
                text = text[: max(0, NORM_ZEICHEN - laenge)].rsplit(" ", 1)[0] + " …"
            absaetze.append({"nr": a["nr"], "text": text})
            laenge += len(text)
            if laenge >= NORM_ZEICHEN:
                break
        kopf = len(n["bezeichnung"]) + len(n["gesetz"]) + len(n.get("titel") or "") + 60
        if not absaetze or laenge + kopf > rest:
            return
        rest -= laenge + kopf
        normen.append({**n, "absaetze": absaetze, "herkunft": herkunft, "nr": len(normen) + 1})

    for gesetz, nummer, typ in kandidaten:
        n = wissensbasis.norm(wb, gesetz, nummer, typ=typ)
        if n is None:
            fehlend.append(f"{'Art.' if typ == 'artikel' else '§'} {nummer} {gesetz}")
        nimm(n, "zitiert")
    woerter = _suchwoerter(frage)
    if woerter:
        abfrage = " OR ".join(f'"{w}"*' for w in woerter)
        try:
            treffer = wb.execute(
                """SELECT n.id FROM norm_fts JOIN norm n ON n.id = norm_fts.rowid JOIN fassung f ON f.id = n.fassung_id
                   WHERE norm_fts MATCH ? AND f.id = (SELECT MAX(id) FROM fassung WHERE gesetz_id = f.gesetz_id)
                   ORDER BY bm25(norm_fts, 5.0, 3.0, 1.0) LIMIT ?""", (abfrage, SUCHTREFFER)).fetchall()
        except sqlite3.OperationalError:
            treffer = []
        for t in treffer:
            nimm(_norm_zeile(wb, t["id"]), "suche")
    return normen, fehlend


def _stand(n: dict) -> str:
    f = n["fassung"]
    stand = "; ".join(f.get("stand") or [])
    return stand or f"abgerufen {str(f.get('abgerufen_am', ''))[:10]}"


def normen_text(normen: list[dict]) -> str:
    teile = []
    for n in normen:
        kopf = f"[G{n['nr']}] {n['bezeichnung']} {n['gesetz']}" + (f" – {n['titel']}" if n.get("titel") else "")
        teile.append(kopf + f" (Fassung: {_stand(n)})\n" + "\n".join(a["text"] for a in n["absaetze"]))
    return "\n\n".join(teile)


ANWEISUNG_GESETZE = (
    "Gesetze: Die Normen oben (mit [G…] nummeriert) stammen aus der Wissensbasis der App, im Wortlaut der "
    "genannten Fassung. Stützt sich eine Einschätzung auf eine dieser Normen, belege sie unter \"normbelege\" mit "
    "der Nummer der Norm (die Zahl nach G) und einem wörtlichen Zitat aus ihrem Text (4 bis 25 Wörter). "
    "Andere Normen nennst du nur ohne Zitat."
)


def normbeleg(normen: list[dict], nr: object, zitat: object) -> dict | None:
    """Fundstelle eines Zitats aus einer vorgelegten Norm, geprüft am gespeicherten Wortlaut."""
    if not isinstance(zitat, str):
        return None
    reihenfolge = [n for n in normen if n["nr"] == nr] + [n for n in normen if n["nr"] != nr]
    for n in reihenfolge:
        absaetze = {i: a["text"] for i, a in enumerate(n["absaetze"])}
        fund = belege.finde(zitat, absaetze)
        if fund is None:
            continue
        a = n["absaetze"][fund.abschnitt]
        text = a["text"]
        von, bis = max(0, fund.start - belege.UMFELD), min(len(text), fund.ende + belege.UMFELD)
        nr_abs = f" Abs. {a['nr']}" if a["nr"] and len(n["absaetze"]) > 1 else ""
        return {
            "norm": f"{n['bezeichnung']}{nr_abs} {n['gesetz']}",
            "gesetz": n["gesetz"],
            "bezeichnung": n["bezeichnung"],
            "titel": n.get("titel"),
            "fassung": _stand(n),
            "fassung_id": n["fassung"]["id"],
            "treffer": fund.treffer,
            "ausschnitt": {
                "davor": ("… " if von > 0 else "") + text[von : fund.start].lstrip(),
                "wert": text[fund.start : fund.ende],
                "danach": text[fund.ende : bis].rstrip() + (" …" if bis < len(text) else ""),
            },
        }
    return None
