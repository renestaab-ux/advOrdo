"""Liste der Kernmethoden, die die Oberfläche aufrufen darf (app/src-tauri/kern-methoden.txt).

Die Tauri-Hülle reicht nur diese Methoden an den Kern weiter. Eingeschleuster Code in der
Oberfläche könnte so keine Methode nutzen, die die App selbst nie aufruft. Die Liste ist die
Schnittmenge aus allen Methoden des Kerns und allen Zeichenketten im Quelltext der Oberfläche
(app/src, ohne Tests); so sind auch Methoden erfasst, deren Name erst über eine Variable übergeben wird.

Neu erzeugen nach Änderungen an Oberfläche oder Kern:  python core/kern_methoden.py
Der Test core/tests/test_kern_methoden.py schlägt fehl, solange die Liste veraltet ist.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parent
OBERFLAECHE = CORE.parent / "app" / "src"
LISTE = CORE.parent / "app" / "src-tauri" / "kern-methoden.txt"
KOPF = "# Kernmethoden, die die Oberfläche aufrufen darf. Erzeugt mit: python core/kern_methoden.py\n"


def kern_methoden() -> set[str]:
    sys.path.insert(0, str(CORE))
    from juracore.rpc import Kern

    with tempfile.TemporaryDirectory() as ordner:
        k = Kern(Path(ordner) / "wissensbasis.sqlite", Path(ordner) / "archiv")
        try:
            return set(k.methoden)
        finally:
            k.con.close()
            k.akten.close()


def zeichenketten() -> set[str]:
    gefunden: set[str] = set()
    for datei in sorted(OBERFLAECHE.rglob("*.ts*")):
        if ".test." in datei.name:
            continue
        gefunden |= set(re.findall(r"""["'`]([a-z_]+(?:\.[a-z_]+)+)["'`]""", datei.read_text(encoding="utf-8")))
    return gefunden


def erwartet() -> list[str]:
    return sorted(kern_methoden() & zeichenketten())


def text() -> str:
    return KOPF + "".join(f"{m}\n" for m in erwartet())


if __name__ == "__main__":
    LISTE.write_text(text(), encoding="utf-8", newline="\n")
    print(f"{LISTE}: {len(erwartet())} Methoden")
