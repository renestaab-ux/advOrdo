import json
import subprocess
import sys
from pathlib import Path

from .conftest import FIXTURES

CORE = Path(__file__).parents[1]


def test_stdio_protokoll(tmp_path):
    anfragen = [
        {"id": 1, "method": "ping"},
        {"id": 2, "method": "gesetze.importieren_datei", "params": {"pfad": str(FIXTURES / "bgb_auszug.xml")}},
        {"id": 3, "method": "zitat.aufloesen", "params": {"zitat": "§ 823 Abs. 2 S. 2 BGB"}},
        {"id": 4, "method": "gibt.es.nicht"},
        {"id": 5, "method": "zitat.aufloesen", "params": {"zitat": "kein Zitat"}},
    ]
    eingabe = "".join(json.dumps(a) + "\n" for a in anfragen)
    lauf = subprocess.run(
        [
            sys.executable,
            "-m",
            "juracore",
            "--db",
            str(tmp_path / "db.sqlite"),
            "--archiv",
            str(tmp_path / "a"),
            "serve",
        ],
        input=eingabe,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=CORE,
        timeout=60,
        check=True,
    )
    antworten = {a["id"]: a for a in map(json.loads, lauf.stdout.splitlines())}
    assert antworten[1]["result"]["version"]
    assert antworten[2]["result"]["neu"] is True
    assert antworten[3]["result"]["wortlaut"].startswith("Ist nach dem Inhalt des Gesetzes")
    assert "Unbekannte Methode" in antworten[4]["error"]["message"]
    assert "Kein Normzitat" in antworten[5]["error"]["message"]


def test_akten_ueber_rpc(tmp_path):
    from juracore.rpc import Kern

    from .conftest import schreibe_pdf

    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    kern.bearbeite(json.dumps({"id": 1, "method": "gesetze.importieren_datei", "params": {"pfad": str(FIXTURES / "zpo_auszug.xml")}}))
    pdf = schreibe_pdf(tmp_path / "klage.pdf", [["(1) Die Klägerin beantragt Beweiswürdigung nach § 286 Abs. 2 ZPO."]])

    def rufe(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    akte = rufe("akten.anlegen", name="Testakte")
    ergebnis = rufe("akten.importieren", akte_id=akte["id"], pfad=str(pdf))
    assert ergebnis["zitate"] == {"belegt": 1}
    assert rufe("akten.liste")[0]["dokumente"] == 1
    inhalt = rufe("akten.dokument", dokument_id=ergebnis["dokument_id"])
    assert inhalt["abschnitte"][0]["rn"] == 1
    assert rufe("akten.normen", akte_id=akte["id"])[0]["zitat"] == "§ 286 Abs. 2 ZPO"
    assert "verfuegbar" in rufe("ocr.status")
    # Originale liegen neben der Datenbank, getrennt je Akte.
    assert (tmp_path / "akten" / f"akte-{akte['id']}").is_dir()

    fehler = kern.bearbeite(json.dumps({"id": 2, "method": "akten.importieren", "params": {"akte_id": akte["id"], "pfad": "x.xlsx"}}))
    assert "error" in fehler
