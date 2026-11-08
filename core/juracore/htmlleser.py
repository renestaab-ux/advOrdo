"""Gemeinsame Grundlage der HTML-Leser (Gesetze, Rechtsprechung, Nachrichten).

Jeder Leser erbt von :class:`HtmlLeser`: Zeichenreferenzen werden aufgelöst, Attribute kommen als Wörterbuch mit
leeren Texten statt ``None``, und :meth:`HtmlLeser.lies` füttert und schließt den Leser in einem Schritt."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Self


class HtmlLeser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)

    @staticmethod
    def attribute(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {k: v or "" for k, v in attrs}

    @classmethod
    def lies(cls, text: str) -> Self:
        leser = cls()
        leser.feed(text)
        leser.close()
        return leser


def leerraum(text: str) -> str:
    """Leerraum (auch geschützte Leerzeichen) zu je einem Leerzeichen zusammenfassen."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
