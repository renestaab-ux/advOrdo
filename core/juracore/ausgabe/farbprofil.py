"""Farbprofil sRGB (ICC v2) für die Ausgabebedingung von PDF/A (ISO 19005-2, 6.2.4.3).

Ein PDF/A darf Gerätefarben (RGB, Grau) nur mit einer Ausgabebedingung (OutputIntent) verwenden, die ein
ICC-Profil enthält. Das Profil wird hier erzeugt statt als Datei mitgeliefert: Primärfarben und Weißpunkt nach
IEC 61966-2-1 (auf D50 angepasst, wie ICC v2 es verlangt) und die sRGB-Gradationskurve als Tabelle.
"""

from __future__ import annotations

import struct
from functools import cache

BESCHREIBUNG = "sRGB IEC61966-2.1"


def _s15(wert: float) -> bytes:
    return struct.pack(">i", round(wert * 65536))


def _xyz(x: float, y: float, z: float) -> bytes:
    return b"XYZ \0\0\0\0" + _s15(x) + _s15(y) + _s15(z)


def _desc(text: str) -> bytes:
    ascii_ = text.encode("ascii") + b"\0"
    # textDescriptionType: ASCII, dann leerer Unicode- und ScriptCode-Teil (67 Byte Füllung).
    return b"desc\0\0\0\0" + struct.pack(">I", len(ascii_)) + ascii_ + struct.pack(">II", 0, 0) + b"\0\0\0" + b"\0" * 67


def _text(text: str) -> bytes:
    return b"text\0\0\0\0" + text.encode("ascii") + b"\0"


def _kurve(punkte: int = 1024) -> bytes:
    werte = []
    for i in range(punkte):
        v = i / (punkte - 1)
        linear = v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        werte.append(round(linear * 65535))
    return b"curv\0\0\0\0" + struct.pack(">I", punkte) + struct.pack(f">{punkte}H", *werte)


@cache
def srgb() -> bytes:
    """Das Profil als Bytes (rund 2,5 KB)."""
    kurve = _kurve()
    tags = [
        (b"desc", _desc(BESCHREIBUNG)),
        (b"cprt", _text("Keine Rechte vorbehalten (gemeinfrei)")),
        (b"wtpt", _xyz(0.9642, 1.0, 0.8249)),
        (b"rXYZ", _xyz(0.4361, 0.2225, 0.0139)),
        (b"gXYZ", _xyz(0.3851, 0.7169, 0.0971)),
        (b"bXYZ", _xyz(0.1431, 0.0606, 0.7141)),
        (b"rTRC", kurve),
        (b"gTRC", kurve),
        (b"bTRC", kurve),
    ]
    versatz = 128 + 4 + 12 * len(tags)
    tabelle, daten = [], b""
    gesehen: dict[bytes, tuple[int, int]] = {}
    for sig, inhalt in tags:
        if inhalt not in gesehen:  # die drei Kurven teilen sich eine Tabelle
            daten += b"\0" * (-len(daten) % 4)
            gesehen[inhalt] = (versatz + len(daten), len(inhalt))
            daten += inhalt
        tabelle.append(sig + struct.pack(">II", *gesehen[inhalt]))
    koerper = struct.pack(">I", len(tags)) + b"".join(tabelle) + daten
    groesse = 128 + len(koerper)
    kopf = (struct.pack(">I", groesse) + b"\0\0\0\0" + struct.pack(">I", 0x02100000) + b"mntrRGB XYZ "
            + struct.pack(">6H", 2026, 1, 1, 0, 0, 0) + b"acsp" + b"\0" * 24 + struct.pack(">I", 0)
            + _s15(0.9642) + _s15(1.0) + _s15(0.8249) + b"\0" * 4 + b"\0" * 44)
    assert len(kopf) == 128
    return kopf + koerper
