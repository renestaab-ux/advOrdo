import { useEffect, useState } from "react";
import Dialog from "./Dialog";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import {
  ZeitLaufend,
  akteTitel,
  heuteIso,
  istDesktop,
  kern,
  timerSeitText,
  uhrText,
  zeitGeaendert,
} from "./kern";
import type { LaufenderTermin } from "./kern";
import { arbeitsfensterOeffnen } from "./terminLaufend";
import { Bearbeitung, offeneBearbeitungen } from "./ungespeichert";

type Frage =
  | { art: "start" | "beenden"; laufend: ZeitLaufend }
  | { art: "ungespeichert"; offen: Bearbeitung[] }
  | { art: "termin-start" | "termin-beenden"; termine: LaufenderTermin[] };

async function laufendeTermine(): Promise<LaufenderTermin[]> {
  try {
    return await kern<LaufenderTermin[]>("sitzung.laufende");
  } catch {
    // Kern nicht erreichbar: nicht am Beenden hindern.
    return [];
  }
}

/** Zuletzt beim Beenden: läuft ein Termin im Arbeitsfenster, darauf hinweisen; sonst beenden. */
async function terminPruefen(setFrage: (f: Frage) => void) {
  const termine = await laufendeTermine();
  if (termine.length) setFrage({ art: "termin-beenden", termine });
  else await invoke("app_beenden");
}

/** Nach den offenen Bearbeitungen: läuft ein Timer, fragen; sonst weiter mit den Terminen. */
async function timerPruefen(setFrage: (f: Frage) => void) {
  let l: ZeitLaufend | null = null;
  try {
    l = await kern<ZeitLaufend | null>("zeit.laufend");
  } catch {
    // Kern nicht erreichbar: nicht am Beenden hindern.
  }
  if (l) setFrage({ art: "beenden", laufend: l });
  else await terminPruefen(setFrage);
}

/**
 * Rückfragen beim Beenden und Hinweise zum laufenden Timer der Zeiterfassung, nur im Hauptfenster:
 * - beim Beenden mit offener Bearbeitung (ungespeicherte Eingaben, siehe ungespeichert.ts): speichern, verwerfen
 *   oder zurück zur Bearbeitung,
 * - beim Start der App, wenn noch ein Timer läuft (er zählt auch bei geschlossener App weiter),
 * - beim Beenden (Fenster schließen, macOS „advOrdo beenden“): anhalten, weiterlaufen lassen oder abbrechen,
 * - ebenso für einen laufenden Termin im Arbeitsfenster (beim Start und beim Beenden; beendet wird er dort).
 *   Rust hält das Beenden an und meldet „beenden-angefragt“ (src-tauri/src/beenden.rs).
 */
export default function TimerHinweise({
  onAkte,
}: {
  onAkte: (akteId: number) => void;
}) {
  const [frage, setFrage] = useState<Frage | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (!istDesktop) return;
    void kern<ZeitLaufend | null>("zeit.laufend").then(
      (l) => l && setFrage((f) => f ?? { art: "start", laufend: l }),
      () => undefined,
    );
    void laufendeTermine().then(
      (t) =>
        t.length && setFrage((f) => f ?? { art: "termin-start", termine: t }),
    );
    let aus: (() => void) | undefined;
    let beendet = false;
    void getCurrentWebviewWindow()
      .listen("beenden-angefragt", async () => {
        const offen = offeneBearbeitungen();
        if (offen.length) setFrage({ art: "ungespeichert", offen });
        else await timerPruefen(setFrage);
      })
      .then((f) => (beendet ? f() : (aus = f)));
    return () => {
      beendet = true;
      aus?.();
    };
  }, []);

  if (!frage) return null;

  function zurueck() {
    setFrage(null);
    void invoke("beenden_abgebrochen");
  }

  if (frage.art === "ungespeichert") {
    const { offen } = frage;
    const speicherbar = offen.every((b) => b.speichern);
    const liste = offen.map((b) => b.was).join(", ");
    return (
      <div className="timer-hinweis-hintergrund">
        <Dialog
          className="rueckfrage timer-hinweis"
          rolle="alertdialog"
          label="Nicht gespeichert"
          onSchliessen={zurueck}
        >
          <strong>
            {offen.length === 1 ? "Eine Eingabe ist" : "Eingaben sind"} noch
            nicht gespeichert
          </strong>
          <p>
            Offen: {liste}. Beim Beenden gehen diese Eingaben verloren.
            {!speicherbar &&
              " Zum Speichern geh zurück und schließe die Bearbeitung mit „Speichern“ ab."}
          </p>
          <div className="aktionen">
            <button onClick={zurueck} autoFocus>
              Zurück zur Bearbeitung
            </button>
            {speicherbar && (
              <button
                className="zweitrangig"
                onClick={async () => {
                  setFehler(null);
                  for (const b of offen) {
                    if (!(await b.speichern!())) {
                      setFehler(
                        `${b.was}: Speichern ist gescheitert. Die App bleibt offen.`,
                      );
                      return;
                    }
                  }
                  await timerPruefen(setFrage);
                }}
              >
                Speichern und beenden
              </button>
            )}
            <button
              className="zweitrangig"
              onClick={() => void timerPruefen(setFrage)}
            >
              Verwerfen und beenden
            </button>
          </div>
          {fehler && (
            <p className="fehler" role="alert">
              {fehler}
            </p>
          )}
        </Dialog>
      </div>
    );
  }

  if (frage.art === "termin-start" || frage.art === "termin-beenden") {
    const beim = frage.art === "termin-beenden";
    const t = frage.termine[0];
    const akte = akteTitel({ name: t.akte, aktenzeichen: t.aktenzeichen });
    const seit = timerSeitText(t.beginn, heuteIso());
    const weitere =
      frage.termine.length > 1
        ? ` Außerdem ${frage.termine.length - 1 === 1 ? "läuft ein weiterer Termin" : `laufen ${frage.termine.length - 1} weitere Termine`}.`
        : "";
    const abbrechen = () => {
      setFrage(null);
      if (beim) void invoke("beenden_abgebrochen");
    };
    return (
      <div className="timer-hinweis-hintergrund">
        <Dialog
          className="rueckfrage timer-hinweis"
          rolle="alertdialog"
          label="Termin läuft noch"
          onSchliessen={abbrechen}
        >
          <strong>
            {beim
              ? `Der Termin in der Akte „${akte}“ läuft noch`
              : `Der Termin in der Akte „${akte}“ läuft seit ${seit}`}
          </strong>
          <p>
            {t.titel}
            {t.wahrgenommen_von ? `, ${t.wahrgenommen_von}` : ""}
            {beim ? `, seit ${seit}` : ""}, bisher {uhrText(t.sekunden)}.
            {weitere}{" "}
            {beim
              ? "Läuft er weiter, zählt die Zeit auch bei geschlossener App weiter. Beenden kannst du ihn im Arbeitsfenster mit „Termin beenden“; dort übernimmst du Protokoll, Zeit und Fristen."
              : "Er lief weiter, während die App geschlossen war. Beende ihn im Arbeitsfenster mit „Termin beenden“; die Minuten kannst du dort anpassen."}
          </p>
          <div className="aktionen">
            <button
              onClick={() => {
                abbrechen();
                void arbeitsfensterOeffnen(t.akte_id, t.akte).catch((x) =>
                  setFehler(String(x)),
                );
              }}
              autoFocus
            >
              Arbeitsfenster öffnen
            </button>
            {beim ? (
              <>
                <button
                  className="zweitrangig"
                  onClick={() => void invoke("app_beenden")}
                >
                  Weiterlaufen lassen und App schließen
                </button>
                <button className="zweitrangig" onClick={abbrechen}>
                  Abbrechen
                </button>
              </>
            ) : (
              <button className="zweitrangig" onClick={abbrechen}>
                Weiterlaufen lassen
              </button>
            )}
          </div>
          {fehler && (
            <p className="fehler" role="alert">
              {fehler}
            </p>
          )}
        </Dialog>
      </div>
    );
  }

  if (!("laufend" in frage)) return null;
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
            {taetigkeit}, seit {seit}, bisher {uhrText(l.sekunden)}. Soll die
            Zeiterfassung beendet werden? Läuft sie weiter, zählt sie auch bei
            geschlossener App weiter.
          </p>
          <div className="aktionen">
            <button
              onClick={() =>
                void anhalten().then((ok) => {
                  if (ok) void terminPruefen(setFrage);
                })
              }
              autoFocus
            >
              Zeiterfassung beenden und App schließen
            </button>
            <button
              className="zweitrangig"
              onClick={() => void terminPruefen(setFrage)}
            >
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
          {fehler && (
            <p className="fehler" role="alert">
              {fehler}
            </p>
          )}
        </Dialog>
      </div>
    );

  return (
    <div className="timer-hinweis-hintergrund">
      <Dialog
        className="rueckfrage timer-hinweis"
        rolle="alertdialog"
        label="Zeiterfassung läuft"
        onSchliessen={() => setFrage(null)}
      >
        <strong>
          Die Zeiterfassung in der Akte „{akte}“ läuft seit {seit}
        </strong>
        <p>
          {l.bearbeiter}
          {taetigkeit}, bisher {uhrText(l.sekunden)}. Sie lief weiter, während
          die App geschlossen war.
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
          <button
            className="zweitrangig"
            onClick={() => void anhalten().then((ok) => ok && setFrage(null))}
          >
            Jetzt beenden
          </button>
          <button className="zweitrangig" onClick={() => setFrage(null)}>
            Weiterlaufen lassen
          </button>
        </div>
        {fehler && (
          <p className="fehler" role="alert">
            {fehler}
          </p>
        )}
      </Dialog>
    </div>
  );
}
