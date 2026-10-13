"""Angaben im Text erkennen: Daten, Beträge, Kilometer und Fehlercodes samt dem Merkmal, zu dem sie gehören.

Eine *Angabe* ist ein Wert mit seinem Bezug, z. B. „Kaufpreis: 14.900,00 €“ oder
„Übergabe: 18.03.2025“. Erkannt wird regelbasiert und bewusst zurückhaltend:
Ein Wert zählt nur, wenn ein Merkmalswort (der *Kopf*, z. B. „Kaufpreis“) nah
genug davor steht und kein anderer Wert derselben Art dazwischen liegt. Werte,
die im Text verneint oder bestritten werden („betrug nicht 64.800 km“,
„Bestritten wird, dass …“), sind keine eigene Angabe des Dokuments und bleiben
außen vor. Lieber eine Angabe übersehen als eine falsche Gegenüberstellung
behaupten.

Inhaltliche Aussagen ohne Zahl oder Datum („lehnt die Nachbesserung ab“ gegen
„hat Nachbesserung angeboten“) erkennt dieser Schritt nicht; das bleibt dem
späteren Abgleich mit dem Sprachmodell vorbehalten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# --- Werte ----------------------------------------------------------------------------------------

MONATE = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7,
    "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}  # fmt: skip
_MONATSNAME = "|".join(MONATE)

_DATUM = re.compile(r"(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})(?![\d.]*\d)")
_DATUM_AUSGESCHRIEBEN = re.compile(rf"(?<![\d.])(\d{{1,2}})\.\s+({_MONATSNAME})\s+(\d{{4}})\b", re.I)
_MONAT = re.compile(rf"\b(?:(Anfang|Mitte|Ende)\s+)?({_MONATSNAME})\s+(\d{{4}})\b", re.I)
_ZAHL = r"\d{1,3}(?:\.\d{3})+|\d+"
_BETRAG = re.compile(rf"(?<![\d.,])({_ZAHL})(?:,(\d{{2}}|-))?\s?(?:€|EUR\b|Euro\b)")
_BETRAG_VORN = re.compile(rf"(?:€|EUR)\s?({_ZAHL})(?:,(\d{{2}}|-))?(?![\d.,]*\d)")
_KM = re.compile(rf"(?<![\d.,])({_ZAHL})\s?km\b")
_FEHLERCODE = re.compile(r"\b[PBCU][0-9A-F]{4}\b")
_KEIN_EINTRAG = re.compile(r"\bkein(?:en)?\s+(?:Fehler)?[Ee]intrag\b|\bkeine\s+(?:Fehler)?[Ee]inträge\b")

# Arten von Werten. Ein Merkmal der Art "datum" nimmt auch Monatsangaben ("Mitte Juni 2025").
DATUM = "datum"
MONAT = "monat"
BETRAG = "betrag"
KM = "km"
CODE = "code"


@dataclass
class Wert:
    art: str
    wert: str  # normalisiert, z. B. "2025-03-18", "14900.00", "68400", "P17BF", "2025-06"
    start: int
    ende: int
    verneint: bool = False


def _jahr(text: str) -> int:
    jahr = int(text)
    return jahr + 2000 if jahr < 100 else jahr


def _iso(tag: int, monat: int, jahr: int) -> str | None:
    try:
        return date(jahr, monat, tag).isoformat()
    except ValueError:
        return None


def _zahl(text: str) -> int:
    return int(text.replace(".", ""))


def finde_werte(text: str) -> list[Wert]:
    """Alle Werte im Text, nach Position geordnet. Überlappende Treffer: der zuerst gefundene gilt."""
    werte: list[Wert] = []
    belegt: list[tuple[int, int]] = []

    def neu(art: str, wert: str | None, m: re.Match) -> None:
        if wert is None or any(m.start() < e and s < m.end() for s, e in belegt):
            return
        belegt.append((m.start(), m.end()))
        werte.append(Wert(art, wert, m.start(), m.end()))

    for m in _DATUM.finditer(text):
        neu(DATUM, _iso(int(m[1]), int(m[2]), _jahr(m[3])), m)
    for m in _DATUM_AUSGESCHRIEBEN.finditer(text):
        neu(DATUM, _iso(int(m[1]), MONATE[m[2].lower()], int(m[3])), m)
    for m in _MONAT.finditer(text):
        neu(MONAT, f"{int(m[3]):04d}-{MONATE[m[2].lower()]:02d}", m)
    for m in (*_BETRAG.finditer(text), *_BETRAG_VORN.finditer(text)):
        cent = m[2] if m[2] and m[2] != "-" else "00"
        neu(BETRAG, f"{_zahl(m[1])}.{cent}", m)
    for m in _KM.finditer(text):
        neu(KM, str(_zahl(m[1])), m)
    for m in _FEHLERCODE.finditer(text):
        neu(CODE, m[0], m)
    for m in _KEIN_EINTRAG.finditer(text):
        neu(CODE, "kein Eintrag", m)
    return sorted(werte, key=lambda w: w.start)


def vereinbar(art_a: str, a: str, art_b: str, b: str) -> bool:
    """Ob zwei Werte desselben Merkmals zusammenpassen. Ein Monat passt zu jedem Datum in diesem Monat."""
    if a == b:
        return True
    if MONAT in (art_a, art_b) and DATUM in (art_a, art_b):
        monat, datum = (a, b) if art_a == MONAT else (b, a)
        return datum.startswith(monat + "-")
    return False


def anzeige(art: str, wert: str) -> str:
    """Normalisierten Wert lesbar machen, z. B. für Überschriften der Gegenüberstellung."""
    if art == DATUM:
        j, m, t = wert.split("-")
        return f"{t}.{m}.{j}"
    if art == MONAT:
        j, m = wert.split("-")
        name = next(n for n, nr in MONATE.items() if nr == int(m) and n != "jänner")
        return f"{name.capitalize()} {j}"
    if art == BETRAG:
        euro, cent = wert.split(".")
        return f"{int(euro):,}".replace(",", ".") + f",{cent} €"
    if art == KM:
        return f"{int(wert):,}".replace(",", ".") + " km"
    return wert


# --- Merkmale -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Merkmal:
    schluessel: str
    titel: str
    art: str  # DATUM (nimmt auch MONAT), BETRAG, KM, CODE
    kopf: re.Pattern
    danach: int = 60  # so viele Zeichen hinter dem Kopf darf der Wert beginnen
    davor: int = 0  # so viele Zeichen vor dem Kopf darf der Wert enden ("am 18.03.2025 übergeben")
    praefix: re.Pattern | None = None  # muss unmittelbar vor dem Wert stehen, z. B. "bis zum"
    kontext: re.Pattern | None = None  # muss im Satz (bzw. Teilsatz) vorkommen
    kontext_im_teilsatz: bool = False  # Kontext nur im Teilsatz des Kopfes (bis zum nächsten ";")
    kontext_im_vorsatz: bool = False  # Kontext darf auch im vorigen Satz stehen ("Hierfür setzen wir eine Frist …")
    ausschluss: re.Pattern | None = None  # Teilsatz des Kopfes darf das nicht enthalten


def _re(muster: str) -> re.Pattern:
    return re.compile(muster)


_BIS = _re(r"\bbis\s+(?:zum\s+|spätestens\s+(?:zum\s+|am\s+)?|einschließlich\s+)?$")

MERKMALE: list[Merkmal] = [
    Merkmal("kaufpreis", "Kaufpreis", BETRAG, _re(r"\bKaufpreis(?:es)?\b|\b(?:zum|zu einem) Preis von\b"), danach=45),
    Merkmal(
        "uebergabe",
        "Übergabe / Gefahrübergang",
        DATUM,
        _re(r"\b(?:Gefahrübergang(?:s|es)?|Übergabe|übergeben|Ablieferung|abgeliefert)\b"),
        danach=30,
        davor=60,
        praefix=_re(r"\bam\s+$"),
    ),
    Merkmal(
        "kilometerstand_uebergabe",
        "Kilometerstand bei Übergabe",
        KM,
        _re(r"\bKilometerstand\b|\bLaufleistung\b|\bbei (?:der )?Übergabe\b"),
        danach=90,
        kontext=_re(r"Übergabe|übergeben|Ablieferung|laut Tacho"),
        kontext_im_teilsatz=True,
        ausschluss=_re(
            r"\baktuell|\bderzeit|\bheute\b|\bSchluss der mündlichen|\bGesamtlaufleistung|\bRestlaufleistung"
        ),
    ),
    Merkmal("gesamtlaufleistung", "Gesamtlaufleistung", KM, _re(r"\bGesamtlaufleistung\b"), danach=90),
    Merkmal(
        "erste_maengelanzeige",
        "Erste Mängelanzeige",
        DATUM,
        _re(r"\berstmal(?:s|ig)\b|\bzum ersten Mal\b"),
        danach=40,
        kontext=_re(r"angezeigt|gerügt|gemeldet|beschwert|beanstandet|Mängelanzeige|Mangelanzeige|mitgeteilt"),
    ),
    Merkmal(
        "frist_nacherfuellung",
        "Frist zur Nacherfüllung",
        DATUM,
        _re(r"\bFrist(?:setzung)?\b"),
        danach=40,
        praefix=_BIS,
        kontext=_re(r"Nachbesserung|Nacherfüllung|Nachlieferung|Mängelbeseitigung|Mangel\w* \w* ?zu beseitigen"),
        kontext_im_vorsatz=True,
    ),
    Merkmal(
        "frist_zahlung",
        "Zahlungsfrist",
        DATUM,
        _re(r"\bFrist(?:setzung)?\b"),
        danach=40,
        praefix=_BIS,
        kontext=_re(r"Rückzahlung|Zahlung|zahlen|erstatten|Erstattung|Ausgleich"),
        kontext_im_vorsatz=True,
    ),
    Merkmal(
        "reparaturkosten",
        "Reparaturkosten",
        BETRAG,
        _re(r"\bReparaturkosten\b|\bMängelbeseitigungskosten\b|\bKosten der (?:Reparatur|Mängelbeseitigung)\b"),
        danach=60,
    ),
    Merkmal("streitwert", "Streitwert", BETRAG, _re(r"\bStreitwert\b"), danach=30),
    Merkmal("fehlerspeicher", "Fehlerspeicher", CODE, _re(r"\bFehlerspeicher\w*"), danach=90),
]

# Datum eines bestimmten Vertrags: "Kaufvertrag vom 14.03.2025", "Projektsteuerungsvertrags vom 15.03.2019".
# Der Vertragsname wird Teil des Merkmals, damit verschiedene Verträge nicht vermischt werden.
_VERTRAG_VOM = re.compile(r"\b([A-ZÄÖÜ][a-zäöüß]+vertrag)(?:e?s)?\s+vom\s+$")

_ANLAGE_DANACH = re.compile(r"[\s—–\-,(]*Anlage\s+([A-Z]{1,2}\s?\d+)\b")
_ANLAGE_DAVOR = re.compile(r"(?:^|\s)(?:Anlage\s+)?([A-Z]{1,2}\s?\d+)\s+$")

# Wer etwas bestreitet, gibt die Angabe der Gegenseite wieder, nicht eine eigene.
_BESTREITEN = re.compile(r"\bbestritten\b|\bbestreite[tn]?\b|\bunzutreffend ist\b", re.I)
_VERNEINUNG = re.compile(r"\bnicht\b|\bnie(?:mals)?\b|\bkein\w*\b", re.I)
_TEILSATZGRENZE = re.compile(r";|,\s|\bsondern\b|\(|\)")

# Abkürzungen, nach denen ein Punkt keinen Satz beendet.
_ABKUERZUNGEN = {
    "abs", "nr", "rn", "s", "art", "dr", "prof", "dipl", "ing", "vgl", "z", "b", "ca", "bzw", "ggf", "inkl",
    "zzgl", "ziff", "az", "gem", "u", "a", "d", "h", "i", "v", "m", "hr", "fr", "hrn", "str", "bzgl", "lit",
    "anl", "bl", "f", "ff", "rdnr", "rz", "st", "sog", "evtl", "max", "min", "mio", "mrd", "tsd", "co", "kg",
}  # fmt: skip


@dataclass
class Angabe:
    merkmal: str
    titel: str
    art: str
    wert: str
    start: int  # Wert im Text
    ende: int
    satz_start: int  # Satz, in dem der Wert steht
    satz_ende: int
    anlage: str | None = None  # bei Verträgen: die Anlage, als die er vorgelegt ist ("K 18")


def saetze(text: str) -> list[tuple[int, int]]:
    """Zerlegt Text in Sätze (Start, Ende). Leerzeilen sind immer Grenzen; Abkürzungen und Zahlen nicht."""
    grenzen: list[tuple[int, int]] = []
    for block in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]*)*", text):
        start = block.start()
        for m in re.finditer(r"[.!?](?=\s+[„\"(]?[A-ZÄÖÜ0-9])", block[0]):
            pos = block.start() + m.start()
            wort = re.search(r"([A-Za-zÄÖÜäöüß]+|\d+)$", text[start:pos])
            # Ordnungszahlen ("3. Zivilkammer", "1. Kaufgegenstand") beenden keinen Satz, Jahreszahlen schon.
            if wort and (wort[1].lower() in _ABKUERZUNGEN or (wort[1].isdigit() and len(wort[1]) <= 2)):
                continue
            grenzen.append((start, pos + 1))
            start = pos + 1
        if text[start : block.end()].strip():
            grenzen.append((start, block.end()))
    return [(s + len(text[s:e]) - len(text[s:e].lstrip()), e) for s, e in grenzen if text[s:e].strip()]


def _teilsatz(satz: str, pos: int) -> tuple[int, int]:
    start, ende = 0, len(satz)
    for m in _TEILSATZGRENZE.finditer(satz):
        if m.end() <= pos:
            start = m.end()
        elif m.start() >= pos:
            ende = m.start()
            break
    return start, ende


def _semikolon_teil(satz: str, pos: int) -> tuple[int, int]:
    start = satz.rfind(";", 0, pos) + 1
    ende = satz.find(";", pos)
    return start, len(satz) if ende < 0 else ende


def _ist_verneint(satz: str, w: Wert) -> bool:
    s, e = _teilsatz(satz, w.start)
    teil = satz[s : w.start] + " " + satz[w.ende : e]
    return bool(_VERNEINUNG.search(teil))


def _passt_art(merkmal_art: str, wert_art: str) -> bool:
    return merkmal_art == wert_art or (merkmal_art == DATUM and wert_art == MONAT)


def _kandidat(m: Merkmal, satz: str, vorsatz: str, werte: list[Wert], w: Wert, mit_vorsatz: bool):
    """Bester Kopf dieses Merkmals für den Wert als (Abstand, Kontextabstand) oder None."""
    if m.praefix and not m.praefix.search(satz[max(0, w.start - 40) : w.start]):
        return None
    bester = None
    for k in m.kopf.finditer(satz):
        if k.end() <= w.start:
            abstand, von, bis = w.start - k.end(), k.end(), w.start
            if abstand > m.danach:
                continue
        elif k.start() >= w.ende:
            abstand, von, bis = k.start() - w.ende, w.ende, k.start()
            if abstand > m.davor:
                continue
        else:
            continue
        # Kein anderer (nicht verneinter) Wert derselben Art zwischen Kopf und Wert.
        if any(_passt_art(m.art, x.art) and not x.verneint and von <= x.start < bis for x in werte if x is not w):
            continue
        if m.ausschluss:
            s, e = _semikolon_teil(satz, k.start())
            if m.ausschluss.search(satz[s:e]):
                continue
        kontext_abstand = 0
        if m.kontext:
            s, e = _semikolon_teil(satz, k.start()) if m.kontext_im_teilsatz else (0, len(satz))
            treffer = [abs(t.start() - w.start) for t in m.kontext.finditer(satz, s, e)]
            if not treffer and mit_vorsatz and m.kontext_im_vorsatz and m.kontext.search(vorsatz):
                treffer = [len(satz) + 1]
            if not treffer:
                continue
            kontext_abstand = min(treffer)
        if bester is None or (abstand, kontext_abstand) < bester:
            bester = (abstand, kontext_abstand)
    return bester


def finde_angaben(text: str) -> list[Angabe]:
    """Alle Angaben im Text, nach Position geordnet."""
    angaben: list[Angabe] = []
    vorsatz = ""
    for s_start, s_ende in saetze(text):
        satz = text[s_start:s_ende]
        if _BESTREITEN.search(satz):
            vorsatz = satz
            continue
        werte = finde_werte(satz)
        for w in werte:
            # "kein Eintrag" ist selbst eine Verneinung und als Wert gemeint.
            w.verneint = w.wert != "kein Eintrag" and _ist_verneint(satz, w)
        for w in werte:
            if w.verneint:
                continue
            treffer = _vertrag(satz, w)
            if treffer is None:
                treffer = _merkmal_fuer(satz, vorsatz, werte, w)
            if treffer is None:
                continue
            schluessel, titel, anlage = treffer
            angaben.append(
                Angabe(schluessel, titel, w.art, w.wert, s_start + w.start, s_start + w.ende, s_start, s_ende, anlage)
            )
        vorsatz = satz
    return angaben


def _vertrag(satz: str, w: Wert) -> tuple[str, str, str | None] | None:
    if w.art != DATUM:
        return None
    vorher = satz[max(0, w.start - 80) : w.start]
    m = _VERTRAG_VOM.search(vorher)
    if not m:
        return None
    name = m[1]
    # "Generalplanervertrag vom 12.11.2019 — Anlage K 18" oder im Anlagenverzeichnis "K 18 Generalplanervertrag vom …"
    anlage = _ANLAGE_DANACH.match(satz, w.ende) or _ANLAGE_DAVOR.search(vorher, 0, m.start())
    return f"vertrag:{name.lower()}", f"{name} vom", re.sub(r"\s+", " ", anlage[1]) if anlage else None


def _merkmal_fuer(satz: str, vorsatz: str, werte: list[Wert], w: Wert) -> tuple[str, str, None] | None:
    for mit_vorsatz in (False, True):
        kandidaten = []
        for m in MERKMALE:
            if not _passt_art(m.art, w.art):
                continue
            if (k := _kandidat(m, satz, vorsatz, werte, w, mit_vorsatz)) is not None:
                kandidaten.append((k, m))
        if kandidaten:
            kandidaten.sort(key=lambda km: km[0])
            # Zwei Merkmale gleich nah: lieber keine Zuordnung als eine geratene.
            if len(kandidaten) > 1 and kandidaten[0][0] == kandidaten[1][0]:
                return None
            m = kandidaten[0][1]
            return m.schluessel, m.titel, None
    return None
