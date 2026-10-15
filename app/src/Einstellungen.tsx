import { FormEvent, useEffect, useState } from "react";
import { KiStatus, groesseText, istDesktop, kern } from "./kern";

const KONTEXTE = [8192, 16384, 32768];

/** Einstellungen: welches lokale Sprachmodell die Analyse verwendet. */
export default function Einstellungen() {
  const [status, setStatus] = useState<KiStatus | null>(null);
  const [anbieter, setAnbieter] = useState("ollama");
  const [endpunkt, setEndpunkt] = useState("");
  const [modell, setModell] = useState("");
  const [kontext, setKontext] = useState(16384);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  function uebernehme(s: KiStatus) {
    setStatus(s);
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

  async function speichern(e: FormEvent) {
    e.preventDefault();
    setLaeuft(true);
    setFehler(null);
    try {
      uebernehme(await kern<KiStatus>("ki.einstellungen_setzen", { anbieter, endpunkt, modell, kontext }));
    } catch (err) {
      setFehler(String(err));
    } finally {
      setLaeuft(false);
    }
  }

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Einstellungen gibt es nur in der Desktop-App: <code>npm run tauri dev</code>
      </section>
    );
  }

  const installiert = status?.modelle ?? [];
  const gespeichert =
    status != null &&
    status.anbieter === anbieter &&
    status.endpunkt === endpunkt.trim().replace(/\/+$/, "") &&
    status.modell === modell &&
    status.kontext === kontext;

  return (
    <div className="einstellungen">
      <header className="kopf">
        <h1>Einstellungen</h1>
      </header>

      <section className="karte">
        <h2>Sprachmodell</h2>
        <p className="erklaerung">
          Modus <strong>nur lokal</strong>: Das Sprachmodell läuft auf diesem Gerät (Ollama oder LM Studio). Die App
          spricht nur mit Adressen auf diesem Gerät; Dokumentinhalte verlassen es nicht.
        </p>

        <form className="ki-formular" onSubmit={speichern}>
          <label>
            Programm
            <select
              value={anbieter}
              onChange={(e) => {
                setAnbieter(e.target.value);
                const vorgabe = status?.anbieter_liste.find((a) => a.id === e.target.value);
                if (vorgabe) setEndpunkt(vorgabe.endpunkt);
              }}
            >
              {(status?.anbieter_liste ?? [{ id: "ollama", titel: "Ollama", endpunkt: "" }]).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.titel}
                </option>
              ))}
            </select>
          </label>
          <label>
            Adresse
            <input value={endpunkt} onChange={(e) => setEndpunkt(e.target.value)} spellCheck={false} />
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
              <input value={modell} onChange={(e) => setModell(e.target.value)} placeholder={status?.empfohlen} spellCheck={false} />
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

        {laeuft && <p className="status">Prüfe …</p>}
        {fehler && <p className="fehler">{fehler}</p>}
        {status && !laeuft && (
          <p className={status.bereit ? "ki-zeile bereit" : "ki-zeile"}>
            {status.bereit
              ? `Bereit: ${status.modell} über ${status.anbieter_titel}.`
              : status.erreichbar
                ? status.hinweis
                : `${status.anbieter_titel} ist nicht erreichbar. ${status.hinweis ?? ""}`}
          </p>
        )}

        <details className="ki-anleitung" open={status != null && !status.erreichbar}>
          <summary>So richtest du Ollama unter Windows ein</summary>
          <ol>
            <li>
              In einer PowerShell: <code>winget install Ollama.Ollama</code> (oder den Installer von ollama.com). Ollama
              startet danach im Hintergrund, das Symbol erscheint unten rechts in der Taskleiste.
            </li>
            <li>
              Modell laden (einmalig, rund 9 GB): <code>ollama pull {status?.empfohlen ?? "qwen3:14b"}</code>. Es passt
              mit 16.384 Token Kontext in 16 GB Grafikspeicher.
            </li>
            <li>Hier „Erneut prüfen“, das Modell wählen und speichern.</li>
          </ol>
          <p className="leise">
            Ollama lauscht nur auf diesem Gerät (127.0.0.1:11434), solange man das nicht ausdrücklich ändert. Linux:{" "}
            <code>curl -fsSL https://ollama.com/install.sh | sh</code>, macOS: <code>brew install ollama</code>.
          </p>
        </details>
      </section>
    </div>
  );
}
