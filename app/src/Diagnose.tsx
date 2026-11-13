import { useEffect, useState } from "react";
import { isPermissionGranted } from "@tauri-apps/plugin-notification";
import { DiagnosePruefung, DiagnoseStand, DiagnoseErgebnis, diagnoseBericht, istDesktop, kern } from "./kern";
import KiLeistungstest from "./KiLeistungstest";
import NetzProtokoll from "./NetzProtokoll";

const STAND_TEXT: Record<DiagnoseStand, string> = { ok: "in Ordnung", warnung: "Hinweis", fehler: "Fehler", aus: "aus" };

// Mitteilungen erlaubt das Betriebssystem der Oberfläche, nicht dem Kern; deshalb prüft sie die Oberfläche selbst.
const MITTEILUNGEN: DiagnosePruefung = {
  id: "mitteilungen",
  gruppe: "programm",
  gruppe_titel: "Programm und Daten",
  titel: "Mitteilungen des Systems (Erinnerungen)",
};

async function mitteilungenPruefen(): Promise<DiagnoseErgebnis> {
  const basis = { id: MITTEILUNGEN.id, gruppe: MITTEILUNGEN.gruppe, titel: MITTEILUNGEN.titel, dauer_ms: 0 };
  if (await isPermissionGranted()) {
    return { ...basis, stand: "ok", meldung: "advOrdo darf Erinnerungen an Fristen anzeigen.", details: [], hilfe: null };
  }
  return {
    ...basis,
    stand: "warnung",
    meldung: "Erinnerungen an Fristen erscheinen nicht, das System erlaubt advOrdo keine Mitteilungen.",
    details: [],
    hilfe:
      "Unter Einstellungen → Akten „Probe-Erinnerung senden“ wählen und die Rückfrage bestätigen. Unter Windows sonst " +
      "Einstellungen → System → Benachrichtigungen, unter macOS Systemeinstellungen → Mitteilungen.",
  };
}

/**
 * Diagnose: prüft Kern, Datenbanken, Archiv, Texterkennung, Programme, Sprachmodelle und die Online-Rechtsquellen
 * einzeln und erklärt, was bei einem Fehler zu tun ist. Erst auf Klick, weil dabei Rechtsquellen angefragt werden.
 */
export default function Diagnose() {
  const [pruefungen, setPruefungen] = useState<DiagnosePruefung[]>([]);
  const [ergebnisse, setErgebnisse] = useState<Record<string, DiagnoseErgebnis>>({});
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [zeitpunkt, setZeitpunkt] = useState<Date | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (!istDesktop) return;
    void kern<DiagnosePruefung[]>("diagnose.liste").then(
      (l) => setPruefungen([...l.filter((p) => p.gruppe === "programm"), MITTEILUNGEN, ...l.filter((p) => p.gruppe !== "programm")]),
      (e) => setFehler(String(e)),
    );
  }, []);

  async function starten() {
    setErgebnisse({});
    setMeldung(null);
    setFehler(null);
    for (const p of pruefungen) {
      setLaeuft(p.id);
      let e: DiagnoseErgebnis;
      try {
        e =
          p.id === MITTEILUNGEN.id
            ? await mitteilungenPruefen()
            : await kern<DiagnoseErgebnis>("diagnose.pruefen", { pruef_id: p.id });
      } catch (x) {
        e = { id: p.id, gruppe: p.gruppe, titel: p.titel, stand: "fehler", meldung: String(x), details: [], hilfe: null, dauer_ms: 0 };
      }
      setErgebnisse((alt) => ({ ...alt, [p.id]: e }));
    }
    setLaeuft(null);
    setZeitpunkt(new Date());
  }

  async function kopieren() {
    const text = diagnoseBericht(pruefungen, ergebnisse, zeitpunkt ?? new Date());
    try {
      await navigator.clipboard.writeText(text);
      setMeldung("Bericht kopiert. Er enthält keine Dokumentinhalte und keine Schlüssel.");
    } catch {
      setFehler("Kopieren war nicht möglich.");
    }
  }

  const fertig = Object.values(ergebnisse);
  const zaehler = (s: DiagnoseStand) => fertig.filter((e) => e.stand === s).length;
  const gruppen = [...new Set(pruefungen.map((p) => p.gruppe))];

  return (
    <div className="diagnose">
      <h2>Diagnose</h2>
      <p className="erklaerung">
        Prüft, ob alle Teile von advOrdo funktionieren: Datenordner, Datenbanken, das Archiv der Rechtsquellen,
        Texterkennung, Programme, die Sprachmodelle und die Rechtsquellen im Internet. Ins Netz gehen nur kurze Abrufe der
        öffentlichen Rechtsquellen und, wenn die externe KI eingebunden ist, die Modellliste des Anbieters. Dokumentinhalte
        werden nicht übertragen. Jede Anfrage steht unten im Protokoll der Online-Anfragen.
      </p>
      <div className="aktionen">
        <button onClick={() => void starten()} disabled={laeuft !== null || pruefungen.length === 0}>
          {laeuft ? "Prüfe …" : fertig.length ? "Erneut prüfen" : "Prüfung starten"}
        </button>
        {fertig.length > 0 && !laeuft && (
          <button className="zweitrangig" onClick={() => void kopieren()}>
            Bericht kopieren
          </button>
        )}
      </div>
      {fertig.length > 0 && !laeuft && (
        <p className={`diagnose-summe stand-${zaehler("fehler") ? "fehler" : zaehler("warnung") ? "warnung" : "ok"}`}>
          {zaehler("fehler") === 0 && zaehler("warnung") === 0
            ? "Alles in Ordnung."
            : `${zaehler("fehler")} Fehler, ${zaehler("warnung")} Hinweise, ${zaehler("ok")} in Ordnung.`}
        </p>
      )}
      {meldung && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}

      {gruppen.map((g) => (
        <section key={g} className="karte">
          <h2>{pruefungen.find((p) => p.gruppe === g)?.gruppe_titel}</h2>
          <ul className="diagnose-liste">
            {pruefungen
              .filter((p) => p.gruppe === g)
              .map((p) => {
                const e = ergebnisse[p.id];
                const stand = e?.stand ?? (laeuft === p.id ? "laeuft" : "offen");
                return (
                  <li key={p.id} className={`diagnose-zeile stand-${stand}`}>
                    <span className="diagnose-marke" aria-hidden />
                    <div>
                      <div className="diagnose-titel">
                        <strong>{p.titel}</strong>
                        <span className="leise klein">
                          {e ? STAND_TEXT[e.stand] : laeuft === p.id ? "wird geprüft …" : "noch nicht geprüft"}
                        </span>
                      </div>
                      {e && <div>{e.meldung}</div>}
                      {e?.hilfe && <div className="diagnose-hilfe">Was tun: {e.hilfe}</div>}
                      {e && e.details.length > 0 && (
                        <ul className="diagnose-details leise klein">
                          {e.details.map((d) => (
                            <li key={d}>{d}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </li>
                );
              })}
          </ul>
        </section>
      ))}

      <KiLeistungstest />

      <NetzProtokoll />
    </div>
  );
}
