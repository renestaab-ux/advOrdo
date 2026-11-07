import importlib.util
from pathlib import Path

SKRIPT = Path(__file__).resolve().parents[1] / "kern_methoden.py"


def test_freigabeliste_der_oberflaeche_ist_aktuell():
    spec = importlib.util.spec_from_file_location("kern_methoden", SKRIPT)
    km = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(km)
    assert km.LISTE.read_text(encoding="utf-8") == km.text(), (
        "app/src-tauri/kern-methoden.txt ist veraltet: python core/kern_methoden.py ausführen")
    # Was die Oberfläche nie aufruft, bleibt gesperrt (Beispiele aus der Code-Prüfung, O4).
    assert "akten.beteiligung_aendern" not in km.erwartet()
    assert "akten.importieren_dateien" in km.erwartet()
