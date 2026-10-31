/**
 * Zuständigkeitssuche nach Gerichtsbarkeit: welche Partei die Anschrift für die Suche liefert und welcher Hinweis
 * zur örtlichen Zuständigkeit dazu passt. Die Fundstellen nennen die Norm, nach der sich der Ort richtet.
 */

export type Gerichtsbarkeit = "zivil" | "arbeit" | "verwaltung" | "sozial" | "mahn";

export interface GerichtssucheEinstellungen {
  aktiv: Gerichtsbarkeit[];
  gerichtsbarkeiten: { id: Gerichtsbarkeit; name: string }[];
}

/** Wessen Anschrift die Suche vorbelegt: beim Sozialgericht und im Mahnverfahren die eigene Seite, sonst der Gegner. */
export function vorbelegungAus(ang: Gerichtsbarkeit): "mandant" | "gegner" {
  return ang === "sozial" || ang === "mahn" ? "mandant" : "gegner";
}

export const ZUSTAENDIGKEIT_HINWEIS: Record<Gerichtsbarkeit, string> = {
  zivil:
    "Allgemeiner Gerichtsstand (Wohnsitz oder Sitz des Beklagten, §§ 12, 13, 17 ZPO). Ob Amts- oder Landgericht " +
    "zuständig ist, richtet sich nach dem Streitwert; das bitte selbst prüfen.",
  arbeit:
    "Allgemeiner Gerichtsstand des Beklagten; daneben auch das Arbeitsgericht des gewöhnlichen Arbeitsorts " +
    "(§ 48 Abs. 1a ArbGG). Für den Arbeitsort bitte dessen Postleitzahl eingeben.",
  verwaltung:
    "Örtlich zuständig ist je nach Fall das Verwaltungsgericht am Ort der Sache (z. B. Baugrundstück), am Sitz der " +
    "Behörde oder am Wohnsitz (§ 52 VwGO); bitte die passende Anschrift eingeben.",
  sozial: "Zuständig ist in der Regel das Sozialgericht am Wohnsitz oder Sitz des Klägers (§ 57 Abs. 1 SGG).",
  mahn:
    "Zuständig ist das Mahngericht am allgemeinen Gerichtsstand des Antragstellers (§ 689 Abs. 2 ZPO); die Länder " +
    "haben die Mahnverfahren bei zentralen Mahngerichten gebündelt (§ 689 Abs. 3 ZPO).",
};

/** Erste Wahl beim Öffnen: im Mahnverfahren das Mahngericht, sonst die erste eingeschaltete Gerichtsbarkeit. */
export function startGerichtsbarkeit(aktiv: Gerichtsbarkeit[], verfahrensArt?: string): Gerichtsbarkeit | null {
  if (verfahrensArt === "mahnverfahren" && aktiv.includes("mahn")) return "mahn";
  return aktiv[0] ?? null;
}
