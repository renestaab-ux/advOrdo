import { useEffect, useState } from "react";
import Zeichen, { SymbolName } from "./Symbole";
import { Akte, EigeneKurzstand, KiModus, akteTitel, istDesktop, kern, zuletztGeoeffnet } from "./kern";

export type StartZiel = "anlegen" | "akten" | "eigene" | "toolbox" | "einstellungen";

const KACHELN: { ziel: StartZiel; titel: string; text: string; symbol: SymbolName }[] = [
  { ziel: "anlegen", titel: "Akte anlegen", text: "Neues Mandat mit Bezeichnung anlegen", symbol: "akteNeu" },
  { ziel: "akten", titel: "Akten", text: "Übersicht, Dokumente, Vergleich und Analyse", symbol: "akten" },
  { ziel: "eigene", titel: "Eigene Daten", text: "Kanzlei bzw. Unternehmen und Ihre Person", symbol: "eigene" },
  { ziel: "toolbox", titel: "Toolbox", text: "Verzugszinsen- und Fristenrechner, eigenes Fenster", symbol: "toolbox" },
];

/** Startbildschirm nach Renés Skizze: Kopfband, große Kacheln, zuletzt geöffnete Akten und Arbeitsbereich. */
export default function Start({
  onWahl,
  onAkte,
  modus,
  umgebung,
}: {
  onWahl: (ziel: StartZiel) => void;
  onAkte: (akteId: number) => void;
  modus: KiModus | null;
  umgebung: string | null;
}) {
  // Stand der Eigenen Daten für die Kachel, z. B. „3 Angaben fehlen“.
  const [profil, setProfil] = useState<EigeneKurzstand | null>(null);
  const [akten, setAkten] = useState<Akte[] | null>(null);
  useEffect(() => {
    if (!istDesktop) return;
    void kern<EigeneKurzstand>("eigene.kurzstand").then(setProfil, () => setProfil(null));
    void kern<Akte[]>("akten.liste").then(setAkten, () => setAkten([]));
  }, []);
  const extern = modus?.aktiv === "extern";
  const zuletzt = zuletztGeoeffnet(akten ?? [], 5);

  return (
    <div className="start">
      <header className="kopfband">
        <div>
          <p className="kopfband-ueber">Startseite</p>
          <h1>Willkommen bei JuraBox</h1>
        </div>
        <span className={extern ? "modus-pille extern" : "modus-pille"}>
          <span className="modus-punkt" aria-hidden />
          {extern ? `Externer Anbieter (${modus?.titel})` : "Nur lokal"}
        </span>
      </header>
      <div className="start-inhalt">
        <p className="erklaerung">Wählen Sie einen Arbeitsbereich oder öffnen Sie direkt eine Akte.</p>
        <div className="kacheln">
          {KACHELN.map((k) => (
            <button key={k.ziel} className="kachel" onClick={() => onWahl(k.ziel)}>
              <span className="kachel-symbol" aria-hidden>
                <Zeichen name={k.symbol} groesse={40} />
              </span>
              <span className="kachel-titel">{k.titel}</span>
              <span className="kachel-text">{k.text}</span>
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

          <section className="kachel kachel-info" aria-label="Ihr Arbeitsbereich">
            <h2>Ihr Arbeitsbereich</h2>
            <dl>
              <dt>Modus</dt>
              <dd className={extern ? "hinweis" : "gut"}>
                {extern
                  ? `Externer Anbieter (${modus?.titel}): Analyse und Chat senden Dokumenttexte dorthin.`
                  : "Nur lokal: Dokumente und Akten bleiben auf diesem Gerät."}
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
