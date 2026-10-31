import { KeyboardEvent, ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  Anmerkung,
  AnmerkFarbe,
  AnmerkFilter,
  AnmerkStil,
  anmerkungOrt,
  BEDEUTUNG_VORGABE,
  Bedeutungen,
  Block,
  FARB_NAME,
  FARBEN,
  filtereAnmerkungen,
  formatiere,
  Inline,
  KEIN_ANMERK_FILTER,
  kommentarText,
  markdownBloecke,
  STILE,
} from "./anmerkungLogik";
import { istDesktop, kern } from "./kern";
import type { LesezeichenStelle } from "./Lesezeichen";
import Zeichen from "./Symbole";

// --- Bedeutung der Farben (je Arbeitsumgebung, im Kern gespeichert) ----------------------------------------------------

let bedeutungenStand: Bedeutungen = BEDEUTUNG_VORGABE;
const bedeutungenHoerer = new Set<(b: Bedeutungen) => void>();
let bedeutungenGeladen = false;

export function bedeutungenGeaendert(b: Bedeutungen) {
  bedeutungenStand = b;
  bedeutungenHoerer.forEach((h) => h(b));
}

/** Bedeutung der Farben (Gelb = Wichtig …); einmal geladen, Änderungen in den Einstellungen kommen überall an. */
export function useBedeutungen(): Bedeutungen {
  const [b, setB] = useState(bedeutungenStand);
  useEffect(() => {
    bedeutungenHoerer.add(setB);
    if (!bedeutungenGeladen && istDesktop) {
      bedeutungenGeladen = true;
      kern<Bedeutungen>("anmerkungen.bedeutungen")
        .then(bedeutungenGeaendert)
        .catch(() => {
          bedeutungenGeladen = false;
        });
    }
    return () => {
      bedeutungenHoerer.delete(setB);
    };
  }, []);
  return b;
}

// --- Markdown ------------------------------------------------------------------------------------------------------

function InlineText({ teile }: { teile: Inline[] }) {
  return (
    <>
      {teile.map((t, i) => {
        let el: ReactNode = t.code ? <code>{t.text}</code> : t.text;
        if (t.kursiv) el = <em>{el}</em>;
        if (t.fett) el = <strong>{el}</strong>;
        return <span key={i}>{el}</span>;
      })}
    </>
  );
}

/** Kommentar mit einfachem Markdown; HTML im Text wird nie ausgewertet. */
export function MarkdownText({ text }: { text: string }) {
  const bloecke = useMemo(() => markdownBloecke(text), [text]);
  return (
    <div className="markdown">
      {bloecke.map((b: Block, i) =>
        b.art === "code" ? (
          <pre key={i}>
            <code>{b.text}</code>
          </pre>
        ) : b.art === "liste" ? (
          b.geordnet ? (
            <ol key={i}>
              {b.punkte.map((p, j) => (
                <li key={j}>
                  <InlineText teile={p} />
                </li>
              ))}
            </ol>
          ) : (
            <ul key={i}>
              {b.punkte.map((p, j) => (
                <li key={j}>
                  <InlineText teile={p} />
                </li>
              ))}
            </ul>
          )
        ) : (
          <p key={i}>
            {b.zeilen.map((z, j) => (
              <span key={j}>
                {j > 0 && <br />}
                <InlineText teile={z} />
              </span>
            ))}
          </p>
        ),
      )}
    </div>
  );
}

// --- Auswahl im Text -----------------------------------------------------------------------------------------------

/** Zeichen vom Anfang des Absatzes ``p`` bis zur Stelle (node, offset); Sprechblasen ([data-kein-text]) zählen nicht. */
function zeichenBis(p: HTMLElement, node: Node, offset: number): number {
  const r = document.createRange();
  r.setStart(p, 0);
  r.setEnd(node, offset);
  return textLaenge(r.cloneContents());
}

function textLaenge(f: DocumentFragment): number {
  f.querySelectorAll("[data-kein-text]").forEach((e) => e.remove());
  return f.textContent?.length ?? 0;
}

/** Absatz eines Dokuments, in dem ``node`` steht, oder der nächste danach (bei einer Stelle zwischen Abschnitten). */
function absatzVon(root: HTMLElement, node: Node, vorne: boolean): { p: HTMLElement; amRand: boolean } | null {
  const el = node.nodeType === Node.ELEMENT_NODE ? (node as HTMLElement) : node.parentElement;
  const p = el?.closest<HTMLElement>("p[data-beginn]");
  if (p && root.contains(p)) return { p, amRand: false };
  const alle = [...root.querySelectorAll<HTMLElement>("p[data-beginn]")];
  const folgend = alle.filter((x) => node.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_FOLLOWING);
  const vorher = alle.filter((x) => node.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_PRECEDING);
  const p2 = vorne ? folgend[0] : vorher[vorher.length - 1];
  return p2 ? { p: p2, amRand: true } : null;
}

/** Die aktuelle Textauswahl als Lage im Dokument (wie im Kern), oder null. */
export function auswahlImDokument(root: HTMLElement): { start: number; ende: number; rect: DOMRect } | null {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const r = sel.getRangeAt(0);
  if (!root.contains(r.commonAncestorContainer)) return null;
  const a = absatzVon(root, r.startContainer, true);
  const b = absatzVon(root, r.endContainer, false);
  if (!a || !b) return null;
  const start = Number(a.p.dataset.beginn) + (a.amRand ? 0 : zeichenBis(a.p, r.startContainer, r.startOffset));
  const ende =
    Number(b.p.dataset.beginn) +
    (b.amRand ? textLaenge(rangeInhalt(b.p)) : zeichenBis(b.p, r.endContainer, r.endOffset));
  if (!(ende > start)) return null;
  return { start, ende, rect: r.getBoundingClientRect() };
}

function rangeInhalt(p: HTMLElement): DocumentFragment {
  const r = document.createRange();
  r.selectNodeContents(p);
  return r.cloneContents();
}

// --- Schwebende Fenster ----------------------------------------------------------------------------------------------

type Lage = { x: number; y: number; oben: number; unten: number };

function lageVon(rect: DOMRect): Lage {
  return { x: rect.left + rect.width / 2, y: rect.top, oben: rect.top, unten: rect.bottom };
}

/** Hält ein schwebendes Fenster im sichtbaren Bereich: über der Stelle, sonst darunter. */
function useSchwebend(lage: Lage, ueber: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [stil, setStil] = useState<{ left: number; top: number; visibility?: "hidden" }>({
    left: lage.x,
    top: lage.oben,
    visibility: "hidden",
  });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const b = el.offsetWidth;
    const h = el.offsetHeight;
    const links = Math.min(Math.max(8, lage.x - b / 2), window.innerWidth - b - 8);
    const obenPasst = lage.oben - h - 10 >= 8;
    const top = ueber && obenPasst ? lage.oben - h - 10 : Math.min(lage.unten + 10, window.innerHeight - h - 8);
    setStil({ left: links, top: Math.max(8, top) });
  }, [lage.x, lage.oben, lage.unten, ueber]);
  return { ref, stil };
}

/** Kleines Menü über einer Textauswahl: vier Farben, Unter-/Durchstreichen, Kommentar. */
function AuswahlMenue({
  lage,
  bedeutungen,
  onMarkieren,
  onKommentar,
  onLesezeichen,
}: {
  lage: Lage;
  bedeutungen: Bedeutungen;
  onMarkieren: (farbe: AnmerkFarbe, stil: AnmerkStil) => void;
  onKommentar: () => void;
  onLesezeichen?: () => void;
}) {
  const { ref, stil } = useSchwebend(lage, true);
  // Sofort sichtbare Erklärung unter den Knöpfen; der Tooltip des Systems kommt spät oder gar nicht.
  const [hinweis, setHinweis] = useState<string | null>(null);
  const zeige = (text: string) => ({ onMouseEnter: () => setHinweis(text), onMouseLeave: () => setHinweis(null) });
  const legende = FARBEN.map((f) => `${FARB_NAME[f]} = ${bedeutungen[f]}`).join(" · ");
  return (
    <div
      ref={ref}
      className="anm-menue"
      style={stil}
      role="toolbar"
      aria-label="Auswahl markieren"
      onMouseDown={(e) => e.preventDefault() /* Auswahl im Text behalten */}
    >
      {FARBEN.map((f) => (
        <button
          key={f}
          className={`anm-farbknopf anm-punkt-${f}`}
          title={`${bedeutungen[f]} (${FARB_NAME[f]})`}
          aria-label={`Markieren: ${bedeutungen[f]}`}
          {...zeige(`${FARB_NAME[f]} markieren: „${bedeutungen[f]}“`)}
          onClick={() => onMarkieren(f, "flaeche")}
        />
      ))}
      <span className="anm-menue-trenner" />
      <button className="anm-menue-knopf" title="Unterstreichen (rot)" {...zeige("Rot unterstreichen")} onClick={() => onMarkieren("rot", "unterstrichen")}>
        <u>U</u>
      </button>
      <button className="anm-menue-knopf" title="Durchstreichen (rot)" {...zeige("Rot durchstreichen")} onClick={() => onMarkieren("rot", "durchgestrichen")}>
        <s>S</s>
      </button>
      <span className="anm-menue-trenner" />
      <button className="anm-menue-knopf" title="Markieren und kommentieren" {...zeige("Gelb markieren und Kommentar schreiben")} onClick={onKommentar}>
        <Zeichen name="kommentar" groesse={15} /> Kommentar
      </button>
      {onLesezeichen && (
        <button className="anm-menue-knopf" title="Lesezeichen an dieser Stelle" {...zeige("Lesezeichen an dieser Stelle setzen")} onClick={onLesezeichen}>
          <Zeichen name="lesezeichen" groesse={15} />
        </button>
      )}
      <span className="anm-menue-hinweis">{hinweis ?? legende}</span>
    </div>
  );
}

function Datum({ iso }: { iso: string }) {
  const d = new Date(iso);
  return <>{isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-DE")}</>;
}

/** Vorschau beim Überfahren: Bedeutung, Kommentar, Datum. */
function Vorschau({ anmerkung, bedeutungen, lage }: { anmerkung: Anmerkung; bedeutungen: Bedeutungen; lage: Lage }) {
  const { ref, stil } = useSchwebend(lage, false);
  return (
    <div ref={ref} className="anm-vorschau" style={stil} role="tooltip">
      {anmerkung.kommentar ? <MarkdownText text={anmerkung.kommentar} /> : <p className="leise">Ohne Kommentar</p>}
      <p className="anm-vorschau-fuss">
        <span className={`anm-punkt anm-punkt-${anmerkung.farbe}`} /> {bedeutungen[anmerkung.farbe]} ·{" "}
        <Datum iso={anmerkung.geaendert_am} /> · Klick zum Bearbeiten
      </p>
    </div>
  );
}

/** Kompaktes Fenster zum Bearbeiten: Farbe, Darstellung, Kommentar (Markdown), Löschen. */
function Editor({
  anmerkung,
  bedeutungen,
  lage,
  onSpeichern,
  onLoeschen,
  onSchliessen,
}: {
  anmerkung: Anmerkung;
  bedeutungen: Bedeutungen;
  lage: Lage;
  onSpeichern: (farbe: AnmerkFarbe, stil: AnmerkStil, kommentar: string) => Promise<void>;
  onLoeschen: () => Promise<void>;
  onSchliessen: () => void;
}) {
  const { ref, stil } = useSchwebend(lage, false);
  const [farbe, setFarbe] = useState(anmerkung.farbe);
  const [darstellung, setDarstellung] = useState(anmerkung.stil);
  const [text, setText] = useState(anmerkung.kommentar ?? "");
  const [vorschau, setVorschau] = useState(false);
  const [laeuft, setLaeuft] = useState(false);
  const feld = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    feld.current?.focus();
  }, []);

  function format(art: Parameters<typeof formatiere>[3]) {
    const el = feld.current;
    if (!el) return;
    const r = formatiere(text, el.selectionStart, el.selectionEnd, art);
    setText(r.text);
    setVorschau(false);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(r.von, r.bis);
    });
  }

  async function speichern() {
    setLaeuft(true);
    try {
      await onSpeichern(farbe, darstellung, text);
    } finally {
      setLaeuft(false);
    }
  }

  function tasten(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onSchliessen();
    } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void speichern();
    } else if ((e.metaKey || e.ctrlKey) && (e.key === "b" || e.key === "i")) {
      e.preventDefault();
      format(e.key === "b" ? "fett" : "kursiv");
    }
  }

  return (
    <div
      ref={ref}
      className="anm-editor"
      style={stil}
      role="dialog"
      aria-label="Anmerkung bearbeiten"
      onKeyDown={tasten}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="anm-editor-zeile">
        {FARBEN.map((f) => (
          <button
            key={f}
            className={`anm-farbwahl${farbe === f ? " aktiv" : ""}`}
            aria-pressed={farbe === f}
            onClick={() => setFarbe(f)}
          >
            <span className={`anm-punkt anm-punkt-${f}`} />
            {bedeutungen[f]}
          </button>
        ))}
      </div>
      <div className="anm-editor-zeile">
        {STILE.map((s) => (
          <button
            key={s.stil}
            className={`anm-stilwahl${darstellung === s.stil ? " aktiv" : ""}`}
            aria-pressed={darstellung === s.stil}
            title={s.name}
            onClick={() => setDarstellung(s.stil)}
          >
            {s.stil === "flaeche" ? <span className={`anm-stilprobe anm-${farbe}`}>ab</span> : s.stil === "unterstrichen" ? <u>ab</u> : <s>ab</s>}
          </button>
        ))}
      </div>
      {anmerkung.zitat && (
        <blockquote className={`anm-zitat anm-rand-${farbe}`} title={anmerkung.zitat}>
          {anmerkung.zitat.length > 160 ? `${anmerkung.zitat.slice(0, 159)}…` : anmerkung.zitat}
        </blockquote>
      )}
      <div className="anm-editor-werkzeug">
        <button title="Fett (Strg/⌘+B)" onClick={() => format("fett")}>
          <strong>F</strong>
        </button>
        <button title="Kursiv (Strg/⌘+I)" onClick={() => format("kursiv")}>
          <em>K</em>
        </button>
        <button title="Liste" onClick={() => format("liste")}>
          • Liste
        </button>
        <button title="Code" onClick={() => format("code")}>
          {"</>"}
        </button>
        <button title="Code-Block" onClick={() => format("codeblock")}>
          {"{ }"}
        </button>
        <button className={vorschau ? "aktiv" : ""} aria-pressed={vorschau} onClick={() => setVorschau(!vorschau)}>
          Vorschau
        </button>
      </div>
      {vorschau ? (
        <div className="anm-editor-vorschau">
          {text.trim() ? <MarkdownText text={text} /> : <p className="leise">Noch kein Kommentar.</p>}
        </div>
      ) : (
        <textarea
          ref={feld}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder="Kommentar (optional). **fett**, *kursiv*, - Liste, `Code`"
          aria-label="Kommentar"
        />
      )}
      <div className="anm-editor-fuss">
        <button className="gefahr-voll" onClick={() => void onLoeschen()} disabled={laeuft}>
          Löschen
        </button>
        <span>
          <button className="zweitrangig" onClick={onSchliessen}>
            Abbrechen
          </button>{" "}
          <button onClick={() => void speichern()} disabled={laeuft} title="Speichern (Strg/⌘+Enter)">
            Speichern
          </button>
        </span>
      </div>
    </div>
  );
}

// --- Steuerung je Dokument ---------------------------------------------------------------------------------------------

/** Gewählte Wörter auf einer Seite des Originals (Nummern aus ``anmerkungen.woerter``, einschließlich). */
export type SeitenAuswahl = { seite: number; von: number; bis: number };

/** Was die Originalansicht für Markierungen braucht: Anzeige, Mausereignisse und Auswahl auf den Seiten. */
export interface OriginalAnmerkungen {
  stand: number;
  aktiv: number | null;
  ereignisse: AnmerkungsEreignisse;
  /** Die Auswahl, über der gerade das Menü steht; die Ansicht hebt sie hervor. */
  auswahl: SeitenAuswahl | null;
  onAuswahl: (seite: SeitenAuswahl | null, rect?: DOMRect) => void;
}

export interface AnmerkungsEreignisse {
  /** Maus über einer Markierung oder Sprechblase. */
  onZeigen: (id: number, el: Element) => void;
  onVerbergen: () => void;
  onKlick: (id: number, el: Element) => void;
}

/**
 * Markierungen und Kommentare eines Dokuments: Liste, Menü über der Auswahl, Vorschau und Editor.
 * ``schicht`` gehört einmal in die Ansicht; Text- und Originalansicht melden Auswahl und Mausereignisse.
 */
export function useAnmerkungen(
  dokumentId: number | null,
  onGeaendert?: () => void,
  /** Menüpunkt „Lesezeichen“ über der Auswahl (Lesezeichen.tsx). */
  onLesezeichen?: (s: LesezeichenStelle) => void,
) {
  const bedeutungen = useBedeutungen();
  const [liste, setListe] = useState<Anmerkung[]>([]);
  // Zählt jede Änderung; die Originalansicht lädt damit ihre Rechtecke neu.
  const [stand, setStand] = useState(0);
  // Auswahl in der Textansicht (start/ende) oder auf einer Seite des Originals (Wortnummern).
  const [menue, setMenue] = useState<
    ({ start: number; ende: number } | { seite: SeitenAuswahl }) & { lage: Lage } | null
  >(null);
  const [vorschau, setVorschau] = useState<{ id: number; lage: Lage } | null>(null);
  const [editor, setEditor] = useState<{ id: number; lage: Lage } | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [aktiv, setAktiv] = useState<number | null>(null);
  const vorschauTakt = useRef<number>();

  const laden = useCallback(async () => {
    if (dokumentId == null || !istDesktop) {
      setListe([]);
      return;
    }
    try {
      setListe(await kern<Anmerkung[]>("anmerkungen.liste", { dokument_id: dokumentId }));
      setFehler(null);
    } catch (e) {
      setFehler(String(e));
    }
  }, [dokumentId]);

  useEffect(() => {
    setMenue(null);
    setEditor(null);
    setVorschau(null);
    setAktiv(null);
    void laden();
  }, [laden]);

  // Menü schließen, sobald die Auswahl weg ist oder gescrollt wird.
  useEffect(() => {
    if (!menue) return;
    const zu = () => setMenue(null);
    if ("seite" in menue) {
      // Im Original gibt es keine Textauswahl des Browsers; nur Scrollen schließt.
      window.addEventListener("scroll", zu, true);
      return () => window.removeEventListener("scroll", zu, true);
    }
    const auswahl = () => {
      if (window.getSelection()?.isCollapsed) setMenue(null);
    };
    document.addEventListener("selectionchange", auswahl);
    window.addEventListener("scroll", zu, true);
    return () => {
      document.removeEventListener("selectionchange", auswahl);
      window.removeEventListener("scroll", zu, true);
    };
  }, [menue]);

  // Editor schließt bei Klick daneben (Eingaben bleiben dann verworfen, wie „Abbrechen“).
  useEffect(() => {
    if (!editor) return;
    const daneben = (e: MouseEvent) => {
      if (!(e.target as Element).closest?.(".anm-editor")) setEditor(null);
    };
    const t = window.setTimeout(() => document.addEventListener("mousedown", daneben), 0);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("mousedown", daneben);
    };
  }, [editor]);

  async function geaendert() {
    await laden();
    setStand((s) => s + 1);
    onGeaendert?.();
  }

  async function anlegen(farbe: AnmerkFarbe, stil: AnmerkStil, mitKommentar: boolean) {
    if (!menue || dokumentId == null) return;
    const { lage } = menue;
    setMenue(null);
    window.getSelection()?.removeAllRanges();
    try {
      const neu =
        "seite" in menue
          ? await kern<Anmerkung>("anmerkungen.anlegen_seite", {
              dokument_id: dokumentId,
              seite: menue.seite.seite,
              wort_von: menue.seite.von,
              wort_bis: menue.seite.bis,
              farbe,
              stil,
            })
          : await kern<Anmerkung>("anmerkungen.anlegen", {
              dokument_id: dokumentId,
              start: menue.start,
              ende: menue.ende,
              farbe,
              stil,
            });
      await geaendert();
      setAktiv(neu.id);
      if (mitKommentar) setEditor({ id: neu.id, lage });
    } catch (e) {
      setFehler(String(e));
    }
  }

  /** Nach dem Loslassen der Maus im Text: Menü über der Auswahl zeigen. */
  function beiAuswahl(root: HTMLElement) {
    const a = auswahlImDokument(root);
    if (!a) return;
    setVorschau(null);
    setEditor(null);
    setMenue({ start: a.start, ende: a.ende, lage: lageVon(a.rect) });
  }

  /** Wörter auf einer Seite des Originals gewählt: dasselbe Menü wie in der Textansicht. */
  function beiSeitenAuswahl(seite: SeitenAuswahl | null, rect?: DOMRect) {
    setVorschau(null);
    setEditor(null);
    setFehler(null);
    setMenue(seite && rect ? { seite, lage: lageVon(rect) } : null);
  }

  const ereignisse: AnmerkungsEreignisse = {
    onZeigen: (id, el) => {
      window.clearTimeout(vorschauTakt.current);
      if (editor || menue) return;
      const lage = lageVon(el.getBoundingClientRect());
      vorschauTakt.current = window.setTimeout(() => setVorschau({ id, lage }), 250);
    },
    onVerbergen: () => {
      window.clearTimeout(vorschauTakt.current);
      setVorschau(null);
    },
    onKlick: (id, el) => {
      window.clearTimeout(vorschauTakt.current);
      setVorschau(null);
      setAktiv(id);
      setEditor({ id, lage: lageVon(el.getBoundingClientRect()) });
    },
  };

  const imEditor = editor ? liste.find((a) => a.id === editor.id) : undefined;
  const inVorschau = vorschau ? liste.find((a) => a.id === vorschau.id) : undefined;

  const schicht = (
    <>
      {fehler && <p className="fehler">{fehler}</p>}
      {menue && (
        <AuswahlMenue
          lage={menue.lage}
          bedeutungen={bedeutungen}
          onMarkieren={(f, s) => void anlegen(f, s, false)}
          onKommentar={() => void anlegen("gelb", "flaeche", true)}
          onLesezeichen={
            onLesezeichen &&
            (() => {
              const m = menue;
              setMenue(null);
              window.getSelection()?.removeAllRanges();
              onLesezeichen(
                "seite" in m ? { seite: m.seite.seite, wort_von: m.seite.von, wort_bis: m.seite.bis } : { start: m.start, ende: m.ende },
              );
            })
          }
        />
      )}
      {inVorschau && vorschau && !editor && <Vorschau anmerkung={inVorschau} bedeutungen={bedeutungen} lage={vorschau.lage} />}
      {imEditor && editor && (
        <Editor
          key={imEditor.id}
          anmerkung={imEditor}
          bedeutungen={bedeutungen}
          lage={editor.lage}
          onSchliessen={() => setEditor(null)}
          onSpeichern={async (farbe, stil, kommentar) => {
            try {
              await kern("anmerkungen.aendern", {
                anmerkung_id: imEditor.id,
                farbe,
                stil,
                kommentar,
                ohne_kommentar: !kommentar.trim(),
              });
              setEditor(null);
              await geaendert();
            } catch (e) {
              setFehler(String(e));
            }
          }}
          onLoeschen={async () => {
            try {
              await kern("anmerkungen.loeschen", { anmerkung_id: imEditor.id });
              setEditor(null);
              setAktiv(null);
              await geaendert();
            } catch (e) {
              setFehler(String(e));
            }
          }}
        />
      )}
    </>
  );

  const original: OriginalAnmerkungen = {
    stand,
    aktiv,
    ereignisse,
    auswahl: menue && "seite" in menue ? menue.seite : null,
    onAuswahl: beiSeitenAuswahl,
  };

  return { liste, stand, aktiv, setAktiv, bedeutungen, beiAuswahl, ereignisse, schicht, original, oeffneEditor: ereignisse.onKlick };
}

/** Mausereignisse eines Bereichs mit Markierungen ([data-anmerkung]) an die Steuerung weitergeben. */
export function anmerkungsHandler(e: AnmerkungsEreignisse) {
  const ziel = (t: EventTarget | null) => {
    const el = (t as Element | null)?.closest?.("[data-anmerkung]");
    if (!el) return null;
    const ids = (el.getAttribute("data-anmerkung") ?? "").split(" ").map(Number).filter(Boolean);
    return ids.length ? { id: ids[ids.length - 1], el } : null;
  };
  return {
    onMouseOver: (ev: { target: EventTarget | null }) => {
      const z = ziel(ev.target);
      if (z) e.onZeigen(z.id, z.el);
    },
    onMouseOut: (ev: { target: EventTarget | null; relatedTarget: EventTarget | null }) => {
      const z = ziel(ev.target);
      if (z && !z.el.contains(ev.relatedTarget as Node | null)) e.onVerbergen();
    },
    onClick: (ev: { target: EventTarget | null }) => {
      if (!window.getSelection()?.isCollapsed) return; // Teil einer neuen Auswahl
      if ((ev.target as Element | null)?.closest?.("button.zitat")) return; // Normzitat hat eigenen Klick
      const z = ziel(ev.target);
      if (z) e.onKlick(z.id, z.el);
    },
  };
}

// --- Liste neben dem Dokument und Reiter der Akte -----------------------------------------------------------------------

export function FilterLeiste({
  liste,
  filter,
  onFilter,
  bedeutungen,
  suchtext,
}: {
  liste: Anmerkung[];
  filter: AnmerkFilter;
  onFilter: (f: AnmerkFilter) => void;
  bedeutungen: Bedeutungen;
  suchtext: string;
}) {
  return (
    <>
      <input
        type="search"
        className="anm-suche"
        value={filter.suche}
        onChange={(e) => onFilter({ ...filter, suche: e.target.value })}
        placeholder={suchtext}
        aria-label={suchtext}
      />
      <div className="anm-chips" role="group" aria-label="Nach Bedeutung filtern">
        {FARBEN.map((f) => {
          const an = filter.farben.includes(f);
          const n = liste.filter((a) => a.farbe === f).length;
          return (
            <button
              key={f}
              className={`anm-chip${an ? " aktiv" : ""}`}
              aria-pressed={an}
              onClick={() => onFilter({ ...filter, farben: an ? filter.farben.filter((x) => x !== f) : [...filter.farben, f] })}
            >
              <span className={`anm-punkt anm-punkt-${f}`} />
              {bedeutungen[f]} <span className="anzahl">{n}</span>
            </button>
          );
        })}
        <button
          className={`anm-chip${filter.nurKommentar ? " aktiv" : ""}`}
          aria-pressed={filter.nurKommentar}
          onClick={() => onFilter({ ...filter, nurKommentar: !filter.nurKommentar })}
        >
          <Zeichen name="kommentar" groesse={13} /> mit Kommentar
        </button>
      </div>
    </>
  );
}

export function AnmerkungsEintrag({
  a,
  bedeutungen,
  aktiv,
  onWaehle,
  mitDokument,
}: {
  a: Anmerkung;
  bedeutungen: Bedeutungen;
  aktiv: boolean;
  onWaehle: (a: Anmerkung, el: Element) => void;
  mitDokument?: boolean;
}) {
  return (
    <li>
      <button
        className={`anm-eintrag${aktiv ? " aktiv" : ""}${a.status === "nicht_gefunden" ? " verloren" : ""}`}
        onClick={(e) => onWaehle(a, e.currentTarget)}
        title={a.status === "nicht_gefunden" ? "Der markierte Wortlaut steht nach einer Änderung nicht mehr im Text." : undefined}
      >
        {mitDokument && <span className="anm-eintrag-dok">{a.dokument}</span>}
        <span className={`anm-zitat anm-rand-${a.farbe} anm-stil-${a.stil}`}>{a.zitat}</span>
        {a.kommentar && <span className="anm-eintrag-kommentar">{kommentarText(a.kommentar)}</span>}
        <span className="anm-eintrag-fuss">
          {[anmerkungOrt(a), bedeutungen[a.farbe]].filter(Boolean).join(" · ")}
          {a.kommentar && (
            <>
              {" · "}
              <Zeichen name="kommentar" groesse={12} />
            </>
          )}
        </span>
      </button>
    </li>
  );
}

/** Seitenleiste neben Text und Original: Anmerkungen des geöffneten Dokuments. */
export function AnmerkungsLeiste({
  liste,
  bedeutungen,
  aktiv,
  onWaehle,
  onAkte,
  onSchliessen,
  lesezeichen,
  lesezeichenAnzahl = 0,
}: {
  liste: Anmerkung[];
  bedeutungen: Bedeutungen;
  aktiv: number | null;
  onWaehle: (a: Anmerkung, el: Element) => void;
  onAkte: () => void;
  onSchliessen: () => void;
  /** Inhalt des Reiters „Lesezeichen“ (Lesezeichen.tsx). */
  lesezeichen?: ReactNode;
  lesezeichenAnzahl?: number;
}) {
  const [filter, setFilter] = useState<AnmerkFilter>(KEIN_ANMERK_FILTER);
  const [teil, setTeil] = useState<"anmerkungen" | "lesezeichen">(() => {
    try {
      return localStorage.getItem("akte.leiste.teil") === "lesezeichen" ? "lesezeichen" : "anmerkungen";
    } catch {
      return "anmerkungen";
    }
  });
  function waehleTeil(t: typeof teil) {
    setTeil(t);
    try {
      localStorage.setItem("akte.leiste.teil", t);
    } catch {
      // Ohne Speicher gilt die Wahl bis zum Neustart.
    }
  }
  const sichtbar = filtereAnmerkungen(liste, filter, bedeutungen);
  return (
    <aside className="akte-seite anm-leiste" aria-label="Anmerkungen und Lesezeichen">
      <div className="anm-leiste-kopf">
        {lesezeichen ? (
          <div className="anm-leiste-reiter" role="tablist">
            <button role="tab" aria-selected={teil === "anmerkungen"} className={teil === "anmerkungen" ? "aktiv" : ""} onClick={() => waehleTeil("anmerkungen")}>
              Anmerkungen{liste.length > 0 && <span className="anzahl">{liste.length}</span>}
            </button>
            <button role="tab" aria-selected={teil === "lesezeichen"} className={teil === "lesezeichen" ? "aktiv" : ""} onClick={() => waehleTeil("lesezeichen")}>
              Lesezeichen{lesezeichenAnzahl > 0 && <span className="anzahl">{lesezeichenAnzahl}</span>}
            </button>
          </div>
        ) : (
          <h3>Anmerkungen</h3>
        )}
        {teil === "anmerkungen" && (
          <button className="link" onClick={onAkte} title="Alle Anmerkungen der Akte, mit Suche">
            Ganze Akte
          </button>
        )}
        <button className="leisten-knopf" onClick={onSchliessen} title="Seitenleiste ausblenden" aria-label="Seitenleiste ausblenden">
          ×
        </button>
      </div>
      {lesezeichen && teil === "lesezeichen" ? (
        lesezeichen
      ) : liste.length === 0 ? (
        <p className="leise anm-leer">
          Text auswählen, dann im Menü über der Auswahl eine Farbe oder „Kommentar“ wählen.
        </p>
      ) : (
        <>
          <FilterLeiste liste={liste} filter={filter} onFilter={setFilter} bedeutungen={bedeutungen} suchtext="In diesem Dokument suchen" />
          <ul className="anm-liste">
            {sichtbar.map((a) => (
              <AnmerkungsEintrag key={a.id} a={a} bedeutungen={bedeutungen} aktiv={a.id === aktiv} onWaehle={onWaehle} />
            ))}
            {sichtbar.length === 0 && <li className="leise">Keine passende Anmerkung.</li>}
          </ul>
        </>
      )}
    </aside>
  );
}

/** Einstellungen → Akten: Bedeutung der vier Farben. */
export function BedeutungenKarte() {
  const bedeutungen = useBedeutungen();
  const [werte, setWerte] = useState<Bedeutungen>(bedeutungen);
  const [meldung, setMeldung] = useState<string | null>(null);
  useEffect(() => setWerte(bedeutungen), [bedeutungen]);
  // Neu laden: Die Bedeutungen gehören zur Arbeitsumgebung, die hier gewechselt werden kann.
  useEffect(() => {
    if (istDesktop) kern<Bedeutungen>("anmerkungen.bedeutungen").then(bedeutungenGeaendert).catch(() => undefined);
  }, []);
  const geaendert = FARBEN.some((f) => werte[f] !== bedeutungen[f]);

  async function speichern() {
    try {
      bedeutungenGeaendert(await kern<Bedeutungen>("anmerkungen.bedeutungen_setzen", { werte }));
      setMeldung("Gespeichert.");
    } catch (e) {
      setMeldung(String(e));
    }
  }

  return (
    <section className="karte">
      <h2>Markierungen</h2>
      <p className="leise">
        Was die Farben beim Markieren in Dokumenten bedeuten. Nach diesen Bedeutungen lässt sich in der Akte filtern und
        suchen.
      </p>
      <div className="anm-bedeutungen">
        {FARBEN.map((f) => (
          <label key={f}>
            <span className={`anm-punkt anm-punkt-${f}`} />
            <input
              value={werte[f]}
              maxLength={40}
              onChange={(e) => {
                setWerte({ ...werte, [f]: e.target.value });
                setMeldung(null);
              }}
            />
          </label>
        ))}
      </div>
      <div className="aktionen">
        <button onClick={() => void speichern()} disabled={!geaendert || FARBEN.some((f) => !werte[f].trim())}>
          Speichern
        </button>
        <button className="zweitrangig" onClick={() => setWerte(BEDEUTUNG_VORGABE)}>
          Vorgabe
        </button>
        {meldung && <span className="leise">{meldung}</span>}
      </div>
    </section>
  );
}
