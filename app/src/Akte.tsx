import {
  CSSProperties,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { DokumentDatum, EinrichtungsHinweise, OrdnerRueckfrage, TagEditor, ZitatZaehlung } from "./AkteTeile";
import { AnmerkungsLeiste, anmerkungsHandler, useAnmerkungen } from "./Anmerkungen";
import Chat from "./Chat";
import {
  DokModusLeiste,
  DokumentAnsicht,
  ErgaenzungsFrage,
  NormenAnsicht,
  OriginalAnsicht,
  RechtsprechungAnsicht,
  VolltextAnsicht,
  ZugeordneteUrteile,
  scrollRahmen,
} from "./DokumentAnsicht";
import DokumentDetails, { DetailsGriff } from "./DokumentDetails";
import DokumentExtern, { UebernahmeFrage } from "./DokumentExtern";
import { dokumentPasst } from "./dokumentSuche";
import { GegenueberstellungBereich } from "./Gegenueberstellung";
import { BelegAnsicht } from "./Gesetze";
import { Bildlaufmarken, LesezeichenLeiste, OrdnerAnsicht, OrdnerAnsichtArt, useLesezeichen } from "./Lesezeichen";
import { Rueckfrage } from "./Rueckfrage";
import Zeichen, { LeerHinweis } from "./Symbole";
import Trenner from "./Trenner";
import { Anmerkung } from "./anmerkungLogik";
import {
  Abschnitt,
  Akte as AkteTyp,
  AktenDokument,
  Arbeitskopie,
  BETEILIGTE,
  Beleg,
  Beteiligung,
  DokumentInhalt,
  ImportErgebnisDatei,
  Loeschergebnis,
  NormEintrag,
  NormZitat,
  OcrStatus,
  OrdnerFunde,
  URTEIL_QUELLEN,
  UrteilEintrag,
  UrteilInfo,
  UrteilStatus,
  UrteilVolltext,
  dokumentName,
  fundstelle,
  istDesktop,
  kern,
  kernImHintergrund,
  kopieSchluessel,
  lesartText,
  offeneUebernahmen,
  sortiereTags,
  tagUebersicht,
  tagsAusText,
  urteilHerkunft,
  urteilTitel,
} from "./kern";
import { vorschlaegeVergessen } from "./Schreibweisen";
import { useKiAn } from "./kiSchalter";
import { Lesezeichen } from "./lesezeichenLogik";
import { gemerkt, merke } from "./merken";

type Ansicht = "dokument" | "anmerkungen" | "normen" | "rechtsprechung" | "chat";
/** Was zum geöffneten Dokument gezeigt wird. */
export type DokModus = "text" | "original" | "normen" | "rechtsprechung" | "chat" | "details";

/** Breite der Seitenleiste (Wortlaut, Volltext), je Gerät gemerkt. */
const SEITE_STANDARD = 360;
const SEITE_MIN = 260;
const BREITE_SCHLUESSEL = "akte.seitenbreite";

/** Breite der Dokumentansicht rechts neben der Dokumentliste, je Gerät gemerkt; null = Standard (anteilig). */
const DOK_MIN = 360;
const DOK_SCHLUESSEL = "akte.dokbreite";
/** Liste behält mindestens so viel Platz neben den Filtern. */
const LISTE_MIN = 340;

function gespeicherteDokBreite(): number | null {
  try {
    const wert = Number(localStorage.getItem(DOK_SCHLUESSEL));
    return wert >= DOK_MIN ? wert : null;
  } catch {
    return null;
  }
}

function gespeicherteBreite(): number {
  try {
    const wert = Number(localStorage.getItem(BREITE_SCHLUESSEL));
    return wert >= SEITE_MIN ? wert : SEITE_STANDARD;
  } catch {
    return SEITE_STANDARD;
  }
}

/** Eine einzulesende Datei, beim Ordner-Import mit Unterordner und bestätigten Tags. */
interface Einzulesen {
  pfad: string;
  name: string;
  tags?: string[];
  herkunft?: string;
}

/** Rückfrage vor dem Ordner-Import: Tags je Unterordner, vom Nutzer änderbar. */
export interface OrdnerFrage {
  funde: OrdnerFunde;
  tags: Record<string, string>;
}

type Loeschfrage = { art: "dokument"; id: number } | { art: "urteil"; id: number; name: string };

/** Angaben zu einer Entscheidung, die aus einer eigenen Datei ergänzt wird. */
export interface Ergaenzung {
  pfad: string;
  name: string;
  zitat: string;
  gericht: string;
  aktenzeichen: string;
  datum: string;
  herkunft: string;
}

export interface Auswahl {
  zitat: NormZitat;
  ort: string;
  beleg: Beleg | null;
}

/** Reiter der Akte, die diese Komponente zeigt; die übrigen (Beteiligte, Vergleich, Analyse) zeigt der Aktenrahmen. */
export type AkteReiter = "dokumente" | "anmerkungen" | "normen" | "rechtsprechung" | "chat";

const FILTER_SCHLUESSEL = "akte.filter.eingeklappt";
const ANMERK_OFFEN_SCHLUESSEL = "akte.anmerkungen.offen";

/** Filter der Dokumentliste; alle gesetzten gelten zusammen. */
interface Filter {
  /** Oberster Ordner aus dem Ordner-Import; "" = Dokumente ohne Ordner. */
  ordner: string | null;
  /** Partei- oder anderer Tag; "" = Dokumente ohne Tag. */
  tag: string | null;
  /** Nur Dokumente mit Zitaten, die nicht belegt sind. */
  unbelegt: boolean;
  /** Art aus „Details“; "" = ohne Art. */
  art: string | null;
  /** Absender aus „Details“: "eigene", Nummer der Beteiligung als Text; "" = ohne Absender. */
  absender: string | null;
}

const KEIN_FILTER: Filter = { ordner: null, tag: null, unbelegt: false, art: null, absender: null };
const absenderSchluessel = (d: AktenDokument) => (d.absender ? String(d.absender.wert) : "");

const oberordner = (d: AktenDokument) => (d.herkunft ? d.herkunft.split(/[\\/]/)[0] : "");
const unbelegt = (d: AktenDokument) => !!(d.zitate.nicht_gefunden || d.zitate.unbekanntes_gesetz);

function zaehle<T>(werte: T[]): Map<T, number> {
  const m = new Map<T, number>();
  for (const w of werte) m.set(w, (m.get(w) ?? 0) + 1);
  return m;
}

/**
 * Inhalt einer geöffneten Akte: Dokumente (Filter, Liste, geöffnetes Dokument) sowie Normen, Rechtsprechung und
 * Chat der ganzen Akte. Kopf, Reiter und Stammdaten liegen im Aktenrahmen.
 */
export default function Akte({
  akte,
  reiter,
  onReiter,
  onGeaendert,
  onBeteiligte,
  onEinstellungen,
}: {
  akte: AkteTyp;
  reiter: AkteReiter;
  onReiter: (r: AkteReiter) => void;
  /** Dokumente kamen hinzu oder wurden entfernt; die Aktenliste (Zähler, „bearbeitet“) neu laden. */
  onGeaendert: () => void;
  /** Ein Beteiligter in der Filterspalte wurde angeklickt. */
  onBeteiligte: () => void;
  onEinstellungen?: () => void;
}) {
  const akteId = akte.id;
  const kiAn = useKiAn();
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [beteiligte, setBeteiligte] = useState<Beteiligung[]>([]);
  const [inhalt, setInhalt] = useState<DokumentInhalt | null>(null);
  const [normen, setNormen] = useState<NormEintrag[] | null>(null);
  const [urteile, setUrteile] = useState<UrteilEintrag[] | null>(null);
  // Aus der Sammlung zugeordnet, in keinem Dokument zitiert („Zur weiteren Bearbeitung zugeordnet“).
  const [zugeordnet, setZugeordnet] = useState<UrteilInfo[]>([]);
  const [dokModus, setDokModus] = useState<DokModus>("text");
  const [auswahl, setAuswahl] = useState<Auswahl | null>(null);
  const [ziel, setZiel] = useState<number | null>(null);
  // Abschnitt, zu dem gesprungen wurde (z. B. die Datumszeile); bleibt hervorgehoben, bis ein anderes Dokument geöffnet wird.
  const [markiert, setMarkiert] = useState<number | null>(null);
  const [ocr, setOcr] = useState<OcrStatus | null>(null);
  const [gesetzeGeladen, setGesetzeGeladen] = useState<number | null>(null);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  // Ungespeicherte Eingaben in „Details“: vor einem Wechsel des Dokuments oder der Ansicht wird nachgefragt.
  const details = useRef<DetailsGriff>(null);
  const [verlassen, setVerlassen] = useState<{ weiter: () => void } | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [ordnerFrage, setOrdnerFrage] = useState<OrdnerFrage | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<Loeschfrage | null>(null);
  const [filter, setFilter] = useState<Filter>(KEIN_FILTER);
  const [filterZu, setFilterZu] = useState(() => gemerkt(FILTER_SCHLUESSEL));
  const [nachDatum, setNachDatum] = useState(true);
  // Suchfeld über der Dokumentliste: Titel, Dateiname, Ordner, Art, Absender, Tags und Datum.
  const [dokSuche, setDokSuche] = useState("");
  const [tagEdit, setTagEdit] = useState<{ id: number; text: string } | null>(null);
  const [ergaenzung, setErgaenzung] = useState<Ergaenzung | null>(null);
  const [volltext, setVolltext] = useState<UrteilVolltext | null>(null);
  const [volltextRn, setVolltextRn] = useState<number | null>(null);
  const [seitenbreite, setSeitenbreite] = useState(gespeicherteBreite);
  const [kopien, setKopien] = useState<Arbeitskopie[]>([]);
  // Geänderte Arbeitskopien, bei denen „Später“ gewählt wurde; gilt bis zum nächsten Speichern.
  const [spaeter, setSpaeter] = useState<ReadonlySet<string>>(new Set());
  const flaeche = useRef<HTMLDivElement>(null);
  // Trennlinie zwischen Dokumentliste und geöffnetem Dokument (Reiter Dokumente).
  const [dokBreite, setDokBreite] = useState<number | null>(gespeicherteDokBreite);
  const dokRahmen = useRef<HTMLDivElement>(null);
  // Markierungen und Kommentare des geöffneten Dokuments; die Zähler in der Dokumentliste folgen jeder Änderung.
  // Lesezeichen: Inhaltsverzeichnis des PDFs und eigene Lesezeichen; „Lesezeichen“ steht auch im Menü über der Auswahl.
  const lz = useLesezeichen(inhalt?.dokument.id ?? null);
  const anm = useAnmerkungen(inhalt?.dokument.id ?? null, () => void ladeDokumente(), (s) => void lz.anlegen(s));
  // Reiter „Anmerkungen“ der Akte: Markierungen und Kommentare oder Lesezeichen.
  const [anmTeil, setAnmTeil] = useState<OrdnerAnsichtArt>("markierungen");
  // Wo die Marken an der Bildlaufleiste gemessen werden: Text oder Original des geöffneten Dokuments.
  const [markenWurzel, setMarkenWurzel] = useState<HTMLElement | null>(null);
  // Seitenleiste mit den Anmerkungen: zunächst zu, damit der Text Platz hat; der Zustand wird je Gerät gemerkt.
  const [anmerkZu, setAnmerkZu] = useState(() => !gemerkt(ANMERK_OFFEN_SCHLUESSEL));
  // Aus dem Reiter „Anmerkungen“ gewählt: nach dem Öffnen des Dokuments dorthin springen.
  const [anmerkZiel, setAnmerkZiel] = useState<number | null>(null);
  const textRahmen = useRef<HTMLDivElement>(null);
  const ansicht: Ansicht = reiter === "dokumente" ? "dokument" : reiter;

  function setzeSeitenbreite(breite: number) {
    setSeitenbreite(breite);
    try {
      localStorage.setItem(BREITE_SCHLUESSEL, String(breite));
    } catch {
      // Ohne Speicher gilt die Breite nur bis zum Neustart.
    }
  }

  /** Platz links der Trennlinie: Filterspalte und Mindestbreite der Liste. */
  function dokRest(): number {
    return (filterZu ? 40 : 210) + LISTE_MIN + 6;
  }

  /** Standardbreite der Dokumentansicht: ihr Anteil wie im Raster ohne eigene Breite (1,3 bzw. 1,5 zu 1). */
  function dokStandard(): number {
    const gesamt = dokRahmen.current?.getBoundingClientRect().width ?? 1200;
    const anteil = filterZu ? 1.5 : 1.3;
    return Math.max(DOK_MIN, Math.round(((gesamt - (filterZu ? 40 : 210)) * anteil) / (1 + anteil)));
  }

  function setzeDokBreite(breite: number | null) {
    // Gleich dem Standard: wieder anteilig, damit die Aufteilung beim Ändern der Fenstergröße mitwächst.
    const neu = breite == null || Math.abs(breite - dokStandard()) < 3 ? null : breite;
    setDokBreite(neu);
    try {
      if (neu == null) localStorage.removeItem(DOK_SCHLUESSEL);
      else localStorage.setItem(DOK_SCHLUESSEL, String(neu));
    } catch {
      // Ohne Speicher gilt die Breite nur bis zum Neustart.
    }
  }

  function dokBreiteZiehen(e: ReactPointerEvent<HTMLDivElement>) {
    const rahmen = dokRahmen.current?.getBoundingClientRect();
    if (!rahmen) return;
    e.preventDefault();
    const breite = (x: number) => Math.round(Math.min(Math.max(rahmen.right - x, DOK_MIN), rahmen.width - dokRest()));
    const bewegen = (ev: PointerEvent) => setDokBreite(breite(ev.clientX));
    const loslassen = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", bewegen);
      window.removeEventListener("pointerup", loslassen);
      setzeDokBreite(breite(ev.clientX));
    };
    window.addEventListener("pointermove", bewegen);
    window.addEventListener("pointerup", loslassen);
  }

  function breiteZiehen(e: ReactPointerEvent<HTMLDivElement>) {
    const rechts = flaeche.current?.getBoundingClientRect().right;
    const gesamt = flaeche.current?.getBoundingClientRect().width;
    if (rechts == null || gesamt == null) return;
    e.preventDefault();
    const bewegen = (ev: PointerEvent) => {
      // Der Text links behält mindestens 320 px.
      setSeitenbreite(Math.round(Math.min(Math.max(rechts - ev.clientX, SEITE_MIN), gesamt - 320)));
    };
    const loslassen = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", bewegen);
      window.removeEventListener("pointerup", loslassen);
      setzeSeitenbreite(Math.round(Math.min(Math.max(rechts - ev.clientX, SEITE_MIN), gesamt - 320)));
    };
    window.addEventListener("pointermove", bewegen);
    window.addEventListener("pointerup", loslassen);
  }

  function filterUmschalten() {
    setFilterZu(!filterZu);
    merke(FILTER_SCHLUESSEL, !filterZu);
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

  const ladeDokumente = useCallback(async () => {
    setDokumente(await kern<AktenDokument[]>("akten.dokumente", { akte_id: akteId }));
  }, [akteId]);

  const ladeKopien = useCallback(async () => {
    try {
      setKopien(await kern<Arbeitskopie[]>("akten.arbeitskopien", { akte_id: akteId }));
    } catch {
      // Nur ein Hinweis; die Akte funktioniert auch ohne.
    }
  }, [akteId]);

  // Ob eine Arbeitskopie im externen Programm gespeichert wurde: beim Zurückkehren in die App und, solange es
  // Arbeitskopien gibt, regelmäßig.
  const mitKopien = kopien.length > 0;
  useEffect(() => {
    if (!istDesktop) return;
    void ladeKopien();
    const pruefen = () => {
      if (document.visibilityState === "visible") void ladeKopien();
    };
    window.addEventListener("focus", pruefen);
    document.addEventListener("visibilitychange", pruefen);
    const takt = mitKopien ? window.setInterval(pruefen, 10000) : undefined;
    return () => {
      window.removeEventListener("focus", pruefen);
      document.removeEventListener("visibilitychange", pruefen);
      window.clearInterval(takt);
    };
  }, [ladeKopien, mitKopien]);

  async function fassungUebernehmen(dokumentId: number) {
    const r = await ausfuehren("Übernehme neue Fassung und lese sie ein …", () =>
      kern<{ dateiname: string; fassung: number; ki_verworfen: number }>("akten.fassung_uebernehmen", {
        dokument_id: dokumentId,
      }),
    );
    await ladeKopien();
    if (!r) return;
    await ladeDokumente();
    if (inhalt?.dokument.id === dokumentId) await oeffneDokument(dokumentId);
    onGeaendert();
    setMeldung(
      `„${r.dateiname}“ ist jetzt Fassung ${r.fassung}; Text, Normzitate und Datum sind neu eingelesen.` +
        (r.ki_verworfen > 0
          ? " Gespeicherte Ergebnisse des Sprachmodells zu dieser Akte passten nicht mehr zum Text und wurden verworfen."
          : ""),
    );
  }

  useEffect(() => {
    if (!istDesktop) return;
    void ausfuehren("Lade Dokumente …", async () => {
      await ladeDokumente();
      setBeteiligte((await kern<{ beteiligte: Beteiligung[] }>("akten.stammdaten", { akte_id: akteId })).beteiligte);
      setOcr(await kern<OcrStatus>("ocr.status"));
      setGesetzeGeladen((await kern<unknown[]>("gesetze.liste")).length);
    });
  }, [akteId, ausfuehren, ladeDokumente]);

  // Kam ein Dokument von außerhalb dieser Ansicht dazu (z. B. ein erzeugtes Schriftstück), die Liste neu laden.
  const dokumentZahl = useRef(akte.dokumente);
  useEffect(() => {
    if (!istDesktop || dokumentZahl.current === akte.dokumente) return;
    dokumentZahl.current = akte.dokumente;
    void ladeDokumente();
    void ladeKopien();
  }, [akte.dokumente, ladeDokumente, ladeKopien]);

  // Ein Reiter der ganzen Akte lädt seine Liste beim Öffnen.
  useEffect(() => {
    if (!istDesktop) return;
    if (reiter === "normen") void ladeNormen(null);
    if (reiter === "rechtsprechung") void ladeUrteile(null);
    if (reiter === "dokumente" && inhalt) void waehleDokModus(dokModus);
    // Nur beim Wechsel des Reiters; die Ladefunktionen ändern sich mit jedem Rendern.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reiter]);

  // Nach dem Öffnen eines Dokuments zur gewünschten Fundstelle scrollen.
  useEffect(() => {
    if (ziel == null || !inhalt) return;
    document.getElementById(`abschnitt-${ziel}`)?.scrollIntoView({ block: "center" });
    setZiel(null);
  }, [ziel, inhalt]);

  async function hinzufuegen() {
    const gewaehlt = await open({
      multiple: true,
      title: "Dokumente zur Akte hinzufügen",
      filters: [{ name: "Schriftsätze, Schreiben, Urteile", extensions: ["pdf", "docx", "txt", "md"] }],
    });
    const pfade = gewaehlt == null ? [] : Array.isArray(gewaehlt) ? gewaehlt : [gewaehlt];
    await einlesen(pfade.map((pfad) => ({ pfad, name: pfad.split(/[\\/]/).pop() ?? pfad })));
  }

  async function ordnerHinzufuegen() {
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
    if (dateien.length === 0) return;
    setFehler(null);
    setMeldung(null);
    setLaeuft(
      `Lese ${dateien.length === 1 ? dateien[0].name : `${dateien.length} Dateien`} … ` +
        "(Scans werden per Texterkennung gelesen, das dauert je Seite einige Sekunden; der Fortschritt steht unten rechts)",
    );
    // Im Hintergrund des Kerns: Die App bleibt bedienbar (Zeiterfassung, Erinnerungen), abbrechen über die Warteanzeige.
    let ergebnisse: ImportErgebnisDatei[] = [];
    let abbruch: string | null = null;
    try {
      ergebnisse = (
        await kernImHintergrund<{ ergebnisse: ImportErgebnisDatei[] }>("akten.importieren_dateien", {
          akte_id: akteId,
          dateien: dateien.map((d) => ({ pfad: d.pfad, name: d.name, tags: d.tags ?? null, herkunft: d.herkunft ?? null })),
        })
      ).ergebnisse;
    } catch (e) {
      abbruch = String(e);
    } finally {
      setLaeuft(null);
    }
    // Auch nach einem Abbruch: Was schon eingelesen ist, steht in der Akte.
    await ausfuehren("Lade Dokumente …", ladeDokumente);
    onGeaendert();
    const fehlschlaege = ergebnisse.filter((e) => e.fehler).map((e) => `${e.name}: ${e.fehler}`);
    const gelesen = ergebnisse.filter((e) => !e.fehler);
    const schonDa = gelesen.filter((e) => e.neu === false).length;
    if (dateien.length === 1 && gelesen.length === 1 && gelesen[0].dokument_id != null)
      await oeffneDokument(gelesen[0].dokument_id);
    if (dateien.length > 1 && !abbruch)
      setMeldung(
        `${gelesen.length} von ${dateien.length} Dateien übernommen` +
          (schonDa ? `, davon ${schonDa} schon in der Akte (nur Tags ergänzt).` : "."),
      );
    if (abbruch) setFehler(abbruch);
    else if (fehlschlaege.length > 0) setFehler(`Nicht gelesen:\n${fehlschlaege.join("\n")}`);
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
      await aktualisiereUrteile();
      setMeldung(`„${frage.name}“ wurde aus der Akte entfernt.${weg.hinweis ? ` ${weg.hinweis}` : ""}`);
      return;
    }
    const ergebnis = await ausfuehren("Entferne …", () =>
      kern<Loeschergebnis>("akten.dokument_loeschen", { dokument_id: frage.id }),
    );
    if (!ergebnis) return;
    if (inhalt?.dokument.id === frage.id) {
      setInhalt(null);
      setAuswahl(null);
    }
    await ausfuehren("Lade Dokumente …", ladeDokumente);
    onGeaendert();
    setMeldung(`„${ergebnis.name ?? ergebnis.dateiname}“ wurde entfernt.${ergebnis.hinweis ? ` ${ergebnis.hinweis}` : ""}`);
  }

  async function tagsSpeichern(dokumentId: number, tags: string[]) {
    await ausfuehren("Speichere Tags …", () => kern("akten.tags_setzen", { dokument_id: dokumentId, tags }));
    setTagEdit(null);
    await ladeDokumente();
    if (inhalt?.dokument.id === dokumentId) await oeffneDokument(dokumentId);
  }

  /** Nach dem Speichern in „Details“: Liste und Kopf zeigen Titel, Datum und Tags neu; die Ansicht bleibt. */
  async function metadatenGespeichert(id: number) {
    await ladeDokumente();
    const d = await kern<DokumentInhalt>("akten.dokument", { dokument_id: id }).catch(() => null);
    // Inzwischen kann ein anderes Dokument geöffnet sein (Speichern in der Rückfrage vor dem Wechsel).
    if (d) setInhalt((alt) => (alt?.dokument.id === id ? d : alt));
  }

  /** Führt ``weiter`` aus; stehen in „Details“ ungespeicherte Eingaben, erst nach der Rückfrage. */
  function nachRueckfrage(weiter: () => void) {
    if (dokModus === "details" && details.current?.offen()) setVerlassen({ weiter });
    else weiter();
  }

  async function oeffneDokument(id: number, abschnitt?: number) {
    if (dokModus === "details" && details.current?.offen()) {
      setVerlassen({ weiter: () => void dokumentOeffnen(id, abschnitt) });
      return;
    }
    await dokumentOeffnen(id, abschnitt);
  }

  async function dokumentOeffnen(id: number, abschnitt?: number) {
    const d = await ausfuehren("Lade Dokument …", () => kern<DokumentInhalt>("akten.dokument", { dokument_id: id }));
    if (!d) return;
    setInhalt(d);
    setAuswahl(null);
    // Eine Fundstelle zeigt immer den Text; sonst bleibt die gewählte Darstellung, soweit es sie für das Dokument gibt.
    const modus: DokModus = abschnitt != null || (dokModus === "original" && d.dokument.format !== "pdf") ? "text" : dokModus;
    setDokModus(modus);
    if (reiter !== "dokumente") onReiter("dokumente");
    else {
      if (modus === "normen") await ladeNormen(id);
      if (modus === "rechtsprechung") await ladeUrteile(id);
    }
    if (abschnitt != null) setZiel(abschnitt);
    setMarkiert(abschnitt ?? null);
  }

  function anmerkungenUmschalten() {
    setAnmerkZu(!anmerkZu);
    merke(ANMERK_OFFEN_SCHLUESSEL, anmerkZu);
  }

  /** Anmerkung in der Seitenleiste gewählt: zur Stelle springen und den Editor dort öffnen. */
  function anmerkungWaehlen(a: Anmerkung, eintrag: Element) {
    anm.setAktiv(a.id);
    const stelle =
      textRahmen.current?.querySelector(`[data-anmerkung~="${a.id}"]`) ??
      document.querySelector(`.original [data-anmerkung="${a.id}"]`);
    if (!stelle) {
      // Nicht (mehr) im Text oder die Seite ist noch nicht geladen: Seite anspringen, Editor an der Liste.
      if (a.seite != null) document.getElementById(`seite-${a.seite}`)?.scrollIntoView({ block: "start" });
      anm.oeffneEditor(a.id, eintrag);
      return;
    }
    stelle.scrollIntoView({ block: "center" });
    // Erst nach dem Scrollen steht die Stelle fest.
    window.setTimeout(() => anm.oeffneEditor(a.id, stelle), 250);
  }

  /** Aus dem Reiter „Anmerkungen“: Dokument in der Textansicht öffnen und zur Stelle springen. */
  async function oeffneAnmerkung(a: Anmerkung) {
    setAnmerkZiel(a.id);
    if (inhalt?.dokument.id === a.dokument_id && dokModus === "text") {
      onReiter("dokumente");
      return;
    }
    await oeffneDokument(a.dokument_id, a.abschnitt ?? undefined);
  }

  useEffect(() => {
    if (anmerkZiel == null || reiter !== "dokumente" || !anm.liste.some((a) => a.id === anmerkZiel)) return;
    const t = window.setTimeout(() => {
      const stelle = textRahmen.current?.querySelector(`[data-anmerkung~="${anmerkZiel}"]`);
      stelle?.scrollIntoView({ block: "center" });
      anm.setAktiv(anmerkZiel);
      setAnmerkZiel(null);
    }, 50);
    return () => window.clearTimeout(t);
  }, [anmerkZiel, anm.liste, reiter]);

  useEffect(() => {
    setMarkenWurzel(
      reiter !== "dokumente"
        ? null
        : dokModus === "text"
          ? textRahmen.current
          : dokModus === "original"
            ? (flaeche.current?.querySelector<HTMLElement>(".original") ?? null)
            : null,
    );
  }, [reiter, dokModus, inhalt?.dokument.id]);

  /** Oberer Rand des sichtbaren Bereichs um ``el`` (Bildschirmkoordinate). */
  function sichtOben(el: HTMLElement) {
    const r = scrollRahmen(el);
    return r ? r.getBoundingClientRect().top : 0;
  }

  /** „Hier setzen“: Lesezeichen am obersten sichtbaren Absatz bzw. an der obersten sichtbaren Seite. */
  function lesezeichenHier() {
    if (dokModus === "text" && textRahmen.current) {
      const oben = sichtOben(textRahmen.current) + 8;
      const p = [...textRahmen.current.querySelectorAll<HTMLElement>("p[data-beginn]")].find(
        (x) => x.getBoundingClientRect().bottom > oben,
      );
      if (p) void lz.anlegen({ start: Number(p.dataset.beginn) });
      return;
    }
    const original = flaeche.current?.querySelector<HTMLElement>(".original");
    if (!original) return;
    const oben = sichtOben(original) + 40;
    const seite = [...original.querySelectorAll<HTMLElement>("figure[data-seite]")].find((f) => f.getBoundingClientRect().bottom > oben);
    if (seite) void lz.anlegen({ seite: Number(seite.dataset.seite) });
  }

  /** Eigenes Lesezeichen gewählt: zum Fähnchen springen, sonst zur Seite. */
  function lesezeichenWaehlen(z: Lesezeichen) {
    const el =
      textRahmen.current?.querySelector(`[data-lesezeichen="${z.id}"]`) ??
      flaeche.current?.querySelector(`.original [data-lesezeichen="${z.id}"]`);
    if (el) el.scrollIntoView({ block: "center" });
    else if (dokModus === "original" && z.seite != null) document.getElementById(`seite-${z.seite}`)?.scrollIntoView({ block: "start" });
    else if (z.abschnitt != null) document.getElementById(`abschnitt-${z.abschnitt}`)?.scrollIntoView({ block: "start" });
  }

  /** Eintrag des Inhaltsverzeichnisses: Seite im Original bzw. ersten Absatz der Seite im Text anspringen. */
  function inhaltWaehlen(seite: number) {
    if (dokModus === "original") {
      document.getElementById(`seite-${seite}`)?.scrollIntoView({ block: "start" });
      return;
    }
    const a = inhalt?.abschnitte.find((x) => x.seite != null && (x.seite_bis ?? x.seite) >= seite);
    if (a) document.getElementById(`abschnitt-${a.nr}`)?.scrollIntoView({ block: "start" });
  }

  /** Aus dem Reiter „Anmerkungen“ → „Lesezeichen“: Dokument an der Stelle öffnen. */
  async function oeffneLesezeichen(z: Lesezeichen) {
    if (inhalt?.dokument.id === z.dokument_id) {
      onReiter("dokumente");
      window.setTimeout(() => lesezeichenWaehlen(z), 80);
      return;
    }
    await oeffneDokument(z.dokument_id, z.abschnitt ?? undefined);
  }

  async function ladeNormen(dokumentId: number | null) {
    const n = await ausfuehren("Sammle Normen …", () =>
      kern<NormEintrag[]>("akten.normen", { akte_id: akteId, dokument_id: dokumentId }),
    );
    setNormen(n ?? null);
  }

  async function ladeUrteile(dokumentId: number | null) {
    const u = await ausfuehren("Sammle Rechtsprechung …", () =>
      kern<UrteilEintrag[]>("akten.rechtsprechung", { akte_id: akteId, dokument_id: dokumentId }),
    );
    setUrteile(u ?? null);
    if (dokumentId == null) {
      const z = await ausfuehren("Sammle Rechtsprechung …", () =>
        kern<UrteilInfo[]>("akten.urteile_zugeordnet", { akte_id: akteId }),
      );
      setZugeordnet(z ?? []);
    }
  }

  async function zuordnungLoesen(u: UrteilInfo) {
    const r = await ausfuehren("Löse die Zuordnung …", () => kern("rechtsprechung.loesen", { urteil_id: u.id }));
    if (r === undefined) return;
    if (volltext?.id === u.id) setVolltext(null);
    setMeldung(`${urteilTitel(u)} ist dieser Akte nicht mehr zugeordnet; sie bleibt im Bereich „Rechtsprechung“.`);
    await aktualisiereUrteile();
  }

  /** Lädt die gerade sichtbare Rechtsprechungsliste neu: die der Akte oder die des geöffneten Dokuments. */
  async function aktualisiereUrteile() {
    await ladeUrteile(ansicht === "dokument" && inhalt ? inhalt.dokument.id : null);
  }

  async function waehleDokModus(modus: DokModus) {
    setDokModus(modus);
    if (!inhalt) return;
    if (modus === "normen") await ladeNormen(inhalt.dokument.id);
    if (modus === "rechtsprechung") await ladeUrteile(inhalt.dokument.id);
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
    if (!ergaenzung) return;
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
    await aktualisiereUrteile();
    await zeigeVolltext(ergebnis.urteil_id);
  }

  async function zeigeVolltext(urteilId: number, rn?: number) {
    setVolltextRn(rn ?? null);
    if (volltext?.id === urteilId) return;
    const v = await ausfuehren("Lade Volltext …", () => kern<UrteilVolltext>("akten.urteil", { urteil_id: urteilId }));
    setVolltext(v ?? null);
  }

  async function volltexteLaden(zitat?: string) {
    const e = await ausfuehren(`Lade ${zitat ? "Volltext" : "Volltexte"} aus den öffentlichen Quellen …`, () =>
      kernImHintergrund<{ geladen: string[]; fehler: { zitat: string; fehler: string }[] }>("akten.volltexte_laden", {
        akte_id: akteId,
        zitat: zitat ?? null,
      }),
    );
    if (!e) return;
    await aktualisiereUrteile();
    setMeldung(
      `${e.geladen.length} ${e.geladen.length === 1 ? "Volltext" : "Volltexte"} geladen.` +
        (e.fehler.length ? ` Nicht geladen: ${e.fehler.map((f) => `${f.zitat} (${f.fehler})`).join("; ")}` : ""),
    );
  }

  async function onlinePruefen() {
    const e = await ausfuehren("Suche zitierte Entscheidungen bei gesetze-bayern.de bzw. NeuRIS …", () =>
      kernImHintergrund<{ geprueft: { zitat: string; quelle: string; status: UrteilStatus }[]; fehler: { zitat: string; quelle: string; fehler: string }[] }>(
        "akten.online_pruefen",
        { akte_id: akteId },
      ),
    );
    if (!e) return;
    await aktualisiereUrteile();
    const belegt = e.geprueft.filter((g) => g.status === "belegt").length;
    setMeldung(
      `${e.geprueft.length} ${e.geprueft.length === 1 ? "Zitat" : "Zitate"} online geprüft, davon ${belegt} belegt.` +
        (e.fehler.length ? ` Nicht geprüft: ${e.fehler.map((f) => `${f.zitat} (${f.quelle}: ${f.fehler})`).join("; ")}` : ""),
    );
  }

  async function neuPruefen() {
    await ausfuehren("Prüfe Zitate gegen die Wissensbasis …", () => kern("akten.zitate_pruefen", { akte_id: akteId }));
    await ladeDokumente();
    if (inhalt) await oeffneDokument(inhalt.dokument.id);
    if (ansicht === "normen") await ladeNormen(null);
    if (ansicht === "rechtsprechung") await ladeUrteile(null);
    if (ansicht === "dokument" && inhalt) await waehleDokModus(dokModus);
  }

  /** „Könnte … gemeint sein?“: eigene Schreibweise anlegen oder aufheben; die Zitate aller Akten werden neu geprüft. */
  async function zuordnen(von: string, nach: string | null) {
    await ausfuehren(nach ? `Ordne „${von}“ ${nach} zu …` : `Hebe Zuordnung von „${von}“ auf …`, () =>
      nach ? kern("gesetze.schreibweise_setzen", { von, nach }) : kern("gesetze.schreibweise_loeschen", { von }),
    );
    vorschlaegeVergessen();
    await ladeDokumente();
    if (ansicht === "normen") await ladeNormen(null);
    if (ansicht === "dokument" && inhalt) {
      await oeffneDokument(inhalt.dokument.id);
      await waehleDokModus(dokModus);
    }
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

  // Filterspalte: Ordner, Parteien (übliche Beteiligten-Tags), übrige Tags und Prüfstand der Zitate.
  const ordner = [...zaehle(dokumente.map(oberordner)).entries()].sort((a, b) => a[0].localeCompare(b[0], "de"));
  const tags = tagUebersicht(dokumente);
  const parteien = tags.filter((t) => BETEILIGTE.includes(t.name));
  const weitereTags = tags.filter((t) => !BETEILIGTE.includes(t.name));
  const ohneTag = dokumente.filter((d) => d.tags.length === 0).length;
  const mitUnbelegt = dokumente.filter(unbelegt).length;
  // Metadaten aus „Details“: Art und Absender; ohne Angabe stehen sie unter „ohne …“.
  const arten = [...zaehle(dokumente.map((d) => d.art ?? "")).entries()].sort(
    (a, b) => Number(a[0] === "") - Number(b[0] === "") || a[0].localeCompare(b[0], "de"),
  );
  const absenderNamen = new Map(dokumente.filter((d) => d.absender).map((d) => [absenderSchluessel(d), d.absender!]));
  const absender = [...zaehle(dokumente.map(absenderSchluessel)).entries()].sort(
    (a, b) =>
      Number(a[0] === "") - Number(b[0] === "") ||
      (a[0] === "eigene" ? -1 : b[0] === "eigene" ? 1 : 0) ||
      (absenderNamen.get(a[0])?.name ?? "").localeCompare(absenderNamen.get(b[0])?.name ?? "", "de"),
  );
  const gefiltert = dokumente.filter(
    (d) =>
      (filter.ordner == null || oberordner(d) === filter.ordner) &&
      (filter.tag == null || (filter.tag === "" ? d.tags.length === 0 : d.tags.some((t) => t.name === filter.tag))) &&
      (!filter.unbelegt || unbelegt(d)) &&
      (filter.art == null || (d.art ?? "") === filter.art) &&
      (filter.absender == null || absenderSchluessel(d) === filter.absender) &&
      dokumentPasst(d, dokSuche),
  );
  // Zeitlich geordnet: neueste zuerst wie in einer Papierakte von oben; Dokumente ohne Datum am Ende.
  const sichtbar = nachDatum
    ? [...gefiltert].sort((a, b) => (b.datum ?? "").localeCompare(a.datum ?? "") || a.dateiname.localeCompare(b.dateiname, "de"))
    : gefiltert;
  const gefiltertAktiv =
    filter.ordner != null || filter.tag != null || filter.unbelegt || filter.art != null || filter.absender != null;
  const mitOrdnern = ordner.some(([o]) => o !== "");

  const zeigeVolltextSeite =
    !!volltext && (ansicht === "rechtsprechung" || (ansicht === "dokument" && dokModus === "rechtsprechung"));
  const zeigeBelegSeite = !!auswahl && ansicht === "dokument" && (dokModus === "text" || dokModus === "original");
  const zeigeAnmerkSeite =
    !zeigeBelegSeite && !anmerkZu && !!inhalt && ansicht === "dokument" && (dokModus === "text" || dokModus === "original");

  const filterKnopf = (aktiv: boolean, text: string, anzahl: number, onClick: () => void, klasse = "") => (
    <button key={text} className={`filter-eintrag ${klasse}${aktiv ? " aktiv" : ""}`} aria-pressed={aktiv} onClick={onClick}>
      <span>{text}</span>
      <span className="anzahl">{anzahl}</span>
    </button>
  );

  const meldungen = (
    <>
      <EinrichtungsHinweise
        hinweise={[
          ocr && !ocr.verfuegbar
            ? {
                titel: "Texterkennung nicht verfügbar",
                text: `${ocr.hinweis} PDFs mit Text und Word-Dateien lassen sich trotzdem lesen.`,
              }
            : null,
          gesetzeGeladen === 0
            ? {
                titel: "Die Wissensbasis ist noch leer",
                text:
                  "Lade unter „Gesetze“ die Voreinstellung, damit zitierte Normen geprüft werden können; danach hier " +
                  "„Zitate neu prüfen“.",
              }
            : null,
        ]}
      />
      <UebernahmeFrage
        kopien={offeneUebernahmen(kopien, spaeter)}
        dokumente={dokumente}
        laeuft={!!laeuft}
        onUebernehmen={fassungUebernehmen}
        onSpaeter={(k) => setSpaeter(new Set(spaeter).add(kopieSchluessel(k)))}
      />
      {loeschfrage && (
        <Rueckfrage
          frage={
            loeschfrage.art === "urteil"
              ? `Entscheidung „${loeschfrage.name}“ aus der Akte entfernen?`
              : `Dokument „${dokumente.find((d) => d.id === loeschfrage.id)?.dateiname}“ aus der Akte entfernen?`
          }
          erklaerung={
            loeschfrage.art === "urteil"
              ? "Entfernt werden der gelesene Text und die Kopie, die die App abgelegt hat. Steht die Entscheidung " +
                "nicht noch in einer anderen Akte oder ohne Akte in der Sammlung, verschwindet sie auch dort. Deine " +
                "Datei am ursprünglichen Ort und geladene Volltexte im Roharchiv bleiben unverändert."
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
      {laeuft && <p className="status" role="status">{laeuft}</p>}
      {meldung && !laeuft && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
    </>
  );

  const rechtsprechungAnsicht = (leer?: string, dokumentId?: number) =>
    urteile && (
      <>
        {kiAn && urteile.length > 0 && (
          <GegenueberstellungBereich
            key={`${akteId}-${dokumentId ?? ""}`}
            akteId={akteId}
            dokumentId={dokumentId}
            onFundstelle={(f) => oeffneDokument(f.dokument_id, f.abschnitt)}
          />
        )}
        {dokumentId == null && zugeordnet.length > 0 && (
          <ZugeordneteUrteile
            urteile={zugeordnet}
            offen={volltext?.id ?? null}
            laeuft={!!laeuft}
            onVolltext={(id) => (volltext?.id === id ? setVolltext(null) : zeigeVolltext(id))}
            onLoesen={zuordnungLoesen}
          />
        )}
        {dokumentId == null && zugeordnet.length > 0 && <h3 className="abschnitt-titel">In den Dokumenten zitiert</h3>}
        <RechtsprechungAnsicht
        urteile={urteile}
        offen={volltext?.id ?? null}
        laeuft={!!laeuft}
        leer={leer}
        onFundstelle={oeffneDokument}
        onErgaenzen={urteilWaehlen}
        onVolltexteLaden={volltexteLaden}
        onOnlinePruefen={onlinePruefen}
        onVolltext={(id, rn) => (volltext?.id === id && rn == null ? setVolltext(null) : zeigeVolltext(id, rn))}
        onEntfernen={(u) => setLoeschfrage({ art: "urteil", id: u.id, name: urteilHerkunft(u) })}
        />
      </>
    );

  // Hauptinhalt mit Seitenleiste (Wortlaut einer Norm, Volltext einer Entscheidung) und verschiebbarem Trenner.
  const arbeitsflaeche = (haupt: ReactNode) => (
    <div className={`akte-arbeitsflaeche${zeigeAnmerkSeite ? " mit-anmerkungen" : ""}`} ref={flaeche} style={{ "--seite-breite": `${seitenbreite}px` } as CSSProperties}>
      <div className="akte-haupt">{haupt}</div>
      {(zeigeVolltextSeite || zeigeBelegSeite || zeigeAnmerkSeite) && (
        <Trenner
          label="Breite der Seitenleiste"
          titel="Ziehen, um die Breite zu ändern"
          breite={seitenbreite}
          min={SEITE_MIN}
          standard={SEITE_STANDARD}
          rahmen={flaeche}
          rest={320}
          onZiehen={breiteZiehen}
          onSetze={setzeSeitenbreite}
        />
      )}
      {zeigeVolltextSeite && volltext && (
        <VolltextAnsicht volltext={volltext} rn={volltextRn} onSchliessen={() => setVolltext(null)} />
      )}
      {zeigeAnmerkSeite && (
        <AnmerkungsLeiste
          liste={anm.liste}
          bedeutungen={anm.bedeutungen}
          aktiv={anm.aktiv}
          onWaehle={anmerkungWaehlen}
          onAkte={() => onReiter("anmerkungen")}
          onSchliessen={anmerkungenUmschalten}
          lesezeichenAnzahl={lz.lesezeichen.length}
          pdfDokument={inhalt?.dokument.format === "pdf" ? inhalt.dokument.id : undefined}
          lesezeichen={
            <LesezeichenLeiste
              lz={lz}
              pdf={inhalt?.dokument.format === "pdf"}
              onWaehle={lesezeichenWaehlen}
              onInhalt={inhaltWaehlen}
              onHier={lesezeichenHier}
              onAkte={() => {
                setAnmTeil("lesezeichen");
                onReiter("anmerkungen");
              }}
            />
          }
        />
      )}
      {zeigeBelegSeite && auswahl && (
        <aside className="akte-seite">
          <p className="fundort">Zitiert in {auswahl.ort}</p>
          {auswahl.beleg ? <BelegAnsicht beleg={auswahl.beleg} /> : <p className="status" role="status">Lade Wortlaut …</p>}
        </aside>
      )}
    </div>
  );

  if (reiter !== "dokumente") {
    return (
      <div className="akte-reiterinhalt">
        {meldungen}
        {reiter === "normen" &&
          arbeitsflaeche(normen && <NormenAnsicht normen={normen} onFundstelle={oeffneDokument} onZuordnen={zuordnen} gesperrt={!!laeuft} />)}
        {reiter === "rechtsprechung" && arbeitsflaeche(rechtsprechungAnsicht())}
        {kiAn && reiter === "chat" && <Chat akteId={akteId} onEinstellungen={onEinstellungen} />}
        {reiter === "anmerkungen" && (
          <div className="anm-reiter-rahmen">
            <div className="segment anm-teil-wahl" role="tablist" aria-label="Was angezeigt wird">
              {(
                [
                  ["markierungen", "Markierungen und Kommentare"],
                  ["lesezeichen", "Lesezeichen"],
                  ["alle", "Alle"],
                ] as const
              ).map(([id, titel]) => (
                <button key={id} role="tab" aria-selected={anmTeil === id} className={`segment-knopf${anmTeil === id ? " aktiv" : ""}`} onClick={() => setAnmTeil(id)}>
                  {titel}
                </button>
              ))}
            </div>
            <OrdnerAnsicht akteId={akteId} ansicht={anmTeil} onLesezeichen={(z) => void oeffneLesezeichen(z)} onAnmerkung={(a) => void oeffneAnmerkung(a)} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      ref={dokRahmen}
      className={`akte-dokumente${filterZu ? " filter-zu" : ""}${dokBreite != null ? " feste-breite" : ""}`}
      style={dokBreite != null ? ({ "--dok-breite": `${dokBreite}px` } as CSSProperties) : undefined}
    >
      <aside className="akte-filter" aria-label="Filter">
        <button
          className="leisten-knopf"
          onClick={filterUmschalten}
          title={filterZu ? "Filter ausklappen" : "Filter einklappen"}
          aria-label={filterZu ? "Filter ausklappen" : "Filter einklappen"}
          aria-expanded={!filterZu}
        >
          <Zeichen name={filterZu ? "ausklappen" : "einklappen"} groesse={18} />
          {filterZu && gefiltertAktiv && <span className="filter-punkt" title="Ein Filter ist gesetzt" />}
        </button>
        {!filterZu && (
          <>
            <h3>Dokumente</h3>
            {filterKnopf(!gefiltertAktiv, "Alle Dokumente", dokumente.length, () => setFilter(KEIN_FILTER))}
            {arten.some(([a]) => a !== "") && (
              <>
                <h4>Art</h4>
                {arten.map(([a, n]) =>
                  filterKnopf(filter.art === a, a || "ohne Art", n, () => setFilter({ ...filter, art: filter.art === a ? null : a }), "unter"),
                )}
              </>
            )}
            {absender.some(([a]) => a !== "") && (
              <>
                <h4>Absender</h4>
                {absender.map(([a, n]) =>
                  filterKnopf(
                    filter.absender === a,
                    a === "" ? "ohne Absender" : a === "eigene" ? "Wir" : (absenderNamen.get(a)?.name ?? a),
                    n,
                    () => setFilter({ ...filter, absender: filter.absender === a ? null : a }),
                    "unter",
                  ),
                )}
              </>
            )}
            {mitOrdnern && (
              <>
                <h3>Ordner</h3>
                {ordner.map(([o, n]) =>
                  filterKnopf(filter.ordner === o, o || "ohne Ordner", n, () =>
                    setFilter({ ...filter, ordner: filter.ordner === o ? null : o }),
                  ),
                )}
              </>
            )}
            {(parteien.length > 0 || weitereTags.length > 0) && (
              <>
                <h3>Tags</h3>
                {[...parteien, ...weitereTags].map((t) =>
                  filterKnopf(filter.tag === t.name, t.name, t.anzahl, () =>
                    setFilter({ ...filter, tag: filter.tag === t.name ? null : t.name }),
                  ),
                )}
                {ohneTag > 0 &&
                  filterKnopf(filter.tag === "", "ohne Tag", ohneTag, () =>
                    setFilter({ ...filter, tag: filter.tag === "" ? null : "" }),
                  )}
              </>
            )}
            {mitUnbelegt > 0 && (
              <>
                <h3>Prüfung</h3>
                {filterKnopf(filter.unbelegt, "Zitate nicht belegt", mitUnbelegt, () =>
                  setFilter({ ...filter, unbelegt: !filter.unbelegt }),
                )}
              </>
            )}
            {beteiligte.length > 0 && (
              <>
                <h3>Beteiligte</h3>
                <ul className="filter-beteiligte">
                  {beteiligte.map((b) => (
                    <li key={b.id}>
                      <button className="link" onClick={onBeteiligte} title="Beteiligte der Akte öffnen">
                        <span className={`punkt ${b.gruppe}`} aria-hidden />
                        {b.name}
                      </button>
                      <span className="leise">{b.rolle_text}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </aside>

      <section className="akte-liste" aria-label="Dokumente der Akte">
        <div className="leiste">
          <button onClick={hinzufuegen} disabled={!!laeuft}>
            + Dokumente
          </button>
          <button className="zweitrangig" onClick={ordnerHinzufuegen} disabled={!!laeuft} title="Liest auch alle Unterordner ein">
            + Ordner
          </button>
          {dokumente.length > 0 && (
            <button className="zweitrangig rechts" onClick={neuPruefen} disabled={!!laeuft} title="Nach dem Laden weiterer Gesetze sinnvoll">
              Zitate neu prüfen
            </button>
          )}
        </div>
        {meldungen}
        {dokumente.length === 0 && !laeuft && (
          <LeerHinweis
            symbol="dokumente"
            aktion={
              <>
                <button onClick={hinzufuegen}>+ Dokumente</button>
                <button className="zweitrangig" onClick={ordnerHinzufuegen}>
                  + Ordner
                </button>
              </>
            }
          >
            Noch keine Dokumente in dieser Akte. Füge PDF-, Word- oder Textdateien hinzu.
          </LeerHinweis>
        )}
        {dokumente.length > 0 && (
          <div className="dok-suche" role="search">
            <input
              type="search"
              value={dokSuche}
              onChange={(e) => setDokSuche(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape" && dokSuche) {
                  e.stopPropagation();
                  setDokSuche("");
                }
              }}
              placeholder="Dokument suchen: Titel, Dateiname, Art, Absender, Datum …"
              aria-label="Dokument in dieser Akte suchen"
              title="Findet auch Wortteile, z. B. „protokoll“ in „Diagnoseprotokoll“. Den Inhalt der Dokumente durchsucht der Bereich „Suche“."
            />
            {dokSuche.trim() && (
              <span className="dok-suche-zahl" aria-live="polite">
                {sichtbar.length} von {dokumente.length}
              </span>
            )}
          </div>
        )}
        {dokumente.length > 0 && (
          <table className="dokumente kompakt">
            <colgroup>
              <col className="spalte-datum" />
              <col />
              <col className="spalte-zitate" />
            </colgroup>
            <thead>
              <tr>
                <th>
                  <button
                    className="link spaltenkopf"
                    onClick={() => setNachDatum(!nachDatum)}
                    aria-pressed={nachDatum}
                    title={nachDatum ? "Nach Ordner und Dateiname ordnen" : "Nach Datum ordnen, neueste zuerst"}
                  >
                    Datum {nachDatum ? "▼" : "↕"}
                  </button>
                </th>
                <th>Dokument</th>
                <th title="Normzitate: belegt / nicht belegt / Gesetz unbekannt">Zitate</th>
              </tr>
            </thead>
            <tbody>
              {sichtbar.map((d) => (
                <tr
                  key={d.id}
                  className={inhalt?.dokument.id === d.id ? "aktiv" : undefined}
                  onClick={(e) => {
                    // Die ganze Zeile öffnet das Dokument; Knöpfe und Eingaben in der Zeile behalten ihre eigene Wirkung.
                    if (!(e.target as HTMLElement).closest("button, input")) void oeffneDokument(d.id);
                  }}
                >
                  <td>
                    <DokumentDatum d={d} onFundstelle={() => oeffneDokument(d.id, d.datum_abschnitt ?? undefined)} />
                  </td>
                  <td>
                    <div className="dok-name-zeile">
                      <span className="dok-symbol">
                        <Zeichen name="dokumente" groesse={16} />
                      </span>
                      <button className="link dok-name" onClick={() => oeffneDokument(d.id)}>
                        {dokumentName(d)}
                      </button>
                    </div>
                    <div className="herkunft">
                      {d.art && <span className="art-chip">{d.art}</span>}
                      {d.absender && <>von {d.absender.wert === "eigene" ? "uns" : d.absender.name} · </>}
                      {d.titel && <>{d.dateiname} · </>}
                      {lesartText(d)}
                      {d.seiten != null && <> · {d.seiten} S.</>}
                      {d.randnummern > 0 && <> · {d.randnummern} Rn.</>}
                      {d.herkunft && <> · {d.herkunft}</>}
                      {d.fassung.nr > 1 && <> · Fassung {d.fassung.nr}</>}
                      {!!d.anmerkungen && (
                        <>
                          {" · "}
                          {d.anmerkungen} {d.anmerkungen === 1 ? "Anmerkung" : "Anmerkungen"}
                        </>
                      )}
                      {kopien.some((k) => k.dokument_id === d.id) && <> · in Bearbeitung</>}
                    </div>
                    {tagEdit?.id === d.id ? (
                      <TagEditor
                        text={tagEdit.text}
                        onText={(text) => setTagEdit({ id: d.id, text })}
                        onSpeichern={() => tagsSpeichern(d.id, tagsAusText(tagEdit.text))}
                        onAbbrechen={() => setTagEdit(null)}
                      />
                    ) : (
                      <>
                        {d.tags.length > 0 && (
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
                          </div>
                        )}
                        {/* Nur beim geöffneten Dokument sichtbar (siehe styles.css). */}
                        <span className="zeilen-aktionen">
                          <button
                            className="link klein"
                            onClick={() => setTagEdit({ id: d.id, text: d.tags.map((t) => t.name).join(", ") })}
                            disabled={!!laeuft}
                          >
                            {d.tags.length ? "Tags ändern" : "+ Tag"}
                          </button>
                          <button
                            className="link klein gefahr"
                            onClick={() => setLoeschfrage({ art: "dokument", id: d.id })}
                            disabled={!!laeuft}
                            title="Dokument aus der Akte entfernen"
                          >
                            entfernen
                          </button>
                        </span>
                      </>
                    )}
                  </td>
                  <td>
                    <ZitatZaehlung zitate={d.zitate} kurz />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {dokumente.length > 0 && sichtbar.length === 0 && (
          <p className="leer">
            {dokSuche.trim()
              ? `Kein Dokument passt zu „${dokSuche.trim()}“${gefiltertAktiv ? " und dem gewählten Filter" : ""}. Den Text der Dokumente durchsucht der Bereich „Suche“.`
              : "Kein Dokument passt zu diesem Filter."}
          </p>
        )}
      </section>

      <Trenner
        label="Breite von Dokumentliste und Dokumentansicht"
        titel="Ziehen, um Dokumentliste und Dokumentansicht anders aufzuteilen"
        breite={dokBreite ?? dokStandard()}
        min={DOK_MIN}
        standard={dokStandard()}
        rahmen={dokRahmen}
        rest={dokRest()}
        onZiehen={dokBreiteZiehen}
        onSetze={setzeDokBreite}
        wertText={`Dokumentansicht ${dokBreite ?? dokStandard()} Pixel breit`}
      />
      <section className="akte-offen" aria-label="Geöffnetes Dokument">
        {inhalt ? (
          <>
            <DokModusLeiste
              dokument={inhalt.dokument}
              modus={dokModus}
              onModus={(m) => m !== dokModus && nachRueckfrage(() => void waehleDokModus(m))}
              anmerkungen={
                dokModus === "text" || dokModus === "original"
                  ? { anzahl: anm.liste.length, offen: zeigeAnmerkSeite, onUmschalten: anmerkungenUmschalten }
                  : undefined
              }
            />
            {verlassen && (
              <div className="rueckfrage" role="alertdialog" aria-label="Änderungen speichern?">
                <strong>Änderungen speichern?</strong>
                <p>In „Details“ gibt es Eingaben, die noch nicht gespeichert sind.</p>
                <div className="aktionen">
                  <button
                    onClick={async () => {
                      if (await details.current?.speichern()) {
                        const { weiter } = verlassen;
                        setVerlassen(null);
                        weiter();
                      }
                    }}
                    autoFocus
                  >
                    Speichern
                  </button>
                  <button
                    className="gefahr-voll"
                    onClick={() => {
                      details.current?.verwerfen();
                      const { weiter } = verlassen;
                      setVerlassen(null);
                      weiter();
                    }}
                  >
                    Verwerfen
                  </button>
                  <button className="zweitrangig" onClick={() => setVerlassen(null)}>
                    Abbrechen
                  </button>
                </div>
              </div>
            )}
            <DokumentExtern
              key={`${inhalt.dokument.id}-${inhalt.dokument.fassung.nr}`}
              dokument={inhalt.dokument}
              kopie={kopien.find((k) => k.dokument_id === inhalt.dokument.id)}
              gefragt={offeneUebernahmen(kopien, spaeter).some((k) => k.dokument_id === inhalt.dokument.id)}
              laeuft={!!laeuft}
              ausfuehren={ausfuehren}
              onKopien={ladeKopien}
              onUebernehmen={fassungUebernehmen}
              onMeldung={setMeldung}
            />
            {arbeitsflaeche(
              <>
                {anm.schicht}
                {dokModus === "text" && (
                  <div
                    ref={textRahmen}
                    className="anm-rahmen"
                    {...anm.rahmenProps}
                    {...anmerkungsHandler(anm.ereignisse)}
                  >
                    <DokumentAnsicht
                      inhalt={inhalt}
                      auswahl={auswahl}
                      onZitat={waehleZitat}
                      markiert={markiert ?? undefined}
                      ohneTitel
                      anmerkungen={anm.liste}
                      aktiveAnmerkung={anm.aktiv}
                      lesezeichen={lz.lesezeichen}
                    />
                  </div>
                )}
                {(dokModus === "text" || dokModus === "original") && <Bildlaufmarken wurzel={markenWurzel} />}
                {dokModus === "original" && (
                  <OriginalAnsicht
                    key={inhalt.dokument.id}
                    dokument={inhalt.dokument}
                    startSeite={auswahl?.zitat.seite ?? null}
                    anmerkungen={anm.original}
                    lesezeichenStand={lz.stand}
                    hinweis="Zum Markieren mit der Maus über die Wörter ziehen; Zitate und Belege zeigt die Textansicht."
                  />
                )}
                {dokModus === "normen" && normen && (
                  <NormenAnsicht
                    normen={normen}
                    onFundstelle={oeffneDokument}
                    onZuordnen={zuordnen}
                    gesperrt={!!laeuft}
                    leer="In diesem Dokument wurden keine Normzitate erkannt."
                  />
                )}
                {dokModus === "rechtsprechung" &&
                  rechtsprechungAnsicht("In diesem Dokument wurden keine Rechtsprechungszitate erkannt.", inhalt.dokument.id)}
                {kiAn && dokModus === "chat" && <Chat akteId={akteId} dokumentId={inhalt.dokument.id} onEinstellungen={onEinstellungen} />}
                {dokModus === "details" && (
                  <DokumentDetails
                    key={inhalt.dokument.id}
                    ref={details}
                    akteId={akteId}
                    dokumentId={inhalt.dokument.id}
                    onGespeichert={() => void metadatenGespeichert(inhalt.dokument.id)}
                  />
                )}
              </>,
            )}
          </>
        ) : (
          dokumente.length > 0 && <LeerHinweis symbol="dokumentLesen">Wähle links ein Dokument, um Text und Normzitate zu sehen.</LeerHinweis>
        )}
      </section>
    </div>
  );
}
