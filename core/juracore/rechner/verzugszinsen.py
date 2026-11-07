"""Verzugszinsenrechner nach §§ 288, 247 BGB, übernommen aus JuraBox Lite.

Rechenweg wie eine Zinsstaffel: Der Zeitraum wird an jedem Basiszinssatz-Stichtag und an jedem Zahlungsereignis
geteilt. Gerechnet wird ungerundet (Zeilen mit vier Nachkommastellen angezeigt); auf den Cent gerundet werden nur die
Endbeträge, wie bei basiszinssatz.de. Ereignisse (weitere Forderungen, Teilzahlungen, Raten)
wirken ab dem Folgetag. Kein Zinseszins auf aufgelaufene Zinsen.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .basiszins import Basiszins

CENT = Decimal("0.01")
VIER = Decimal("0.0001")  # Anzeige der ungerundeten Zwischenwerte
PAUSCHALE = Decimal(40)  # § 288 Abs. 5 S. 1 BGB
STICHTAG_2014 = date(2014, 7, 29)  # § 288 Abs. 2 BGB n. F., Art. 229 § 34 EGBGB
MAX_RATEN = 2400

ARTEN = {
    "verbraucher": "Verbrauchergeschäft (§ 288 Abs. 1 BGB): Basiszinssatz + 5 Prozentpunkte",
    "entgelt": "Entgeltforderung ohne Verbraucher (§ 288 Abs. 2 BGB): Basiszinssatz + 9 Prozentpunkte "
               "(+ 8 bei Verzugsbeginn vor dem 29.07.2014)",
    "dauerschuld": "Dauerschuldverhältnis (§ 288 Abs. 2 BGB, Art. 229 § 34 EGBGB): + 8 Prozentpunkte bis 28.07.2014, "
                   "danach + 9",
    "dynamisch": "Basiszinssatz + frei gewählte Prozentpunkte",
    "fest": "Fester Zinssatz, nicht an den Basiszinssatz gekoppelt",
}
VERRECHNUNG = {
    "zinsen_zuerst": "Zahlungen zuerst auf die Zinsen, dann auf die Hauptforderung (§ 367 Abs. 1 BGB)",
    "hauptschuld_zuerst": "Zahlungen zuerst auf die Hauptforderung, dann auf die Zinsen (§ 497 Abs. 3 S. 1 BGB)",
}


def cent(betrag: Decimal) -> Decimal:
    return betrag.quantize(CENT, rounding=ROUND_HALF_UP)


def genau(betrag: Decimal) -> str:
    return str(betrag.quantize(VIER, rounding=ROUND_HALF_UP))


def betrag(wert) -> Decimal:
    """Betrag aus Zahl oder Text; deutsches Komma und Tausenderpunkte erlaubt („1.234,56“, „10.000“)."""
    if isinstance(wert, (int, Decimal)):
        return Decimal(wert)
    text = str(wert).strip().replace("€", "").replace(" ", "")
    if "," in text or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except ArithmeticError as f:
        raise ValueError(f"Kein gültiger Betrag: {wert!r}") from f


@dataclass
class Ereignis:
    datum: date
    betrag: Decimal
    art: str  # "zugang" | "teilzahlung" | "rate"

    @property
    def wirkt_ab(self) -> date:
        return self.datum + timedelta(days=1)


@dataclass
class Eingabe:
    hauptbetrag: Decimal
    beginn: date
    ende: date
    art: str = "verbraucher"
    punkte: Decimal = Decimal(5)
    fester_satz: Decimal = Decimal(5)
    methode: str = "act/act"
    verrechnung: str = "zinsen_zuerst"
    pauschalen: int = 0
    ereignisse: list[Ereignis] = field(default_factory=list)


def plus_monate(tag: date, monate: int, wunschtag: int | None = None) -> date:
    """Kalendermonate addieren; fehlt der Tag im Zielmonat, gilt dessen letzter Tag (§ 188 Abs. 3 BGB)."""
    m = tag.month - 1 + monate
    jahr, monat = tag.year + m // 12, m % 12 + 1
    return date(jahr, monat, min(wunschtag or tag.day, calendar.monthrange(jahr, monat)[1]))


def raten(rate: Decimal, erstes: date, ende: date) -> list[Ereignis]:
    """Monatliche Raten am selben Kalendertag bis zum Ende."""
    folge = []
    for i in range(MAX_RATEN):
        tag = plus_monate(erstes, i, erstes.day)
        if tag > ende:
            break
        folge.append(Ereignis(tag, rate, "rate"))
    return folge


def _aufschlag(e: Eingabe, abschnitt_beginn: date) -> Decimal:
    if e.art == "verbraucher":
        return Decimal(5)
    if e.art == "entgelt":
        return Decimal(9) if e.beginn >= STICHTAG_2014 else Decimal(8)
    if e.art == "dauerschuld":
        return Decimal(9) if abschnitt_beginn >= STICHTAG_2014 else Decimal(8)
    if e.art == "dynamisch":
        return e.punkte
    raise ValueError(f"Unbekannte Geschäftsart: {e.art}")


def _satz(e: Eingabe, bz: Basiszins, abschnitt_beginn: date) -> tuple[Decimal, str]:
    if e.art == "fest":
        return e.fester_satz, "fester Satz"
    basis = bz.satz(abschnitt_beginn)
    aufschlag = _aufschlag(e, abschnitt_beginn)
    return basis + aufschlag, f"Basiszins {_de(basis)} % + {_de(aufschlag)} Pkt."


def _de(zahl: Decimal) -> str:
    return f"{zahl:.2f}".replace(".", ",")


def _tage_und_basis(methode: str, von: date, bis: date) -> tuple[int, Decimal]:
    if methode == "30E/360":
        nach = bis + timedelta(days=1)  # Ende exklusiv: 01.01.–30.06. = 180 Tage
        tage = 360 * (nach.year - von.year) + 30 * (nach.month - von.month) + (min(nach.day, 30) - min(von.day, 30))
        return tage, Decimal(360)
    tage = (bis - von).days + 1
    if methode == "act/act":
        return tage, Decimal(366 if calendar.isleap(von.year) else 365)
    basen = {"act/360": "360", "act/365": "365", "act/365.25": "365.25", "act/366": "366"}
    if methode not in basen:
        raise ValueError(f"Unbekannte Zinsmethode: {methode}")
    return tage, Decimal(basen[methode])


def berechne(e: Eingabe, bz: Basiszins | None = None) -> dict:
    bz = bz or Basiszins()
    if e.art not in ARTEN:
        raise ValueError(f"Unbekannte Geschäftsart: {e.art}")
    if e.verrechnung not in VERRECHNUNG:
        raise ValueError(f"Unbekannte Verrechnung: {e.verrechnung}")
    if e.ende < e.beginn:
        raise ValueError("Das Ende liegt vor dem Verzugsbeginn.")
    if e.hauptbetrag <= 0:
        raise ValueError("Die Hauptforderung muss größer als 0 sein.")

    # Ereignisse wirken ab dem Folgetag, und nur wenn dieser in (Verzugsbeginn, Ende] liegt.
    ereignisse = sorted((x for x in e.ereignisse if e.beginn < x.wirkt_ab <= e.ende),
                        key=lambda x: (x.wirkt_ab, x.art != "zugang"))
    grenzen = {x.wirkt_ab for x in ereignisse}
    if e.art != "fest":
        grenzen |= {t for t in bz.stichtage() if e.beginn < t <= e.ende}
    if e.art == "dauerschuld" and e.beginn < STICHTAG_2014 <= e.ende:
        grenzen.add(STICHTAG_2014)
    if e.methode == "act/act":  # kalendergenau: Jahresbasis je Kalenderjahr
        grenzen |= {date(j, 1, 1) for j in range(e.beginn.year + 1, e.ende.year + 1)}
    anfaenge = [e.beginn, *sorted(grenzen)]

    rest, zinssaldo, summe = e.hauptbetrag, Decimal(0), Decimal(0)
    zeilen = []
    satz, basis = Decimal(0), Decimal(365)
    for i, von in enumerate(anfaenge):
        bis = anfaenge[i + 1] - timedelta(days=1) if i + 1 < len(anfaenge) else e.ende
        texte = []
        for x in (x for x in ereignisse if x.wirkt_ab == von):
            if x.art == "zugang":
                rest += x.betrag
                texte.append(f"weitere Forderung {_de(x.betrag)} € vom {x.datum:%d.%m.%Y}")
                continue
            zahlung = x.betrag
            if e.verrechnung == "zinsen_zuerst":
                auf_zinsen = min(zahlung, zinssaldo)
                auf_haupt = min(zahlung - auf_zinsen, rest)
            else:
                auf_haupt = min(zahlung, rest)
                auf_zinsen = min(zahlung - auf_haupt, zinssaldo)
            zinssaldo -= auf_zinsen
            rest -= auf_haupt
            name = "Ratenzahlung" if x.art == "rate" else "Teilzahlung"
            texte.append(f"{name} {_de(zahlung)} € vom {x.datum:%d.%m.%Y} "
                         f"(auf Zinsen {_de(auf_zinsen)} €, auf Hauptforderung {_de(auf_haupt)} €)")
        satz, grundlage = _satz(e, bz, von)
        tage, basis = _tage_und_basis(e.methode, von, bis)
        if rest <= Decimal("0.005"):
            if texte:
                zeilen.append({"von": von.isoformat(), "bis": bis.isoformat(), "tage": 0, "satz": str(satz),
                               "grundlage": grundlage, "zinsen": genau(Decimal(0)), "zinssaldo": genau(zinssaldo),
                               "restschuld": str(cent(rest)), "ereignis": "; ".join(texte)})
            if zinssaldo <= Decimal("0.005"):
                break
            continue
        zinsen = rest * satz / 100 * tage / basis if satz > 0 else Decimal(0)
        zinssaldo += zinsen
        summe += zinsen
        zeilen.append({"von": von.isoformat(), "bis": bis.isoformat(), "tage": tage, "satz": str(satz),
                       "grundlage": grundlage, "zinsen": genau(zinsen), "zinssaldo": genau(zinssaldo),
                       "restschuld": str(cent(rest)), "ereignis": "; ".join(texte)})

    pauschale = PAUSCHALE * e.pauschalen
    bekannt_bis = Basiszins.bekannt_bis(bz.letzter()[0])
    hinweise = []
    if e.art != "fest" and e.ende > bekannt_bis:
        hinweise.append(f"Der Basiszinssatz ist nur bis {bekannt_bis:%d.%m.%Y} hinterlegt; danach wurde der letzte "
                        f"bekannte Satz ({_de(bz.letzter()[1])} %) weiterverwendet. Neuere Sätze lassen sich in der "
                        "Toolbox eintragen.")
    if satz < 0:
        hinweise.append("Der Zinssatz war zeitweise negativ; für diese Zeilen wurden keine Zinsen angesetzt.")
    pro_tag = genau(rest * max(satz, Decimal(0)) / 100 / basis)
    return {
        "zeilen": zeilen,
        "summe_tage": sum(z["tage"] for z in zeilen),
        "summe_zinsen": str(cent(summe)),
        "summe_zinsen_genau": genau(summe),
        "pauschale": str(cent(pauschale)),
        "hauptforderung": str(cent(rest)),
        "offene_zinsen": str(cent(zinssaldo)),
        "gesamt": str(cent(rest + zinssaldo + pauschale)),
        "aktueller_satz": str(satz),
        "zinsen_pro_tag": pro_tag,
        "grundlagen": _grundlagen(e),
        "basiszins_quelle": f"{bz.letzter()[0]:%d.%m.%Y}: {_de(bz.letzter()[1])} %",
        "hinweise": hinweise,
    }


def _grundlagen(e: Eingabe) -> list[str]:
    g = {"verbraucher": ["§ 288 Abs. 1 BGB", "§ 247 BGB"],
         "entgelt": ["§ 288 Abs. 2 BGB", "§ 247 BGB"],
         "dauerschuld": ["§ 288 Abs. 2 BGB", "§ 247 BGB", "Art. 229 § 34 EGBGB"],
         "dynamisch": ["§ 247 BGB"],
         "fest": []}[e.art]
    if e.pauschalen:
        g.append("§ 288 Abs. 5 BGB")
    if any(x.art != "zugang" for x in e.ereignisse):
        g.append("§ 367 Abs. 1 BGB" if e.verrechnung == "zinsen_zuerst" else "§ 497 Abs. 3 BGB")
    return g


def aus_params(p: dict) -> Eingabe:
    """Eingabe aus den RPC-Parametern (Beträge als Text oder Zahl, Daten als JJJJ-MM-TT)."""
    ende = date.fromisoformat(p["ende"])
    ereignisse = [Ereignis(date.fromisoformat(x["datum"]), betrag(x["betrag"]), "zugang")
                  for x in p.get("zugaenge") or []]
    ereignisse += [Ereignis(date.fromisoformat(x["datum"]), betrag(x["betrag"]), "teilzahlung")
                   for x in p.get("teilzahlungen") or []]
    if (r := p.get("rate")) and r.get("betrag") and r.get("erstes"):
        ereignisse += raten(betrag(r["betrag"]), date.fromisoformat(r["erstes"]), ende)
    return Eingabe(
        hauptbetrag=betrag(p["hauptbetrag"]),
        beginn=date.fromisoformat(p["beginn"]),
        ende=ende,
        art=p.get("art", "verbraucher"),
        punkte=betrag(p.get("punkte", 5)),
        fester_satz=betrag(p.get("fester_satz", 5)),
        methode=p.get("methode", "act/act"),
        verrechnung=p.get("verrechnung", "zinsen_zuerst"),
        pauschalen=int(p.get("pauschalen") or 0),
        ereignisse=ereignisse,
    )
