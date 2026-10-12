import { FormEvent, useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { BelegAnsicht } from "./Gesetze";
import {
  Abschnitt,
  Akte as AkteTyp,
  AktenDokument,
  AktenImport,
  Beleg,
  DokumentInhalt,
  NormEintrag,
  NormZitat,
  OcrStatus,
  STATUS_TEXT,
  ZitatStatus,
  fundstelle,
  istDesktop,
  kern,
  lesartText,
  segmente,
} from "./kern";

type Ansicht = "dokument" | "normen";

interface Auswahl {
  zitat: NormZitat;
  ort: string;
  beleg: Beleg | null;
}

export default function Akte() {
  const [akten, setAkten] = useState<AkteTyp[]>([]);
  const [akteId, setAkteId] = useState<number | null>(null);
  const [neuerName, setNeuerName] = useState("");
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [inhalt, setInhalt] = useState<DokumentInhalt | null>(null);
  const [normen, setNormen] = useState<NormEintrag[] | null>(null);
  const [ansicht, setAnsicht] = useState<Ansicht>("dokument");
  const [auswahl, setAuswahl] = useState<Auswahl | null>(null);
  const [ziel, setZiel] = useState<number | null>(null);
  const [ocr, setOcr] = useState<OcrStatus | null>(null);
  const [gesetzeGeladen, setGesetzeGeladen] = useState<number | null>(null);
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

  const ladeAkten = useCallback(async () => {
    const liste = await kern<AkteTyp[]>("akten.liste");
    setAkten(liste);
    setAkteId((aktuell) => aktuell ?? liste[0]?.id ?? null);
  }, []);

  const ladeDokumente = useCallback(async (id: number) => {
    setDokumente(await kern<AktenDokument[]>("akten.dokumente", { akte_id: id }));
  }, []);

  useEffect(() => {
    if (!istDesktop) return;
    void ausfuehren("Lade Akten …", async () => {
      await ladeAkten();
      setOcr(await kern<OcrStatus>("ocr.status"));
      setGesetzeGeladen((await kern<unknown[]>("gesetze.liste")).length);
    });
  }, [ausfuehren, ladeAkten]);

  useEffect(() => {
    setInhalt(null);
    setNormen(null);
    setAuswahl(null);
    if (akteId != null) void ausfuehren("Lade Dokumente …", () => ladeDokumente(akteId));
  }, [akteId, ausfuehren, ladeDokumente]);

  // Nach dem Öffnen eines Dokuments zur gewünschten Fundstelle scrollen.
  useEffect(() => {
    if (ziel == null || !inhalt) return;
    document.getElementById(`abschnitt-${ziel}`)?.scrollIntoView({ block: "center" });
    setZiel(null);
  }, [ziel, inhalt]);

  async function anlegen(e: FormEvent) {
    e.preventDefault();
    const name = neuerName.trim();
    if (!name) return;
    await ausfuehren("Lege Akte an …", async () => {
      const a = await kern<AkteTyp>("akten.anlegen", { name });
      setNeuerName("");
      await ladeAkten();
      setAkteId(a.id);
    });
  }

  async function hinzufuegen() {
    if (akteId == null) return;
    const gewaehlt = await open({
      multiple: true,
      title: "Dokumente zur Akte hinzufügen",
      filters: [{ name: "Schriftsätze, Schreiben, Urteile", extensions: ["pdf", "docx", "txt", "md"] }],
    });
    const pfade = gewaehlt == null ? [] : Array.isArray(gewaehlt) ? gewaehlt : [gewaehlt];
    if (pfade.length === 0) return;
    const fehlschlaege: string[] = [];
    let letztes: AktenImport | null = null;
    setFehler(null);
    for (const [i, pfad] of pfade.entries()) {
      const name = pfad.split(/[\\/]/).pop() ?? pfad;
      setLaeuft(
        `Lese ${i + 1} von ${pfade.length}: ${name} … (Scans werden per Texterkennung gelesen, das dauert je Seite einige Sekunden)`,
      );
      try {
        letztes = await kern<AktenImport>("akten.importieren", { akte_id: akteId, pfad });
      } catch (e) {
        // Eine unlesbare Datei soll die übrigen nicht aufhalten.
        fehlschlaege.push(`${name}: ${String(e)}`);
      }
    }
    setLaeuft(null);
    await ausfuehren("Lade Dokumente …", async () => {
      await ladeDokumente(akteId);
      await ladeAkten();
    });
    if (letztes) await oeffneDokument(letztes.dokument_id);
    if (fehlschlaege.length > 0) setFehler(`Nicht gelesen:\n${fehlschlaege.join("\n")}`);
  }

  async function oeffneDokument(id: number, abschnitt?: number) {
    const d = await ausfuehren("Lade Dokument …", () => kern<DokumentInhalt>("akten.dokument", { dokument_id: id }));
    if (!d) return;
    setInhalt(d);
    setAnsicht("dokument");
    setAuswahl(null);
    if (abschnitt != null) setZiel(abschnitt);
  }

  async function zeigeNormen() {
    if (akteId == null) return;
    setAnsicht("normen");
    const n = await ausfuehren("Sammle Normen …", () => kern<NormEintrag[]>("akten.normen", { akte_id: akteId }));
    setNormen(n ?? null);
  }

  async function neuPruefen() {
    if (akteId == null) return;
    await ausfuehren("Prüfe Zitate gegen die Wissensbasis …", () => kern("akten.zitate_pruefen", { akte_id: akteId }));
    await ladeDokumente(akteId);
    if (inhalt) await oeffneDokument(inhalt.dokument.id);
    if (ansicht === "normen") await zeigeNormen();
  }

  async function waehleZitat(zitat: NormZitat, abschnitt: Abschnitt) {
    const ort = `${inhalt?.dokument.dateiname ?? ""}, ${fundstelle({ ...abschnitt, seite: zitat.seite ?? abschnitt.seite })}`;
    setAuswahl({ zitat, ort, beleg: null });
    // Wortlaut aus derselben Fassung, gegen die beim Einlesen geprüft wurde.
    const beleg = await ausfuehren("Lade Wortlaut …", () =>
      kern<Beleg>("zitat.aufloesen", { zitat: zitat.zitat, fassung_id: zitat.fassung_id }),
    );
    setAuswahl({ zitat, ort, beleg: beleg ?? null });
  }

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Akten lassen sich nur in der Desktop-App lesen:{" "}
        <code>npm run tauri dev</code>
      </section>
    );
  }

  const akte = akten.find((a) => a.id === akteId) ?? null;

  return (
    <div className="akte">
      <header className="kopf">
        <h1>Akte</h1>
        <div className="aktionen">
          {akte && (
            <>
              <button onClick={hinzufuegen} disabled={!!laeuft}>
                Dokumente hinzufügen …
              </button>
              {dokumente.length > 0 && (
                <button className="zweitrangig" onClick={neuPruefen} disabled={!!laeuft} title="Nach dem Laden weiterer Gesetze sinnvoll">
                  Zitate neu prüfen
                </button>
              )}
            </>
          )}
        </div>
      </header>

      <div className="akten-wahl">
        {akten.length > 0 && (
          <select value={akteId ?? ""} onChange={(e) => setAkteId(Number(e.target.value))} aria-label="Akte wählen">
            {akten.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.dokumente} Dokumente)
              </option>
            ))}
          </select>
        )}
        <form className="weiteres" onSubmit={anlegen}>
          <input
            value={neuerName}
            onChange={(e) => setNeuerName(e.target.value)}
            placeholder="Neue Akte, z. B. Brückner ./. Autohaus Rehnfeld"
            aria-label="Name der neuen Akte"
          />
          <button type="submit" className="zweitrangig" disabled={!!laeuft || !neuerName.trim()}>
            Anlegen
          </button>
        </form>
      </div>

      {ocr && !ocr.verfuegbar && (
        <p className="hinweis">Texterkennung nicht verfügbar: {ocr.hinweis} PDFs mit Text und Word-Dateien lassen sich trotzdem lesen.</p>
      )}
      {gesetzeGeladen === 0 && (
        <p className="hinweis">
          Die Wissensbasis ist noch leer. Lade unter „Gesetze“ die Voreinstellung, damit zitierte Normen geprüft werden
          können; danach hier „Zitate neu prüfen“.
        </p>
      )}
      {laeuft && <p className="status">{laeuft}</p>}
      {fehler && <p className="fehler">{fehler}</p>}

      {akte && dokumente.length === 0 && !laeuft && (
        <p className="leer">Noch keine Dokumente in dieser Akte. Füge PDF-, Word- oder Textdateien hinzu.</p>
      )}

      {dokumente.length > 0 && (
        <table className="dokumente">
          <thead>
            <tr>
              <th>Dokument</th>
              <th>Gelesen als</th>
              <th>Seiten</th>
              <th>Rn.</th>
              <th>Normzitate</th>
            </tr>
          </thead>
          <tbody>
            {dokumente.map((d) => (
              <tr key={d.id} className={inhalt?.dokument.id === d.id && ansicht === "dokument" ? "aktiv" : undefined}>
                <td>
                  <button className="link" onClick={() => oeffneDokument(d.id)}>
                    {d.dateiname}
                  </button>
                </td>
                <td>{lesartText(d)}</td>
                <td>{d.seiten ?? "–"}</td>
                <td>{d.randnummern || "–"}</td>
                <td>
                  <ZitatZaehlung zitate={d.zitate} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {dokumente.length > 0 && (
        <nav className="reiter" aria-label="Ansicht">
          <button className={ansicht === "dokument" ? "reiter-aktiv" : "zweitrangig"} onClick={() => setAnsicht("dokument")}>
            Dokument
          </button>
          <button className={ansicht === "normen" ? "reiter-aktiv" : "zweitrangig"} onClick={zeigeNormen}>
            Normen der Akte
          </button>
        </nav>
      )}

      <div className="akte-arbeitsflaeche">
        <div className="akte-haupt">
          {ansicht === "dokument" && inhalt && <DokumentAnsicht inhalt={inhalt} auswahl={auswahl} onZitat={waehleZitat} />}
          {ansicht === "dokument" && !inhalt && dokumente.length > 0 && (
            <p className="leer">Wähle oben ein Dokument, um Text und Normzitate zu sehen.</p>
          )}
          {ansicht === "normen" && normen && <NormenAnsicht normen={normen} onFundstelle={oeffneDokument} />}
        </div>
        {ansicht === "dokument" && auswahl && (
          <aside className="akte-seite">
            <p className="fundort">Zitiert in {auswahl.ort}</p>
            {auswahl.beleg ? <BelegAnsicht beleg={auswahl.beleg} /> : <p className="status">Lade Wortlaut …</p>}
          </aside>
        )}
      </div>
    </div>
  );
}

function ZitatZaehlung({ zitate }: { zitate: Partial<Record<ZitatStatus, number>> }) {
  const reihenfolge: ZitatStatus[] = ["belegt", "nicht_gefunden", "unbekanntes_gesetz"];
  const teile = reihenfolge.filter((s) => zitate[s]);
  if (teile.length === 0) return <span className="leer">keine</span>;
  return (
    <>
      {teile.map((s) => (
        <span key={s} className={`zitat-zahl ${s}`}>
          {zitate[s]} {STATUS_TEXT[s]}
        </span>
      ))}
    </>
  );
}

function DokumentAnsicht({
  inhalt,
  auswahl,
  onZitat,
}: {
  inhalt: DokumentInhalt;
  auswahl: Auswahl | null;
  onZitat: (z: NormZitat, a: Abschnitt) => void;
}) {
  const d = inhalt.dokument;
  return (
    <article className="dokument">
      <h2>{d.dateiname}</h2>
      <p className="dokument-info">
        {lesartText(d)}
        {d.seiten != null && <> · {d.seiten} Seiten</>} · SHA-256 {d.sha256.slice(0, 12)}…
      </p>
      {d.hinweise.map((h) => (
        <p key={h} className="hinweis">
          {h}
        </p>
      ))}
      {inhalt.abschnitte.map((a) => (
        <section key={a.nr} id={`abschnitt-${a.nr}`} className={`abschnitt ${a.art}`}>
          <span className="abschnitt-ort">{fundstelle(a)}</span>
          <p>
            {segmente(a.text, a.zitate).map((s, i) =>
              s.zitat ? (
                <button
                  key={i}
                  className={`zitat ${s.zitat.status}${auswahl?.zitat === s.zitat ? " gewaehlt" : ""}`}
                  title={`${s.zitat.zitat}: ${STATUS_TEXT[s.zitat.status]}${s.zitat.hinweis ? ` – ${s.zitat.hinweis}` : ""}`}
                  onClick={() => onZitat(s.zitat!, a)}
                >
                  {s.text}
                </button>
              ) : (
                <span key={i}>{s.text}</span>
              ),
            )}
          </p>
        </section>
      ))}
    </article>
  );
}

function NormenAnsicht({
  normen,
  onFundstelle,
}: {
  normen: NormEintrag[];
  onFundstelle: (dokumentId: number, abschnitt: number) => void;
}) {
  if (normen.length === 0) return <p className="leer">In dieser Akte wurden keine Normzitate erkannt.</p>;
  return (
    <ul className="normen">
      {normen.map((n) => (
        <li key={n.zitat} className={n.status}>
          <div>
            <span className={`marke-status ${n.status}`}>{STATUS_TEXT[n.status]}</span> <strong>{n.zitat}</strong>
            {n.titel && <span className="titel"> – {n.titel}</span>}
          </div>
          {n.status !== "belegt" && n.hinweis && <div className="hinweis">{n.hinweis}</div>}
          <div className="fundstellen">
            {n.fundstellen.map((f, i) => (
              <button key={i} className="link" onClick={() => onFundstelle(f.dokument_id, f.abschnitt)}>
                {f.dateiname}, {fundstelle(f)}
              </button>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}
