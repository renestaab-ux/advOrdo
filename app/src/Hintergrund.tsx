import { useEffect, useState } from "react";
import { HintergrundAuftrag, beobachteHintergrund, hintergrundAbbrechen } from "./kern";

/**
 * Warteanzeige für lange Befehle (Gesetze laden, Volltexte laden, Zitate online prüfen …), unten rechts im Fenster.
 * Sie bleibt sichtbar, wenn man währenddessen in einen anderen Bereich wechselt, und bietet „Abbrechen“.
 */
export default function Hintergrund() {
  const [liste, setListe] = useState<HintergrundAuftrag[]>([]);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => beobachteHintergrund(setListe), []);

  if (liste.length === 0) return null;
  return (
    <div className="hintergrund-anzeige" role="status" aria-live="polite">
      {liste.map((a) => {
        const bricht = a.text === "Wird abgebrochen …";
        return (
          <div key={a.auftrag_id} className="hintergrund-auftrag">
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
                hintergrundAbbrechen(a.auftrag_id).catch((x) => setFehler(String(x)));
              }}
            >
              {bricht ? "Bricht ab …" : "Abbrechen"}
            </button>
          </div>
        );
      })}
      {fehler && <p className="fehler">{fehler}</p>}
    </div>
  );
}
