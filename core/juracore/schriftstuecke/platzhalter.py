"""Platzhalter für Schriftstücke und ihre Werte in einer Akte.

Die Werte kommen aus „Eigene Daten“ (Absender, Bearbeiter), den Stammdaten der Akte, den Beteiligten und dem
gewählten Verfahren. Was fehlt, bleibt leer; ``werte`` nennt dazu, wo es sich nachtragen lässt.

Rubrum: Parteibezeichnung nach Verfahrensart (Kläger/Beklagte, im Mahn-, Eil- und Beweisverfahren
Antragsteller/Antragsgegner). Bei juristischen Personen steht der gesetzliche Vertreter dabei, wie es die Klage
verlangt (§ 130 Nr. 1, § 253 Abs. 4 ZPO).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation

from .. import zeiterfassung
from ..aktenverwaltung import beteiligte, stammdaten, verfahren
from ..eigene import daten as eigene

# (Platzhalter, Bedeutung). Die Gruppe ist der Teil vor dem Punkt; die Oberfläche zeigt die Liste so an.
KATALOG: list[tuple[str, str]] = [
    ("Absender.Name", "Kanzlei bzw. Unternehmen"),
    ("Absender.Abteilung", "Bezeichnung der Rechtsabteilung"),
    ("Absender.Anschrift", "Name und Anschrift, mehrzeilig"),
    ("Absender.Zeile", "Absenderangabe in einer Zeile, z. B. über dem Anschriftfeld"),
    ("Absender.Straße", "Straße und Hausnummer"),
    ("Absender.PLZ", "Postleitzahl"),
    ("Absender.Ort", "Ort"),
    ("Absender.Telefon", "Telefon"),
    ("Absender.Fax", "Fax"),
    ("Absender.E-Mail", "E-Mail"),
    ("Absender.Website", "Website"),
    ("Absender.Kontakt", "Telefon, Fax, E-Mail und Website in einer Zeile, soweit eingetragen"),
    ("Absender.Register", "Registergericht und Registernummer"),
    ("Absender.Berufsträger", "Berufsträger der Kanzlei mit Berufs- und Fachanwaltsbezeichnung (§ 10 BORA)"),
    ("Absender.Vertreter", "Gesetzliche Vertreter des Unternehmens"),
    ("Absender.Steuernummer", "USt-IdNr., sonst Steuernummer (für Rechnungen)"),
    ("Absender.Bank", "Name der Bank"),
    ("Absender.IBAN", "IBAN"),
    ("Absender.BIC", "BIC"),
    ("Absender.Bankverbindung", "Bank, IBAN und BIC in einer Zeile"),
    ("Bearbeiter.Name", "Sachbearbeiter der Akte, sonst der Profilinhaber"),
    ("Bearbeiter.Berufsbezeichnung", "z. B. Rechtsanwältin"),
    ("Bearbeiter.Fachanwalt", "Fachanwaltsbezeichnungen"),
    ("Bearbeiter.Telefon", "Durchwahl, sonst Telefon des Absenders"),
    ("Bearbeiter.E-Mail", "E-Mail, sonst E-Mail des Absenders"),
    ("Akte.Bezeichnung", "Kurzbezeichnung der Akte"),
    ("Akte.Aktenzeichen", "Unser Zeichen"),
    ("Akte.Gegenstand", "Gegenstand"),
    ("Akte.Gegenstandswert", "Gegenstandswert in Euro"),
    ("Mandant.Name", "Mandant"),
    ("Mandant.Anschrift", "Name und Anschrift, mehrzeilig"),
    ("Mandant.Anrede", "Briefanrede, z. B. „Sehr geehrte Frau Dr. Brückner,“"),
    ("Mandant.Vertreter", "Gesetzlicher Vertreter, z. B. „vertreten durch den Geschäftsführer …“"),
    ("Gegner.Name", "Gegner"),
    ("Gegner.Anschrift", "Name und Anschrift, mehrzeilig"),
    ("Gegner.Vertreter", "Gesetzlicher Vertreter"),
    ("Gegner.Zeichen", "Zeichen des Gegners"),
    ("Gegnervertreter.Name", "Prozessbevollmächtigter des Gegners"),
    ("Gegnervertreter.Anschrift", "Name und Anschrift, mehrzeilig"),
    ("Gegnervertreter.Zeichen", "Zeichen des Gegnervertreters"),
    ("Gericht.Name", "Gericht des gewählten Verfahrens"),
    ("Gericht.Anschrift", "Gericht mit Spruchkörper und Anschrift, mehrzeilig"),
    ("Gericht.Aktenzeichen", "Gerichtliches Aktenzeichen"),
    ("Gericht.Spruchkörper", "z. B. 2. Zivilkammer"),
    ("Verfahren.Art", "z. B. Klageverfahren"),
    ("Verfahren.Instanz", "z. B. 1. Instanz"),
    ("Empfänger.Name", "Gewählter Empfänger"),
    ("Empfänger.Anschrift", "Name und Anschrift, mehrzeilig"),
    ("Empfänger.Anrede", "Briefanrede"),
    ("Empfänger.Zeichen", "Zeichen des Empfängers (bei einem Gericht das Aktenzeichen)"),
    ("Rubrum", "Parteien mit Anschrift, Rolle und Prozessbevollmächtigten, mehrzeilig"),
    ("Rubrum.Kurz", "z. B. „Brückner ./. Autohaus Rehnfeld GmbH“"),
    ("Vergütung.Stundensätze", "Stundensätze je Stufe aus der Zeiterfassung, mehrzeilig"),
    ("Vergütung.Taktung", "Satz zur Taktung nach der Vereinbarung mit dem Mandanten"),
    ("Vergütung.Kostenschätzung", "Kostenschätzung der Akte in Euro (Reiter „Zeiten“)"),
    ("Vergütung.Mindestvergütung", "Klausel zur RVG-Mindestvergütung, wenn mit dem Mandanten vereinbart"),
    ("Datum", "Heutiges Datum, z. B. 27. Oktober 2026"),
    ("Datum.Kurz", "z. B. 27.10.2026"),
    ("Datum.Ort", "Ort des Absenders und Datum"),
]

# Wo sich eine fehlende Angabe nachtragen lässt, je Gruppe.
_WO = {
    "Absender": "Eigene Daten",
    "Bearbeiter": "Eigene Daten bzw. Stammdaten (Sachbearbeiter)",
    "Akte": "Stammdaten der Akte",
    "Mandant": "Beteiligte der Akte",
    "Gegner": "Beteiligte der Akte",
    "Gegnervertreter": "Beteiligte der Akte",
    "Gericht": "Stammdaten → Verfahren bzw. Beteiligte (Gericht)",
    "Verfahren": "Stammdaten → Verfahren",
    "Empfänger": "Empfänger wählen bzw. Beteiligte der Akte",
    "Rubrum": "Beteiligte der Akte",
    "Vergütung": "Einstellungen → Zeiterfassung bzw. Reiter „Zeiten“ der Akte",
    "Datum": "Eigene Daten",
}

# Angaben, die oft zu Recht fehlen (keine Abteilung in einer Kanzlei, kein Register bei einer GbR, kein Zeichen der
# Gegenseite); leer bleiben sie ohne Hinweis.
OPTIONAL = {
    "Absender.Abteilung", "Absender.Fax", "Absender.Website", "Absender.Register", "Absender.Vertreter",
    "Absender.Berufsträger", "Absender.Steuernummer", "Absender.Bank", "Absender.IBAN", "Absender.BIC",
    "Absender.Bankverbindung", "Bearbeiter.Fachanwalt", "Akte.Gegenstand", "Akte.Gegenstandswert", "Mandant.Vertreter",
    "Gegner.Vertreter", "Gegner.Zeichen", "Gegnervertreter.Zeichen", "Empfänger.Zeichen", "Gericht.Spruchkörper",
    "Verfahren.Instanz", "Vergütung.Mindestvergütung",
}

MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember")


def schluessel(name: str) -> str:
    """Vergleichsform eines Platzhalters: „Empfänger.E-Mail“, „empfaenger.email“ und „EMPFÄNGER.E Mail“ sind gleich."""
    t = name.casefold().replace("ß", "ss")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        t = t.replace(a, b)
    return re.sub(r"[\s_\-]+", "", t)


_BEKANNT = {schluessel(k): k for k, _ in KATALOG}


def bekannt(name: str) -> str | None:
    """Der Platzhalter in der Schreibweise des Katalogs, oder None."""
    return _BEKANNT.get(schluessel(name))


def wo(name: str) -> str:
    """Wo sich der Platzhalter füllen lässt; leer bei Angaben, die oft zu Recht fehlen."""
    return "" if name in OPTIONAL else _WO.get(name.split(".")[0], "")


def datum_lang(tag: date) -> str:
    return f"{tag.day}. {MONATE[tag.month - 1]} {tag.year}"


def euro(text: str | None) -> str:
    try:
        wert = Decimal(text or "")
    except InvalidOperation:
        return text or ""
    ganz, _, cent = f"{wert:.2f}".partition(".")
    return f"{int(ganz):,}".replace(",", ".") + f",{cent} €"


# --------------------------------------------------------------------------- Personen und Anschriften


def _z(*teile: str | None, trenner: str = " ") -> str:
    return trenner.join(t for t in teile if t)


def _ausland(d: dict) -> str:
    land = (d.get("land") or "").strip()
    return "" if land.lower() in ("", "deutschland", "de", "germany") else land.upper()


def _ort_zeile(d: dict) -> str:
    return _z(d.get("plz"), d.get("ort"))


def _person_name(d: dict) -> str:
    return _z(d.get("titel"), d.get("vorname"), d.get("nachname"))


def _org_name(d: dict) -> str:
    """Name mit Rechtsform, wenn sie im Namen noch fehlt (wie im Beteiligtenverzeichnis)."""
    return beteiligte.anzeigename("organisation", d)


def _anrede(art: str, d: dict, kategorie: str = "") -> str:
    if art == "person":
        nachname = _z(d.get("titel"), d.get("nachname"))
        if d.get("anrede") == "Frau":
            return f"Sehr geehrte Frau {nachname},"
        if d.get("anrede") == "Herr":
            return f"Sehr geehrter Herr {nachname},"
    if kategorie == "Kanzlei":
        return "Sehr geehrte Kolleginnen und Kollegen,"
    return "Sehr geehrte Damen und Herren,"


def _vertreter_teil(funktion: str, name: str) -> str:
    """„den Geschäftsführer Max Rehnfeld“, „die Vorstandsvorsitzende Dr. Eva Kern“ oder nur der Name."""
    funktion = funktion.strip()
    if not funktion:
        return name
    artikel = "die" if funktion.endswith("in") or funktion.endswith("ende") else "den"
    return f"{artikel} {funktion} {name}"


class Partei:
    """Ein Beteiligter der Akte in der Form, die Schriftstücke brauchen."""

    def __init__(self, art: str, d: dict, *, kategorie: str = "", vertreter: list[str] | None = None,
                 zeichen: str = "", zusatz: list[str] | None = None):
        self.art = art
        self.d = d
        self.kategorie = kategorie
        self.vertreter = vertreter or []  # je gesetzlichem Vertreter „den Geschäftsführer …“
        self.zeichen = zeichen
        self.zusatz = zusatz or []  # Zeilen nach dem Namen im Anschriftfeld, z. B. der Spruchkörper

    @property
    def name(self) -> str:
        return _person_name(self.d) if self.art == "person" else _org_name(self.d)

    @property
    def kurzname(self) -> str:
        return (self.d.get("nachname") or self.name) if self.art == "person" else self.name

    @property
    def weiblich(self) -> bool:
        # Juristische Personen stehen im Rubrum als „die Klägerin“, „die Beklagte“.
        return self.art != "person" or self.d.get("anrede") == "Frau"

    def anschrift(self) -> str:
        zeilen = []
        if self.art == "person":
            if self.d.get("anrede") in ("Herr", "Frau"):
                zeilen.append(self.d["anrede"])
            zeilen.append(self.name)
        else:
            zeilen.append(self.name)
        zeilen += self.zusatz
        zeilen += [self.d.get("strasse", ""), _ort_zeile(self.d), _ausland(self.d)]
        return "\n".join(z for z in zeilen if z)

    def anschrift_zeile(self) -> str:
        return _z(self.d.get("strasse"), _ort_zeile(self.d), _ausland(self.d), trenner=", ")

    def anrede(self) -> str:
        return _anrede(self.art, self.d, self.kategorie)

    def vertreter_text(self) -> str:
        if not self.vertreter:
            return ""
        teile = self.vertreter
        liste = teile[0] if len(teile) == 1 else f"{', '.join(teile[:-1])} und {teile[-1]}"
        return f"vertreten durch {liste}"


def _aus_verzeichnis(con: sqlite3.Connection, beteiligter_id: int, zeichen: str) -> Partei:
    e = beteiligte.eintrag(con, beteiligter_id)
    vertreter = [_vertreter_teil(b["funktion"], _person_name(beteiligte.eintrag(con, b["von"])["daten"]) or b["name"])
        for b in e["beziehungen"] if b["art"] == "gesetzlicher_vertreter" and b["zu"] == beteiligter_id]
    return Partei(e["art"], e["daten"], kategorie=e["daten"].get("kategorie", ""), vertreter=vertreter,
                  zeichen=zeichen)


def _aus_eigenen(con: sqlite3.Connection, b: dict) -> Partei:
    if b["eigene_organisation_id"] is not None:
        o = eigene.organisation(con, b["eigene_organisation_id"])["daten"]
        vertreter = [v for v in (o.get("gesetzliche_vertreter") or "").splitlines() if v]
        return Partei("organisation", o, vertreter=vertreter, zeichen=b["aktenzeichen"])
    # Vertretender Anwalt aus „Eigene Daten“: Anschrift der beauftragten Kanzlei bzw. des eigenen Unternehmens.
    p = eigene.person(con, b["eigene_person_id"])["daten"]
    org = con.execute("SELECT o.daten FROM eigene_mitgliedschaft m JOIN eigene_organisation o "
                      "ON o.id = m.organisation_id WHERE m.person_id = ? ORDER BY o.id LIMIT 1",
                      (b["eigene_person_id"],)).fetchone()
    od = json.loads(org["daten"]) if org else {}
    anschrift = {k: od.get(k, "") for k in ("strasse", "plz", "ort", "land")}
    return Partei("person", {**p, **anschrift}, zeichen=b["aktenzeichen"],
                  zusatz=[od["name"]] if od.get("name") else [])


def partei(con: sqlite3.Connection, b: dict) -> Partei:
    """Eine Beteiligung (aus ``stammdaten.beteiligungen``) als Partei."""
    if b["beteiligter_id"] is not None:
        return _aus_verzeichnis(con, b["beteiligter_id"], b["aktenzeichen"])
    return _aus_eigenen(con, b)


# --------------------------------------------------------------------------- Absender und Bearbeiter


def _fachanwalt(d: dict) -> str:
    weiblich = d.get("anrede") == "Frau" or "anwältin" in (d.get("berufsbezeichnung") or "")
    titel = "Fachanwältin für" if weiblich else "Fachanwalt für"
    return ", ".join(f"{titel} {g}" for g in d.get("fachanwalt") or [])


def _beruf(d: dict) -> str:
    beruf = d.get("berufsbezeichnung") or ""
    if not beruf and (d.get("zulassungsstatus") or "").startswith("Syndikus"):
        beruf = "Syndikusrechtsanwältin" if d.get("anrede") == "Frau" else "Syndikusrechtsanwalt"
    if beruf in ("Sonstige", "Volljurist ohne Zulassung", "Volljuristin ohne Zulassung"):
        beruf = ""
    return beruf or d.get("funktion", "")


def _absender(con: sqlite3.Connection) -> tuple[dict, dict | None]:
    s = eigene.stand(con, mit_archiv=False)
    w: dict[str, str] = {}
    haupt = s["organisation"]
    if haupt is None:
        return w, s["inhaber"]
    d = haupt["daten"]
    rechtsabteilung = s["profil"]["form"] == "rechtsabteilung"
    name = s["organisation_name"]
    w["Absender.Name"] = name
    w["Absender.Abteilung"] = d.get("abteilung", "") if rechtsabteilung else ""
    w["Absender.Straße"] = d.get("strasse", "")
    w["Absender.PLZ"] = d.get("plz", "")
    w["Absender.Ort"] = d.get("ort", "")
    w["Absender.Anschrift"] = "\n".join(z for z in (name, w["Absender.Abteilung"], d.get("strasse"), _ort_zeile(d),
                                                     _ausland(d)) if z)
    w["Absender.Zeile"] = _z(name, d.get("strasse"), _ort_zeile(d), trenner=" · ")
    w["Absender.Telefon"] = d.get("abteilung_telefon" if rechtsabteilung else "telefon", "") or d.get("telefon", "")
    w["Absender.Fax"] = d.get("fax", "")
    w["Absender.E-Mail"] = d.get("abteilung_email" if rechtsabteilung else "email", "") or d.get("email", "")
    w["Absender.Website"] = d.get("website", "")
    w["Absender.Kontakt"] = " · ".join(
        f"{titel} {w[k]}".strip() for titel, k in (("Telefon", "Absender.Telefon"), ("Fax", "Absender.Fax"),
                                                  ("", "Absender.E-Mail"), ("", "Absender.Website")) if w[k])
    w["Absender.Register"] = _z(d.get("registergericht"), d.get("registernummer"), trenner=", ")
    w["Absender.Vertreter"] = ", ".join((d.get("gesetzliche_vertreter") or "").splitlines())
    w["Absender.Berufsträger"] = " · ".join(
        _z(_person_name(b["daten"]), _beruf(b["daten"]), _fachanwalt(b["daten"]), trenner=", ")
        for b in s["berufstraeger"] if not b["archiviert"] and not b["mitgliedschaft"].get("ausgeschieden_am"))
    if d.get("ust_id"):
        w["Absender.Steuernummer"] = f"USt-IdNr. {d['ust_id']}"
    elif d.get("steuernummer"):
        w["Absender.Steuernummer"] = f"Steuernummer {d['steuernummer']}"
    w["Absender.Bank"] = d.get("bank", "")
    w["Absender.IBAN"] = d.get("iban", "")
    w["Absender.BIC"] = d.get("bic", "")
    w["Absender.Bankverbindung"] = _z(d.get("bank"), f"IBAN {d['iban']}" if d.get("iban") else "",
                                      f"BIC {d['bic']}" if d.get("bic") else "", trenner=" · ")
    return w, s["inhaber"]


def _bearbeiter(con: sqlite3.Connection, akte: dict, inhaber: dict | None, absender: dict) -> dict:
    person = None
    if akte.get("sachbearbeiter_id"):
        try:
            person = eigene.person(con, akte["sachbearbeiter_id"])
        except LookupError:
            person = None
    person = person or inhaber
    d = person["daten"] if person else {}
    return {
        "Bearbeiter.Name": _person_name(d),
        "Bearbeiter.Berufsbezeichnung": _beruf(d),
        "Bearbeiter.Fachanwalt": _fachanwalt(d),
        "Bearbeiter.Telefon": d.get("telefon") or absender.get("Absender.Telefon", ""),
        "Bearbeiter.E-Mail": d.get("email") or absender.get("Absender.E-Mail", ""),
    }


# --------------------------------------------------------------------------- Rubrum

_BEZEICHNUNG = {
    # Verfahrensart: (Eingang, aktiv männlich, aktiv weiblich, passiv männlich, passiv weiblich)
    "antrag": ("In dem Verfahren", "Antragsteller", "Antragstellerin", "Antragsgegner", "Antragsgegnerin"),
    "klage": ("In dem Rechtsstreit", "Kläger", "Klägerin", "Beklagter", "Beklagte"),
}
_ANTRAGSVERFAHREN = ("mahnverfahren", "eilverfahren", "beweisverfahren", "beschwerde")


def _rolle(art: str, aktiv: bool, p: Partei, nummer: int | None) -> str:
    _, am, aw, pm, pw = _BEZEICHNUNG["antrag" if art in _ANTRAGSVERFAHREN else "klage"]
    text = (aw if p.weiblich else am) if aktiv else (pw if p.weiblich else pm)
    return f"{text} zu {nummer}" if nummer else text


def _partei_block(p: Partei, rolle: str, bevollmaechtigte: str) -> list[str]:
    zeilen = [_z(p.name, p.vertreter_text(), p.anschrift_zeile(), trenner=", ")]
    zeilen.append(f"\t– {rolle} –")
    if bevollmaechtigte:
        zeilen.append(f"Prozessbevollmächtigte: {bevollmaechtigte}")
    return zeilen


def _seite(parteien: list[Partei], art: str, aktiv: bool, bevollmaechtigte: str) -> list[str]:
    zeilen: list[str] = []
    for i, p in enumerate(parteien, start=1):
        if zeilen:
            zeilen.append("")
        zeilen += _partei_block(p, _rolle(art, aktiv, p, i if len(parteien) > 1 else None),
                                bevollmaechtigte if i == len(parteien) else "")
    return zeilen


def _kanzlei_zeile(p: Partei) -> str:
    teile = [p.name] + p.zusatz
    return _z(*teile, p.anschrift_zeile(), trenner=", ")


# --------------------------------------------------------------------------- Werte einer Akte


MINDESTVERGUETUNG = ("In gerichtlichen Verfahren schuldet der Auftraggeber mindestens die gesetzliche Vergütung nach "
                     "dem RVG. Übersteigt sie das nach Zeitaufwand berechnete Honorar, wird statt des Zeithonorars die "
                     "gesetzliche Vergütung berechnet; beide werden nicht nebeneinander berechnet.")


def _verguetung(con: sqlite3.Connection, akte_id: int) -> dict[str, str]:
    """Angaben aus der Zeiterfassung für die Vergütungsvereinbarung."""
    if con.execute("SELECT 1 FROM sqlite_master WHERE name = 'zeit_vereinbarung'").fetchone() is None:
        return {}
    v = zeiterfassung.vereinbarung(con, akte_id)
    stufen = con.execute("SELECT name, satz FROM zeit_stufe ORDER BY reihenfolge, id").fetchall()
    takt = v["taktung"]
    if takt == 1:
        taktung = "Die Zeit wird minutengenau erfasst und abgerechnet."
    else:
        stunde = zeiterfassung.stunden_text(takt)
        taktung = (f"Die Zeit wird je Tätigkeit in Einheiten von {takt} Minuten ({stunde} Stunde) abgerechnet; eine "
                   "angefangene Einheit wird aufgerundet.")
    return {"Vergütung.Stundensätze": "\n".join(f"{s['name']}: {euro(s['satz'])} je Stunde" for s in stufen),
            "Vergütung.Taktung": taktung,
            "Vergütung.Kostenschätzung": euro(v["kostenschaetzung"]) if v["kostenschaetzung"] else "",
            "Vergütung.Mindestvergütung": MINDESTVERGUETUNG if v["mindestverguetung"] else ""}


def werte(con: sqlite3.Connection, akte_id: int, empfaenger_id: int | None = None, verfahren_id: int | None = None,
          heute: date | None = None) -> dict:
    """Alle Platzhalter mit ihrem Wert in dieser Akte (leer, wo nichts eingetragen ist) und Hinweise.

    ``empfaenger_id`` ist die Beteiligung (Zeile der Beteiligtenliste), ``verfahren_id`` das Verfahren für Gericht und
    Rubrum; ohne Angabe gilt das aktuelle Verfahren.
    """
    heute = heute or date.today()
    akte = stammdaten.stammdaten(con, akte_id)
    bet = akte["beteiligte"]
    hinweise: list[str] = []
    w: dict[str, str] = {k: "" for k, _ in KATALOG}

    absender, inhaber = _absender(con)
    w.update(absender)
    w.update(_bearbeiter(con, akte, inhaber, absender))

    w["Akte.Bezeichnung"] = akte.get("name") or ""
    w["Akte.Aktenzeichen"] = akte.get("aktenzeichen") or ""
    w["Akte.Gegenstand"] = akte.get("gegenstand") or ""
    w["Akte.Gegenstandswert"] = euro(akte.get("gegenstandswert")) if akte.get("gegenstandswert") else ""

    parteien = {b["id"]: partei(con, b) for b in bet}

    def von(rolle: str) -> list[tuple[dict, Partei]]:
        return [(b, parteien[b["id"]]) for b in bet if b["rolle"] == rolle]

    mandanten, gegner, gegnervertreter = von("mandant"), von("gegner"), von("bevollmaechtigter_gegner")
    if mandanten:
        m = mandanten[0][1]
        w["Mandant.Name"] = ", ".join(p.name for _, p in mandanten)
        w["Mandant.Anschrift"] = m.anschrift()
        w["Mandant.Anrede"] = m.anrede()
        w["Mandant.Vertreter"] = m.vertreter_text()
    if gegner:
        g = gegner[0][1]
        w["Gegner.Name"] = ", ".join(p.name for _, p in gegner)
        w["Gegner.Anschrift"] = g.anschrift()
        w["Gegner.Vertreter"] = g.vertreter_text()
        w["Gegner.Zeichen"] = g.zeichen
    if gegnervertreter:
        gv = gegnervertreter[0][1]
        w["Gegnervertreter.Name"] = gv.name
        w["Gegnervertreter.Anschrift"] = gv.anschrift()
        w["Gegnervertreter.Zeichen"] = gv.zeichen

    # Verfahren und Gericht
    alle = verfahren.liste(con, akte_id)
    v = next((x for x in alle if x["id"] == verfahren_id), None) if verfahren_id else verfahren.aktuelles(alle)
    gericht_bet = None
    if v:
        w["Verfahren.Art"] = v["art_text"]
        w["Verfahren.Instanz"] = v.get("instanz") or ""
        w["Gericht.Spruchkörper"] = v.get("spruchkoerper") or ""
        if v.get("gericht"):
            s = beteiligte.schluessel(v["gericht"])
            gericht_bet = next((b for b in bet if b["rolle"] == "gericht" and beteiligte.schluessel(b["name"]) == s),
                               None)
            w["Gericht.Name"] = v["gericht"]
        w["Gericht.Aktenzeichen"] = v.get("aktenzeichen") or (gericht_bet or {}).get("aktenzeichen", "")
    else:
        gericht_bet = next((b for b in bet if b["rolle"] == "gericht"), None)
        if gericht_bet:
            w["Gericht.Name"] = gericht_bet["name"]
            w["Gericht.Aktenzeichen"] = gericht_bet["aktenzeichen"]
    if gericht_bet:
        gp = parteien[gericht_bet["id"]]
        gp.zusatz = [w["Gericht.Spruchkörper"]] if w["Gericht.Spruchkörper"] else []
        w["Gericht.Anschrift"] = gp.anschrift()
    elif w["Gericht.Name"]:
        w["Gericht.Anschrift"] = "\n".join(z for z in (w["Gericht.Name"], w["Gericht.Spruchkörper"]) if z)

    # Empfänger
    e_bet = next((b for b in bet if b["id"] == empfaenger_id), None) if empfaenger_id else None
    if e_bet:
        e = parteien[e_bet["id"]]
        if e_bet is gericht_bet:
            w["Empfänger.Anschrift"] = w["Gericht.Anschrift"]
            w["Empfänger.Zeichen"] = w["Gericht.Aktenzeichen"]
        else:
            w["Empfänger.Anschrift"] = e.anschrift()
            w["Empfänger.Zeichen"] = e.zeichen
        w["Empfänger.Name"] = e.name
        w["Empfänger.Anrede"] = e.anrede()

    # Rubrum
    art = v["art"] if v else "klage"
    rolle = akte.get("eigene_rolle") or ""
    if "Beklagten" in rolle:
        mandant_aktiv = False
    else:
        mandant_aktiv = True
        if "Klägers" not in rolle and mandanten and gegner:
            hinweise.append("Im Rubrum steht der Mandant auf der Klägerseite, weil in den Stammdaten keine "
                            "Prozessrolle („Prozessbevollmächtigter des Klägers/Beklagten“) eingetragen ist.")
    eigene_vertretung = ""
    vertretende = von("vertretender_anwalt")
    if vertretende:
        eigene_vertretung = _kanzlei_zeile(vertretende[0][1])
    elif absender.get("Absender.Name"):
        eigene_vertretung = _z(absender["Absender.Name"], absender.get("Absender.Straße"),
                               _z(absender.get("Absender.PLZ"), absender.get("Absender.Ort")), trenner=", ")
    gegen_vertretung = _kanzlei_zeile(gegnervertreter[0][1]) if gegnervertreter else ""
    m_seite = _seite([p for _, p in mandanten], art, mandant_aktiv, eigene_vertretung)
    g_seite = _seite([p for _, p in gegner], art, not mandant_aktiv, gegen_vertretung)
    aktiv, passiv = (m_seite, g_seite) if mandant_aktiv else (g_seite, m_seite)
    if aktiv or passiv:
        eingang = _BEZEICHNUNG["antrag" if art in _ANTRAGSVERFAHREN else "klage"][0]
        zeilen = [eingang, "", *aktiv, "", "gegen", "", *passiv]
        if w["Akte.Gegenstand"]:
            zeilen += ["", f"wegen {w['Akte.Gegenstand']}"]
        w["Rubrum"] = "\n".join(zeilen)
        kurz_m = ", ".join(p.kurzname for _, p in mandanten)
        kurz_g = ", ".join(p.kurzname for _, p in gegner)
        a, b = (kurz_m, kurz_g) if mandant_aktiv else (kurz_g, kurz_m)
        w["Rubrum.Kurz"] = " ./. ".join(t for t in (a, b) if t)

    w.update(_verguetung(con, akte_id))

    w["Datum"] = datum_lang(heute)
    w["Datum.Kurz"] = heute.strftime("%d.%m.%Y")
    w["Datum.Ort"] = _z(absender.get("Absender.Ort"), datum_lang(heute), trenner=", ")

    return {"werte": w, "hinweise": hinweise, "verfahren": v}


def katalog() -> list[dict]:
    return [{"platzhalter": k, "gruppe": k.split(".")[0], "bedeutung": b, "wo": wo(k)} for k, b in KATALOG]
