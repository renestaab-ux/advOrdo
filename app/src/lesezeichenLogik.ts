import { FARBEN, type AnmerkFilter, type Anmerkung, type Bedeutungen } from "./anmerkungLogik";

/** Lesezeichen: Inhaltsverzeichnis des PDFs und eigene Lesezeichen in Ordnern; dazu die Marken an der Bildlaufleiste. */

export interface Lesezeichen {
  id: number;
  dokument_id: number;
  ordner_id: number | null;
  titel: string;
  start: number;
  ende: number;
  zitat: string;
  seite: number | null;
  abschnitt: number | null;
  rn: number | null;
  status: "gefunden" | "nicht_gefunden";
  reihenfolge: number;
  angelegt_am: string;
  dokument: string;
}

export interface LesezeichenOrdner {
  id: number;
  name: string;
  reihenfolge: number;
}

export interface LesezeichenListe {
  ordner: LesezeichenOrdner[];
  lesezeichen: Lesezeichen[];
}

/** Ein Eintrag im Inhaltsverzeichnis des PDFs (nur lesend). */
export interface InhaltEintrag {
  ebene: number;
  titel: string;
  seite: number | null;
}

/** Lesezeichen auf einer Seite des Originals; ``y`` ist die Höhe der Stelle als Anteil der Seite. */
export type LesezeichenAufSeite = Lesezeichen & { y: number | null };

export interface LesezeichenGruppe {
  /** null: „Ohne Ordner“. */
  id: number | null;
  name: string;
  eintraege: Lesezeichen[];
}

/** Ordner in ihrer Reihenfolge, darunter „Ohne Ordner“; Lesezeichen je Ordner in ihrer Reihenfolge. */
export function lesezeichenGruppen(l: LesezeichenListe, mitLeeren = true): LesezeichenGruppe[] {
  const gruppen: LesezeichenGruppe[] = l.ordner.map((o) => ({ id: o.id, name: o.name, eintraege: [] }));
  const ohne: LesezeichenGruppe = { id: null, name: "Ohne Ordner", eintraege: [] };
  for (const z of l.lesezeichen) (gruppen.find((g) => g.id === z.ordner_id) ?? ohne).eintraege.push(z);
  return [...gruppen, ohne].filter((g) => mitLeeren || g.eintraege.length > 0);
}

// --- Gemeinsame Ordner für Lesezeichen und Markierungen ---------------------------------------------------------------

/** Ein Eintrag in den Ordnern der Akte: Lesezeichen oder Markierung (mit oder ohne Kommentar). */
export type OrdnerEintrag = { art: "lesezeichen"; z: Lesezeichen } | { art: "markierung"; a: Anmerkung };

export interface OrdnerGruppe {
  id: number | null;
  name: string;
  eintraege: OrdnerEintrag[];
}

export const schluessel = (e: OrdnerEintrag) => (e.art === "lesezeichen" ? `l${e.z.id}` : `m${e.a.id}`);
const eintragId = (e: OrdnerEintrag) => (e.art === "lesezeichen" ? e.z.id : e.a.id);
const eintragOrdner = (e: OrdnerEintrag) => (e.art === "lesezeichen" ? e.z.ordner_id : (e.a.ordner_id ?? null));
const eintragPlatz = (e: OrdnerEintrag) => (e.art === "lesezeichen" ? e.z.reihenfolge : (e.a.reihenfolge ?? 0));

/** Ordner in ihrer Reihenfolge, darunter „Ohne Ordner“; darin Markierungen und Lesezeichen in der gemeinsamen Ordnung. */
export function ordnerGruppen(ordner: LesezeichenOrdner[], lesezeichen: Lesezeichen[], markierungen: Anmerkung[]): OrdnerGruppe[] {
  const alle: OrdnerEintrag[] = [
    ...markierungen.map((a) => ({ art: "markierung" as const, a })),
    ...lesezeichen.map((z) => ({ art: "lesezeichen" as const, z })),
  ];
  // Stabil sortieren: Gleiche Plätze (ältere Markierungen ohne Ordnung) bleiben in Lesereihenfolge.
  const sortiert = alle.map((e, i) => [e, i] as const).sort((x, y) => eintragPlatz(x[0]) - eintragPlatz(y[0]) || x[1] - y[1]).map((x) => x[0]);
  const gruppen: OrdnerGruppe[] = ordner.map((o) => ({ id: o.id, name: o.name, eintraege: [] }));
  const ohne: OrdnerGruppe = { id: null, name: "Ohne Ordner", eintraege: [] };
  for (const e of sortiert) (gruppen.find((g) => g.id === eintragOrdner(e)) ?? ohne).eintraege.push(e);
  return [...gruppen, ohne];
}

/** Eintrag ``key`` in Ordner ``ziel`` legen, vor den Eintrag ``vor`` (null: ans Ende des Ordners). */
export function verschiebeEintrag(gruppen: OrdnerGruppe[], key: string, ziel: number | null, vor: string | null): OrdnerGruppe[] {
  const e = gruppen.flatMap((g) => g.eintraege).find((x) => schluessel(x) === key);
  if (!e || key === vor) return gruppen;
  const neu: OrdnerEintrag = e.art === "lesezeichen" ? { art: e.art, z: { ...e.z, ordner_id: ziel } } : { art: e.art, a: { ...e.a, ordner_id: ziel } };
  return gruppen.map((g) => {
    const rest = g.eintraege.filter((x) => schluessel(x) !== key);
    if (g.id !== ziel) return { ...g, eintraege: rest };
    const stelle = vor == null ? -1 : rest.findIndex((x) => schluessel(x) === vor);
    rest.splice(stelle < 0 ? rest.length : stelle, 0, neu);
    return { ...g, eintraege: rest };
  });
}

/** Ordner ``id`` vor den Ordner ``vor`` schieben (null: ans Ende der Ordner, vor „Ohne Ordner“). */
export function verschiebeOrdner<G extends { id: number | null }>(gruppen: G[], id: number, vor: number | null): G[] {
  const g = gruppen.find((x) => x.id === id);
  if (!g || id === vor) return gruppen;
  const rest = gruppen.filter((x) => x.id !== id);
  const stelle = vor == null ? rest.findIndex((x) => x.id === null) : rest.findIndex((x) => x.id === vor);
  rest.splice(stelle < 0 ? rest.length : stelle, 0, g);
  return rest;
}

/** Was der Kern zum Speichern einer neuen Ordnung braucht. */
export function ordnung(gruppen: OrdnerGruppe[]) {
  return gruppen.map((g) => ({ id: g.id, eintraege: g.eintraege.map((e) => ({ art: e.art, id: eintragId(e) })) }));
}

/** Nur die sichtbaren Einträge in der Ordnung der Ordner, für Export und Druck; leere Ordner fallen weg. */
export function sichtbareOrdnung(gruppen: OrdnerGruppe[], sichtbar: (e: OrdnerEintrag) => boolean) {
  return ordnung(gruppen.map((g) => ({ ...g, eintraege: g.eintraege.filter(sichtbar) })).filter((g) => g.eintraege.length > 0));
}

export type OrdnerAnsichtArt = "markierungen" | "lesezeichen" | "alle";

/** In Worten, was ausgewählt ist, für den Kopf des Ausdrucks; null = alles. */
export function auswahlText(ansicht: OrdnerAnsichtArt, f: AnmerkFilter, bedeutungen: Bedeutungen): string | null {
  const teile: string[] = [];
  if (ansicht === "markierungen") teile.push("nur Markierungen und Kommentare");
  if (ansicht === "lesezeichen") teile.push("nur Lesezeichen");
  if (ansicht !== "lesezeichen") {
    if (f.farben.length > 0) teile.push(`Bedeutung ${FARBEN.filter((x) => f.farben.includes(x)).map((x) => bedeutungen[x]).join(", ")}`);
    if (f.nurKommentar) teile.push("nur mit Kommentar");
    if (f.suche.trim()) teile.push(`Suche „${f.suche.trim()}“`);
  }
  return teile.length ? teile.join("; ") : null;
}

// --- Bildlaufleiste --------------------------------------------------------------------------------------------------

export interface Marke {
  /** Lage im Dokument, 0 (oben) bis 1 (unten). */
  lage: number;
  /** Farbe einer Markierung oder "lesezeichen". */
  art: string;
  /** Wohin ein Klick springt (Pixel im Bildlaufbereich). */
  ziel: number;
  titel: string;
}

/** Marken, die näher als ``abstand`` (Anteil) beieinander liegen und dieselbe Art haben, zusammenfassen. */
export function verdichteMarken(marken: Marke[], abstand = 0.004): Marke[] {
  const sortiert = [...marken].sort((a, b) => a.lage - b.lage);
  const ergebnis: Marke[] = [];
  for (const m of sortiert) {
    const nah = ergebnis.find((x) => x.art === m.art && Math.abs(x.lage - m.lage) < abstand);
    if (!nah) ergebnis.push(m);
  }
  return ergebnis;
}
