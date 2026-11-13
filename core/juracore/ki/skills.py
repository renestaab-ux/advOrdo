"""Skills: Arbeitsanweisungen für das Sprachmodell (Rolle, Vorgehen, Schwerpunkte).

Ein Skill im Format von Claude und ChatGPT ist ein Ordner mit einer Datei ``SKILL.md``: oben ein Kopf in YAML
(``name``, ``description``), darunter die Anweisung in Markdown. advOrdo übernimmt Name, Beschreibung und Text;
weitere Dateien des Ordners (``references/``, ``scripts/``) nicht, sie werden beim Import nur genannt.

Der Skill ergänzt die Systemanweisung, ersetzt sie aber nicht: Die Regeln von advOrdo (nur Tatsachen aus dem
vorgelegten Text, Belege, Antwort als JSON nach dem Schema) stehen vorn und gehen vor. Werkzeuge, Webseiten oder
Dateiausgaben, die ein Skill voraussetzt, gibt es hier nicht; darauf weisen ``hinweise`` hin.

Gespeichert wird in ``skills.json`` im Datenverzeichnis des Geräts (wie ``ki.json``), für alle Arbeitsumgebungen.
Importiert wird nur aus Dateien auf dem Gerät; der Kern lädt dafür nichts aus dem Netz.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

DATEINAME = "skills.json"
SKILL_DATEI = "SKILL.md"
HOECHST_ZEICHEN = 60_000  # länger ist kein Skill, sondern ein Buch; passt in kein lokales Kontextfenster
HOECHST_DATEIEN = 500  # je Import (Ordner oder ZIP)
NAME_LAENGE = 80
BESCHREIBUNG_LAENGE = 400
ZEICHEN_JE_TOKEN = 3  # wie bei der Menge Dokumenttext je Anfrage (analyse.Analyse.budget)

# Was ein Skill voraussetzt, das advOrdo nicht kann. Der Text wird trotzdem übernommen.
_VORAUSSETZUNGEN = [
    (r"https?://|www\.|dejure|juris\.de|beck-online|openjur|websuche|im internet|online (?:prüf|recherch|such)",
     "Der Skill verweist auf Webseiten oder Online-Recherche. advOrdo ruft für die KI keine Webseiten auf; "
     "das Sprachmodell kennt nur die vorgelegten Texte."),
    (r"\b(?:docx|xlsx|pptx)\b|word-datei|pdf (?:erzeug|erstell|export)|datei (?:erzeug|erstell|speicher|export)",
     "Der Skill verlangt Dateien (etwa Word oder PDF). Die KI antwortet in advOrdo nur mit Text; exportieren "
     "lässt sich das Ergebnis über die Analyse."),
    (r"references/|reference/|scripts?/|assets/|\.py\b",
     "Der Skill verweist auf weitere Dateien seines Ordners. Übernommen wird nur der Text aus SKILL.md."),
    (r"\b(?:tools?|werkzeugen?|werkzeuge|bash)\b|befehl ausführ|skript ausführ",
     "Der Skill erwähnt Werkzeuge oder Befehle. Die gibt es für das Sprachmodell in advOrdo nicht."),
]


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --- SKILL.md lesen ---------------------------------------------------------------------------------------------

def _wert(roh: str) -> str:
    roh = roh.strip()
    if len(roh) >= 2 and roh[0] == roh[-1] and roh[0] in "\"'":
        innen = roh[1:-1]
        return innen.replace('\\"', '"').replace("\\\\", "\\") if roh[0] == '"' else innen.replace("''", "'")
    return roh


def _kopf(zeilen: list[str]) -> dict[str, str]:
    """Die einfachen Schlüssel eines YAML-Kopfs (``name: …``), auch mehrzeilig mit ``>`` oder ``|``.

    Ein vollständiger YAML-Leser ist nicht nötig: Ausgewertet werden nur ``name`` und ``description``."""
    werte: dict[str, str] = {}
    i = 0
    while i < len(zeilen):
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", zeilen[i])
        i += 1
        if not m:
            continue
        schluessel, rest = m.group(1).lower(), m.group(2).strip()
        if rest[:1] in (">", "|") or rest == "":
            block = []
            while i < len(zeilen) and (zeilen[i].startswith((" ", "\t")) or not zeilen[i].strip()):
                block.append(zeilen[i].strip())
                i += 1
            trenner = "\n" if rest[:1] == "|" else " "
            werte[schluessel] = trenner.join(z for z in block if z).strip()
        else:
            werte[schluessel] = _wert(rest)
    return werte


def lies_skill_md(text: str, ersatzname: str = "") -> dict:
    """Name, Beschreibung und Anweisung aus dem Inhalt einer ``SKILL.md`` (oder einer schlichten Markdown-Datei).

    Ohne Kopf gilt die erste Überschrift als Name, sonst ``ersatzname``."""
    text = text.replace("\r\n", "\n").lstrip("﻿")
    kopf: dict[str, str] = {}
    koerper = text
    if text.startswith("---\n"):
        ende = text.find("\n---", 4)
        if ende != -1:
            kopf = _kopf(text[4:ende].split("\n"))
            koerper = text[ende + 4:].lstrip("-").lstrip("\n")
    koerper = koerper.strip()
    name = kopf.get("name", "").strip()
    if not name:
        m = re.search(r"^#\s+(.+)$", koerper, re.MULTILINE)
        name = m.group(1).strip() if m else ersatzname
    return {"name": name[:NAME_LAENGE] or "Skill", "beschreibung": kopf.get("description", "")[:BESCHREIBUNG_LAENGE],
            "text": koerper}


def hinweise(text: str) -> list[str]:
    """Was der Skill voraussetzt, das advOrdo nicht bietet (siehe ``_VORAUSSETZUNGEN``)."""
    klein = text.lower()
    return [h for muster, h in _VORAUSSETZUNGEN if re.search(muster, klein)]


# --- Speicher ----------------------------------------------------------------------------------------------------

def lade(datei: Path) -> list[dict]:
    try:
        daten = json.loads(Path(datei).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [s for s in daten.get("skills", []) if isinstance(s, dict) and s.get("id") and s.get("text")]


def _schreibe(datei: Path, skills: list[dict]) -> None:
    datei = Path(datei)
    datei.parent.mkdir(parents=True, exist_ok=True)
    tmp = datei.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "skills": skills}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, datei)


def hoechstlaenge(kontext: int) -> int:
    """Zeichen, die ein Skill bei diesem Kontextfenster höchstens haben darf: ein Viertel des Fensters, damit genug
    Platz für Dokumenttext und Antwort bleibt (bei Apple On-Device mit 8192 Token rund 6.000 Zeichen)."""
    return max(1000, int(kontext) // 4 * ZEICHEN_JE_TOKEN)


def _oeffentlich(s: dict, kontext: int | None) -> dict:
    aus = {k: s.get(k) for k in ("id", "name", "beschreibung", "text", "herkunft", "angelegt_am", "geaendert_am",
                                 "nicht_uebernommen")}
    aus["zeichen"] = len(s["text"])
    aus["hinweise"] = hinweise(s["text"])
    if kontext:
        aus["hoechstens"] = hoechstlaenge(kontext)
        aus["passt"] = len(s["text"]) <= aus["hoechstens"]
    return aus


def liste(datei: Path, kontext: int | None = None) -> list[dict]:
    """Alle Skills, nach Namen; mit ``kontext`` auch, ob sie in das Kontextfenster des aktiven Modells passen."""
    return sorted((_oeffentlich(s, kontext) for s in lade(datei)), key=lambda s: s["name"].lower())


def hole(datei: Path, skill_id: str) -> dict:
    for s in lade(datei):
        if s["id"] == skill_id:
            return s
    raise LookupError("Diesen Skill gibt es nicht mehr. Bitte einen anderen wählen.")


def _pruefe(name: str, text: str) -> tuple[str, str]:
    name = " ".join(str(name).split())[:NAME_LAENGE]
    text = str(text).replace("\r\n", "\n").strip()
    if not name:
        raise ValueError("Der Skill braucht einen Namen.")
    if not text:
        raise ValueError("Der Skill braucht eine Anweisung.")
    if len(text) > HOECHST_ZEICHEN:
        raise ValueError(f"Die Anweisung ist mit {len(text):,} Zeichen zu lang (höchstens {HOECHST_ZEICHEN:,})."
                         .replace(",", "."))
    return name, text


def _freier_name(skills: list[dict], name: str, ausser: str | None = None) -> str:
    vergeben = {s["name"].lower() for s in skills if s["id"] != ausser}
    if name.lower() not in vergeben:
        return name
    n = 2
    while f"{name} ({n})".lower() in vergeben:
        n += 1
    return f"{name} ({n})"


def speichern(datei: Path, name: str, text: str, beschreibung: str = "", skill_id: str | None = None,
              kontext: int | None = None) -> dict:
    """Legt einen eigenen Skill an oder ändert einen vorhandenen (``skill_id``)."""
    name, text = _pruefe(name, text)
    beschreibung = " ".join(str(beschreibung or "").split())[:BESCHREIBUNG_LAENGE]
    skills = lade(datei)
    if any(s["name"].lower() == name.lower() and s["id"] != skill_id for s in skills):
        raise ValueError(f"Es gibt schon einen Skill „{name}“.")
    jetzt = _jetzt()
    if skill_id:
        s = next((s for s in skills if s["id"] == skill_id), None)
        if s is None:
            raise LookupError("Diesen Skill gibt es nicht mehr.")
        s.update(name=name, text=text, beschreibung=beschreibung, geaendert_am=jetzt)
    else:
        s = {"id": uuid.uuid4().hex, "name": name, "beschreibung": beschreibung, "text": text,
             "herkunft": "Eigener Skill", "angelegt_am": jetzt, "geaendert_am": jetzt, "nicht_uebernommen": []}
        skills.append(s)
    _schreibe(datei, skills)
    return _oeffentlich(s, kontext)


def loeschen(datei: Path, skill_id: str) -> dict:
    skills = lade(datei)
    rest = [s for s in skills if s["id"] != skill_id]
    if len(rest) == len(skills):
        raise LookupError("Diesen Skill gibt es nicht mehr.")
    _schreibe(datei, rest)
    return {"geloescht": 1}


def exportieren(datei: Path, skill_id: str, pfad: str) -> dict:
    """Schreibt den Skill als ``SKILL.md`` (mit Kopf), etwa zum Weitergeben oder für Claude und ChatGPT."""
    s = hole(datei, skill_id)
    kennung = re.sub(r"[^a-z0-9]+", "-", s["name"].lower().translate(str.maketrans("äöüß", "aous"))).strip("-")
    kopf = ["---", f"name: {kennung or 'skill'}",
            "description: " + json.dumps(s.get("beschreibung") or s["name"], ensure_ascii=False), "---", ""]
    Path(pfad).write_text("\n".join(kopf) + s["text"] + "\n", encoding="utf-8")
    return {"pfad": str(pfad)}


# --- Import ------------------------------------------------------------------------------------------------------

def _uebrige(dateien: list[str], ordner: str) -> list[str]:
    """Weitere Dateien eines Skill-Ordners (relativ), die nicht übernommen werden."""
    praefix = f"{ordner}/" if ordner else ""
    return sorted(d[len(praefix):] for d in dateien
                  if d.startswith(praefix) and PurePosixPath(d).name != SKILL_DATEI and not d.endswith("/"))[:20]


def _aus_zip(pfad: Path) -> list[tuple[str, str, str, list[str]]]:
    funde = []
    with zipfile.ZipFile(pfad) as z:
        namen = [n for n in z.namelist() if not n.startswith("__MACOSX/")]
        md = [n for n in namen if PurePosixPath(n).name == SKILL_DATEI]
        if not md:
            md = [n for n in namen if n.lower().endswith(".md") and n.count("/") <= 1][:1]
        for n in md[:HOECHST_DATEIEN]:
            info = z.getinfo(n)
            if info.file_size > HOECHST_ZEICHEN * 4:
                funde.append((n, "", "", []))  # zu groß: wird als übersprungen gemeldet
                continue
            text = z.read(n).decode("utf-8", errors="replace")
            ordner = str(PurePosixPath(n).parent) if "/" in n else ""
            ersatz = PurePosixPath(ordner).name if ordner else pfad.stem
            funde.append((n, text, ersatz, _uebrige(namen, ordner)))
    return funde


def _aus_ordner(pfad: Path) -> list[tuple[str, str, str, list[str]]]:
    funde = []
    for md in sorted(pfad.rglob(SKILL_DATEI))[:HOECHST_DATEIEN]:
        rel = md.relative_to(pfad).as_posix()
        if md.stat().st_size > HOECHST_ZEICHEN * 4:
            funde.append((rel, "", "", []))
            continue
        weitere = sorted(p.relative_to(md.parent).as_posix() for p in md.parent.rglob("*")
                         if p.is_file() and p != md)[:20]
        funde.append((rel, md.read_text(encoding="utf-8", errors="replace"), md.parent.name, weitere))
    return funde


def importieren(datei: Path, pfad: str, kontext: int | None = None) -> dict:
    """Übernimmt Skills aus einer Datei ``SKILL.md`` bzw. ``.md``, einem ZIP-Archiv oder einem Ordner (alle darin
    enthaltenen ``SKILL.md``). Gleicher Name und gleicher Text: übersprungen; gleicher Name, anderer Text: neuer
    Skill mit Nummer im Namen. Zurück kommen die übernommenen und die übersprungenen Dateien mit Grund."""
    quelle = Path(pfad)
    if quelle.is_dir():
        funde = _aus_ordner(quelle)
    elif quelle.suffix.lower() == ".zip":
        try:
            funde = _aus_zip(quelle)
        except zipfile.BadZipFile as fehler:
            raise ValueError("Die ZIP-Datei lässt sich nicht öffnen.") from fehler
    elif quelle.suffix.lower() in (".md", ".markdown", ".txt"):
        if quelle.stat().st_size > HOECHST_ZEICHEN * 4:
            raise ValueError("Die Datei ist zu groß für einen Skill.")
        ersatz = quelle.parent.name if quelle.name == SKILL_DATEI else quelle.stem
        funde = [(quelle.name, quelle.read_text(encoding="utf-8", errors="replace"), ersatz, [])]
    else:
        raise ValueError("Bitte eine Datei SKILL.md, eine Markdown-Datei, ein ZIP-Archiv oder einen Ordner wählen.")
    if not funde:
        raise ValueError("Darin wurde keine Datei SKILL.md gefunden.")

    skills = lade(datei)
    uebernommen: list[dict] = []
    uebersprungen: list[dict] = []
    jetzt = _jetzt()
    for ort, inhalt, ersatz, weitere in funde:
        if not inhalt:
            uebersprungen.append({"datei": ort, "grund": "zu groß"})
            continue
        gelesen = lies_skill_md(inhalt, ersatz)
        try:
            name, text = _pruefe(gelesen["name"], gelesen["text"])
        except ValueError as fehler:
            uebersprungen.append({"datei": ort, "grund": str(fehler)})
            continue
        if any(s["name"].lower() == name.lower() and s["text"] == text for s in skills):
            uebersprungen.append({"datei": ort, "grund": "schon vorhanden"})
            continue
        s = {"id": uuid.uuid4().hex, "name": _freier_name(skills, name), "beschreibung": gelesen["beschreibung"],
             "text": text, "herkunft": f"Importiert aus {quelle.name}" + (f" ({ort})" if ort != quelle.name else ""),
             "angelegt_am": jetzt, "geaendert_am": jetzt, "nicht_uebernommen": weitere}
        skills.append(s)
        uebernommen.append(_oeffentlich(s, kontext))
    if uebernommen:
        _schreibe(datei, skills)
    return {"uebernommen": uebernommen, "uebersprungen": uebersprungen}


# --- Anwendung ---------------------------------------------------------------------------------------------------

def fuer_anfrage(datei: Path, skill_id: str | None, kontext: int) -> dict | None:
    """Der gewählte Skill für eine Anfrage; ``None`` ohne Auswahl. Ist er zu lang für das Kontextfenster, sagt das
    ein Fehler, statt ihn still zu kürzen."""
    if not skill_id:
        return None
    s = hole(datei, skill_id)
    grenze = hoechstlaenge(kontext)
    if len(s["text"]) > grenze:
        raise ValueError(
            f"Der Skill „{s['name']}“ ist mit {len(s['text']):,} Zeichen zu lang für das Kontextfenster des "
            f"Sprachmodells ({int(kontext):,} Token, höchstens {grenze:,} Zeichen). Bitte den Skill kürzen "
            f"(„Einstellungen“ → „Skills“) oder ohne Skill arbeiten.".replace(",", "."))
    return {"id": s["id"], "name": s["name"], "text": s["text"]}


def systemanweisung(basis: str, skill: dict | None) -> str:
    """Die Systemanweisung mit dem Skill dahinter; die Regeln von advOrdo stehen vorn und gehen vor."""
    if not skill:
        return basis
    return (
        f"{basis}\n\n"
        f"Zusätzlich gilt die folgende Arbeitsanweisung (Skill „{skill['name']}“). Sie bestimmt Rolle, Vorgehen "
        "und Schwerpunkte. Die Regeln oben gehen ihr vor: Tatsachen nur aus dem vorgelegten Text, jede Aussage "
        "mit Beleg, Antwort nur als JSON nach dem vorgegebenen Schema. Werkzeuge, Webseiten, Dateien oder "
        "Rückfragen, die die Arbeitsanweisung nennt, stehen dir nicht zur Verfügung; arbeite ohne sie. "
        "Entscheidungen oder Normen, die nur in der Arbeitsanweisung stehen, sind nicht geprüft: Nenne sie "
        "höchstens als Einschätzung, nie als Tatsache.\n"
        "<<< Arbeitsanweisung\n"
        f"{skill['text']}\n"
        "Arbeitsanweisung >>>"
    )


def kennung(skill: dict | None) -> str | None:
    """Kurzer Fingerabdruck des Skill-Texts für die gespeicherten Ergebnisse (anderer Text, anderes Ergebnis)."""
    if not skill:
        return None
    return hashlib.sha256((skill["name"] + "\n" + skill["text"]).encode()).hexdigest()[:16]
