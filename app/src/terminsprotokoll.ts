/**
 * Terminsprotokoll als Aktennotiz: „Termin beenden“ speichert die Terminsnotizen als schlichten Text
 * (core: sitzung.protokoll), damit Export, Druck und Suche ihn unverändert lesen. Für die Anzeige wird er hier
 * wieder in Einträge zerlegt und so dargestellt wie im Terminmodus (Uhrzeit, Art, Text, Dokumentbezug).
 */
import { TERMIN_NOTIZ_ARTEN } from "./kern/sitzung";

export interface ProtokollEintrag {
  zeit: string;
  /** „Hinweis des Gerichts“ usw.; null bei einer einfachen Notiz. */
  art: string | null;
  text: string;
  /** Dateiname aus „[zu …]“ am Ende. */
  bezug: string | null;
}

export interface Terminsprotokoll {
  kopf: string;
  eintraege: ProtokollEintrag[];
}

const KOPF = /^Terminsprotokoll \d{2}\.\d{2}\.\d{4}/;
const ZEILE = /^(\d{2}:\d{2}) (.*)$/;
const BEZUG = /\s*\[zu ([^\]]+)\]$/;
const ARTEN = TERMIN_NOTIZ_ARTEN.filter((a) => a.art !== "notiz").map((a) => a.titel);

/** Zerlegt den Text eines Terminsprotokolls; null, wenn der Text keins ist (dann bleibt er schlichter Text). */
export function protokollLesen(text: string): Terminsprotokoll | null {
  const zeilen = text.replace(/\r\n/g, "\n").split("\n");
  if (!KOPF.test(zeilen[0] ?? "")) return null;
  const kopf: string[] = [zeilen[0]];
  const roh: { zeit: string; text: string }[] = [];
  for (const zeile of zeilen.slice(1)) {
    const m = ZEILE.exec(zeile);
    if (m) roh.push({ zeit: m[1], text: m[2] });
    else if (roh.length > 0) roh[roh.length - 1].text += "\n" + zeile.replace(/^ {6}/, "");
    else kopf.push(zeile);
  }
  const eintraege = roh.map(({ zeit, text: t }) => {
    let rest = t.trimEnd();
    let bezug: string | null = null;
    const b = BEZUG.exec(rest);
    if (b) {
      bezug = b[1];
      rest = rest.slice(0, b.index);
    }
    const art = ARTEN.find((a) => rest.startsWith(a + ": ")) ?? null;
    if (art) rest = rest.slice(art.length + 2);
    return { zeit, art, text: rest, bezug };
  });
  return { kopf: kopf.join("\n").trim(), eintraege };
}
