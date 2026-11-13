import { FormEvent, KeyboardEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { Rueckfrage } from "./Rueckfrage";
import { useFokusAuf } from "./barrierefrei";
import { Skill, SkillImport, SkillListe, istDesktop, kern } from "./kern";

const zahl = (n: number) => n.toLocaleString("de-DE");
const ALLE = "alle";
const ORDNER = "ordner:";
const OHNE_ORDNER = "Ohne Ordner";

/** Wo Skills gewählt werden; die Wahl gilt je Akte und wird auf dem Gerät gemerkt. */
export type SkillBereich = "chat" | "analyse";

function schluessel(bereich: SkillBereich, akteId: number | null) {
  return `skills.${bereich}.${akteId ?? "ohne"}`;
}

function gemerkteSkills(bereich: SkillBereich, akteId: number | null): string[] {
  try {
    const roh = localStorage.getItem(schluessel(bereich, akteId));
    if (roh) {
      const liste: unknown = JSON.parse(roh);
      if (Array.isArray(liste)) return liste.filter((x): x is string => typeof x === "string");
    }
    // Frühere Fassung: ein einzelner Skill je Akte.
    const alt = localStorage.getItem(`skill.${bereich}.${akteId ?? "ohne"}`);
    return alt ? [alt] : [];
  } catch {
    return [];
  }
}

/** Die gewählten Skills für Chat bzw. Analyse dieser Akte: Kennungen, „ordner:Name“ oder „alle“; leer = keine. */
export function useSkillWahl(bereich: SkillBereich, akteId: number | null): [string[], (auswahl: string[]) => void] {
  const [wert, setWert] = useState(() => gemerkteSkills(bereich, akteId));
  useEffect(() => setWert(gemerkteSkills(bereich, akteId)), [bereich, akteId]);
  const setze = useCallback(
    (auswahl: string[]) => {
      setWert(auswahl);
      try {
        if (auswahl.length) localStorage.setItem(schluessel(bereich, akteId), JSON.stringify(auswahl));
        else localStorage.removeItem(schluessel(bereich, akteId));
        localStorage.removeItem(`skill.${bereich}.${akteId ?? "ohne"}`);
      } catch {
        // ohne Speicher gilt die Wahl bis zum Neustart
      }
    },
    [bereich, akteId],
  );
  return [wert, setze];
}

/** Liegt der Skill in diesem Ordner oder einem Unterordner davon? */
function imOrdner(s: Skill, ordner: string) {
  return s.ordner === ordner || s.ordner.startsWith(`${ordner} / `);
}

/** Skills nach Ordnern, in der Reihenfolge des Kerns (Ordner alphabetisch, ohne Ordner zuletzt). */
function nachOrdnern(skills: Skill[]): [string, Skill[]][] {
  const gruppen = new Map<string, Skill[]>();
  for (const s of skills) {
    const liste = gruppen.get(s.ordner) ?? [];
    liste.push(s);
    gruppen.set(s.ordner, liste);
  }
  return [...gruppen.entries()];
}

/** Suchbegriffe: alle Wörter müssen in Name, Beschreibung oder Ordner vorkommen (Groß-/Kleinschreibung egal). */
function passtZurSuche(s: Skill, suche: string) {
  const woerter = suche.toLowerCase().split(/\s+/).filter(Boolean);
  if (!woerter.length) return true;
  const heu = `${s.name} ${s.beschreibung} ${s.ordner}`.toLowerCase().replace(/-/g, " ");
  return woerter.every((w) => heu.includes(w));
}

/** Kurztext der Auswahl für den Knopf, z. B. „Alle (passende je Frage)“ oder „3 gewählt“. */
export function auswahlText(auswahl: string[], skills: Skill[]): string {
  if (!auswahl.length) return "keine";
  if (auswahl.includes(ALLE)) return "Alle (passende je Frage)";
  if (auswahl.length === 1) {
    const a = auswahl[0];
    if (a.startsWith(ORDNER)) return `Ordner ${a.slice(ORDNER.length)}`;
    return skills.find((s) => s.id === a)?.name ?? "1 gewählt";
  }
  return `${auswahl.length} gewählt`;
}

/**
 * Auswahl der Skills in Chat und Analyse: ein Knopf öffnet eine Liste mit Suche, Ordnern und „Alle“. Mehrere
 * Skills, ganze Ordner oder alle lassen sich wählen; je Frage nimmt advOrdo davon die passendsten, so viele in das
 * Kontextfenster passen. Escape oder „Fertig“ schließt die Liste.
 */
export function SkillWahl({
  wert,
  onWert,
  disabled,
  onEinstellungen,
}: {
  wert: string[];
  onWert: (auswahl: string[]) => void;
  disabled?: boolean;
  onEinstellungen?: () => void;
}) {
  const [liste, setListe] = useState<SkillListe | null>(null);
  const [offen, setOffen] = useState(false);
  const [suche, setSuche] = useState("");
  const [aufgeklappt, setAufgeklappt] = useState<Set<string>>(new Set());
  const knopf = useRef<HTMLButtonElement>(null);
  const flaeche = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!istDesktop) return;
    let aktuell = true;
    kern<SkillListe>("skills.liste")
      .then((l) => aktuell && setListe(l))
      .catch(() => aktuell && setListe({ skills: [], kontext: null }));
    return () => {
      aktuell = false;
    };
  }, []);

  // Gelöschte Skills und Ordner sind keine gültige Wahl mehr.
  useEffect(() => {
    if (!liste) return;
    const gueltig = wert.filter(
      (a) =>
        a === ALLE ||
        (a.startsWith(ORDNER) ? liste.skills.some((s) => imOrdner(s, a.slice(ORDNER.length))) : liste.skills.some((s) => s.id === a)),
    );
    if (gueltig.length !== wert.length) onWert(gueltig);
  }, [liste, wert, onWert]);

  // Klick außerhalb schließt die Liste.
  useEffect(() => {
    if (!offen) return;
    function weg(e: MouseEvent) {
      const ziel = e.target as Node;
      if (!flaeche.current?.contains(ziel) && !knopf.current?.contains(ziel)) setOffen(false);
    }
    document.addEventListener("mousedown", weg);
    return () => document.removeEventListener("mousedown", weg);
  }, [offen]);

  const skills = liste?.skills ?? [];
  const gruppen = useMemo(() => nachOrdnern(skills.filter((s) => passtZurSuche(s, suche))), [skills, suche]);

  if (!liste) return null;
  if (skills.length === 0) {
    return onEinstellungen ? (
      <span className="skill-wahl leise">
        Skills: keine angelegt{" "}
        <button type="button" className="link klein" onClick={onEinstellungen}>
          Skills anlegen
        </button>
      </span>
    ) : null;
  }

  const alle = wert.includes(ALLE);
  const gewaehlt = new Set(wert);
  const kontext = liste.kontext;
  const grenze = kontext ? Math.max(1000, Math.floor(kontext / 4) * 3) : null;

  function schliessen() {
    setOffen(false);
    setSuche("");
    knopf.current?.focus();
  }

  function taste(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      schliessen();
    }
  }

  function umschalten(eintrag: string, an: boolean) {
    const rest = wert.filter((a) => a !== eintrag && a !== ALLE);
    onWert(an ? [...rest, eintrag] : rest);
  }

  function aufklappen(ordner: string) {
    const neu = new Set(aufgeklappt);
    if (neu.has(ordner)) neu.delete(ordner);
    else neu.add(ordner);
    setAufgeklappt(neu);
  }

  return (
    <span className="skill-wahl">
      <button
        type="button"
        ref={knopf}
        className="zweitrangig klein"
        aria-expanded={offen}
        aria-controls={`${id}-flaeche`}
        disabled={disabled}
        onClick={() => (offen ? schliessen() : setOffen(true))}
        title="Skills geben dem Sprachmodell Rolle und Vorgehen vor. Die Regeln von advOrdo (Belege aus der Akte) gelten weiter."
      >
        Skills: {auswahlText(wert, skills)} ▾
      </button>
      {offen && (
        <div
          className="skill-flaeche"
          id={`${id}-flaeche`}
          ref={flaeche}
          role="group"
          aria-label="Skills wählen"
          onKeyDown={taste}
        >
          <input
            type="search"
            value={suche}
            autoFocus
            placeholder="Skills suchen, z. B. Zugang oder 130"
            aria-label="Skills suchen"
            onChange={(e) => setSuche(e.target.value)}
          />
          <label className="skill-alle">
            <input type="checkbox" checked={alle} onChange={(e) => onWert(e.target.checked ? [ALLE] : [])} /> Alle
            Skills <span className="leise">(je Frage die passendsten)</span>
          </label>
          <div className="skill-gruppen">
            {gruppen.length === 0 && <p className="leise">Kein Skill passt zur Suche.</p>}
            {gruppen.map(([ordner, eintraege]) => {
              const name = ordner || OHNE_ORDNER;
              const ordnerGewaehlt = alle || (!!ordner && gewaehlt.has(ORDNER + ordner));
              const zeigen = suche.trim() !== "" || aufgeklappt.has(ordner) || gruppen.length === 1;
              const listeId = `${id}-o-${name}`;
              return (
                <div key={ordner} className="skill-gruppe">
                  <div className="skill-gruppe-kopf">
                    <button
                      type="button"
                      className="link"
                      aria-expanded={zeigen}
                      aria-controls={listeId}
                      onClick={() => aufklappen(ordner)}
                    >
                      {zeigen ? "▾" : "▸"} {name} ({zahl(eintraege.length)})
                    </button>
                    {ordner && (
                      <label className="leise">
                        <input
                          type="checkbox"
                          checked={ordnerGewaehlt}
                          disabled={alle}
                          onChange={(e) => umschalten(ORDNER + ordner, e.target.checked)}
                        />{" "}
                        ganzer Ordner
                      </label>
                    )}
                  </div>
                  {zeigen && (
                    <ul id={listeId}>
                      {eintraege.map((s) => (
                        <li key={s.id}>
                          <label title={s.beschreibung || undefined}>
                            <input
                              type="checkbox"
                              checked={ordnerGewaehlt || gewaehlt.has(s.id)}
                              disabled={ordnerGewaehlt || s.passt === false}
                              onChange={(e) => umschalten(s.id, e.target.checked)}
                            />{" "}
                            {s.name}
                            {s.passt === false && <span className="leise"> (zu lang für das Modell)</span>}
                          </label>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
          <p className="leise skill-erklaerung">
            Bei mehreren Skills, einem Ordner oder „Alle“ nimmt advOrdo je Frage die passendsten (nach Name, Überschriften
            und Beschreibung), höchstens fünf
            {grenze ? ` und zusammen bis etwa ${zahl(grenze)} Zeichen` : ""}. Passt keiner, gilt keiner. Unter der Antwort
            steht, welche gewirkt haben.
          </p>
          <div className="aktionen">
            <button type="button" onClick={schliessen}>
              Fertig
            </button>
            <button type="button" className="zweitrangig" disabled={!wert.length} onClick={() => onWert([])}>
              Keine
            </button>
            {onEinstellungen && (
              <button type="button" className="link klein" onClick={onEinstellungen}>
                Skills verwalten
              </button>
            )}
          </div>
        </div>
      )}
    </span>
  );
}

type Entwurf = { id: string | null; name: string; beschreibung: string; text: string; ordner: string };

/**
 * Einstellungen → Skills: eigene Skills anlegen und bearbeiten, Skills aus Claude oder ChatGPT importieren
 * (SKILL.md, ZIP, Ordner), in Ordnern ordnen, suchen, exportieren und löschen. Gilt für alle Arbeitsumgebungen
 * dieses Geräts.
 */
export default function SkillsEinstellungen() {
  const [liste, setListe] = useState<SkillListe | null>(null);
  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const [loeschen, setLoeschen] = useState<Skill | null>(null);
  const [ordnerLoeschen, setOrdnerLoeschen] = useState<{ ordner: string; anzahl: number } | null>(null);
  const [umbenennen, setUmbenennen] = useState<{ alt: string; neu: string } | null>(null);
  // Markierte Skills lassen sich gemeinsam löschen; ``alle`` fragt nach allen Skills.
  const [markiert, setMarkiert] = useState<Set<string>>(new Set());
  const [mehrereLoeschen, setMehrereLoeschen] = useState<{ ids: string[]; alle: boolean } | null>(null);
  const [suche, setSuche] = useState("");
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

  const skills = useMemo(() => liste?.skills ?? [], [liste]);
  const alleOrdner = useMemo(() => [...new Set(skills.map((s) => s.ordner).filter(Boolean))], [skills]);
  const gruppen = useMemo(() => nachOrdnern(skills.filter((s) => passtZurSuche(s, suche))), [skills, suche]);
  const angezeigt = useMemo(() => gruppen.flatMap(([, e]) => e.map((s) => s.id)), [gruppen]);
  const alleAngezeigtMarkiert = angezeigt.length > 0 && angezeigt.every((id) => markiert.has(id));

  // Gelöschte Skills fallen aus der Markierung.
  useEffect(() => {
    setMarkiert((m) => {
      const da = new Set(skills.map((s) => s.id));
      const rest = [...m].filter((id) => da.has(id));
      return rest.length === m.size ? m : new Set(rest);
    });
  }, [skills]);

  function markieren(ids: string[], an: boolean) {
    setMarkiert((m) => {
      const neu = new Set(m);
      for (const id of ids) {
        if (an) neu.add(id);
        else neu.delete(id);
      }
      return neu;
    });
  }

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
    const ordnerNamen = [...new Set(r.uebernommen.map((s) => s.ordner || OHNE_ORDNER))];
    const teile = [
      n === 0
        ? "Kein neuer Skill übernommen."
        : `${n === 1 ? "1 Skill" : `${zahl(n)} Skills`} übernommen, in ${
            ordnerNamen.length === 1 ? `den Ordner „${ordnerNamen[0]}“` : `die Ordner ${ordnerNamen.map((o) => `„${o}“`).join(", ")}`
          }.`,
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
        ordner: entwurf.ordner,
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

  async function mehrereLoeschenBestaetigt() {
    const m = mehrereLoeschen;
    setMehrereLoeschen(null);
    if (!m) return;
    const r = await mit(() => kern<{ geloescht: number }>("skills.loeschen", { skill_ids: m.ids }));
    if (r) {
      setMarkiert(new Set());
      await laden();
      setMeldung(`${r.geloescht === 1 ? "1 Skill" : `${zahl(r.geloescht)} Skills`} gelöscht.`);
    }
  }

  async function ordnerLoeschenBestaetigt() {
    const o = ordnerLoeschen;
    setOrdnerLoeschen(null);
    if (!o) return;
    const r = await mit(() => kern<{ geloescht: number }>("skills.ordner_loeschen", { ordner: o.ordner }));
    if (r) {
      await laden();
      setMeldung(
        `${o.ordner ? `Ordner „${o.ordner}“ mit` : ""} ${r.geloescht === 1 ? "1 Skill" : `${zahl(r.geloescht)} Skills`}${o.ordner ? "" : " ohne Ordner"} gelöscht.`.trim(),
      );
    }
  }

  async function umbenennenSpeichern(e: FormEvent) {
    e.preventDefault();
    const u = umbenennen;
    if (!u) return;
    const r = await mit(() => kern<{ geaendert: number }>("skills.ordner_umbenennen", { alt: u.alt, neu: u.neu }));
    if (!r) return;
    setUmbenennen(null);
    await laden();
    setMeldung(u.neu.trim() ? `Ordner „${u.alt}“ heißt jetzt „${u.neu.trim()}“.` : `Ordner „${u.alt}“ aufgelöst.`);
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
  const sucht = suche.trim() !== "";

  return (
    <div className="skills">
      <section className="karte">
        <h2>Skills</h2>
        <p className="leise">
          Ein Skill ist eine Arbeitsanweisung für das Sprachmodell: welche Rolle es einnimmt, wie es vorgeht und worauf
          es achtet, etwa „Lies den Schriftsatz wie die Gegenseite“ oder „Prüfe zuerst Fristen und Zuständigkeit“. Im
          Chat und in der Analyse einer Akte wählst du einen oder mehrere Skills, ganze Ordner oder alle; advOrdo nimmt
          dann je Frage die passendsten. Skills wirken bei lokaler und externer KI.
        </p>
        <p className="leise">
          Skills aus Claude oder ChatGPT lassen sich importieren: eine Datei <code>SKILL.md</code>, ein ZIP-Archiv oder
          ein Ordner mit vielen Skills. Jedes Paket kommt in einen eigenen Ordner, den du umbenennen kannst (Unterordner
          mit „/“, etwa „Zivilrecht / BGB AT“). Was ein Skill an Werkzeugen voraussetzt (Webseiten, Word-Dateien,
          weitere Dateien im Ordner), gibt es hier nicht; darauf weist die Liste hin. Die Regeln von advOrdo gehen immer
          vor: Tatsachen nur aus der Akte, jede Aussage mit Beleg.
        </p>
        <p className="leise">
          {kontext && grenze
            ? `Das aktive Sprachmodell hat ein Kontextfenster von ${zahl(kontext)} Token. Skills dürfen zusammen höchstens ein Viertel davon belegen, rund ${zahl(grenze)} Zeichen; der Rest bleibt für Dokumenttext und Antwort.`
            : "Ist ein Sprachmodell eingerichtet, zeigt die Liste, welche Skills in sein Kontextfenster passen."}
        </p>
        <div className="aktionen">
          <button
            disabled={laeuft || entwurf != null}
            onClick={() => setEntwurf({ id: null, name: "", beschreibung: "", text: "", ordner: "" })}
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
              Ordner <span className="leise">(leer = ohne Ordner, Unterordner mit „/“)</span>
              <input
                value={entwurf.ordner}
                maxLength={120}
                list="skill-ordner"
                onChange={(e) => setEntwurf({ ...entwurf, ordner: e.target.value })}
              />
              <datalist id="skill-ordner">
                {alleOrdner.map((o) => (
                  <option key={o} value={o} />
                ))}
              </datalist>
            </label>
            <label>
              Kurzbeschreibung <span className="leise">(wofür der Skill gedacht ist; hilft auch bei der Auswahl)</span>
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
            <p id="skill-laenge" className={grenze && entwurf.text.length > grenze ? "hinweis" : "leise"}>
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
        <h2>Angelegte Skills{liste ? ` (${zahl(skills.length)})` : ""}</h2>
        {loeschen && (
          <Rueckfrage
            frage={`Skill „${loeschen.name}“ löschen?`}
            erklaerung="Antworten und Analysen, die schon mit diesem Skill entstanden sind, bleiben erhalten."
            ja="Löschen"
            onJa={loeschenBestaetigt}
            onNein={() => setLoeschen(null)}
          />
        )}
        {ordnerLoeschen && (
          <Rueckfrage
            frage={`${ordnerLoeschen.ordner ? `Ordner „${ordnerLoeschen.ordner}“ mit` : "Alle"} ${ordnerLoeschen.anzahl === 1 ? "1 Skill" : `${zahl(ordnerLoeschen.anzahl)} Skills`}${ordnerLoeschen.ordner ? "" : " ohne Ordner"} löschen?`}
            erklaerung={`Gelöscht werden alle Skills ${ordnerLoeschen.ordner ? "in diesem Ordner und seinen Unterordnern" : "ohne Ordner"}. Antworten und Analysen, die schon mit ihnen entstanden sind, bleiben erhalten.`}
            ja="Ordner löschen"
            onJa={ordnerLoeschenBestaetigt}
            onNein={() => setOrdnerLoeschen(null)}
          />
        )}
        {mehrereLoeschen && (
          <Rueckfrage
            frage={
              mehrereLoeschen.alle
                ? `Wirklich alle ${zahl(mehrereLoeschen.ids.length)} Skills löschen?`
                : `${mehrereLoeschen.ids.length === 1 ? "1 markierten Skill" : `${zahl(mehrereLoeschen.ids.length)} markierte Skills`} löschen?`
            }
            erklaerung={
              mehrereLoeschen.alle
                ? "Gelöscht werden alle importierten und selbst angelegten Skills in allen Ordnern. Das lässt sich nicht rückgängig machen; exportiere vorher, was du behalten willst. Antworten und Analysen, die schon mit ihnen entstanden sind, bleiben erhalten."
                : "Antworten und Analysen, die schon mit diesen Skills entstanden sind, bleiben erhalten."
            }
            ja={mehrereLoeschen.alle ? "Alle löschen" : "Markierte löschen"}
            onJa={mehrereLoeschenBestaetigt}
            onNein={() => setMehrereLoeschen(null)}
          />
        )}
        {liste == null && !fehler && <p className="status" role="status">Lade Skills …</p>}
        {liste && skills.length === 0 && <p className="leise">Noch kein Skill angelegt oder importiert.</p>}
        {skills.length > 0 && (
          <input
            type="search"
            className="skill-suche"
            value={suche}
            placeholder="Skills suchen (Name, Beschreibung, Ordner)"
            aria-label="Skills suchen"
            onChange={(e) => setSuche(e.target.value)}
          />
        )}
        {skills.length > 0 && (
          <div className="aktionen skill-markierung">
            <label>
              <input
                type="checkbox"
                checked={alleAngezeigtMarkiert}
                disabled={angezeigt.length === 0}
                onChange={(e) => markieren(angezeigt, e.target.checked)}
              />{" "}
              {sucht ? "Alle Treffer markieren" : "Alle markieren"}
            </label>
            <span className="leise" aria-live="polite">
              {zahl(markiert.size)} markiert
            </span>
            <button
              className="zweitrangig gefahr klein"
              disabled={laeuft || markiert.size === 0}
              onClick={() => setMehrereLoeschen({ ids: [...markiert], alle: false })}
            >
              Markierte löschen
            </button>
            {markiert.size > 0 && (
              <button className="link klein" onClick={() => setMarkiert(new Set())}>
                Markierung aufheben
              </button>
            )}
            <button
              className="zweitrangig gefahr klein skill-alle-loeschen"
              disabled={laeuft}
              onClick={() => setMehrereLoeschen({ ids: skills.map((s) => s.id), alle: true })}
            >
              Alle Skills löschen …
            </button>
          </div>
        )}
        {sucht && gruppen.length === 0 && <p className="leise">Kein Skill passt zur Suche.</p>}
        {gruppen.map(([ordner, eintraege]) => {
          const name = ordner || OHNE_ORDNER;
          const gesamt = skills.filter((s) => s.ordner === ordner).length;
          return (
            <details key={ordner} className="skill-ordner" open={sucht || gruppen.length === 1}>
              <summary>
                <strong>{name}</strong>{" "}
                <span className="leise">
                  ({sucht ? `${zahl(eintraege.length)} von ${zahl(gesamt)}` : zahl(gesamt)})
                </span>
              </summary>
              {!ordner && (
                <div className="aktionen skill-ordner-aktionen">
                  <button
                    className="zweitrangig gefahr klein"
                    disabled={laeuft}
                    onClick={() => setOrdnerLoeschen({ ordner: "", anzahl: gesamt })}
                  >
                    Alle ohne Ordner löschen
                  </button>
                </div>
              )}
              {ordner && (
                <div className="aktionen skill-ordner-aktionen">
                  {umbenennen?.alt === ordner ? (
                    <form className="skill-umbenennen" onSubmit={umbenennenSpeichern}>
                      <input
                        value={umbenennen.neu}
                        autoFocus
                        maxLength={120}
                        aria-label={`Neuer Name für Ordner ${ordner}`}
                        onChange={(e) => setUmbenennen({ alt: ordner, neu: e.target.value })}
                        onKeyDown={(e) => e.key === "Escape" && setUmbenennen(null)}
                      />
                      <button type="submit" className="zweitrangig" disabled={laeuft}>
                        Umbenennen
                      </button>
                      <button type="button" className="link klein" onClick={() => setUmbenennen(null)}>
                        Abbrechen
                      </button>
                    </form>
                  ) : (
                    <>
                      <button
                        className="zweitrangig klein"
                        disabled={laeuft}
                        onClick={() => setUmbenennen({ alt: ordner, neu: ordner })}
                      >
                        Ordner umbenennen
                      </button>
                      <button
                        className="zweitrangig gefahr klein"
                        disabled={laeuft}
                        onClick={() => setOrdnerLoeschen({ ordner, anzahl: gesamt })}
                      >
                        Ordner löschen
                      </button>
                    </>
                  )}
                </div>
              )}
              <ul className="skill-liste">
                {eintraege.map((s) => (
                  <li key={s.id} className={markiert.has(s.id) ? "markiert" : undefined}>
                    <div className="skill-titel">
                      <input
                        type="checkbox"
                        checked={markiert.has(s.id)}
                        aria-label={`${s.name} markieren`}
                        onChange={(e) => markieren([s.id], e.target.checked)}
                      />
                      <h3>{s.name}</h3>
                    </div>
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
                        <summary>Hinweise ({s.hinweise.length + (s.nicht_uebernommen.length > 0 ? 1 : 0)})</summary>
                        <ul>
                          {s.hinweise.map((h) => (
                            <li key={h}>{h}</li>
                          ))}
                          {s.nicht_uebernommen.length > 0 && <li>Nicht übernommen: {s.nicht_uebernommen.join(", ")}</li>}
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
                          setEntwurf({
                            id: s.id,
                            name: s.name,
                            beschreibung: s.beschreibung ?? "",
                            text: s.text,
                            ordner: s.ordner,
                          })
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
            </details>
          );
        })}
      </section>
    </div>
  );
}
