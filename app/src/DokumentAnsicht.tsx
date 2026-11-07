import {
  MouseEvent as ReactMouseEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Auswahl, DokModus, Ergaenzung } from "./Akte";
import { OriginalAnmerkungen, SeitenAuswahl, anmerkungsHandler } from "./Anmerkungen";
import Zeichen from "./Symbole";
import {
  Anmerkung,
  AnmerkungAufSeite,
  SeitenWort,
  abschnittBeginne,
  auswahlRechtecke,
  stueckKlassen,
  stuecke,
  wortAn,
} from "./anmerkungLogik";
import {
  Abschnitt,
  AktenDokument,
  DokumentInhalt,
  NormEintrag,
  NormZitat,
  ONLINE_QUELLE,
  QUELLEN_HINWEIS,
  STATUS_TEXT,
  Seitenbild,
  URTEIL_QUELLEN,
  URTEIL_QUELLE_NAME,
  URTEIL_STATUS_TEXT,
  URTEIL_TEILE,
  UrteilEintrag,
  UrteilInfo,
  UrteilVolltext,
  dokumentDatum,
  dokumentName,
  fundstelle,
  kern,
  lesartText,
  markiereBegriffe,
  renderBreite,
  rnHinweis,
  segmente,
  sortiereTags,
  urteilHerkunft,
  urteilTitel,
} from "./kern";
import { useKiAn } from "./kiSchalter";
import { Lesezeichen, LesezeichenAufSeite } from "./lesezeichenLogik";

export function DokumentAnsicht({
  inhalt,
  auswahl = null,
  onZitat,
  markiert,
  begriffe = [],
  ohneTitel = false,
  anmerkungen = [],
  aktiveAnmerkung = null,
  lesezeichen = [],
}: {
  inhalt: DokumentInhalt;
  auswahl?: Auswahl | null;
  /** Ohne Handler werden Normzitate nur markiert, nicht anklickbar. */
  onZitat?: (z: NormZitat, a: Abschnitt) => void;
  /** Abschnitt, der hervorgehoben wird (Fundstelle aus dem Vergleich oder der Suche). */
  markiert?: number;
  /** Gesuchte Begriffe, die im Text gelb markiert werden. */
  begriffe?: string[];
  /** In der Akte steht der Name schon im Kopf des geöffneten Dokuments. */
  ohneTitel?: boolean;
  /** Markierungen und Kommentare (Anmerkungen.tsx); Mausereignisse fängt der umgebende Rahmen ab. */
  anmerkungen?: Anmerkung[];
  aktiveAnmerkung?: number | null;
  /** Eigene Lesezeichen: ein Fähnchen am Rand des Absatzes, in dem die Stelle beginnt. */
  lesezeichen?: Lesezeichen[];
}) {
  const d = inhalt.dokument;
  const beginne = useMemo(() => abschnittBeginne(inhalt.abschnitte), [inhalt]);

  /** Text von ``von`` bis ``bis`` im Abschnitt: Markierungen, Sprechblasen am Ende kommentierter Stellen, Suchbegriffe. */
  const markierterText = (text: string, von: number, bis: number, beginn: number) =>
    stuecke(von, bis, beginn, anmerkungen).map((st) => {
      const teil = text.slice(st.von, st.bis);
      const inhaltTeil = markiereBegriffe(teil, begriffe).map((m, j) => (m.treffer ? <mark key={j}>{m.text}</mark> : m.text));
      const blasen = st.endeVon
        .filter((a) => a.kommentar)
        .map((a) => (
          <span
            key={`b${a.id}`}
            className={`anm-blase anm-blase-${a.farbe}`}
            data-kein-text=""
            data-anmerkung={a.id}
            role="button"
            tabIndex={0}
            aria-label="Kommentar zeigen"
          >
            <Zeichen name="kommentar" groesse={12} />
          </span>
        ));
      if (st.anmerkungen.length === 0) return <span key={st.von}>{inhaltTeil}</span>;
      const aktiv = st.anmerkungen.some((a) => a.id === aktiveAnmerkung);
      return (
        <span key={st.von}>
          <span
            className={`${stueckKlassen(st.anmerkungen)}${aktiv ? " anm-aktiv" : ""}`}
            data-anmerkung={st.anmerkungen.map((a) => a.id).join(" ")}
          >
            {inhaltTeil}
          </span>
          {blasen}
        </span>
      );
    });

  return (
    <article className="dokument">
      {!ohneTitel && <h2>{d.dateiname}</h2>}
      <p className="dokument-info">
        {lesartText(d)}
        {d.seiten != null && <> · {d.seiten} Seiten</>} · SHA-256 {d.sha256.slice(0, 12)}…
        {d.herkunft && <> · Ordner {d.herkunft}</>}
        {d.datum && (
          <span title={dokumentDatum(d).erklaerung}>
            {" "}
            · Datum {dokumentDatum(d).text} ({dokumentDatum(d).herkunft})
          </span>
        )}
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
      {inhalt.abschnitte.map((a, ai) => {
        let pos = 0;
        return (
        <section key={a.nr} id={`abschnitt-${a.nr}`} className={`abschnitt ${a.art}${a.nr === markiert ? " markiert" : ""}`}>
          <span className="abschnitt-ort">{fundstelle(a)}</span>
          <p data-beginn={beginne[ai]}>
            {lesezeichen
              .filter((z) => z.status === "gefunden" && z.start >= beginne[ai] && z.start <= beginne[ai] + a.text.length)
              .map((z) => (
                <span key={`lz${z.id}`} className="lz-fahne" data-kein-text="" data-lesezeichen={z.id} title={`Lesezeichen: ${z.titel}`}>
                  <Zeichen name="lesezeichen" groesse={14} />
                </span>
              ))}
            {segmente(a.text, a.zitate).map((s, i) => {
              const von = pos;
              pos += s.text.length;
              return s.zitat ? (
                <button
                  key={i}
                  className={`zitat ${s.zitat.status}${auswahl?.zitat === s.zitat ? " gewaehlt" : ""}`}
                  title={`${s.zitat.zitat}: ${STATUS_TEXT[s.zitat.status]}${s.zitat.hinweis ? ` – ${s.zitat.hinweis}` : ""}`}
                  onClick={() => onZitat?.(s.zitat!, a)}
                  disabled={!onZitat}
                >
                  {markierterText(a.text, von, pos, beginne[ai])}
                </button>
              ) : (
                <span key={i}>{markierterText(a.text, von, pos, beginne[ai])}</span>
              );
            })}
          </p>
        </section>
        );
      })}
    </article>
  );
}

const DOK_MODI: { modus: DokModus; text: string }[] = [
  { modus: "text", text: "Text" },
  { modus: "original", text: "Original" },
  { modus: "normen", text: "Normen" },
  { modus: "rechtsprechung", text: "Rechtsprechung" },
  { modus: "chat", text: "Chat" },
  { modus: "details", text: "Details" },
];

const FORMAT_NAME: Record<AktenDokument["format"], string> = { pdf: "PDF", docx: "Word", txt: "Text", md: "Markdown" };

export function DokModusLeiste({
  dokument,
  modus,
  onModus,
  anmerkungen,
}: {
  dokument: AktenDokument;
  modus: DokModus;
  onModus: (m: DokModus) => void;
  /** Knopf für die Seitenleiste mit Markierungen und Kommentaren (nur in Text und Original). */
  anmerkungen?: { anzahl: number; offen: boolean; onUmschalten: () => void };
}) {
  const pdf = dokument.format === "pdf";
  // Ohne KI (Einstellungen) kein Chat mit dem Dokument.
  const kiAn = useKiAn();
  return (
    <div className="dok-modi">
      <div className="dok-modi-kopf">
        <span className="dok-modi-name" title={dokument.titel ? dokument.dateiname : undefined}>
          {dokumentName(dokument)}
        </span>
        <span className="dok-modi-angaben">
          {[
            dokument.art,
            dokument.datum ? dokumentDatum(dokument).text : null,
            FORMAT_NAME[dokument.format],
            dokument.seiten != null ? `${dokument.seiten} S.` : null,
            dokument.titel ? dokument.dateiname : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
      <div className="dok-modi-reiter" role="tablist" aria-label={`Darstellung von ${dokument.dateiname}`}>
      {DOK_MODI.filter((m) => kiAn || m.modus !== "chat").map((m) => (
        <button
          key={m.modus}
          role="tab"
          aria-selected={modus === m.modus}
          className={modus === m.modus ? "dok-modus aktiv" : "dok-modus"}
          disabled={m.modus === "original" && !pdf}
          title={m.modus === "original" && !pdf ? "Die Originalansicht gibt es nur für PDF-Dateien." : undefined}
          onClick={() => onModus(m.modus)}
        >
          {m.text}
        </button>
      ))}
      </div>
      {anmerkungen && (
        <button
          className={`anm-umschalter${anmerkungen.offen ? " aktiv" : ""}`}
          aria-pressed={anmerkungen.offen}
          onClick={anmerkungen.onUmschalten}
          title={anmerkungen.offen ? "Anmerkungen ausblenden" : "Markierungen und Kommentare dieses Dokuments zeigen"}
        >
          <Zeichen name="markieren" groesse={15} /> Anmerkungen
          {anmerkungen.anzahl > 0 && <span className="anzahl">{anmerkungen.anzahl}</span>}
        </button>
      )}
    </div>
  );
}

/** Seiten des Original-PDFs; der Kern rendert sie, sobald sie in Sichtweite kommen. */
/** Nächster Vorfahr, der selbst scrollt; dort wird beobachtet, welche Seiten in Sicht kommen. */
export function scrollRahmen(el: HTMLElement): HTMLElement | null {
  for (let p = el.parentElement; p; p = p.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(p).overflowY)) return p;
  }
  return null;
}

export function OriginalAnsicht({
  dokument,
  startSeite,
  begriffe,
  hinweis = "Zitate und Belege zeigt die Textansicht.",
  anmerkungen,
  lesezeichenStand,
}: {
  dokument: Pick<AktenDokument, "id" | "dateiname" | "seiten">;
  startSeite: number | null;
  /** Gesuchte Begriffe; ihre Fundstellen werden auf den Seiten gelb markiert. */
  begriffe?: string[];
  hinweis?: string;
  /** Markierungen über die Seiten legen und auf den Seiten markieren lassen; ``stand`` zählt jede Änderung. */
  anmerkungen?: OriginalAnmerkungen;
  /** Eigene Lesezeichen als Fähnchen am Seitenrand zeigen; die Zahl ändert sich mit jeder Änderung. */
  lesezeichenStand?: number;
}) {
  const seiten = dokument.seiten ?? 1;
  const rahmen = useRef<HTMLDivElement>(null);
  const [bilder, setBilder] = useState<Record<number, Seitenbild | string>>({});
  const angefragt = useRef(new Set<number>());
  const [aufSeite, setAufSeite] = useState<Record<number, AnmerkungAufSeite[]>>({});
  const mitAnmerkungen = !!anmerkungen;
  const anmerkStand = anmerkungen?.stand ?? 0;
  const [woerter, setWoerter] = useState<Record<number, SeitenWort[]>>({});
  const [fahnen, setFahnen] = useState<Record<number, LesezeichenAufSeite[]>>({});
  const mitLesezeichen = lesezeichenStand != null;
  const zug = useRef<{ seite: number; anker: number; x: number; y: number; bewegt: boolean } | null>(null);
  const [gezogen, setGezogen] = useState<SeitenAuswahl | null>(null);

  // Markierungen je geladener Seite; nach jeder Änderung neu.
  const geladen = Object.keys(bilder).join(",");
  useEffect(() => {
    if (!mitAnmerkungen) return;
    let gueltig = true;
    for (const s of Object.keys(bilder).map(Number)) {
      if (typeof bilder[s] !== "object") continue;
      kern<AnmerkungAufSeite[]>("anmerkungen.seite", { dokument_id: dokument.id, seite: s })
        .then((l) => gueltig && setAufSeite((v) => ({ ...v, [s]: l })))
        .catch(() => undefined);
      if (!woerter[s])
        kern<SeitenWort[]>("anmerkungen.woerter", { dokument_id: dokument.id, seite: s })
          .then((w) => gueltig && setWoerter((v) => ({ ...v, [s]: w })))
          .catch(() => undefined);
    }
    return () => {
      gueltig = false;
    };
    // Nur bei neuen Seiten oder geänderten Anmerkungen; ``bilder`` selbst ändert sich mit jeder Seite.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mitAnmerkungen, anmerkStand, geladen, dokument.id]);

  useEffect(() => {
    const el = rahmen.current;
    if (!el) return;
    const breite = renderBreite(el.clientWidth, window.devicePixelRatio || 1);
    const beobachter = new IntersectionObserver(
      (eintraege) => {
        for (const e of eintraege) {
          if (!e.isIntersecting) continue;
          const seite = Number((e.target as HTMLElement).dataset.seite);
          if (angefragt.current.has(seite)) continue;
          angefragt.current.add(seite);
          kern<Seitenbild>("akten.seitenbild", { dokument_id: dokument.id, seite, breite, begriffe: begriffe ?? null })
            .then((b) => setBilder((v) => ({ ...v, [seite]: b })))
            .catch((f) => setBilder((v) => ({ ...v, [seite]: String(f) })));
        }
      },
      { root: scrollRahmen(el), rootMargin: "600px 0px" },
    );
    el.querySelectorAll<HTMLElement>("[data-seite]").forEach((s) => beobachter.observe(s));
    return () => beobachter.disconnect();
    // Neue Begriffe: Elternteil setzt einen neuen key, die Ansicht wird neu aufgebaut.
  }, [dokument.id]);

  // Zur Zielseite springen; sobald sie geladen ist, zur ersten Markierung darauf.
  const ziel = startSeite != null ? bilder[startSeite] : undefined;
  const zielMarkiert = typeof ziel === "object" && ziel.markierungen.length > 0;
  useEffect(() => {
    if (startSeite == null) return;
    const el = zielMarkiert
      ? rahmen.current?.querySelector(`#seite-${startSeite} .markierung`)
      : rahmen.current?.querySelector(`#seite-${startSeite}`);
    el?.scrollIntoView({ block: zielMarkiert ? "center" : "start" });
  }, [startSeite, zielMarkiert]);

  // Lesezeichen je geladener Seite; nach jeder Änderung neu.
  useEffect(() => {
    if (!mitLesezeichen) return;
    let gueltig = true;
    for (const s of Object.keys(bilder).map(Number)) {
      if (typeof bilder[s] !== "object") continue;
      kern<LesezeichenAufSeite[]>("lesezeichen.seite", { dokument_id: dokument.id, seite: s })
        .then((l) => gueltig && setFahnen((v) => ({ ...v, [s]: l })))
        .catch(() => undefined);
    }
    return () => {
      gueltig = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mitLesezeichen, lesezeichenStand, geladen, dokument.id]);

  // Markieren im Original: mit der Maus über die Wörter ziehen (oder Doppelklick auf ein Wort).
  function punkt(e: ReactPointerEvent<HTMLDivElement> | ReactMouseEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
  }
  function auswahlMelden(el: HTMLElement, a: SeitenAuswahl) {
    const r = el.getBoundingClientRect();
    const teile = auswahlRechtecke(woerter[a.seite] ?? [], a.von, a.bis);
    if (!teile.length) return;
    const oben = Math.min(...teile.map((t) => t.y));
    const unten = Math.max(...teile.map((t) => t.y + t.h));
    const links = Math.min(...teile.map((t) => t.x));
    const rechts = Math.max(...teile.map((t) => t.x + t.b));
    anmerkungen?.onAuswahl(
      a,
      new DOMRect(r.left + links * r.width, r.top + oben * r.height, (rechts - links) * r.width, (unten - oben) * r.height),
    );
  }
  const ziehen = (s: number) =>
    anmerkungen && woerter[s]?.length
      ? {
          onPointerDown: (e: ReactPointerEvent<HTMLDivElement>) => {
            if (e.button !== 0 || (e.target as Element).closest("[data-anmerkung]")) return;
            const p = punkt(e);
            const i = wortAn(woerter[s], p.x, p.y);
            if (i == null) return;
            e.preventDefault();
            e.currentTarget.setPointerCapture(e.pointerId);
            zug.current = { seite: s, anker: i, x: e.clientX, y: e.clientY, bewegt: false };
          },
          onPointerMove: (e: ReactPointerEvent<HTMLDivElement>) => {
            const z = zug.current;
            if (!z) return;
            if (!z.bewegt && Math.hypot(e.clientX - z.x, e.clientY - z.y) < 5) return;
            z.bewegt = true;
            const p = punkt(e);
            const i = wortAn(woerter[s], p.x, p.y) ?? z.anker;
            setGezogen({ seite: s, von: Math.min(z.anker, i), bis: Math.max(z.anker, i) });
          },
          onPointerUp: (e: ReactPointerEvent<HTMLDivElement>) => {
            const z = zug.current;
            zug.current = null;
            if (!z) return;
            if (z.bewegt && gezogen) auswahlMelden(e.currentTarget, gezogen);
            else if (anmerkungen.auswahl) anmerkungen.onAuswahl(null);
            setGezogen(null);
          },
          onDoubleClick: (e: ReactMouseEvent<HTMLDivElement>) => {
            if ((e.target as Element).closest("[data-anmerkung]")) return;
            const p = punkt(e);
            const i = wortAn(woerter[s], p.x, p.y);
            if (i != null) auswahlMelden(e.currentTarget, { seite: s, von: i, bis: i });
          },
        }
      : {};
  const gewaehlt = gezogen ?? anmerkungen?.auswahl ?? null;

  return (
    <div className="original" ref={rahmen} {...(anmerkungen ? anmerkungsHandler(anmerkungen.ereignisse) : {})}>
      <p className="dokument-info">
        Originaldatei aus der Ablage der Akte, {seiten} {seiten === 1 ? "Seite" : "Seiten"}. {hinweis}
      </p>
      {Array.from({ length: seiten }, (_, i) => i + 1).map((s) => {
        const b = bilder[s];
        return (
          <figure key={s} id={`seite-${s}`} data-seite={s} className="original-seite">
            {typeof b === "object" ? (
              <div className={`original-bild${anmerkungen && woerter[s]?.length ? " anm-waehlbar" : ""}`} {...ziehen(s)}>
                <img draggable={false} src={b.bild} width={b.breite} height={b.hoehe} alt={`Seite ${s} von ${dokument.dateiname}`} />
                {b.markierungen.map((m, i) => (
                  <span
                    key={i}
                    className="markierung"
                    style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%`, width: `${m.b * 100}%`, height: `${m.h * 100}%` }}
                  />
                ))}
                {(fahnen[s] ?? []).map((z) => (
                  <span
                    key={`lz${z.id}`}
                    className="lz-fahne lz-fahne-seite"
                    data-lesezeichen={z.id}
                    title={`Lesezeichen: ${z.titel}`}
                    style={{ top: `${(z.y ?? 0.02) * 100}%` }}
                  >
                    <Zeichen name="lesezeichen" groesse={16} />
                  </span>
                ))}
                {gewaehlt?.seite === s &&
                  auswahlRechtecke(woerter[s] ?? [], gewaehlt.von, gewaehlt.bis).map((r, i) => (
                    <span
                      key={`w${i}`}
                      className="anm-seitenauswahl"
                      style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.b * 100}%`, height: `${r.h * 100}%` }}
                    />
                  ))}
                {(aufSeite[s] ?? []).flatMap((a) =>
                  a.rechtecke.map((r, i) => (
                    <span
                      key={`a${a.id}-${i}`}
                      className={`anm-rechteck ${stueckKlassen([a])}${a.id === anmerkungen?.aktiv ? " anm-aktiv" : ""}`}
                      data-anmerkung={a.id}
                      style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.b * 100}%`, height: `${r.h * 100}%` }}
                    >
                      {a.kommentar && i === a.rechtecke.length - 1 && (
                        <span className={`anm-blase anm-blase-${a.farbe}`} aria-hidden>
                          <Zeichen name="kommentar" groesse={11} />
                        </span>
                      )}
                    </span>
                  )),
                )}
              </div>
            ) : typeof b === "string" ? (
              <p className="fehler" role="alert">Seite {s} lässt sich nicht anzeigen: {b}</p>
            ) : (
              <div className="original-platzhalter">Seite {s} wird geladen …</div>
            )}
            <figcaption>Seite {s}</figcaption>
          </figure>
        );
      })}
    </div>
  );
}

export function NormenAnsicht({
  normen,
  onFundstelle,
  leer = "In dieser Akte wurden keine Normzitate erkannt.",
}: {
  normen: NormEintrag[];
  onFundstelle: (dokumentId: number, abschnitt: number) => void;
  leer?: string;
}) {
  if (normen.length === 0) return <p className="leer">{leer}</p>;
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

export function RechtsprechungAnsicht({
  urteile,
  offen,
  laeuft,
  onFundstelle,
  onErgaenzen,
  onVolltexteLaden,
  onOnlinePruefen,
  onVolltext,
  onEntfernen,
  leer = "In dieser Akte wurden keine Rechtsprechungszitate erkannt.",
}: {
  urteile: UrteilEintrag[];
  offen: number | null;
  laeuft: boolean;
  leer?: string;
  onFundstelle: (dokumentId: number, abschnitt: number) => void;
  onErgaenzen: (u: UrteilEintrag) => void;
  onVolltexteLaden: (zitat?: string) => void;
  onOnlinePruefen: () => void;
  onVolltext: (urteilId: number, rn?: number) => void;
  onEntfernen: (u: UrteilInfo) => void;
}) {
  const [kopiert, setKopiert] = useState<string | null>(null);
  if (urteile.length === 0) return <p className="leer">{leer}</p>;
  const ohneVerzeichnis = urteile.some((u) => u.status === "kein_verzeichnis");
  const ladbar = urteile.filter((u) => u.status === "belegt" && !u.urteil && u.entscheidung).length;
  const online = urteile.filter((u) => u.online_offen);
  const onlineQuellen = [...new Set(online.map((u) => ONLINE_QUELLE[u.online_offen!]))].join(" und ");
  async function kopiere(link: string) {
    await navigator.clipboard.writeText(link);
    setKopiert(link);
  }
  return (
    <>
      {ohneVerzeichnis && (
        <p className="hinweis">
          Das Verzeichnis der Bundesrechtsprechung ist noch nicht geladen. Lade es in den Einstellungen unter
          „Rechtsquellen“ und wähle danach hier „Zitate neu prüfen“.
        </p>
      )}
      {online.length > 0 && (
        <div className="volltexte-laden">
          <button className="zweitrangig" onClick={onOnlinePruefen} disabled={laeuft}>
            Online prüfen ({online.length})
          </button>
          <span className="fundort">
            Sucht offene Zitate bei {onlineQuellen}. Gesendet wird nur das Aktenzeichen der zitierten Entscheidung.
          </span>
        </div>
      )}
      {ladbar > 0 && (
        <div className="volltexte-laden">
          <button className="zweitrangig" onClick={() => onVolltexteLaden()} disabled={laeuft}>
            Alle Volltexte laden ({ladbar})
          </button>
          <span className="fundort">
            Belegte Entscheidungen aus der Quelle, die sie belegt hat (rechtsprechung-im-internet.de, gesetze-bayern.de
            oder NeuRIS); danach prüft die App zitierte Randnummern. Gesendet wird nur die Nummer der Entscheidung.
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
            {u.online_gesperrt && <div className="fundort">{u.online_gesperrt}</div>}
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
                    Entscheidung entfernen
                  </button>
                </>
              ) : (
                <>
                  {u.status === "belegt" && u.entscheidung && (
                    <button className="link" onClick={() => onVolltexteLaden(u.zitat)} disabled={laeuft}>
                      Volltext laden
                    </button>
                  )}
                  <button className="link" onClick={() => onErgaenzen(u)} disabled={laeuft}>
                    {u.status === "belegt" ? "eigene Datei ergänzen …" : "Urteil selbst ergänzen …"}
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="grenze">
        Geprüft wird, ob es eine Entscheidung dieses Gerichts mit diesem Aktenzeichen und Datum gibt, nicht, ob sie die
        zitierte Aussage trägt; das zeigt die Gegenüberstellung oben. Bundesgerichte prüft die App gegen das Verzeichnis von rechtsprechung-im-internet.de (und auf
        Wunsch bei NeuRIS), bayerische Gerichte online bei gesetze-bayern.de; dort stehen nur zur Veröffentlichung
        bestimmte Entscheidungen. Andere Gerichte und der EuGH lassen sich als eigene Datei ergänzen, z. B. als
        PDF-Ausdruck aus juris oder beck-online.
      </p>
    </>
  );
}

/** Entscheidungen, die aus dem Bereich „Rechtsprechung“ zugeordnet wurden, ohne dass ein Dokument sie zitiert. */
export function ZugeordneteUrteile({
  urteile,
  offen,
  laeuft,
  onVolltext,
  onLoesen,
}: {
  urteile: UrteilInfo[];
  offen: number | null;
  laeuft: boolean;
  onVolltext: (urteilId: number) => void;
  onLoesen: (u: UrteilInfo) => void;
}) {
  return (
    <section className="zugeordnet">
      <h3 className="abschnitt-titel">Zur weiteren Bearbeitung zugeordnet</h3>
      <p className="leise">
        Aus dem Bereich „Rechtsprechung“ dieser Akte zugeordnet, in den Dokumenten bisher nicht zitiert. Sie stehen auch
        dem Chat und der Gegenüberstellung zur Verfügung.
      </p>
      <ul className="normen">
        {urteile.map((u) => (
          <li key={u.id}>
            <div>
              <strong>{urteilTitel(u)}</strong>
            </div>
            {u.kopf?.titel && <div className="titel">{u.kopf.titel}</div>}
            <div className="fundort">
              {URTEIL_QUELLE_NAME[u.quelle]}
              {u.quelle === "manuell" && ` (${urteilHerkunft(u)})`}
            </div>
            <div className="urteil-aktionen">
              <button className="link" onClick={() => onVolltext(u.id)}>
                {offen === u.id ? "Volltext schließen" : "Volltext anzeigen"}
              </button>
              <button
                className="link klein"
                onClick={() => onLoesen(u)}
                disabled={laeuft}
                title="Die Entscheidung bleibt im Bereich „Rechtsprechung“"
              >
                Zuordnung lösen
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ErgaenzungsFrage({
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

export function VolltextAnsicht({
  volltext,
  rn,
  onSchliessen,
  aktionen,
}: {
  volltext: UrteilVolltext;
  rn: number | null;
  onSchliessen: () => void;
  /** Weitere Knöpfe in der Leiste, z. B. „In die Sammlung“ bei einem Treffer der Online-Suche. */
  aktionen?: ReactNode;
}) {
  const v = volltext;
  useEffect(() => {
    if (rn != null) document.getElementById(`vt-rn-${rn}`)?.scrollIntoView({ block: "center" });
  }, [rn, v.id]);
  let teil: string | null = null;
  return (
    <aside className="akte-seite volltext">
      {/* Eigene Leiste oben, bleibt beim Blättern stehen: Schließen ist immer erreichbar. */}
      <div className="volltext-leiste">
        <span className="leise">{v.id == null ? "Treffer, noch nicht gespeichert" : "Volltext"}</span>
        {aktionen}
        <button className="zweitrangig klein" onClick={onSchliessen}>
          Volltext schließen
        </button>
      </div>
      <div className="volltext-kopf">
        <strong>
          {[v.gericht, v.kopf?.spruchkoerper].filter(Boolean).join(" ")}
          {v.datum && `, ${v.kopf?.doktyp ?? "Entscheidung"} vom ${v.datum.split("-").reverse().join(".")}`}
          {v.aktenzeichen && ` – ${v.aktenzeichen}`}
        </strong>
      </div>
      <p className="fundort">
        {v.quelle === "manuell" ? "Selbst ergänzt" : "Geladen"}: {urteilHerkunft(v)}
      </p>
      {QUELLEN_HINWEIS[v.quelle] && <p className="fundort">{QUELLEN_HINWEIS[v.quelle]}</p>}
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
        const kopf = a.teil && a.teil !== teil ? URTEIL_TEILE[a.teil] ?? a.teil[0].toUpperCase() + a.teil.slice(1) : null;
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
