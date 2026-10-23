"""Aktenverwaltung Stufe 2: Verfahren, Fristen/Termine, Notizen, Rubrum und Akte aus Dokument.

Alle Texte stammen aus der fiktiven Testakte „Brückner ./. Weber Haustechnik GmbH“.
"""

from datetime import date

import pytest

from juracore.aktenverwaltung import (
    aus_dokument,
    beteiligte,
    einrichten,
    kalender,
    notizen,
    rubrum,
    stammdaten,
    verfahren,
)
from juracore.dokumente import akte
from juracore.eigene import daten as eigene
from juracore.rpc import Kern

HEUTE = date(2026, 9, 25)


@pytest.fixture
def con(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    eigene.einrichten(verbindung)
    einrichten(verbindung)
    yield verbindung
    verbindung.close()


def neue_akte(con, name="Brückner ./. Weber"):
    return akte.akte_anlegen(con, name)["id"]


def abschnitte(*texte):
    return [{"nr": i, "seite": 1, "text": t} for i, t in enumerate(texte, 1)]


ANSPRUCHSBEGRUENDUNG = abschnitte(
    "Seefeld Rechtsanwälte",
    "Bertoldstraße 48 · 79098 Freiburg im Breisgau",
    "An das",
    "Landgericht Freiburg im Breisgau",
    "Salzstraße 17",
    "79098 Freiburg im Breisgau",
    "Freiburg, den 20.08.2026",
    "Unser Zeichen: 388/26 SE",
    "Aktenzeichen: 2 O 233/26",
    "Anspruchsbegründung",
    "In dem Rechtsstreit",
    "der Frau Dr. Lena Brückner, Ahornstieg 7, 79100 Freiburg im Breisgau, – Klägerin –",
    "Prozessbevollmächtigte: Seefeld Rechtsanwälte, Bertoldstraße 48, 79098 Freiburg im Breisgau",
    "gegen",
    "die Weber Haustechnik GmbH, Elzstraße 21, 79312 Emmendingen, vertreten durch den Geschäftsführer Markus Weber,",
    "– Beklagte –",
    "Prozessbevollmächtigte: Albrecht Tiedemann Rechtsanwälte, Kaiser-Joseph-Straße 300, 79098 Freiburg im Breisgau",
    "wegen: Rückzahlung einer Abschlagszahlung aus Werkvertrag Streitwert: 14.860,00 €",
    "begründen wir den im Mahnverfahren geltend gemachten Anspruch und werden beantragen:",
    "(3) Mit Schreiben vom 18.03.2026 setzte die Klägerin eine Frist zur Fortsetzung bis zum 01.04.2026.",
)

MAHNBESCHEID = abschnitte(
    "Amtsgericht Stuttgart",
    "– Zentrales Mahngericht Baden-Württemberg –",
    "Geschäftsnummer: 26-4815162-0-3",
    "Mahnbescheid",
    "Antragsteller:",
    "Frau Dr. Lena Brückner, Ahornstieg 7, 79100 Freiburg im Breisgau Prozessbevollmächtigte des Antragstellers:",
    "Seefeld Rechtsanwälte, Bertoldstraße 48, 79098 Freiburg im Breisgau, Zeichen 388/26 SE",
    "Antragsgegner:",
    "Weber Haustechnik GmbH, Elzstraße 21, 79312 Emmendingen, vertreten durch den Geschäftsführer Markus Weber",
    "Der Antragsteller macht gegen Sie folgende Ansprüche geltend: Hauptforderung: Rückzahlung Abschlagszahlung "
    "aus Werkvertrag (Heizungsanlage) vom 12.01.2026 – 14.860,00 EUR",
    "Sie werden aufgefordert, binnen zwei Wochen seit der Zustellung dieses Bescheids die behaupteten Beträge zu "
    "begleichen oder dem Gericht mitzuteilen, ob und in welchem Umfang Sie dem Anspruch widersprechen.",
    "Zustellungsvermerk: zugestellt am 08.06.2026",
)

VERFUEGUNG = abschnitte(
    "Landgericht Freiburg im Breisgau",
    "2. Zivilkammer",
    "Aktenzeichen: 2 O 233/26",
    "Freiburg, 27.08.2026",
    "In dem Rechtsstreit",
    "Dr. Lena Brückner ./. Weber Haustechnik GmbH",
    "Verfügung",
    "2. Der Beklagten wird aufgegeben, binnen einer Frist von vier Wochen nach Zustellung dieser Verfügung "
    "schriftlich auf die Anspruchsbegründung zu erwidern (§ 697 Abs. 2, § 275 Abs. 1 Satz 1 ZPO).",
    "3. Termin zur Güteverhandlung und zum sich unmittelbar anschließenden frühen ersten Termin wird bestimmt auf",
    "Donnerstag, 19.11.2026, 10:30 Uhr, Saal 104",
    "Empfangsbekenntnis der Prozessbevollmächtigten der Beklagten: zugestellt am 01.09.2026",
)

TERMINSVERLEGUNG = abschnitte(
    "Aktenzeichen: 2 O 233/26",
    "der Termin vom 19.11.2026 muss aus dienstlichen Gründen aufgehoben werden.",
    "Neuer Termin zur Güteverhandlung und zum frühen ersten Termin:",
    "Donnerstag, 26.11.2026, 11:00 Uhr, Saal 104",
)


# --------------------------------------------------------------------------- Verfahren


def test_verfahren_mit_instanz_und_gericht_als_beteiligter(con):
    a = neue_akte(con)
    liste = verfahren.speichern(con, a, {"art": "mahnverfahren", "gericht": "Amtsgericht Stuttgart",
                                         "aktenzeichen": "26-4815162-0-3", "beginn": "2026-06-03"})
    assert liste[0]["instanz"] is None and liste[0]["aktuell"]
    liste = verfahren.speichern(con, a, {"art": "klage", "gericht": "Landgericht Freiburg im Breisgau",
                                         "aktenzeichen": "2 O 233/26", "beginn": "2026-07-10"})
    klage = liste[-1]
    assert klage["instanz"] == "1. Instanz" and klage["aktuell"] and not liste[0]["aktuell"]
    assert klage["bezeichnung"] == "Klageverfahren, 1. Instanz · Landgericht Freiburg im Breisgau, 2 O 233/26"
    gerichte = [b for b in stammdaten.beteiligungen(con, a) if b["rolle"] == "gericht"]
    assert {(g["name"], g["aktenzeichen"]) for g in gerichte} == {
        ("Amtsgericht Stuttgart", "26-4815162-0-3"), ("Landgericht Freiburg im Breisgau", "2 O 233/26")}
    # Mahnverfahren abschließen: das Klageverfahren bleibt aktuell; das Gericht wird nicht doppelt eingetragen.
    verfahren.speichern(con, a, {"status": "abgeschlossen"}, liste[0]["id"])
    liste = verfahren.speichern(con, a, {"spruchkoerper": "2. Zivilkammer"}, klage["id"])
    assert liste[-1]["spruchkoerper"] == "2. Zivilkammer" and liste[-1]["instanz"] == "1. Instanz"
    assert len([b for b in stammdaten.beteiligungen(con, a) if b["rolle"] == "gericht"]) == 2


def test_verfahren_pruefungen(con):
    a = neue_akte(con)
    with pytest.raises(ValueError, match="Art des Verfahrens"):
        verfahren.speichern(con, a, {"art": ""})
    with pytest.raises(ValueError, match="Instanz"):
        verfahren.speichern(con, a, {"art": "klage", "instanz": "4. Instanz"})
    v = verfahren.speichern(con, a, {"art": "berufung"})[0]
    assert v["instanz"] == "2. Instanz"
    assert verfahren.loeschen(con, v["id"]) == []


# --------------------------------------------------------------------------- Fristen, Termine, Wiedervorlagen


def test_frist_mit_fristenrechner_und_lage(con):
    a = neue_akte(con)
    liste = kalender.speichern(con, a, {
        "art": "frist", "titel": "Klageerwiderung", "vorfrist": "2026-09-22",
        "berechnung": {"bezugstag": "2026-09-01", "anzahl": 4, "einheit": "wochen", "land": "BW"}}, heute=HEUTE)
    f = liste[0]
    assert f["datum"] == "2026-09-29" and f["berechnung"]["wochentag"] == "Dienstag"
    assert "§ 188 Abs. 2 BGB" in f["berechnung"]["grundlagen"]
    assert f["lage"] == "vorfrist" and f["in_tagen"] == 4
    kalender.speichern(con, a, {"art": "termin", "titel": "Güteverhandlung", "datum": "2026-11-19",
                                "uhrzeit": "10.30", "ort": "Saal 104"}, heute=HEUTE)
    kalender.speichern(con, a, {"art": "wiedervorlage", "titel": "Akte vorlegen", "datum": "2026-09-20"}, heute=HEUTE)
    liste = kalender.liste(con, a, HEUTE)
    assert [e["titel"] for e in liste] == ["Akte vorlegen", "Klageerwiderung", "Güteverhandlung"]
    assert liste[0]["lage"] == "abgelaufen" and liste[2]["uhrzeit"] == "10:30"
    liste = kalender.erledigen(con, liste[0]["id"], vermerk="erledigt", heute=HEUTE)
    assert liste[-1]["titel"] == "Akte vorlegen" and liste[-1]["lage"] == "erledigt"
    naechste = kalender.naechste(con, tage=7, heute=HEUTE)
    assert [e["titel"] for e in naechste] == ["Klageerwiderung"]
    assert naechste[0]["akte"] == "Brückner ./. Weber"
    assert kalender.naechste_je_akte(con, HEUTE)[a]["titel"] == "Klageerwiderung"


def test_kalender_pruefungen(con):
    a = neue_akte(con)
    with pytest.raises(ValueError, match="worum es geht"):
        kalender.speichern(con, a, {"art": "frist", "datum": "2026-10-01"})
    with pytest.raises(ValueError, match="Datum"):
        kalender.speichern(con, a, {"art": "frist", "titel": "X"})
    with pytest.raises(ValueError, match="Vorfrist"):
        kalender.speichern(con, a, {"art": "frist", "titel": "X", "datum": "2026-10-01", "vorfrist": "2026-10-02"})
    with pytest.raises(ValueError, match="Uhrzeit"):
        kalender.speichern(con, a, {"art": "termin", "titel": "X", "datum": "2026-10-01", "uhrzeit": "25:00"})


def test_vorschlaege_mahnbescheid_und_verfuegung():
    v = kalender.vorschlaege(MAHNBESCHEID, "2026-06-03", "BW")
    assert len(v) == 1
    assert (v[0]["titel"], v[0]["datum"], v[0]["vorfrist"]) == ("Widerspruchsfrist (Mahnbescheid)", "2026-06-22",
                                                                  "2026-06-15")
    assert v[0]["fundstelle"]["abschnitt"] == 11 and v[0]["bezug_fundstelle"]["abschnitt"] == 12

    v = kalender.vorschlaege(VERFUEGUNG, "2026-08-27", "BW")
    assert [(x["art"], x["datum"]) for x in v] == [("frist", "2026-09-29"), ("termin", "2026-11-19")]
    assert v[0]["titel"] == "Erwiderung auf die Anspruchsbegründung"
    assert v[0]["berechnung"]["bezugstag"] == "2026-09-01"
    assert (v[1]["titel"], v[1]["uhrzeit"], v[1]["ort"]) == ("Güteverhandlung und früher erster Termin", "10:30",
                                                             "Saal 104")


def test_vorschlaege_ohne_zustellung_und_alte_fristen():
    ohne = abschnitte("Der Beklagten wird aufgegeben, binnen zwei Wochen nach Zustellung Stellung zu nehmen.")
    v = kalender.vorschlaege(ohne)
    assert v[0]["datum"] is None and "Bezugstag" in v[0]["hinweis"]
    # Eine im Schriftsatz geschilderte, längst abgelaufene Frist ist kein Vorschlag.
    assert kalender.vorschlaege(ANSPRUCHSBEGRUENDUNG, "2026-08-20") == []


def test_vorschlaege_terminsverlegung(con):
    a = neue_akte(con)
    kalender.speichern(con, a, {"art": "termin", "titel": "Güteverhandlung", "datum": "2026-11-19"})
    vorhandene = [dict(z) for z in con.execute("SELECT * FROM kalender")]
    v = kalender.vorschlaege(TERMINSVERLEGUNG, "2026-10-05", "BW", vorhandene)
    assert [(x["art"], x["datum"]) for x in v] == [("erledigen", "2026-11-19"), ("termin", "2026-11-26")]
    assert v[0]["eintrag_id"] == vorhandene[0]["id"] and v[0]["vermerk"] == "Termin aufgehoben"
    # Schon eingetragene Termine werden nicht noch einmal vorgeschlagen.
    assert kalender.vorschlaege(VERFUEGUNG, None, "BW", vorhandene)[1:] == []


# --------------------------------------------------------------------------- Notizen


def test_notizen(con):
    a = neue_akte(con)
    notizen.speichern(con, a, "Mandant ruft Montag zurück.")
    liste = notizen.speichern(con, a, "Vergleichsbereitschaft bis 8.000 €", angeheftet=True)
    assert [n["text"] for n in liste] == ["Vergleichsbereitschaft bis 8.000 €", "Mandant ruft Montag zurück."]
    liste = notizen.anheften(con, liste[0]["id"], False)
    liste = notizen.speichern(con, a, "Mandant ruft Dienstag zurück.", notiz_id=liste[-1]["id"])
    assert any(n["text"] == "Mandant ruft Dienstag zurück." for n in liste)
    with pytest.raises(ValueError, match="leer"):
        notizen.speichern(con, a, "  ")
    assert len(notizen.loeschen(con, liste[0]["id"])) == 1


# --------------------------------------------------------------------------- Rubrum


def test_rubrum_anspruchsbegruendung():
    r = rubrum.erkenne(ANSPRUCHSBEGRUENDUNG)
    assert r["gericht"]["name"] == "Landgericht Freiburg im Breisgau"
    assert r["gericht"]["anschrift"] == {"strasse": "Salzstraße 17", "plz": "79098", "ort": "Freiburg im Breisgau"}
    assert r["aktenzeichen"]["wert"] == "2 O 233/26" and r["aktenzeichen"]["fundstelle"]["abschnitt"] == 9
    assert r["gegenstand"]["wert"] == "Rückzahlung einer Abschlagszahlung aus Werkvertrag"
    assert r["streitwert"]["wert"] == "14.860,00" and r["verfahren_art"] == "klage"
    assert r["kurzbezeichnung"] == "Brückner ./. Weber Haustechnik GmbH"
    klaegerin, beklagte = r["parteien"]
    assert (klaegerin["art"], klaegerin["seite"], klaegerin["rolle"]) == ("person", "aktiv", "Klägerin")
    assert klaegerin["daten"] | {} == {"anrede": "Frau", "titel": "Dr.", "vorname": "Lena", "nachname": "Brückner",
                                       "strasse": "Ahornstieg 7", "plz": "79100", "ort": "Freiburg im Breisgau"}
    assert klaegerin["bevollmaechtigte"]["name"] == "Seefeld Rechtsanwälte"
    assert klaegerin["bevollmaechtigte"]["zeichen"] == "388/26 SE"  # aus dem Briefkopf
    assert (beklagte["art"], beklagte["name"], beklagte["seite"]) == ("organisation", "Weber Haustechnik GmbH",
                                                                     "passiv")
    assert beklagte["vertreter"][0]["funktion"] == "Geschäftsführer"
    assert beklagte["vertreter"][0]["name"] == "Markus Weber"
    assert beklagte["bevollmaechtigte"]["name"] == "Albrecht Tiedemann Rechtsanwälte"


def test_rubrum_klage_ohne_einleitung():
    """Rubrum direkt nach der Dokumentart („Klage¶der Frau …“), Streitwert mit Zusatz in Klammern."""
    r = rubrum.erkenne(abschnitte(
        "Albrecht Tiedemann Rechtsanwälte", "An das", "Landgericht Freiburg im Breisgau", "Unser Zeichen: 117/25 SA",
        "Klage",
        "der Frau Dr. Lena Brückner, Ahornstieg 7, 79100 Freiburg im Breisgau, – Klägerin –",
        "Prozessbevollmächtigte: Albrecht Tiedemann Rechtsanwälte, Kaiser-Joseph-Straße 300, 79098 Freiburg im Breisgau",
        "gegen",
        "die Autohaus Rehnfeld GmbH, vertreten durch den Geschäftsführer Markus Rehnfeld, Gewerbering 112, "
        "79211 Denzlingen,",
        "– Beklagte –",
        "wegen: Rückabwicklung eines Kaufvertrags",
        "Streitwert (vorläufig): 14.555,40 €",
    ))
    assert [(p["name"], p["seite"]) for p in r["parteien"]] == [
        ("Dr. Lena Brückner", "aktiv"), ("Autohaus Rehnfeld GmbH", "passiv")]
    assert r["parteien"][0]["bevollmaechtigte"]["name"] == "Albrecht Tiedemann Rechtsanwälte"
    assert r["dokumentart"]["wert"] == "Klage" and r["gericht"]["name"] == "Landgericht Freiburg im Breisgau"
    assert r["streitwert"]["wert"] == "14.555,40" and r["kurzbezeichnung"]


def test_rubrum_mahnbescheid():
    r = rubrum.erkenne(MAHNBESCHEID)
    assert r["verfahren_art"] == "mahnverfahren" and r["aktenzeichen"]["wert"] == "26-4815162-0-3"
    assert r["gericht"]["name"] == "Amtsgericht Stuttgart"
    assert [(p["name"], p["seite"], p["rolle"]) for p in r["parteien"]] == [
        ("Dr. Lena Brückner", "aktiv", "Antragsteller"), ("Weber Haustechnik GmbH", "passiv", "Antragsgegner")]
    assert r["parteien"][0]["bevollmaechtigte"]["zeichen"] == "388/26 SE"
    assert r["streitwert"]["wert"] == "14.860,00"


def test_rubrum_zwei_beklagte_kommanditgesellschaft():
    r = rubrum.erkenne(abschnitte(
        "Landgericht Mannheim",
        "– Kammer für Handelssachen –",
        "Klage",
        "In Sachen",
        "Bäderbetriebe Lindenau GmbH",
        "Am Weilbad 3, 77999 Lindenau am Rhein",
        "gesetzlich vertreten durch die Geschäftsführerin Frau Dr. Petra Engelhardt – Klägerin –",
        "gegen",
        "Kornmeier Projektmanagement GmbH & Co. KG",
        "Neckarhafen 12, 68159 Mannheim",
        "gesetzlich vertreten durch ihre persönlich haftende Gesellschafterin, die Kornmeier Verwaltungs GmbH, diese "
        "vertreten durch ihren Geschäftsführer Herrn Tobias Kornmeier – Beklagte zu 1) –",
        "Kornmeier Verwaltungs GmbH",
        "Neckarhafen 12, 68159 Mannheim",
        "gesetzlich vertreten durch ihren Geschäftsführer Herrn Tobias Kornmeier – Beklagte zu 2) –",
        "wegen Schadensersatz aus Projektsteuerungsvertrag",
    ))
    assert r["gericht"]["spruchkoerper"] == "Kammer für Handelssachen"
    assert [(p["name"], p["zusatz"]) for p in r["parteien"]] == [
        ("Bäderbetriebe Lindenau GmbH", ""), ("Kornmeier Projektmanagement GmbH & Co. KG", "zu 1)"),
        ("Kornmeier Verwaltungs GmbH", "zu 2)")]
    assert r["parteien"][0]["vertreter"][0]["daten"]["anrede"] == "Frau"
    assert r["parteien"][1]["vertreter"] == [] and "Kornmeier Verwaltungs GmbH" in r["parteien"][1]["hinweise"][0]
    assert r["kurzbezeichnung"].endswith("u. a.")
    assert "Kein gerichtliches Aktenzeichen gefunden." in r["hinweise"]


def test_rubrum_kurzrubrum():
    r = rubrum.erkenne(VERFUEGUNG)
    assert [(p["name"], p["seite"]) for p in r["parteien"]] == [("Dr. Lena Brückner", "aktiv"),
                                                                ("Weber Haustechnik GmbH", "passiv")]
    assert r["gericht"]["spruchkoerper"] == "2. Zivilkammer"


# --------------------------------------------------------------------------- Akte aus Dokument


def test_vorschau_erkennt_eigene_seite_und_treffer(con):
    from juracore.aktenverwaltung import beteiligte
    beteiligte.speichern(con, "person", {"vorname": "Lena", "nachname": "Brückner", "titel": "Dr."})
    r = aus_dokument.vorschau(con, ANSPRUCHSBEGRUENDUNG, ["Albrecht Tiedemann Rechtsanwälte"])
    assert r["eigene_seite"]["wert"] == "passiv"
    assert r["parteien"][0]["treffer"][0]["stufe"] == "gleich"
    assert r["parteien"][1]["bevollmaechtigte"]["eigene"]


def test_akte_aus_dokument_ueber_kern(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    datei = tmp_path / "Anspruchsbegruendung.txt"
    datei.write_text("\n\n".join(a["text"] for a in ANSPRUCHSBEGRUENDUNG), encoding="utf-8")
    vorschau = kern.methoden["akten.rubrum_lesen"](pfad=str(datei))
    assert vorschau["kurzbezeichnung"] == "Brückner ./. Weber Haustechnik GmbH"
    auswahl = {
        "name": vorschau["kurzbezeichnung"], "eigene_seite": "passiv",
        "gegenstand": vorschau["gegenstand"]["wert"], "gegenstandswert": vorschau["streitwert"]["wert"],
        "parteien": vorschau["parteien"],
        "verfahren": {"art": "klage", "gericht": vorschau["gericht"]["name"],
                      "aktenzeichen": vorschau["aktenzeichen"]["wert"],
                      "gericht_anschrift": vorschau["gericht"]["anschrift"]},
    }
    neu = kern.methoden["akten.aus_dokument_anlegen"](pfad=str(datei), auswahl=auswahl)
    assert neu["mandanten"] == ["Weber Haustechnik GmbH"] and neu["gegner"] == ["Dr. Lena Brückner"]
    assert neu["gegenstandswert"] == "14860.00" and neu["eigene_rolle"] == "Prozessbevollmächtigter des Beklagten"
    assert neu["verfahren"] == "Klageverfahren, 1. Instanz · Landgericht Freiburg im Breisgau, 2 O 233/26"
    assert neu["dokumente"] == 1
    s = kern.methoden["akten.stammdaten"](akte_id=neu["id"])
    rollen = {(b["rolle"], b["name"], b["aktenzeichen"]) for b in s["beteiligte"]}
    assert ("bevollmaechtigter_gegner", "Seefeld Rechtsanwälte", "388/26 SE") in rollen
    assert ("gericht", "Landgericht Freiburg im Breisgau", "2 O 233/26") in rollen
    assert not any(b["name"] == "Albrecht Tiedemann Rechtsanwälte" for b in s["beteiligte"])
    gericht = next(b for b in s["beteiligte"] if b["rolle"] == "gericht")
    daten = kern.methoden["beteiligte.eintrag"](beteiligter_id=gericht["beteiligter_id"])["daten"]
    assert (daten["kategorie"], daten["strasse"], daten["plz"]) == ("Gericht", "Salzstraße 17", "79098")
    weber = next(b for b in s["beteiligte"] if b["rolle"] == "mandant")
    gf = kern.methoden["beteiligte.eintrag"](beteiligter_id=weber["beteiligter_id"])["beziehungen"]
    assert gf[0]["text"].startswith("vertreten durch Markus Weber")
    # Vorschläge aus dem eingelesenen Dokument (keine, die Frist im Schriftsatz ist abgelaufen) und die Übersicht.
    assert kern.methoden["akten.kalender_vorschlaege"](akte_id=neu["id"], land="BW") == []
    assert kern.methoden["akten.liste"]()[0]["naechste"] is None


def test_akte_aus_dokument_ohne_seite_legt_nichts_an(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    datei = tmp_path / "Anspruchsbegruendung.txt"
    datei.write_text("\n\n".join(a["text"] for a in ANSPRUCHSBEGRUENDUNG), encoding="utf-8")
    with pytest.raises(ValueError, match="welche Seite"):
        kern.methoden["akten.aus_dokument_anlegen"](pfad=str(datei), auswahl={"name": "X", "parteien": []})
    assert kern.methoden["akten.liste"]() == []


def test_gerichtsanschrift_aus_dem_kopf():
    r = rubrum.erkenne(abschnitte(
        "Landgericht Freiburg im Breisgau 2. Zivilkammer Salzstraße 17, 79098 Freiburg im Breisgau",
        "FIKTIVES DOKUMENT", "Aktenzeichen: 2 O 233/26", "In dem Rechtsstreit"))
    assert (r["gericht"]["name"], r["gericht"]["spruchkoerper"]) == ("Landgericht Freiburg im Breisgau", "2. Zivilkammer")
    assert r["gericht"]["anschrift"] == {"strasse": "Salzstraße 17", "plz": "79098", "ort": "Freiburg im Breisgau"}
    r = rubrum.erkenne(abschnitte("An das", "Landgericht Berlin II", "Hans-Litten-Straße 16",
                                  "10179 Berlin FIKTIV", "Klage"))
    assert r["gericht"]["anschrift"]["strasse"].startswith("Hans-Litten-Straße 16")
    assert r["gericht"]["anschrift"]["ort"] == "Berlin"


def test_gericht_ergaenzt_nur_leere_felder(con):
    a = neue_akte(con)
    lg = {"strasse": "Salzstraße 17", "plz": "79098", "ort": "Freiburg im Breisgau"}
    verfahren.speichern(con, a, {"art": "klage", "gericht": "Landgericht Freiburg im Breisgau"},
                        gericht_daten={"strasse": "Salzstraße 17", "plz": "79098"})
    verfahren.speichern(con, neue_akte(con, "Zweite"), {"art": "klage", "gericht": "Landgericht Freiburg im Breisgau"},
                        gericht_daten={"strasse": "Falsche Straße 1", "ort": "Freiburg im Breisgau"})
    g = next(b for b in stammdaten.beteiligungen(con, a) if b["rolle"] == "gericht")
    daten = beteiligte.eintrag(con, g["beteiligter_id"])["daten"]
    assert {k: daten[k] for k in lg} == lg and daten["kategorie"] == "Gericht"


# --------------------------------------------------------------------------- Weiteres Verfahren aus Dokument


def _weber_aus_mahnbescheid(kern, tmp_path):
    """Akte Weber wie in der Testakte: angelegt aus dem Mahnbescheid, wir vertreten die Antragsgegnerin."""
    mb = tmp_path / "Mahnbescheid.txt"
    mb.write_text("\n\n".join(a["text"] for a in MAHNBESCHEID), encoding="utf-8")
    v = kern.methoden["akten.rubrum_lesen"](pfad=str(mb))
    auswahl = {"name": "Brückner ./. Weber", "eigene_seite": "passiv", "parteien": v["parteien"],
               "verfahren": {"art": "mahnverfahren", "gericht": v["gericht"]["name"],
                             "aktenzeichen": v["aktenzeichen"]["wert"]}}
    return kern.methoden["akten.aus_dokument_anlegen"](pfad=str(mb), auswahl=auswahl)["id"]


def _auswahl_wie_pruefansicht(v):
    """Was die Prüfansicht mit ihren Vorgaben schickt: neue Parteien und Bevollmächtigte angehakt, vorhandene nicht."""
    return {
        "eigene_seite": v["eigene_seite"]["wert"],
        "parteien": [p | {"uebernehmen": not p["in_akte"],
                          "bevollmaechtigte": p["bevollmaechtigte"] and p["bevollmaechtigte"] | {
                              "uebernehmen": not p["bevollmaechtigte"]["in_akte"] and not p["bevollmaechtigte"]["eigene"]}}
                     for p in v["parteien"]],
        "verfahren": {"art": v["verfahren_art"], "instanz": "1. Instanz", "gericht": v["gericht"]["name"],
                      "aktenzeichen": v["aktenzeichen"]["wert"], "beginn": "2026-07-09",
                      "gericht_anschrift": v["gericht"].get("anschrift")},
        "abschliessen": [x["id"] for x in v["laufende_verfahren"]],
    }


def test_verfahren_aus_neuem_dokument(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    a = _weber_aus_mahnbescheid(kern, tmp_path)
    ab = tmp_path / "Anspruchsbegruendung.txt"
    ab.write_text("\n\n".join(a["text"] for a in ANSPRUCHSBEGRUENDUNG), encoding="utf-8")
    v = kern.methoden["akten.rubrum_lesen"](pfad=str(ab), akte_id=a)
    # Die Seite kommt aus der Akte (Brückner ist dort Gegnerin), nicht aus den Bevollmächtigten.
    assert v["eigene_seite"] == {"wert": "passiv", "grund": "Dr. Lena Brückner ist in dieser Akte Gegner."}
    assert [p["in_akte"]["rolle"] for p in v["parteien"]] == ["gegner", "mandant"]
    assert v["parteien"][0]["bevollmaechtigte"]["in_akte"]["rolle"] == "bevollmaechtigter_gegner"
    assert v["verfahren_vorhanden"] is None
    assert [x["art"] for x in v["laufende_verfahren"]] == ["mahnverfahren"]
    vorher = kern.methoden["akten.stammdaten"](akte_id=a)["beteiligte"]

    liste = kern.methoden["akten.verfahren_aus_dokument"](akte_id=a, auswahl=_auswahl_wie_pruefansicht(v), pfad=str(ab))
    assert [(x["art"], x["status"], x["ende"]) for x in liste] == [
        ("mahnverfahren", "abgeschlossen", "2026-07-09"), ("klage", "laufend", None)]
    assert liste[1]["aktuell"] and liste[1]["bezeichnung"].endswith("Landgericht Freiburg im Breisgau, 2 O 233/26")
    s = kern.methoden["akten.stammdaten"](akte_id=a)
    assert s["dokumente"] == 2
    neu = [(b["rolle"], b["name"]) for b in s["beteiligte"] if b["id"] not in {x["id"] for x in vorher}]
    assert neu == [("gericht", "Landgericht Freiburg im Breisgau")]  # keine doppelten Parteien
    # Dasselbe Dokument noch einmal: das Verfahren steht schon in der Akte.
    v2 = kern.methoden["akten.rubrum_lesen"](pfad=str(ab), akte_id=a)
    assert v2["verfahren_vorhanden"]["bezeichnung"].startswith("Klageverfahren")
    assert len(v2["laufende_verfahren"]) == 1


def test_verfahren_aus_dokument_der_akte(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    a = _weber_aus_mahnbescheid(kern, tmp_path)
    ab = tmp_path / "Anspruchsbegruendung.txt"
    ab.write_text("\n\n".join(a["text"] for a in ANSPRUCHSBEGRUENDUNG), encoding="utf-8")
    dok = kern.methoden["akten.importieren"](akte_id=a, pfad=str(ab))
    v = kern.methoden["akten.rubrum_lesen"](dokument_id=dok["dokument_id"])  # Akte ergibt sich aus dem Dokument
    assert v["dateiname"] == "Anspruchsbegruendung.txt" and v["aktenzeichen"]["wert"] == "2 O 233/26"
    assert not any("Streitwert" in h or "Gegenstand" in h for h in v["hinweise"])
    assert v["eigene_seite"]["wert"] == "passiv" and v["parteien"][0]["in_akte"]
    # Eine neue Partei ohne Angabe der Seite: nichts wird eingetragen.
    ohne_seite = _auswahl_wie_pruefansicht(v) | {"eigene_seite": ""}
    ohne_seite["parteien"][0] = ohne_seite["parteien"][0] | {"in_akte": None, "uebernehmen": True}
    with pytest.raises(ValueError, match="welche Seite"):
        kern.methoden["akten.verfahren_aus_dokument"](akte_id=a, auswahl=ohne_seite)
    assert len(kern.methoden["akten.verfahren"](akte_id=a)) == 1
    liste = kern.methoden["akten.verfahren_aus_dokument"](
        akte_id=a, auswahl=_auswahl_wie_pruefansicht(v) | {"abschliessen": []})
    assert [x["status"] for x in liste] == ["laufend", "laufend"]
    assert kern.methoden["akten.stammdaten"](akte_id=a)["dokumente"] == 2


def test_verfahren_aus_dokument_ohne_art_liest_nichts_ein(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    a = _weber_aus_mahnbescheid(kern, tmp_path)
    ab = tmp_path / "Anspruchsbegruendung.txt"
    ab.write_text("\n\n".join(a["text"] for a in ANSPRUCHSBEGRUENDUNG), encoding="utf-8")
    with pytest.raises(ValueError, match="Art des Verfahrens"):
        kern.methoden["akten.verfahren_aus_dokument"](akte_id=a, auswahl={"verfahren": {}}, pfad=str(ab))
    assert kern.methoden["akten.stammdaten"](akte_id=a)["dokumente"] == 1


def test_verfahren_aus_kurzrubrum_ohne_unnoetige_hinweise(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    a = _weber_aus_mahnbescheid(kern, tmp_path)
    vf = tmp_path / "Verfuegung.txt"
    vf.write_text("\n\n".join(a["text"] for a in VERFUEGUNG), encoding="utf-8")
    v = kern.methoden["akten.rubrum_lesen"](pfad=str(vf), akte_id=a)
    assert all(p["in_akte"] for p in v["parteien"]) and v["hinweise"] == []
    assert v["gericht"]["spruchkoerper"] == "2. Zivilkammer"
    # Ergänzen statt doppelt anlegen: der Spruchkörper kommt dazu, Beginn und Aktenzeichen bleiben.
    vorhanden = kern.methoden["akten.verfahren"](akte_id=a)[0]
    auswahl = _auswahl_wie_pruefansicht(v) | {"verfahren_id": vorhanden["id"]}
    auswahl["verfahren"] = auswahl["verfahren"] | {"art": "mahnverfahren", "aktenzeichen": "", "beginn": "",
                                                   "spruchkoerper": "Zentrales Mahngericht Baden-Württemberg"}
    liste = kern.methoden["akten.verfahren_aus_dokument"](akte_id=a, auswahl=auswahl)
    assert len(liste) == 1 and liste[0]["aktenzeichen"] == "26-4815162-0-3"
    assert liste[0]["spruchkoerper"] == "Zentrales Mahngericht Baden-Württemberg"
