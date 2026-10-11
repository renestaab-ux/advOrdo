"""Speicherorte. Die Desktop-App übergibt ihr Datenverzeichnis über JURACORE_DATEN."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def datenverzeichnis() -> Path:
    if env := os.environ.get("JURACORE_DATEN"):
        return Path(env)
    if sys.platform == "win32":
        basis = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        basis = Path.home() / "Library" / "Application Support"
    else:
        basis = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return basis / "juristischer-datenabgleich"


def datenbank() -> Path:
    return datenverzeichnis() / "wissensbasis.sqlite"


def roharchiv() -> Path:
    return datenverzeichnis() / "roharchiv" / "gesetze"
