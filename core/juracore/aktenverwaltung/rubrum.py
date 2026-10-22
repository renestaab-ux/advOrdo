"""Rubrum erkennen: Gericht, Aktenzeichen, Parteien, Prozessbevollmächtigte, Gegenstand und Streitwert.

Grundlage für „Akte aus Dokument anlegen“. Gelesen wird der Kopf eines Schriftsatzes, einer Verfügung oder eines
Mahnbescheids; jedes erkannte Feld trägt seine Fundstelle (Abschnitt und Seite), damit es vor der Übernahme
geprüft werden kann. Übernommen wird nichts ohne Bestätigung.

Erkannt werden die üblichen Formen:
- Rolle nach der Partei: „Weber Haustechnik GmbH, …, vertreten durch … – Beklagte –“, auch „– Beklagte zu 2) –“
- Rolle vor der Partei (Mahnbescheid): „Antragsteller: Frau Dr. Lena Brückner, …“
- Kurzrubrum: „Dr. Lena Brückner ./. Weber Haustechnik GmbH“
"""

from __future__ import annotations

import re

_STRICH = r"[–—-]"
_ROLLEN = {
    # Wortstamm → (Seite, Rolle in der Akte aus Sicht der Partei)
    "kläger": "aktiv", "klägerin": "aktiv", "antragsteller": "aktiv", "antragstellerin": "aktiv",
    "berufungskläger": "aktiv", "berufungsklägerin": "aktiv", "gläubiger": "aktiv", "gläubigerin": "aktiv",
    "beklagte": "passiv", "beklagter": "passiv", "beklagten": "passiv", "antragsgegner": "passiv",
    "antragsgegnerin": "passiv", "berufungsbeklagte": "passiv", "berufungsbeklagter": "passiv",
    "schuldner": "passiv", "schuldnerin": "passiv",
}
_ROLLE = (r"(?P<rolle>Berufungskläger(?:in)?|Berufungsbeklagte[r]?|Kläger(?:in)?|Beklagte[rn]?|"
          r"Antragsteller(?:in)?|Antragsgegner(?:in)?|Gläubiger(?:in)?|Schuldner(?:in)?)")
_EREIGNIS = re.compile(
    r"(?P<bev>(?:Prozess|Verfahrens)bevollmächtigte[rn]?(?:\s+(?:des|der)\s+[A-ZÄÖÜ]\w+)?\s*:)"
    r"|(?P<nach>" + _STRICH + r"\s*" + _ROLLE + r"(?:\s+(?P<zu>zu\s*\d+\)?))?\s*" + _STRICH + r")"
    r"|(?P<vor>(?:^|¶)\s*" + _ROLLE.replace("rolle", "vrolle") + r"\s*:)"
    r"|(?P<gegen>¶\s*gegen\s*(?=¶))"
)
_ANFANG = re.compile(r"^(?:In dem Rechtsstreit|In Sachen|In der Sache|In dem Verfahren|In der Zwangsvollstreckungs)",
                     re.IGNORECASE)
_LABEL_ANFANG = re.compile(r"^" + _ROLLE + r"\s*:")
_ENDE = re.compile(
    r"^(?:wegen\b|(?:Vorläufiger\s+)?Streitwert|Gegenstandswert|Der Antragsteller macht|Wir beantragen|"
    r"Namens und in Vollmacht|begründen wir|beantragen wir|erheben wir|Verfügung$|Beschluss$|Urteil$|"
    r"hat die|erlässt|wird\s)", re.IGNORECASE)
_GERICHT = re.compile(
    r"^(?:An\s+(?:das|den)\s+)?(?P<art>Amtsgericht|Landgericht|Oberlandesgericht|Kammergericht|Bundesgerichtshof|Arbeitsgericht|"
    r"Landesarbeitsgericht|Bundesarbeitsgericht|Verwaltungsgericht|Oberverwaltungsgericht|"
    r"Verwaltungsgerichtshof|Sozialgericht|Landessozialgericht|Finanzgericht)\b(?P<rest>.*)$")
_SPRUCHKOERPER = re.compile(r"((?:\d+\.\s*)?(?:Zivilkammer|Zivilsenat|Kammer für Handelssachen|Senat|Abteilung|"
                            r"Kammer)[\w\s]*?)(?=\s*" + _STRICH + r"|$|,)")
_AZ = re.compile(
    r"(?:Aktenzeichen|Az\.|Geschäftsnummer|Geschäftszeichen|Gesch\.-Nr\.)\s*:?\s*"
    r"(?P<az>\d{1,3}\s?[A-Za-zÄÖÜ]{1,4}\s?\d{1,6}/\d{2,4}(?:\s?[A-Z]{1,3}\b)?|\d{2}-\d{5,8}-\d{1,2}-\d)")
_ZEICHEN = re.compile(r"\b(?:Unser|Ihr)?\s*Zeichen:?\s+(?P<z>\d{1,6}/\d{2}(?:\s[A-ZÄÖÜ]{1,4}\b)?)")
_WEGEN = re.compile(r"^wegen:?\s+(?P<g>.+?)(?=\s+(?:Vorläufiger\s+)?Streitwert|$)", re.IGNORECASE)
_BETRAG = r"(?P<b>\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:€|Euro|EUR)"
_STREITWERT = re.compile(r"(?:Streitwert|Gegenstandswert)\s*:?\s*(?:bis\s+)?" + _BETRAG, re.IGNORECASE)
_HAUPTFORDERUNG = re.compile(r"Hauptforderung:\s*(?P<g>.+?)\s*" + _STRICH + r"\s*" + _BETRAG)
_KURZRUBRUM = re.compile(r"^(?P<a>[^¶]{3,120}?)\s+\./\.\s+(?P<p>[^¶]{3,120})$")
_RECHTSFORM = re.compile(
    r"\b(?:GmbH\s*&\s*Co\.\s*KGaA|GmbH\s*&\s*Co\.\s*KG|UG\s*\(haftungsbeschränkt\)(?:\s*&\s*Co\.\s*KG)?|"
    r"PartG\s*mbB|Partnerschaftsgesellschaft\s+mbB|gGmbH|GmbH|mbH|AG\s*&\s*Co\.\s*KG|KGaA|AG|KG|OHG|GbR|e\.\s?V\.|"
    r"eG|SE|e\.\s?K\.|Rechtsanwälte|Rechtsanwaltsgesellschaft\s+mbH)(?=[\s,¶]|$)")
_BEHOERDE = re.compile(r"^(?:Stadt|Gemeinde|Landkreis|Kreis|Land|Bundesrepublik|Freistaat|Markt)\b")
_VERTRETER = re.compile(
    r"(?P<f>Geschäftsführer(?:in)?|Vorstandsvorsitzende[r]?|Vorstand|Inhaber(?:in)?|Liquidator(?:in)?|"
    r"Insolvenzverwalter(?:in)?|(?:Ober)?[Bb]ürgermeister(?:in)?|Landrat|Landrätin)\s+"
    r"(?:(?P<anrede>Frau|Herrn?)\s+)?(?P<n>(?:(?:Dr|Prof)\.\s?(?:[a-z]+\.\s?)*)*[A-ZÄÖÜ][\wäöüß\-]+"
    r"(?:\s+(?:von\s+|van\s+|de\s+)?[A-ZÄÖÜ][\wäöüß\-]+)+)")
_ANSCHRIFT = re.compile(r"(?P<strasse>[A-ZÄÖÜ][^,¶]*?\s\d+\s?[a-zA-Z]?(?:\s?-\s?\d+)?)\s*,?\s*(?P<plz>\d{5})\s+"
                        r"(?P<ort>[A-ZÄÖÜ][^,¶–]*?)(?=\s*(?:,|¶|$|" + _STRICH + r"|gesetzlich|vertreten))")
_TITEL = re.compile(r"^((?:(?:Dr|Prof|Dipl)\.(?:[\s-]?[A-Za-z]+\.)*\s*)+)")
DOKUMENTARTEN = ("Klage", "Klageschrift", "Anspruchsbegründung", "Klageerwiderung", "Replik", "Duplik", "Mahnbescheid",
                 "Vollstreckungsbescheid", "Verfügung", "Beschluss", "Urteil", "Versäumnisurteil", "Berufung",
                 "Berufungsbegründung", "Antrag auf Erlass einer einstweiligen Verfügung", "Ladung", "Schriftsatz")


def _fund(a: dict) -> dict:
    return {"abschnitt": a["nr"], "seite": a.get("seite")}


def _sauber(text: str) -> str:
    return " ".join(text.replace("¶", " ").split()).strip(" ,;")


def _gericht(text: str) -> dict | None:
    m = _GERICHT.match(text)
    if not m:
        return None
    woerter: list[str] = []
    rest = m.group("rest").split()
    for i, w in enumerate(rest):
        if re.match(_STRICH, w) or w[0].isdigit() or (i + 1 < len(rest) and re.match(r"^\d", rest[i + 1])
                                                       and w[0].isupper() and woerter):
            break
        woerter.append(w.strip(","))
        if w.endswith(","):
            break
    name = " ".join([m.group("art"), *woerter]).strip()
    sk = _SPRUCHKOERPER.search(m.group("rest"))
    return {"name": name, "spruchkoerper": " ".join(sk.group(1).split()) if sk else ""}


def _person(name: str) -> dict:
    name = _sauber(name)
    anrede = ""
    if m := re.match(r"^(Frau|Herrn?)\s+", name):
        anrede = "Herr" if m.group(1).startswith("Herr") else "Frau"
        name = name[m.end():]
    titel = ""
    if m := _TITEL.match(name):
        titel = " ".join(m.group(1).split())
        name = name[m.end():].strip()
    teile = name.split()
    if len(teile) >= 3 and teile[-2].casefold() in ("von", "van", "de", "zu"):
        vorname, nachname = " ".join(teile[:-2]), " ".join(teile[-2:])
    else:
        vorname, nachname = " ".join(teile[:-1]), (teile[-1] if teile else "")
    return {"anrede": anrede, "titel": titel, "vorname": vorname, "nachname": nachname}


def _anschrift(text: str) -> dict:
    m = _ANSCHRIFT.search(text)
    if not m:
        return {}
    return {"strasse": _sauber(m.group("strasse")), "plz": m.group("plz"), "ort": _sauber(m.group("ort"))}


def partei(text: str) -> dict:
    """Name, Art, Anschrift und gesetzliche Vertreter aus dem Text einer Partei im Rubrum."""
    text = re.sub(r"^\s*(?:¶\s*)*(?:der|die|des|dem|den)\s+(?=[A-ZÄÖÜ])", "", text.strip(" ¶,"))
    vertretung = re.search(r"\b(?:gesetzlich\s+)?vertreten\s+durch\b", text)
    kopf, vert = (text[: vertretung.start()], text[vertretung.start():]) if vertretung else (text, "")
    kopf = kopf.strip(" ¶,")
    form = None
    for m in _RECHTSFORM.finditer(kopf):
        if form is None or m.start() <= form.end() + 1:
            form = m
        else:
            break
    erstes = kopf.split("¶")[0]
    organisation = bool(form and form.start() < len(erstes) + 1) or bool(_BEHOERDE.match(kopf))
    if organisation:
        ende = form.end() if form else (min((i for i in (kopf.find(","), kopf.find("¶")) if i >= 0), default=len(kopf)))
        name, rest = _sauber(kopf[:ende]), kopf[ende:]
        daten: dict = {"name": name}
    else:
        trenner = [i for i in (kopf.find(","), kopf.find("¶")) if i >= 0]
        ende = min(trenner) if trenner else len(kopf)
        name_text, rest = kopf[:ende], kopf[ende:]
        daten = _person(name_text)
        name = " ".join(t for t in (daten["titel"], daten["vorname"], daten["nachname"]) if t)
    daten |= _anschrift(rest)
    vertreter: list[dict] = []
    hinweise: list[str] = []
    if vert:
        if phg := re.search(r"persönlich haftende(?:n)? Gesellschafter(?:in)?,?\s+(?:die\s+)?"
                            r"(?P<n>[^,¶]+?(?:GmbH|AG|SE|mbH))", vert):
            hinweise.append(f"Persönlich haftende Gesellschafterin: {_sauber(phg.group('n'))}")
        elif organisation:
            for m in _VERTRETER.finditer(vert):
                p = _person(m.group("n"))
                if m.group("anrede"):
                    p["anrede"] = "Herr" if m.group("anrede").startswith("Herr") else "Frau"
                elif m.group("f").endswith("in"):
                    p["anrede"] = "Frau"
                funktion = m.group("f")
                vertreter.append({"funktion": funktion, "daten": p,
                                  "name": " ".join(t for t in (p["titel"], p["vorname"], p["nachname"]) if t)})
    return {"art": "organisation" if organisation else "person", "name": name, "daten": daten,
            "vertreter": vertreter, "hinweise": hinweise}


def _bevollmaechtigte(text: str) -> dict:
    text = text.strip(" ¶,")
    zeichen = _ZEICHEN.search(text) or re.search(r"\bZeichen\s+(?P<z>\S+(?:\s[A-ZÄÖÜ]{1,4}\b)?)", text)
    ende = min((i for i in (text.find(","), text.find("¶")) if i >= 0), default=len(text))
    name = _sauber(text[:ende])
    return {"name": name, "daten": {"name": name, "kategorie": "Kanzlei"} | _anschrift(text[ende:]),
            "zeichen": zeichen.group("z") if zeichen else ""}


def _kurz(p: dict) -> str:
    return p["daten"].get("nachname") or p["name"] if p["art"] == "person" else p["name"]


def erkenne(abschnitte: list[dict]) -> dict:
    """Rubrum aus den Abschnitten eines Dokuments (``[{"nr", "seite", "text"}]``, Dokumentreihenfolge).

    Liefert nur, was gefunden wurde; jedes Feld mit Fundstelle. Fehlt etwas, steht es in ``hinweise``.
    """
    kopf = abschnitte[:80]
    ergebnis: dict = {"dokumentart": None, "gericht": None, "aktenzeichen": None, "zeichen_absender": None,
                      "gegenstand": None, "streitwert": None, "parteien": [], "hinweise": []}
    anfang = next((i for i, a in enumerate(kopf) if _ANFANG.match(a["text"]) or _LABEL_ANFANG.match(a["text"])),
                  None)
    vor_rubrum = kopf[: anfang if anfang is not None else 20]

    for i, a in enumerate(vor_rubrum):
        if ergebnis["gericht"] is None and (g := _gericht(a["text"])):
            if not g["spruchkoerper"] and i + 1 < len(vor_rubrum) and (
                    sk := _SPRUCHKOERPER.match(vor_rubrum[i + 1]["text"].strip("–— "))):
                g["spruchkoerper"] = " ".join(sk.group(1).split())
            ergebnis["gericht"] = g | {"fundstelle": _fund(a)}
        if ergebnis["dokumentart"] is None and a["text"].strip() in DOKUMENTARTEN:
            ergebnis["dokumentart"] = {"wert": a["text"].strip(), "fundstelle": _fund(a)}
    for a in kopf[:30]:
        if ergebnis["aktenzeichen"] is None and (m := _AZ.search(a["text"])):
            ergebnis["aktenzeichen"] = {"wert": " ".join(m.group("az").split()), "fundstelle": _fund(a)}
        if ergebnis["zeichen_absender"] is None and (m := re.search(r"Unser Zeichen:?\s+(?P<z>\d{1,6}/\d{2}"
                                                                     r"(?:\s[A-ZÄÖÜ]{1,4}\b)?)", a["text"])):
            ergebnis["zeichen_absender"] = {"wert": m.group("z"), "fundstelle": _fund(a)}
        if ergebnis["dokumentart"] is None and a["text"].strip() in DOKUMENTARTEN:
            ergebnis["dokumentart"] = {"wert": a["text"].strip(), "fundstelle": _fund(a)}

    if anfang is not None:
        start = anfang + (1 if _ANFANG.match(kopf[anfang]["text"]) else 0)
        bereich = []
        for a in kopf[start:]:
            if _ENDE.match(a["text"]) or re.match(r"^\d+\.\s", a["text"]):
                break
            bereich.append(a)
        ergebnis["parteien"] = _parteien(bereich)
    for a in kopf:
        if ergebnis["gegenstand"] is None and (m := _WEGEN.match(a["text"])):
            ergebnis["gegenstand"] = {"wert": _sauber(m.group("g")), "fundstelle": _fund(a)}
        if ergebnis["streitwert"] is None and (m := _STREITWERT.search(a["text"])):
            ergebnis["streitwert"] = {"wert": m.group("b"), "fundstelle": _fund(a)}
        if (m := _HAUPTFORDERUNG.search(a["text"])):
            if ergebnis["gegenstand"] is None:
                g = re.split(r"\s+vom\s+\d", m.group("g"))[0]
                ergebnis["gegenstand"] = {"wert": _sauber(g), "fundstelle": _fund(a)}
            if ergebnis["streitwert"] is None:
                ergebnis["streitwert"] = {"wert": m.group("b"), "fundstelle": _fund(a), "art": "Hauptforderung"}

    if not ergebnis["parteien"]:
        for a in kopf[:30]:
            if m := _KURZRUBRUM.match(a["text"].strip()):
                for text, seite in ((m.group("a"), "aktiv"), (m.group("p"), "passiv")):
                    p = partei(text)
                    ergebnis["parteien"].append(p | {"seite": seite, "rolle": "", "zusatz": "", "fundstelle": _fund(a),
                                                     "bevollmaechtigte": None})
                ergebnis["hinweise"].append("Nur das Kurzrubrum gefunden; Rollen und Anschriften bitte ergänzen.")
                break

    art = (ergebnis["dokumentart"] or {}).get("wert", "")
    if art in ("Mahnbescheid", "Vollstreckungsbescheid") or (ergebnis["gericht"] or {}).get("spruchkoerper", "") \
            .startswith("Zentrales Mahngericht") or any(p["rolle"].startswith("Antrag") for p in ergebnis["parteien"]) \
            and "Mahn" in " ".join(a["text"] for a in kopf[:10]):
        ergebnis["verfahren_art"] = "mahnverfahren"
    elif art.startswith("Berufung"):
        ergebnis["verfahren_art"] = "berufung"
    elif "einstweilig" in art:
        ergebnis["verfahren_art"] = "eilverfahren"
    else:
        ergebnis["verfahren_art"] = "klage" if ergebnis["gericht"] else "aussergerichtlich"
    if ergebnis["gericht"] and "Mahngericht" in " ".join(a["text"] for a in vor_rubrum[:4]):
        ergebnis["verfahren_art"] = "mahnverfahren"
        ergebnis["gericht"]["spruchkoerper"] = ergebnis["gericht"]["spruchkoerper"] or "Zentrales Mahngericht"

    # Das Zeichen im Briefkopf gehört zu den Bevollmächtigten, von denen das Schreiben stammt.
    if ergebnis["zeichen_absender"] and kopf:
        absender = " ".join(a["text"] for a in kopf[:2]).casefold()
        for p in ergebnis["parteien"]:
            b = p.get("bevollmaechtigte")
            if b and not b["zeichen"] and b["name"].casefold() in absender:
                b["zeichen"] = ergebnis["zeichen_absender"]["wert"]
    aktiv = [p for p in ergebnis["parteien"] if p["seite"] == "aktiv"]
    passiv = [p for p in ergebnis["parteien"] if p["seite"] == "passiv"]
    if aktiv and passiv:
        ergebnis["kurzbezeichnung"] = (f"{_kurz(aktiv[0])}{' u. a.' if len(aktiv) > 1 else ''} ./. "
                                       f"{_kurz(passiv[0])}{' u. a.' if len(passiv) > 1 else ''}")
    else:
        ergebnis["kurzbezeichnung"] = ""
    for feld, text in (("gericht", "Gericht"), ("aktenzeichen", "gerichtliches Aktenzeichen"),
                       ("gegenstand", "Gegenstand (wegen …)"), ("streitwert", "Streitwert")):
        if not ergebnis[feld]:
            ergebnis["hinweise"].append(f"Kein {text} gefunden." if feld != "gegenstand" else
                                        "Kein Gegenstand (wegen …) gefunden.")
    if not aktiv or not passiv:
        ergebnis["hinweise"].append("Parteien nicht vollständig erkannt; bitte prüfen und ergänzen.")
    return ergebnis


def _parteien(bereich: list[dict]) -> list[dict]:
    """Zerlegt den Rubrumsbereich in Parteien (siehe Moduldoku)."""
    strom, marken = "", []  # marken: (Position im Strom, Abschnitt)
    for a in bereich:
        if strom:
            strom += "¶"
        marken.append((len(strom), a))
        strom += a["text"]
    strom += "¶"

    def abschnitt_bei(pos: int) -> dict:
        treffer = marken[0][1]
        for p, a in marken:
            if p <= pos:
                treffer = a
        return treffer

    parteien: list[dict] = []
    puffer, puffer_start = "", 0
    modus: str | None = None
    vor_rolle: str | None = None

    def neue_partei(text: str, rolle: str, zusatz: str, pos: int) -> None:
        if not _sauber(text):
            return
        p = partei(text)
        seite = _ROLLEN.get(rolle.casefold(), "passiv")
        parteien.append(p | {"seite": seite, "rolle": rolle, "zusatz": zusatz, "bevollmaechtigte": None,
                             "fundstelle": _fund(abschnitt_bei(pos))})

    def abschliessen() -> None:
        nonlocal puffer, modus, vor_rolle
        if modus == "bev" and parteien and _sauber(puffer):
            parteien[-1]["bevollmaechtigte"] = _bevollmaechtigte(puffer)
        elif vor_rolle and _sauber(puffer):
            neue_partei(puffer, vor_rolle, "", puffer_start)
        puffer = ""

    pos = 0
    for m in _EREIGNIS.finditer(strom):
        if not puffer.strip(" ¶"):
            puffer_start = pos + (len(strom[pos:m.start()]) - len(strom[pos:m.start()].lstrip(" ¶")))
        puffer += strom[pos:m.start()]
        pos = m.end()
        if m.group("nach"):
            if modus == "bev":
                abschliessen()
            neue_partei(puffer, m.group("rolle"), " ".join((m.group("zu") or "").split()), puffer_start)
            puffer, modus, vor_rolle = "", None, None
        elif m.group("vor"):
            abschliessen()
            vor_rolle, modus = m.group("vrolle"), None
        elif m.group("bev"):
            abschliessen()
            modus, vor_rolle = "bev", None
        elif m.group("gegen"):
            abschliessen()
            modus, vor_rolle = None, None
    puffer += strom[pos:]
    abschliessen()
    return parteien
