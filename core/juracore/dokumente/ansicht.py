"""Ansicht des Originals: PDF-Seiten als Bild für die Oberfläche.

Die Oberfläche hat bewusst keine Dateirechte. Sie bekommt das Original deshalb nicht als Datei,
sondern Seite für Seite als PNG vom Kern, gerendert aus der unverändert abgelegten Kopie. Der
PNG-Kodierer kommt ohne Zusatzbibliothek aus (zlib aus der Standardbibliothek).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import sqlite3
import struct
import zlib
from pathlib import Path

log = logging.getLogger("juracore.dokumente")

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
    Bei Scans (Text per Texterkennung) kommen die Rechtecke aus den gespeicherten Wortpositionen der OCR.
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
                "markierungen": _markierungen_seite(con, dokument_id, seite, p, begriffe or [])}
    finally:
        pdf.close()


def _markierungen_seite(con: sqlite3.Connection, dokument_id: int, nr: int, seite, begriffe: list[str]) -> list[dict]:
    if not begriffe:
        return []
    zeile = con.execute("SELECT quelle, woerter FROM seite WHERE dokument_id = ? AND nr = ?",
                        (dokument_id, nr)).fetchone()
    if zeile is None or zeile["quelle"] != "ocr":
        return _markierungen(seite, begriffe)
    if zeile["woerter"] is not None:
        woerter = json.loads(zeile["woerter"])
    else:
        # Scan aus einer älteren Version ohne Wortpositionen: diese Seite einmal neu erkennen und merken.
        woerter = _woerter_nachtragen(con, dokument_id, nr, seite)
    return markierungen_aus_woertern(woerter or [], begriffe)


def _woerter_nachtragen(con: sqlite3.Connection, dokument_id: int, nr: int, seite) -> list[list] | None:
    from .lesen import _seitenbild
    from .ocr import OcrNichtVerfuegbar, Tesseract

    try:
        t = Tesseract.finden()
        t.pruefe_sprache()
        _, _, woerter = t.erkenne_mit_woertern(_seitenbild(seite))
    except (OcrNichtVerfuegbar, OSError) as fehler:
        log.warning("Wortpositionen für Seite %s nicht ermittelt: %s", nr, fehler)
        return None
    with con:
        con.execute("UPDATE seite SET woerter = ? WHERE dokument_id = ? AND nr = ?",
                    (json.dumps(woerter, ensure_ascii=False), dokument_id, nr))
    return woerter


def markierungen_aus_woertern(woerter: list[list], begriffe: list[str]) -> list[dict]:
    """Rechtecke der Begriffe aus den OCR-Wörtern ``[text, zeile, x, y, b, h]`` (Anteile der Seite).

    Die Wörter werden zu einem Text verbunden; eine Silbentrennung am Zeilenende ("Verzugs-" / "schaden") wird dabei
    aufgehoben, damit auch getrennte Wörter gefunden werden. Ein Fund kann so mehrere Wörter und Zeilen umfassen;
    je Zeile entsteht ein Rechteck. Innerhalb eines Worts wird die Lage nach dem Zeichenanteil geschätzt.
    """
    text = ""
    zuordnung: list[tuple[int, int]] = []  # je Zeichen: (Wort, Position im Wort)
    for i, (wort, zeile, *_lage) in enumerate(woerter):
        if i:
            vorher, vorher_zeile = woerter[i - 1][0], woerter[i - 1][1]
            if not (zeile != vorher_zeile and vorher.endswith("-") and len(vorher) > 1):
                text += " "
                zuordnung.append((-1, 0))
        naechstes_neue_zeile = i + 1 < len(woerter) and woerter[i + 1][1] != zeile
        sichtbar = wort[:-1] if naechstes_neue_zeile and wort.endswith("-") and len(wort) > 1 else wort
        text += sichtbar
        zuordnung += [(i, k) for k in range(len(sichtbar))]
    klein = _klein(text)

    rechtecke: list[dict] = []
    for begriff in dict.fromkeys(_klein(b.strip()) for b in begriffe if b.strip()):
        # Der Suchtext ist für "§" schon korrigiert, die Wörter der Texterkennung nicht ("8 256", "$ 280").
        muster = re.compile(re.escape(begriff).replace("§", "[§$8s]"))
        for fund in muster.finditer(klein):
            start, ende = fund.span()
            teile: dict[int, list[float]] = {}  # je Zeile: links, oben, rechts, unten
            for wi, k in zuordnung[start:ende]:
                if wi < 0:
                    continue
                wort, zeile, x, y, b, h = woerter[wi]
                zeichen = max(len(wort), 1)
                links, rechts = x + b * k / zeichen, x + b * (k + 1) / zeichen
                r = teile.setdefault(zeile, [links, y, rechts, y + h])
                r[0], r[1], r[2], r[3] = min(r[0], links), min(r[1], y), max(r[2], rechts), max(r[3], y + h)
            for links, oben, rechts, unten in teile.values():
                rechtecke.append({"x": round(links, 5), "y": round(oben, 5),
                                  "b": round(rechts - links, 5), "h": round(unten - oben, 5)})
    return sorted(rechtecke, key=lambda r: (r["y"], r["x"]))


def _klein(text: str) -> str:
    """Kleinschreibung Zeichen für Zeichen, ohne die Länge zu ändern (die Positionen müssen stimmen)."""
    return "".join(z.lower() if len(z.lower()) == 1 else z for z in text)


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
