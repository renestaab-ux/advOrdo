"""Gesetze, Dokumente einer Akte und Urteile als Markdown-Datei, z. B. für Wissenssammlungen oder Sprachmodelle.

Der Wortlaut bleibt unverändert; Markdown gliedert nur (Überschriften, Listen, Tabellen) und markiert Fundstellen:
Seiten als ``[S. 3]`` in eigener Zeile, Randnummern als ``[Rn. 12]`` am Absatzanfang. Im Kopf stehen Herkunft und
Stand, damit jede Aussage aus der Datei auf ihre Quelle zurückführbar bleibt.

- Gesetze von gesetze-im-internet.de werden aus der unverändert archivierten XML umgewandelt
  (``juracore.gesetze.markdown``, Nachbau von ``gii2md.py``). Andere Quellen (gesetze-bayern.de, EUR-Lex) und
  Fassungen ohne Roharchiv kommen aus der Wissensbasis, gegliedert wie die gii-Ausgabe.
- Dokumente einer Akte: der in advOrdo gelesene Text (bei Scans aus der Texterkennung) mit Seiten und Randnummern.
- Urteile: Kopf (Gericht, Datum, Aktenzeichen, Normen, Vorinstanz), Teile (Leitsatz, Tenor, Gründe …) als
  Überschriften, Randnummern.
"""

from __future__ import annotations

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .. import grenzen
from ..aktenverwaltung import stammdaten
from ..gesetze import bayern, eurlex, wissensbasis
from ..gesetze import markdown as gii_markdown

# Wie in der App (app/src/kern/rechtsprechung.ts).
URTEIL_TEILE = {
    "leitsatz": "Leitsatz",
    "sonstosatz": "Orientierungssatz",
    "tenor": "Tenor",
    "tatbestand": "Tatbestand",
    "entscheidungsgruende": "Entscheidungsgründe",
    "gruende": "Gründe",
    "abwmeinung": "Abweichende Meinung",
    "sonstlt": "Sonstiger Langtext",
}
URTEIL_QUELLEN = {
    "rii": "Rechtsprechung im Internet (BMJ/BfJ). Anonymisierte Fassung, kein amtlicher Text.",
    "bayern": "Bürgerservice BAYERN.RECHT (gesetze-bayern.de). Redaktionell bearbeitete, anonymisierte Fassung, "
    "kein amtlicher Text; redaktionelle Leitsätze urheberrechtlich geschützt.",
    "neuris": "Rechtsinformationsportal des Bundes, Testphase – ohne Gewähr. Kein amtlicher Text.",
    "manuell": "Eigene Datei",
}
DATUM_HERKUNFT = {
    "dokument": "laut Dokument",
    "manuell": "selbst eingetragen",
    "word": "Speicherdatum laut Word",
    "datei": "Dateidatum",
}
FORMAT_NAME = {"pdf": "PDF", "docx": "Word", "txt": "Text", "md": "Markdown"}
LESART = {
    "textebene": "Textebene der Datei",
    "ocr": "Texterkennung (OCR)",
    "gemischt": "Textebene und Texterkennung",
    "datei": "Text der Datei",
    "leer": "kein Text erkannt",
}


def _datei(name: str) -> str:
    """Zeichen entfernen, die Windows, macOS oder Linux in Dateinamen nicht erlauben."""
    name = re.sub(r"\s*\./\.\s*", " gg. ", name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", name)
    return " ".join(name.split()).strip(" .-")[:120] or "Export"


def _de(datum: str | None) -> str:
    """„2026-10-09“ -> „09.10.2026“; anderes bleibt, wie es ist."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", datum or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else (datum or "")


def speichern(ergebnis: dict, pfad: str | Path) -> dict:
    ziel = Path(pfad)
    if ziel.suffix.lower() != ".md":
        ziel = ziel.with_name(ziel.name + ".md")
    daten = ergebnis["markdown"].encode("utf-8")
    ziel.write_bytes(daten)
    return {"pfad": str(ziel), "groesse": len(daten), "warnung": ergebnis.get("warnung")}


# --- Gesetze -------------------------------------------------------------------------------------------------------


def gesetz(con: sqlite3.Connection, abk: str, fassung_id: int | None = None) -> dict:
    """Ein Gesetz (aktuelle oder gewählte Fassung) als Markdown: {markdown, name, warnung, aus}."""
    fassung = wissensbasis._fassung(con, abk, fassung_id)
    if fassung is None:
        raise LookupError(f"{abk} ist nicht in der Wissensbasis.")
    xml = _gii_xml(fassung["roharchiv"])
    if xml is not None:
        try:
            md, meta = gii_markdown.umwandeln(xml)
        except (ValueError, ET.ParseError):
            pass
        else:
            return {
                "markdown": md,
                "name": gii_markdown.dateiname(meta),
                "warnung": gii_markdown.WARNUNG_LETZTMALIG if meta["letztmalig"] else None,
                "aus": "xml",
            }
    return _gesetz_aus_wissensbasis(con, fassung)


def _gii_xml(roharchiv: str | None) -> bytes | None:
    """Die unverändert archivierte Datei, bei einem ZIP die XML darin; None, wenn es sie nicht (mehr) gibt."""
    if not roharchiv:
        return None
    pfad = Path(roharchiv)
    try:
        daten = pfad.read_bytes()
    except OSError:
        return None
    if daten[:2] != b"PK" and pfad.suffix.lower() != ".xml":
        return None  # gespeicherte Seite (EUR-Lex, gesetze-bayern.de)
    try:
        return gii_markdown.xml_aus(daten)
    except (ValueError, zipfile.BadZipFile, grenzen.ZuGross):
        return None


def _gesetz_aus_wissensbasis(con: sqlite3.Connection, fassung: sqlite3.Row) -> dict:
    abk, titel = fassung["abk"], fassung["langtitel"] or fassung["abk"]
    stand = json.loads(fassung["stand"] or "[]")
    if wissensbasis._ist_amtsblatt(fassung):
        hinweis = eurlex.HINWEIS
    elif wissensbasis._ist_bayern(fassung):
        hinweis = bayern.HINWEIS
    else:
        hinweis = wissensbasis.GII_HINWEIS
    out = [f"# {titel} ({abk})", ""]
    out += [f"- Stand: {' '.join(s.split())}" for s in stand]
    out.append(f"- Quelle: {fassung['quelle']}, abgerufen {fassung['abgerufen_am'][:10]}"
               + (f", Stand der Quelle {fassung['builddate'][:8]}" if fassung["builddate"] else ""))
    out.append(f"- {hinweis}")
    out.append(f"- SHA-256 der Quelldatei: {fassung['sha256']}")
    out.append("- Aus der Wissensbasis von advOrdo in Markdown umgewandelt; Wortlaut unverändert.")
    out.append("")
    normen = con.execute(
        "SELECT * FROM norm WHERE fassung_id = ? ORDER BY reihenfolge", (fassung["id"],)
    ).fetchall()
    gliederungen = [json.loads(n["gliederung"]) for n in normen]
    tiefe = max((len(g) for g in gliederungen), default=0)
    norm_ebene = "#" * min(tiefe + 2, 6)
    bisher: list[str] = []
    for n, gl in zip(normen, gliederungen, strict=True):
        gemeinsam = 0
        while gemeinsam < min(len(gl), len(bisher)) and gl[gemeinsam] == bisher[gemeinsam]:
            gemeinsam += 1
        for i in range(gemeinsam, len(gl)):
            out += [f"{'#' * min(i + 2, 6)} {gl[i]}", ""]
        bisher = gl
        out += [f"{norm_ebene} {n['bezeichnung']} {n['titel'] or ''}".rstrip(), ""]
        for a in con.execute("SELECT nr, text FROM absatz WHERE norm_id = ? ORDER BY reihenfolge", (n["id"],)):
            text = a["text"].strip()
            if text:
                out += [f"({a['nr']}) {text}" if a["nr"] else text, ""]
        if n["fussnoten"]:
            out += ["> Fußnote: " + n["fussnoten"].strip().replace("\n", "\n> "), ""]
    md = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    datum = (fassung["builddate"] or "")[:8]
    datum = f"{datum[:4]}-{datum[4:6]}-{datum[6:]}" if len(datum) == 8 else fassung["abgerufen_am"][:10]
    name = gii_markdown.dateiname({"abk": abk, "titel": titel, "stand_datum": datum})
    return {"markdown": md, "name": name, "warnung": None, "aus": "wissensbasis"}


# --- Dokumente einer Akte ------------------------------------------------------------------------------------------


def _absaetze(abschnitte: list[dict], mit_teilen: bool = False) -> list[str]:
    """Abschnitte mit Seiten- und Randnummern; aufeinanderfolgende Tabellenzeilen werden eine Markdown-Tabelle."""
    out: list[str] = []
    seite = None
    teil = None
    tabelle: list[list[str]] = []

    def tabelle_schliessen() -> None:
        if not tabelle:
            return
        breite = max(len(z) for z in tabelle)
        if breite < 2:
            out.extend(z[0] for z in tabelle)
        else:
            zeilen = [z + [""] * (breite - len(z)) for z in tabelle]
            out.append("| " + " | ".join(zeilen[0]) + " |")
            out.append("|" + " --- |" * breite)
            out.extend("| " + " | ".join(z) + " |" for z in zeilen[1:])
        out.append("")
        tabelle.clear()

    for a in abschnitte:
        if mit_teilen and a.get("teil") and a["teil"] != teil:
            tabelle_schliessen()
            teil = a["teil"]
            out += [f"## {URTEIL_TEILE.get(teil, teil[:1].upper() + teil[1:])}", ""]
        if a.get("seite") is not None and a["seite"] != seite:
            tabelle_schliessen()
            seite = a["seite"]
            out += [f"[S. {seite}]", ""]
        text = a["text"].strip()
        if not text:
            continue
        art = a.get("art", "absatz")
        if art == "tabelle":
            tabelle.append([z.strip().replace("|", "\\|") for z in text.split(" | ")])
            continue
        tabelle_schliessen()
        if a.get("rn") is not None and not text.startswith(f"({a['rn']})"):
            text = f"[Rn. {a['rn']}] {text}"
        if art == "fussnote":
            out += ["> Fußnote: " + text.replace("\n", "\n> "), ""]
        elif art == "kopfzeile":
            out += [f"*Kopf- oder Fußzeile:* {text}", ""]
        else:
            out += [text, ""]
    tabelle_schliessen()
    return out


def dokument(con: sqlite3.Connection, dokument_id: int) -> dict:
    """Ein Dokument einer Akte als Markdown: {markdown, name}."""
    d = con.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if d is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    akte = stammdaten.stammdaten(con, d["akte_id"])
    titel = (d["titel"] or "").strip() or d["dateiname"]
    kopf = [f"- Akte: {akte['name']}" + (f" (Az. {akte['aktenzeichen']})" if akte.get("aktenzeichen") else "")]
    if d["art"]:
        kopf.append(f"- Art: {d['art']}")
    if d["datum"] and d["datum_quelle"] not in (None, "unbekannt"):
        herkunft = DATUM_HERKUNFT.get(d["datum_quelle"])
        kopf.append(f"- Datum: {_de(d['datum'])}" + (f" ({herkunft})" if herkunft else ""))
    seiten = f", {d['seiten']} Seiten" if d["seiten"] is not None else ""
    kopf.append(f"- Datei: {d['dateiname']} ({FORMAT_NAME.get(d['format'], d['format'])}{seiten})")
    if d["herkunft"]:
        kopf.append(f"- Ordner: {d['herkunft']}")
    lesart = LESART.get(d["lesart"], d["lesart"])
    if d["ocr_konfidenz"] is not None:
        lesart += f", Erkennungssicherheit {round(d['ocr_konfidenz'])} %"
    kopf.append(f"- Gelesen aus: {lesart}")
    kopf.append(f"- SHA-256 des Originals: {d['sha256']}")
    kopf += [f"- Hinweis: {h}" for h in json.loads(d["hinweise"] or "[]")]
    kopf.append("- Aus advOrdo in Markdown umgewandelt; Wortlaut wie gelesen, Seiten als [S. …], Randnummern als "
                "[Rn. …] markiert.")
    abschnitte = [dict(a) for a in con.execute(
        "SELECT nr, seite, rn, art, text FROM abschnitt WHERE dokument_id = ? ORDER BY nr", (dokument_id,))]
    out = [f"# {titel}", "", *kopf, "", *_absaetze(abschnitte)]
    md = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    return {"markdown": md, "name": _datei(re.sub(r"\.(pdf|docx|txt|md)$", "", titel, flags=re.I)) + ".md",
            "warnung": None}


# --- Urteile -------------------------------------------------------------------------------------------------------


def urteil(con: sqlite3.Connection, urteil_id: int) -> dict:
    """Ein Urteil (gespeicherter Volltext) als Markdown: {markdown, name}."""
    z = con.execute("SELECT * FROM urteil WHERE id = ?", (urteil_id,)).fetchone()
    if z is None:
        raise LookupError(f"Urteil {urteil_id} gibt es nicht.")
    k = json.loads(z["kopf"]) if z["kopf"] else {}
    doktyp = k.get("doktyp") or "Entscheidung"
    gericht = " ".join(t for t in (z["gericht"], k.get("spruchkoerper")) if t)
    titel = gericht + (f", {doktyp} vom {_de(z['datum'])}" if z["datum"] else "")
    titel += f" – {z['aktenzeichen']}" if z["aktenzeichen"] else ""
    kopf = [f"- Gericht: {gericht}"]
    if z["datum"]:
        kopf.append(f"- Datum: {_de(z['datum'])} ({doktyp})")
    if z["aktenzeichen"]:
        kopf.append(f"- Aktenzeichen: {z['aktenzeichen']}")
    if k.get("ecli"):
        kopf.append(f"- ECLI: {k['ecli']}")
    if k.get("normen"):
        kopf.append(f"- Normen: {k['normen']}")
    kopf += [f"- Vorinstanz: {v}" for v in k.get("vorinstanz") or []]
    quelle = URTEIL_QUELLEN.get(z["quelle"], z["quelle"])
    herkunft = z["herkunft"] or z["dateiname"]
    kopf.append(f"- Quelle: {quelle} ({herkunft})" if herkunft else f"- Quelle: {quelle}")
    if z["doknr"]:
        kopf.append(f"- Dokumentnummer: {z['doknr']}")
    kopf.append(f"- SHA-256 der Quelldatei: {z['sha256']}")
    if z["akte_id"] is not None:
        akte = stammdaten.stammdaten(con, z["akte_id"])
        kopf.append(f"- Akte: {akte['name']}" + (f" (Az. {akte['aktenzeichen']})" if akte.get("aktenzeichen") else ""))
    kopf += [f"- Hinweis: {h}" for h in json.loads(z["hinweise"] or "[]")]
    kopf.append("- Aus advOrdo in Markdown umgewandelt; Wortlaut unverändert, Randnummern als [Rn. …] markiert.")
    abschnitte = [dict(a) for a in con.execute(
        "SELECT nr, seite, rn, text, teil FROM urteil_abschnitt WHERE urteil_id = ? ORDER BY nr", (urteil_id,))]
    out = [f"# {titel or z['dateiname']}", "", *kopf, ""]
    if k.get("titel"):
        out += [f"**{k['titel']}**", ""]
    out += _absaetze(abschnitte, mit_teilen=True)
    md = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    name = " ".join(t for t in (z["gericht"], doktyp if z["datum"] else None, z["datum"],
                                (z["aktenzeichen"] or "").replace("/", "-")) if t)
    return {"markdown": md, "name": _datei(name or z["dateiname"]) + ".md", "warnung": None}


def fuer(con: sqlite3.Connection, wissen: sqlite3.Connection, gesetz_abk: str | None = None,
         fassung_id: int | None = None, dokument_id: int | None = None, urteil_id: int | None = None) -> dict:
    """Wählt die Quelle: genau eines von Gesetz, Dokument oder Urteil."""
    gewaehlt = [x is not None for x in (gesetz_abk, dokument_id, urteil_id)]
    if sum(gewaehlt) != 1:
        raise ValueError("Bitte genau ein Gesetz, ein Dokument oder ein Urteil angeben.")
    if gesetz_abk is not None:
        return gesetz(wissen, gesetz_abk, fassung_id)
    if dokument_id is not None:
        return dokument(con, dokument_id)
    return urteil(con, urteil_id)

