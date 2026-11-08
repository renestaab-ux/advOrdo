"""Kopie des Original-PDFs mit den Markierungen als PDF-Anmerkungen, zum Weitergeben.

Das Original in der Ablage bleibt unverändert; geschrieben wird immer eine neue Datei. Jede Markierung wird zu einer
echten PDF-Markierung (Hervorhebung, Unterstreichung oder Durchstreichung in ihrer Farbe), ein Kommentar zu deren
Notiz. So zeigen Acrobat, Vorschau, Browser und andere PDF-Programme sie an, und der Empfänger kann sie dort lesen,
ändern oder löschen. Stellen, die im Seitenbild nicht zu finden sind (Wortlaut nicht mehr im Text, abweichende
Texterkennung), werden gezählt und genannt, aber nicht geraten.
"""

from __future__ import annotations

import ctypes
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from . import anmerkungen

# Kräftiger als in der App: PDF-Programme legen Hervorhebungen multiplizierend über den Text.
FARBEN_RGB = {"gelb": (255, 226, 0), "gruen": (110, 205, 90), "blau": (90, 160, 255), "rot": (255, 105, 95)}
_DRUCKEN = 4  # Anmerkungs-Flag „Print“: erscheint auch im Ausdruck


def _wtext(text: str):
    import pypdfium2.raw as raw

    daten = text.encode("utf-16-le") + b"\0\0"
    puffer = ctypes.create_string_buffer(daten, len(daten))
    return puffer, ctypes.cast(puffer, ctypes.POINTER(raw.FPDF_WCHAR))


def _pdf_punkt(fx: float, fy: float, breite: float, hoehe: float, drehung: int) -> tuple[float, float]:
    """Anteil der angezeigten Seite (oben links 0/0) → Punkt im PDF (unten links 0/0, ohne Drehung)."""
    if drehung == 90:
        return fy * breite, fx * hoehe
    if drehung == 180:
        return breite - fx * breite, fy * hoehe
    if drehung == 270:
        return breite - fy * breite, hoehe - fx * hoehe
    return fx * breite, hoehe - fy * hoehe


def _kommentar(a: dict, bedeutungen: dict[str, str]) -> str:
    """Notiz der PDF-Markierung: Bedeutung, dann der Kommentar (Markdown-Zeichen für Fett entfernt)."""
    teile = [bedeutungen.get(a["farbe"], a["farbe"])]
    if a.get("kommentar"):
        teile.append(re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), a["kommentar"]).strip())
    return "\n\n".join(teile)


def _markieren(seite, rechtecke: list[dict], farbe: str, stil: str, notiz: str | None, titel: str,
               breite: float, hoehe: float, drehung: int) -> None:
    import pypdfium2.raw as raw

    art = {"unterstrichen": raw.FPDF_ANNOT_UNDERLINE, "durchgestrichen": raw.FPDF_ANNOT_STRIKEOUT}.get(
        stil, raw.FPDF_ANNOT_HIGHLIGHT)
    annot = raw.FPDFPage_CreateAnnot(seite, art)
    if not annot:
        raise RuntimeError("PDFium konnte keine Markierung anlegen.")
    try:
        xs, ys = [], []
        for r in rechtecke:
            links, oben, rechts, unten = r["x"], r["y"], r["x"] + r["b"], r["y"] + r["h"]
            ecken = [_pdf_punkt(fx, fy, breite, hoehe, drehung) for fx, fy in (
                (links, oben), (rechts, oben), (links, unten), (rechts, unten))]
            # Reihenfolge der Ecken wie in der PDF-Norm: oben links, oben rechts, unten links, unten rechts
            punkte = [c for e in ecken for c in e]
            raw.FPDFAnnot_AppendAttachmentPoints(annot, raw.FS_QUADPOINTSF(*punkte))
            xs += punkte[0::2]
            ys += punkte[1::2]
        raw.FPDFAnnot_SetRect(annot, raw.FS_RECTF(min(xs), max(ys), max(xs), min(ys)))
        raw.FPDFAnnot_SetColor(annot, raw.FPDFANNOT_COLORTYPE_Color, *FARBEN_RGB.get(farbe, FARBEN_RGB["gelb"]), 255)
        raw.FPDFAnnot_SetFlags(annot, _DRUCKEN)
        for schluessel, wert in (("T", titel), ("Contents", notiz)):
            if wert:
                _puffer, zeiger = _wtext(wert)
                raw.FPDFAnnot_SetStringValue(annot, schluessel.encode(), zeiger)
    finally:
        raw.FPDFPage_CloseAnnot(annot)


def schreiben(con: sqlite3.Connection, dokument_id: int, pfad: str | Path, ids: list[int] | None = None,
              titel: str = "advOrdo") -> dict:
    """Schreibt die Kopie nach ``pfad``; ``ids`` = nur diese Markierungen (sonst alle des Dokuments)."""
    import pypdfium2 as pdfium

    d = con.execute("SELECT id, format, original, dateiname FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if d is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    if d["format"] != "pdf" or not d["original"]:
        raise ValueError(f"„{d['dateiname']}“ ist kein PDF; Markierungen lassen sich nur in ein PDF einzeichnen.")
    ziel = Path(pfad)
    if ziel.suffix.lower() != ".pdf":
        ziel = ziel.with_name(ziel.name + ".pdf")
    if ziel.resolve() == Path(d["original"]).resolve():
        raise ValueError("Das Original in der Ablage wird nicht überschrieben. Bitte einen anderen Speicherort wählen.")
    alle = [a for a in anmerkungen.liste(con, dokument_id=dokument_id) if a["art"] == "markierung"]
    gewuenscht = {a["id"] for a in alle} if ids is None else set(ids) & {a["id"] for a in alle}
    if ids is not None and len(gewuenscht) != len(set(ids)):
        raise LookupError("Eine der Markierungen gehört nicht zu diesem Dokument.")
    bedeutungen = anmerkungen.bedeutungen(con)
    eingezeichnet: set[int] = set()
    pdf = pdfium.PdfDocument(d["original"])
    try:
        for nr in range(1, len(pdf) + 1):
            auf_der_seite = [m for m in anmerkungen.auf_seite(con, dokument_id, nr) if m["id"] in gewuenscht]
            if not auf_der_seite:
                continue
            seite = pdf[nr - 1]
            drehung = seite.get_rotation()
            breite, hoehe = seite.get_size()
            if drehung in (90, 270):
                breite, hoehe = hoehe, breite  # ungedrehte Maße der Seite
            for m in auf_der_seite:
                # Läuft eine Markierung über zwei Seiten, trägt nur der erste Teil die Notiz.
                notiz = None if m["id"] in eingezeichnet else _kommentar(m, bedeutungen)
                _markieren(seite, m["rechtecke"], m["farbe"], m["stil"], notiz, titel, breite, hoehe, drehung)
                eingezeichnet.add(m["id"])
        ziel.parent.mkdir(parents=True, exist_ok=True)
        pdf.save(ziel)
    finally:
        pdf.close()
    fehlend = [{"id": a["id"], "zitat": a["zitat"], "seite": a["seite"],
                "grund": "nicht mehr im Text" if a["status"] == "nicht_gefunden" else "im Seitenbild nicht gefunden"}
               for a in alle if a["id"] in gewuenscht and a["id"] not in eingezeichnet]
    return {"pfad": str(ziel), "eingezeichnet": len(eingezeichnet), "fehlend": fehlend}


def dateiname(con: sqlite3.Connection, dokument_id: int) -> str:
    """Vorschlag ohne Endung: „05_Klageschrift (markiert 2026-10-31)“."""
    z = con.execute("SELECT dateiname FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if z is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    return f"{Path(z['dateiname']).stem} (markiert {datetime.now():%Y-%m-%d})"


def _frei(ordner: Path, name: str) -> Path:
    """Freier Dateiname im Ordner; vorhandene Dateien werden nie überschrieben."""
    ziel = ordner / f"{name}.pdf"
    n = 2
    while ziel.exists():
        ziel = ordner / f"{name} ({n}).pdf"
        n += 1
    return ziel


def akte_schreiben(con: sqlite3.Connection, akte_id: int, ordner: str | Path, ids: list[int] | None = None,
                   titel: str = "advOrdo") -> dict:
    """Je PDF der Akte mit (ausgewählten) Markierungen eine Kopie im Ordner; andere Formate werden genannt."""
    zeilen = con.execute(
        """SELECT DISTINCT d.id, d.format, d.dateiname FROM anmerkung a JOIN dokument d ON d.id = a.dokument_id
           WHERE d.akte_id = ? AND a.art = 'markierung' ORDER BY d.datum, d.id""", (akte_id,)).fetchall()
    wahl = None if ids is None else set(ids)
    if wahl is not None:
        bekannt = {z[0] for z in con.execute(
            "SELECT a.id FROM anmerkung a JOIN dokument d ON d.id = a.dokument_id WHERE d.akte_id = ?", (akte_id,))}
        if not wahl <= bekannt:
            raise LookupError("Eine der Markierungen gehört nicht zu dieser Akte.")
    ziel = Path(ordner)
    if not ziel.is_dir():
        raise ValueError(f"Den Ordner {ziel} gibt es nicht.")
    dateien, kein_pdf, fehlend = [], [], []
    for d in zeilen:
        eigene = [z[0] for z in con.execute(
            "SELECT id FROM anmerkung WHERE dokument_id = ? AND art = 'markierung'", (d["id"],))]
        auswahl = eigene if wahl is None else [i for i in eigene if i in wahl]
        if not auswahl:
            continue
        if d["format"] != "pdf":
            kein_pdf.append(d["dateiname"])
            continue
        r = schreiben(con, d["id"], _frei(ziel, dateiname(con, d["id"])), auswahl, titel)
        dateien.append({"dokument": d["dateiname"], "pfad": r["pfad"], "eingezeichnet": r["eingezeichnet"]})
        fehlend += [f | {"dokument": d["dateiname"]} for f in r["fehlend"]]
    if not dateien and not kein_pdf:
        raise ValueError("Es ist keine Markierung ausgewählt.")
    return {"ordner": str(ziel), "dateien": dateien, "kein_pdf": kein_pdf, "fehlend": fehlend}
