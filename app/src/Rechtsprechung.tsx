import {
  CSSProperties,
  FormEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { open } from "@tauri-apps/plugin-dialog";
import AktenWahl from "./AktenWahl";
import { Rueckfrage, VolltextAnsicht } from "./Akte";
import RechtsprechungSuche, { trefferSchluessel } from "./RechtsprechungSuche";
import {
  Akte,
  Erkannt,
  KopfVorschlag,
  RechercheTreffer,
  SammlungEintrag,
  SammlungSuche,
  URTEIL_ARTEN,
  URTEIL_QUELLEN,
  URTEIL_QUELLE_NAME,
  UrteilQuelle,
  UrteilVolltext,
  erkanntText,
  istDesktop,
  kern,
  sammlungPasst,
  urteilHerkunft,
  urteilTitel,
} from "./kern";

type Zuordnung = "alle" | "zugeordnet" | "frei";
type Ansicht = "sammlung" | "suche";

/** Breite des Volltexts rechts, je Gerät gemerkt; die Liste links behält mindestens LISTE_MIN. */
const VOLLTEXT_STANDARD = 520;
const VOLLTEXT_MIN = 300;
const LISTE_MIN = 360;
const BREITE_SCHLUESSEL = "rechtsprechung.volltextbreite";

function gespeicherteBreite(): number {
  try {
    const wert = Number(localStorage.getItem(BREITE_SCHLUESSEL));
    return wert >= VOLLTEXT_MIN ? wert : VOLLTEXT_STANDARD;
  } catch {
    return VOLLTEXT_STANDARD;
  }
}

/** Angaben zu einer eigenen Datei, die ohne Akte in die Sammlung kommt. */
interface NeueDatei {
  pfad: string;
  name: string;
  gericht: string;
  aktenzeichen: string;
  datum: string;
  art: string;
  herkunft: string;
  /** Was aus dem Text erkannt wurde, mit Fundstelle; null, solange noch gelesen wird. */
  vorschlag: KopfVorschlag | null;
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
  const [ansicht, setAnsicht] = useState<Ansicht>("sammlung");
  const [volltext, setVolltext] = useState<UrteilVolltext | null>(null);
  /** Treffer der Online-Suche, der rechts offen ist und noch nicht gespeichert wurde. */
  const [vorschau, setVorschau] = useState<RechercheTreffer | null>(null);
  /** Seit dem Öffnen des Bereichs gespeicherte Treffer: Schlüssel → Entscheidung. */
  const [gespeichert, setGespeichert] = useState<Record<string, number>>({});
  const [rn, setRn] = useState<number | null>(null);
  const [neu, setNeu] = useState<NeueDatei | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<SammlungEintrag | null>(null);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [breite, setBreite] = useState(gespeicherteBreite);
  const flaeche = useRef<HTMLDivElement>(null);

  function setzeBreite(b: number) {
    setBreite(b);
    try {
      localStorage.setItem(BREITE_SCHLUESSEL, String(b));
    } catch {
      // Ohne Speicher gilt die Breite nur bis zum Neustart.
    }
  }

  /** Trennlinie ziehen: nach links bekommt der Volltext mehr Platz, nach rechts die Liste. */
  function breiteZiehen(e: ReactPointerEvent<HTMLDivElement>) {
    const rahmen = flaeche.current?.getBoundingClientRect();
    if (!rahmen) return;
    e.preventDefault();
    const neu = (x: number) => Math.round(Math.min(Math.max(rahmen.right - x, VOLLTEXT_MIN), rahmen.width - LISTE_MIN));
    const bewegen = (ev: PointerEvent) => setBreite(neu(ev.clientX));
    const loslassen = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", bewegen);
      window.removeEventListener("pointerup", loslassen);
      setzeBreite(neu(ev.clientX));
    };
    window.addEventListener("pointermove", bewegen);
    window.addEventListener("pointerup", loslassen);
  }

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
    setVorschau(null);
  }

  async function gespeicherteOeffnen(urteilId: number) {
    const v = await ausfuehren("Lade Volltext …", () => kern<UrteilVolltext>("akten.urteil", { urteil_id: urteilId }));
    if (v) {
      setVolltext(v);
      setVorschau(null);
    }
  }

  /** Treffer der Online-Suche öffnen: gespeicherte aus der Sammlung, sonst von der Quelle laden (noch ohne Speichern). */
  async function trefferOeffnen(t: RechercheTreffer) {
    setRn(null);
    setMeldung(null);
    const id = t.urteil_id ?? gespeichert[trefferSchluessel(t)];
    if (id != null) return gespeicherteOeffnen(id);
    const v = await ausfuehren(`Lade die Entscheidung von ${URTEIL_QUELLE_NAME[t.quelle]} …`, () =>
      kern<UrteilVolltext>("rechtsprechung.recherche_oeffnen", { quelle: t.quelle, doknr: t.doknr, treffer: t }),
    );
    if (v) {
      setVolltext(v);
      setVorschau(t);
    }
  }

  /** Den offenen Treffer in die Sammlung übernehmen, auf Wunsch gleich einer Akte zugeordnet. */
  async function trefferSpeichern(t: RechercheTreffer, akteId: number | null) {
    const akte = akteId != null ? akten.find((a) => a.id === akteId) : undefined;
    const r = await ausfuehren("Übernehme in die Sammlung …", async () => {
      const s = await kern<{ urteil_id: number; neu: boolean }>("rechtsprechung.recherche_speichern", {
        quelle: t.quelle,
        doknr: t.doknr,
        treffer: t,
      });
      if (akteId != null) await kern("rechtsprechung.zuordnen", { urteil_id: s.urteil_id, akte_id: akteId });
      return s;
    });
    if (!r) return;
    setGespeichert((g) => ({ ...g, [trefferSchluessel(t)]: r.urteil_id }));
    const titel = urteilTitel(volltext ?? { gericht: t.gericht, datum: t.datum, aktenzeichen: t.aktenzeichen, kopf: null });
    const zuAkte = akte ? ` und der Akte ${akte.aktenzeichen ?? akte.name} zugeordnet` : "";
    setMeldung(r.neu ? `${titel} steht jetzt in der Sammlung${zuAkte}.` : `${titel} stand schon in der Sammlung${zuAkte ? `; jetzt${zuAkte}` : ""}.`);
    await laden();
    await gespeicherteOeffnen(r.urteil_id);
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
    setAnsicht("sammlung");
    const name = gewaehlt.split(/[\\/]/).pop() ?? gewaehlt;
    // Quelle aus dem Dateinamen vorschlagen, wenn er sie nennt (z. B. „juris_BGH_VIII_ZR_999-20.pdf“).
    const herkunft = URTEIL_QUELLEN.find((q) => name.toLowerCase().includes(q.toLowerCase().split(" ")[0])) ?? "";
    const leer = { pfad: gewaehlt, name, gericht: "", aktenzeichen: "", datum: "", art: "", herkunft, vorschlag: null };
    setNeu(leer);
    // Gericht, Aktenzeichen, Datum, Art und Quelle aus dem Kopf der Entscheidung vorschlagen.
    const v = await ausfuehren(`Lese ${name} und suche Gericht, Aktenzeichen und Datum …`, () =>
      kern<KopfVorschlag>("rechtsprechung.vorschlag", { pfad: gewaehlt }),
    );
    if (!v) return;
    setNeu((n) =>
      n && n.pfad === gewaehlt
        ? {
            ...n,
            gericht: n.gericht || v.gericht?.wert || "",
            aktenzeichen: n.aktenzeichen || v.aktenzeichen?.wert || "",
            datum: n.datum || v.datum?.wert || "",
            art: n.art || v.art?.wert || "",
            herkunft: n.herkunft || v.herkunft?.wert || "",
            vorschlag: v,
          }
        : n,
    );
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
        art: n.art || null,
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
    <div className="sammlung" ref={flaeche} style={{ "--seite-breite": `${breite}px` } as CSSProperties}>
      <div className="sammlung-liste">
        <header className="kopf">
          <h1>Rechtsprechung</h1>
          <button onClick={dateiWaehlen} disabled={!!laeuft}>
            Eigene Datei hinzufügen …
          </button>
        </header>
        <div className="wahl-reihe bereich-wahl" role="group" aria-label="Ansicht">
          {(
            [
              ["sammlung", `Gespeicherte Entscheidungen (${anzahl})`],
              ["suche", "Online suchen"],
            ] as [Ansicht, string][]
          ).map(([id, titel]) => (
            <button key={id} className={`chip${ansicht === id ? " aktiv" : ""}`} onClick={() => setAnsicht(id)}>
              {titel}
            </button>
          ))}
        </div>
        {ansicht === "sammlung" ? (
          <p className="erklaerung">
            Alle gespeicherten Entscheidungen, aus allen Akten und ohne Akte. Sie kommen aus der Akte („Rechtsprechung
            der Akte“), aus der Online-Suche oder als eigene Datei;{" "}
            <button className="link" onClick={onQuellen}>
              Quellen in den Einstellungen
            </button>
            .
          </p>
        ) : (
          <p className="erklaerung">
            Entscheidungen bei rechtsprechung-im-internet.de, gesetze-bayern.de und NeuRIS suchen. Ein Treffer öffnet sich
            rechts; von dort kommt er in die Sammlung und auf Wunsch gleich in eine Akte.
          </p>
        )}

        {laeuft && <p className="status">{laeuft}</p>}
        {fehler && <p className="fehler">{fehler}</p>}
        {meldung && !laeuft && <p className="hinweis">{meldung}</p>}

        {/* Beide Ansichten bleiben bestehen, damit Suche und Filter beim Umschalten erhalten bleiben. */}
        <div hidden={ansicht !== "suche"}>
          <RechtsprechungSuche
            offen={vorschau ? trefferSchluessel(vorschau) : volltext?.doknr ? `${volltext.quelle}:${volltext.doknr}` : null}
            gespeichert={gespeichert}
            gesperrt={!!laeuft}
            onOeffnen={trefferOeffnen}
            onQuellen={onQuellen}
          />
        </div>
        <div hidden={ansicht !== "sammlung"}>

        {neu && (
          <form className="rueckfrage" aria-label="Entscheidung hinzufügen" onSubmit={dateiSpeichern}>
            <strong>„{neu.name}“ zur Sammlung hinzufügen</strong>
            <p>
              Die Datei wird unverändert abgelegt und gelesen; Randnummern werden als Fundstellen erkannt. Einer Akte
              zuordnen lässt sie sich danach.
            </p>
            {neu.vorschlag && <VorschlagHinweis v={neu.vorschlag} />}
            <div className="formular">
              <label>
                Gericht
                <Feld erkannt={neu.vorschlag?.gericht} wert={neu.gericht}>
                  <input value={neu.gericht} onChange={(e) => setNeu({ ...neu, gericht: e.target.value })} required autoFocus />
                </Feld>
              </label>
              <label>
                Aktenzeichen
                <Feld erkannt={neu.vorschlag?.aktenzeichen} wert={neu.aktenzeichen}>
                  <input value={neu.aktenzeichen} onChange={(e) => setNeu({ ...neu, aktenzeichen: e.target.value })} />
                </Feld>
              </label>
              <label>
                Datum
                <Feld erkannt={neu.vorschlag?.datum} wert={neu.datum}>
                  <input type="date" value={neu.datum} onChange={(e) => setNeu({ ...neu, datum: e.target.value })} />
                </Feld>
              </label>
              <label>
                Art
                <Feld erkannt={neu.vorschlag?.art} wert={neu.art}>
                  <input
                    list="sammlung-arten"
                    value={neu.art}
                    onChange={(e) => setNeu({ ...neu, art: e.target.value })}
                    placeholder="z. B. Urteil"
                  />
                  <datalist id="sammlung-arten">
                    {URTEIL_ARTEN.map((a) => (
                      <option key={a} value={a} />
                    ))}
                  </datalist>
                </Feld>
              </label>
              <label>
                Quelle
                <Feld erkannt={neu.vorschlag?.herkunft} wert={neu.herkunft}>
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
                </Feld>
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

        {eintraege && anzahl === 0 && (
          <p className="leer">
            Noch keine Entscheidungen gespeichert. Sie kommen hierher, wenn man in einer Akte unter „Rechtsprechung der
            Akte“ Volltexte lädt oder ein Urteil selbst ergänzt, über „Online suchen“ oder über „Eigene Datei
            hinzufügen …“.
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
              {/* Die ganze Fläche öffnet die Entscheidung; nur die Leiste darunter (Akten, Knöpfe) nicht. */}
              <div
                className="sammlung-flaeche"
                role="button"
                tabIndex={0}
                aria-label={`${urteilTitel(e)} öffnen`}
                onClick={() => oeffne(e)}
                onKeyDown={(ev) => {
                  if (ev.target !== ev.currentTarget || (ev.key !== "Enter" && ev.key !== " ")) return;
                  ev.preventDefault();
                  void oeffne(e);
                }}
              >
                <strong className="sammlung-titel">{urteilTitel(e)}</strong>
                {e.kopf?.titel && <p className="volltext-titel">{e.kopf.titel}</p>}
                <p className="fundort">
                  {URTEIL_QUELLE_NAME[e.quelle]}
                  {e.quelle === "manuell" && ` (${urteilHerkunft(e)})`}
                </p>
                {fundstellen && (
                  <ul className="sammlung-fundstellen">
                    {fundstellen.slice(0, 3).map((f) => (
                      <li key={f.nr}>
                        <button
                          className="link"
                          onClick={(ev) => {
                            ev.stopPropagation();
                            void oeffne(e, f.rn);
                          }}
                        >
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
              </div>
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
                  Entscheidung entfernen
                </button>
              </div>
            </li>
          ))}
        </ul>
        </div>
      </div>
      {volltext && (
        <div
          className="trenner"
          role="separator"
          aria-orientation="vertical"
          aria-label="Aufteilung zwischen Liste und Volltext"
          title="Ziehen: nach links mehr Platz für den Volltext, nach rechts für die Liste; Doppelklick setzt zurück"
          onPointerDown={breiteZiehen}
          onDoubleClick={() => setzeBreite(VOLLTEXT_STANDARD)}
        />
      )}
      {volltext && (
        <VolltextAnsicht
          volltext={volltext}
          rn={rn}
          onSchliessen={() => {
            setVolltext(null);
            setVorschau(null);
          }}
          aktionen={
            vorschau && (
              <>
                <button className="klein" onClick={() => trefferSpeichern(vorschau, null)} disabled={!!laeuft}>
                  In die Sammlung
                </button>
                <AktenWahl
                  akten={akten}
                  akteId={null}
                  onWahl={(id) => id != null && trefferSpeichern(vorschau, id)}
                  knopf="In die Sammlung und Akte zuordnen …"
                />
              </>
            )
          }
        />
      )}
    </div>
  );
}

/** Eingabefeld mit der Fundstelle des erkannten Werts darunter, solange er nicht geändert wurde. */
function Feld({ erkannt, wert, children }: { erkannt: Erkannt | null | undefined; wert: string; children: ReactNode }) {
  return (
    <div className="feld-mit-fundstelle">
      {children}
      {erkannt && erkannt.wert === wert && <span className="leise feld-hinweis">Fundstelle {erkanntText(erkannt)}</span>}
    </div>
  );
}

/** Was beim Lesen herauskam: alles erkannt, teilweise oder nichts (etwa ein Scan ohne Texterkennung). */
function VorschlagHinweis({ v }: { v: KopfVorschlag }) {
  const felder: [string, Erkannt | null][] = [
    ["Gericht", v.gericht],
    ["Aktenzeichen", v.aktenzeichen],
    ["Datum", v.datum],
  ];
  const fehlt = felder.filter(([, e]) => !e).map(([name]) => name);
  if (v.lesart === "leer") {
    return <p className="hinweis">In der Datei steht kein lesbarer Text. {v.hinweise.join(" ")} Bitte die Angaben selbst eintragen.</p>;
  }
  if (!fehlt.length) return <p className="leise">Aus dem Dokument vorgeschlagen; bitte prüfen.</p>;
  return (
    <p className="leise">
      {fehlt.length === felder.length ? "Im Kopf der Entscheidung wurde nichts erkannt" : `Nicht erkannt: ${fehlt.join(", ")}`}
      ; bitte selbst eintragen.
    </p>
  );
}
