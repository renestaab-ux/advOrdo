import { useState } from "react";
import Gesetze from "./Gesetze";

type Bereich = "akte" | "vergleich" | "gesetze";

const BEREICHE: { id: Bereich; titel: string; bald?: boolean }[] = [
  { id: "akte", titel: "Akte", bald: true },
  { id: "vergleich", titel: "Vergleich", bald: true },
  { id: "gesetze", titel: "Gesetze" },
];

export default function App() {
  const [bereich, setBereich] = useState<Bereich>("gesetze");

  return (
    <div className="rahmen">
      <nav className="navigation" aria-label="Bereiche">
        <div className="marke">Juristischer Datenabgleich</div>
        {BEREICHE.map((b) => (
          <button
            key={b.id}
            className={b.id === bereich ? "nav-eintrag aktiv" : "nav-eintrag"}
            onClick={() => setBereich(b.id)}
            disabled={b.bald}
            title={b.bald ? "Folgt in einem späteren Schritt" : undefined}
          >
            {b.titel}
            {b.bald && <span className="bald">bald</span>}
          </button>
        ))}
        <div className="modus" title="Dokumentinhalte verlassen dieses Gerät nicht.">
          Modus: nur lokal
        </div>
      </nav>
      <main className="inhalt">{bereich === "gesetze" && <Gesetze />}</main>
    </div>
  );
}
