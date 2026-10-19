"""Aktenverwaltung (Konzept „Aktenverwaltung“ vom 19.10.2026, Stufe 1).

- ``beteiligte``: Verzeichnis aller Personen und Organisationen, die in Akten vorkommen.
- ``stammdaten``: Aktenzeichen, Gegenstand, Status usw. einer Akte und ihre Beteiligten mit Rolle.
- ``kollision``: Prüfung auf widerstreitende Interessen über alle Akten (§ 43a Abs. 4 BRAO, § 3 BORA).

Alles liegt in der Aktendatenbank der aktiven Arbeitsumgebung. Akten verweisen auf Beteiligte, statt sie zu kopieren.
"""

from __future__ import annotations

import sqlite3

from . import beteiligte, kollision, stammdaten


def einrichten(con: sqlite3.Connection) -> None:
    """Legt die Tabellen an und ergänzt die Akten aus älteren Versionen; vorhandene Inhalte bleiben unverändert."""
    beteiligte.einrichten(con)
    stammdaten.einrichten(con)
    kollision.einrichten(con)
