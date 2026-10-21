"""Bündelt den Analysekern zu einem eigenständigen Programm für den Installer.

Aufruf aus dem Projektordner, mit dem Python der ``.venv``:

    python core/kern_bauen.py

Ergebnis: ``app/src-tauri/binaries/juracore-<Zielsystem>[.exe]``. Tauri legt die Datei beim
``npm run paket`` als ``juracore[.exe]`` neben die App; ``kern.rs`` startet sie von dort.
Voraussetzung: ``pip install -e "core[paket]"`` (PyInstaller) in derselben Umgebung.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parent
ZIEL = CORE.parent / "app" / "src-tauri" / "binaries"


def zielsystem() -> str:
    """Rust-Zieltripel wie ``x86_64-pc-windows-msvc``; Tauri erwartet es im Dateinamen."""
    ausgabe = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    for zeile in ausgabe.splitlines():
        if zeile.startswith("host:"):
            return zeile.split(":", 1)[1].strip()
    raise SystemExit("rustc -vV nennt kein Zielsystem")


def main() -> int:
    endung = ".exe" if os.name == "nt" else ""
    name = f"juracore-{zielsystem()}"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_pfad = Path(tmp)
        start = tmp_pfad / "juracore_start.py"
        start.write_text("from juracore.__main__ import main\n\nraise SystemExit(main())\n", encoding="utf-8")
        daten = CORE / "juracore" / "gesetze" / "voreinstellung.json"
        befehl = [
            sys.executable, "-m", "PyInstaller", str(start),
            "--onefile", "--noconfirm", "--clean",
            "--name", name,
            "--paths", str(CORE),
            "--collect-submodules", "juracore",
            "--collect-all", "pypdfium2",
            "--collect-all", "pypdfium2_raw",
            "--add-data", f"{daten}{os.pathsep}juracore/gesetze",
            "--distpath", str(ZIEL),
            "--workpath", str(tmp_pfad / "build"),
            "--specpath", str(tmp_pfad),
        ]
        subprocess.run(befehl, check=True)
    datei = ZIEL / f"{name}{endung}"
    print(f"Kern gebündelt: {datei} ({datei.stat().st_size // 1_000_000} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
