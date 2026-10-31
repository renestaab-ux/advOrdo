import pytest

from juracore.dokumente import akte, anmerkungen, lesezeichen

from .conftest import schreibe_pdf


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    anmerkungen.einrichten(con)
    lesezeichen.einrichten(con)
    yield con
    con.close()


def _text(akten, dokument_id):
    return "\n".join(z["text"] for z in akten.execute(
        "SELECT text FROM abschnitt WHERE dokument_id = ? ORDER BY nr", (dokument_id,)))


def _dokument(akten, con, tmp_path, text, akte_id=None):
    a = akte_id or akte.akte_anlegen(akten, "Brückner")["id"]
    (tmp_path / "klage.md").write_text(text, encoding="utf-8")
    return akte.importiere(akten, con, a, tmp_path / "klage.md", tmp_path / "ablage", ocr=False)["dokument_id"], a


def _mit_gliederung(pfad, seiten, gliederung):
    """Fügt einem Test-PDF eine Gliederung hinzu: ``gliederung`` = [(Titel, Seitenindex, [Kinder …])]."""
    daten = schreibe_pdf(pfad, seiten).read_bytes()
    kopf, rest = daten.split(b"xref\n", 1)
    objekte = kopf.split(b"endobj\n")[:-1]
    texte = [o.split(b" 0 obj\n", 1)[1].rstrip(b"\n") for o in objekte]
    seiten_obj = [i + 1 for i, t in enumerate(texte) if t.startswith(b"<< /Type /Page ")]
    neu: list[bytes] = []
    wurzel = len(texte) + 1

    def baue(eintraege, eltern):
        ids = [len(texte) + len(neu) + 1 + k for k in range(len(eintraege))]
        neu.extend([b""] * len(eintraege))
        for k, (titel, seite, kinder) in enumerate(eintraege):
            teile = [b"/Title (" + titel.encode("cp1252") + b")", b"/Parent %d 0 R" % eltern,
                     b"/Dest [%d 0 R /XYZ 0 800 0]" % seiten_obj[seite]]
            if k:
                teile.append(b"/Prev %d 0 R" % ids[k - 1])
            if k + 1 < len(ids):
                teile.append(b"/Next %d 0 R" % ids[k + 1])
            if kinder:
                kind_ids = baue(kinder, ids[k])
                teile.append(b"/First %d 0 R /Last %d 0 R /Count %d" % (kind_ids[0], kind_ids[-1], len(kind_ids)))
            neu[ids[k] - len(texte) - 1] = b"<< " + b" ".join(teile) + b" >>"
        return ids

    neu.append(b"")
    oben = baue(gliederung, wurzel)
    neu[0] = b"<< /Type /Outlines /First %d 0 R /Last %d 0 R /Count %d >>" % (oben[0], oben[-1], len(oben))
    texte[0] = b"<< /Type /Catalog /Pages 2 0 R /Outlines %d 0 R >>" % wurzel
    texte += neu
    daten = b"%PDF-1.4\n"
    versaetze = []
    for i, t in enumerate(texte, start=1):
        versaetze.append(len(daten))
        daten += b"%d 0 obj\n" % i + t + b"\nendobj\n"
    xref = len(daten)
    daten += b"xref\n0 %d\n0000000000 65535 f \n" % (len(texte) + 1)
    daten += b"".join(b"%010d 00000 n \n" % v for v in versaetze)
    daten += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(texte) + 1, xref)
    pfad.write_bytes(daten)
    return pfad


def test_inhaltsverzeichnis_des_pdfs(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "PDF")
    pdf = _mit_gliederung(tmp_path / "klage.pdf", [
        ["Es wird beantragt, die Beklagte zur Zahlung von 500 EUR zu verurteilen."],
        ["Die Klaegerin kaufte am 14.03.2025 ein Fahrzeug von der Beklagten."],
        ["Rechtliches: Der Anspruch folgt aus dem Kaufvertrag und dem Gesetz."],
    ], [
        ("Anträge", 0, []),
        ("Begründung", 1, [("A. Sachverhalt", 1, []), ("B. Rechtliche Würdigung", 2, [])]),
    ])
    d = akte.importiere(akten, con, a["id"], pdf, tmp_path / "ablage", ocr=False)["dokument_id"]
    assert lesezeichen.inhalt(akten, d) == [
        {"ebene": 0, "titel": "Anträge", "seite": 1},
        {"ebene": 0, "titel": "Begründung", "seite": 2},
        {"ebene": 1, "titel": "A. Sachverhalt", "seite": 2},
        {"ebene": 1, "titel": "B. Rechtliche Würdigung", "seite": 3},
    ]
    # Ohne Gliederung bzw. kein PDF: leer.
    d2, _ = _dokument(akten, con, tmp_path, "Nur Text.", a["id"])
    assert lesezeichen.inhalt(akten, d2) == []
    # Lesezeichen am Seitenanfang und an gewählten Wörtern im Original.
    s = lesezeichen.anlegen_auf_seite(akten, d, 3)
    assert s["titel"] == "Seite 3" and s["seite"] == 3 and s["zitat"].startswith("Rechtliches")
    assert lesezeichen.auf_seite(akten, d, 3)[0]["y"] is not None
    assert lesezeichen.auf_seite(akten, d, 1) == []


def test_lesezeichen_ordner_und_reihenfolge(akten, con, tmp_path):
    d, a = _dokument(akten, con, tmp_path, "Klage\n\nDer Beklagte schuldet 500 EUR.\n\nBegründung folgt.")
    text = _text(akten, d)
    eins = lesezeichen.anlegen(akten, d, text.index("schuldet") + 2)
    assert eins["zitat"].startswith("schuldet") and eins["titel"] == eins["zitat"]  # Wortanfang, Titel aus Wortlaut
    zwei = lesezeichen.anlegen(akten, d, text.index("Begründung"), titel="  Begründung   ")
    assert zwei["titel"] == "Begründung"
    o = lesezeichen.ordner_anlegen(akten, a, "Beweis")
    leer = lesezeichen.ordner_anlegen(akten, a, "Später")
    neu = lesezeichen.anordnen(akten, a, [
        {"id": leer["id"], "lesezeichen": []},
        {"id": o["id"], "lesezeichen": [zwei["id"], eins["id"]]},
        {"id": None, "lesezeichen": []},
    ])
    assert [x["name"] for x in neu["ordner"]] == ["Später", "Beweis"]
    assert [(x["id"], x["ordner_id"]) for x in neu["lesezeichen"]] == [(zwei["id"], o["id"]), (eins["id"], o["id"])]
    assert lesezeichen.aendern(akten, eins["id"], "Forderung")["titel"] == "Forderung"
    # Ordner löschen: Lesezeichen bleiben, ohne Ordner.
    lesezeichen.ordner_loeschen(akten, o["id"])
    assert {x["ordner_id"] for x in lesezeichen.liste(akten, dokument_id=d)["lesezeichen"]} == {None}
    # Fremder Ordner wird abgelehnt.
    anders = akte.akte_anlegen(akten, "Andere")["id"]
    fremd = lesezeichen.ordner_anlegen(akten, anders, "X")
    with pytest.raises(ValueError):
        lesezeichen.anordnen(akten, a, [{"id": fremd["id"], "lesezeichen": [eins["id"]]}])
    lesezeichen.loeschen(akten, zwei["id"])
    assert len(lesezeichen.liste(akten, akte_id=a)["lesezeichen"]) == 1


def test_lesezeichen_nach_neuer_fassung(akten, con, tmp_path):
    d, _ = _dokument(akten, con, tmp_path, "Einleitung.\n\nDer Rücktritt ist wirksam erklärt.")
    text = _text(akten, d)
    z = lesezeichen.anlegen(akten, d, text.index("Rücktritt"), text.index("Rücktritt") + 9)
    akten.execute("UPDATE abschnitt SET text = 'Neue Einleitung mit mehr Text.' WHERE dokument_id = ? AND nr = 1",
                  (d,))
    akten.commit()
    neu = lesezeichen.liste(akten, dokument_id=d)["lesezeichen"][0]
    assert neu["status"] == "gefunden" and _text(akten, d)[neu["start"]:neu["ende"]] == "Rücktritt"
    akten.execute("UPDATE abschnitt SET text = 'Alles anders.' WHERE dokument_id = ?", (d,))
    akten.commit()
    assert lesezeichen.liste(akten, dokument_id=d)["lesezeichen"][0]["status"] == "nicht_gefunden"
    assert z["id"]


def test_gemeinsame_ordner_mit_markierungen(akten, con, tmp_path):
    d, a = _dokument(akten, con, tmp_path, "Klage\n\nDer Beklagte schuldet 500 EUR.\n\nBegründung folgt.")
    text = _text(akten, d)
    m = anmerkungen.anlegen(akten, d, text.index("schuldet"), text.index("schuldet") + 8, "rot")
    z = lesezeichen.anlegen(akten, d, text.index("Begründung"))
    assert z["reihenfolge"] > m["reihenfolge"]  # gemeinsame Ordnung: das Neue kommt ans Ende
    o = lesezeichen.ordner_anlegen(akten, a, "Streitig")
    lesezeichen.anordnen(akten, a, [
        {"id": o["id"], "eintraege": [{"art": "lesezeichen", "id": z["id"]}, {"art": "markierung", "id": m["id"]}]},
        {"id": None, "eintraege": []},
    ])
    neu = anmerkungen.liste(akten, akte_id=a)[0]
    assert (neu["ordner_id"], neu["reihenfolge"]) == (o["id"], 1)
    assert lesezeichen.liste(akten, akte_id=a)["lesezeichen"][0]["reihenfolge"] == 0
    with pytest.raises(ValueError):
        lesezeichen.anordnen(akten, a, [{"id": None, "eintraege": [{"art": "markierung", "id": 999}]}])
    lesezeichen.ordner_loeschen(akten, o["id"])
    assert anmerkungen.liste(akten, akte_id=a)[0]["ordner_id"] is None


def test_alte_tabelle_wird_ergaenzt(tmp_path):
    import sqlite3
    pfad = tmp_path / "alt.sqlite"
    alt = sqlite3.connect(pfad)
    alt.execute("CREATE TABLE anmerkung (id INTEGER PRIMARY KEY, dokument_id INTEGER, art TEXT, farbe TEXT, "
                "stil TEXT, start INTEGER, ende INTEGER, zitat TEXT, davor TEXT, danach TEXT, seite INTEGER, "
                "form TEXT, kommentar TEXT, status TEXT, textstand TEXT, angelegt_am TEXT, geaendert_am TEXT)")
    alt.commit()
    alt.close()
    con = akte.oeffne(pfad)
    anmerkungen.einrichten(con)
    anmerkungen.einrichten(con)  # zweimal: nichts doppelt
    spalten = {z[1] for z in con.execute("PRAGMA table_info(anmerkung)")}
    assert {"ordner_id", "reihenfolge"} <= spalten
    con.close()
