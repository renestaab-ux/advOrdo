// ---------------------------------------------------------------- Sortieren von Tabellen

export interface Sortierung {
  spalte: string;
  absteigend: boolean;
}

type SortWert = string | number | null | undefined;

/**
 * Sortiert nach einer Spalte; Texte deutsch und mit Zahlen in natürlicher Reihenfolge („2 O“ vor „10 O“).
 * Leere Werte stehen immer am Ende, auch bei absteigender Sortierung.
 */
export function sortiert<T>(liste: T[], s: Sortierung, werte: Record<string, (x: T) => SortWert>): T[] {
  const wert = werte[s.spalte];
  if (!wert) return liste;
  const leer = (v: SortWert) => v == null || v === "";
  return [...liste].sort((a, b) => {
    const x = wert(a);
    const y = wert(b);
    if (leer(x) || leer(y)) return leer(x) === leer(y) ? 0 : leer(x) ? 1 : -1;
    const c =
      typeof x === "number" && typeof y === "number"
        ? x - y
        : String(x).localeCompare(String(y), "de", { numeric: true, sensitivity: "base" });
    return s.absteigend ? -c : c;
  });
}

/** Sortierschlüssel für eigene Aktenzeichen Nummer/Jahr („102/26 RS“): erst das Jahr, dann die Nummer. */
export function aktenzeichenSchluessel(az: string | null | undefined): string | null {
  if (!az) return null;
  const m = /^(\d+)\s*\/\s*(\d{2,4})/.exec(az.trim());
  return m ? `${m[2].slice(-2)}-${m[1].padStart(6, "0")}` : az;
}
