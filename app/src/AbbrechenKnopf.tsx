import { useState } from "react";

/**
 * „Abbrechen“ für einen laufenden Auftrag. Nach dem Klick sofort „Bricht ab …“ und gesperrt, bis der Auftrag
 * endet: Der Kern trennt die Verbindung zum Sprachmodell, das dauert meist nur einen Augenblick.
 */
export function AbbrechenKnopf({
  auftrag,
  onAbbrechen,
  klein = false,
}: {
  auftrag: { auftrag_id: number; abbruch?: boolean };
  onAbbrechen: () => unknown;
  klein?: boolean;
}) {
  const [geklickt, setGeklickt] = useState<number | null>(null);
  const bricht = !!auftrag.abbruch || geklickt === auftrag.auftrag_id;
  return (
    <button
      className={klein ? "link klein" : "zweitrangig"}
      disabled={bricht}
      aria-busy={bricht}
      onClick={() => {
        setGeklickt(auftrag.auftrag_id);
        Promise.resolve(onAbbrechen()).catch(() => setGeklickt(null));
      }}
    >
      {bricht ? "Bricht ab …" : "Abbrechen"}
    </button>
  );
}
