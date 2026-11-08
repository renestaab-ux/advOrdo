"""Adapter zum Schlüsselbund des Betriebssystems für geheime Zugangsdaten (API-Schlüssel).

Windows: Anmeldeinformationsverwaltung, macOS: Schlüsselbund, Linux: Secret Service
(GNOME-Schlüsselbund, KWallet). Dort liegen die Schlüssel verschlüsselt und an die
Anmeldung des Benutzers gebunden, statt im Klartext in einer Datei.

Ist kein Schlüsselbund nutzbar (etwa Linux ohne Secret Service), bleibt es bei der
bisherigen Datei, die nur für den Benutzer lesbar ist. ``JURACORE_SCHLUESSELBUND=aus``
schaltet den Schlüsselbund ab (Tests, Server ohne Anmeldung).
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Protocol

log = logging.getLogger("juracore.schluesselbund")

# Dienstname bleibt „JuraBox“ (früherer Name der App), sonst fänden sich gespeicherte API-Schlüssel nicht mehr.
DIENST = "JuraBox"
SCHLUESSELBUND = "schluesselbund"
DATEI = "datei"


class Bund(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


_bund: Bund | None = None
_geprueft = False


def bund() -> Bund | None:
    """Der Schlüsselbund des Systems oder ``None``, wenn keiner nutzbar ist."""
    global _bund, _geprueft
    if os.environ.get("JURACORE_SCHLUESSELBUND", "").lower() in ("aus", "0", "nein"):
        return None
    if not _geprueft:
        _geprueft = True
        try:
            import keyring
            from keyring.backends import fail, null

            kandidat = keyring.get_keyring()
            if not isinstance(kandidat, (fail.Keyring, null.Keyring)):
                _bund = kandidat
        except Exception as fehler:
            log.info("Kein Schlüsselbund nutzbar: %s", fehler)
    return _bund


def setze_bund(neu: Bund | None) -> None:
    """Für Tests: einen anderen Schlüsselbund verwenden (``None``: keinen)."""
    global _bund, _geprueft
    _bund, _geprueft = neu, True


def eintrag(ordner: Path, name: str) -> str:
    """Name des Eintrags: je Datenordner getrennt, damit sich verschiedene Datenordner nicht überschreiben.

    Die API-Schlüssel liegen am gemeinsamen Datenordner (``Kern.schluessel_datei``) und gelten damit für alle
    Arbeitsumgebungen, so wie ``ki.json``. Das Löschen einer Umgebung lässt sie deshalb bewusst bestehen.
    """
    kennung = hashlib.sha256(str(Path(ordner).resolve()).encode("utf-8")).hexdigest()[:12]
    return f"{name}@{kennung}"


def lies(ordner: Path, name: str) -> str | None:
    """Wert aus dem Schlüsselbund; ``None``, wenn keiner da ist oder der Schlüsselbund nicht antwortet."""
    if (b := bund()) is None:
        return None
    try:
        return b.get_password(DIENST, eintrag(ordner, name)) or None
    except Exception as fehler:
        log.warning("Schlüsselbund nicht lesbar: %s", fehler)
        return None


def schreibe(ordner: Path, name: str, wert: str | None) -> bool:
    """Hinterlegt oder löscht (``None``) einen Wert. ``False``: kein Schlüsselbund, die Datei muss es tun."""
    if (b := bund()) is None:
        return False
    try:
        if wert:
            b.set_password(DIENST, eintrag(ordner, name), wert)
        else:
            try:
                b.delete_password(DIENST, eintrag(ordner, name))
            except Exception:
                pass
        return True
    except Exception as fehler:
        log.warning("Schlüsselbund nicht beschreibbar, nehme die Datei: %s", fehler)
        return False


def ort() -> str:
    return SCHLUESSELBUND if bund() is not None else DATEI
