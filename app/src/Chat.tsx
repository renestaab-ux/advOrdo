import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { DokumentAnsicht } from "./Akte";
import { FundstelleZeile, Offen } from "./Analyse";
import { Zitatbereich, ZitateSchalter } from "./Belege";
import {
  ChatAussage,
  ChatEintrag,
  DokumentInhalt,
  KiAuftrag,
  KiFundstelle,
  KiStatus,
  auswahlText,
  dauerText,
  kern,
  zeitpunkt,
} from "./kern";

const ART_TEXT: Record<ChatAussage["art"], string> = {
  tatsache: "Aus der Akte",
  einschaetzung: "Einschätzung des Modells",
  hinweis: "Hinweis",
};

/** Fragen an die ganze Akte oder an ein Dokument; jede Antwort mit Fundstellen, die die App am Originaltext prüft. */
export default function Chat({
  akteId,
  dokumentId = null,
  onEinstellungen,
}: {
  akteId: number;
  /** Ohne Dokument: Chat mit der ganzen Akte. */
  dokumentId?: number | null;
  onEinstellungen?: () => void;
}) {
  const [status, setStatus] = useState<KiStatus | null>(null);
  const [verlauf, setVerlauf] = useState<ChatEintrag[]>([]);
  const [eingabe, setEingabe] = useState("");
  const [gestellt, setGestellt] = useState<string | null>(null);
  const [auftrag, setAuftrag] = useState<KiAuftrag | null>(null);
  const [offen, setOffen] = useState<Offen>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const ende = useRef<HTMLDivElement>(null);
  const seite = useRef<HTMLDivElement>(null);

  const ladeVerlauf = useCallback(async () => {
    setVerlauf(await kern<ChatEintrag[]>("ki.chat_verlauf", { akte_id: akteId, dokument_id: dokumentId }));
  }, [akteId, dokumentId]);

  useEffect(() => {
    setVerlauf([]);
    setOffen(null);
    setFehler(null);
    void (async () => {
      try {
        await ladeVerlauf();
        setStatus(await kern<KiStatus>("ki.status"));
        const laufend = await kern<KiAuftrag | null>("ki.laufend");
        if (laufend?.aufgabe === "chat") setAuftrag(laufend);
      } catch (e) {
        setFehler(String(e));
      }
    })();
  }, [ladeVerlauf]);

  // Laufende Frage jede Sekunde abfragen; danach den Verlauf neu laden.
  const laeuft = auftrag?.status === "laeuft";
  useEffect(() => {
    if (!laeuft || !auftrag) return;
    const id = auftrag.auftrag_id;
    const takt = window.setInterval(async () => {
      try {
        const stand = await kern<KiAuftrag>("ki.auftrag", { auftrag_id: id });
        setAuftrag(stand);
        if (stand.status === "laeuft") return;
        if (stand.status === "fehler") {
          setFehler(stand.fehler);
          setEingabe((alt) => alt || gestellt || "");
        }
        setGestellt(null);
        await ladeVerlauf();
      } catch (e) {
        setFehler(String(e));
        setAuftrag(null);
      }
    }, 1000);
    return () => window.clearInterval(takt);
  }, [laeuft, auftrag?.auftrag_id, ladeVerlauf, gestellt]);

  useEffect(() => {
    ende.current?.scrollIntoView({ block: "nearest" });
  }, [verlauf.length, gestellt]);

  useEffect(() => {
    const leiste = seite.current;
    const ziel = offen && leiste?.querySelector(`#abschnitt-${offen.abschnitt}`);
    if (!leiste || !ziel) return;
    leiste.scrollTop += ziel.getBoundingClientRect().top - leiste.getBoundingClientRect().top - leiste.clientHeight / 3;
  }, [offen]);

  async function fragen() {
    const frage = eingabe.trim();
    if (!frage) return;
    setFehler(null);
    try {
      setAuftrag(await kern<KiAuftrag>("ki.chat_fragen", { akte_id: akteId, dokument_id: dokumentId, frage }));
      setGestellt(frage);
      setEingabe("");
    } catch (e) {
      setFehler(String(e));
    }
  }

  async function abbrechen() {
    if (auftrag) setAuftrag(await kern<KiAuftrag>("ki.abbrechen", { auftrag_id: auftrag.auftrag_id }));
  }

  async function leeren() {
    try {
      await kern("ki.chat_leeren", { akte_id: akteId, dokument_id: dokumentId });
      await ladeVerlauf();
      setOffen(null);
    } catch (e) {
      setFehler(String(e));
    }
  }

  async function oeffne(f: KiFundstelle) {
    try {
      const inhalt = await kern<DokumentInhalt>("akten.dokument", { dokument_id: f.dokument_id });
      setOffen({ inhalt, abschnitt: f.abschnitt });
    } catch (e) {
      setFehler(String(e));
    }
  }

  function taste(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Eingabetaste stellt die Frage, Umschalt+Eingabe macht eine neue Zeile.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!laeuft && bereit) void fragen();
    }
  }

  const bereit = status?.bereit ?? false;
  const gegenstand = dokumentId == null ? "der Akte" : "diesem Dokument";

  return (
    <div className={offen ? "chat mit-seite" : "chat"}>
      <div className="chat-haupt">
        <p className={status?.extern ? "ki-zeile extern" : bereit ? "ki-zeile bereit" : "ki-zeile"}>
          {status == null
            ? "Prüfe Sprachmodell …"
            : !bereit
              ? `Sprachmodell nicht bereit: ${status.hinweis ?? ""}`
              : status.extern
                ? `Externer Anbieter ${status.titel} (${status.modell}): Fragen und Dokumenttexte werden dorthin übertragen.`
                : `Sprachmodell ${status.modell} auf diesem Gerät. Nichts verlässt das Gerät.`}{" "}
          {onEinstellungen && (
            <button className="link klein" onClick={onEinstellungen}>
              Einstellungen
            </button>
          )}
        </p>

        <div className="chat-verlauf" aria-live="polite">
          {verlauf.length === 0 && !gestellt && (
            <p className="leer">
              Stelle eine Frage zu {gegenstand}, etwa „Wann wurde der Mangel gemeldet?“ oder „Was trägt die Beklagte
              zur Nacherfüllung vor?“. Die Antwort nennt zu jeder Tatsache die Fundstelle; ob das Zitat dort steht,
              prüft die App am Originaltext.
            </p>
          )}
          {verlauf.map((e) =>
            e.rolle === "frage" ? (
              <div key={e.id} className="chat-frage">
                {e.text}
              </div>
            ) : (
              <ChatAntwort key={e.id} eintrag={e} offen={offen} onFundstelle={oeffne} />
            ),
          )}
          {gestellt && <div className="chat-frage wartet">{gestellt}</div>}
          {laeuft && auftrag && (
            <div className="ki-fortschritt" role="status">
              <div>
                <strong>{auftrag.text}</strong> <span className="leise">· {dauerText(auftrag.sekunden)}</span>
              </div>
              <button className="zweitrangig" onClick={abbrechen}>
                Abbrechen
              </button>
            </div>
          )}
          {auftrag?.status === "abgebrochen" && <p className="meldung">Frage abgebrochen.</p>}
          <div ref={ende} />
        </div>

        {fehler && <p className="fehler">{fehler}</p>}
        <div className="chat-eingabe">
          <textarea
            value={eingabe}
            onChange={(e) => setEingabe(e.target.value)}
            onKeyDown={taste}
            rows={2}
            placeholder={`Frage zu ${gegenstand} … (Eingabe stellt die Frage, Umschalt+Eingabe für eine neue Zeile)`}
            aria-label={`Frage zu ${gegenstand}`}
          />
          <div className="aktionen">
            <button onClick={fragen} disabled={!bereit || laeuft || !eingabe.trim()}>
              Fragen
            </button>
            {verlauf.length > 0 && (
              <button className="zweitrangig" onClick={leeren} disabled={laeuft} title="Löscht die Fragen und Antworten dieses Chats">
                Verlauf leeren
              </button>
            )}
          </div>
        </div>
        <p className="grenze">
          Das Modell kann Stellen übersehen oder falsch verstehen. Maßgeblich sind die Fundstellen; „ohne Beleg“ heißt,
          das Zitat des Modells steht so nicht im Dokument.
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
  );
}

function ChatAntwort({
  eintrag,
  offen,
  onFundstelle,
}: {
  eintrag: ChatEintrag;
  offen: Offen;
  onFundstelle: (f: KiFundstelle) => void;
}) {
  const aussagen = eintrag.aussagen ?? [];
  return (
    <Zitatbereich>
      <div className="chat-antwort">
        {aussagen.length === 0 && <p className="leer">Das Modell hat keine Antwort geliefert.</p>}
        <ul className="chat-aussagen">
          {aussagen.map((a, i) => (
            <li key={i} className={`${a.status} chat-${a.art}`}>
              <div>
                {a.art !== "tatsache" && <span className="art">{ART_TEXT[a.art]}</span>} {a.text}
                {a.art === "tatsache" && a.status === "ohne_beleg" && <span className="ohne-beleg">ohne Beleg</span>}
              </div>
              {a.fundstellen.length > 0 && (
                <ul className="belege">
                  {a.fundstellen.map((f, j) => (
                    <FundstelleZeile key={j} f={f} offen={offen} onFundstelle={onFundstelle} />
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
        <p className="ki-herkunft chat-fuss">
          <span>
            {zeitpunkt(eintrag.erstellt_am)} · {eintrag.modell}
            {eintrag.extern ? ` über ${eintrag.extern} (extern)` : ", auf diesem Gerät"}
            {eintrag.auswahl && <> · Vorgelegt: {auswahlText(eintrag.auswahl)}</>}
          </span>
          {aussagen.some((a) => a.fundstellen.length > 0) && <ZitateSchalter />}
        </p>
      </div>
    </Zitatbereich>
  );
}
