"""Zeiterfassung je Akte: Stufen, Bearbeiter, Taktung, Timer und Übernahme in die Kostennote."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from juracore import zeiterfassung as zeit
from juracore.dokumente import akte
from juracore.schriftstuecke import kostennote

from .test_schriftstuecke import kern  # noqa: F401  (Akte Brückner ./. Autohaus Rehnfeld mit Kanzleiprofil)

TAG = date(2026, 10, 28)


def _stufe(kern, name):  # noqa: F811
    return next(s["id"] for s in zeit.einstellungen(kern.akten)["stufen"] if s["name"] == name)


def _bearbeiter(kern, name, stufe):  # noqa: F811
    e = zeit.bearbeiter_speichern(kern.akten, name, _stufe(kern, stufe))
    return next(b["id"] for b in e["bearbeiter"] if b["name"] == name)


def test_taktung_und_stundentext():
    assert zeit.getaktet(0, 6) == 0
    assert zeit.getaktet(1, 6) == 6 and zeit.getaktet(6, 6) == 6 and zeit.getaktet(7, 6) == 12
    assert zeit.getaktet(16, 15) == 30
    assert zeit.stunden_text(6) == "0,1" and zeit.stunden_text(90) == "1,5" and zeit.stunden_text(60) == "1"
    assert zeit.stunden_text(100) == "1:40"


def test_beispielstufen_einmalig_und_aenderbar(kern):  # noqa: F811
    e = zeit.einstellungen(kern.akten)
    assert [s["name"] for s in e["stufen"]][:2] == ["Equity Partner", "Partner"]
    assert e["taktung"] == 6
    for s in e["stufen"]:
        zeit.stufe_loeschen(kern.akten, s["id"])
    zeit.einrichten(kern.akten)  # Neustart: gelöschte Beispiele kommen nicht wieder
    assert zeit.einstellungen(kern.akten)["stufen"] == []
    e = zeit.stufe_speichern(kern.akten, "Partner", "380,50")
    assert e["stufen"][0]["satz"] == "380.50"
    with pytest.raises(ValueError, match="keine Zahl"):
        zeit.stufe_speichern(kern.akten, "Associate", "viel")
    with pytest.raises(ValueError, match="gibt es nicht"):
        zeit.taktung_setzen(kern.akten, 7)
    assert zeit.taktung_setzen(kern.akten, 15)["taktung"] == 15


def test_bearbeiter_aus_eigenen_daten(kern):  # noqa: F811
    e = zeit.aus_eigenen_daten(kern.akten)
    assert e["neu"] >= 1
    namen = [b["name"] for b in e["bearbeiter"]]
    assert any("Albrecht" in n for n in namen)
    assert e["standard_bearbeiter_id"] is not None
    assert zeit.aus_eigenen_daten(kern.akten)["neu"] == 0  # keine Doppelten


def test_eintraege_von_hand_mit_summen(kern):  # noqa: F811
    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    r = _bearbeiter(kern, "Jana Köhler", "Rechtsanwaltsfachangestellte")
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-01", "dauer": "1:07", "bearbeiter_id": p,
                                     "taetigkeit": "Besprechung mit Mandantin"})
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-02", "von": "09:00", "bis": "09:20", "bearbeiter_id": r})
    liste = zeit.speichern(kern.akten, aid, {"datum": "2026-10-03", "dauer": "0,5", "bearbeiter_id": p,
                                         "abrechenbar": False, "taetigkeit": "Interne Abstimmung"})
    e = {x["datum"]: x for x in liste["eintraege"]}
    assert e["2026-10-01"]["minuten"] == 67 and e["2026-10-01"]["getaktet"] == 72
    assert e["2026-10-01"]["betrag"] == "456.00"  # 1,2 Std. × 380 €
    assert e["2026-10-02"]["getaktet"] == 24 and e["2026-10-02"]["betrag"] == "36.00"  # 0,4 × 90 €
    assert e["2026-10-03"]["getaktet"] == 0 and e["2026-10-03"]["betrag"] is None  # nicht abrechenbar
    assert liste["gesamt"]["minuten"] == 117 and liste["gesamt"]["offen"] == "492.00"
    with pytest.raises(ValueError, match="nicht nach"):
        zeit.speichern(kern.akten, aid, {"von": "10:00", "bis": "09:00", "bearbeiter_id": p})
    with pytest.raises(ValueError, match="Dauer"):
        zeit.speichern(kern.akten, aid, {"bearbeiter_id": p})
    # ohne Bearbeiter und ohne Standard: klare Meldung
    with pytest.raises(ValueError, match="Bearbeiter"):
        zeit.speichern(kern.akten, aid, {"dauer": "1"})
    zeit.standard_setzen(kern.akten, p)
    assert zeit.speichern(kern.akten, aid, {"dauer": "1"})["eintraege"][0]["bearbeiter"] == "Dr. Sophie Albrecht"


def test_satz_bleibt_beim_eintrag(kern):  # noqa: F811
    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-01", "dauer": "1", "bearbeiter_id": p})
    zeit.stufe_speichern(kern.akten, "Partner", "400", _stufe(kern, "Partner"))
    liste = zeit.speichern(kern.akten, aid, {"datum": "2026-10-02", "dauer": "1", "bearbeiter_id": p})
    assert sorted(x["satz"] for x in liste["eintraege"]) == ["380.00", "400.00"]


def test_timer_laeuft_ueber_neustart_und_nur_einer(kern, tmp_path):  # noqa: F811
    aid = kern.test_akte
    zweite = akte.akte_anlegen(kern.akten, "Weber ./. Brückner")["id"]
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    start = datetime(2026, 10, 28, 9, 0)
    zeit.starten(kern.akten, aid, p, "Klageerwiderung lesen", jetzt=start)
    assert zeit.laufend(kern.akten)["akte_id"] == aid
    # anderer Timer: der erste hält an (25 Minuten)
    zeit.starten(kern.akten, zweite, p, jetzt=start + timedelta(minutes=25))
    erste = zeit.liste(kern.akten, aid)["eintraege"][0]
    assert erste["minuten"] == 25 and erste["laeuft_seit"] is None
    assert zeit.laufend(kern.akten)["akte_id"] == zweite
    zeit.stoppen(kern.akten, jetzt=start + timedelta(minutes=25, seconds=10))
    assert zeit.laufend(kern.akten) is None
    assert zeit.liste(kern.akten, zweite)["eintraege"][0]["minuten"] == 1  # mindestens eine Minute
    # Fortsetzen addiert
    zeit.starten(kern.akten, aid, eintrag_id=erste["id"], jetzt=start + timedelta(hours=1))
    zeit.stoppen(kern.akten, jetzt=start + timedelta(hours=1, minutes=10))
    assert zeit.liste(kern.akten, aid)["eintraege"][0]["minuten"] == 35
    assert zeit.liste(kern.akten, aid)["eintraege"][0]["abschnitte"] == [
        {"von": "2026-10-28T09:00:00", "bis": "2026-10-28T09:25:00", "quelle": "timer"},
        {"von": "2026-10-28T10:00:00", "bis": "2026-10-28T10:10:00", "quelle": "timer"}]
    assert zeit.uhrzeiten_text(zeit.liste(kern.akten, aid)["eintraege"][0]) == "09:00–09:25, 10:00–10:10"
    # an einem anderen Tag nicht
    with pytest.raises(ValueError, match="nur am Tag des Eintrags"):
        zeit.starten(kern.akten, aid, eintrag_id=erste["id"], jetzt=start + timedelta(days=1))


def test_uebernahme_in_kostennote_und_storno(kern):  # noqa: F811
    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    r = _bearbeiter(kern, "Jana Köhler", "Rechtsanwaltsfachangestellte")
    zeit.taktung_setzen(kern.akten, 10)
    zeit.speichern(kern.akten, aid, {"datum": "2026-09-01", "dauer": "0:55", "bearbeiter_id": p})
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-01", "dauer": "0:35", "bearbeiter_id": p})
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-02", "dauer": "0:20", "bearbeiter_id": r})
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-03", "dauer": "2", "bearbeiter_id": p, "abrechenbar": False})
    k = zeit.fuer_kostennote(kern.akten, aid)
    assert k["leistungszeitraum"] == "01.09.2026 bis 02.10.2026"
    partner = next(x for x in k["posten"] if x["text"].startswith("Dr. Sophie"))
    assert partner["minuten"] == 100 and partner["stundensatz"] == "380.00"  # 60 + 40 Minuten getaktet
    assert partner["text"] == "Dr. Sophie Albrecht (Partner)"

    e = {"art": "rechnung", "nummer": "2026-0001", "datum": TAG.isoformat(), "posten": k["posten"],
         "leistungszeitraum": k["leistungszeitraum"]}
    b = kostennote.berechne(e)
    zeilen = b["abschnitte"][0]["zeilen"]
    assert b["abschnitte"][0]["titel"].startswith("Zeitaufwand")
    z = next(x for x in zeilen if x["text"].startswith("Dr. Sophie"))
    assert z["betrag"] == "633.33"  # 100/60 × 380 € genau aus den Minuten
    assert "1:40 Std." in z["text"]

    # Vorschuss rechnet die Zeiten nicht ab
    kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid, e | {"art": "vorschuss"})
    assert len(zeit.fuer_kostennote(kern.akten, aid)["posten"]) == 2

    erg = kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid,
                              e | {"nummer": "2026-0002"})
    assert erg["zeiten_abgerechnet"] == 3
    assert zeit.fuer_kostennote(kern.akten, aid)["posten"] == []
    liste = zeit.liste(kern.akten, aid)
    abgerechnet = [x for x in liste["eintraege"] if x["kostennote_id"]]
    assert {x["kostennote"] for x in abgerechnet} == {"2026-0002"}
    with pytest.raises(ValueError, match="abgerechnet"):
        zeit.loeschen(kern.akten, abgerechnet[0]["id"])
    # dieselben Quellen ein zweites Mal: abgelehnt, keine Nummer verbraucht
    with pytest.raises(ValueError, match="nicht mehr offen"):
        kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid,
                            e | {"nummer": "2026-0003"})
    assert kostennote.naechste_nummer(kern.akten, TAG) == "2026-0003"
    # Als Ausgangspunkt ohne Quellen
    kid = next(x["id"] for x in kostennote.liste(kern.akten, aid) if x["nummer"] == "2026-0002")
    assert all("quelle" not in p for p in kostennote.eingabe(kern.akten, kid)["posten"])
    # Storno gibt die Zeiten frei
    kostennote.stornieren(kern.akten, kid)
    assert len(zeit.fuer_kostennote(kern.akten, aid)["posten"]) == 2


def test_akte_loeschen_entfernt_zeiten(kern):  # noqa: F811
    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    zeit.starten(kern.akten, aid, p)
    akte.akte_loeschen(kern.akten, aid, kern.ablage)
    assert zeit.laufend(kern.akten) is None
    assert kern.akten.execute("SELECT COUNT(*) FROM zeit_eintrag").fetchone()[0] == 0


def test_grenzen_der_taktung_und_konkrete_taetigkeit(kern):  # noqa: F811
    """BGH, Urt. v. 13.02.2020 – IX ZR 140/19: 15-Minuten-Takt gegenüber Verbrauchern, pauschale Angaben."""
    aid = kern.test_akte  # Mandantin Dr. Lena Brückner ist eine natürliche Person
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    assert zeit.einstellungen(kern.akten)["taktung_hinweis"] is None
    assert zeit.liste(kern.akten, aid)["hinweise"] == []
    e = zeit.taktung_setzen(kern.akten, 15)
    assert "IX ZR 140/19" in e["taktung_hinweis"]
    assert "Verbraucher" in zeit.liste(kern.akten, aid)["hinweise"][0]
    zeit.speichern(kern.akten, aid, {"dauer": "0:07", "bearbeiter_id": p, "taetigkeit": "Telefonat"})
    zeit.speichern(kern.akten, aid, {"dauer": "0:20", "bearbeiter_id": p,
                                     "taetigkeit": "Telefonat mit Frau Brückner zur Vergleichsbereitschaft"})
    k = zeit.fuer_kostennote(kern.akten, aid)
    assert any(h.startswith("1 Eintrag/Einträge ohne konkrete Tätigkeit") for h in k["hinweise"])
    assert any("Verbraucher" in h for h in k["hinweise"])
    # minutengenau erfasst bleibt erhalten
    assert sorted(x["minuten"] for x in zeit.liste(kern.akten, aid)["eintraege"]) == [7, 20]
    zeit.taktung_setzen(kern.akten, 6)
    assert [h for h in zeit.liste(kern.akten, aid)["hinweise"] if "Verbraucher" in h] == []


def test_zehn_minuten_ueber_empfehlung(kern):  # noqa: F811
    e = zeit.taktung_setzen(kern.akten, 10)
    assert "5 bis 6 Minuten" in e["taktung_hinweis"] and "IX ZR" not in e["taktung_hinweis"]
    assert "5 bis 6 Minuten" in zeit.liste(kern.akten, kern.test_akte)["hinweise"][0]


def test_rvg_mindestverguetung_berechnet_das_hoehere():
    """Zeithonorar, mindestens die gesetzlichen Gebühren (BGH IX ZR 90/23): nie beides."""
    gebuehren = [{"nr": "3100"}, {"nr": "3104"}]  # 10.000 €: 847,60 + 782,40 + 20,00 = 1.650,00 €
    wenig = {"typ": "stunden", "text": "RA", "minuten": 240, "stundensatz": "250"}  # 1.000 €
    viel = {"typ": "stunden", "text": "RA", "minuten": 600, "stundensatz": "250"}  # 2.500 €
    r = kostennote.berechne({"gegenstandswert": "10000", "mindestverguetung": True, "posten": gebuehren + [wenig]})
    assert r["vergleich"] == {"zeithonorar": "1000.00", "gesetzlich": "1650.00", "gewaehlt": "gesetzlich"}
    assert r["netto"] == "1650.00" and not any(a["titel"].startswith("Zeitaufwand") for a in r["abschnitte"])
    r = kostennote.berechne({"gegenstandswert": "10000", "mindestverguetung": True, "posten": gebuehren + [viel]})
    assert r["vergleich"]["gewaehlt"] == "zeithonorar" and r["netto"] == "2500.00"
    # ohne Haken: addiert, mit Hinweis
    r = kostennote.berechne({"gegenstandswert": "10000", "posten": gebuehren + [wenig]})
    assert r["netto"] == "2650.00" and any("Mindestvergütung" in h for h in r["hinweise"])
    # Haken ohne Gebühren: Hinweis, nur Zeithonorar
    r = kostennote.berechne({"mindestverguetung": True, "posten": [wenig]})
    assert r["vergleich"] is None and r["netto"] == "1000.00"
    assert any("Vergleichsrechnung" in h for h in r["hinweise"])


def test_taetigkeitsnachweis_in_der_kostennote(kern, tmp_path):  # noqa: F811
    import zipfile
    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-01", "dauer": "0:07", "bearbeiter_id": p,
                                     "taetigkeit": "Telefonat mit Frau Brückner zur Vergleichsbereitschaft"})
    k = zeit.fuer_kostennote(kern.akten, aid)
    ziel = tmp_path / "k.docx"
    kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid,
                        {"nummer": "2026-0001", "datum": TAG.isoformat(), "posten": k["posten"]}, pfad=ziel,
                        in_akte=False)
    with zipfile.ZipFile(ziel) as z:
        xml = z.read("word/document.xml").decode()
    for text in ("Anlage: Tätigkeitsnachweis zu Rechnung Nr. 2026-0001", "01.10.2026",
                 "Telefonat mit Frau Brückner zur Vergleichsbereitschaft", "0,2 (7 Min.)", "76,00 €"):
        assert text in xml, text


def test_abweichende_stufe_je_eintrag_reisezeit(kern):  # noqa: F811
    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    reise = next(s["id"] for s in zeit.stufe_speichern(kern.akten, "Reisezeit", "150")["stufen"]
                 if s["name"] == "Reisezeit")
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-01", "dauer": "1", "bearbeiter_id": p,
                                     "taetigkeit": "Termin beim LG Freiburg wahrgenommen"})
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-01", "dauer": "2", "bearbeiter_id": p, "stufe_id": reise,
                                     "taetigkeit": "Fahrt Kanzlei zum LG Freiburg und zurück"})
    zeit.starten(kern.akten, aid, p, "Rückfahrt vom Ortstermin", stufe_id=reise)
    zeit.stoppen(kern.akten)
    k = zeit.fuer_kostennote(kern.akten, aid)
    texte = {x["text"]: x["stundensatz"] for x in k["posten"]}
    assert texte == {"Dr. Sophie Albrecht (Partner)": "380.00", "Dr. Sophie Albrecht (Reisezeit)": "150.00"}


# --------------------------------------------------------------------------- Stufe 2


def test_rahmen_und_einzelvereinbarung(kern):  # noqa: F811
    from juracore.aktenverwaltung import stammdaten

    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    zeit.speichern(kern.akten, aid, {"dauer": "0:07", "bearbeiter_id": p,
                                     "taetigkeit": "Klageerwiderung auf Seite 3 geprüft"})
    stand = zeit.liste(kern.akten, aid)
    v = stand["vereinbarung"]
    mandant = v["mandant"]["schluessel"]
    assert v["mandant"]["name"] == "Dr. Lena Brückner" and v["mandant"]["akten"] == 1
    assert not v["vermerkt"] and v["art"] is None and v["taktung"] == 6 and v["taktung_eigen"] is None
    assert any("keine Vergütungsvereinbarung" in h and "§ 4b S. 1 RVG" in h for h in stand["hinweise"])
    assert zeit.fuer_kostennote(kern.akten, aid)["mindestverguetung"] is None

    # Rahmenvereinbarung mit der Mandantin gilt in allen ihren Akten
    stand = zeit.vereinbarung_speichern(kern.akten, aid, {"art": "rahmen", "taktung": 1,
                                                          "vereinbart_am": "2026-10-01", "mindestverguetung": True})
    assert stand["vereinbarung"]["art"] == "rahmen"
    assert stand["taktung"] == 1 and stand["eintraege"][0]["getaktet"] == 7
    assert not any("keine Vergütungsvereinbarung" in h for h in stand["hinweise"])
    assert zeit.fuer_kostennote(kern.akten, aid)["mindestverguetung"] is True
    assert zeit.einstellungen(kern.akten)["taktung"] == 6  # die allgemeine bleibt
    b = akte.akte_anlegen(kern.akten, "Brückner, Mietsache")["id"]
    stammdaten.beteiligung_hinzufuegen(kern.akten, b, "mandant", beteiligter_id=int(mandant[2:]))
    assert zeit.akte_taktung(kern.akten, b) == 1
    assert zeit.liste(kern.akten, b)["vereinbarung"]["mandant"]["akten"] == 2

    # Einzelvereinbarung für die zweite Akte ersetzt den Rahmen dort ganz
    v = zeit.vereinbarung_speichern(kern.akten, b, {"art": "einzel", "taktung": 5, "vereinbart_am": "2026-10-20",
                                                    "notiz": "Pauschal je Instanz besprochen"})["vereinbarung"]
    assert v["art"] == "einzel" and v["taktung"] == 5 and v["mindestverguetung"] is False
    assert v["rahmen"]["taktung"] == 1  # der Rahmen bleibt sichtbar
    assert zeit.akte_taktung(kern.akten, aid) == 1  # die erste Akte behält den Rahmen
    m = zeit.mandant_vereinbarungen(kern.akten, mandant)
    assert m["rahmen"]["taktung"] == 1 and m["akten"] == 2
    assert [(e["akte"], e["taktung"]) for e in m["einzel"]] == [("Brückner, Mietsache", 5)]
    # Einzel ohne eigene Taktung: dann die allgemeine, nicht der Rahmen
    assert zeit.vereinbarung_speichern(kern.akten, b, {"art": "einzel", "taktung": None})["taktung"] == 6
    # aufheben: wieder der Rahmen
    v = zeit.vereinbarung_speichern(kern.akten, b, {"einzel_aufheben": True})["vereinbarung"]
    assert v["art"] == "rahmen" and v["taktung"] == 1
    assert zeit.mandant_vereinbarungen(kern.akten, mandant)["einzel"] == []

    # Rahmen aus den Daten des Mandanten ändern und löschen
    assert zeit.rahmen_speichern(kern.akten, mandant, {"taktung": 6})["rahmen"]["taktung"] == 6
    assert zeit.rahmen_speichern(kern.akten, mandant, {"taktung": 6})["rahmen"]["mindestverguetung"] is True
    assert zeit.rahmen_loeschen(kern.akten, mandant)["rahmen"] is None
    assert zeit.vereinbarung(kern.akten, aid)["art"] is None
    with pytest.raises(LookupError):
        zeit.mandant_vereinbarungen(kern.akten, "b:9999")

    with pytest.raises(ValueError, match="gibt es nicht"):
        zeit.vereinbarung_speichern(kern.akten, aid, {"taktung": 7})
    # Akte ohne Mandant: Einzelvereinbarung und Kostenschätzung gehen, ein Rahmen nicht
    leer = akte.akte_anlegen(kern.akten, "Ohne Mandant")["id"]
    assert zeit.vereinbarung_speichern(kern.akten, leer, {"kostenschaetzung": "1.000"})["vereinbarung"][
        "kostenschaetzung"] == "1000.00"
    assert zeit.vereinbarung_speichern(kern.akten, leer, {"taktung": 10})["taktung"] == 10
    with pytest.raises(ValueError, match="kein Mandant"):
        zeit.vereinbarung_speichern(kern.akten, leer, {"art": "rahmen", "taktung": 6})


def test_kostenschaetzung_meldet_ueberschreitung(kern):  # noqa: F811
    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")  # 380 €/Std.
    zeit.vereinbarung_speichern(kern.akten, aid, {"kostenschaetzung": "500,00", "vereinbart_am": "2026-10-01"})
    stand = zeit.speichern(kern.akten, aid, {"dauer": "1:00", "bearbeiter_id": p,
                                             "taetigkeit": "Besprechung mit Frau Brückner zum Vergleich"})
    assert stand["gesamt"]["budget_anteil"] == 76 and not any("Kostenschätzung" in h for h in stand["hinweise"])
    stand = zeit.speichern(kern.akten, aid, {"dauer": "0:30", "bearbeiter_id": p,
                                             "taetigkeit": "Replik zur Klageerwiderung entworfen"})
    assert stand["gesamt"]["budget_anteil"] == 114
    assert any("überschreiten 114 % der Kostenschätzung (500,00 €)" in h for h in stand["hinweise"])


def test_fuenffach_pruefung():
    zeit_posten = {"typ": "stunden", "text": "RAin Albrecht", "minuten": 600, "stundensatz": "380.00"}
    gebuehr = {"typ": "gebuehr", "nr": "3100", "satz": "1,3"}
    e = {"art": "rechnung", "gegenstandswert": "1.000", "auftrag_am": "2026-10-01", "posten": [zeit_posten, gebuehr],
         "mindestverguetung": True}
    r = kostennote.berechne(e)
    assert r["vergleich"]["gewaehlt"] == "zeithonorar" and float(r["vergleich"]["faktor"]) > 5
    assert any("§ 3a Abs. 3 S. 1 RVG" in h and "BB 2025, 2893" in h for h in r["hinweise"])
    # unter dem Fünffachen kein Hinweis
    e["posten"] = [{**zeit_posten, "minuten": 60}, gebuehr]
    r = kostennote.berechne(e)
    assert "faktor" not in r["vergleich"] and not any("Fünffachen" in h for h in r["hinweise"])


def test_vorlage_verguetungsvereinbarung(kern, tmp_path):  # noqa: F811
    import zipfile

    from juracore.schriftstuecke import platzhalter, vorlagen

    aid = kern.test_akte
    zeit.vereinbarung_speichern(kern.akten, aid, {"taktung": 6, "mindestverguetung": True,
                                                  "kostenschaetzung": "4.500", "vereinbart_am": "2026-10-01"})
    w = platzhalter.werte(kern.akten, aid)["werte"]
    assert "Partner: 380,00 € je Stunde" in w["Vergütung.Stundensätze"]
    assert "6 Minuten (0,1 Stunde)" in w["Vergütung.Taktung"]
    assert w["Vergütung.Kostenschätzung"] == "4.500,00 €"
    assert "mindestens die gesetzliche Vergütung" in w["Vergütung.Mindestvergütung"]
    ziel = tmp_path / "v.docx"
    r = vorlagen.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid, "grund:verguetung",
                          pfad=ziel, in_akte=False, heute=TAG)
    assert r["dateiname"] == "2026-10-28 Vergütungsvereinbarung Dr. Lena Brückner.docx"
    assert r["leer"] == [] and r["unbekannt"] == []
    text = zipfile.ZipFile(ziel).read("word/document.xml").decode()
    assert "Vergütungsvereinbarung" in text and "regelmäßig nicht mehr als die gesetzliche Vergütung" in text
    assert "Anerkenntnis" in text and "4.500,00 €" in text and "Vorzeitige Beendigung" in text
    assert "Nicht umfasst sind" in text
    # ohne Mindestvergütung bleibt der Absatz leer, ohne Hinweis auf eine Lücke
    zeit.vereinbarung_speichern(kern.akten, aid, {"mindestverguetung": False})
    r = vorlagen.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid, "grund:verguetung",
                          pfad=ziel, in_akte=False, heute=TAG)
    assert r["leer"] == []
    assert "mindestens die gesetzliche" not in zipfile.ZipFile(ziel).read("word/document.xml").decode()


def test_export_der_zeiten(kern, tmp_path):  # noqa: F811
    import zipfile

    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-02", "dauer": "0:07", "bearbeiter_id": p,
                                     "taetigkeit": "Telefonat mit Frau Brückner; Fristen besprochen"})
    zeit.speichern(kern.akten, aid, {"datum": "2026-10-01", "dauer": "1:30", "bearbeiter_id": p,
                                     "taetigkeit": "Klageschrift =SUMME(A1) entworfen", "abrechenbar": False})
    csv_pfad = tmp_path / "zeiten.csv"
    r = zeit.exportieren(kern.akten, aid, str(csv_pfad))
    assert r["anzahl"] == 2
    roh = csv_pfad.read_bytes()
    assert roh.startswith(b"\xef\xbb\xbf") and b"\r\r\n" not in roh
    zeilen = roh.decode("utf-8-sig").split("\r\n")
    assert zeilen[0].startswith("Datum;Uhrzeit;Bearbeiter;Stufe;Tätigkeit")
    assert zeilen[1].startswith("01.10.2026;;Dr. Sophie Albrecht;Partner;")  # älteste zuerst
    assert ";0,20;380,00;76,00;ja;" in zeilen[2]
    assert zeilen[0].startswith("Datum;Uhrzeit;Bearbeiter")
    for art in ("xlsx", "pdf", "docx"):
        ziel = tmp_path / f"zeiten.{art}"
        zeit.exportieren(kern.akten, aid, str(ziel))
        assert ziel.stat().st_size > 500
    blatt = zipfile.ZipFile(tmp_path / "zeiten.xlsx").read("xl/worksheets/sheet2.xml").decode()
    assert "=SUMME(A1)" in blatt and "<f>" not in blatt  # Text bleibt Text
    with pytest.raises(ValueError, match="nicht unterstützt"):
        zeit.exportieren(kern.akten, aid, str(tmp_path / "zeiten.odt"))


def test_uhrzeiten_von_hand(kern):  # noqa: F811
    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    stand = zeit.speichern(kern.akten, aid, {"datum": "2026-10-29", "von": "9:05", "bis": "09:50", "bearbeiter_id": p,
                                             "taetigkeit": "Telefonat mit Frau Brückner zum Vergleich"})
    e = stand["eintraege"][0]
    assert e["minuten"] == 45 and zeit.uhrzeiten_text(e) == "09:05–09:50" and e["abschnitte"][0]["quelle"] == "hand"
    # bloße Dauer ändern: Zeitspanne bleibt (zeigt, dass von Hand angepasst wurde)
    e = zeit.speichern(kern.akten, aid, {"datum": "2026-10-29", "dauer": "1:00", "bearbeiter_id": p,
                                         "taetigkeit": e["taetigkeit"]}, e["id"])["eintraege"][0]
    assert e["minuten"] == 60 and len(e["abschnitte"]) == 1
    # neue von–bis ersetzt sie
    e = zeit.speichern(kern.akten, aid, {"datum": "2026-10-29", "von": "14:00", "bis": "14:30", "bearbeiter_id": p,
                                         "taetigkeit": e["taetigkeit"]}, e["id"])["eintraege"][0]
    assert zeit.uhrzeiten_text(e) == "14:00–14:30"
    # nur Dauer: keine Uhrzeit
    e = zeit.speichern(kern.akten, aid, {"datum": "2026-10-29", "dauer": "0,5", "bearbeiter_id": p,
                                         "taetigkeit": "Akte für Termin vorbereitet"})["eintraege"][0]
    assert e["abschnitte"] == [] and zeit.uhrzeiten_text(e) == ""


def test_notiz_zum_zeiteintrag(kern):  # noqa: F811
    from juracore.aktenverwaltung import notizen

    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    e = zeit.speichern(kern.akten, aid, {"datum": "2026-10-29", "von": "09:00", "bis": "09:20", "bearbeiter_id": p,
                                         "taetigkeit": "Telefonat mit Frau Brückner"})["eintraege"][0]
    assert e["notiz"] is None and e["notiz_id"] is None
    e = zeit.notiz_speichern(kern.akten, e["id"], "Telefonat 29.10.2026, 09:00–09:20\nVergleich bis 8.000 €")[
        "eintraege"][0]
    assert e["notiz"].endswith("8.000 €") and e["notiz_id"]
    n = notizen.liste(kern.akten, aid)
    assert len(n) == 1 and n[0]["zeiteintrag"] == "2026-10-29 · Dr. Sophie Albrecht"
    # zweites Speichern ändert dieselbe Notiz
    e = zeit.notiz_speichern(kern.akten, e["id"], "Vergleich bis 9.000 €")["eintraege"][0]
    assert e["notiz"] == "Vergleich bis 9.000 €" and len(notizen.liste(kern.akten, aid)) == 1
    # Notiz gelöscht: Eintrag bleibt, Verweis fällt weg
    notizen.loeschen(kern.akten, e["notiz_id"])
    e = zeit.liste(kern.akten, aid)["eintraege"][0]
    assert e["notiz"] is None and e["notiz_id"] is None


def test_vorhandene_notiz_verknuepfen(kern):  # noqa: F811
    from juracore.aktenverwaltung import notizen

    aid = kern.test_akte
    p = _bearbeiter(kern, "Dr. Sophie Albrecht", "Partner")
    nid = notizen.speichern(kern.akten, aid, "Telefonnotiz: Gegenseite bietet 6.000 €")[0]["id"]
    e = zeit.speichern(kern.akten, aid, {"dauer": "0:15", "bearbeiter_id": p,
                                         "taetigkeit": "Telefonat mit Gegenanwalt Vogt"})["eintraege"][0]
    e = zeit.notiz_verknuepfen(kern.akten, e["id"], nid)["eintraege"][0]
    assert e["notiz_id"] == nid and e["notiz"].startswith("Telefonnotiz")
    e = zeit.notiz_verknuepfen(kern.akten, e["id"], None)["eintraege"][0]
    assert e["notiz_id"] is None and len(notizen.liste(kern.akten, aid)) == 1  # Notiz bleibt
    andere = akte.akte_anlegen(kern.akten, "Andere Akte")["id"]
    fremd = notizen.speichern(kern.akten, andere, "fremd")[0]["id"]
    with pytest.raises(ValueError, match="nicht zu dieser Akte"):
        zeit.notiz_verknuepfen(kern.akten, e["id"], fremd)
