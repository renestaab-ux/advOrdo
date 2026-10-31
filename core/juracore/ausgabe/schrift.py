"""Eingebettete Schrift für PDF-Berichte mit Zeichen außerhalb von WinAnsi (z. B. ş, ł, č, ă).

Die PDF-Standardschrift Helvetica kennt nur die Zeichen von cp1252; Namen wie „Şahin“ oder „Łukasz“ würden sonst
zu „?“. Enthält ein Bericht solche Zeichen, setzt ``ausgabe.pdf`` ihn in Liberation Sans (SIL Open Font License
1.1, siehe ``schriften/OFL.txt``). Die Schrift hat dieselben Zeichenbreiten wie Helvetica bzw. Arial, der Umbruch
bleibt also gleich. Eingebettet wird nur eine Teilmenge: alle Glyphen, die der Bericht braucht, die übrigen leer.
Die Glyphennummern bleiben erhalten, deshalb genügt ``CIDToGIDMap /Identity``. Eine ``ToUnicode``-Tabelle sorgt
dafür, dass sich der Text im PDF suchen und kopieren lässt.

Ohne Zusatzbibliothek: gelesen werden nur die Tabellen, die dafür nötig sind (TrueType mit ``glyf``).
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

ORDNER = Path(__file__).with_name("schriften")
DATEIEN = {"normal": "LiberationSans-Regular.ttf", "fett": "LiberationSans-Bold.ttf",
           "kursiv": "LiberationSans-Italic.ttf"}

# Tabellen der Teilmenge; die übrigen (Kerning, OpenType-Layout, Namen) braucht ein PDF-Betrachter nicht.
_TABELLEN = ("OS/2", "cvt ", "fpgm", "glyf", "head", "hhea", "hmtx", "loca", "maxp", "prep")

# Glyphen zusammengesetzter Zeichen (z. B. „ş“ = „s“ + Cedille) verweisen auf Bestandteile.
_ARGS_WORTE, _SKALIERUNG, _WEITERE, _XY_SKALIERUNG, _MATRIX = 0x1, 0x8, 0x20, 0x40, 0x80


def verfuegbar() -> bool:
    return all((ORDNER / d).is_file() for d in DATEIEN.values())


class TrueType:
    """Eine TrueType-Datei: Glyphen je Zeichen, Breiten und Maße, und die Teilmenge zum Einbetten."""

    def __init__(self, daten: bytes, name: str):
        self.daten = daten
        self.name = name
        anzahl = struct.unpack(">H", daten[4:6])[0]
        self.tabellen: dict[str, tuple[int, int]] = {}
        for i in range(anzahl):
            eintrag = daten[12 + 16 * i: 28 + 16 * i]
            self.tabellen[eintrag[:4].decode("latin-1")] = struct.unpack(">II", eintrag[8:16])
        if "glyf" not in self.tabellen:
            raise ValueError(f"{name}: keine TrueType-Schrift mit glyf-Tabelle")
        head = self._tabelle("head")
        self.einheiten = struct.unpack(">H", head[18:20])[0]
        self.rahmen = struct.unpack(">hhhh", head[36:44])
        self.lang_loca = struct.unpack(">h", head[50:52])[0] == 1
        hhea = self._tabelle("hhea")
        self.oben, self.unten = struct.unpack(">hh", hhea[4:8])
        metriken = struct.unpack(">H", hhea[34:36])[0]
        self.glyphen = struct.unpack(">H", self._tabelle("maxp")[4:6])[0]
        hmtx = self._tabelle("hmtx")
        breiten = [struct.unpack(">H", hmtx[4 * i: 4 * i + 2])[0] for i in range(metriken)]
        self.breiten = breiten + [breiten[-1]] * (self.glyphen - metriken)
        os2 = self._tabelle("OS/2") if "OS/2" in self.tabellen else b""
        version = struct.unpack(">H", os2[:2])[0] if len(os2) >= 2 else 0
        self.versalhoehe = struct.unpack(">h", os2[88:90])[0] if version >= 2 and len(os2) >= 90 else self.oben
        post = self._tabelle("post") if "post" in self.tabellen else b""
        self.neigung = struct.unpack(">i", post[4:8])[0] / 65536 if len(post) >= 8 else 0.0
        self.zeichen = self._cmap()
        self._loca = self._lies_loca()

    @classmethod
    def laden(cls, stil: str) -> TrueType:
        datei = ORDNER / DATEIEN[stil]
        return cls(datei.read_bytes(), datei.stem)

    def _tabelle(self, name: str) -> bytes:
        versatz, laenge = self.tabellen[name]
        return self.daten[versatz: versatz + laenge]

    def _cmap(self) -> dict[int, int]:
        """Zeichen → Glyphe aus der Unicode-Tabelle (Format 12, sonst Format 4)."""
        cmap = self._tabelle("cmap")
        unter: dict[tuple[int, int], int] = {}
        for i in range(struct.unpack(">H", cmap[2:4])[0]):
            plattform, kodierung, versatz = struct.unpack(">HHI", cmap[4 + 8 * i: 12 + 8 * i])
            unter[(plattform, kodierung)] = versatz
        for schluessel in ((3, 10), (0, 4), (3, 1), (0, 3)):
            if schluessel not in unter:
                continue
            t = cmap[unter[schluessel]:]
            fmt = struct.unpack(">H", t[:2])[0]
            if fmt == 12:
                zuordnung: dict[int, int] = {}
                for j in range(struct.unpack(">I", t[12:16])[0]):
                    von, bis, glyphe = struct.unpack(">III", t[16 + 12 * j: 28 + 12 * j])
                    for c in range(von, bis + 1):
                        zuordnung[c] = glyphe + c - von
                return zuordnung
            if fmt == 4:
                return _cmap_format4(t)
        raise ValueError(f"{self.name}: keine Unicode-Zuordnung (cmap)")

    def _lies_loca(self) -> list[int]:
        loca = self._tabelle("loca")
        if self.lang_loca:
            return list(struct.unpack(f">{self.glyphen + 1}I", loca[: 4 * (self.glyphen + 1)]))
        return [2 * w for w in struct.unpack(f">{self.glyphen + 1}H", loca[: 2 * (self.glyphen + 1)])]

    def glyphe(self, zeichen: str) -> int:
        """Glyphennummer eines Zeichens; fehlt es in der Schrift, die des Fragezeichens."""
        return self.zeichen.get(ord(zeichen)) or self.zeichen.get(ord("?"), 0)

    def breite(self, glyphe: int) -> float:
        """Vorschub in 1/1000 em."""
        return self.breiten[glyphe] * 1000 / self.einheiten

    def _glyphdaten(self, glyphe: int) -> bytes:
        versatz, _ = self.tabellen["glyf"]
        return self.daten[versatz + self._loca[glyphe]: versatz + self._loca[glyphe + 1]]

    def _mit_bestandteilen(self, glyphen: set[int]) -> set[int]:
        alle: set[int] = set()
        offen = set(glyphen) | {0}
        while offen:
            g = offen.pop()
            if g in alle or g >= self.glyphen:
                continue
            alle.add(g)
            d = self._glyphdaten(g)
            if len(d) < 10 or struct.unpack(">h", d[:2])[0] >= 0:
                continue
            pos = 10
            while pos + 4 <= len(d):
                flags, teil = struct.unpack(">HH", d[pos: pos + 4])
                if teil not in alle:
                    offen.add(teil)
                pos += 4 + (4 if flags & _ARGS_WORTE else 2)
                pos += 2 if flags & _SKALIERUNG else 4 if flags & _XY_SKALIERUNG else 8 if flags & _MATRIX else 0
                if not flags & _WEITERE:
                    break
        return alle

    def teilmenge(self, glyphen: set[int]) -> bytes:
        """Die Schrift mit nur diesen Glyphen (samt Bestandteilen); Nummern und Breiten bleiben unverändert."""
        behalten = self._mit_bestandteilen(glyphen)
        glyf, loca = bytearray(), [0]
        for g in range(self.glyphen):
            if g in behalten:
                glyf += self._glyphdaten(g)
                glyf += b"\0" * (-len(glyf) % 4)
            loca.append(len(glyf))
        head = bytearray(self._tabelle("head"))
        head[8:12] = b"\0\0\0\0"  # checkSumAdjustment, unten neu berechnet
        head[50:52] = struct.pack(">h", 1)  # loca im langen Format
        neu = {name: self._tabelle(name) for name in _TABELLEN if name in self.tabellen}
        neu |= {"glyf": bytes(glyf), "loca": struct.pack(f">{len(loca)}I", *loca), "head": bytes(head)}
        return _baue(neu)

    def kennung(self, glyphen: set[int]) -> str:
        """Sechs Großbuchstaben vor dem Schriftnamen, wie für Teilmengen vorgeschrieben (ISO 32000-1, 9.6.4)."""
        h = hashlib.sha256((self.name + ",".join(map(str, sorted(glyphen)))).encode()).digest()
        return "".join(chr(65 + b % 26) for b in h[:6])


def _cmap_format4(t: bytes) -> dict[int, int]:
    segmente = struct.unpack(">H", t[6:8])[0] // 2
    enden = struct.unpack(f">{segmente}H", t[14: 14 + 2 * segmente])
    basis = 16 + 2 * segmente
    anfaenge = struct.unpack(f">{segmente}H", t[basis: basis + 2 * segmente])
    deltas = struct.unpack(f">{segmente}h", t[basis + 2 * segmente: basis + 4 * segmente])
    versatz_pos = basis + 4 * segmente
    versaetze = struct.unpack(f">{segmente}H", t[versatz_pos: versatz_pos + 2 * segmente])
    zuordnung: dict[int, int] = {}
    for i in range(segmente):
        for c in range(anfaenge[i], enden[i] + 1):
            if c == 0xFFFF:
                continue
            if versaetze[i] == 0:
                g = (c + deltas[i]) & 0xFFFF
            else:
                stelle = versatz_pos + 2 * i + versaetze[i] + 2 * (c - anfaenge[i])
                g = struct.unpack(">H", t[stelle: stelle + 2])[0]
                g = (g + deltas[i]) & 0xFFFF if g else 0
            if g:
                zuordnung[c] = g
    return zuordnung


def _pruefsumme(daten: bytes) -> int:
    daten += b"\0" * (-len(daten) % 4)
    return sum(struct.unpack(f">{len(daten) // 4}I", daten)) & 0xFFFFFFFF


def _baue(tabellen: dict[str, bytes]) -> bytes:
    namen = sorted(tabellen)
    n = len(namen)
    potenz = 1 << (n.bit_length() - 1)
    kopf = struct.pack(">IHHHH", 0x00010000, n, potenz * 16, potenz.bit_length() - 1, n * 16 - potenz * 16)
    versatz = 12 + 16 * n
    verzeichnis, rumpf = b"", b""
    for name in namen:
        d = tabellen[name]
        verzeichnis += name.encode("latin-1") + struct.pack(">III", _pruefsumme(d), versatz + len(rumpf), len(d))
        rumpf += d + b"\0" * (-len(d) % 4)
    datei = bytearray(kopf + verzeichnis + rumpf)
    head = 12 + 16 * n + sum(len(tabellen[x]) + (-len(tabellen[x]) % 4) for x in namen[: namen.index("head")])
    datei[head + 8: head + 12] = struct.pack(">I", (0xB1B0AFBA - _pruefsumme(bytes(datei))) & 0xFFFFFFFF)
    return bytes(datei)


class Satzschrift:
    """Eine eingebettete Schrift im PDF: merkt sich die benutzten Glyphen und liefert am Ende die PDF-Objekte."""

    def __init__(self, schrift: TrueType):
        self.schrift = schrift
        self.benutzt: dict[int, str] = {}

    def breite(self, text: str) -> float:
        return sum(self.schrift.breite(self.schrift.glyphe(c)) for c in text)

    def zeichenkette(self, text: str) -> bytes:
        glyphen = []
        for c in text:
            if ord(c) not in self.schrift.zeichen:
                c = "?"  # fehlt in der Schrift (z. B. chinesische Zeichen)
            g = self.schrift.glyphe(c)
            self.benutzt.setdefault(g, c)
            glyphen.append(g)
        return b"<" + "".join(f"{g:04X}" for g in glyphen).encode() + b">"

    def objekte(self, erste_nummer: int) -> list[bytes]:
        """Type0-Schrift, CID-Schrift, Beschreibung, Schriftdatei und ToUnicode; die erste ist ``erste_nummer``."""
        s, n = self.schrift, erste_nummer
        glyphen = set(self.benutzt) | {0}
        name = f"{s.kennung(glyphen)}+{s.name}".encode()
        datei = s.teilmenge(glyphen)
        gepackt = zlib.compress(datei)
        faktor = 1000 / s.einheiten
        breiten = b" ".join(b"%d [%d]" % (g, round(s.breite(g))) for g in sorted(glyphen))
        flags = 4 | (64 if s.neigung else 0)  # symbolisch (eigene Glyphennummern), ggf. kursiv
        return [
            b"<< /Type /Font /Subtype /Type0 /BaseFont /%s /Encoding /Identity-H /DescendantFonts [%d 0 R] "
            b"/ToUnicode %d 0 R >>" % (name, n + 1, n + 4),
            b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /%s /CIDSystemInfo << /Registry (Adobe) /Ordering "
            b"(Identity) /Supplement 0 >> /FontDescriptor %d 0 R /CIDToGIDMap /Identity /W [%s] >>"
            % (name, n + 2, breiten),
            b"<< /Type /FontDescriptor /FontName /%s /Flags %d /FontBBox [%d %d %d %d] /ItalicAngle %.1f /Ascent %d "
            b"/Descent %d /CapHeight %d /StemV 80 /FontFile2 %d 0 R >>"
            % (name, flags, *(round(v * faktor) for v in s.rahmen), s.neigung, round(s.oben * faktor),
               round(s.unten * faktor), round(s.versalhoehe * faktor), n + 3),
            b"<< /Length %d /Length1 %d /Filter /FlateDecode >>\nstream\n" % (len(gepackt), len(datei))
            + gepackt + b"\nendstream",
            _strom(_tounicode(self.benutzt)),
        ]


def _strom(inhalt: bytes) -> bytes:
    gepackt = zlib.compress(inhalt)
    return b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(gepackt) + gepackt + b"\nendstream"


def _tounicode(benutzt: dict[int, str]) -> bytes:
    zeilen = [b"/CIDInit /ProcSet findresource begin", b"12 dict begin", b"begincmap",
              b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
              b"/CMapName /Adobe-Identity-UCS def", b"/CMapType 2 def",
              b"1 begincodespacerange", b"<0000> <FFFF>", b"endcodespacerange"]
    eintraege = sorted(benutzt.items())
    for i in range(0, len(eintraege), 100):
        block = eintraege[i: i + 100]
        zeilen.append(b"%d beginbfchar" % len(block))
        zeilen += [b"<%04X> <%s>" % (g, c.encode("utf-16-be").hex().upper().encode()) for g, c in block]
        zeilen.append(b"endbfchar")
    zeilen += [b"endcmap", b"CMapName currentdict /CMap defineresource pop", b"end", b"end"]
    return b"\n".join(zeilen)
