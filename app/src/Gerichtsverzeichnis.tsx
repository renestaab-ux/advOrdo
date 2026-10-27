import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { GerichtsverzeichnisStand, istDesktop, kern, zeitpunkt } from "./kern";

/** Öffnet das Orts- und Gerichtsverzeichnis der Justiz im Browser, für Anschrift und Zuständigkeit. */
export function OrtsverzeichnisKnopf({ onFehler }: { onFehler?: (text: string) => void }) {
  return (
    <button
      type="button"
      className="link"
      title="justiz.de: Anschrift und Zuständigkeit eines Gerichts nach Ort oder Postleitzahl"
      onClick={() => void kern("gerichte.verzeichnis_oeffnen").catch((e) => onFehler?.(String(e)))}
    >
      Orts- und Gerichtsverzeichnis öffnen
    </button>
  );
}

/**
 * Einstellungen: Gerichtsverzeichnis aus der XJustiz-Codeliste GDS.Gerichte. Geladen wird nur auf Klick; danach
 * schlägt das Feld „Gericht“ in den Verfahren alle deutschen Gerichte vor.
 */
export default function Gerichtsverzeichnis() {
  const [stand, setStand] = useState<GerichtsverzeichnisStand | null>(null);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  useEffect(() => {
    if (istDesktop) void kern<GerichtsverzeichnisStand | null>("gerichte.stand").then(setStand, (e) => setFehler(String(e)));
  }, []);

  async function ausfuehren(text: string, f: () => Promise<GerichtsverzeichnisStand | null>) {
    setLaeuft(text);
    setFehler(null);
    setMeldung(null);
    try {
      const s = await f();
      if (!s) return;
      setStand(s);
      setMeldung(s.neu ? "Gerichtsverzeichnis übernommen." : "Das Verzeichnis ist unverändert.");
    } catch (e) {
      setFehler(
        `${String(e)} Falls XRepository nicht erreichbar ist: Die Codeliste „GDS.Gerichte“ auf xrepository.de als ` +
          "genericode-Datei herunterladen und mit „Aus Datei laden“ übernehmen.",
      );
    } finally {
      setLaeuft(null);
    }
  }

  async function ausDatei() {
    const pfad = await open({ title: "Codeliste GDS.Gerichte wählen", filters: [{ name: "XML", extensions: ["xml"] }] });
    if (typeof pfad !== "string") return;
    await ausfuehren("Lese die Datei …", () => kern<GerichtsverzeichnisStand>("gerichte.laden_datei", { pfad }));
  }

  return (
    <section className="karte">
      <h2>Gerichtsverzeichnis</h2>
      <p className="fundort">XRepository · XJustiz-Codeliste GDS.Gerichte · alle Gerichte, Staatsanwaltschaften und Justizbehörden</p>
      {stand ? (
        <p>
          {(stand.arten.gericht ?? 0).toLocaleString("de-DE")} Gerichte
          {stand.version ? ` (Version ${stand.version})` : ""}, geladen {zeitpunkt(stand.abgerufen_am)}. Das Feld
          „Gericht“ in den Verfahren schlägt sie beim Tippen vor.
        </p>
      ) : (
        <p className="leer">
          Noch nicht geladen. Mit dem Verzeichnis schlägt das Feld „Gericht“ in den Verfahren alle deutschen Gerichte
          mit ihrem amtlichen Namen vor. Geladen wird nur die öffentliche Liste; aus den Akten verlässt nichts das Gerät.
        </p>
      )}
      <div className="aktionen">
        <button
          className={stand ? "zweitrangig" : undefined}
          disabled={!!laeuft}
          onClick={() => void ausfuehren("Lade das Gerichtsverzeichnis von xrepository.de …", () => kern("gerichte.laden"))}
        >
          {stand ? "Verzeichnis aktualisieren" : "Verzeichnis laden"}
        </button>
        <button className="zweitrangig" disabled={!!laeuft} onClick={() => void ausDatei()}>
          Aus Datei laden
        </button>
      </div>
      {laeuft && <p className="status">{laeuft}</p>}
      {meldung && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler">{fehler}</p>}
      <p className="grenze">
        Die Codeliste enthält nur die Namen, keine Anschriften und keine Zuständigkeiten. Beides findet man im Orts- und
        Gerichtsverzeichnis der Justiz auf justiz.de: <OrtsverzeichnisKnopf onFehler={setFehler} />
      </p>
    </section>
  );
}
