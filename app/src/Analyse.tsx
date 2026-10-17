import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from "react";
import { DokumentAnsicht } from "./Akte";
import {
  ART_TEXT,
  Akte as AkteTyp,
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
  fundstelle,
  istDesktop,
  kern,
  veraltet,
  zeitpunkt,
} from "./kern";

type Ansicht = "widersprueche" | "chronologie" | "akte" | "dokumente";
export type Offen = { inhalt: DokumentInhalt; abschnitt: number } | null;

const LEER: KiErgebnisse = { zusammenfassung_akte: null, widersprueche: null, chronologie: null, dokumente: {} };

/** Zusammenfassungen und inhaltliche Widersprüche mit dem lokalen Sprachmodell, jede Aussage mit Fundstelle. */
export default function Analyse({
  akteId,
  setAkteId,
  onEinstellungen,
}: {
  akteId: number | null;
  setAkteId: Dispatch<SetStateAction<number | null>>;
  onEinstellungen: () => void;
}) {
  const [akten, setAkten] = useState<AkteTyp[]>([]);
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [status, setStatus] = useState<KiStatus | null>(null);
  const [ergebnisse, setErgebnisse] = useState<KiErgebnisse>(LEER);
  const [auftrag, setAuftrag] = useState<KiAuftrag | null>(null);
  const [ansicht, setAnsicht] = useState<Ansicht>("widersprueche");
  const [offen, setOffen] = useState<Offen>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const seite = useRef<HTMLDivElement>(null);

  const ladeErgebnisse = useCallback(async (id: number) => {
    setErgebnisse(await kern<KiErgebnisse>("ki.ergebnisse", { akte_id: id }));
  }, []);

  useEffect(() => {
    if (!istDesktop) return;
    void (async () => {
      try {
        const liste = await kern<AkteTyp[]>("akten.liste");
        setAkten(liste);
        setAkteId((a) => (a != null && liste.some((x) => x.id === a) ? a : (liste[0]?.id ?? null)));
        setAuftrag(await kern<KiAuftrag | null>("ki.laufend"));
        setStatus(await kern<KiStatus>("ki.status"));
      } catch (e) {
        setFehler(String(e));
      }
    })();
  }, [setAkteId]);

  useEffect(() => {
    setErgebnisse(LEER);
    setDokumente([]);
    setOffen(null);
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
  useEffect(() => {
    if (!laeuft || !auftrag) return;
    const id = auftrag.auftrag_id;
    const takt = window.setInterval(async () => {
      try {
        const stand = await kern<KiAuftrag>("ki.auftrag", { auftrag_id: id });
        setAuftrag(stand);
        if (stand.status === "fehler") setFehler(stand.fehler);
        if (stand.status !== "laeuft" && akteId != null) await ladeErgebnisse(akteId);
      } catch (e) {
        setFehler(String(e));
        setAuftrag(null);
      }
    }, 1000);
    return () => window.clearInterval(takt);
  }, [laeuft, auftrag?.auftrag_id, akteId, ladeErgebnisse]);

  async function starte(aufgabe: KiAufgabe, params: Record<string, unknown>) {
    setFehler(null);
    try {
      setAuftrag(await kern<KiAuftrag>("ki.starten", { aufgabe, ...params }));
      if (aufgabe === "widersprueche") setAnsicht("widersprueche");
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
      <header className="kopf">
        <h1>Analyse</h1>
      </header>
      <p className="erklaerung">
        Fasst Dokumente und die Akte zusammen, sucht inhaltliche Widersprüche und erstellt eine Chronologie mit dem
        gewählten Sprachmodell. Jede
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
        {akten.length > 0 ? (
          <select value={akteId ?? ""} onChange={(e) => setAkteId(Number(e.target.value))} aria-label="Akte wählen">
            {akten.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.dokumente} Dokumente)
              </option>
            ))}
          </select>
        ) : (
          <p className="leer">Noch keine Akte. Lege unter „Akte“ eine an und füge Dokumente hinzu.</p>
        )}
        <button onClick={() => starte("widersprueche", { akte_id: akteId, neu: w != null })} disabled={!kannStarten}>
          {w ? "Widersprüche neu suchen" : "Widersprüche suchen"}
        </button>
        <button
          className="zweitrangig"
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
      </div>

      {auftrag && auftrag.status === "laeuft" && <Fortschritt auftrag={auftrag} onAbbrechen={abbrechen} />}
      {auftrag?.status === "abgebrochen" && <p className="meldung">Analyse abgebrochen.</p>}
      {fehler && <p className="fehler">{fehler}</p>}

      <nav className="reiter" aria-label="Ansicht">
        {(
          [
            ["widersprueche", `Widersprüche${w ? ` (${w.widersprueche.length})` : ""}`],
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
          {ansicht === "widersprueche" &&
            (w ? (
              <>
                <ErgebnisKopf
                  ergebnis={w}
                  veraltet={veraltet(w, ids)}
                  text={`${w.widersprueche.length} ${w.widersprueche.length === 1 ? "möglicher Widerspruch" : "mögliche Widersprüche"} aus ${w.angaben} belegten Tatsachenangaben${
                    w.verworfen ? ` (${w.verworfen} Angaben ohne auffindbares Zitat verworfen)` : ""
                  }`}
                />
                {w.widersprueche.length === 0 && <p className="leer">Keine inhaltlichen Widersprüche gefunden.</p>}
                {w.widersprueche.map((x, i) => (
                  <WiderspruchKarte key={i} w={x} offen={offen} onFundstelle={oeffne} />
                ))}
                <p className="grenze">
                  Daten, Beträge und Kilometerstände gleicht der Bereich „Vergleich“ regelbasiert ab. Hier stehen
                  zusätzlich Widersprüche, die sich nicht in Zahlen zeigen. Das Modell kann Widersprüche übersehen oder
                  Angaben falsch verstehen; maßgeblich sind die Fundstellen.
                </p>
              </>
            ) : (
              <p className="leer">Noch keine Suche für diese Akte mit diesem Modell. „Widersprüche suchen“ startet sie.</p>
            ))}

          {ansicht === "chronologie" &&
            (c ? (
              <>
                <ErgebnisKopf ergebnis={c} veraltet={veraltet(c, ids)} text={chronologieText(c)} />
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
              {dokumente.map((d) => {
                const zf = ergebnisse.dokumente[String(d.id)];
                return (
                  <details key={d.id} className="ki-dokument" open={zf != null && dokumente.length <= 3}>
                    <summary>
                      <strong>{d.dateiname}</strong> {zf ? <span className="leise">{zaehlungText(zf)}</span> : null}
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
}: {
  ergebnis: {
    modell: string;
    erstellt_am: string;
    teile?: number;
    luecken?: number[];
    luecken_dokumente?: { dateiname: string; absaetze: string[] }[];
  };
  veraltet: boolean;
  text: string;
}) {
  const luecken = ergebnis.luecken ?? [];
  return (
    <>
      <p className="zusammenfassung">{text}</p>
      <p className="ki-herkunft">
        Erstellt {zeitpunkt(ergebnis.erstellt_am)} mit {ergebnis.modell}
        {veraltet && <span className="hinweis"> · Die Akte hat sich seitdem geändert, bitte neu berechnen.</span>}
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
  const gewaehlt = offen?.inhalt.dokument.id === f.dokument_id && offen.abschnitt === f.abschnitt;
  return (
    <li className={gewaehlt ? "gewaehlt" : undefined}>
      <button className="link" onClick={() => onFundstelle(f)} title="Dokument an dieser Stelle öffnen">
        {f.dateiname}, {fundstelle(f)}
      </button>
      {f.parteien.map((p) => (
        <span key={p} className="tag">
          {p}
        </span>
      ))}
      {f.treffer === "angenaehert" && (
        <span className="leise" title="Das Zitat des Modells weicht leicht vom Originaltext ab; gezeigt wird das Original.">
          angenähert
        </span>
      )}
      <div className="ausschnitt">
        {f.ausschnitt.davor}
        <mark>{f.ausschnitt.wert}</mark>
        {f.ausschnitt.danach}
      </div>
    </li>
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

function WiderspruchKarte({
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
