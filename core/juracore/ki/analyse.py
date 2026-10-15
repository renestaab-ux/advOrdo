"""Zusammenfassungen und inhaltliche Widersprüche mit einem lokalen Sprachmodell, jede Aussage mit Fundstelle.

Ablauf („Beleg vor Behauptung“):

1. Das Modell liest ein Dokument als nummerierte Absätze und antwortet mit
   Aussagen, jede mit Absatznummer und wörtlichem Zitat.
2. ``belege.finde`` prüft jedes Zitat am gespeicherten Originaltext. Gezeigt wird
   die Fundstelle aus dem Dokument (Seite, Randnummer, Ausschnitt), nicht die
   Wiedergabe des Modells. Aussagen ohne gefundenes Zitat heißen „ohne Beleg“
   (Zusammenfassung) bzw. werden verworfen (Angaben für den Widerspruchsabgleich).
3. Verdichtungen (Akte, lange Dokumente) verweisen auf die Kennungen geprüfter
   Aussagen und übernehmen deren Fundstellen; eine Verdichtung ohne gültige
   Kennung ist „ohne Beleg“.
4. Für Widersprüche sammelt das Modell je Dokument die Tatsachenangaben (mit
   Beleg) und vergleicht sie dann über die Akte. Ein Widerspruch zählt nur, wenn
   er auf mindestens zwei geprüfte Angaben verweist. Ob er wirklich besteht,
   entscheidet der Mensch an den Fundstellen; die Erklärung ist eine Einschätzung
   des Modells.

Lange Dokumente werden in Stücke geteilt, die in den Kontext des Modells passen.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from typing import Protocol

from ..abgleich.abgleich import PARTEIEN
from . import belege, chronologie, speicher
from .anbieter import ANTWORT_TOKEN, Anbieter, KiFehler

log = logging.getLogger("juracore.ki")

# Fassung der Anweisungen je Aufgabe; eine Änderung macht gespeicherte Ergebnisse ungültig.
FASSUNG = {"zusammenfassung_dokument": 1, "zusammenfassung_akte": 1, "angaben": 2, "widersprueche": 3,
           "chronologie": 1}

# Zeichen Angaben je Vergleichsanfrage. Mittelgroße Modelle (12–14 B) übersehen in langen Listen viel; kleinere
# Blöcke, je zwei gemeinsam geprüft, kosten mehr Anfragen, finden aber mehr.
VERGLEICH_EINZELN = 9000
VERGLEICH_BLOCK = 4500
# Zeichen Text je Anfrage beim Sammeln der Tatsachenangaben, unabhängig vom Kontext. Die Antwort hat höchstens
# 25 Angaben; ein größerer Kontext soll bei langen Dokumenten nicht zu weniger Angaben führen.
ANGABEN_STUECK = 12000

ARTEN = ["tatsache", "vortrag", "bestreiten", "rechtsansicht", "antrag", "entscheidung", "sonstiges"]
THEMEN = ["gegenstand", "verlauf", "vortrag", "streitig", "entscheidung", "offen"]
HALTUNGEN = ["behauptet", "bestritten", "unstreitig", "festgestellt"]

BELEGT = "belegt"
OHNE_BELEG = "ohne_beleg"

SYSTEM = (
    "Du bist ein sorgfältiger juristischer Assistent in einer deutschen Anwaltskanzlei. Du arbeitest "
    "ausschließlich mit dem vorgelegten Text und erfindest nichts. Rechtsauffassungen gibst du nicht als "
    "Tatsachen aus. Du antwortest nur mit JSON nach dem vorgegebenen Schema, auf Deutsch."
)

BELEGREGEL = (
    "Belege jede Angabe mit der Nummer des Absatzes (die Zahl in eckigen Klammern) und einem wörtlichen Zitat "
    "aus genau diesem Absatz: eine zusammenhängende Wortfolge von 4 bis 25 Wörtern, Zeichen für Zeichen "
    "abgeschrieben, ohne Auslassungen."
)

_BELEG_SCHEMA = {
    "type": "object",
    "properties": {"absatz": {"type": "integer"}, "zitat": {"type": "string"}},
    "required": ["absatz", "zitat"],
}

SCHEMA_ZUSAMMENFASSUNG = {
    "type": "object",
    "properties": {
        "aussagen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "art": {"type": "string", "enum": ARTEN},
                    "belege": {"type": "array", "items": _BELEG_SCHEMA},
                },
                "required": ["text", "art", "belege"],
            },
        }
    },
    "required": ["aussagen"],
}

SCHEMA_ANGABEN = {
    "type": "object",
    "properties": {
        "angaben": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "haltung": {"type": "string", "enum": HALTUNGEN},
                    "absatz": {"type": "integer"},
                    "zitat": {"type": "string"},
                },
                "required": ["text", "haltung", "absatz", "zitat"],
            },
        }
    },
    "required": ["angaben"],
}

SCHEMA_VERDICHTUNG = {
    "type": "object",
    "properties": {
        "aussagen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "art": {"type": "string", "enum": ARTEN + THEMEN},
                    "quellen": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "art", "quellen"],
            },
        }
    },
    "required": ["aussagen"],
}

SCHEMA_WIDERSPRUECHE = {
    "type": "object",
    "properties": {
        "widersprueche": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "thema": {"type": "string"},
                    "art": {"type": "string", "enum": ["widerspruch", "spannung"]},
                    "erklaerung": {"type": "string"},
                    "angaben": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["thema", "art", "erklaerung", "angaben"],
            },
        }
    },
    "required": ["widersprueche"],
}

ARTEN_TEXT = """- tatsache: was im Dokument selbst feststeht (z. B. Vertragsinhalt, Absender, Datum)
- vortrag: Tatsachenbehauptung einer Partei; nenne im Text, wer sie aufstellt
- bestreiten: eine Partei bestreitet eine Behauptung der anderen
- rechtsansicht: rechtliche Würdigung oder Argumentation
- antrag: Klageantrag oder anderer Antrag
- entscheidung: Ausspruch oder Feststellung des Gerichts
- sonstiges"""


class Abgebrochen(Exception):
    """Der Nutzer hat die Analyse abgebrochen."""


class Fortschritt(Protocol):
    def melde(self, text: str, schritt: int | None = None, von: int | None = None) -> None: ...

    def pruefe(self) -> None: ...


class OhneFortschritt:
    def melde(self, text: str, schritt: int | None = None, von: int | None = None) -> None:
        log.info("%s", text)

    def pruefe(self) -> None:
        pass


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _kopf(t: belege.Text) -> str:
    return f"Dokument: {t.dateiname}" + (f" (Beteiligte: {', '.join(t.parteien)})" if t.parteien else "")


@dataclass
class Analyse:
    con: sqlite3.Connection
    anbieter: Anbieter
    kontext: int = 16384
    fortschritt: Fortschritt = field(default_factory=OhneFortschritt)
    neu: bool = False  # das angefragte Ergebnis neu berechnen; Zwischenergebnisse (je Dokument) bleiben gespeichert

    def __post_init__(self) -> None:
        speicher.einrichten(self.con)

    @property
    def budget(self) -> int:
        """Zeichen Dokumenttext je Anfrage: Kontext abzüglich Anweisung und Antwort, rund 3 Zeichen je Token."""
        return max(3000, (self.kontext - ANTWORT_TOKEN - 800) * 3)

    @property
    def modell(self) -> str:
        return self.anbieter.modell

    # --- Grundbausteine ----------------------------------------------------------------------------

    def _frage(self, nutzer: str, schema: dict) -> dict:
        self.fortschritt.pruefe()
        try:
            return self.anbieter.chat(SYSTEM, nutzer, schema)
        except KiFehler as fehler:
            if "JSON" not in str(fehler):
                raise
            log.warning("Unbrauchbare Antwort, frage erneut: %s", fehler)
            self.fortschritt.pruefe()
            return self.anbieter.chat(SYSTEM, nutzer, schema)

    def _gespeichert(
        self, aufgabe: str, eingabe: object, berechne: Callable[[], dict], akte_id: int | None,
        dokument_id: int | None = None, bezug: str = "", ziel: bool = True,
    ) -> dict:
        key = speicher.schluessel(aufgabe, FASSUNG[aufgabe], type(self.anbieter).__name__, self.modell,
                                  self.kontext, eingabe)
        if not (self.neu and ziel) and (alt := speicher.lies(self.con, key)) is not None:
            alt["gespeichert"] = True
            return alt
        ergebnis = berechne()
        ergebnis.update(modell=self.modell, erstellt_am=_jetzt())
        speicher.schreibe(self.con, key, aufgabe, self.modell, ergebnis, akte_id, dokument_id, bezug)
        ergebnis["gespeichert"] = False
        return ergebnis

    def _text(self, dokument_id: int) -> belege.Text:
        return belege.lade_text(self.con, dokument_id, PARTEIEN)

    def _akte(self, dokument_id: int) -> int:
        return self.con.execute("SELECT akte_id FROM dokument WHERE id = ?", (dokument_id,)).fetchone()[0]

    def _dokument_ids(self, akte_id: int, dokument_ids: list[int] | None) -> list[int]:
        if self.con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
            raise LookupError(f"Akte {akte_id} gibt es nicht.")
        alle = [z[0] for z in self.con.execute(
            "SELECT id FROM dokument WHERE akte_id = ? ORDER BY COALESCE(herkunft, ''), dateiname, id", (akte_id,)
        )]
        if not dokument_ids:
            return alle
        gewaehlt = {int(i) for i in dokument_ids}
        if not gewaehlt <= set(alle):
            raise LookupError("Mindestens eines der gewählten Dokumente gehört nicht zu dieser Akte.")
        return [i for i in alle if i in gewaehlt]

    @staticmethod
    def _beleg(t: belege.Text, absatz: object, zitat: object) -> dict | None:
        bevorzugt = absatz if isinstance(absatz, int) else None
        fund = belege.finde(zitat, t.nach_nr, bevorzugt) if isinstance(zitat, str) else None
        return t.fundstelle(fund) if fund else None

    # --- Zusammenfassung eines Dokuments -----------------------------------------------------------

    def zusammenfassung_dokument(self, dokument_id: int, ziel: bool = True) -> dict:
        t = self._text(dokument_id)
        return self._gespeichert(
            "zusammenfassung_dokument", [t.dateiname, t.parteien, belege.zeilen(t.abschnitte)],
            lambda: self._fasse_dokument(t), self._akte(dokument_id), dokument_id, ziel=ziel,
        )

    def _fasse_dokument(self, t: belege.Text) -> dict:
        stuecke = belege.teile_auf(t.abschnitte, self.budget)
        aussagen: list[dict] = []
        for i, stueck in enumerate(stuecke, 1):
            teil = f" (Teil {i} von {len(stuecke)})" if len(stuecke) > 1 else ""
            self.fortschritt.melde(f"Fasse {t.dateiname}{teil} zusammen")
            antwort = self._frage(
                f"{_kopf(t)}{teil}\n\n"
                f"Aufgabe: Fasse {'diesen Teil des Dokuments' if teil else 'das Dokument'} in höchstens "
                f"{8 if teil else 10} Kernaussagen zusammen, die wichtigste zuerst. Die erste Aussage nennt, was "
                "für ein Dokument es ist, wer es verfasst hat und worum es geht. Ordne jede Aussage einer Art zu:\n"
                f"{ARTEN_TEXT}\n\n{BELEGREGEL}\n\n"
                f"Text (jede Zeile ein Absatz, vorn seine Nummer):\n{belege.zeilen(stueck)}",
                SCHEMA_ZUSAMMENFASSUNG,
            )
            for a in antwort.get("aussagen") or []:
                if not isinstance(a, dict) or not str(a.get("text", "")).strip():
                    continue
                fundstellen = [f for b in a.get("belege") or [] if isinstance(b, dict)
                               if (f := self._beleg(t, b.get("absatz"), b.get("zitat")))]
                aussagen.append(_aussage(a.get("text"), a.get("art"), fundstellen))
        if len(stuecke) > 1:
            self.fortschritt.melde(f"Verdichte die Zusammenfassung von {t.dateiname}")
            aussagen = self._verdichte(
                aussagen, f"Die Aussagen stammen aus den Teilen des Dokuments {t.dateiname}. Fasse sie zu "
                "höchstens 10 Kernaussagen über das ganze Dokument zusammen, die wichtigste zuerst; die erste "
                "nennt, was für ein Dokument es ist und worum es geht. Ordne jede Aussage einer Art zu:\n"
                + ARTEN_TEXT, {t.dokument_id: t.dateiname},
            )
        return {"dokument_id": t.dokument_id, "dateiname": t.dateiname, "teile": len(stuecke),
                "aussagen": aussagen, "zaehlung": _zaehle(aussagen)}

    # --- Verdichtung (lange Dokumente, Akte) -------------------------------------------------------

    def _verdichte(self, aussagen: list[dict], aufgabe: str, namen: dict[int, str], tiefe: int = 0) -> list[dict]:
        """Lässt das Modell geprüfte Aussagen zusammenfassen; jede Verdichtung verweist auf deren Kennungen."""
        belegte = [a for a in aussagen if a["status"] == BELEGT]
        if not belegte:
            return aussagen
        zeilen = []
        for i, a in enumerate(belegte, 1):
            dok = sorted({namen.get(f["dokument_id"], str(f["dokument_id"])) for f in a["fundstellen"]})
            parteien = sorted({p for f in a["fundstellen"] for p in f["parteien"]})
            herkunft = "; ".join(filter(None, [", ".join(dok), ", ".join(parteien), a["art"]]))
            zeilen.append(f"[A{i}] ({herkunft}) {a['text']}")
        if sum(len(z) + 1 for z in zeilen) > self.budget and len(belegte) > 1 and tiefe < 4:
            # Zu viel auf einmal: in Gruppen verdichten, dann die Ergebnisse.
            gruppen, aktuell, groesse = [], [], 0
            for a, z in zip(belegte, zeilen, strict=True):
                if aktuell and groesse + len(z) > self.budget:
                    gruppen.append(aktuell)
                    aktuell, groesse = [], 0
                aktuell.append(a)
                groesse += len(z) + 1
            gruppen.append(aktuell)
            zwischen = [v for g in gruppen for v in self._verdichte(g, aufgabe, namen, tiefe + 1)]
            return self._verdichte(zwischen, aufgabe, namen, tiefe + 1)
        antwort = self._frage(
            f"Aufgabe: {aufgabe}\n\nGib bei jeder Aussage in „quellen“ die Kennungen (z. B. A3) der Aussagen an, "
            "auf denen sie beruht. Schreibe nichts, was nicht in diesen Aussagen steht.\n\n"
            "Aussagen (Kennung, Herkunft, Text):\n" + "\n".join(zeilen),
            SCHEMA_VERDICHTUNG,
        )
        ergebnis = []
        for a in antwort.get("aussagen") or []:
            if not isinstance(a, dict) or not str(a.get("text", "")).strip():
                continue
            fundstellen: dict[tuple[int, int], dict] = {}  # je Absatz eine Fundstelle
            for q in a.get("quellen") or []:
                nr = str(q).strip().lstrip("[A").rstrip("]")
                if nr.isdigit() and 1 <= int(nr) <= len(belegte):
                    for f in belegte[int(nr) - 1]["fundstellen"]:
                        fundstellen.setdefault((f["dokument_id"], f["abschnitt"]), f)
            ergebnis.append(_aussage(a.get("text"), a.get("art"), list(fundstellen.values())))
        return ergebnis

    # --- Zusammenfassung der Akte ------------------------------------------------------------------

    def zusammenfassung_akte(self, akte_id: int) -> dict:
        ids = self._dokument_ids(akte_id, None)
        if not ids:
            raise ValueError("Die Akte enthält noch keine Dokumente.")
        einzeln = []
        for i, d in enumerate(ids, 1):
            self.fortschritt.melde(f"Dokument {i} von {len(ids)}", i - 1, len(ids) + 1)
            einzeln.append(self.zusammenfassung_dokument(d, ziel=False))
        self.fortschritt.melde("Fasse die Akte zusammen", len(ids), len(ids) + 1)
        namen = {e["dokument_id"]: e["dateiname"] for e in einzeln}

        def berechne() -> dict:
            alle = [a for e in einzeln for a in e["aussagen"]]
            aussagen = self._verdichte(
                alle,
                "Die Aussagen stammen aus den Zusammenfassungen aller Dokumente einer Akte. Gib einen Überblick "
                "über die Akte in höchstens 12 Aussagen: worum es geht, wie es dazu kam, was jede Seite vorträgt, "
                "was streitig ist und was das Gericht entschieden hat (falls ein Urteil dabei ist). Ordne jede "
                "Aussage einem Thema zu: gegenstand, verlauf, vortrag, streitig, entscheidung, offen. Nenne bei "
                "Vortrag, wer ihn hält.",
                namen,
            )
            return {"akte_id": akte_id, "aussagen": aussagen, "zaehlung": _zaehle(aussagen),
                    "dokumente": [{"dokument_id": e["dokument_id"], "dateiname": e["dateiname"],
                                   "zaehlung": e["zaehlung"]} for e in einzeln]}

        return self._gespeichert("zusammenfassung_akte", [e["aussagen"] for e in einzeln], berechne, akte_id)

    # --- Tatsachenangaben und Widersprüche ---------------------------------------------------------

    def angaben(self, dokument_id: int, ziel: bool = True) -> dict:
        t = self._text(dokument_id)
        return self._gespeichert(
            "angaben", [t.dateiname, t.parteien, belege.zeilen(t.abschnitte)],
            lambda: self._sammle_angaben(t), self._akte(dokument_id), dokument_id, ziel=ziel,
        )

    def _sammle_angaben(self, t: belege.Text) -> dict:
        stuecke = belege.teile_auf(t.abschnitte, min(self.budget, ANGABEN_STUECK))
        angaben: list[dict] = []
        verworfen = 0
        for i, stueck in enumerate(stuecke, 1):
            teil = f" (Teil {i} von {len(stuecke)})" if len(stuecke) > 1 else ""
            antwort = self._frage(
                f"{_kopf(t)}{teil}\n\n"
                "Aufgabe: Liste die Tatsachenangaben dieses Textes, damit sie mit anderen Dokumenten der Akte "
                "verglichen werden können. Gemeint ist, wer wann was getan, gesagt, angeboten, abgelehnt, "
                "erklärt oder erhalten hat, sowie Eigenschaften, Ausstattung und Zustand von Sachen. Nicht gemeint "
                "sind Rechtsansichten, Anträge, Beweisangebote, Anschriften und Grußformeln.\n"
                "- Formuliere jede Angabe als vollständigen Satz, der ohne das Dokument verständlich ist "
                "(Namen statt Pronomen, Datum, wenn genannt).\n"
                "- haltung: behauptet (der Verfasser stellt es als wahr dar), bestritten (der Verfasser bestreitet "
                "es), unstreitig (ausdrücklich unstreitig), festgestellt (vom Gericht festgestellt).\n"
                f"- Höchstens 25 Angaben.\n\n{BELEGREGEL}\n\n"
                f"Text (jede Zeile ein Absatz, vorn seine Nummer):\n{belege.zeilen(stueck)}",
                SCHEMA_ANGABEN,
            )
            for a in antwort.get("angaben") or []:
                if not isinstance(a, dict) or not str(a.get("text", "")).strip():
                    continue
                fundstelle = self._beleg(t, a.get("absatz"), a.get("zitat"))
                if fundstelle is None:
                    verworfen += 1
                    continue
                haltung = a.get("haltung") if a.get("haltung") in HALTUNGEN else "behauptet"
                angaben.append({"text": str(a["text"]).strip(), "haltung": haltung, "fundstelle": fundstelle})
        return {"dokument_id": t.dokument_id, "dateiname": t.dateiname, "angaben": angaben, "verworfen": verworfen}

    def widersprueche(self, akte_id: int, dokument_ids: list[int] | None = None) -> dict:
        ids = self._dokument_ids(akte_id, dokument_ids)
        if not ids:
            raise ValueError("Die Akte enthält noch keine Dokumente.")
        je_dokument = self._sammle(ids)
        self.fortschritt.melde("Vergleiche die Angaben", len(ids), len(ids) + 1)
        bezug = ",".join(map(str, ids)) if dokument_ids else ""
        return self._gespeichert(
            "widersprueche", [[a["text"] for a in e["angaben"]] for e in je_dokument],
            lambda: self._vergleiche(je_dokument), akte_id, bezug=bezug,
        )

    def _sammle(self, ids: list[int]) -> list[dict]:
        """Tatsachenangaben aller Dokumente (gespeichert oder neu), mit Fortschritt."""
        je_dokument = []
        for i, d in enumerate(ids, 1):
            name = self.con.execute("SELECT dateiname FROM dokument WHERE id = ?", (d,)).fetchone()[0]
            self.fortschritt.melde(f"Sammle Tatsachenangaben: {name}", i - 1, len(ids) + 1)
            je_dokument.append(self.angaben(d, ziel=False))
        return je_dokument

    # --- Chronologie -------------------------------------------------------------------------------

    def chronologie(self, akte_id: int) -> dict:
        ids = self._dokument_ids(akte_id, None)
        if not ids:
            raise ValueError("Die Akte enthält noch keine Dokumente.")
        je_dokument = self._sammle(ids)
        self.fortschritt.melde("Ordne die Ereignisse", len(ids), len(ids) + 1)
        texte = {d: self._text(d) for d in ids}
        eingabe = ([[a["text"] for a in e["angaben"]] for e in je_dokument]
                   + [belege.zeilen(chronologie.kopf(t)) for t in texte.values()])
        return self._gespeichert(
            "chronologie", eingabe,
            lambda: chronologie.erstelle(self._frage, self.budget, je_dokument, texte, self.fortschritt.melde),
            akte_id,
        )

    def _vergleiche(self, je_dokument: list[dict]) -> dict:
        alle = [a for e in je_dokument for a in e["angaben"]]

        def zeile(i: int, a: dict) -> str:
            f = a["fundstelle"]
            herkunft = " · ".join(filter(None, [f["dateiname"], ", ".join(f["parteien"]), a["haltung"]]))
            return f"[A{i}] {herkunft}: {a['text']}"

        zeilen = [zeile(i, a) for i, a in enumerate(alle, 1)]
        # Wenige Angaben prüft das Modell in einer Anfrage. Sonst kommen sie in Blöcke, und je zwei Blöcke werden
        # gemeinsam geprüft: So trifft jede Angabe auf jede.
        block = min(VERGLEICH_BLOCK, self.budget // 2)
        if sum(len(z) + 1 for z in zeilen) <= min(VERGLEICH_EINZELN, self.budget):
            gruppen = [list(range(len(alle)))]
        else:
            bloecke: list[list[int]] = [[]]
            groesse = 0
            for i, z in enumerate(zeilen):
                if bloecke[-1] and groesse + len(z) + 1 > block:
                    bloecke.append([])
                    groesse = 0
                bloecke[-1].append(i)
                groesse += len(z) + 1
            gruppen = [a + b for a, b in combinations(bloecke, 2)]
        gefunden: dict[frozenset[int], dict] = {}
        for g, gruppe in enumerate(gruppen, 1):
            if len(gruppe) < 2:
                continue
            if len(gruppen) > 1:
                self.fortschritt.melde(f"Vergleiche die Angaben (Teil {g} von {len(gruppen)})")
            antwort = self._frage(
                "Unten stehen Tatsachenangaben aus Dokumenten einer Akte. Jede hat eine Kennung, das Dokument, den "
                "Beteiligten (falls bekannt) und die Haltung des Verfassers.\n\n"
                "Aufgabe: Finde Angaben, die einander widersprechen, also nicht zugleich zutreffen können. Achte "
                "besonders auf Widersprüche, die sich nicht in Zahlen oder Daten zeigen, etwa: etwas wurde "
                "abgelehnt, laut anderer Angabe aber angeboten; eine Ausstattung fehlt, wird anderswo aber "
                "vorausgesetzt. Prüfe bei jeder Angabe über eine Absicht, Nutzung oder Fähigkeit, ob eine andere "
                "Angabe etwas ausschließt, das dafür nötig wäre (das ist mindestens eine spannung). Widersprüche "
                "innerhalb desselben Dokuments oder derselben Partei zählen auch.\n"
                "Nicht aufführen: Abweichungen, die nur in einer Zahl, einem Betrag oder einem Datum bestehen (die "
                "gleicht die App bereits selbst ab); Angaben zu verschiedenen Zeitpunkten oder Gegenständen, die "
                "beide zutreffen können; bloß unterschiedlich ausführliche Darstellungen.\n"
                "- art: widerspruch (können nicht beide zutreffen) oder spannung (passen schlecht zusammen, "
                "schließen sich aber nicht zwingend aus)\n"
                "- thema: wenige Wörter, worum es geht\n"
                "- erklaerung: ein Satz, warum die Angaben nicht zusammenpassen\n"
                "- angaben: die Kennungen der beteiligten Angaben, mindestens zwei\n"
                "Höchstens 20 Einträge, die deutlichsten zuerst.\n\n"
                "Angaben:\n" + "\n".join(zeilen[i] for i in gruppe),
                SCHEMA_WIDERSPRUECHE,
            )
            for w in antwort.get("widersprueche") or []:
                if not isinstance(w, dict):
                    continue
                nummern = set()
                for k in w.get("angaben") or []:
                    nr = str(k).strip().lstrip("[A").rstrip("]")
                    if nr.isdigit() and int(nr) - 1 in gruppe:
                        nummern.add(int(nr) - 1)
                schluessel = frozenset(nummern)
                if len(nummern) < 2 or schluessel in gefunden:
                    continue
                gefunden[schluessel] = {
                    "nummern": nummern,
                    "thema": _ohne_kennungen(w.get("thema"), alle) or "Widerspruch",
                    "art": w.get("art") if w.get("art") in ("widerspruch", "spannung") else "widerspruch",
                    "erklaerung": _ohne_kennungen(w.get("erklaerung"), alle),
                }
        widersprueche = []
        for g in _fasse_zusammen(list(gefunden.values())):
            beteiligt = [alle[n] for n in sorted(g["nummern"])]
            widersprueche.append({
                "thema": g["thema"], "art": g["art"], "erklaerung": g["erklaerung"],
                "einordnung": _einordnung([a["fundstelle"] for a in beteiligt]),
                "angaben": beteiligt,
            })
        widersprueche.sort(key=lambda w: (w["art"] != "widerspruch",))
        return {
            "dokumente": [{"dokument_id": e["dokument_id"], "dateiname": e["dateiname"],
                           "angaben": len(e["angaben"]), "verworfen": e["verworfen"]} for e in je_dokument],
            "angaben": len(alle),
            "verworfen": sum(e["verworfen"] for e in je_dokument),
            "widersprueche": widersprueche,
        }


def _fasse_zusammen(treffer: list[dict]) -> list[dict]:
    """Treffer, die dieselbe Angabe enthalten, betreffen denselben Streitpunkt und werden ein Eintrag.

    Das Modell meldet einen Streitpunkt oft mehrfach (je Paar von Dokumenten, je Vergleichsblock). Thema bleibt
    das des ersten Treffers; die Erklärungen werden aneinandergehängt, „widerspruch“ geht vor „spannung“.
    """
    gruppen: list[dict] = []
    for t in treffer:
        neu = {"nummern": set(t["nummern"]), "thema": t["thema"], "art": t["art"], "erklaerungen": [t["erklaerung"]]}
        for g in [g for g in gruppen if g["nummern"] & neu["nummern"]]:
            gruppen.remove(g)
            neu = {"nummern": g["nummern"] | neu["nummern"], "thema": g["thema"],
                   "art": "widerspruch" if "widerspruch" in (g["art"], neu["art"]) else "spannung",
                   "erklaerungen": g["erklaerungen"] + neu["erklaerungen"]}
        gruppen.append(neu)
    return [{"nummern": g["nummern"], "thema": g["thema"], "art": g["art"],
             "erklaerung": " ".join(dict.fromkeys(e for e in g["erklaerungen"] if e))} for g in gruppen]


def _ohne_kennungen(text: object, alle: list[dict]) -> str:
    """Ersetzt Kennungen wie „A66“ oder „[A66]“, die das Modell in seine Erklärung schreibt, durch den Dateinamen."""

    def ersetze(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= len(alle):
            return alle[n - 1]["fundstelle"]["dateiname"].rsplit(".", 1)[0]
        return m.group(0)

    return re.sub(r"\[?\bA(\d+)\b\]?", ersetze, str(text or "")).strip()


def _aussage(text: object, art: object, fundstellen: list[dict]) -> dict:
    return {
        "text": str(text).strip(),
        "art": art if art in ARTEN + THEMEN else "sonstiges",
        "status": BELEGT if fundstellen else OHNE_BELEG,
        "fundstellen": fundstellen,
    }


def _zaehle(aussagen: list[dict]) -> dict:
    return {s: sum(1 for a in aussagen if a["status"] == s) for s in (BELEGT, OHNE_BELEG)}


def _einordnung(fundstellen: list[dict]) -> list[str]:
    """Wie beim Abgleich: im selben Dokument, innerhalb einer Partei, zwischen den Beteiligten."""
    einordnung: set[str] = set()
    for a, b in combinations(fundstellen, 2):
        if a["dokument_id"] == b["dokument_id"]:
            einordnung.add("im_dokument")
        elif set(a["parteien"]) & set(b["parteien"]):
            einordnung.add("innerhalb_partei")
        elif a["parteien"] and b["parteien"]:
            einordnung.add("zwischen_parteien")
        else:
            einordnung.add("partei_unbekannt")
    reihenfolge = ["im_dokument", "innerhalb_partei", "zwischen_parteien", "partei_unbekannt"]
    return [e for e in reihenfolge if e in einordnung]
