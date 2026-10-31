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

/** Lesezeichen ``id`` in Ordner ``ziel`` an Stelle ``index`` legen (ohne Index: ans Ende). */
export function verschiebeLesezeichen(
  gruppen: LesezeichenGruppe[],
  id: number,
  ziel: number | null,
  index?: number,
): LesezeichenGruppe[] {
  const z = gruppen.flatMap((g) => g.eintraege).find((x) => x.id === id);
  if (!z) return gruppen;
  const ohne = gruppen.map((g) => ({ ...g, eintraege: g.eintraege.filter((x) => x.id !== id) }));
  return ohne.map((g) => {
    if (g.id !== ziel) return g;
    const e = [...g.eintraege];
    e.splice(index == null ? e.length : Math.min(index, e.length), 0, { ...z, ordner_id: ziel });
    return { ...g, eintraege: e };
  });
}

/** Ordner ``id`` vor den Ordner ``vor`` schieben (null: ans Ende der Ordner, vor „Ohne Ordner“). */
export function verschiebeOrdner(gruppen: LesezeichenGruppe[], id: number, vor: number | null): LesezeichenGruppe[] {
  const g = gruppen.find((x) => x.id === id);
  if (!g || id === vor) return gruppen;
  const rest = gruppen.filter((x) => x.id !== id);
  const stelle = vor == null ? rest.findIndex((x) => x.id === null) : rest.findIndex((x) => x.id === vor);
  rest.splice(stelle < 0 ? rest.length : stelle, 0, g);
  return rest;
}

/** Was der Kern zum Speichern einer neuen Ordnung braucht. */
export function ordnung(gruppen: LesezeichenGruppe[]) {
  return gruppen.map((g) => ({ id: g.id, lesezeichen: g.eintraege.map((z) => z.id) }));
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
