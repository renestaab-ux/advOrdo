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
import Chat from "./Chat";
import DokumentExtern, { UebernahmeFrage } from "./DokumentExtern";
import { GegenueberstellungBereich } from "./Gegenueberstellung";
import { BelegAnsicht } from "./Gesetze";
import { gemerkt, merke } from "./merken";
import Zeichen from "./Symbole";
import {
  Abschnitt,
  Akte as AkteTyp,
  AktenDokument,
  AktenImport,
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
  fundstelle,
  istDesktop,
  kern,
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

type Ansicht = "dokument" | "normen" | "rechtsprechung" | "chat";
/** Was zum geöffneten Dokument gezeigt wird. */
type DokModus = "text" | "original" | "normen" | "rechtsprechung" | "chat";

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
export type AkteReiter = "dokumente" | "normen" | "rechtsprechung" | "chat";

const FILTER_SCHLUESSEL = "akte.filter.eingeklappt";

/** Filter der Dokumentliste; alle gesetzten gelten zusammen. */
interface Filter {
  /** Oberster Ordner aus dem Ordner-Import; "" = Dokumente ohne Ordner. */
  ordner: string | null;
  /** Partei- oder anderer Tag; "" = Dokumente ohne Tag. */
  tag: string | null;
  /** Nur Dokumente mit Zitaten, die nicht belegt sind. */
  unbelegt: boolean;
}

const KEIN_FILTER: Filter = { ordner: null, tag: null, unbelegt: false };

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
    await ausfuehren("Lade Dokumente …", ladeDokumente);
    onGeaendert();
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

  async function oeffneDokument(id: number, abschnitt?: number) {
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
      kern<{ geladen: string[]; fehler: { zitat: string; fehler: string }[] }>("akten.volltexte_laden", {
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
      kern<{ geprueft: { zitat: string; quelle: string; status: UrteilStatus }[]; fehler: { zitat: string; quelle: string; fehler: string }[] }>(
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
  const gefiltert = dokumente.filter(
    (d) =>
      (filter.ordner == null || oberordner(d) === filter.ordner) &&
      (filter.tag == null || (filter.tag === "" ? d.tags.length === 0 : d.tags.some((t) => t.name === filter.tag))) &&
      (!filter.unbelegt || unbelegt(d)),
  );
  // Zeitlich geordnet: neueste zuerst wie in einer Papierakte von oben; Dokumente ohne Datum am Ende.
  const sichtbar = nachDatum
    ? [...gefiltert].sort((a, b) => (b.datum ?? "").localeCompare(a.datum ?? "") || a.dateiname.localeCompare(b.dateiname, "de"))
    : gefiltert;
  const gefiltertAktiv = filter.ordner != null || filter.tag != null || filter.unbelegt;
  const mitOrdnern = ordner.some(([o]) => o !== "");

  const zeigeVolltextSeite =
    !!volltext && (ansicht === "rechtsprechung" || (ansicht === "dokument" && dokModus === "rechtsprechung"));
  const zeigeBelegSeite = !!auswahl && ansicht === "dokument" && (dokModus === "text" || dokModus === "original");

  const filterKnopf = (aktiv: boolean, text: string, anzahl: number, onClick: () => void, klasse = "") => (
    <button key={text} className={`filter-eintrag ${klasse}${aktiv ? " aktiv" : ""}`} aria-pressed={aktiv} onClick={onClick}>
      <span>{text}</span>
      <span className="anzahl">{anzahl}</span>
    </button>
  );

  const meldungen = (
    <>
      {ocr && !ocr.verfuegbar && (
        <details className="hinweis kurz-hinweis">
          <summary>Texterkennung nicht verfügbar</summary>
          {ocr.hinweis} PDFs mit Text und Word-Dateien lassen sich trotzdem lesen.
        </details>
      )}
      {gesetzeGeladen === 0 && (
        <details className="hinweis kurz-hinweis">
          <summary>Die Wissensbasis ist noch leer</summary>
          Lade unter „Gesetze“ die Voreinstellung, damit zitierte Normen geprüft werden können; danach hier „Zitate neu
          prüfen“.
        </details>
      )}
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
      {laeuft && <p className="status">{laeuft}</p>}
      {meldung && !laeuft && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler">{fehler}</p>}
    </>
  );

  const rechtsprechungAnsicht = (leer?: string, dokumentId?: number) =>
    urteile && (
      <>
        {urteile.length > 0 && (
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
    <div className="akte-arbeitsflaeche" ref={flaeche} style={{ "--seite-breite": `${seitenbreite}px` } as CSSProperties}>
      <div className="akte-haupt">{haupt}</div>
      {(zeigeVolltextSeite || zeigeBelegSeite) && (
        <div
          className="trenner"
          role="separator"
          aria-orientation="vertical"
          aria-label="Breite der Seitenleiste"
          title="Ziehen, um die Breite zu ändern; Doppelklick setzt sie zurück"
          onPointerDown={breiteZiehen}
          onDoubleClick={() => setzeSeitenbreite(SEITE_STANDARD)}
        />
      )}
      {zeigeVolltextSeite && volltext && (
        <VolltextAnsicht volltext={volltext} rn={volltextRn} onSchliessen={() => setVolltext(null)} />
      )}
      {zeigeBelegSeite && auswahl && (
        <aside className="akte-seite">
          <p className="fundort">Zitiert in {auswahl.ort}</p>
          {auswahl.beleg ? <BelegAnsicht beleg={auswahl.beleg} /> : <p className="status">Lade Wortlaut …</p>}
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
        {reiter === "chat" && <Chat akteId={akteId} onEinstellungen={onEinstellungen} />}
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
                <h3>Partei und Tags</h3>
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
          <p className="leer">Noch keine Dokumente in dieser Akte. Füge PDF-, Word- oder Textdateien hinzu.</p>
        )}
        {dokumente.length > 0 && (
          <table className="dokumente kompakt">
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
                    <button className="link" onClick={() => oeffneDokument(d.id)}>
                      {d.dateiname}
                    </button>
                    <div className="herkunft">
                      {lesartText(d)}
                      {d.seiten != null && <> · {d.seiten} S.</>}
                      {d.randnummern > 0 && <> · {d.randnummern} Rn.</>}
                      {d.herkunft && <> · {d.herkunft}</>}
                      {d.fassung.nr > 1 && <> · Fassung {d.fassung.nr}</>}
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
                      </div>
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
            <DokModusLeiste dokument={inhalt.dokument} modus={dokModus} onModus={waehleDokModus} />
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
                {dokModus === "text" && (
                  <DokumentAnsicht inhalt={inhalt} auswahl={auswahl} onZitat={waehleZitat} markiert={markiert ?? undefined} />
                )}
                {dokModus === "original" && (
                  <OriginalAnsicht key={inhalt.dokument.id} dokument={inhalt.dokument} startSeite={auswahl?.zitat.seite ?? null} />
                )}
                {dokModus === "normen" && normen && (
                  <NormenAnsicht normen={normen} onFundstelle={oeffneDokument} leer="In diesem Dokument wurden keine Normzitate erkannt." />
                )}
                {dokModus === "rechtsprechung" &&
                  rechtsprechungAnsicht("In diesem Dokument wurden keine Rechtsprechungszitate erkannt.", inhalt.dokument.id)}
                {dokModus === "chat" && <Chat akteId={akteId} dokumentId={inhalt.dokument.id} onEinstellungen={onEinstellungen} />}
              </>,
            )}
          </>
        ) : (
          <p className="leer">{dokumente.length > 0 ? "Wähle links ein Dokument, um Text und Normzitate zu sehen." : ""}</p>
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

export function DokumentAnsicht({
  inhalt,
  auswahl = null,
  onZitat,
  markiert,
  begriffe = [],
}: {
  inhalt: DokumentInhalt;
  auswahl?: Auswahl | null;
  /** Ohne Handler werden Normzitate nur markiert, nicht anklickbar. */
  onZitat?: (z: NormZitat, a: Abschnitt) => void;
  /** Abschnitt, der hervorgehoben wird (Fundstelle aus dem Vergleich oder der Suche). */
  markiert?: number;
  /** Gesuchte Begriffe, die im Text gelb markiert werden. */
  begriffe?: string[];
}) {
  const d = inhalt.dokument;
  return (
    <article className="dokument">
      <h2>{d.dateiname}</h2>
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
                <span key={i}>
                  {markiereBegriffe(s.text, begriffe).map((m, j) => (m.treffer ? <mark key={j}>{m.text}</mark> : m.text))}
                </span>
              ),
            )}
          </p>
        </section>
      ))}
    </article>
  );
}

const DOK_MODI: { modus: DokModus; text: string }[] = [
  { modus: "text", text: "Text" },
  { modus: "original", text: "Original" },
  { modus: "normen", text: "Normen" },
  { modus: "rechtsprechung", text: "Rechtsprechung" },
  { modus: "chat", text: "Chat" },
];

function DokModusLeiste({
  dokument,
  modus,
  onModus,
}: {
  dokument: AktenDokument;
  modus: DokModus;
  onModus: (m: DokModus) => void;
}) {
  const pdf = dokument.format === "pdf";
  return (
    <div className="dok-modi" role="tablist" aria-label={`Darstellung von ${dokument.dateiname}`}>
      <span className="dok-modi-name">{dokument.dateiname}</span>
      {DOK_MODI.map((m) => (
        <button
          key={m.modus}
          role="tab"
          aria-selected={modus === m.modus}
          className={modus === m.modus ? "reiter-aktiv" : "zweitrangig"}
          disabled={m.modus === "original" && !pdf}
          title={m.modus === "original" && !pdf ? "Die Originalansicht gibt es nur für PDF-Dateien." : undefined}
          onClick={() => onModus(m.modus)}
        >
          {m.text}
        </button>
      ))}
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
}: {
  dokument: Pick<AktenDokument, "id" | "dateiname" | "seiten">;
  startSeite: number | null;
  /** Gesuchte Begriffe; ihre Fundstellen werden auf den Seiten gelb markiert. */
  begriffe?: string[];
  hinweis?: string;
}) {
  const seiten = dokument.seiten ?? 1;
  const rahmen = useRef<HTMLDivElement>(null);
  const [bilder, setBilder] = useState<Record<number, Seitenbild | string>>({});
  const angefragt = useRef(new Set<number>());

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

  return (
    <div className="original" ref={rahmen}>
      <p className="dokument-info">
        Originaldatei aus der Ablage der Akte, {seiten} {seiten === 1 ? "Seite" : "Seiten"}. {hinweis}
      </p>
      {Array.from({ length: seiten }, (_, i) => i + 1).map((s) => {
        const b = bilder[s];
        return (
          <figure key={s} id={`seite-${s}`} data-seite={s} className="original-seite">
            {typeof b === "object" ? (
              <div className="original-bild">
                <img src={b.bild} width={b.breite} height={b.hoehe} alt={`Seite ${s} von ${dokument.dateiname}`} />
                {b.markierungen.map((m, i) => (
                  <span
                    key={i}
                    className="markierung"
                    style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%`, width: `${m.b * 100}%`, height: `${m.h * 100}%` }}
                  />
                ))}
              </div>
            ) : typeof b === "string" ? (
              <p className="fehler">Seite {s} lässt sich nicht anzeigen: {b}</p>
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
