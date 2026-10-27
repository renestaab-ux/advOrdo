import { useEffect, useRef, useState } from "react";
import Zeichen, { SymbolName } from "./Symbole";
import {
  Akte,
  EigeneKurzstand,
  KalenderEintrag,
  KiModus,
  Marke,
  NachrichtenListe,
  kiModusName,
  abstandText,
  akteTitel,
  datumLang,
  istDesktop,
  kern,
  nachrichtAlter,
  zeitpunkt,
  zuletztGeoeffnet,
} from "./kern";

export type StartZiel = "anlegen" | "akten" | "eigene" | "toolbox" | "einstellungen";

const KACHELN: { ziel: StartZiel; titel: string; text: string; symbol: SymbolName }[] = [
  { ziel: "anlegen", titel: "Akte anlegen", text: "Neues Mandat anlegen, auch aus einem Dokument", symbol: "akteNeu" },
  { ziel: "akten", titel: "Akten", text: "Übersicht, Dokumente, Vergleich und Analyse", symbol: "akten" },
  { ziel: "eigene", titel: "Eigene Daten", text: "Kanzlei bzw. Unternehmen und Ihre Person", symbol: "eigene" },
  { ziel: "toolbox", titel: "Toolbox", text: "Zinsen-, Fristen- und Prozesskostenrechner, eigenes Fenster", symbol: "toolbox" },
];

/** Startbildschirm nach Renés Skizze: Kopfband, große Kacheln, zuletzt geöffnete Akten und Arbeitsbereich. */
export default function Start({
  onWahl,
  onAkte,
  modus,
  umgebung,
  marke,
  onNachrichten,
}: {
  onWahl: (ziel: StartZiel) => void;
  onNachrichten: () => void;
  onAkte: (akteId: number, reiter?: "fristen") => void;
  modus: KiModus | null;
  umgebung: string | null;
  marke: Marke | null;
}) {
  // Stand der Eigenen Daten für die Kachel, z. B. „3 Angaben fehlen“.
  const [profil, setProfil] = useState<EigeneKurzstand | null>(null);
  const [akten, setAkten] = useState<Akte[] | null>(null);
  const [fristen, setFristen] = useState<KalenderEintrag[] | null>(null);
  useEffect(() => {
    if (!istDesktop) return;
    // Offene Fristen, Termine und Wiedervorlagen der nächsten 14 Tage aus allen Akten, abgelaufene zuerst.
    void kern<KalenderEintrag[]>("akten.kalender_naechste", { tage: 14, limit: 8 }).then(setFristen, () => setFristen([]));
    void kern<EigeneKurzstand>("eigene.kurzstand").then(setProfil, () => setProfil(null));
    void kern<Akte[]>("akten.liste").then(setAkten, () => setAkten([]));
  }, []);
  const aus = !!modus?.aus;
  const extern = !aus && modus?.aktiv === "extern";
  const zuletzt = zuletztGeoeffnet(akten ?? [], 5);

  return (
    <div className="start">
      <header className="kopfband">
        <div>
          <p className="kopfband-ueber">Startseite</p>
          <h1>Willkommen bei JuraBox</h1>
        </div>
        <span className={aus ? "modus-pille aus" : extern ? "modus-pille extern" : "modus-pille"}>
          <span className="modus-punkt" aria-hidden />
          KI: {kiModusName(modus)}
        </span>
      </header>
      <div className="start-inhalt">
        {(marke?.logo || marke?.name) && (
          <div className="start-marke">
            {marke.logo && <img src={marke.logo} alt="Logo" />}
            {marke.name && <span>{marke.name}</span>}
          </div>
        )}
        <p className="erklaerung">Wählen Sie einen Arbeitsbereich oder öffnen Sie direkt eine Akte.</p>
        <div className="kacheln">
          {KACHELN.map((k) => (
            <button key={k.ziel} className="kachel" onClick={() => onWahl(k.ziel)}>
              <span className="kachel-symbol" aria-hidden>
                <Zeichen name={k.symbol} groesse={40} />
              </span>
              <span className="kachel-titel">{k.titel}</span>
              <span className="kachel-text">{aus && k.ziel === "akten" ? "Übersicht, Dokumente und Vergleich" : k.text}</span>
              {k.ziel === "eigene" && profil && (
                <span className={profil.eingerichtet && profil.fehlend === 0 ? "kachel-stand gut" : "kachel-stand"}>
                  {profil.text}
                </span>
              )}
            </button>
          ))}

          <section className="kachel kachel-liste" aria-label="Zuletzt geöffnete Akten">
            <h2>Zuletzt geöffnet</h2>
            {zuletzt.length > 0 ? (
              <ul>
                {zuletzt.map((a) => (
                  <li key={a.id}>
                    <button className="link" onClick={() => onAkte(a.id)}>
                      {akteTitel(a)}
                    </button>
                    {a.gegenstand && <span className="leise">{a.gegenstand}</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="leer">
                {akten && akten.length > 0 ? "Noch keine Akte geöffnet." : "Noch keine Akte angelegt."}
              </p>
            )}
            <button className="link klein" onClick={() => onWahl("akten")}>
              Alle Akten
            </button>
          </section>

          <section className="kachel kachel-liste kachel-fristen" aria-label="Nächste Fristen">
            <h2>Nächste Fristen und Termine</h2>
            {fristen && fristen.length > 0 ? (
              <ul>
                {fristen.map((f) => (
                  <li key={f.id} className={`start-frist ${f.lage}`}>
                    <button className="link" onClick={() => onAkte(f.akte_id, "fristen")}>
                      {datumLang(f.datum)}
                      {f.uhrzeit && `, ${f.uhrzeit}`} · {f.titel}
                    </button>
                    <span className="leise">
                      {abstandText(f)} · {f.aktenzeichen ? `${f.aktenzeichen} ` : ""}
                      {f.akte}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="leer">{fristen ? "Keine offenen Fristen in den nächsten 14 Tagen." : "Lade …"}</p>
            )}
          </section>

          <StartNachrichten onVerwalten={onNachrichten} />

          <section className="kachel kachel-info" aria-label="Ihr Arbeitsbereich">
            <h2>Ihr Arbeitsbereich</h2>
            <dl>
              <dt>KI-Modus</dt>
              <dd className={extern ? "hinweis" : aus ? undefined : "gut"}>
                {aus
                  ? "Nicht aktiv: Die KI ist ausgeschaltet. Dokumente und Akten bleiben auf diesem Gerät."
                  : extern
                  ? `Externer Anbieter (${modus?.titel}): Analyse und Chat senden Dokumenttexte dorthin.`
                  : modus?.ort === "netzwerk"
                    ? "Lokales Netzwerk: Das Sprachmodell läuft auf einem anderen Rechner im eigenen Netz; Dokumente und Akten verlassen es nicht."
                    : "Eigener Rechner: Dokumente und Akten bleiben auf diesem Gerät."}
              </dd>
              {umgebung && (
                <>
                  <dt>Umgebung</dt>
                  <dd>{umgebung}</dd>
                </>
              )}
            </dl>
            <button className="link klein" onClick={() => onWahl("einstellungen")}>
              Einstellungen
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}

const WENIGE = 8;
const VIELE = 30;

/** Nachrichten aus den RSS-Feeds der Einstellungen; ohne eingetragenen Feed erscheint nichts. */
function StartNachrichten({ onVerwalten }: { onVerwalten: () => void }) {
  const [liste, setListe] = useState<NachrichtenListe | null>(null);
  const [alle, setAlle] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const warte = useRef<number | null>(null);

  function laden(aktualisieren = false, limit = alle ? VIELE : WENIGE, runde = 0) {
    if (warte.current != null) window.clearTimeout(warte.current);
    kern<NachrichtenListe>("nachrichten.liste", { limit, aktualisieren }).then(
      (l) => {
        setListe(l);
        // Der Kern lädt im Hintergrund; bis er fertig ist, alle zwei Sekunden nachsehen (höchstens eine Minute).
        if (l.laeuft && runde < 30) warte.current = window.setTimeout(() => laden(false, limit, runde + 1), 2000);
      },
      () => setListe(null),
    );
  }

  useEffect(() => {
    if (istDesktop) laden();
    return () => {
      if (warte.current != null) window.clearTimeout(warte.current);
    };
  }, []);

  if (!liste || liste.feeds === 0) return null;

  async function oeffnen(link: string) {
    setFehler(null);
    try {
      await kern("nachrichten.oeffnen", { adresse: link });
    } catch (e) {
      setFehler(String(e));
    }
  }

  return (
    <section className="kachel kachel-liste kachel-nachrichten" aria-label="Nachrichten">
      <div className="nachrichten-kopf">
        <h2>Nachrichten</h2>
        <span className="leise">
          {liste.laeuft ? "Lade …" : liste.stand ? `Stand ${zeitpunkt(liste.stand)}` : ""}
        </span>
        <button className="link klein" onClick={() => laden(true)} disabled={liste.laeuft}>
          Aktualisieren
        </button>
      </div>
      {liste.eintraege.length > 0 ? (
        <ul>
          {liste.eintraege.map((n, i) => (
            <li key={`${n.feed_id}-${n.link ?? n.titel}-${i}`}>
              {n.link ? (
                <button className="link" onClick={() => void oeffnen(n.link!)} title={n.auszug || n.link}>
                  {n.titel}
                </button>
              ) : (
                <span title={n.auszug}>{n.titel}</span>
              )}
              <span className="leise">
                {n.quelle}
                {n.datum && ` · ${nachrichtAlter(n.datum)}`}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="leer">{liste.laeuft ? "Lade Nachrichten …" : "Keine Nachrichten geladen."}</p>
      )}
      {liste.fehler.length > 0 && (
        <p className="hinweis klein">
          Nicht geladen: {liste.fehler.map((f) => `${f.titel} (${f.text})`).join("; ")}
        </p>
      )}
      {fehler && <p className="fehler">{fehler}</p>}
      <div className="nachrichten-fuss">
        {liste.gesamt > WENIGE && (
          <button
            className="link klein"
            onClick={() => {
              setAlle(!alle);
              laden(false, alle ? WENIGE : VIELE);
            }}
          >
            {alle ? "Weniger anzeigen" : `Mehr anzeigen (${Math.min(liste.gesamt, VIELE)})`}
          </button>
        )}
        <button className="link klein" onClick={onVerwalten}>
          Feeds verwalten
        </button>
      </div>
    </section>
  );
}
