"""Schriftstücke aus der Akte erzeugen: Briefe und Schriftsätze als Word-Datei, ohne Sprachmodell und ohne Netz.

- ``platzhalter``: welche Platzhalter es gibt und was sie in einer Akte bedeuten (Eigene Daten, Stammdaten,
  Beteiligte, Verfahren).
- ``fuellen``: setzt die Werte in eine Word-Datei ein (eigene Vorlage oder Grundvorlage).
- ``grundvorlagen``: mitgelieferte Vorlagen für Brief und Schriftsatz mit Briefkopf und Logo.
- ``vorlagen``: eigene Vorlagen der Arbeitsumgebung verwalten und Schriftstücke erzeugen.

Platzhalter stehen in doppelten geschweiften Klammern, z. B. ``{{Mandant.Name}}``. Groß- und Kleinschreibung,
Umlaute (``Empfänger`` oder ``Empfaenger``) und Bindestriche spielen keine Rolle.
"""
