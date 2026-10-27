"""Metadaten eines Dokuments: Titel, Art, Absender, Datum, Schlagworte und Beteiligte, mit Vorschlägen und Verlauf.

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
FELDER = {"titel": "Titel", "art": "Art", "absender": "Absender", "datum": "Datum", "schlagworte": "Schlagworte",
          "beteiligte": "Weitere Beteiligte"}
# Art des Dokuments (Auswahl in „Details“); eigene Angaben sind ebenfalls möglich.
ARTEN = ("Schreiben", "E-Mail", "Schriftsatz", "Verfügung", "Beschluss", "Urteil", "Ladung", "Protokoll",
         "Mahnbescheid", "Vollstreckungsbescheid", "Gutachten", "Vertrag", "Rechnung", "Vollmacht", "Vermerk",
         "Sonstiges")
MAX_ART = 60
EIGENE = "eigene"  # Absender: wir selbst (eigene Kanzlei bzw. Rechtsabteilung)
# Erkannte Dokumentart (juracore.aktenverwaltung.rubrum) → Art.
_ART_AUS_DOKUMENTART = {"Urteil": "Urteil", "Versäumnisurteil": "Urteil", "Beschluss": "Beschluss",
                        "Verfügung": "Verfügung", "Ladung": "Ladung", "Mahnbescheid": "Mahnbescheid",
                        "Vollstreckungsbescheid": "Vollstreckungsbescheid"}
_ART_AUS_UEBERSCHRIFT = (("vertrag", "Vertrag"), ("vereinbarung", "Vertrag"), ("vollmacht", "Vollmacht"),
                         ("rechnung", "Rechnung"), ("kostennote", "Rechnung"), ("gutachten", "Gutachten"),
                         ("protokoll", "Protokoll"), ("vermerk", "Vermerk"))

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
# Bezugszeile im Briefkopf („Unser Zeichen … | Ihr Zeichen … | Akte …“): kein Titel.
_ZEICHENZEILE = re.compile(r"\b(?:unser|ihr)\s+zeichen\b|\baz\.|\baktenzeichen\b|\|", re.IGNORECASE)
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


def _absender(con: sqlite3.Connection, dokument_id: int, akte_beteiligte: list[dict]) -> dict | None:
    z = con.execute("SELECT beteiligung_id, eigene FROM dokument_absender WHERE dokument_id = ?",
                    (dokument_id,)).fetchone()
    if z is None:
        return None
    if z["eigene"]:
        return {"wert": EIGENE, "name": "Wir (eigene Seite)", "rolle_text": ""}
    b = next((b for b in akte_beteiligte if b["id"] == z["beteiligung_id"]), None)
    return {"wert": b["id"], "name": b["name"], "rolle_text": b["rolle_text"]} if b else None


def mit_absender(con: sqlite3.Connection, dokumente: list[dict]) -> list[dict]:
    """Ergänzt die Dokumentliste einer Akte um den Absender (Filter und Anzeige in der Liste)."""
    if not dokumente:
        return dokumente
    akte_beteiligte = stammdaten.beteiligungen(con, dokumente[0]["akte_id"])
    for d in dokumente:
        d["absender"] = _absender(con, d["id"], akte_beteiligte)
    return dokumente


def _absender_text(a: dict | None) -> str:
    return "" if a is None else (a["name"] if not a["rolle_text"] else f"{a['name']} ({a['rolle_text']})")


def lesen(con: sqlite3.Connection, dokument_id: int, eigene_namen: list[str] | None = None) -> dict:
    """Alles für die Ansicht „Details“: Werte, Beteiligte der Akte zur Auswahl, Vorschläge und Verlauf.

    ``eigene_namen``: Name der eigenen Kanzlei bzw. Organisation (Eigene Daten); steht er im Briefkopf, schlägt
    die Ansicht „Wir“ als Absender vor."""
    d = _dokument(con, dokument_id)
    akte_beteiligte = stammdaten.beteiligungen(con, d["akte_id"])
    verknuepft = set(_verknuepft(con, dokument_id))
    erkannt = json.loads(d["datum_erkannt"]) if d["datum_erkannt"] else None
    return {
        "dokument_id": dokument_id,
        "dateiname": d["dateiname"],
        "titel": d["titel"] or "",
        "art": d["art"] or "",
        "arten": list(ARTEN),
        "absender": _absender(con, dokument_id, akte_beteiligte),
        "datum": {"wert": d["datum"], "quelle": d["datum_quelle"], "seite": d["datum_seite"],
                  "abschnitt": d["datum_abschnitt"], "text": d["datum_text"], "erkannt": erkannt},
        "schlagworte": akte._tags(con, dokument_id),
        "beteiligte": [b for b in akte_beteiligte if b["id"] in verknuepft],
        "akte_beteiligte": akte_beteiligte,
        "vorschlaege": vorschlaege(con, dokument_id, akte_beteiligte, eigene_namen),
        "benennung": benennung(con, dokument_id, akte_beteiligte, eigene_namen or []),
        "verlauf": verlauf(con, dokument_id, akte_beteiligte),
    }


def vorschlaege(con: sqlite3.Connection, dokument_id: int, akte_beteiligte: list[dict] | None = None,
                eigene_namen: list[str] | None = None) -> dict:
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
    art = _art_vorschlag(abschnitte, r, nach_nr)
    return {
        "titel": _titel_vorschlaege(d, abschnitte, r, nach_nr, akte_beteiligte),
        "art": art if art and art["wert"] != (d["art"] or "") else None,
        "absender": _absender_vorschlag(con, dokument_id, abschnitte, r, art, akte_beteiligte, eigene_namen or [],
                                        nach_nr),
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
        elif " ./. " in text and len(text) <= 250 and not text.startswith(("In dem", "In Sachen")) \
                and not _ZEICHENZEILE.search(text):
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


# --------------------------------------------------------------------------- Benennung „Wer schreibt was an wen“

# Kanzleien: „Albrecht Tiedemann Rechtsanwälte“ → „RA Albrecht Tiedemann“.
_KANZLEI = re.compile(r"(?:\s*,\s*|\s+)(?:Rechtsanw\w*|Anwaltskanzlei|Anwälte|Kanzlei|Partnerschaft\w*|PartG\b|"
                      r"&\s*Partner\b).*$")
_KANZLEI_VORN = re.compile(r"^(?:Rechtsanwaltskanzlei|Anwaltskanzlei|Kanzlei|Rechtsanwält\w*|Anwälte)\s+")
_ANWALTSROLLEN = ("bevollmaechtigter_gegner", "vertretender_anwalt")
# Was ein Schreiben ist, aus Betreff und ersten Absätzen (erster Treffer gewinnt).
_SCHREIBEN_WAS = (("kündig", "Kündigung"), ("rücktritt", "Rücktritt"), ("widerruf", "Widerruf"),
                  ("anfecht", "Anfechtung"), ("abmahnung", "Abmahnung"), ("mahnung", "Mahnung"),
                  ("wir lehnen", "Ablehnung"), ("lehnen wir", "Ablehnung"),
                  ("zahlungsaufforderung", "Zahlungsaufforderung"), ("zur zahlung", "Zahlungsaufforderung"),
                  ("nacherfüllung", "Nacherfüllungsverlangen"), ("nachbesserung", "Nacherfüllungsverlangen"),
                  ("nachlieferung", "Nacherfüllungsverlangen"), ("mängelrüge", "Mängelrüge"),
                  ("mangelanzeige", "Mängelrüge"), ("vergleichsvorschlag", "Vergleichsvorschlag"),
                  ("terminsverlegung", "Terminsverlegung"), ("neuer termin", "Terminsverlegung"),
                  ("termin", "Terminsnachricht"),
                  ("stellungnahme", "Stellungnahme"))
_SCHRIFTSATZ_WAS = {"Klage": "Klageschrift"}
_SCHRIFTSATZ_KURZ = ("Widerspruch", "Einspruch", "Stellungnahme", "Klageschrift", "Klageerwiderung", "Replik",
                     "Duplik", "Anspruchsbegründung", "Berufung", "Berufungsbegründung")


def kurzname(b: dict, nachname: str = "") -> str:
    """Kurzer Name für Titel: Gericht abgekürzt, Kanzlei als „RA …“, Person mit Nachnamen."""
    name = " ".join((b.get("name") or "").split())
    if b.get("rolle") == "gericht":
        return _gericht_kurz(name)
    ohne = _KANZLEI_VORN.sub("", name)
    kanzlei = _KANZLEI.search(ohne)
    if ohne != name or (kanzlei and kanzlei.start() > 0):
        return f"RA {(ohne[:kanzlei.start()] if kanzlei else ohne).strip(' ,&')}"
    if b.get("art") == "person":
        nach = nachname or (name.split() or [""])[-1]
        return f"RA {nach}" if b.get("rolle") in _ANWALTSROLLEN else nach
    return name


def benennung(con: sqlite3.Connection, dokument_id: int, akte_beteiligte: list[dict],
              eigene_namen: list[str]) -> dict:
    """Bausteine für Titel nach dem Schema „Wer schreibt was an wen“ (die Oberfläche setzt sie zusammen, je nach
    gewählter Art und gewähltem Absender): Kurznamen der Beteiligten, erkanntes „Was“, Empfänger, Vertragsparteien.
    """
    abschnitte = _abschnitte(con, dokument_id, 40)
    nachnamen = {}
    for b in akte_beteiligte:
        if b.get("beteiligter_id") is not None and b.get("art") == "person":
            z = con.execute("SELECT daten FROM beteiligter WHERE id = ?", (b["beteiligter_id"],)).fetchone()
            nachnamen[b["id"]] = (json.loads(z["daten"]).get("nachname") or "").strip() if z else ""
    kurz = {str(b["id"]): kurzname(b, nachnamen.get(b["id"], "")) for b in akte_beteiligte}
    # Eigene Seite: Kanzlei aus „Eigene Daten“ („RA Albrecht Tiedemann“); ohne Eintrag bleibt das „Wer“ leer.
    kurz["eigene"] = kurzname({"name": eigene_namen[0], "art": "organisation"}) if eigene_namen else ""

    # Wer im Kopf genannt ist, in der Reihenfolge des Auftretens (Anschrift bzw. Vertragsparteien). Schlüssel wie in
    # kurznamen: Beteiligungs-ID als Text oder „eigene“.
    suche: list[tuple[str, list[re.Pattern]]] = []
    for b in akte_beteiligte:
        muster = _suchmuster(con, b)
        if b["rolle"] == "gericht":
            muster.append(re.compile(re.escape(_gericht_kurz(b["name"])) + r"(?!\w)"))
        suche.append((str(b["id"]), muster))
    if eigene_namen:
        suche.append((EIGENE, [re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, n.split())) + r"(?!\w)",
                                          re.IGNORECASE) for n in eigene_namen if n.strip()]))
    genannt = []
    for schluessel, muster in suche:
        pos = next((i for i, a in enumerate(abschnitte[:12]) if any(p.search(a["text"]) for p in muster)), None)
        if pos is not None:
            genannt.append((pos, schluessel))
    reihenfolge = [s for _, s in sorted(genannt, key=lambda g: g[0])]

    r = rubrum.erkenne(abschnitte) if abschnitte else {}
    return {
        "kurznamen": kurz,
        "empfaenger": reihenfolge,
        "vertragsparteien": reihenfolge,
        "was": {
            "schreiben": _was_schreiben(abschnitte),
            "schriftsatz": _was_schriftsatz(abschnitte, r),
            "vertrag": _was_vertrag(abschnitte),
        },
    }


def _was_schreiben(abschnitte: list[dict]) -> str | None:
    anrede = next((i for i, a in enumerate(abschnitte) if a["text"].startswith(("Sehr geehrte", "Guten Tag"))), None)
    # Betreff (vor der Anrede) und die ersten beiden Absätze danach.
    bereich = (abschnitte[max(0, anrede - 3):anrede + 7] if anrede is not None else abschnitte[:10])
    text = " ".join(a["text"] for a in bereich).casefold()
    return next((was for wort, was in _SCHREIBEN_WAS if wort in text), None)


def _was_schriftsatz(abschnitte: list[dict], r: dict) -> str | None:
    if art := (r.get("dokumentart") or {}).get("wert"):
        return _SCHRIFTSATZ_WAS.get(art, art)
    for a in abschnitte[:20]:
        text = a["text"].strip()
        if text in _SCHRIFTSATZ_KURZ:
            return text
        if len(text) <= 60 and text.split(" ")[0] in _SCHRIFTSATZ_KURZ:
            return text.split(" ")[0]
    return None


def _was_vertrag(abschnitte: list[dict]) -> str | None:
    for a in abschnitte[:10]:
        erstes = (a["text"].split() or [""])[0].strip(" *#:")
        if re.search(r"(?:vertrag|vereinbarung)$", erstes, re.IGNORECASE) and erstes[:1].isupper():
            return erstes
    return None


def _ist_schreiben(abschnitte: list[dict]) -> dict | None:
    return next((a for a in abschnitte[:30] if a["text"].startswith(("Sehr geehrte", "Guten Tag", "Hallo"))), None)


def _art_vorschlag(abschnitte: list[dict], r: dict, nach_nr: dict) -> dict | None:
    """Art aus der erkannten Dokumentart, sonst aus Überschrift oder Anrede."""
    if art := r.get("dokumentart"):
        wert = _ART_AUS_DOKUMENTART.get(art["wert"], "Schriftsatz")
        return {"wert": wert, "grund": f"„{art['wert']}“ im Kopf des Dokuments",
                "fundstelle": _fund(nach_nr[art["fundstelle"]["abschnitt"]])}
    for a in abschnitte[:15]:
        text = " ".join(a["text"].split())
        if len(text) <= 90 and ":" not in text and _UEBERSCHRIFT.match(text):
            erstes = text.split()[0].casefold()
            if wert := next((w for endung, w in _ART_AUS_UEBERSCHRIFT if erstes.endswith(endung)), None):
                return {"wert": wert, "grund": "Überschrift", "fundstelle": _fund(a)}
    # „An das Amtsgericht …“ ohne erkannte Dokumentart: ein Schriftsatz an das Gericht (z. B. Widerspruch).
    if a := next((a for a in abschnitte[:10] if a["text"].startswith(("An das", "An den"))
                  and "gericht" in a["text"].casefold()), None):
        return {"wert": "Schriftsatz", "grund": "an das Gericht gerichtet", "fundstelle": _fund(a)}
    if a := _ist_schreiben(abschnitte):
        return {"wert": "Schreiben", "grund": "Briefform mit Anrede", "fundstelle": _fund(a)}
    return None


def _absender_vorschlag(con: sqlite3.Connection, dokument_id: int, abschnitte: list[dict], r: dict,
                        art: dict | None, akte_beteiligte: list[dict], eigene_namen: list[str],
                        nach_nr: dict) -> dict | None:
    """Wer das Dokument erstellt hat: das Gericht bei gerichtlichen Dokumenten, sonst wer im Briefkopf steht."""
    if not abschnitte:
        return None
    bisher = _absender(con, dokument_id, akte_beteiligte)
    vorschlag = None
    gericht = r.get("gericht")
    vom_gericht = art and art["wert"] in _ART_AUS_DOKUMENTART.values()
    if gericht and (vom_gericht or gericht["fundstelle"]["abschnitt"] <= 2 and _ist_schreiben(abschnitte)):
        gerichte = [b for b in akte_beteiligte if b["rolle"] == "gericht"]
        b = next((b for b in gerichte if _gleich(b["name"], gericht["name"])), None)
        grund = f"vom {gericht['name']} erlassen" if vom_gericht else "Gericht im Briefkopf"
        fund = _fund(nach_nr[gericht["fundstelle"]["abschnitt"]])
        vorschlag = ({"wert": b["id"], "name": b["name"], "rolle_text": b["rolle_text"], "grund": grund,
                      "fundstelle": fund} if b else None)
    if vorschlag is None and not vom_gericht:
        # Briefkopf: die ersten Absätze; bei Schriftsätzen steht dort die Kanzlei, die ihn einreicht.
        for a in abschnitte[:2]:
            kopf = " ".join(a["text"].split()).casefold()
            if any(n and kopf.startswith(n.casefold()) for n in eigene_namen):
                vorschlag = {"wert": EIGENE, "name": "Wir (eigene Seite)", "rolle_text": "",
                             "grund": "eigene Kanzlei im Briefkopf", "fundstelle": _fund(a)}
                break
            b = next((b for b in akte_beteiligte if b["name"] and kopf.startswith(b["name"].casefold())), None)
            if b:
                vorschlag = {"wert": b["id"], "name": b["name"], "rolle_text": b["rolle_text"],
                             "grund": "im Briefkopf", "fundstelle": _fund(a)}
                break
    if vorschlag and bisher and bisher["wert"] == vorschlag["wert"]:
        return None
    return vorschlag


def _gleich(a: str, b: str) -> bool:
    return beteiligte.aehnlichkeit(beteiligte.schluessel(a), beteiligte.schluessel(b)) is not None


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
        # Die Dokumentart selbst steht im Feld „Art“; als Schlagwort bleibt das Gericht als Absender.
        fund = _fund(nach_nr[art["fundstelle"]["abschnitt"]])
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
              schlagworte: list[str] | None = None, beteiligte_ids: list[int] | None = None,
              art: str | None = None, absender: str | int | None = None,
              eigene_namen: list[str] | None = None) -> dict:
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
        if art is not None:
            neu = " ".join(str(art).split())[:MAX_ART]
            akte.aenderung_merken(con, dokument_id, "art", d["art"], neu)
            con.execute("UPDATE dokument SET art = ? WHERE id = ?", (neu or None, dokument_id))
        if absender is not None:
            _absender_setzen(con, dokument_id, absender, akte_beteiligte)
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
    return lesen(con, dokument_id, eigene_namen)


def _absender_setzen(con: sqlite3.Connection, dokument_id: int, absender: str | int,
                     akte_beteiligte: list[dict]) -> None:
    """``absender``: "eigene" (wir), die Nummer einer Beteiligung der Akte oder "" (keiner)."""
    alt = _absender(con, dokument_id, akte_beteiligte)
    con.execute("DELETE FROM dokument_absender WHERE dokument_id = ?", (dokument_id,))
    if absender == EIGENE:
        con.execute("INSERT INTO dokument_absender (dokument_id, eigene) VALUES (?, 1)", (dokument_id,))
    elif absender not in ("", None):
        beteiligung_id = int(absender)
        if beteiligung_id not in {b["id"] for b in akte_beteiligte}:
            raise ValueError("Der Absender gehört nicht zu den Beteiligten dieser Akte.")
        con.execute("INSERT INTO dokument_absender (dokument_id, beteiligung_id) VALUES (?, ?)",
                    (dokument_id, beteiligung_id))
    akte.aenderung_merken(con, dokument_id, "absender", _absender_text(alt),
                          _absender_text(_absender(con, dokument_id, akte_beteiligte)))


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
