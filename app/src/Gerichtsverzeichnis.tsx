import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { GerichtsverzeichnisStand, datumLang, istDesktop, kern, kernImHintergrund, zeitpunkt } from "./kern";
import {
  Gerichtsbarkeit,
  GerichtssucheEinstellungen,
  ZUSTAENDIGKEIT_HINWEIS,
  startGerichtsbarkeit,
  vorbelegungAus,
} from "./gerichtssuche";

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
  gerichtsbarkeit: Gerichtsbarkeit;
  stellen: ZustaendigeStelle[];
  quelle: string;
  abgerufen_am: string;
}

type Partei = { name: string; plz: string; ort: string };

/**
 * Zuständige Gerichte für Postleitzahl und Ort aus dem Orts- und Gerichtsverzeichnis der Justiz: ordentliche
 * Gerichte (allgemeiner Gerichtsstand), Arbeits-, Verwaltungs- und Sozialgerichte und das zentrale Mahngericht, je
 * nachdem, welche unter Einstellungen → Akten eingeschaltet sind. Gesendet werden nur Postleitzahl und Ort;
 * vorbelegt mit der Anschrift des Gegners, beim Sozial- und Mahngericht mit der des Mandanten.
 */
export function ZustaendigesGericht({
  akteId,
  verfahrensArt,
  onUebernehmen,
  onSchliessen,
}: {
  akteId: number;
  verfahrensArt?: string;
  onUebernehmen: (stelle: ZustaendigeStelle) => void;
  onSchliessen: () => void;
}) {
  const [plz, setPlz] = useState("");
  const [ort, setOrt] = useState("");
  const [vorbelegt, setVorbelegt] = useState("");
  const [parteien, setParteien] = useState<{ mandant?: Partei; gegner?: Partei }>({});
  const [einstellungen, setEinstellungen] = useState<GerichtssucheEinstellungen | null>(null);
  const [ang, setAng] = useState<Gerichtsbarkeit | null>(null);
  const [ergebnis, setErgebnis] = useState<Zustaendigkeit | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<GerichtssucheEinstellungen>("gerichte.suche_einstellungen").then(
      (e) => {
        setEinstellungen(e);
        setAng(startGerichtsbarkeit(e.aktiv, verfahrensArt));
      },
      // Älterer Kern ohne Einstellung: nur der allgemeine Gerichtsstand, wie bisher.
      () => setAng("zivil"),
    );
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const a = await kern<{ beteiligte: { rolle: string; name: string; beteiligter_id: number | null }[] }>(
          "akten.stammdaten",
          { akte_id: akteId },
        );
        const gefunden: { mandant?: Partei; gegner?: Partei } = {};
        for (const rolle of ["mandant", "gegner"] as const) {
          const b = a.beteiligte.find((x) => x.rolle === rolle && x.beteiligter_id != null);
          if (!b) continue;
          const d = (await kern<{ daten: Record<string, string> }>("beteiligte.eintrag", { beteiligter_id: b.beteiligter_id }))
            .daten;
          if (d.plz || d.ort) gefunden[rolle] = { name: b.name, plz: d.plz ?? "", ort: d.ort ?? "" };
        }
        setParteien(gefunden);
      } catch {
        // Ohne Anschriften der Parteien bleibt das Formular leer.
      }
    })();
  }, [akteId]);

  function uebernimm(p: Partei | undefined) {
    if (!p) return;
    setPlz(p.plz);
    setOrt(p.ort);
    setVorbelegt(p.name);
  }

  // Vorbelegung je Gerichtsbarkeit, solange von Hand nichts anderes eingetragen ist.
  useEffect(() => {
    if (!ang) return;
    const p = parteien[vorbelegungAus(ang)] ?? parteien.gegner ?? parteien.mandant;
    if (!p) return;
    const vorher = [parteien.mandant, parteien.gegner].some((x) => x && x.plz === plz && x.ort === ort);
    if (vorher || (!plz && !ort)) uebernimm(p);
  }, [ang, parteien]);

  const bereit = /^\d{5}$/.test(plz.trim()) && ort.trim() !== "" && ang != null;

  // Steht im Formular des Verfahrens, darf also selbst kein <form> sein; Enter startet trotzdem die Suche.
  async function suchen() {
    if (!bereit || laeuft) return;
    setLaeuft(true);
    setFehler(null);
    try {
      setErgebnis(await kern<Zustaendigkeit>("gerichte.zustaendig", { plz: plz.trim(), ort: ort.trim(), ang }));
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  const aktiv = einstellungen?.gerichtsbarkeiten.filter((g) => einstellungen.aktiv.includes(g.id)) ?? [];
  const gerichte = ergebnis?.gerichtsbarkeit === ang ? ergebnis.stellen.filter((s) => s.art === "gericht") : [];
  const andere = ang ? (vorbelegungAus(ang) === "mandant" ? parteien.gegner : parteien.mandant) : undefined;
  return (
    <div className="zustaendiges-gericht">
      {einstellungen && aktiv.length === 0 && (
        <p className="hinweis">Die Gerichtssuche ist unter Einstellungen → Akten für alle Gerichtsbarkeiten ausgeschaltet.</p>
      )}
      {aktiv.length > 1 && (
        <div className="segment" role="tablist" aria-label="Gerichtsbarkeit">
          {aktiv.map((g) => (
            <button
              key={g.id}
              type="button"
              role="tab"
              aria-selected={ang === g.id}
              className={`segment-knopf${ang === g.id ? " aktiv" : ""}`}
              onClick={() => setAng(g.id)}
            >
              {g.name}
            </button>
          ))}
        </div>
      )}
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
          <input value={plz} onChange={(ev) => setPlz(ev.target.value)} inputMode="numeric" maxLength={5} placeholder="5 Ziffern" />
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
        {andere && andere.name !== vorbelegt && (
          <>
            <button type="button" className="link" onClick={() => uebernimm(andere)}>
              Anschrift von {andere.name} nehmen
            </button>
            {". "}
          </>
        )}
        {ang && ZUSTAENDIGKEIT_HINWEIS[ang]} Gesendet werden nur Postleitzahl und Ort.
      </p>
      {!bereit && (plz.trim() || ort.trim()) && (
        <p className="hinweis">
          {!/^\d{5}$/.test(plz.trim())
            ? "Zum Suchen bitte die fünfstellige Postleitzahl eintragen; das Verzeichnis sucht nicht nach dem Ort allein."
            : "Bitte auch den Ort eintragen."}
        </p>
      )}
      {fehler && <p className="fehler">{fehler}</p>}
      {ergebnis?.gerichtsbarkeit === ang && gerichte.length === 0 && (
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
      {ergebnis?.gerichtsbarkeit === ang && (
        <p className="leise klein">
          Quelle: Orts- und Gerichtsverzeichnis der Justiz ({ergebnis.gesucht}), abgerufen am {datumLang(ergebnis.abgerufen_am.slice(0, 10))}.
        </p>
      )}
    </div>
  );
}

/**
 * Einstellungen → Akten: welche Gerichtsbarkeiten die Suche „Zuständiges Gericht“ im Verfahren anbietet. Sind alle
 * aus, verschwindet die Suche aus dem Verfahren.
 */
export function GerichtssucheKarte() {
  const [e, setE] = useState<GerichtssucheEinstellungen | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (istDesktop) void kern<GerichtssucheEinstellungen>("gerichte.suche_einstellungen").then(setE, (x) => setFehler(String(x)));
  }, []);

  async function umschalten(id: Gerichtsbarkeit) {
    if (!e) return;
    const aktiv = e.aktiv.includes(id) ? e.aktiv.filter((a) => a !== id) : [...e.aktiv, id];
    setFehler(null);
    try {
      setE(await kern<GerichtssucheEinstellungen>("gerichte.suche_einstellungen_setzen", { aktiv }));
    } catch (x) {
      setFehler(String(x));
    }
  }

  if (!e) return fehler ? <p className="fehler">{fehler}</p> : null;
  return (
    <section className="karte">
      <h2>Zuständiges Gericht suchen</h2>
      <p className="fundort">Orts- und Gerichtsverzeichnis der Justiz (justizadressen.nrw.de)</p>
      <p className="erklaerung">
        Im Verfahren sucht „Zuständiges Gericht suchen“ nach Postleitzahl und Ort das zuständige Gericht mit Anschrift.
        Hier lässt sich wählen, für welche Gerichtsbarkeiten die Suche angeboten wird. Arbeits-, Verwaltungs- und
        Sozialgerichte erscheinen mit ihren Rechtsmittelgerichten.
      </p>
      {e.gerichtsbarkeiten.map((g) => (
        <label key={g.id} className="schalter-zeile">
          <input type="checkbox" checked={e.aktiv.includes(g.id)} onChange={() => void umschalten(g.id)} />
          {g.name}
          {g.id === "zivil" && " (Amts-, Land- und Oberlandesgericht)"}
          {g.id === "mahn" && " (zentrales Mahngericht des Landes)"}
        </label>
      ))}
      {e.aktiv.length === 0 && <p className="hinweis">Alle aus: Die Suche erscheint im Verfahren nicht mehr.</p>}
      {fehler && <p className="fehler">{fehler}</p>}
    </section>
  );
}
