import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { DokumentAnsicht, OriginalAnsicht, VolltextAnsicht } from "./Akte";
import AktenWahl from "./AktenWahl";
import { anmerkungsHandler, useAnmerkungen } from "./Anmerkungen";
import { Anmerkung, anmerkungOrt, kommentarText } from "./anmerkungLogik";
import {
  Akte,
  DokumentInhalt,
  SammlungSuche,
  SuchDokument,
  SuchErgebnis,
  SuchFundstelle,
  UrteilVolltext,
  fundstelle,
  istDesktop,
  kern,
  urteilTitel,
} from "./kern";

interface Auswahl {
  dokument: SuchDokument;
  fundstelle: SuchFundstelle;
}

type SuchAnmerkung = Anmerkung & { akte_id: number; akte: string; format: SuchDokument["format"]; seiten: number | null };
type SuchUrteil = SammlungSuche["urteile"][number];

/** Wo gesucht wird: alles, nur im Text der Dokumente, nur in Markierungen und Kommentaren, nur in der Rechtsprechung. */
export type SuchBereich = "alles" | "dokumente" | "anmerkungen" | "rechtsprechung";
const BEREICHE: { id: SuchBereich; titel: string }[] = [
  { id: "alles", titel: "Überall" },
  { id: "dokumente", titel: "Nur Dokumente" },
  { id: "anmerkungen", titel: "Nur Markierungen und Kommentare" },
  { id: "rechtsprechung", titel: "Nur Rechtsprechung" },
];

function gemerkterBereich(): SuchBereich {
  try {
    const b = localStorage.getItem("suche.bereich");
    return BEREICHE.some((x) => x.id === b) ? (b as SuchBereich) : "alles";
  } catch {
    return "alles";
  }
}

const SUCH_ORT: Record<SuchBereich, string> = {
  alles: "im gelesenen Text aller Dokumente, in Markierungen und Kommentaren und in der gespeicherten Rechtsprechung",
  dokumente: "im gelesenen Text aller Dokumente",
  anmerkungen: "im markierten Wortlaut, in Kommentaren und in den Bedeutungen der Farben",
  rechtsprechung: "in den gespeicherten Entscheidungen (Sammlung im Bereich Rechtsprechung)",
};

/** Volltextsuche über alle Akten, nach dem Vorbild von „PDF Search“: links die Treffer, rechts das Dokument. */
export default function Suche({ onAkte }: { onAkte: (id: number) => void }) {
  const [eingabe, setEingabe] = useState("");
  const [akten, setAkten] = useState<Akte[]>([]);
  // Gesucht wird zunächst in allen Akten; null heißt „Alle Akten“.
  const [akteId, setAkteId] = useState<number | null>(null);
  const [ergebnis, setErgebnis] = useState<SuchErgebnis | null>(null);
  // Treffer in Markierungen und Kommentaren (Wortlaut, Kommentar, Bedeutung der Farbe).
  const [anmerkungen, setAnmerkungen] = useState<SuchAnmerkung[]>([]);
  // Treffer in den gespeicherten Entscheidungen (Sammlung im Bereich „Rechtsprechung“).
  const [urteile, setUrteile] = useState<SuchUrteil[]>([]);
  const [bereich, setBereich] = useState<SuchBereich>(gemerkterBereich);
  const [urteilWahl, setUrteilWahl] = useState<{ urteil: SuchUrteil; rn: number | null; nr: number } | null>(null);
  const [volltext, setVolltext] = useState<UrteilVolltext | null>(null);
  const [zu, setZu] = useState<Set<number>>(new Set());
  const [auswahl, setAuswahl] = useState<Auswahl | null>(null);
  const [inhalt, setInhalt] = useState<DokumentInhalt | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  // Wofür die angezeigten Treffer gelten; „Keine Treffer“ erst, wenn die Suche zur Eingabe fertig ist.
  const [gesuchtFuer, setGesuchtFuer] = useState("");
  const anfrage = useRef(0);
  const textRahmen = useRef<HTMLDivElement>(null);
  const mit = (b: SuchBereich) => bereich === "alles" || bereich === b;

  // Markieren und Kommentieren auch hier, im Original wie im Text; die Trefferliste der Anmerkungen folgt.
  const anm = useAnmerkungen(auswahl?.dokument.id ?? null, () => void anmerkungenNeu());
  async function anmerkungenNeu() {
    if (!mit("anmerkungen") || !eingabe.trim()) return;
    try {
      setAnmerkungen(await kern<SuchAnmerkung[]>("anmerkungen.suche", { text: eingabe, akte_id: akteId }));
    } catch {
      // Die Liste bleibt dann, wie sie war.
    }
  }

  async function suchen(text: string) {
    const nr = ++anfrage.current;
    if (!text.trim()) {
      setErgebnis(null);
      setAnmerkungen([]);
      setUrteile([]);
      return;
    }
    try {
      const [e, a, u] = await Promise.all([
        mit("dokumente") ? kern<SuchErgebnis>("akten.suche", { text, akte_id: akteId }) : null,
        mit("anmerkungen") ? kern<SuchAnmerkung[]>("anmerkungen.suche", { text, akte_id: akteId }) : [],
        mit("rechtsprechung") ? kern<SammlungSuche>("rechtsprechung.suche", { suchtext: text }) : null,
      ]);
      if (nr !== anfrage.current) return; // eine neuere Eingabe ist schon unterwegs
      setFehler(null);
      setErgebnis(e);
      setAnmerkungen(a);
      setUrteile(u?.urteile ?? []);
      setGesuchtFuer(text);
      setZu(new Set());
      const erstes = e?.dokumente[0];
      if (erstes) void waehle(erstes, erstes.fundstellen.find((f) => f.rang === erstes.rang) ?? erstes.fundstellen[0]);
      else if (a[0]) waehleAnmerkung(a[0]);
      else if (u?.urteile[0]) void waehleUrteil(u.urteile[0], u.urteile[0].fundstellen[0]);
      else {
        setAuswahl(null);
        setUrteilWahl(null);
      }
    } catch (f) {
      if (nr === anfrage.current) setFehler(String(f));
    }
  }

  // Treffer schon beim Tippen, kurz verzögert.
  useEffect(() => {
    if (!istDesktop) return;
    const t = setTimeout(() => void suchen(eingabe), 250);
    return () => clearTimeout(t);
  }, [eingabe, akteId, bereich]);

  function bereichWaehlen(b: SuchBereich) {
    setBereich(b);
    try {
      localStorage.setItem("suche.bereich", b);
    } catch {
      // Ohne Speicher gilt die Wahl bis zum Neustart.
    }
  }

  /** Treffer in einer Entscheidung: Volltext an der Randnummer zeigen. */
  async function waehleUrteil(urteil: SuchUrteil, f: SuchUrteil["fundstellen"][number]) {
    setAuswahl(null);
    setUrteilWahl({ urteil, rn: f.rn, nr: f.nr });
    if (volltext?.id === urteil.id) return;
    try {
      setVolltext(await kern<UrteilVolltext>("akten.urteil", { urteil_id: urteil.id }));
    } catch (e) {
      setFehler(String(e));
    }
  }

  // Akten für die Auswahl „Suchen in“.
  useEffect(() => {
    if (!istDesktop) return;
    kern<Akte[]>("akten.liste")
      .then(setAkten)
      .catch((f) => setFehler(String(f)));
  }, []);

  async function waehle(dokument: SuchDokument, f: SuchFundstelle) {
    setUrteilWahl(null);
    setAuswahl({ dokument, fundstelle: f });
    if (dokument.format === "pdf") {
      setInhalt(null);
      return;
    }
    if (inhalt?.dokument.id !== dokument.id) {
      try {
        setInhalt(await kern<DokumentInhalt>("akten.dokument", { dokument_id: dokument.id }));
      } catch (e) {
        setFehler(String(e));
      }
    }
  }

  // Gewählte Fundstelle in der Liste sichtbar halten (▲/▼).
  useEffect(() => {
    document.querySelector(".such-fundstelle.gewaehlt")?.scrollIntoView({ block: "nearest" });
  }, [auswahl]);

  // Fundstelle im Text anspringen (Word, Text, Markdown).
  useEffect(() => {
    if (!auswahl || !inhalt || inhalt.dokument.id !== auswahl.dokument.id) return;
    document.getElementById(`abschnitt-${auswahl.fundstelle.abschnitt}`)?.scrollIntoView({ block: "center" });
  }, [auswahl, inhalt]);

  // Alle Fundstellen in der Reihenfolge der Liste, für ▲ und ▼.
  const folge = useMemo(
    () => ergebnis?.dokumente.flatMap((d) => d.fundstellen.map((f) => ({ dokument: d, fundstelle: f }))) ?? [],
    [ergebnis],
  );
  const position = auswahl ? folge.findIndex((x) => x.fundstelle === auswahl.fundstelle) : -1;
  function springe(schritt: number) {
    const ziel = folge[position + schritt];
    if (!ziel) return;
    setZu((z) => {
      const neu = new Set(z);
      neu.delete(ziel.dokument.id);
      return neu;
    });
    void waehle(ziel.dokument, ziel.fundstelle);
  }

  /** Treffer in einer Anmerkung: Dokument an der markierten Stelle zeigen, der Wortlaut ist gelb hervorgehoben. */
  function waehleAnmerkung(a: SuchAnmerkung) {
    const zitat = a.zitat ?? "";
    void waehle(
      { id: a.dokument_id, dateiname: a.dateiname ?? "", format: a.format, seiten: a.seiten, akte_id: a.akte_id, akte: a.akte,
        treffer: 0, rang: 0, fundstellen: [] },
      { seite: a.seite, abschnitt: a.abschnitt ?? 1, rn: a.rn, treffer: 1, rang: 0,
        ausschnitt: { vor: "", treffer: zitat, nach: "" }, begriffe: zitat ? [zitat] : [] },
    );
  }

  function absenden(e: FormEvent) {
    e.preventDefault();
    void suchen(eingabe);
  }

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Der Analysekern steht nur in der Desktop-App zur Verfügung:{" "}
        <code>npm run tauri dev</code>
      </section>
    );
  }

  // Alle gefundenen Wortformen des Dokuments markieren, nicht nur die der gewählten Seite.
  const begriffe = [...new Set(auswahl?.dokument.fundstellen.flatMap((f) => f.begriffe) ?? [])];
  return (
    <div className="suche-bereich">
      <header className="kopf">
        <h1>Suche</h1>
      </header>
      <form className="suche-feld" onSubmit={absenden} role="search">
        <input
          autoFocus
          type="search"
          value={eingabe}
          onChange={(e) => setEingabe(e.target.value)}
          placeholder="Suchen, z. B. Mechatronik, „Frist bis zum“ oder Nachbesser*"
          aria-label="Suchbegriff"
        />
        <select
          className="such-bereich"
          value={bereich}
          onChange={(e) => bereichWaehlen(e.target.value as SuchBereich)}
          aria-label="Suchen in"
        >
          {BEREICHE.map((b) => (
            <option key={b.id} value={b.id}>
              {b.titel}
            </option>
          ))}
        </select>
        {bereich !== "rechtsprechung" && <AktenWahl akten={akten} akteId={akteId} onWahl={setAkteId} />}
      </form>
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {ergebnis && (
        <div className="such-stand">
          <span>
            {ergebnis.dokumente.length} {ergebnis.dokumente.length === 1 ? "Dokument" : "Dokumente"}, {ergebnis.seiten}{" "}
            {ergebnis.seiten === 1 ? "Fundstelle" : "Fundstellen"}, {ergebnis.treffer} Treffer (
            {(ergebnis.dauer_ms / 1000).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 3 })} s)
          </span>
          {ergebnis.gekuerzt && <span className="hinweis"> · nur die ersten 5.000 passenden Abschnitte</span>}
          <span className="such-pfeile">
            <button className="zweitrangig" onClick={() => springe(-1)} disabled={position <= 0} title="Vorige Fundstelle" aria-label="Vorige Fundstelle">
              ▲
            </button>
            <button
              className="zweitrangig"
              onClick={() => springe(1)}
              disabled={position < 0 || position >= folge.length - 1}
              title="Nächste Fundstelle"
              aria-label="Nächste Fundstelle"
            >
              ▼
            </button>
            {position >= 0 && (
              <span className="such-position">
                {position + 1} / {folge.length}
              </span>
            )}
          </span>
        </div>
      )}

      <div className="such-flaeche">
        <ul className="such-liste" aria-label="Treffer">
          {anmerkungen.length > 0 && (
            <li className="such-dokument">
              <div className="such-dokument-kopf such-anmerkungen-kopf">
                <span className="such-name">In Markierungen und Kommentaren</span>
                <span className="such-meta">{anmerkungen.length} Treffer</span>
              </div>
              <ul>
                {anmerkungen.map((a) => (
                  <li key={`a${a.id}`}>
                    <button
                      className={`such-fundstelle${auswahl?.dokument.id === a.dokument_id && auswahl.fundstelle.ausschnitt.treffer === a.zitat ? " gewaehlt" : ""}`}
                      onClick={() => waehleAnmerkung(a)}
                    >
                      <span className="such-ort">
                        {a.dokument} · {anmerkungOrt(a)}
                      </span>
                      <span className="such-rang">
                        <span className={`anm-punkt anm-punkt-${a.farbe}`} /> {anm.bedeutungen[a.farbe]}
                      </span>
                      <span className={`ausschnitt anm-zitat anm-rand-${a.farbe}`}>{a.zitat}</span>
                      {a.kommentar && <span className="ausschnitt">{kommentarText(a.kommentar)}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          )}
          {gesuchtFuer && gesuchtFuer === eingabe && !ergebnis?.dokumente.length && !anmerkungen.length && !urteile.length && (
            <li className="leer">Keine Treffer.</li>
          )}
          {!eingabe.trim() && (
            <li className="leer">
              Gesucht wird {SUCH_ORT[bereich]}. Groß- und Kleinschreibung spielt keine Rolle. Mehrere Wörter müssen alle
              vorkommen; „genaue Wortfolge“ in Anführungszeichen; Wortanfang mit *.
            </li>
          )}
          {ergebnis?.dokumente.map((d) => {
            const offen = !zu.has(d.id);
            return (
              <li key={d.id} className="such-dokument">
                <button
                  className="such-dokument-kopf"
                  aria-expanded={offen}
                  onClick={() =>
                    setZu((z) => {
                      const neu = new Set(z);
                      if (offen) neu.add(d.id);
                      else neu.delete(d.id);
                      return neu;
                    })
                  }
                >
                  <span className="such-pfeil">{offen ? "▾" : "▸"}</span>
                  <span className="such-name">{d.dateiname}</span>
                  <span className="such-meta">
                    {d.akte} · {d.seiten != null ? `${d.seiten} S. · ` : ""}
                    {d.treffer} Treffer
                  </span>
                </button>
                {offen && (
                  <ul>
                    {d.fundstellen.map((f) => (
                      <li key={`${f.seite}-${f.abschnitt}`}>
                        <button
                          className={`such-fundstelle${auswahl?.fundstelle === f ? " gewaehlt" : ""}`}
                          onClick={() => void waehle(d, f)}
                        >
                          <span className="such-ort">
                            {fundstelle(f)}
                            {f.treffer > 1 && <> · {f.treffer}×</>}
                          </span>
                          <span className="such-rang">Rang {f.rang}</span>
                          <span className="ausschnitt">
                            {f.ausschnitt.vor}
                            <mark>{f.ausschnitt.treffer}</mark>
                            {f.ausschnitt.nach}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
          {urteile.length > 0 && (
            <li className="such-dokument">
              <div className="such-dokument-kopf such-anmerkungen-kopf">
                <span className="such-name">In der Rechtsprechung</span>
                <span className="such-meta">
                  {urteile.length} {urteile.length === 1 ? "Entscheidung" : "Entscheidungen"} aus der Sammlung
                  {akteId != null && bereich === "alles" ? ", unabhängig von der Akte" : ""}
                </span>
              </div>
              <ul>
                {urteile.flatMap((u) =>
                  u.fundstellen.map((f) => (
                    <li key={`u${u.id}-${f.nr}`}>
                      <button
                        className={`such-fundstelle${urteilWahl?.urteil.id === u.id && urteilWahl.nr === f.nr ? " gewaehlt" : ""}`}
                        onClick={() => void waehleUrteil(u, f)}
                      >
                        <span className="such-ort">
                          {urteilTitel(u)}
                          {f.rn != null && <> · Rn. {f.rn}</>}
                        </span>
                        <span className="ausschnitt">
                          {f.ausschnitt.vor}
                          <mark>{f.ausschnitt.treffer}</mark>
                          {f.ausschnitt.nach}
                        </span>
                      </button>
                    </li>
                  )),
                )}
              </ul>
            </li>
          )}
        </ul>

        <section className="such-dokument-ansicht" aria-label="Dokument">
          {anm.schicht}
          {urteilWahl && volltext?.id === urteilWahl.urteil.id && (
            <VolltextAnsicht volltext={volltext} rn={urteilWahl.rn} onSchliessen={() => setUrteilWahl(null)} />
          )}
          {auswahl && (
            <div className="such-dokument-titel">
              <strong>{auswahl.dokument.dateiname}</strong>
              <span className="such-meta"> · Akte {auswahl.dokument.akte}</span>
              <button className="link" onClick={() => onAkte(auswahl.dokument.akte_id)}>
                in der Akte öffnen
              </button>
            </div>
          )}
          {auswahl?.dokument.format === "pdf" && (
            <OriginalAnsicht
              key={`${auswahl.dokument.id}:${begriffe.join("\u0000")}`}
              dokument={auswahl.dokument}
              startSeite={auswahl.fundstelle.seite}
              begriffe={begriffe}
              hinweis="Fundstellen sind gelb hinterlegt. Zum Markieren mit der Maus über die Wörter ziehen."
              anmerkungen={anm.original}
            />
          )}
          {auswahl && auswahl.dokument.format !== "pdf" && inhalt?.dokument.id === auswahl.dokument.id && (
            <div
              ref={textRahmen}
              className="anm-rahmen"
              onMouseUp={() => textRahmen.current && anm.beiAuswahl(textRahmen.current)}
              {...anmerkungsHandler(anm.ereignisse)}
            >
              <DokumentAnsicht
                inhalt={inhalt}
                markiert={auswahl.fundstelle.abschnitt}
                begriffe={begriffe}
                anmerkungen={anm.liste}
                aktiveAnmerkung={anm.aktiv}
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
