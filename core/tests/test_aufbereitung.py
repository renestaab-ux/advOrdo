from juracore.dokumente.aufbereitung import abschnitte_bilden, korrigiere_ocr
from juracore.dokumente.modell import OCR, TEXTEBENE, Seite

# Volle Zeilen im Blocksatz; nur die letzte Zeile eines Absatzes ist kürzer.
VOLL = "x" * 80


def test_seitenkopf_entfernt_und_absatz_laeuft_ueber_die_seite():
    seiten = [
        Seite(1, TEXTEBENE, ["(4) Etwa acht Wochen nach Übergabe trat beim Anfahren ein deutliches Ruckeln auf. Der", VOLL]),
        Seite(2, TEXTEBENE, ["- 2 -", "Gangwechsel erfolgte verzögert; die Getriebewarnleuchte leuchtete sporadisch auf.", "Ende."]),
    ]
    a = abschnitte_bilden(seiten)
    assert len(a) == 1
    assert a[0].rn == 4
    assert (a[0].seite, a[0].seite_bis) == (1, 2)
    assert "- 2 -" not in a[0].text
    pos = a[0].text.index("Gangwechsel")
    assert a[0].seitenwechsel and a[0].seitenwechsel[0][1] == 2
    assert a[0].seitenwechsel[0][0] <= pos


def test_silbentrennung_und_bindestrich():
    seiten = [
        Seite(
            1,
            TEXTEBENE,
            [
                "Der Kilome-",
                "terstand betrug 68.400 km und die Werkstatt Kfz-",
                "Technik Baumann prüfte Getriebe- und Motorschaden sowie das Normzitat nach §",
                "433 Abs. 1 BGB.",
            ],
        )
    ]
    text = abschnitte_bilden(seiten)[0].text
    assert "Kilometerstand" in text
    assert "Kfz-Technik" in text
    assert "Getriebe- und" in text
    assert "nach § 433 Abs. 1 BGB" in text


def test_randnummer_und_beweis_beginnen_neue_absaetze():
    seiten = [
        Seite(
            1,
            TEXTEBENE,
            [
                "(1) Die Klägerin ist niedergelassene Ärztin und erwarb das Fahrzeug für private Zwecke, insbesondere",
                "für die tägliche Fahrt zwischen Wohnung und Kindergarten ihrer Tochter, nicht beruflich genutzt.",
                "Beweis: Internetauftritt der Beklagten, Ausdruck vom 15.10.2025 Anlage K 6 und weitere Belege dazu",
                "II. Der Kaufvertrag",
                "(2) Mit Kaufvertrag vom 14.03.2025 erwarb die Klägerin von der Beklagten den Pkw VW Golf Variant.",
            ],
        )
    ]
    a = abschnitte_bilden(seiten)
    assert [x.text.split(" ")[0] for x in a] == ["(1)", "Beweis:", "II.", "(2)"]
    assert [x.rn for x in a] == [1, None, None, 2]


def test_ocr_paragraphenzeichen():
    assert korrigiere_ocr("nach $ 331 Abs. 3 ZPO") == "nach § 331 Abs. 3 ZPO"
    assert korrigiere_ocr("aus $8 437 Nr. 2, 440 BGB") == "aus §§ 437 Nr. 2, 440 BGB"
    assert korrigiere_ocr("aus §8§ 286 Abs. 1 BGB") == "aus §§ 286 Abs. 1 BGB"
    assert korrigiere_ocr("Annahmeverzug (83 293, 295 BGB)") == "Annahmeverzug (§§ 293, 295 BGB)"
    assert korrigiere_ocr("im Sinne des 8 434 Abs. 1 BGB") == "im Sinne des § 434 Abs. 1 BGB"
    # Ohne folgendes Normzitat bleibt die Zahl stehen.
    assert korrigiere_ocr("Es waren 83 Fälle um 8 Uhr") == "Es waren 83 Fälle um 8 Uhr"


def test_ocr_korrektur_ueber_den_zeilenumbruch():
    zeile = "Der Feststellungsantrag ist wegen des besonderen Interesses der Klägerin nach $"
    seiten = [Seite(1, OCR, [zeile, "256 Abs. 1 ZPO zulässig."])]
    assert abschnitte_bilden(seiten)[0].text.endswith("Klägerin nach § 256 Abs. 1 ZPO zulässig.")


def test_ocr_seitenkopf_als_kuerzel():
    seiten = [Seite(1, OCR, [VOLL]), Seite(2, OCR, ["Dis", "Weiter im Text."])]
    assert "Dis" not in " ".join(a.text for a in abschnitte_bilden(seiten))
