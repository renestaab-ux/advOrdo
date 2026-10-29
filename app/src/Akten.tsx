import { Dispatch, FormEvent, SetStateAction, useCallback, useEffect, useRef, useState } from "react";
import Akte, { AkteReiter, Rueckfrage } from "./Akte";
import AkteStammdaten from "./AkteStammdaten";
import Analyse from "./Analyse";
import AusDokument from "./AusDokument";
import Fristen from "./Fristen";
import Notizen from "./Notizen";
import Zeiten from "./Zeiten";
import Schriftstuecke from "./Schriftstuecke";
import type { EinstellungsReiter } from "./Einstellungen";
import Zeichen, { FristZeichen, SymbolName } from "./Symbole";
import Vergleich from "./Vergleich";
import VerfahrenKarte from "./Verfahren";
import { open } from "@tauri-apps/plugin-dialog";
import {
  Akte as AkteTyp,
  AktenOptionen,
  Loeschergebnis,
  RubrumVorschau,
  abstandText,
  aktenzeichenSchluessel,
  akteTitel,
  aktePasst,
  datumLang,
  bearbeitetText,
  betragAnzeige,
  istDesktop,
  kern,
  sortiert,
  zuletztGeoeffnet,
} from "./kern";
import { SortKopf, useSortierung } from "./Sortierung";
import { useKiAn } from "./kiSchalter";

/** Reiter einer geöffneten Akte; „stammdaten“ öffnet der Knopf im Kopf. */
export type Reiter =
  | AkteReiter
  | "beteiligte"
  | "fristen"
  | "notizen"
  | "zeiten"
  | "schriftstuecke"
  | "vergleich"
  | "analyse"
  | "stammdaten";

const REITER: { id: Reiter; titel: string; symbol: SymbolName }[] = [
  { id: "dokumente", titel: "Dokumente", symbol: "dokumente" },
  { id: "schriftstuecke", titel: "Schriftstücke", symbol: "schriftstueck" },
  { id: "beteiligte", titel: "Beteiligte", symbol: "beteiligte" },
  { id: "fristen", titel: "Fristen", symbol: "fristen" },
  { id: "notizen", titel: "Notizen", symbol: "notizen" },
  { id: "zeiten", titel: "Zeiten", symbol: "zeiten" },
  { id: "vergleich", titel: "Vergleich", symbol: "vergleich" },
  { id: "analyse", titel: "Analyse", symbol: "analyse" },
  { id: "normen", titel: "Normen", symbol: "gesetze" },
  { id: "rechtsprechung", titel: "Rechtsprechung", symbol: "rechtsprechung" },
  { id: "chat", titel: "Chat mit der Akte", symbol: "chat" },
];
/** Reiter, die zwingend ein Sprachmodell brauchen; ausgeblendet, wenn die KI ausgeschaltet ist. */
const KI_REITER: Reiter[] = ["analyse", "chat"];

/** Kleinschreibung ohne Akzente, damit „bruckner“ auch „Brückner“ findet. */
const bearbeitet = (a: AkteTyp) => a.geaendert_am ?? a.angelegt_am;

/**
 * Bereich „Akten“: ohne geöffnete Akte die Aktenübersicht (Ebene 1), sonst die Akte mit Kopf und Reitern (Ebene 2).
 */
export default function Akten({
  akteId,
  setAkteId,
  anlegen,
  onAnlegen,
  onEinstellungen,
  onEigeneDaten,
  reiterWunsch,
}: {
  akteId: number | null;
  setAkteId: Dispatch<SetStateAction<number | null>>;
  /** Mit welchem Reiter eine von außen geöffnete Akte startet (z. B. „fristen“ aus „Nächste Fristen“). */
  reiterWunsch?: { reiter: Reiter } | null;
  /** „Akte anlegen“ (Startseite oder „+ Neue Akte“): statt der Übersicht der Anlegeprozess. */
  anlegen: boolean;
  onAnlegen: (an: boolean) => void;
  /** Zu den Einstellungen, auf Wunsch gleich zu einem Thema (ohne Angabe: Sprachmodell). */
  onEinstellungen: (reiter?: EinstellungsReiter) => void;
  /** Zu Eigene Daten (z. B. Steuernummer und Bankverbindung für die Kostennote). */
  onEigeneDaten: () => void;
}) {
  const [akten, setAkten] = useState<AkteTyp[] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [reiter, setReiter] = useState<Reiter>("dokumente");
  useEffect(() => {
    if (reiterWunsch) setReiter(reiterWunsch.reiter);
  }, [reiterWunsch]);

  const laden = useCallback(async () => {
    try {
      setAkten(await kern<AkteTyp[]>("akten.liste"));
    } catch (e) {
      setFehler(String(e));
    }
  }, []);

  useEffect(() => {
    if (istDesktop) void laden();
  }, [laden]);

  // Geöffnet wird mit Zeitstempel für „Zuletzt geöffnet“; „bearbeitet“ bleibt davon unberührt.
  useEffect(() => {
    if (akteId == null || !istDesktop) return;
    void kern("akten.geoeffnet", { akte_id: akteId }).then(laden, () => undefined);
  }, [akteId, laden]);

  // Die Akte gibt es nicht mehr (z. B. gelöscht): zurück zur Übersicht.
  useEffect(() => {
    if (akteId != null && akten && !akten.some((a) => a.id === akteId)) setAkteId(null);
  }, [akteId, akten, setAkteId]);

  function oeffnen(id: number, start: Reiter = "dokumente") {
    setReiter(start);
    setAkteId(id);
  }

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Akten lassen sich nur in der Desktop-App lesen:{" "}
        <code>npm run tauri dev</code>
      </section>
    );
  }

  const akte = akteId != null ? akten?.find((a) => a.id === akteId) : undefined;
  if (akteId != null && akte) {
    return (
      <AkteRahmen
        akte={akte}
        reiter={reiter}
        onReiter={setReiter}
        onZurueck={() => setAkteId(null)}
        onGeaendert={() => void laden()}
        onEntfernt={() => {
          setAkteId(null);
          void laden();
        }}
        onEinstellungen={onEinstellungen}
        onEigeneDaten={onEigeneDaten}
      />
    );
  }

  if (anlegen) {
    return (
      <AkteAnlegen
        onAbbrechen={() => onAnlegen(false)}
        onAngelegt={async (id, start) => {
          await laden();
          onAnlegen(false);
          // Eine neue Akte braucht zuerst ihre Stammdaten, danach Mandant und Gegner (mit Kollisionsprüfung).
          // Aus einem Dokument sind beide schon ausgefüllt; dann gleich die Beteiligten mit der Kollisionsprüfung.
          oeffnen(id, start ?? "stammdaten");
        }}
      />
    );
  }

  return <AktenUebersicht akten={akten} fehler={fehler} onOeffnen={oeffnen} onNeu={() => onAnlegen(true)} />;
}

// --------------------------------------------------------------------------- Neue Akte anlegen

const SCHRITTE = [
  ["Kurzbezeichnung und Aktenzeichen", "Das Aktenzeichen schlägt JuraBox vor; ein eigenes geht auch."],
  ["Stammdaten", "Gegenstand, Sachgebiet, Sachbearbeiter, Gegenstandswert."],
  ["Beteiligte", "Mandant, Gegner, Gericht; die Kollisionsprüfung läuft dabei mit."],
] as const;

/** Erster Schritt einer neuen Akte als eigene Seite; danach geht es in der Akte mit Stammdaten und Beteiligten weiter. */
function AkteAnlegen({
  onAbbrechen,
  onAngelegt,
}: {
  onAbbrechen: () => void;
  onAngelegt: (id: number, reiter?: Reiter) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [ausDokument, setAusDokument] = useState<{ pfad: string; vorschau: RubrumVorschau } | null>(null);
  const [az, setAz] = useState("");
  const [azVorschlag, setAzVorschlag] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<{ aktenzeichen: string }>("akten.aktenzeichen_vorschlag").then((v) => setAzVorschlag(v.aktenzeichen), () => undefined);
  }, []);

  async function dokumentWaehlen() {
    const pfad = await open({
      title: "Dokument mit Rubrum wählen (Klage, Mahnbescheid, Verfügung …)",
      multiple: false,
      directory: false,
      filters: [{ name: "Dokumente", extensions: ["pdf", "docx", "txt", "md"] }],
    });
    if (typeof pfad !== "string") return;
    setLaeuft(true);
    setFehler(null);
    try {
      setAusDokument({ pfad, vorschau: await kern<RubrumVorschau>("akten.rubrum_lesen", { pfad }) });
    } catch (f) {
      setFehler(String(f));
    } finally {
      setLaeuft(false);
    }
  }

  async function abschicken(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLaeuft(true);
    setFehler(null);
    try {
      const a = await kern<AkteTyp>("akten.anlegen", { name: name.trim(), aktenzeichen: az.trim() || null });
      await onAngelegt(a.id);
    } catch (f) {
      setFehler(String(f));
      setLaeuft(false);
    }
  }

  return (
    <div className="akte-rahmen">
      <header className="kopfband akte-kopf">
        <button className="zurueck" onClick={onAbbrechen} title="Zur Aktenübersicht, ohne anzulegen">
          <Zeichen name="zurueck" groesse={16} /> Akten
        </button>
        <div className="akte-kopf-titel">
          <p className="kopfband-ueber">{ausDokument ? "Aus Dokument" : "Schritt 1 von 3"}</p>
          <h1>Neue Akte anlegen</h1>
        </div>
      </header>
      {ausDokument ? (
        <div className="akte-anlegen einspaltig">
          <AusDokument
            pfad={ausDokument.pfad}
            vorschau={ausDokument.vorschau}
            onAbbrechen={() => setAusDokument(null)}
            onAngelegt={(id) => onAngelegt(id, "beteiligte")}
          />
        </div>
      ) : (
      <div className="akte-anlegen">
        <form className="karte akte-anlegen-form" onSubmit={abschicken}>
          <label className="feld">
            Kurzbezeichnung
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Brückner ./. Autohaus Rehnfeld"
            />
          </label>
          <label className="feld">
            Aktenzeichen
            <input
              value={az}
              onChange={(e) => setAz(e.target.value)}
              placeholder={azVorschlag ? `${azVorschlag} (Vorschlag)` : "Nummer/Jahr"}
              title="Leer lassen für das vorgeschlagene Aktenzeichen"
            />
            <small className="leise">
              {azVorschlag ? `Leer lassen für den Vorschlag ${azVorschlag}.` : "Leer lassen für den Vorschlag."}
            </small>
          </label>
          <span className="aktionen">
            <button type="submit" disabled={laeuft || !name.trim()}>
              Anlegen und weiter zu den Stammdaten
            </button>
            <button type="button" className="zweitrangig" onClick={onAbbrechen}>
              Abbrechen
            </button>
          </span>
          {fehler && <p className="fehler">{fehler}</p>}
        </form>
        <div className="anlegen-seite">
          <ol className="anlegen-schritte">
            {SCHRITTE.map(([titel, text], i) => (
              <li key={titel} className={i === 0 ? "aktiv" : undefined}>
                <strong>{titel}</strong>
                <span className="leise">{text}</span>
              </li>
            ))}
          </ol>
          <div className="karte aus-dokument-start">
            <strong>Oder aus einem Dokument</strong>
            <p className="leise">
              Klage, Anspruchsbegründung, Mahnbescheid oder Verfügung wählen: JuraBox liest Gericht, Aktenzeichen,
              Parteien und Gegenstand aus dem Rubrum und zeigt alles mit Fundstelle zur Prüfung.
            </p>
            <button className="zweitrangig" onClick={dokumentWaehlen} disabled={laeuft}>
              <Zeichen name="dokumentLesen" groesse={16} /> Dokument wählen …
            </button>
          </div>
        </div>
      </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- Ebene 1: Aktenübersicht

function AktenUebersicht({
  akten,
  fehler,
  onOeffnen,
  onNeu,
}: {
  akten: AkteTyp[] | null;
  fehler: string | null;
  onOeffnen: (id: number, reiter?: Reiter) => void;
  onNeu: () => void;
}) {
  const [optionen, setOptionen] = useState<AktenOptionen | null>(null);
  const [suche, setSuche] = useState("");
  const [status, setStatus] = useState<string | null>("laufend");
  const [sachgebiet, setSachgebiet] = useState("");
  const [sachbearbeiter, setSachbearbeiter] = useState("");
  const [bald, setBald] = useState(false);
  const [gericht, setGericht] = useState("");
  const [sortierung, sortieren] = useSortierung("akten.sortierung", { spalte: "bearbeitet", absteigend: true });

  useEffect(() => {
    void kern<AktenOptionen>("akten.optionen").then(setOptionen, () => setOptionen(null));
  }, []);

  const alle = akten ?? [];
  // Status zählt innerhalb der übrigen Filter, damit die Zahlen zu dem passen, was ein Klick zeigt.
  const vorStatus = alle.filter(
    (a) =>
      (!sachgebiet || a.sachgebiet === sachgebiet) &&
      (!sachbearbeiter || String(a.sachbearbeiter_id ?? "") === sachbearbeiter) &&
      (!bald || fristBald(a)) &&
      (!gericht || a.gerichte.some((g) => g.name === gericht)) &&
      aktePasst(a, suche),
  );
  const statusRang = Object.keys(optionen?.status ?? {});
  const sichtbar = sortiert(
    vorStatus.filter((a) => status == null || a.status === status),
    sortierung,
    {
      az: (a) => aktenzeichenSchluessel(a.aktenzeichen),
      name: (a) => a.name,
      mandant: (a) => a.mandanten.join(", "),
      gegner: (a) => a.gegner.join(", "),
      gegenstand: (a) => a.gegenstand,
      gericht: (a) => a.gerichte[0]?.name,
      frist: (a) => a.naechste?.datum,
      status: (a) => statusRang.indexOf(a.status),
      bearbeitet: (a) => bearbeitet(a),
    },
  );
  const zaehlung = (s: string) => vorStatus.filter((a) => a.status === s).length;
  const baldAnzahl = alle.filter(fristBald).length;
  const zuletzt = zuletztGeoeffnet(alle, 4);
  const sachgebiete = [...new Set(alle.map((a) => a.sachgebiet).filter((s): s is string => !!s))].sort();
  const gerichte = [...new Set(alle.flatMap((a) => a.gerichte.map((g) => g.name)).filter(Boolean))].sort((x, y) =>
    x.localeCompare(y, "de"),
  );

  return (
    <div className="akten-uebersicht">
      <header className="kopf">
        <h1>Akten</h1>
        <span className="aktionen">
          <button onClick={onNeu}>
            + Neue Akte
          </button>
        </span>
      </header>


      <input
        type="search"
        className="akten-suche"
        value={suche}
        onChange={(e) => setSuche(e.target.value)}
        placeholder="Suchen nach Aktenzeichen, Mandant, Gegner, Gegenstand, Gericht, gerichtl. Az. …"
        aria-label="Akten durchsuchen"
      />

      <div className="filterleiste" role="group" aria-label="Filter">
        {optionen &&
          Object.entries(optionen.status).map(([k, t]) => (
            <button
              key={k}
              className={status === k ? "chip aktiv" : "chip"}
              aria-pressed={status === k}
              onClick={() => setStatus(status === k ? null : k)}
            >
              {t[0].toLocaleUpperCase("de") + t.slice(1)} ({zaehlung(k)})
            </button>
          ))}
        <button className={status == null ? "chip aktiv" : "chip"} aria-pressed={status == null} onClick={() => setStatus(null)}>
          Alle ({vorStatus.length})
        </button>
        <button
          className={bald ? "chip aktiv frist-chip" : "chip frist-chip"}
          aria-pressed={bald}
          onClick={() => setBald(!bald)}
          title="Akten mit einer offenen Frist, einem Termin oder einer Wiedervorlage in den nächsten 7 Tagen (auch abgelaufene)"
        >
          Frist in 7 Tagen ({baldAnzahl})
        </button>
        <select value={sachgebiet} onChange={(e) => setSachgebiet(e.target.value)} aria-label="Sachgebiet">
          <option value="">Sachgebiet: alle</option>
          {sachgebiete.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        {optionen && optionen.sachbearbeiter.length > 0 && (
          <select value={sachbearbeiter} onChange={(e) => setSachbearbeiter(e.target.value)} aria-label="Sachbearbeiter">
            <option value="">Sachbearbeiter: alle</option>
            {optionen.sachbearbeiter.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        {gerichte.length > 0 && (
          <select value={gericht} onChange={(e) => setGericht(e.target.value)} aria-label="Gericht">
            <option value="">Gericht: alle</option>
            {gerichte.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        )}
      </div>

      {zuletzt.length > 0 && !suche.trim() && (
        <section aria-label="Zuletzt geöffnet">
          <h2 className="abschnitt-titel">Zuletzt geöffnet</h2>
          <div className="zuletzt">
            {zuletzt.map((a) => (
              <button key={a.id} className="zuletzt-karte" onClick={() => onOeffnen(a.id)}>
                <strong>{akteTitel(a)}</strong>
                <span className="leise">
                  {[a.gerichte[0] && `${a.gerichte[0].name} ${a.gerichte[0].aktenzeichen}`.trim(), bearbeitetText(a.geoeffnet_am)]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {fehler && <p className="fehler">{fehler}</p>}
      {akten == null && !fehler && <p className="status">Lade Akten …</p>}

      {sichtbar.length > 0 && (
        <table className="dokumente akten-tabelle">
          <thead>
            <tr>
              {(
                [
                  ["az", "Az."],
                  ["name", "Kurzbezeichnung"],
                  ["mandant", "Mandant"],
                  ["gegner", "Gegner"],
                  ["gegenstand", "Gegenstand"],
                  ["gericht", "Gericht · Az."],
                  ["frist", "Nächste Frist"],
                  ["status", "Status"],
                  ["bearbeitet", "Bearbeitet"],
                ] as const
              ).map(([k, t]) => (
                <SortKopf key={k} spalte={k} titel={t} sortierung={sortierung} onSortieren={sortieren} />
              ))}
            </tr>
          </thead>
          <tbody>
            {sichtbar.map((a) => (
              <tr key={a.id} onClick={() => onOeffnen(a.id)} className="klickbar">
                <td className="az">{a.aktenzeichen ?? "–"}</td>
                <td>
                  <button className="link" onClick={() => onOeffnen(a.id)}>
                    {a.name}
                  </button>
                  {!a.aktenzeichen && (
                    <button
                      className="marke-fehlt"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOeffnen(a.id, "stammdaten");
                      }}
                      title="Stammdaten öffnen und ein Aktenzeichen vergeben"
                    >
                      Aktenzeichen fehlt
                    </button>
                  )}
                </td>
                <td>{namen(a.mandanten)}</td>
                <td>{namen(a.gegner)}</td>
                <td>{a.gegenstand || "–"}</td>
                <td>
                  {a.gerichte.length > 0 ? (
                    a.gerichte.map((g) => (
                      <div key={g.name + g.aktenzeichen}>
                        {g.name}
                        {g.aktenzeichen && <div className="leise">{g.aktenzeichen}</div>}
                      </div>
                    ))
                  ) : (
                    <span className="leise">–</span>
                  )}
                </td>
                <td>
                  {a.naechste ? (
                    <button
                      className={`naechste-frist ${a.naechste.lage}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onOeffnen(a.id, "fristen");
                      }}
                      title={`${a.naechste.art_text}: ${a.naechste.titel}`}
                    >
                      <span className="frist-datum">
                        <FristZeichen lage={a.naechste.lage} />
                        {datumLang(a.naechste.datum)}
                      </span>
                      <span className="leise">
                        {a.naechste.titel} · {abstandText({ ...a.naechste, erledigt_am: null })}
                      </span>
                    </button>
                  ) : (
                    <span className="leise">–</span>
                  )}
                </td>
                <td>
                  <span className={`status-marke ${a.status}`}>{optionen?.status[a.status] ?? a.status}</span>
                </td>
                <td className="leise">{bearbeitetText(bearbeitet(a))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {akten != null && sichtbar.length === 0 && (
        <p className="leer">
          {alle.length === 0
            ? "Noch keine Akte. Lege mit „+ Neue Akte“ die erste an."
            : "Keine Akte passt zu Suche und Filtern."}
        </p>
      )}
    </div>
  );
}

/** Offene Frist, Termin oder Wiedervorlage in den nächsten 7 Tagen oder schon abgelaufen. */
const fristBald = (a: AkteTyp) => !!a.naechste && a.naechste.in_tagen <= 7;

/** Mehrere Mandanten oder Gegner: der erste und „u. a.“, alle im Tooltip. */
function namen(liste: string[]) {
  if (liste.length === 0) return <span className="leise">–</span>;
  return <span title={liste.join("\n")}>{liste.length > 1 ? `${liste[0]} u. a.` : liste[0]}</span>;
}

// --------------------------------------------------------------------------- Ebene 2: geöffnete Akte

function AkteRahmen({
  akte,
  reiter,
  onReiter,
  onZurueck,
  onGeaendert,
  onEntfernt,
  onEinstellungen,
  onEigeneDaten,
}: {
  akte: AkteTyp;
  reiter: Reiter;
  onReiter: (r: Reiter) => void;
  onZurueck: () => void;
  onGeaendert: () => void;
  onEntfernt: () => void;
  /** Zu den Einstellungen, auf Wunsch gleich zu einem Thema (ohne Angabe: Sprachmodell). */
  onEinstellungen: (reiter?: EinstellungsReiter) => void;
  onEigeneDaten: () => void;
}) {
  const [loeschfrage, setLoeschfrage] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const kiAn = useKiAn();
  const gericht = akte.gerichte[0];
  // Dokumente, Normen, Rechtsprechung und Chat teilen sich eine Ansicht, die beim Wechsel zu Vergleich oder Analyse
  // erhalten bleibt (geöffnetes Dokument, Filter).
  const istAkteReiter = (r: Reiter): r is AkteReiter =>
    r === "dokumente" || r === "normen" || r === "rechtsprechung" || r === "chat";
  const letzter = useRef<AkteReiter>("dokumente");
  if (istAkteReiter(reiter)) letzter.current = reiter;

  async function entfernen() {
    setLoeschfrage(false);
    try {
      await kern<Loeschergebnis>("akten.loeschen", { akte_id: akte.id });
      onEntfernt();
    } catch (e) {
      setFehler(String(e));
    }
  }

  return (
    <div className="akte-rahmen">
      <header className="kopfband akte-kopf">
        <button className="zurueck" onClick={onZurueck} title="Zur Aktenübersicht">
          <Zeichen name="zurueck" groesse={16} /> Akten
        </button>
        <div className="akte-kopf-titel">
          <p className="kopfband-ueber" title={akte.gegenstand ?? undefined}>
            {akte.aktenzeichen ? `Akte ${akte.aktenzeichen}` : "Akte ohne Aktenzeichen"}
            {akte.gegenstand && ` · ${akte.gegenstand}`}
            {akte.gegenstandswert && ` · Wert ${betragAnzeige(akte.gegenstandswert)} €`}
          </p>
          <h1>{akte.name}</h1>
        </div>
        {akte.mandanten.length > 0 && (
          <div className="akte-kopf-angabe">
            <p className="kopfband-ueber">Wir vertreten</p>
            <strong title={akte.eigene_rolle ?? undefined}>{akte.mandanten.join(", ")}</strong>
          </div>
        )}
        {akte.verfahren ? (
          <div className="akte-kopf-angabe">
            <p className="kopfband-ueber">Verfahren</p>
            <strong title={akte.verfahren}>{akte.verfahren}</strong>
          </div>
        ) : (
          gericht && (
            <div className="akte-kopf-angabe">
              <p className="kopfband-ueber">Gericht</p>
              <strong>
                {gericht.name}
                {gericht.aktenzeichen && ` · ${gericht.aktenzeichen}`}
              </strong>
            </div>
          )
        )}
        {akte.naechste && (
          <button
            className={`akte-kopf-angabe kopf-frist ${akte.naechste.lage}`}
            onClick={() => onReiter("fristen")}
            title="Zu den Fristen"
          >
            <p className="kopfband-ueber">Nächste {akte.naechste.art_text}</p>
            <strong title={`${akte.naechste.titel}: ${abstandText({ ...akte.naechste, erledigt_am: null })}`}>
              <FristZeichen lage={akte.naechste.lage} />
              {datumLang(akte.naechste.datum)}
              {akte.naechste.in_tagen < 0 ? " · abgelaufen" : akte.naechste.in_tagen <= 7 ? ` · ${abstandText({ ...akte.naechste, erledigt_am: null })}` : ""}
            </strong>
          </button>
        )}
        <button
          className={reiter === "stammdaten" ? "kopf-knopf aktiv" : "kopf-knopf"}
          onClick={() => onReiter(reiter === "stammdaten" ? "dokumente" : "stammdaten")}
          aria-pressed={reiter === "stammdaten"}
          title="Aktenzeichen, Gegenstand, Sachgebiet, Status"
        >
          <Zeichen name="stammdaten" groesse={16} /> Stammdaten
          {!akte.aktenzeichen && <span className="fehlt-punkt" title="Aktenzeichen fehlt" />}
        </button>
      </header>

      <nav className="akte-reiter" role="tablist" aria-label="Bereiche der Akte">
        {REITER.filter((r) => kiAn || !KI_REITER.includes(r.id)).map((r) => (
          <button
            key={r.id}
            role="tab"
            aria-selected={reiter === r.id}
            className={reiter === r.id ? "akte-reiter-knopf aktiv" : "akte-reiter-knopf"}
            onClick={() => onReiter(r.id)}
          >
            <Zeichen name={r.symbol} groesse={16} />
            {r.titel}
            {r.id === "dokumente" && <span className="anzahl">{akte.dokumente}</span>}
            {r.id === "fristen" && akte.naechste && akte.naechste.in_tagen <= 7 && (
              <span className={`anzahl frist ${akte.naechste.lage}`} title="Frist, Termin oder Wiedervorlage in den nächsten 7 Tagen">
                !
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="akte-reiterflaeche">
        {fehler && <p className="fehler">{fehler}</p>}
        {loeschfrage && (
          <Rueckfrage
            frage={`Akte „${akte.name}“ mit ${akte.dokumente} Dokumenten entfernen?`}
            erklaerung={
              "Entfernt werden die gelesenen Texte, Normzitate, Tags und die Kopien, die die App beim Einlesen abgelegt hat. " +
              "Deine Originaldateien am ursprünglichen Ort bleiben unverändert. Das Aktenzeichen bleibt vergeben."
            }
            ja="Entfernen"
            onJa={entfernen}
            onNein={() => setLoeschfrage(false)}
          />
        )}
        {reiter === "stammdaten" && (
          <AkteStammdaten
            key={`s${akte.id}`}
            akteId={akte.id}
            teil="stammdaten"
            onGeaendert={onGeaendert}
            onWeiter={() => onReiter("beteiligte")}
            onEntfernen={() => setLoeschfrage(true)}
          />
        )}
        {reiter === "stammdaten" && <VerfahrenKarte key={`v${akte.id}`} akteId={akte.id} onGeaendert={onGeaendert} />}
        {reiter === "fristen" && <Fristen key={`f${akte.id}`} akteId={akte.id} onGeaendert={onGeaendert} />}
        {reiter === "notizen" && <Notizen key={`n${akte.id}`} akteId={akte.id} />}
        {reiter === "zeiten" && (
          <Zeiten
            key={`z${akte.id}`}
            akteId={akte.id}
            onEinstellungen={() => onEinstellungen("zeiterfassung")}
            onKostennote={() => onReiter("schriftstuecke")}
          />
        )}
        {reiter === "schriftstuecke" && (
          <Schriftstuecke
            key={`sch${akte.id}`}
            akteId={akte.id}
            onGeaendert={onGeaendert}
            onDokumente={() => onReiter("dokumente")}
            onVorlagen={() => onEinstellungen("schriftstuecke")}
            onEigeneDaten={onEigeneDaten}
          />
        )}
        {reiter === "beteiligte" && (
          <AkteStammdaten key={`b${akte.id}`} akteId={akte.id} teil="beteiligte" onGeaendert={onGeaendert} />
        )}
        {reiter === "vergleich" && <Vergleich key={akte.id} akteId={akte.id} />}
        {kiAn && reiter === "analyse" && <Analyse key={akte.id} akteId={akte.id} onEinstellungen={() => onEinstellungen()} />}
        <div hidden={!istAkteReiter(reiter)} className="akte-reiter-halter">
          <Akte
            key={akte.id}
            akte={akte}
            reiter={letzter.current}
            onReiter={onReiter}
            onGeaendert={onGeaendert}
            onBeteiligte={() => onReiter("beteiligte")}
            onEinstellungen={() => onEinstellungen()}
          />
        </div>
      </div>
    </div>
  );
}
