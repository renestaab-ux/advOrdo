import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { GerichtsverzeichnisStand, datumLang, istDesktop, kern, kernImHintergrund, zeitpunkt } from "./kern";

/** Öffnet das Orts- und Gerichtsverzeichnis der Justiz im Browser, für Anschrift und Zuständigkeit. */
export function OrtsverzeichnisKnopf({ onFehler }: { onFehler?: (text: string) => void }) {
  return (
    <button
      type="button"
      className="link"
      title="Orts- und Gerichtsverzeichnis der Justiz: Anschrift und Zuständigkeit eines Gerichts nach Ort oder Postleitzahl"
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
    await ausfuehren("Lese die Datei …", () => kernImHintergrund<GerichtsverzeichnisStand>("gerichte.laden_datei", { pfad }));
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
          onClick={() => void ausfuehren("Lade das Gerichtsverzeichnis von xrepository.de …", () => kernImHintergrund("gerichte.laden"))}
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
        Gerichtsverzeichnis der Justiz: <OrtsverzeichnisKnopf onFehler={setFehler} />
      </p>
    </section>
  );
}

interface Anschrift {
  zeilen: string[];
  strasse: string;
  postfach: string;
  plz: string;
  ort: string;
}

export interface ZustaendigeStelle {
  name: string;
  hinweis: string;
  art: "gericht" | "staatsanwaltschaft" | "sonstige";
  xjustiz_id: string;
  lieferanschrift: Anschrift | null;
  postanschrift: Anschrift | null;
  telefon: string;
  fax: string;
  internet: string;
  email: string;
  /** Felder für das Beteiligtenverzeichnis (Postanschrift, Telefon, E-Mail, Notiz mit Fax, XJustiz-ID und Quelle). */
  beteiligter: Record<string, string>;
}

interface Zustaendigkeit {
  gesucht: string;
  stellen: ZustaendigeStelle[];
  quelle: string;
  abgerufen_am: string;
}

/**
 * Zuständige Gerichte für Postleitzahl und Ort aus dem Orts- und Gerichtsverzeichnis der Justiz (allgemeiner
 * Gerichtsstand). Gesendet werden nur Postleitzahl und Ort; vorbelegt mit der Anschrift des ersten Gegners.
 */
export function ZustaendigesGericht({
  akteId,
  onUebernehmen,
  onSchliessen,
}: {
  akteId: number;
  onUebernehmen: (stelle: ZustaendigeStelle) => void;
  onSchliessen: () => void;
}) {
  const [plz, setPlz] = useState("");
  const [ort, setOrt] = useState("");
  const [vorbelegt, setVorbelegt] = useState("");
  const [ergebnis, setErgebnis] = useState<Zustaendigkeit | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const a = await kern<{ beteiligte: { rolle: string; name: string; beteiligter_id: number | null }[] }>(
          "akten.stammdaten",
          { akte_id: akteId },
        );
        const gegner = a.beteiligte.find((b) => b.rolle === "gegner" && b.beteiligter_id != null);
        if (!gegner) return;
        const d = (await kern<{ daten: Record<string, string> }>("beteiligte.eintrag", { beteiligter_id: gegner.beteiligter_id }))
          .daten;
        if (d.plz || d.ort) {
          setPlz(d.plz ?? "");
          setOrt(d.ort ?? "");
          setVorbelegt(gegner.name);
        }
      } catch {
        // Ohne Gegneranschrift bleibt das Formular leer.
      }
    })();
  }, [akteId]);

  const bereit = /^\d{5}$/.test(plz.trim()) && ort.trim() !== "";

  // Steht im Formular des Verfahrens, darf also selbst kein <form> sein; Enter startet trotzdem die Suche.
  async function suchen() {
    if (!bereit || laeuft) return;
    setLaeuft(true);
    setFehler(null);
    try {
      setErgebnis(await kern<Zustaendigkeit>("gerichte.zustaendig", { plz: plz.trim(), ort: ort.trim() }));
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  const gerichte = ergebnis?.stellen.filter((s) => s.art === "gericht") ?? [];
  return (
    <div className="zustaendiges-gericht">
      <div
        className="zeile"
        onKeyDown={(ev) => {
          if (ev.key === "Enter") {
            ev.preventDefault();
            void suchen();
          }
        }}
      >
        <label className="feld">
          PLZ
          <input value={plz} onChange={(ev) => setPlz(ev.target.value)} inputMode="numeric" maxLength={5} placeholder="79098" />
        </label>
        <label className="feld">
          Ort
          <input value={ort} onChange={(ev) => setOrt(ev.target.value)} placeholder="Freiburg im Breisgau" />
        </label>
        <button type="button" disabled={laeuft || !bereit} onClick={() => void suchen()}>
          {laeuft ? "Suche läuft …" : "Gerichte suchen"}
        </button>
        <button type="button" className="zweitrangig" onClick={onSchliessen}>
          Schließen
        </button>
      </div>
      <p className="leise klein">
        {vorbelegt && `Vorbelegt mit der Anschrift von ${vorbelegt}. `}
        Allgemeiner Gerichtsstand (Wohnsitz oder Sitz). Ob Amts- oder Landgericht zuständig ist, richtet sich nach dem
        Streitwert; das bitte selbst prüfen. Gesendet werden nur Postleitzahl und Ort.
      </p>
      {fehler && <p className="fehler">{fehler}</p>}
      {ergebnis && gerichte.length === 0 && (
        <p className="hinweis">
          Kein Gericht gefunden. Der Ort muss so geschrieben sein wie im Verzeichnis (etwa „Freiburg im Breisgau“) und
          zur Postleitzahl passen.
        </p>
      )}
      {gerichte.length > 0 && (
        <ul className="zustaendig-liste">
          {gerichte.map((s) => {
            const a = s.postanschrift?.strasse || s.postanschrift?.postfach ? s.postanschrift : s.lieferanschrift;
            return (
              <li key={s.name}>
                <div>
                  <strong>{s.name}</strong>
                  {s.hinweis && <span className="leise"> · {s.hinweis}</span>}
                  <div className="klein">{a?.zeilen.join(", ")}</div>
                  <div className="leise">
                    {[s.telefon && `Tel. ${s.telefon}`, s.fax && `Fax ${s.fax}`, s.xjustiz_id && `XJustiz-ID ${s.xjustiz_id}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
                <button type="button" className="zweitrangig" onClick={() => onUebernehmen(s)}>
                  Übernehmen
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {ergebnis && (
        <p className="leise klein">
          Quelle: Orts- und Gerichtsverzeichnis der Justiz ({ergebnis.gesucht}), abgerufen am {datumLang(ergebnis.abgerufen_am.slice(0, 10))}.
        </p>
      )}
    </div>
  );
}
