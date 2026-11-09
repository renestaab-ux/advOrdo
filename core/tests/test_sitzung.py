"""Terminmodus des Arbeitsfensters: Sitzungsblatt, Terminsnotizen und „Termin beenden“.

Alle Angaben stammen aus der fiktiven Testakte „Brückner ./. Autohaus Rehnfeld GmbH“.
"""

from datetime import date, datetime

import pytest

from juracore import zeiterfassung as zeit
from juracore.aktenverwaltung import einrichten, kalender, notizen, sitzung
from juracore.dokumente import akte
from juracore.eigene import daten as eigene
from juracore.schriftstuecke import kostennote

BEGINN = datetime(2026, 11, 24, 10, 32)


@pytest.fixture
def con(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    eigene.einrichten(verbindung)
    einrichten(verbindung)
    kostennote.einrichten(verbindung)
    zeit.einrichten(verbindung)
    yield verbindung
    verbindung.close()


def _akte_mit_dokument(con):
    a = akte.akte_anlegen(con, "Brückner ./. Autohaus Rehnfeld GmbH")["id"]
    with con:
        d = con.execute(
            "INSERT INTO dokument (akte_id, dateiname, format, sha256, groesse, original, importiert_am, seiten, "
            "lesart, hinweise) VALUES (?, '05_Klageschrift_2025-10-20.pdf', 'pdf', 'abc', 1, '/x', '2026-11-01', 1, "
            "'textebene', '[]')", (a,)).lastrowid
    return a, d


def test_sitzungsblatt_mit_belegen_und_reihenfolge(con):
    a, d = _akte_mit_dokument(con)
    sitzung.punkt_speichern(con, a, {"art": "streitpunkt", "text": "Mangel bei Gefahrübergang, § 477 BGB",
                                     "ampel": "gelb"})
    liste = sitzung.punkt_speichern(con, a, {
        "art": "streitpunkt", "text": "Endgültige Verweigerung der Nacherfüllung?", "ampel": "rot",
        "belege": [{"dokument_id": d, "abschnitt": 3}], "herkunft": "ki"})
    liste = sitzung.punkt_speichern(con, a, {"art": "antrag", "text": "Zahlung 14.555,40 € Zug um Zug"})
    assert [p["art"] for p in liste] == ["antrag", "streitpunkt", "streitpunkt"]
    beleg = liste[2]["belege"][0]
    assert beleg == {"dokument_id": d, "abschnitt": 3, "rn": None, "bezeichnung": "05_Klageschrift_2025-10-20.pdf"}
    mit_rn = sitzung.punkt_speichern(con, a, {"text": "Hilfsaufrechnung", "belege": [{"dokument_id": d, "rn": 5}]})
    assert mit_rn[-1]["belege"][0]["bezeichnung"] == "05_Klageschrift_2025-10-20.pdf, Rn. 5"
    sitzung.punkt_loeschen(con, mit_rn[-1]["id"])
    assert liste[2]["herkunft"] == "ki" and liste[1]["belege"] == []
    liste = sitzung.punkt_verschieben(con, liste[2]["id"], -1)
    assert [p["text"][:5] for p in liste] == ["Zahlu", "Endgü", "Mange"]
    # Ändern ohne Belege lässt sie stehen.
    liste = sitzung.punkt_speichern(con, a, {"ampel": "gruen"}, liste[1]["id"])
    assert liste[1]["ampel"] == "gruen" and liste[1]["belege"][0]["abschnitt"] == 3
    with pytest.raises(ValueError, match="nicht zu dieser Akte"):
        sitzung.punkt_speichern(con, a, {"text": "x", "belege": [{"dokument_id": 999}]})
    with pytest.raises(ValueError, match="eintragen"):
        sitzung.punkt_speichern(con, a, {"text": "  "})
    assert len(sitzung.punkt_loeschen(con, liste[0]["id"])) == 2


def test_sitzung_mitschreiben_und_fristvorschlag(con):
    a, d = _akte_mit_dokument(con)
    assert sitzung.aktiv(con, a) is None
    s = sitzung.beginnen(con, a, titel="LG Freiburg, Saal 2.14", jetzt=BEGINN)
    assert sitzung.beginnen(con, a)["id"] == s["id"], "eine laufende Sitzung wird weitergeführt"
    sitzung.notiz_anlegen(con, s["id"], "Vorsitzende führt in den Sach- und Streitstand ein.",
                          jetzt=datetime(2026, 11, 24, 10, 34))
    sitzung.notiz_anlegen(con, s["id"], "Kammer hält Fristsetzung für entbehrlich.", "hinweis", d,
                          jetzt=datetime(2026, 11, 24, 10, 41))
    s = sitzung.notiz_anlegen(con, s["id"], "Schriftsatznachlass für Bekl. drei Wochen zum Hinweis.", "auflage",
                              jetzt=datetime(2026, 11, 24, 11, 9))
    assert [n["zeit"][11:16] for n in s["notizen"]] == ["10:34", "10:41", "11:09"]
    assert s["notizen"][1]["dokument"] == "05_Klageschrift_2025-10-20.pdf"

    vorschlag = sitzung.abschluss(con, s["id"], jetzt=datetime(2026, 11, 24, 11, 14))
    assert vorschlag["minuten"] == 42
    assert vorschlag["protokoll"].splitlines() == [
        "Terminsprotokoll 24.11.2026, 10:32–11:14 Uhr (LG Freiburg, Saal 2.14)",
        "10:34 Vorsitzende führt in den Sach- und Streitstand ein.",
        "10:41 Hinweis des Gerichts: Kammer hält Fristsetzung für entbehrlich. [zu 05_Klageschrift_2025-10-20.pdf]",
        "11:09 Frist / Auflage: Schriftsatznachlass für Bekl. drei Wochen zum Hinweis.",
    ]
    [frist] = vorschlag["fristen"]
    assert frist["anzahl"] == 3 and frist["einheit"] == "wochen" and frist["datum"] == "2026-12-15"
    assert "11:09" in frist["quelle"]


def test_kein_fristvorschlag_ohne_bezug(con):
    a, _ = _akte_mit_dokument(con)
    s = sitzung.beginnen(con, a, jetzt=BEGINN)
    s = sitzung.notiz_anlegen(con, s["id"], "Zeuge war drei Wochen im Urlaub.", jetzt=BEGINN)
    assert sitzung.fristvorschlaege(s) == []


def test_termin_beenden_uebernimmt_nur_ausgewaehltes(con):
    a, _ = _akte_mit_dokument(con)
    s = sitzung.beginnen(con, a, jetzt=BEGINN)
    sitzung.notiz_anlegen(con, s["id"], "Vergleich: Rückzahlung 12.800 €.", "vergleich", jetzt=BEGINN)
    # Ohne Bearbeiter scheitert die Zeit; dann bleibt alles unverändert und der Termin läuft weiter.
    with pytest.raises(ValueError, match="Bearbeiter"):
        sitzung.beenden(con, s["id"], zeit={"minuten": 42}, fristen=[{"titel": "Stellungnahme", "datum": "2026-12-15"}])
    assert sitzung.aktiv(con, a) is not None and kalender.liste(con, a) == [] and notizen.liste(con, a) == []

    with pytest.raises(ValueError, match="Datum"):
        sitzung.beenden(con, s["id"], fristen=[{"titel": "Stellungnahme", "datum": "15.12."}])

    stufe = zeit.einstellungen(con)["stufen"][0]["id"]
    b = next(x["id"] for x in zeit.bearbeiter_speichern(con, "RA Tiedemann", stufe)["bearbeiter"]
             if x["name"] == "RA Tiedemann")
    fertig = sitzung.beenden(con, s["id"], zeit={"minuten": 42, "bearbeiter_id": b},
                             fristen=[{"titel": "Stellungnahme Bekl. zum Hinweis", "datum": "2026-12-15"}],
                             jetzt=datetime(2026, 11, 24, 11, 14))
    assert fertig["ende"].endswith("11:14:00")
    assert fertig["uebernommen"] == {"notiz": True, "zeit": 42, "fristen": 1}
    assert notizen.liste(con, a)[0]["text"].startswith("Terminsprotokoll 24.11.2026, 10:32–11:14 Uhr")
    [frist] = kalender.liste(con, a)
    assert frist["art"] == "frist" and frist["datum"] == "2026-12-15"
    eintraege = zeit.liste(con, a)["eintraege"]
    assert eintraege[0]["minuten"] == 42 and eintraege[0]["datum"] == "2026-11-24"
    assert sitzung.aktiv(con, a) is None
    with pytest.raises(ValueError, match="schon beendet"):
        sitzung.notiz_anlegen(con, s["id"], "zu spät")


def test_termine_heute(con):
    a, _ = _akte_mit_dokument(con)
    kalender.speichern(con, a, {"art": "termin", "titel": "Mündliche Verhandlung", "datum": "2026-11-24",
                                "uhrzeit": "10:30", "ort": "Saal 2.14"}, heute=date(2026, 11, 1))
    [t] = sitzung.termine_heute(con, a, date(2026, 11, 24))
    s = sitzung.beginnen(con, a, kalender_id=t["id"], jetzt=BEGINN)
    assert s["titel"] == "Mündliche Verhandlung · Saal 2.14" and s["kalender_id"] == t["id"]


def test_fristvorschlag_mit_festem_datum(con):
    a, _ = _akte_mit_dokument(con)
    s = sitzung.beginnen(con, a, jetzt=BEGINN)
    um = datetime(2026, 11, 24, 11, 0)
    sitzung.notiz_anlegen(con, s["id"], "Stellungnahme zum Gutachten bis zum 15.12.2026.", "auflage", jetzt=um)
    sitzung.notiz_anlegen(con, s["id"], "Schriftsatznachlass bis 19. Dezember (Schreiben vom 23.06.2025).", "auflage",
                          jetzt=um)
    sitzung.notiz_anlegen(con, s["id"], "Frist zur Zahlung bis 15.1.", "notiz", jetzt=um)
    s = sitzung.notiz_anlegen(con, s["id"], "Auflage: Unterlagen binnen zwei Wochen, spätestens 4.12.26", "auflage",
                              jetzt=um)
    fristen = sitzung.fristvorschlaege(s)
    assert [(f["art"], f["datum"]) for f in fristen] == [
        ("datum", "2026-12-15"), ("datum", "2026-12-19"), ("datum", "2027-01-15"), ("datum", "2026-12-04")]
    assert [f["kein_werktag"] for f in fristen] == [None, "Samstag", None, None]
    assert fristen[0]["anzahl"] is None


def test_fristvorschlag_monate_und_vergangenes_datum(con):
    a, _ = _akte_mit_dokument(con)
    s = sitzung.beginnen(con, a, jetzt=BEGINN)
    s = sitzung.notiz_anlegen(con, s["id"], "Frist zwei Monate, Bezug Schreiben vom 01.10.2026", "auflage",
                              jetzt=datetime(2026, 11, 24, 11, 0))
    [f] = sitzung.fristvorschlaege(s)
    assert (f["art"], f["anzahl"], f["einheit"], f["datum"]) == ("dauer", 2, "monate", "2027-01-25")


def test_fristbeginn_ab_zustellung_bleibt_offen(con):
    a, _ = _akte_mit_dokument(con)
    s = sitzung.beginnen(con, a, jetzt=BEGINN)
    um = datetime(2026, 11, 24, 11, 0)
    sitzung.notiz_anlegen(con, s["id"], "Stellungnahme zwei Monate ab Zustellung Protokoll", "auflage", jetzt=um)
    s = sitzung.notiz_anlegen(con, s["id"], "Frist 4 Wochen nach Zugang des Gutachtens", "notiz", jetzt=um)
    fristen = sitzung.fristvorschlaege(s)
    assert [(f["beginn_offen"], f["datum"], f["bezugstag"], f["anzahl"]) for f in fristen] == [
        ("Zustellung Protokoll", None, None, 2), ("Zugang des Gutachtens", None, None, 4)]


def test_wahrnehmung_durch_sachbearbeiter_oder_gewaehlte_person(con):
    import json as _json
    a, _ = _akte_mit_dokument(con)
    with con:
        p1 = con.execute("INSERT INTO eigene_person (daten, angelegt_am, geaendert_am) VALUES (?, '', '')",
                         (_json.dumps({"titel": "RA", "vorname": "Albrecht", "nachname": "Tiedemann"}),)).lastrowid
        p2 = con.execute("INSERT INTO eigene_person (daten, angelegt_am, geaendert_am) VALUES (?, '', '')",
                         (_json.dumps({"titel": "RAin", "vorname": "Jana", "nachname": "Kolb"}),)).lastrowid
        con.execute("UPDATE akte SET sachbearbeiter_id = ? WHERE id = ?", (p1, a))
        b2 = con.execute("INSERT INTO zeit_bearbeiter (name, person_id) VALUES ('RAin Kolb', ?)", (p2,)).lastrowid
    s = sitzung.beginnen(con, a, titel="LG Freiburg", jetzt=BEGINN)
    assert (s["person_id"], s["wahrgenommen_von"]) == (p1, "RA Albrecht Tiedemann")
    assert sitzung.abschluss(con, s["id"], jetzt=BEGINN)["bearbeiter_id"] is None
    sitzung.beenden(con, s["id"], protokoll_uebernehmen=False, jetzt=BEGINN)

    s = sitzung.beginnen(con, a, titel="LG Freiburg", jetzt=BEGINN, person_id=p2)
    vorschlag = sitzung.abschluss(con, s["id"], jetzt=BEGINN)
    assert vorschlag["bearbeiter_id"] == b2
    assert vorschlag["protokoll"].splitlines()[0].endswith("(LG Freiburg), wahrgenommen von RAin Jana Kolb")
    sitzung.beenden(con, s["id"], protokoll_uebernehmen=False, jetzt=BEGINN)
    with pytest.raises(LookupError, match="Eigene Daten"):
        sitzung.beginnen(con, a, person_id=9999)
