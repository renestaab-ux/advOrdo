"""Prozesskostenrechner: Gerichtskosten nach GKG und Anwaltskosten nach RVG aus dem Streitwert (Zivilprozess).

Die Wertgebühren werden aus den Stufen von § 34 Abs. 1 GKG und § 13 Abs. 1 RVG gerechnet; die Tabellen in Anlage 2
GKG und Anlage 2 RVG sind nur deren Ausdruck. Jede Gebühr wird auf den Cent gerundet (§ 34 Abs. 2 S. 2 GKG,
§ 2 Abs. 2 S. 2 RVG), der Mindestbetrag einer Gebühr ist 15 € (§ 34 Abs. 2 S. 1 GKG, § 13 Abs. 3 RVG).

Zwei Fassungen sind hinterlegt: die seit 01.06.2025 (KostBRÄG 2025) und die vom 01.01.2021 bis 31.05.2025
(KostRÄG 2021). Welche gilt, richtet sich beim Anwalt nach dem Tag des unbedingten Auftrags (§ 60 RVG), bei den
Gerichtskosten nach der Anhängigkeit des Rechtszugs (§ 71 GKG).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal

from .verzugszinsen import betrag, cent

UNENDLICH = Decimal("Infinity")
MINDESTGEBUEHR = Decimal(15)
HOECHSTWERT = Decimal(30_000_000)  # § 39 Abs. 2 GKG, § 22 Abs. 2 S. 1 RVG
PAUSCHALE_SATZ = Decimal("0.2")  # Nr. 7002 VV RVG
PAUSCHALE_HOECHST = Decimal(20)
MEHRVERTRETUNG_SATZ = Decimal("0.3")  # Nr. 1008 VV RVG, je weiterer Auftraggeber
MEHRVERTRETUNG_HOECHST = Decimal(2)

# Je Fassung: Gebühr bis 500 € und die Stufen (Wert bis, je angefangene weitere, Erhöhung um).
FASSUNGEN = {
    "2025": {
        "titel": "seit 01.06.2025 (KostBRÄG 2025)",
        "fundstelle": "i. d. F. des KostBRÄG 2025, BGBl. 2025 I Nr. 109",
        "gkg": (Decimal(40), [
            (Decimal(2_000), Decimal(500), Decimal("21")),
            (Decimal(10_000), Decimal(1_000), Decimal("22.5")),
            (Decimal(25_000), Decimal(3_000), Decimal("30.5")),
            (Decimal(50_000), Decimal(5_000), Decimal("40.5")),
            (Decimal(200_000), Decimal(15_000), Decimal("140")),
            (Decimal(500_000), Decimal(30_000), Decimal("210")),
            (UNENDLICH, Decimal(50_000), Decimal("210")),
        ]),
        "rvg": (Decimal("51.5"), [
            (Decimal(2_000), Decimal(500), Decimal("41.5")),
            (Decimal(10_000), Decimal(1_000), Decimal("59.5")),
            (Decimal(25_000), Decimal(3_000), Decimal("55")),
            (Decimal(50_000), Decimal(5_000), Decimal("86")),
            (Decimal(200_000), Decimal(15_000), Decimal("99.5")),
            (Decimal(500_000), Decimal(30_000), Decimal("140")),
            (UNENDLICH, Decimal(50_000), Decimal("175")),
        ]),
    },
    "2021": {
        "titel": "01.01.2021 bis 31.05.2025 (KostRÄG 2021)",
        "fundstelle": "i. d. F. des KostRÄG 2021, BGBl. 2020 I S. 3229",
        "gkg": (Decimal(38), [
            (Decimal(2_000), Decimal(500), Decimal("20")),
            (Decimal(10_000), Decimal(1_000), Decimal("21")),
            (Decimal(25_000), Decimal(3_000), Decimal("29")),
            (Decimal(50_000), Decimal(5_000), Decimal("38")),
            (Decimal(200_000), Decimal(15_000), Decimal("132")),
            (Decimal(500_000), Decimal(30_000), Decimal("198")),
            (UNENDLICH, Decimal(50_000), Decimal("198")),
        ]),
        "rvg": (Decimal(49), [
            (Decimal(2_000), Decimal(500), Decimal("39")),
            (Decimal(10_000), Decimal(1_000), Decimal("56")),
            (Decimal(25_000), Decimal(3_000), Decimal("52")),
            (Decimal(50_000), Decimal(5_000), Decimal("81")),
            (Decimal(200_000), Decimal(15_000), Decimal("94")),
            (Decimal(500_000), Decimal(30_000), Decimal("132")),
            (UNENDLICH, Decimal(50_000), Decimal("165")),
        ]),
    },
}

# Je Rechtszug: Gerichtsgebühr (KV GKG) voll und ermäßigt, Anwaltsgebühren (VV RVG).
INSTANZEN = {
    "erste": {
        "titel": "Erste Instanz",
        "gericht": ("1210", Decimal(3), "1211", Decimal(1)),
        "verfahren": ("3100", Decimal("1.3")),
        "termin": ("3104", Decimal("1.2")),
        "einigung": ("1003", Decimal(1)),
    },
    "berufung": {
        "titel": "Berufung",
        "gericht": ("1220", Decimal(4), "1222", Decimal(2)),
        "verfahren": ("3200", Decimal("1.6")),
        "termin": ("3202", Decimal("1.2")),
        "einigung": ("1004", Decimal("1.3")),
    },
    "revision": {
        "titel": "Revision (BGH)",
        "gericht": ("1230", Decimal(5), "1232", Decimal(3)),
        "verfahren": ("3208", Decimal("2.3")),  # nur beim BGH zugelassener Anwalt
        "termin": ("3210", Decimal("1.5")),
        "einigung": ("1004", Decimal("1.3")),
    },
}
ENDEN = {
    "urteil": "durch Urteil",
    "vergleich": "durch Vergleich",
    "ruecknahme": "durch Rücknahme, Anerkenntnis oder Verzicht",
}


def wertgebuehr(wert: Decimal, grund: Decimal, stufen: list) -> Decimal:
    """Die volle (1,0-)Gebühr für einen Wert nach den Stufen von § 34 Abs. 1 GKG bzw. § 13 Abs. 1 RVG."""
    gebuehr, unten = grund, Decimal(500)
    for bis, schritt, plus in stufen:
        if wert <= unten:
            break
        spanne = min(wert, bis) - unten
        gebuehr += (spanne / schritt).to_integral_value(rounding=ROUND_CEILING) * plus
        unten = bis
    return gebuehr


def gebuehr(satz: Decimal, voll: Decimal) -> Decimal:
    return max(cent(satz * voll), MINDESTGEBUEHR)


@dataclass
class Rechtszug:
    instanz: str = "erste"
    ende: str = "urteil"
    termin: bool = True


@dataclass
class Eingabe:
    streitwert: Decimal
    fassung: str = "2025"
    rechtszuege: list[Rechtszug] = field(default_factory=lambda: [Rechtszug()])
    auftraggeber: int = 1
    geschaeftsgebuehr: Decimal | None = None  # Satz Nr. 2300 VV RVG, None = keine vorgerichtliche Tätigkeit
    gegner: bool = True
    umsatzsteuer: Decimal | None = Decimal(19)


def _zahl(d: Decimal) -> str:
    return format(d.normalize(), "f").replace(".", ",")


def _posten(nr: str, text: str, satz: Decimal | None, betrag_: Decimal) -> dict:
    return {"nr": nr, "text": text, "satz": None if satz is None else str(satz), "betrag": str(cent(betrag_))}


def _abrechnung(titel: str, posten: list[dict], ust: Decimal | None) -> dict:
    """Pauschale Nr. 7002, Umsatzsteuer Nr. 7008 und Summe zu einer Reihe von Gebühren."""
    gebuehren = sum((Decimal(p["betrag"]) for p in posten), Decimal(0))
    pauschale = min(cent(gebuehren * PAUSCHALE_SATZ), PAUSCHALE_HOECHST)
    posten = posten + [_posten("Nr. 7002 VV RVG", "Post- und Telekommunikationspauschale", None, pauschale)]
    netto = gebuehren + pauschale
    steuer = cent(netto * ust / 100) if ust else Decimal(0)
    if ust:
        posten.append(_posten("Nr. 7008 VV RVG", f"Umsatzsteuer {_zahl(ust)} %", None, steuer))
    return {"titel": titel, "posten": posten, "netto": str(cent(netto)), "summe": str(cent(netto + steuer))}


def _anwalt(i: dict, r: Rechtszug, voll_rvg: Decimal, mehr: Decimal, anrechnen: Decimal) -> list[dict]:
    """Anwaltsgebühren eines Rechtszugs: Verfahrens-, Termins- und Einigungsgebühr."""
    nr_v, satz_v = i["verfahren"]
    text_v = "Verfahrensgebühr" + (f" (Erhöhung {_zahl(mehr)}, Nr. 1008)" if mehr else "")
    liste = [_posten(f"Nr. {nr_v} VV RVG", text_v, satz_v + mehr, gebuehr(satz_v + mehr, voll_rvg))]
    if anrechnen:
        liste.append(_posten("Vorbem. 3 Abs. 4 VV RVG", "Anrechnung der Geschäftsgebühr", None, -anrechnen))
    if r.termin:
        nr_t, satz_t = i["termin"]
        liste.append(_posten(f"Nr. {nr_t} VV RVG", "Terminsgebühr", satz_t, gebuehr(satz_t, voll_rvg)))
    if r.ende == "vergleich":
        nr_e, satz_e = i["einigung"]
        liste.append(_posten(f"Nr. {nr_e} VV RVG", "Einigungsgebühr", satz_e, gebuehr(satz_e, voll_rvg)))
    return liste


def berechne(e: Eingabe) -> dict:
    if e.fassung not in FASSUNGEN:
        raise ValueError(f"Unbekannte Fassung: {e.fassung}")
    if e.streitwert <= 0:
        raise ValueError("Der Streitwert muss größer als 0 € sein.")
    if not e.rechtszuege:
        raise ValueError("Mindestens ein Rechtszug ist nötig.")
    f = FASSUNGEN[e.fassung]
    hinweise: list[str] = []
    wert = e.streitwert
    if wert > HOECHSTWERT:
        wert = HOECHSTWERT
        hinweise.append("Gerechnet mit dem Höchstwert von 30 Mio. € (§ 39 Abs. 2 GKG, § 22 Abs. 2 RVG).")
    voll_gkg = wertgebuehr(wert, *f["gkg"])
    voll_rvg = wertgebuehr(wert, *f["rvg"])
    auftraggeber = max(1, int(e.auftraggeber))
    erhoehung = min(MEHRVERTRETUNG_SATZ * (auftraggeber - 1), MEHRVERTRETUNG_HOECHST)
    ust = e.umsatzsteuer if e.umsatzsteuer and e.umsatzsteuer > 0 else None

    gericht: list[dict] = []
    eigene: list[dict] = []
    gegner: list[dict] = []
    grundlagen = [f"§ 34 GKG {f['fundstelle']}", f"§ 13 RVG {f['fundstelle']}", "KV GKG Teil 1 Hauptabschnitt 2",
                  "VV RVG Teil 3, Nr. 1000 ff., Nr. 7002, 7008"]

    vorgerichtlich = None
    anrechnung = Decimal(0)
    if e.geschaeftsgebuehr is not None and e.geschaeftsgebuehr > 0:
        satz = e.geschaeftsgebuehr + erhoehung
        text = "Geschäftsgebühr" + (f" (Satz {_zahl(e.geschaeftsgebuehr)} + Erhöhung {_zahl(erhoehung)}, Nr. 1008)"
                                     if erhoehung else "")
        geschaeft = gebuehr(satz, voll_rvg)
        vorgerichtlich = _abrechnung("Vorgerichtliche Tätigkeit", [_posten("Nr. 2300 VV RVG", text, satz, geschaeft)],
                                     ust)
        anrechnung = cent(min(satz / 2, Decimal("0.75")) * voll_rvg)
        if e.geschaeftsgebuehr > Decimal("1.3"):
            hinweise.append("Eine Geschäftsgebühr über 1,3 setzt eine umfangreiche oder schwierige Tätigkeit voraus "
                            "(Anm. zu Nr. 2300 VV RVG).")

    instanzen = []
    for r in e.rechtszuege:
        if r.instanz not in INSTANZEN or r.ende not in ENDEN:
            raise ValueError(f"Unbekannter Rechtszug: {r.instanz} / {r.ende}")
        i = INSTANZEN[r.instanz]
        nr_voll, satz_voll, nr_erm, satz_erm = i["gericht"]
        if r.ende == "urteil":
            nr, satz, text = nr_voll, satz_voll, "Verfahrensgebühr"
        else:
            nr, satz, text = nr_erm, satz_erm, "Verfahrensgebühr, ermäßigt"
        gericht.append(_posten(f"Nr. {nr} KV GKG", f"{i['titel']}: {text}", satz, gebuehr(satz, voll_gkg)))

        # Die Geschäftsgebühr wird nur auf die Verfahrensgebühr der ersten Instanz angerechnet.
        anrechnen = anrechnung if r.instanz == "erste" and not instanzen else Decimal(0)
        eigene.append(_abrechnung(i["titel"], _anwalt(i, r, voll_rvg, erhoehung, anrechnen), ust))
        if e.gegner:
            gegner.append(_abrechnung(i["titel"], _anwalt(i, r, voll_rvg, Decimal(0), Decimal(0)), ust))
        instanzen.append(r)

    if any(r.instanz == "revision" for r in e.rechtszuege):
        hinweise.append("Revision: Gebühren des beim BGH zugelassenen Anwalts (Nr. 3208 VV RVG).")
    if e.gegner:
        hinweise.append("Gegnerische Anwaltskosten: gleicher Verlauf, ein Auftraggeber, ohne vorgerichtliche "
                        "Tätigkeit.")

    summe_gericht = sum((Decimal(p["betrag"]) for p in gericht), Decimal(0))
    summe_eigene = sum((Decimal(a["summe"]) for a in eigene), Decimal(0))
    if vorgerichtlich:
        summe_eigene += Decimal(vorgerichtlich["summe"])
    summe_gegner = sum((Decimal(a["summe"]) for a in gegner), Decimal(0))
    return {
        "streitwert": str(cent(e.streitwert)),
        "fassung": e.fassung,
        "fassung_titel": f["titel"],
        "gebuehr_gkg": str(voll_gkg),
        "gebuehr_rvg": str(voll_rvg),
        "gericht": gericht,
        "vorgerichtlich": vorgerichtlich,
        "eigene": eigene,
        "gegner": gegner,
        "summe_gericht": str(cent(summe_gericht)),
        "summe_eigene": str(cent(summe_eigene)),
        "summe_gegner": str(cent(summe_gegner)),
        "kostenrisiko": str(cent(summe_gericht + summe_eigene + summe_gegner)),
        "umsatzsteuer": None if ust is None else str(ust),
        "hinweise": hinweise,
        "grundlagen": grundlagen,
    }


def aus_params(p: dict) -> Eingabe:
    """Eingabe aus den RPC-Parametern (Beträge als Text oder Zahl)."""
    gg = p.get("geschaeftsgebuehr")
    ust = p.get("umsatzsteuer", 19)
    return Eingabe(
        streitwert=betrag(p["streitwert"]),
        fassung=p.get("fassung", "2025"),
        rechtszuege=[Rechtszug(x.get("instanz", "erste"), x.get("ende", "urteil"), bool(x.get("termin", True)))
                     for x in p.get("rechtszuege") or [{}]],
        auftraggeber=int(p.get("auftraggeber") or 1),
        geschaeftsgebuehr=None if gg in (None, "") else betrag(gg),
        gegner=bool(p.get("gegner", True)),
        umsatzsteuer=None if ust in (None, "", False) else betrag(ust),
    )


def tabelle(fassung: str = "2025", bis: Decimal = Decimal(500_000)) -> list[tuple[Decimal, Decimal, Decimal]]:
    """Die Wertstufen mit voller Gebühr nach GKG und RVG, wie Anlage 2 GKG und Anlage 2 RVG (für die Tests)."""
    f = FASSUNGEN[fassung]
    zeilen, wert = [], Decimal(500)
    while wert <= bis:
        zeilen.append((wert, wertgebuehr(wert, *f["gkg"]), wertgebuehr(wert, *f["rvg"])))
        schritt = next(s for b, s, _ in f["rvg"][1] if wert < b)
        wert += schritt
    return zeilen


__all__ = ["FASSUNGEN", "INSTANZEN", "ENDEN", "Eingabe", "Rechtszug", "berechne", "aus_params", "wertgebuehr",
           "tabelle"]
