"""Bericht als Word-Datei (.docx, Office Open XML), ohne Zusatzbibliothek.

Nur, was der Bericht braucht: Formatvorlagen für Titel, Überschriften, Belege und Zitate, eine Tabelle für den
Kopf und eine Fußzeile mit Seitenzahl. Die Formatvorlagen tragen deutsche Namen und lassen sich in Word ändern.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

from . import Absatz, Bericht, Eintrag, Kopf, Ueberschrift
from .pdf import nummernspalte as _nummernspalte

_UNGUELTIG = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _x(text: str) -> str:
    return escape(_UNGUELTIG.sub("", text))


def _lauf(text: str, fett: bool = False, kursiv: bool = False, grau: bool = False, rot: bool = False) -> str:
    eigenschaften = ("<w:b/>" if fett else "") + ("<w:i/>" if kursiv else "") + (
        '<w:color w:val="595959"/>' if grau else '<w:color w:val="B31A1A"/>' if rot else "")
    rpr = f"<w:rPr>{eigenschaften}</w:rPr>" if eigenschaften else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{_x(text)}</w:t></w:r>'


def _absatz(laeufe: str, stil: str | None = None, zusammen: bool = False, einzug: int = 0,
            haengend: bool = False) -> str:
    """``einzug`` (Twips) überschreibt die Einrückung der Formatvorlage; ``haengend``: erste Zeile beginnt links,
    ein Tabulator führt zur Einrückung (Nummernspalte)."""
    ppr = (f'<w:pStyle w:val="{stil}"/>' if stil else "") + ("<w:keepNext/>" if zusammen else "")
    if einzug and haengend:
        ppr += f'<w:tabs><w:tab w:val="left" w:pos="{einzug}"/></w:tabs><w:ind w:left="{einzug}" w:hanging="{einzug}"/>'
    elif einzug:
        ppr += f'<w:ind w:left="{einzug}"/>'
    return f"<w:p>{f'<w:pPr>{ppr}</w:pPr>' if ppr else ''}{laeufe}</w:p>"


def _kopf(k: Kopf) -> str:
    zeilen = "".join(
        f'<w:tr><w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>{_absatz(_lauf(name, fett=True), "Kopf")}'
        f'</w:tc><w:tc><w:tcPr><w:tcW w:w="6600" w:type="dxa"/></w:tcPr>{_absatz(_lauf(wert), "Kopf")}</w:tc></w:tr>'
        for name, wert in k.zeilen)
    return (f'<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/><w:tblLook w:val="0000"/></w:tblPr>'
            f'<w:tblGrid><w:gridCol w:w="2400"/><w:gridCol w:w="6600"/></w:tblGrid>{zeilen}</w:tbl>'
            + _absatz(""))


def _eintrag(e: Eintrag, nummernspalte: int = 0) -> str:
    """``nummernspalte`` (Twips): kompakte Einträge mit Nummer in eigener Spalte, Zeilen bündig unter dem Titel."""
    teile = []
    spalte_ = nummernspalte if e.kompakt else 0
    if spalte_:
        titel = (_lauf(e.nummer, fett=True) if e.nummer else "") + "<w:r><w:tab/></w:r>"
    else:
        titel = _lauf(f"{e.nummer} ", fett=True) if e.nummer else ""
    titel += _lauf(e.titel, fett=not e.kompakt or e.dringend, rot=e.dringend)
    if e.marken:
        titel += _lauf(f"  [{', '.join(e.marken)}]", fett=e.dringend, grau=not e.dringend, rot=e.dringend)
    teile.append(_absatz(titel, "Eintrag" if e.kompakt else "Ueberschrift3", zusammen=bool(e.zeilen or e.belege),
                         einzug=spalte_, haengend=True))
    for z in e.zeilen:
        teile.append(_absatz(_lauf(z), "Einschaetzung", zusammen=bool(e.belege), einzug=spalte_))
    for i, b in enumerate(e.belege):
        laeufe = (_lauf(f"{b.vorab} – ") if b.vorab else "") + _lauf(b.ort, fett=True)
        if b.angenaehert:
            laeufe += _lauf(" (Zitat angenähert)", grau=True)
        if b.zitat:
            laeufe += _lauf(": ") + _lauf(f"„{b.zitat}“", kursiv=True)
        teile.append(_absatz(laeufe, "Beleg", zusammen=i < len(e.belege) - 1, einzug=spalte_ + 284 if spalte_ else 0))
    return "".join(teile)


def _koerper(bericht: Bericht) -> str:
    teile = [_absatz(_lauf(bericht.titel), "Titel")]
    nummernspalte = round(_nummernspalte(bericht) * 20)
    for b in bericht.bausteine:
        if isinstance(b, Kopf):
            teile.append(_kopf(b))
        elif isinstance(b, Ueberschrift):
            teile.append(_absatz(_lauf(b.text), f"Ueberschrift{b.ebene}", zusammen=True))
        elif isinstance(b, Absatz):
            teile.append(_absatz(_lauf(b.text), "Hinweis" if b.leise else None))
        elif isinstance(b, Eintrag):
            teile.append(_eintrag(b, nummernspalte))
    return "".join(teile)


_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _dokument(bericht: Bericht) -> str:
    # A4, Ränder 2,5 cm; Fußzeile aus footer1.xml.
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS}><w:body>'
            f"{_koerper(bericht)}"
            '<w:sectPr><w:footerReference w:type="default" r:id="rIdFuss"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418" w:header="709" w:footer="709" '
            'w:gutter="0"/></w:sectPr></w:body></w:document>')


def _fusszeile(bericht: Bericht) -> str:
    feld = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> {} </w:instrText>'
            '</w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {_NS}>'
            f'<w:p><w:pPr><w:pStyle w:val="Fusszeile"/></w:pPr>{_lauf(bericht.titel + " · Seite ")}'
            f'{feld.format("PAGE")}{_lauf(" von ")}{feld.format("NUMPAGES")}</w:p></w:ftr>')


def _stil(stil_id: str, name: str, groesse: int, fett: bool = False, kursiv: bool = False, grau: bool = False,
          vor: int = 0, nach: int = 80, einzug: int = 0, gliederung: int | None = None) -> str:
    rpr = ("<w:b/>" if fett else "") + ("<w:i/>" if kursiv else "") + (
        '<w:color w:val="595959"/>' if grau else "") + f'<w:sz w:val="{groesse}"/>'
    ppr = f'<w:spacing w:before="{vor}" w:after="{nach}"/>' + (f'<w:ind w:left="{einzug}"/>' if einzug else "") + (
        f'<w:outlineLvl w:val="{gliederung}"/>' if gliederung is not None else "")
    return (f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{stil_id}"><w:name w:val="{name}"/>'
            f'<w:basedOn w:val="Standard"/><w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


STILE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial" w:eastAsia="Arial"/>'
    '<w:sz w:val="21"/><w:lang w:val="de-DE"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
    "</w:docDefaults>"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Standard"><w:name w:val="Normal"/><w:qFormat/></w:style>'
    + _stil("Titel", "Title", 32, fett=True, nach=160)
    + _stil("Ueberschrift1", "heading 1", 26, fett=True, vor=320, nach=80, gliederung=0)
    + _stil("Ueberschrift2", "heading 2", 23, fett=True, vor=240, nach=60, gliederung=1)
    + _stil("Ueberschrift3", "heading 3", 21, fett=True, vor=180, nach=40, gliederung=2)
    + _stil("Kopf", "Berichtskopf", 20, nach=0)
    + _stil("Hinweis", "Hinweis", 18, grau=True)
    + _stil("Eintrag", "Eintrag", 21, vor=100, nach=20)
    + _stil("Einschaetzung", "Einschätzung", 20, einzug=284, nach=20)
    + _stil("Beleg", "Beleg", 18, einzug=567, nach=20)
    + _stil("Fusszeile", "Fußzeile Bericht", 16, grau=True, nach=0)
    + "</w:styles>"
)

_TYPEN = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/footer1.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    "</Types>"
)

_PAKET_BEZUEGE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    '<Relationship Id="rId2" '
    'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
    'Target="docProps/core.xml"/>'
    "</Relationships>"
)

_DOKUMENT_BEZUEGE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rIdStile" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/>'
    '<Relationship Id="rIdFuss" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
    'Target="footer1.xml"/>'
    "</Relationships>"
)


def _eigenschaften(bericht: Bericht) -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{_x(bericht.titel)}</dc:title><dc:creator>advOrdo</dc:creator><dc:language>de-DE</dc:language>"
            "</cp:coreProperties>")


def schreiben(bericht: Bericht) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TYPEN)
        z.writestr("_rels/.rels", _PAKET_BEZUEGE)
        z.writestr("docProps/core.xml", _eigenschaften(bericht))
        z.writestr("word/_rels/document.xml.rels", _DOKUMENT_BEZUEGE)
        z.writestr("word/document.xml", _dokument(bericht))
        z.writestr("word/styles.xml", STILE)
        z.writestr("word/footer1.xml", _fusszeile(bericht))
    return puffer.getvalue()
