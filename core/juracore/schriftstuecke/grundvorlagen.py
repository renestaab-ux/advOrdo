"""Mitgelieferte Vorlagen: Brief und Schriftsatz (mit vollem oder kurzem Rubrum) als Word-Datei mit Platzhaltern.

Die Vorlagen entstehen bei jedem Aufruf neu, damit das Logo der Arbeitsumgebung im Kopf steht, und werden dann wie
eine eigene Vorlage gefüllt. Gespeichert (``Grundvorlage speichern``) taugen sie als Ausgangspunkt für eigene
Vorlagen.

Seite nach DIN 5008 (Form B): A4, Rand links 25 mm, rechts 20 mm; das Anschriftfeld (85 × 45 mm) beginnt 45 mm
unter der Blattoberkante und 25 mm vom linken Rand, die Absenderangabe steht in seiner ersten Zeile. Rechts daneben
der Informationsblock mit Zeichen, Bearbeiter und Datum.
"""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

GRUNDVORLAGEN = {
    "brief": {"titel": "Brief", "beschreibung": "Anwaltsschreiben mit Briefkopf, Anschrift, Betreff und Anrede",
              "art": "brief"},
    "schriftsatz": {"titel": "Schriftsatz mit Rubrum",
                    "beschreibung": "An das Gericht, mit vollständigem Rubrum, z. B. Klage oder Klageerwiderung",
                    "art": "schriftsatz"},
    "kurzrubrum": {"titel": "Schriftsatz mit Kurzrubrum",
                   "beschreibung": "An das Gericht im laufenden Verfahren: Parteien kurz und Aktenzeichen",
                   "art": "schriftsatz"},
}

# Maße in twips (1/20 pt; 1 mm ≈ 56,7 twips) bzw. EMU für Bilder (1 mm = 36 000 EMU).
_MM = 56.7
_RAND_LINKS, _RAND_RECHTS, _RAND_OBEN, _RAND_UNTEN = 1418, 1134, 1531, 1418  # 25, 20, 27, 25 mm
_SATZBREITE = 11906 - _RAND_LINKS - _RAND_RECHTS  # 165 mm
_ANSCHRIFT_BREITE = round(85 * _MM)
_INFO_BREITE = _SATZBREITE - _ANSCHRIFT_BREITE
_LOGO_BREITE, _LOGO_HOEHE = 50 * 36000, 15 * 36000

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')


# --------------------------------------------------------------------------- Bausteine


def _lauf(text: str, fett: bool = False, markiert: bool = False) -> str:
    rpr = ("<w:b/>" if fett else "") + ('<w:highlight w:val="yellow"/>' if markiert else "")
    rpr = f"<w:rPr>{rpr}</w:rPr>" if rpr else ""
    teile = text.split("\t")
    return "<w:r>" + rpr + '<w:tab/>'.join(f'<w:t xml:space="preserve">{escape(t)}</w:t>' for t in teile) + "</w:r>"


def _p(*laeufe: str, stil: str | None = None, zentriert: bool = False, rechts: bool = False) -> str:
    ppr = (f'<w:pStyle w:val="{stil}"/>' if stil else "") + (
        '<w:jc w:val="center"/>' if zentriert else '<w:jc w:val="right"/>' if rechts else "")
    return f"<w:p>{f'<w:pPr>{ppr}</w:pPr>' if ppr else ''}{''.join(laeufe)}</w:p>"


def _text(text: str, stil: str | None = None, fett: bool = False, **kw) -> str:
    return _p(_lauf(text, fett=fett), stil=stil, **kw)


def _ausfuellen(text: str, **kw) -> str:
    """Gelb markierter Hinweis, was hier zu schreiben ist."""
    return _p(_lauf(text, markiert=True), **kw)


def _zelle(breite: int, inhalt: str) -> str:
    return f'<w:tc><w:tcPr><w:tcW w:w="{breite}" w:type="dxa"/></w:tcPr>{inhalt or _p()}</w:tc>'


def _anschriftfeld(empfaenger: str, info: list[tuple[str, str]]) -> str:
    """Abstand bis 45 mm, dann Anschriftfeld und Informationsblock nebeneinander, 45 mm hoch."""
    abstand = '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="1020" w:lineRule="exact"/></w:pPr></w:p>'
    links = _text("{{Absender.Zeile}}", "Absenderzeile") + _text("", "Anschrift") + _text(empfaenger, "Anschrift")
    rechts = "".join(_p(_lauf(f"{name}\t", fett=False), _lauf(wert), stil="Info") for name, wert in info)
    return (abstand + '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="113" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:val="0000"/></w:tblPr>'
            f'<w:tblGrid><w:gridCol w:w="{_ANSCHRIFT_BREITE}"/><w:gridCol w:w="{_INFO_BREITE}"/></w:tblGrid>'
            '<w:tr><w:trPr><w:trHeight w:val="2552" w:hRule="exact"/></w:trPr>'
            f"{_zelle(_ANSCHRIFT_BREITE, links)}{_zelle(_INFO_BREITE, rechts)}</w:tr></w:tbl>")


_INFO_BRIEF = [("Unser Zeichen", "{{Akte.Aktenzeichen}}"), ("Ihr Zeichen", "{{Empfänger.Zeichen}}"),
               ("Bearbeiter", "{{Bearbeiter.Name}}"), ("Telefon", "{{Bearbeiter.Telefon}}"),
               ("E-Mail", "{{Bearbeiter.E-Mail}}"), ("", ""), ("Datum", "{{Datum}}")]
_INFO_GERICHT = [("Unser Zeichen", "{{Akte.Aktenzeichen}}"), ("Bearbeiter", "{{Bearbeiter.Name}}"),
                 ("Telefon", "{{Bearbeiter.Telefon}}"), ("E-Mail", "{{Bearbeiter.E-Mail}}"), ("", ""),
                 ("Datum", "{{Datum}}")]


def _unterschrift(gruss: bool) -> str:
    return ((_text("Mit freundlichen Grüßen") if gruss else "") + _text("") + _text("") +
            _text("{{Bearbeiter.Name}}") + _text("{{Bearbeiter.Berufsbezeichnung}}"))


def _koerper(art: str) -> str:
    if art == "brief":
        return (_anschriftfeld("{{Empfänger.Anschrift}}", _INFO_BRIEF)
                + _text("{{Akte.Bezeichnung}}", "Betreff", fett=True)
                + _text("{{Akte.Gegenstand}}", "Betreff")
                + _text("") + _text("{{Empfänger.Anrede}}")
                + _ausfuellen("[Text des Schreibens]")
                + _text("") + _unterschrift(gruss=True))
    if art == "schriftsatz":
        return (_anschriftfeld("{{Gericht.Anschrift}}", _INFO_GERICHT)
                + _text("Az.: {{Gericht.Aktenzeichen}}", "Betreff", fett=True)
                + _text("")
                + _text("{{Rubrum}}", "Rubrum")
                + _text("")
                + _ausfuellen("[Bezeichnung, z. B. Klageerwiderung]", stil="Titelzeile", zentriert=True)
                + _ausfuellen("[Anträge bzw. Anzeige der Vertretung]")
                + _text("Begründung:", "Zwischen", fett=True)
                + _ausfuellen("[Text des Schriftsatzes]")
                + _text("") + _unterschrift(gruss=False))
    if art == "kurzrubrum":
        return (_anschriftfeld("{{Gericht.Anschrift}}", _INFO_GERICHT)
                + _text("In dem Rechtsstreit", "Betreff")
                + _text("{{Rubrum.Kurz}}", "Betreff", fett=True)
                + _text("Az.: {{Gericht.Aktenzeichen}}", "Betreff")
                + _text("")
                + _ausfuellen("[Text des Schriftsatzes]")
                + _text("") + _unterschrift(gruss=False))
    raise ValueError(f"Unbekannte Grundvorlage: {art!r}")


# --------------------------------------------------------------------------- Logo


def bildgroesse(daten: bytes) -> tuple[int, int] | None:
    """Breite und Höhe in Pixeln eines PNG oder JPEG, sonst None."""
    if daten[:8] == b"\x89PNG\r\n\x1a\n" and len(daten) >= 24:
        return struct.unpack(">II", daten[16:24])
    if daten[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(daten):
            if daten[i] != 0xFF:
                i += 1
                continue
            marke = daten[i + 1]
            if marke in (0xD8, 0x01) or 0xD0 <= marke <= 0xD7:
                i += 2
                continue
            laenge = struct.unpack(">H", daten[i + 2:i + 4])[0]
            if marke in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                hoehe, breite = struct.unpack(">HH", daten[i + 5:i + 9])
                return breite, hoehe
            i += 2 + laenge
    return None


def _logo_lauf(breite_px: int, hoehe_px: int, dateiname: str) -> str:
    faktor = min(_LOGO_BREITE / breite_px, _LOGO_HOEHE / hoehe_px)
    cx, cy = round(breite_px * faktor), round(hoehe_px * faktor)
    return ('<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="1" name="Logo"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
            f'<pic:nvPicPr><pic:cNvPr id="0" name="{escape(dateiname)}"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="rIdLogo"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            "</wp:inline></w:drawing></w:r>")


# --------------------------------------------------------------------------- Kopf, Fuß, Stile, Paket


def _kopfzeile(logo: str) -> str:
    """Name des Absenders links, Logo rechts."""
    breite_links = _SATZBREITE - 2900
    links = _text("{{Absender.Name}}", "Briefkopf", fett=True) + _text("{{Absender.Abteilung}}", "Briefkopf")
    rechts = _p(logo, rechts=True) if logo else _p()
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {_NS}>'
            '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:val="0000"/></w:tblPr>'
            f'<w:tblGrid><w:gridCol w:w="{breite_links}"/><w:gridCol w:w="2900"/></w:tblGrid>'
            f"<w:tr>{_zelle(breite_links, links)}{_zelle(2900, rechts)}</w:tr></w:tbl>"
            '<w:p><w:pPr><w:pStyle w:val="Briefkopf"/></w:pPr></w:p></w:hdr>')


def _fusszeile() -> str:
    feld = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> {} </w:instrText>'
            '</w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {_NS}>'
            + _text("{{Absender.Zeile}}", "Fusszeile")
            + _text("{{Absender.Kontakt}}", "Fusszeile")
            + _text("{{Absender.Register}}", "Fusszeile")
            + _text("{{Absender.Berufsträger}}", "Fusszeile")
            + f'<w:p><w:pPr><w:pStyle w:val="Fusszeile"/><w:jc w:val="right"/></w:pPr>{_lauf("Seite ")}'
              f'{feld.format("PAGE")}{_lauf(" von ")}{feld.format("NUMPAGES")}</w:p></w:ftr>')


def _stil(stil_id: str, name: str, groesse: int, vor: int = 0, nach: int = 0, fett: bool = False,
          tab: int | None = None, unterstrichen: bool = False, zusammen: bool = False) -> str:
    rpr = ("<w:b/>" if fett else "") + ('<w:u w:val="single"/>' if unterstrichen else "") + f'<w:sz w:val="{groesse}"/>'
    ppr = (f'<w:tabs><w:tab w:val="{"right" if stil_id == "Rubrum" else "left"}" w:pos="{tab}"/></w:tabs>'
           if tab else "") + ("<w:keepNext/>" if zusammen else "") + f'<w:spacing w:before="{vor}" w:after="{nach}"/>'
    return (f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{stil_id}"><w:name w:val="{name}"/>'
            f'<w:basedOn w:val="Standard"/><w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


STILE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial" w:eastAsia="Arial"/>'
    '<w:sz w:val="22"/><w:lang w:val="de-DE"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
    "</w:docDefaults>"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Standard"><w:name w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:spacing w:after="120"/></w:pPr></w:style>'
    + _stil("Briefkopf", "Briefkopf", 24)
    + _stil("Absenderzeile", "Absenderzeile", 14, unterstrichen=True)
    + _stil("Anschrift", "Anschriftfeld", 22)
    + _stil("Info", "Informationsblock", 17, tab=1500)
    + _stil("Betreff", "Betreff", 22, nach=0)
    + _stil("Rubrum", "Rubrum", 22, tab=_SATZBREITE)
    + _stil("Titelzeile", "Bezeichnung des Schriftsatzes", 26, vor=240, nach=240, fett=True)
    + _stil("Zwischen", "Zwischenüberschrift", 22, vor=240, nach=120, fett=True, zusammen=True)
    + _stil("Fusszeile", "Fußzeile Briefbogen", 14)
    + "</w:styles>"
)


def _typen(bild: str | None) -> str:
    bildtyp = {"png": "image/png", "jpeg": "image/jpeg"}
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + (f'<Default Extension="{bild}" ContentType="{bildtyp[bild]}"/>' if bild else "")
            + '<Override PartName="/word/document.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/header1.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
              '<Override PartName="/word/footer1.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
              '<Override PartName="/docProps/core.xml" '
              'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              "</Types>")


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
    '<Relationship Id="rIdKopf" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
    'Target="header1.xml"/>'
    '<Relationship Id="rIdFuss" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
    'Target="footer1.xml"/>'
    "</Relationships>"
)


def _kopf_bezuege(bild: str | None) -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + (f'<Relationship Id="rIdLogo" '
               f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
               f'Target="media/logo.{bild}"/>' if bild else "")
            + "</Relationships>")


def _dokument(art: str) -> str:
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS}><w:body>'
            f"{_koerper(art)}"
            '<w:sectPr><w:headerReference w:type="default" r:id="rIdKopf"/>'
            '<w:footerReference w:type="default" r:id="rIdFuss"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            f'<w:pgMar w:top="{_RAND_OBEN}" w:right="{_RAND_RECHTS}" w:bottom="{_RAND_UNTEN}" w:left="{_RAND_LINKS}" '
            'w:header="567" w:footer="454" w:gutter="0"/></w:sectPr></w:body></w:document>')


def logo_lesen(ordner: Path) -> tuple[bytes, str, str] | None:
    """Logo der Arbeitsumgebung (Einstellungen → Allgemeines) als (Daten, Endung, Dateiname), wenn Word es kann.

    Bei SVG und WebP gilt das PNG, das die Oberfläche daraus gerendert hat (logo-druck.png).
    """
    for p in sorted(Path(ordner).glob("logo.*")):
        endung = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}.get(p.suffix.lower())
        if endung:
            return p.read_bytes(), endung, p.name
    druck = Path(ordner) / "logo-druck.png"
    if druck.is_file() and any(p.suffix.lower() in (".svg", ".webp") for p in Path(ordner).glob("logo.*")):
        return druck.read_bytes(), "png", "logo.png"
    return None


def logo_hinweis(ordner: Path) -> str | None:
    """Hinweis, wenn ein Logo eingestellt ist, das Word nicht einbetten kann und für das kein Druckbild vorliegt."""
    vorhanden = [p for p in Path(ordner).glob("logo.*") if p.suffix.lower() in (".svg", ".webp")]
    if vorhanden and logo_lesen(ordner) is None:
        return ("Das Logo (SVG oder WebP) erscheint noch nicht im Schriftstück. Bitte JuraBox einmal neu starten oder "
                "das Logo in Einstellungen → Allgemeines erneut wählen; dann legt JuraBox eine Fassung für Word an.")
    return None


def erzeugen(art: str, logo: tuple[bytes, str, str] | None = None) -> bytes:
    """Die Grundvorlage als .docx mit Platzhaltern."""
    if art not in GRUNDVORLAGEN:
        raise ValueError(f"Unbekannte Grundvorlage: {art!r}")
    bild = None
    lauf = ""
    if logo:
        groesse = bildgroesse(logo[0])
        if groesse and all(groesse):
            bild = logo[1]
            lauf = _logo_lauf(*groesse, logo[2])
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _typen(bild))
        z.writestr("_rels/.rels", _PAKET_BEZUEGE)
        z.writestr("docProps/core.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-'
                   'properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   f"<dc:title>{escape(GRUNDVORLAGEN[art]['titel'])}</dc:title><dc:creator>JuraBox</dc:creator>"
                   "<dc:language>de-DE</dc:language></cp:coreProperties>")
        z.writestr("word/_rels/document.xml.rels", _DOKUMENT_BEZUEGE)
        z.writestr("word/_rels/header1.xml.rels", _kopf_bezuege(bild))
        z.writestr("word/document.xml", _dokument(art))
        z.writestr("word/styles.xml", STILE)
        z.writestr("word/header1.xml", _kopfzeile(lauf))
        z.writestr("word/footer1.xml", _fusszeile())
        if bild and logo:
            z.writestr(f"word/media/logo.{bild}", logo[0])
    return puffer.getvalue()
