import { useCallback, useEffect, useState } from "react";
import {
  EigeneUrteile,
  RechtsprechungQuellen,
  RechtsprechungStand,
  UrteilQuelle,
  istDesktop,
  kern,
  kernImHintergrund,
  rechtsprechungUmfang,
  zeitpunkt,
} from "./kern";

/**
 * Einstellungen, Reiter „Rechtsquellen“: die Quellen, gegen die Urteilszitate geprüft und aus denen Volltexte
 * genommen werden. Gearbeitet wird mit den Entscheidungen in der Akte („Rechtsprechung der Akte“).
 */
export default function Rechtsquellen({ onAkte }: { onAkte: () => void }) {
  const [stand, setStand] = useState<RechtsprechungStand | null>(null);
  const [eigene, setEigene] = useState<EigeneUrteile | null>(null);
  const [quellen, setQuellen] = useState<RechtsprechungQuellen | null>(null);
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
      setQuellen(await kern<RechtsprechungQuellen>("rechtsprechung.quellen"));
    });
  }, [ausfuehren]);

  async function laden() {
    await ausfuehren("Lade das Verzeichnis der Bundesrechtsprechung von rechtsprechung-im-internet.de …", async () => {
      setStand(await kernImHintergrund<RechtsprechungStand>("rechtsprechung.laden"));
    });
  }

  async function neurisSchalten(an: boolean) {
    await ausfuehren("Speichere …", async () => {
      setQuellen(await kern<RechtsprechungQuellen>("rechtsprechung.quellen_setzen", { neuris: an }));
    });
  }

  const manuell = eigene?.quellen.filter((q) => q.quelle === "manuell") ?? [];
  const selbst = manuell.reduce((n, q) => n + q.anzahl, 0);
  const anzahl = (quelle: UrteilQuelle) =>
    (eigene?.quellen ?? []).filter((q) => q.quelle === quelle).reduce((n, q) => n + q.anzahl, 0);
  const geladen = anzahl("rii");

  return (
    <>
      <p className="erklaerung">
        Urteilszitate in Akten prüft die App gegen diese Quellen. Geladen werden nur öffentliche Verzeichnisse und
        Entscheidungen; aus der Akte verlässt nichts das Gerät. Die Gesetze selbst verwaltet der Bereich „Gesetze“.
      </p>
      {laeuft && <p className="status" role="status">{laeuft}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}

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
            {geladen} {geladen === 1 ? "Volltext" : "Volltexte"} geladen und in der Sammlung („Rechtsprechung“).
          </p>
        )}
        <p className="grenze">
          Das Verzeichnis enthält keine Texte. Die Volltexte der zitierten Entscheidungen lädt man je Akte unter
          „Rechtsprechung der Akte“ („Volltexte laden“); weitere Entscheidungen findet man im Bereich „Rechtsprechung“
          unter „Online suchen“.
        </p>
      </section>

      <section className="karte">
        <h2>Bürgerservice BAYERN.RECHT</h2>
        <p className="fundort">gesetze-bayern.de · Entscheidungen bayerischer Gerichte aller Instanzen</p>
        <p>
          Ohne Verzeichnis: Zitate bayerischer Gerichte (z. B. OLG München, LG Traunstein, BayObLG) sucht die App erst,
          wenn man in der Akte unter „Rechtsprechung der Akte“ „Online prüfen“ wählt. Gesendet wird nur das
          Aktenzeichen.
        </p>
        {anzahl("bayern") > 0 && (
          <p>
            {anzahl("bayern")} {anzahl("bayern") === 1 ? "Volltext" : "Volltexte"} geladen und in der Sammlung („Rechtsprechung“).
          </p>
        )}
        <p className="grenze">
          Im Portal stehen nur Entscheidungen, die die Gerichte zur Veröffentlichung bestimmt haben; fehlt eine, heißt das
          nicht, dass es sie nicht gibt. Die redaktionellen Leitsätze stammen von C.H.Beck und sind urheberrechtlich
          geschützt. Abgerufen werden nur einzelne Entscheidungen, nie der ganze Bestand.
        </p>
      </section>

      <section className="karte">
        <h2>NeuRIS – Rechtsinformationsportal des Bundes</h2>
        <p className="fundort">rechtsinformationen.bund.de · Testphase · oberste Bundesgerichte</p>
        <label className="schalter">
          <input
            type="checkbox"
            checked={!!quellen?.neuris}
            disabled={!quellen || !!laeuft}
            onChange={(e) => neurisSchalten(e.target.checked)}
          />{" "}
          NeuRIS-Rechtsprechung nutzen
        </label>
        <p>
          Zweite Quelle für Zitate der Bundesgerichte, die im Verzeichnis von rechtsprechung-im-internet.de fehlen, etwa
          ganz neue Entscheidungen. Geprüft wird wie bei Bayern erst auf „Online prüfen“ in der Akte.
        </p>
        {anzahl("neuris") > 0 && (
          <p>
            {anzahl("neuris")} {anzahl("neuris") === 1 ? "Volltext" : "Volltexte"} geladen und in der Sammlung („Rechtsprechung“).
          </p>
        )}
        <p className="grenze">Testbetrieb, ohne Gewähr: Die Schnittstelle kann sich ändern oder zeitweise fehlen.</p>
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
          Entscheidungen). Ohne Akte geht es im Bereich „Rechtsprechung“ mit „Eigene Datei hinzufügen …“.
        </p>
        <button className="zweitrangig" onClick={onAkte}>
          Zur Akte
        </button>
      </section>

      <section className="karte">
        <h2>Weitere Quellen (geplant)</h2>
        <ul>
          <li>Rechtsprechung weiterer Länder (Landesportale, z. B. NRWE)</li>
          <li>EuGH und EuG (EUR-Lex, curia.europa.eu)</li>
        </ul>
      </section>
    </>
  );
}
