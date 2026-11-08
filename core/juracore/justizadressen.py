"""Zuständige Gerichte mit Anschrift aus dem Orts- und Gerichtsverzeichnis der Justiz.

Das Justizportal des Bundes und der Länder (justiz.de) führt sein Orts- und Gerichtsverzeichnis unter
justizadressen.nrw.de. Für eine Postleitzahl mit Ort nennt es die Gerichte des allgemeinen Gerichtsstands
(Amtsgericht, Landgericht, Oberlandesgericht) und die Staatsanwaltschaften, jeweils mit Liefer- und Postanschrift,
Telefon, Fax und XJustiz-ID. Dieselbe Abfrage gibt es für die Fachgerichtsbarkeiten (Arbeits-, Verwaltungs- und
Sozialgerichte, jeweils mit den Rechtsmittelgerichten) und für das zentrale Mahngericht; welche davon die App anbietet,
lässt sich in den Einstellungen ein- und ausschalten. Die XJustiz-ID ist derselbe Schlüssel wie in der Codeliste
GDS.Gerichte (``gerichte.py``).

Abgefragt wird nur auf Wunsch und nur einzeln; gesendet werden Postleitzahl und Ort, sonst nichts aus der Akte. Die
Antwort wird unverändert unter ihrer SHA-256-Prüfsumme archiviert, damit sich jede übernommene Anschrift belegen
lässt.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from . import gerichte, netzprotokoll

BASIS = "https://www.justizadressen.nrw.de/de/justiz/gericht"
USER_AGENT = "advOrdo/0.1 (Gerichtsanschriften; advordo@staab.legal)"

# Gerichtsbarkeiten der Zuständigkeitssuche: Schlüssel ``ang`` des Verzeichnisses → Bezeichnung in der App.
GERICHTSBARKEITEN = {
    "zivil": "Ordentliche Gerichte",
    "arbeit": "Arbeitsgerichte",
    "verwaltung": "Verwaltungsgerichte",
    "sozial": "Sozialgerichte",
    "mahn": "Mahngericht",
}
EINSTELLUNGEN = "gerichtssuche.json"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gericht_anschrift (
    name            TEXT PRIMARY KEY,   -- Abteilungen (Register, Insolvenz) teilen sich die XJustiz-ID
    xjustiz_id      TEXT NOT NULL,
    daten           TEXT NOT NULL,      -- JSON: Anschriften und Kontakt wie von ``lies`` geliefert
    quelle          TEXT NOT NULL,      -- Adresse der Abfrage
    sha256          TEXT NOT NULL,
    abgerufen_am    TEXT NOT NULL
);
"""


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


def adresse(plz: str, ort: str, ang: str = "zivil") -> str:
    """Abfrage für Postleitzahl und Ort; ``ang=zivil`` ist der allgemeine Gerichtsstand, sonst die Gerichtsbarkeit."""
    return f"{BASIS}?{urllib.parse.urlencode({'plz': plz.strip(), 'ort': ort.strip(), 'ang': ang})}"


# --- Einstellungen ---------------------------------------------------------------------------------


def einstellungen(datei: Path) -> dict:
    """Welche Gerichtsbarkeiten die Suche anbietet; ohne gespeicherte Wahl alle."""
    try:
        roh = json.loads(Path(datei).read_text(encoding="utf-8"))
        aktiv = [a for a in roh.get("aktiv", []) if a in GERICHTSBARKEITEN]
    except (OSError, ValueError, AttributeError, TypeError):
        aktiv = list(GERICHTSBARKEITEN)
    return {"aktiv": [a for a in GERICHTSBARKEITEN if a in aktiv],
            "gerichtsbarkeiten": [{"id": k, "name": v} for k, v in GERICHTSBARKEITEN.items()]}


def einstellungen_setzen(datei: Path, aktiv: list[str]) -> dict:
    unbekannt = [a for a in aktiv if a not in GERICHTSBARKEITEN]
    if unbekannt:
        raise ValueError(f"Unbekannte Gerichtsbarkeit: {', '.join(unbekannt)}")
    datei = Path(datei)
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps({"aktiv": [a for a in GERICHTSBARKEITEN if a in aktiv]}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return einstellungen(datei)


# --- Lesen -----------------------------------------------------------------------------------------


def _text(teil: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", teil)).strip()


def _zeilen(block: str) -> list[str]:
    return [z for z in (_text(t) for t in re.split(r"<br\s*/?>", block, flags=re.I)) if z]


def _anschrift(zeilen: list[str]) -> dict:
    """„Straße 1“ / „Postfach 10 13 49“ und „12345 Ort“ in Felder; die Zeilen bleiben zum Nachlesen erhalten."""
    a: dict = {"zeilen": zeilen, "strasse": "", "postfach": "", "plz": "", "ort": ""}
    for z in zeilen:
        if m := re.fullmatch(r"(\d{5})\s+(.+)", z):
            a["plz"], a["ort"] = m.group(1), m.group(2)
        elif z.lower().startswith("postfach"):
            a["postfach"] = z
        elif not a["strasse"]:
            a["strasse"] = z
    return a


def _feld(block: str, name: str) -> str:
    m = re.search(rf"<span>\s*{name}:\s*</span>\s*([^<]*)", block)
    return html.unescape(m.group(1)).strip() if m else ""


def lies(text: str) -> dict:
    """Liest die Ergebnisseite: Suchbegriff und je Behörde Name, Anschriften, Kontakt und XJustiz-ID."""
    gesucht = re.search(r"Gesucht wurde:\s*<strong>(.*?)</strong>", text, re.S)
    stellen: list[dict] = []
    # Jede Behörde beginnt mit einer Überschrift <h6>; ihr Block reicht bis zur nächsten.
    teile = re.split(r"<h6>", text)[1:]
    for teil in teile:
        kopf, _, rumpf = teil.partition("</h6>")
        name_html, *hinweis_html = re.split(r"<br\s*/?>", kopf, maxsplit=1)
        name = re.sub(r"\s+", " ", _text(name_html))
        rumpf = rumpf.split("<hr")[0]
        anschriften: dict[str, dict] = {}
        for m in re.finditer(r"<address>\s*<strong>(Lieferanschrift|Postanschrift)</strong>(.*?)</address>", rumpf,
                             re.S):
            anschriften[m.group(1)] = _anschrift(_zeilen(m.group(2)))
        internet = re.search(r"<span>\s*Internet:\s*</span>\s*<a href=\"([^\"]+)\"", rumpf)
        email = re.search(r"href=\"mailto:([^\"]+)\"", rumpf)
        stellen.append({
            "name": name,
            "hinweis": _text(hinweis_html[0]) if hinweis_html else "",
            "art": gerichte.art(name),
            "xjustiz_id": _feld(rumpf, "XJustiz-ID"),
            "lieferanschrift": anschriften.get("Lieferanschrift"),
            "postanschrift": anschriften.get("Postanschrift"),
            "telefon": _feld(rumpf, "Telefon"),
            "fax": _feld(rumpf, "Fax"),
            "internet": internet.group(1).strip() if internet else "",
            "email": email.group(1).strip() if email else "",
        })
    return {"gesucht": re.sub(r"\s+", " ", _text(gesucht.group(1))) if gesucht else "", "stellen": stellen}


def beteiligten_daten(stelle: dict, quelle: str = "", abgerufen_am: str = "") -> dict:
    """Felder für das Gericht im Beteiligtenverzeichnis: Postanschrift (für Schriftsätze), sonst Lieferanschrift.

    Was das Verzeichnis nicht als eigenes Feld kennt (Fax, XJustiz-ID, Internet), steht mit der Quelle in der Notiz.
    Die E-Mail-Adresse auch: Die Gerichte nennen sie nur für Verwaltungsangelegenheiten, nicht für Rechtssachen.
    """
    post, liefer = stelle.get("postanschrift") or {}, stelle.get("lieferanschrift") or {}
    a = post if (post.get("strasse") or post.get("postfach")) else liefer
    notiz = [f"{k}: {stelle[f]}" for k, f in (("Fax", "fax"), ("XJustiz-ID", "xjustiz_id"), ("Internet", "internet"),
                                                        ("E-Mail (nur Verwaltungsangelegenheiten)", "email"))
             if stelle.get(f)]
    if a is post and liefer.get("strasse") and liefer.get("strasse") != post.get("strasse"):
        ort = f"{liefer.get('plz', '')} {liefer.get('ort', '')}".strip()
        notiz.insert(0, f"Lieferanschrift: {liefer['strasse']}, {ort}")
    if quelle:
        notiz.append(f"Quelle: Orts- und Gerichtsverzeichnis der Justiz, {quelle}"
                     + (f", abgerufen am {abgerufen_am[:10]}" if abgerufen_am else ""))
    return {k: v for k, v in {
        "strasse": a.get("strasse") or a.get("postfach") or "",
        "plz": a.get("plz", ""),
        "ort": a.get("ort", ""),
        "telefon": stelle.get("telefon", ""),
        "notiz": "\n".join(notiz),
    }.items() if v}


# --- Abfragen --------------------------------------------------------------------------------------


def archiviere(daten: bytes, archiv: Path | None) -> tuple[str, str]:
    """Legt die Antwort unverändert unter ihrer Prüfsumme ab; vorhandene Dateien bleiben unberührt."""
    sha = hashlib.sha256(daten).hexdigest()
    pfad = ""
    if archiv is not None:
        ziel = archiv / "GERICHTE" / "anschriften" / f"{sha}.html"
        if not ziel.exists():
            ziel.parent.mkdir(parents=True, exist_ok=True)
            tmp = ziel.with_suffix(".tmp")
            tmp.write_bytes(daten)
            tmp.replace(ziel)
            ziel.chmod(0o444)
        pfad = str(ziel)
    return sha, pfad


def zustaendig(con: sqlite3.Connection, plz: str, ort: str, archiv: Path | None,
               oeffnen: Callable[..., object] = urllib.request.urlopen, timeout: float = 20,
               ang: str = "zivil") -> dict:
    """Fragt die zuständigen Gerichte der Gerichtsbarkeit ``ang`` für Postleitzahl und Ort ab und merkt sich die
    Anschriften. ``zivil`` ist der allgemeine Gerichtsstand (Amts-, Land-, Oberlandesgericht)."""
    if ang not in GERICHTSBARKEITEN:
        raise ValueError(f"Unbekannte Gerichtsbarkeit: {ang}")
    if not re.fullmatch(r"\d{5}", plz.strip()):
        raise ValueError("Bitte eine fünfstellige Postleitzahl angeben.")
    if not ort.strip():
        raise ValueError("Bitte den Ort angeben.")
    url = adresse(plz, ort, ang)
    gesendet = f"PLZ {plz.strip()}, Ort {ort.strip()}"
    if ang != "zivil":
        gesendet += f", {GERICHTSBARKEITEN[ang]}"
    anfrage = netzprotokoll.kennzeichnen(
        urllib.request.Request(url, headers={"User-Agent": USER_AGENT}),
        "Zuständiges Gericht suchen (justizadressen.nrw.de)", gesendet)
    with oeffnen(anfrage, timeout=timeout) as antwort:
        daten = antwort.read()
    sha, archivpfad = archiviere(daten, archiv)
    ergebnis = lies(daten.decode("utf-8", errors="replace"))
    jetzt = datetime.now(UTC).isoformat(timespec="seconds")
    einrichten(con)
    with con:
        for s in ergebnis["stellen"]:
            if s["name"]:
                con.execute(
                    "INSERT OR REPLACE INTO gericht_anschrift (name, xjustiz_id, daten, quelle, sha256, abgerufen_am) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (s["name"], s["xjustiz_id"], json.dumps(s, ensure_ascii=False), url, sha, jetzt))
    for s in ergebnis["stellen"]:
        s["beteiligter"] = beteiligten_daten(s, url, jetzt)
    return {**ergebnis, "gerichtsbarkeit": ang, "quelle": url, "sha256": sha, "archiv": archivpfad,
            "abgerufen_am": jetzt}
