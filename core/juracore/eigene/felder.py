"""Felder der Eigenen Daten je Organisationsform; die Oberfläche baut ihre Formulare daraus.

Fundstellen der Auswahllisten:
- Fachanwaltsbezeichnungen: § 1 FAO (24 Fachgebiete), höchstens drei je Person: § 43c Abs. 1 BRAO.
- Rechtsanwaltskammern: 27 regionale Kammern und die Rechtsanwaltskammer beim Bundesgerichtshof.
"""

from __future__ import annotations

FORMEN = {
    "einzelanwalt": "Einzelanwalt",
    "kanzlei": "Kanzlei",
    "rechtsabteilung": "Rechtsabteilung",
}

FACHANWALT = [
    "Verwaltungsrecht", "Steuerrecht", "Arbeitsrecht", "Sozialrecht", "Familienrecht", "Strafrecht",
    "Insolvenz- und Sanierungsrecht", "Versicherungsrecht", "Medizinrecht", "Miet- und Wohnungseigentumsrecht",
    "Verkehrsrecht", "Bau- und Architektenrecht", "Erbrecht", "Transport- und Speditionsrecht",
    "gewerblichen Rechtsschutz", "Handels- und Gesellschaftsrecht", "Urheber- und Medienrecht",
    "Informationstechnologierecht", "Bank- und Kapitalmarktrecht", "Agrarrecht", "Internationales Wirtschaftsrecht",
    "Vergaberecht", "Migrationsrecht", "Sportrecht",
]
FACHANWALT_HOECHSTENS = 3

KAMMERN = [
    "Rechtsanwaltskammer Bamberg", "Rechtsanwaltskammer Berlin", "Brandenburgische Rechtsanwaltskammer",
    "Rechtsanwaltskammer für den Oberlandesgerichtsbezirk Braunschweig", "Hanseatische Rechtsanwaltskammer Bremen",
    "Rechtsanwaltskammer für den Oberlandesgerichtsbezirk Celle", "Rechtsanwaltskammer Düsseldorf",
    "Rechtsanwaltskammer Frankfurt", "Rechtsanwaltskammer Freiburg", "Hanseatische Rechtsanwaltskammer Hamburg",
    "Rechtsanwaltskammer für den Oberlandesgerichtsbezirk Hamm", "Rechtsanwaltskammer Karlsruhe",
    "Rechtsanwaltskammer Kassel", "Rechtsanwaltskammer Koblenz", "Rechtsanwaltskammer Köln",
    "Rechtsanwaltskammer Mecklenburg-Vorpommern", "Rechtsanwaltskammer für den Oberlandesgerichtsbezirk München",
    "Rechtsanwaltskammer Nürnberg", "Rechtsanwaltskammer für den Oberlandesgerichtsbezirk Oldenburg",
    "Rechtsanwaltskammer des Saarlandes", "Rechtsanwaltskammer Sachsen",
    "Rechtsanwaltskammer des Landes Sachsen-Anhalt",
    "Schleswig-Holsteinische Rechtsanwaltskammer", "Rechtsanwaltskammer Stuttgart", "Rechtsanwaltskammer Thüringen",
    "Rechtsanwaltskammer Tübingen", "Pfälzische Rechtsanwaltskammer Zweibrücken",
    "Rechtsanwaltskammer beim Bundesgerichtshof",
]

BERUFSBEZEICHNUNGEN = [
    "Rechtsanwalt", "Rechtsanwältin", "Syndikusrechtsanwalt", "Syndikusrechtsanwältin", "Rechtsanwalt und Notar",
    "Rechtsanwältin und Notarin", "Volljurist ohne Zulassung", "Volljuristin ohne Zulassung", "Sonstige",
]
ZULASSUNGSSTATUS = [
    "Syndikusrechtsanwalt", "Syndikusrechtsanwalt und niedergelassener Rechtsanwalt", "Niedergelassener Rechtsanwalt",
    "Ohne Zulassung",
]
RECHTSFORMEN_KANZLEI = ["GbR/Sozietät", "PartG", "PartG mbB", "GmbH", "AG", "Sonstige"]
RECHTSFORMEN_UNTERNEHMEN = [
    "GmbH", "AG", "SE", "KG", "GmbH & Co. KG", "OHG", "UG (haftungsbeschränkt)", "eG", "e. V.", "Einzelunternehmen",
    "Ausländische Gesellschaft", "Sonstige",
]
# Rechtsformen, deren Geschäftsbriefe Registergericht und Registernummer nennen müssen (Abschnitt 6 des Konzepts).
REGISTERPFLICHTIG = {
    "PartG": "§ 7 Abs. 3 PartGG i. V. m. § 125 HGB",
    "PartG mbB": "§ 7 Abs. 3 PartGG i. V. m. § 125 HGB",
    "GmbH": "§ 35a Abs. 1 GmbHG",
    "AG": "§ 80 Abs. 1 AktG",
}
STELLUNGEN = ["Gesellschafter/Partner", "Angestellt", "Freie Mitarbeit", "Of Counsel"]
BEZIEHUNGEN = ["Muttergesellschaft", "Tochtergesellschaft", "Schwestergesellschaft", "Sonstige"]
ANREDEN = ["Herr", "Frau", "Ohne Anrede"]


def feld(schluessel: str, titel: str, typ: str = "text", pflicht: bool = False, **weiteres) -> dict:
    return {"schluessel": schluessel, "titel": titel, "typ": typ, "pflicht": pflicht, **weiteres}


def _anschrift(pflicht: bool) -> list[dict]:
    return [
        feld("strasse", "Straße und Hausnummer", pflicht=pflicht),
        feld("plz", "PLZ", pflicht=pflicht),
        feld("ort", "Ort", pflicht=pflicht),
        feld("land", "Land", vorgabe="Deutschland"),
    ]


_PERSON = [
    feld("anrede", "Anrede", "auswahl", optionen=ANREDEN),
    feld("titel", "Akademischer Titel", hinweis="z. B. Dr."),
    feld("vorname", "Vorname", pflicht=True),
    feld("nachname", "Nachname", pflicht=True),
]
_BERUF = [
    feld("berufsbezeichnung", "Berufsbezeichnung", "auswahl", pflicht=True, optionen=BERUFSBEZEICHNUNGEN),
    feld("fachanwalt", "Fachanwaltsbezeichnungen", "mehrfach", optionen=FACHANWALT, hoechstens=FACHANWALT_HOECHSTENS,
         hinweis="Höchstens drei (§ 43c Abs. 1 BRAO)."),
    feld("kammer", "Rechtsanwaltskammer", "auswahl", optionen=KAMMERN,
         hinweis="Die Zulassung erfolgt durch die Kammer; eine Bindung an ein Gericht gibt es nicht."),
    feld("safe_id", "beA-SAFE-ID",
         hinweis="Persönliches beA (§ 31a BRAO); hilft später, eigene Schriftsätze zu erkennen."),
]
_KONTAKT_PERSON = [
    feld("telefon", "Durchwahl", "tel"),
    feld("email", "E-Mail", "email"),
]
_HAFTPFLICHT = [
    feld("haftpflicht_versicherer", "Berufshaftpflicht: Versicherer",
         hinweis="Pflichtinformation gegenüber Mandanten (§ 2 Abs. 1 Nr. 11 DL-InfoV)."),
    feld("haftpflicht_anschrift", "Berufshaftpflicht: Anschrift des Versicherers"),
    feld("haftpflicht_geltungsbereich", "Berufshaftpflicht: räumlicher Geltungsbereich"),
]
_KONTAKT_ORG = [
    feld("telefon", "Telefon", "tel"),
    feld("fax", "Fax", "tel"),
    feld("email", "E-Mail", "email"),
    feld("website", "Website", "url"),
]
# Angaben für Kostennoten: § 14 Abs. 4 UStG (Steuernummer oder USt-IdNr., fortlaufende Rechnungsnummer).
_RECHNUNG = [
    feld("steuernummer", "Steuernummer",
         hinweis="Auf jeder Rechnung steht die Steuernummer oder die USt-IdNr. (§ 14 Abs. 4 S. 1 Nr. 2 UStG)."),
    feld("ust_id", "USt-IdNr.", hinweis="Wenn vorhanden, steht sie statt der Steuernummer auf der Rechnung."),
    feld("bank", "Bank"),
    feld("iban", "IBAN"),
    feld("bic", "BIC"),
    feld("rechnungsnummer_muster", "Muster der Rechnungsnummer", vorgabe="{JJJJ}-{NNNN}",
         hinweis="{JJJJ} = Jahr, {NNNN} = laufende Nummer, jedes Jahr neu ab 1. Die Nummer muss einmalig sein "
                 "(§ 14 Abs. 4 S. 1 Nr. 4 UStG)."),
]
_REGISTER = [
    feld("registergericht", "Registergericht"),
    feld("registernummer", "Registernummer", hinweis="z. B. HRB 12345 oder PR 678"),
]

FELDER: dict[str, list[dict]] = {
    # Profilinhaber und Berufsträger einer Kanzlei bzw. eines Einzelanwalts.
    "person_anwalt": _PERSON + _BERUF + _KONTAKT_PERSON,
    # Profilinhaber einer Rechtsabteilung.
    "person_rechtsabteilung": _PERSON + [
        feld("zulassungsstatus", "Zulassungsstatus", "auswahl", pflicht=True, optionen=ZULASSUNGSSTATUS,
             hinweis="Wird beim Anlegen einer Akte gebraucht (§ 46c Abs. 2 BRAO)."),
        feld("funktion", "Funktion", hinweis="z. B. Head of Legal"),
    ] + _BERUF[1:] + _KONTAKT_PERSON,
    # Anwälte einer beauftragten Kanzlei.
    "person_extern": _PERSON + [
        feld("berufsbezeichnung", "Berufsbezeichnung", "auswahl", optionen=BERUFSBEZEICHNUNGEN),
    ] + _BERUF[1:2] + [_BERUF[3]] + _KONTAKT_PERSON,
    # Zugehörigkeit eines Berufsträgers zur eigenen Kanzlei.
    "mitgliedschaft": [
        feld("stellung", "Stellung", "auswahl", optionen=STELLUNGEN),
        feld("standort", "Standort", hinweis="Hauptkanzlei oder Zweigstelle"),
        feld("dezernat", "Dezernat"),
        feld("vertretungsorgan", "Geschäftsführer bzw. Vorstand", "ja_nein",
             hinweis="Bei GmbH und AG: erscheint auf dem Briefbogen (§ 35a GmbHG, § 80 AktG)."),
        feld("ausgeschieden_am", "Ausgeschieden am", "datum",
             hinweis="Ausgeschiedene nur noch erkennbar als ausgeschieden nennen (§ 10 Abs. 4 BORA)."),
    ],
    "einzelanwalt": [
        feld("name", "Kanzleiname", hinweis="Leer lassen für „Rechtsanwalt Vorname Nachname“."),
        *_anschrift(True),
        feld("zweigstellen", "Zweigstellen", "mehrzeilig", hinweis="Eine Anschrift je Zeile."),
        *_KONTAKT_ORG,
        *_HAFTPFLICHT,
        *_RECHNUNG,
    ],
    "kanzlei": [
        feld("name", "Name bzw. Kurzbezeichnung", pflicht=True),
        feld("rechtsform", "Rechtsform", "auswahl", pflicht=True, optionen=RECHTSFORMEN_KANZLEI),
        *_anschrift(True),
        feld("zweigstellen", "Zweigstellen", "mehrzeilig", hinweis="Eine Anschrift je Zeile."),
        *_KONTAKT_ORG,
        *_REGISTER,
        feld("bea_kanzlei", "beA der Kanzlei (SAFE-ID)",
             hinweis="Postfach der Berufsausübungsgesellschaft (§ 31b BRAO)."),
        *_HAFTPFLICHT,
        *_RECHNUNG,
    ],
    "unternehmen": [
        feld("name", "Firma", pflicht=True),
        feld("rechtsform", "Rechtsform", "auswahl", optionen=RECHTSFORMEN_UNTERNEHMEN),
        feld("kurzname", "Kurzname"),
        *_anschrift(True),
        *_REGISTER,
        feld("gesetzliche_vertreter", "Gesetzliche Vertreter", "mehrzeilig", hinweis="Eine Person je Zeile."),
        feld("abteilung", "Bezeichnung der Rechtsabteilung", vorgabe="Rechtsabteilung"),
        feld("abteilung_email", "Funktionspostfach (E-Mail)", "email"),
        feld("abteilung_telefon", "Telefon der Rechtsabteilung", "tel"),
        feld("ebo", "eBO-Postfach des Unternehmens"),
    ],
    "konzerngesellschaft": [
        feld("name", "Firma", pflicht=True),
        feld("rechtsform", "Rechtsform", "auswahl", optionen=RECHTSFORMEN_UNTERNEHMEN),
        feld("kurzname", "Kurzname"),
        feld("strasse", "Straße und Hausnummer"),
        feld("plz", "PLZ"),
        feld("ort", "Sitz (Ort)", pflicht=True),
        feld("land", "Land", vorgabe="Deutschland"),
        *_REGISTER,
        feld("gesetzliche_vertreter", "Gesetzliche Vertreter", "mehrzeilig",
             hinweis="Eine Person je Zeile; die Klage muss sie nennen (§ 130 Nr. 1, § 253 Abs. 4 ZPO)."),
        feld("interne_kennung", "Interne Kennung"),
        feld("beziehung", "Verhältnis zum Unternehmen", "auswahl", optionen=BEZIEHUNGEN),
    ],
    "beauftragte_kanzlei": [
        feld("name", "Kanzleiname", pflicht=True),
        feld("rechtsform", "Rechtsform", "auswahl", optionen=RECHTSFORMEN_KANZLEI),
        *_anschrift(False),
        feld("telefon", "Telefon", "tel"),
        feld("email", "E-Mail", "email"),
        feld("bea_kanzlei", "beA der Kanzlei (SAFE-ID)"),
    ],
}


def felder_von(art: str) -> list[dict]:
    if art not in FELDER:
        raise ValueError(f"Unbekannte Art: {art!r}")
    return FELDER[art]
