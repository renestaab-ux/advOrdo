import io
import json
import urllib.error

import pytest

from juracore import nachrichten, programme, rpc

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>Legal Tribune Online - Aktuelles</title>
  <link>https://www.lto.de/</link>
  <item>
    <title>BGH: Ein fiktives Urteil</title>
    <link>https://www.lto.de/recht/nachrichten/n/eins?r=rss</link>
    <description>&lt;p&gt;Der &lt;b&gt;BGH&lt;/b&gt; hat entschieden &amp;amp; mehr.&lt;/p&gt;</description>
    <pubDate>Mon, 26 Oct 2026 17:15:00 +0100</pubDate>
  </item>
  <item>
    <title>LG Köln: Ältere Meldung</title>
    <link>https://www.lto.de/recht/nachrichten/n/zwei?r=rss</link>
    <pubDate>Mon, 26 Oct 2026 10:00:00 +0100</pubDate>
  </item>
  <item>
    <title>Ohne Link</title>
    <link>javascript:alert(1)</link>
  </item>
</channel>
</rss>""".encode()

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Pressemitteilungen</title>
  <entry>
    <title>Neue Pressemitteilung</title>
    <link rel="alternate" href="/presse/1"/>
    <updated>2026-10-26T15:00:00Z</updated>
    <summary>Kurz gesagt.</summary>
  </entry>
</feed>"""

RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel><title>RDF-Feed</title></channel>
  <item><title>Eintrag</title><link>https://example.org/a</link><dc:date>2026-10-01T08:00:00+02:00</dc:date></item>
</rdf:RDF>"""

SEITE = b"""<!DOCTYPE html><html><head><title>RSS</title></head><body>
<a href="/impressum">Impressum</a>
<a href="/rss/feed.xml">Alle Beitr\xc3\xa4ge</a>
</body></html>"""


class Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def oeffner(seiten: dict[str, bytes], aufrufe: list | None = None):
    def oeffnen(anfrage, timeout=None):
        if aufrufe is not None:
            aufrufe.append(anfrage.full_url)
        if anfrage.full_url not in seiten:
            raise urllib.error.URLError("nicht erreichbar")
        return Antwort(seiten[anfrage.full_url])

    return oeffnen


def test_rss_wird_gelesen():
    feed = nachrichten.lies_feed(RSS, "https://www.lto.de/rss/feed.xml")
    assert feed["titel"] == "Legal Tribune Online - Aktuelles"
    erster = feed["eintraege"][0]
    assert erster["titel"] == "BGH: Ein fiktives Urteil"
    assert erster["datum"] == "2026-10-26T16:15:00+00:00"
    assert erster["auszug"] == "Der BGH hat entschieden & mehr."
    # Nur http(s)-Links werden übernommen.
    assert feed["eintraege"][2]["link"] is None


def test_atom_und_rdf():
    atom = nachrichten.lies_feed(ATOM, "https://gericht.example/feed")
    assert atom["titel"] == "Pressemitteilungen"
    assert atom["eintraege"][0]["link"] == "https://gericht.example/presse/1"
    assert atom["eintraege"][0]["datum"] == "2026-10-26T15:00:00+00:00"
    rdf = nachrichten.lies_feed(RDF)
    assert rdf["titel"] == "RDF-Feed"
    assert rdf["eintraege"][0]["datum"] == "2026-10-01T06:00:00+00:00"


def test_kein_feed_und_entitaeten():
    with pytest.raises(nachrichten.KeinFeed):
        nachrichten.lies_feed(SEITE)
    with pytest.raises(nachrichten.KeinFeed):
        nachrichten.lies_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel/></rss>')


def test_hinzufuegen_findet_feed_auf_webseite(tmp_path):
    n = nachrichten.Nachrichten(tmp_path / "n.json", tmp_path / "c.json", oeffner({
        "https://www.lto.de/rss": SEITE,
        "https://www.lto.de/rss/feed.xml": RSS,
    }), im_hintergrund=False)
    ergebnis = n.hinzufuegen("www.lto.de/rss")
    assert ergebnis["neu"]["url"] == "https://www.lto.de/rss/feed.xml"
    assert ergebnis["neu"]["titel"] == "Legal Tribune Online - Aktuelles"
    assert ergebnis["eintraege"] == 3
    with pytest.raises(ValueError, match="schon eingetragen"):
        n.hinzufuegen("https://www.lto.de/rss/feed.xml")


def test_ungueltige_adresse(tmp_path):
    n = nachrichten.Nachrichten(tmp_path / "n.json", tmp_path / "c.json", oeffner({}), im_hintergrund=False)
    with pytest.raises(ValueError):
        n.hinzufuegen("file:///etc/passwd")
    with pytest.raises(urllib.error.URLError):
        n.hinzufuegen("https://nicht.da/feed")
    assert n.einstellungen()["feeds"] == []


def test_liste_mischt_feeds_und_behaelt_stand_bei_fehler(tmp_path):
    seiten = {"https://a.example/rss": RSS, "https://b.example/atom": ATOM}
    aufrufe: list[str] = []
    n = nachrichten.Nachrichten(tmp_path / "n.json", tmp_path / "c.json", oeffner(seiten, aufrufe),
                                im_hintergrund=False)
    # Ohne Feed: nichts laden, nichts anzeigen.
    assert n.liste()["feeds"] == 0
    assert aufrufe == []

    n.hinzufuegen("https://a.example/rss", "LTO")
    n.hinzufuegen("https://b.example/atom")
    aufrufe.clear()
    liste = n.liste(limit=10)
    assert aufrufe == []  # frisch geladen, kein erneuter Abruf
    assert [e["titel"] for e in liste["eintraege"]][:3] == [
        "BGH: Ein fiktives Urteil", "Neue Pressemitteilung", "LG Köln: Ältere Meldung"]
    assert liste["eintraege"][0]["quelle"] == "LTO"
    assert liste["eintraege"][1]["quelle"] == "Pressemitteilungen"

    # Feed fällt aus: Meldung, aber die letzten Einträge bleiben.
    del seiten["https://a.example/rss"]
    liste = n.liste(limit=10, aktualisieren=True)
    assert liste["fehler"][0]["titel"] == "LTO"
    assert "Nicht erreichbar" in liste["fehler"][0]["text"]
    assert any(e["quelle"] == "LTO" for e in liste["eintraege"])

    feed_id = n.einstellungen()["feeds"][0]["id"]
    n.umbenennen(feed_id, "Legal Tribune")
    assert n.einstellungen()["feeds"][0]["titel"] == "Legal Tribune"
    n.entfernen(feed_id)
    assert all(e["feed_id"] != feed_id for e in n.liste(limit=10)["eintraege"])
    assert "a.example" not in json.dumps(json.loads((tmp_path / "c.json").read_text()))


def test_vorschlaege_markieren_eingetragene(tmp_path):
    url = nachrichten.VORSCHLAEGE[0]["url"]
    n = nachrichten.Nachrichten(tmp_path / "n.json", tmp_path / "c.json", oeffner({url: RSS}),
                                im_hintergrund=False)
    n.hinzufuegen(url)
    vorschlaege = n.einstellungen()["vorschlaege"]
    assert vorschlaege[0]["eingetragen"] is True
    assert vorschlaege[1]["eingetragen"] is False


def test_adresse_oeffnen_nur_web():
    with pytest.raises(ValueError):
        programme.adresse_oeffnen("file:///C:/Windows/system32/calc.exe")


def test_rpc_meldet_netzfehler(tmp_path):
    kern = rpc.Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    kern.nachrichten.oeffnen = oeffner({})
    antwort = kern.bearbeite(json.dumps({"id": 1, "method": "nachrichten.hinzufuegen",
                                         "params": {"url": "https://nicht.da/rss"}}))
    assert "nicht erreichbar" in antwort["error"]["message"]
    antwort = kern.bearbeite(json.dumps({"id": 2, "method": "nachrichten.liste"}))
    assert antwort["result"]["feeds"] == 0
