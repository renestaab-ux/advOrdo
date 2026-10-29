"""Kostennote aus der Akte: Vorschuss (§ 9 RVG) oder Berechnung der Vergütung (§ 10 RVG) als Word-Datei.

Die Wertgebühren rechnet der Prozesskostenrechner (§ 13 RVG, Fassung nach dem Tag des unbedingten Auftrags,
§ 60 RVG). Die Kostennote nennt je Posten die Nummer des Vergütungsverzeichnisses, den kurzen Gebührentatbestand,
den Gegenstandswert und den Betrag (§ 10 Abs. 2 RVG) sowie die Angaben einer Rechnung nach § 14 Abs. 4 UStG:
Steuernummer oder USt-IdNr. des Absenders, fortlaufende Rechnungsnummer, Leistungszeitraum, Entgelt, Steuersatz und
Steuerbetrag. Gezahlte Vorschüsse werden mit der darin enthaltenen Umsatzsteuer abgezogen (§ 14 Abs. 5 S. 2 UStG).

Posten einer Kostennote:
- ``gebuehr``: Wertgebühr nach VV RVG (Nummer aus ``GEBUEHREN``, Satz, wahlweise eigener Gegenstandswert).
- ``auslage``: Auslage mit Betrag, z. B. Nr. 7000 (Kopien) oder Nr. 7003 (Fahrtkosten); wahlweise ohne Umsatzsteuer
  (durchlaufender Posten, § 10 Abs. 1 S. 6 UStG).
- ``stunden``: Zeitaufwand × Stundensatz aus einer Vergütungsvereinbarung (§ 3a RVG). Aus der Zeiterfassung kommen
  zusätzlich ``minuten`` (getaktet; der Betrag wird dann genau aus den Minuten gerechnet) und ``quelle`` (die
  Zeiteinträge, die eine Kostennote als abgerechnet kennzeichnet und ein Storno wieder freigibt).

Jede vergebene Rechnungsnummer bleibt in der Tabelle ``kostennote`` stehen, auch wenn die Akte gelöscht oder die
Rechnung storniert wird; so wird keine Nummer zweimal vergeben.
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .. import zeiterfassung
from ..aktenverwaltung import stammdaten
from ..dokumente import akte as akten
from ..eigene import daten as eigene
from ..rechner.prozesskosten import (
    FASSUNGEN,
    HOECHSTWERT,
    MEHRVERTRETUNG_HOECHST,
    MEHRVERTRETUNG_SATZ,
    PAUSCHALE_HOECHST,
    PAUSCHALE_SATZ,
    gebuehr,
    wertgebuehr,
)
from ..rechner.verzugszinsen import betrag, cent
from . import fuellen, grundvorlagen, platzhalter
from .grundvorlagen import _anschriftfeld, _lauf, _p, _text, _unterschrift
from .vorlagen import _UNZULAESSIG, HERKUNFT

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kostennote (
    id          INTEGER PRIMARY KEY,
    akte_id     INTEGER NOT NULL,           -- ohne Fremdschlüssel: die Nummer bleibt vergeben, auch ohne Akte
    nummer      TEXT NOT NULL UNIQUE,
    art         TEXT NOT NULL,              -- vorschuss | rechnung
    datum       TEXT NOT NULL,
    eingabe     TEXT NOT NULL,              -- JSON
    ergebnis    TEXT NOT NULL,              -- JSON
    brutto      TEXT NOT NULL,
    zahlbetrag  TEXT NOT NULL,
    dokument_id INTEGER,
    angelegt_am TEXT NOT NULL,
    storniert_am TEXT
);
CREATE INDEX IF NOT EXISTS kostennote_akte ON kostennote(akte_id);
"""

ARTEN = {"vorschuss": "Vorschussrechnung", "rechnung": "Kostennote"}

# Angelegenheiten (§ 15 RVG): je Angelegenheit eine Pauschale Nr. 7002. Die Reihenfolge gilt auch in der Kostennote.
ANGELEGENHEITEN = {
    "aussergerichtlich": "Außergerichtliche Vertretung",
    "mahnverfahren": "Mahnverfahren",
    "erste": "Gerichtliches Verfahren, erste Instanz",
    "berufung": "Berufungsverfahren",
}

# Nr. VV RVG: (Gebührentatbestand, Satz als Vorgabe, Angelegenheit, Erhöhung nach Nr. 1008 möglich, Rahmen)
GEBUEHREN: dict[str, tuple[str, Decimal, str, bool, tuple[Decimal, Decimal] | None]] = {
    "2300": ("Geschäftsgebühr", Decimal("1.3"), "aussergerichtlich", True, (Decimal("0.5"), Decimal("2.5"))),
    "1000": ("Einigungsgebühr", Decimal("1.5"), "aussergerichtlich", False, None),
    "3305": ("Verfahrensgebühr Mahnverfahren", Decimal("1.0"), "mahnverfahren", True, None),
    "3308": ("Verfahrensgebühr Vollstreckungsbescheid", Decimal("0.5"), "mahnverfahren", False, None),
    "3100": ("Verfahrensgebühr", Decimal("1.3"), "erste", True, None),
    "3101": ("Verfahrensgebühr bei vorzeitiger Beendigung", Decimal("0.8"), "erste", True, None),
    "3104": ("Terminsgebühr", Decimal("1.2"), "erste", False, None),
    "1003": ("Einigungsgebühr, Verfahren anhängig", Decimal("1.0"), "erste", False, None),
    "3200": ("Verfahrensgebühr Berufung", Decimal("1.6"), "berufung", True, None),
    "3202": ("Terminsgebühr Berufung", Decimal("1.2"), "berufung", False, None),
    "1004": ("Einigungsgebühr, Berufung anhängig", Decimal("1.3"), "berufung", False, None),
}
# Auf diese Verfahrensgebühren wird die Geschäftsgebühr angerechnet (Vorbem. 3 Abs. 4 VV RVG).
ANRECHNUNG_AUF = ("3305", "3100", "3101")

AUSLAGEN = {
    "7000": "Dokumentenpauschale",
    "7003": "Fahrtkosten eigenes Kfz",
    "7004": "Fahrtkosten andere Verkehrsmittel",
    "7005": "Tage- und Abwesenheitsgeld",
    "7006": "Sonstige Auslagen anlässlich einer Geschäftsreise",
    "": "Sonstige Auslage",
}

MUSTER_VORGABE = "{JJJJ}-{NNNN}"


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    con.commit()


def _zahl(d: Decimal) -> str:
    return format(d.normalize(), "f").replace(".", ",")


def _satz_text(d: Decimal) -> str:
    """1,3 statt 1,30; 1,0 statt 1."""
    t = _zahl(d)
    return t if "," in t else t + ",0"


def katalog() -> dict:
    return {
        "gebuehren": [{"nr": nr, "text": t, "satz": str(s), "angelegenheit": a, "erhoehbar": e,
                       "rahmen": [str(r[0]), str(r[1])] if r else None} for nr, (t, s, a, e, r) in GEBUEHREN.items()],
        "auslagen": [{"nr": nr, "text": t} for nr, t in AUSLAGEN.items()],
        "angelegenheiten": ANGELEGENHEITEN,
        "anrechnung_auf": list(ANRECHNUNG_AUF),
        "fassungen": {k: v["titel"] for k, v in FASSUNGEN.items()},
        "arten": ARTEN,
    }


def fassung_fuer(auftrag: date) -> str:
    """Gebührentabelle nach dem Tag des unbedingten Auftrags (§ 60 Abs. 1 RVG)."""
    if auftrag >= date(2025, 6, 1):
        return "2025"
    if auftrag >= date(2021, 1, 1):
        return "2021"
    raise ValueError("Für Aufträge vor dem 01.01.2021 ist keine Gebührentabelle hinterlegt.")


def _datum(text: str | None, feld: str) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError as fehler:
        raise ValueError(f"{feld}: bitte ein Datum im Format JJJJ-MM-TT.") from fehler


def _betrag(wert, feld: str) -> Decimal:
    try:
        return betrag(wert)
    except (ValueError, ArithmeticError) as fehler:
        raise ValueError(f"{feld}: „{wert}“ ist kein Betrag.") from fehler


def _zeile(art: str, nr: str, text: str, betrag_: Decimal, wert: Decimal | None = None,
           satz: Decimal | None = None) -> dict:
    return {"art": art, "nr": nr, "text": text, "wert": None if wert is None else str(cent(wert)),
            "satz": None if satz is None else str(satz), "betrag": str(cent(betrag_))}


def berechne(e: dict) -> dict:
    """Rechnet eine Kostennote aus den Eingaben (ohne Datenbank); Beträge als Text mit Punkt."""
    hinweise: list[str] = []
    auftrag = _datum(e.get("auftrag"), "Auftrag erteilt am")
    fassung = e.get("fassung") or (fassung_fuer(auftrag) if auftrag else "2025")
    if fassung not in FASSUNGEN:
        raise ValueError(f"Unbekannte Fassung: {fassung}")
    if not auftrag and not e.get("fassung"):
        hinweise.append("Kein Auftragsdatum eingetragen: gerechnet mit der Gebührentabelle seit 01.06.2025 "
                        "(§ 60 RVG). Bitte „Auftrag erteilt am“ ausfüllen oder in den Stammdaten „Mandat seit“.")
    f = FASSUNGEN[fassung]
    grund = (_betrag(e["gegenstandswert"], "Gegenstandswert") if e.get("gegenstandswert") not in (None, "")
             else None)
    auftraggeber = max(1, int(e.get("auftraggeber") or 1))
    erhoehung = min(MEHRVERTRETUNG_SATZ * (auftraggeber - 1), MEHRVERTRETUNG_HOECHST)
    roh = e.get("umsatzsteuer", 19)  # ohne Angabe 19 %; leer, 0 oder false: ohne Umsatzsteuer
    ust = _betrag(roh, "Umsatzsteuer") if roh not in (None, "", False) else Decimal(0)

    def wert_von(p: dict) -> Decimal:
        w = _betrag(p["wert"], "Gegenstandswert") if p.get("wert") not in (None, "") else grund
        if w is None or w <= 0:
            raise ValueError("Bitte einen Gegenstandswert angeben (Stammdaten der Akte oder hier).")
        if w > HOECHSTWERT:
            hinweise.append("Gerechnet mit dem Höchstwert von 30 Mio. € (§ 22 Abs. 2 RVG).")
            return HOECHSTWERT
        return w

    gruppen: dict[str, list[dict]] = {k: [] for k in ANGELEGENHEITEN}
    weitere: list[dict] = []
    zeit: list[dict] = []
    steuerfrei: list[dict] = []
    geschaeft: tuple[Decimal, Decimal] | None = None  # (Satz, Wert) einer Geschäftsgebühr in dieser Kostennote
    verfahren: dict | None = None  # erste Verfahrensgebühr, auf die angerechnet werden kann

    for p in e.get("posten") or []:
        typ = p.get("typ", "gebuehr")
        if typ == "gebuehr":
            nr = str(p.get("nr", ""))
            if nr not in GEBUEHREN:
                raise ValueError(f"Unbekannte Gebühr: Nr. {nr} VV RVG")
            text, vorgabe, angelegenheit, erhoehbar, rahmen = GEBUEHREN[nr]
            satz = _betrag(p["satz"], f"Satz zu Nr. {nr}") if p.get("satz") not in (None, "") else vorgabe
            if rahmen and not rahmen[0] <= satz <= rahmen[1]:
                raise ValueError(f"Nr. {nr} VV RVG: Satz {_satz_text(satz)} liegt außerhalb des Rahmens "
                                 f"{_satz_text(rahmen[0])} bis {_satz_text(rahmen[1])}.")
            if nr == "2300" and satz > Decimal("1.3"):
                hinweise.append("Eine Geschäftsgebühr über 1,3 setzt eine umfangreiche oder schwierige Tätigkeit "
                                "voraus (Anm. zu Nr. 2300 VV RVG).")
            mehr = erhoehung if erhoehbar else Decimal(0)
            if mehr:
                text += f" ({_satz_text(satz)} + Erhöhung {_satz_text(mehr)} nach Nr. 1008)"
            wert = wert_von(p)
            voll = wertgebuehr(wert, *f["rvg"])
            z = _zeile("gebuehr", f"Nr. {nr}", text, gebuehr(satz + mehr, voll), wert, satz + mehr)
            gruppen[angelegenheit].append(z)
            if nr == "2300" and geschaeft is None:
                geschaeft = (satz + mehr, wert)
            if nr in ANRECHNUNG_AUF and verfahren is None:
                verfahren = z
        elif typ == "auslage":
            nr = str(p.get("nr") or "")
            text = (p.get("text") or "").strip() or AUSLAGEN.get(nr, "Auslage")
            z = _zeile("auslage", f"Nr. {nr}" if nr else "", text, _betrag(p.get("betrag") or 0, text))
            (weitere if p.get("ust", True) else steuerfrei).append(z)
        elif typ == "stunden":
            satz_euro = _betrag(p.get("stundensatz") or 0, "Stundensatz")
            text = (p.get("text") or "").strip() or "Tätigkeit"
            if p.get("minuten") not in (None, ""):
                minuten = int(p["minuten"])
                stunden = Decimal(minuten) / 60
                dauer = zeiterfassung.stunden_text(minuten)
            else:
                stunden = _betrag(p.get("stunden") or 0, "Stunden")
                dauer = _zahl(stunden)
            z = _zeile("stunden", "", f"{text} ({dauer} Std. × {platzhalter.euro(str(satz_euro))})",
                       stunden * satz_euro)
            z["stunden"], z["stundensatz"] = dauer, str(satz_euro)
            if p.get("quelle"):
                z["quelle"] = p["quelle"]
            zeit.append(z)
        else:
            raise ValueError(f"Unbekannte Art eines Postens: {typ!r}")

    # Anrechnung der Geschäftsgebühr: die Hälfte, höchstens 0,75, nach dem Wert, der in das gerichtliche Verfahren
    # übergegangen ist (Vorbem. 3 Abs. 4 VV RVG).
    a = e.get("anrechnung")
    if isinstance(a, dict):
        if verfahren is None:
            hinweise.append("Die Anrechnung der Geschäftsgebühr entfällt: keine Verfahrensgebühr (Nr. 3100, 3101 "
                            "oder 3305) in dieser Kostennote.")
        else:
            satz = _betrag(a["satz"], "Satz der Geschäftsgebühr") if a.get("satz") not in (None, "") else (
                geschaeft[0] if geschaeft else Decimal("1.3"))
            wert_g = (_betrag(a["wert"], "Wert der Geschäftsgebühr") if a.get("wert") not in (None, "") else
                      geschaeft[1] if geschaeft else Decimal(verfahren["wert"]))
            wert = min(wert_g, Decimal(verfahren["wert"]))
            anteil = min(satz / 2, Decimal("0.75"))
            abzug = min(cent(anteil * wertgebuehr(wert, *f["rvg"])), Decimal(verfahren["betrag"]))
            herkunft = f" aus Rechnung {a['nummer']}" if a.get("nummer") else ""
            z = _zeile("anrechnung", "Vorbem. 3 Abs. 4",
                       f"abzüglich {_satz_text(anteil)} Geschäftsgebühr{herkunft} (Anrechnung)", -abzug, wert, anteil)
            liste = next(g for g in gruppen.values() if verfahren in g)
            liste.insert(liste.index(verfahren) + 1, z)

    abschnitte = []
    for schluessel, titel in ANGELEGENHEITEN.items():
        zeilen = gruppen[schluessel]
        if not zeilen:
            continue
        summe = sum((Decimal(z["betrag"]) for z in zeilen), Decimal(0))
        if e.get("pauschale", True):
            pauschale = min(cent(max(summe, Decimal(0)) * PAUSCHALE_SATZ), PAUSCHALE_HOECHST)
            zeilen.append(_zeile("pauschale", "Nr. 7002", "Post- und Telekommunikationspauschale", pauschale))
        abschnitte.append({"titel": titel, "zeilen": zeilen})
    if zeit:
        abschnitte.append({"titel": "Zeitaufwand nach Vergütungsvereinbarung (§ 3a RVG)", "zeilen": zeit})
    if weitere:
        abschnitte.append({"titel": "Auslagen", "zeilen": weitere})
    if zeit and any(gruppen.values()):
        hinweise.append("Zeithonorar und Gebühren nach dem RVG zusammen in einer Kostennote: Zusätzliche gesetzliche "
                        "Gebühren (etwa Einigungsgebühr) neben dem Zeithonorar können gegenüber Verbrauchern die "
                        "Vereinbarung unwirksam machen (BGH IX ZR 65/23 nach Krumscheid in: Heidel/Pauly, "
                        "AnwaltFormulare, § 57; IWW Institut, FMP 2024, 189). Zulässig ist dagegen eine Klausel, "
                        "nach der im gerichtlichen Verfahren mindestens die gesetzlichen Gebühren geschuldet sind (BGH "
                        "IX ZR 90/23 nach BB 2025, 2893); dann wird entweder das Zeithonorar oder, wenn höher, die "
                        "gesetzliche Vergütung berechnet, nicht beides.")
    if not abschnitte and not steuerfrei:
        raise ValueError("Die Kostennote hat noch keine Posten.")

    netto = sum((Decimal(z["betrag"]) for a_ in abschnitte for z in a_["zeilen"]), Decimal(0))
    steuer = cent(netto * ust / 100) if ust else Decimal(0)
    frei = sum((Decimal(z["betrag"]) for z in steuerfrei), Decimal(0))
    brutto = netto + steuer + frei

    abzuege = []
    for x in e.get("abzuege") or []:
        b = _betrag(x.get("betrag") or 0, "Abzug")
        if not b:
            continue
        text = (x.get("text") or "").strip() or (f"Vorschuss Rechnung {x['nummer']}" if x.get("nummer") else
                                                  "Gezahlter Vorschuss")
        abzuege.append({"text": text, "nummer": x.get("nummer") or "", "betrag": str(cent(b)),
                        "ust": str(cent(b * ust / (100 + ust))) if ust else "0.00"})
    zahlbetrag = brutto - sum((Decimal(x["betrag"]) for x in abzuege), Decimal(0))
    if zahlbetrag < 0:
        hinweise.append("Die Vorschüsse übersteigen die Vergütung; der Rest ist zu erstatten.")

    return {
        "art": e.get("art") if e.get("art") in ARTEN else "rechnung",
        "fassung": fassung,
        "fassung_titel": f["titel"],
        "grundlage": f"§§ 2, 13 RVG {f['fundstelle']} mit Vergütungsverzeichnis (Anlage 1 RVG)",
        "abschnitte": abschnitte,
        "steuerfrei": steuerfrei,
        "netto": str(cent(netto)),
        "umsatzsteuer_satz": str(ust),
        "umsatzsteuer": str(cent(steuer)),
        "brutto": str(cent(brutto)),
        "abzuege": abzuege,
        "zahlbetrag": str(cent(zahlbetrag)),
        "hinweise": list(dict.fromkeys(hinweise)),
    }


# --------------------------------------------------------------------------- Rechnungsnummer


def _muster(con: sqlite3.Connection) -> str:
    s = eigene.stand(con, mit_archiv=False)
    m = ((s["organisation"] or {}).get("daten") or {}).get("rechnungsnummer_muster") or ""
    return m if re.search(r"\{N+\}", m) else MUSTER_VORGABE


def _muster_regex(muster: str, tag: date) -> tuple[re.Pattern, int]:
    teile = re.split(r"(\{JJJJ\}|\{JJ\}|\{N+\})", muster)
    regex, stellen = "", 1
    for t in teile:
        if t == "{JJJJ}":
            regex += str(tag.year)
        elif t == "{JJ}":
            regex += f"{tag.year % 100:02d}"
        elif re.fullmatch(r"\{N+\}", t):
            regex += r"(\d+)"
            stellen = len(t) - 2
        else:
            regex += re.escape(t)
    return re.compile(f"^{regex}$"), stellen


def naechste_nummer(con: sqlite3.Connection, tag: date | None = None) -> str:
    """Die nächste freie Nummer nach dem Muster aus Eigene Daten; die laufende Nummer beginnt jedes Jahr neu,
    wenn das Muster das Jahr enthält."""
    tag = tag or date.today()
    muster = _muster(con)
    regex, stellen = _muster_regex(muster, tag)
    hoechste = 0
    for (nummer,) in con.execute("SELECT nummer FROM kostennote"):
        if m := regex.match(nummer):
            hoechste = max(hoechste, int(m.group(1)))
    lauf = str(hoechste + 1).zfill(stellen)
    ergebnis = muster.replace("{JJJJ}", str(tag.year)).replace("{JJ}", f"{tag.year % 100:02d}")
    return re.sub(r"\{N+\}", lauf, ergebnis, count=1)


def _vergeben(con: sqlite3.Connection, nummer: str) -> bool:
    return con.execute("SELECT 1 FROM kostennote WHERE nummer = ?", (nummer,)).fetchone() is not None


# --------------------------------------------------------------------------- Akte


def _zeile_db(z: sqlite3.Row) -> dict:
    return {"id": z["id"], "nummer": z["nummer"], "art": z["art"], "art_text": ARTEN.get(z["art"], z["art"]),
            "datum": z["datum"], "brutto": z["brutto"], "zahlbetrag": z["zahlbetrag"], "dokument_id": z["dokument_id"],
            "storniert": z["storniert_am"] is not None, "storniert_am": z["storniert_am"]}


def liste(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    return [_zeile_db(z) for z in con.execute("SELECT * FROM kostennote WHERE akte_id = ? ORDER BY datum, id",
                                              (akte_id,))]


def vorschlag(con: sqlite3.Connection, akte_id: int, heute: date | None = None) -> dict:
    """Vorgaben für eine neue Kostennote dieser Akte: Gegenstandswert, Auftragsdatum, nächste Nummer, offene
    Vorschüsse und eine früher berechnete Geschäftsgebühr (zur Anrechnung)."""
    heute = heute or date.today()
    s = stammdaten.stammdaten(con, akte_id)
    zeilen = con.execute("SELECT * FROM kostennote WHERE akte_id = ? AND storniert_am IS NULL ORDER BY datum, id",
                         (akte_id,)).fetchall()
    verrechnet = {x.get("nummer") for z in zeilen if z["art"] == "rechnung"
                  for x in json.loads(z["eingabe"]).get("abzuege") or []}
    offen = [{"nummer": z["nummer"], "datum": z["datum"], "betrag": z["brutto"]} for z in zeilen
             if z["art"] == "vorschuss" and z["nummer"] not in verrechnet]
    geschaeft = None
    for z in zeilen:
        for a in json.loads(z["ergebnis"])["abschnitte"]:
            for p in a["zeilen"]:
                if p["nr"] == "Nr. 2300":
                    geschaeft = {"nummer": z["nummer"], "satz": p["satz"], "wert": p["wert"]}
    mandant = next((b for b in s["beteiligte"] if b["rolle"] == "mandant"), None)
    hinweise = []
    org = (eigene.stand(con, mit_archiv=False)["organisation"] or {}).get("daten") or {}
    if not (org.get("steuernummer") or org.get("ust_id")):
        hinweise.append("In Eigene Daten fehlt die Steuernummer oder USt-IdNr.; eine Rechnung muss eine davon "
                        "nennen (§ 14 Abs. 4 S. 1 Nr. 2 UStG).")
    if not org.get("iban"):
        hinweise.append("In Eigene Daten fehlt die Bankverbindung (IBAN).")
    if mandant is None:
        hinweise.append("Die Akte hat keinen Mandanten; die Kostennote braucht einen Rechnungsempfänger.")
    return {
        "nummer": naechste_nummer(con, heute),
        "muster": _muster(con),
        "datum": heute.isoformat(),
        "auftrag": s.get("mandat_seit") or "",
        "gegenstandswert": s.get("gegenstandswert") or "",
        "empfaenger_id": mandant["id"] if mandant else None,
        "offene_vorschuesse": offen,
        "geschaeftsgebuehr": geschaeft,
        "kostennoten": liste(con, akte_id),
        "hinweise": hinweise,
    }


# --------------------------------------------------------------------------- Word-Datei

_SPALTEN = (1550, 4280, 1300, 750, 1473)  # Nr. | Tatbestand | Wert | Satz | Betrag: zusammen die Satzbreite 165 mm


def _zelle(breite: int, text: str, rechts: bool = False, fett: bool = False, spanne: int = 1,
           linie: bool = False) -> str:
    rand = '<w:tcBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="808080"/></w:tcBorders>' if linie else ""
    span = f'<w:gridSpan w:val="{spanne}"/>' if spanne > 1 else ""
    return (f'<w:tc><w:tcPr><w:tcW w:w="{breite}" w:type="dxa"/>{span}{rand}</w:tcPr>'
            f"{_p(_lauf(text, fett=fett), stil='Tabelle', rechts=rechts)}</w:tc>")


def _reihe(*zellen: str) -> str:
    return f"<w:tr><w:trPr><w:cantSplit/></w:trPr>{''.join(zellen)}</w:tr>"


def _summe(text: str, betrag_: str, fett: bool = False, linie: bool = False) -> str:
    links = sum(_SPALTEN[:4])
    return _reihe(_zelle(links, text, fett=fett, spanne=4, linie=linie),
                  _zelle(_SPALTEN[4], platzhalter.euro(betrag_), rechts=True, fett=fett, linie=linie))


def _tabelle(r: dict) -> str:
    kopf = _reihe(*(_zelle(b, t, rechts=i >= 2, fett=True) for i, (b, t) in enumerate(
        zip(_SPALTEN, ("Nr. VV RVG", "Gebührentatbestand bzw. Auslage", "Wert", "Satz", "Betrag"), strict=True))))
    reihen = [kopf]
    for a in r["abschnitte"]:
        reihen.append(_reihe(_zelle(sum(_SPALTEN), a["titel"], fett=True, spanne=5)))
        for z in a["zeilen"]:
            reihen.append(_reihe(
                _zelle(_SPALTEN[0], z["nr"].removeprefix("Nr. ")),
                _zelle(_SPALTEN[1], z["text"]),
                _zelle(_SPALTEN[2], platzhalter.euro(z["wert"]) if z["wert"] else "", rechts=True),
                _zelle(_SPALTEN[3], _satz_text(Decimal(z["satz"])) if z["satz"] else "", rechts=True),
                _zelle(_SPALTEN[4], platzhalter.euro(z["betrag"]), rechts=True)))
    ust = Decimal(r["umsatzsteuer_satz"])
    reihen.append(_summe("Summe netto", r["netto"], linie=True))
    if ust:
        reihen.append(_summe(f"Umsatzsteuer {_zahl(ust)} % (Nr. 7008 VV RVG)", r["umsatzsteuer"]))
    for z in r["steuerfrei"]:
        reihen.append(_summe(f"{z['text']} (ohne Umsatzsteuer)", z["betrag"]))
    reihen.append(_summe("Gesamtbetrag", r["brutto"], fett=not r["abzuege"], linie=True))
    for x in r["abzuege"]:
        darin = f", darin USt {platzhalter.euro(x['ust'])}" if Decimal(x["ust"]) else ""
        reihen.append(_summe(f"abzüglich {x['text']}{darin}", str(-Decimal(x["betrag"]))))
    if r["abzuege"]:
        reihen.append(_summe("Noch zu zahlen" if Decimal(r["zahlbetrag"]) >= 0 else "Zu erstatten",
                             str(abs(Decimal(r["zahlbetrag"]))), fett=True, linie=True))
    raster = "".join(f'<w:gridCol w:w="{b}"/>' for b in _SPALTEN)
    return ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="85" w:type="dxa"/></w:tblCellMar>'
            f'<w:tblLook w:val="0000"/></w:tblPr><w:tblGrid>{raster}</w:tblGrid>{"".join(reihen)}</w:tbl>')


_NACHWEIS = (1250, 2300, 3900, 850, 1053)  # Datum | Bearbeiter | Tätigkeit | Dauer | Betrag: 165 mm


def _nachweis(eintraege: list[dict], nummer: str) -> str:
    """Anlage auf eigener Seite: jede abgerechnete Zeiteinheit mit Datum, Bearbeiter, Tätigkeit und Dauer."""
    def zelle(i: int, text: str, rechts: bool = False, fett: bool = False) -> str:
        return _zelle(_NACHWEIS[i], text, rechts=rechts, fett=fett)

    reihen = [_reihe(*(zelle(i, t, rechts=i >= 3, fett=True) for i, t in enumerate(
        ("Datum", "Bearbeiter", "Tätigkeit", "Std.", "Betrag"))))]
    summe, minuten = Decimal(0), 0
    for z in eintraege:
        tag = date.fromisoformat(z["datum"]).strftime("%d.%m.%Y")
        wer = f"{z['bearbeiter']} ({z['stufe']})" if z["stufe"] else z["bearbeiter"]
        dauer = zeiterfassung.stunden_text(z["getaktet"])
        if z["getaktet"] != z["minuten"]:
            dauer += f" ({z['minuten']} Min.)"
        reihen.append(_reihe(zelle(0, tag), zelle(1, wer), zelle(2, z["taetigkeit"] or "–"), zelle(3, dauer, True),
                             zelle(4, platzhalter.euro(z["betrag"]) if z["betrag"] else "", True)))
        minuten += z["getaktet"]
        summe += Decimal(z["betrag"] or 0)
    reihen.append(_reihe(_zelle(sum(_NACHWEIS[:3]), "Summe", fett=True, spanne=3, linie=True),
                         _zelle(_NACHWEIS[3], zeiterfassung.stunden_text(minuten), rechts=True, fett=True, linie=True),
                         _zelle(_NACHWEIS[4], platzhalter.euro(str(summe)), rechts=True, fett=True, linie=True)))
    raster = "".join(f'<w:gridCol w:w="{b}"/>' for b in _NACHWEIS)
    tabelle = ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblLayout w:type="fixed"/>'
               '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="85" w:type="dxa"/></w:tblCellMar>'
               f'<w:tblLook w:val="0000"/></w:tblPr><w:tblGrid>{raster}</w:tblGrid>{"".join(reihen)}</w:tbl>')
    seite = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
    return (seite + _text(f"Anlage: Tätigkeitsnachweis zu Rechnung Nr. {nummer}", "Betreff", fett=True)
            + _text("{{Akte.Bezeichnung}}", "Betreff") + _text("") + tabelle + _text("")
            + _text("Dauer nach der vereinbarten Taktung je Eintrag; in Klammern die tatsächlich erfasste Zeit.",
                    "Klein"))


def _koerper(r: dict, e: dict, ich: bool, nachweis: list[dict] | None = None) -> str:
    vorschuss = r["art"] == "vorschuss"
    titel = f"{ARTEN[r['art']]} Nr. {e['nummer']}"
    info = [("Rechnung Nr.", e["nummer"]), ("Unser Zeichen", "{{Akte.Aktenzeichen}}"),
            ("Bearbeiter", "{{Bearbeiter.Name}}"), ("Telefon", "{{Bearbeiter.Telefon}}"),
            ("E-Mail", "{{Bearbeiter.E-Mail}}"), ("", ""), ("Datum", "{{Datum}}")]
    wir, unser = ("ich", "mein") if ich else ("wir", "unser")
    if vorschuss:
        einleitung = (f"in der oben genannten Angelegenheit bitte{'' if ich else 'n'} {wir} nach § 9 RVG um einen "
                      "Vorschuss auf die Vergütung, berechnet wie folgt:")
    else:
        einleitung = (f"für {unser}e Tätigkeit in der oben genannten Angelegenheit berechne{'' if ich else 'n'} "
                      f"{wir} {unser}e Vergütung nach § 10 RVG wie folgt:")
    zahlen = Decimal(r["zahlbetrag"])
    ziel = int(e.get("zahlungsziel") or 14)
    teile = [
        _anschriftfeld("{{Empfänger.Anschrift}}", info),
        _text(titel, "Betreff", fett=True),
        _text("{{Akte.Bezeichnung}}", "Betreff"),
    ]
    if e.get("gegenstandswert"):
        teile.append(_text(f"Gegenstandswert: {platzhalter.euro(str(_betrag(e['gegenstandswert'], 'Wert')))}",
                           "Betreff"))
    if e.get("leistungszeitraum"):
        teile.append(_text(f"Leistungszeitraum: {e['leistungszeitraum']}", "Betreff"))
    teile += [_text(""), _text("{{Empfänger.Anrede}}"), _text(einleitung), _tabelle(r), _text("")]
    teile.append(_text(f"Berechnung nach {r['grundlage']}.", "Klein"))
    if zahlen > 0:
        teile.append(_text(f"Bitte überweisen Sie den Betrag von {platzhalter.euro(str(zahlen))} "
                           f"innerhalb von {ziel} Tagen unter Angabe der Rechnungsnummer {e['nummer']} auf "
                           f"{unser} Konto: {{{{Absender.Bankverbindung}}}}."))
    elif r["abzuege"] and zahlen == 0:
        teile.append(_text("Der Betrag ist durch den gezahlten Vorschuss ausgeglichen."))
    elif zahlen < 0:
        teile.append(_text(f"Den Betrag von {platzhalter.euro(str(-zahlen))} erstatte{'' if ich else 'n'} {wir} "
                           "Ihnen in den nächsten Tagen."))
    teile.append(_text("{{Absender.Steuernummer}}", "Klein"))
    if nachweis:
        teile.append(_text("Den Zeitaufwand im Einzelnen weist die Anlage aus.", "Klein"))
    teile += [_text(""), _unterschrift(gruss=True)]
    if nachweis:
        teile.append(_nachweis(nachweis, e["nummer"]))
    return "".join(teile)


_STIL_TABELLE = ('<w:style w:type="paragraph" w:customStyle="1" w:styleId="Tabelle"><w:name w:val="Tabelle"/>'
                 '<w:basedOn w:val="Standard"/><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr>'
                 '<w:rPr><w:sz w:val="20"/></w:rPr></w:style>'
                 '<w:style w:type="paragraph" w:customStyle="1" w:styleId="Klein"><w:name w:val="Hinweis klein"/>'
                 '<w:basedOn w:val="Standard"/><w:rPr><w:sz w:val="18"/></w:rPr></w:style>')


def _docx(umgebung: Path, r: dict, e: dict, ich: bool, nachweis: list[dict] | None = None) -> bytes:
    return grundvorlagen.erzeugen("kostennote", grundvorlagen.logo_lesen(umgebung),
                                  koerper=_koerper(r, e, ich, nachweis),
                                  titel=f"{ARTEN[r['art']]} {e['nummer']}", stile=_STIL_TABELLE)


def dateiname(art: str, nummer: str, tag: date) -> str:
    name = _UNZULAESSIG.sub(" ", f"{tag.isoformat()} {ARTEN[art]} {nummer}")
    return " ".join(name.split())[:120].rstrip(". ") + ".docx"


def erzeugen(con: sqlite3.Connection, wissen: sqlite3.Connection, umgebung: Path, ablage: Path, akte_id: int,
             eingabe: dict, pfad: str | Path | None = None, in_akte: bool = True) -> dict:
    """Rechnet die Kostennote, schreibt die Word-Datei in die Akte (und/oder unter ``pfad``) und vergibt die Nummer.

    Nur gespeichert unter ``pfad`` (ohne Akte) wird keine Nummer vergeben: das ist ein Entwurf.
    """
    e = dict(eingabe)
    nummer = " ".join(str(e.get("nummer") or "").split())
    if not nummer:
        raise ValueError("Bitte eine Rechnungsnummer angeben.")
    if in_akte and _vergeben(con, nummer):
        raise ValueError(f"Die Rechnungsnummer {nummer} ist schon vergeben; nächste freie: "
                         f"{naechste_nummer(con, _datum(e.get('datum'), 'Rechnungsdatum') or date.today())}.")
    e["nummer"] = nummer
    tag = _datum(e.get("datum"), "Rechnungsdatum") or date.today()
    e["datum"] = tag.isoformat()
    r = berechne(e)
    # Zeiten aus der Zeiterfassung gelten nur mit einer Kostennote als abgerechnet, nicht mit einem Vorschuss.
    zeiten = [int(i) for p in e.get("posten") or [] if p.get("typ") == "stunden" for i in p.get("quelle") or []]
    abrechnen = in_akte and r["art"] == "rechnung" and zeiten
    if abrechnen:
        zeiterfassung.pruefe_quellen(con, akte_id, zeiten)
    w = platzhalter.werte(con, akte_id, e.get("empfaenger_id"), None, tag)
    werte = w["werte"]
    leer: list[str] = []

    def ersatz(roh: str) -> str | None:
        name = platzhalter.bekannt(roh)
        if name is None:
            return None
        if not werte.get(name) and name not in platzhalter.OPTIONAL:
            leer.append(name)
        return werte.get(name, "")

    ich = eigene.stand(con, mit_archiv=False)["profil"]["form"] == "einzelanwalt"
    daten = fuellen.fuellen(_docx(umgebung, r, e, ich, zeiterfassung.nachweis(con, zeiten)), ersatz)
    name = dateiname(r["art"], nummer, tag)
    antwort: dict = {"dateiname": name, "ergebnis": r, "leer": list(dict.fromkeys(leer)),
                     "hinweise": w["hinweise"] + r["hinweise"]}
    if not werte.get("Absender.Steuernummer"):
        antwort["hinweise"].append("Steuernummer bzw. USt-IdNr. fehlt (Eigene Daten).")
    if pfad:
        Path(pfad).write_bytes(daten)
        antwort["pfad"] = str(pfad)
    if in_akte:
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / name
            datei.write_bytes(daten)
            eingelesen = akten.importiere(con, wissen, akte_id, datei, ablage, ocr=False, herkunft=HERKUNFT)
        antwort["dokument_id"] = eingelesen["dokument_id"]
        con.execute("INSERT INTO kostennote (akte_id, nummer, art, datum, eingabe, ergebnis, brutto, zahlbetrag, "
                    "dokument_id, angelegt_am) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (akte_id, nummer, r["art"], e["datum"], json.dumps(e, ensure_ascii=False),
                     json.dumps(r, ensure_ascii=False), r["brutto"], r["zahlbetrag"], eingelesen["dokument_id"],
                     datetime.now().isoformat(timespec="seconds")))
        if abrechnen:
            kid = con.execute("SELECT id FROM kostennote WHERE nummer = ?", (nummer,)).fetchone()["id"]
            zeiterfassung.abrechnen(con, akte_id, zeiten, kid)
            antwort["zeiten_abgerechnet"] = len(zeiten)
        con.commit()
        antwort["kostennoten"] = liste(con, akte_id)
    return antwort


def stornieren(con: sqlite3.Connection, kostennote_id: int) -> dict:
    """Markiert eine Kostennote als storniert; die Nummer bleibt vergeben, das Dokument bleibt in der Akte."""
    z = con.execute("SELECT akte_id, storniert_am FROM kostennote WHERE id = ?", (kostennote_id,)).fetchone()
    if z is None:
        raise LookupError(f"Unbekannte Kostennote: {kostennote_id}")
    if z["storniert_am"] is None:
        con.execute("UPDATE kostennote SET storniert_am = ? WHERE id = ?",
                    (datetime.now().isoformat(timespec="seconds"), kostennote_id))
        zeiterfassung.freigeben(con, kostennote_id)
        con.commit()
    return {"kostennoten": liste(con, z["akte_id"])}


def eingabe(con: sqlite3.Connection, kostennote_id: int) -> dict:
    """Die Eingaben einer früheren Kostennote, etwa um sie als Ausgangspunkt für eine neue zu nehmen."""
    z = con.execute("SELECT eingabe FROM kostennote WHERE id = ?", (kostennote_id,)).fetchone()
    if z is None:
        raise LookupError(f"Unbekannte Kostennote: {kostennote_id}")
    e = json.loads(z["eingabe"])
    # Als Ausgangspunkt rechnet die neue Rechnung dieselben Zeiteinträge nicht noch einmal ab.
    for p in e.get("posten") or []:
        p.pop("quelle", None)
    return e
