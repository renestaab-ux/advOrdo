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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

DATEINAME = "skills.json"
SKILL_DATEI = "SKILL.md"
HOECHST_ZEICHEN = 60_000  # länger ist kein Skill, sondern ein Buch; passt in kein lokales Kontextfenster
HOECHST_DATEIEN = 500  # je Import (Ordner oder ZIP)
NAME_LAENGE = 80
BESCHREIBUNG_LAENGE = 400
ORDNER_LAENGE = 120
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
    aus["ordner"] = s.get("ordner") or ""
    aus["zeichen"] = len(s["text"])
    aus["hinweise"] = hinweise(s["text"])
    if kontext:
        aus["hoechstens"] = hoechstlaenge(kontext)
        aus["passt"] = len(s["text"]) <= aus["hoechstens"]
    return aus


def liste(datei: Path, kontext: int | None = None) -> list[dict]:
    """Alle Skills, nach Ordner und Namen (ohne Ordner zuletzt); mit ``kontext`` auch, ob sie in das Kontextfenster
    des aktiven Modells passen."""
    return sorted((_oeffentlich(s, kontext) for s in lade(datei)),
                  key=lambda s: (not s["ordner"], s["ordner"].lower(), s["name"].lower()))


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
              kontext: int | None = None, ordner: str = "") -> dict:
    """Legt einen eigenen Skill an oder ändert einen vorhandenen (``skill_id``); ``ordner`` z. B.
    „Zivilrecht / BGB AT“."""
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
        s.update(name=name, text=text, beschreibung=beschreibung, ordner=_ordnername(ordner), geaendert_am=jetzt)
    else:
        s = {"id": uuid.uuid4().hex, "name": name, "beschreibung": beschreibung, "text": text,
             "herkunft": "Eigener Skill", "ordner": _ordnername(ordner), "angelegt_am": jetzt,
             "geaendert_am": jetzt, "nicht_uebernommen": []}
        skills.append(s)
    _schreibe(datei, skills)
    return _oeffentlich(s, kontext)


def loeschen(datei: Path, skill_id: str | None = None, skill_ids: list[str] | None = None) -> dict:
    """Löscht einen Skill (``skill_id``) oder mehrere markierte auf einmal (``skill_ids``)."""
    weg = set(skill_ids or []) | ({skill_id} if skill_id else set())
    if not weg:
        raise ValueError("Kein Skill zum Löschen angegeben.")
    skills = lade(datei)
    rest = [s for s in skills if s["id"] not in weg]
    if len(rest) == len(skills):
        raise LookupError("Diesen Skill gibt es nicht mehr.")
    _schreibe(datei, rest)
    return {"geloescht": len(skills) - len(rest)}


def exportieren(datei: Path, skill_id: str, pfad: str) -> dict:
    """Schreibt den Skill als ``SKILL.md`` (mit Kopf), etwa zum Weitergeben oder für Claude und ChatGPT."""
    s = hole(datei, skill_id)
    kennung = re.sub(r"[^a-z0-9]+", "-", s["name"].lower().translate(str.maketrans("äöüß", "aous"))).strip("-")
    kopf = ["---", f"name: {kennung or 'skill'}",
            "description: " + json.dumps(s.get("beschreibung") or s["name"], ensure_ascii=False), "---", ""]
    Path(pfad).write_text("\n".join(kopf) + s["text"] + "\n", encoding="utf-8")
    return {"pfad": str(pfad)}


# --- Import ------------------------------------------------------------------------------------------------------

def _menschlich(kennung: str) -> str:
    """„bgb-at-pruefer“ → „BGB AT Pruefer“: Ersatz für den Ordnernamen, wenn das Paket keinen Titel nennt."""
    woerter = [w for w in re.split(r"[-_\s]+", kennung) if w]
    return " ".join(w.upper() if len(w) <= 3 else w[:1].upper() + w[1:] for w in woerter)[:NAME_LAENGE]


def _paket_titel(lies: Callable[[str], str | None], wurzel: str, ersatz: str) -> str:
    """Titel eines Skill-Pakets: ``displayName`` aus ``.claude-plugin/plugin.json``, sonst die erste Überschrift der
    README, sonst der Ordnername. ``lies`` liefert den Inhalt einer Datei relativ zum Paket oder ``None``."""
    praefix = f"{wurzel}/" if wurzel else ""
    if roh := lies(f"{praefix}.claude-plugin/plugin.json"):
        try:
            daten = json.loads(roh)
            if titel := str(daten.get("displayName") or "").strip():
                return titel[:NAME_LAENGE]
        except ValueError:
            pass
    if roh := lies(f"{praefix}README.md"):
        if m := re.search(r"^#\s+(.+)$", roh, re.MULTILINE):
            return m.group(1).strip()[:NAME_LAENGE]
    return _menschlich(PurePosixPath(wurzel).name if wurzel else ersatz)


def _paketwurzel(rel: str) -> str:
    """Wurzel des Pakets zu einer ``SKILL.md`` (relativ): der Ordner über ``skills/``, sonst der oberste Ordner."""
    teile = PurePosixPath(rel).parts[:-1]
    if "skills" in teile:
        return "/".join(teile[: teile.index("skills")])
    return teile[0] if len(teile) > 1 else ""


def _uebrige(dateien: list[str], ordner: str) -> list[str]:
    """Weitere Dateien eines Skill-Ordners (relativ), die nicht übernommen werden."""
    praefix = f"{ordner}/" if ordner else ""
    return sorted(d[len(praefix):] for d in dateien
                  if d.startswith(praefix) and PurePosixPath(d).name != SKILL_DATEI and not d.endswith("/"))[:20]


Fund = tuple[str, str, str, list[str], str]  # Ort, Inhalt (leer: zu groß), Ersatzname, weitere Dateien, Ordner


def _aus_zip(pfad: Path) -> list[Fund]:
    funde: list[Fund] = []
    with zipfile.ZipFile(pfad) as z:
        namen = [n for n in z.namelist() if not n.startswith("__MACOSX/")]
        vorhanden = set(namen)

        def lies(n: str) -> str | None:
            if n not in vorhanden or z.getinfo(n).file_size > 4_000_000:
                return None
            return z.read(n).decode("utf-8", errors="replace")

        md = [n for n in namen if PurePosixPath(n).name == SKILL_DATEI]
        if not md:
            md = [n for n in namen if n.lower().endswith(".md") and n.count("/") <= 1][:1]
        titel: dict[str, str] = {}
        for n in md[:HOECHST_DATEIEN]:
            wurzel = _paketwurzel(n)
            if wurzel not in titel:
                titel[wurzel] = _paket_titel(lies, wurzel, pfad.stem)
            if z.getinfo(n).file_size > HOECHST_ZEICHEN * 4:
                funde.append((n, "", "", [], ""))  # zu groß: wird als übersprungen gemeldet
                continue
            text = z.read(n).decode("utf-8", errors="replace")
            ordner = str(PurePosixPath(n).parent) if "/" in n else ""
            ersatz = PurePosixPath(ordner).name if ordner else pfad.stem
            funde.append((n, text, ersatz, _uebrige(namen, ordner), titel[wurzel]))
    return funde


def _aus_ordner(pfad: Path) -> list[Fund]:
    def lies(rel: str) -> str | None:
        p = pfad / rel
        if not p.is_file() or p.stat().st_size > 4_000_000:
            return None
        return p.read_text(encoding="utf-8", errors="replace")

    funde: list[Fund] = []
    titel: dict[str, str] = {}
    for md in sorted(pfad.rglob(SKILL_DATEI))[:HOECHST_DATEIEN]:
        rel = md.relative_to(pfad).as_posix()
        wurzel = _paketwurzel(rel) if "/" in rel else ""
        if wurzel not in titel:
            titel[wurzel] = _paket_titel(lies, wurzel, pfad.name)
        if md.stat().st_size > HOECHST_ZEICHEN * 4:
            funde.append((rel, "", "", [], ""))
            continue
        weitere = sorted(p.relative_to(md.parent).as_posix() for p in md.parent.rglob("*")
                         if p.is_file() and p != md)[:20]
        funde.append((rel, md.read_text(encoding="utf-8", errors="replace"), md.parent.name, weitere, titel[wurzel]))
    return funde


def importieren(datei: Path, pfad: str, kontext: int | None = None, ordner: str | None = None) -> dict:
    """Übernimmt Skills aus einer Datei ``SKILL.md`` bzw. ``.md``, einem ZIP-Archiv oder einem Ordner (alle darin
    enthaltenen ``SKILL.md``). Gleicher Name und gleicher Text: übersprungen; gleicher Name, anderer Text: neuer
    Skill mit Nummer im Namen. Zurück kommen die übernommenen und die übersprungenen Dateien mit Grund.

    Jeder Skill kommt in den Ordner seines Pakets (Titel aus ``plugin.json`` oder README, sonst der Paketname);
    ``ordner`` gibt stattdessen einen Ordner für alle vor. Eine einzelne Datei landet ohne Ordner."""
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
        funde = [(quelle.name, quelle.read_text(encoding="utf-8", errors="replace"), ersatz, [], "")]
    else:
        raise ValueError("Bitte eine Datei SKILL.md, eine Markdown-Datei, ein ZIP-Archiv oder einen Ordner wählen.")
    if not funde:
        raise ValueError("Darin wurde keine Datei SKILL.md gefunden.")

    skills = lade(datei)
    uebernommen: list[dict] = []
    uebersprungen: list[dict] = []
    jetzt = _jetzt()
    for ort, inhalt, ersatz, weitere, paket in funde:
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
             "ordner": _ordnername(ordner if ordner is not None else paket),
             "angelegt_am": jetzt, "geaendert_am": jetzt, "nicht_uebernommen": weitere}
        skills.append(s)
        uebernommen.append(_oeffentlich(s, kontext))
    if uebernommen:
        _schreibe(datei, skills)
    return {"uebernommen": uebernommen, "uebersprungen": uebersprungen}


# --- Ordner ------------------------------------------------------------------------------------------------------

def _ordnername(ordner: str | None) -> str:
    """Ordnerpfad bereinigt: Teile mit „/“ getrennt, z. B. „Zivilrecht / BGB AT“; leer heißt ohne Ordner."""
    teile = [" ".join(t.split()) for t in str(ordner or "").split("/")]
    return " / ".join(t for t in teile if t)[:ORDNER_LAENGE]


def im_ordner(skill: dict, ordner: str) -> bool:
    """Liegt der Skill in diesem Ordner oder einem Unterordner davon?"""
    o = skill.get("ordner") or ""
    return o == ordner or o.startswith(ordner + " / ")


def ordner_umbenennen(datei: Path, alt: str, neu: str) -> dict:
    """Benennt einen Ordner um (samt Unterordnern); ``neu`` leer nimmt die Skills aus dem Ordner."""
    alt, neu = _ordnername(alt), _ordnername(neu)
    if not alt:
        raise ValueError("Skills ohne Ordner lassen sich nur einzeln einem Ordner zuweisen.")
    skills = lade(datei)
    n = 0
    for s in skills:
        if im_ordner(s, alt):
            s["ordner"] = _ordnername(neu + (s.get("ordner") or "")[len(alt):])
            n += 1
    if n:
        _schreibe(datei, skills)
    return {"geaendert": n}


def ordner_loeschen(datei: Path, ordner: str) -> dict:
    """Löscht alle Skills dieses Ordners (samt Unterordnern); ``ordner`` leer: alle Skills ohne Ordner."""
    ordner = _ordnername(ordner)
    skills = lade(datei)
    rest = [s for s in skills if not (im_ordner(s, ordner) if ordner else not s.get("ordner"))]
    if len(rest) != len(skills):
        _schreibe(datei, rest)
    return {"geloescht": len(skills) - len(rest)}


# --- Anwendung ---------------------------------------------------------------------------------------------------

ALLE = "alle"
ORDNER_PRAEFIX = "ordner:"
HOECHST_JE_ANFRAGE = 5  # mehr Skills gleichzeitig verwirren ein kleines Modell eher, als dass sie helfen
MINDEST_PUNKTE = 3  # bei „Alle“ oder einem Ordner: so viel Übereinstimmung muss ein Skill mit der Frage haben

_FUELLWOERTER = set(
    "aber alle also auch beim bitte dann dass denn diese dieser dieses doch eine einem einen einer eines etwas "
    "gibt habe haben hast hatte nach nicht noch oder seit sich sind uber unter warum was welche welcher "
    "welches wenn wer wie wird wurde wurden zum zur zwischen steht stehen akte dokument dokumente "
    "prufen pruft prufung prufer skill skills frage fragen ergebnis recht rechts paragraph paragraphen "
    "paragraf paragrafen artikel absatz workflow routing router schnittstelle schnittstellen grundschema "
    "allgemein allgemeiner spezial modul output memo bgb zivilrecht ordnet norm normen beweislast "
    "gegenargument nachster schritt risiko prufprodukt fachgebiet route durch sein seine seiner wegen kann "
    "konnen muss mussen soll sollen darf gegen ohne bitte welchen".split()
)


def _woerter(text: str) -> set[str]:
    """Wörter ab vier Buchstaben, klein, Umlaute ohne Punkte (ä → a), ohne Füllwörter."""
    klein = text.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    klein = klein.replace("ae", "a").replace("oe", "o").replace("ue", "u")
    return {w for w in re.findall(r"[a-z]{4,}", klein) if w not in _FUELLWOERTER}


def _nummern(text: str) -> set[str]:
    """Paragraphen- und Artikelnummern („§ 130“, „paragraph-130“, „Art. 6“)."""
    klein = text.lower()
    return set(re.findall(r"(?:§+|paragraph|paragraf|paragraphen|art\.?|artikel)[\s-]*(\d+[a-z]?)\b", klein))


def _passt(wort: str, q: str) -> bool:
    """Gehören ein Wort des Skills und ein Wort der Frage zusammen? Kurze Wörter (bis sechs Buchstaben): gleiche
    ersten vier („Käufer“ – „Kaufrecht“, „Tier“ – „Tierhalter“); sonst gleiche ersten sechs („anfechtbar“ –
    „Anfechtung“, nicht „Vertrag“ – „Vertreter“). Ein langes Wort der Frage darf den Stamm auch in der Mitte
    enthalten („zurücktreten“ – „Rücktritt“), ein langes Wort des Skills das Wort der Frage („Halter“ –
    „Tierhalter“, „anfechtbar“ – „Irrtumsanfechtung“)."""
    if min(len(q), len(wort)) <= 6:
        if q[:4] == wort[:4]:
            return True
    elif q[:6] == wort[:6]:
        return True
    if len(q) >= 9 and len(wort) >= 6 and wort[:6] in q:
        return True
    return len(wort) >= 9 and len(q) >= 5 and q[:6] in wort


def _treffer(woerter: set[str], frage: set[str]) -> set[str]:
    """Die Wörter der Frage, zu denen eines der Wörter passt."""
    return {q for q in frage if any(_passt(w, q) for w in woerter)}


def _punkte(skill: dict, frage: set[str], nummern: set[str]) -> float:
    """Übereinstimmung von Skill und Frage: je Wort der Frage, das im Namen vorkommt, drei Punkte, in einer
    Überschrift zwei, in der Beschreibung einer; eine gleiche Paragraphennummer im Namen
    vier, in der Beschreibung zwei. So gewinnt der Skill, der die meisten Begriffe der Frage abdeckt; bei Gleichstand
    der, dessen Name enger zur Frage passt (Anteil der passenden Wörter im Namen, als Nachkommastelle)."""
    name = _woerter(skill["name"].replace("-", " "))
    ueberschriften = _woerter(" ".join(re.findall(r"^#{1,3}\s+(.+)$", skill["text"], re.MULTILINE)))
    beschreibung = _woerter(skill.get("beschreibung") or "")
    im_namen = _treffer(name, frage)
    in_ueberschriften = _treffer(ueberschriften, frage) - im_namen
    in_beschreibung = _treffer(beschreibung, frage) - im_namen - in_ueberschriften
    nummern_name = set(re.findall(r"(?<![\d.])(\d{2,4}[a-z]?)(?![\d.])", skill["name"]))
    nummern_sonst = _nummern(skill.get("beschreibung") or "") - nummern_name
    anteil = sum(1 for w in name if any(_passt(w, q) for q in frage)) / len(name) if name else 0.0
    return (3 * len(im_namen) + 2 * len(in_ueberschriften) + len(in_beschreibung)
            + 4 * len(nummern & nummern_name) + 2 * len(nummern & nummern_sonst) + 0.9 * anteil)


def _kandidaten(skills: list[dict], auswahl: list[str]) -> tuple[list[dict], set[str]]:
    """Alle Skills der Auswahl und die Kennungen der einzeln gewählten."""
    einzeln = {a for a in auswahl if a != ALLE and not a.startswith(ORDNER_PRAEFIX)}
    ordner = [a[len(ORDNER_PRAEFIX):] for a in auswahl if a.startswith(ORDNER_PRAEFIX)]
    if ALLE in auswahl:
        return skills, einzeln
    return [s for s in skills if s["id"] in einzeln or any(im_ordner(s, o) for o in ordner)], einzeln


def fuer_anfrage(datei: Path, auswahl: list[str] | str | None, kontext: int, frage: str = "") -> dict:
    """Die Skills für eine Anfrage aus der Auswahl (Kennungen einzelner Skills, „ordner:Name“, „alle“).

    Ein einzeln gewählter Skill gilt immer; ist er zu lang für das Kontextfenster, sagt das ein Fehler, statt ihn
    still zu kürzen. Bei mehreren, einem Ordner oder „Alle“ nimmt die App die zur Frage passendsten (Wortvergleich
    mit Name, Überschriften und Beschreibung, ohne Anfrage an das Modell), höchstens fünf und nur so viele, wie in
    ein Viertel des Kontextfensters passen. Einzeln gewählte haben Vorrang; aus Ordnern und „Alle“ kommt nur, was
    genug übereinstimmt. Zurück: ``skills`` (je id, name, text) und ``hinweis``, wenn keiner passte."""
    if isinstance(auswahl, str):
        auswahl = [auswahl]
    auswahl = [str(a) for a in auswahl or [] if a]
    if not auswahl:
        return {"skills": [], "hinweis": None}
    grenze = hoechstlaenge(kontext)
    alle = lade(datei)
    kandidaten, einzeln = _kandidaten(alle, auswahl)
    if len(auswahl) == 1 and einzeln:
        s = next((s for s in alle if s["id"] in einzeln), None)
        if s is None:
            raise LookupError("Diesen Skill gibt es nicht mehr. Bitte einen anderen wählen.")
        if len(s["text"]) > grenze:
            raise ValueError(
                f"Der Skill „{s['name']}“ ist mit {len(s['text']):,} Zeichen zu lang für das Kontextfenster des "
                f"Sprachmodells ({int(kontext):,} Token, höchstens {grenze:,} Zeichen). Bitte den Skill kürzen "
                f"(„Einstellungen“ → „Skills“) oder ohne Skill arbeiten.".replace(",", "."))
        return {"skills": [{"id": s["id"], "name": s["name"], "text": s["text"]}], "hinweis": None}
    if not kandidaten:
        return {"skills": [], "hinweis": "Die gewählten Skills gibt es nicht mehr."}
    woerter, nummern = _woerter(frage), _nummern(frage)
    bewertet = sorted(((s["id"] in einzeln, _punkte(s, woerter, nummern), s) for s in kandidaten),
                      key=lambda x: (-int(x[0]), -x[1], x[2]["name"].lower()))
    gewaehlt: list[dict] = []
    rest = grenze
    for vorrang, punkte, s in bewertet:
        if len(gewaehlt) >= HOECHST_JE_ANFRAGE:
            break
        if not vorrang and punkte < MINDEST_PUNKTE:
            continue
        laenge = len(s["text"]) + 200  # Kopfzeile je Skill
        if laenge <= rest:
            gewaehlt.append({"id": s["id"], "name": s["name"], "text": s["text"]})
            rest -= laenge
    hinweis = None
    if not gewaehlt:
        hinweis = ("Kein Skill der Auswahl passte gut genug zur Frage; geantwortet wurde ohne Skill."
                   if any(not v for v, _, _ in bewertet) else
                   "Die gewählten Skills sind zu lang für das Kontextfenster des Sprachmodells.")
    return {"skills": gewaehlt, "hinweis": hinweis}


def systemanweisung(basis: str, skills: list[dict] | dict | None) -> str:
    """Die Systemanweisung mit den Skills dahinter; die Regeln von advOrdo stehen vorn und gehen vor."""
    if isinstance(skills, dict):
        skills = [skills]
    if not skills:
        return basis
    namen = ", ".join(f"„{s['name']}“" for s in skills)
    einleitung = ("gilt die folgende Arbeitsanweisung" if len(skills) == 1
                  else "gelten die folgenden Arbeitsanweisungen")
    bloecke = "\n".join(f"<<< Arbeitsanweisung „{s['name']}“\n{s['text']}\nArbeitsanweisung >>>" for s in skills)
    return (
        f"{basis}\n\n"
        f"Zusätzlich {einleitung} (Skill {namen}). {'Sie bestimmt' if len(skills) == 1 else 'Sie bestimmen'} "
        f"Rolle, Vorgehen und Schwerpunkte. Die Regeln oben gehen {'ihr' if len(skills) == 1 else 'ihnen'} vor: "
        "Tatsachen nur aus dem vorgelegten Text, jede Aussage "
        "mit Beleg, Antwort nur als JSON nach dem vorgegebenen Schema. Werkzeuge, Webseiten, Dateien oder "
        "Rückfragen, die die Arbeitsanweisung nennt, stehen dir nicht zur Verfügung; arbeite ohne sie. "
        "Entscheidungen oder Normen, die nur in der Arbeitsanweisung stehen, sind nicht geprüft: Nenne sie "
        "höchstens als Einschätzung, nie als Tatsache.\n"
        f"{bloecke}"
    )


def kennung(skills: list[dict] | dict | None) -> str | None:
    """Kurzer Fingerabdruck der Skill-Texte für die gespeicherten Ergebnisse (anderer Text, anderes Ergebnis)."""
    if isinstance(skills, dict):
        skills = [skills]
    if not skills:
        return None
    roh = "\n\n".join(s["name"] + "\n" + s["text"] for s in skills)
    return hashlib.sha256(roh.encode()).hexdigest()[:16]
