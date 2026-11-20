"""Gesetze aus der XML-Fassung von gesetze-im-internet.de (gii-norm, DTD 1.01) als Markdown.

Nachbau des Referenzskripts ``gii2md.py`` (Stand 20.11.2026): Für dieselbe XML entsteht dieselbe Markdown-Datei
(tests/test_gesetz_markdown.py vergleicht mit Ausgaben des Skripts). Der Gesetzeswortlaut bleibt unverändert.

- Kopf mit Titel, Ausfertigungsdatum, Fundstelle, Stand („Zuletzt geändert durch …“), Quelle, XML-Stand und
  Dokumentnummer.
- Gliederung (Buch/Teil/Abschnitt) als Überschriften, jeder Paragraf/Artikel als eigene Überschrift.
- Nummern- und Buchstabenlisten eingerückt (verschachtelt), Tabellen als Markdown-Tabellen, Fußnoten und amtliche
  Hinweise als Zitatblock.
- Satznummern hochgestellt (soweit die Vorlage sie enthält).
- Die amtliche Inhaltsübersicht wird nicht übernommen (die Überschriften ersetzen sie).

Zwei Abweichungen vom Skript, beide ohne Einfluss auf den Text: ``stand_datum`` nimmt für den Dateinamen das Datum
der letzten Änderung, nicht das der Neufassung. Und ``_bereinige`` löst vorher HTML-Entitäten wie ``&nbsp;`` auf
und entfernt die DOCTYPE-Zeile, wie beim Import (``gii._bereinige``). An Dateien, die das Skript lesen kann, ändert
das nichts.

``pruefen`` ist der Wort-für-Wort-Abgleich des Skripts (Option ``--pruefen``): Er meldet Wörter der XML, die in der
Markdown-Datei fehlen.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

from .. import grenzen
from .gii import _bereinige

_HOCH = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
# Unsichtbarer Platzhalter für Einrückungen; wird am Ende zu Leerzeichen (wie im Skript).
_EINZUG = "⁣"


def _wurzel(daten: bytes | str) -> ET.Element:
    return ET.fromstring(_bereinige(daten))


def _sauber(s: str) -> str:
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    return s.strip()


def _inline(el: ET.Element) -> str:
    """Text eines Elements samt Inline-Kindern."""
    out = [el.text or ""]
    for c in el:
        t = c.tag
        if t == "BR":
            out.append("\n")
        elif t == "SUP":
            txt = "".join(c.itertext())
            out.append(txt.translate(_HOCH) if c.get("class") == "Rec" else "^" + txt)
        elif t == "B":
            out.append("**" + _inline(c).strip() + "**")
        elif t == "I":
            out.append("*" + _inline(c).strip() + "*")
        elif t in ("FnR", "noindex"):
            out.append(_inline(c))
        elif t in ("DL", "table", "P", "pre"):
            out.append("\n" + _block(c, 0) + "\n")
        else:
            out.append(_inline(c))
        out.append(c.tail or "")
    return "".join(out)


def _tabelle(el: ET.Element) -> str:
    zeilen = []
    for row in el.iter("row"):
        zeilen.append([_sauber(_inline(e)).replace("\n", " ").replace("|", "\\|") for e in row.findall("entry")])
    if not zeilen:
        return ""
    n = max(len(z) for z in zeilen)
    zeilen = [z + [""] * (n - len(z)) for z in zeilen]
    md = ["| " + " | ".join(zeilen[0]) + " |", "|" + " --- |" * n]
    md += ["| " + " | ".join(z) + " |" for z in zeilen[1:]]
    return "\n".join(md)


def _liste(el: ET.Element, tiefe: int) -> str:
    zeilen: list[str] = []
    begriff = ""
    einzug = _EINZUG * (2 * tiefe)
    for c in el:
        if c.tag == "DT":
            begriff = _sauber(_inline(c))
        elif c.tag == "DD":
            teile: list[str] = []
            for k in c:
                if k.tag == "LA":
                    tmp = ET.Element("LA")
                    tmp.text = k.text
                    for x in k:
                        if x.tag == "DL":
                            teile.append(_sauber(_inline(tmp)))
                            tmp = ET.Element("LA")
                            tmp.text = x.tail
                            teile.append(_liste(x, tiefe + 1))
                        else:
                            tmp.append(x)
                    teile.append(_sauber(_inline(tmp)))
                elif k.tag == "DL":
                    teile.append(_liste(k, tiefe + 1))
                else:
                    teile.append(_sauber(_inline(k)))
            inhalt = "\n".join(p for p in teile if p) or _sauber(c.text or "")
            erste, *rest = inhalt.split("\n")
            zeilen.append(f"{einzug}- {begriff} {erste}".rstrip())
            zeilen += [
                r if r.lstrip().startswith("- ") and r.startswith(einzug + _EINZUG * 2) else f"{einzug}{_EINZUG * 2}{r}"
                for r in rest
            ]
    return "\n".join(zeilen)


def _block(el: ET.Element, tiefe: int = 0) -> str:
    t = el.tag
    if t == "DL":
        return _liste(el, tiefe)
    if t == "table":
        return _tabelle(el)
    if t == "pre":
        return _sauber(_inline(el))
    if t == "P":
        return _sauber(_inline(el))
    if t in ("Content", "text", "Footnote", "Footnotes", "FnArea"):
        return "\n\n".join(b for b in (_block(c, tiefe) for c in el) if b)
    return _sauber(_inline(el))


def _inhalt(content: ET.Element | None) -> str:
    if content is None:
        return ""
    return "\n\n".join(b for b in (_block(c) for c in content) if b)


def umwandeln(daten: bytes | str) -> tuple[str, dict]:
    """XML (Bytes oder Text) -> (Markdown, Metadaten mit abk, titel, stand, stand_datum, doknr, letztmalig)."""
    wurzel = _wurzel(daten)
    if wurzel.tag != "dokumente" or wurzel.find("norm/metadaten") is None:
        raise ValueError("Keine XML-Fassung von gesetze-im-internet.de (gii-norm).")
    normen = wurzel.findall("norm")
    meta0 = normen[0].find("metadaten")
    langue = meta0.findtext("langue") or ""
    amtabk = meta0.findtext("amtabk") or meta0.findtext("jurabk") or ""
    ausf = meta0.findtext("ausfertigung-datum") or ""
    fund = meta0.find("fundstelle")
    fundtxt = f"{fund.findtext('periodikum')} {fund.findtext('zitstelle')}" if fund is not None else ""
    stand = [s.findtext("standkommentar") for s in meta0.findall("standangabe")]
    out = [f"# {langue} ({amtabk})", ""]
    out.append(f"- Ausfertigungsdatum: {ausf}")
    if fundtxt:
        out.append(f"- Fundstelle: {fundtxt}")
    for s in stand:
        out.append(f"- Stand: {_sauber(s or '')}")
    out.append(
        f"- Quelle: gesetze-im-internet.de (nichtamtliche Fassung), XML-Stand {wurzel.get('builddate', '')[:8]}, "
        f"Dokument {wurzel.get('doknr', '')}"
    )
    out.append(
        "- Umgewandelt aus der XML-Fassung in Markdown; Wortlaut unverändert, Satznummern (soweit in der Vorlage "
        "enthalten) hochgestellt; amtliche Inhaltsübersicht nicht übernommen."
    )
    t0 = _inhalt(normen[0].find("textdaten/text/Content"))
    if t0:
        out += ["", "Amtlicher Hinweis:", "", t0]
    fn0 = normen[0].find("textdaten/fussnoten/Content")
    if fn0 is not None:
        txt = _inhalt(fn0)
        if txt:
            out += ["", "> " + txt.replace("\n", "\n> ")]
    out.append("")
    tiefen = [len(n.findtext("metadaten/gliederungseinheit/gliederungskennzahl") or "") // 3 for n in normen[1:]]
    maxt = max([d for d in tiefen if d] or [0])
    norm_ebene = "#" * min(maxt + 2, 6)
    for n in normen[1:]:
        m = n.find("metadaten")
        ge = m.find("gliederungseinheit")
        enbez = m.findtext("enbez")
        titel = m.find("titel")
        titeltxt = _sauber("".join(titel.itertext())) if titel is not None else ""
        if enbez:
            if enbez.lower() in ("inhaltsübersicht", "inhaltsverzeichnis"):
                continue
            out.append(f"{norm_ebene} {_sauber(enbez)} {titeltxt}".rstrip())
        elif ge is not None:
            ebene = min(len(ge.findtext("gliederungskennzahl") or "000") // 3, 5)
            gb = _sauber(ge.findtext("gliederungsbez") or "")
            gt = _sauber(ge.findtext("gliederungstitel") or "")
            out.append(f"{'#' * (ebene + 1)} {gb} {gt}".rstrip().replace("\n", " "))
        elif titeltxt or n.find("textdaten/text/Content") is not None:
            out.append(f"{norm_ebene} {titeltxt}".rstrip() if titeltxt else "")
        else:
            continue
        out.append("")
        text = _inhalt(n.find("textdaten/text/Content"))
        fns = n.find("textdaten/text/Footnotes")
        if fns is not None:
            punkte = [f"- Fußnote {f.get('FnZ', '')} " + _sauber(_inline(f)) for f in fns.iter("Footnote")]
            if punkte:
                text = (text + "\n\nFußnoten:\n" + "\n".join(punkte)).strip()
        if text:
            out += [text, ""]
        fn = n.find("textdaten/fussnoten/Content")
        if fn is not None:
            ft = _inhalt(fn)
            if ft:
                out += ["> Fußnote: " + ft.replace("\n", "\n> "), ""]
    md = "\n".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(_EINZUG + "+", lambda m: " " * len(m.group(0)), md)
    staende = [_sauber(x) for x in stand if x]
    meta = {
        "abk": amtabk,
        "titel": langue,
        "stand": staende,
        "stand_datum": stand_datum(stand, ausf),
        "doknr": wurzel.get("doknr", ""),
        "letztmalig": any("letztmalig" in s for s in staende),
    }
    return md.strip() + "\n", meta


def stand_datum(stand: list[str | None], ausf: str) -> str:
    """Datum des letzten Änderungsgesetzes aus der Standangabe (JJJJ-MM-TT), sonst das Ausfertigungsdatum.

    Abweichend vom Skript zählt „Zuletzt geändert durch …“ vor „Neugefasst durch …“: Beim BGB steht die
    Neufassung von 2002 zuerst, der Dateiname hieße sonst „Stand-2002-01-02“."""
    stand = [s for s in stand or [] if s]
    for s in sorted(stand, key=lambda s: "geändert" not in s):
        m = re.search(r"v\.\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", s or "")
        if m and not re.search(r"letztmalig", s):
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ausf or "unbekannt"


def xml_aus(daten: bytes) -> bytes:
    """Die XML-Datei aus dem ZIP-Paket von gesetze-im-internet.de (oder die Daten selbst, wenn es kein ZIP ist)."""
    if not zipfile.is_zipfile(io.BytesIO(daten)):
        return daten
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        namen = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not namen:
            raise ValueError("Im ZIP ist keine XML-Datei enthalten.")
        return grenzen.entpacke(z, namen[0])


def _slug(t: str) -> str:
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = t.replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue")
    return re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-")


def dateiname(meta: dict) -> str:
    """``<Abkürzung>_<Langtitel>_Stand-<JJJJ-MM-TT>.md``"""
    return f"{_slug(meta['abk'])}_{_slug(meta['titel'])[:80]}_Stand-{meta['stand_datum']}.md"


WARNUNG_LETZTMALIG = (
    "Laut Standangabe ist dies eine außer Kraft getretene Fassung (letztmalige Anwendung). "
    "Bitte die geltende Fassung prüfen."
)


def pruefen(daten: bytes | str, md: str) -> dict[str, int]:
    """Wort-für-Wort-Abgleich (Wörter ab 4 Buchstaben) ohne Inhaltsübersicht: Wörter der XML, die im Markdown fehlen,
    mit Anzahl. Leer heißt vollständig."""
    wurzel = _wurzel(daten)
    text = " ".join(
        " ".join(n.itertext())
        for n in wurzel.findall("norm")
        if (n.findtext("metadaten/enbez") or "").lower() != "inhaltsübersicht"
    )

    def woerter(s: str) -> list[str]:
        return re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", s)

    fehlt = Counter(woerter(text)) - Counter(woerter(md))
    abk = {x for tag in ("jurabk", "amtabk", "standtyp") for n in wurzel.iter(tag) for x in woerter(n.text or "")}
    return {k: v for k, v in fehlt.items() if k not in abk}
