import { useEffect } from "react";
import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";
import { gemerkt } from "./merken";
import { Erinnerung, KalenderEintrag, faelligeErinnerungen, istDesktop, kern } from "./kern";

/** Gerätweiter Schalter in den Einstellungen; ohne Eintrag sind die Erinnerungen an. */
export const ERINNERUNGEN_AUS = "erinnerungen.aus";
const GEZEIGT = "erinnerungen.gezeigt";
const ABSTAND_MS = 10 * 60 * 1000;
// Mehr einzelne Meldungen auf einmal (etwa beim Start) werden zu einer zusammengefasst.
const EINZELN_HOECHSTENS = 3;

function gezeigtLesen(): string[] {
  try {
    const liste: unknown = JSON.parse(localStorage.getItem(GEZEIGT) ?? "[]");
    return Array.isArray(liste) ? liste.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function gezeigtMerken(liste: string[]) {
  try {
    localStorage.setItem(GEZEIGT, JSON.stringify(liste.slice(-400)));
  } catch {
    // Ohne Speicher wird nach einem Neustart noch einmal erinnert.
  }
}

/** Fragt beim ersten Mal das Betriebssystem, ob die App Mitteilungen zeigen darf. */
export async function mitteilungenErlaubt(): Promise<boolean> {
  if (await isPermissionGranted()) return true;
  return (await requestPermission()) === "granted";
}

function senden(liste: Erinnerung[]) {
  if (liste.length <= EINZELN_HOECHSTENS) {
    for (const e of liste) sendNotification({ title: e.titel, body: e.text });
    return;
  }
  const zeilen = liste.slice(0, EINZELN_HOECHSTENS).map((e) => e.titel);
  zeilen.push(`… und ${liste.length - EINZELN_HOECHSTENS} weitere, siehe Startseite.`);
  sendNotification({ title: `advOrdo: ${liste.length} Fristen, Termine und Wiedervorlagen`, body: zeilen.join("\n") });
}

export async function testErinnerung() {
  if (!(await mitteilungenErlaubt())) throw new Error("Das Betriebssystem erlaubt advOrdo keine Mitteilungen.");
  sendNotification({ title: "advOrdo: Probe-Erinnerung", body: "So erscheinen Erinnerungen an Fristen und Termine." });
}

/**
 * Erinnert über Mitteilungen des Betriebssystems an Fristen, Termine und Wiedervorlagen der aktiven Umgebung:
 * beim Start und danach alle zehn Minuten, solange die App läuft. Jede Erinnerung erscheint je Stufe nur einmal.
 */
export function useErinnerungen(umgebung: string | undefined) {
  useEffect(() => {
    if (!istDesktop || umgebung === undefined) return;
    let vorbei = false;
    async function pruefen() {
      if (gemerkt(ERINNERUNGEN_AUS)) return;
      const eintraege = await kern<KalenderEintrag[]>("akten.kalender_naechste", { limit: 500 });
      const gezeigt = gezeigtLesen();
      // Die Einträge gehören zur Umgebung; ihre Nummern wiederholen sich in anderen Umgebungen.
      const vorsilbe = `${umgebung}:`;
      const neu = faelligeErinnerungen(eintraege, new Set(gezeigt.filter((s) => s.startsWith(vorsilbe)).map((s) => s.slice(vorsilbe.length))));
      if (vorbei || neu.length === 0 || !(await mitteilungenErlaubt())) return;
      senden(neu);
      gezeigtMerken([...gezeigt, ...neu.map((e) => vorsilbe + e.schluessel)]);
    }
    const einmal = () => void pruefen().catch(() => undefined);
    einmal();
    const uhr = window.setInterval(einmal, ABSTAND_MS);
    return () => {
      vorbei = true;
      window.clearInterval(uhr);
    };
  }, [umgebung]);
}
