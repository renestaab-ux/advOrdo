import type { AktenDokument } from "./dokumente";

// ---- Toolbox: Rechner aus JuraBox Lite ----

export interface ZinsZeile {
  von: string;
  bis: string;
  tage: number;
  satz: string;
  grundlage: string;
  zinsen: string;
  zinssaldo: string;
  restschuld: string;
  ereignis: string;
}

export interface ZinsErgebnis {
  zeilen: ZinsZeile[];
  summe_tage: number;
  summe_zinsen: string;
  summe_zinsen_genau: string;
  pauschale: string;
  hauptforderung: string;
  offene_zinsen: string;
  gesamt: string;
  aktueller_satz: string;
  zinsen_pro_tag: string;
  grundlagen: string[];
  basiszins_quelle: string;
  hinweise: string[];
}

export interface BasiszinsStand {
  quelle: string;
  stand: string;
  saetze: { ab: string; satz: string; eigen: boolean }[];
  aktuell: { ab: string; satz: string };
  bekannt_bis: string;
}

export interface FristErgebnis {
  bezugstag: string;
  wochentag_bezugstag: string;
  fristbeginn: string;
  wochentag_fristbeginn: string;
  rechnerisches_ende: string;
  wochentag_rechnerisch: string;
  ende: string;
  wochentag: string;
  hinweise: string[];
  verschoben: boolean;
  grund: string;
  grundlagen: string[];
  land: string;
  feiertage_stand: string;
}

export interface KostenPosten {
  nr: string;
  text: string;
  satz: string | null;
  betrag: string;
}

export interface KostenAbrechnung {
  titel: string;
  posten: KostenPosten[];
  netto: string;
  summe: string;
  /** Gegenseite: so viele gleiche Anwälte stehen hinter dieser Abrechnung. */
  anzahl?: number;
}

export interface ProzesskostenErgebnis {
  streitwert: string;
  fassung: string;
  fassung_titel: string;
  gebuehr_gkg: string;
  gebuehr_rvg: string;
  gericht: KostenPosten[];
  vorgerichtlich: KostenAbrechnung | null;
  eigene: KostenAbrechnung[];
  gegner: KostenAbrechnung[];
  summe_gericht: string;
  summe_eigene: string;
  summe_gegner: string;
  kostenrisiko: string;
  umsatzsteuer: string | null;
  hinweise: string[];
  grundlagen: string[];
}

export const BUNDESLAENDER: [string, string][] = [
  ["BW", "Baden-Württemberg"], ["BY", "Bayern"], ["BE", "Berlin"], ["BB", "Brandenburg"], ["HB", "Bremen"],
  ["HH", "Hamburg"], ["HE", "Hessen"], ["MV", "Mecklenburg-Vorpommern"], ["NI", "Niedersachsen"],
  ["NW", "Nordrhein-Westfalen"], ["RP", "Rheinland-Pfalz"], ["SL", "Saarland"], ["SN", "Sachsen"],
  ["ST", "Sachsen-Anhalt"], ["SH", "Schleswig-Holstein"], ["TH", "Thüringen"],
];

/** Betrag aus dem Kern ("1234.5") deutsch, mit zwei oder mehr Nachkommastellen: "1.234,50 €". */
export function euro(betrag: string | number, stellen = 2): string {
  return Number(betrag).toLocaleString("de-DE", { minimumFractionDigits: stellen, maximumFractionDigits: stellen }) + " €";
}

/** Gebührensatz aus dem Kern deutsch: "1.3" → "1,3", "3" → "3,0". */
export function satzDe(satz: string): string {
  return satz.includes(".") ? satz.replace(".", ",") : satz + ",0";
}

/** Prozentsatz aus dem Kern ("8.62") deutsch: "8,62 %". */
export function prozent(satz: string | number): string {
  return Number(satz).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " %";
}

/** ISO-Datum (JJJJ-MM-TT) als TT.MM.JJJJ, ohne Umweg über die Zeitzone. */
export function datumDe(iso: string): string {
  const [j, m, t] = iso.split("-");
  return `${t}.${m}.${j}`;
}

/** ISO-Zeitpunkt ("2026-10-17T21:30:00+02:00") als "17.10.2026, 21:30", so wie er gespeichert ist. */
export function zeitpunktDe(iso: string): string {
  const uhr = iso.slice(11, 16);
  return datumDe(iso.slice(0, 10)) + (uhr ? `, ${uhr}` : "");
}

/** Datum eines Dokuments für die Anzeige: Wert, kurze Herkunft und Erläuterung mit Fundstelle. */
export function dokumentDatum(
  d: Pick<AktenDokument, "datum" | "datum_quelle" | "datum_seite" | "datum_text" | "gespeichert_am" | "gespeichert_quelle">,
): { text: string; herkunft: string; erklaerung: string } {
  const gespeichert =
    d.gespeichert_am &&
    `Zuletzt gespeichert: ${zeitpunktDe(d.gespeichert_am)} (${d.gespeichert_quelle === "word" ? "laut Word" : "Dateidatum"}).`;
  if (!d.datum || d.datum_quelle === "unbekannt" || !d.datum_quelle) {
    return { text: "–", herkunft: "", erklaerung: "Im Dokument steht keine Datumszeile; ein Speicherdatum ist nicht bekannt." };
  }
  switch (d.datum_quelle) {
    case "dokument":
      return {
        text: datumDe(d.datum),
        herkunft: "aus dem Dokument",
        erklaerung: [
          `Datumszeile${d.datum_seite != null ? ` auf S. ${d.datum_seite}` : ""}: „${d.datum_text}“.`,
          gespeichert,
        ]
          .filter(Boolean)
          .join(" "),
      };
    case "word":
      return {
        text: datumDe(d.datum),
        herkunft: "zuletzt gespeichert",
        erklaerung: `Keine Datumszeile im Dokument. ${gespeichert}`,
      };
    case "datei":
      return {
        text: datumDe(d.datum),
        herkunft: "Dateidatum",
        erklaerung: `Keine Datumszeile im Dokument. ${gespeichert}`,
      };
    case "manuell":
      return {
        text: datumDe(d.datum),
        herkunft: "von Hand",
        erklaerung: "Von Hand eingetragen (Ansicht „Details“).",
      };
  }
}

/** Heutiges Datum als JJJJ-MM-TT in lokaler Zeit. */
export function heuteIso(jetzt = new Date()): string {
  const z = (n: number) => String(n).padStart(2, "0");
  return `${jetzt.getFullYear()}-${z(jetzt.getMonth() + 1)}-${z(jetzt.getDate())}`;
}

export interface Umgebung {
  id: string;
  name: string;
  angelegt_am: string | null;
  standard: boolean;
  aktiv: boolean;
}

export interface UmgebungsListe {
  aktiv: string;
  umgebungen: Umgebung[];
}

/** Die aktive Arbeitsumgebung; angezeigt wird sie erst, wenn es mehr als eine gibt. */
export function aktiveUmgebung(liste: UmgebungsListe | null): Umgebung | null {
  if (!liste || liste.umgebungen.length < 2) return null;
  return liste.umgebungen.find((u) => u.id === liste.aktiv) ?? null;
}
