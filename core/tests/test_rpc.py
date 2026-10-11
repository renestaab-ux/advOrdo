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
