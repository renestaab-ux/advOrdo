import { FormEvent, useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  Beleg,
  Fassung,
  GesetzEintrag,
  GesetzesPaket,
  ImportErgebnis,
  Norm,
  Voreinstellung,
  Treffer,
  formatiereBuilddate,
  istDesktop,
  paketGruppen,
  istZitat,
  kern,
  kernImHintergrund,
} from "./kern";

export default function Gesetze() {
  const [gesetze, setGesetze] = useState<GesetzEintrag[]>([]);
  const [verfuegbar, setVerfuegbar] = useState<Voreinstellung[]>([]);
  const [alle, setAlle] = useState<Voreinstellung[]>([]);
  const [pakete, setPakete] = useState<GesetzesPaket[]>([]);
  const [eingabe, setEingabe] = useState("");
  const [weiteres, setWeiteres] = useState("");
  const [treffer, setTreffer] = useState<Treffer[] | null>(null);
  const [beleg, setBeleg] = useState<Beleg | null>(null);
  const [norm, setNorm] = useState<Norm | null>(null);
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

  const ladeListe = useCallback(async () => {
    const [liste, verf, voll, pak] = await Promise.all([
      kern<GesetzEintrag[]>("gesetze.liste"),
      kern<Voreinstellung[]>("gesetze.verfuegbar"),
      kern<Voreinstellung[]>("gesetze.voreinstellung"),
      kern<GesetzesPaket[]>("gesetze.pakete"),
    ]);
    setGesetze(liste);
    setVerfuegbar(verf);
    setAlle(voll);
    setPakete(pak);
  }, []);

  useEffect(() => {
    if (istDesktop) void ausfuehren("Lade Wissensbasis …", ladeListe);
  }, [ausfuehren, ladeListe]);

  async function importieren(abk: string[]) {
    await ausfuehren(`Lade ${abk.join(", ")} …`, async () => {
      const ergebnisse = await kernImHintergrund<ImportErgebnis[]>("gesetze.importieren", { gesetze: abk });
      await ladeListe();
      const fehler = ergebnisse.filter((e) => e.fehler).map((e) => `${e.abk}: ${e.fehler}`);
      if (fehler.length > 0) throw new Error(fehler.join("\n"));
    });
  }

  async function paketSchalten(paket: string, aktiv: boolean) {
    await ausfuehren(aktiv ? "Schalte das Paket ein …" : "Schalte das Paket aus …", async () => {
      await kern<GesetzesPaket[]>("gesetze.paket_schalten", { paket, aktiv });
      await ladeListe();
    });
  }

  async function dateiImportieren() {
    const pfad = await open({
      title: "Gesetz aus Datei importieren",
      filters: [{ name: "Gesetzestext (XML, ZIP, gespeicherte Webseite)", extensions: ["xml", "zip", "html", "htm"] }],
    });
    if (typeof pfad !== "string") return;
    await ausfuehren("Lese die Datei …", async () => {
      await kernImHintergrund<ImportErgebnis>("gesetze.importieren_datei", { pfad });
      await ladeListe();
    });
  }

  async function weiteresLaden(e: FormEvent) {
    e.preventDefault();
    const abk = weiteres.trim();
    if (!abk) return;
    await importieren([abk]);
    setWeiteres("");
  }

  async function suchen(e: FormEvent) {
    e.preventDefault();
    if (!eingabe.trim()) return;
    setNorm(null);
    if (istZitat(eingabe)) {
      setTreffer(null);
      const b = await ausfuehren("Löse Zitat auf …", () => kern<Beleg>("zitat.aufloesen", { zitat: eingabe }));
      setBeleg(b ?? null);
    } else {
      setBeleg(null);
      const t = await ausfuehren("Suche …", () => kern<Treffer[]>("gesetze.suche", { text: eingabe }));
      setTreffer(t ?? null);
    }
  }

  async function oeffne(abk: string, bezeichnung: string) {
    const nummer = bezeichnung.replace(/^(§§?|Art\.?|Artikel|Erwägungsgrund)\s*/, "");
    const typ = bezeichnung.startsWith("Art")
      ? "artikel"
      : bezeichnung.startsWith("Erwägungsgrund")
        ? "erwaegungsgrund"
        : "paragraph";
    const n = await ausfuehren("Lade Norm …", () => kern<Norm | null>("gesetze.norm", { gesetz: abk, nummer, typ }));
    setNorm(n ?? null);
  }

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Der Analysekern steht nur in der Desktop-App zur Verfügung:{" "}
        <code>npm run tauri dev</code>
      </section>
    );
  }

  const geladen = new Set(gesetze.map((g) => g.abk.toUpperCase()));
  const fehlend = verfuegbar.filter((v) => !geladen.has(v.abk.toUpperCase())).map((v) => v.abk);

  return (
    <div className="gesetze">
      <header className="kopf">
        <h1>Gesetze</h1>
        <div className="aktionen">
          {fehlend.length > 0 && (
            <button onClick={() => importieren(fehlend)} disabled={!!laeuft}>
              {fehlend.length === verfuegbar.length ? "Eingeschaltete Pakete laden" : `${fehlend.length} fehlende laden`}
            </button>
          )}
          {gesetze.length > 0 && (
            <button className="zweitrangig" onClick={() => importieren(gesetze.map((g) => g.abk))} disabled={!!laeuft}>
              Auf neue Fassung prüfen
            </button>
          )}
        </div>
      </header>

      <section className="gesetzespakete">
        <h2>Gesetzespakete</h2>
        <p className="leise">
          Eingeschaltete Pakete erscheinen in der Voreinstellung und werden mit „fehlende laden“ geholt. Ausschalten
          löscht nichts: Bereits geladene Gesetze bleiben in der Wissensbasis.
        </p>
        {pakete
          .filter((p) => !p.teil_von)
          .flatMap((p) => [p, ...pakete.filter((u) => u.teil_von === p.id)])
          .map((p) => {
            const imPaket = alle.filter((g) => g.pakete.includes(p.id));
            const fehlendImPaket = imPaket.filter((g) => !geladen.has(g.abk.toUpperCase())).map((g) => g.abk);
            const ober = pakete.find((o) => o.id === p.teil_von);
            return (
              <div
                key={p.id}
                className={["paket", p.teil_von ? "unterpaket" : "", p.wirksam ? "" : "aus"].filter(Boolean).join(" ")}
              >
                <div className="paket-kopf">
                  <label className="schalter">
                    <input
                      type="checkbox"
                      checked={p.aktiv}
                      disabled={!!laeuft}
                      onChange={(e) => void paketSchalten(p.id, e.target.checked)}
                    />
                    <span>{p.titel}</span>
                  </label>
                  <span className="leise">
                    {imPaket.length - fehlendImPaket.length} von {p.gesetze} geladen
                  </span>
                  {p.wirksam && fehlendImPaket.length > 0 && (
                    <button className="zweitrangig" onClick={() => importieren(fehlendImPaket)} disabled={!!laeuft}>
                      {fehlendImPaket.length === imPaket.length ? "Paket laden" : `${fehlendImPaket.length} fehlende laden`}
                    </button>
                  )}
                </div>
                <p className="leise">
                  {p.beschreibung}
                  {p.aktiv && !p.wirksam && ober && <> Wirkt erst, wenn „{ober.titel}“ eingeschaltet ist.</>}
                </p>
                <details className="voreinstellung">
                  <summary>Gesetze anzeigen</summary>
                  {paketGruppen(alle, p.id).map(([gruppe, liste]) => (
                    <div key={gruppe} className="gruppe">
                      <h3>{gruppe}</h3>
                      <ul>
                        {liste.map((v) => (
                          <li key={v.abk} className={geladen.has(v.abk.toUpperCase()) ? "geladen" : undefined}>
                            <strong>{v.abk}</strong> {v.titel}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </details>
              </div>
            );
          })}
      </section>

      <form className="weiteres" onSubmit={weiteresLaden}>
        <input
          value={weiteres}
          onChange={(e) => setWeiteres(e.target.value)}
          placeholder="Weiteres Bundesgesetz, z. B. GmbHG, InsO, AktG"
          aria-label="Abkürzung eines weiteren Gesetzes"
        />
        <button type="submit" className="zweitrangig" disabled={!!laeuft || !weiteres.trim()}>
          Laden
        </button>
        <button
          type="button"
          className="zweitrangig"
          onClick={() => void dateiImportieren()}
          disabled={!!laeuft}
          title="XML oder ZIP von gesetze-im-internet.de, gespeicherte Seite von EUR-Lex oder gesetze-bayern.de"
        >
          Datei importieren …
        </button>
      </form>

      {gesetze.length > 0 ? (
        <details className="bestand-klappe">
          <summary>
            Geladene Gesetze: {gesetze.length}, zusammen {gesetze.reduce((s, g) => s + g.normen, 0).toLocaleString("de-DE")}{" "}
            Normen
          </summary>
          <ul className="bestand">
            {gesetze.map((g) => (
              <li key={g.abk}>
                <strong>{g.abk}</strong> {g.langtitel} · {g.normen} Normen · Stand der Quelle{" "}
                {formatiereBuilddate(g.builddate)}
                {g.fassungen > 1 && <> · {g.fassungen} Fassungen gespeichert</>}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p className="leer">Noch keine Gesetze in der Wissensbasis. Lade die Voreinstellung, um zu beginnen.</p>
      )}

      <form className="suche" onSubmit={suchen}>
        <input
          value={eingabe}
          onChange={(e) => setEingabe(e.target.value)}
          placeholder="Suchbegriff oder Zitat, z. B. „Verjährung“ oder „§ 280 Abs. 1 S. 2 BGB“"
          aria-label="Suche in Gesetzen"
        />
        <button type="submit" disabled={!!laeuft || gesetze.length === 0}>
          Suchen
        </button>
      </form>

      {laeuft && <p className="status" role="status">{laeuft}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}

      {beleg && <BelegAnsicht beleg={beleg} />}

      {treffer && (
        <ul className="treffer">
          {treffer.length === 0 && <li className="leer">Keine Treffer.</li>}
          {treffer.map((t) => (
            <li key={t.id}>
              <button className="link" onClick={() => oeffne(t.abk, t.bezeichnung)}>
                {t.bezeichnung} {t.abk}
                {t.titel && <span className="titel"> – {t.titel}</span>}
              </button>
              <div className="ausschnitt">
                <Hervorhebung text={t.ausschnitt} />
              </div>
            </li>
          ))}
        </ul>
      )}

      {norm && <NormAnsicht norm={norm} />}
    </div>
  );
}

export function BelegAnsicht({ beleg }: { beleg: Beleg }) {
  const belegt = beleg.status === "belegt";
  return (
    <article className={belegt ? "beleg belegt" : "beleg offen"}>
      <header>
        <span className="marke-status">{belegt ? "belegt" : "nicht belegt"}</span> {beleg.zitat}
        {beleg.titel && <span className="titel"> – {beleg.titel}</span>}
      </header>
      {beleg.wortlaut && <blockquote>{beleg.wortlaut}</blockquote>}
      {beleg.hinweis && <p className="hinweis">{beleg.hinweis}</p>}
      {beleg.fassung && <FassungsZeile fassung={beleg.fassung} />}
    </article>
  );
}

function NormAnsicht({ norm }: { norm: Norm }) {
  return (
    <article className="norm">
      <p className="gliederung">{norm.gliederung.join(" › ")}</p>
      <h2>
        {norm.bezeichnung} {norm.gesetz} {norm.titel && <span className="titel">{norm.titel}</span>}
      </h2>
      {norm.absaetze.map((a, i) => (
        <section key={i} className="absatz">
          {a.nr && <span className="absatz-nr">({a.nr})</span>}
          {a.saetze.map((s) => (
            <span key={s.nr} className="satz" title={`${a.nr ? `Abs. ${a.nr} ` : ""}S. ${s.nr}`}>
              {s.text}{" "}
            </span>
          ))}
        </section>
      ))}
      <FassungsZeile fassung={norm.fassung} />
    </article>
  );
}

function FassungsZeile({ fassung }: { fassung: Fassung }) {
  return (
    <footer className="fassung">
      Fassung #{fassung.id} · Quelle vom {formatiereBuilddate(fassung.builddate)} · abgerufen{" "}
      {new Date(fassung.abgerufen_am).toLocaleString("de-DE")}
      {fassung.stand.length > 0 && <> · {fassung.stand[fassung.stand.length - 1]}</>}
      <br />
      {fassung.hinweis}
    </footer>
  );
}

/** FTS-Ausschnitt mit [Treffer]-Markierungen sicher als <mark> darstellen. */
function Hervorhebung({ text }: { text: string }) {
  const teile = text.split(/(\[[^\]]*\])/g);
  return (
    <>
      {teile.map((t, i) => (t.startsWith("[") && t.endsWith("]") ? <mark key={i}>{t.slice(1, -1)}</mark> : t))}
    </>
  );
}
