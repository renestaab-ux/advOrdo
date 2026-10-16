"""Ansicht des Originals: PDF-Seiten als Bild für die Oberfläche.

Die Oberfläche hat bewusst keine Dateirechte. Sie bekommt das Original deshalb nicht als Datei,
sondern Seite für Seite als PNG vom Kern, gerendert aus der unverändert abgelegten Kopie. Der
PNG-Kodierer kommt ohne Zusatzbibliothek aus (zlib aus der Standardbibliothek).
"""

from __future__ import annotations

import base64
import sqlite3
import struct
import zlib
from pathlib import Path

MIN_BREITE = 200
MAX_BREITE = 2400


def png(breite: int, hoehe: int, pixel: bytes, schritt: int | None = None, kanaele: int = 3) -> bytes:
    """Kodiert ein RGB- bzw. RGBA-Bild (``kanaele`` Byte je Pixel, Zeilen mit ``schritt`` Byte Abstand) als PNG."""
    if kanaele not in (3, 4):
        raise ValueError(f"Nicht unterstütztes Bildformat mit {kanaele} Kanälen.")
    zeile = breite * kanaele
    schritt = schritt or zeile
    zeilen = b"".join(b"\x00" + pixel[y * schritt: y * schritt + zeile] for y in range(hoehe))

    def block(art: bytes, daten: bytes) -> bytes:
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)

    kopf = struct.pack(">IIBBBBB", breite, hoehe, 8, 2 if kanaele == 3 else 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + block(b"IHDR", kopf) + block(b"IDAT", zlib.compress(zeilen, 6)) + block(b"IEND", b"")


def seitenbild(
    con: sqlite3.Connection, dokument_id: int, seite: int, breite: int = 1000, begriffe: list[str] | None = None
) -> dict:
    """Rendert Seite ``seite`` (ab 1) des abgelegten Originals in der gewünschten Breite (Pixel).

    ``begriffe`` (z. B. die Treffer der Volltextsuche) werden auf der Seite gesucht; ``markierungen`` enthält ihre
    Rechtecke als Anteile von Breite und Höhe der Seite (0 bis 1), damit die Oberfläche sie über das Bild legen kann.
    """
    import pypdfium2 as pdfium

    zeile = con.execute("SELECT format, original, dateiname FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if zeile is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    if zeile["format"] != "pdf":
        raise ValueError(f"{zeile['dateiname']} ist kein PDF; das Original lässt sich nur bei PDF-Dateien anzeigen.")
    pfad = Path(zeile["original"])
    if not pfad.is_file():
        raise FileNotFoundError(f"Die abgelegte Kopie von {zeile['dateiname']} fehlt: {pfad}")
    breite = max(MIN_BREITE, min(int(breite), MAX_BREITE))
    pdf = pdfium.PdfDocument(pfad)
    try:
        seiten = len(pdf)
        if not 1 <= seite <= seiten:
            raise ValueError(f"{zeile['dateiname']} hat {seiten} Seiten, nicht Seite {seite}.")
        p = pdf[seite - 1]
        # Knapp unter dem Ziel skalieren: PDFium rundet die Pixelbreite auf.
        bild = p.render(scale=(breite - 0.5) / p.get_width(), rev_byteorder=True)
        daten = png(bild.width, bild.height, bytes(bild.buffer), bild.stride, bild.n_channels)
        return {"seite": seite, "seiten": seiten, "breite": bild.width, "hoehe": bild.height,
                "bild": "data:image/png;base64," + base64.b64encode(daten).decode("ascii"),
                "markierungen": _markierungen(p, begriffe or [])}
    finally:
        pdf.close()


def _markierungen(seite, begriffe: list[str]) -> list[dict]:
    """Rechtecke aller Vorkommen der Begriffe auf der Seite, oben links beginnend, als Anteile der Seitengröße."""
    if not begriffe:
        return []
    breite, hoehe = seite.get_size()
    textseite = seite.get_textpage()
    rechtecke: list[dict] = []
    try:
        for begriff in dict.fromkeys(b.strip() for b in begriffe if b.strip()):
            suche = textseite.search(begriff, match_case=False)
            while (fund := suche.get_next()) is not None:
                for i in range(textseite.count_rects(*fund)):
                    links, unten, rechts, oben = textseite.get_rect(i)
                    rechtecke.append({
                        "x": round(links / breite, 5), "y": round((hoehe - oben) / hoehe, 5),
                        "b": round((rechts - links) / breite, 5), "h": round((oben - unten) / hoehe, 5),
                    })
    finally:
        textseite.close()
    return sorted(rechtecke, key=lambda r: (r["y"], r["x"]))
