import Trenner from "./Trenner";
import {
  CSSProperties,
  MouseEvent as ReactMouseEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  AnmerkungsLeiste,
  anmerkungsHandler,
  OriginalAnmerkungen,
  SeitenAuswahl,
  useAnmerkungen,
} from "./Anmerkungen";
import {
  abschnittBeginne,
  Anmerkung,
  AnmerkungAufSeite,
  auswahlRechtecke,
  SeitenWort,
  stueckKlassen,
  stuecke,
  wortAn,
} from "./anmerkungLogik";
import Chat from "./Chat";
import DokumentDetails, { DetailsGriff } from "./DokumentDetails";
import DokumentExtern, { UebernahmeFrage } from "./DokumentExtern";
import { GegenueberstellungBereich } from "./Gegenueberstellung";
import { useKiAn } from "./kiSchalter";
import { BelegAnsicht } from "./Gesetze";
import { gemerkt, merke } from "./merken";
import Zeichen, { LeerHinweis } from "./Symbole";
import { Bildlaufmarken, LesezeichenLeiste, OrdnerAnsicht, OrdnerAnsichtArt, useLesezeichen } from "./Lesezeichen";
import { Lesezeichen, LesezeichenAufSeite } from "./lesezeichenLogik";
import {
  Abschnitt,
  Akte as AkteTyp,
  AktenDokument,
  ImportErgebnisDatei,
  Arbeitskopie,
  BETEILIGTE,
  Beleg,
  Beteiligung,
  DokumentInhalt,
  Loeschergebnis,
  NormEintrag,
  NormZitat,
  ONLINE_QUELLE,
  OcrStatus,
  OrdnerFunde,
  QUELLEN_HINWEIS,
  Seitenbild,
  STATUS_TEXT,
  URTEIL_QUELLEN,
  URTEIL_STATUS_TEXT,
  URTEIL_TEILE,
  UrteilEintrag,
  UrteilInfo,
  UrteilStatus,
  UrteilVolltext,
  ZitatStatus,
  dokumentDatum,
  dokumentName,
  fundstelle,
  istDesktop,
  kern,
  kernImHintergrund,
  kopieSchluessel,
  lesartText,
  markiereBegriffe,
  offeneUebernahmen,
  renderBreite,
  segmente,
  sortiereTags,
  tagUebersicht,
  tagsAusText,
  rnHinweis,
  urteilHerkunft,
  urteilTitel,
  URTEIL_QUELLE_NAME,
} from "./kern";

type Ansicht = "dokument" | "anmerkungen" | "normen" | "rechtsprechung" | "chat";
/** Was zum geöffneten Dokument gezeigt wird. */
type DokModus = "text" | "original" | "normen" | "rechtsprechung" | "chat" | "details";

/** Breite der Seitenleiste (Wortlaut, Volltext), je Gerät gemerkt. */
const SEITE_STANDARD = 360;
const SEITE_MIN = 260;
const BREITE_SCHLUESSEL = "akte.seitenbreite";

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
interface OrdnerFrage {
  funde: OrdnerFunde;
  tags: Record<string, string>;
}

type Loeschfrage = { art: "dokument"; id: number } | { art: "urteil"; id: number; name: string };

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
  const [tagEdit, setTagEdit] = useState<{ id: number; text: string } | null>(null);
  const [ergaenzung, setErgaenzung] = useState<Ergaenzung | null>(null);
  const [volltext, setVolltext] = useState<UrteilVolltext | null>(null);
  const [volltextRn, setVolltextRn] = useState<number | null>(null);
  const [seitenbreite, setSeitenbreite] = useState(gespeicherteBreite);
  const [kopien, setKopien] = useState<Arbeitskopie[]>([]);
  // Geänderte Arbeitskopien, bei denen „Später“ gewählt wurde; gilt bis zum nächsten Speichern.
  const [spaeter, setSpaeter] = useState<ReadonlySet<string>>(new Set());
  const flaeche = useRef<HTMLDivElement>(null);
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
      (filter.absender == null || absenderSchluessel(d) === filter.absender),
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
          arbeitsflaeche(normen && <NormenAnsicht normen={normen} onFundstelle={oeffneDokument} />)}
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
    <div className={filterZu ? "akte-dokumente filter-zu" : "akte-dokumente"}>
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
        {dokumente.length > 0 && sichtbar.length === 0 && <p className="leer">Kein Dokument passt zu diesem Filter.</p>}
      </section>

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
                    onMouseUp={() => textRahmen.current && anm.beiAuswahl(textRahmen.current)}
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
                  <NormenAnsicht normen={normen} onFundstelle={oeffneDokument} leer="In diesem Dokument wurden keine Normzitate erkannt." />
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

export function Rueckfrage({
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

/** Datum in der Dokumentliste: Wert und Herkunft; die Datumszeile öffnet das Dokument an ihrer Fundstelle. */
function DokumentDatum({ d, onFundstelle }: { d: AktenDokument; onFundstelle: () => void }) {
  const angabe = dokumentDatum(d);
  if (!d.datum) return <span title={angabe.erklaerung}>–</span>;
  return (
    <div className="dok-datum" title={angabe.erklaerung}>
      {d.datum_quelle === "dokument" && d.datum_abschnitt != null ? (
        <button className="link" onClick={onFundstelle}>
          {angabe.text}
        </button>
      ) : (
        angabe.text
      )}
      <div className="herkunft">{angabe.herkunft}</div>
    </div>
  );
}

/** Zahl der Normzitate je Prüfstand; „kurz“ zeigt nur die Zahlen, der Text steht im Tooltip. */
function ZitatZaehlung({ zitate, kurz = false }: { zitate: Partial<Record<ZitatStatus, number>>; kurz?: boolean }) {
  const reihenfolge: ZitatStatus[] = ["belegt", "nicht_gefunden", "unbekanntes_gesetz"];
  const teile = reihenfolge.filter((s) => zitate[s]);
  if (teile.length === 0) return <span className="leer">{kurz ? "–" : "keine"}</span>;
  return (
    <span className={kurz ? "zitat-kurz" : undefined}>
      {teile.map((s) => (
        <span key={s} className={`zitat-zahl ${s}`} title={kurz ? `${zitate[s]} ${STATUS_TEXT[s]}` : undefined}>
          {kurz ? zitate[s] : `${zitate[s]} ${STATUS_TEXT[s]}`}
        </span>
      ))}
    </span>
  );
}

/** Hinweise zur Einrichtung (Texterkennung, Wissensbasis) in einer einzigen, eingeklappten Zeile. */
function EinrichtungsHinweise({ hinweise }: { hinweise: ({ titel: string; text: string } | null)[] }) {
  const da = hinweise.filter((h): h is { titel: string; text: string } => h != null);
  if (da.length === 0) return null;
  if (da.length === 1)
    return (
      <details className="hinweis kurz-hinweis">
        <summary>{da[0].titel}</summary>
        {da[0].text}
      </details>
    );
  return (
    <details className="hinweis kurz-hinweis">
      <summary>{da.length} Hinweise zur Einrichtung</summary>
      {da.map((h) => (
        <p key={h.titel}>
          <strong>{h.titel}:</strong> {h.text}
        </p>
      ))}
    </details>
  );
}

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

function DokModusLeiste({
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
function scrollRahmen(el: HTMLElement): HTMLElement | null {
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

function NormenAnsicht({
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

function RechtsprechungAnsicht({
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
function ZugeordneteUrteile({
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
