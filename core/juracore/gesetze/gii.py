"""Parser für das XML-Format von "Gesetze im Internet" (gii-norm.dtd).

Ein Gesetz kommt als ``<dokumente>`` mit einer Folge von ``<norm>``-Elementen:
die erste Norm trägt die Stammdaten (Langtitel, Stand), Gliederungsnormen
tragen Buch/Abschnitt/Titel, Einzelnormen tragen ``enbez`` (z. B. "§ 280")
und den Normtext in ``textdaten/text/Content/P``.

Der Parser liefert die Normen strukturiert bis auf Absatz-, Satz- und
Nummernebene, damit Fundstellen wie "§ 280 Abs. 1 S. 2 BGB" exakt aufgelöst
werden können.
"""

from __future__ import annotations

import html.entities
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .saetze import Liste, Satz, zerlege_in_saetze

_ABSATZ_NR = re.compile(r"^\((\d+[a-z]?)\)\s*")
_ENBEZ = re.compile(r"^(§§?|Art\.?|Artikel|Anlage)\s*(.*)$")
_XML_ENTITAETEN = {"amp", "lt", "gt", "quot", "apos"}


@dataclass
class Absatz:
    nr: str | None
    text: str
    saetze: list[Satz]


@dataclass
class Norm:
    doknr: str
    reihenfolge: int
    bezeichnung: str  # "§ 280", "Art 1", "Anlage 2"
    typ: str  # "paragraph" | "artikel" | "anlage" | "sonstige"
    nummer: str | None  # "280", "312g"
    titel: str | None
    gliederung: list[str]
    absaetze: list[Absatz]
    weggefallen: bool
    fussnoten: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(a.text for a in self.absaetze)


@dataclass
class GesetzDokument:
    abk: str
    langtitel: str | None
    builddate: str | None
    doknr: str | None
    stand: list[str] = field(default_factory=list)
    normen: list[Norm] = field(default_factory=list)


def parse_gii_xml(daten: bytes | str) -> GesetzDokument:
    """Parst ein komplettes Gesetz im GII-XML-Format."""
    wurzel = ET.fromstring(_bereinige(daten))
    if wurzel.tag != "dokumente":
        raise ValueError(f"Kein GII-Dokument: Wurzelelement <{wurzel.tag}>")

    dokument = GesetzDokument(
        abk="",
        langtitel=None,
        builddate=wurzel.get("builddate"),
        doknr=wurzel.get("doknr"),
    )
    # Gliederung als Stapel (Kennzahl, Bezeichnung); die Kennzahl wächst je Ebene um drei Ziffern.
    gliederung: list[tuple[str, str]] = []
    reihenfolge = 0

    for norm_el in wurzel.findall("norm"):
        meta = norm_el.find("metadaten")
        if meta is None:
            continue
        if not dokument.abk:
            dokument.abk = _text(meta.find("jurabk")) or _text(meta.find("amtabk")) or ""
        if dokument.langtitel is None and meta.find("langue") is not None:
            dokument.langtitel = _text(meta.find("langue"))
            dokument.stand = [
                _text(s.find("standkommentar")) for s in meta.findall("standangabe") if _text(s.find("standkommentar"))
            ]

        einheit = meta.find("gliederungseinheit")
        if einheit is not None:
            kennzahl = _text(einheit.find("gliederungskennzahl")) or ""
            bez = " ".join(
                t for t in (_text(einheit.find("gliederungsbez")), _text(einheit.find("gliederungstitel"))) if t
            )
            while gliederung and not kennzahl.startswith(gliederung[-1][0]):
                gliederung.pop()
            gliederung.append((kennzahl, bez))
            continue

        enbez = _text(meta.find("enbez"))
        if not enbez or enbez in ("Inhaltsübersicht", "Eingangsformel", "Schlußformel", "Schlussformel"):
            continue

        typ, nummer = _klassifiziere(enbez)
        titel = _text(meta.find("titel"))
        content = norm_el.find("textdaten/text/Content")
        absaetze = _parse_absaetze(content) if content is not None else []
        weggefallen = (titel or "").strip("() ").lower() == "weggefallen" or (
            not absaetze or all(a.text.strip() in ("", "-", "(weggefallen)") for a in absaetze)
        )
        fussnoten_el = norm_el.find("textdaten/fussnoten/Content")
        reihenfolge += 1
        dokument.normen.append(
            Norm(
                doknr=norm_el.get("doknr", ""),
                reihenfolge=reihenfolge,
                bezeichnung=enbez,
                typ=typ,
                nummer=nummer,
                titel=titel,
                gliederung=[b for _, b in gliederung],
                absaetze=absaetze,
                weggefallen=weggefallen,
                fussnoten=(_leerraum(_flach(fussnoten_el)).strip() or None) if fussnoten_el is not None else None,
            )
        )
    if not dokument.abk:
        raise ValueError("GII-Dokument ohne Abkürzung (jurabk)")
    return dokument


def _bereinige(daten: bytes | str) -> str:
    """Entfernt die DOCTYPE-Deklaration und löst HTML-Entitäten auf.

    Die GII-Dateien verweisen auf eine externe DTD; ohne sie kennt der Parser
    benannte Entitäten wie ``&nbsp;`` nicht. Externe Ressourcen werden nie geladen.
    """
    text = daten.decode("utf-8") if isinstance(daten, bytes) else daten
    text = re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?\s*>", "", text, count=1)

    def ersetze(m: re.Match[str]) -> str:
        name = m.group(1)
        if name in _XML_ENTITAETEN:
            return m.group(0)
        zeichen = html.entities.html5.get(name + ";")
        return zeichen if zeichen is not None else m.group(0)

    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", ersetze, text)


def _klassifiziere(enbez: str) -> tuple[str, str | None]:
    m = _ENBEZ.match(enbez.strip())
    if not m:
        return "sonstige", None
    praefix, rest = m.groups()
    nummer = rest.strip() or None
    if praefix.startswith("§"):
        return "paragraph", nummer
    if praefix.startswith("Art"):
        return "artikel", nummer
    return "anlage", nummer


def _parse_absaetze(content: ET.Element) -> list[Absatz]:
    absaetze: list[Absatz] = []
    for p in content.findall("P"):
        teile = _teile(p)
        if not teile:
            continue
        nr = None
        if isinstance(teile[0], str):
            m = _ABSATZ_NR.match(teile[0].lstrip())
            if m:
                nr = m.group(1)
                teile[0] = teile[0].lstrip()[m.end() :]
        if nr is None and absaetze and absaetze[-1].nr is not None:
            # Unnummerierter Folgeabsatz gehört zum vorangehenden nummerierten Absatz.
            vorher = absaetze[-1]
            saetze = zerlege_in_saetze(teile, start_nr=len(vorher.saetze) + 1)
            vorher.saetze.extend(saetze)
            vorher.text = vorher.text + "\n" + _verbinde(teile)
            continue
        absaetze.append(Absatz(nr=nr, text=_verbinde(teile), saetze=zerlege_in_saetze(teile)))
    return absaetze


def _teile(el: ET.Element) -> list[str | Liste]:
    """Zerlegt ein Absatzelement in Fließtext und Aufzählungen (DL)."""
    teile: list[str | Liste] = []

    def text_anhaengen(t: str | None) -> None:
        if not t:
            return
        if teile and isinstance(teile[-1], str):
            teile[-1] += t
        else:
            teile.append(t)

    def lauf(e: ET.Element) -> None:
        text_anhaengen(e.text)
        for kind in e:
            if kind.tag == "DL":
                teile.append(_liste(kind))
            elif kind.tag in ("SUP", "FnR", "FnArea"):
                pass  # Fußnotenmarker gehören nicht zum Normtext
            elif kind.tag == "BR":
                text_anhaengen(" ")
            else:
                lauf(kind)
            text_anhaengen(kind.tail)

    lauf(el)
    bereinigt: list[str | Liste] = []
    for t in teile:
        if isinstance(t, str):
            t = _leerraum(t)
            if not t.strip():
                continue
        bereinigt.append(t)
    return bereinigt


def _liste(dl: ET.Element) -> Liste:
    eintraege: list[tuple[str, str]] = []
    nr = ""
    for kind in dl:
        if kind.tag == "DT":
            nr = _leerraum(_flach(kind)).strip().rstrip(".").rstrip(")")
        elif kind.tag == "DD":
            eintraege.append((nr, _leerraum(_flach(kind)).strip()))
    return Liste(eintraege)


def _flach(el: ET.Element) -> str:
    """Text eines Elements; verschachtelte Listen werden als "a) …" eingeebnet."""
    teile: list[str] = [el.text or ""]
    for kind in el:
        if kind.tag in ("SUP", "FnR"):
            pass
        elif kind.tag == "DT":
            teile.append(" " + _flach(kind) + " ")
        elif kind.tag == "BR":
            teile.append(" ")
        else:
            teile.append(_flach(kind))
        teile.append(kind.tail or "")
    return "".join(teile)


def _verbinde(teile: list[str | Liste]) -> str:
    stuecke: list[str] = []
    for t in teile:
        if isinstance(t, Liste):
            stuecke.append("\n" + t.als_text() + "\n")
        else:
            stuecke.append(t)
    return re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(stuecke)).strip()


def _leerraum(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("\xa0", " "))


def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    t = _leerraum("".join(el.itertext())).strip()
    return t or None
