import { KeyboardEvent, PointerEvent as ReactPointerEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useFremdeAenderung } from "./aenderungen";
import {
  Anordnung,
  MAX_SPALTEN,
  MIN_SPALTEN,
  SPALTEN_ARTEN,
  Spalte,
  SpaltenArt,
  SprungZiel,
  anordnungMerken,
  anteileVon,
  gemerkteAnordnung,
  gemerkteLage,
  lageMerken,
  spalteEntfernen,
  spalteSetzen,
  spaltenZahl,
  terminAnordnung,
  trennerVerschieben,
  vorTerminHolen,
  vorTerminMerken,
  zielSpalte,
} from "./arbeitsfensterLogik";
import { darstellungLesen, fensterThema } from "./darstellung";
import Dialog from "./Dialog";
import { DokumentAnsicht, NormenAnsicht, OriginalAnsicht, VolltextAnsicht } from "./DokumentAnsicht";
import {
  Akte,
  AktenDokument,
  DokumentInhalt,
  NormEintrag,
  urteilStatusText,
  UrteilEintrag,
  UrteilVolltext,
  betragAnzeige,
  datumDe,
  dokumentName,
  fundstelle,
  istDesktop,
  kern,
  lesartText,
  sortiereTags,
  urteilHerkunft,
} from "./kern";
import { OrdnerAnsicht, type OrdnerAnsichtArt } from "./Lesezeichen";
import { Anmerkung } from "./anmerkungLogik";
import { Lesezeichen } from "./lesezeichenLogik";
import Notizen from "./Notizen";
import Zeichen, { LeerHinweis } from "./Symbole";
import {
  Sichtschutz,
  SitzungsblattSpalte,
  Springen,
  TerminBeenden,
  TerminBeginnen,
  TerminUhr,
  TerminsnotizenSpalte,
  useSitzung,
} from "./Termin";
import type { Sitzung } from "./kern";
import { offeneBearbeitungen } from "./ungespeichert";

/** Schritt der Trennlinie per Tastatur (Anteil der Breite); mit Umschalt größer. */
const SCHRITT = 0.02;
const SCHRITT_GROSS = 0.08;

/** Öffnet ein Dokument aus Spalte ``von`` (Fundstelle) in einer passenden Spalte, siehe ``zielSpalte``. */
type Oeffnen = (
  von: number,
  dokumentId: number,
  ziel?: { abschnitt?: number | null; seite?: number | null; rn?: number | null },
) => void;

/**
 * Arbeitsfenster einer Akte: ein eigenes Fenster (z. B. auf dem zweiten Bildschirm) mit 1 bis 4 Spalten, jede mit
 * frei gewähltem Inhalt. Es bleibt an seine Akte gebunden, auch wenn im Hauptfenster eine andere geöffnet wird.
 * Die Anordnung wird je Akte gemerkt, ebenso Lage und Größe des Fensters (src-tauri/src/fenster.rs).
 */
export default function Arbeitsfenster({ akteId }: { akteId: number }) {
  const [akte, setAkte] = useState<Akte | null>(null);
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [anordnung, setAnordnungRoh] = useState<Anordnung>(() => gemerkteAnordnung(akteId));
  const [fehler, setFehler] = useState<string | null>(null);
  const [schliessFrage, setSchliessFrage] = useState<string[] | null>(null);
  const rahmen = useRef<HTMLDivElement>(null);
  const spaltenRefs = useRef<(HTMLElement | null)[]>([]);
  // Terminmodus: laufende Sitzung, Dialoge zum Beginnen und Beenden, Springen (Strg+K) und Sichtschutz (F9).
  const { sitzung, setSitzung } = useSitzung(akteId);
  const [beginnen, setBeginnen] = useState(false);
  const [beenden, setBeenden] = useState(false);
  const [springen, setSpringen] = useState(false);
  const [sichtschutz, setSichtschutz] = useState(false);
  const [meldung, setMeldung] = useState<string | null>(null);
  // Zuletzt benutzte Spalte: Ziel für „Springen“ und Bezug für Fundstellen aus dem Sitzungsblatt.
  const letzteSpalte = useRef(0);

  const setAnordnung = useCallback(
    (f: (a: Anordnung) => Anordnung) => {
      setAnordnungRoh((alt) => {
        const neu = f(alt);
        anordnungMerken(akteId, neu);
        return neu;
      });
    },
    [akteId],
  );

  useEffect(() => {
    if (!istDesktop) return;
    kern<Akte[]>("akten.liste").then(
      (liste) => {
        const a = liste.find((x) => x.id === akteId) ?? null;
        setAkte(a);
        if (!a) setFehler("Diese Akte gibt es nicht mehr. Das Fenster kann geschlossen werden.");
        else document.title = `advOrdo – Arbeitsfenster · ${a.name}`;
      },
      (e) => setFehler(String(e)),
    );
    kern<AktenDokument[]>("akten.dokumente", { akte_id: akteId }).then(setDokumente, (e) => setFehler(String(e)));
  }, [akteId]);

  // Lage und Größe merken, damit das Fenster beim nächsten Öffnen wieder dort steht (etwa auf dem zweiten Bildschirm).
  useEffect(() => {
    if (!istDesktop) return;
    const fenster = getCurrentWindow();
    let takt: number | undefined;
    const merken = () => {
      window.clearTimeout(takt);
      takt = window.setTimeout(async () => {
        try {
          if (await fenster.isMinimized()) return;
          const [pos, groesse] = await Promise.all([fenster.outerPosition(), fenster.innerSize()]);
          lageMerken(akteId, { x: pos.x, y: pos.y, breite: groesse.width, hoehe: groesse.height });
        } catch {
          // Lage nicht lesbar (etwa unter Wayland): das Fenster öffnet dann mittig.
        }
      }, 400);
    };
    const aus: (() => void)[] = [];
    void fenster.onMoved(merken).then((f) => aus.push(f));
    void fenster.onResized(merken).then((f) => aus.push(f));
    return () => {
      window.clearTimeout(takt);
      aus.forEach((f) => f());
    };
  }, [akteId]);

  // Vor dem Schließen nach ungespeicherten Eingaben fragen (z. B. eine angefangene Notiz).
  useEffect(() => {
    if (!istDesktop) return;
    let aus: (() => void) | undefined;
    void getCurrentWindow()
      .onCloseRequested((e) => {
        const offen = offeneBearbeitungen();
        if (offen.length === 0) return;
        e.preventDefault();
        setSchliessFrage(offen.map((b) => b.was));
      })
      .then((f) => (aus = f));
    return () => aus?.();
  }, []);

  // Strg+1 … 4 (macOS: ⌘): Spalte anwählen; Strg+K: Springen; F9: Sichtschutz.
  useEffect(() => {
    const taste = (e: globalThis.KeyboardEvent) => {
      if (e.key === "F9" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setSichtschutz((x) => !x);
        return;
      }
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return;
      if (e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSpringen(true);
        return;
      }
      const n = Number(e.key);
      if (!Number.isInteger(n) || n < 1 || n > MAX_SPALTEN) return;
      const ziel = spaltenRefs.current[n - 1];
      if (!ziel) return;
      e.preventDefault();
      letzteSpalte.current = n - 1;
      ziel.focus();
    };
    window.addEventListener("keydown", taste);
    return () => window.removeEventListener("keydown", taste);
  }, []);

  const oeffnen: Oeffnen = useCallback(
    (von, dokumentId, ziel) => {
      const dok = dokumente.find((d) => d.id === dokumentId);
      const original = ziel?.abschnitt == null && ziel?.rn == null && ziel?.seite != null && dok?.format === "pdf";
      setAnordnung((a) => {
        const z = zielSpalte(a, von);
        return spalteSetzen(z.anordnung, z.index, {
          art: "dokument",
          dokumentId,
          modus: original ? "original" : "text",
          abschnitt: ziel?.abschnitt ?? null,
          seite: ziel?.seite ?? null,
          rn: ziel?.rn ?? null,
        });
      });
    },
    [dokumente, setAnordnung],
  );

  function terminBegonnen(s: Sitzung) {
    setBeginnen(false);
    setSitzung(s);
    setMeldung(null);
    setAnordnung((a) => {
      if (a.spalten.some((x) => x.art === "terminsnotizen")) return a;
      vorTerminMerken(akteId, a);
      return terminAnordnung(a);
    });
  }

  function terminBeendet(s: Sitzung) {
    setBeenden(false);
    setSitzung(null);
    setAnordnung(() => vorTerminHolen(akteId));
    const u = s.uebernommen;
    const teile = [
      u?.notiz && "Protokoll als Aktennotiz übernommen",
      u?.zeit && `${u.zeit} Minuten erfasst`,
      u?.fristen && `${u.fristen === 1 ? "eine Frist" : `${u.fristen} Fristen`} im Kalender`,
    ].filter(Boolean);
    setMeldung(`Termin beendet${teile.length ? `: ${teile.join(", ")}` : ""}.`);
  }

  function springeZu(z: SprungZiel) {
    setSpringen(false);
    oeffnen(letzteSpalte.current, z.dokumentId, { abschnitt: z.abschnitt ?? null, rn: z.rn ?? null });
  }

  const offeneDokumente = anordnung.spalten.flatMap((s) => (s.art === "dokument" && s.dokumentId != null ? [s.dokumentId] : []));
  const anteile = anteileVon(anordnung);
  const anzahl = anordnung.spalten.length;

  function trennerZiehen(index: number, e: ReactPointerEvent<HTMLDivElement>) {
    const breite = rahmen.current?.getBoundingClientRect().width;
    if (!breite) return;
    e.preventDefault();
    let letztesX = e.clientX;
    const bewegen = (ev: PointerEvent) => {
      const delta = (ev.clientX - letztesX) / breite;
      letztesX = ev.clientX;
      setAnordnung((a) => trennerVerschieben(a, index, delta));
    };
    const loslassen = () => {
      window.removeEventListener("pointermove", bewegen);
      window.removeEventListener("pointerup", loslassen);
    };
    window.addEventListener("pointermove", bewegen);
    window.addEventListener("pointerup", loslassen);
  }

  function trennerTaste(index: number, e: KeyboardEvent<HTMLDivElement>) {
    const schritt = e.shiftKey ? SCHRITT_GROSS : SCHRITT;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      setAnordnung((a) => trennerVerschieben(a, index, e.key === "ArrowLeft" ? -schritt : schritt));
    } else if (e.key === "Home") {
      e.preventDefault();
      setAnordnung((a) => ({ ...a, anteile: null }));
    }
  }

  const gericht = akte?.gerichte[0];

  return (
    <div className={`arbeitsfenster${sitzung ? " af-termin" : ""}`}>
      <header className="kopfband af-kopf">
        <div className="af-kopf-titel">
          <p className="kopfband-ueber">
            {sitzung
              ? `Termin · ${sitzung.titel} · seit ${sitzung.beginn.slice(11, 16)} Uhr${sitzung.wahrgenommen_von ? ` · ${sitzung.wahrgenommen_von}` : ""}`
              : "Arbeitsfenster"} ·{" "}
            {akte?.aktenzeichen ? `Akte ${akte.aktenzeichen}` : "Akte ohne Aktenzeichen"}
            {gericht && ` · ${gericht.name}${gericht.aktenzeichen ? ` ${gericht.aktenzeichen}` : ""}`}
            {akte?.gegenstandswert && ` · Wert ${betragAnzeige(akte.gegenstandswert)} €`}
          </p>
          <h1>{akte?.name ?? "Akte wird geladen …"}</h1>
        </div>
        {!sitzung && akte?.mandanten && akte.mandanten.length > 0 && (
          <div className="akte-kopf-angabe">
            <p className="kopfband-ueber">Wir vertreten</p>
            <strong>{akte.mandanten.join(", ")}</strong>
          </div>
        )}
        {sitzung && <TerminUhr beginn={sitzung.beginn} />}
        <button className="kopf-knopf" onClick={() => setSichtschutz(true)} title="Inhalt sofort verdecken (F9)">
          Sichtschutz
        </button>
        {sitzung ? (
          <button className="kopf-knopf af-kopf-haupt" onClick={() => setBeenden(true)}>
            Termin beenden
          </button>
        ) : (
          <button className="kopf-knopf" onClick={() => setBeginnen(true)} title="Sitzungsblatt und Terminsnotizen mit Uhrzeit">
            Termin beginnen
          </button>
        )}
      </header>

      <div className="af-leiste" role="toolbar" aria-label="Ansicht des Arbeitsfensters">
        <span id="af-spalten-label">Spalten</span>
        <div className="segment" role="group" aria-labelledby="af-spalten-label">
          {Array.from({ length: MAX_SPALTEN - MIN_SPALTEN + 1 }, (_, i) => i + MIN_SPALTEN).map((n) => (
            <button
              key={n}
              className={`segment-knopf${anzahl === n ? " aktiv" : ""}`}
              aria-pressed={anzahl === n}
              onClick={() => setAnordnung((a) => spaltenZahl(a, n))}
            >
              {n}
            </button>
          ))}
        </div>
        <button className="zweitrangig af-springen-knopf" onClick={() => setSpringen(true)} title="Zu Anlage, Randnummer, Norm oder Dokument springen">
          Springen … <kbd>Strg+K</kbd>
        </button>
        {anordnung.anteile && (
          <button className="link" onClick={() => setAnordnung((a) => ({ ...a, anteile: null }))}>
            Gleich breit
          </button>
        )}
        <span className="af-tipp">Strg+1 bis {anzahl}: Spalte wählen · F9: Sichtschutz</span>
      </div>
      {meldung && (
        <p className="af-meldung" role="status">
          {meldung}{" "}
          <button className="link" onClick={() => setMeldung(null)}>
            Ausblenden
          </button>
        </p>
      )}

      {fehler && (
        <p className="fehler af-fehler" role="alert">
          {fehler}
        </p>
      )}

      <div className="af-spalten" ref={rahmen}>
        {anordnung.spalten.map((s, i) => (
          <SpaltenTeil
            key={i}
            index={i}
            anzahl={anzahl}
            anteil={anteile[i]}
            spalte={s}
            akteId={akteId}
            akte={akte}
            sitzung={sitzung}
            onSitzung={setSitzung}
            onBeginnen={() => setBeginnen(true)}
            onFokus={() => (letzteSpalte.current = i)}
            dokumente={dokumente}
            spaltenRef={(el) => (spaltenRefs.current[i] = el)}
            onSetzen={(neu) => setAnordnung((a) => spalteSetzen(a, i, neu))}
            onSchliessen={() => setAnordnung((a) => spalteEntfernen(a, i))}
            onOeffnen={oeffnen}
            trenner={
              i < anzahl - 1 ? (
                <div
                  className="af-trenner"
                  role="separator"
                  aria-orientation="vertical"
                  aria-label={`Trennlinie zwischen Spalte ${i + 1} und ${i + 2}`}
                  aria-valuenow={Math.round(anteile[i] * 100)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  tabIndex={0}
                  title="Ziehen oder Pfeiltasten: Breite ändern · Doppelklick oder Pos1: gleich breit"
                  onPointerDown={(e) => trennerZiehen(i, e)}
                  onDoubleClick={() => setAnordnung((a) => ({ ...a, anteile: null }))}
                  onKeyDown={(e) => trennerTaste(i, e)}
                />
              ) : null
            }
          />
        ))}
      </div>

      {beginnen && <TerminBeginnen akteId={akteId} sachbearbeiterId={akte?.sachbearbeiter_id ?? null} onBegonnen={terminBegonnen} onAbbrechen={() => setBeginnen(false)} />}
      {beenden && sitzung && <TerminBeenden sitzung={sitzung} onBeendet={terminBeendet} onAbbrechen={() => setBeenden(false)} />}
      {springen && (
        <Springen akteId={akteId} dokumente={dokumente} offen={offeneDokumente} onZiel={springeZu} onSchliessen={() => setSpringen(false)} />
      )}
      {sichtschutz && <Sichtschutz onAufheben={() => setSichtschutz(false)} />}
      {schliessFrage && (
        <div className="timer-hinweis-hintergrund">
          <Dialog className="rueckfrage timer-hinweis" rolle="alertdialog" label="Nicht gespeichert" onSchliessen={() => setSchliessFrage(null)}>
            <strong>{schliessFrage.length === 1 ? "Eine Eingabe ist" : "Eingaben sind"} noch nicht gespeichert</strong>
            <p>Offen: {schliessFrage.join(", ")}. Beim Schließen des Arbeitsfensters gehen diese Eingaben verloren.</p>
            <div className="aktionen">
              <button onClick={() => setSchliessFrage(null)} autoFocus>
                Zurück zur Bearbeitung
              </button>
              <button className="zweitrangig" onClick={() => void getCurrentWindow().destroy()}>
                Verwerfen und schließen
              </button>
            </div>
          </Dialog>
        </div>
      )}
    </div>
  );
}

function SpaltenTeil({
  index,
  anzahl,
  anteil,
  spalte,
  akteId,
  akte,
  sitzung,
  onSitzung,
  onBeginnen,
  onFokus,
  dokumente,
  spaltenRef,
  onSetzen,
  onSchliessen,
  onOeffnen,
  trenner,
}: {
  index: number;
  anzahl: number;
  anteil: number;
  spalte: Spalte;
  akteId: number;
  akte: Akte | null;
  sitzung: Sitzung | null;
  onSitzung: (s: Sitzung) => void;
  onBeginnen: () => void;
  onFokus: () => void;
  dokumente: AktenDokument[];
  spaltenRef: (el: HTMLElement | null) => void;
  onSetzen: (s: Spalte) => void;
  onSchliessen: () => void;
  onOeffnen: Oeffnen;
  trenner: ReactNode;
}) {
  const nr = index + 1;
  const dok = spalte.art === "dokument" ? dokumente.find((d) => d.id === spalte.dokumentId) : undefined;
  const titel =
    spalte.art === "leer"
      ? "leer"
      : spalte.art === "dokument"
        ? dok
          ? dokumentName(dok)
          : "Dokument"
        : SPALTEN_ARTEN.find((a) => a.art === spalte.art)!.titel;

  return (
    <>
      <section
        ref={spaltenRef}
        className="af-spalte"
        style={{ flexBasis: 0, flexGrow: anteil }}
        aria-label={`Spalte ${nr}: ${titel}`}
        tabIndex={-1}
        onFocus={onFokus}
        onPointerDown={onFokus}
      >
        <div className="af-spalten-kopf">
          <span className="af-nr" aria-hidden>
            {nr}
          </span>
          <label className="unsichtbar" htmlFor={`af-art-${nr}`}>
            Inhalt der Spalte {nr}
          </label>
          <select
            id={`af-art-${nr}`}
            value={spalte.art}
            onChange={(e) => {
              const art = e.target.value as SpaltenArt;
              onSetzen(art === "dokument" ? { art, dokumentId: null, modus: "text" } : { art });
            }}
          >
            {spalte.art === "leer" && <option value="leer">Inhalt wählen …</option>}
            {SPALTEN_ARTEN.map((a) => (
              <option key={a.art} value={a.art}>
                {a.titel}
              </option>
            ))}
          </select>
          {spalte.art === "dokument" && (
            <>
              <label className="unsichtbar" htmlFor={`af-dok-${nr}`}>
                Dokument in Spalte {nr}
              </label>
              <select
                id={`af-dok-${nr}`}
                className="af-dok-wahl"
                value={spalte.dokumentId ?? ""}
                onChange={(e) =>
                  onSetzen({ art: "dokument", dokumentId: e.target.value ? Number(e.target.value) : null, modus: spalte.modus ?? "text" })
                }
              >
                <option value="">Dokument wählen …</option>
                {dokumente.map((d) => (
                  <option key={d.id} value={d.id}>
                    {dokumentName(d)}
                  </option>
                ))}
              </select>
            </>
          )}
          <span className="af-kopf-rest" />
          {anzahl > MIN_SPALTEN && (
            <button className="leisten-knopf af-zu" onClick={onSchliessen} title={`Spalte ${nr} schließen`} aria-label={`Spalte ${nr} schließen`}>
              ✕
            </button>
          )}
        </div>
        <div className="af-spalten-inhalt">
          {spalte.art === "leer" && (
            <LeerHinweis symbol="dokumente">
              Oben wählen, was diese Spalte zeigt: ein Dokument, Notizen, Anmerkungen, Normen, Rechtsprechung, Sitzungsblatt oder
              Terminsnotizen.
            </LeerHinweis>
          )}
          {spalte.art === "dokument" && (
            <DokumentSpalte spalte={spalte} dokumente={dokumente} onSetzen={onSetzen} />
          )}
          {spalte.art === "notizen" && <Notizen akteId={akteId} />}
          {spalte.art === "anmerkungen" && <AnmerkungenSpalte akteId={akteId} onOeffnen={(id, ziel) => onOeffnen(index, id, ziel)} />}
          {spalte.art === "normen" && <NormenSpalte akteId={akteId} onOeffnen={(id, ab) => onOeffnen(index, id, { abschnitt: ab })} />}
          {spalte.art === "sitzungsblatt" && (
            <SitzungsblattSpalte akte={akte} dokumente={dokumente} onOeffnen={(id, ziel) => onOeffnen(index, id, ziel)} />
          )}
          {spalte.art === "terminsnotizen" && (
            <TerminsnotizenSpalte
              akteId={akteId}
              sitzung={sitzung}
              dokumente={dokumente}
              onSitzung={onSitzung}
              onBeginnen={onBeginnen}
              onOeffnen={(id, ziel) => onOeffnen(index, id, ziel)}
            />
          )}
          {spalte.art === "rechtsprechung" && (
            <RechtsprechungSpalte akteId={akteId} onOeffnen={(id, ab) => onOeffnen(index, id, { abschnitt: ab })} />
          )}
        </div>
      </section>
      {trenner}
    </>
  );
}

/** Ein Dokument der Akte als Text (mit Markierungen und Lesezeichen) oder als Original. */
function DokumentSpalte({ spalte, dokumente, onSetzen }: { spalte: Spalte; dokumente: AktenDokument[]; onSetzen: (s: Spalte) => void }) {
  const id = spalte.dokumentId ?? null;
  const [inhalt, setInhalt] = useState<DokumentInhalt | null>(null);
  const [anmerkungen, setAnmerkungen] = useState<Anmerkung[]>([]);
  const [lesezeichen, setLesezeichen] = useState<Lesezeichen[]>([]);
  const [stand, setStand] = useState(0);
  const [fehler, setFehler] = useState<string | null>(null);
  const rahmen = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setInhalt(null);
    setFehler(null);
    if (id == null || !istDesktop) return;
    let aktuell = true;
    kern<DokumentInhalt>("akten.dokument", { dokument_id: id }).then(
      (d) => aktuell && setInhalt(d),
      (e) => aktuell && setFehler(String(e)),
    );
    return () => {
      aktuell = false;
    };
  }, [id]);

  const ladeMarken = useCallback(async () => {
    if (id == null || !istDesktop) return;
    try {
      const [a, l] = await Promise.all([
        kern<Anmerkung[]>("anmerkungen.liste", { dokument_id: id }),
        kern<{ lesezeichen: Lesezeichen[] }>("lesezeichen.liste", { dokument_id: id }),
      ]);
      setAnmerkungen(a);
      setLesezeichen(l.lesezeichen);
      setStand((s) => s + 1);
    } catch {
      // Ohne Markierungen bleibt der Text lesbar.
    }
  }, [id]);
  useEffect(() => {
    void ladeMarken();
  }, [ladeMarken]);
  useFremdeAenderung(["anmerkungen", "lesezeichen"], () => void ladeMarken());

  // Fundstelle: Abschnitt direkt, Randnummer über die Abschnitte des Textes.
  const zielAbschnitt =
    spalte.abschnitt ?? (spalte.rn != null && inhalt ? (inhalt.abschnitte.find((a) => a.rn === spalte.rn)?.nr ?? null) : null);
  const rnFehlt = spalte.rn != null && inhalt != null && zielAbschnitt == null;

  // Zur Fundstelle springen, sobald der Text da ist.
  useEffect(() => {
    if (!inhalt || zielAbschnitt == null || spalte.modus === "original") return;
    rahmen.current?.querySelector(`#abschnitt-${zielAbschnitt}`)?.scrollIntoView({ block: "center" });
  }, [inhalt, zielAbschnitt, spalte.modus, spalte.rn]);

  if (id == null) {
    return (
      <div className="af-dokliste">
        <p className="leise">Welches Dokument soll diese Spalte zeigen?</p>
        {dokumente.length > 0 && (
          <table className="dokumente kompakt">
            <colgroup>
              <col className="spalte-datum" />
              <col />
            </colgroup>
            <thead>
              <tr>
                <th>Datum</th>
                <th>Dokument</th>
              </tr>
            </thead>
            <tbody>
              {dokumente.map((d) => (
                <tr
                  key={d.id}
                  className="klickbar"
                  onClick={(e) => {
                    if (!(e.target as HTMLElement).closest("button")) onSetzen({ art: "dokument", dokumentId: d.id, modus: "text" });
                  }}
                >
                  <td>{d.datum ? datumDe(d.datum) : <span className="leise">–</span>}</td>
                  <td>
                    <div className="dok-name-zeile">
                      <span className="dok-symbol">
                        <Zeichen name="dokumente" groesse={16} />
                      </span>
                      <button className="link dok-name" onClick={() => onSetzen({ art: "dokument", dokumentId: d.id, modus: "text" })}>
                        {dokumentName(d)}
                      </button>
                    </div>
                    <div className="herkunft">
                      {d.art && <span className="art-chip">{d.art}</span>}
                      {d.absender && <>von {d.absender.wert === "eigene" ? "uns" : d.absender.name} · </>}
                      {d.titel && <>{d.dateiname} · </>}
                      {lesartText(d)}
                      {d.seiten != null && <> · {d.seiten} S.</>}
                    </div>
                    {d.tags.length > 0 && (
                      <div className="tags">
                        {sortiereTags(d.tags).map((t) => (
                          <span key={t.name} className={`tag ${t.quelle}`}>
                            {t.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {dokumente.length === 0 && <p className="leer">Diese Akte enthält noch keine Dokumente.</p>}
      </div>
    );
  }

  const d = dokumente.find((x) => x.id === id);
  const pdf = d?.format === "pdf";
  const modus = pdf ? (spalte.modus ?? "text") : "text";

  return (
    <div className="af-dokument">
      <div className="segment af-modus" role="group" aria-label="Darstellung">
        {(["text", "original"] as const).map((m) => (
          <button
            key={m}
            className={`segment-knopf${modus === m ? " aktiv" : ""}`}
            aria-pressed={modus === m}
            disabled={m === "original" && !pdf}
            title={m === "original" && !pdf ? "Das Original gibt es nur bei PDF-Dokumenten." : undefined}
            onClick={() => onSetzen({ art: "dokument", dokumentId: id, modus: m })}
          >
            {m === "text" ? "Text" : "Original"}
          </button>
        ))}
      </div>
      {fehler && <p className="fehler">{fehler}</p>}
      {rnFehlt && <p className="hinweis">Rn. {spalte.rn} steht in diesem Dokument nicht.</p>}
      <div className="af-dokument-flaeche" ref={rahmen}>
        {!inhalt && !fehler && <p className="leise">Lade Dokument …</p>}
        {inhalt && modus === "text" && (
          <DokumentAnsicht
            inhalt={inhalt}
            ohneTitel
            markiert={zielAbschnitt ?? undefined}
            anmerkungen={anmerkungen}
            lesezeichen={lesezeichen}
          />
        )}
        {inhalt && modus === "original" && (
          <OriginalAnsicht
            key={`${id}-${spalte.seite ?? ""}`}
            dokument={inhalt.dokument}
            startSeite={spalte.seite ?? null}
            lesezeichenStand={stand}
            hinweis="Markierungen, Zitate und Belege zeigt die Textansicht."
          />
        )}
      </div>
    </div>
  );
}

function AnmerkungenSpalte({
  akteId,
  onOeffnen,
}: {
  akteId: number;
  onOeffnen: (dokumentId: number, ziel: { abschnitt?: number | null; seite?: number | null }) => void;
}) {
  const [teil, setTeil] = useState<OrdnerAnsichtArt>("markierungen");
  return (
    <div className="anm-reiter-rahmen af-anmerkungen">
      <div className="segment anm-teil-wahl" role="tablist" aria-label="Was angezeigt wird">
        {(
          [
            ["markierungen", "Markierungen"],
            ["lesezeichen", "Lesezeichen"],
            ["alle", "Alle"],
          ] as const
        ).map(([id, titel]) => (
          <button key={id} role="tab" aria-selected={teil === id} className={`segment-knopf${teil === id ? " aktiv" : ""}`} onClick={() => setTeil(id)}>
            {titel}
          </button>
        ))}
      </div>
      <OrdnerAnsicht
        akteId={akteId}
        ansicht={teil}
        onLesezeichen={(z) => onOeffnen(z.dokument_id, { abschnitt: z.abschnitt, seite: z.seite })}
        onAnmerkung={(a) => onOeffnen(a.dokument_id, { abschnitt: a.abschnitt, seite: a.seite })}
      />
    </div>
  );
}

function NormenSpalte({ akteId, onOeffnen }: { akteId: number; onOeffnen: (dokumentId: number, abschnitt: number) => void }) {
  const [normen, setNormen] = useState<NormEintrag[] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  useEffect(() => {
    if (!istDesktop) return;
    kern<NormEintrag[]>("akten.normen", { akte_id: akteId, dokument_id: null }).then(setNormen, (e) => setFehler(String(e)));
  }, [akteId]);
  if (fehler) return <p className="fehler">{fehler}</p>;
  if (!normen) return <p className="leise">Sammle Normen …</p>;
  return <NormenAnsicht normen={normen} onFundstelle={onOeffnen} />;
}

/** Zitierte Entscheidungen der Akte zum Nachschlagen; Laden, Ergänzen und Prüfen bleiben im Hauptfenster. */
function RechtsprechungSpalte({ akteId, onOeffnen }: { akteId: number; onOeffnen: (dokumentId: number, abschnitt: number) => void }) {
  const [urteile, setUrteile] = useState<UrteilEintrag[] | null>(null);
  const [volltext, setVolltext] = useState<UrteilVolltext | null>(null);
  const [rn, setRn] = useState<number | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  useEffect(() => {
    if (!istDesktop) return;
    kern<UrteilEintrag[]>("akten.rechtsprechung", { akte_id: akteId, dokument_id: null }).then(setUrteile, (e) => setFehler(String(e)));
  }, [akteId]);

  async function zeigeVolltext(urteilId: number, randnummer?: number) {
    try {
      setVolltext(await kern<UrteilVolltext>("akten.urteil", { urteil_id: urteilId }));
      setRn(randnummer ?? null);
    } catch (e) {
      setFehler(String(e));
    }
  }

  if (fehler) return <p className="fehler">{fehler}</p>;
  if (volltext) {
    return (
      <div className="af-volltext">
        <VolltextAnsicht volltext={volltext} rn={rn} onSchliessen={() => setVolltext(null)} />
      </div>
    );
  }
  if (!urteile) return <p className="leise">Sammle Rechtsprechung …</p>;
  if (urteile.length === 0) return <p className="leer">In dieser Akte wurden keine Rechtsprechungszitate erkannt.</p>;
  return (
    <>
      <ul className="normen">
        {urteile.map((u) => (
          <li key={u.zitat} className={`urteil-${u.status}`}>
            <div>
              <span className={`marke-status urteil-${u.status}`}>{urteilStatusText(u)}</span> <strong>{u.zitat}</strong>
            </div>
            {u.hinweis && <div className={u.status === "belegt" ? "titel" : "hinweis"}>{u.hinweis}</div>}
            <div className="fundstellen">
              {u.fundstellen.map((f, i) => (
                <button key={i} className="link" onClick={() => onOeffnen(f.dokument_id, f.abschnitt)}>
                  {f.dateiname}, {fundstelle(f)}
                  {f.rn_zitiert != null && ` (Rn. ${f.rn_zitiert})`}
                </button>
              ))}
            </div>
            {u.urteil && (
              <div className="urteil-aktionen">
                <button className="link" onClick={() => void zeigeVolltext(u.urteil!.id)}>
                  Volltext anzeigen ({urteilHerkunft(u.urteil)})
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="grenze">Volltexte laden, Urteile ergänzen und online prüfen: im Hauptfenster unter „Rechtsprechung“.</p>
    </>
  );
}

/** Knopf im Kopf der Akte (Hauptfenster): öffnet das Arbeitsfenster dieser Akte oder holt es nach vorn. */
export function ArbeitsfensterKnopf({ akte, onFehler }: { akte: Pick<Akte, "id" | "name">; onFehler: (f: string) => void }) {
  if (!istDesktop) return null;
  return (
    <button
      className="kopf-knopf"
      title="Eigenes Fenster mit Spalten für diese Akte, z. B. auf einem zweiten Bildschirm"
      onClick={async () => {
        try {
          await invoke("arbeitsfenster_oeffnen", {
            akteId: akte.id,
            titel: akte.name,
            thema: fensterThema(darstellungLesen()),
            lage: gemerkteLage(akte.id),
          });
        } catch (e) {
          onFehler(`Das Arbeitsfenster ließ sich nicht öffnen: ${String(e)}`);
        }
      }}
    >
      <Zeichen name="spalten" groesse={16} /> Arbeitsfenster
    </button>
  );
}
