"""Skills: Lesen von SKILL.md, Import (Datei, ZIP, Ordner), Verwaltung und Einbau in Chat und Analyse.

Die Skills sind frei erfunden.
"""

import json
import zipfile

import pytest

from juracore import rpc
from juracore.ki import chat, skills
from juracore.ki.analyse import Analyse

from .test_chat import akten, gute_antwort  # noqa: F401  (Fixture)
from .test_ki import Attrappe, _akte, _warte, modell_antwort

SKILL_MD = """---
name: mietrecht-kuendigung-pruefen
description: "Prüft eine Kündigung im Wohnraummietrecht: Form, Frist, Begründung."
---

# Kündigung prüfen

1. Form nach § 568 BGB prüfen.
2. Frist nach § 573c BGB berechnen.
"""

MIT_BLOCK = """---
name: Vertragsprüfung
description: >
  Prüft einen Vertrag
  Klausel für Klausel.
license: MIT
---
Gehe jede Klausel durch. Prüfe Rechtsprechung bei dejure.org und erzeuge eine Word-Datei (docx).
Nutze references/checkliste.md.
"""


class Merker(Attrappe):
    """Wie Attrappe, merkt sich zusätzlich die Systemanweisung."""

    def __init__(self, antwort):
        super().__init__(antwort)
        self.systeme: list[str] = []

    def chat(self, system, nutzer, schema):
        self.systeme.append(system)
        return super().chat(system, nutzer, schema)


def test_skill_md_mit_kopf():
    s = skills.lies_skill_md(SKILL_MD)
    assert s["name"] == "mietrecht-kuendigung-pruefen"
    assert s["beschreibung"] == "Prüft eine Kündigung im Wohnraummietrecht: Form, Frist, Begründung."
    assert s["text"].startswith("# Kündigung prüfen") and "---" not in s["text"]


def test_skill_md_mit_mehrzeiliger_beschreibung_und_hinweisen():
    s = skills.lies_skill_md(MIT_BLOCK)
    assert s["name"] == "Vertragsprüfung"
    assert s["beschreibung"] == "Prüft einen Vertrag Klausel für Klausel."
    h = skills.hinweise(s["text"])
    assert len(h) == 3  # Webseiten, Dateien, weitere Dateien des Ordners
    assert not skills.hinweise("Rechne Zinsen mit der Toolbox.")


def test_markdown_ohne_kopf_nimmt_die_ueberschrift():
    s = skills.lies_skill_md("# Strenger Gegner\n\nLies den Schriftsatz wie die Gegenseite.", "datei")
    assert s["name"] == "Strenger Gegner" and s["beschreibung"] == ""
    assert skills.lies_skill_md("Nur Text.", "notiz")["name"] == "notiz"


def test_anlegen_aendern_loeschen(tmp_path):
    datei = tmp_path / "skills.json"
    s = skills.speichern(datei, "Gegnerbrille", "Lies alles aus Sicht der Gegenseite.", "kritisch")
    assert s["herkunft"] == "Eigener Skill" and s["zeichen"] == 36
    with pytest.raises(ValueError, match="schon"):
        skills.speichern(datei, "gegnerbrille", "anders")
    with pytest.raises(ValueError, match="Namen"):
        skills.speichern(datei, "  ", "Text")
    geaendert = skills.speichern(datei, "Gegnerbrille", "Neu.", skill_id=s["id"])
    assert geaendert["text"] == "Neu." and len(skills.liste(datei)) == 1
    assert skills.loeschen(datei, s["id"]) == {"geloescht": 1}
    assert skills.liste(datei) == []
    with pytest.raises(LookupError):
        skills.loeschen(datei, s["id"])


def test_import_einer_datei_zweimal(tmp_path):
    datei = tmp_path / "skills.json"
    md = tmp_path / "SKILL.md"
    md.write_text(SKILL_MD, encoding="utf-8")
    erst = skills.importieren(datei, str(md))
    assert [s["name"] for s in erst["uebernommen"]] == ["mietrecht-kuendigung-pruefen"]
    assert erst["uebernommen"][0]["herkunft"] == "Importiert aus SKILL.md"
    zweit = skills.importieren(datei, str(md))
    assert zweit["uebernommen"] == [] and zweit["uebersprungen"][0]["grund"] == "schon vorhanden"
    md.write_text(SKILL_MD + "\n3. Zugang prüfen.\n", encoding="utf-8")
    dritt = skills.importieren(datei, str(md))
    assert dritt["uebernommen"][0]["name"] == "mietrecht-kuendigung-pruefen (2)"


def test_import_aus_zip_und_ordner(tmp_path):
    datei = tmp_path / "skills.json"
    zip_pfad = tmp_path / "paket.zip"
    with zipfile.ZipFile(zip_pfad, "w") as z:
        z.writestr("paket/skills/kuendigung/SKILL.md", SKILL_MD)
        z.writestr("paket/skills/vertrag/SKILL.md", MIT_BLOCK)
        z.writestr("paket/skills/vertrag/references/checkliste.md", "- Punkt")
        z.writestr("__MACOSX/paket/skills/vertrag/SKILL.md", "Müll")
    aus_zip = skills.importieren(datei, str(zip_pfad))
    namen = sorted(s["name"] for s in aus_zip["uebernommen"])
    assert namen == ["Vertragsprüfung", "mietrecht-kuendigung-pruefen"]
    vertrag = next(s for s in aus_zip["uebernommen"] if s["name"] == "Vertragsprüfung")
    assert vertrag["nicht_uebernommen"] == ["references/checkliste.md"]

    ordner = tmp_path / "ordner" / "eigener"
    ordner.mkdir(parents=True)
    (ordner / "SKILL.md").write_text("---\nname: Fristenblick\n---\nAchte auf jede Frist.", encoding="utf-8")
    aus_ordner = skills.importieren(datei, str(tmp_path / "ordner"))
    assert [s["name"] for s in aus_ordner["uebernommen"]] == ["Fristenblick"]
    assert len(skills.liste(datei)) == 3

    with pytest.raises(ValueError, match="SKILL.md"):
        (tmp_path / "leer").mkdir()
        skills.importieren(datei, str(tmp_path / "leer"))
    with pytest.raises(ValueError):
        (tmp_path / "bild.png").write_bytes(b"x")
        skills.importieren(datei, str(tmp_path / "bild.png"))


def test_export_laesst_sich_wieder_einlesen(tmp_path):
    datei = tmp_path / "skills.json"
    s = skills.speichern(datei, "Gegnerbrille „scharf“", "Lies alles aus Sicht der Gegenseite.", 'Sagt "nein"')
    ziel = tmp_path / "SKILL.md"
    skills.exportieren(datei, s["id"], str(ziel))
    wieder = skills.lies_skill_md(ziel.read_text(encoding="utf-8"))
    assert wieder["name"] == "gegnerbrille-scharf"
    assert wieder["beschreibung"] == 'Sagt "nein"' and wieder["text"] == "Lies alles aus Sicht der Gegenseite."


def test_laenge_haengt_am_kontextfenster(tmp_path):
    datei = tmp_path / "skills.json"
    s = skills.speichern(datei, "Lang", "x" * 7000)
    assert skills.hoechstlaenge(8192) == 6144
    assert skills.liste(datei, 8192)[0]["passt"] is False
    assert skills.liste(datei, 32768)[0]["passt"] is True
    with pytest.raises(ValueError, match="zu lang für das Kontextfenster"):
        skills.fuer_anfrage(datei, s["id"], 8192)
    assert skills.fuer_anfrage(datei, s["id"], 32768)["skills"][0]["name"] == "Lang"
    assert skills.fuer_anfrage(datei, None, 8192) == {"skills": [], "hinweis": None}
    with pytest.raises(LookupError):
        skills.fuer_anfrage(datei, "weg", 8192)


def test_systemanweisung_regeln_zuerst():
    ohne = skills.systemanweisung("REGELN", None)
    assert ohne == "REGELN"
    mit = skills.systemanweisung("REGELN", {"name": "Gegnerbrille", "text": "Sei kritisch."})
    assert mit.startswith("REGELN") and mit.index("Regeln oben gehen ihr vor") < mit.index("Sei kritisch.")


def test_chat_mit_skill(akten, con, tmp_path):  # noqa: F811
    akte_id, _ = _akte(akten, con, tmp_path)
    modell = Merker(gute_antwort)
    skill = {"id": "1", "name": "Gegnerbrille", "text": "Lies alles aus Sicht der Gegenseite."}
    antwort = chat.frage(akten, modell, 16384, akte_id, "Lehnt das Autohaus ab?", skills=[skill])
    assert "Lies alles aus Sicht der Gegenseite." in modell.systeme[0]
    assert antwort["skills"] == ["Gegnerbrille"]
    assert chat.verlauf(akten, akte_id)[-1]["skills"] == ["Gegnerbrille"]
    ohne = chat.frage(akten, modell, 16384, akte_id, "Und sonst?", skill_hinweis="Kein Skill passte.")
    assert "Gegnerbrille" not in modell.systeme[-1] and "skills" not in ohne
    assert ohne["skill_hinweis"] == "Kein Skill passte."


def test_analyse_mit_skill_speichert_getrennt(akten, con, tmp_path):  # noqa: F811
    _, ids = _akte(akten, con, tmp_path)
    modell = Merker(modell_antwort)
    ohne = Analyse(akten, modell).zusammenfassung_dokument(ids["03"])
    assert "skill" not in ohne and "Arbeitsanweisung" not in modell.systeme[-1]
    anfragen = len(modell.systeme)
    skill = {"id": "1", "name": "Gegnerbrille", "text": "Lies alles aus Sicht der Gegenseite."}
    mit = Analyse(akten, modell, skills=[skill]).zusammenfassung_dokument(ids["03"])
    assert len(modell.systeme) > anfragen, "mit Skill ist das gespeicherte Ergebnis ohne Skill nicht passend"
    assert mit["skills"] == ["Gegnerbrille"] and "Gegenseite" in modell.systeme[-1]
    wieder = Analyse(akten, modell, skills=[skill]).zusammenfassung_dokument(ids["03"])
    assert wieder["gespeichert"] is True and wieder["skills"] == ["Gegnerbrille"]


def test_rpc_skills_und_chat(con, tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    modell = Merker(gute_antwort)
    kern.ki_fabrik = lambda e, schluessel=None: modell
    akte_id, _ = _akte(kern.akten, con, tmp_path)

    def aufruf(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    assert aufruf("skills.liste") == {"skills": [], "kontext": None}
    s = aufruf("skills.speichern", name="Gegnerbrille", text="Lies alles aus Sicht der Gegenseite.")
    aufruf("ki.einstellungen_setzen", anbieter="ollama", endpunkt="http://127.0.0.1:9", modell=Attrappe.modell)
    liste = aufruf("skills.liste")
    assert liste["kontext"] and liste["skills"][0]["passt"] is True
    auftrag = aufruf("ki.chat_fragen", akte_id=akte_id, frage="Lehnt das Autohaus ab?", skill=s["id"])
    stand = _warte(lambda: aufruf("ki.auftrag", auftrag_id=auftrag["auftrag_id"]))
    assert stand["status"] == "fertig", stand
    assert stand["ergebnis"]["skills"] == ["Gegnerbrille"] and "Gegenseite" in modell.systeme[-1]

    # Mehrfachauswahl über einen Ordner: zur Frage passt keiner, also ohne Skill und mit Hinweis.
    aufruf("skills.speichern", name="Mietminderung", text="Prüfe § 536 BGB.", ordner="Zivilrecht / Miete")
    auftrag = aufruf("ki.chat_fragen", akte_id=akte_id, frage="Lehnt das Autohaus ab?",
                     skills=["ordner:Zivilrecht"])
    stand = _warte(lambda: aufruf("ki.auftrag", auftrag_id=auftrag["auftrag_id"]))
    assert "skills" not in stand["ergebnis"] and "passte" in stand["ergebnis"]["skill_hinweis"]
    assert (tmp_path / "skills.json").exists()

    fehler = kern.bearbeite(json.dumps({"id": 2, "method": "ki.chat_fragen",
                                        "params": {"akte_id": akte_id, "frage": "x", "skill": "gibt-es-nicht"}}))
    assert "Skill" in fehler["error"]["message"]


def test_import_ordnet_nach_paket(tmp_path):
    datei = tmp_path / "skills.json"
    zip_pfad = tmp_path / "pakete.zip"
    with zipfile.ZipFile(zip_pfad, "w") as z:
        z.writestr("bgb-at-pruefer/README.md", "# BGB AT Prüfer\n\nText")
        z.writestr("bgb-at-pruefer/skills/zugang/SKILL.md", "---\nname: zugang-paragraph-130\n---\nZugang.")
        z.writestr("bgb-bt-pruefer/.claude-plugin/plugin.json", json.dumps({"displayName": "BGB BT Prüfer"}))
        z.writestr("bgb-bt-pruefer/skills/miete/SKILL.md", "---\nname: mietminderung\n---\nMiete.")
        z.writestr("ohne-titel/skills/frist/SKILL.md", "---\nname: fristen\n---\nFristen.")
    r = skills.importieren(datei, str(zip_pfad))
    assert {s["name"]: s["ordner"] for s in r["uebernommen"]} == {
        "zugang-paragraph-130": "BGB AT Prüfer", "mietminderung": "BGB BT Prüfer", "fristen": "Ohne Titel"}
    md = tmp_path / "einzeln.md"
    md.write_text("# Einzeln\n\nText.", encoding="utf-8")
    assert skills.importieren(datei, str(md))["uebernommen"][0]["ordner"] == ""
    assert skills.importieren(datei, str(zip_pfad),
                              ordner="Test")["uebernommen"] == []  # schon vorhanden
    assert [s["ordner"] for s in skills.liste(datei)] == ["BGB AT Prüfer", "BGB BT Prüfer", "Ohne Titel", ""]


def test_ordner_umbenennen_und_loeschen(tmp_path):
    datei = tmp_path / "skills.json"
    skills.speichern(datei, "A", "a", ordner="BGB AT Prüfer")
    skills.speichern(datei, "B", "b", ordner=" Zivilrecht/ BGB  BT ")
    skills.speichern(datei, "C", "c")
    assert skills.liste(datei)[1]["ordner"] == "Zivilrecht / BGB BT"
    assert skills.ordner_umbenennen(datei, "BGB AT Prüfer", "Zivilrecht / BGB AT") == {"geaendert": 1}
    assert [s["ordner"] for s in skills.liste(datei)] == ["Zivilrecht / BGB AT", "Zivilrecht / BGB BT", ""]
    assert skills.ordner_umbenennen(datei, "Zivilrecht", "Privatrecht") == {"geaendert": 2}
    assert skills.ordner_loeschen(datei, "Privatrecht") == {"geloescht": 2}
    assert [s["name"] for s in skills.liste(datei)] == ["C"]
    with pytest.raises(ValueError):
        skills.ordner_umbenennen(datei, "", "X")


def test_auswahl_nimmt_die_passendsten(tmp_path):
    datei = tmp_path / "skills.json"
    zugang = skills.speichern(datei, "zugang-paragraph-130", "# Zugang von Willenserklärungen\nPrüfe § 130 BGB.",
                              "Zugang unter Abwesenden", ordner="BGB AT")
    skills.speichern(datei, "anfechtung-irrtum", "# Anfechtung\nPrüfe §§ 119, 142 BGB.", ordner="BGB AT")
    miete = skills.speichern(datei, "mietminderung-536", "# Mietminderung\nPrüfe § 536 BGB.", ordner="BGB BT")
    lang = skills.speichern(datei, "zugang-lang", "# Zugang\n" + "x" * 7000, ordner="BGB AT")

    w = skills.fuer_anfrage(datei, ["alle"], 32768, "Ist der Zugang der Kündigung nach § 130 BGB erfolgt?")
    assert [s["name"] for s in w["skills"]] == ["zugang-paragraph-130", "zugang-lang"] and w["hinweis"] is None
    # Bei 8k passt neben dem kurzen der lange nicht mehr hinein.
    w = skills.fuer_anfrage(datei, ["alle"], 8192, "Ist der Zugang der Kündigung nach § 130 BGB erfolgt?")
    assert [s["name"] for s in w["skills"]] == ["zugang-paragraph-130"]
    w = skills.fuer_anfrage(datei, ["ordner:BGB BT"], 32768, "Ist die Kündigung zugegangen?")
    assert w["skills"] == [] and "passte" in w["hinweis"]
    # Einzeln gewählte gelten immer, auch ohne Übereinstimmung, und kommen zuerst.
    w = skills.fuer_anfrage(datei, [miete["id"], "ordner:BGB AT"], 32768, "Zugang nach § 130?")
    assert [s["name"] for s in w["skills"]][:2] == ["mietminderung-536", "zugang-paragraph-130"]
    # Ein einzelner zu langer Skill ist ein Fehler, in einer Menge wird er übergangen.
    with pytest.raises(ValueError):
        skills.fuer_anfrage(datei, [lang["id"]], 8192, "")
    assert skills.fuer_anfrage(datei, [zugang["id"], lang["id"]], 8192, "Zugang")["skills"][0]["id"] == zugang["id"]
    system = skills.systemanweisung("REGELN", w["skills"])
    assert "gelten die folgenden Arbeitsanweisungen" in system and system.count("<<< Arbeitsanweisung") == len(w["skills"]) == 3
