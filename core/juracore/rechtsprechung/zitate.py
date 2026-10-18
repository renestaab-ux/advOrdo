"""Erkennung von Rechtsprechungszitaten wie „BGH, Urteil vom 12.10.2016 – VIII ZR 103/15“.

Erkannt werden die in Schriftsätzen üblichen Formen:

- mit Entscheidungsart und Datum: „BGH, Urt. v. 12.10.2016 - VIII ZR 103/15“
- ohne Datum: „BGH, VIII ZR 103/15“, „OLG München, 14 U 1068/25 e“
- Gericht mit Ort: „AG Kleve, Urteil vom 20.07.1998 - 3 C 239/98“
- europäische Gerichte: „EuGH, Urteil vom 04.06.2015 – C-497/13 „Faber““
- nur mit Zeitschriftenfundstelle: „BGH NJW 2017, 1093“ (ohne Aktenzeichen nicht prüfbar)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Bundesgerichte und europäische Gerichte stehen ohne Ort; andere Gerichte mit Ort („OLG Hamm“).
_OHNE_ORT = r"BVerfG|BGH|BAG|BSG|BFH|BVerwG|BPatG|GmS-OGB|EuGH|EuG|EGMR|BayObLG|RG"
_MIT_ORT = r"OLG|LG|AG|KG|OVG|VGH|VG|LAG|ArbG|LSG|SG|FG"
_ORT = (
    r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
    r"(?:\s(?:am|an\sder|im|in|i\.\s?Br\.|a\.\s?M\.)(?:\s[A-ZÄÖÜ][a-zäöüß]+)?)?"
)
_GERICHT = rf"(?P<gericht>(?:{_OHNE_ORT})\b|KG\b|(?:{_MIT_ORT})\s(?P<ort>{_ORT}))"
_ART = (
    r"(?P<art>Urteil|Urt\.|Beschluss|Beschl\.|Versäumnisurteil|VU|Teilurteil|Endurteil|Hinweisbeschluss"
    r"|Gerichtsbescheid|Kammerbeschluss)"
)
_DATUM = r"(?P<datum>\d{1,2}\.\s?\d{1,2}\.\s?(?:\d{4}|\d{2}))"
# Deutsches Aktenzeichen: Spruchkörper (römisch oder arabisch), Registerzeichen, laufende Nummer/Jahr.
_AZ_DE = (
    r"(?:B\s\d+\s[A-Z]{1,3}\s\d+/\d{2}\s?[A-Z]{1,2}"  # BSG: „B 1 KR 2/20 R“
    r"|GmS-OGB\s\d+/\d{2}"  # Gemeinsamer Senat: „GmS-OGB 1/09“
    r"|(?:[IVX]+[a-z]?|\d{1,3}[a-z]?)\s(?:[A-Z][A-Za-z]{0,5})(?:\s\([A-Za-zÄÖÜäöü]+\))?\s\d{1,5}/\d{2,4}"
    r"(?:\s[a-z](?![a-zäöüß]))?)"
)
_AZ_EU = r"(?:[CT]-\d{1,4}/\d{2}(?:\sP)?)"
_AKTENZEICHEN = rf"(?P<az>{_AZ_EU}|{_AZ_DE})"

_MIT_AZ = re.compile(
    rf"{_GERICHT}"
    rf"(?:\s*,?\s*{_ART}\.?)?"
    rf"(?:\s*,?\s*(?:vom|v\.)?\s*{_DATUM})?"
    rf"\s*(?:,|–|-|—|\(|:)?\s*(?:Az\.?:?\s*)?"
    rf"{_AKTENZEICHEN}"
)
_ZEITSCHRIFTEN = r"BGHZ|BVerfGE|BAGE|BSGE|BFHE|BVerwGE|NJW-RR|NJW|NZM|NZBau|NZA|ZIP|MDR|DAR|VersR|WM|BB|DB|JZ|FamRZ"
_NUR_FUNDSTELLE = re.compile(
    rf"(?:{_GERICHT})\s*,?\s*(?P<fundstelle>(?:{_ZEITSCHRIFTEN})\s\d{{1,4}},\s*\d{{1,5}})"
)

ARTEN = {"Urt.": "Urteil", "Beschl.": "Beschluss", "VU": "Versäumnisurteil"}

# Zitierte Randnummer hinter dem Aktenzeichen: „…, Rn. 22“, „…, NJW 2017, 1093 Rn. 22“, „juris Rz. 7“.
_RN = re.compile(r"\b(?:Rn|Rdnr|Rdn|Rz|Tz)\.?\s*(\d{1,4})\b")
# Ende des Zitats: Semikolon, Klammer zu, Zeilenende oder Satzende vor einem neuen Satz.
_ZITAT_ENDE = re.compile(r"[;)\n]|\.\s+[A-ZÄÖÜ]")


@dataclass(frozen=True)
class UrteilsZitat:
    gericht: str  # „BGH“, „OLG München“
    aktenzeichen: str | None  # „VIII ZR 103/15“; None bei bloßer Zeitschriftenfundstelle
    datum: str | None = None  # ISO „2016-10-12“
    art: str | None = None  # „Urteil“, „Beschluss“ …
    fundstelle: str | None = None  # „NJW 2017, 1093“
    treffer: tuple[int, int] = (0, 0)
    rn: int | None = None  # zitierte Randnummer, z. B. 22 bei „…, Rn. 22“

    @property
    def gerichtstyp(self) -> str:
        return self.gericht.split()[0]

    def __str__(self) -> str:
        teile = [self.gericht]
        if self.art or self.datum:
            teile.append(" ".join(filter(None, [self.art, f"vom {_anzeige(self.datum)}" if self.datum else None])))
        kopf = ", ".join(teile)
        if self.aktenzeichen:
            return f"{kopf} – {self.aktenzeichen}"
        return f"{kopf}, {self.fundstelle}"


def _iso(datum: str | None) -> str | None:
    if not datum:
        return None
    t, m, j = (int(x) for x in re.findall(r"\d+", datum))
    if j < 100:
        j += 2000 if j < 50 else 1900
    if not (1 <= t <= 31 and 1 <= m <= 12):
        return None
    return f"{j:04d}-{m:02d}-{t:02d}"


def _anzeige(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def normalisiere_az(az: str) -> str:
    """Vergleichsform eines Aktenzeichens: Leerraum vereinheitlicht, Groß- und Kleinschreibung egal."""
    az = re.sub(r"\s*/\s*", "/", az)
    az = re.sub(r"\s*-\s*", "-", az)
    return " ".join(az.split()).casefold()


def az_kern(az: str) -> str:
    """Vergleichsform ohne das Kennzeichen elektronischer Akten („14 U 2300/25 e“ = „14 U 2300/25“)."""
    return re.sub(r"/(\d{2,4}) e$", r"/\1", normalisiere_az(az))


def _zitierte_rn(text: str, ende: int) -> int | None:
    """Randnummer, die unmittelbar hinter einem Zitat angegeben ist (bis Semikolon, Klammer oder Satzende)."""
    rest = text[ende:ende + 80]
    if m := _ZITAT_ENDE.search(rest):
        rest = rest[:m.start()]
    m = _RN.search(rest)
    return int(m.group(1)) if m else None


def finde_urteilszitate(text: str) -> list[UrteilsZitat]:
    zitate: list[UrteilsZitat] = []
    belegt: list[tuple[int, int]] = []
    for m in _MIT_AZ.finditer(text):
        gericht = " ".join(m.group("gericht").split())
        art = m.group("art")
        zitate.append(UrteilsZitat(
            gericht=gericht,
            aktenzeichen=" ".join(m.group("az").split()),
            datum=_iso(m.group("datum")),
            art=ARTEN.get(art, art) if art else None,
            treffer=(m.start(), m.end()),
            rn=_zitierte_rn(text, m.end()),
        ))
        belegt.append((m.start(), m.end()))
    for m in _NUR_FUNDSTELLE.finditer(text):
        if any(s <= m.start() < e for s, e in belegt):
            continue
        zitate.append(UrteilsZitat(
            gericht=" ".join(m.group("gericht").split()),
            aktenzeichen=None,
            fundstelle=" ".join(m.group("fundstelle").split()),
            treffer=(m.start(), m.end()),
        ))
    return sorted(zitate, key=lambda z: z.treffer)
