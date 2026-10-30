import pytest

from juracore.dokumente import akte, anmerkungen, ansicht

from .conftest import schreibe_pdf


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    anmerkungen.einrichten(con)
    yield con
    con.close()


def _dokument(akten, con, tmp_path, text, name="klage.md", akte_name="Brückner"):
    a = next((x for x in akte.akten(akten) if x["name"] == akte_name), None) or akte.akte_anlegen(akten, akte_name)
    (tmp_path / name).write_text(text, encoding="utf-8")
    return akte.importiere(akten, con, a["id"], tmp_path / name, tmp_path / "ablage", ocr=False)["dokument_id"], a["id"]


def _gesamttext(akten, dokument_id):
    return "\n".join(a["text"] for a in akte.dokument(akten, dokument_id)["abschnitte"])


TEXT = ("(1) Die Klägerin erklärte den Rücktritt vom Kaufvertrag.\n\n"
        "(2) Die Frist zur Nacherfüllung lief am 07.07.2025 ab. Der Rücktritt war wirksam.")


def test_anlegen_aendern_loeschen(akten, con, tmp_path):
    d, a = _dokument(akten, con, tmp_path, TEXT)
    text = _gesamttext(akten, d)
    start = text.index("Rücktritt vom")
    m = anmerkungen.anlegen(akten, d, start - 1, start + len("Rücktritt vom Kaufvertrag"), farbe="gruen")
    # Leerraum am Rand der Auswahl fällt weg.
    assert m["zitat"] == "Rücktritt vom Kaufvertrag" and m["start"] == start
    assert (m["farbe"], m["stil"], m["kommentar"], m["status"], m["abschnitt"], m["rn"]) == (
        "gruen", "flaeche", None, "gefunden", 1, 1)

    m = anmerkungen.aendern(akten, m["id"], stil="unterstrichen", kommentar="  **Anlage K4** beigefügt?  \n")
    assert (m["stil"], m["kommentar"], m["farbe"]) == ("unterstrichen", "**Anlage K4** beigefügt?", "gruen")
    assert anmerkungen.aendern(akten, m["id"], farbe="rot")["kommentar"] == "**Anlage K4** beigefügt?"
    assert anmerkungen.aendern(akten, m["id"], ohne_kommentar=True)["kommentar"] is None

    with pytest.raises(ValueError):
        anmerkungen.aendern(akten, m["id"], farbe="lila")
    with pytest.raises(ValueError):
        anmerkungen.anlegen(akten, d, 3, 3)
    # Angeschnittene Wörter werden ganz markiert.
    teil = anmerkungen.anlegen(akten, d, start + 3, start + len("Rücktritt vom Ka"))
    assert teil["zitat"] == "Rücktritt vom Kaufvertrag"
    anmerkungen.loeschen(akten, teil["id"])

    assert [x["id"] for x in anmerkungen.liste(akten, akte_id=a)] == [m["id"]]
    assert anmerkungen.zahlen(akten, a) == {d: 1}
    anmerkungen.loeschen(akten, m["id"])
    assert anmerkungen.liste(akten, dokument_id=d) == []


def test_lesereihenfolge_und_dokument_loeschen(akten, con, tmp_path):
    d, a = _dokument(akten, con, tmp_path, TEXT)
    text = _gesamttext(akten, d)
    spaet = anmerkungen.anlegen(akten, d, text.index("wirksam"), text.index("wirksam") + 7)
    frueh = anmerkungen.anlegen(akten, d, text.index("Klägerin"), text.index("Klägerin") + 8, farbe="blau")
    assert [x["id"] for x in anmerkungen.liste(akten, dokument_id=d)] == [frueh["id"], spaet["id"]]
    assert spaet["abschnitt"] == 2
    akte.dokument_loeschen(akten, d, tmp_path / "ablage")
    assert anmerkungen.liste(akten, akte_id=a) == []


def test_wiederfinden_nach_geaendertem_text(akten, con, tmp_path):
    d, _ = _dokument(akten, con, tmp_path, TEXT)
    text = _gesamttext(akten, d)
    # "Der Rücktritt" steht zweimal sinngemäß; markiert ist das zweite "Rücktritt".
    zweite = text.rindex("Rücktritt")
    m = anmerkungen.anlegen(akten, d, zweite, zweite + len("Rücktritt"), kommentar="wirksam?")
    weg = anmerkungen.anlegen(akten, d, text.index("07.07.2025"), text.index("07.07.2025") + 10)

    # Neue Fassung: Satz davor eingefügt, Datum geändert.
    with akten:
        akten.execute("UPDATE abschnitt SET text = ? WHERE dokument_id = ? AND nr = 2", (
            "(2) Neu eingefügt. Die Frist zur Nacherfüllung lief am 14.07.2025 ab. Der Rücktritt war wirksam.", d))
    neu = _gesamttext(akten, d)
    liste = {x["id"]: x for x in anmerkungen.liste(akten, dokument_id=d)}
    assert liste[m["id"]]["status"] == "gefunden"
    assert liste[m["id"]]["start"] == neu.rindex("Rücktritt") and liste[m["id"]]["kommentar"] == "wirksam?"
    # Nicht mehr gefunden: bleibt erhalten, steht am Ende.
    assert liste[weg["id"]]["status"] == "nicht_gefunden" and liste[weg["id"]]["zitat"] == "07.07.2025"
    assert list(liste) == [m["id"], weg["id"]]


def test_wiederfinden_waehlt_passende_umgebung():
    text = "Der Rücktritt ist erklärt. Später: der Rücktritt war wirksam."
    assert anmerkungen.wiederfinden(text, "Rücktritt", "Später: der ", " war", None) == (39, 48)
    assert anmerkungen.wiederfinden(text, "Rücktritt", "Der ", " ist", 40) == (4, 13)
    assert anmerkungen.wiederfinden("a Rück-\ntritt b", "Rücktritt", "", "", 0) is None
    assert anmerkungen.wiederfinden("vom  Kauf\nvertrag", "vom Kauf vertrag", "", "", 0) == (0, 17)


def test_suche_in_wortlaut_kommentar_und_bedeutung(akten, con, tmp_path):
    d, a = _dokument(akten, con, tmp_path, TEXT)
    d2, a2 = _dokument(akten, con, tmp_path, "(1) Hallenbad ohne Rücktritt.", "b.md", "Hallenbad")
    text = _gesamttext(akten, d)
    eins = anmerkungen.anlegen(akten, d, text.index("Frist"), text.index("Frist") + 5, farbe="rot",
                               kommentar="Angemessenheit **bestritten**")
    zwei = anmerkungen.anlegen(akten, d2, 4, 13, farbe="gelb")
    assert [x["id"] for x in anmerkungen.suche(akten, "frist")] == [eins["id"]]
    assert [x["id"] for x in anmerkungen.suche(akten, "angemessenheit bestritten")] == [eins["id"]]
    assert [x["id"] for x in anmerkungen.suche(akten, "streitig")] == [eins["id"]]  # Bedeutung von Rot
    assert [x["id"] for x in anmerkungen.suche(akten, "hallenbad")] == [zwei["id"]]
    assert anmerkungen.suche(akten, "hallenbad", akte_id=a) == []
    treffer = anmerkungen.suche(akten, "Frist")[0]
    assert (treffer["akte"], treffer["dokument"], treffer["format"]) == ("Brückner", "klage.md", "md")
    assert anmerkungen.suche(akten, "  ") == []


def test_bedeutungen(akten):
    assert anmerkungen.bedeutungen(akten)["gelb"] == "Wichtig"
    werte = anmerkungen.bedeutungen_setzen(akten, {"gelb": "  Kernaussage ", "rot": "Definition"})
    assert werte == {"gelb": "Kernaussage", "gruen": "Erledigt", "blau": "Beweis", "rot": "Definition"}
    with pytest.raises(ValueError):
        anmerkungen.bedeutungen_setzen(akten, {"lila": "x"})
    with pytest.raises(ValueError):
        anmerkungen.bedeutungen_setzen(akten, {"gelb": " "})


def test_rechtecke_im_original(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "PDF")
    pdf = schreibe_pdf(tmp_path / "klage.pdf", [
        ["(1) Auf der ersten Seite steht nichts."],
        ["(2) Die Mechatronik ist defekt.", "Die Mechatronik wurde getauscht."],
    ])
    d = akte.importiere(akten, con, a["id"], pdf, tmp_path / "ablage", ocr=False)["dokument_id"]
    text = _gesamttext(akten, d)
    # Das zweite Vorkommen, über die Zeilengrenze hinweg.
    start = text.index("defekt.")
    m = anmerkungen.anlegen(akten, d, start, text.rindex("Mechatronik") + len("Mechatronik"))
    assert m["seite"] == 2
    assert anmerkungen.auf_seite(akten, d, 1) == []
    (auf,) = anmerkungen.auf_seite(akten, d, 2)
    assert auf["id"] == m["id"] and len(auf["rechtecke"]) == 2  # je Zeile ein Rechteck
    oben, unten = auf["rechtecke"]
    assert oben["y"] < unten["y"] and oben["x"] > unten["x"]

    nur_zweite = anmerkungen.anlegen(akten, d, text.rindex("Mechatronik"), text.rindex("Mechatronik") + 11)
    (r,) = next(x for x in anmerkungen.auf_seite(akten, d, 2) if x["id"] == nur_zweite["id"])["rechtecke"]
    assert r["y"] == unten["y"]  # nicht das erste "Mechatronik" in Zeile 1


def test_woerter_textebene(tmp_path):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(schreibe_pdf(tmp_path / "a.pdf", [["Erste Zeile hier", "Zweite"]]))
    woerter = ansicht.woerter_textebene(pdf[0])
    pdf.close()
    assert [(w[0], w[1]) for w in woerter] == [("Erste", 0), ("Zeile", 0), ("hier", 0), ("Zweite", 1)]
    assert all(0 < w[2] < 1 and 0 < w[3] < 1 and w[4] > 0 and w[5] > 0 for w in woerter)
    assert woerter[3][3] > woerter[0][3]


def test_markieren_im_original(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "PDF")
    pdf = schreibe_pdf(tmp_path / "klage.pdf", [
        ["(1) Auf der ersten Seite steht die Mechatronik."],
        ["(2) Die Mechatronik ist defekt.", "Die Mechatronik wurde getauscht."],
    ])
    d = akte.importiere(akten, con, a["id"], pdf, tmp_path / "ablage", ocr=False)["dokument_id"]
    woerter = anmerkungen.woerter(akten, d, 2)
    namen = [w[0] for w in woerter]
    # Das zweite "Mechatronik" auf Seite 2 bis "wurde" (über die Zeilengrenze).
    von = namen.index("defekt.")
    bis = len(namen) - 1 - namen[::-1].index("wurde")
    m = anmerkungen.anlegen_auf_seite(akten, d, 2, von, bis, farbe="blau")
    assert " ".join(m["zitat"].split()) == "defekt. Die Mechatronik wurde" and m["seite"] == 2 and m["farbe"] == "blau"
    nur = anmerkungen.anlegen_auf_seite(akten, d, 2, bis - 1, bis - 1)
    text = _gesamttext(akten, d)
    assert nur["start"] == text.rindex("Mechatronik")  # das Vorkommen an dieser Stelle, nicht das erste
    with pytest.raises(ValueError):
        anmerkungen.anlegen_auf_seite(akten, d, 2, 5, 2)


def test_original_stelle_trotz_ocr_abweichungen():
    t = object.__new__(anmerkungen._Text)
    teile = ["Der Gewährleistungsausschluss ist nach § 476 BGB unwirksam.",
             "Die Haftung ist nicht ausgeschlossen; § 476 BGB gilt."]
    t.abschnitte = [{"seite": 2, "seitenwechsel": "[]", "text": x} for x in teile]
    t.beginn = [0, len(teile[0]) + 1]
    t.text = "\n".join(teile)
    # „$“ statt „§“, Silbentrennung am Zeilenende, „8“ statt „§“: die zweite Fundstelle liegt näher an der Lage.
    von, bis = anmerkungen._auf_seite_finden(t, 2, "nach $ 476 BGB", 0.2)
    assert t.text[von:bis] == "nach § 476 BGB"
    von, bis = anmerkungen._auf_seite_finden(t, 2, "nicht ausge-", 0.7)
    assert t.text[von:bis] == "nicht ausge"
    von, bis = anmerkungen._auf_seite_finden(t, 2, "ausgeschlossen; 8 476 BGB", 0.9)
    assert t.text[von:bis] == "ausgeschlossen; § 476 BGB"
    assert anmerkungen._auf_seite_finden(t, 3, "BGB", 0.5) is None
    assert anmerkungen._auf_seite_finden(t, 2, "—", 0.5) is None
