"""Bericht als Excel-Mappe (.xlsx), ohne Zusatzbibliothek.

Erstes Blatt „Übersicht“ mit Titel, Kopf und Hinweisen, danach je Tabelle des Berichts ein Blatt mit fetter,
fixierter Kopfzeile und Filter. Texte stehen als Inline-Text in den Zellen, nie als Formel: Ein Zitat, das mit
„=“ beginnt, bleibt Text.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

from . import Absatz, Bericht, Kopf, Tabelle, Ueberschrift

_UNGUELTIG = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BLATT_VERBOTEN = re.compile(r"[\[\]:*?/\\]")
ZELLE_MAX = 32767  # mehr Zeichen nimmt Excel in einer Zelle nicht


def _x(text: str) -> str:
    return escape(_UNGUELTIG.sub("", text)[:ZELLE_MAX])


def _spalte(n: int) -> str:
    name = ""
    n += 1
    while n:
        n, rest = divmod(n - 1, 26)
        name = chr(65 + rest) + name
    return name


def _zelle(zeile: int, spalte: int, wert: str | int | float | None, stil: int = 1) -> str:
    ref = f"{_spalte(spalte)}{zeile}"
    if wert is None or wert == "":
        return f'<c r="{ref}" s="{stil}"/>'
    if isinstance(wert, bool):
        wert = "ja" if wert else "nein"
    if isinstance(wert, int | float):
        return f'<c r="{ref}" s="{stil}"><v>{wert}</v></c>'
    return f'<c r="{ref}" s="{stil}" t="inlineStr"><is><t xml:space="preserve">{_x(str(wert))}</t></is></c>'


def _blatt(spalten: list[str], zeilen: list[list], breiten: list[int], kopfzeile: bool = True) -> str:
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{b}" customWidth="1"/>' for i, b in enumerate(breiten))
    daten = []
    nr = 1
    if spalten:
        daten.append(f'<row r="1">{"".join(_zelle(1, i, s, 2) for i, s in enumerate(spalten))}</row>')
        nr = 2
    for z in zeilen:
        daten.append(f'<row r="{nr}">{"".join(_zelle(nr, i, w) for i, w in enumerate(z))}</row>')
        nr += 1
    ansicht = ('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
               'state="frozen"/></sheetView></sheetViews>' if spalten and kopfzeile else "")
    filter_ = (f'<autoFilter ref="A1:{_spalte(len(spalten) - 1)}{max(nr - 1, 1)}"/>'
               if spalten and kopfzeile and zeilen else "")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"{ansicht}{f'<cols>{cols}</cols>' if cols else ''}<sheetData>{''.join(daten)}</sheetData>{filter_}"
            "</worksheet>")


def _blattname(name: str, vergeben: set[str]) -> str:
    basis = _BLATT_VERBOTEN.sub(" ", name).strip("'")[:31] or "Blatt"
    kandidat, i = basis, 2
    while kandidat.lower() in vergeben:
        kandidat = f"{basis[:28]} {i}"
        i += 1
    vergeben.add(kandidat.lower())
    return kandidat


def _uebersicht(bericht: Bericht) -> Tabelle:
    zeilen: list[list] = [[bericht.titel, ""]]
    for b in bericht.bausteine:
        if isinstance(b, Kopf):
            zeilen += [[k, v] for k, v in b.zeilen]
        elif isinstance(b, Ueberschrift) and b.ebene == 1:
            zeilen.append(["", ""])
            zeilen.append([b.text, ""])
        elif isinstance(b, Absatz):
            zeilen.append(["", b.text])
    return Tabelle("Übersicht", [], zeilen, [28, 110])


_STILE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE7E6E6"/><bgColor indexed="64"/></patternFill></fill>'
    "</fills>"
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
    '<alignment vertical="top" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
    '<alignment vertical="top" wrapText="1"/></xf></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Standard" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)


def schreiben(bericht: Bericht) -> bytes:
    blaetter = [_uebersicht(bericht), *bericht.tabellen]
    vergeben: set[str] = set()
    namen = [_blattname(t.name, vergeben) for t in blaetter]
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                      'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                      for i in range(len(blaetter)))
            + "</Types>"))
        z.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>'))
        z.writestr("xl/workbook.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name="{_x(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(namen))
            + "</sheets></workbook>"))
        z.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i + 1}" '
                      'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                      f'Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(blaetter)))
            + '<Relationship Id="rIdStile" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"))
        z.writestr("xl/styles.xml", _STILE)
        for i, t in enumerate(blaetter):
            breiten = t.breiten or [20] * len(t.spalten)
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", _blatt(t.spalten, t.zeilen, breiten))
    return puffer.getvalue()
