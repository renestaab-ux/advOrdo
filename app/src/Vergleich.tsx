import { useCallback, useEffect, useRef, useState } from "react";
import { DokumentAnsicht } from "./Akte";
import { Beleg, Zitatbereich, ZitateSchalter } from "./Belege";
import { useKiAn } from "./kiSchalter";
import {
  Abgleich,
  AbgleichFundstelle,
  AbgleichMerkmal,
  AktenDokument,
  DokumentInhalt,
  EINORDNUNG_TEXT,
  abgleichZusammenfassung,
  istDesktop,
  kern,
} from "./kern";

type Umfang = "alle" | "zwei";

/** Gleicht die Angaben der Dokumente einer Akte ab: ganze Akte oder zwei gewählte Dokumente. */
export default function Vergleich({ akteId }: { akteId: number }) {
  const kiAn = useKiAn();
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [umfang, setUmfang] = useState<Umfang>("alle");
  const [paar, setPaar] = useState<[number | null, number | null]>([null, null]);
  const [ergebnis, setErgebnis] = useState<Abgleich | null>(null);
  const [offen, setOffen] = useState<{ inhalt: DokumentInhalt; abschnitt: number } | null>(null);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const seite = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    setErgebnis(null);
    setOffen(null);
    setDokumente([]);
    setPaar([null, null]);
    if (akteId == null) return;
    void ausfuehren("Lade Dokumente …", async () => {
      const d = await kern<AktenDokument[]>("akten.dokumente", { akte_id: akteId });
      setDokumente(d);
      setPaar([d[0]?.id ?? null, d[1]?.id ?? null]);
    });
  }, [akteId, ausfuehren]);

  // null: ganze Akte; undefined: noch keine gültige Auswahl zweier verschiedener Dokumente.
  const [erstes, zweites] = paar;
  const auswahl =
    umfang === "alle" ? null : erstes != null && zweites != null && erstes !== zweites ? [erstes, zweites] : undefined;

  useEffect(() => {
    // Der Abgleich ist schnell (nur gespeicherter Text), daher bei jeder Änderung der Auswahl neu.
    setErgebnis(null);
    setOffen(null);
    if (akteId == null || dokumente.length === 0 || auswahl === undefined) return;
    void ausfuehren("Gleiche Angaben ab …", async () => {
      const params: Record<string, unknown> = { akte_id: akteId };
      if (auswahl) params.dokument_ids = auswahl;
      setErgebnis(await kern<Abgleich>("akten.abgleich", params));
    });
  }, [akteId, dokumente, umfang, erstes, zweites, ausfuehren]);

  async function oeffne(f: AbgleichFundstelle) {
    const inhalt = await ausfuehren("Lade Dokument …", () => kern<DokumentInhalt>("akten.dokument", { dokument_id: f.dokument_id }));
    if (inhalt) setOffen({ inhalt, abschnitt: f.abschnitt });
  }

  // Nur die Seitenleiste zur Fundstelle scrollen, die Liste der Abweichungen bleibt stehen.
  useEffect(() => {
    const leiste = seite.current;
    const ziel = offen && document.getElementById(`abschnitt-${offen.abschnitt}`);
    if (!leiste || !ziel) return;
    const abstand = ziel.getBoundingClientRect().top - leiste.getBoundingClientRect().top;
    leiste.scrollTop += abstand - leiste.clientHeight / 3;
  }, [offen]);

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Der Vergleich arbeitet nur in der Desktop-App: <code>npm run tauri dev</code>
      </section>
    );
  }

  const abweichend = ergebnis?.merkmale.filter((m) => m.status === "abweichend") ?? [];
  const gleich = ergebnis?.merkmale.filter((m) => m.status === "uebereinstimmend") ?? [];
  const einzeln = ergebnis?.merkmale.filter((m) => m.status === "einzeln") ?? [];

  return (
    <div className="vergleich">
      <p className="erklaerung">
        Stellt dieselben Angaben aus den Dokumenten nebeneinander: Daten, Beträge, Kilometerstände und Fehlercodes,
        jeweils mit Fundstelle. Eine Abweichung ist ein Hinweis, keine Bewertung. Ob ein Widerspruch vorliegt, entscheidest
        du anhand der Fundstellen.
      </p>

      <div className="akten-wahl">
        {dokumente.length > 1 && (
          <div className="umfang" role="radiogroup" aria-label="Was abgleichen?">
            <label>
              <input type="radio" checked={umfang === "alle"} onChange={() => setUmfang("alle")} /> Alle Dokumente
            </label>
            <label>
              <input type="radio" checked={umfang === "zwei"} onChange={() => setUmfang("zwei")} /> Zwei Dokumente
            </label>
          </div>
        )}
      </div>

      {umfang === "zwei" && dokumente.length > 1 && (
        <div className="paar">
          {([0, 1] as const).map((i) => (
            <select
              key={i}
              value={paar[i] ?? ""}
              onChange={(e) => setPaar(i === 0 ? [Number(e.target.value), paar[1]] : [paar[0], Number(e.target.value)])}
              aria-label={i === 0 ? "Erstes Dokument" : "Zweites Dokument"}
            >
              {dokumente.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.dateiname}
                </option>
              ))}
            </select>
          ))}
          {auswahl === undefined && <span className="hinweis">Bitte zwei verschiedene Dokumente wählen.</span>}
        </div>
      )}

      {laeuft && <p className="status" role="status">{laeuft}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {akteId != null && dokumente.length === 0 && !laeuft && (
        <p className="leer">Diese Akte enthält noch keine Dokumente.</p>
      )}

      {ergebnis && (
        <div className="akte-arbeitsflaeche">
          <div className="akte-haupt">
            <Zitatbereich>
            <p className="zusammenfassung">
              {abgleichZusammenfassung(ergebnis)} <ZitateSchalter />
            </p>
            {abweichend.length === 0 && (
              <p className="leer">Keine abweichenden Angaben gefunden.</p>
            )}
            {abweichend.map((m) => (
              <MerkmalKarte key={m.merkmal} merkmal={m} onFundstelle={oeffne} offen={offen} />
            ))}
            {gleich.length > 0 && (
              <details className="weitere-merkmale">
                <summary>Übereinstimmend ({gleich.length})</summary>
                {gleich.map((m) => (
                  <MerkmalKarte key={m.merkmal} merkmal={m} onFundstelle={oeffne} offen={offen} />
                ))}
              </details>
            )}
            {einzeln.length > 0 && (
              <details className="weitere-merkmale">
                <summary>Nur in einem Dokument ({einzeln.length})</summary>
                {einzeln.map((m) => (
                  <MerkmalKarte key={m.merkmal} merkmal={m} onFundstelle={oeffne} offen={offen} />
                ))}
              </details>
            )}
            </Zitatbereich>
            {kiAn && (
              <p className="grenze">
                Aussagen ohne Zahl oder Datum, etwa ob eine Nachbesserung angeboten oder abgelehnt wurde, prüft der Bereich
                „Analyse“ mit dem lokalen Sprachmodell.
              </p>
            )}
          </div>
          {offen && (
            <aside className="akte-seite vergleich-dokument">
              <div className="vergleich-dokument-kopf">
                <span className="fundort">{offen.inhalt.dokument.dateiname}</span>
                <button className="zweitrangig" onClick={() => setOffen(null)}>
                  Schließen
                </button>
              </div>
              <div className="vergleich-dokument-text" ref={seite}>
                <DokumentAnsicht inhalt={offen.inhalt} markiert={offen.abschnitt} />
              </div>
            </aside>
          )}
        </div>
      )}
    </div>
  );
}

function MerkmalKarte({
  merkmal,
  onFundstelle,
  offen,
}: {
  merkmal: AbgleichMerkmal;
  onFundstelle: (f: AbgleichFundstelle) => void;
  offen: { inhalt: DokumentInhalt; abschnitt: number } | null;
}) {
  return (
    <section className={`merkmal ${merkmal.status}`}>
      <header>
        <strong>{merkmal.titel}</strong>
        {merkmal.einordnung.map((e) => (
          <span key={e} className={`einordnung ${e}`}>
            {EINORDNUNG_TEXT[e]}
          </span>
        ))}
      </header>
      <div className="werte">
        {merkmal.werte.map((w) => (
          <div key={w.wert} className="wert">
            <div className="wert-anzeige">{w.anzeige}</div>
            <ul className="belege">
              {w.fundstellen.map((f, i) => (
                <Beleg
                  key={i}
                  f={f}
                  gewaehlt={offen?.inhalt.dokument.id === f.dokument_id && offen.abschnitt === f.abschnitt}
                  onFundstelle={() => onFundstelle(f)}
                />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
