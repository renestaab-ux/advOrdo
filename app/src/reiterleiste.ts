/**
 * Aufteilung einer Reiterleiste, wenn nicht alle Reiter in eine Zeile passen: Die vorderen Reiter bleiben stehen,
 * der Rest kommt in das Menü „Mehr“. Der gewählte Reiter bleibt immer sichtbar; liegt er hinten, rückt er an
 * die letzte sichtbare Stelle. Die Reihenfolge der Reiter bleibt in beiden Teilen erhalten.
 *
 * @param breiten Breite jedes Reiters in Pixeln, in der Reihenfolge der Leiste
 * @param platz verfügbare Breite der Zeile
 * @param mehrBreite Breite des Knopfs „Mehr“
 * @param aktiv Stelle des gewählten Reiters (−1, wenn keiner der Leiste gewählt ist)
 * @returns Stellen der sichtbaren Reiter und der Reiter im Menü
 */
export function reiterAufteilen(
  breiten: number[],
  platz: number,
  mehrBreite: number,
  aktiv: number,
): { sichtbar: number[]; mehr: number[] } {
  const alle = breiten.map((_, i) => i);
  const summe = (stellen: number[]) => stellen.reduce((s, i) => s + breiten[i], 0);
  if (summe(alle) <= platz) return { sichtbar: alle, mehr: [] };

  const rest = platz - mehrBreite;
  const sichtbar: number[] = [];
  // Platz für den gewählten Reiter freihalten, damit er nie im Menü verschwindet.
  let belegt = aktiv >= 0 ? breiten[aktiv] : 0;
  for (const i of alle) {
    if (i === aktiv) continue;
    if (belegt + breiten[i] > rest) break;
    sichtbar.push(i);
    belegt += breiten[i];
  }
  if (aktiv >= 0) {
    sichtbar.push(aktiv);
    sichtbar.sort((a, b) => a - b);
  }
  // Mindestens ein Reiter bleibt stehen, auch wenn die Zeile sehr schmal ist.
  if (sichtbar.length === 0) sichtbar.push(0);
  const gesehen = new Set(sichtbar);
  return { sichtbar, mehr: alle.filter((i) => !gesehen.has(i)) };
}

/** Nächster Menüeintrag für Pfeil hoch/runter, Pos1 und Ende; null bei anderen Tasten. Läuft am Ende herum. */
export function menueZiel(taste: string, jetzt: number, anzahl: number): number | null {
  if (anzahl === 0) return null;
  if (taste === "ArrowDown") return (jetzt + 1) % anzahl;
  if (taste === "ArrowUp") return (jetzt - 1 + anzahl) % anzahl;
  if (taste === "Home") return 0;
  if (taste === "End") return anzahl - 1;
  return null;
}
