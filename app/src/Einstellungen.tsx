import ZeitSaetze from "./ZeitSaetze";
import { FormEvent, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import AktenEinstellungen from "./AktenEinstellungen";
import { BedeutungenKarte } from "./Anmerkungen";
import Diagnose from "./Diagnose";
import Nachrichten from "./Nachrichten";
import Gerichtsverzeichnis, { GerichtssucheKarte } from "./Gerichtsverzeichnis";
import Programme from "./Programme";
import Rechtsquellen from "./Rechtsquellen";
import SchriftVorlagenEinstellungen from "./SchriftVorlagen";
import Umgebungen from "./Umgebungen";
import {
  AKZENTE,
  Darstellung,
  HILFEN,
  SCHRIFTGROESSEN,
  THEMEN,
  darstellungLesen,
  darstellungSpeichern,
  istDunkel,
  modusAn,
  modusSetzen,
  systemWillKontrast,
} from "./darstellung";
import { KiStatus, Marke, UmgebungsListe, groesseText, istDesktop, kern } from "./kern";

const KONTEXTE = [8192, 16384, 32768];
const KONTEXTE_EXTERN = [32768, 131072];

export type EinstellungsReiter =
  | "allgemeines"
  | "umgebungen"
  | "eigene"
  | "akten"
  | "schriftstuecke"
  | "zeiterfassung"
  | "rechtsquellen"
  | "nachrichten"
  | "ki"
  | "extern"
  | "programme"
  | "diagnose";

// Ein Reiter je Thema; „Diagnose“ steht immer zuletzt.
const REITER: { id: EinstellungsReiter; titel: string }[] = [
  { id: "allgemeines", titel: "Allgemeines" },
  { id: "umgebungen", titel: "Arbeitsumgebungen" },
  { id: "eigene", titel: "Eigene Daten" },
  { id: "akten", titel: "Akten" },
  { id: "schriftstuecke", titel: "Schriftstücke" },
  { id: "zeiterfassung", titel: "Zeiterfassung" },
  { id: "rechtsquellen", titel: "Rechtsquellen" },
  { id: "nachrichten", titel: "Nachrichten" },
  { id: "ki", titel: "Lokales Sprachmodell" },
  { id: "extern", titel: "Externe KI" },
  { id: "programme", titel: "Programme" },
  { id: "diagnose", titel: "Diagnose" },
];

/**
 * Einstellungen: links ein Reiter je Thema, rechts nur das gewählte Thema. Darunter u. a. welches Sprachmodell
 * Analyse und Chat verwenden; lokal, oder ausnahmsweise ein externer Anbieter.
 */
export default function Einstellungen({
  reiter,
  onReiter,
  marke,
  onMarke,
  onGeaendert,
  umgebungen,
  onUmgebungen,
  onEigeneDaten,
  onAkten,
}: {
  reiter: EinstellungsReiter;
  onReiter: (r: EinstellungsReiter) => void;
  marke: Marke | null;
  onMarke: (m: Marke) => void;
  onGeaendert?: () => void;
  umgebungen: UmgebungsListe | null;
  onUmgebungen: (liste: UmgebungsListe, gewechselt: boolean) => void;
  onEigeneDaten: () => void;
  onAkten: () => void;
}) {
  const [status, setStatus] = useState<KiStatus | null>(null);
  const [anbieter, setAnbieter] = useState("ollama");
  const [endpunkt, setEndpunkt] = useState("");
  const [modell, setModell] = useState("");
  const [kontext, setKontext] = useState(16384);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  function uebernehme(g: KiStatus) {
    const s = g.lokal;
    setStatus(g);
    setAnbieter(s.anbieter);
    setEndpunkt(s.endpunkt);
    setModell(s.modell || (s.modelle.some((m) => m.name === s.empfohlen) ? s.empfohlen : (s.modelle[0]?.name ?? "")));
    setKontext(s.kontext);
  }

  async function pruefe() {
    setLaeuft(true);
    setFehler(null);
    try {
      uebernehme(await kern<KiStatus>("ki.status"));
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  useEffect(() => {
    if (istDesktop) void pruefe();
  }, []);

  // Schalter „KI verwenden“: aus heißt, die App fragt kein Sprachmodell; die Angaben darunter bleiben gespeichert.
  async function schalten(an: boolean) {
    setLaeuft(true);
    setFehler(null);
    try {
      await kern<KiStatus>("ki.schalten", { an });
      onGeaendert?.();
      // Eingeschaltet: das Modellprogramm wieder fragen, ob es bereit ist.
      uebernehme(await kern<KiStatus>("ki.status"));
    } catch (err) {
      setFehler(String(err));
    } finally {
      setLaeuft(false);
    }
  }

  async function speichern(e: FormEvent) {
    e.preventDefault();
    setLaeuft(true);
    setFehler(null);
    try {
      uebernehme(await kern<KiStatus>("ki.einstellungen_setzen", { anbieter, endpunkt, modell, kontext }));
      onGeaendert?.();
    } catch (err) {
      setFehler(String(err));
    } finally {
      setLaeuft(false);
    }
  }

  const lokal = status?.lokal ?? null;
  const installiert = lokal?.modelle ?? [];
  const gespeichert =
    lokal != null &&
    lokal.anbieter === anbieter &&
    lokal.endpunkt === endpunkt.trim().replace(/\/+$/, "") &&
    lokal.modell === modell &&
    lokal.kontext === kontext;

  const abgeschaltet = status?.abgeschaltet ?? false;
  const kiZeile = status && !abgeschaltet && (
    <p className={status.extern ? "ki-zeile extern" : status.bereit ? "ki-zeile bereit" : "ki-zeile"}>
      Analyse und Chat verwenden{" "}
      {status.extern
        ? `den externen Anbieter ${status.titel} (${status.modell || "kein Modell gewählt"}). Dokumenttexte verlassen dieses Gerät.`
        : `das Modell auf diesem Gerät (${status.modell || "kein Modell gewählt"}). Dokumentinhalte verlassen es nicht.`}
    </p>
  );

  let inhalt;
  if (reiter === "allgemeines") {
    inhalt = (
      <>
        <Allgemeines />
        <LogoKarte marke={marke} onMarke={onMarke} />
      </>
    );
  } else if (!istDesktop) {
    inhalt = (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Diese Einstellungen gibt es nur in der Desktop-App:{" "}
        <code>npm run tauri dev</code>
      </section>
    );
  } else if (reiter === "umgebungen") {
    inhalt = <Umgebungen liste={umgebungen} onGeaendert={onUmgebungen} />;
  } else if (reiter === "eigene") {
    inhalt = (
      <section className="karte">
        <div className="kopf">
          <h2>Eigene Daten</h2>
          <button className="zweitrangig" onClick={onEigeneDaten}>
            Öffnen
          </button>
        </div>
        <p className="erklaerung">
          Wer mit JuraBox arbeitet: Organisationsform, Kanzlei bzw. Unternehmen und Ihre Person. Die Angaben gehören zur
          aktiven Arbeitsumgebung.
        </p>
      </section>
    );
  } else if (reiter === "akten") {
    inhalt = (
      <>
        <AktenEinstellungen umgebungen={umgebungen} />
        <BedeutungenKarte key={umgebungen?.aktiv} />
        <Gerichtsverzeichnis />
        <GerichtssucheKarte />
      </>
    );
  } else if (reiter === "schriftstuecke") {
    inhalt = <SchriftVorlagenEinstellungen />;
  } else if (reiter === "zeiterfassung") {
    inhalt = <ZeitSaetze onEigeneDaten={onEigeneDaten} />;
  } else if (reiter === "rechtsquellen") {
    inhalt = <Rechtsquellen onAkte={onAkten} />;
  } else if (reiter === "nachrichten") {
    inhalt = <Nachrichten />;
  } else if (reiter === "ki") {
    const schalter = (
      <section className="karte">
        <h2>KI verwenden</h2>
        <label className="schalter ki-schalter">
          <input
            type="checkbox"
            checked={status != null && !abgeschaltet}
            disabled={status == null || laeuft}
            onChange={(e) => void schalten(e.target.checked)}
          />
          <span>KI einschalten</span>
          <span className="leise">{status == null ? "" : abgeschaltet ? "aus" : "eingeschaltet (Voreinstellung)"}</span>
        </label>
        <p className="erklaerung">
          {abgeschaltet
            ? "Die KI ist ausgeschaltet. JuraBox fragt kein Sprachmodell, weder auf diesem Gerät noch im Netzwerk oder bei einem externen Anbieter. Analyse, Chat und Gegenüberstellung sind ausgeblendet; Texterkennung, Normen, Rechtsprechung, Vergleich, Suche und die Vorschläge in „Details“ arbeiten ohne KI weiter. Die Einstellungen des Sprachmodells bleiben gespeichert."
            : "Ausgeschaltet fragt JuraBox kein Sprachmodell mehr, auch keinen externen Anbieter. Knöpfe und Reiter, die zwingend eine KI brauchen (Analyse, Chat, Gegenüberstellung), verschwinden dann; alles andere arbeitet ohne KI weiter."}
        </p>
      </section>
    );
    inhalt = abgeschaltet ? (
      <>
        {schalter}
        {fehler && <p className="fehler" role="alert">{fehler}</p>}
      </>
    ) : (
      <>
        {schalter}
        {kiZeile}
        <section className="karte">
          <h2>Lokales Sprachmodell</h2>
          <p className="erklaerung">
            Modus <strong>lokal</strong>: Das Sprachmodell (Ollama oder LM Studio) läuft auf diesem Gerät oder auf einem
            anderen Rechner im eigenen Netzwerk. Die App spricht nur mit solchen Adressen; Dokumentinhalte verlassen das
            eigene Netz nicht. Voreingestellt ist dieses Gerät (127.0.0.1).
          </p>

          <form className="ki-formular" onSubmit={speichern}>
            <label>
              Programm
              <select
                value={anbieter}
                onChange={(e) => {
                  setAnbieter(e.target.value);
                  const vorgabe = lokal?.anbieter_liste.find((a) => a.id === e.target.value);
                  if (vorgabe) setEndpunkt(vorgabe.endpunkt);
                }}
              >
                {(lokal?.anbieter_liste ?? [{ id: "ollama", titel: "Ollama", endpunkt: "" }]).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.titel}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Adresse
              <input value={endpunkt} onChange={(e) => setEndpunkt(e.target.value)} spellCheck={false} />
              <span className="leise feld-hinweis">
                Anderer Rechner im Netzwerk: dessen IP-Adresse oder Namen eintragen, z. B. http://192.168.178.20:1234
                oder http://pc-buero.local:11434.
              </span>
            </label>
            <label>
              Modell
              {installiert.length > 0 ? (
                <select value={modell} onChange={(e) => setModell(e.target.value)}>
                  {!installiert.some((m) => m.name === modell) && <option value={modell}>{modell || "(bitte wählen)"}</option>}
                  {installiert.map((m) => (
                    <option key={m.name} value={m.name}>
                      {m.name}
                      {m.parameter ? ` · ${m.parameter}` : ""}
                      {m.quantisierung ? ` · ${m.quantisierung}` : ""}
                      {m.groesse ? ` · ${groesseText(m.groesse)}` : ""}
                    </option>
                  ))}
                </select>
              ) : (
                <input value={modell} onChange={(e) => setModell(e.target.value)} placeholder={lokal?.empfohlen} spellCheck={false} />
              )}
            </label>
            <label>
              Kontext
              <select value={kontext} onChange={(e) => setKontext(Number(e.target.value))}>
                {KONTEXTE.map((k) => (
                  <option key={k} value={k}>
                    {k.toLocaleString("de-DE")} Token{k === 16384 ? " (empfohlen)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <div className="aktionen">
              <button type="submit" disabled={laeuft || gespeichert}>
                Speichern
              </button>
              <button type="button" className="zweitrangig" onClick={pruefe} disabled={laeuft}>
                Erneut prüfen
              </button>
            </div>
          </form>

          {laeuft && <p className="status" role="status">Prüfe …</p>}
          {fehler && <p className="fehler" role="alert">{fehler}</p>}
          {lokal && !laeuft && (
            <p className={lokal.bereit ? "ki-zeile bereit" : "ki-zeile"}>
              {lokal.bereit
                ? `Bereit: ${lokal.modell} über ${lokal.anbieter_titel}.`
                : lokal.erreichbar
                  ? lokal.hinweis
                  : `${lokal.anbieter_titel} ist nicht erreichbar. ${lokal.hinweis ?? ""}`}
            </p>
          )}

          <details className="ki-anleitung" open={lokal != null && !lokal.erreichbar && !status?.extern}>
            <summary>So richtest du Ollama unter Windows ein</summary>
            <ol>
              <li>
                In einer PowerShell: <code>winget install Ollama.Ollama</code> (oder den Installer von ollama.com). Ollama
                startet danach im Hintergrund, das Symbol erscheint unten rechts in der Taskleiste.
              </li>
              <li>
                Modell laden (einmalig, rund 9 GB): <code>ollama pull {lokal?.empfohlen ?? "qwen3:14b"}</code>. Es passt
                mit 16.384 Token Kontext in 16 GB Grafikspeicher.
              </li>
              <li>Hier „Erneut prüfen“, das Modell wählen und speichern.</li>
            </ol>
            <p className="leise">
              Ollama lauscht nur auf diesem Gerät (127.0.0.1:11434), solange man das nicht ausdrücklich ändert. Linux:{" "}
              <code>curl -fsSL https://ollama.com/install.sh | sh</code>, macOS: <code>brew install ollama</code>.
            </p>
            <p className="leise">
              Modell auf einem anderen Rechner im Netzwerk: Dort muss das Programm Verbindungen aus dem Netzwerk annehmen
              (LM Studio: Developer → Settings → „Serve on Local Network“; Ollama: Umgebungsvariable{" "}
              <code>OLLAMA_HOST=0.0.0.0</code>), und die Firewall dieses Rechners muss den Port (1234 bzw. 11434) für das
              private Netzwerk freigeben. Die Verbindung im Heimnetz ist unverschlüsselt; sie bleibt aber im eigenen Netz.
            </p>
          </details>
        </section>
      </>
    );
  } else if (reiter === "extern") {
    inhalt = abgeschaltet ? (
      <section className="hinweis-box">
        Die KI ist ausgeschaltet; es wird auch kein externer Anbieter gefragt. Einschalten unter{" "}
        <button className="link" onClick={() => onReiter("ki")}>
          Lokales Sprachmodell
        </button>
        .
      </section>
    ) : (
      <>
        {kiZeile}
        {status ? (
          <ExterneKi status={status} onStatus={setStatus} onGeaendert={onGeaendert} />
        ) : (
          <p className="status" role="status">{fehler ?? "Prüfe …"}</p>
        )}
      </>
    );
  } else if (reiter === "programme") {
    inhalt = <Programme />;
  } else {
    inhalt = <Diagnose />;
  }

  return (
    <div className="einstellungen">
      <header className="kopf">
        <h1>Einstellungen</h1>
      </header>
      <div className="einstellungen-raster">
        <nav className="einstellungen-reiter" role="tablist" aria-orientation="vertical" aria-label="Einstellungen">
          {REITER.map((r) => (
            <button
              key={r.id}
              role="tab"
              aria-selected={r.id === reiter}
              className={`nav-eintrag${r.id === reiter ? " aktiv" : ""}${r.id === "diagnose" ? " trenner-oben" : ""}`}
              onClick={() => onReiter(r.id)}
            >
              {r.titel}
            </button>
          ))}
        </nav>
        <div className="einstellungen-flaeche" role="tabpanel">
          {inhalt}
        </div>
      </div>
    </div>
  );
}

/** Allgemeines: Darstellung je Gerät, gilt sofort und auch für die Toolbox. */
function Allgemeines() {
  const [d, setD] = useState<Darstellung>(() => darstellungLesen());
  function setze(teil: Partial<Darstellung>) {
    const neu = { ...d, ...teil };
    setD(neu);
    darstellungSpeichern(neu);
  }
  const dunkel = istDunkel(d);

  return (
    <>
    <section className="karte">
      <h2>Darstellung</h2>
      <p className="erklaerung">Gilt für dieses Gerät, sofort und für alle Arbeitsumgebungen.</p>

      <div className="darstellung-gruppe">
        <h3>Hell oder dunkel</h3>
        <div className="segment darstellung-segment" role="group" aria-label="Hell oder dunkel">
          {THEMEN.map((t) => (
            <button
              key={t.id}
              className={d.thema === t.id ? "segment-knopf aktiv" : "segment-knopf"}
              aria-pressed={d.thema === t.id}
              onClick={() => setze({ thema: t.id })}
            >
              {t.titel}
            </button>
          ))}
        </div>
        <p className="leise">„Systemstandard“ folgt der Einstellung von Windows, macOS bzw. Linux.</p>
      </div>

      <div className="darstellung-gruppe">
        <h3>Farbakzent</h3>
        <div className="wahl-reihe" role="group" aria-label="Farbakzent">
          {AKZENTE.map((a) => (
            <button key={a.id} aria-pressed={d.akzent === a.id} onClick={() => setze({ akzent: a.id })}>
              <span className="farbmuster" style={{ background: dunkel ? a.dunkel : a.hell }} aria-hidden />
              {a.titel}
            </button>
          ))}
        </div>
      </div>

      <div className="darstellung-gruppe">
        <h3>Schriftgröße</h3>
        <div className="segment darstellung-segment" role="group" aria-label="Schriftgröße">
          {SCHRIFTGROESSEN.map((g) => (
            <button
              key={g.wert}
              className={d.schrift === g.wert ? "segment-knopf aktiv" : "segment-knopf"}
              aria-pressed={d.schrift === g.wert}
              onClick={() => setze({ schrift: g.wert })}
            >
              {g.titel}
            </button>
          ))}
        </div>
        <p className="leise">Vergrößert die ganze Oberfläche samt Leiste, Knöpfen und Dokumentansicht.</p>
      </div>

      <div className="darstellung-probe" aria-hidden>
        <span>
          So sieht das Kopfband einer Akte aus. <span className="leise">Az. 12 O 345/26</span>
        </span>
        <button tabIndex={-1}>Knopf</button>
      </div>
    </section>

    <section className="karte" aria-labelledby="barrierefreiheit">
      <h2 id="barrierefreiheit">Barrierefreiheit</h2>
      <p className="erklaerung">
        Der barrierefreie Modus schaltet alle Hilfen unten ein und stellt die Schrift mindestens auf „Sehr groß“. Jede Hilfe
        lässt sich auch einzeln an- oder abschalten. Gilt wie die Darstellung für dieses Gerät.
      </p>
      <label className="schalter barrierefrei-schalter">
        <input
          type="checkbox"
          checked={modusAn(d.barrierefrei)}
          onChange={(e) => {
            const neu = modusSetzen(d, e.target.checked);
            setD(neu);
            darstellungSpeichern(neu);
          }}
        />
        <span>Barrierefreier Modus</span>
        <span className="leise">{modusAn(d.barrierefrei) ? "an" : HILFEN.some((h) => d.barrierefrei[h.id]) ? "teilweise an" : "aus"}</span>
      </label>
      <ul className="hilfen-liste" aria-label="Einzelne Hilfen">
        {HILFEN.map((h) => (
          <li key={h.id}>
            <label>
              <input
                type="checkbox"
                checked={d.barrierefrei[h.id]}
                aria-describedby={`hilfe-${h.id}`}
                onChange={(e) => setze({ barrierefrei: { ...d.barrierefrei, [h.id]: e.target.checked } })}
              />
              <span>{h.titel}</span>
            </label>
            <p className="leise" id={`hilfe-${h.id}`}>
              {h.erklaerung}
            </p>
          </li>
        ))}
      </ul>
      <p className="leise">
        JuraBox folgt auch den Einstellungen des Systems: Unter Windows übernimmt es die Farben eines Kontrastdesigns
        (Einstellungen → Barrierefreiheit → Kontrastdesigns), unter macOS schaltet „Kontrast erhöhen“ den hohen Kontrast
        ein, und „Animationen aus“ bzw. „Bewegung reduzieren“ hält die Oberfläche ruhig.
        {systemWillKontrast() && " Das System verlangt gerade mehr Kontrast; der hohe Kontrast ist deshalb an."}
      </p>
    </section>
    </>
  );
}

/** Kanzlei- bzw. Firmenlogo und Kurzbezeichnung: oben in der Leiste klein, auf der Startseite groß mit dem Namen. */
function LogoKarte({ marke, onMarke }: { marke: Marke | null; onMarke: (m: Marke) => void }) {
  const [kurz, setKurz] = useState(marke?.kurzbezeichnung ?? "");
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  useEffect(() => setKurz(marke?.kurzbezeichnung ?? ""), [marke?.kurzbezeichnung]);

  async function setze(methode: string, params?: Record<string, unknown>) {
    setLaeuft(true);
    setFehler(null);
    try {
      onMarke(await kern<Marke>(methode, params));
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  async function waehlen() {
    const pfad = await open({
      title: "Logo wählen",
      multiple: false,
      filters: [{ name: "Bild (PNG, JPG, SVG, WebP)", extensions: ["png", "jpg", "jpeg", "svg", "webp"] }],
    });
    if (typeof pfad === "string") await setze("marke.logo_setzen", { pfad });
  }

  if (!istDesktop) {
    return (
      <section className="karte">
        <h2>Logo und Kurzbezeichnung</h2>
        <p className="leise">Nur in der Desktop-App.</p>
      </section>
    );
  }

  return (
    <section className="karte">
      <h2>Logo und Kurzbezeichnung</h2>
      <p className="erklaerung">
        Erscheinen oben in der Leiste (eingeklappt nur das Logo) und auf der Startseite groß mit dem Namen aus „Eigene
        Daten“. Beides gehört zur aktiven Arbeitsumgebung.
      </p>

      <div className="darstellung-gruppe">
        <h3>Kanzlei- oder Firmenlogo</h3>
        <div className="logo-zeile">
          <div className="logo-vorschau">{marke?.logo ? <img src={marke.logo} alt="Logo" /> : <span className="leise">kein Logo</span>}</div>
          <div className="aktionen">
            <button className="zweitrangig" onClick={() => void waehlen()} disabled={laeuft}>
              {marke?.logo ? "Anderes Logo wählen …" : "Logo wählen …"}
            </button>
            {marke?.logo && (
              <button className="zweitrangig gefahr" onClick={() => void setze("marke.logo_entfernen")} disabled={laeuft}>
                Entfernen
              </button>
            )}
          </div>
        </div>
        <p className="leise">PNG, JPG, SVG oder WebP bis 2 MB; am besten mit transparentem Hintergrund.</p>
      </div>

      <form
        className="darstellung-gruppe"
        onSubmit={(e) => {
          e.preventDefault();
          void setze("marke.kurz_setzen", { text: kurz });
        }}
      >
        <h3>Kurzbezeichnung in der Leiste</h3>
        <div className="weiteres">
          <input value={kurz} onChange={(e) => setKurz(e.target.value)} maxLength={40} placeholder="JuraBox" />
          <button type="submit" disabled={laeuft || kurz.trim() === (marke?.kurzbezeichnung ?? "")}>
            Speichern
          </button>
        </div>
        <p className="leise">Leer lassen, dann steht dort „JuraBox“.</p>
      </form>

      {fehler && <p className="fehler" role="alert">{fehler}</p>}
    </section>
  );
}

/** Externe KI: abgesetzt, standardmäßig aus, nur über den Schalter mit Hinweis auf Datenschutz- und Berufsrecht. */
function ExterneKi({
  status,
  onStatus,
  onGeaendert,
}: {
  status: KiStatus;
  onStatus: (s: KiStatus) => void;
  onGeaendert?: () => void;
}) {
  const x = status.externe;
  const [bestaetigen, setBestaetigen] = useState(false);
  const [gelesen, setGelesen] = useState(false);
  const [anbieter, setAnbieter] = useState(x.anbieter);
  const [adresse, setAdresse] = useState(x.anbieter === "anderer" ? x.adresse : "");
  const [modell, setModell] = useState(
    x.modell || (x.anbieter_liste.find((a) => a.id === x.anbieter)?.vorschlag ?? ""),
  );
  const [kontext, setKontext] = useState(x.kontext);
  const [schluessel, setSchluessel] = useState("");
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  async function setze(params: Record<string, unknown>, text: string) {
    setLaeuft(text);
    setFehler(null);
    try {
      const neu = await kern<KiStatus>("ki.extern_setzen", { freigegeben: x.freigegeben, ...params });
      onStatus(neu);
      setSchluessel("");
      if (neu.externe.modell) setModell(neu.externe.modell);
      onGeaendert?.();
      return neu;
    } catch (e) {
      setFehler(String(e));
      return null;
    } finally {
      setLaeuft(null);
    }
  }

  async function speichern(e: FormEvent) {
    e.preventDefault();
    await setze(
      { anbieter, modell, kontext, adresse: anbieter === "anderer" ? adresse : undefined, schluessel: schluessel || undefined, verbindung: true },
      "Speichere und frage die Modellliste beim Anbieter ab …",
    );
  }

  const liste = x.anbieter_liste.find((a) => a.id === anbieter);
  const geaendert =
    anbieter !== x.anbieter ||
    modell !== x.modell ||
    kontext !== x.kontext ||
    schluessel !== "" ||
    (anbieter === "anderer" && adresse.trim().replace(/\/+$/, "") !== x.adresse);
  const modelle = anbieter === x.anbieter ? x.modelle : [];

  return (
    <section className={x.freigegeben ? "karte extern-karte freigegeben" : "karte extern-karte"}>
      <h2>Externe KI</h2>
      <label className="schalter">
        <input
          type="checkbox"
          checked={x.freigegeben || bestaetigen}
          disabled={!!laeuft}
          onChange={(e) => {
            if (e.target.checked) {
              setBestaetigen(true);
              setGelesen(false);
            } else if (bestaetigen) {
              setBestaetigen(false);
            } else {
              void setze({ freigegeben: false }, "Schalte externe KI aus …");
            }
          }}
        />
        <span>Externe KI einbinden</span>
        <span className="leise">{x.freigegeben ? "eingeschaltet" : "aus (Voreinstellung)"}</span>
      </label>

      <div className="rechtshinweis" role="note">
        <strong>Bitte Datenschutzrecht und Berufsrecht beachten.</strong> Externe KI ist die Ausnahme. Mit ihr gehen
        deine Fragen und die Texte der befragten Dokumente an den gewählten Anbieter, also auf fremde Server, oft
        außerhalb der EU. Vor dem Einsatz mit Mandatsdaten insbesondere prüfen:
        <ul>
          <li>
            Datenschutz: Rechtsgrundlage, Vertrag zur Auftragsverarbeitung mit dem Anbieter (Art. 28 DSGVO), bei
            Übermittlung in Drittländer die Voraussetzungen der Art. 44 ff. DSGVO.
          </li>
          <li>
            Verschwiegenheit: § 43a Abs. 2 BRAO und § 2 BORA. Dienstleister dürfen nur unter den Voraussetzungen des §
            43e BRAO Kenntnis von Mandatsgeheimnissen erhalten (u. a. Vereinbarung in Textform, Verpflichtung zur
            Verschwiegenheit, bei Anbietern im Ausland vergleichbarer Geheimnisschutz). Andernfalls droht eine
            Strafbarkeit nach § 203 StGB.
          </li>
          <li>Wo möglich: Dokumente vorher anonymisieren oder die Einwilligung der Mandantschaft einholen.</li>
        </ul>
        Die App prüft das nicht für dich; sie zeigt nur deutlich an, wann Inhalte das Gerät verlassen.
      </div>

      {bestaetigen && !x.freigegeben && (
        <div className="rueckfrage">
          <label className="schalter">
            <input type="checkbox" checked={gelesen} onChange={(e) => setGelesen(e.target.checked)} />
            <span>Ich habe den Hinweis gelesen und prüfe die Zulässigkeit im Einzelfall selbst.</span>
          </label>
          <div className="aktionen">
            <button
              disabled={!gelesen || !!laeuft}
              onClick={async () => {
                if (await setze({ freigegeben: true }, "Schalte externe KI ein …")) setBestaetigen(false);
              }}
            >
              Externe KI einbinden
            </button>
            <button className="zweitrangig" onClick={() => setBestaetigen(false)}>
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {x.freigegeben && (
        <>
          <form className="ki-formular" onSubmit={speichern}>
            <label>
              Anbieter
              <select
                value={anbieter}
                onChange={(e) => {
                  setAnbieter(e.target.value);
                  const neu = x.anbieter_liste.find((a) => a.id === e.target.value);
                  setModell(e.target.value === x.anbieter ? x.modell : (neu?.vorschlag ?? ""));
                }}
              >
                {x.anbieter_liste.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.titel}
                  </option>
                ))}
              </select>
            </label>
            {anbieter === "anderer" ? (
              <label>
                Adresse
                <input
                  value={adresse}
                  onChange={(e) => setAdresse(e.target.value)}
                  placeholder="https://…/v1"
                  spellCheck={false}
                />
              </label>
            ) : (
              <label>
                Adresse
                <span className="leise">{liste?.adresse}</span>
              </label>
            )}
            <label>
              API-Schlüssel
              <input
                type="password"
                value={schluessel}
                onChange={(e) => setSchluessel(e.target.value)}
                placeholder={
                  anbieter === x.anbieter && x.schluessel_hinterlegt
                    ? `hinterlegt${x.schluessel_ende ? ` (endet auf …${x.schluessel_ende})` : ""}; neu eingeben zum Ersetzen`
                    : "beim Anbieter erzeugen und hier einfügen"
                }
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            <label>
              Modell
              {modelle.length > 0 ? (
                <select value={modell} onChange={(e) => setModell(e.target.value)}>
                  {!modelle.some((m) => m.name === modell) && <option value={modell}>{modell || "(bitte wählen)"}</option>}
                  {modelle.map((m) => (
                    <option key={m.name} value={m.name}>
                      {m.name}
                      {m.parameter && m.parameter !== m.name ? ` · ${m.parameter}` : ""}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={modell}
                  onChange={(e) => setModell(e.target.value)}
                  placeholder={liste?.vorschlag || "nach „Verbindung prüfen“ aus der Liste wählen"}
                  spellCheck={false}
                />
              )}
            </label>
            <label>
              Textmenge
              <select value={kontext} onChange={(e) => setKontext(Number(e.target.value))}>
                {KONTEXTE_EXTERN.map((k) => (
                  <option key={k} value={k}>
                    {k.toLocaleString("de-DE")} Token je Anfrage{k === 32768 ? " (empfohlen)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <div className="aktionen">
              <button type="submit" disabled={!!laeuft || !geaendert}>
                Speichern
              </button>
              <button
                type="button"
                className="zweitrangig"
                disabled={!!laeuft || geaendert || !x.schluessel_hinterlegt}
                onClick={() => setze({ verbindung: true }, "Frage die Modellliste beim Anbieter ab …")}
                title="Fragt nur die Liste der Modelle ab, sendet keine Dokumentinhalte"
              >
                Verbindung prüfen
              </button>
              {x.schluessel_hinterlegt && anbieter === x.anbieter && (
                <button
                  type="button"
                  className="zweitrangig gefahr"
                  disabled={!!laeuft}
                  onClick={() => setze({ schluessel_loeschen: true }, "Lösche den Schlüssel …")}
                >
                  Schlüssel löschen
                </button>
              )}
            </div>
          </form>
          <p className="leise">
            Der Schlüssel liegt in der Datei ki-schluessel.json im Datenverzeichnis der App, getrennt von den übrigen
            Einstellungen, und wird nicht wieder angezeigt.
          </p>
          {laeuft && <p className="status" role="status">{laeuft}</p>}
          {fehler && <p className="fehler" role="alert">{fehler}</p>}
          {!laeuft && (
            <p className={x.bereit ? "ki-zeile bereit" : "ki-zeile"}>
              {x.bereit
                ? `Eingerichtet: ${x.modell} über ${x.anbieter_titel}${x.geprueft ? ", Verbindung geprüft" : ""}.`
                : x.hinweis}
            </p>
          )}

          <fieldset className="ki-wahl">
            <legend>Analyse und Chat verwenden</legend>
            <label>
              <input
                type="radio"
                checked={status.aktiv === "lokal"}
                disabled={!!laeuft}
                onChange={() => setze({ aktiv: "lokal" }, "Stelle auf das Modell auf diesem Gerät um …")}
              />{" "}
              das Modell auf diesem Gerät (empfohlen)
            </label>
            <label>
              <input
                type="radio"
                checked={status.aktiv === "extern"}
                disabled={!!laeuft || !x.bereit}
                onChange={() => setze({ aktiv: "extern" }, "Stelle auf den externen Anbieter um …")}
              />{" "}
              den externen Anbieter {x.anbieter_titel}
              {!x.bereit && <span className="leise"> (erst Schlüssel und Modell speichern)</span>}
            </label>
          </fieldset>
        </>
      )}
    </section>
  );
}
