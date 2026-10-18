"""Eigene Daten: wer mit JuraBox arbeitet und in welchem Rahmen (Konzept „Eigene Daten“, Fassung vom 18.10.2026).

Gespeichert wird in der Aktendatenbank der aktiven Arbeitsumgebung, damit Akten später auf Organisation und
Person verweisen können. Die Angaben verlassen das Gerät nicht; Export und Import laufen über eine Datei.

Bausteine:
- Organisation: die eigene Kanzlei bzw. das Unternehmen, Konzerngesellschaften, beauftragte Kanzleien.
- Person: Profilinhaber, Berufsträger der Kanzlei, Anwälte beauftragter Kanzleien.
- Mitgliedschaft: verbindet Person und Organisation (Stellung, Standort, Dezernat, ausgeschieden).
- Profil: Organisationsform und wer „ich“ bin.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .felder import FORMEN, REGISTERPFLICHTIG, felder_von

_SCHEMA = """
CREATE TABLE IF NOT EXISTS eigene_profil (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    form TEXT,
    organisation_id INTEGER REFERENCES eigene_organisation(id) ON DELETE SET NULL,
    person_id INTEGER REFERENCES eigene_person(id) ON DELETE SET NULL,
    assistent_fertig INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS eigene_organisation (
    id INTEGER PRIMARY KEY,
    art TEXT NOT NULL,
    daten TEXT NOT NULL,
    archiviert_am TEXT,
    angelegt_am TEXT NOT NULL,
    geaendert_am TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eigene_person (
    id INTEGER PRIMARY KEY,
    daten TEXT NOT NULL,
    archiviert_am TEXT,
    angelegt_am TEXT NOT NULL,
    geaendert_am TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eigene_mitgliedschaft (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES eigene_person(id) ON DELETE CASCADE,
    organisation_id INTEGER NOT NULL REFERENCES eigene_organisation(id) ON DELETE CASCADE,
    daten TEXT NOT NULL,
    UNIQUE (person_id, organisation_id)
);
CREATE TABLE IF NOT EXISTS eigene_aenderung (
    id INTEGER PRIMARY KEY,
    zeitpunkt TEXT NOT NULL,
    objekt TEXT NOT NULL,
    objekt_id INTEGER NOT NULL,
    bezeichnung TEXT NOT NULL,
    feld TEXT NOT NULL,
    alt TEXT,
    neu TEXT
);
"""

ARTEN_EINHEIT = ("konzerngesellschaft", "beauftragte_kanzlei")
EXPORT_FORMAT = "jurabox-eigene-daten"
EXPORT_VERSION = 1


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    con.execute("INSERT OR IGNORE INTO eigene_profil (id) VALUES (1)")
    con.commit()


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- Felder prüfen


def bereinige(daten: dict | None, art: str, vorher: dict | None = None) -> dict:
    """Nur bekannte Felder, Text getrimmt, Auswahlwerte geprüft. Fehlende Pflichtangaben sind erlaubt (Entwurf)."""
    daten = daten or {}
    ergebnis: dict = {}
    for f in felder_von(art):
        k, typ = f["schluessel"], f["typ"]
        if k not in daten and vorher is None and "vorgabe" in f:
            wert = f["vorgabe"]
        else:
            wert = daten.get(k)
        if typ == "mehrfach":
            werte = [str(w).strip() for w in (wert or []) if str(w).strip()]
            werte = list(dict.fromkeys(werte))
            for w in werte:
                if w not in f["optionen"]:
                    raise ValueError(f"{f['titel']}: „{w}“ ist kein zulässiger Wert.")
            if len(werte) > f.get("hoechstens", len(werte)):
                raise ValueError(f"{f['titel']}: höchstens {f['hoechstens']} (§ 43c Abs. 1 BRAO).")
            ergebnis[k] = werte
        elif typ == "ja_nein":
            ergebnis[k] = bool(wert)
        else:
            text = "" if wert is None else str(wert).strip()
            if typ != "mehrzeilig":
                text = " ".join(text.split())
            else:
                text = "\n".join(z.strip() for z in text.splitlines() if z.strip())
            if text and typ == "auswahl" and text not in f["optionen"]:
                raise ValueError(f"{f['titel']}: „{text}“ ist kein zulässiger Wert.")
            if text and typ == "datum":
                try:
                    date.fromisoformat(text)
                except ValueError as fehler:
                    raise ValueError(f"{f['titel']}: bitte ein Datum im Format JJJJ-MM-TT.") from fehler
            ergebnis[k] = text
    return ergebnis


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _ist_deutschland(daten: dict) -> bool:
    return daten.get("land", "").strip().lower() in ("", "deutschland", "de", "germany")


def fehlende(daten: dict, art: str) -> list[str]:
    return [f["titel"] for f in felder_von(art) if f["pflicht"] and not daten.get(f["schluessel"])]


def plausibel(daten: dict, art: str) -> list[str]:
    """Hinweise ohne Netz und ohne harte Sperre."""
    hinweise = []
    for f in felder_von(art):
        wert = daten.get(f["schluessel"])
        if f["typ"] == "email" and wert and not _EMAIL.match(wert):
            hinweise.append(f"{f['titel']} sieht nicht wie eine E-Mail-Adresse aus.")
    if daten.get("plz") and _ist_deutschland(daten) and not re.fullmatch(r"\d{5}", daten["plz"]):
        hinweise.append("Eine deutsche Postleitzahl hat fünf Ziffern.")
    return hinweise


# --------------------------------------------------------------------------- Lesen


def _org(zeile: sqlite3.Row) -> dict:
    return {"id": zeile["id"], "art": zeile["art"], "daten": json.loads(zeile["daten"]),
            "archiviert": zeile["archiviert_am"] is not None, "geaendert_am": zeile["geaendert_am"]}


def _person(zeile: sqlite3.Row, mitgliedschaft: dict | None = None) -> dict:
    return {"id": zeile["id"], "daten": json.loads(zeile["daten"]), "archiviert": zeile["archiviert_am"] is not None,
            "geaendert_am": zeile["geaendert_am"], "mitgliedschaft": mitgliedschaft or {}}


def profil(con: sqlite3.Connection) -> dict:
    z = con.execute("SELECT * FROM eigene_profil WHERE id = 1").fetchone()
    return {"form": z["form"], "organisation_id": z["organisation_id"], "person_id": z["person_id"],
            "assistent_fertig": bool(z["assistent_fertig"])}


def organisation(con: sqlite3.Connection, org_id: int) -> dict:
    z = con.execute("SELECT * FROM eigene_organisation WHERE id = ?", (org_id,)).fetchone()
    if z is None:
        raise LookupError(f"Unbekannte Organisation: {org_id}")
    return _org(z)


def person(con: sqlite3.Connection, person_id: int) -> dict:
    z = con.execute("SELECT * FROM eigene_person WHERE id = ?", (person_id,)).fetchone()
    if z is None:
        raise LookupError(f"Unbekannte Person: {person_id}")
    return _person(z)


def personen_von(con: sqlite3.Connection, org_id: int) -> list[dict]:
    zeilen = con.execute(
        """SELECT p.*, m.daten AS m_daten FROM eigene_person p
           JOIN eigene_mitgliedschaft m ON m.person_id = p.id
           WHERE m.organisation_id = ? ORDER BY p.id""",
        (org_id,),
    ).fetchall()
    return [_person(z, json.loads(z["m_daten"])) for z in zeilen]


def _personen_art(con: sqlite3.Connection, org_id: int | None, form: str | None) -> str:
    if org_id is None:
        return "person_rechtsabteilung" if form == "rechtsabteilung" else "person_anwalt"
    art = organisation(con, org_id)["art"]
    return {"unternehmen": "person_rechtsabteilung", "beauftragte_kanzlei": "person_extern"}.get(art, "person_anwalt")


def _org_art(form: str | None) -> tuple[str, str]:
    """(Art in der Tabelle, Feldsatz) der Hauptorganisation je Organisationsform."""
    if form == "rechtsabteilung":
        return "unternehmen", "unternehmen"
    if form == "einzelanwalt":
        return "kanzlei", "einzelanwalt"
    return "kanzlei", "kanzlei"


def anzeigename(daten: dict, art: str, inhaber: dict | None = None) -> str:
    if art in ("person_anwalt", "person_rechtsabteilung", "person_extern"):
        return " ".join(t for t in (daten.get("titel"), daten.get("vorname"), daten.get("nachname")) if t)
    if not daten.get("name") and art == "einzelanwalt" and inhaber:
        beruf = inhaber.get("berufsbezeichnung") or "Rechtsanwalt"
        return f"{beruf} {anzeigename(inhaber, 'person_anwalt')}".strip()
    return daten.get("name", "")


def stand(con: sqlite3.Connection, mit_archiv: bool = True) -> dict:
    """Alles, was die Oberfläche braucht, samt Vollständigkeit und Hinweisen."""
    p = profil(con)
    form = p["form"]
    _, org_felder = _org_art(form)
    haupt = organisation(con, p["organisation_id"]) if p["organisation_id"] else None
    inhaber = person(con, p["person_id"]) if p["person_id"] else None
    inhaber_art = _personen_art(con, p["organisation_id"], form)
    berufstraeger = personen_von(con, haupt["id"]) if haupt and form in ("einzelanwalt", "kanzlei") else []
    einheiten = {art: [] for art in ARTEN_EINHEIT}
    for z in con.execute("SELECT * FROM eigene_organisation WHERE art IN (?, ?) ORDER BY id", ARTEN_EINHEIT):
        o = _org(z)
        if o["archiviert"] and not mit_archiv:
            continue
        if o["art"] == "beauftragte_kanzlei":
            o["anwaelte"] = personen_von(con, o["id"])
        einheiten[o["art"]].append(o)

    fehlend: list[str] = []
    hinweise: list[str] = []
    if not form:
        fehlend.append("Organisationsform")
    else:
        bereich = {"rechtsabteilung": "Unternehmen", "kanzlei": "Kanzlei", "einzelanwalt": "Kanzlei"}[form]
        if haupt is None:
            fehlend.append(f"{bereich}: Angaben")
        else:
            fehlend += [f"{bereich}: {t}" for t in fehlende(haupt["daten"], org_felder)]
            hinweise += [f"{bereich}: {h}" for h in plausibel(haupt["daten"], org_felder)]
            rechtsform = haupt["daten"].get("rechtsform", "")
            if form == "kanzlei" and rechtsform in REGISTERPFLICHTIG and not (
                haupt["daten"].get("registergericht") and haupt["daten"].get("registernummer")
            ):
                hinweise.append(f"Kanzlei: Bei der Rechtsform {rechtsform} gehören Registergericht und Registernummer "
                                f"auf den Briefbogen ({REGISTERPFLICHTIG[rechtsform]}).")
            if form == "kanzlei" and rechtsform in ("GmbH", "AG") and not any(
                b["mitgliedschaft"].get("vertretungsorgan") and not b["mitgliedschaft"].get("ausgeschieden_am")
                for b in berufstraeger
            ):
                organ = "Geschäftsführer" if rechtsform == "GmbH" else "Vorstandsmitglieder"
                norm = "§ 35a Abs. 1 GmbHG" if rechtsform == "GmbH" else "§ 80 Abs. 1 AktG"
                hinweise.append(f"Kanzlei: Bei der Rechtsform {rechtsform} nennt der Briefbogen alle {organ} ({norm}); "
                                f"bitte bei den Berufsträgern kennzeichnen.")
        if inhaber is None:
            fehlend.append("Ihre Person: Angaben")
        else:
            fehlend += [f"Ihre Person: {t}" for t in fehlende(inhaber["daten"], inhaber_art)]
            hinweise += [f"Ihre Person: {h}" for h in plausibel(inhaber["daten"], inhaber_art)]
        if form == "rechtsabteilung":
            for o in einheiten["konzerngesellschaft"]:
                if o["archiviert"]:
                    continue
                name = o["daten"].get("name") or "Konzerngesellschaft"
                fehlend += [f"{name}: {t}" for t in fehlende(o["daten"], "konzerngesellschaft")]
                hinweise += [f"{name}: {h}" for h in plausibel(o["daten"], "konzerngesellschaft")]
                if not o["daten"].get("gesetzliche_vertreter"):
                    hinweise.append(f"{name}: Gesetzliche Vertreter fehlen; eine Klage muss sie nennen "
                                    f"(§ 130 Nr. 1, § 253 Abs. 4 ZPO).")
            for o in einheiten["beauftragte_kanzlei"]:
                if o["archiviert"]:
                    continue
                name = o["daten"].get("name") or "Beauftragte Kanzlei"
                fehlend += [f"{name}: {t}" for t in fehlende(o["daten"], "beauftragte_kanzlei")]
                hinweise += [f"{name}: {h}" for h in plausibel(o["daten"], "beauftragte_kanzlei")]

    return {
        "profil": p,
        "formen": FORMEN,
        "organisation": haupt,
        "organisation_felder": org_felder,
        "organisation_name": anzeigename(haupt["daten"], org_felder, inhaber and inhaber["daten"]) if haupt else "",
        "inhaber": inhaber,
        "inhaber_felder": inhaber_art,
        "berufstraeger": berufstraeger,
        "konzerngesellschaften": einheiten["konzerngesellschaft"],
        "beauftragte_kanzleien": einheiten["beauftragte_kanzlei"],
        "fehlend": fehlend,
        "hinweise": hinweise,
    }


def kurzstand(con: sqlite3.Connection) -> dict:
    """Für die Kachel auf dem Startbildschirm."""
    s = stand(con, mit_archiv=False)
    if not s["profil"]["form"]:
        text = "Noch nicht eingerichtet"
    elif s["fehlend"]:
        n = len(s["fehlend"])
        text = "1 Angabe fehlt" if n == 1 else f"{n} Angaben fehlen"
    else:
        text = "Profil vollständig"
    return {"text": text, "eingerichtet": bool(s["profil"]["form"]), "fehlend": len(s["fehlend"]),
            "hinweise": len(s["hinweise"])}


# --------------------------------------------------------------------------- Schreiben


def _protokolliere(con: sqlite3.Connection, objekt: str, objekt_id: int, bezeichnung: str, alt: dict, neu: dict,
                   zeitpunkt: str) -> None:
    for k in sorted(set(alt) | set(neu)):
        a, n = alt.get(k), neu.get(k)
        if (a or None) != (n or None):
            con.execute(
                "INSERT INTO eigene_aenderung (zeitpunkt, objekt, objekt_id, bezeichnung, feld, alt, neu) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (zeitpunkt, objekt, objekt_id, bezeichnung, k, _als_text(a), _als_text(n)),
            )


def _als_text(wert) -> str | None:
    if wert in (None, "", [], False):
        return None
    if isinstance(wert, list):
        return ", ".join(wert)
    if wert is True:
        return "ja"
    return str(wert)


def _speichere_org(con: sqlite3.Connection, art: str, feldsatz: str, daten: dict, org_id: int | None) -> int:
    jetzt = _jetzt()
    if org_id is None:
        sauber = bereinige(daten, feldsatz)
        cur = con.execute(
            "INSERT INTO eigene_organisation (art, daten, angelegt_am, geaendert_am) VALUES (?, ?, ?, ?)",
            (art, json.dumps(sauber, ensure_ascii=False), jetzt, jetzt),
        )
        org_id = cur.lastrowid
        _protokolliere(con, "organisation", org_id, sauber.get("name") or art, {}, sauber, jetzt)
        return org_id
    alt = organisation(con, org_id)
    if alt["art"] != art:
        raise ValueError("Die Organisation hat eine andere Art.")
    sauber = bereinige(daten, feldsatz, vorher=alt["daten"])
    con.execute("UPDATE eigene_organisation SET daten = ?, geaendert_am = ? WHERE id = ?",
                (json.dumps(sauber, ensure_ascii=False), jetzt, org_id))
    _protokolliere(con, "organisation", org_id, sauber.get("name") or art, alt["daten"], sauber, jetzt)
    return org_id


def _speichere_person(con: sqlite3.Connection, feldsatz: str, daten: dict, person_id: int | None) -> int:
    jetzt = _jetzt()
    vorher = person(con, person_id)["daten"] if person_id is not None else None
    sauber = bereinige(daten, feldsatz, vorher=vorher)
    name = anzeigename(sauber, feldsatz) or "Person"
    if person_id is None:
        cur = con.execute("INSERT INTO eigene_person (daten, angelegt_am, geaendert_am) VALUES (?, ?, ?)",
                          (json.dumps(sauber, ensure_ascii=False), jetzt, jetzt))
        person_id = cur.lastrowid
        _protokolliere(con, "person", person_id, name, {}, sauber, jetzt)
        return person_id
    con.execute("UPDATE eigene_person SET daten = ?, geaendert_am = ? WHERE id = ?",
                (json.dumps(sauber, ensure_ascii=False), jetzt, person_id))
    _protokolliere(con, "person", person_id, name, vorher or {}, sauber, jetzt)
    return person_id


def _verbinde(con: sqlite3.Connection, person_id: int, org_id: int, mitgliedschaft: dict | None) -> None:
    sauber = bereinige(mitgliedschaft, "mitgliedschaft", vorher={}) if mitgliedschaft is not None else {}
    vorhanden = con.execute("SELECT daten FROM eigene_mitgliedschaft WHERE person_id = ? AND organisation_id = ?",
                            (person_id, org_id)).fetchone()
    if vorhanden is None:
        con.execute("INSERT INTO eigene_mitgliedschaft (person_id, organisation_id, daten) VALUES (?, ?, ?)",
                    (person_id, org_id, json.dumps(sauber, ensure_ascii=False)))
    elif mitgliedschaft is not None:
        alt = json.loads(vorhanden["daten"])
        con.execute("UPDATE eigene_mitgliedschaft SET daten = ? WHERE person_id = ? AND organisation_id = ?",
                    (json.dumps(sauber, ensure_ascii=False), person_id, org_id))
        _protokolliere(con, "mitgliedschaft", person_id, anzeigename(person(con, person_id)["daten"], "person_anwalt"),
                       alt, sauber, _jetzt())


def form_setzen(con: sqlite3.Connection, form: str) -> dict:
    """Organisationsform wählen oder ändern.

    Einzelanwalt ↔ Kanzlei: dieselbe Kanzlei, nur weitere Berufsträger kommen hinzu.
    Kanzlei ↔ Rechtsabteilung: die bisherige Organisation wird archiviert, die Person bleibt.
    """
    if form not in FORMEN:
        raise ValueError(f"Unbekannte Organisationsform: {form!r}")
    p = profil(con)
    alt_art, _ = _org_art(p["form"])
    neu_art, _ = _org_art(form)
    with con:
        if p["organisation_id"] and p["form"] and alt_art != neu_art:
            con.execute("UPDATE eigene_organisation SET archiviert_am = ? WHERE id = ?",
                        (_jetzt(), p["organisation_id"]))
            if p["person_id"]:
                con.execute("DELETE FROM eigene_mitgliedschaft WHERE person_id = ? AND organisation_id = ?",
                            (p["person_id"], p["organisation_id"]))
            con.execute("UPDATE eigene_profil SET organisation_id = NULL WHERE id = 1")
        if p["form"] != form:
            con.execute("INSERT INTO eigene_aenderung (zeitpunkt, objekt, objekt_id, bezeichnung, feld, alt, neu) "
                        "VALUES (?, 'profil', 1, 'Profil', 'form', ?, ?)",
                        (_jetzt(), FORMEN.get(p["form"] or ""), FORMEN[form]))
        con.execute("UPDATE eigene_profil SET form = ? WHERE id = 1", (form,))
    return stand(con)


def _form(con: sqlite3.Connection) -> str:
    form = profil(con)["form"]
    if not form:
        raise ValueError("Bitte zuerst die Organisationsform wählen.")
    return form


def organisation_speichern(con: sqlite3.Connection, daten: dict) -> dict:
    """Die eigene Kanzlei bzw. das Unternehmen der Rechtsabteilung."""
    form = _form(con)
    art, feldsatz = _org_art(form)
    p = profil(con)
    with con:
        org_id = _speichere_org(con, art, feldsatz, daten, p["organisation_id"])
        con.execute("UPDATE eigene_profil SET organisation_id = ? WHERE id = 1", (org_id,))
        if p["person_id"]:
            _verbinde(con, p["person_id"], org_id, None)
    return stand(con)


def inhaber_speichern(con: sqlite3.Connection, daten: dict, mitgliedschaft: dict | None = None) -> dict:
    """Der Profilinhaber; in Kanzleien zugleich Berufsträger."""
    form = _form(con)
    p = profil(con)
    feldsatz = _personen_art(con, p["organisation_id"], form)
    with con:
        person_id = _speichere_person(con, feldsatz, daten, p["person_id"])
        con.execute("UPDATE eigene_profil SET person_id = ? WHERE id = 1", (person_id,))
        if p["organisation_id"]:
            _verbinde(con, person_id, p["organisation_id"], mitgliedschaft)
    return stand(con)


def inhaber_waehlen(con: sqlite3.Connection, person_id: int) -> dict:
    """Kanzlei: der Profilinhaber wird aus den Berufsträgern gewählt."""
    p = profil(con)
    if not p["organisation_id"] or not con.execute(
        "SELECT 1 FROM eigene_mitgliedschaft WHERE person_id = ? AND organisation_id = ?",
        (person_id, p["organisation_id"]),
    ).fetchone():
        raise ValueError("Die Person gehört nicht zur eigenen Kanzlei.")
    with con:
        con.execute("UPDATE eigene_profil SET person_id = ? WHERE id = 1", (person_id,))
    return stand(con)


def einheit_speichern(con: sqlite3.Connection, art: str, daten: dict, einheit_id: int | None = None) -> dict:
    """Konzerngesellschaft oder beauftragte Kanzlei."""
    if art not in ARTEN_EINHEIT:
        raise ValueError(f"Unbekannte Art: {art!r}")
    with con:
        einheit_id = _speichere_org(con, art, art, daten, einheit_id)
    return {"id": einheit_id, "stand": stand(con)}


def person_speichern(con: sqlite3.Connection, organisation_id: int, daten: dict, mitgliedschaft: dict | None = None,
                     person_id: int | None = None) -> dict:
    """Berufsträger der eigenen Kanzlei oder Anwalt einer beauftragten Kanzlei."""
    org = organisation(con, organisation_id)
    if org["art"] == "kanzlei":
        feldsatz = "person_anwalt"
    elif org["art"] == "beauftragte_kanzlei":
        feldsatz = "person_extern"
    else:
        raise ValueError("Personen werden hier nur Kanzleien zugeordnet.")
    with con:
        person_id = _speichere_person(con, feldsatz, daten, person_id)
        _verbinde(con, person_id, organisation_id, mitgliedschaft if org["art"] == "kanzlei" else {})
    return {"id": person_id, "stand": stand(con)}


def archivieren(con: sqlite3.Connection, objekt: str, objekt_id: int, archiviert: bool = True) -> dict:
    tabelle = _tabelle(objekt)
    p = profil(con)
    if archiviert and objekt_id == p["organisation_id" if objekt == "organisation" else "person_id"]:
        raise ValueError("Die eigene Organisation bzw. der Profilinhaber kann nicht archiviert werden.")
    with con:
        con.execute(f"UPDATE {tabelle} SET archiviert_am = ? WHERE id = ?",
                    (_jetzt() if archiviert else None, objekt_id))
    return stand(con)


def loeschen(con: sqlite3.Connection, objekt: str, objekt_id: int) -> dict:
    """Löscht einen Eintrag ganz. Später: nur, solange keine Akte darauf verweist; sonst archivieren."""
    tabelle = _tabelle(objekt)
    p = profil(con)
    if objekt_id == p["organisation_id" if objekt == "organisation" else "person_id"]:
        raise ValueError("Die eigene Organisation bzw. der Profilinhaber kann nicht gelöscht werden.")
    with con:
        if objekt == "organisation":
            # Anwälte einer beauftragten Kanzlei gehören nur zu ihr.
            for z in con.execute("SELECT person_id FROM eigene_mitgliedschaft WHERE organisation_id = ?", (objekt_id,)):
                if z["person_id"] != p["person_id"]:
                    andere = con.execute("SELECT COUNT(*) FROM eigene_mitgliedschaft WHERE person_id = ?",
                                         (z["person_id"],)).fetchone()[0]
                    if andere == 1:
                        con.execute("DELETE FROM eigene_person WHERE id = ?", (z["person_id"],))
        con.execute(f"DELETE FROM {tabelle} WHERE id = ?", (objekt_id,))
    return stand(con)


def duplizieren(con: sqlite3.Connection, organisation_id: int) -> dict:
    org = organisation(con, organisation_id)
    if org["art"] not in ARTEN_EINHEIT:
        raise ValueError("Nur Konzerngesellschaften und beauftragte Kanzleien lassen sich duplizieren.")
    daten = dict(org["daten"], name=f"{org['daten'].get('name', '')} (Kopie)".strip())
    return einheit_speichern(con, org["art"], daten)


def assistent_fertig(con: sqlite3.Connection, fertig: bool = True) -> dict:
    with con:
        con.execute("UPDATE eigene_profil SET assistent_fertig = ? WHERE id = 1", (int(bool(fertig)),))
    return stand(con)


def aenderungen(con: sqlite3.Connection, limit: int = 50) -> list[dict]:
    return [dict(z) for z in con.execute("SELECT * FROM eigene_aenderung ORDER BY id DESC LIMIT ?", (int(limit),))]


def _tabelle(objekt: str) -> str:
    tabellen = {"organisation": "eigene_organisation", "person": "eigene_person"}
    if objekt not in tabellen:
        raise ValueError(f"Unbekanntes Objekt: {objekt!r}")
    return tabellen[objekt]


# --------------------------------------------------------------------------- Export und Import


def exportieren(con: sqlite3.Connection, pfad: str | Path) -> dict:
    """Schreibt die Eigenen Daten als JSON-Datei (Sicherung, Weitergabe an Kollegen, Testprofile)."""
    p = profil(con)
    orgs = [_org(z) for z in con.execute("SELECT * FROM eigene_organisation ORDER BY id")]
    personen = [_person(z) for z in con.execute("SELECT * FROM eigene_person ORDER BY id")]
    mitglied = [dict(z) for z in con.execute("SELECT * FROM eigene_mitgliedschaft ORDER BY id")]
    daten = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exportiert_am": _jetzt(),
        "form": p["form"],
        "organisation": f"o{p['organisation_id']}" if p["organisation_id"] else None,
        "inhaber": f"p{p['person_id']}" if p["person_id"] else None,
        "organisationen": [{"schluessel": f"o{o['id']}", "art": o["art"], "archiviert": o["archiviert"],
                            "daten": o["daten"]} for o in orgs],
        "personen": [{"schluessel": f"p{x['id']}", "archiviert": x["archiviert"], "daten": x["daten"]}
                     for x in personen],
        "mitgliedschaften": [{"person": f"p{m['person_id']}", "organisation": f"o{m['organisation_id']}",
                              "daten": json.loads(m["daten"])} for m in mitglied],
    }
    ziel = Path(pfad)
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"pfad": str(ziel), "organisationen": len(orgs), "personen": len(personen)}


def ist_leer(con: sqlite3.Connection) -> bool:
    p = profil(con)
    leer = not con.execute("SELECT 1 FROM eigene_organisation").fetchone() and not con.execute(
        "SELECT 1 FROM eigene_person").fetchone()
    return leer and not p["form"]


def importieren(con: sqlite3.Connection, pfad: str | Path, ersetzen: bool = False) -> dict:
    """Liest eine Exportdatei. Vorhandene Eigene Daten werden nur mit ``ersetzen`` überschrieben."""
    try:
        daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
    except (OSError, ValueError) as fehler:
        raise ValueError(f"Die Datei konnte nicht gelesen werden: {fehler}") from fehler
    if not isinstance(daten, dict) or daten.get("format") != EXPORT_FORMAT:
        raise ValueError("Das ist keine Exportdatei der Eigenen Daten von JuraBox.")
    if daten.get("version") != EXPORT_VERSION:
        raise ValueError(f"Unbekannte Version der Exportdatei: {daten.get('version')!r}")
    form = daten.get("form")
    if form is not None and form not in FORMEN:
        raise ValueError(f"Unbekannte Organisationsform: {form!r}")
    if not ist_leer(con) and not ersetzen:
        raise ValueError("In dieser Umgebung gibt es schon Eigene Daten. Beim Import würden sie ersetzt.")

    _, haupt_felder = _org_art(form)
    org_ids: dict[str, int] = {}
    person_ids: dict[str, int] = {}
    with con:
        con.execute("DELETE FROM eigene_mitgliedschaft")
        con.execute("UPDATE eigene_profil SET form = NULL, organisation_id = NULL, person_id = NULL, "
                    "assistent_fertig = 0 WHERE id = 1")
        con.execute("DELETE FROM eigene_person")
        con.execute("DELETE FROM eigene_organisation")
        jetzt = _jetzt()
        for o in daten.get("organisationen", []):
            art = o.get("art")
            if art not in ("kanzlei", "unternehmen", *ARTEN_EINHEIT):
                raise ValueError(f"Unbekannte Art in der Exportdatei: {art!r}")
            # Die Hauptorganisation nach der Organisationsform, frühere (archivierte) nach ihrer Art.
            feldsatz = haupt_felder if o.get("schluessel") == daten.get("organisation") else art
            sauber = bereinige(o.get("daten"), feldsatz, vorher={})
            cur = con.execute(
                "INSERT INTO eigene_organisation (art, daten, archiviert_am, angelegt_am, geaendert_am) "
                "VALUES (?, ?, ?, ?, ?)",
                (art, json.dumps(sauber, ensure_ascii=False), jetzt if o.get("archiviert") else None, jetzt, jetzt),
            )
            org_ids[o["schluessel"]] = cur.lastrowid
        arten = {o["schluessel"]: o.get("art") for o in daten.get("organisationen", [])}
        zuordnung = {m["person"]: m["organisation"] for m in daten.get("mitgliedschaften", [])}
        for x in daten.get("personen", []):
            org_art = arten.get(zuordnung.get(x["schluessel"], ""))
            feldsatz = {"unternehmen": "person_rechtsabteilung", "beauftragte_kanzlei": "person_extern"}.get(
                org_art or "", "person_rechtsabteilung" if form == "rechtsabteilung" else "person_anwalt")
            sauber = bereinige(x.get("daten"), feldsatz, vorher={})
            cur = con.execute(
                "INSERT INTO eigene_person (daten, archiviert_am, angelegt_am, geaendert_am) VALUES (?, ?, ?, ?)",
                (json.dumps(sauber, ensure_ascii=False), jetzt if x.get("archiviert") else None, jetzt, jetzt),
            )
            person_ids[x["schluessel"]] = cur.lastrowid
        for m in daten.get("mitgliedschaften", []):
            if m["person"] not in person_ids or m["organisation"] not in org_ids:
                raise ValueError("Die Exportdatei verweist auf eine unbekannte Person oder Organisation.")
            con.execute("INSERT INTO eigene_mitgliedschaft (person_id, organisation_id, daten) VALUES (?, ?, ?)",
                        (person_ids[m["person"]], org_ids[m["organisation"]],
                         json.dumps(bereinige(m.get("daten"), "mitgliedschaft", vorher={}), ensure_ascii=False)))
        con.execute(
            "UPDATE eigene_profil SET form = ?, organisation_id = ?, person_id = ?, assistent_fertig = 1 WHERE id = 1",
            (form, org_ids.get(daten.get("organisation") or ""), person_ids.get(daten.get("inhaber") or "")),
        )
        con.execute("INSERT INTO eigene_aenderung (zeitpunkt, objekt, objekt_id, bezeichnung, feld, alt, neu) "
                    "VALUES (?, 'profil', 1, 'Profil', 'import', NULL, ?)", (jetzt, Path(pfad).name))
    return stand(con)
