import { useEffect, useRef } from "react";
import { kern, type KiAuftrag } from "./kern";

/**
 * Fragt einen laufenden KI-Auftrag in festem Takt ab, bis er endet oder `auftragId` null wird.
 *
 * `beiStand` bekommt jeden Stand (auch den letzten mit „fertig“, „fehler“ oder „abgebrochen“), `beiFehler`
 * einen Fehler der Abfrage selbst. Beide dürfen sich bei jedem Rendern ändern; es gilt immer die neueste
 * Fassung. Antworten, die nach einem Wechsel des Auftrags oder nach dem Schließen eintreffen, werden verworfen.
 */
export function useAuftrag(
  auftragId: number | null,
  beiStand: (stand: KiAuftrag) => void | Promise<void>,
  beiFehler: (fehler: unknown) => void,
  takt = 1000,
): void {
  const stand = useRef(beiStand);
  const fehler = useRef(beiFehler);
  stand.current = beiStand;
  fehler.current = beiFehler;

  useEffect(() => {
    if (auftragId == null) return;
    let aktiv = true;
    const zeitgeber = window.setInterval(async () => {
      try {
        const a = await kern<KiAuftrag>("ki.auftrag", { auftrag_id: auftragId });
        if (aktiv) await stand.current(a);
      } catch (e) {
        if (aktiv) fehler.current(e);
      }
    }, takt);
    return () => {
      aktiv = false;
      window.clearInterval(zeitgeber);
    };
  }, [auftragId, takt]);
}
