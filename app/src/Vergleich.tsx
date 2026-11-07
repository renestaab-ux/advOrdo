import { useCallback, useEffect, useRef, useState } from "react";
import { DokumentAnsicht } from "./Akte";
import { WiderspruchKarte } from "./Analyse";
import { Beleg, Zitatbereich, ZitateSchalter } from "./Belege";
import { useKiAn } from "./kiSchalter";
import {
  Abgleich,
  AbgleichFundstelle,
  AbgleichMerkmal,
  AktenDokument,
  DokumentInhalt,
  EINORDNUNG_TEXT,
  HALTUNG_TEXT,
  KiAuftrag,
  KiVergleich,
  KiVergleichStand,
  abgleichZusammenfassung,
  istDesktop,
  kern,
  zeitpunkt,
} from "./kern";

type Umfang = "alle" | "zwei";

/** Stand der KI beim Vergleich: was die Zeile über dem Ergebnis sagt. */
type KiStand =
  | { art: "pruefe" }
  | { art: "aus"; abgeschaltet: boolean; hinweis?: string }
  | { art: "laeuft"; auftrag: KiAuftrag }
  | { art: "fertig"; ergebnis: KiVergleich }
  | { art: "belegt" }
  | { art: "extern" }
  | { art: "fehler"; text: string }
  | { art: "abgebrochen" };

/**
 * Gleicht die Angaben der Dokumente einer Akte ab: ganze Akte oder zwei gewählte Dokumente.
 * Zweistufig: Ist ein Sprachmodell eingerichtet, vergleicht es mit Blick auf den Zusammenhang (worauf sich ein Wert
 * bezieht) und sucht inhaltliche Widersprüche. Bis es fertig ist, und wenn die KI aus oder nicht erreichbar ist,
 * gilt der regelbasierte Abgleich.
 */
export default function Vergleich({ akteId, onEinstellungen }: { akteId: number; onEinstellungen?: () => void }) {
  const kiAn = useKiAn();
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [umfang, setUmfang] = useState<Umfang>("alle");
  const [paar, setPaar] = useState<[number | null, number | null]>([null, null]);
  const [regel, setRegel] = useState<Abgleich | null>(null);
  const [ki, setKi] = useState<KiStand>({ art: "pruefe" });
  const [offen, setOffen] = useState<{ inhalt: DokumentInhalt; abschnitt: number } | null>(null);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const seite = useRef<HTMLDivElement>(null);
  // Zur aktuellen Auswahl gehörende Anfrage; Antworten zu einer älteren Auswahl werden verworfen.
  const anfrage = useRef(0);

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
    setRegel(null);
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
  const auswahlSchluessel = auswahl === undefined ? "" : JSON.stringify(auswahl);

  const kiFragen = useCallback(
    async (params: { neu?: boolean; automatisch?: boolean } = {}) => {
      if (akteId == null || auswahl === undefined) return;
      const nr = anfrage.current;
      const p: Record<string, unknown> = { akte_id: akteId, ...params };
      if (auswahl) p.dokument_ids = auswahl;
      try {
        const stand = await kern<KiVergleichStand>("ki.vergleich", p);
        if (nr !== anfrage.current) return;
        if (stand.status === "aus") setKi({ art: "aus", abgeschaltet: stand.abgeschaltet, hinweis: stand.hinweis });
        else if (stand.status === "fertig") setKi({ art: "fertig", ergebnis: stand.ergebnis });
        else if (stand.status === "laeuft") setKi({ art: "laeuft", auftrag: stand.auftrag });
        else if (stand.status === "belegt") setKi({ art: "belegt" });
        else setKi({ art: "extern" });
      } catch (e) {
        if (nr === anfrage.current) setKi({ art: "fehler", text: String(e) });
      }
    },
    // auswahlSchluessel steht für auswahl (ein neues Feld bei jedem Rendern).
    [akteId, auswahlSchluessel],
  );

  useEffect(() => {
    // Der regelbasierte Abgleich ist schnell (nur gespeicherter Text) und steht sofort da; die KI folgt.
    anfrage.current += 1;
    setRegel(null);
    setOffen(null);
    setKi(kiAn ? { art: "pruefe" } : { art: "aus", abgeschaltet: true });
    if (akteId == null || dokumente.length === 0 || auswahl === undefined) return;
    void ausfuehren("Gleiche Angaben ab …", async () => {
      const params: Record<string, unknown> = { akte_id: akteId };
      if (auswahl) params.dokument_ids = auswahl;
      setRegel(await kern<Abgleich>("akten.abgleich", params));
    });
    if (kiAn) void kiFragen({ automatisch: true });
  }, [akteId, dokumente, umfang, erstes, zweites, kiAn, ausfuehren, kiFragen]);

  // Laufenden KI-Auftrag jede Sekunde abfragen.
  const kiAuftragId = ki.art === "laeuft" ? ki.auftrag.auftrag_id : null;
  useEffect(() => {
    if (kiAuftragId == null) return;
    const nr = anfrage.current;
    const takt = window.setInterval(async () => {
      try {
        const a = await kern<KiAuftrag>("ki.auftrag", { auftrag_id: kiAuftragId });
        if (nr !== anfrage.current) return;
        if (a.status === "laeuft") setKi({ art: "laeuft", auftrag: a });
        else if (a.status === "fertig") setKi({ art: "fertig", ergebnis: a.ergebnis as KiVergleich });
        else if (a.status === "abgebrochen") setKi({ art: "abgebrochen" });
        else setKi({ art: "fehler", text: a.fehler ?? "Unbekannter Fehler" });
      } catch (e) {
        if (nr === anfrage.current) setKi({ art: "fehler", text: String(e) });
      }
    }, 1000);
    return () => window.clearInterval(takt);
  }, [kiAuftragId]);

  async function kiAbbrechen() {
    if (ki.art !== "laeuft") return;
    try {
      await kern("ki.abbrechen", { auftrag_id: ki.auftrag.auftrag_id });
    } catch (e) {
      setFehler(String(e));
    }
  }

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

  const ergebnis: Abgleich | KiVergleich | null = ki.art === "fertig" ? ki.ergebnis : regel;
  const mitKi = ki.art === "fertig" ? ki.ergebnis : null;
  const nach = (status: AbgleichMerkmal["status"]) => ergebnis?.merkmale.filter((m) => m.status === status) ?? [];
  const abweichend = nach("abweichend");
  const verschieden = nach("verschieden");
  const gleich = nach("uebereinstimmend");
  const einzeln = nach("einzeln");
  const inhaltlich = mitKi?.inhaltlich.widersprueche ?? [];
  const karte = (m: AbgleichMerkmal) => (
    <MerkmalKarte key={m.merkmal} merkmal={m} onFundstelle={oeffne} offen={offen} mitKi={mitKi != null} />
  );

  return (
    <div className="vergleich">
      <p className="erklaerung">
        Stellt dieselben Angaben aus den Dokumenten nebeneinander: Daten, Beträge, Kilometerstände und Fehlercodes,
        jeweils mit Fundstelle. Mit KI achtet der Vergleich darauf, worauf sich ein Wert bezieht, und zeigt auch
        inhaltliche Widersprüche. Eine Abweichung ist ein Hinweis, keine Bewertung. Ob ein Widerspruch vorliegt,
        entscheidest du anhand der Fundstellen.
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

      {laeuft && <p className="status">{laeuft}</p>}
      {fehler && <p className="fehler">{fehler}</p>}
      {akteId != null && dokumente.length === 0 && !laeuft && (
        <p className="leer">Diese Akte enthält noch keine Dokumente.</p>
      )}

      {ergebnis && (
        <KiZeile
          ki={ki}
          onNeu={() => void kiFragen({ neu: ki.art === "fertig" })}
          onAbbrechen={kiAbbrechen}
          onEinstellungen={onEinstellungen}
        />
      )}

      {ergebnis && (
        <div className="akte-arbeitsflaeche">
          <div className="akte-haupt">
            <Zitatbereich>
            <p className="zusammenfassung">
              {abgleichZusammenfassung(ergebnis)}
              {mitKi && inhaltlich.length > 0 &&
                `, dazu ${inhaltlich.length} ${inhaltlich.length === 1 ? "inhaltlicher Widerspruch" : "inhaltliche Widersprüche"}`}{" "}
              <ZitateSchalter />
            </p>
            {mitKi?.unvollstaendig && (
              <p className="hinweis">
                Unvollständig: Das Modell hat {mitKi.luecken_dokumente.length > 0
                  ? `in ${mitKi.luecken_dokumente.map((d) => d.dateiname).join(", ")} `
                  : ""}
                Teile unbrauchbar beantwortet. Was dort steht, fehlt. Das Ergebnis wurde nicht gespeichert; „Neu
                vergleichen“ versucht es erneut.
              </p>
            )}
            {abweichend.length === 0 && <p className="leer">Keine abweichenden Zahlen oder Daten gefunden.</p>}
            {abweichend.map(karte)}
            {mitKi && (
              <section className="vergleich-inhaltlich">
                <h3>Inhaltliche Widersprüche</h3>
                {inhaltlich.length === 0 ? (
                  <p className="leer">Keine inhaltlichen Widersprüche gefunden.</p>
                ) : (
                  inhaltlich.map((w, i) => <WiderspruchKarte key={i} w={w} offen={offen} onFundstelle={oeffne} />)
                )}
              </section>
            )}
            {verschieden.length > 0 && (
              <details className="weitere-merkmale">
                <summary>Abweichend, laut KI aber Verschiedenes gemeint ({verschieden.length})</summary>
                {verschieden.map(karte)}
              </details>
            )}
            {gleich.length > 0 && (
              <details className="weitere-merkmale">
                <summary>Übereinstimmend ({gleich.length})</summary>
                {gleich.map(karte)}
              </details>
            )}
            {einzeln.length > 0 && (
              <details className="weitere-merkmale">
                <summary>Nur in einem Dokument ({einzeln.length})</summary>
                {einzeln.map(karte)}
              </details>
            )}
            </Zitatbereich>
            <p className="grenze">
              {mitKi
                ? "Die KI kann Werte übersehen oder einem falschen Bezug zuordnen. Jeder Wert stammt aus dem Dokument, " +
                  "nicht aus der Antwort des Modells; was die Regeln zusätzlich finden, ist mit „Regel“ gekennzeichnet. " +
                  "Maßgeblich sind die Fundstellen."
                : "Die Regeln erkennen Werte nur hinter festen Merkmalswörtern (Kaufpreis, Übergabe, Kilometerstand …) " +
                  "und keine Aussagen ohne Zahl oder Datum. Das kann der Vergleich mit KI."}
            </p>
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

/** Zeile über dem Ergebnis: Vergleich mit KI oder regelbasiert, und warum. */
function KiZeile({
  ki,
  onNeu,
  onAbbrechen,
  onEinstellungen,
}: {
  ki: KiStand;
  onNeu: () => void;
  onAbbrechen: () => void;
  onEinstellungen?: () => void;
}) {
  const einstellungen = onEinstellungen && (
    <button className="link klein" onClick={onEinstellungen}>
      Einstellungen
    </button>
  );
  if (ki.art === "fertig") {
    const e = ki.ergebnis;
    return (
      <p className="ki-zeile bereit">
        Vergleich mit KI ({e.modell}), erstellt {zeitpunkt(e.erstellt_am)}.{" "}
        <button className="link klein" onClick={onNeu}>
          Neu vergleichen
        </button>
      </p>
    );
  }
  if (ki.art === "laeuft") {
    const a = ki.auftrag;
    return (
      <p className="ki-zeile" role="status">
        Regelbasiertes Ergebnis. Die KI vergleicht im Hintergrund
        {a.text ? `: ${a.text}` : " …"} ({a.sekunden} s){" "}
        <button className="link klein" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </p>
    );
  }
  if (ki.art === "pruefe") return <p className="ki-zeile">Regelbasiertes Ergebnis. Prüfe Sprachmodell …</p>;
  if (ki.art === "aus") {
    return (
      <p className="ki-zeile">
        Regelbasiert{" "}
        {ki.abgeschaltet ? "(KI ausgeschaltet)" : ki.hinweis ? `(${ki.hinweis})` : "(kein Sprachmodell eingerichtet)"}.{" "}
        {einstellungen}
      </p>
    );
  }
  if (ki.art === "extern") {
    return (
      <p className="ki-zeile">
        Regelbasiert. Als KI ist ein externer Anbieter gewählt; die Dokumenttexte gehen erst auf Knopfdruck hinaus.{" "}
        <button className="link klein" onClick={onNeu}>
          Mit externer KI vergleichen
        </button>
      </p>
    );
  }
  const grund =
    ki.art === "belegt"
      ? "Das Sprachmodell arbeitet gerade an einer anderen Aufgabe."
      : ki.art === "abgebrochen"
        ? "Vergleich mit KI abgebrochen."
        : `KI nicht erreichbar: ${ki.text}`;
  return (
    <p className="ki-zeile">
      Regelbasiert. {grund}{" "}
      <button className="link klein" onClick={onNeu}>
        Erneut mit KI versuchen
      </button>{" "}
      {ki.art === "fehler" && einstellungen}
    </p>
  );
}

function MerkmalKarte({
  merkmal,
  onFundstelle,
  offen,
  mitKi,
}: {
  merkmal: AbgleichMerkmal;
  onFundstelle: (f: AbgleichFundstelle) => void;
  offen: { inhalt: DokumentInhalt; abschnitt: number } | null;
  mitKi: boolean;
}) {
  return (
    <section className={`merkmal ${merkmal.status}`}>
      <header>
        <strong>{merkmal.titel}</strong>
        {mitKi && (
          <span
            className={`quelle-art ${merkmal.quelle ?? "regel"}`}
            title={merkmal.quelle === "ki" ? "Bezug von der KI erkannt" : "Nur von den Regeln gefunden"}
          >
            {merkmal.quelle === "ki" ? "KI" : "Regel"}
          </span>
        )}
        {merkmal.einordnung.map((e) => (
          <span key={e} className={`einordnung ${e}`}>
            {EINORDNUNG_TEXT[e]}
          </span>
        ))}
      </header>
      {merkmal.erklaerung && <p className="ki-erklaerung">Einschätzung des Modells: {merkmal.erklaerung}</p>}
      <div className="werte">
        {merkmal.werte.map((w) => {
          const bezuege = [...new Set(w.fundstellen.map((f) => f.bezug).filter((b): b is string => !!b))].filter(
            (b) => b !== merkmal.titel,
          );
          const regel = mitKi && merkmal.quelle === "ki" && w.fundstellen.some((f) => f.quelle === "regel");
          return (
            <div key={w.wert} className="wert">
              <div className="wert-anzeige">
                {w.anzeige}
                {bezuege.length > 0 && <div className="leise">{bezuege.join("; ")}</div>}
                {regel && <div className="leise">von den Regeln ergänzt</div>}
              </div>
              <ul className="belege">
                {w.fundstellen.map((f, i) => (
                  <Beleg
                    key={i}
                    f={f}
                    gewaehlt={offen?.inhalt.dokument.id === f.dokument_id && offen.abschnitt === f.abschnitt}
                    onFundstelle={() => onFundstelle(f)}
                    zusatz={
                      mitKi && (f.haltung || f.quelle === "regel") ? (
                        <span className="leise">
                          {" "}
                          {[f.haltung && f.haltung !== "behauptet" ? HALTUNG_TEXT[f.haltung] ?? f.haltung : "",
                            f.quelle === "regel" ? "Regel" : ""].filter(Boolean).join(" · ")}
                        </span>
                      ) : undefined
                    }
                  />
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
