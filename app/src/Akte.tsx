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
  URTEIL_QUELLEN,
  URTEIL_STATUS_TEXT,
  URTEIL_TEILE,
  UrteilEintrag,
  UrteilInfo,
  UrteilVolltext,
  ZitatStatus,
  fundstelle,
  istDesktop,
  kern,
  lesartText,
  segmente,
  sortiereTags,
  tagUebersicht,
  tagsAusText,
  rnHinweis,
  urteilHerkunft,
} from "./kern";

type Ansicht = "dokument" | "normen" | "rechtsprechung";

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

type Loeschfrage = { art: "akte"; id: number } | { art: "dokument"; id: number } | { art: "urteil"; id: number; name: string };

/** Angaben zu einer Entscheidung, die aus einer eigenen Datei ergänzt wird. */
interface Ergaenzung {
  pfad: string;
  name: string;
  zitat: string;
  gericht: string;
  aktenzeichen: string;
  datum: string;
  herkunft: string;
}

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
  const [urteile, setUrteile] = useState<UrteilEintrag[] | null>(null);
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
  const [ergaenzung, setErgaenzung] = useState<Ergaenzung | null>(null);
  const [volltext, setVolltext] = useState<UrteilVolltext | null>(null);
  const [volltextRn, setVolltextRn] = useState<number | null>(null);

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
    setUrteile(null);
    setAuswahl(null);
    setTagFilter(null);
    setTagEdit(null);
    setOrdnerFrage(null);
    setLoeschfrage(null);
    setErgaenzung(null);
    setVolltext(null);
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
    if (frage.art === "urteil") {
      const weg = await ausfuehren("Entferne …", () => kern<Loeschergebnis>("akten.urteil_entfernen", { urteil_id: frage.id }));
      if (!weg) return;
      if (volltext?.id === frage.id) setVolltext(null);
      await zeigeRechtsprechung();
      setMeldung(`„${frage.name}“ wurde aus der Akte entfernt.${weg.hinweis ? ` ${weg.hinweis}` : ""}`);
      return;
    }
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

  async function zeigeRechtsprechung() {
    if (akteId == null) return;
    setAnsicht("rechtsprechung");
    const u = await ausfuehren("Sammle Rechtsprechung …", () =>
      kern<UrteilEintrag[]>("akten.rechtsprechung", { akte_id: akteId }),
    );
    setUrteile(u ?? null);
  }

  async function urteilWaehlen(u: UrteilEintrag) {
    const gewaehlt = await open({
      title: `Volltext zu „${u.zitat}“ ergänzen`,
      filters: [{ name: "Entscheidung (PDF, Word, Text)", extensions: ["pdf", "docx", "txt", "md"] }],
    });
    if (typeof gewaehlt !== "string") return;
    const name = gewaehlt.split(/[\\/]/).pop() ?? gewaehlt;
    // Quelle aus dem Dateinamen vorschlagen, wenn er sie nennt (z. B. „juris_BGH_VIII_ZR_999-20.pdf“).
    const herkunft = URTEIL_QUELLEN.find((q) => name.toLowerCase().includes(q.toLowerCase().split(" ")[0])) ?? "";
    setErgaenzung({
      pfad: gewaehlt,
      name,
      zitat: u.zitat,
      gericht: u.gericht,
      aktenzeichen: u.aktenzeichen ?? "",
      datum: u.datum ?? "",
      herkunft,
    });
  }

  async function ergaenzungSpeichern() {
    if (akteId == null || !ergaenzung) return;
    const e = ergaenzung;
    const ergebnis = await ausfuehren(`Lese ${e.name} …`, () =>
      kern<{ urteil_id: number; neu: boolean }>("akten.urteil_ergaenzen", {
        akte_id: akteId,
        pfad: e.pfad,
        gericht: e.gericht,
        aktenzeichen: e.aktenzeichen || null,
        datum: e.datum || null,
        zitat: e.zitat,
        herkunft: e.herkunft || null,
      }),
    );
    if (!ergebnis) return;
    setErgaenzung(null);
    setMeldung(ergebnis.neu ? `${e.name} zur Akte abgelegt.` : `${e.name} liegt schon bei dieser Akte.`);
    await zeigeRechtsprechung();
    await zeigeVolltext(ergebnis.urteil_id);
  }

  async function zeigeVolltext(urteilId: number, rn?: number) {
    setVolltextRn(rn ?? null);
    if (volltext?.id === urteilId) return;
    const v = await ausfuehren("Lade Volltext …", () => kern<UrteilVolltext>("akten.urteil", { urteil_id: urteilId }));
    setVolltext(v ?? null);
  }

  async function volltexteLaden() {
    if (akteId == null) return;
    const e = await ausfuehren("Lade Volltexte von rechtsprechung-im-internet.de …", () =>
      kern<{ geladen: string[]; fehler: { zitat: string; fehler: string }[] }>("akten.volltexte_laden", { akte_id: akteId }),
    );
    if (!e) return;
    await zeigeRechtsprechung();
    setMeldung(
      `${e.geladen.length} ${e.geladen.length === 1 ? "Volltext" : "Volltexte"} geladen.` +
        (e.fehler.length ? ` Nicht geladen: ${e.fehler.map((f) => `${f.zitat} (${f.fehler})`).join("; ")}` : ""),
    );
  }

  async function neuPruefen() {
    if (akteId == null) return;
    await ausfuehren("Prüfe Zitate gegen die Wissensbasis …", () => kern("akten.zitate_pruefen", { akte_id: akteId }));
    await ladeDokumente(akteId);
    if (inhalt) await oeffneDokument(inhalt.dokument.id);
    if (ansicht === "normen") await zeigeNormen();
    if (ansicht === "rechtsprechung") await zeigeRechtsprechung();
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
              : loeschfrage.art === "urteil"
                ? `Ergänztes Urteil „${loeschfrage.name}“ aus der Akte entfernen?`
                : `Dokument „${dokumente.find((d) => d.id === loeschfrage.id)?.dateiname}“ aus der Akte entfernen?`
          }
          erklaerung={
            loeschfrage.art === "urteil"
              ? "Entfernt werden der gelesene Text und die Kopie, die die App abgelegt hat. Deine Datei am " +
                "ursprünglichen Ort bleibt unverändert."
              : "Entfernt werden der gelesene Text, die Normzitate, die Tags und die Kopie, die die App beim Einlesen " +
                "abgelegt hat. Deine Originaldatei am ursprünglichen Ort bleibt unverändert."
          }
          ja="Entfernen"
          onJa={loeschen}
          onNein={() => setLoeschfrage(null)}
        />
      )}
      {ergaenzung && (
        <ErgaenzungsFrage
          ergaenzung={ergaenzung}
          onAendern={(felder) => setErgaenzung({ ...ergaenzung, ...felder })}
          onSpeichern={ergaenzungSpeichern}
          onAbbrechen={() => setErgaenzung(null)}
          laeuft={!!laeuft}
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
          <button className={ansicht === "rechtsprechung" ? "reiter-aktiv" : "zweitrangig"} onClick={zeigeRechtsprechung}>
            Rechtsprechung der Akte
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
          {ansicht === "rechtsprechung" && urteile && (
            <RechtsprechungAnsicht
              urteile={urteile}
              offen={volltext?.id ?? null}
              laeuft={!!laeuft}
              onFundstelle={oeffneDokument}
              onErgaenzen={urteilWaehlen}
              onVolltexteLaden={volltexteLaden}
              onVolltext={(id, rn) => (volltext?.id === id && rn == null ? setVolltext(null) : zeigeVolltext(id, rn))}
              onEntfernen={(u) => setLoeschfrage({ art: "urteil", id: u.id, name: urteilHerkunft(u) })}
            />
          )}
        </div>
        {ansicht === "rechtsprechung" && volltext && (
          <VolltextAnsicht volltext={volltext} rn={volltextRn} onSchliessen={() => setVolltext(null)} />
        )}
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

function RechtsprechungAnsicht({
  urteile,
  offen,
  laeuft,
  onFundstelle,
  onErgaenzen,
  onVolltexteLaden,
  onVolltext,
  onEntfernen,
}: {
  urteile: UrteilEintrag[];
  offen: number | null;
  laeuft: boolean;
  onFundstelle: (dokumentId: number, abschnitt: number) => void;
  onErgaenzen: (u: UrteilEintrag) => void;
  onVolltexteLaden: () => void;
  onVolltext: (urteilId: number, rn?: number) => void;
  onEntfernen: (u: UrteilInfo) => void;
}) {
  const [kopiert, setKopiert] = useState<string | null>(null);
  if (urteile.length === 0) return <p className="leer">In dieser Akte wurden keine Rechtsprechungszitate erkannt.</p>;
  const ohneVerzeichnis = urteile.some((u) => u.status === "kein_verzeichnis");
  const ladbar = urteile.filter((u) => u.status === "belegt" && !u.urteil && u.entscheidung).length;
  async function kopiere(link: string) {
    await navigator.clipboard.writeText(link);
    setKopiert(link);
  }
  return (
    <>
      {ohneVerzeichnis && (
        <p className="hinweis">
          Das Verzeichnis der Bundesrechtsprechung ist noch nicht geladen. Lade es unter „Rechtsprechung“ und wähle danach
          hier „Zitate neu prüfen“.
        </p>
      )}
      {ladbar > 0 && (
        <div className="volltexte-laden">
          <button className="zweitrangig" onClick={onVolltexteLaden} disabled={laeuft}>
            {ladbar === 1 ? "Volltext laden" : `${ladbar} Volltexte laden`}
          </button>
          <span className="fundort">
            Belegte Entscheidungen der Bundesgerichte von rechtsprechung-im-internet.de; danach prüft die App zitierte
            Randnummern. Gesendet wird nur die Nummer der Entscheidung.
          </span>
        </div>
      )}
      <ul className="normen">
        {urteile.map((u) => (
          <li key={u.zitat} className={`urteil-${u.status}`}>
            <div>
              <span className={`marke-status urteil-${u.status}`}>{URTEIL_STATUS_TEXT[u.status]}</span>{" "}
              {u.urteil && <span className="marke-status urteil-volltext">Volltext liegt vor</span>}{" "}
              <strong>{u.zitat}</strong>
            </div>
            {u.hinweis && <div className={u.status === "belegt" ? "titel" : "hinweis"}>{u.hinweis}</div>}
            {u.entscheidung?.link && (
              <div className="link-zeile">
                <code>{u.entscheidung.link}</code>{" "}
                <button className="link" onClick={() => kopiere(u.entscheidung!.link!)}>
                  {kopiert === u.entscheidung.link ? "kopiert" : "Link kopieren"}
                </button>
              </div>
            )}
            <div className="fundstellen">
              {u.fundstellen.map((f, i) => {
                const rn = rnHinweis(f, u.rn_hoechste);
                return (
                  <span key={i} className="fundstelle">
                    <button className="link" onClick={() => onFundstelle(f.dokument_id, f.abschnitt)}>
                      {f.dateiname}, {fundstelle(f)}
                    </button>
                    {rn && (
                      <button
                        className={`link rn-hinweis ${f.rn_vorhanden ? "rn-ok" : "rn-fehlt"}`}
                        onClick={() => f.rn_vorhanden && onVolltext(u.urteil!.id, f.rn_zitiert!)}
                        title={f.rn_vorhanden ? "Randnummer im Volltext zeigen" : undefined}
                      >
                        {rn}
                      </button>
                    )}
                  </span>
                );
              })}
            </div>
            <div className="urteil-aktionen">
              {u.urteil ? (
                <>
                  <button className="link" onClick={() => onVolltext(u.urteil!.id)}>
                    {offen === u.urteil.id ? "Volltext schließen" : `Volltext anzeigen (${urteilHerkunft(u.urteil)})`}
                  </button>
                  <button className="link klein gefahr" onClick={() => onEntfernen(u.urteil!)} disabled={laeuft}>
                    entfernen
                  </button>
                </>
              ) : (
                <button className="link" onClick={() => onErgaenzen(u)} disabled={laeuft}>
                  {u.status === "belegt" ? "Volltext ergänzen …" : "Urteil selbst ergänzen …"}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="grenze">
        Geprüft wird, ob es eine Entscheidung dieses Bundesgerichts mit diesem Aktenzeichen und Datum gibt, nicht, ob sie
        die zitierte Aussage trägt. Entscheidungen anderer Gerichte und des EuGH sind nicht im Verzeichnis; sie lassen sich
        als eigene Datei ergänzen, z. B. als PDF-Ausdruck aus juris oder beck-online.
      </p>
    </>
  );
}

function ErgaenzungsFrage({
  ergaenzung,
  onAendern,
  onSpeichern,
  onAbbrechen,
  laeuft,
}: {
  ergaenzung: Ergaenzung;
  onAendern: (felder: Partial<Ergaenzung>) => void;
  onSpeichern: () => void;
  onAbbrechen: () => void;
  laeuft: boolean;
}) {
  const e = ergaenzung;
  return (
    <form
      className="rueckfrage"
      aria-label="Urteil ergänzen"
      onSubmit={(ev) => {
        ev.preventDefault();
        onSpeichern();
      }}
    >
      <strong>„{e.name}“ als Volltext zu „{e.zitat}“ ablegen</strong>
      <p>
        Die Datei wird unverändert bei dieser Akte abgelegt und gelesen; Randnummern werden als Fundstellen erkannt. Bitte
        prüfe die Angaben, damit die Entscheidung auch anderen Zitaten mit demselben Aktenzeichen zugeordnet wird.
      </p>
      <div className="formular">
        <label>
          Gericht
          <input value={e.gericht} onChange={(ev) => onAendern({ gericht: ev.target.value })} required />
        </label>
        <label>
          Aktenzeichen
          <input value={e.aktenzeichen} onChange={(ev) => onAendern({ aktenzeichen: ev.target.value })} />
        </label>
        <label>
          Datum
          <input type="date" value={e.datum} onChange={(ev) => onAendern({ datum: ev.target.value })} />
        </label>
        <label>
          Quelle
          <input
            list="urteil-quellen"
            value={e.herkunft}
            onChange={(ev) => onAendern({ herkunft: ev.target.value })}
            placeholder="z. B. juris"
          />
          <datalist id="urteil-quellen">
            {URTEIL_QUELLEN.map((q) => (
              <option key={q} value={q} />
            ))}
          </datalist>
        </label>
      </div>
      <div className="aktionen">
        <button type="submit" disabled={laeuft || !e.gericht.trim()}>
          Ablegen
        </button>
        <button type="button" className="zweitrangig" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </div>
    </form>
  );
}

function VolltextAnsicht({
  volltext,
  rn,
  onSchliessen,
}: {
  volltext: UrteilVolltext;
  rn: number | null;
  onSchliessen: () => void;
}) {
  const v = volltext;
  useEffect(() => {
    if (rn != null) document.getElementById(`vt-rn-${rn}`)?.scrollIntoView({ block: "center" });
  }, [rn, v.id]);
  let teil: string | null = null;
  return (
    <aside className="akte-seite volltext">
      <div className="volltext-kopf">
        <strong>
          {[v.gericht, v.kopf?.spruchkoerper].filter(Boolean).join(" ")}
          {v.datum && `, ${v.kopf?.doktyp ?? "Entscheidung"} vom ${v.datum.split("-").reverse().join(".")}`}
          {v.aktenzeichen && ` – ${v.aktenzeichen}`}
        </strong>
        <button className="link" onClick={onSchliessen}>
          schließen
        </button>
      </div>
      <p className="fundort">
        {v.quelle === "manuell" ? "Selbst ergänzt" : "Geladen"}: {urteilHerkunft(v)}
      </p>
      {v.kopf?.titel && <p className="volltext-titel">{v.kopf.titel}</p>}
      {v.kopf?.normen && <p className="fundort">Normen: {v.kopf.normen}</p>}
      {v.kopf?.vorinstanz.map((z, i) => (
        <p key={i} className="fundort">
          {z}
        </p>
      ))}
      {v.hinweise.map((h, i) => (
        <p key={i} className="hinweis">
          {h}
        </p>
      ))}
      {v.abschnitte.map((a) => {
        const kopf = a.teil && a.teil !== teil ? URTEIL_TEILE[a.teil] ?? a.teil : null;
        teil = a.teil;
        return (
          <div key={a.nr}>
            {kopf && <h3 className="volltext-teil">{kopf}</h3>}
            <p id={a.rn != null ? `vt-rn-${a.rn}` : undefined} className={`volltext-abschnitt${a.rn != null && a.rn === rn ? " ziel" : ""}`}>
              {/* Steht die Randnummer schon im Text („(2) …“), nicht doppelt zeigen. */}
              {a.rn != null && !a.text.startsWith(`(${a.rn})`) && <span className="rn">{a.rn}</span>}
              {a.text}
            </p>
          </div>
        );
      })}
    </aside>
  );
}
