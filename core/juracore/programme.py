"""Externe Programme: Dokumente im PDF-Programm oder in der Textverarbeitung öffnen.

Herstellerneutral: JuraBox übergibt nur die Datei an das gewählte Programm (LibreOffice,
Microsoft Office, PDF-XChange, Okular …). Voreinstellung ist das Standardprogramm des
Systems. Die Einstellung gilt für das Gerät, nicht je Arbeitsumgebung.

Dies ist der Adapter für die Systemaufrufe (Projektregel): Nur hier steht, wie Windows,
macOS und Linux ein Programm oder den Dateimanager starten. Gestartet wird ohne
Verbindung zu den Ein- und Ausgaben des Kerns, weil der Kern über stdout mit der App spricht.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

ARTEN = {"pdf": "PDF-Programm", "text": "Textverarbeitung"}
PLATZHALTER = "{datei}"


def art_fuer(fmt: str) -> str:
    """PDFs gehen an das PDF-Programm, Word- und Textdateien an die Textverarbeitung."""
    return "pdf" if fmt == "pdf" else "text"


def lade(datei: Path) -> dict:
    try:
        gespeichert = json.loads(Path(datei).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        gespeichert = {}
    return {
        art: {
            "titel": titel,
            "programm": str((gespeichert.get(art) or {}).get("programm") or ""),
            "parameter": str((gespeichert.get(art) or {}).get("parameter") or ""),
        }
        for art, titel in ARTEN.items()
    }


def speichere(datei: Path, art: str, programm: str = "", parameter: str = "") -> dict:
    """Setzt das Programm für ``art``; leeres ``programm`` heißt Standardprogramm des Systems."""
    if art not in ARTEN:
        raise ValueError(f"Unbekannte Programmart: {art}")
    programm, parameter = programm.strip(), parameter.strip()
    if programm and not _vorhanden(programm):
        raise ValueError(f"Programm nicht gefunden: {programm}")
    if parameter:
        _zerlege(parameter)  # unvollständige Anführungszeichen gleich melden
    daten = {a: {k: e[k] for k in ("programm", "parameter")} for a, e in lade(datei).items()}
    daten[art] = {"programm": programm, "parameter": parameter}
    Path(datei).parent.mkdir(parents=True, exist_ok=True)
    Path(datei).write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    return lade(datei)


def _vorhanden(programm: str) -> bool:
    return Path(programm).exists() or shutil.which(programm) is not None


def _zerlege(parameter: str, system: str = sys.platform) -> list[str]:
    # Windows-Pfade enthalten Backslashes; dort nur Anführungszeichen auswerten.
    teile = shlex.split(parameter, posix=system != "win32")
    return [t[1:-1] if system == "win32" and len(t) > 1 and t[0] == t[-1] == '"' else t for t in teile]


def befehl(datei: Path, programm: str = "", parameter: str = "", system: str = sys.platform) -> list[str] | None:
    """Aufruf für ``datei``. ``None`` heißt: Windows-Standardprogramm über die Dateizuordnung (``os.startfile``)."""
    datei_text = str(datei)
    if not programm:
        if system == "win32":
            return None
        if system == "darwin":
            return ["open", datei_text]
        return ["xdg-open", datei_text]
    zusatz = _zerlege(parameter, system) if parameter else []
    if PLATZHALTER in " ".join(zusatz):
        argumente = [t.replace(PLATZHALTER, datei_text) for t in zusatz]
    else:
        argumente = [*zusatz, datei_text]
    if system == "darwin" and programm.rstrip("/").endswith(".app"):
        # Ein macOS-Programmpaket ist ein Ordner; gestartet wird es über „open -a“.
        rest = [a for a in argumente if a != datei_text]
        return ["open", "-a", programm, datei_text, *(["--args", *rest] if rest else [])]
    return [programm, *argumente]


def ordner_befehl(datei: Path, system: str = sys.platform) -> list[str]:
    """Dateimanager mit der Datei (Windows, macOS markieren sie) bzw. ihrem Ordner (Linux)."""
    if system == "win32":
        return ["explorer", f"/select,{datei}"]
    if system == "darwin":
        return ["open", "-R", str(datei)]
    return ["xdg-open", str(Path(datei).parent)]


def starten(datei: Path, einstellung: dict) -> None:
    aufruf = befehl(datei, einstellung.get("programm", ""), einstellung.get("parameter", ""))
    if aufruf is None:
        try:
            os.startfile(datei)  # type: ignore[attr-defined]  # nur unter Windows vorhanden
        except OSError as fehler:
            raise RuntimeError(
                f"Für {Path(datei).suffix or 'diese Datei'} ist kein Standardprogramm eingerichtet ({fehler}). "
                "Bitte in den Einstellungen unter „Programme“ ein Programm wählen."
            ) from fehler
        return
    _ausfuehren(aufruf)


def befehlszeile(aufruf: list[str]) -> str | list[str]:
    """Unter Windows die Befehlszeile für den Explorer selbst bauen.

    ``subprocess`` setzt ein Argument mit Leerzeichen ganz in Anführungszeichen (``"/select,C:\\a b.pdf"``). Das
    versteht der Explorer nicht und öffnet dann „Dokumente“; er braucht ``/select,"C:\\a b.pdf"``.
    """
    if len(aufruf) == 2 and aufruf[0] == "explorer" and aufruf[1].startswith("/select,"):
        return f'explorer /select,"{aufruf[1][len("/select,"):]}"'
    return aufruf


def im_ordner_zeigen(datei: Path) -> None:
    aufruf = ordner_befehl(datei)
    _ausfuehren(aufruf, befehlszeile(aufruf) if sys.platform == "win32" else None)


def im_browser_oeffnen(adresse: str) -> None:
    """Öffnet eine Internetadresse im Standardbrowser, ohne die Ausgabe des Kerns zu stören."""
    if not adresse.startswith("https://"):
        raise ValueError("Nur https-Adressen werden geöffnet.")
    if sys.platform == "win32":
        os.startfile(adresse)  # type: ignore[attr-defined]  # nur unter Windows vorhanden
        return
    _ausfuehren(["open" if sys.platform == "darwin" else "xdg-open", adresse])


def _ausfuehren(aufruf: list[str], zeile: str | list[str] | None = None) -> None:
    if shutil.which(aufruf[0]) is None and not Path(aufruf[0]).exists():
        if aufruf[0] == "xdg-open":
            raise RuntimeError(
                "xdg-open ist nicht installiert. Bitte in den Einstellungen unter „Programme“ ein Programm wählen."
            )
        raise RuntimeError(f"Programm nicht gefunden: {aufruf[0]}")
    zusatz: dict = {}
    if sys.platform == "win32":
        zusatz["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        zusatz["start_new_session"] = True
    try:
        subprocess.Popen(  # noqa: S603 - Programm und Datei stammen aus den Einstellungen und der Ablage
            zeile or aufruf, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, **zusatz,
        )
    except OSError as fehler:
        raise RuntimeError(f"{aufruf[0]} ließ sich nicht starten: {fehler}") from fehler


def adresse_oeffnen(adresse: str) -> None:
    """Öffnet eine Internetadresse (z. B. eine Nachricht der Startseite) im Standardbrowser."""
    if urllib.parse.urlsplit(adresse).scheme not in ("http", "https"):
        raise ValueError("Nur Adressen mit http:// oder https:// lassen sich öffnen.")
    if sys.platform == "win32":
        try:
            os.startfile(adresse)  # type: ignore[attr-defined]  # nur unter Windows vorhanden
        except OSError as fehler:
            raise RuntimeError(f"Der Browser ließ sich nicht öffnen ({fehler}).") from fehler
        return
    _ausfuehren(["open" if sys.platform == "darwin" else "xdg-open", adresse])
