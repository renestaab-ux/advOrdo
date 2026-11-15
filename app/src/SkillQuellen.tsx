import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Rueckfrage } from "./Rueckfrage";
import { useFokusAuf } from "./barrierefrei";
import { SkillImport, SkillQuelle, SkillQuellenPaket, istDesktop, kern, kernImHintergrund } from "./kern";

const zahl = (n: number) => n.toLocaleString("de-DE");
const ANZEIGEN = 50; // so viele Pakete je Quelle, bis „weitere anzeigen“ oder eine Suche

function datum(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

function passt(text: string, suche: string) {
  const s = suche.trim().toLowerCase();
  return !s || text.toLowerCase().includes(s);
}

/** Ein geöffnetes Paket: seine Skills und welche davon zum Import markiert sind. */
interface Offen {
  inhalt: SkillQuellenPaket | null;
  markiert: Set<string>;
  suche: string;
}

function importText(r: SkillImport): string {
  const neu = r.uebernommen.length;
  const akt = r.aktualisiert?.length ?? 0;
  const ordner = [...new Set(r.uebernommen.map((s) => s.ordner).filter(Boolean))];
  const teile: string[] = [];
  if (neu) {
    teile.push(
      `${neu === 1 ? "1 Skill" : `${zahl(neu)} Skills`} übernommen${
        ordner.length === 1 ? ` in den Ordner „${ordner[0]}“` : ""
      }.`,
    );
  }
  if (akt) teile.push(`${akt === 1 ? "1 Skill" : `${zahl(akt)} Skills`} aktualisiert.`);
  if (!neu && !akt) teile.push("Kein Skill neu übernommen.");
  if (r.uebersprungen.length) {
    const gruende = [...new Set(r.uebersprungen.map((u) => u.grund))];
    teile.push(`${zahl(r.uebersprungen.length)} übersprungen (${gruende.join("; ")}).`);
  }
  return teile.join(" ");
}

/**
 * Quellen für Skills: öffentliche GitHub-Repositorys. advOrdo lädt nur das Verzeichnis und die angeklickten Skills;
 * die Netzzugriffe laufen im Kern als Hintergrundauftrag und stehen im Netzprotokoll.
 */
export default function SkillQuellen({ onImportiert }: { onImportiert: () => Promise<void> | void }) {
  const [quellen, setQuellen] = useState<SkillQuelle[] | null>(null);
  const [adresse, setAdresse] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [entfernen, setEntfernen] = useState<SkillQuelle | null>(null);
  const [suche, setSuche] = useState<Record<string, string>>({});
  const [alleZeigen, setAlleZeigen] = useState<Set<string>>(new Set());
  const [offen, setOffen] = useState<Record<string, Offen>>({});
  const meldungRef = useFokusAuf<HTMLParagraphElement>(meldung);

  const laden = useCallback(async () => {
    setQuellen((await kern<{ quellen: SkillQuelle[] }>("skills.quellen")).quellen);
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
      setFehler(String(e instanceof Error ? e.message : e));
      return undefined;
    } finally {
      setLaeuft(false);
    }
  }

  async function anbinden(e: FormEvent) {
    e.preventDefault();
    const q = await mit(() => kernImHintergrund<SkillQuelle>("skills.quelle_anbinden", { adresse: adresse.trim() }));
    if (!q) return;
    setAdresse("");
    await laden();
    setMeldung(`Quelle „${q.titel}“ angebunden: ${zahl(q.pakete.length)} ${q.pakete.length === 1 ? "Paket" : "Pakete"}.`);
  }

  async function aktualisieren(q: SkillQuelle) {
    const neu = await mit(() => kernImHintergrund<SkillQuelle>("skills.quelle_aktualisieren", { quelle_id: q.id }));
    if (!neu) return;
    setOffen((o) => Object.fromEntries(Object.entries(o).filter(([k]) => !k.startsWith(`${q.id}|`))));
    await laden();
    setMeldung(`Verzeichnis von „${neu.titel}“ neu geladen.`);
  }

  async function entfernenBestaetigt() {
    const q = entfernen;
    setEntfernen(null);
    if (!q) return;
    if (await mit(() => kern("skills.quelle_entfernen", { quelle_id: q.id }))) {
      await laden();
      setMeldung(`Quelle „${q.titel}“ entfernt. Schon übernommene Skills bleiben.`);
    }
  }

  async function paketOeffnen(q: SkillQuelle, pfad: string) {
    const schluessel = `${q.id}|${pfad}`;
    if (offen[schluessel]) {
      setOffen(({ [schluessel]: _, ...rest }) => rest);
      return;
    }
    setOffen((o) => ({ ...o, [schluessel]: { inhalt: null, markiert: new Set(), suche: "" } }));
    const inhalt = await mit(() =>
      kernImHintergrund<SkillQuellenPaket>("skills.quelle_paket", { quelle_id: q.id, pfad }),
    );
    if (!inhalt) {
      setOffen(({ [schluessel]: _, ...rest }) => rest);
      return;
    }
    setOffen((o) => ({ ...o, [schluessel]: { ...(o[schluessel] ?? { markiert: new Set(), suche: "" }), inhalt } }));
    if (inhalt.skills.length === 0) setMeldung(`Im Paket „${inhalt.name}“ wurde kein Skill gefunden.`);
    void laden();
  }

  function setzeOffen(schluessel: string, f: (o: Offen) => Offen) {
    setOffen((alt) => (alt[schluessel] ? { ...alt, [schluessel]: f(alt[schluessel]) } : alt));
  }

  async function importieren(q: SkillQuelle, schluessel: string, pfade: string[]) {
    const r = await mit(() =>
      kernImHintergrund<SkillImport>("skills.quelle_importieren", { quelle_id: q.id, pfade }),
    );
    if (!r) return;
    await onImportiert();
    const pfad = schluessel.slice(q.id.length + 1);
    const inhalt = await kernImHintergrund<SkillQuellenPaket>("skills.quelle_paket", { quelle_id: q.id, pfad }).catch(
      () => null,
    );
    setzeOffen(schluessel, (o) => ({ ...o, inhalt: inhalt ?? o.inhalt, markiert: new Set() }));
    setMeldung(importText(r));
  }

  const gezeigt = useMemo(
    () =>
      (quellen ?? []).map((q) => {
        const s = suche[q.id] ?? "";
        const treffer = q.pakete.filter((p) => passt(`${p.name} ${p.beschreibung}`, s));
        return { q, treffer, sichtbar: alleZeigen.has(q.id) || s.trim() ? treffer : treffer.slice(0, ANZEIGEN) };
      }),
    [quellen, suche, alleZeigen],
  );

  if (!istDesktop) return null;

  return (
    <section className="karte skill-quellen">
      <h2>Quellen</h2>
      <p className="leise">
        Eine Quelle ist ein öffentliches GitHub-Repository mit Skills, etwa eine Sammlung für deutsches Recht. advOrdo
        lädt daraus nur das Verzeichnis und die Skills, die du auswählst; jedes Paket kommt in einen eigenen Ordner. Aus
        deinen Akten wird dabei nichts gesendet, nur welches Repository und welche Datei gemeint ist (siehe
        Netzprotokoll). Ohne Anmeldung erlaubt GitHub rund 60 Verzeichnisabfragen pro Stunde; geladene Verzeichnisse
        merkt sich advOrdo.
      </p>
      <form className="skill-quelle-neu" onSubmit={anbinden}>
        <label>
          Adresse eines GitHub-Repositorys
          <input
            value={adresse}
            inputMode="url"
            spellCheck={false}
            autoCapitalize="off"
            placeholder="https://github.com/besitzer/sammlung"
            onChange={(e) => setAdresse(e.target.value)}
          />
        </label>
        <button type="submit" disabled={laeuft || !adresse.trim()}>
          Quelle anbinden
        </button>
      </form>
      {meldung && (
        <p className="status" role="status" tabIndex={-1} ref={meldungRef}>
          {meldung}
        </p>
      )}
      {fehler && (
        <p className="fehler" role="alert">
          {fehler}
        </p>
      )}
      {entfernen && (
        <Rueckfrage
          frage={`Quelle „${entfernen.titel}“ entfernen?`}
          erklaerung="Die schon übernommenen Skills bleiben erhalten; sie lassen sich danach nur nicht mehr aus der Quelle aktualisieren, bis du sie wieder anbindest."
          ja="Entfernen"
          onJa={entfernenBestaetigt}
          onNein={() => setEntfernen(null)}
        />
      )}
      {quellen && quellen.length === 0 && <p className="leise">Noch keine Quelle angebunden.</p>}
      {gezeigt.map(({ q, treffer, sichtbar }) => (
        <details key={q.id} className="skill-ordner skill-quelle" open={quellen?.length === 1}>
          <summary>
            <strong>{q.titel}</strong>{" "}
            <span className="leise">
              ({zahl(q.pakete.length)} {q.pakete.length === 1 ? "Paket" : "Pakete"})
            </span>
          </summary>
          {q.beschreibung && <p>{q.beschreibung}</p>}
          <p className="leise">
            {q.adresse} · Zweig {q.zweig} · Verzeichnis vom {datum(q.geladen_am)}
          </p>
          {q.hinweis && <p className="hinweis">{q.hinweis}</p>}
          <div className="aktionen skill-ordner-aktionen">
            <button className="zweitrangig klein" disabled={laeuft} onClick={() => aktualisieren(q)}>
              Verzeichnis aktualisieren
            </button>
            <button className="zweitrangig gefahr klein" disabled={laeuft} onClick={() => setEntfernen(q)}>
              Quelle entfernen
            </button>
          </div>
          {q.pakete.length > 5 && (
            <input
              type="search"
              className="skill-suche"
              value={suche[q.id] ?? ""}
              placeholder="Pakete suchen (Name, Beschreibung)"
              aria-label={`Pakete in ${q.titel} suchen`}
              onChange={(e) => setSuche({ ...suche, [q.id]: e.target.value })}
            />
          )}
          {treffer.length === 0 && <p className="leise">Kein Paket passt zur Suche.</p>}
          <ul className="skill-liste skill-pakete">
            {sichtbar.map((p) => {
              const schluessel = `${q.id}|${p.pfad}`;
              const o = offen[schluessel];
              return (
                <li key={p.pfad}>
                  <h3>{p.name}</h3>
                  {p.beschreibung && <p>{p.beschreibung}</p>}
                  <p className="leise">
                    {p.pfad || "Hauptordner"}
                    {p.anzahl != null && ` · ${p.anzahl === 1 ? "1 Skill" : `${zahl(p.anzahl)} Skills`}`}
                  </p>
                  <div className="aktionen">
                    <button
                      className="zweitrangig klein"
                      aria-expanded={!!o}
                      disabled={laeuft && !o}
                      onClick={() => paketOeffnen(q, p.pfad)}
                    >
                      {o ? "Skills ausblenden" : "Skills anzeigen"}
                    </button>
                  </div>
                  {o && !o.inhalt && (
                    <p className="status" role="status">
                      Lade die Skills des Pakets …
                    </p>
                  )}
                  {o?.inhalt && o.inhalt.skills.length > 0 && (
                    <PaketSkills
                      offen={o}
                      laeuft={laeuft}
                      onOffen={(f) => setzeOffen(schluessel, f)}
                      onImport={(pfade) => importieren(q, schluessel, pfade)}
                    />
                  )}
                </li>
              );
            })}
          </ul>
          {sichtbar.length < treffer.length && (
            <button className="link klein" onClick={() => setAlleZeigen(new Set(alleZeigen).add(q.id))}>
              Weitere {zahl(treffer.length - sichtbar.length)} Pakete anzeigen
            </button>
          )}
        </details>
      ))}
    </section>
  );
}

function PaketSkills({
  offen,
  laeuft,
  onOffen,
  onImport,
}: {
  offen: Offen;
  laeuft: boolean;
  onOffen: (f: (o: Offen) => Offen) => void;
  onImport: (pfade: string[]) => void;
}) {
  const skills = offen.inhalt?.skills ?? [];
  const sichtbar = skills.filter((s) => passt(s.name, offen.suche));
  const alleMarkiert = sichtbar.length > 0 && sichtbar.every((s) => offen.markiert.has(s.pfad));
  const n = offen.markiert.size;

  function markieren(pfade: string[], an: boolean) {
    onOffen((o) => {
      const neu = new Set(o.markiert);
      for (const p of pfade) {
        if (an) neu.add(p);
        else neu.delete(p);
      }
      return { ...o, markiert: neu };
    });
  }

  return (
    <div className="skill-paket">
      {skills.length > 8 && (
        <input
          type="search"
          className="skill-suche"
          value={offen.suche}
          placeholder="Skills im Paket suchen"
          aria-label={`Skills in ${offen.inhalt?.name ?? "diesem Paket"} suchen`}
          onChange={(e) => {
            const suche = e.target.value;
            onOffen((o) => ({ ...o, suche }));
          }}
        />
      )}
      <div className="aktionen skill-markierung">
        <label>
          <input
            type="checkbox"
            checked={alleMarkiert}
            disabled={sichtbar.length === 0}
            onChange={(e) => markieren(sichtbar.map((s) => s.pfad), e.target.checked)}
          />{" "}
          {offen.suche.trim() ? "Alle Treffer markieren" : "Alle markieren"}
        </label>
        <button disabled={laeuft || n === 0} onClick={() => onImport([...offen.markiert])}>
          {n === 0 ? "Markierte importieren" : `${n === 1 ? "1 Skill" : `${zahl(n)} Skills`} importieren`}
        </button>
      </div>
      <ul className="skill-quellen-skills">
        {sichtbar.map((s) => (
          <li key={s.pfad}>
            <label>
              <input
                type="checkbox"
                checked={offen.markiert.has(s.pfad)}
                onChange={(e) => markieren([s.pfad], e.target.checked)}
              />{" "}
              {s.name}
              {s.importiert && <span className="leise"> · schon übernommen</span>}
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}
