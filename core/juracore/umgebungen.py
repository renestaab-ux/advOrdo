"""Arbeitsumgebungen: getrennte Datenordner je Identität (z. B. Kanzlei, Rechtsabteilung, Test).

Jede Umgebung hat eigene Akten mit Ablage, eigene KI-Ergebnisse und später ein eigenes Profil.
Gemeinsam bleiben die Wissensbasis (Gesetze, Rechtsprechungsverzeichnis) und die Einstellungen.
Die Umgebung „Standard“ ist der bisherige Datenordner selbst; beim Einführen wird nichts verschoben.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

STANDARD = "standard"


class Umgebungen:
    def __init__(self, basis: Path):
        self.basis = Path(basis)
        self.datei = self.basis / "umgebungen.json"
        self.wurzel = self.basis / "umgebungen"

    def _lade(self) -> dict:
        try:
            daten = json.loads(self.datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            daten = {}
        eintraege = [e for e in daten.get("umgebungen", []) if isinstance(e, dict) and e.get("id") != STANDARD]
        standard = {"id": STANDARD, "name": daten.get("standard_name") or "Standard", "angelegt_am": None}
        aktiv = daten.get("aktiv", STANDARD)
        if aktiv != STANDARD and not any(e["id"] == aktiv for e in eintraege):
            aktiv = STANDARD
        return {"aktiv": aktiv, "standard": standard, "umgebungen": eintraege}

    def _speichere(self, z: dict) -> None:
        self.basis.mkdir(parents=True, exist_ok=True)
        daten = {"aktiv": z["aktiv"], "standard_name": z["standard"]["name"], "umgebungen": z["umgebungen"]}
        tmp = self.datei.with_suffix(".tmp")
        tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.datei)

    def liste(self) -> dict:
        z = self._lade()
        alle = [z["standard"], *z["umgebungen"]]
        return {
            "aktiv": z["aktiv"],
            "umgebungen": [{**e, "standard": e["id"] == STANDARD, "aktiv": e["id"] == z["aktiv"]} for e in alle],
        }

    def aktiv(self) -> str:
        return self._lade()["aktiv"]

    def ordner(self, umgebung_id: str | None = None) -> Path:
        uid = umgebung_id or self.aktiv()
        return self.basis if uid == STANDARD else self.wurzel / uid

    def _name_pruefen(self, z: dict, name: str, ausser: str | None = None) -> str:
        name = " ".join(str(name).split())
        if not name:
            raise ValueError("Bitte einen Namen für die Umgebung angeben.")
        if len(name) > 60:
            raise ValueError("Der Name ist zu lang (höchstens 60 Zeichen).")
        for e in [z["standard"], *z["umgebungen"]]:
            if e["id"] != ausser and e["name"].casefold() == name.casefold():
                raise ValueError(f"Eine Umgebung „{name}“ gibt es schon.")
        return name

    def anlegen(self, name: str) -> dict:
        z = self._lade()
        name = self._name_pruefen(z, name)
        basis_id = kennung(name)
        vergeben = {STANDARD, *(e["id"] for e in z["umgebungen"])}
        uid, n = basis_id, 2
        while uid in vergeben or (self.wurzel / uid).exists():
            uid, n = f"{basis_id}-{n}", n + 1
        (self.wurzel / uid).mkdir(parents=True)
        eintrag = {"id": uid, "name": name, "angelegt_am": datetime.now().isoformat(timespec="seconds")}
        z["umgebungen"].append(eintrag)
        self._speichere(z)
        return {**eintrag, "standard": False, "aktiv": False}

    def umbenennen(self, umgebung_id: str, name: str) -> dict:
        z = self._lade()
        name = self._name_pruefen(z, name, ausser=umgebung_id)
        if umgebung_id == STANDARD:
            z["standard"]["name"] = name
        else:
            self._finde(z, umgebung_id)["name"] = name
        self._speichere(z)
        return self.liste()

    def aktivieren(self, umgebung_id: str) -> Path:
        z = self._lade()
        if umgebung_id != STANDARD:
            self._finde(z, umgebung_id)
        z["aktiv"] = umgebung_id
        self._speichere(z)
        ordner = self.ordner(umgebung_id)
        ordner.mkdir(parents=True, exist_ok=True)
        return ordner

    def loeschen(self, umgebung_id: str) -> dict:
        """Entfernt eine Umgebung samt ihrer Akten. „Standard“ und die aktive Umgebung bleiben geschützt."""
        z = self._lade()
        if umgebung_id == STANDARD:
            raise ValueError("Die Umgebung „Standard“ enthält die bisherigen Daten und kann nicht gelöscht werden.")
        if umgebung_id == z["aktiv"]:
            raise ValueError("Die aktive Umgebung kann nicht gelöscht werden. Bitte vorher in eine andere wechseln.")
        self._finde(z, umgebung_id)
        ordner = (self.wurzel / umgebung_id).resolve()
        if ordner.parent != self.wurzel.resolve():
            raise ValueError("Ungültige Umgebung.")
        z["umgebungen"] = [e for e in z["umgebungen"] if e["id"] != umgebung_id]
        self._speichere(z)
        try:
            shutil.rmtree(ordner)
        except OSError as fehler:
            # Die Umgebung ist aus der Liste entfernt; der Ordner blieb (teilweise) bestehen,
            # etwa weil eine Datei gesperrt ist. Der Fehler darf nicht still bleiben (Datenschutz).
            raise RuntimeError(
                "Die Umgebung wurde entfernt, ihr Ordner ließ sich aber nicht vollständig löschen: "
                f"{fehler}") from fehler
        return self.liste()

    @staticmethod
    def _finde(z: dict, umgebung_id: str) -> dict:
        for e in z["umgebungen"]:
            if e["id"] == umgebung_id:
                return e
        raise LookupError(f"Unbekannte Umgebung: {umgebung_id!r}")


def kennung(name: str) -> str:
    """Ordnertaugliche Kennung aus dem Namen: „Test Rechtsabteilung“ → „test-rechtsabteilung“."""
    text = name.replace("ß", "ss")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue")):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-")
    return text if text and text != STANDARD else "umgebung"
