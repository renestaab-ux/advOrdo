import { useCallback, useEffect, useState } from "react";
import { EigeneUrteile, RechtsprechungStand, istDesktop, kern, rechtsprechungUmfang, zeitpunkt } from "./kern";

/** Bereich „Rechtsprechung“: die Quellen, gegen die Urteilszitate geprüft und aus denen Volltexte genommen werden. */
export default function Rechtsprechung({ onAkte }: { onAkte: () => void }) {
  const [stand, setStand] = useState<RechtsprechungStand | null>(null);
  const [eigene, setEigene] = useState<EigeneUrteile | null>(null);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const ausfuehren = useCallback(async <T,>(was: string, f: () => Promise<T>) => {
    setLaeuft(was);
    setFehler(null);
    try {
      return await f();
    } catch (e) {
      setFehler(String(e));
      return undefined;
    } finally {
      setLaeuft(null);
    }
  }, []);

  useEffect(() => {
    if (!istDesktop) return;
    void ausfuehren("Lade Quellen …", async () => {
      setStand(await kern<RechtsprechungStand | null>("rechtsprechung.stand"));
      setEigene(await kern<EigeneUrteile>("rechtsprechung.eigene"));
    });
  }, [ausfuehren]);

  async function laden() {
    await ausfuehren("Lade das Verzeichnis der Bundesrechtsprechung von rechtsprechung-im-internet.de …", async () => {
      setStand(await kern<RechtsprechungStand>("rechtsprechung.laden"));
    });
  }

  const manuell = eigene?.quellen.filter((q) => q.quelle === "manuell") ?? [];
  const selbst = manuell.reduce((n, q) => n + q.anzahl, 0);
  const geladen = (eigene?.quellen ?? []).filter((q) => q.quelle === "rii").reduce((n, q) => n + q.anzahl, 0);

  return (
    <div className="rechtsprechung">
      <header className="kopf">
        <h1>Rechtsprechung</h1>
      </header>
      <p className="erklaerung">
        Urteilszitate in Akten prüft die App gegen diese Quellen. Geladen werden nur öffentliche Verzeichnisse und
        Entscheidungen; aus der Akte verlässt nichts das Gerät.
      </p>
      {laeuft && <p className="status">{laeuft}</p>}
      {fehler && <p className="fehler">{fehler}</p>}

      <section className="karte">
        <h2>Rechtsprechung im Internet (Bund)</h2>
        <p className="fundort">rechtsprechung-im-internet.de · BVerfG, BGH, BVerwG, BFH, BAG, BSG, BPatG, GmS-OGB</p>
        {stand ? (
          <p>
            Verzeichnis: {stand.eintraege.toLocaleString("de-DE")} Entscheidungen ({rechtsprechungUmfang(stand)}), geladen{" "}
            {zeitpunkt(stand.abgerufen_am)}.
          </p>
        ) : (
          <p className="leer">
            Noch nicht geladen. Das Verzeichnis listet die Entscheidungen der Bundesgerichte mit Gericht, Datum und
            Aktenzeichen. Damit prüft die App, ob eine zitierte Entscheidung so existiert.
          </p>
        )}
        <button className={stand ? "zweitrangig" : undefined} onClick={laden} disabled={!!laeuft}>
          {stand ? "Verzeichnis aktualisieren" : "Verzeichnis laden"}
        </button>
        {geladen > 0 && (
          <p>
            {geladen} {geladen === 1 ? "Volltext" : "Volltexte"} zu Akten geladen.
          </p>
        )}
        <p className="grenze">
          Das Verzeichnis enthält keine Texte. Die Volltexte der zitierten Entscheidungen lädt man je Akte unter
          „Rechtsprechung der Akte“ („Volltexte laden“).
        </p>
      </section>

      <section className="karte">
        <h2>Eigene Dateien</h2>
        <p className="fundort">z. B. PDF-Ausdrucke aus juris, beck-online oder openJur</p>
        {selbst > 0 ? (
          <p>
            {selbst} {selbst === 1 ? "Entscheidung" : "Entscheidungen"} selbst ergänzt
            {manuell.length > 0 && <> ({manuell.map((q) => `${q.herkunft ?? "ohne Angabe"}: ${q.anzahl}`).join(", ")})</>}.
          </p>
        ) : (
          <p className="leer">Noch keine Entscheidungen selbst ergänzt.</p>
        )}
        <p>
          Ergänzt wird in der Akte unter „Rechtsprechung der Akte“: Bei jedem Zitat lässt sich eine eigene Datei als
          Volltext ablegen, besonders wenn die Entscheidung nicht im Verzeichnis steht (Instanzgerichte, EuGH, ältere
          Entscheidungen).
        </p>
        <button className="zweitrangig" onClick={onAkte}>
          Zur Akte
        </button>
      </section>

      <section className="karte">
        <h2>Weitere Quellen (geplant)</h2>
        <ul>
          <li>Rechtsprechung der Länder (Landesportale, z. B. Bürgerservice Bayern, NRWE)</li>
          <li>EuGH und EuG (EUR-Lex, curia.europa.eu)</li>
        </ul>
      </section>
    </div>
  );
}
