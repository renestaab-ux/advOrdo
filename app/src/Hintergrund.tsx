import { useEffect, useState } from "react";
import { HintergrundAuftrag, beobachteHintergrund, hintergrundAbbrechen, kiBeobachten } from "./kern";

/**
 * Warteanzeige für lange Befehle (Gesetze laden, Volltexte laden, Zitate online prüfen …) und KI-Aufgaben
 * (Analyse, Chat, Vorschläge für Details), unten rechts im Fenster.
 * Sie bleibt sichtbar, wenn man währenddessen in einen anderen Bereich wechselt, und bietet „Abbrechen“.
 */
export default function Hintergrund() {
  const [liste, setListe] = useState<HintergrundAuftrag[]>([]);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    const aus = beobachteHintergrund(setListe);
    void kiBeobachten(); // eine KI-Aufgabe kann schon laufen (Fenster neu geladen)
    return aus;
  }, []);

  // Für Bildschirmleser nur Beginn und Ende ansagen, nicht jede Sekunde; der Bereich steht immer da, damit Ansagen ankommen.
  const ansage = liste.length ? `Läuft im Hintergrund: ${liste.map((a) => a.titel).join(", ")}` : "";
  return (
    <>
      <div className="nur-vorlesen" role="status">
        {ansage}
      </div>
      {liste.length > 0 && (
    <div className="hintergrund-anzeige" aria-label="Aufträge im Hintergrund" role="region">
      {liste.map((a) => {
        const bricht = a.text.startsWith("Wird ") && a.text.includes("abgebrochen");
        return (
          <div key={`${a.ki ? "ki" : "kern"}-${a.auftrag_id}`} className="hintergrund-auftrag">
            <span className="hintergrund-drehen" aria-hidden="true" />
            <div className="hintergrund-text">
              <strong>{a.titel}</strong>
              <span className="leise">
                {a.text !== `${a.titel} …` ? `${a.text} · ` : ""}
                {a.sekunden} s
              </span>
            </div>
            <button
              className="zweitrangig"
              disabled={bricht}
              onClick={() => {
                setFehler(null);
                hintergrundAbbrechen(a.auftrag_id, a.ki).catch((x) => setFehler(String(x)));
              }}
            >
              {bricht ? "Bricht ab …" : "Abbrechen"}
            </button>
          </div>
        );
      })}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
    </div>
      )}
    </>
  );
}
