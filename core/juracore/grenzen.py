"""Größengrenzen für Daten von außen: Antworten aus dem Netz und entpackte Teile von ZIP-Dateien.

Eine fehlerhafte oder böswillige Quelle (ein endloser Download, eine „ZIP-Bombe“ in einer
Word-Datei der Gegenseite) soll den Kern nicht mit vollem Arbeitsspeicher lahmlegen. Die
Grenzen liegen weit über allem, was die Rechtsquellen und übliche Dokumente brauchen.
"""

from __future__ import annotations

import zipfile

MB = 1024 * 1024
GROESSTE_ANTWORT = 512 * MB  # eine Antwort aus dem Netz
GROESSTER_ZIPTEIL = 512 * MB  # ein entpackter Teil einer ZIP-Datei (auch DOCX)


class ZuGross(ValueError):
    """Daten überschreiten eine Grenze."""


def _text(groesse: int) -> str:
    return f"{groesse // MB} MB"


def entpacke(z: zipfile.ZipFile, name: str | zipfile.ZipInfo, grenze: int = GROESSTER_ZIPTEIL) -> bytes:
    """Liest einen Teil einer ZIP-Datei, höchstens ``grenze`` Bytes. Die Größe im Verzeichnis der ZIP-Datei wird
    vorab geprüft, die tatsächlich entpackte Menge beim Lesen (das Verzeichnis kann falsche Angaben enthalten)."""
    info = name if isinstance(name, zipfile.ZipInfo) else z.getinfo(name)
    if info.file_size > grenze:
        raise ZuGross(f"{info.filename} ist entpackt größer als {_text(grenze)} und wird nicht gelesen.")
    with z.open(info) as datei:
        daten = datei.read(grenze + 1)
    if len(daten) > grenze:
        raise ZuGross(f"{info.filename} ist entpackt größer als {_text(grenze)} und wird nicht gelesen.")
    return daten


def begrenze(antwort, grenze: int = GROESSTE_ANTWORT):
    """Lässt ``antwort.read()`` höchstens ``grenze`` Bytes liefern und bricht sonst mit ZuGross ab."""
    laenge = (getattr(antwort, "headers", None) or {}).get("Content-Length")
    if laenge and str(laenge).strip().isdigit() and int(laenge) > grenze:
        antwort.close()
        raise ZuGross(f"Die Antwort von {getattr(antwort, 'url', 'der Quelle')} ist größer als {_text(grenze)}.")
    lies = antwort.read
    gelesen = 0

    def zaehle(daten: bytes) -> bytes:
        nonlocal gelesen
        gelesen += len(daten)
        if gelesen > grenze:
            antwort.close()
            raise ZuGross(f"Die Antwort von {getattr(antwort, 'url', 'der Quelle')} ist größer als {_text(grenze)}.")
        return daten

    def read(amt: int | None = None) -> bytes:
        if amt is not None and amt >= 0:
            return zaehle(lies(amt))
        teile = []
        while teil := lies(MB):
            teile.append(zaehle(teil))
        return b"".join(teile)

    antwort.read = read
    return antwort
