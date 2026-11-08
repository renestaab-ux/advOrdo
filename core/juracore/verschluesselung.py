"""Ist der Datenordner auf einer verschlüsselten Festplatte? (Adapter je Betriebssystem)

advOrdo speichert Akten und Originale unverschlüsselt im Datenordner. Für die
Verschwiegenheit (§ 43a Abs. 2 BRAO, § 2 BORA) und die Sicherheit der Verarbeitung
(Art. 32 DSGVO) genügt das, wenn das Laufwerk selbst verschlüsselt ist. Geprüft wird
ohne Administratorrechte und ohne etwas zu ändern:

- Windows: BitLocker bzw. Geräteverschlüsselung über die Laufwerkseigenschaft
  ``System.Volume.BitLockerProtection`` (Explorer-Eigenschaft, keine Adminrechte nötig).
- macOS: ``fdesetup status`` (FileVault).
- Linux: Liegt der Ordner auf einem dm-crypt-Gerät (LUKS), auch unter LVM, oder auf ecryptfs?
"""

from __future__ import annotations

import ntpath
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

AN, AUS, UNBEKANNT = "an", "aus", "unbekannt"
ZEITLIMIT = 20


@dataclass
class Befund:
    stand: str  # an, aus, unbekannt
    verfahren: str  # BitLocker, FileVault, LUKS …
    details: list[str] = field(default_factory=list)


def _ausfuehren(befehl: list[str]) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ergebnis = subprocess.run(befehl, capture_output=True, timeout=ZEITLIMIT, creationflags=flags,
                              stdin=subprocess.DEVNULL)
    return ergebnis.stdout.decode("utf-8", "replace").strip()


# --- Windows ---------------------------------------------------------------------------------------

# Werte der Eigenschaft System.Volume.BitLockerProtection
_BITLOCKER = {
    "1": (AN, "BitLocker ist eingeschaltet."),
    "3": (AN, "BitLocker verschlüsselt das Laufwerk gerade."),
    "6": (AN, "BitLocker ist eingeschaltet (Laufwerk gesperrt)."),
    "2": (AUS, "BitLocker ist ausgeschaltet."),
    "4": (AUS, "BitLocker entschlüsselt das Laufwerk gerade."),
    "5": (AUS, "BitLocker ist angehalten; die Daten liegen derzeit ungeschützt auf dem Laufwerk."),
    "0": (AUS, "Das Laufwerk kann nicht mit BitLocker verschlüsselt werden."),
}


def _windows(ordner: Path) -> Befund:
    laufwerk = ntpath.splitdrive(str(ordner))[0]
    if not laufwerk or laufwerk.startswith("\\\\"):
        return Befund(UNBEKANNT, "BitLocker", [f"Der Datenordner liegt nicht auf einem lokalen Laufwerk ({ordner})."])
    powershell = ntpath.join(os.environ.get("SystemRoot") or r"C:\Windows",
                             "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    skript = ("(New-Object -ComObject Shell.Application).NameSpace('" + laufwerk + "\\').Self"
              ".ExtendedProperty('System.Volume.BitLockerProtection')")
    wert = _ausfuehren([powershell, "-NoProfile", "-NonInteractive", "-Command", skript])
    stand, text = _BITLOCKER.get(wert, (UNBEKANNT, f"Unbekannter Wert der Laufwerkseigenschaft: {wert or 'leer'}"))
    return Befund(stand, "BitLocker", [f"Laufwerk {laufwerk}: {text}"])


# --- macOS -----------------------------------------------------------------------------------------

def _macos(_ordner: Path) -> Befund:
    text = _ausfuehren(["/usr/bin/fdesetup", "status"])
    if "FileVault is On" in text:
        return Befund(AN, "FileVault", [text.splitlines()[0]])
    if "FileVault is Off" in text:
        return Befund(AUS, "FileVault", [text.splitlines()[0]])
    return Befund(UNBEKANNT, "FileVault", [text or "fdesetup lieferte keine Antwort."])


# --- Linux -----------------------------------------------------------------------------------------

def _einhaengepunkt(pfad: Path, mountinfo: str) -> tuple[str, str, str] | None:
    """(Einhängepunkt, Dateisystem, Quelle) des längsten passenden Eintrags aus /proc/self/mountinfo."""
    bester = None
    for zeile in mountinfo.splitlines():
        teile = zeile.split()
        if " - " not in zeile or len(teile) < 10:
            continue
        punkt = teile[4].replace("\\040", " ")
        rest = zeile.split(" - ", 1)[1].split()
        if len(rest) < 2:
            continue
        p = str(pfad)
        if (p == punkt or p.startswith(punkt.rstrip("/") + "/")) and (bester is None or len(punkt) > len(bester[0])):
            bester = (punkt, rest[0], rest[1])
    return bester


def _verschluesselt(block: Path, tiefe: int = 0) -> bool:
    """Ist das Blockgerät (unter /sys/dev/block) oder eines darunter ein dm-crypt-Gerät?"""
    try:
        if (block / "dm" / "uuid").read_text(encoding="utf-8").startswith("CRYPT-"):
            return True
    except OSError:
        pass
    if tiefe > 8:
        return False
    try:
        unten = list((block / "slaves").iterdir())
    except OSError:
        unten = []
    return any(_verschluesselt(s.resolve(), tiefe + 1) for s in unten)


def _geraetenummer(quelle: str) -> tuple[int, int]:
    nummer = os.stat(quelle).st_rdev
    return os.major(nummer), os.minor(nummer)  # nur unter Linux aufgerufen


def _linux(ordner: Path, sys_block: Path = Path("/sys/dev/block"), mountinfo: str | None = None,
           geraet_von: Callable[[str], tuple[int, int]] | None = None) -> Befund:
    if mountinfo is None:
        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    eintrag = _einhaengepunkt(ordner.resolve(), mountinfo)
    if eintrag is None:
        return Befund(UNBEKANNT, "LUKS", ["Einhängepunkt des Datenordners nicht gefunden."])
    punkt, dateisystem, quelle = eintrag
    details = [f"Datenordner auf {quelle} ({dateisystem}, eingehängt unter {punkt})"]
    if dateisystem in ("ecryptfs", "gocryptfs", "fuse.gocryptfs", "fuse.cryfs"):
        return Befund(AN, dateisystem, details)
    if not quelle.startswith("/dev/"):
        return Befund(UNBEKANNT, "LUKS", details + ["Kein Blockgerät; Verschlüsselung nicht prüfbar."])
    try:
        haupt, neben = (geraet_von or _geraetenummer)(quelle)
    except OSError as fehler:
        return Befund(UNBEKANNT, "LUKS", details + [str(fehler)])
    block = sys_block / f"{haupt}:{neben}"
    if _verschluesselt(block):
        return Befund(AN, "LUKS (dm-crypt)", details)
    return Befund(AUS, "LUKS (dm-crypt)", details + ["Kein dm-crypt-Gerät unter dem Datenordner gefunden."])


def pruefe(ordner: Path, system: str = sys.platform) -> Befund:
    try:
        if system == "win32":
            return _windows(Path(ordner))
        if system == "darwin":
            return _macos(Path(ordner))
        return _linux(Path(ordner))
    except (OSError, subprocess.SubprocessError) as fehler:
        return Befund(UNBEKANNT, "", [f"Prüfung nicht möglich: {fehler}"])
