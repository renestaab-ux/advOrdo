import { useCallback, useEffect, useState } from "react";
import Akten from "./Akten";
import EigeneDaten from "./EigeneDaten";
import Einstellungen from "./Einstellungen";
import Gesetze from "./Gesetze";
import Rechtsprechung from "./Rechtsprechung";
import Beteiligte from "./Beteiligte";
import Start, { StartZiel } from "./Start";
import Suche from "./Suche";
import Toolbox from "./Toolbox";
import Zeichen, { SymbolName } from "./Symbole";
import { invoke } from "@tauri-apps/api/core";
import { gemerkt, merke } from "./merken";
import { KiModus, UmgebungsListe, aktiveUmgebung, istDesktop, kern } from "./kern";

type Bereich = "start" | "eigene" | "toolbox" | "akten" | "beteiligte" | "suche" | "gesetze" | "rechtsprechung" | "einstellungen";

// Vergleich und Analyse sind Reiter in der geöffneten Akte; die Toolbox und Eigene Daten erreicht man über Start.
const BEREICHE: { id: Bereich; titel: string; symbol: SymbolName }[] = [
  { id: "start", titel: "Start", symbol: "start" },
  { id: "akten", titel: "Akten", symbol: "akten" },
  { id: "beteiligte", titel: "Beteiligte", symbol: "beteiligte" },
  { id: "suche", titel: "Suche", symbol: "suche" },
  { id: "gesetze", titel: "Gesetze", symbol: "gesetze" },
  { id: "rechtsprechung", titel: "Rechtsprechung", symbol: "rechtsprechung" },
  { id: "einstellungen", titel: "Einstellungen", symbol: "einstellungen" },
];

const EINGEKLAPPT_SCHLUESSEL = "navigation.eingeklappt";

export default function App() {
  const [bereich, setBereich] = useState<Bereich>("start");
  // Die geöffnete Akte; null zeigt die Aktenübersicht.
  const [akteId, setAkteId] = useState<number | null>(null);
  const [eingeklappt, setEingeklappt] = useState(() => gemerkt(EINGEKLAPPT_SCHLUESSEL));
  // Ob Dokumentinhalte das Gerät verlassen (externe KI gewählt); immer sichtbar in der Navigation.
  const [modus, setModus] = useState<KiModus | null>(null);
  const ladeModus = useCallback(() => {
    if (istDesktop) void kern<KiModus>("ki.modus").then(setModus, () => setModus(null));
  }, []);
  useEffect(ladeModus, [ladeModus]);
  // Arbeitsumgebung (eigene Akten je Identität); nach einem Wechsel werden alle Bereiche neu geladen.
  const [umgebungen, setUmgebungen] = useState<UmgebungsListe | null>(null);
  const [stand, setStand] = useState(0);
  useEffect(() => {
    if (istDesktop) void kern<UmgebungsListe>("umgebungen.liste").then(setUmgebungen, () => setUmgebungen(null));
  }, []);
  function umgebungGeaendert(liste: UmgebungsListe, gewechselt: boolean) {
    setUmgebungen(liste);
    if (gewechselt) {
      setAkteId(null);
      setStand((n) => n + 1);
    }
  }
  const umgebung = aktiveUmgebung(umgebungen);
  // „Akte anlegen“ (Startbildschirm oder „+ Neue Akte“): eigene Seite für den Anlegeprozess.
  const [anlegen, setAnlegen] = useState(false);

  function einklappen() {
    setEingeklappt(!eingeklappt);
    merke(EINGEKLAPPT_SCHLUESSEL, !eingeklappt);
  }

  function oeffneAkte(id: number | null) {
    setAnlegen(false);
    setAkteId(id);
    setBereich("akten");
  }

  async function starte(ziel: StartZiel) {
    if (ziel === "anlegen") {
      oeffneAkte(null);
      setAnlegen(true);
    } else if (ziel === "akten") {
      oeffneAkte(null);
    } else if (ziel === "eigene") {
      setBereich("eigene");
    } else if (ziel === "einstellungen") {
      setBereich("einstellungen");
    } else if (ziel === "toolbox") {
      // Die Toolbox hat ein eigenes Fenster; im Browser (ohne Desktop-App) erscheint sie hier.
      if (istDesktop) await invoke("toolbox_oeffnen");
      else setBereich("toolbox");
    }
  }

  return (
    <div className={eingeklappt ? "rahmen eingeklappt" : "rahmen"}>
      <nav className="navigation" aria-label="Bereiche">
        <div className="marke">
          <span className="marke-zeichen" aria-hidden>
            §
          </span>
          <span className="nav-text">JuraBox</span>
        </div>
        {BEREICHE.map((b) => (
          <button
            key={b.id}
            className={b.id === bereich ? "nav-eintrag aktiv" : "nav-eintrag"}
            aria-current={b.id === bereich ? "page" : undefined}
            onClick={() => {
              // „Akten“ in der Leiste führt immer zur Übersicht, auch aus einer geöffneten Akte.
              if (b.id === "akten") {
                setAkteId(null);
                setAnlegen(false);
              }
              setBereich(b.id);
            }}
            title={eingeklappt ? b.titel : undefined}
          >
            <Zeichen name={b.symbol} />
            <span className="nav-text">{b.titel}</span>
          </button>
        ))}
        <div className="nav-fuss">
          {modus?.aktiv === "extern" ? (
            <button
              className="modus extern"
              onClick={() => setBereich("einstellungen")}
              title="Analyse und Chat senden Fragen und Dokumenttexte an diesen Anbieter. Umstellen unter „Einstellungen“."
            >
              <span className="modus-punkt" aria-hidden />
              <span className="nav-text">Modus: Externer Anbieter ({modus.titel})</span>
            </button>
          ) : (
            <div className="modus" title="Modus: nur lokal. Dokumentinhalte verlassen dieses Gerät nicht.">
              <span className="modus-punkt" aria-hidden />
              <span className="nav-text">Modus: nur lokal</span>
            </div>
          )}
          {umgebung && (
            <button
              className="umgebung-anzeige"
              onClick={() => setBereich("einstellungen")}
              title={`Umgebung: ${umgebung.name}. Akten und Analysen gehören zu dieser Umgebung. Wechseln unter „Einstellungen“.`}
            >
              <span className="nav-text">
                Umgebung: <strong>{umgebung.name}</strong>
              </span>
            </button>
          )}
          <button
            className="nav-eintrag einklappen"
            onClick={einklappen}
            title={eingeklappt ? "Leiste ausklappen" : "Leiste einklappen"}
            aria-label={eingeklappt ? "Leiste ausklappen" : "Leiste einklappen"}
          >
            <Zeichen name={eingeklappt ? "ausklappen" : "einklappen"} />
            <span className="nav-text">Einklappen</span>
          </button>
        </div>
      </nav>
      <main className={bereich === "akten" && (akteId != null || anlegen) ? "inhalt ohne-rand" : "inhalt"} key={stand}>
        {bereich === "start" && (
          <Start
            onWahl={(z) => void starte(z)}
            onAkte={oeffneAkte}
            modus={modus}
            umgebung={umgebung?.name ?? null}
          />
        )}
        {bereich === "toolbox" && <Toolbox />}
        {bereich === "eigene" && <EigeneDaten onZurueck={() => setBereich("start")} />}
        {bereich === "akten" && (
          <Akten
            anlegen={anlegen}
            onAnlegen={setAnlegen}
            akteId={akteId}
            setAkteId={setAkteId}
            onEinstellungen={() => setBereich("einstellungen")}
          />
        )}
        {bereich === "suche" && <Suche akteId={akteId} setAkteId={setAkteId} onAkte={oeffneAkte} />}
        {bereich === "beteiligte" && <Beteiligte onAkte={oeffneAkte} />}
        {bereich === "gesetze" && <Gesetze />}
        {bereich === "rechtsprechung" && <Rechtsprechung onAkte={() => setBereich("akten")} />}
        {bereich === "einstellungen" && (
          <Einstellungen
            onGeaendert={ladeModus}
            umgebungen={umgebungen}
            onUmgebungen={umgebungGeaendert}
            onEigeneDaten={() => setBereich("eigene")}
          />
        )}
      </main>
    </div>
  );
}
