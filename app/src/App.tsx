import { useState } from "react";
import Akte from "./Akte";
import Analyse from "./Analyse";
import Einstellungen from "./Einstellungen";
import Gesetze from "./Gesetze";
import Rechtsprechung from "./Rechtsprechung";
import Suche from "./Suche";
import Vergleich from "./Vergleich";

type Bereich = "akte" | "suche" | "vergleich" | "analyse" | "gesetze" | "rechtsprechung" | "einstellungen";

const BEREICHE: { id: Bereich; titel: string; bald?: boolean }[] = [
  { id: "akte", titel: "Akte" },
  { id: "suche", titel: "Suche" },
  { id: "vergleich", titel: "Vergleich" },
  { id: "analyse", titel: "Analyse" },
  { id: "gesetze", titel: "Gesetze" },
  { id: "rechtsprechung", titel: "Rechtsprechung" },
  { id: "einstellungen", titel: "Einstellungen" },
];

export default function App() {
  const [bereich, setBereich] = useState<Bereich>("akte");
  // Die gewählte Akte gilt für Akte, Vergleich und Analyse gemeinsam.
  const [akteId, setAkteId] = useState<number | null>(null);

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
      <main className="inhalt">
        {bereich === "akte" && <Akte akteId={akteId} setAkteId={setAkteId} onVergleich={() => setBereich("vergleich")} />}
        {bereich === "suche" && (
          <Suche
            akteId={akteId}
            onAkte={(id) => {
              setAkteId(id);
              setBereich("akte");
            }}
          />
        )}
        {bereich === "vergleich" && <Vergleich akteId={akteId} setAkteId={setAkteId} />}
        {bereich === "analyse" && (
          <Analyse akteId={akteId} setAkteId={setAkteId} onEinstellungen={() => setBereich("einstellungen")} />
        )}
        {bereich === "gesetze" && <Gesetze />}
        {bereich === "rechtsprechung" && <Rechtsprechung onAkte={() => setBereich("akte")} />}
        {bereich === "einstellungen" && <Einstellungen />}
      </main>
    </div>
  );
}
