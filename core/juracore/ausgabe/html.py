"""Bericht als HTML, zum Drucken aus der App (eigene Druckansicht, schwarz auf weiß)."""

from __future__ import annotations

from html import escape

from . import Absatz, Bericht, Eintrag, Kopf, Ueberschrift

# Gilt nur innerhalb von .druckbericht, damit die Oberfläche der App unberührt bleibt.
STIL = """
.druckbericht { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #000;
  background: #fff; line-height: 1.35; }
.druckbericht h1 { font-size: 16pt; margin: 0 0 8pt; }
.druckbericht h2 { font-size: 13pt; margin: 16pt 0 4pt; border-bottom: 1px solid #999; break-after: avoid; }
.druckbericht h3 { font-size: 11pt; margin: 10pt 0 2pt; break-after: avoid; }
.druckbericht table.kopf { border-collapse: collapse; margin-bottom: 8pt; }
.druckbericht table.kopf th { text-align: left; padding: 1pt 12pt 1pt 0; vertical-align: top; }
.druckbericht table.kopf td { padding: 1pt 0; }
.druckbericht p { margin: 3pt 0; }
.druckbericht .leise { color: #555; font-size: 9pt; }
.druckbericht .marke { font-size: 8.5pt; border: 1px solid #777; border-radius: 3pt; padding: 0 3pt; margin-left: 4pt; }
.druckbericht .eintrag { break-inside: avoid; margin: 0 0 6pt; }
.druckbericht ul.belege { margin: 2pt 0 0; padding-left: 16pt; font-size: 9.5pt; }
.druckbericht .ort { font-weight: 600; }
.druckbericht .zitat { font-style: italic; }
"""


def fragment(bericht: Bericht) -> str:
    teile = [f'<div class="druckbericht"><h1>{escape(bericht.titel)}</h1>']
    for b in bericht.bausteine:
        if isinstance(b, Kopf):
            teile.append('<table class="kopf">' + "".join(
                f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in b.zeilen) + "</table>")
        elif isinstance(b, Ueberschrift):
            teile.append(f"<h{b.ebene + 1}>{escape(b.text)}</h{b.ebene + 1}>")
        elif isinstance(b, Absatz):
            teile.append(f'<p class="leise">{escape(b.text)}</p>' if b.leise else f"<p>{escape(b.text)}</p>")
        elif isinstance(b, Eintrag):
            teile.append(_eintrag(b))
    teile.append("</div>")
    return "".join(teile)


def _eintrag(e: Eintrag) -> str:
    nummer = f"{escape(e.nummer)} " if e.nummer else ""
    marken = "".join(f'<span class="marke">{escape(m)}</span>' for m in e.marken)
    kopf = (f"<p><strong>{nummer}</strong>{escape(e.titel)}{marken}</p>" if e.kompakt
            else f"<h3>{nummer}{escape(e.titel)}{marken}</h3>")
    zeilen = "".join(f"<p>{escape(z)}</p>" for z in e.zeilen)
    belege = ""
    if e.belege:
        punkte = []
        for b in e.belege:
            text = f"{escape(b.vorab)} – " if b.vorab else ""
            text += f'<span class="ort">{escape(b.ort)}</span>'
            if b.angenaehert:
                text += ' <span class="leise">(Zitat angenähert)</span>'
            if b.zitat:
                text += f': <span class="zitat">„{escape(b.zitat)}“</span>'
            punkte.append(f"<li>{text}</li>")
        belege = f'<ul class="belege">{"".join(punkte)}</ul>'
    return f'<div class="eintrag">{kopf}{zeilen}{belege}</div>'


def seite(bericht: Bericht) -> str:
    """Eigenständige HTML-Seite (für Tests und zum Ansehen im Browser)."""
    return (f'<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{escape(bericht.titel)}</title>'
            f"<style>{STIL}</style></head><body>{fragment(bericht)}</body></html>")
