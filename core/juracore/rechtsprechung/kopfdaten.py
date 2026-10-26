"""Kopfdaten einer Entscheidung aus ihrem Text: Gericht, Aktenzeichen, Datum, Art und Quelle.

Gedacht für eigene Dateien, die man der Sammlung hinzufügt (PDF-Ausdruck aus juris oder beck-online, Ausfertigung
des Gerichts, openJur). Gelesen wird nur der Kopf; erkannt werden drei Formen:

- Felder mit Beschriftung wie bei juris und openJur: „Gericht: OLG Hamm“, „Entscheidungsdatum: 03.05.2022“,
  „Aktenzeichen: 28 U 12/21“, „Dokumenttyp: Urteil“ (Wert in derselben oder der nächsten Zeile),
- eine Zitierzeile wie bei beck-online: „BGH, Urteil vom 17.03.2021 – VIII ZR 999/20“,
- der Kopf einer Ausfertigung: „BUNDESGERICHTSHOF“, „IM NAMEN DES VOLKES“, „URTEIL“, „VIII ZR 999/20“,
  „Verkündet am: 17. März 2021“.

Jeder Wert kommt mit seiner Fundstelle (Abschnitt, Seite, Zeile), damit man ihn vor dem Speichern prüfen kann.
Es sind Vorschläge; was nicht erkannt wird, bleibt leer.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..dokumente import datum as datumszeile
from .zitate import _AKTENZEICHEN, ARTEN, _iso, finde_urteilszitate

KOPF_ABSCHNITTE = 60

# Gerichte ausgeschrieben → übliche Abkürzung, wie in Zitaten und im Verzeichnis des Bundes.
_GERICHTE = {
    "bundesverfassungsgericht": "BVerfG",
    "bundesgerichtshof": "BGH",
    "bundesarbeitsgericht": "BAG",
    "bundessozialgericht": "BSG",
    "bundesfinanzhof": "BFH",
    "bundesverwaltungsgericht": "BVerwG",
    "bundespatentgericht": "BPatG",
    "bayerisches oberstes landesgericht": "BayObLG",
    "oberlandesgericht": "OLG",
    "landgericht": "LG",
    "amtsgericht": "AG",
    "kammergericht": "KG",
    "landesarbeitsgericht": "LAG",
    "arbeitsgericht": "ArbG",
    "oberverwaltungsgericht": "OVG",
    "verwaltungsgerichtshof": "VGH",
    "verwaltungsgericht": "VG",
    "landessozialgericht": "LSG",
    "sozialgericht": "SG",
    "finanzgericht": "FG",
    "gerichtshof der europäischen union": "EuGH",
    "europäischer gerichtshof": "EuGH",
}
_GERICHT_LANG = re.compile(
    r"^(?P<art>" + "|".join(sorted(_GERICHTE, key=len, reverse=True)) + r")\b(?P<ort>[^,;:\d]*)", re.IGNORECASE
)
# Ort hinter dem Gericht: großgeschriebene Wörter und Verbindungen wie „am Main“, „im Breisgau“, „i. Br.“.
_VERBINDUNG = {"am", "an", "der", "im", "in", "i.", "a.", "d.", "Br.", "M."}
_KEIN_ORT = re.compile(r"^(?:Zivil|Straf|Senat|Kammer|Abteilung|Beschluss|Urteil|Namen|Az|Aktenzeichen)")
_KURZ = re.compile(
    r"^(?P<g>BVerfG|BGH|BAG|BSG|BFH|BVerwG|BPatG|BayObLG|EuGH|EuG|KG|(?:OLG|LG|AG|OVG|VGH|VG|LAG|ArbG|LSG|SG|FG)"
    r"\s+[A-ZÄÖÜ][\wäöüß.\-]*(?:\s+(?:am|an der|im|in|i\.\s?Br\.|a\.\s?M\.)(?:\s+[A-ZÄÖÜ][\wäöüß]+)?)?)\s*"
    r"(?:\d+\.\s*\S+)?$"
)
_ART = re.compile(
    r"^(?:(?:Teil|End|Grund|Schluss|Anerkenntnis|Versäumnis)?urteil|Beschluss|Hinweisbeschluss|Gerichtsbescheid|"
    r"Kammerbeschluss|Vorlagebeschluss)$",
    re.IGNORECASE,
)
_LABEL = re.compile(
    r"^(?P<label>Gericht|Spruchkörper|Entscheidungsdatum|Datum|Verkündet am|Aktenzeichen|Az\.?|"
    r"Geschäftszeichen|Dokumenttyp|Entscheidungsart|Typ|Entscheidungsform)\s*:\s*(?P<wert>.*)$",
    re.IGNORECASE,
)
_FORMEL = re.compile(r"für Recht erkannt|\bbeschlossen\s*:", re.IGNORECASE)
_NUR_AZ = re.compile(rf"^(?:(?:Aktenzeichen|Az\.?|Geschäftszeichen)\s*:?\s*)?{_AKTENZEICHEN}\s*$")
_HERKUNFT = (("juris", re.compile(r"\bjuris\b", re.IGNORECASE)),
             ("beck-online", re.compile(r"beck-?online|BeckRS", re.IGNORECASE)),
             ("openJur", re.compile(r"\bopenjur\b", re.IGNORECASE)))


def gericht_kurz(text: str) -> str | None:
    """„Oberlandesgericht Hamm“ → „OLG Hamm“, „BUNDESGERICHTSHOF“ → „BGH“, „OLG Hamm“ bleibt. Sonst ``None``."""
    text = " ".join(text.split()).strip(" ,;:")
    if not text:
        return None
    if m := _KURZ.match(text):
        return " ".join(m.group("g").split())
    if text.isupper():
        text = text.title()
    m = _GERICHT_LANG.match(text)
    if not m:
        return None
    kurz = _GERICHTE[m.group("art").lower()]
    woerter: list[str] = []
    for w in m.group("ort").split():
        if w.lower() in _VERBINDUNG:
            w = w.lower()  # aus Großbuchstaben: „AM MAIN“ → „Am Main“ → „am Main“
        if _KEIN_ORT.match(w) or not (w[0].isupper() or w in _VERBINDUNG):
            break
        woerter.append(w)
    while woerter and woerter[-1] in _VERBINDUNG - {"Br.", "M."}:
        woerter.pop()
    ort = " ".join(woerter).strip(" -–—")
    if kurz in ("BVerfG", "BGH", "BAG", "BSG", "BFH", "BVerwG", "BPatG", "BayObLG", "EuGH", "KG"):
        return kurz
    return f"{kurz} {ort}" if ort else None


def _zeilen(abschnitte: Iterable[tuple[int, int | None, str]]):
    for nr, seite, text in abschnitte:
        for zeile in text.splitlines():
            if zeile := " ".join(zeile.split()):
                yield nr, seite, zeile


def _fund(nr: int, seite: int | None, zeile: str) -> dict:
    return {"abschnitt": nr, "seite": seite, "text": zeile[:160]}


def _art(text: str) -> str | None:
    text = text.strip(" .:")
    if not _ART.match(text):
        return None
    return ARTEN.get(text, text[0].upper() + text[1:].lower())


def erkenne(abschnitte: list[tuple[int, int | None, str]]) -> dict:
    """Vorschlag aus ``(Abschnitt-Nr., Seite, Text)`` in Dokumentreihenfolge; je Feld ``{"wert", "fundstelle"}``."""
    kopf = list(_zeilen(abschnitte[:KOPF_ABSCHNITTE]))
    ergebnis: dict[str, dict | None] = {"gericht": None, "aktenzeichen": None, "datum": None, "art": None,
                                         "herkunft": None}

    def setze(feld: str, wert: str | None, nr: int, seite: int | None, zeile: str) -> None:
        if wert and ergebnis[feld] is None:
            ergebnis[feld] = {"wert": wert, "fundstelle": _fund(nr, seite, zeile)}

    # 1. Beschriftete Felder; der Wert steht dahinter oder in der nächsten Zeile.
    for i, (nr, seite, zeile) in enumerate(kopf):
        if not (m := _LABEL.match(zeile)):
            continue
        label, wert = m.group("label").lower().rstrip("."), m.group("wert").strip()
        if not wert and i + 1 < len(kopf) and not _LABEL.match(kopf[i + 1][2]):
            nr, seite, wert = kopf[i + 1][0], kopf[i + 1][1], kopf[i + 1][2]
            zeile = f"{zeile} {wert}"
        if label == "gericht":
            setze("gericht", gericht_kurz(wert), nr, seite, zeile)
        elif label in ("entscheidungsdatum", "datum", "verkündet am"):
            setze("datum", _datum(wert), nr, seite, zeile)
        elif label in ("aktenzeichen", "az", "geschäftszeichen"):
            az = re.match(_AKTENZEICHEN, wert)
            setze("aktenzeichen", " ".join(az.group("az").split()) if az else None, nr, seite, zeile)
        elif label in ("dokumenttyp", "entscheidungsart", "typ", "entscheidungsform"):
            setze("art", _art(wert), nr, seite, zeile)

    # 2. Zitierzeile im Kopf, z. B. bei beck-online.
    for nr, seite, zeile in kopf[:25]:
        if z := next((z for z in finde_urteilszitate(zeile) if z.aktenzeichen), None):
            setze("gericht", z.gericht, nr, seite, zeile)
            setze("aktenzeichen", z.aktenzeichen, nr, seite, zeile)
            setze("datum", z.datum, nr, seite, zeile)
            setze("art", z.art, nr, seite, zeile)
            break

    # 3. Kopf einer Ausfertigung: Gericht, Art und Aktenzeichen je in eigener Zeile, „Verkündet am …“.
    for nr, seite, zeile in kopf[:30]:
        if ergebnis["gericht"] is None and len(zeile) <= 80:
            setze("gericht", gericht_kurz(zeile), nr, seite, zeile)
        if ergebnis["art"] is None:
            setze("art", _art(zeile), nr, seite, zeile)
        if ergebnis["aktenzeichen"] is None and (m := _NUR_AZ.match(zeile)):
            setze("aktenzeichen", " ".join(m.group("az").split()), nr, seite, zeile)
    # Ohne Überschrift: die Tenorformel verrät die Art („… für Recht erkannt“, „… beschlossen:“).
    for nr, seite, zeile in kopf:
        if ergebnis["art"] is not None:
            break
        if m := _FORMEL.search(zeile):
            setze("art", "Urteil" if m.group(0).lower().startswith("für recht") else "Beschluss", nr, seite, zeile)
    if ergebnis["datum"] is None and (d := datumszeile.aus_text((nr, seite, z) for nr, seite, z in kopf)):
        ergebnis["datum"] = {"wert": d["datum"], "fundstelle": _fund(d["abschnitt"], d["seite"], d["text"])}

    # Quelle: Datenbankvermerk irgendwo im Text (Kopf- oder Fußzeile des Ausdrucks).
    for nr, seite, text in abschnitte:
        if treffer := next(((name, m) for name, muster in _HERKUNFT if (m := muster.search(text))), None):
            name, m = treffer
            setze("herkunft", name, nr, seite, text[max(0, m.start() - 40):m.end() + 40].strip())
            break
    return ergebnis


def _datum(text: str) -> str | None:
    if m := re.search(r"\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4}", text):
        return _iso(m.group(0))
    if d := datumszeile.aus_text([(0, None, f"Datum: {text}")]):
        return d["datum"]
    return None
