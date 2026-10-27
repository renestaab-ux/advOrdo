"""Platzhalter in einer Word-Datei (.docx, .dotx) finden und durch Werte ersetzen.

Word teilt Text beim Bearbeiten oft in mehrere Läufe („{{Man“ + „dant.Name}}“), etwa wegen Rechtschreibprüfung
oder Formatierung. Gesucht wird deshalb im zusammengesetzten Text eines Absatzes; der Wert landet im Lauf, in dem
der Platzhalter beginnt, und übernimmt dessen Formatierung. Alles andere in der Datei bleibt Byte für Byte gleich,
damit Formatvorlagen, Kopf- und Fußzeilen, Bilder und Felder erhalten bleiben.

Zeilenumbrüche im Wert werden zu Zeilenwechseln im Absatz (Umschalt+Eingabe in Word), Tabulatoren zu Tabulatoren.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable
from xml.sax.saxutils import escape, unescape

PLATZHALTER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
# Text eines Laufs bzw. Ende eines Absatzes; <w:tab/>, <w:tbl> u. ä. passen nicht, weil nach „w:t“ ein Leerzeichen
# oder „>“ folgen muss.
_TEIL = re.compile(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)|</w:p>", re.S)
_TEILE = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")
_ENTITAETEN = {"&quot;": '"', "&apos;": "'"}
_UNGUELTIG = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

VORLAGE_TYP = "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
DOKUMENT_TYP = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


class KeineVorlage(ValueError):
    pass


def _absaetze(xml: str) -> list[list[re.Match]]:
    """Die Textläufe je Absatz, in der Reihenfolge der Datei."""
    absaetze: list[list[re.Match]] = [[]]
    for m in _TEIL.finditer(xml):
        if m.group(1) is None:
            absaetze.append([])
        else:
            absaetze[-1].append(m)
    return [a for a in absaetze if a]


def _wert_xml(wert: str) -> str:
    """Wert als Inhalt eines <w:t>; Zeilenumbruch und Tabulator schließen den Text kurz und setzen ihn fort."""
    weiter = '</w:t>{}<w:t xml:space="preserve">'
    zeilen = []
    for zeile in _UNGUELTIG.sub("", wert).split("\n"):
        zeilen.append(weiter.format("<w:tab/>").join(escape(t) for t in zeile.split("\t")))
    return weiter.format("<w:br/>").join(zeilen)


def _ersetze_teil(xml: str, ersatz: Callable[[str], str | None]) -> str:
    """Ersetzt alle Platzhalter eines XML-Teils; ``ersatz`` gibt None zurück, wenn der Platzhalter bleiben soll."""
    neu: dict[int, str] = {}  # Anfang des Textinhalts → neuer Inhalt (bereits XML)
    for laeufe in _absaetze(xml):
        texte = [unescape(m.group(2), _ENTITAETEN) for m in laeufe]
        gesamt = "".join(texte)
        if "{{" not in gesamt:
            continue
        treffer = [(m, ersatz(m.group(1))) for m in PLATZHALTER.finditer(gesamt)]
        treffer = [(m, w) for m, w in treffer if w is not None]
        if not treffer:
            continue
        # Zu jedem Zeichen der Lauf, aus dem es stammt.
        herkunft = [i for i, t in enumerate(texte) for _ in t]
        stuecke: list[list[str]] = [[] for _ in texte]
        pos = 0
        for m, wert in treffer:
            for k in range(pos, m.start()):
                stuecke[herkunft[k]].append(escape(gesamt[k]))
            stuecke[herkunft[m.start()]].append(_wert_xml(wert))
            pos = m.end()
        for k in range(pos, len(gesamt)):
            stuecke[herkunft[k]].append(escape(gesamt[k]))
        for i, m in enumerate(laeufe):
            inhalt = "".join(stuecke[i])
            if inhalt != m.group(2):
                neu[m.start(1)] = inhalt
    if not neu:
        return xml
    teile, pos = [], 0
    for m in _TEIL.finditer(xml):
        if m.group(1) is None or m.start(1) not in neu:
            continue
        teile.append(xml[pos:m.start(1)])
        teile.append(f'<w:t xml:space="preserve">{neu[m.start(1)]}</w:t>')
        pos = m.end(3)
    teile.append(xml[pos:])
    return "".join(teile)


def _oeffne(daten: bytes) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(io.BytesIO(daten))
        namen = set(z.namelist())
    except zipfile.BadZipFile as fehler:
        raise KeineVorlage("Die Datei ist keine Word-Datei (.docx oder .dotx).") from fehler
    if "word/document.xml" not in namen or "[Content_Types].xml" not in namen:
        raise KeineVorlage("Die Datei ist keine Word-Datei (.docx oder .dotx).")
    if "word/vbaProject.bin" in namen:
        raise KeineVorlage("Vorlagen mit Makros (.docm, .dotm) werden nicht verwendet. Bitte als .docx speichern.")
    return z


def platzhalter_finden(daten: bytes) -> list[str]:
    """Alle Platzhalter der Datei in der Reihenfolge ihres ersten Vorkommens, wie sie geschrieben sind."""
    gefunden: list[str] = []
    with _oeffne(daten) as z:
        for name in sorted(z.namelist(), key=lambda n: (n != "word/document.xml", n)):
            if not _TEILE.match(name):
                continue
            xml = z.read(name).decode("utf-8")
            for laeufe in _absaetze(xml):
                gesamt = "".join(unescape(m.group(2), _ENTITAETEN) for m in laeufe)
                gefunden += [" ".join(m.group(1).split()) for m in PLATZHALTER.finditer(gesamt)]
    return list(dict.fromkeys(gefunden))


def fuellen(daten: bytes, ersatz: Callable[[str], str | None]) -> bytes:
    """Neue Word-Datei mit eingesetzten Werten. Aus einer Dokumentvorlage (.dotx) wird ein Dokument (.docx)."""
    puffer = io.BytesIO()
    with _oeffne(daten) as quelle, zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as ziel:
        for info in quelle.infolist():
            inhalt = quelle.read(info.filename)
            if _TEILE.match(info.filename):
                inhalt = _ersetze_teil(inhalt.decode("utf-8"), ersatz).encode("utf-8")
            elif info.filename == "[Content_Types].xml":
                inhalt = inhalt.replace(VORLAGE_TYP.encode(), DOKUMENT_TYP.encode())
            ziel.writestr(info, inhalt)
    return puffer.getvalue()
