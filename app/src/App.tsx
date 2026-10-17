import { useCallback, useEffect, useState } from "react";
import Akte from "./Akte";
import Analyse from "./Analyse";
import Einstellungen from "./Einstellungen";
import Gesetze from "./Gesetze";
import Rechtsprechung from "./Rechtsprechung";
import Start, { StartZiel } from "./Start";
import Suche from "./Suche";
import Toolbox from "./Toolbox";
import Vergleich from "./Vergleich";
import { invoke } from "@tauri-apps/api/core";
import { KiModus, istDesktop, kern } from "./kern";

type Bereich = "start" | "toolbox" | "akte" | "suche" | "vergleich" | "analyse" | "gesetze" | "rechtsprechung" | "einstellungen";

const BEREICHE: { id: Bereich; titel: string; bald?: boolean }[] = [
  { id: "start", titel: "Start" },
  { id: "akte", titel: "Akte" },
  { id: "suche", titel: "Suche" },
  { id: "vergleich", titel: "Vergleich" },
  { id: "analyse", titel: "Analyse" },
  { id: "gesetze", titel: "Gesetze" },
  { id: "rechtsprechung", titel: "Rechtsprechung" },
  { id: "einstellungen", titel: "Einstellungen" },
];

export default function App() {
  const [bereich, setBereich] = useState<Bereich>("start");
  // Die gewählte Akte gilt für Akte, Vergleich und Analyse gemeinsam.
  const [akteId, setAkteId] = useState<number | null>(null);
  // Ob Dokumentinhalte das Gerät verlassen (externe KI gewählt); immer sichtbar in der Navigation.
  const [modus, setModus] = useState<KiModus | null>(null);
  const ladeModus = useCallback(() => {
    if (istDesktop) void kern<KiModus>("ki.modus").then(setModus, () => setModus(null));
  }, []);
  useEffect(ladeModus, [ladeModus]);
  // „Akte anlegen“ vom Startbildschirm: Bereich Akte mit dem Namensfeld im Fokus.
  const [neueAkte, setNeueAkte] = useState(0);

  async function starte(ziel: StartZiel) {
    if (ziel === "anlegen") {
      setNeueAkte((n) => n + 1);
      setBereich("akte");
    } else if (ziel === "akte") {
      setNeueAkte(0);
      setBereich("akte");
    } else if (ziel === "einstellungen") {
      setBereich("einstellungen");
    } else if (ziel === "toolbox") {
      // Die Toolbox hat ein eigenes Fenster; im Browser (ohne Desktop-App) erscheint sie hier.
      if (istDesktop) await invoke("toolbox_oeffnen");
      else setBereich("toolbox");
    }
  }

  return (
    <div className="rahmen">
      <nav className="navigation" aria-label="Bereiche">
        <div className="marke">JuraBox</div>
        {BEREICHE.filter((b) => b.id !== "toolbox").map((b) => (
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
        {modus?.aktiv === "extern" ? (
          <button
            className="modus extern"
            onClick={() => setBereich("einstellungen")}
            title="Analyse und Chat senden Fragen und Dokumenttexte an diesen Anbieter. Umstellen unter „Einstellungen“."
          >
            Modus: Externer Anbieter ({modus.titel})
          </button>
        ) : (
          <div className="modus" title="Dokumentinhalte verlassen dieses Gerät nicht.">
            Modus: nur lokal
          </div>
        )}
      </nav>
      <main className="inhalt">
        {bereich === "start" && <Start onWahl={(z) => void starte(z)} />}
        {bereich === "toolbox" && <Toolbox />}
        {bereich === "akte" && (
          <Akte
            neueAkte={neueAkte}
            akteId={akteId}
            setAkteId={setAkteId}
            onVergleich={() => setBereich("vergleich")}
            onEinstellungen={() => setBereich("einstellungen")}
          />
        )}
        {bereich === "suche" && (
          <Suche
            akteId={akteId}
            setAkteId={setAkteId}
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
        {bereich === "einstellungen" && <Einstellungen onGeaendert={ladeModus} />}
      </main>
    </div>
  );
}
