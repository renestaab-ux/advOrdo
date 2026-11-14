"""Quellen für Skills: öffentliche GitHub-Repositorys mit Skill-Sammlungen (Einstellungen → Skills → Quellen).

Der Nutzer gibt die Adresse eines Repositorys ein, etwa ``https://github.com/besitzer/sammlung``. advOrdo lädt
daraus nur das Verzeichnis und danach genau die Skills, die der Nutzer anklickt; das Repository selbst wird nie
ganz heruntergeladen (große Sammlungen haben mehrere Gigabyte). Keine Quelle ist fest eingebaut.

So wird das Verzeichnis gelesen:

* Hat das Repository einen Plugin-Marktplatz (``.claude-plugin/marketplace.json``), sind dessen Plugins die
  Pakete. Welche Skills ein Paket enthält, fragt advOrdo erst beim Aufklappen ab (ein Aufruf der GitHub-API je
  Paket, Ordner ``<paket>/skills``) und merkt es sich.
* Sonst liest advOrdo den Dateibaum des Repositorys (zwei Aufrufe der API) und sammelt alle ``SKILL.md``, nach
  Paketen geordnet wie beim Import eines Ordners.

Die Dateien selbst kommen von ``raw.githubusercontent.com``. Ohne Anmeldung erlaubt GitHub je Gerät rund 60
API-Aufrufe in der Stunde; das reicht, weil Verzeichnisse zwischengespeichert werden. Gesendet wird dabei nur, welches
Repository und welche Datei gemeint ist, nie etwas aus einer Akte. Jede Anfrage steht im Netzprotokoll.
"""

from __future__ import annotations

import contextvars
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .. import netzprotokoll
from . import skills as ki_skills

DATEINAME = "skill_quellen.json"
USER_AGENT = "advOrdo/0.1 (Skills; advordo@staab.legal)"
ZEITLIMIT = 20
HOECHST_BYTES = 20 * 1024 * 1024  # Verzeichnis einer großen Sammlung; Skills selbst sind viel kleiner
HOECHST_QUELLEN = 20
HOECHST_JE_IMPORT = ki_skills.HOECHST_DATEIEN
GLEICHZEITIG = 6
API = "https://api.github.com"
ROH = "https://raw.githubusercontent.com"

Oeffner = Callable[..., Any]
_TEIL = re.compile(r"^[A-Za-z0-9_.-]+$")


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --- Adresse ---------------------------------------------------------------------------------------------------

def zerlege(adresse: str) -> dict:
    """``https://github.com/besitzer/repo[/tree/zweig/pfad]`` (auch ohne ``https://`` oder nur ``besitzer/repo``)
    → Besitzer, Repository, Zweig (oder ``None`` für den Standardzweig) und Unterordner."""
    roh = (adresse or "").strip().rstrip("/")
    roh = re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", roh, flags=re.IGNORECASE)
    if re.match(r"^[a-z]+://", roh, re.IGNORECASE):
        raise ValueError("Bisher lassen sich nur Repositorys auf GitHub anbinden, etwa "
                         "https://github.com/besitzer/sammlung.")
    teile = [urllib.parse.unquote(t) for t in roh.split("/") if t]
    if len(teile) < 2 or not all(_TEIL.match(t) for t in teile[:2]):
        raise ValueError("Bitte die Adresse eines GitHub-Repositorys angeben, etwa https://github.com/besitzer/sammlung.")
    besitzer, repo = teile[0], re.sub(r"\.git$", "", teile[1])
    zweig, pfad = None, ""
    if len(teile) >= 4 and teile[2] in ("tree", "blob"):
        zweig, pfad = teile[3], "/".join(teile[4:])
    if ".." in pfad.split("/"):
        raise ValueError("Ungültiger Pfad in der Adresse.")
    return {"besitzer": besitzer, "repo": repo, "zweig": zweig, "pfad": pfad}


def _q(pfad: str) -> str:
    return urllib.parse.quote(pfad, safe="/")


def _verbinde(*teile: str) -> str:
    return "/".join(t.strip("/") for t in teile if t and t.strip("/"))


# --- Abruf -----------------------------------------------------------------------------------------------------

def _hole(adresse: str, zweck: str, oeffnen: Oeffner | None, api: bool = False) -> bytes | None:
    """Lädt eine Adresse; ``None`` bei 404. Andere Fehler als verständliche Meldung (``ValueError``)."""
    oeffnen = oeffnen or urllib.request.urlopen  # erst jetzt: Netzprotokoll und Tests stellen es um
    kopf = {"User-Agent": USER_AGENT}
    if api:
        kopf |= {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    anfrage = netzprotokoll.kennzeichnen(urllib.request.Request(adresse, headers=kopf), zweck)
    try:
        with oeffnen(anfrage, timeout=ZEITLIMIT) as antwort:
            daten = antwort.read(HOECHST_BYTES + 1)
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404:
            return None
        if fehler.code in (403, 429) and api:
            rest = fehler.headers.get("X-RateLimit-Remaining") if fehler.headers else None
            if rest == "0" or fehler.code == 429:
                frei = fehler.headers.get("X-RateLimit-Reset") if fehler.headers else None
                ab = ""
                if frei and frei.isdigit():
                    ab = " (wieder ab " + datetime.fromtimestamp(int(frei)).strftime("%H:%M") + " Uhr)"
                raise ValueError("GitHub erlaubt ohne Anmeldung nur rund 60 Verzeichnisabfragen in der Stunde; "
                                 f"dieses Kontingent ist aufgebraucht{ab}. Bereits geladene Verzeichnisse und der "
                                 "Import von Skills funktionieren weiter.") from fehler
        raise ValueError(f"GitHub antwortet mit Fehler {fehler.code}.") from fehler
    except (urllib.error.URLError, TimeoutError, OSError) as fehler:
        grund = getattr(fehler, "reason", fehler)
        raise ValueError(f"GitHub ist nicht erreichbar ({grund}). Besteht eine Internetverbindung?") from fehler
    if len(daten) > HOECHST_BYTES:
        raise ValueError("Die Antwort von GitHub ist zu groß.")
    return daten


def _json(adresse: str, zweck: str, oeffnen: Oeffner | None, api: bool = False) -> Any:
    daten = _hole(adresse, zweck, oeffnen, api)
    if daten is None:
        return None
    try:
        return json.loads(daten)
    except ValueError as fehler:
        raise ValueError(f"Die Antwort von GitHub ist kein gültiges JSON ({adresse}).") from fehler


def _roh(q: dict, pfad: str) -> str:
    return f"{ROH}/{q['besitzer']}/{q['repo']}/{_q(q['zweig'])}/{_q(pfad)}"


def _lies_roh(q: dict, pfad: str, oeffnen: Oeffner | None, zweck: str = "Skill laden") -> str | None:
    daten = _hole(_roh(q, pfad), zweck, oeffnen)
    return None if daten is None else daten.decode("utf-8", errors="replace")


# --- Speicher --------------------------------------------------------------------------------------------------

def lade(datei: Path) -> list[dict]:
    try:
        daten = json.loads(Path(datei).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [q for q in daten.get("quellen", []) if isinstance(q, dict) and q.get("id")]


def _schreibe(datei: Path, quellen: list[dict]) -> None:
    datei = Path(datei)
    datei.parent.mkdir(parents=True, exist_ok=True)
    tmp = datei.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "quellen": quellen}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, datei)


def _hole_quelle(quellen: list[dict], quelle_id: str) -> dict:
    for q in quellen:
        if q["id"] == quelle_id:
            return q
    raise LookupError("Diese Quelle ist nicht mehr angebunden.")


def _kennung(q: dict, pfad: str) -> str:
    """Feste Kennung einer Datei in der Quelle, unter der der übernommene Skill gespeichert wird."""
    return f"github:{q['besitzer']}/{q['repo']}:{pfad}"


def _oeffentlich(q: dict) -> dict:
    aus = {k: q.get(k) for k in ("id", "adresse", "besitzer", "repo", "zweig", "pfad", "titel", "beschreibung",
                                 "art", "geladen_am", "hinweis")}
    aus["pakete"] = [{k: p.get(k) for k in ("pfad", "name", "beschreibung")}
                     | {"anzahl": len(p["skills"]) if p.get("skills") is not None else None}
                     for p in q.get("pakete", [])]
    return aus


def liste(datei: Path) -> list[dict]:
    return [_oeffentlich(q) for q in lade(datei)]


def entfernen(datei: Path, quelle_id: str) -> dict:
    """Löst die Quelle; schon übernommene Skills bleiben."""
    quellen = lade(datei)
    rest = [q for q in quellen if q["id"] != quelle_id]
    if len(rest) == len(quellen):
        raise LookupError("Diese Quelle ist nicht mehr angebunden.")
    _schreibe(datei, rest)
    return {"entfernt": 1}


# --- Verzeichnis -----------------------------------------------------------------------------------------------

def _verzeichnis(q: dict, oeffnen: Oeffner | None) -> None:
    """Liest Titel, Standardzweig und Pakete der Quelle (siehe Moduldoku) in ``q``."""
    basis = f"{API}/repos/{q['besitzer']}/{q['repo']}"
    repo = _json(basis, "Skill-Quelle: Repository prüfen", oeffnen, api=True)
    if repo is None:
        raise ValueError(f"Das Repository {q['besitzer']}/{q['repo']} gibt es auf GitHub nicht, oder es ist nicht "
                         "öffentlich.")
    if repo.get("private"):
        raise ValueError("Nur öffentliche Repositorys lassen sich anbinden.")
    q["zweig"] = q.get("zweig") or str(repo.get("default_branch") or "main")
    q["titel"] = f"{q['besitzer']}/{q['repo']}" + (f" ({q['pfad']})" if q["pfad"] else "")
    q["beschreibung"] = str(repo.get("description") or "")[:ki_skills.BESCHREIBUNG_LAENGE]
    q["hinweis"] = None

    markt = _lies_roh(q, _verbinde(q["pfad"], ".claude-plugin/marketplace.json"), oeffnen,
                      "Skill-Quelle: Verzeichnis laden")
    if markt is not None:
        try:
            daten = json.loads(markt)
        except ValueError:
            daten = None
        if isinstance(daten, dict) and isinstance(daten.get("plugins"), list):
            q["art"] = "marktplatz"
            if daten.get("description"):
                q["beschreibung"] = str(daten["description"])[:ki_skills.BESCHREIBUNG_LAENGE]
            pakete = []
            for p in daten["plugins"]:
                quelle = p.get("source") if isinstance(p, dict) else None
                # Nur Plugins in diesem Repository; Verweise auf andere Repositorys werden nicht verfolgt.
                if not isinstance(quelle, str) or not quelle.startswith("./") or ".." in quelle.split("/"):
                    continue
                pfad = _verbinde(q["pfad"], quelle[2:])
                pakete.append({"pfad": pfad, "name": str(p.get("name") or PurePosixPath(pfad).name),
                               "beschreibung": str(p.get("description") or "")[:ki_skills.BESCHREIBUNG_LAENGE],
                               "skills": None})
            q["pakete"] = sorted(pakete, key=lambda p: p["name"].lower())
            return

    q["art"] = "baum"
    baum = _json(f"{basis}/git/trees/{urllib.parse.quote(q['zweig'], safe='')}?recursive=1",
                 "Skill-Quelle: Dateibaum laden", oeffnen, api=True)
    if baum is None:
        raise ValueError(f"Den Zweig „{q['zweig']}“ gibt es in diesem Repository nicht.")
    praefix = f"{q['pfad']}/" if q["pfad"] else ""
    nach_paket: dict[str, list[dict]] = {}
    for eintrag in baum.get("tree", []):
        pfad = str(eintrag.get("path") or "")
        if eintrag.get("type") != "blob" or PurePosixPath(pfad).name != ki_skills.SKILL_DATEI:
            continue
        if not pfad.startswith(praefix):
            continue
        rel = pfad[len(praefix):]
        wurzel = ki_skills._paketwurzel(rel) if "/" in rel else ""
        ordner = str(PurePosixPath(pfad).parent)
        nach_paket.setdefault(_verbinde(q["pfad"], wurzel), []).append(
            {"pfad": pfad, "name": PurePosixPath(ordner).name if "/" in rel else q["repo"]})
    q["pakete"] = [{"pfad": wurzel, "name": PurePosixPath(wurzel).name if wurzel else q["repo"], "beschreibung": "",
                    "skills": sorted(s, key=lambda x: x["name"].lower())}
                   for wurzel, s in sorted(nach_paket.items(), key=lambda e: e[0].lower())]
    if baum.get("truncated"):
        q["hinweis"] = ("Das Repository ist so groß, dass GitHub nicht alle Dateien auflistet; manche Skills fehlen "
                        "hier. Mit einer Adresse auf einen Unterordner (…/tree/main/ordner) geht es vollständig.")
    if not q["pakete"]:
        raise ValueError("In diesem Repository wurde keine Datei SKILL.md gefunden.")


def anbinden(datei: Path, adresse: str, oeffnen: Oeffner | None = None) -> dict:
    """Bindet ein GitHub-Repository als Quelle an und lädt sein Verzeichnis. Ist es schon angebunden, wird nur das
    Verzeichnis neu geladen."""
    teile = zerlege(adresse)
    quellen = lade(datei)
    for q in quellen:
        if (q["besitzer"].lower(), q["repo"].lower(), q["pfad"]) == (
                teile["besitzer"].lower(), teile["repo"].lower(), teile["pfad"]) and (
                teile["zweig"] in (None, q["zweig"])):
            return aktualisieren(datei, q["id"], oeffnen)
    if len(quellen) >= HOECHST_QUELLEN:
        raise ValueError(f"Es lassen sich höchstens {HOECHST_QUELLEN} Quellen anbinden.")
    q = {"id": uuid.uuid4().hex, **teile}
    with netzprotokoll.anlass("Skill-Quelle anbinden"):
        _verzeichnis(q, oeffnen)
    q["adresse"] = f"https://github.com/{q['besitzer']}/{q['repo']}" + (
        f"/tree/{q['zweig']}/{q['pfad']}" if q["pfad"] else "")
    q["geladen_am"] = _jetzt()
    quellen = lade(datei)  # inzwischen geändert? (Hintergrundauftrag)
    quellen.append(q)
    _schreibe(datei, quellen)
    return _oeffentlich(q)


def aktualisieren(datei: Path, quelle_id: str, oeffnen: Oeffner | None = None) -> dict:
    """Lädt das Verzeichnis der Quelle neu (gemerkte Paketinhalte werden verworfen)."""
    q = dict(_hole_quelle(lade(datei), quelle_id))
    with netzprotokoll.anlass("Skill-Quelle aktualisieren"):
        _verzeichnis(q, oeffnen)
    q["geladen_am"] = _jetzt()
    quellen = [q if x["id"] == quelle_id else x for x in lade(datei)]
    _schreibe(datei, quellen)
    return _oeffentlich(q)


def paket(datei: Path, skills_datei: Path, quelle_id: str, paket_pfad: str,
          oeffnen: Oeffner | None = None) -> dict:
    """Die Skills eines Pakets (Name, Pfad, ob schon übernommen). Beim Marktplatz beim ersten Mal von GitHub."""
    quellen = lade(datei)
    q = _hole_quelle(quellen, quelle_id)
    p = next((p for p in q.get("pakete", []) if p["pfad"] == paket_pfad), None)
    if p is None:
        raise LookupError("Dieses Paket gibt es in der Quelle nicht (mehr). Bitte die Quelle aktualisieren.")
    if p.get("skills") is None:
        with netzprotokoll.anlass("Skill-Quelle: Paket öffnen"):
            p["skills"] = _paket_skills(q, p["pfad"], oeffnen)
        quellen = [q if x["id"] == quelle_id else x for x in lade(datei)]
        _schreibe(datei, quellen)
    schon = ki_skills.aus_quellen(skills_datei)
    return {"quelle_id": quelle_id, "pfad": p["pfad"], "name": p["name"],
            "skills": [s | {"importiert": _kennung(q, s["pfad"]) in schon} for s in p["skills"]]}


def _inhalt(q: dict, pfad: str, oeffnen: Oeffner | None) -> list[dict] | None:
    adresse = (f"{API}/repos/{q['besitzer']}/{q['repo']}/contents/{_q(pfad)}"
               f"?ref={urllib.parse.quote(q['zweig'], safe='')}")
    daten = _json(adresse, "Skill-Quelle: Paket öffnen", oeffnen, api=True)
    return daten if isinstance(daten, list) else None


def _paket_skills(q: dict, pfad: str, oeffnen: Oeffner | None) -> list[dict]:
    """Skills eines Plugins: die Unterordner von ``<paket>/skills``; sonst eine ``SKILL.md`` im Paket selbst."""
    ordner = _inhalt(q, _verbinde(pfad, "skills"), oeffnen)
    if ordner is not None:
        return sorted(({"pfad": _verbinde(pfad, "skills", e["name"], ki_skills.SKILL_DATEI), "name": e["name"]}
                       for e in ordner if e.get("type") == "dir" and e.get("name")), key=lambda s: s["name"].lower())
    eintraege = _inhalt(q, pfad, oeffnen) or []
    if any(e.get("name") == ki_skills.SKILL_DATEI and e.get("type") == "file" for e in eintraege):
        return [{"pfad": _verbinde(pfad, ki_skills.SKILL_DATEI), "name": PurePosixPath(pfad).name or q["repo"]}]
    return []


# --- Import ----------------------------------------------------------------------------------------------------

def importieren(datei: Path, skills_datei: Path, quelle_id: str, pfade: list[str], kontext: int | None = None,
                oeffnen: Oeffner | None = None,
                melde: Callable[[str, int, int], None] | None = None) -> dict:
    """Lädt die gewählten ``SKILL.md`` der Quelle und übernimmt sie, jedes Paket in einen eigenen Ordner (Titel aus
    ``plugin.json`` oder README wie beim Import einer ZIP-Datei). Schon übernommene werden aktualisiert."""
    q = _hole_quelle(lade(datei), quelle_id)
    bekannt = {s["pfad"]: (p["pfad"], s["name"]) for p in q.get("pakete", []) for s in (p.get("skills") or [])}
    pfade = list(dict.fromkeys(pfade or []))
    if not pfade:
        raise ValueError("Keine Skills ausgewählt.")
    if len(pfade) > HOECHST_JE_IMPORT:
        raise ValueError(f"Höchstens {HOECHST_JE_IMPORT} Skills auf einmal, bitte in Teilen importieren.")
    fremd = [p for p in pfade if p not in bekannt]
    if fremd:
        raise LookupError("Diese Skills gibt es in der Quelle nicht (mehr). Bitte die Quelle aktualisieren.")

    def lies(pfad: str) -> str | None:
        return _lies_roh(q, pfad, oeffnen)

    gesamt = len(pfade)
    fertig = [0]

    def laden(pfad: str) -> tuple[str, str | None]:
        text = lies(pfad)
        fertig[0] += 1
        if melde:
            melde(f"Skills laden: {fertig[0]} von {gesamt}", fertig[0], gesamt)
        return pfad, text

    with netzprotokoll.anlass("Skills aus Quelle importieren"):
        titel: dict[str, str] = {}
        for paket_pfad in dict.fromkeys(bekannt[p][0] for p in pfade):
            titel[paket_pfad] = ki_skills._paket_titel(lies, paket_pfad, PurePosixPath(paket_pfad).name or q["repo"])
        # Parallel, aber jede Anfrage mit Anlass und Abbruchprüfung des Auftrags (Kontext je Aufgabe kopiert).
        with ThreadPoolExecutor(max_workers=GLEICHZEITIG) as pool:
            auftraege = [pool.submit(contextvars.copy_context().run, laden, p) for p in pfade]
            texte = dict(a.result() for a in auftraege)

    funde: list[ki_skills.Fund] = []
    fehlt: list[dict] = []
    for pfad in pfade:
        text = texte.get(pfad)
        if text is None:
            fehlt.append({"datei": pfad, "grund": "auf GitHub nicht gefunden"})
            continue
        if len(text) > ki_skills.HOECHST_ZEICHEN * 4:
            text = ""
        paket_pfad, name = bekannt[pfad]
        funde.append((pfad, text, name, [], titel[paket_pfad]))
    ergebnis = ki_skills.uebernehmen(
        skills_datei, funde, lambda ort: f"Aus github.com/{q['besitzer']}/{q['repo']} ({ort})", kontext,
        quelle=lambda ort: _kennung(q, ort))
    ergebnis["uebersprungen"] = fehlt + ergebnis["uebersprungen"]
    return ergebnis
