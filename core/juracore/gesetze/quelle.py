"""Abruf von Bundesrecht aus "Gesetze im Internet", Unionsrecht aus EUR-Lex, Landesrecht Bayern aus
gesetze-bayern.de und revisionssicheres Roharchiv.

Jede Quelldatei wird unverändert unter ihrer SHA-256-Prüfsumme abgelegt.
Der Abruf ist bedingt (ETag / Last-Modified), damit unveränderte Gesetze
nicht erneut übertragen werden. Es werden ausschließlich Normtexte geladen,
keine Dokumentinhalte des Nutzers übertragen.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .. import grenzen
from . import bayern, eurlex

BASIS_URL = "https://www.gesetze-im-internet.de"
USER_AGENT = "advOrdo/0.1 (Wissensbasis-Import; advordo@staab.legal)"

# Voreingestellte Gesetze stehen in voreinstellung.json, gegliedert in Pakete (Zivilrecht, Strafrecht,
# Verwaltungsrecht, Landesrecht Bayern), die sich einzeln ein- und ausschalten lassen. Jedes andere
# Bundesgesetz lässt sich über sein Kürzel laden (meist die kleingeschriebene Abkürzung, z. B. "GmbHG" ->
# "gmbhg"). Einträge, deren Kürzel eine CELEX-Nummer ist (DSGVO: 32016R0679), kommen aus EUR-Lex, Einträge
# mit "quelle": "bayern" aus gesetze-bayern.de.
_VOREINSTELLUNG = Path(__file__).with_name("voreinstellung.json")
EIGENES_PAKET = "eigene"


def _liste_lesen(eigene_liste: Path | None) -> tuple[Path, dict]:
    pfad = eigene_liste if eigene_liste is not None and eigene_liste.exists() else _VOREINSTELLUNG
    return pfad, json.loads(pfad.read_text(encoding="utf-8"))


def voreinstellung(eigene_liste: Path | None = None) -> list[dict]:
    """Gesetzesliste aller Pakete; eine eigene Datei (gleiches Format) ersetzt die mitgelieferte.

    Jeder Eintrag trägt unter "pakete" die Pakete, zu denen er gehört."""
    pfad, daten = _liste_lesen(eigene_liste)
    gesetze = daten["gesetze"]
    standard = EIGENES_PAKET if "pakete" not in daten else "zivilrecht"
    for g in gesetze:
        if not _ABK.match(g["abk"]) or not _KUERZEL.match(g["kuerzel"]):
            raise ValueError(f"Ungültiger Eintrag in {pfad.name}: {g}")
        if g.get("quelle") not in (None, bayern.QUELLE):
            raise ValueError(f"Unbekannte Quelle in {pfad.name}: {g}")
        paket = g.get("paket", standard)
        g["pakete"] = [paket] if isinstance(paket, str) else list(paket)
        g.pop("paket", None)
    return gesetze


def pakete(eigene_liste: Path | None = None, schalter: Path | None = None) -> list[dict]:
    """Die Pakete der Gesetzesliste mit Schalterstand.

    ``aktiv`` ist der gesetzte Schalter, ``wirksam`` berücksichtigt das übergeordnete Paket (Landesrecht
    Bayern gilt nur zusammen mit Verwaltungsrecht). Eine eigene Liste ohne Pakete bildet ein Paket „Eigene
    Liste“, das immer an ist."""
    _pfad, daten = _liste_lesen(eigene_liste)
    gesetze = voreinstellung(eigene_liste)
    liste = [dict(p) for p in daten.get("pakete", [])] or [
        {"id": EIGENES_PAKET, "titel": "Eigene Liste", "beschreibung": "Gesetze aus der eigenen gesetze.json.",
         "standard": True}]
    an = _schalter_lesen(schalter, liste)
    for p in liste:
        p["aktiv"] = p["id"] in an
        p["gesetze"] = sum(p["id"] in g["pakete"] for g in gesetze)
    nach_id = {p["id"]: p for p in liste}
    for p in liste:
        ober = nach_id.get(p.get("teil_von") or "")
        p["wirksam"] = p["aktiv"] and (ober is None or ober["aktiv"])
    return liste


def _schalter_lesen(schalter: Path | None, liste: list[dict]) -> set[str]:
    if schalter is not None and schalter.exists():
        try:
            gespeichert = json.loads(schalter.read_text(encoding="utf-8"))
            return set(gespeichert.get("aktiv", [])) | {
                p["id"] for p in liste if p.get("standard") and p["id"] not in gespeichert.get("bekannt", [])}
        except (ValueError, AttributeError):
            pass
    return {p["id"] for p in liste if p.get("standard")}


def paket_schalten(paket: str, aktiv: bool, eigene_liste: Path | None, schalter: Path) -> list[dict]:
    """Schaltet ein Paket ein oder aus. Geladene Gesetze bleiben in der Wissensbasis."""
    liste = pakete(eigene_liste, schalter)
    if paket not in {p["id"] for p in liste}:
        raise ValueError(f"Unbekanntes Gesetzespaket: {paket!r}")
    an = {p["id"] for p in liste if p["aktiv"]}
    an = an | {paket} if aktiv else an - {paket}
    schalter.parent.mkdir(parents=True, exist_ok=True)
    tmp = schalter.with_suffix(".tmp")
    # "bekannt": Pakete, die es beim Speichern schon gab; neue Standardpakete späterer Versionen sind dann an.
    tmp.write_text(json.dumps({"aktiv": sorted(an), "bekannt": sorted(p["id"] for p in liste)}, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(schalter)
    return pakete(eigene_liste, schalter)


def verfuegbar(eigene_liste: Path | None = None, schalter: Path | None = None) -> list[dict]:
    """Gesetze der eingeschalteten Pakete, jedes einmal (Grundlage für „fehlende laden“)."""
    an = {p["id"] for p in pakete(eigene_liste, schalter) if p["wirksam"]}
    gesehen: set[str] = set()
    ergebnis = []
    for g in voreinstellung(eigene_liste):
        if set(g["pakete"]) & an and g["abk"].upper() not in gesehen:
            gesehen.add(g["abk"].upper())
            ergebnis.append(g)
    return ergebnis


def eintrag(abk: str, gesetze: list[dict] | None = None) -> dict | None:
    """Der Eintrag der Gesetzesliste zu einer Abkürzung (ohne Rücksicht auf Groß- und Kleinschreibung)."""
    abk = abk.strip().upper()
    return next((g for g in (gesetze if gesetze is not None else voreinstellung()) if g["abk"].upper() == abk), None)


_KUERZEL = re.compile(r"^[A-Za-z0-9_]{1,40}$")
# Abkürzungen wie "Rom I-VO" enthalten Leerzeichen und Bindestrich, "AVBFernwärmeV" Umlaute; Punkte und Schrägstriche
# nie (die Abkürzung wird zum Ordnernamen im Roharchiv).
_ABK = re.compile(r"^[A-Za-z0-9_ÄÖÜäöüß](?:[A-Za-z0-9_ÄÖÜäöüß -]{0,38}[A-Za-z0-9_ÄÖÜäöüß])?$")
_UMLAUTE = str.maketrans({"ä": "_", "ö": "_", "ü": "_", "ß": "_"})
_UMSCHRIFT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _freies_kuerzel(abk: str) -> str:
    """Pfadkürzel auf gesetze-im-internet.de für eine Abkürzung, die nicht in der Liste steht: klein, ohne
    Bindestriche, Umlaute als „_“ (AVBFernwärmeV → avbfernw_rmev)."""
    return abk.lower().replace("-", "").translate(_UMLAUTE)


@dataclass
class Rohdatei:
    abk: str
    quelle: str
    sha256: str
    xml: bytes
    archivpfad: Path | None


class NichtGeaendert(Exception):
    """Der Server meldet keine Änderung seit dem letzten Abruf (HTTP 304)."""


def lade_gesetz(abk: str, archiv: Path, timeout: float = 60, gesetze: list[dict] | None = None) -> Rohdatei:
    """Lädt die XML-Fassung eines Gesetzes und legt das ZIP im Roharchiv ab."""
    abk, kuerzel = pfadkuerzel(abk, gesetze)
    e = eintrag(abk, gesetze)
    if e is not None and e.get("quelle") == bayern.QUELLE:
        return _lade_bayern(abk, kuerzel, archiv, timeout)
    if eurlex.ist_celex(kuerzel):
        daten, url = eurlex.lade(kuerzel, timeout)
        return archiviere(abk, daten, url, archiv)
    try:
        return _lade_gii(abk, kuerzel, archiv, timeout)
    except NichtGefunden:
        # Viele Gesetze tragen auf gesetze-im-internet.de eine Jahreszahl im Pfad (umwg_1995, vvg_2008). Für ein
        # Kürzel, das nicht in der Liste steht, im Verzeichnis aller Gesetze nach „<kürzel>_<jahr>“ suchen.
        # Umlaute schreibt die Seite meist als „_“, manchmal umschrieben (ae) oder weggelassen.
        varianten = [] if e is not None else list(dict.fromkeys((
            kuerzel, abk.lower().replace("-", "").translate(_UMSCHRIFT),
            abk.lower().replace("-", "").translate({ord(c): None for c in "äöüß"}))))
        gefunden = _pfad_im_verzeichnis(varianten, timeout) if varianten else None
        if gefunden is None:
            raise ValueError(
                f"{abk} wurde auf gesetze-im-internet.de nicht gefunden (Kürzel {kuerzel!r}). "
                "Bitte die Abkürzung aus der Adresse des Gesetzes verwenden."
            ) from None
        return _lade_gii(abk, gefunden, archiv, timeout)


class NichtGefunden(Exception):
    """gesetze-im-internet.de kennt das Pfadkürzel nicht (404)."""


VERZEICHNIS_URL = f"{BASIS_URL}/gii-toc.xml"


def _pfad_im_verzeichnis(varianten: list[str], timeout: float) -> str | None:
    """Pfadkürzel aus dem Verzeichnis gii-toc.xml: eine der Schreibweisen, ggf. mit Jahreszahl („<kürzel>_<jahr>“);
    bei mehreren die ohne Jahreszahl, sonst das jüngste Jahr."""
    anfrage = urllib.request.Request(VERZEICHNIS_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            text = antwort.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return None
    namen = "|".join(re.escape(v) for v in varianten)
    muster = re.compile(r"gesetze-im-internet\.de/((?:" + namen + r")(?:_(\d{4}))?)/xml\.zip", re.IGNORECASE)
    treffer = {m.group(1).lower(): int(m.group(2) or 9999) for m in muster.finditer(text)}
    return max(treffer, key=treffer.__getitem__) if treffer else None


def _lade_gii(abk: str, kuerzel: str, archiv: Path, timeout: float) -> Rohdatei:
    url = f"{BASIS_URL}/{kuerzel}/xml.zip"
    meta_pfad = archiv / abk / "abruf.json"
    meta = json.loads(meta_pfad.read_text(encoding="utf-8")) if meta_pfad.exists() else {}

    anfrage = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if meta.get("etag"):
        anfrage.add_header("If-None-Match", meta["etag"])
    if meta.get("last_modified"):
        anfrage.add_header("If-Modified-Since", meta["last_modified"])
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            daten = antwort.read()
            kopf = antwort.headers
    except urllib.error.HTTPError as fehler:
        if fehler.code == 304:
            raise NichtGeaendert(abk) from None
        if fehler.code == 404:
            raise NichtGefunden(kuerzel) from None
        raise

    roh = archiviere(abk, daten, url, archiv)
    meta_pfad.write_text(
        json.dumps({"etag": kopf.get("ETag"), "last_modified": kopf.get("Last-Modified"), "sha256": roh.sha256}),
        encoding="utf-8",
    )
    return roh


def _lade_bayern(abk: str, kennung: str, archiv: Path, timeout: float) -> Rohdatei:
    """Gesamtansicht einer bayerischen Vorschrift. Die Seite ändert sich bei jedem Abruf ein wenig (Sitzung),
    deshalb zählt als „unverändert“ derselbe Stand (gilt ab, Vollzitat, Zahl der Artikel)."""
    daten, url = bayern.lade(kennung, timeout)
    meta_pfad = archiv / abk / "abruf.json"
    meta = json.loads(meta_pfad.read_text(encoding="utf-8")) if meta_pfad.exists() else {}
    kennzeichen = bayern.kennzeichen(daten)
    if meta.get("kennzeichen") == kennzeichen:
        raise NichtGeaendert(abk)
    roh = archiviere(abk, daten, url, archiv)
    meta_pfad.write_text(json.dumps({"kennzeichen": kennzeichen, "sha256": roh.sha256}, ensure_ascii=False),
                         encoding="utf-8")
    return roh


def pfadkuerzel(abk: str, gesetze: list[dict] | None = None) -> tuple[str, str]:
    """Normalisierte Abkürzung und Pfadkürzel; lehnt alles ab, was kein Kürzel sein kann."""
    abk = abk.strip()
    if not _ABK.match(abk):
        raise ValueError(f"Ungültige Gesetzesabkürzung: {abk!r}")
    bekannt = {g["abk"].upper(): g["kuerzel"] for g in (gesetze if gesetze is not None else voreinstellung())}
    kuerzel = bekannt.get(abk.upper()) or _freies_kuerzel(abk)
    if not _KUERZEL.match(kuerzel):
        raise ValueError(f"Ungültige Gesetzesabkürzung: {abk!r}")
    return abk.upper(), kuerzel


def lies_datei(pfad: Path, archiv: Path | None, abk: str | None = None, gesetze: list[dict] | None = None) -> Rohdatei:
    """Liest eine lokal vorliegende GII-Datei (.xml oder .zip) oder eine aus EUR-Lex bzw. gesetze-bayern.de
    gespeicherte HTML-Seite, z. B. für Offline-Importe."""
    daten = pfad.read_bytes()
    if abk is None and eurlex.ist_eurlex(daten):
        abk = _abk_zu_celex(daten, gesetze)
    elif abk is None and bayern.ist_bayern(daten):
        abk = _abk_zu_bayern(daten, gesetze)
    return archiviere(abk or pfad.stem.upper(), daten, str(pfad), archiv)


def _abk_zu_celex(daten: bytes, gesetze: list[dict] | None) -> str | None:
    """Abkürzung einer gespeicherten EUR-Lex-Seite aus der Voreinstellung, erkannt an der CELEX-Nummer."""
    text = daten.decode("utf-8", "replace")
    for g in gesetze if gesetze is not None else voreinstellung():
        if eurlex.ist_celex(g["kuerzel"]) and re.search(rf"CELEX(?::|%3A)\s*{g['kuerzel']}\b", text):
            return g["abk"].upper()
    return None


def _abk_zu_bayern(daten: bytes, gesetze: list[dict] | None) -> str | None:
    """Abkürzung einer gespeicherten Seite aus gesetze-bayern.de: aus dem Seitentitel („BayBO: …“), die Kennung
    der Voreinstellung („BayPAG“) wird in deren Abkürzung („PAG“) übersetzt."""
    titel = bayern.abk_aus_titel(daten)
    if not titel or not _ABK.match(titel):
        return None
    for g in gesetze if gesetze is not None else voreinstellung():
        if g.get("quelle") == bayern.QUELLE and titel.upper() in (g["kuerzel"].upper(), g["abk"].upper()):
            return g["abk"].upper()
    return titel.upper()


def archiviere(abk: str, daten: bytes, quelle: str, archiv: Path | None) -> Rohdatei:
    sha = hashlib.sha256(daten).hexdigest()
    ist_zip = daten[:2] == b"PK"
    endung = "zip" if ist_zip else "html" if eurlex.ist_eurlex(daten) or bayern.ist_bayern(daten) else "xml"
    archivpfad = None
    if archiv is not None:
        archivpfad = archiv / abk.upper() / f"{sha}.{endung}"
        if not archivpfad.exists():
            archivpfad.parent.mkdir(parents=True, exist_ok=True)
            tmp = archivpfad.with_suffix(".tmp")
            tmp.write_bytes(daten)
            tmp.replace(archivpfad)
            archivpfad.chmod(0o444)
    return Rohdatei(
        abk=abk.upper(), quelle=quelle, sha256=sha, xml=_xml_aus(daten) if ist_zip else daten, archivpfad=archivpfad
    )


def _xml_aus(zipdaten: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zipdaten)) as z:
        xmls = [n for n in z.namelist() if n.lower().endswith(".xml") and "/" not in n.strip("/")]
        if len(xmls) != 1:
            raise ValueError(f"Erwartet genau eine XML-Datei im Archiv, gefunden: {xmls}")
        return grenzen.entpacke(z, xmls[0])
