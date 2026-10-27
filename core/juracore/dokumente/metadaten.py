"""Metadaten eines Dokuments: Titel, Datum, Schlagworte und Beteiligte, mit Vorschlägen und Änderungsverlauf.

Die Ansicht „Details“ in der Akte bündelt, was es zu einem Dokument schon gibt (Datum aus
``juracore.dokumente.datum``, Tags, Fassungen, Notizen) und was von Hand dazukommt (Titel, Beteiligte).

Vorschläge liest der Kern aus dem Text (Rubrum, Briefkopf, Betreffzeile, Datumszeile), jeweils mit Fundstelle.
Eingetragen wird ein Vorschlag nur, wenn die Oberfläche ihn nach Bestätigung mit ``speichern`` übergibt.

Jede Änderung an Titel, Datum, Schlagworten und Beteiligten steht mit Zeitpunkt, altem und neuem Wert in
``dokument_aenderung``; zusammen mit den Fassungen ergibt das den Verlauf des Dokuments.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date

from ..aktenverwaltung import beteiligte, rubrum, stammdaten
from . import akte, fassungen

MAX_TITEL = 200
FELDER = {"titel": "Titel", "datum": "Datum", "schlagworte": "Schlagworte", "beteiligte": "Beteiligte"}

# Dokumentarten, die das Gericht erlässt: Der Titel nennt das Gericht mit, das Schlagwort „Gericht“ passt.
_VOM_GERICHT = ("Urteil", "Versäumnisurteil", "Beschluss", "Verfügung", "Ladung", "Mahnbescheid",
                "Vollstreckungsbescheid")
_GERICHT_KURZ = (("Bundesgerichtshof", "BGH"), ("Oberlandesgericht", "OLG"), ("Landesarbeitsgericht", "LAG"),
                 ("Landessozialgericht", "LSG"), ("Oberverwaltungsgericht", "OVG"), ("Verwaltungsgerichtshof", "VGH"),
                 ("Bundesarbeitsgericht", "BAG"), ("Landgericht", "LG"), ("Amtsgericht", "AG"),
                 ("Arbeitsgericht", "ArbG"), ("Sozialgericht", "SG"), ("Verwaltungsgericht", "VG"),
                 ("Finanzgericht", "FG"))  # fmt: skip
# Überschriften wie „Kaufvertrag über …“, „Vollmacht“, „Gutachten zur …“.
_UEBERSCHRIFT = re.compile(
    r"^[A-ZÄÖÜ][\wäöüß-]*?(?:vertrag|vereinbarung|vollmacht|rechnung|gutachten|kündigung|mahnung|protokoll|bescheid|"
    r"beschluss|urteil|verfügung|klage|klageschrift|erwiderung|replik|duplik|antrag|stellungnahme|bestätigung|"
    r"angebot|abmahnung|widerspruch|einspruch|berufung|vermerk|aufstellung|quittung|kostennote)\b", re.IGNORECASE)
_BETREFF = re.compile(r"^(?:Betreff|Betr\.|Re|AW|WG)\s*:\s*(?P<b>.+)$", re.IGNORECASE)


def _dokument(con: sqlite3.Connection, dokument_id: int) -> sqlite3.Row:
    z = con.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if z is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    return z


def _abschnitte(con: sqlite3.Connection, dokument_id: int, anzahl: int = 80) -> list[dict]:
    return [dict(a) for a in con.execute(
        "SELECT nr, seite, text FROM abschnitt WHERE dokument_id = ? ORDER BY nr LIMIT ?", (dokument_id, anzahl))]


def _kurz(text: str, laenge: int = 100) -> str:
    text = " ".join(text.replace("¶", " ").split()).strip(" *#")
    if len(text) <= laenge:
        return text
    return text[:laenge].rsplit(" ", 1)[0].rstrip(" ,;–-") + " …"


def _fund(a: dict, text: str | None = None) -> dict:
    return {"abschnitt": a["nr"], "seite": a.get("seite"), "text": _kurz(text if text is not None else a["text"], 160)}


def _gericht_kurz(name: str) -> str:
    for lang, kurz in _GERICHT_KURZ:
        if name.startswith(lang):
            return kurz + name[len(lang):]
    return name


def _verknuepft(con: sqlite3.Connection, dokument_id: int) -> list[int]:
    return [z[0] for z in con.execute(
        "SELECT beteiligung_id FROM dokument_beteiligung WHERE dokument_id = ? ORDER BY beteiligung_id",
        (dokument_id,))]


def _namen(akte_beteiligte: list[dict], ids: list[int]) -> str:
    nach_id = {b["id"]: b for b in akte_beteiligte}
    return ", ".join(f"{nach_id[i]['name']} ({nach_id[i]['rolle_text']})" for i in ids if i in nach_id)


# --------------------------------------------------------------------------- Lesen


def lesen(con: sqlite3.Connection, dokument_id: int) -> dict:
    """Alles für die Ansicht „Details“: Werte, Beteiligte der Akte zur Auswahl, Vorschläge und Verlauf."""
    d = _dokument(con, dokument_id)
    akte_beteiligte = stammdaten.beteiligungen(con, d["akte_id"])
    verknuepft = set(_verknuepft(con, dokument_id))
    erkannt = json.loads(d["datum_erkannt"]) if d["datum_erkannt"] else None
    return {
        "dokument_id": dokument_id,
        "dateiname": d["dateiname"],
        "titel": d["titel"] or "",
        "datum": {"wert": d["datum"], "quelle": d["datum_quelle"], "seite": d["datum_seite"],
                  "abschnitt": d["datum_abschnitt"], "text": d["datum_text"], "erkannt": erkannt},
        "schlagworte": akte._tags(con, dokument_id),
        "beteiligte": [b for b in akte_beteiligte if b["id"] in verknuepft],
        "akte_beteiligte": akte_beteiligte,
        "vorschlaege": vorschlaege(con, dokument_id, akte_beteiligte),
        "verlauf": verlauf(con, dokument_id, akte_beteiligte),
    }


def vorschlaege(con: sqlite3.Connection, dokument_id: int, akte_beteiligte: list[dict] | None = None) -> dict:
    """Aus dem Text erkannte Werte, die noch nicht eingetragen sind; jeder mit Grund und Fundstelle."""
    d = _dokument(con, dokument_id)
    if akte_beteiligte is None:
        akte_beteiligte = stammdaten.beteiligungen(con, d["akte_id"])
    abschnitte = _abschnitte(con, dokument_id)
    r = rubrum.erkenne(abschnitte) if abschnitte else {"dokumentart": None, "gericht": None, "parteien": []}
    nach_nr = {a["nr"]: a for a in abschnitte}
    if not r.get("dokumentart"):
        # Urteile tragen oft nur „Im Namen des Volkes“; die Überschrift „Urteil“ fehlt im gelesenen Text.
        if a := next((a for a in abschnitte[:15] if a["text"].strip() == "Im Namen des Volkes"), None):
            r = r | {"dokumentart": {"wert": "Urteil", "fundstelle": {"abschnitt": a["nr"]}}}
    return {
        "titel": _titel_vorschlaege(d, abschnitte, r, nach_nr, akte_beteiligte),
        "datum": _datum_vorschlag(d),
        "schlagworte": _schlagwort_vorschlaege(con, dokument_id, r, nach_nr),
        "beteiligte": _beteiligte_vorschlaege(con, dokument_id, abschnitte, r, akte_beteiligte, nach_nr),
    }


def _titel_vorschlaege(d: sqlite3.Row, abschnitte: list[dict], r: dict, nach_nr: dict,
                       akte_beteiligte: list[dict]) -> list[dict]:
    vorschlaege: list[dict] = []
    if art := r.get("dokumentart"):
        wert, grund = art["wert"], "Dokumentart im Kopf des Dokuments"
        if wert in _VOM_GERICHT and r.get("gericht"):
            wert = f"{wert} {_gericht_kurz(r['gericht']['name'])}"
            grund = "Dokumentart und Gericht im Kopf des Dokuments"
        vorschlaege.append({"wert": wert, "grund": grund, "fundstelle": _fund(nach_nr[art["fundstelle"]["abschnitt"]])})
    for a in abschnitte[:25]:
        text = " ".join(a["text"].split())
        if m := _BETREFF.match(text):
            vorschlaege.append({"wert": _kurz(m.group("b")), "grund": "Betreffzeile", "fundstelle": _fund(a)})
        elif " ./. " in text and len(text) <= 250 and not text.startswith(("In dem", "In Sachen")):
            vorschlaege.append({"wert": _kurz(text), "grund": "Betreffzeile", "fundstelle": _fund(a)})
        elif (len(text) <= 90 and ":" not in text and not text.endswith((".", ",")) and _UEBERSCHRIFT.match(text)
              # „Mahnbescheid“ als Überschrift neben „Mahnbescheid AG Stuttgart“
              and text.casefold() != (r.get("dokumentart") or {}).get("wert", "").casefold()):
            vorschlaege.append({"wert": _kurz(text), "grund": "Überschrift", "fundstelle": _fund(a)})
    anrede = next((a for a in abschnitte[:30] if a["text"].startswith("Sehr geehrte")), None)
    if anrede and not r.get("dokumentart"):
        # Ein Schreiben ohne Dokumentart: Absender aus dem Briefkopf (Gericht oder Beteiligter der Akte).
        absender, fund = None, abschnitte[0]
        if r.get("gericht") and r["gericht"]["fundstelle"]["abschnitt"] <= 3:
            absender, fund = _gericht_kurz(r["gericht"]["name"]), nach_nr[r["gericht"]["fundstelle"]["abschnitt"]]
        else:
            kopf = abschnitte[0]["text"].casefold()
            absender = next((b["name"] for b in akte_beteiligte if b["name"] and kopf.startswith(b["name"].casefold())),
                            None)
        if absender:
            vorschlaege.append({"wert": f"Schreiben {absender}", "grund": "Briefkopf", "fundstelle": _fund(fund)})
    gesehen = {(d["titel"] or "").casefold()}
    ergebnis = []
    for v in vorschlaege:
        if v["wert"].casefold() not in gesehen:
            gesehen.add(v["wert"].casefold())
            ergebnis.append(v)
    return ergebnis[:3]


def _datum_vorschlag(d: sqlite3.Row) -> dict | None:
    """Bei einem Datum von Hand: das erkannte Datum, falls es abweicht."""
    if d["datum_quelle"] != "manuell" or not d["datum_erkannt"]:
        return None
    e = json.loads(d["datum_erkannt"])
    if not e.get("datum") or e["datum"] == d["datum"]:
        return None
    grund = {"dokument": "Datumszeile im Dokument", "word": "zuletzt gespeichert laut Word",
             "datei": "Dateidatum"}.get(e.get("quelle"), "erkannt")
    fund = ({"abschnitt": e["abschnitt"], "seite": e.get("seite"), "text": e.get("text")}
            if e.get("abschnitt") is not None else None)
    return {"wert": e["datum"], "grund": grund, "fundstelle": fund}


def _schlagwort_vorschlaege(con: sqlite3.Connection, dokument_id: int, r: dict, nach_nr: dict) -> list[dict]:
    vorhanden = {t["name"].casefold() for t in akte._tags(con, dokument_id)}
    vorschlaege = []
    if art := r.get("dokumentart"):
        fund = _fund(nach_nr[art["fundstelle"]["abschnitt"]])
        vorschlaege.append({"wert": art["wert"], "grund": "Dokumentart", "fundstelle": fund})
        if art["wert"] in _VOM_GERICHT and r.get("gericht"):
            vorschlaege.append({"wert": "Gericht", "grund": f"erlassen vom {r['gericht']['name']}", "fundstelle": fund})
    return [v for v in vorschlaege if v["wert"].casefold() not in vorhanden]


def _suchmuster(con: sqlite3.Connection, b: dict) -> list[re.Pattern]:
    """Wie ein Beteiligter im Text stehen kann: voller Name, bei Personen auch „Frau/Herrn (Dr.) Nachname“."""
    muster = [re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, b["name"].split())) + r"(?!\w)", re.IGNORECASE)]
    if b.get("beteiligter_id") is not None and b.get("art") == "person":
        z = con.execute("SELECT daten FROM beteiligter WHERE id = ?", (b["beteiligter_id"],)).fetchone()
        nachname = (json.loads(z["daten"]).get("nachname") or "").strip() if z else ""
        if len(nachname) >= 3:
            muster.append(re.compile(r"\b(?:Frau|Herrn?)\s+(?:(?:Dr|Prof)\.\s*)*" + re.escape(nachname) + r"(?!\w)"))
    return muster


def _beteiligte_vorschlaege(con: sqlite3.Connection, dokument_id: int, abschnitte: list[dict], r: dict,
                            akte_beteiligte: list[dict], nach_nr: dict) -> list[dict]:
    verknuepft = set(_verknuepft(con, dokument_id))
    offen = [b for b in akte_beteiligte if b["id"] not in verknuepft]
    vorschlaege: dict[int, dict] = {}

    def gleich(a: str, b: str) -> bool:
        return beteiligte.aehnlichkeit(beteiligte.schluessel(a), beteiligte.schluessel(b)) is not None

    def vorschlagen(b: dict, grund: str, fund: dict) -> None:
        vorschlaege.setdefault(b["id"], {"beteiligung_id": b["id"], "name": b["name"], "rolle_text": b["rolle_text"],
                                         "grund": grund, "fundstelle": fund})

    # Rubrum: Parteien, ihre Bevollmächtigten und das Gericht.
    erkannt: list[tuple[str, str, dict]] = []
    for p in r.get("parteien", []):
        grund = f"im Rubrum als {p['rolle']}" if p.get("rolle") else "im Kurzrubrum genannt"
        erkannt.append((p["name"], grund, p["fundstelle"]))
        if bev := p.get("bevollmaechtigte"):
            erkannt.append((bev["name"], "im Rubrum als Prozessbevollmächtigte", p["fundstelle"]))
    if g := r.get("gericht"):
        erkannt.append((g["name"], "im Kopf des Dokuments als Gericht", g["fundstelle"]))
    for name, grund, fund in erkannt:
        for b in offen:
            if gleich(name, b["name"]) and fund.get("abschnitt") in nach_nr:
                vorschlagen(b, grund, _fund(nach_nr[fund["abschnitt"]]))

    # Briefkopf, Anschrift, Anrede und erste Absätze: Namen der Beteiligten der Akte.
    for b in offen:
        if b["id"] in vorschlaege or not b["name"]:
            continue
        muster = _suchmuster(con, b)
        for a in abschnitte[:40]:
            if m := next((m for p in muster if (m := p.search(a["text"]))), None):
                grund = "im Briefkopf genannt" if a["nr"] <= 8 else "im Dokument genannt"
                vorschlagen(b, grund, _fund(a, _umgebung(a["text"], m.start(), m.end())))
                break
    return list(vorschlaege.values())


def _umgebung(text: str, start: int, ende: int, rand: int = 60) -> str:
    anfang = max(0, start - rand)
    return ("… " if anfang else "") + text[anfang:ende + rand] + (" …" if ende + rand < len(text) else "")


def verlauf(con: sqlite3.Connection, dokument_id: int, akte_beteiligte: list[dict] | None = None) -> list[dict]:
    """Fassungen und Änderungen an den Metadaten, neueste zuerst."""
    eintraege = [
        {"zeitpunkt": f["erstellt_am"], "art": "fassung", "nr": f["nr"], "dateiname": f["dateiname"],
         "quelle": f["quelle"]}
        for f in fassungen.liste(con, dokument_id)
    ]
    for z in con.execute("SELECT * FROM dokument_aenderung WHERE dokument_id = ? ORDER BY id", (dokument_id,)):
        eintraege.append({"zeitpunkt": z["zeitpunkt"], "art": "aenderung", "id": z["id"], "feld": z["feld"],
                          "feld_text": FELDER.get(z["feld"], z["feld"]), "alt": z["alt"], "neu": z["neu"]})
    return sorted(eintraege, key=lambda e: (e["zeitpunkt"], e["art"] == "aenderung", e.get("id", 0)), reverse=True)


# --------------------------------------------------------------------------- Speichern


def _datum_pruefen(wert: str) -> str:
    try:
        return date.fromisoformat(wert.strip()).isoformat()
    except ValueError:
        raise ValueError(f"Kein gültiges Datum: {wert!r} (erwartet JJJJ-MM-TT).") from None


def speichern(con: sqlite3.Connection, dokument_id: int, titel: str | None = None, datum: str | None = None,
              schlagworte: list[str] | None = None, beteiligte_ids: list[int] | None = None) -> dict:
    """Speichert die übergebenen Felder; nicht übergebene bleiben. ``datum=""`` kehrt zum erkannten Datum zurück,
    ``titel=""`` zum Dateinamen. Jede tatsächliche Änderung kommt in den Verlauf."""
    d = _dokument(con, dokument_id)
    akte_beteiligte = stammdaten.beteiligungen(con, d["akte_id"])
    if schlagworte is not None:
        akte.tags_setzen(con, dokument_id, schlagworte)
    with con:
        if titel is not None:
            neu = " ".join(str(titel).split())[:MAX_TITEL]
            akte.aenderung_merken(con, dokument_id, "titel", d["titel"], neu)
            con.execute("UPDATE dokument SET titel = ? WHERE id = ?", (neu or None, dokument_id))
        if datum is not None:
            _datum_setzen(con, d, datum.strip())
        if beteiligte_ids is not None:
            gueltig = {b["id"] for b in akte_beteiligte}
            ids = sorted({int(i) for i in beteiligte_ids})
            if fremd := [i for i in ids if i not in gueltig]:
                raise ValueError(f"Diese Beteiligten gehören nicht zur Akte: {fremd}")
            bisher = _verknuepft(con, dokument_id)
            akte.aenderung_merken(con, dokument_id, "beteiligte", _namen(akte_beteiligte, bisher),
                                  _namen(akte_beteiligte, ids))
            con.execute("DELETE FROM dokument_beteiligung WHERE dokument_id = ?", (dokument_id,))
            con.executemany("INSERT INTO dokument_beteiligung (dokument_id, beteiligung_id) VALUES (?, ?)",
                            [(dokument_id, i) for i in ids])
    return lesen(con, dokument_id)


def _datum_setzen(con: sqlite3.Connection, d: sqlite3.Row, wert: str) -> None:
    manuell = d["datum_quelle"] == "manuell"
    if not wert:
        if not manuell:
            return
        # Zurück zum erkannten Datum, so wie es vor der Eingabe von Hand war (oder seitdem neu erkannt wurde).
        e = json.loads(d["datum_erkannt"]) if d["datum_erkannt"] else {
            "datum": None, "quelle": "unbekannt", "abschnitt": None, "seite": None, "text": None,
            "gespeichert": d["gespeichert_am"], "gespeichert_quelle": d["gespeichert_quelle"]}
        con.execute("UPDATE dokument SET datum_quelle = NULL, datum_erkannt = NULL WHERE id = ?", (d["id"],))
        akte._datum_speichern(con, d["id"], e)
        akte.aenderung_merken(con, d["id"], "datum", d["datum"], e["datum"])
        return
    neu = _datum_pruefen(wert)
    if manuell and neu == d["datum"]:
        return
    erkannt = d["datum_erkannt"] if manuell else json.dumps(
        {"datum": d["datum"], "quelle": d["datum_quelle"] or "unbekannt", "abschnitt": d["datum_abschnitt"],
         "seite": d["datum_seite"], "text": d["datum_text"], "gespeichert": d["gespeichert_am"],
         "gespeichert_quelle": d["gespeichert_quelle"]}, ensure_ascii=False)
    con.execute(
        """UPDATE dokument SET datum = ?, datum_quelle = 'manuell', datum_abschnitt = NULL, datum_seite = NULL,
                               datum_text = NULL, datum_erkannt = ? WHERE id = ?""", (neu, erkannt, d["id"]))
    akte.aenderung_merken(con, d["id"], "datum", d["datum"], neu)
