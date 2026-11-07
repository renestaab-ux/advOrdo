import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from juracore import programme
from juracore.dokumente import akte, fassungen
from juracore.ki import speicher


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    speicher.einrichten(con)
    yield con
    con.close()


def _einlesen(akten, con, tmp_path, text="Der Anspruch folgt aus § 280 Abs. 1 BGB.", name="schriftsatz.txt"):
    datei = tmp_path / "eingang" / name
    datei.parent.mkdir(exist_ok=True)
    datei.write_text(text, encoding="utf-8")
    a = akten.execute("SELECT id FROM akte").fetchone() or akte.akte_anlegen(akten, "Akte")
    d = akte.importiere(akten, con, a["id"], datei, tmp_path / "ablage", ocr=False)
    return a["id"], d["dokument_id"], datei


def _schreibbar(pfad: Path) -> bool:
    return bool(pfad.stat().st_mode & stat.S_IWRITE)


def test_eingelesene_datei_ist_fassung_1(akten, con, tmp_path):
    akte_id, dok, _ = _einlesen(akten, con, tmp_path)
    info = akte.dokumente(akten, akte_id)[0]
    assert info["fassung"]["nr"] == 1 and info["fassung"]["quelle"] == "import"
    assert info["arbeitskopie"] is False
    assert [f["nr"] for f in fassungen.liste(akten, dok)] == [1]


def test_ansichtskopie_ist_schreibgeschuetzt(akten, con, tmp_path):
    akte_id, dok, datei = _einlesen(akten, con, tmp_path)
    ablage = tmp_path / "ablage"
    kopie = fassungen.ansichtskopie(akten, ablage, dok)
    assert kopie.name == "schriftsatz.txt"
    assert kopie.read_bytes() == datei.read_bytes()
    assert not _schreibbar(kopie)
    # Die abgelegte Datei ist eine andere und bleibt unberührt.
    assert Path(akte.dokumente(akten, akte_id)[0]["original"]) != kopie
    assert fassungen.ansichtskopie(akten, ablage, dok) == kopie


def test_bearbeiten_und_als_neue_fassung_uebernehmen(akten, con, tmp_path):
    akte_id, dok, datei = _einlesen(akten, con, tmp_path)
    ablage = tmp_path / "ablage"
    erste = Path(akte.dokumente(akten, akte_id)[0]["original"])

    k = fassungen.arbeitskopie(akten, ablage, dok)
    assert k["neu"] is True and _schreibbar(Path(k["pfad"]))
    assert fassungen.arbeitskopien(akten, akte_id)[0]["status"] == "unveraendert"
    with pytest.raises(ValueError, match="unverändert"):
        fassungen.uebernehmen(akten, con, ablage, dok, ocr=False)

    Path(k["pfad"]).write_text("Der Anspruch folgt aus § 280 Abs. 1 BGB und § 286 Abs. 2 ZPO.", encoding="utf-8")
    assert fassungen.arbeitskopien(akten, akte_id)[0]["status"] == "geaendert"
    ergebnis = fassungen.uebernehmen(akten, con, ablage, dok, ocr=False)
    assert ergebnis["fassung"] == 2
    assert ergebnis["zitate"] == {"belegt": 2}

    info = akte.dokumente(akten, akte_id)[0]
    assert info["fassung"]["nr"] == 2 and info["fassung"]["quelle"] == "bearbeitet"
    assert info["arbeitskopie"] is True
    assert "§ 286 Abs. 2 ZPO" in akte.dokument(akten, dok)["abschnitte"][0]["text"]
    # Die erste Fassung liegt unverändert weiter in der Ablage und lässt sich ansehen.
    assert erste.read_bytes() == datei.read_bytes()
    assert Path(info["original"]) != erste
    assert fassungen.ansichtskopie(akten, ablage, dok, 1).read_bytes() == datei.read_bytes()
    assert [(f["nr"], f["aktuell"]) for f in fassungen.liste(akten, dok)] == [(2, True), (1, False)]
    # Die Arbeitskopie zählt jetzt gegen Fassung 2 und wird beim nächsten Bearbeiten weiterverwendet.
    assert fassungen.arbeitskopien(akten, akte_id)[0]["status"] == "unveraendert"
    assert fassungen.arbeitskopie(akten, ablage, dok) == {"pfad": k["pfad"], "neu": False}
    # Die Volltextsuche findet den neuen Text.
    assert akten.execute("SELECT COUNT(*) FROM abschnitt_fts WHERE abschnitt_fts MATCH 'ZPO'").fetchone()[0] == 1


def test_uebernahme_lehnt_doppeltes_dokument_ab(akten, con, tmp_path):
    akte_id, dok, _ = _einlesen(akten, con, tmp_path)
    _einlesen(akten, con, tmp_path, "Anderer Text.", "anlage.txt")
    k = fassungen.arbeitskopie(akten, tmp_path / "ablage", dok)
    Path(k["pfad"]).write_text("Anderer Text.", encoding="utf-8")
    with pytest.raises(ValueError, match="anlage.txt"):
        fassungen.uebernehmen(akten, con, tmp_path / "ablage", dok, ocr=False)


def test_verwerfen_und_loeschen_raeumen_auf(akten, con, tmp_path):
    akte_id, dok, _ = _einlesen(akten, con, tmp_path)
    ablage = tmp_path / "ablage"
    k = fassungen.arbeitskopie(akten, ablage, dok)
    assert fassungen.verwerfen(akten, ablage, dok)["entfernt"] is True
    assert not Path(k["pfad"]).exists() and fassungen.arbeitskopien(akten, akte_id) == []

    k = fassungen.arbeitskopie(akten, ablage, dok)
    Path(k["pfad"]).write_text("Geändert.", encoding="utf-8")
    fassungen.uebernehmen(akten, con, ablage, dok, ocr=False)
    ansicht = fassungen.ansichtskopie(akten, ablage, dok, 1)
    dateien = [Path(f["original"]) for f in akten.execute("SELECT original FROM dokument_fassung").fetchall()]
    assert len(dateien) == 2 and all(f.exists() for f in dateien)

    assert akte.dokument_loeschen(akten, dok, ablage)["hinweis"] is None
    assert not any(f.exists() for f in dateien)
    assert not ansicht.exists() and not Path(k["pfad"]).exists()
    assert akten.execute("SELECT COUNT(*) FROM dokument_fassung").fetchone()[0] == 0


def test_akte_loeschen_mit_schreibgeschuetzter_kopie(akten, con, tmp_path):
    akte_id, dok, _ = _einlesen(akten, con, tmp_path)
    fassungen.ansichtskopie(akten, tmp_path / "ablage", dok)
    assert akte.akte_loeschen(akten, akte_id, tmp_path / "ablage")["hinweis"] is None
    assert not (tmp_path / "ablage" / f"akte-{akte_id}").exists()


def test_alte_dokumente_bekommen_fassung_1(tmp_path, con):
    pfad = tmp_path / "akten.sqlite"
    akten = akte.oeffne(pfad)
    _einlesen(akten, con, tmp_path)
    with akten:
        akten.execute("DELETE FROM dokument_fassung")
    akten.close()
    akten = akte.oeffne(pfad)
    assert [f["nr"] for f in fassungen.liste(akten, 1)] == [1]
    akten.close()


# --- Programme (Adapter) --------------------------------------------------------------------------


def test_befehle_je_system():
    datei = Path("/ablage/klage.pdf")
    assert programme.befehl(datei, system="win32") is None
    assert programme.befehl(datei, system="darwin") == ["open", str(datei)]
    assert programme.befehl(datei, system="linux") == ["xdg-open", str(datei)]
    assert programme.befehl(datei, "/usr/bin/okular", system="linux") == ["/usr/bin/okular", str(datei)]
    assert programme.befehl(datei, "soffice", "--writer --nologo", system="linux") == [
        "soffice", "--writer", "--nologo", str(datei)]
    assert programme.befehl(datei, "acrobat", "/A page=2 {datei}", system="linux") == [
        "acrobat", "/A", "page=2", str(datei)]
    assert programme.befehl(datei, "/Applications/LibreOffice.app", system="darwin") == [
        "open", "-a", "/Applications/LibreOffice.app", str(datei)]
    assert programme.befehl(datei, "/Applications/LibreOffice.app", "--nologo", system="darwin") == [
        "open", "-a", "/Applications/LibreOffice.app", str(datei), "--args", "--nologo"]
    assert programme.befehl(datei, r"C:\Programme\Word.exe", r'/q "C:\Vorlagen\x.dotx"', system="win32") == [
        r"C:\Programme\Word.exe", "/q", r"C:\Vorlagen\x.dotx", str(datei)]
    assert programme.ordner_befehl(datei, system="win32") == [programme.explorer(), f"/select,{datei}"]
    assert programme.explorer().lower().endswith("\\explorer.exe")  # voller Pfad, nicht nur „explorer“
    assert programme.ordner_befehl(datei, system="darwin") == ["open", "-R", str(datei)]
    assert programme.ordner_befehl(datei, system="linux") == ["xdg-open", str(datei.parent)]
    # Der Explorer braucht die Anführungszeichen nur um den Pfad, sonst öffnet er „Dokumente“
    assert programme.befehlszeile([r"C:\Windows\explorer.exe", r"/select,C:\Akten\05 Klage (markiert).pdf"]) == \
        r'"C:\Windows\explorer.exe" /select,"C:\Akten\05 Klage (markiert).pdf"'
    assert programme.befehlszeile(["open", "-R", "x"]) == ["open", "-R", "x"]


def test_einstellungen_der_programme(tmp_path):
    datei = tmp_path / "programme.json"
    assert programme.lade(datei)["pdf"] == {"titel": "PDF-Programm", "programm": "", "parameter": ""}
    programm = tmp_path / "okular"
    programm.write_text("")
    e = programme.speichere(datei, "pdf", str(programm), "--unique")
    assert e["pdf"]["programm"] == str(programm) and e["text"]["programm"] == ""
    assert json.loads(datei.read_text(encoding="utf-8"))["pdf"]["parameter"] == "--unique"
    with pytest.raises(ValueError, match="nicht gefunden"):
        programme.speichere(datei, "text", str(tmp_path / "fehlt.exe"))
    with pytest.raises(ValueError):
        programme.speichere(datei, "tabelle")
    assert programme.speichere(datei, "pdf")["pdf"]["programm"] == ""


def test_starten_ohne_verbindung_zum_kern(tmp_path, monkeypatch):
    aufrufe = []

    class Popen:
        def __init__(self, aufruf, **kw):
            aufrufe.append((aufruf, kw))

    monkeypatch.setattr(programme.subprocess, "Popen", Popen)
    programm = tmp_path / "leser"
    programm.write_text("")
    programme.starten(tmp_path / "a.pdf", {"programm": str(programm), "parameter": ""})
    aufruf, kw = aufrufe[0]
    assert aufruf == [str(programm), str(tmp_path / "a.pdf")]
    # stdout gehört dem Protokoll zwischen App und Kern.
    assert kw["stdout"] is subprocess.DEVNULL and kw["stdin"] is subprocess.DEVNULL
    with pytest.raises(RuntimeError, match="nicht gefunden"):
        programme.starten(tmp_path / "a.pdf", {"programm": str(tmp_path / "weg"), "parameter": ""})


def test_extern_bearbeiten_ueber_rpc(tmp_path, monkeypatch):
    from juracore.rpc import Kern

    gestartet = []
    monkeypatch.setattr(programme, "starten", lambda pfad, e: gestartet.append((Path(pfad), e)))
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")

    def rufe(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    datei = tmp_path / "brief.txt"
    datei.write_text("Sehr geehrte Damen und Herren,", encoding="utf-8")
    a = rufe("akten.anlegen", name="Akte")
    dok = rufe("akten.importieren", akte_id=a["id"], pfad=str(datei))["dokument_id"]

    ansicht = rufe("akten.extern_ansehen", dokument_id=dok)
    assert ansicht["programm"] == "Standardprogramm" and gestartet[-1][0] == Path(ansicht["pfad"])
    k = rufe("akten.extern_bearbeiten", dokument_id=dok)
    assert gestartet[-1][0] == Path(k["pfad"]) and gestartet[-1][1]["titel"] == "Textverarbeitung"

    speicher.schreibe(kern.akten, "x", "zusammenfassung_dokument", "m", {"text": "alt"}, a["id"], dok)
    speicher.schreibe(kern.akten, "y", "zusammenfassung_akte", "m", {"text": "alt"}, a["id"])
    Path(k["pfad"]).write_text("Sehr geehrte Damen und Herren, neu.", encoding="utf-8")
    assert rufe("akten.arbeitskopien", akte_id=a["id"])[0]["status"] == "geaendert"
    ergebnis = rufe("akten.fassung_uebernehmen", dokument_id=dok)
    assert ergebnis["fassung"] == 2 and ergebnis["ki_verworfen"] == 2
    assert len(rufe("akten.fassungen", dokument_id=dok)) == 2
    assert rufe("akten.arbeitskopie_verwerfen", dokument_id=dok)["entfernt"] is True
    assert rufe("programme.einstellungen")["pdf"]["programm"] == ""


@pytest.mark.skipif(os.name != "nt", reason="Schreibschutz-Attribut nur unter Windows")
def test_windows_schreibschutz(akten, con, tmp_path):
    _, dok, _ = _einlesen(akten, con, tmp_path)
    kopie = fassungen.ansichtskopie(akten, tmp_path / "ablage", dok)
    with pytest.raises(PermissionError):
        kopie.write_text("x")
