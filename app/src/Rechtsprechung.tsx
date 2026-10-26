import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import AktenWahl from "./AktenWahl";
import { Rueckfrage, VolltextAnsicht } from "./Akte";
import {
  Akte,
  SammlungEintrag,
  SammlungSuche,
  URTEIL_QUELLEN,
  URTEIL_QUELLE_NAME,
  UrteilQuelle,
  UrteilVolltext,
  istDesktop,
  kern,
  sammlungPasst,
  urteilHerkunft,
  urteilTitel,
} from "./kern";

type Zuordnung = "alle" | "zugeordnet" | "frei";

/** Angaben zu einer eigenen Datei, die ohne Akte in die Sammlung kommt. */
interface NeueDatei {
  pfad: string;
  name: string;
  gericht: string;
  aktenzeichen: string;
  datum: string;
  herkunft: string;
}

/**
 * Bereich „Rechtsprechung“: alle gespeicherten Entscheidungen über alle Akten, je Datei einmal. Zeigt, welchen Akten
 * eine Entscheidung zugeordnet ist (oder „nicht zugeordnet“) und woher sie stammt; durchsuchbar im Volltext. Eine
 * Entscheidung lässt sich einer Akte zuordnen, etwa um einen Schriftsatz vorzubereiten.
 */
export default function Rechtsprechung({
  onAkte,
  onQuellen,
}: {
  onAkte: (akteId: number) => void;
  onQuellen: () => void;
}) {
  const [eintraege, setEintraege] = useState<SammlungEintrag[] | null>(null);
  const [akten, setAkten] = useState<Akte[]>([]);
  const [zuordnung, setZuordnung] = useState<Zuordnung>("alle");
  const [quelle, setQuelle] = useState<UrteilQuelle | "alle">("alle");
  const [filter, setFilter] = useState("");
  const [suchtext, setSuchtext] = useState("");
  const [treffer, setTreffer] = useState<SammlungSuche | null>(null);
  const [volltext, setVolltext] = useState<UrteilVolltext | null>(null);
  const [rn, setRn] = useState<number | null>(null);
  const [neu, setNeu] = useState<NeueDatei | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<SammlungEintrag | null>(null);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

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

  const laden = useCallback(async () => {
    const [liste, alle] = await Promise.all([
      kern<SammlungEintrag[]>("rechtsprechung.sammlung"),
      kern<Akte[]>("akten.liste"),
    ]);
    setEintraege(liste);
    setAkten(alle);
    return liste;
  }, []);

  useEffect(() => {
    if (istDesktop) void ausfuehren("Lade die Sammlung …", laden);
  }, [ausfuehren, laden]);

  // Volltextsuche im Kern; die übrigen Filter wirken sofort auf die geladene Liste.
  useEffect(() => {
    if (!istDesktop) return;
    if (!suchtext.trim()) {
      setTreffer(null);
      return;
    }
    let aktuell = true;
    const zeit = setTimeout(() => {
      kern<SammlungSuche>("rechtsprechung.suche", { suchtext }).then(
        (t) => aktuell && setTreffer(t),
        (e) => aktuell && setFehler(String(e)),
      );
    }, 300);
    return () => {
      aktuell = false;
      clearTimeout(zeit);
    };
  }, [suchtext]);

  const sichtbar = useMemo(() => {
    const passend = (eintraege ?? []).filter((e) => sammlungPasst(e, { zuordnung, quelle, text: filter }));
    if (!treffer) return passend.map((e) => ({ e, fundstellen: null }));
    const je = new Map(passend.map((e) => [e.sha256, e]));
    return treffer.urteile.flatMap((t) => {
      const e = je.get(t.sha256);
      return e ? [{ e, fundstellen: t.fundstellen }] : [];
    });
  }, [eintraege, zuordnung, quelle, filter, treffer]);

  const anzahl = eintraege?.length ?? 0;
  const frei = eintraege?.filter((e) => !e.zugeordnet).length ?? 0;
  const quellen = [...new Set((eintraege ?? []).map((e) => e.quelle))];

  async function oeffne(e: SammlungEintrag, rnZiel?: number | null) {
    setRn(rnZiel ?? null);
    if (volltext?.sha256 === e.sha256) return;
    const v = await ausfuehren("Lade Volltext …", () => kern<UrteilVolltext>("akten.urteil", { urteil_id: e.id }));
    setVolltext(v ?? null);
  }

  async function zuordnen(e: SammlungEintrag, akteId: number | null) {
    if (akteId == null) return;
    const akte = akten.find((a) => a.id === akteId);
    const r = await ausfuehren("Ordne zu …", () =>
      kern<{ urteil_id: number; neu: boolean }>("rechtsprechung.zuordnen", { urteil_id: e.id, akte_id: akteId }),
    );
    if (!r) return;
    setMeldung(
      r.neu
        ? `${urteilTitel(e)} ist jetzt der Akte ${akte?.aktenzeichen ?? akte?.name ?? ""} zugeordnet.`
        : `${urteilTitel(e)} ist dieser Akte schon zugeordnet.`,
    );
    await laden();
  }

  async function loesen(e: SammlungEintrag, a: SammlungEintrag["akten"][number]) {
    const r = await ausfuehren("Löse die Zuordnung …", () =>
      kern<{ urteil_id: number }>("rechtsprechung.loesen", { urteil_id: a.urteil_id }),
    );
    if (!r) return;
    setMeldung(`${urteilTitel(e)} ist der Akte ${a.name} nicht mehr zugeordnet; sie bleibt in der Sammlung.`);
    await laden();
  }

  async function entfernen(e: SammlungEintrag) {
    setLoeschfrage(null);
    const r = await ausfuehren("Entferne …", () =>
      kern<{ entfernt: number; hinweise: string[] }>("rechtsprechung.entfernen", { urteil_id: e.id }),
    );
    if (!r) return;
    if (volltext?.sha256 === e.sha256) setVolltext(null);
    setMeldung([`${urteilTitel(e)} entfernt.`, ...r.hinweise].join(" "));
    await laden();
  }

  async function dateiWaehlen() {
    const gewaehlt = await open({
      title: "Entscheidung zur Sammlung hinzufügen",
      filters: [{ name: "Entscheidung (PDF, Word, Text)", extensions: ["pdf", "docx", "txt", "md"] }],
    });
    if (typeof gewaehlt !== "string") return;
    const name = gewaehlt.split(/[\\/]/).pop() ?? gewaehlt;
    // Quelle aus dem Dateinamen vorschlagen, wenn er sie nennt (z. B. „juris_BGH_VIII_ZR_999-20.pdf“).
    const herkunft = URTEIL_QUELLEN.find((q) => name.toLowerCase().includes(q.toLowerCase().split(" ")[0])) ?? "";
    setNeu({ pfad: gewaehlt, name, gericht: "", aktenzeichen: "", datum: "", herkunft });
  }

  async function dateiSpeichern(ev: FormEvent) {
    ev.preventDefault();
    if (!neu) return;
    const n = neu;
    const r = await ausfuehren(`Lese ${n.name} …`, () =>
      kern<{ urteil_id: number; neu: boolean }>("rechtsprechung.ergaenzen", {
        pfad: n.pfad,
        gericht: n.gericht,
        aktenzeichen: n.aktenzeichen || null,
        datum: n.datum || null,
        herkunft: n.herkunft || null,
      }),
    );
    if (!r) return;
    setNeu(null);
    setMeldung(r.neu ? `${n.name} zur Sammlung hinzugefügt.` : `${n.name} steht schon in der Sammlung.`);
    const liste = await laden();
    const e = liste.find((x) => x.id === r.urteil_id || x.akten.some((a) => a.urteil_id === r.urteil_id));
    if (e) await oeffne(e);
  }

  if (!istDesktop) {
    return (
      <div className="rechtsprechung">
        <header className="kopf">
          <h1>Rechtsprechung</h1>
        </header>
        <section className="hinweis-box">
          Die Oberfläche läuft gerade im Browser. Die Sammlung gibt es nur in der Desktop-App: <code>npm run tauri dev</code>
        </section>
      </div>
    );
  }

  return (
    <div className="sammlung">
      <div className="sammlung-liste">
        <header className="kopf">
          <h1>Rechtsprechung</h1>
          <button onClick={dateiWaehlen} disabled={!!laeuft}>
            Eigene Datei hinzufügen …
          </button>
        </header>
        <p className="erklaerung">
          Alle gespeicherten Entscheidungen, aus allen Akten und ohne Akte. Geladen werden sie in der Akte unter
          „Rechtsprechung der Akte“ oder hier als eigene Datei;{" "}
          <button className="link" onClick={onQuellen}>
            Quellen in den Einstellungen
          </button>
          .
        </p>

        {neu && (
          <form className="rueckfrage" aria-label="Entscheidung hinzufügen" onSubmit={dateiSpeichern}>
            <strong>„{neu.name}“ zur Sammlung hinzufügen</strong>
            <p>
              Die Datei wird unverändert abgelegt und gelesen; Randnummern werden als Fundstellen erkannt. Einer Akte
              zuordnen lässt sie sich danach.
            </p>
            <div className="formular">
              <label>
                Gericht
                <input value={neu.gericht} onChange={(e) => setNeu({ ...neu, gericht: e.target.value })} required autoFocus />
              </label>
              <label>
                Aktenzeichen
                <input value={neu.aktenzeichen} onChange={(e) => setNeu({ ...neu, aktenzeichen: e.target.value })} />
              </label>
              <label>
                Datum
                <input type="date" value={neu.datum} onChange={(e) => setNeu({ ...neu, datum: e.target.value })} />
              </label>
              <label>
                Quelle
                <input
                  list="sammlung-quellen"
                  value={neu.herkunft}
                  onChange={(e) => setNeu({ ...neu, herkunft: e.target.value })}
                  placeholder="z. B. juris"
                />
                <datalist id="sammlung-quellen">
                  {URTEIL_QUELLEN.map((q) => (
                    <option key={q} value={q} />
                  ))}
                </datalist>
              </label>
            </div>
            <div className="aktionen">
              <button type="submit" disabled={!!laeuft || !neu.gericht.trim()}>
                Hinzufügen
              </button>
              <button type="button" className="zweitrangig" onClick={() => setNeu(null)}>
                Abbrechen
              </button>
            </div>
          </form>
        )}

        {loeschfrage && (
          <Rueckfrage
            frage={`„${urteilTitel(loeschfrage)}“ ganz entfernen?`}
            erklaerung={
              loeschfrage.akten.length > 0
                ? `Sie verschwindet auch aus ${loeschfrage.akten.length === 1 ? "der Akte" : "den Akten"} ${loeschfrage.akten
                    .map((a) => a.name)
                    .join(", ")}. Geladene Volltexte bleiben im Roharchiv.`
                : "Geladene Volltexte bleiben im Roharchiv; eine eigene Datei am ursprünglichen Ort bleibt unberührt."
            }
            ja="Entfernen"
            onJa={() => entfernen(loeschfrage)}
            onNein={() => setLoeschfrage(null)}
          />
        )}

        <div className="suche-feld">
          <input
            type="search"
            value={suchtext}
            onChange={(e) => setSuchtext(e.target.value)}
            placeholder="Im Text aller gespeicherten Entscheidungen suchen, z. B. Nacherfüllung Fristsetzung"
            aria-label="Volltextsuche in den gespeicherten Entscheidungen"
          />
        </div>
        <div className="sammlung-filter">
          <div className="wahl-reihe" role="group" aria-label="Zuordnung">
            {(
              [
                ["alle", `Alle (${anzahl})`],
                ["zugeordnet", `Einer Akte zugeordnet (${anzahl - frei})`],
                ["frei", `Nicht zugeordnet (${frei})`],
              ] as [Zuordnung, string][]
            ).map(([id, titel]) => (
              <button key={id} className={`chip${zuordnung === id ? " aktiv" : ""}`} onClick={() => setZuordnung(id)}>
                {titel}
              </button>
            ))}
          </div>
          <select value={quelle} onChange={(e) => setQuelle(e.target.value as UrteilQuelle | "alle")} aria-label="Quelle">
            <option value="alle">Alle Quellen</option>
            {quellen.map((q) => (
              <option key={q} value={q}>
                {URTEIL_QUELLE_NAME[q]}
              </option>
            ))}
          </select>
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Gericht, Aktenzeichen, Akte …"
            aria-label="Liste eingrenzen"
          />
        </div>

        {laeuft && <p className="status">{laeuft}</p>}
        {fehler && <p className="fehler">{fehler}</p>}
        {meldung && !laeuft && <p className="hinweis">{meldung}</p>}

        {eintraege && anzahl === 0 && (
          <p className="leer">
            Noch keine Entscheidungen gespeichert. Sie kommen hierher, wenn man in einer Akte unter „Rechtsprechung der
            Akte“ Volltexte lädt oder ein Urteil selbst ergänzt, oder über „Eigene Datei hinzufügen …“.
          </p>
        )}
        {anzahl > 0 && sichtbar.length === 0 && (
          <p className="leer">{treffer ? `Keine gespeicherte Entscheidung enthält „${suchtext}“.` : "Keine Entscheidung passt zum Filter."}</p>
        )}
        {treffer && sichtbar.length > 0 && (
          <p className="leise">
            {sichtbar.length} {sichtbar.length === 1 ? "Entscheidung" : "Entscheidungen"} mit „{suchtext}“, beste Treffer
            zuerst.
          </p>
        )}

        <ul className="sammlung-eintraege">
          {sichtbar.map(({ e, fundstellen }) => (
            <li key={e.sha256} className={volltext?.sha256 === e.sha256 ? "sammlung-eintrag aktiv" : "sammlung-eintrag"}>
              <button className="link sammlung-titel" onClick={() => oeffne(e)}>
                {urteilTitel(e)}
              </button>
              {e.kopf?.titel && <p className="volltext-titel">{e.kopf.titel}</p>}
              <p className="fundort">
                {URTEIL_QUELLE_NAME[e.quelle]}
                {e.quelle === "manuell" && ` (${urteilHerkunft(e)})`}
              </p>
              {fundstellen && (
                <ul className="sammlung-fundstellen">
                  {fundstellen.slice(0, 3).map((f) => (
                    <li key={f.nr}>
                      <button className="link" onClick={() => oeffne(e, f.rn)}>
                        {f.rn != null ? `Rn. ${f.rn}` : `Abs. ${f.nr}`}
                      </button>{" "}
                      {f.ausschnitt.vor}
                      <mark>{f.ausschnitt.treffer}</mark>
                      {f.ausschnitt.nach}
                    </li>
                  ))}
                  {fundstellen.length > 3 && <li className="leise">und {fundstellen.length - 3} weitere Stellen</li>}
                </ul>
              )}
              <div className="sammlung-akten">
                {e.akten.length === 0 && <span className="leise">nicht zugeordnet</span>}
                {e.akten.map((a) => (
                  <span key={a.urteil_id} className="sammlung-akte">
                    <button className="link" onClick={() => onAkte(a.akte_id)} title="Akte öffnen">
                      {akten.find((x) => x.id === a.akte_id)?.aktenzeichen ?? a.name}
                    </button>
                    <button
                      className="link klein"
                      onClick={() => loesen(e, a)}
                      disabled={!!laeuft}
                      aria-label={`Zuordnung zur Akte ${a.name} lösen`}
                      title="Zuordnung lösen; die Entscheidung bleibt in der Sammlung"
                    >
                      ×
                    </button>
                  </span>
                ))}
                <AktenWahl
                  akten={akten.filter((a) => !e.akten.some((x) => x.akte_id === a.id))}
                  akteId={null}
                  onWahl={(id) => zuordnen(e, id)}
                  knopf="Akte zuordnen …"
                />
                <button className="link klein" onClick={() => setLoeschfrage(e)} disabled={!!laeuft}>
                  entfernen
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
      {volltext && <VolltextAnsicht volltext={volltext} rn={rn} onSchliessen={() => setVolltext(null)} />}
    </div>
  );
}
