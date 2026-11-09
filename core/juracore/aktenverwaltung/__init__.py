"""Aktenverwaltung (Konzept „Aktenverwaltung“ vom 19.10.2026, Stufe 1).

- ``beteiligte``: Verzeichnis aller Personen und Organisationen, die in Akten vorkommen.
- ``stammdaten``: Aktenzeichen, Gegenstand, Status usw. einer Akte und ihre Beteiligten mit Rolle.
- ``kollision``: Prüfung auf widerstreitende Interessen über alle Akten (§ 43a Abs. 4 BRAO, § 3 BORA).

Stufe 2:
- ``verfahren``: Verfahren einer Akte mit Instanz, Gericht und gerichtlichem Aktenzeichen.
- ``kalender``: Fristen, Termine und Wiedervorlagen; Vorschläge aus Dokumenten.
- ``fristenbuch``: Fristenbuch (Word, PDF, Excel …) und Kalenderdatei (.ics) eines Zeitraums.
- ``notizen``: Aktennotizen.
- ``rubrum`` und ``aus_dokument``: Akte aus einem Dokument anlegen.
- ``sitzung``: Sitzungsblatt und Terminsnotizen für den Terminmodus des Arbeitsfensters.

Alles liegt in der Aktendatenbank der aktiven Arbeitsumgebung. Akten verweisen auf Beteiligte, statt sie zu kopieren.
"""

from __future__ import annotations

import sqlite3

from . import beteiligte, kalender, kollision, notizen, sitzung, stammdaten, verfahren


def einrichten(con: sqlite3.Connection) -> None:
    """Legt die Tabellen an und ergänzt die Akten aus älteren Versionen; vorhandene Inhalte bleiben unverändert."""
    beteiligte.einrichten(con)
    stammdaten.einrichten(con)
    kollision.einrichten(con)
    verfahren.einrichten(con)
    kalender.einrichten(con)
    notizen.einrichten(con)
    sitzung.einrichten(con)
