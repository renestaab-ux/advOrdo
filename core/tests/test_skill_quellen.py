"""Skill-Quellen (GitHub-Repositorys): Adresse, Verzeichnis (Marktplatz oder Dateibaum), Paket, Import.

Kein Netz: Ein nachgebautes GitHub antwortet aus einem Wörterbuch. Repository und Skills sind frei erfunden.
"""

import io
import json
import urllib.error
from email.message import Message

import pytest

from juracore import rpc
from juracore.ki import skill_quellen as sq
from juracore.ki import skills

API = "https://api.github.com/repos/muster/sammlung"
ROH = "https://raw.githubusercontent.com/muster/sammlung/main"

SKILL = """---
name: {name}
description: {beschreibung}
---
# {name}

Prüfe zuerst die Form nach § 126 BGB.
"""


class Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class GitHub:
    """Nachgebautes GitHub: Adresse → Inhalt (dict/list als JSON, str als Text); merkt sich die Abrufe."""

    def __init__(self, seiten: dict):
        self.seiten = seiten
        self.abrufe: list[str] = []
        self.kontingent_weg = False

    def __call__(self, anfrage, timeout=None):
        url = anfrage.full_url
        self.abrufe.append(url)
        assert "advOrdo" in anfrage.get_header("User-agent")
        if self.kontingent_weg and url.startswith("https://api.github.com"):
            kopf = Message()
            kopf["X-RateLimit-Remaining"] = "0"
            kopf["X-RateLimit-Reset"] = "1700000000"
            raise urllib.error.HTTPError(url, 403, "rate limit", kopf, None)
        if url not in self.seiten:
            raise urllib.error.HTTPError(url, 404, "Not Found", Message(), None)
        inhalt = self.seiten[url]
        daten = inhalt.encode() if isinstance(inhalt, str) else json.dumps(inhalt).encode()
        return Antwort(daten)


def _marktplatz() -> GitHub:
    return GitHub({
        API: {"default_branch": "main", "description": "Erfundene Sammlung", "private": False},
        f"{ROH}/.claude-plugin/marketplace.json": {"name": "sammlung", "description": "Skills zum Testen", "plugins": [
            {"name": "mietrecht-pruefer", "source": "./mietrecht-pruefer", "description": "Wohnraummiete"},
            {"name": "extern", "source": {"source": "github", "repo": "anderer/repo"}},
            {"name": "boese", "source": "./../ausserhalb"},
        ]},
        f"{API}/contents/mietrecht-pruefer/skills?ref=main": [
            {"name": "kuendigung", "type": "dir"}, {"name": "README.md", "type": "file"},
            {"name": "betriebskosten", "type": "dir"}],
        f"{ROH}/mietrecht-pruefer/.claude-plugin/plugin.json": {"name": "mietrecht-pruefer",
                                                                 "displayName": "Mietrecht Prüfer"},
        f"{ROH}/mietrecht-pruefer/skills/kuendigung/SKILL.md": SKILL.format(
            name="kuendigung", beschreibung="Prüft die Kündigung"),
        f"{ROH}/mietrecht-pruefer/skills/betriebskosten/SKILL.md": SKILL.format(
            name="betriebskosten", beschreibung="Prüft die Abrechnung"),
    })


def test_adresse_zerlegen():
    assert sq.zerlege("https://github.com/muster/sammlung") == {
        "besitzer": "muster", "repo": "sammlung", "zweig": None, "pfad": ""}
    assert sq.zerlege("github.com/muster/sammlung.git/")["repo"] == "sammlung"
    assert sq.zerlege("muster/sammlung/tree/dev/recht/zivil") == {
        "besitzer": "muster", "repo": "sammlung", "zweig": "dev", "pfad": "recht/zivil"}
    for falsch in ("", "muster", "https://gitlab.com/a/b", "github.com/a b/c", "a/b/tree/main/../x"):
        with pytest.raises(ValueError):
            sq.zerlege(falsch)


def test_marktplatz_paket_und_import(tmp_path):
    quellen, skills_datei = tmp_path / sq.DATEINAME, tmp_path / skills.DATEINAME
    gh = _marktplatz()
    q = sq.anbinden(quellen, "https://github.com/muster/sammlung", gh)
    assert q["art"] == "marktplatz" and q["zweig"] == "main" and q["beschreibung"] == "Skills zum Testen"
    # Nur Plugins aus diesem Repository; Inhalte werden erst beim Öffnen gelesen.
    assert q["pakete"] == [{"pfad": "mietrecht-pruefer", "name": "mietrecht-pruefer",
                            "beschreibung": "Wohnraummiete", "anzahl": None}]
    assert not any("/contents/" in a for a in gh.abrufe)

    p = sq.paket(quellen, skills_datei, q["id"], "mietrecht-pruefer", gh)
    assert [(s["name"], s["importiert"]) for s in p["skills"]] == [("betriebskosten", False), ("kuendigung", False)]
    vorher = len(gh.abrufe)
    sq.paket(quellen, skills_datei, q["id"], "mietrecht-pruefer", gh)
    assert len(gh.abrufe) == vorher  # gemerkt
    assert sq.liste(quellen)[0]["pakete"][0]["anzahl"] == 2

    meldungen = []
    pfad = "mietrecht-pruefer/skills/kuendigung/SKILL.md"
    r = sq.importieren(quellen, skills_datei, q["id"], [pfad], 8192, gh,
                       melde=lambda t, s, v: meldungen.append(t))
    assert [s["name"] for s in r["uebernommen"]] == ["kuendigung"] and meldungen == ["Skills laden: 1 von 1"]
    s = skills.liste(skills_datei)[0]
    assert s["ordner"] == "Mietrecht Prüfer" and s["beschreibung"] == "Prüft die Kündigung"
    assert s["herkunft"] == f"Aus github.com/muster/sammlung ({pfad})"
    assert sq.paket(quellen, skills_datei, q["id"], "mietrecht-pruefer", gh)["skills"][1]["importiert"]

    # Erneut: unverändert übersprungen; geändert auf GitHub: aktualisiert, Name und Ordner des Nutzers bleiben.
    r = sq.importieren(quellen, skills_datei, q["id"], [pfad], 8192, gh)
    assert r["uebersprungen"] == [{"datei": pfad, "grund": "schon vorhanden, unverändert"}]
    skills.ordner_umbenennen(skills_datei, "Mietrecht Prüfer", "Zivilrecht / Miete")
    gh.seiten[f"{ROH}/{pfad}"] = SKILL.format(name="kuendigung", beschreibung="Neu") + "Dann die Frist.\n"
    r = sq.importieren(quellen, skills_datei, q["id"], [pfad], 8192, gh)
    assert len(r["aktualisiert"]) == 1 and not r["uebernommen"]
    s = skills.liste(skills_datei)[0]
    assert s["ordner"] == "Zivilrecht / Miete" and s["text"].endswith("Dann die Frist.")
    assert len(skills.liste(skills_datei)) == 1

    with pytest.raises(LookupError):
        sq.importieren(quellen, skills_datei, q["id"], ["anderes/SKILL.md"], 8192, gh)


def test_dateibaum_ohne_marktplatz(tmp_path):
    quellen = tmp_path / sq.DATEINAME
    gh = GitHub({
        API: {"default_branch": "main"},
        f"{API}/git/trees/main?recursive=1": {"truncated": True, "tree": [
            {"path": "README.md", "type": "blob"},
            {"path": "skills/gegnerbrille/SKILL.md", "type": "blob"},
            {"path": "skills/gegnerbrille/references/a.md", "type": "blob"},
            {"path": "strafrecht/skills/haft/SKILL.md", "type": "blob"},
        ]},
    })
    q = sq.anbinden(quellen, "muster/sammlung", gh)
    assert q["art"] == "baum" and "Unterordner" in q["hinweis"]
    assert [(p["pfad"], p["name"], p["anzahl"]) for p in q["pakete"]] == [("", "sammlung", 1),
                                                                         ("strafrecht", "strafrecht", 1)]
    p = sq.paket(quellen, tmp_path / "s.json", q["id"], "", gh)
    assert p["skills"] == [{"pfad": "skills/gegnerbrille/SKILL.md", "name": "gegnerbrille", "importiert": False}]
    # Dieselbe Adresse noch einmal: keine zweite Quelle, nur neu geladen.
    assert sq.anbinden(quellen, "https://github.com/Muster/sammlung", gh)["id"] == q["id"]
    assert len(sq.liste(quellen)) == 1
    assert sq.entfernen(quellen, q["id"]) == {"entfernt": 1} and sq.liste(quellen) == []


def test_fehler_verstaendlich(tmp_path):
    quellen = tmp_path / sq.DATEINAME
    with pytest.raises(ValueError, match="gibt es auf GitHub nicht"):
        sq.anbinden(quellen, "muster/fehlt", GitHub({}))
    gh = _marktplatz()
    gh.kontingent_weg = True
    with pytest.raises(ValueError, match="60 Verzeichnisabfragen"):
        sq.anbinden(quellen, "muster/sammlung", gh)


def test_rpc_im_hintergrund(tmp_path, monkeypatch):
    monkeypatch.setattr(sq.urllib.request, "urlopen", _marktplatz())
    k = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    a = k.hintergrund_starten("skills.quelle_anbinden", {"adresse": "muster/sammlung"}, warten=True)
    assert a["status"] == "fertig", a
    qid = k.methoden["skills.quellen"]()["quellen"][0]["id"]
    a = k.hintergrund_starten("skills.quelle_paket", {"quelle_id": qid, "pfad": "mietrecht-pruefer"}, warten=True)
    assert len(a["ergebnis"]["skills"]) == 2
    a = k.hintergrund_starten("skills.quelle_importieren", {
        "quelle_id": qid, "pfade": ["mietrecht-pruefer/skills/betriebskosten/SKILL.md"]}, warten=True)
    assert a["status"] == "fertig", a
    assert [s["name"] for s in k.methoden["skills.liste"]()["skills"]] == ["betriebskosten"]
    assert k.methoden["skills.quelle_entfernen"](quelle_id=qid) == {"entfernt": 1}
