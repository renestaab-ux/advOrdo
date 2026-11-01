import { useCallback, useEffect, useState } from "react";
import Akten, { Reiter } from "./Akten";
import EigeneDaten from "./EigeneDaten";
import Einstellungen, { EinstellungsReiter } from "./Einstellungen";
import Gesetze from "./Gesetze";
import Kalender from "./Kalender";
import Rechtsprechung from "./Rechtsprechung";
import Beteiligte from "./Beteiligte";
import Start, { StartZiel } from "./Start";
import Suche from "./Suche";
import Toolbox from "./Toolbox";
import Zeichen, { SymbolName } from "./Symbole";
import { invoke } from "@tauri-apps/api/core";
import { gemerkt, merke } from "./merken";
import { useErinnerungen } from "./erinnerungen";
import { useLaufenderTimer } from "./zeitTimer";
import TimerHinweise from "./TimerHinweise";
import Hintergrund from "./Hintergrund";
import { KiAn } from "./kiSchalter";
import { bereichAusTaste } from "./barrierefrei";
import {
  KiModus,
  Marke,
  UmgebungsListe,
  aktiveUmgebung,
  istDesktop,
  kern,
  kiModusName,
  mitDruckbild,
  uhrText,
  zeitGeaendert,
} from "./kern";
import jurabox from "./bilder/jurabox-64.png";

type Bereich = "start" | "eigene" | "toolbox" | "akten" | "kalender" | "beteiligte" | "suche" | "rechtsprechung" | "gesetze" | "einstellungen";

// Vergleich und Analyse sind Reiter in der geöffneten Akte; die Toolbox und Eigene Daten erreicht man über Start,
// die Rechtsquellen (Verzeichnisse der Rechtsprechung) über die Einstellungen.
const BEREICHE: { id: Bereich; titel: string; symbol: SymbolName }[] = [
  { id: "start", titel: "Start", symbol: "start" },
  { id: "akten", titel: "Akten", symbol: "akten" },
  { id: "kalender", titel: "Kalender", symbol: "fristen" },
  { id: "beteiligte", titel: "Beteiligte", symbol: "beteiligte" },
  { id: "suche", titel: "Suche", symbol: "suche" },
  { id: "rechtsprechung", titel: "Rechtsprechung", symbol: "rechtsprechung" },
  { id: "gesetze", titel: "Gesetze", symbol: "gesetze" },
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
  // Kanzlei- bzw. Firmenlogo und Kurzbezeichnung; gehören zur Umgebung. Neu geladen bei jedem Bereichswechsel,
  // damit ein in „Eigene Daten“ geänderter Name gleich auf der Startseite steht.
  const [marke, setMarke] = useState<Marke | null>(null);
  useEffect(() => {
    if (istDesktop) void kern<Marke>("marke.lesen").then(mitDruckbild).then(setMarke, () => setMarke(null));
  }, [stand, bereich]);
  // Mitteilungen des Systems bei Vorfrist, Ablauf und Terminen, solange die App läuft.
  useErinnerungen(umgebungen ? umgebungen.aktiv : undefined);
  // Laufender Timer der Zeiterfassung: immer sichtbar in der Leiste, damit er nicht vergessen wird.
  const timer = useLaufenderTimer(umgebungen?.aktiv);
  // „Akte anlegen“ (Startbildschirm oder „+ Neue Akte“): eigene Seite für den Anlegeprozess.
  const [anlegen, setAnlegen] = useState(false);
  const [reiterWunsch, setReiterWunsch] = useState<{ reiter: Reiter } | null>(null);
  // Gewählter Reiter in den Einstellungen; Hinweise in der App führen direkt zum passenden Thema.
  const [einstellungsReiter, setEinstellungsReiter] = useState<EinstellungsReiter>("allgemeines");

  function zuEinstellungen(reiter?: EinstellungsReiter) {
    if (reiter) setEinstellungsReiter(reiter);
    setBereich("einstellungen");
  }

  // Leiste aufrufen wie ein Klick darauf; auch für die Tastenkürzel Alt + 1 … 8.
  function bereichWaehlen(b: Bereich) {
    // „Akten“ in der Leiste führt immer zur Übersicht, auch aus einer geöffneten Akte.
    if (b === "akten") {
      setAkteId(null);
      setAnlegen(false);
    }
    setBereich(b);
  }
  useEffect(() => {
    function taste(e: KeyboardEvent) {
      const i = bereichAusTaste(e, BEREICHE.length);
      if (i == null) return;
      e.preventDefault();
      bereichWaehlen(BEREICHE[i].id);
      // Danach liest der Bildschirmleser die neue Seite ab ihrem Anfang.
      requestAnimationFrame(() => document.getElementById("inhalt")?.focus());
    }
    window.addEventListener("keydown", taste);
    return () => window.removeEventListener("keydown", taste);
  }, []);

  function einklappen() {
    setEingeklappt(!eingeklappt);
    merke(EINGEKLAPPT_SCHLUESSEL, !eingeklappt);
  }

  function oeffneAkte(id: number | null, reiter?: Reiter) {
    setAnlegen(false);
    setAkteId(id);
    setReiterWunsch(reiter ? { reiter } : null);
    setBereich("akten");
  }

  async function starte(ziel: StartZiel) {
    if (ziel === "anlegen") {
      oeffneAkte(null);
      setAnlegen(true);
    } else if (ziel === "akten") {
      oeffneAkte(null);
    } else if (ziel === "kalender") {
      setBereich("kalender");
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
      <a className="zum-inhalt" href="#inhalt" onClick={(e) => {
        e.preventDefault();
        document.getElementById("inhalt")?.focus();
      }}>
        Zum Inhalt springen
      </a>
      <nav className="navigation" aria-label="Bereiche">
        {/* Auf der Startseite stehen Logo und Name groß im Kopfband; die Leiste zeigt dort nur JuraBox. */}
        {bereich === "start" ? (
          <div className="marke" title="JuraBox">
            <img className="marke-zeichen" src={jurabox} alt="" aria-hidden />
            <span className="nav-text">JuraBox</span>
          </div>
        ) : (
          <div className={marke?.logo ? "marke mit-logo" : "marke"} title={marke?.kurzbezeichnung || "JuraBox"}>
            <img className="marke-zeichen" src={marke?.logo ?? jurabox} alt="" aria-hidden />
            <span className="nav-text">{marke?.kurzbezeichnung || "JuraBox"}</span>
          </div>
        )}
        {BEREICHE.map((b, i) => (
          <button
            key={b.id}
            className={b.id === bereich ? "nav-eintrag aktiv" : "nav-eintrag"}
            aria-current={b.id === bereich ? "page" : undefined}
            aria-keyshortcuts={`Alt+${i + 1}`}
            onClick={() => bereichWaehlen(b.id)}
            title={`${b.titel} (Alt + ${i + 1})`}
          >
            <Zeichen name={b.symbol} />
            <span className="nav-text">{b.titel}</span>
          </button>
        ))}
        <div className="nav-fuss">
          {timer.laufend && (
            <div className="zeit-leiste">
              <button
                className="zeit-leiste-akte"
                onClick={() => oeffneAkte(timer.laufend!.akte_id, "zeiten")}
                title={`Timer läuft: ${timer.laufend.akte}${timer.laufend.taetigkeit ? ` · ${timer.laufend.taetigkeit}` : ""} (${timer.laufend.bearbeiter}). Zur Zeiterfassung der Akte.`}
              >
                <span className="zeit-leiste-symbol">
                  <Zeichen name="zeiten" groesse={eingeklappt ? 26 : 20} />
                </span>
                <span className="nav-text zeit-leiste-text">
                  <strong className="zeit-leiste-uhr">{uhrText(timer.sekunden)}</strong>
                  <span className="zeit-leiste-name">{timer.laufend.akte}</span>
                </span>
              </button>
              <button
                className="zeit-leiste-stopp"
                title="Timer anhalten"
                aria-label="Timer anhalten"
                onClick={() => void kern("zeit.stoppen").then(zeitGeaendert, () => undefined)}
              >
                ■
              </button>
            </div>
          )}
          {modus?.aus ? (
            <button
              className="modus aus"
              onClick={() => zuEinstellungen("ki")}
              title="KI-Modus: Nicht aktiv. Die KI ist ausgeschaltet; die App fragt kein Sprachmodell. Einschalten unter „Einstellungen → Lokales Sprachmodell“."
            >
              <span className="modus-punkt" aria-hidden />
              <span className="nav-text">KI-Modus: {kiModusName(modus)}</span>
            </button>
          ) : modus?.aktiv === "extern" ? (
            <button
              className="modus extern"
              onClick={() => zuEinstellungen("extern")}
              title="Analyse und Chat senden Fragen und Dokumenttexte an diesen Anbieter. Umstellen unter „Einstellungen“."
            >
              <span className="modus-punkt" aria-hidden />
              <span className="nav-text">KI-Modus: {kiModusName(modus)}</span>
            </button>
          ) : (
            <div
              className="modus"
              title={
                modus?.ort === "netzwerk"
                  ? "KI-Modus: Lokales Netzwerk. Das Sprachmodell läuft auf einem anderen Rechner im eigenen Netzwerk; Dokumentinhalte verlassen das eigene Netz nicht."
                  : "KI-Modus: Eigener Rechner. Das Sprachmodell läuft auf diesem Gerät; Dokumentinhalte verlassen es nicht."
              }
            >
              <span className="modus-punkt" aria-hidden />
              <span className="nav-text">KI-Modus: {kiModusName(modus)}</span>
            </div>
          )}
          {umgebung && (
            <button
              className="umgebung-anzeige"
              onClick={() => zuEinstellungen("umgebungen")}
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
      <TimerHinweise onAkte={(id) => oeffneAkte(id, "zeiten")} />
      <Hintergrund />
      <KiAn.Provider value={!modus?.aus}>
        <main
          id="inhalt"
          tabIndex={-1}
          className={bereich === "akten" && (akteId != null || anlegen) ? "inhalt ohne-rand" : "inhalt"}
          key={stand}
        >
          {bereich === "start" && (
            <Start
              onWahl={(z) => void starte(z)}
              onAkte={oeffneAkte}
              modus={modus}
              umgebung={umgebung?.name ?? null}
              marke={marke}
              onNachrichten={() => zuEinstellungen("nachrichten")}
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
              reiterWunsch={reiterWunsch}
              onEinstellungen={(r) => zuEinstellungen(r ?? "ki")}
              onEigeneDaten={() => setBereich("eigene")}
            />
          )}
          {bereich === "kalender" && <Kalender onAkte={(id) => oeffneAkte(id, "fristen")} />}
          {bereich === "suche" && <Suche onAkte={oeffneAkte} />}
          {bereich === "beteiligte" && <Beteiligte onAkte={oeffneAkte} />}
          {bereich === "rechtsprechung" && (
            <Rechtsprechung onAkte={(id) => oeffneAkte(id, "rechtsprechung")} onQuellen={() => zuEinstellungen("rechtsquellen")} />
          )}
          {bereich === "gesetze" && <Gesetze />}
          {bereich === "einstellungen" && (
            <Einstellungen
              reiter={einstellungsReiter}
              onReiter={setEinstellungsReiter}
              marke={marke}
              onMarke={(m) => void mitDruckbild(m).then(setMarke)}
              onGeaendert={ladeModus}
              umgebungen={umgebungen}
              onUmgebungen={umgebungGeaendert}
              onEigeneDaten={() => setBereich("eigene")}
              onAkten={() => setBereich("akten")}
            />
          )}
        </main>
      </KiAn.Provider>
    </div>
  );
}
