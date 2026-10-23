"""Bericht als Markdown und als reiner Text."""

from __future__ import annotations

import re
import textwrap

from . import Absatz, Bericht, Eintrag, Kopf, Ueberschrift, beleg_text, marken_text

_MD_SONDER = re.compile(r"([\\`*_\[\]<>|])")


def _md(text: str) -> str:
    """Zeichen, die Markdown als Auszeichnung liest, wörtlich lassen; Zeilenumbrüche werden Leerzeichen."""
    text = _MD_SONDER.sub(r"\\\1", " ".join(text.split()))
    return re.sub(r"^([#>+-]|\d+\.)(\s)", r"\\\1\2", text)


def markdown(bericht: Bericht) -> str:
    zeilen = [f"# {_md(bericht.titel)}", ""]
    for b in bericht.bausteine:
        if isinstance(b, Kopf):
            zeilen += ["| | |", "|---|---|"] + [f"| {_md(k)} | {_md(v)} |" for k, v in b.zeilen] + [""]
        elif isinstance(b, Ueberschrift):
            zeilen += [f"{'#' * (b.ebene + 1)} {_md(b.text)}", ""]
        elif isinstance(b, Absatz):
            zeilen += [f"*{_md(b.text)}*" if b.leise else _md(b.text), ""]
        elif isinstance(b, Eintrag):
            zeilen += _md_eintrag(b)
    return "\n".join(zeilen).rstrip() + "\n"


def _md_eintrag(e: Eintrag) -> list[str]:
    marken = f" *({_md(', '.join(e.marken))})*" if e.marken else ""
    belege = [f"{'   ' if e.kompakt else ''}- {_md(beleg_text(b))}" for b in e.belege]
    if e.kompakt:
        # Nummer als Text, nicht als Markdown-Liste: Die Nummern sollen genau wie in der App lauten.
        zeilen = [f"**{_md(e.nummer)}** {_md(e.titel)}{marken}"] if e.nummer else [f"{_md(e.titel)}{marken}"]
        zeilen += [_md(z) for z in e.zeilen]
        return [zeilen[0] + "  ", *(z + "  " for z in zeilen[1:]), *belege, ""]
    zeilen = [f"### {_md(e.nummer) + ' ' if e.nummer else ''}{_md(e.titel)}{marken}", ""]
    for z in e.zeilen:
        zeilen += [_md(z), ""]
    return zeilen + belege + [""]


BREITE = 100


def klartext(bericht: Bericht) -> str:
    zeilen = [bericht.titel, "=" * min(BREITE, len(bericht.titel)), ""]
    for b in bericht.bausteine:
        if isinstance(b, Kopf):
            breite = max(len(k) for k, _ in b.zeilen) + 2 if b.zeilen else 0
            for k, v in b.zeilen:
                zeilen += textwrap.wrap(v, BREITE, initial_indent=f"{k}:".ljust(breite),
                                        subsequent_indent=" " * breite) or [f"{k}:"]
            zeilen.append("")
        elif isinstance(b, Ueberschrift):
            strich = "=" if b.ebene == 1 else "-"
            zeilen += ["", b.text, strich * min(BREITE, len(b.text)), ""]
        elif isinstance(b, Absatz):
            zeilen += textwrap.wrap(" ".join(b.text.split()), BREITE) + [""]
        elif isinstance(b, Eintrag):
            zeilen += _text_eintrag(b)
    return "\n".join(zeilen).rstrip() + "\n"


def _text_eintrag(e: Eintrag) -> list[str]:
    kopf = f"{e.nummer} " if e.nummer else ""
    zeilen = textwrap.wrap(kopf + " ".join(e.titel.split()) + marken_text(e), BREITE,
                           subsequent_indent=" " * len(kopf))
    for z in e.zeilen:
        zeilen += textwrap.wrap(" ".join(z.split()), BREITE, initial_indent="   ", subsequent_indent="   ")
    for b in e.belege:
        zeilen += textwrap.wrap(" ".join(beleg_text(b).split()), BREITE, initial_indent="   - ",
                                subsequent_indent="     ")
    return zeilen + [""]
