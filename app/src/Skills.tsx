import { FormEvent, useCallback, useEffect, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { Rueckfrage } from "./Rueckfrage";
import { useFokusAuf } from "./barrierefrei";
import { Skill, SkillImport, SkillListe, istDesktop, kern } from "./kern";

const zahl = (n: number) => n.toLocaleString("de-DE");

/** Wo ein Skill gewählt wird; die Wahl gilt je Akte und wird auf dem Gerät gemerkt. */
export type SkillBereich = "chat" | "analyse";

function schluessel(bereich: SkillBereich, akteId: number | null) {
  return `skill.${bereich}.${akteId ?? "ohne"}`;
}

function gemerkterSkill(bereich: SkillBereich, akteId: number | null): string {
  try {
    return localStorage.getItem(schluessel(bereich, akteId)) ?? "";
  } catch {
    return "";
  }
}

/** Der gewählte Skill (Kennung, leer = keiner) für Chat bzw. Analyse dieser Akte. */
export function useSkillWahl(bereich: SkillBereich, akteId: number | null): [string, (id: string) => void] {
  const [wert, setWert] = useState(() => gemerkterSkill(bereich, akteId));
  useEffect(() => setWert(gemerkterSkill(bereich, akteId)), [bereich, akteId]);
  const setze = useCallback(
    (id: string) => {
      setWert(id);
      try {
        if (id) localStorage.setItem(schluessel(bereich, akteId), id);
        else localStorage.removeItem(schluessel(bereich, akteId));
      } catch {
        // ohne Speicher gilt die Wahl bis zum Neustart
      }
    },
    [bereich, akteId],
  );
  return [wert, setze];
}

/**
 * Auswahl „Skill: keiner / …“ in Chat und Analyse. Ohne angelegte Skills erscheint nur ein Verweis auf die
 * Einstellungen. Skills, die nicht in das Kontextfenster des Modells passen, sind nicht wählbar.
 */
export function SkillWahl({
  wert,
  onWert,
  disabled,
  onEinstellungen,
}: {
  wert: string;
  onWert: (id: string) => void;
  disabled?: boolean;
  onEinstellungen?: () => void;
}) {
  const [liste, setListe] = useState<Skill[] | null>(null);
  useEffect(() => {
    if (!istDesktop) return;
    let aktuell = true;
    kern<SkillListe>("skills.liste")
      .then((l) => aktuell && setListe(l.skills))
      .catch(() => aktuell && setListe([]));
    return () => {
      aktuell = false;
    };
  }, []);
  // Ein gelöschter Skill ist keine gültige Wahl mehr.
  useEffect(() => {
    if (liste && wert && !liste.some((s) => s.id === wert)) onWert("");
  }, [liste, wert, onWert]);

  if (!liste) return null;
  if (liste.length === 0) {
    return onEinstellungen ? (
      <span className="skill-wahl leise">
        Skill: keiner angelegt{" "}
        <button type="button" className="link klein" onClick={onEinstellungen}>
          Skills anlegen
        </button>
      </span>
    ) : null;
  }
  const gewaehlt = liste.find((s) => s.id === wert);
  return (
    <label
      className="skill-wahl"
      title={
        gewaehlt?.beschreibung ||
        "Ein Skill gibt dem Sprachmodell Rolle und Vorgehen vor. Die Regeln von advOrdo (Belege aus der Akte) gelten weiter."
      }
    >
      Skill:{" "}
      <select value={wert} disabled={disabled} onChange={(e) => onWert(e.target.value)}>
        <option value="">keiner</option>
        {liste.map((s) => (
          <option key={s.id} value={s.id} disabled={s.passt === false}>
            {s.name}
            {s.passt === false ? " (zu lang für das Modell)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

type Entwurf = { id: string | null; name: string; beschreibung: string; text: string };

/**
 * Einstellungen → Skills: eigene Skills anlegen und bearbeiten, Skills aus Claude oder ChatGPT importieren
 * (SKILL.md, ZIP, Ordner), exportieren und löschen. Gilt für alle Arbeitsumgebungen dieses Geräts.
 */
export default function SkillsEinstellungen() {
  const [liste, setListe] = useState<SkillListe | null>(null);
  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const [loeschen, setLoeschen] = useState<Skill | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  // Nach einem Dateidialog liest die Sprachausgabe eine Statusmeldung nur vor, wenn sie den Fokus bekommt.
  const meldungRef = useFokusAuf<HTMLParagraphElement>(meldung);

  const laden = useCallback(async () => {
    setListe(await kern<SkillListe>("skills.liste"));
  }, []);

  useEffect(() => {
    if (istDesktop) void laden().catch((e) => setFehler(String(e)));
  }, [laden]);

  async function mit<T>(f: () => Promise<T>): Promise<T | undefined> {
    setFehler(null);
    setMeldung(null);
    setLaeuft(true);
    try {
      return await f();
    } catch (e) {
      setFehler(String(e));
      return undefined;
    } finally {
      setLaeuft(false);
    }
  }

  async function importieren(ordner: boolean) {
    const pfad = await open(
      ordner
        ? { title: "Ordner mit Skills importieren", directory: true, multiple: false }
        : {
            title: "Skill importieren",
            multiple: false,
            filters: [{ name: "Skill (SKILL.md, Markdown oder ZIP)", extensions: ["md", "markdown", "txt", "zip"] }],
          },
    );
    if (typeof pfad !== "string") return;
    const r = await mit(() => kern<SkillImport>("skills.importieren", { pfad }));
    if (!r) return;
    await laden();
    const n = r.uebernommen.length;
    const teile = [
      n === 0
        ? "Kein neuer Skill übernommen."
        : `${n === 1 ? "1 Skill" : `${zahl(n)} Skills`} übernommen: ${r.uebernommen
            .slice(0, 8)
            .map((s) => s.name)
            .join(", ")}${n > 8 ? " …" : ""}.`,
    ];
    if (r.uebersprungen.length) {
      const vorhanden = r.uebersprungen.filter((u) => u.grund === "schon vorhanden").length;
      const andere = r.uebersprungen.filter((u) => u.grund !== "schon vorhanden");
      if (vorhanden) teile.push(`${zahl(vorhanden)} schon vorhanden.`);
      if (andere.length)
        teile.push(
          `Übersprungen: ${andere
            .slice(0, 5)
            .map((u) => `${u.datei} (${u.grund})`)
            .join("; ")}${andere.length > 5 ? " …" : ""}.`,
        );
    }
    setMeldung(teile.join(" "));
  }

  async function exportieren(s: Skill) {
    const ziel = await save({
      title: `Skill „${s.name}“ exportieren`,
      defaultPath: "SKILL.md",
      filters: [{ name: "Skill (Markdown)", extensions: ["md"] }],
    });
    if (!ziel) return;
    const r = await mit(() => kern<{ pfad: string }>("skills.exportieren", { skill_id: s.id, pfad: ziel }));
    if (r) setMeldung(`Gespeichert unter ${r.pfad}`);
  }

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!entwurf) return;
    const r = await mit(() =>
      kern<Skill>("skills.speichern", {
        name: entwurf.name,
        beschreibung: entwurf.beschreibung,
        text: entwurf.text,
        skill_id: entwurf.id,
      }),
    );
    if (!r) return;
    setEntwurf(null);
    await laden();
    setMeldung(`Skill „${r.name}“ gespeichert.`);
  }

  async function loeschenBestaetigt() {
    const s = loeschen;
    setLoeschen(null);
    if (!s) return;
    if (await mit(() => kern("skills.loeschen", { skill_id: s.id }))) {
      await laden();
      setMeldung(`Skill „${s.name}“ gelöscht.`);
    }
  }

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Skills gibt es nur in der Desktop-App: <code>npm run tauri dev</code>
      </section>
    );
  }

  const kontext = liste?.kontext ?? null;
  const grenze = kontext ? Math.max(1000, Math.floor(kontext / 4) * 3) : null;

  return (
    <div className="skills">
      <section className="karte">
        <h2>Skills</h2>
        <p className="leise">
          Ein Skill ist eine Arbeitsanweisung für das Sprachmodell: welche Rolle es einnimmt, wie es vorgeht und worauf
          es achtet, etwa „Lies den Schriftsatz wie die Gegenseite“ oder „Prüfe zuerst Fristen und Zuständigkeit“. Im
          Chat und in der Analyse einer Akte wählst du, welcher Skill gilt. Er wirkt bei lokaler und externer KI.
        </p>
        <p className="leise">
          Skills aus Claude oder ChatGPT lassen sich importieren: eine Datei <code>SKILL.md</code>, ein ZIP-Archiv oder
          ein Ordner mit vielen Skills. advOrdo übernimmt Name, Beschreibung und Anweisung. Was ein Skill an Werkzeugen
          voraussetzt (Webseiten, Word-Dateien, weitere Dateien im Ordner), gibt es hier nicht; darauf weist die Liste
          hin. Die Regeln von advOrdo gehen immer vor: Tatsachen nur aus der Akte, jede Aussage mit Beleg.
        </p>
        <p className="leise">
          {kontext && grenze
            ? `Das aktive Sprachmodell hat ein Kontextfenster von ${zahl(kontext)} Token. Ein Skill darf höchstens ein Viertel davon belegen, rund ${zahl(grenze)} Zeichen; der Rest bleibt für Dokumenttext und Antwort.`
            : "Ist ein Sprachmodell eingerichtet, zeigt die Liste, welche Skills in sein Kontextfenster passen."}
        </p>
        <div className="aktionen">
          <button
            disabled={laeuft || entwurf != null}
            onClick={() => setEntwurf({ id: null, name: "", beschreibung: "", text: "" })}
          >
            Neuer Skill
          </button>
          <button className="zweitrangig" disabled={laeuft} onClick={() => importieren(false)}>
            Datei importieren …
          </button>
          <button className="zweitrangig" disabled={laeuft} onClick={() => importieren(true)}>
            Ordner importieren …
          </button>
        </div>
        {meldung && (
          <p className="status" role="status" tabIndex={-1} ref={meldungRef}>
            {meldung}
          </p>
        )}
        {fehler && <p className="fehler" role="alert">{fehler}</p>}
      </section>

      {entwurf && (
        <section className="karte skill-entwurf">
          <h2>{entwurf.id ? "Skill bearbeiten" : "Neuer Skill"}</h2>
          <form onSubmit={speichern}>
            <label>
              Name
              <input
                value={entwurf.name}
                maxLength={80}
                autoFocus
                onChange={(e) => setEntwurf({ ...entwurf, name: e.target.value })}
              />
            </label>
            <label>
              Kurzbeschreibung <span className="leise">(wofür der Skill gedacht ist)</span>
              <input
                value={entwurf.beschreibung}
                maxLength={400}
                onChange={(e) => setEntwurf({ ...entwurf, beschreibung: e.target.value })}
              />
            </label>
            <label>
              Anweisung an das Sprachmodell
              <textarea
                value={entwurf.text}
                rows={14}
                aria-describedby="skill-laenge"
                onChange={(e) => setEntwurf({ ...entwurf, text: e.target.value })}
                placeholder={
                  "z. B.\nDu liest jeden Schriftsatz aus Sicht der Gegenseite.\n1. Welche Tatsachen sind bestritten?\n2. Wo fehlt ein Beweisangebot?"
                }
              />
            </label>
            <p
              id="skill-laenge"
              className={grenze && entwurf.text.length > grenze ? "hinweis" : "leise"}
            >
              {zahl(entwurf.text.trim().length)} Zeichen
              {grenze &&
                (entwurf.text.trim().length > grenze
                  ? `, zu lang für das aktive Sprachmodell (höchstens ${zahl(grenze)})`
                  : `, höchstens ${zahl(grenze)} für das aktive Sprachmodell`)}
            </p>
            <div className="aktionen">
              <button type="submit" disabled={laeuft || !entwurf.name.trim() || !entwurf.text.trim()}>
                Speichern
              </button>
              <button type="button" className="zweitrangig" onClick={() => setEntwurf(null)}>
                Abbrechen
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="karte">
        <h2>Angelegte Skills{liste ? ` (${zahl(liste.skills.length)})` : ""}</h2>
        {loeschen && (
          <Rueckfrage
            frage={`Skill „${loeschen.name}“ löschen?`}
            erklaerung="Antworten und Analysen, die schon mit diesem Skill entstanden sind, bleiben erhalten."
            ja="Löschen"
            onJa={loeschenBestaetigt}
            onNein={() => setLoeschen(null)}
          />
        )}
        {liste == null && !fehler && <p className="status" role="status">Lade Skills …</p>}
        {liste && liste.skills.length === 0 && <p className="leise">Noch kein Skill angelegt oder importiert.</p>}
        {liste && liste.skills.length > 0 && (
          <ul className="skill-liste">
            {liste.skills.map((s) => (
              <li key={s.id}>
                <h3>{s.name}</h3>
                {s.beschreibung && <p>{s.beschreibung}</p>}
                <p className="leise">
                  {s.herkunft} · {zahl(s.zeichen)} Zeichen
                  {s.passt === false && (
                    <span className="hinweis">
                      {" "}
                      · zu lang für das aktive Sprachmodell (höchstens {zahl(s.hoechstens ?? 0)})
                    </span>
                  )}
                </p>
                {(s.hinweise.length > 0 || s.nicht_uebernommen.length > 0) && (
                  <details className="skill-hinweise">
                    <summary>
                      Hinweise ({s.hinweise.length + (s.nicht_uebernommen.length > 0 ? 1 : 0)})
                    </summary>
                    <ul>
                      {s.hinweise.map((h) => (
                        <li key={h}>{h}</li>
                      ))}
                      {s.nicht_uebernommen.length > 0 && (
                        <li>Nicht übernommen: {s.nicht_uebernommen.join(", ")}</li>
                      )}
                    </ul>
                  </details>
                )}
                <details className="skill-text">
                  <summary>Anweisung ansehen</summary>
                  <pre>{s.text}</pre>
                </details>
                <div className="aktionen">
                  <button
                    className="zweitrangig"
                    disabled={laeuft || entwurf != null}
                    onClick={() =>
                      setEntwurf({ id: s.id, name: s.name, beschreibung: s.beschreibung ?? "", text: s.text })
                    }
                  >
                    Bearbeiten
                  </button>
                  <button className="zweitrangig" disabled={laeuft} onClick={() => exportieren(s)}>
                    Exportieren …
                  </button>
                  <button className="zweitrangig gefahr" disabled={laeuft} onClick={() => setLoeschen(s)}>
                    Löschen
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
