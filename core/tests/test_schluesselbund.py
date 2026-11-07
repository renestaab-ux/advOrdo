import json

from juracore import schluesselbund
from juracore.ki import anbieter


class Bund:
    def __init__(self):
        self.daten = {}

    def get_password(self, dienst, name):
        return self.daten.get((dienst, name))

    def set_password(self, dienst, name, wert):
        self.daten[(dienst, name)] = wert

    def delete_password(self, dienst, name):
        del self.daten[(dienst, name)]


def test_schluessel_liegt_im_schluesselbund_nicht_in_der_datei(tmp_path):
    bund = Bund()
    schluesselbund.setze_bund(bund)
    datei = tmp_path / "ki-schluessel.json"
    anbieter.speichere_schluessel(datei, "anthropic", " sk-geheim-1234 ")
    assert not datei.exists()
    assert list(bund.daten.values()) == ["sk-geheim-1234"]
    assert anbieter.lade_schluessel(datei, "anthropic") == "sk-geheim-1234"
    anbieter.speichere_schluessel(datei, "anthropic", None)
    assert bund.daten == {} and anbieter.lade_schluessel(datei, "anthropic") is None


def test_alter_schluessel_zieht_aus_der_datei_um(tmp_path):
    datei = tmp_path / "ki-schluessel.json"
    datei.write_text(json.dumps({"gemini": "g-alt", "mistral": "m-alt"}), encoding="utf-8")
    bund = Bund()
    schluesselbund.setze_bund(bund)
    assert anbieter.lade_schluessel(datei, "gemini") == "g-alt"
    assert json.loads(datei.read_text(encoding="utf-8")) == {"mistral": "m-alt"}
    assert anbieter.lade_schluessel(datei, "mistral") == "m-alt"
    assert not datei.exists()
    assert sorted(bund.daten.values()) == ["g-alt", "m-alt"]


def test_arbeitsumgebungen_getrennt(tmp_path):
    schluesselbund.setze_bund(Bund())
    a, b = tmp_path / "a" / "ki-schluessel.json", tmp_path / "b" / "ki-schluessel.json"
    anbieter.speichere_schluessel(a, "openai", "eins")
    anbieter.speichere_schluessel(b, "openai", "zwei")
    assert anbieter.lade_schluessel(a, "openai") == "eins" and anbieter.lade_schluessel(b, "openai") == "zwei"


def test_ohne_schluesselbund_bleibt_die_datei(tmp_path):
    datei = tmp_path / "ki-schluessel.json"
    anbieter.speichere_schluessel(datei, "openai", "datei-schluessel")
    assert json.loads(datei.read_text(encoding="utf-8")) == {"openai": "datei-schluessel"}
    assert anbieter.lade_schluessel(datei, "openai") == "datei-schluessel"
    assert schluesselbund.ort() == schluesselbund.DATEI


def test_gestoerter_schluesselbund_faellt_auf_die_datei_zurueck(tmp_path):
    class Kaputt(Bund):
        def set_password(self, dienst, name, wert):
            raise RuntimeError("gesperrt")

        def get_password(self, dienst, name):
            raise RuntimeError("gesperrt")

    schluesselbund.setze_bund(Kaputt())
    datei = tmp_path / "ki-schluessel.json"
    anbieter.speichere_schluessel(datei, "openai", "x-1")
    assert anbieter.lade_schluessel(datei, "openai") == "x-1"
    assert datei.exists()
