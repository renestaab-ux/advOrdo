import json
from decimal import Decimal

import pytest

from juracore import rpc
from juracore.rechner import prozesskosten
from juracore.rechner.prozesskosten import Eingabe, Rechtszug, berechne, wertgebuehr

# Auszug aus Anlage 2 GKG und Anlage 2 RVG, Fassung seit 01.06.2025 (BGBl. 2025 I Nr. 109), gesetze-im-internet.de.
ANLAGE_2025 = {
    500: ("40", "51.5"), 1_000: ("61", "93"), 1_500: ("82", "134.5"), 2_000: ("103", "176"),
    3_000: ("125.5", "235.5"), 5_000: ("170.5", "354.5"), 10_000: ("283", "652"), 13_000: ("313.5", "707"),
    25_000: ("435.5", "927"), 30_000: ("476", "1013"), 50_000: ("638", "1357"), 65_000: ("778", "1456.5"),
    200_000: ("2038", "2352"), 230_000: ("2248", "2492"), 500_000: ("4138", "3752"),
}


@pytest.mark.parametrize("wert", ANLAGE_2025)
def test_wie_anlage_2_seit_2025(wert):
    f = prozesskosten.FASSUNGEN["2025"]
    gkg, rvg = ANLAGE_2025[wert]
    assert wertgebuehr(Decimal(wert), *f["gkg"]) == Decimal(gkg)
    assert wertgebuehr(Decimal(wert), *f["rvg"]) == Decimal(rvg)


# Anlage 2 GKG und Anlage 2 RVG vollständig (Fassung seit 01.06.2025), Spalten: Wert bis, GKG, RVG.
ANLAGE_2025_VOLL = """
500 40 51.5|1000 61 93|1500 82 134.5|2000 103 176|3000 125.5 235.5|4000 148 295|5000 170.5 354.5|6000 193 414
7000 215.5 473.5|8000 238 533|9000 260.5 592.5|10000 283 652|13000 313.5 707|16000 344 762|19000 374.5 817
22000 405 872|25000 435.5 927|30000 476 1013|35000 516.5 1099|40000 557 1185|45000 597.5 1271|50000 638 1357
65000 778 1456.5|80000 918 1556|95000 1058 1655.5|110000 1198 1755|125000 1338 1854.5|140000 1478 1954
155000 1618 2053.5|170000 1758 2153|185000 1898 2252.5|200000 2038 2352|230000 2248 2492|260000 2458 2632
290000 2668 2772|320000 2878 2912|350000 3088 3052|380000 3298 3192|410000 3508 3332|440000 3718 3472
470000 3928 3612|500000 4138 3752
"""


def test_ganze_tabelle_seit_2025():
    erwartet = [tuple(Decimal(x) for x in z.split()) for z in ANLAGE_2025_VOLL.replace("\n", "|").split("|") if z]
    assert prozesskosten.tabelle("2025") == erwartet


def test_angefangene_stufe_und_ueber_500000():
    f = prozesskosten.FASSUNGEN["2025"]
    assert wertgebuehr(Decimal("500.01"), *f["rvg"]) == Decimal(93)
    assert wertgebuehr(Decimal(2001), *f["gkg"]) == Decimal("125.5")
    # 550.000 €: eine weitere Stufe zu 50.000 €
    assert wertgebuehr(Decimal(550_000), *f["gkg"]) == Decimal(4348)
    assert wertgebuehr(Decimal(550_000), *f["rvg"]) == Decimal(3927)


def test_fassung_2021():
    f = prozesskosten.FASSUNGEN["2021"]
    assert wertgebuehr(Decimal(10_000), *f["gkg"]) == Decimal(266)
    assert wertgebuehr(Decimal(10_000), *f["rvg"]) == Decimal(614)
    assert wertgebuehr(Decimal(500_000), *f["rvg"]) == Decimal(3539)


def test_erste_instanz_mit_urteil():
    # 10.000 €: 3,0 × 283 = 849 €; Anwalt 1,3 × 652 = 847,60 + 1,2 × 652 = 782,40 + 20 = 1.650 netto, 313,50 USt.
    e = berechne(Eingabe(Decimal(10_000)))
    assert e["summe_gericht"] == "849.00"
    assert [p["betrag"] for p in e["eigene"][0]["posten"]] == ["847.60", "782.40", "20.00", "313.50"]
    assert e["summe_eigene"] == "1963.50" and e["summe_gegner"] == "1963.50"
    assert e["kostenrisiko"] == "4776.00"


def test_alte_fassung_erste_instanz():
    e = berechne(Eingabe(Decimal(10_000), fassung="2021"))
    assert (e["summe_gericht"], e["summe_eigene"]) == ("798.00", "1850.45")


def test_vergleich_ermaessigt_und_einigungsgebuehr():
    e = berechne(Eingabe(Decimal(5_000), rechtszuege=[Rechtszug("erste", "vergleich")], gegner_anwaelte=[]))
    assert e["gericht"][0]["nr"] == "Nr. 1211 KV GKG" and e["summe_gericht"] == "170.50"
    posten = {p["nr"]: p["betrag"] for p in e["eigene"][0]["posten"]}
    assert posten["Nr. 1003 VV RVG"] == "354.50"
    assert e["summe_gegner"] == "0.00"


def test_vorgerichtlich_mit_anrechnung_und_mehrvertretung():
    # 10.000 €, zwei Auftraggeber: Geschäftsgebühr 1,6 × 652 = 1.043,20; angerechnet 0,75 × 652 = 489,00.
    e = berechne(Eingabe(Decimal(10_000), auftraggeber=2, geschaeftsgebuehr=Decimal("1.3"), umsatzsteuer=None))
    assert e["vorgerichtlich"]["posten"][0]["betrag"] == "1043.20"
    posten = e["eigene"][0]["posten"]
    assert posten[0]["satz"] == "1.6" and posten[0]["betrag"] == "1043.20"
    assert posten[1]["betrag"] == "-489.00"
    assert e["eigene"][0]["netto"] == str(Decimal("1043.20") - 489 + Decimal("782.40") + 20)


def test_drei_gegner_mit_gemeinsamem_anwalt():
    # 10.000 €: Verfahrensgebühr 1,3 + 2 × 0,3 = 1,9 × 652 = 1.238,80 + 782,40 + 20 = 2.041,20 netto, 387,83 USt.
    e = berechne(Eingabe(Decimal(10_000), gegner_anwaelte=[3]))
    a = e["gegner"][0]
    assert (a["posten"][0]["satz"], a["posten"][0]["betrag"]) == ("1.9", "1238.80")
    assert (a["summe"], a["anzahl"], e["summe_gegner"]) == ("2429.03", 1, "2429.03")
    assert "3 Gegner" in a["titel"]


def test_drei_gegner_mit_eigenen_anwaelten():
    e = berechne(Eingabe(Decimal(10_000), gegner_anwaelte=[1, 1, 1]))
    assert len(e["gegner"]) == 1 and e["gegner"][0]["anzahl"] == 3
    assert e["summe_gegner"] == "5890.50"  # 3 × 1.963,50
    assert e["kostenrisiko"] == str(Decimal("849.00") + Decimal("1963.50") + Decimal("5890.50"))
    assert any("§ 91 Abs. 2 ZPO" in h for h in e["hinweise"])
    assert any("3 Gegner, 3 Anwälte" in h for h in e["hinweise"])


def test_gegner_aus_params():
    a = prozesskosten.aus_params
    assert a({"streitwert": 1}).gegner_anwaelte == [1]
    assert a({"streitwert": 1, "gegner": False, "gegner_anzahl": 3}).gegner_anwaelte == []
    assert a({"streitwert": 1, "gegner_anzahl": 3}).gegner_anwaelte == [3]
    assert a({"streitwert": 1, "gegner_anzahl": 3, "gegner_getrennt": True}).gegner_anwaelte == [1, 1, 1]
    # gemischt: ein Anwalt für zwei Gegner (1,6 × 652 + 782,40 + 20 = 1.845,60 + 350,66 USt), einer für den dritten
    e = berechne(a({"streitwert": "10.000", "gegner_anwaelte": [2, 1]}))
    assert [g["anzahl"] for g in e["gegner"]] == [1, 1]
    assert e["summe_gegner"] == str(Decimal("2196.26") + Decimal("1963.50"))


def test_drei_rechtszuege():
    e = berechne(Eingabe(Decimal(10_000), rechtszuege=[
        Rechtszug("erste"), Rechtszug("berufung"), Rechtszug("revision", "ruecknahme", termin=False)]))
    assert [p["nr"] for p in e["gericht"]] == ["Nr. 1210 KV GKG", "Nr. 1220 KV GKG", "Nr. 1232 KV GKG"]
    assert [p["betrag"] for p in e["gericht"]] == ["849.00", "1132.00", "849.00"]
    assert e["eigene"][2]["posten"][0] == {"nr": "Nr. 3208 VV RVG", "text": "Verfahrensgebühr", "satz": "2.3",
                                           "betrag": "1499.60"}


def test_hoechstwert_und_fehler():
    e = berechne(Eingabe(Decimal(50_000_000)))
    assert any("30 Mio" in h for h in e["hinweise"])
    with pytest.raises(ValueError):
        berechne(Eingabe(Decimal(0)))


def test_rpc(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")

    def rufe(**params):
        return kern.bearbeite(json.dumps({"id": 1, "method": "rechner.prozesskosten", "params": params}))

    erg = rufe(streitwert="10.000,00", rechtszuege=[{"instanz": "erste", "ende": "urteil", "termin": True}])
    assert erg["result"]["kostenrisiko"] == "4776.00"
    assert "error" in rufe(streitwert="x")
    # Tausenderpunkt ohne Komma, wie man ihn eintippt
    assert rufe(streitwert="10.000")["result"]["streitwert"] == "10000.00"
