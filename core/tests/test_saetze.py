import pytest

from juracore.gesetze.saetze import Liste, zerlege_in_saetze


def saetze(text):
    return [s.text for s in zerlege_in_saetze([text])]


@pytest.mark.parametrize(
    "text",
    [
        "Die Frist nach Abs. 1 Satz 2 beginnt am 1. Januar des Folgejahres.",
        "Dies gilt z. B. für Ansprüche nach § 280 Abs. 1 Nr. 2 BGB.",
        "Die Vorschrift gilt i. V. m. § 281 entsprechend.",
        "Die Bek. v. 2.1.2002 bleibt unberührt.",
    ],
)
def test_kein_satzende_bei_abkuerzungen(text):
    assert saetze(text) == [text]


def test_satzende_nach_zahl_bei_verweis():
    assert saetze("Es gilt Absatz 2. Dies gilt auch für Dritte.") == [
        "Es gilt Absatz 2.",
        "Dies gilt auch für Dritte.",
    ]


def test_liste_mit_neuem_satz_danach():
    teile = [
        "Erforderlich sind:",
        Liste([("1", "die Angabe;"), ("2", "der Antrag.")]),
        " Weitere Angaben sind zulässig.",
    ]
    ergebnis = zerlege_in_saetze(teile)
    assert len(ergebnis) == 2
    assert ergebnis[0].nummern == [("1", "die Angabe;"), ("2", "der Antrag.")]
    assert ergebnis[1].text == "Weitere Angaben sind zulässig."


def test_liste_mit_fortsetzung_im_selben_satz():
    teile = ["Er haftet, wenn", Liste([("1", "a,"), ("2", "b")]), ", es sei denn, er war gutgläubig."]
    assert len(zerlege_in_saetze(teile)) == 1
