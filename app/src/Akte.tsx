import { Dispatch, FormEvent, SetStateAction, useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { BelegAnsicht } from "./Gesetze";
import {
  Abschnitt,
  Akte as AkteTyp,
  AktenDokument,
  AktenImport,
  BETEILIGTE,
  Beleg,
  DokumentInhalt,
  Loeschergebnis,
  NormEintrag,
  NormZitat,
  OcrStatus,
  OrdnerFunde,
  STATUS_TEXT,
  ZitatStatus,
  fundstelle,
  istDesktop,
  kern,
  lesartText,
  segmente,
  sortiereTags,
  tagUebersicht,
  tagsAusText,
} from "./kern";

type Ansicht = "dokument" | "normen";

/** Eine einzulesende Datei, beim Ordner-Import mit Unterordner und bestätigten Tags. */
interface Einzulesen {
  pfad: string;
  name: string;
  tags?: string[];
  herkunft?: string;
}

/** Rückfrage vor dem Ordner-Import: Tags je Unterordner, vom Nutzer änderbar. */
interface OrdnerFrage {
  funde: OrdnerFunde;
  tags: Record<string, string>;
}

type Loeschfrage = { art: "akte"; id: number } | { art: "dokument"; id: number };

interface Auswahl {
  zitat: NormZitat;
  ort: string;
  beleg: Beleg | null;
}

export default function Akte({
  akteId,
  setAkteId,
  onVergleich,
}: {
  akteId: number | null;
  setAkteId: Dispatch<SetStateAction<number | null>>;
  onVergleich: () => void;
}) {
  const [akten, setAkten] = useState<AkteTyp[]>([]);
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
  const [meldung, setMeldung] = useState<string | null>(null);
  const [ordnerFrage, setOrdnerFrage] = useState<OrdnerFrage | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<Loeschfrage | null>(null);
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [tagEdit, setTagEdit] = useState<{ id: number; text: string } | null>(null);

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
    setAkteId((aktuell) => (aktuell != null && liste.some((a) => a.id === aktuell) ? aktuell : (liste[0]?.id ?? null)));
  }, [setAkteId]);

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
    setTagFilter(null);
    setTagEdit(null);
    setOrdnerFrage(null);
    setLoeschfrage(null);
    if (akteId == null) setDokumente([]);
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
    await einlesen(pfade.map((pfad) => ({ pfad, name: pfad.split(/[\\/]/).pop() ?? pfad })));
  }

  async function ordnerHinzufuegen() {
    if (akteId == null) return;
    const gewaehlt = await open({ directory: true, title: "Ordner mit Unterordnern zur Akte hinzufügen" });
    if (typeof gewaehlt !== "string") return;
    const funde = await ausfuehren("Durchsuche Ordner …", () => kern<OrdnerFunde>("akten.ordner_pruefen", { pfad: gewaehlt }));
    if (!funde) return;
    if (funde.dateien.length === 0) {
      setFehler(`Im Ordner „${funde.name}“ liegen keine PDF-, Word- oder Textdateien.`);
      return;
    }
    // Ohne Vorschläge gibt es nichts zu fragen; sonst erst bestätigen lassen, welche Tags übernommen werden.
    if (funde.unterordner.every((u) => u.tags.length === 0)) {
      await einlesen(funde.dateien.map((d) => ({ pfad: d.pfad, name: d.relativ, herkunft: d.herkunft })));
      return;
    }
    setOrdnerFrage({ funde, tags: Object.fromEntries(funde.unterordner.map((u) => [u.herkunft, u.tags.join(", ")])) });
  }

  async function ordnerEinlesen(mitTags: boolean) {
    if (!ordnerFrage) return;
    const { funde, tags } = ordnerFrage;
    setOrdnerFrage(null);
    await einlesen(
      funde.dateien.map((d) => ({
        pfad: d.pfad,
        name: d.relativ,
        herkunft: d.herkunft,
        tags: mitTags ? tagsAusText(tags[d.herkunft] ?? "") : [],
      })),
    );
  }

  async function einlesen(dateien: Einzulesen[]) {
    if (akteId == null || dateien.length === 0) return;
    const fehlschlaege: string[] = [];
    let letztes: AktenImport | null = null;
    let schonDa = 0;
    setFehler(null);
    setMeldung(null);
    for (const [i, d] of dateien.entries()) {
      setLaeuft(
        `Lese ${i + 1} von ${dateien.length}: ${d.name} … (Scans werden per Texterkennung gelesen, das dauert je Seite einige Sekunden)`,
      );
      try {
        letztes = await kern<AktenImport>("akten.importieren", {
          akte_id: akteId,
          pfad: d.pfad,
          tags: d.tags ?? null,
          herkunft: d.herkunft ?? null,
        });
        if (!letztes.neu) schonDa += 1;
      } catch (e) {
        // Eine unlesbare Datei soll die übrigen nicht aufhalten.
        fehlschlaege.push(`${d.name}: ${String(e)}`);
      }
    }
    setLaeuft(null);
    await ausfuehren("Lade Dokumente …", async () => {
      await ladeDokumente(akteId);
      await ladeAkten();
    });
    if (dateien.length === 1 && letztes) await oeffneDokument(letztes.dokument_id);
    const gelesen = dateien.length - fehlschlaege.length;
    if (dateien.length > 1)
      setMeldung(
        `${gelesen} von ${dateien.length} Dateien übernommen` +
          (schonDa ? `, davon ${schonDa} schon in der Akte (nur Tags ergänzt).` : "."),
      );
    if (fehlschlaege.length > 0) setFehler(`Nicht gelesen:\n${fehlschlaege.join("\n")}`);
  }

  async function loeschen() {
    if (!loeschfrage) return;
    const frage = loeschfrage;
    setLoeschfrage(null);
    setMeldung(null);
    const methode = frage.art === "akte" ? "akten.loeschen" : "akten.dokument_loeschen";
    const params = frage.art === "akte" ? { akte_id: frage.id } : { dokument_id: frage.id };
    const ergebnis = await ausfuehren("Entferne …", () => kern<Loeschergebnis>(methode, params));
    if (!ergebnis) return;
    if (frage.art === "dokument" && inhalt?.dokument.id === frage.id) {
      setInhalt(null);
      setAuswahl(null);
    }
    await ausfuehren("Lade Akten …", async () => {
      await ladeAkten();
      if (frage.art === "dokument" && akteId != null) await ladeDokumente(akteId);
    });
    if (ansicht === "normen" && frage.art === "dokument") await zeigeNormen();
    setMeldung(`„${ergebnis.name ?? ergebnis.dateiname}“ wurde entfernt.${ergebnis.hinweis ? ` ${ergebnis.hinweis}` : ""}`);
  }

  async function tagsSpeichern(dokumentId: number, tags: string[]) {
    await ausfuehren("Speichere Tags …", () => kern("akten.tags_setzen", { dokument_id: dokumentId, tags }));
    setTagEdit(null);
    if (akteId != null) await ladeDokumente(akteId);
    if (inhalt?.dokument.id === dokumentId) await oeffneDokument(dokumentId);
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
  const tags = tagUebersicht(dokumente);
  const ohneTag = dokumente.filter((d) => d.tags.length === 0).length;
  const sichtbar =
    tagFilter == null
      ? dokumente
      : dokumente.filter((d) => (tagFilter === "" ? d.tags.length === 0 : d.tags.some((t) => t.name === tagFilter)));

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
              <button onClick={ordnerHinzufuegen} disabled={!!laeuft} title="Liest auch alle Unterordner ein">
                Ordner hinzufügen …
              </button>
              {dokumente.length > 1 && (
                <button className="zweitrangig" onClick={onVergleich} disabled={!!laeuft} title="Angaben der Dokumente gegenüberstellen">
                  Abgleichen
                </button>
              )}
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
          <select value={akteId ?? ""} onChange={(e) => {
              setMeldung(null);
              setAkteId(Number(e.target.value));
            }} aria-label="Akte wählen">
            {akten.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.dokumente} Dokumente)
              </option>
            ))}
          </select>
        )}
        {akte && (
          <button className="zweitrangig gefahr" onClick={() => setLoeschfrage({ art: "akte", id: akte.id })} disabled={!!laeuft}>
            Akte entfernen …
          </button>
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
      {loeschfrage && (
        <Rueckfrage
          frage={
            loeschfrage.art === "akte"
              ? `Akte „${akte?.name}“ mit ${akte?.dokumente ?? 0} Dokumenten entfernen?`
              : `Dokument „${dokumente.find((d) => d.id === loeschfrage.id)?.dateiname}“ aus der Akte entfernen?`
          }
          erklaerung={
            "Entfernt werden der gelesene Text, die Normzitate, die Tags und die Kopie, die die App beim Einlesen " +
            "abgelegt hat. Deine Originaldatei am ursprünglichen Ort bleibt unverändert."
          }
          ja="Entfernen"
          onJa={loeschen}
          onNein={() => setLoeschfrage(null)}
        />
      )}
      {ordnerFrage && (
        <OrdnerRueckfrage
          frage={ordnerFrage}
          onTags={(herkunft, text) => setOrdnerFrage({ ...ordnerFrage, tags: { ...ordnerFrage.tags, [herkunft]: text } })}
          onEinlesen={ordnerEinlesen}
          onAbbrechen={() => setOrdnerFrage(null)}
        />
      )}
      {laeuft && <p className="status">{laeuft}</p>}
      {meldung && !laeuft && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler">{fehler}</p>}

      {akte && dokumente.length === 0 && !laeuft && (
        <p className="leer">Noch keine Dokumente in dieser Akte. Füge PDF-, Word- oder Textdateien hinzu.</p>
      )}

      {tags.length > 0 && (
        <div className="tag-filter" role="group" aria-label="Nach Tag filtern">
          <button className={tagFilter == null ? "tag-wahl aktiv" : "tag-wahl"} onClick={() => setTagFilter(null)}>
            Alle ({dokumente.length})
          </button>
          {tags.map((t) => (
            <button
              key={t.name}
              className={tagFilter === t.name ? "tag-wahl aktiv" : "tag-wahl"}
              onClick={() => setTagFilter(tagFilter === t.name ? null : t.name)}
            >
              {t.name} ({t.anzahl})
            </button>
          ))}
          {ohneTag > 0 && (
            <button className={tagFilter === "" ? "tag-wahl aktiv" : "tag-wahl"} onClick={() => setTagFilter(tagFilter === "" ? null : "")}>
              ohne Tag ({ohneTag})
            </button>
          )}
        </div>
      )}

      {dokumente.length > 0 && (
        <table className="dokumente">
          <thead>
            <tr>
              <th>Dokument</th>
              <th>Beteiligte / Tags</th>
              <th>Gelesen als</th>
              <th>Seiten</th>
              <th>Rn.</th>
              <th>Normzitate</th>
              <th>
                <span className="unsichtbar">Aktionen</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sichtbar.map((d) => (
              <tr key={d.id} className={inhalt?.dokument.id === d.id && ansicht === "dokument" ? "aktiv" : undefined}>
                <td>
                  <button className="link" onClick={() => oeffneDokument(d.id)}>
                    {d.dateiname}
                  </button>
                  {d.herkunft && <div className="herkunft">{d.herkunft}</div>}
                </td>
                <td>
                  {tagEdit?.id === d.id ? (
                    <TagEditor
                      text={tagEdit.text}
                      onText={(text) => setTagEdit({ id: d.id, text })}
                      onSpeichern={() => tagsSpeichern(d.id, tagsAusText(tagEdit.text))}
                      onAbbrechen={() => setTagEdit(null)}
                    />
                  ) : (
                    <div className="tags">
                      {sortiereTags(d.tags).map((t) => (
                        <span
                          key={t.name}
                          className={`tag ${t.quelle}`}
                          title={t.quelle === "ordner" ? "Aus dem Ordnernamen übernommen" : "Von Hand gesetzt"}
                        >
                          {t.name}
                        </span>
                      ))}
                      <button
                        className="link klein"
                        onClick={() => setTagEdit({ id: d.id, text: d.tags.map((t) => t.name).join(", ") })}
                        disabled={!!laeuft}
                      >
                        {d.tags.length ? "ändern" : "+ Tag"}
                      </button>
                    </div>
                  )}
                </td>
                <td>{lesartText(d)}</td>
                <td>{d.seiten ?? "–"}</td>
                <td>{d.randnummern || "–"}</td>
                <td>
                  <ZitatZaehlung zitate={d.zitate} />
                </td>
                <td>
                  <button
                    className="link klein gefahr"
                    onClick={() => setLoeschfrage({ art: "dokument", id: d.id })}
                    disabled={!!laeuft}
                    title="Dokument aus der Akte entfernen"
                  >
                    entfernen
                  </button>
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

function Rueckfrage({
  frage,
  erklaerung,
  ja,
  onJa,
  onNein,
}: {
  frage: string;
  erklaerung: string;
  ja: string;
  onJa: () => void;
  onNein: () => void;
}) {
  return (
    <div className="rueckfrage" role="alertdialog" aria-label={frage}>
      <strong>{frage}</strong>
      <p>{erklaerung}</p>
      <div className="aktionen">
        <button className="gefahr-voll" onClick={onJa}>
          {ja}
        </button>
        <button className="zweitrangig" onClick={onNein} autoFocus>
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function OrdnerRueckfrage({
  frage,
  onTags,
  onEinlesen,
  onAbbrechen,
}: {
  frage: OrdnerFrage;
  onTags: (herkunft: string, text: string) => void;
  onEinlesen: (mitTags: boolean) => void;
  onAbbrechen: () => void;
}) {
  const { funde } = frage;
  return (
    <div className="rueckfrage" role="dialog" aria-label="Ordner einlesen">
      <strong>
        Ordner „{funde.name}“: {funde.dateien.length} Dateien in {funde.unterordner.length}{" "}
        {funde.unterordner.length === 1 ? "Ordner" : "Ordnern"}
      </strong>
      <p>
        Aus den Ordnernamen lassen sich Tags ableiten, die zeigen, zu welchem Beteiligten ein Dokument gehört. Sollen sie
        übernommen werden? Du kannst die Vorschläge hier anpassen (mehrere mit Komma trennen) und später jederzeit ändern.
      </p>
      <table className="dokumente">
        <thead>
          <tr>
            <th>Ordner</th>
            <th>Dateien</th>
            <th>Tags</th>
          </tr>
        </thead>
        <tbody>
          {funde.unterordner.map((u) => (
            <tr key={u.herkunft}>
              <td>{u.herkunft || <span className="leer">(oberste Ebene)</span>}</td>
              <td>{u.dateien}</td>
              <td>
                <input
                  className="tag-eingabe"
                  value={frage.tags[u.herkunft] ?? ""}
                  onChange={(e) => onTags(u.herkunft, e.target.value)}
                  placeholder="kein Tag"
                  aria-label={`Tags für ${u.herkunft || "oberste Ebene"}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {funde.uebersprungen.length > 0 && (
        <p className="hinweis" title={funde.uebersprungen.join("\n")}>
          {funde.uebersprungen.length} Dateien in anderen Formaten werden übersprungen (z. B. {funde.uebersprungen[0]}).
        </p>
      )}
      <div className="aktionen">
        <button onClick={() => onEinlesen(true)}>Mit diesen Tags einlesen</button>
        <button className="zweitrangig" onClick={() => onEinlesen(false)}>
          Ohne Tags einlesen
        </button>
        <button className="zweitrangig" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function TagEditor({
  text,
  onText,
  onSpeichern,
  onAbbrechen,
}: {
  text: string;
  onText: (t: string) => void;
  onSpeichern: () => void;
  onAbbrechen: () => void;
}) {
  const gesetzt = tagsAusText(text);
  const ergaenze = (name: string) => onText(tagsAusText(`${text}, ${name}`).join(", "));
  return (
    <form
      className="tag-editor"
      onSubmit={(e) => {
        e.preventDefault();
        onSpeichern();
      }}
    >
      <input
        className="tag-eingabe"
        value={text}
        onChange={(e) => onText(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onAbbrechen()}
        placeholder="z. B. Kläger, Anlage K 1"
        aria-label="Tags, mit Komma getrennt"
        autoFocus
      />
      <div className="tags">
        {BETEILIGTE.filter((b) => !gesetzt.includes(b)).map((b) => (
          <button key={b} type="button" className="tag-wahl" onClick={() => ergaenze(b)}>
            + {b}
          </button>
        ))}
      </div>
      <div className="aktionen">
        <button type="submit">Speichern</button>
        <button type="button" className="zweitrangig" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </div>
    </form>
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

export function DokumentAnsicht({
  inhalt,
  auswahl = null,
  onZitat,
  markiert,
}: {
  inhalt: DokumentInhalt;
  auswahl?: Auswahl | null;
  /** Ohne Handler werden Normzitate nur markiert, nicht anklickbar. */
  onZitat?: (z: NormZitat, a: Abschnitt) => void;
  /** Abschnitt, der hervorgehoben wird (Fundstelle aus dem Vergleich). */
  markiert?: number;
}) {
  const d = inhalt.dokument;
  return (
    <article className="dokument">
      <h2>{d.dateiname}</h2>
      <p className="dokument-info">
        {lesartText(d)}
        {d.seiten != null && <> · {d.seiten} Seiten</>} · SHA-256 {d.sha256.slice(0, 12)}…
        {d.herkunft && <> · Ordner {d.herkunft}</>}
      </p>
      {d.tags.length > 0 && (
        <div className="tags">
          {sortiereTags(d.tags).map((t) => (
            <span key={t.name} className={`tag ${t.quelle}`}>
              {t.name}
            </span>
          ))}
        </div>
      )}
      {d.hinweise.map((h) => (
        <p key={h} className="hinweis">
          {h}
        </p>
      ))}
      {inhalt.abschnitte.map((a) => (
        <section key={a.nr} id={`abschnitt-${a.nr}`} className={`abschnitt ${a.art}${a.nr === markiert ? " markiert" : ""}`}>
          <span className="abschnitt-ort">{fundstelle(a)}</span>
          <p>
            {segmente(a.text, a.zitate).map((s, i) =>
              s.zitat ? (
                <button
                  key={i}
                  className={`zitat ${s.zitat.status}${auswahl?.zitat === s.zitat ? " gewaehlt" : ""}`}
                  title={`${s.zitat.zitat}: ${STATUS_TEXT[s.zitat.status]}${s.zitat.hinweis ? ` – ${s.zitat.hinweis}` : ""}`}
                  onClick={() => onZitat?.(s.zitat!, a)}
                  disabled={!onZitat}
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
