import { Dispatch, FormEvent, SetStateAction, useCallback, useEffect, useRef, useState } from "react";
import Akte, { AkteReiter, Rueckfrage } from "./Akte";
import AkteStammdaten from "./AkteStammdaten";
import Analyse from "./Analyse";
import Zeichen, { SymbolName } from "./Symbole";
import Vergleich from "./Vergleich";
import {
  Akte as AkteTyp,
  AktenOptionen,
  Loeschergebnis,
  akteTitel,
  bearbeitetText,
  istDesktop,
  kern,
  zuletztGeoeffnet,
} from "./kern";

/** Reiter einer geöffneten Akte; „stammdaten“ öffnet der Knopf im Kopf. Notizen und Fristen folgen in Stufe 2. */
type Reiter = AkteReiter | "beteiligte" | "vergleich" | "analyse" | "stammdaten";

const REITER: { id: Reiter; titel: string; symbol: SymbolName }[] = [
  { id: "dokumente", titel: "Dokumente", symbol: "dokumente" },
  { id: "beteiligte", titel: "Beteiligte", symbol: "beteiligte" },
  { id: "vergleich", titel: "Vergleich", symbol: "vergleich" },
  { id: "analyse", titel: "Analyse", symbol: "analyse" },
  { id: "normen", titel: "Normen", symbol: "gesetze" },
  { id: "rechtsprechung", titel: "Rechtsprechung", symbol: "rechtsprechung" },
  { id: "chat", titel: "Chat mit der Akte", symbol: "chat" },
];

/** Kleinschreibung ohne Akzente, damit „bruckner“ auch „Brückner“ findet. */
function einfach(text: string): string {
  return text.toLocaleLowerCase("de").normalize("NFD").replace(/[̀-ͯ]/g, "");
}

/** Alles, wonach die Aktenübersicht sucht: Aktenzeichen, Kurzbezeichnung, Parteien, Gegenstand, Gericht und gerichtl. Az. */
function suchtext(a: AkteTyp): string {
  return einfach(
    [a.aktenzeichen, a.name, a.gegenstand, ...a.mandanten, ...a.gegner, ...a.gerichte.flatMap((g) => [g.name, g.aktenzeichen])]
      .filter(Boolean)
      .join(" "),
  );
}

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
}: {
  akteId: number | null;
  setAkteId: Dispatch<SetStateAction<number | null>>;
  /** „Akte anlegen“ (Startseite oder „+ Neue Akte“): statt der Übersicht der Anlegeprozess. */
  anlegen: boolean;
  onAnlegen: (an: boolean) => void;
  onEinstellungen: () => void;
}) {
  const [akten, setAkten] = useState<AkteTyp[] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [reiter, setReiter] = useState<Reiter>("dokumente");

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
      />
    );
  }

  if (anlegen) {
    return (
      <AkteAnlegen
        onAbbrechen={() => onAnlegen(false)}
        onAngelegt={async (id) => {
          await laden();
          onAnlegen(false);
          // Eine neue Akte braucht zuerst ihre Stammdaten, danach Mandant und Gegner (mit Kollisionsprüfung).
          oeffnen(id, "stammdaten");
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
function AkteAnlegen({ onAbbrechen, onAngelegt }: { onAbbrechen: () => void; onAngelegt: (id: number) => Promise<void> }) {
  const [name, setName] = useState("");
  const [az, setAz] = useState("");
  const [azVorschlag, setAzVorschlag] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<{ aktenzeichen: string }>("akten.aktenzeichen_vorschlag").then((v) => setAzVorschlag(v.aktenzeichen), () => undefined);
  }, []);

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
          <p className="kopfband-ueber">Schritt 1 von 3</p>
          <h1>Neue Akte anlegen</h1>
        </div>
      </header>
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
        <ol className="anlegen-schritte">
          {SCHRITTE.map(([titel, text], i) => (
            <li key={titel} className={i === 0 ? "aktiv" : undefined}>
              <strong>{titel}</strong>
              <span className="leise">{text}</span>
            </li>
          ))}
        </ol>
      </div>
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

  useEffect(() => {
    void kern<AktenOptionen>("akten.optionen").then(setOptionen, () => setOptionen(null));
  }, []);

  const alle = akten ?? [];
  const begriffe = einfach(suche).split(/\s+/).filter(Boolean);
  // Status zählt innerhalb der übrigen Filter, damit die Zahlen zu dem passen, was ein Klick zeigt.
  const vorStatus = alle.filter(
    (a) =>
      (!sachgebiet || a.sachgebiet === sachgebiet) &&
      (!sachbearbeiter || String(a.sachbearbeiter_id ?? "") === sachbearbeiter) &&
      begriffe.every((b) => suchtext(a).includes(b)),
  );
  const sichtbar = vorStatus
    .filter((a) => status == null || a.status === status)
    .sort((a, b) => bearbeitet(b).localeCompare(bearbeitet(a)));
  const zaehlung = (s: string) => vorStatus.filter((a) => a.status === s).length;
  const zuletzt = zuletztGeoeffnet(alle, 4);
  const sachgebiete = [...new Set(alle.map((a) => a.sachgebiet).filter((s): s is string => !!s))].sort();

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
        <span className="leise rechts">Sortiert nach: zuletzt bearbeitet</span>
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
              <th>Az.</th>
              <th>Kurzbezeichnung</th>
              <th>Mandant</th>
              <th>Gegner</th>
              <th>Gegenstand</th>
              <th>Gericht · Az.</th>
              <th>Status</th>
              <th>Bearbeitet</th>
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
}: {
  akte: AkteTyp;
  reiter: Reiter;
  onReiter: (r: Reiter) => void;
  onZurueck: () => void;
  onGeaendert: () => void;
  onEntfernt: () => void;
  onEinstellungen: () => void;
}) {
  const [loeschfrage, setLoeschfrage] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
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
          <p className="kopfband-ueber">
            {akte.aktenzeichen ? `Akte ${akte.aktenzeichen}` : "Akte ohne Aktenzeichen"}
            {akte.gegenstand && ` · ${akte.gegenstand}`}
          </p>
          <h1>{akte.name}</h1>
        </div>
        {gericht && (
          <div className="akte-kopf-angabe">
            <p className="kopfband-ueber">Gericht</p>
            <strong>
              {gericht.name}
              {gericht.aktenzeichen && ` · ${gericht.aktenzeichen}`}
            </strong>
          </div>
        )}
        {akte.mandanten.length > 0 && (
          <div className="akte-kopf-angabe">
            <p className="kopfband-ueber">Wir vertreten</p>
            <strong title={akte.eigene_rolle ?? undefined}>{akte.mandanten.join(", ")}</strong>
          </div>
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
        {REITER.map((r) => (
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
        {reiter === "beteiligte" && (
          <AkteStammdaten key={`b${akte.id}`} akteId={akte.id} teil="beteiligte" onGeaendert={onGeaendert} />
        )}
        {reiter === "vergleich" && <Vergleich key={akte.id} akteId={akte.id} />}
        {reiter === "analyse" && <Analyse key={akte.id} akteId={akte.id} onEinstellungen={onEinstellungen} />}
        <div hidden={!istAkteReiter(reiter)} className="akte-reiter-halter">
          <Akte
            key={akte.id}
            akte={akte}
            reiter={letzter.current}
            onReiter={onReiter}
            onGeaendert={onGeaendert}
            onBeteiligte={() => onReiter("beteiligte")}
            onEinstellungen={onEinstellungen}
          />
        </div>
      </div>
    </div>
  );
}
