import json
from datetime import date
from decimal import Decimal

import pytest

from juracore import rpc
from juracore.rechner import basiszins, feiertage, fristen, verzugszinsen
from juracore.rechner.verzugszinsen import Eingabe, Ereignis, berechne


def test_basiszins_historie():
    b = basiszins.Basiszins()
    assert b.satz(date(2024, 3, 1)) == Decimal("3.62")
    assert b.satz(date(2024, 7, 1)) == Decimal("3.37")
    assert b.satz(date(2020, 1, 1)) == Decimal("-0.88")
    assert b.satz(date(2001, 1, 1)) == Decimal("2.47")  # vor dem ersten Eintrag gilt der erste


def test_verbraucher_ein_jahr_kalendergenau():
    # 2024 ist ein Schaltjahr: 1.000 € × 8,62 % × 182/366 = 42,864… und × 8,37 % × 184/366 = 42,078…
    e = berechne(Eingabe(Decimal(1000), date(2024, 1, 1), date(2024, 12, 31)))
    assert [(z["von"], z["tage"], z["satz"], z["zinsen"]) for z in e["zeilen"]] == [
        ("2024-01-01", 182, "8.62", "42.8645"),
        ("2024-07-01", 184, "8.37", "42.0787"),
    ]
    assert e["summe_tage"] == 366 and e["summe_zinsen"] == "84.94" and e["gesamt"] == "1084.94"
    assert e["zinsen_pro_tag"] == "0.2287"
    assert e["grundlagen"] == ["§ 288 Abs. 1 BGB", "§ 247 BGB"]


def test_wie_basiszinssatz_de():
    # Kontrollrechnung von René mit basiszinssatz.de (18.10.2026): 2.000 €, Handelsgeschäft, 15.01.2015–18.10.2026.
    e = berechne(Eingabe(Decimal(2000), date(2015, 1, 15), date(2026, 10, 18), art="entgelt"))
    assert [(z["tage"], z["satz"], z["zinsen"]) for z in (e["zeilen"][0], e["zeilen"][-1])] == [
        (167, "8.17", "74.7611"), (110, "10.52", "63.4082")]
    assert (e["summe_tage"], e["summe_zinsen_genau"], e["gesamt"]) == (4295, "2152.4214", "4152.42")
    assert e["zinsen_pro_tag"] == "0.5764"


def test_entgelt_weiche_2014_und_pauschale():
    alt = berechne(Eingabe(Decimal(1000), date(2014, 1, 2), date(2014, 1, 31), art="entgelt", pauschalen=1))
    assert alt["zeilen"][0]["satz"] == "7.37"  # −0,63 + 8
    neu = berechne(Eingabe(Decimal(1000), date(2014, 8, 1), date(2014, 8, 31), art="entgelt"))
    assert neu["zeilen"][0]["satz"] == "8.27"  # −0,73 + 9
    assert alt["pauschale"] == "40.00" and "§ 288 Abs. 5 BGB" in alt["grundlagen"]


def test_dauerschuld_teilt_am_29_juli_2014():
    e = berechne(Eingabe(Decimal(1000), date(2014, 7, 1), date(2014, 8, 31), art="dauerschuld"))
    assert [(z["von"], z["bis"], z["satz"]) for z in e["zeilen"]] == [
        ("2014-07-01", "2014-07-28", "7.27"), ("2014-07-29", "2014-08-31", "8.27")]


def test_30e_360_und_fester_satz():
    e = berechne(Eingabe(Decimal(1000), date(2025, 1, 1), date(2025, 6, 30), art="fest",
                         fester_satz=Decimal(6), methode="30E/360"))
    (z,) = e["zeilen"]
    assert (z["tage"], z["zinsen"]) == (180, "30.0000")


def test_teilzahlung_zuerst_auf_zinsen_ab_folgetag():
    e = berechne(Eingabe(Decimal(1000), date(2025, 1, 1), date(2025, 3, 31), art="fest", fester_satz=Decimal(10),
                         ereignisse=[Ereignis(date(2025, 1, 31), Decimal(100), "teilzahlung")]))
    erste, zweite = e["zeilen"]
    # 31 Tage auf 1.000 € = 8,4932 € Zinsen; am Zahltag gilt noch der alte Stand.
    assert (erste["bis"], erste["tage"], erste["zinsen"]) == ("2025-01-31", 31, "8.4932")
    assert zweite["von"] == "2025-02-01" and zweite["restschuld"] == "908.49"
    assert "auf Zinsen 8,49 €" in zweite["ereignis"]
    assert "§ 367 Abs. 1 BGB" in e["grundlagen"]

    h = berechne(Eingabe(Decimal(1000), date(2025, 1, 1), date(2025, 3, 31), art="fest", fester_satz=Decimal(10),
                         verrechnung="hauptschuld_zuerst",
                         ereignisse=[Ereignis(date(2025, 1, 31), Decimal(100), "teilzahlung")]))
    assert h["zeilen"][1]["restschuld"] == "900.00"


def test_raten_und_vollstaendige_tilgung():
    folge = verzugszinsen.raten(Decimal(500), date(2025, 1, 31), date(2025, 4, 30))
    assert [r.datum for r in folge] == [date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31), date(2025, 4, 30)]
    e = berechne(Eingabe(Decimal(1000), date(2025, 1, 1), date(2025, 12, 31), art="fest", ereignisse=folge))
    assert e["hauptforderung"] == "0.00" and e["offene_zinsen"] == "0.00"
    assert e["zinsen_pro_tag"] == "0.0000"


def test_eingaben_und_fehler():
    assert verzugszinsen.betrag("1.234,56 €") == Decimal("1234.56")
    assert verzugszinsen.betrag("1234.5") == Decimal("1234.5")
    assert verzugszinsen.betrag("10.000") == Decimal(10000)  # Tausenderpunkt ohne Komma
    with pytest.raises(ValueError):
        verzugszinsen.betrag("abc")
    with pytest.raises(ValueError):
        berechne(Eingabe(Decimal(1000), date(2025, 2, 1), date(2025, 1, 1)))


def test_hinweis_wenn_basiszins_nicht_hinterlegt():
    e = berechne(Eingabe(Decimal(1000), date(2026, 12, 1), date(2027, 2, 1)))
    assert "nur bis 31.12.2026 hinterlegt" in e["hinweise"][0]
    eigen = basiszins.Basiszins([(date(2027, 1, 1), Decimal("2.00"))])
    e = berechne(Eingabe(Decimal(1000), date(2026, 12, 1), date(2027, 2, 1)), eigen)
    assert e["zeilen"][-1]["satz"] == "7.00" and e["hinweise"] == []


def test_basiszins_eintragen(tmp_path):
    datei = tmp_path / "basiszins.json"
    with pytest.raises(ValueError):
        basiszins.eintragen(datei, "2027-02-01", "2")
    with pytest.raises(ValueError):
        basiszins.eintragen(datei, "2026-07-01", "2")  # hinterlegt, wird nie überschrieben
    s = basiszins.eintragen(datei, "2027-01-01", "1,77")
    assert s["aktuell"] == {"ab": "2027-01-01", "satz": "1.77"} and s["saetze"][-1]["eigen"]
    assert basiszins.entfernen(datei, "2027-01-01")["aktuell"]["ab"] == "2026-07-01"


@pytest.mark.parametrize("jahr, ostern", [(2024, date(2024, 3, 31)), (2026, date(2026, 4, 5)),
                                          (2027, date(2027, 3, 28)), (2038, date(2038, 4, 25))])
def test_ostern(jahr, ostern):
    assert feiertage.ostersonntag(jahr) == ostern


def test_feiertage_je_land():
    assert feiertage.feiertage(2026, "SN")[date(2026, 11, 18)] == "Buß- und Bettag"
    assert date(2026, 6, 4) in feiertage.feiertage(2026, "BY")  # Fronleichnam
    assert date(2026, 6, 4) not in feiertage.feiertage(2026, "BE")
    assert date(2026, 3, 8) in feiertage.feiertage(2026, "BE")
    assert date(2018, 3, 8) not in feiertage.feiertage(2018, "BE")  # erst seit 2019
    assert date(2017, 10, 31) in feiertage.feiertage(2017, "BY")  # einmalig bundesweit
    assert date(2026, 8, 15) not in feiertage.feiertage(2026, "BY")
    assert date(2026, 8, 15) in feiertage.feiertage(2026, "BY", maria_himmelfahrt_bayern=True)


def test_frist_wochen_mit_193():
    # Samstag + 2 Wochen = Samstag 31.10.2026 → Montag 02.11.2026.
    f = fristen.berechne(date(2026, 10, 17), 2, "wochen", land="SN")
    assert (f["fristbeginn"], f["rechnerisches_ende"], f["ende"]) == ("2026-10-18", "2026-10-31", "2026-11-02")
    assert f["grund"] == "Samstag, Sonntag" and f["wochentag"] == "Montag"
    assert f["grundlagen"] == ["§ 187 Abs. 1 BGB", "§ 188 Abs. 2 BGB", "§ 193 BGB"]


def test_frist_feiertag_und_monatsende():
    f = fristen.berechne(date(2026, 3, 22), 2, "wochen", land="NW")  # 05.04.2026 Ostersonntag
    assert f["ende"] == "2026-04-07" and f["grund"] == "Sonntag, Ostermontag"
    f = fristen.berechne(date(2026, 1, 31), 1, "monate", paragraf_193=False)
    assert f["ende"] == "2026-02-28" and "§ 188 Abs. 3 BGB" in f["grundlagen"]


def test_frist_bayern_mariae_himmelfahrt():
    # Kontrollrechnung von René mit lto.de (Bayern kath.): 15.07.2024 + 1 Monat = Do 15.08.2024 → Fr 16.08.2024.
    f = fristen.berechne(date(2024, 7, 15), 1, "monate", land="BY")
    assert (f["fristbeginn"], f["wochentag_fristbeginn"]) == ("2024-07-16", "Dienstag")
    assert (f["rechnerisches_ende"], f["wochentag_rechnerisch"]) == ("2024-08-15", "Donnerstag")
    assert (f["ende"], f["wochentag"], f["grund"]) == ("2024-08-16", "Freitag", "Mariä Himmelfahrt")
    assert "ohne überwiegend katholische Bevölkerung endet die Frist am Donnerstag, 15.08.2024" in f["hinweise"][0]
    ohne = fristen.berechne(date(2024, 7, 15), 1, "monate", land="BY", maria_himmelfahrt_bayern=False)
    assert ohne["ende"] == "2024-08-15" and "16.08.2024" in ohne["hinweise"][0]
    assert fristen.berechne(date(2024, 7, 15), 2, "wochen", land="BY")["hinweise"] == []


def test_frist_tagesbeginn():
    f = fristen.berechne(date(2026, 1, 1), 1, "jahre", beginn="tagesbeginn")
    assert (f["fristbeginn"], f["ende"]) == ("2026-01-01", "2026-12-31")


def test_frist_tagesbeginn_am_monatsende():
    """§ 188 Abs. 2 Alt. 2, Abs. 3 BGB: Fehlt der entsprechende Tag, endet die Frist am Monatsletzten."""
    def ende(tag, anzahl=1, einheit="monate"):
        return fristen.berechne(tag, anzahl, einheit, beginn="tagesbeginn", paragraf_193=False)["rechnerisches_ende"]

    assert ende(date(2026, 1, 31)) == "2026-02-28"
    assert ende(date(2026, 1, 30)) == "2026-02-28"
    assert ende(date(2026, 1, 29)) == "2026-02-28"
    assert ende(date(2026, 1, 28)) == "2026-02-27"
    assert ende(date(2028, 1, 31)) == "2028-02-29"  # Schaltjahr
    assert ende(date(2026, 3, 31)) == "2026-04-30"
    assert ende(date(2026, 3, 1)) == "2026-03-31"
    assert ende(date(2024, 2, 29), 1, "jahre") == "2025-02-28"
    assert ende(date(2026, 8, 31), 6) == "2027-02-28"


def test_rpc(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")

    def rufe(methode, **params):
        return kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))

    z = rufe("rechner.verzugszinsen", hauptbetrag="1.000,00", beginn="2024-01-01", ende="2024-12-31",
             art="verbraucher", teilzahlungen=[], zugaenge=[], rate=None)
    assert z["result"]["summe_zinsen"] == "84.94"
    assert rufe("rechner.frist", bezugstag="2026-10-17", anzahl=2, einheit="wochen")["result"]["ende"] == "2026-11-02"
    assert rufe("rechner.basiszins")["result"]["aktuell"]["satz"] == "1.52"
    assert "error" in rufe("rechner.verzugszinsen", hauptbetrag="x", beginn="2024-01-01", ende="2024-12-31")
