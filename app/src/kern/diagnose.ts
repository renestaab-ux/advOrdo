
// ---------------------------------------------------------------- Diagnose

export type DiagnoseStand = "ok" | "warnung" | "fehler" | "aus";

export interface DiagnosePruefung {
  id: string;
  gruppe: string;
  gruppe_titel: string;
  titel: string;
}

export interface DiagnoseErgebnis {
  id: string;
  gruppe: string;
  titel: string;
  stand: DiagnoseStand;
  meldung: string;
  details: string[];
  hilfe: string | null;
  dauer_ms: number;
}

/** Klartext-Bericht zum Weitergeben; enthält nur die Prüfergebnisse, keine Dokumentinhalte. */
export function diagnoseBericht(
  pruefungen: DiagnosePruefung[],
  ergebnisse: Record<string, DiagnoseErgebnis>,
  zeitpunkt: Date,
): string {
  const zeichen: Record<DiagnoseStand, string> = { ok: "OK", warnung: "HINWEIS", fehler: "FEHLER", aus: "AUS" };
  const zeilen = [`JuraBox-Diagnose vom ${zeitpunkt.toLocaleString("de-DE")}`];
  let gruppe = "";
  for (const p of pruefungen) {
    if (p.gruppe_titel !== gruppe) {
      gruppe = p.gruppe_titel;
      zeilen.push("", `## ${gruppe}`);
    }
    const e = ergebnisse[p.id];
    if (!e) {
      zeilen.push(`- ${p.titel}: nicht geprüft`);
      continue;
    }
    zeilen.push(`- [${zeichen[e.stand]}] ${p.titel}: ${e.meldung}`);
    for (const d of e.details) zeilen.push(`    ${d}`);
    if (e.hilfe) zeilen.push(`    Was tun: ${e.hilfe}`);
  }
  return zeilen.join("\n");
}
