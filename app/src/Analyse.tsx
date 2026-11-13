import { useCallback, useEffect, useRef, useState } from "react";
import { DokumentAnsicht } from "./DokumentAnsicht";
import { Beleg, Zitatbereich, ZitateSchalter } from "./Belege";
import KiExport from "./Export";
import { useAuftrag } from "./useAuftrag";
import { SkillWahl, useSkillWahl } from "./Skills";
import {
  ART_TEXT,
  EREIGNIS_ART_TEXT,
  AktenDokument,
  DokumentInhalt,
  EINORDNUNG_TEXT,
  HALTUNG_TEXT,
  KiAufgabe,
  KiAuftrag,
  KiAussage,
  KiChronologie,
  KiErgebnisse,
  KiFundstelle,
  KiStatus,
  KiWiderspruch,
  KiZusammenfassung,
  dauerText,
  istDesktop,
  kern,
  skillText,
  veraltet,
  zeitpunkt,
} from "./kern";

type Ansicht = "chronologie" | "akte" | "dokumente";
export type Offen = { inhalt: DokumentInhalt; abschnitt: number } | null;

const LEER: KiErgebnisse = { zusammenfassung_akte: null, widersprueche: null, chronologie: null, dokumente: {} };

/** Zusammenfassungen und Chronologie mit dem Sprachmodell, jede Aussage mit Fundstelle. Widersprüche zeigt der Vergleich. */
export default function Analyse({
  akteId,
  onEinstellungen,
  onSkills,
}: {
  akteId: number;
  onEinstellungen: () => void;
  /** Öffnet Einstellungen → Skills. */
  onSkills?: () => void;
}) {
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [status, setStatus] = useState<KiStatus | null>(null);
  const [ergebnisse, setErgebnisse] = useState<KiErgebnisse>(LEER);
  const [auftrag, setAuftrag] = useState<KiAuftrag | null>(null);
  const [ansicht, setAnsicht] = useState<Ansicht>("chronologie");
  const [offen, setOffen] = useState<Offen>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [ausgeben, setAusgeben] = useState(false);
  const seite = useRef<HTMLDivElement>(null);
  const [skill, setSkill] = useSkillWahl("analyse", akteId);

  const ladeErgebnisse = useCallback(async (id: number) => {
    setErgebnisse(await kern<KiErgebnisse>("ki.ergebnisse", { akte_id: id }));
  }, []);

  useEffect(() => {
    if (!istDesktop) return;
    void (async () => {
      try {
        setAuftrag(await kern<KiAuftrag | null>("ki.laufend"));
        setStatus(await kern<KiStatus>("ki.status"));
      } catch (e) {
        setFehler(String(e));
      }
    })();
  }, []);

  useEffect(() => {
    setErgebnisse(LEER);
    setDokumente([]);
    setOffen(null);
    setAusgeben(false);
    if (akteId == null || !istDesktop) return;
    void (async () => {
      try {
        setDokumente(await kern<AktenDokument[]>("akten.dokumente", { akte_id: akteId }));
        await ladeErgebnisse(akteId);
      } catch (e) {
        setFehler(String(e));
      }
    })();
  }, [akteId, ladeErgebnisse]);

  // Laufenden Auftrag jede Sekunde abfragen; danach die gespeicherten Ergebnisse neu laden.
  const laeuft = auftrag?.status === "laeuft";
  useAuftrag(
    laeuft && auftrag ? auftrag.auftrag_id : null,
    async (stand) => {
      setAuftrag(stand);
      if (stand.status === "fehler") setFehler(stand.fehler);
      if (stand.status !== "laeuft" && akteId != null) await ladeErgebnisse(akteId);
    },
    (e) => {
      setFehler(String(e));
      setAuftrag(null);
    },
  );

  async function starte(aufgabe: KiAufgabe, params: Record<string, unknown>) {
    setFehler(null);
    try {
      setAuftrag(await kern<KiAuftrag>("ki.starten", { aufgabe, ...params, skills: skill }));
      if (aufgabe === "zusammenfassung_akte") setAnsicht("akte");
      if (aufgabe === "chronologie") setAnsicht("chronologie");
    } catch (e) {
      setFehler(String(e));
    }
  }

  async function abbrechen() {
    if (auftrag) setAuftrag(await kern<KiAuftrag>("ki.abbrechen", { auftrag_id: auftrag.auftrag_id }));
  }

  async function oeffne(f: KiFundstelle) {
    try {
      const inhalt = await kern<DokumentInhalt>("akten.dokument", { dokument_id: f.dokument_id });
      setOffen({ inhalt, abschnitt: f.abschnitt });
    } catch (e) {
      setFehler(String(e));
    }
  }

  useEffect(() => {
    const leiste = seite.current;
    const ziel = offen && document.getElementById(`abschnitt-${offen.abschnitt}`);
    if (!leiste || !ziel) return;
    leiste.scrollTop += ziel.getBoundingClientRect().top - leiste.getBoundingClientRect().top - leiste.clientHeight / 3;
  }, [offen]);

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Die Analyse arbeitet nur in der Desktop-App: <code>npm run tauri dev</code>
      </section>
    );
  }

  const bereit = status?.bereit ?? false;
  const kannStarten = bereit && !laeuft && akteId != null && dokumente.length > 0;
  const ids = dokumente.map((d) => d.id);
  const w = ergebnisse.widersprueche;
  const z = ergebnisse.zusammenfassung_akte;
  const c = ergebnisse.chronologie;

  return (
    <div className="analyse">
      <p className="erklaerung">
        Fasst Dokumente und die Akte zusammen und erstellt eine Chronologie mit dem gewählten Sprachmodell.
        Widersprüche zwischen den Dokumenten zeigt der Bereich „Vergleich“. Jede
        Aussage verweist auf ihre Fundstelle; ob das Zitat dort wirklich steht, prüft die App am Originaltext. Aussagen
        ohne auffindbares Zitat sind als „ohne Beleg“ markiert. Die Einschätzungen des Modells sind Hinweise, keine
        Bewertung.
      </p>

      <p className={bereit && !status?.extern ? "ki-zeile bereit" : "ki-zeile"}>
        {status == null
          ? "Prüfe Sprachmodell …"
          : bereit
            ? status.extern
              ? `Externer Anbieter: ${status.modell} über ${status.titel}. Dokumenttexte werden dorthin übertragen.`
              : `Sprachmodell: ${status.modell} über ${status.titel}, auf diesem Gerät`
            : `Sprachmodell nicht bereit: ${status.hinweis ?? ""}`}{" "}
        <button className="link klein" onClick={onEinstellungen}>
          Einstellungen
        </button>
      </p>

      <div className="akten-wahl">
        <button
          onClick={() => starte("chronologie", { akte_id: akteId, neu: c != null })}
          disabled={!kannStarten}
        >
          {c ? "Chronologie neu erstellen" : "Chronologie erstellen"}
        </button>
        <button
          className="zweitrangig"
          onClick={() => starte("zusammenfassung_akte", { akte_id: akteId, neu: z != null })}
          disabled={!kannStarten}
        >
          {z ? "Akte neu zusammenfassen" : "Akte zusammenfassen"}
        </button>
        {(w || c || z || Object.keys(ergebnisse.dokumente).length > 0) && (
          <button
            className="zweitrangig ki-ausgeben"
            onClick={() => setAusgeben(!ausgeben)}
            aria-expanded={ausgeben}
            title="Ergebnisse mit Fundstellen als Word, PDF, Excel, Markdown oder Text speichern oder drucken"
          >
            Exportieren / Drucken …
          </button>
        )}
        <SkillWahl wert={skill} onWert={setSkill} disabled={laeuft} onEinstellungen={onSkills} />
      </div>

      {ausgeben && <KiExport akteId={akteId} ergebnisse={ergebnisse} onSchliessen={() => setAusgeben(false)} />}

      {auftrag && auftrag.status === "laeuft" && <Fortschritt auftrag={auftrag} onAbbrechen={abbrechen} />}
      {auftrag?.status === "abgebrochen" && <p className="meldung">Analyse abgebrochen.</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}

      <nav className="reiter" aria-label="Ansicht">
        {(
          [
            ["chronologie", `Chronologie${c ? ` (${c.ereignisse.length})` : ""}`],
            ["akte", "Zusammenfassung der Akte"],
            ["dokumente", "Dokumente"],
          ] as [Ansicht, string][]
        ).map(([id, titel]) => (
          <button
            key={id}
            className={id === ansicht ? "reiter-aktiv" : "zweitrangig"}
            onClick={() => setAnsicht(id)}
            disabled={id === ansicht}
          >
            {titel}
          </button>
        ))}
      </nav>

      <div className="akte-arbeitsflaeche">
        <div className="akte-haupt">
          <Zitatbereich>
          {ansicht === "chronologie" &&
            (c ? (
              <>
                <ErgebnisKopf ergebnis={c} veraltet={veraltet(c, ids)} text={chronologieText(c)} mitSchalter={false} />
                <ChronologieTabelle c={c} offen={offen} onFundstelle={oeffne} />
                <p className="grenze">
                  Die Daten stammen aus den belegten Tatsachenangaben und den Köpfen der Dokumente. „Datum ohne Beleg“
                  heißt: Das Modell nennt ein Datum, das in keinem der zitierten Absätze steht. Ereignisse ohne Datum
                  fehlen; maßgeblich sind die Fundstellen.
                </p>
              </>
            ) : (
              <p className="leer">Noch keine Chronologie dieser Akte. „Chronologie erstellen“ startet sie.</p>
            ))}

          {ansicht === "akte" &&
            (z ? (
              <>
                <ErgebnisKopf ergebnis={z} veraltet={veraltet(z, ids)} text={zaehlungText(z)} />
                <AussagenListe aussagen={z.aussagen} offen={offen} onFundstelle={oeffne} />
              </>
            ) : (
              <p className="leer">Noch keine Zusammenfassung dieser Akte. „Akte zusammenfassen“ erstellt sie.</p>
            ))}

          {ansicht === "dokumente" && (
            <div className="ki-dokumente">
              {dokumente.length === 0 && <p className="leer">Diese Akte enthält noch keine Dokumente.</p>}
              {Object.keys(ergebnisse.dokumente).length > 0 && (
                <p className="ki-herkunft">
                  <ZitateSchalter />
                </p>
              )}
              {dokumente.map((d) => {
                const zf = ergebnisse.dokumente[String(d.id)];
                return (
                  <details key={d.id} className="ki-dokument" open={zf != null && dokumente.length <= 3}>
                    <summary>
                      <strong>{d.dateiname}</strong> {zf ? (
                        <span className="leise">
                          {zaehlungText(zf)}
                          {skillText(zf) ? ` · ${skillText(zf)}` : ""}
                        </span>
                      ) : null}
                      <button
                        className="link klein"
                        disabled={!kannStarten}
                        onClick={(e) => {
                          e.preventDefault();
                          void starte("zusammenfassung_dokument", { dokument_id: d.id, neu: zf != null });
                        }}
                      >
                        {zf ? "neu zusammenfassen" : "zusammenfassen"}
                      </button>
                    </summary>
                    {zf ? (
                      <AussagenListe aussagen={zf.aussagen} offen={offen} onFundstelle={oeffne} />
                    ) : (
                      <p className="leer">Noch nicht zusammengefasst.</p>
                    )}
                  </details>
                );
              })}
            </div>
          )}
          </Zitatbereich>
        </div>
        {offen && (
          <aside className="akte-seite vergleich-dokument">
            <div className="vergleich-dokument-kopf">
              <span className="fundort">{offen.inhalt.dokument.dateiname}</span>
              <button className="zweitrangig" onClick={() => setOffen(null)}>
                Schließen
              </button>
            </div>
            <div className="vergleich-dokument-text" ref={seite}>
              <DokumentAnsicht inhalt={offen.inhalt} markiert={offen.abschnitt} />
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function chronologieText(c: KiChronologie): string {
  const streitig = c.ereignisse.filter((e) => e.streitig).length;
  const ohne = c.ereignisse.filter((e) => e.status === "ohne_beleg").length;
  return [
    `${c.ereignisse.length} ${c.ereignisse.length === 1 ? "Eintrag" : "Einträge"} aus ${c.angaben} datierten Angaben`,
    streitig ? `${streitig} streitig` : "",
    ohne ? `${ohne} mit Datum ohne Beleg` : "",
  ]
    .filter(Boolean)
    .join(", ");
}

function ChronologieTabelle({
  c,
  offen,
  onFundstelle,
}: {
  c: KiChronologie;
  offen: Offen;
  onFundstelle: (f: KiFundstelle) => void;
}) {
  if (c.ereignisse.length === 0) return <p className="leer">Das Modell hat keine datierten Ereignisse geliefert.</p>;
  return (
    <ol className="chronologie">
      {c.ereignisse.map((e, i) => (
        <li key={i} className={`ereignis-${e.art}${e.streitig ? " streitig" : ""}`}>
          {/* Mehrere Einträge am selben Tag: Datum nur beim ersten. */}
          <div className="chrono-datum">{i > 0 && c.ereignisse[i - 1].anzeige === e.anzeige ? "" : e.anzeige}</div>
          <div className="chrono-inhalt">
            <div>
              {e.art !== "ereignis" && <span className="art">{EREIGNIS_ART_TEXT[e.art]}</span>} {e.ereignis}
              {e.streitig && <span className="einordnung zwischen_parteien">streitig</span>}
              {e.status === "ohne_beleg" && <span className="ohne-beleg">Datum ohne Beleg</span>}
            </div>
            <details>
              <summary className="leise">
                {e.quellen.length} {e.quellen.length === 1 ? "Fundstelle" : "Fundstellen"}
              </summary>
              <Zitatbereich zeigen>
              <ul className="belege">
                {e.quellen.map((q, j) => (
                  <li key={j} className="chrono-quelle">
                    {q.haltung && (
                      <div className="leise">
                        {q.text} ({HALTUNG_TEXT[q.haltung] ?? q.haltung})
                      </div>
                    )}
                    <ul className="belege">
                      <FundstelleZeile f={q.fundstelle} offen={offen} onFundstelle={onFundstelle} />
                    </ul>
                  </li>
                ))}
              </ul>
              </Zitatbereich>
            </details>
          </div>
        </li>
      ))}
    </ol>
  );
}

function zaehlungText(z: KiZusammenfassung): string {
  const { belegt, ohne_beleg } = z.zaehlung;
  return `${belegt} belegte ${belegt === 1 ? "Aussage" : "Aussagen"}${ohne_beleg ? `, ${ohne_beleg} ohne Beleg` : ""}`;
}

function Fortschritt({ auftrag, onAbbrechen }: { auftrag: KiAuftrag; onAbbrechen: () => void }) {
  const anteil = auftrag.von ? Math.round(((auftrag.schritt ?? 0) / auftrag.von) * 100) : null;
  return (
    <div className="ki-fortschritt" role="status">
      <div>
        <strong>{auftrag.text}</strong> <span className="leise">· {dauerText(auftrag.sekunden)}</span>
      </div>
      {anteil != null && (
        <div className="balken" aria-label={`${anteil} %`}>
          <div style={{ width: `${anteil}%` }} />
        </div>
      )}
      <button className="zweitrangig" onClick={onAbbrechen}>
        Abbrechen
      </button>
    </div>
  );
}

function ErgebnisKopf({
  ergebnis,
  veraltet,
  text,
  mitSchalter = true,
}: {
  ergebnis: {
    modell: string;
    erstellt_am: string;
    skill?: string;
    skills?: string[];
    skill_hinweis?: string;
    teile?: number;
    luecken?: number[];
    luecken_dokumente?: { dateiname: string; absaetze: string[] }[];
  };
  veraltet: boolean;
  text: string;
  /** Die Chronologie klappt ihre Fundstellen selbst ein. */
  mitSchalter?: boolean;
}) {
  const luecken = ergebnis.luecken ?? [];
  return (
    <>
      <p className="zusammenfassung">{text}</p>
      <p className="ki-herkunft">
        Erstellt {zeitpunkt(ergebnis.erstellt_am)} mit {ergebnis.modell}
        {skillText(ergebnis) && <> · {skillText(ergebnis)}</>}
        {veraltet && <span className="hinweis"> · Die Akte hat sich seitdem geändert, bitte neu berechnen.</span>}
        {mitSchalter && (
          <>
            {" · "}
            <ZitateSchalter />
          </>
        )}
      </p>
      {luecken.length > 0 && (
        <p className="hinweis">
          Unvollständig: Teil {luecken.join(", ")} von {ergebnis.teile} hat das Modell auch beim zweiten Versuch
          unbrauchbar beantwortet. Was dort steht, fehlt hier. Das Ergebnis wurde nicht gespeichert; neu berechnen
          versucht es erneut.
        </p>
      )}
      {(ergebnis.luecken_dokumente ?? []).map((d) => (
        <p className="hinweis" key={d.dateiname}>
          Unvollständig: Aus {d.dateiname} fehlen die Angaben von Absatz {d.absaetze.join(", ")}, weil das Modell dort
          unbrauchbar geantwortet hat. Das Ergebnis wurde nicht gespeichert.
        </p>
      ))}
    </>
  );
}

export function FundstelleZeile({
  f,
  offen,
  onFundstelle,
}: {
  f: KiFundstelle;
  offen: Offen;
  onFundstelle: (f: KiFundstelle) => void;
}) {
  return (
    <Beleg
      f={f}
      gewaehlt={offen?.inhalt.dokument.id === f.dokument_id && offen.abschnitt === f.abschnitt}
      onFundstelle={() => onFundstelle(f)}
      zusatz={
        f.treffer === "angenaehert" && (
          <span className="leise" title="Das Zitat des Modells weicht leicht vom Originaltext ab; gezeigt wird das Original.">
            angenähert
          </span>
        )
      }
    />
  );
}

function AussagenListe({
  aussagen,
  offen,
  onFundstelle,
}: {
  aussagen: KiAussage[];
  offen: Offen;
  onFundstelle: (f: KiFundstelle) => void;
}) {
  if (aussagen.length === 0) return <p className="leer">Das Modell hat keine Aussagen geliefert.</p>;
  return (
    <ol className="ki-aussagen">
      {aussagen.map((a, i) => (
        <li key={i} className={a.status}>
          <div>
            <span className="art">{ART_TEXT[a.art] ?? a.art}</span> {a.text}
            {a.status === "ohne_beleg" && <span className="ohne-beleg">ohne Beleg</span>}
          </div>
          {a.fundstellen.length > 0 && (
            <ul className="belege">
              {a.fundstellen.map((f, j) => (
                <FundstelleZeile key={j} f={f} offen={offen} onFundstelle={onFundstelle} />
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

export function WiderspruchKarte({
  w,
  offen,
  onFundstelle,
}: {
  w: KiWiderspruch;
  offen: Offen;
  onFundstelle: (f: KiFundstelle) => void;
}) {
  return (
    <section className={`merkmal ${w.art === "widerspruch" ? "abweichend" : "spannung"}`}>
      <header>
        <strong>{w.thema}</strong>
        <span className="art">{w.art === "widerspruch" ? "Widerspruch" : "Spannung"}</span>
        {w.einordnung.map((e) => (
          <span key={e} className={`einordnung ${e}`}>
            {EINORDNUNG_TEXT[e]}
          </span>
        ))}
      </header>
      {w.erklaerung && <p className="ki-erklaerung">Einschätzung des Modells: {w.erklaerung}</p>}
      <div className="werte">
        {w.angaben.map((a, i) => (
          <div key={i} className="wert">
            <div className="wert-anzeige ki-angabe">
              {a.text}
              <div className="leise">{HALTUNG_TEXT[a.haltung] ?? a.haltung}</div>
            </div>
            <ul className="belege">
              <FundstelleZeile f={a.fundstelle} offen={offen} onFundstelle={onFundstelle} />
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
