
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
  const zeilen = [`advOrdo-Diagnose vom ${zeitpunkt.toLocaleString("de-DE")}`];
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

// ---------------------------------------------------------------- KI-Leistungstest

export interface KiMesswert {
  titel: string;
  wert: string;
  stand: "ok" | "warnung" | "fehler";
  hinweis: string | null;
}

export interface KiPrueffrage {
  id: string;
  bereich: string;
  frage: string;
  erwartet: string;
  antwort: string;
  richtig: boolean;
  fundstelle: string;
  sekunden: number;
}

export interface KiLeistung {
  anbieter: string;
  modell: string;
  ort: string;
  dauer: number;
  messwerte: KiMesswert[];
  fragen: KiPrueffrage[];
  bereiche: { bereich: string; richtig: number; von: number }[];
  gesamt: { richtig: number; von: number; stand: "ok" | "warnung" | "fehler"; meldung: string };
  stand_fundstellen: string;
}

/** Klartext-Bericht des KI-Leistungstests; enthält nur die festen Testfragen und die Antworten des Modells. */
export function leistungsBericht(l: KiLeistung, zeitpunkt: Date): string {
  const zeichen = { ok: "OK", warnung: "HINWEIS", fehler: "FEHLER" } as const;
  const zeilen = [
    `advOrdo – KI-Leistungstest vom ${zeitpunkt.toLocaleString("de-DE")}`,
    `Modell: ${l.modell || "–"} (${l.anbieter}, ${l.ort}), Dauer ${l.dauer} s`,
    "",
    "## Geschwindigkeit",
  ];
  for (const w of l.messwerte) {
    zeilen.push(`- [${zeichen[w.stand]}] ${w.titel}: ${w.wert}`);
    if (w.hinweis) zeilen.push(`    ${w.hinweis}`);
  }
  zeilen.push("", `## Prüffragen: ${l.gesamt.richtig} von ${l.gesamt.von} richtig`, l.gesamt.meldung);
  for (const b of l.bereiche) zeilen.push(`- ${b.bereich}: ${b.richtig} von ${b.von}`);
  for (const f of l.fragen) {
    zeilen.push("", `[${f.richtig ? "RICHTIG" : "FALSCH"}] ${f.bereich}: ${f.frage}`);
    zeilen.push(`    Antwort: ${f.antwort}`, `    Erwartet: ${f.erwartet}`, `    Fundstelle: ${f.fundstelle}`);
  }
  zeilen.push(
    "",
    "Ein Dutzend Fragen ist eine Stichprobe, kein Benchmark. Ans Modell gingen nur die festen Testtexte, keine Akteninhalte.",
  );
  return zeilen.join("\n");
}
