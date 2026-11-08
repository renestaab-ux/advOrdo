import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { ProgrammArt, ProgrammEinstellung, kern, programmName } from "./kern";

type Programme = Record<ProgrammArt, ProgrammEinstellung>;

/** Einstellungen: mit welchem Programm PDFs und Word-Dateien außerhalb von advOrdo geöffnet werden. */
export default function Programme() {
  const [programme, setProgramme] = useState<Programme | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<Programme>("programme.einstellungen").then(setProgramme, (e) => setFehler(String(e)));
  }, []);

  async function setze(art: ProgrammArt, programm: string, parameter: string) {
    setFehler(null);
    try {
      setProgramme(await kern<Programme>("programme.setzen", { art, programm, parameter }));
    } catch (e) {
      setFehler(String(e));
    }
  }

  return (
    <section className="karte">
      <h2>Programme</h2>
      <p className="erklaerung">
        Mit „Öffnen“ und „Bearbeiten“ an einem Dokument übergibt advOrdo die Datei an diese Programme. Jedes Programm
        ist möglich, etwa LibreOffice, Microsoft Word oder ein PDF-Programm Ihrer Wahl. Die Einstellung gilt für dieses
        Gerät.
      </p>
      {programme &&
        (["pdf", "text"] as const).map((art) => (
          <ProgrammZeile key={art} art={art} e={programme[art]} onSetzen={(p, par) => setze(art, p, par)} />
        ))}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
    </section>
  );
}

function ProgrammZeile({
  art,
  e,
  onSetzen,
}: {
  art: ProgrammArt;
  e: ProgrammEinstellung;
  onSetzen: (programm: string, parameter: string) => void;
}) {
  const [eigenes, setEigenes] = useState(!!e.programm);
  const [parameter, setParameter] = useState(e.parameter);
  useEffect(() => {
    setEigenes(!!e.programm);
    setParameter(e.parameter);
  }, [e.programm, e.parameter]);

  async function waehlen() {
    const gewaehlt = await open({ title: `${e.titel} wählen`, multiple: false, directory: false });
    if (typeof gewaehlt === "string") onSetzen(gewaehlt, parameter);
  }

  return (
    <div className="programm-zeile">
      <label>
        {e.titel}
        <small className="leise">{art === "pdf" ? "PDF-Dateien" : "Word- und Textdateien"}</small>
        <select
          value={eigenes ? "eigenes" : "system"}
          onChange={(ev) => {
            if (ev.target.value === "system") {
              setEigenes(false);
              if (e.programm) onSetzen("", "");
            } else {
              setEigenes(true);
              if (!e.programm) void waehlen();
            }
          }}
        >
          <option value="system">Standardprogramm des Systems</option>
          <option value="eigenes">Eigenes Programm …</option>
        </select>
      </label>
      {eigenes && (
        <div className="programm-eigenes">
          <div className="programm-pfad">
            <span title={e.programm}>{e.programm ? programmName(e.programm) : "noch keins gewählt"}</span>
            <button className="zweitrangig" onClick={waehlen}>
              Wählen …
            </button>
          </div>
          {e.programm && <code className="programm-voll">{e.programm}</code>}
          <label>
            Aufrufparameter (optional)
            <input
              value={parameter}
              placeholder="z. B. --nologo"
              onChange={(ev) => setParameter(ev.target.value)}
              onBlur={() => parameter !== e.parameter && e.programm && onSetzen(e.programm, parameter)}
            />
            <small className="leise">„{"{datei}"}“ steht für die Datei; ohne den Platzhalter kommt sie ans Ende.</small>
          </label>
        </div>
      )}
    </div>
  );
}
