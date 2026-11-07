import { PointerEvent as ReactPointerEvent, useCallback, useEffect, useRef, useState } from "react";
import { Druckansicht, istDesktop, kern } from "./kern";
import { AusgabeKnoepfe } from "./Export";
import { PdfKopienAkte } from "./PdfMarkiert";
import { AnmerkungsEintrag, FilterLeiste, useBedeutungen } from "./Anmerkungen";
import { bewegungVermeiden } from "./darstellung";
import { AnmerkFilter, Anmerkung, filtereAnmerkungen, KEIN_ANMERK_FILTER, vergleichbar } from "./anmerkungLogik";
import {
  eintragSchritt,
  ordnerSchritt,
  InhaltEintrag,
  Lesezeichen,
  LesezeichenListe,
  Marke,
  OrdnerEintrag,
  OrdnerGruppe,
  type OrdnerAnsichtArt,
  auswahlText,
  lesezeichenGruppen,
  ordnerGruppen,
  ordnung,
  schluessel,
  sichtbareOrdnung,
  verdichteMarken,
  verschiebeEintrag,
  verschiebeOrdner,
} from "./lesezeichenLogik";
import Zeichen, { LeerHinweis } from "./Symbole";

const LEER: LesezeichenListe = { ordner: [], lesezeichen: [] };

/** Wo ein neues Lesezeichen hinkommt: an eine Textstelle oder auf eine Seite des Originals (ggf. an Wörter). */
export type LesezeichenStelle =
  | { start: number; ende?: number; titel?: string }
  | { seite: number; wort_von?: number; wort_bis?: number; titel?: string };

/** Lesezeichen und Inhaltsverzeichnis des geöffneten Dokuments. */
export function useLesezeichen(dokumentId: number | null) {
  const [daten, setDaten] = useState<LesezeichenListe>(LEER);
  const [inhalt, setInhalt] = useState<InhaltEintrag[]>([]);
  // Zählt jede Änderung; die Originalansicht lädt damit ihre Fähnchen neu.
  const [stand, setStand] = useState(0);
  const [fehler, setFehler] = useState<string | null>(null);

  const laden = useCallback(async () => {
    if (dokumentId == null || !istDesktop) {
      setDaten(LEER);
      setInhalt([]);
      return;
    }
    try {
      const [l, i] = await Promise.all([
        kern<LesezeichenListe>("lesezeichen.liste", { dokument_id: dokumentId }),
        kern<InhaltEintrag[]>("lesezeichen.inhalt", { dokument_id: dokumentId }),
      ]);
      setDaten(l);
      setInhalt(i);
      setFehler(null);
    } catch (e) {
      setFehler(String(e));
    }
  }, [dokumentId]);

  useEffect(() => {
    void laden();
  }, [laden]);

  async function aendern(aufruf: () => Promise<unknown>) {
    try {
      await aufruf();
      setFehler(null);
      await laden();
      setStand((s) => s + 1);
    } catch (e) {
      setFehler(String(e));
    }
  }

  return {
    ...daten,
    inhalt,
    stand,
    fehler,
    anlegen: (s: LesezeichenStelle) =>
      dokumentId == null
        ? Promise.resolve()
        : aendern(() =>
            "seite" in s
              ? kern("lesezeichen.anlegen_seite", { dokument_id: dokumentId, ...s })
              : kern("lesezeichen.anlegen", { dokument_id: dokumentId, ...s }),
          ),
    umbenennen: (id: number, titel: string) => aendern(() => kern("lesezeichen.aendern", { lesezeichen_id: id, titel })),
    loeschen: (id: number) => aendern(() => kern("lesezeichen.loeschen", { lesezeichen_id: id })),
  };
}

export type LesezeichenSteuerung = ReturnType<typeof useLesezeichen>;

function ortText(z: Lesezeichen) {
  if (z.status === "nicht_gefunden") return "Stelle nicht mehr gefunden";
  return [z.seite != null ? `S. ${z.seite}` : null, z.rn != null ? `Rn. ${z.rn}` : null].filter(Boolean).join(", ");
}

/** Ein eigenes Lesezeichen: Klick springt hin, ✎ benennt um, × löscht. */
function Eintrag({
  z,
  mitDokument,
  onWaehle,
  onUmbenennen,
  onLoeschen,
  griff,
  extra,
}: {
  z: Lesezeichen;
  mitDokument?: boolean;
  onWaehle: (z: Lesezeichen) => void;
  onUmbenennen: (titel: string) => void;
  onLoeschen: () => void;
  griff?: React.ReactNode;
  extra?: React.ReactNode;
}) {
  const [bearbeiten, setBearbeiten] = useState(false);
  const [titel, setTitel] = useState(z.titel);
  useEffect(() => setTitel(z.titel), [z.titel]);
  function fertig() {
    setBearbeiten(false);
    if (titel.trim() && titel !== z.titel) onUmbenennen(titel);
    else setTitel(z.titel);
  }
  return (
    <div className={`lz-eintrag${z.status === "nicht_gefunden" ? " verloren" : ""}`}>
      {griff}
      <span className="lz-fahne-symbol" aria-hidden>
        <Zeichen name="lesezeichen" groesse={14} />
      </span>
      {bearbeiten ? (
        <input
          className="lz-titel-feld"
          autoFocus
          value={titel}
          onChange={(e) => setTitel(e.target.value)}
          onBlur={fertig}
          onKeyDown={(e) => {
            if (e.key === "Enter") fertig();
            if (e.key === "Escape") {
              setTitel(z.titel);
              setBearbeiten(false);
            }
          }}
          aria-label="Name des Lesezeichens"
        />
      ) : (
        <button className="lz-titel" onClick={() => onWaehle(z)} onDoubleClick={() => setBearbeiten(true)} title={z.zitat}>
          {mitDokument && <span className="lz-dokument">{z.dokument}</span>}
          <span>{z.titel}</span>
          <span className="lz-ort">{ortText(z)}</span>
        </button>
      )}
      {extra}
      <button className="lz-knopf" onClick={() => setBearbeiten(true)} title="Umbenennen" aria-label="Umbenennen">
        <Zeichen name="bearbeiten" groesse={13} />
      </button>
      <button className="lz-knopf" onClick={onLoeschen} title="Lesezeichen löschen" aria-label="Lesezeichen löschen">
        ×
      </button>
    </div>
  );
}

/** Inhalt der Seitenleiste „Lesezeichen“: Inhaltsverzeichnis des PDFs und eigene Lesezeichen des Dokuments. */
export function LesezeichenLeiste({
  lz,
  pdf,
  onWaehle,
  onInhalt,
  onHier,
  onAkte,
}: {
  lz: LesezeichenSteuerung;
  pdf: boolean;
  onWaehle: (z: Lesezeichen) => void;
  onInhalt: (seite: number) => void;
  onHier: () => void;
  onAkte: () => void;
}) {
  const gruppen = lesezeichenGruppen(lz, false);
  const ordnerDa = lz.ordner.length > 0;
  return (
    <div className="lz-leiste">
      {lz.fehler && <p className="fehler" role="alert">{lz.fehler}</p>}
      <section>
        <div className="lz-kopf">
          <h4>Eigene Lesezeichen</h4>
          <button className="zweitrangig klein" onClick={onHier} title="Lesezeichen an der Stelle oben im sichtbaren Bereich">
            + Hier setzen
          </button>
        </div>
        {lz.lesezeichen.length === 0 ? (
          <p className="leise anm-leer">
            „Hier setzen“ merkt die Stelle oben im sichtbaren Bereich. Oder Text auswählen und im Menü „Lesezeichen“
            wählen.
          </p>
        ) : (
          gruppen.map((g) => (
            <div key={g.id ?? "ohne"} className="lz-gruppe">
              {ordnerDa && (
                <h5>
                  <Zeichen name="ordner" groesse={13} /> {g.name}
                </h5>
              )}
              {g.eintraege.map((z) => (
                <Eintrag
                  key={z.id}
                  z={z}
                  onWaehle={onWaehle}
                  onUmbenennen={(t) => void lz.umbenennen(z.id, t)}
                  onLoeschen={() => void lz.loeschen(z.id)}
                />
              ))}
            </div>
          ))
        )}
        <button className="link" onClick={onAkte}>
          Ordner und Reihenfolge in der Akte verwalten
        </button>
      </section>
      <section>
        <h4>Inhaltsverzeichnis</h4>
        {lz.inhalt.length === 0 ? (
          <p className="leise anm-leer">
            {pdf ? "Das PDF bringt kein Inhaltsverzeichnis mit." : "Nur PDFs bringen ein eigenes Inhaltsverzeichnis mit."}
          </p>
        ) : (
          <ul className="lz-inhalt">
            {lz.inhalt.map((e, i) => (
              <li key={i} style={{ paddingLeft: `${e.ebene * 14}px` }}>
                <button className="lz-titel" disabled={e.seite == null} onClick={() => e.seite != null && onInhalt(e.seite)}>
                  <span>{e.titel}</span>
                  {e.seite != null && <span className="lz-ort">S. {e.seite}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/** Was der Reiter „Anmerkungen“ der Akte zeigt; die Ordner sind für alle drei Ansichten dieselben. */
export type { OrdnerAnsichtArt };

/**
 * Reiter „Anmerkungen“ der Akte: Markierungen und Kommentare, Lesezeichen oder beides in den Ordnern der Akte.
 * Ordner anlegen, Einträge per Ziehen sortieren und einordnen.
 */
export function OrdnerAnsicht({
  akteId,
  ansicht,
  onLesezeichen,
  onAnmerkung,
}: {
  akteId: number;
  ansicht: OrdnerAnsichtArt;
  onLesezeichen: (z: Lesezeichen) => void;
  onAnmerkung: (a: Anmerkung) => void;
}) {
  const bedeutungen = useBedeutungen();
  const [gruppen, setGruppen] = useState<OrdnerGruppe[] | null>(null);
  const [markierungen, setMarkierungen] = useState<Anmerkung[]>([]);
  const [filter, setFilter] = useState<AnmerkFilter>(KEIN_ANMERK_FILTER);
  const [neuerOrdner, setNeuerOrdner] = useState("");
  const [umbenennen, setUmbenennen] = useState<{ id: number; name: string } | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  // Ziehen mit Zeiger statt HTML-Drag-and-Drop: Das funktioniert in den Fenstern aller drei Systeme gleich.
  const zug = useRef<{ art: "eintrag"; key: string } | { art: "ordner"; id: number } | null>(null);
  const [ziel, setZiel] = useState<{ gruppe: number | null; vor: string | null; ordner: boolean } | null>(null);
  const [gezogen, setGezogen] = useState<string | null>(null);
  const [ausgabe, setAusgabe] = useState(false);
  const [gliederung, setGliederung] = useState<"ordner" | "dokumente">("ordner");

  const laden = useCallback(async () => {
    try {
      const [l, m] = await Promise.all([
        kern<LesezeichenListe>("lesezeichen.liste", { akte_id: akteId }),
        kern<Anmerkung[]>("anmerkungen.liste", { akte_id: akteId }),
      ]);
      setMarkierungen(m);
      setGruppen(ordnerGruppen(l.ordner, l.lesezeichen, m));
      setFehler(null);
    } catch (e) {
      setFehler(String(e));
    }
  }, [akteId]);
  useEffect(() => {
    if (istDesktop) void laden();
  }, [laden]);

  async function aufruf(f: () => Promise<unknown>) {
    try {
      await f();
      await laden();
    } catch (e) {
      setFehler(String(e));
    }
  }

  async function speichern(neu: OrdnerGruppe[]) {
    setGruppen(neu);
    try {
      await kern("lesezeichen.anordnen", { akte_id: akteId, ordner: ordnung(neu) });
      await laden();
    } catch (e) {
      setFehler(String(e));
      await laden();
    }
  }

  // Sichtbar je Ansicht und Filter; verschoben wird in der vollständigen Ordnung (vor dem nächsten sichtbaren Eintrag).
  const passendeMarkierungen = new Set(filtereAnmerkungen(markierungen, filter, bedeutungen).map((a) => a.id));
  const woerter = vergleichbar(filter.suche).split(/\s+/).filter(Boolean);
  const sichtbar = (e: OrdnerEintrag) =>
    e.art === "markierung"
      ? ansicht !== "lesezeichen" && passendeMarkierungen.has(e.a.id)
      : ansicht !== "markierungen" &&
        filter.farben.length === 0 &&
        !filter.nurKommentar &&
        woerter.every((w) => vergleichbar(`${e.z.titel} ${e.z.zitat} ${e.z.dokument}`).includes(w));

  function zielUnter(x: number, y: number, ordner: boolean) {
    const el = document.elementFromPoint(x, y);
    const gruppe = el?.closest<HTMLElement>("[data-lz-gruppe]");
    if (!gruppe) return null;
    const gid = gruppe.dataset.lzGruppe === "ohne" ? null : Number(gruppe.dataset.lzGruppe);
    if (ordner) return { gruppe: gid, vor: null, ordner };
    const zeile = el?.closest<HTMLElement>("[data-lz-key]");
    if (!zeile) return { gruppe: gid, vor: null, ordner };
    const r = zeile.getBoundingClientRect();
    if (y <= r.top + r.height / 2) return { gruppe: gid, vor: zeile.dataset.lzKey!, ordner };
    const naechste = zeile.nextElementSibling as HTMLElement | null;
    return { gruppe: gid, vor: naechste?.dataset.lzKey ?? null, ordner };
  }

  const ziehen = (was: { art: "eintrag"; key: string } | { art: "ordner"; id: number }) => ({
    onPointerDown: (e: ReactPointerEvent<HTMLElement>) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      zug.current = was;
      setGezogen(was.art === "eintrag" ? was.key : `o${was.id}`);
    },
    onPointerMove: (e: ReactPointerEvent<HTMLElement>) => {
      if (zug.current) setZiel(zielUnter(e.clientX, e.clientY, zug.current.art === "ordner"));
    },
    onPointerUp: (e: ReactPointerEvent<HTMLElement>) => {
      const z = zug.current;
      zug.current = null;
      setGezogen(null);
      setZiel(null);
      const wohin = z && zielUnter(e.clientX, e.clientY, z.art === "ordner");
      if (!z || !wohin || !gruppen) return;
      if (z.art === "ordner") {
        if (wohin.gruppe !== z.id) void speichern(verschiebeOrdner(gruppen, z.id, wohin.gruppe));
        return;
      }
      if (wohin.vor === z.key) return;
      void speichern(verschiebeEintrag(gruppen, z.key, wohin.gruppe, wohin.vor));
    },
  });

  if (fehler && !gruppen) return <p className="fehler" role="alert">{fehler}</p>;
  if (!gruppen) return <p className="status" role="status">Lade …</p>;
  const ordner = gruppen.filter((g) => g.id != null);
  const vorhanden = gruppen.flatMap((g) => g.eintraege).filter(
    (e) => ansicht === "alle" || (ansicht === "lesezeichen") === (e.art === "lesezeichen"),
  );
  const anzahlSichtbar = gruppen.reduce((n, g) => n + g.eintraege.filter(sichtbar).length, 0);
  const mitMarkierungen = ansicht !== "lesezeichen" && markierungen.length > 0;

  return (
    <div className="lz-verwaltung">
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {mitMarkierungen && (
        <FilterLeiste
          liste={markierungen}
          filter={filter}
          onFilter={setFilter}
          bedeutungen={bedeutungen}
          suchtext={ansicht === "alle" ? "Suchen in Markierungen, Kommentaren und Lesezeichen" : "Suchen in Wortlaut, Kommentar und Bedeutung"}
        />
      )}
      {vorhanden.length === 0 ? (
        <LeerHinweis symbol={ansicht === "lesezeichen" ? "lesezeichen" : "markieren"}>
          {ansicht === "lesezeichen"
            ? "Noch keine Lesezeichen in dieser Akte. Öffne ein Dokument, blende rechts „Anmerkungen“ ein und wähle dort den Reiter „Lesezeichen“ – oder wähle Text aus und klicke im Menü auf das Lesezeichen."
            : "Noch nichts markiert. Öffne ein Dokument, wähle Text aus und markiere ihn im Menü über der Auswahl; dort lassen sich auch ein Kommentar oder ein Lesezeichen anfügen."}
        </LeerHinweis>
      ) : (
        <div className="lz-hinweis-zeile">
          <p className="leise">
            {anzahlSichtbar === vorhanden.length ? `${vorhanden.length} Einträge` : `${anzahlSichtbar} von ${vorhanden.length} Einträgen`}. Am Griff
            ziehen: Einträge in einen Ordner oder an eine andere Stelle, Ordner in eine andere Reihenfolge. Ohne Ziehen: ▲ ▼,
            Pfeil hoch/runter auf dem Griff oder die Ordnerauswahl. Die Ordner gelten für Markierungen und Lesezeichen gemeinsam.
          </p>
          <button className="zweitrangig" aria-expanded={ausgabe} onClick={() => setAusgabe(!ausgabe)}>
            Exportieren / Drucken …
          </button>
        </div>
      )}
      {ausgabe && vorhanden.length > 0 && (
        <section className="karte ki-export lz-ausgabe">
          <div className="ki-export-kopf">
            <strong>{anzahlSichtbar === vorhanden.length ? "Alle angezeigten Einträge ausgeben" : `${anzahlSichtbar} angezeigte Einträge ausgeben`}</strong>
            <button className="zweitrangig" onClick={() => setAusgabe(false)}>
              Schließen
            </button>
          </div>
          <p className="leise">
            Ausgegeben wird, was oben angezeigt ist (Ansicht, Bedeutung, Suche), mit Fundstelle (Dokument, Seite, Rn.) und
            Kommentar.
          </p>
          <div className="ki-export-teile" role="radiogroup" aria-label="Gliederung">
            <label>
              <input type="radio" checked={gliederung === "ordner"} onChange={() => setGliederung("ordner")} /> Nach Ordnern, in der Reihenfolge wie hier
            </label>
            <label>
              <input type="radio" checked={gliederung === "dokumente"} onChange={() => setGliederung("dokumente")} /> Nach Dokumenten, in Textfolge
            </label>
          </div>
          {(() => {
            const params = {
              akte_id: akteId,
              ordner: sichtbareOrdnung(gruppen, sichtbar),
              gliederung,
              auswahl: auswahlText(ansicht, filter, bedeutungen),
            };
            return (
              <AusgabeKnoepfe
                was="Anmerkungen"
                gesperrt={anzahlSichtbar === 0}
                name={async () => (await kern<{ name: string }>("anmerkungen.export_name", { akte_id: akteId })).name}
                schreiben={(format, pfad) => kern<{ pfad: string }>("anmerkungen.export", { ...params, format, pfad })}
                druckansicht={() => kern<Druckansicht>("anmerkungen.export_druck", params)}
              />
            );
          })()}
          {ansicht !== "lesezeichen" && (
            <PdfKopienAkte
              akteId={akteId}
              ids={gruppen.flatMap((g) => g.eintraege.filter(sichtbar)).flatMap((e) => (e.art === "markierung" ? [e.a.id] : []))}
            />
          )}
        </section>
      )}
      {gruppen.map((g) => {
        const zeilen = g.eintraege.filter(sichtbar);
        if (g.id == null && zeilen.length === 0 && ordner.length > 0) return null;
        return (
          <section
            key={g.id ?? "ohne"}
            data-lz-gruppe={g.id ?? "ohne"}
            className={`lz-ordner${ziel && ziel.gruppe === g.id && (ziel.ordner || ziel.vor == null) ? " lz-ziel" : ""}${gezogen === `o${g.id}` ? " gezogen" : ""}`}
          >
            <div className="lz-ordner-kopf">
              {g.id != null && (
                <Schieber
                  titel={`Ordner „${g.name}“`}
                  ziehen={ziehen({ art: "ordner", id: g.id })}
                  onSchritt={(r) => void speichern(ordnerSchritt(gruppen, g.id!, r))}
                />
              )}
              <Zeichen name="ordner" groesse={15} />
              {umbenennen && umbenennen.id === g.id ? (
                <input
                  autoFocus
                  className="lz-titel-feld"
                  value={umbenennen.name}
                  onChange={(e) => setUmbenennen({ id: g.id!, name: e.target.value })}
                  onBlur={() => {
                    const n = umbenennen.name;
                    setUmbenennen(null);
                    if (n.trim() && n !== g.name) void aufruf(() => kern("lesezeichen.ordner_umbenennen", { ordner_id: g.id, name: n }));
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                    if (e.key === "Escape") setUmbenennen(null);
                  }}
                  aria-label="Name des Ordners"
                />
              ) : (
                <h3>{g.name}</h3>
              )}
              <span className="leise">{zeilen.length}</span>
              {g.id != null && (
                <>
                  <button className="lz-knopf" title="Ordner umbenennen" aria-label="Ordner umbenennen" onClick={() => setUmbenennen({ id: g.id!, name: g.name })}>
                    <Zeichen name="bearbeiten" groesse={13} />
                  </button>
                  <button
                    className="lz-knopf"
                    title="Ordner löschen (der Inhalt bleibt erhalten, ohne Ordner)"
                    aria-label="Ordner löschen"
                    onClick={() => void aufruf(() => kern("lesezeichen.ordner_loeschen", { ordner_id: g.id }))}
                  >
                    ×
                  </button>
                </>
              )}
            </div>
            <div className="lz-ordner-inhalt">
              {zeilen.length === 0 && <p className="leise lz-leer">Hierher ziehen</p>}
              {zeilen.map((e) => {
                const key = schluessel(e);
                const griff = (
                  <Schieber
                    titel={e.art === "lesezeichen" ? `Lesezeichen „${e.z.titel}“` : "Markierung"}
                    ziehen={ziehen({ art: "eintrag", key })}
                    onSchritt={(r) => void speichern(eintragSchritt(gruppen, key, r))}
                  />
                );
                const wahl = ordner.length > 0 && (
                  <select
                    className="lz-ordner-wahl"
                    value={g.id ?? ""}
                    aria-label="In Ordner verschieben"
                    title="In Ordner verschieben"
                    onChange={(ev) => void speichern(verschiebeEintrag(gruppen, key, ev.target.value ? Number(ev.target.value) : null, null))}
                  >
                    {ordner.map((o) => (
                      <option key={o.id} value={o.id!}>
                        {o.name}
                      </option>
                    ))}
                    <option value="">Ohne Ordner</option>
                  </select>
                );
                return (
                  <div
                    key={key}
                    data-lz-key={key}
                    className={`lz-zeile${ziel && !ziel.ordner && ziel.gruppe === g.id && ziel.vor === key ? " lz-ziel-vor" : ""}${gezogen === key ? " gezogen" : ""}`}
                  >
                    {e.art === "lesezeichen" ? (
                      <Eintrag
                        z={e.z}
                        mitDokument
                        onWaehle={onLesezeichen}
                        onUmbenennen={(t) => void aufruf(() => kern("lesezeichen.aendern", { lesezeichen_id: e.z.id, titel: t }))}
                        onLoeschen={() => void aufruf(() => kern("lesezeichen.loeschen", { lesezeichen_id: e.z.id }))}
                        griff={griff}
                        extra={wahl}
                      />
                    ) : (
                      <div className="lz-markierung">
                        {griff}
                        <ul className="anm-liste">
                          <AnmerkungsEintrag a={e.a} bedeutungen={bedeutungen} aktiv={false} mitDokument onWaehle={() => onAnmerkung(e.a)} />
                        </ul>
                        {wahl}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
      <form
        className="lz-neuer-ordner"
        onSubmit={(e) => {
          e.preventDefault();
          if (neuerOrdner.trim())
            void aufruf(async () => {
              await kern("lesezeichen.ordner_anlegen", { akte_id: akteId, name: neuerOrdner });
              setNeuerOrdner("");
            });
        }}
      >
        <input value={neuerOrdner} onChange={(e) => setNeuerOrdner(e.target.value)} placeholder="Neuer Ordner, z. B. Beweisangebote" aria-label="Name des neuen Ordners" />
        <button className="zweitrangig" disabled={!neuerOrdner.trim()}>
          Ordner anlegen
        </button>
      </form>
    </div>
  );
}

/**
 * Farbige Marken am rechten Rand des Bildlaufbereichs um ``wurzel``: Markierungen ([data-anmerkung] mit Farbklasse)
 * und Lesezeichen ([data-lesezeichen]). Ein Klick springt zur Stelle.
 */
export function Bildlaufmarken({ wurzel }: { wurzel: HTMLElement | null }) {
  const [lage, setLage] = useState<{ top: number; hoehe: number; rechts: number } | null>(null);
  const [marken, setMarken] = useState<Marke[]>([]);
  const rahmen = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!wurzel) return;
    let r: HTMLElement | null = null;
    for (let p = wurzel.parentElement; p; p = p.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(p).overflowY)) {
        r = p;
        break;
      }
    }
    // Ohne eigenen Bildlaufbereich scrollt das Fenster.
    const bereich = r ?? document.scrollingElement as HTMLElement;
    rahmen.current = bereich;
    let takt = 0;
    const messen = () => {
      window.clearTimeout(takt);
      takt = window.setTimeout(() => {
        const box = r ? r.getBoundingClientRect() : new DOMRect(0, 0, window.innerWidth, window.innerHeight);
        const leiste = r ? r.offsetWidth - r.clientWidth : 0;
        setLage({ top: box.top, hoehe: r ? r.clientHeight : window.innerHeight, rechts: window.innerWidth - box.right + leiste });
        const oben = r ? box.top - r.scrollTop : -window.scrollY;
        const gesamt = bereich.scrollHeight || 1;
        const gesehen = new Set<string>();
        const neu: Marke[] = [];
        wurzel.querySelectorAll<HTMLElement>("[data-anmerkung], [data-lesezeichen]").forEach((el) => {
          const lz = el.dataset.lesezeichen;
          const schluessel = lz ? `l${lz}` : `a${el.dataset.anmerkung}`;
          const farbe = lz ? "lesezeichen" : (el.className.match(/\banm-(gelb|gruen|blau|rot)\b/)?.[1] ?? null);
          if (!farbe || gesehen.has(schluessel)) return;
          gesehen.add(schluessel);
          const y = el.getBoundingClientRect().top - oben;
          neu.push({ lage: Math.min(1, Math.max(0, y / gesamt)), art: farbe, ziel: y, titel: el.title || el.textContent?.slice(0, 60) || "" });
        });
        setMarken(verdichteMarken(neu));
      }, 120);
    };
    messen();
    const beobachter = new MutationObserver(messen);
    beobachter.observe(wurzel, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style", "src"] });
    const groesse = new ResizeObserver(messen);
    groesse.observe(wurzel);
    if (r) groesse.observe(r);
    window.addEventListener("resize", messen);
    return () => {
      window.clearTimeout(takt);
      beobachter.disconnect();
      groesse.disconnect();
      window.removeEventListener("resize", messen);
    };
  }, [wurzel]);

  if (!lage || marken.length === 0) return null;
  return (
    <div className="bildlaufmarken" style={{ top: lage.top, height: lage.hoehe, right: lage.rechts }} aria-hidden>
      {marken.map((m, i) => (
        <span
          key={i}
          className={`bildlaufmarke marke-${m.art}`}
          style={{ top: `${m.lage * 100}%` }}
          title={m.art === "lesezeichen" ? `Lesezeichen: ${m.titel}` : m.titel}
          onClick={() => rahmen.current?.scrollTo({ top: Math.max(0, m.ziel - (rahmen.current.clientHeight || 0) / 3), behavior: bewegungVermeiden() ? "auto" : "smooth" })}
        />
      ))}
    </div>
  );
}

/**
 * Griff zum Verschieben: Ziehen mit der Maus, Pfeil hoch/runter mit der Tastatur und die Knöpfe ▲ ▼ für einen
 * einzelnen Klick (WCAG 2.2, 2.5.7 Ziehbewegungen; 2.1.1 Tastatur).
 */
function Schieber({
  titel,
  ziehen,
  onSchritt,
}: {
  titel: string;
  ziehen: Record<string, unknown>;
  onSchritt: (richtung: -1 | 1) => void;
}) {
  return (
    <span className="lz-schieber">
      <button
        type="button"
        className="lz-griff"
        title="Ziehen oder mit Pfeil hoch/runter verschieben"
        aria-label={`${titel} verschieben, Pfeil hoch oder runter`}
        onKeyDown={(e) => {
          if (e.key === "ArrowUp" || e.key === "ArrowDown") {
            e.preventDefault();
            onSchritt(e.key === "ArrowUp" ? -1 : 1);
          }
        }}
        {...ziehen}
      >
        <Zeichen name="griff" groesse={14} />
      </button>
      <button type="button" className="lz-knopf lz-schritt" aria-label={`${titel} nach oben`} title="Nach oben" onClick={() => onSchritt(-1)}>
        ▲
      </button>
      <button type="button" className="lz-knopf lz-schritt" aria-label={`${titel} nach unten`} title="Nach unten" onClick={() => onSchritt(1)}>
        ▼
      </button>
    </span>
  );
}
