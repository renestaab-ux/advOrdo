import { useEffect, useState } from "react";
import Dialog from "./Dialog";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import { ZeitLaufend, akteTitel, heuteIso, istDesktop, kern, timerSeitText, uhrText, zeitGeaendert } from "./kern";

type Frage = { art: "start" | "beenden"; laufend: ZeitLaufend };

/**
 * Hinweise zum laufenden Timer der Zeiterfassung, nur im Hauptfenster:
 * - beim Start der App, wenn noch ein Timer läuft (er zählt auch bei geschlossener App weiter),
 * - beim Beenden (Fenster schließen, macOS „advOrdo beenden“): anhalten, weiterlaufen lassen oder abbrechen.
 *   Rust hält das Beenden an und meldet „beenden-angefragt“ (src-tauri/src/beenden.rs).
 */
export default function TimerHinweise({ onAkte }: { onAkte: (akteId: number) => void }) {
  const [frage, setFrage] = useState<Frage | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (!istDesktop) return;
    void kern<ZeitLaufend | null>("zeit.laufend").then(
      (l) => l && setFrage((f) => f ?? { art: "start", laufend: l }),
      () => undefined,
    );
    let aus: (() => void) | undefined;
    let beendet = false;
    void getCurrentWebviewWindow()
      .listen("beenden-angefragt", async () => {
        let l: ZeitLaufend | null = null;
        try {
          l = await kern<ZeitLaufend | null>("zeit.laufend");
        } catch {
          // Kern nicht erreichbar: nicht am Beenden hindern.
        }
        if (l) setFrage({ art: "beenden", laufend: l });
        else await invoke("app_beenden");
      })
      .then((f) => (beendet ? f() : (aus = f)));
    return () => {
      beendet = true;
      aus?.();
    };
  }, []);

  if (!frage) return null;
  const l = frage.laufend;
  const akte = akteTitel({ name: l.akte, aktenzeichen: l.aktenzeichen });
  const seit = l.laeuft_seit ? timerSeitText(l.laeuft_seit, heuteIso()) : "";
  const taetigkeit = l.taetigkeit ? ` („${l.taetigkeit}“)` : "";

  async function anhalten() {
    setFehler(null);
    try {
      await kern("zeit.stoppen");
      zeitGeaendert();
      return true;
    } catch (x) {
      setFehler(String(x));
      return false;
    }
  }

  if (frage.art === "beenden")
    return (
      <div className="timer-hinweis-hintergrund">
        <Dialog
          className="rueckfrage timer-hinweis"
          rolle="alertdialog"
          label="Zeiterfassung läuft noch"
          onSchliessen={() => {
            setFrage(null);
            void invoke("beenden_abgebrochen");
          }}
        >
          <strong>Zeiterfassung in der Akte „{akte}“ läuft noch</strong>
          <p>
            {l.bearbeiter}
            {taetigkeit}, seit {seit}, bisher {uhrText(l.sekunden)}. Soll die Zeiterfassung beendet werden? Läuft
            sie weiter, zählt sie auch bei geschlossener App weiter.
          </p>
          <div className="aktionen">
            <button onClick={() => void anhalten().then((ok) => ok && invoke("app_beenden"))} autoFocus>
              Zeiterfassung beenden und App schließen
            </button>
            <button className="zweitrangig" onClick={() => void invoke("app_beenden")}>
              Weiterlaufen lassen und App schließen
            </button>
            <button
              className="zweitrangig"
              onClick={() => {
                setFrage(null);
                void invoke("beenden_abgebrochen");
              }}
            >
              Abbrechen
            </button>
          </div>
          {fehler && <p className="fehler" role="alert">{fehler}</p>}
        </Dialog>
      </div>
    );

  return (
    <div className="timer-hinweis-hintergrund">
      <Dialog className="rueckfrage timer-hinweis" rolle="alertdialog" label="Zeiterfassung läuft" onSchliessen={() => setFrage(null)}>
        <strong>
          Die Zeiterfassung in der Akte „{akte}“ läuft seit {seit}
        </strong>
        <p>
          {l.bearbeiter}
          {taetigkeit}, bisher {uhrText(l.sekunden)}. Sie lief weiter, während die App geschlossen war.
          {!seit.startsWith("heute") &&
            " Wurde sie versehentlich nicht beendet, halte sie an und korrigiere die Dauer im Reiter „Zeiten“ unter „Bearbeiten“."}
        </p>
        <div className="aktionen">
          <button
            onClick={() => {
              setFrage(null);
              onAkte(l.akte_id);
            }}
            autoFocus
          >
            Zur Zeiterfassung der Akte
          </button>
          <button className="zweitrangig" onClick={() => void anhalten().then((ok) => ok && setFrage(null))}>
            Jetzt beenden
          </button>
          <button className="zweitrangig" onClick={() => setFrage(null)}>
            Weiterlaufen lassen
          </button>
        </div>
        {fehler && <p className="fehler" role="alert">{fehler}</p>}
      </Dialog>
    </div>
  );
}
