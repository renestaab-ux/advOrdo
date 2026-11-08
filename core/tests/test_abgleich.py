import pytest

from juracore.abgleich import abgleich as ab
from juracore.abgleich.angaben import anzeige, finde_angaben, finde_werte, saetze, vereinbar, zahlendreher
from juracore.dokumente import akte

from .conftest import schreibe_pdf


def _angaben(text):
    return [(a.titel, a.wert) for a in finde_angaben(text)]


# --- Werte und Sätze ------------------------------------------------------------------------------


def test_werte_werden_normalisiert():
    werte = finde_werte("Am 18.03.2025 für 14.900,00 € bei 68.400 km, Code P17BF, Mitte Juni 2025, 3. Mai 2025, € 50,-")
    assert [(w.art, w.wert) for w in werte] == [
        ("datum", "2025-03-18"),
        ("betrag", "14900.00"),
        ("km", "68400"),
        ("code", "P17BF"),
        ("monat", "2025-06"),
        ("datum", "2025-05-03"),
        ("betrag", "50.00"),
    ]
    assert anzeige("betrag", "2262307.27") == "2.262.307,27 €"
    assert anzeige("monat", "2025-06") == "Juni 2025"


def test_ungueltige_daten_und_ordnungszahlen_sind_keine_werte():
    assert finde_werte("am 31.02.2025 in der 3. Zivilkammer") == []


def test_saetze_trennen_nicht_an_abkuerzungen_und_ordnungszahlen():
    text = "Nach § 437 Nr. 2 BGB und Abs. 1 gilt das. Die 3. Zivilkammer entschied am 18.03.2025. Dr. Lena zahlte."
    assert [text[s:e] for s, e in saetze(text)] == [
        "Nach § 437 Nr. 2 BGB und Abs. 1 gilt das.",
        "Die 3. Zivilkammer entschied am 18.03.2025.",
        "Dr. Lena zahlte.",
    ]


def test_monat_ist_mit_datum_desselben_monats_vereinbar():
    assert vereinbar("monat", "2025-06", "datum", "2025-06-15")
    assert not vereinbar("monat", "2025-06", "datum", "2025-05-28")


# --- Angaben --------------------------------------------------------------------------------------


def test_zahlendreher():
    assert zahlendreher("betrag", "69415.80", "betrag", "96415.80")
    assert zahlendreher("datum", "2019-03-01", "datum", "2019-03-10")  # 01.03. und 10.03.
    assert zahlendreher("km", "68400", "km", "64800")
    assert not zahlendreher("betrag", "14900.00", "betrag", "14990.00")  # andere Ziffer, kein Dreher
    assert not zahlendreher("betrag", "69415.80", "betrag", "69415.80")
    assert not zahlendreher("betrag", "1234.00", "betrag", "4231.00")  # nicht nebeneinander
    assert not zahlendreher("betrag", "4100.00", "km", "1400")
    assert not zahlendreher("code", "P17BF", "code", "P71BF")


def test_wert_gehoert_zum_naechsten_merkmal():
    text = "Die Reparaturkosten von 3.480,00 € betragen rund 23 % des Kaufpreises."
    assert _angaben(text) == [("Reparaturkosten", "3480.00")]
    text = "Mit Kaufvertrag vom 14.03.2025 erwarb sie den Pkw zum Preis von 14.900,00 €."
    assert _angaben(text) == [("Kaufvertrag vom", "2025-03-14"), ("Kaufpreis", "14900.00")]


def test_verneinte_und_bestrittene_werte_zaehlen_nicht():
    text = "Der Kilometerstand bei Übergabe betrug nicht 64.800 km (Klageerwiderung Rn. 1), sondern 68.400 km."
    assert _angaben(text) == [("Kilometerstand bei Übergabe", "68400")]
    text = "Bestritten wird, dass die Klägerin erstmals am 12.05.2025 telefonisch angezeigt hat."
    assert _angaben(text) == []
    text = "Ein Fehlerspeichereintrag P17BF ließ sich nicht feststellen; gespeichert war vielmehr der Eintrag P189C."
    assert _angaben(text) == [("Fehlerspeicher", "P189C")]
    assert _angaben("Das Auslesen des Fehlerspeichers ergab keinen Eintrag.") == [("Fehlerspeicher", "kein Eintrag")]


def test_kilometerstand_nur_mit_bezug_zur_uebergabe():
    text = "Der Kilometerstand betrug zu diesem Zeitpunkt 71.900 km; bei Übergabe waren es 68.400 km."
    assert _angaben(text) == [("Kilometerstand bei Übergabe", "68400")]
    assert _angaben("Der Kilometerstand beträgt aktuell 72.600 km.") == []


def test_datum_vor_dem_merkmalswort():
    assert _angaben("Das Fahrzeug wurde am 18.03.2025 übergeben.") == [("Übergabe / Gefahrübergang", "2025-03-18")]
    assert _angaben("Seit dem Gefahrübergang am 21.03.2025 zeigte er sich.") == [
        ("Übergabe / Gefahrübergang", "2025-03-21")
    ]


def test_fristen_nach_ihrem_zweck():
    text = "Wir fordern Sie auf, den Mangel durch Nachbesserung zu beseitigen. Hierfür setzen wir Ihnen eine Frist bis zum 07.07.2025."
    assert _angaben(text) == [("Frist zur Nacherfüllung", "2025-07-07")]
    text = "Sie forderte die Beklagte unter Fristsetzung bis zum 29.07.2025 zur Rückzahlung des Kaufpreises auf."
    assert _angaben(text) == [("Zahlungsfrist", "2025-07-29")]
    # Ohne erkennbaren Zweck wird nichts zugeordnet.
    assert _angaben("Wir setzen Ihnen eine Frist bis zum 07.07.2025.") == []


def test_erste_maengelanzeige_auch_als_monat():
    text = "Die Klägerin hat sich erstmals Mitte Juni 2025 bei der Beklagten über ein Ruckeln beschwert."
    assert _angaben(text) == [("Erste Mängelanzeige", "2025-06")]


def test_vertrag_mit_anlage():
    angaben = finde_angaben("Beweis: Generalplanervertrag vom 12.11.2019 — Anlage K 18")
    assert [(a.merkmal, a.wert, a.anlage) for a in angaben] == [("vertrag:generalplanervertrag", "2019-11-12", "K 18")]
    angaben = finde_angaben("K 20 Generalplanervertrag vom 04.03.2021 17")
    assert angaben[0].anlage == "K 20"


# --- Abgleich einer Akte --------------------------------------------------------------------------


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _einlesen(akten, con, tmp_path, akte_id, name, seiten, tags):
    pdf = schreibe_pdf(tmp_path / name, seiten)
    return akte.importiere(akten, con, akte_id, pdf, tmp_path / "ablage", ocr=False, tags=tags)["dokument_id"]


def _brueckner(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner ./. Autohaus")
    klage = _einlesen(
        akten, con, tmp_path, a["id"], "05_klage.pdf",
        [
            ["(3) Mit Kaufvertrag vom 14.03.2025 erwarb die Klägerin den Pkw zum Preis von 14.900,00 €."],
            ["- 2 -", "(4) Die Klägerin hat den Mangel erstmals am 12.05.2025 telefonisch angezeigt."],
        ],
        ["Kläger"],
    )
    ruecktritt = _einlesen(
        akten, con, tmp_path, a["id"], "04_ruecktritt.pdf",
        [["Wir fordern Sie auf, unserer Mandantin den Kaufpreis in Höhe von 14.990,00 € zu erstatten."]],
        ["Kläger"],
    )
    erwiderung = _einlesen(
        akten, con, tmp_path, a["id"], "06_erwiderung.pdf",
        [
            ["(1) Unstreitig ist der Abschluss des Kaufvertrags vom 14.03.2025 zu einem Kaufpreis von 14.900,00 €.",
             "(2) Die Klägerin hat sich erstmals Mitte Juni 2025 bei der Beklagten beschwert."]
        ],
        ["Beklagter"],
    )  # fmt: skip
    return a["id"], klage, ruecktritt, erwiderung


def test_abgleich_stellt_abweichungen_mit_fundstellen_gegenueber(akten, con, tmp_path):
    akte_id, klage, ruecktritt, _ = _brueckner(akten, con, tmp_path)
    ergebnis = ab.abgleich(akten, akte_id)
    assert ergebnis["dokumente"] == 3
    assert ergebnis["zaehlung"] == {"abweichend": 2, "uebereinstimmend": 1, "einzeln": 0}
    merkmale = {m["titel"]: m for m in ergebnis["merkmale"]}

    kaufpreis = merkmale["Kaufpreis"]
    assert kaufpreis["status"] == "abweichend"
    assert kaufpreis["einordnung"] == ["innerhalb_partei", "zwischen_parteien"]
    werte = {w["anzeige"]: w for w in kaufpreis["werte"]}
    assert set(werte) == {"14.900,00 €", "14.990,00 €"}
    beleg = werte["14.990,00 €"]["fundstellen"][0]
    assert beleg["dokument_id"] == ruecktritt and beleg["parteien"] == ["Kläger"]
    assert beleg["ausschnitt"]["wert"] == "14.990,00 €"
    assert beleg["ausschnitt"]["davor"].endswith("den Kaufpreis in Höhe von ")

    anzeige_ = merkmale["Erste Mängelanzeige"]
    assert anzeige_["status"] == "abweichend"
    beleg = next(w for w in anzeige_["werte"] if w["wert"] == "2025-05-12")["fundstellen"][0]
    assert (beleg["dokument_id"], beleg["seite"], beleg["rn"]) == (klage, 2, 4)

    assert merkmale["Kaufvertrag vom"]["status"] == "uebereinstimmend"
    assert merkmale["Kaufvertrag vom"]["dokumente"] == 2
    # Abweichungen stehen vorn.
    assert [m["status"] for m in ergebnis["merkmale"]] == ["abweichend", "abweichend", "uebereinstimmend"]


def test_abgleich_zweier_dokumente(akten, con, tmp_path):
    akte_id, klage, _, erwiderung = _brueckner(akten, con, tmp_path)
    ergebnis = ab.abgleich(akten, akte_id, [klage, erwiderung])
    merkmale = {m["titel"]: m for m in ergebnis["merkmale"]}
    assert merkmale["Kaufpreis"]["status"] == "uebereinstimmend"
    assert merkmale["Erste Mängelanzeige"]["einordnung"] == ["zwischen_parteien"]
    with pytest.raises(LookupError):
        ab.abgleich(akten, akte_id, [klage, 999])


def test_widerspruch_im_selben_dokument(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Urteil")
    _einlesen(
        akten, con, tmp_path, a["id"], "urteil.pdf",
        [["Das Fahrzeug wurde der Klägerin am 18.03.2025 übergeben.",
          "Der Zustand hat sich innerhalb eines Jahres seit dem Gefahrübergang am 21.03.2025 gezeigt."]],
        [],
    )  # fmt: skip
    (m,) = ab.abgleich(akten, a["id"])["merkmale"]
    assert m["status"] == "abweichend" and m["einordnung"] == ["im_dokument"]


def test_satz_ueber_absatzgrenze(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Schreiben")
    pfad = tmp_path / "schreiben.md"
    pfad.write_text(
        "Wir fordern Sie auf, den Mangel durch Nachbesserung zu beseitigen. Hierfür setzen wir Ihnen eine Frist\n\n"
        "**bis zum 07.07.2025.**\n",
        encoding="utf-8",
    )
    akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)
    (m,) = ab.abgleich(akten, a["id"])["merkmale"]
    assert (m["titel"], m["werte"][0]["wert"]) == ("Frist zur Nacherfüllung", "2025-07-07")
    assert m["werte"][0]["fundstellen"][0]["abschnitt"] == 2


def test_verschiedene_vertraege_werden_nicht_verglichen(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Hallenbad")
    _einlesen(
        akten, con, tmp_path, a["id"], "klage.pdf",
        [["Beweis: Generalplanervertrag vom 12.11.2019 - Anlage K 18",
          "Beweis: Generalplanervertrag vom 04.03.2021 - Anlage K 20",
          "Aus dem Projektsteuerungsvertrag vom 01.03.2019 folgt das.",
          "Beweis: Projektsteuerungsvertrag vom 15.03.2019 - Anlage K 1"]],
        [],
    )  # fmt: skip
    merkmale = {m["titel"]: m["status"] for m in ab.abgleich(akten, a["id"])["merkmale"]}
    assert merkmale == {
        "Projektsteuerungsvertrag vom": "abweichend",
        "Generalplanervertrag vom (Anlage K 18)": "einzeln",
        "Generalplanervertrag vom (Anlage K 20)": "einzeln",
    }


def test_zahlendreher_wird_benannt(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Gutachten")
    _einlesen(
        akten, con, tmp_path, a["id"], "klage.pdf",
        [["Inhaltsverzeichnis: Kaufpreis (14.900,00 €)"],
         ["(3) Mit Kaufvertrag vom 14.03.2025 erwarb die Klägerin den Pkw zum Preis von 19.400,00 €.",
          "Die Klägerin hat den Kaufpreis von 19.400,00 € bar bezahlt."]],
        ["Kläger"],
    )  # fmt: skip
    _einlesen(
        akten, con, tmp_path, a["id"], "ruecktritt.pdf",
        [["Wir fordern Sie auf, den Kaufpreis in Höhe von 14.990,00 € zu erstatten."]],
        ["Kläger"],
    )
    merkmale = {m["titel"]: m for m in ab.abgleich(akten, a["id"])["merkmale"]}
    kaufpreis = merkmale["Kaufpreis"]
    assert {w["anzeige"] for w in kaufpreis["werte"]} >= {"19.400,00 €", "14.900,00 €", "14.990,00 €"}
    assert kaufpreis["hinweis"] == (
        "Möglicher Zahlendreher: 19.400,00 € und 14.900,00 € unterscheiden sich nur durch zwei vertauschte Ziffern. "
        "19.400,00 € steht zweimal im Text, 14.900,00 € einmal."
    )
    assert merkmale["Kaufvertrag vom"]["hinweis"] == ""


def test_unbekannte_akte(akten):
    with pytest.raises(LookupError):
        ab.abgleich(akten, 42)
