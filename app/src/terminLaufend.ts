/**
 * Laufende Termine (Terminmodus des Arbeitsfensters) für das Hauptfenster: Anzeige in der Leiste wie beim Timer der
 * Zeiterfassung und Rückfragen beim Start und Beenden der App. Ein Termin zählt weiter, auch wenn das Arbeitsfenster
 * oder die App geschlossen ist; beendet wird er im Arbeitsfenster mit „Termin beenden“.
 */
import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useFremdeAenderung } from "./aenderungen";
import { gemerkteLage } from "./arbeitsfensterLogik";
import { darstellungLesen, fensterThema } from "./darstellung";
import { istDesktop, kern } from "./kern";
import type { LaufenderTermin } from "./kern";

/** Öffnet das Arbeitsfenster einer Akte oder holt es nach vorn. */
export async function arbeitsfensterOeffnen(
  akteId: number,
  titel: string,
): Promise<void> {
  await invoke("arbeitsfenster_oeffnen", {
    akteId,
    titel,
    thema: fensterThema(darstellungLesen()),
    lage: gemerkteLage(akteId),
  });
}

/** Alle laufenden Termine mit sekundengenauer Laufzeit; neu geladen bei Änderungen aus einem Arbeitsfenster. */
export function useLaufendeTermine(umgebung?: string): {
  termine: LaufenderTermin[];
  sekunden: (t: LaufenderTermin) => number;
} {
  const [termine, setTermine] = useState<LaufenderTermin[]>([]);
  const [geladen, setGeladen] = useState(0);
  const [jetzt, setJetzt] = useState(() => Date.now());

  const neu = useCallback(() => {
    if (!istDesktop) return;
    void kern<LaufenderTermin[]>("sitzung.laufende").then(
      (t) => {
        setTermine(t);
        setGeladen(Date.now());
        setJetzt(Date.now());
      },
      () => setTermine([]),
    );
  }, []);

  useFremdeAenderung(["sitzung"], neu);
  useEffect(() => {
    neu();
    const t = setInterval(neu, 60_000);
    return () => clearInterval(t);
  }, [neu, umgebung]);

  useEffect(() => {
    if (termine.length === 0) return;
    const t = setInterval(() => setJetzt(Date.now()), 1000);
    return () => clearInterval(t);
  }, [termine.length]);

  const sekunden = (t: LaufenderTermin) =>
    t.sekunden + Math.max(0, Math.floor((jetzt - geladen) / 1000));
  return { termine, sekunden };
}
