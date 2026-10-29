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
    assert zeit.liste(kern.akten, aid)["hinweise"] == []


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
