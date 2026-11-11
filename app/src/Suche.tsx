import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { DokumentAnsicht, OriginalAnsicht, VolltextAnsicht } from "./DokumentAnsicht";
import AktenWahl from "./AktenWahl";
import { anmerkungsHandler, useAnmerkungen } from "./Anmerkungen";
import { Anmerkung, anmerkungOrt, kommentarText } from "./anmerkungLogik";
import {
  Akte,
  AktenTreffer,
  DokumentInhalt,
  SammlungSuche,
  SuchDokument,
  SuchErgebnis,
  SuchFundstelle,
  UrteilVolltext,
  datumDe,
  fundstelle,
  istDesktop,
  kern,
  urteilTitel,
  wortteilVorschlag,
} from "./kern";

interface Auswahl {
  dokument: SuchDokument;
  fundstelle: SuchFundstelle;
}

type SuchAnmerkung = Anmerkung & { akte_id: number; akte: string; format: SuchDokument["format"]; seiten: number | null };
type SuchUrteil = SammlungSuche["urteile"][number];

/**
 * Wo gesucht wird: alles, nur im Text der Dokumente, nur in Markierungen und Kommentaren, nur in der Rechtsprechung;
 * in der Akte außerdem in Notizen, Fristen und Terminen, Stammdaten und Beteiligten sowie Zeiten.
 */
export type SuchBereich =
  | "alles"
  | "dokumente"
  | "anmerkungen"
  | "notizen"
  | "fristen"
  | "beteiligte"
  | "zeiten"
  | "rechtsprechung";
type BereichListe = { id: SuchBereich; titel: string }[];
const BEREICHE: BereichListe = [
  { id: "alles", titel: "Überall" },
  { id: "dokumente", titel: "Nur Dokumente" },
  { id: "anmerkungen", titel: "Nur Markierungen und Kommentare" },
  { id: "rechtsprechung", titel: "Nur Rechtsprechung" },
];
/** Suche in einer Akte (Reiter „Suche“): die ganze Akte, auf Wunsch nur ein Teil davon. */
const AKTE_BEREICHE: BereichListe = [
  { id: "alles", titel: "Ganze Akte" },
  { id: "dokumente", titel: "Nur Dokumente" },
  { id: "anmerkungen", titel: "Nur Markierungen und Kommentare" },
  { id: "notizen", titel: "Nur Notizen" },
  { id: "fristen", titel: "Nur Fristen und Termine" },
  { id: "beteiligte", titel: "Nur Stammdaten und Beteiligte" },
  { id: "zeiten", titel: "Nur Zeiten" },
  { id: "rechtsprechung", titel: "Nur Rechtsprechung der Akte" },
];
/** Welche Teile der Kern zu einem Bereich in akten.aktensuche durchsucht. */
const AKTEN_TEILE: Partial<Record<SuchBereich, AktenTreffer["bereich"][]>> = {
  notizen: ["notizen"],
  fristen: ["fristen"],
  beteiligte: ["stammdaten", "beteiligte"],
  zeiten: ["zeiten"],
};
/** Überschriften der Treffergruppen außerhalb der Dokumente, in der Reihenfolge der Liste. */
const AKTEN_GRUPPEN: { bereich: AktenTreffer["bereich"]; titel: string }[] = [
  { bereich: "notizen", titel: "In den Notizen" },
  { bereich: "fristen", titel: "In Fristen und Terminen" },
  { bereich: "stammdaten", titel: "In Stammdaten und Verfahren" },
  { bereich: "beteiligte", titel: "Bei den Beteiligten" },
  { bereich: "zeiten", titel: "In der Zeiterfassung" },
];

function gemerkterBereich(schluessel: string, liste: BereichListe): SuchBereich {
  try {
    const b = localStorage.getItem(schluessel);
    return liste.some((x) => x.id === b) ? (b as SuchBereich) : "alles";
  } catch {
    return "alles";
  }
}

const SUCH_ORT: Record<SuchBereich, string> = {
  alles: "im gelesenen Text aller Dokumente, in Markierungen und Kommentaren und in der gespeicherten Rechtsprechung",
  dokumente: "im gelesenen Text aller Dokumente",
  anmerkungen: "im markierten Wortlaut, in Kommentaren und in den Bedeutungen der Farben",
  notizen: "in den Notizen der Akte, auch in Terminsprotokollen und Notizen zu Dokumenten",
  fristen: "in Bezeichnung, Ort, Notiz und Vermerk der Fristen, Termine und Wiedervorlagen",
  beteiligte: "in Stammdaten und Verfahren der Akte und bei den Beteiligten (Name, Rolle, Aktenzeichen, Anschrift, Kontakt)",
  zeiten: "in den Tätigkeiten und Bearbeitern der Zeiterfassung",
  rechtsprechung: "in den gespeicherten Entscheidungen (Sammlung im Bereich Rechtsprechung)",
};
const AKTE_SUCH_ORT: Partial<Record<SuchBereich, string>> = {
  alles:
    "in der ganzen Akte: im Text der Dokumente, in Markierungen und Kommentaren, Notizen, Fristen und Terminen, " +
    "Stammdaten, Beteiligten, Zeiten und in den Entscheidungen der Akte",
  dokumente: "im gelesenen Text der Dokumente dieser Akte",
  rechtsprechung: "in den Entscheidungen, die dieser Akte zugeordnet sind (Reiter Rechtsprechung)",
};

const REITER_NAME: Record<AktenTreffer["reiter"], string> = {
  notizen: "Notizen",
  fristen: "Fristen",
  stammdaten: "Stammdaten",
  beteiligte: "Beteiligte",
  zeiten: "Zeiten",
};

/** Suche auf eine Akte beschränkt (Reiter „Suche“ der Akte). */
export interface AktenSuche {
  akte: Akte;
  /** Einen Eintrag in seinem Reiter zeigen (Notizen, Fristen, Stammdaten, Beteiligte, Zeiten). */
  onReiter: (reiter: AktenTreffer["reiter"]) => void;
  /** Ein Dokument im Reiter „Dokumente“ öffnen. */
  onDokument: (dokumentId: number) => void;
  /** Suchbegriff von außen (Dokumentliste); ``nr`` zählt hoch, damit derselbe Begriff erneut wirkt. */
  vorgabe?: { text: string; nr: number } | null;
  /** Zählt hoch, wenn das Suchfeld den Fokus bekommen soll (Reiter gewählt, Strg/⌘+F). */
  fokus?: number;
}

/** Volltextsuche über alle Akten, nach dem Vorbild von „PDF Search“: links die Treffer, rechts das Dokument. */
export default function Suche({ onAkte, inAkte }: { onAkte?: (id: number) => void; inAkte?: AktenSuche }) {
  const bereiche = inAkte ? AKTE_BEREICHE : BEREICHE;
  const bereichSchluessel = inAkte ? "akte.suche.bereich" : "suche.bereich";
  const [eingabe, setEingabe] = useState("");
  const [akten, setAkten] = useState<Akte[]>([]);
  // Gesucht wird zunächst in allen Akten; null heißt „Alle Akten“. Im Reiter „Suche“ der Akte steht sie fest.
  const [gewaehlteAkte, setAkteId] = useState<number | null>(null);
  const akteId = inAkte ? inAkte.akte.id : gewaehlteAkte;
  // Treffer in Notizen, Fristen, Stammdaten, Beteiligten und Zeiten (nur in der Akte).
  const [eintraege, setEintraege] = useState<AktenTreffer[]>([]);
  const [eintragWahl, setEintragWahl] = useState<AktenTreffer | null>(null);
  const feld = useRef<HTMLInputElement>(null);
  const [ergebnis, setErgebnis] = useState<SuchErgebnis | null>(null);
  // Treffer in Markierungen und Kommentaren (Wortlaut, Kommentar, Bedeutung der Farbe).
  const [anmerkungen, setAnmerkungen] = useState<SuchAnmerkung[]>([]);
  // Treffer in den gespeicherten Entscheidungen (Sammlung im Bereich „Rechtsprechung“).
  const [urteile, setUrteile] = useState<SuchUrteil[]>([]);
  const [bereich, setBereich] = useState<SuchBereich>(() => gemerkterBereich(bereichSchluessel, bereiche));
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
      setEintraege([]);
      return;
    }
    // In der Akte: Notizen, Fristen usw. bei „Ganze Akte“ oder dem passenden Bereich.
    const teile = !inAkte ? null : bereich === "alles" ? [] : (AKTEN_TEILE[bereich] ?? null);
    try {
      const [e, a, u, t] = await Promise.all([
        mit("dokumente") ? kern<SuchErgebnis>("akten.suche", { text, akte_id: akteId }) : null,
        mit("anmerkungen") ? kern<SuchAnmerkung[]>("anmerkungen.suche", { text, akte_id: akteId }) : [],
        mit("rechtsprechung")
          ? kern<SammlungSuche>("rechtsprechung.suche", inAkte ? { suchtext: text, akte_id: akteId } : { suchtext: text })
          : null,
        teile
          ? kern<{ treffer: AktenTreffer[] }>("akten.aktensuche", {
              akte_id: akteId,
              text,
              bereiche: teile.length ? teile : null,
            })
          : null,
      ]);
      if (nr !== anfrage.current) return; // eine neuere Eingabe ist schon unterwegs
      setFehler(null);
      setErgebnis(e);
      setAnmerkungen(a);
      setUrteile(u?.urteile ?? []);
      setEintraege(t?.treffer ?? []);
      setEintragWahl(null);
      setGesuchtFuer(text);
      setZu(new Set());
      const erstes = e?.dokumente[0];
      if (erstes) void waehle(erstes, erstes.fundstellen.find((f) => f.rang === erstes.rang) ?? erstes.fundstellen[0]);
      else if (a[0]) waehleAnmerkung(a[0]);
      else if (u?.urteile[0]) void waehleUrteil(u.urteile[0], u.urteile[0].fundstellen[0]);
      else if (t?.treffer[0]) waehleEintrag(t.treffer[0]);
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

  // Begriff aus der Dokumentliste übernehmen; Suchfeld fokussieren, wenn der Reiter gewählt wird oder Strg/⌘+F.
  useEffect(() => {
    if (inAkte?.vorgabe) setEingabe(inAkte.vorgabe.text);
  }, [inAkte?.vorgabe]);
  useEffect(() => {
    if (!inAkte?.fokus) return;
    const t = requestAnimationFrame(() => {
      feld.current?.focus();
      feld.current?.select();
    });
    return () => cancelAnimationFrame(t);
  }, [inAkte?.fokus]);

  /** Treffer in Notizen, Fristen usw.: rechts kurz zeigen, mit Knopf zum Reiter, der den Eintrag führt. */
  function waehleEintrag(t: AktenTreffer) {
    setAuswahl(null);
    setUrteilWahl(null);
    setEintragWahl(t);
  }

  function bereichWaehlen(b: SuchBereich) {
    setBereich(b);
    try {
      localStorage.setItem(bereichSchluessel, b);
    } catch {
      // Ohne Speicher gilt die Wahl bis zum Neustart.
    }
  }

  /** Treffer in einer Entscheidung: Volltext an der Randnummer zeigen. */
  async function waehleUrteil(urteil: SuchUrteil, f: SuchUrteil["fundstellen"][number]) {
    setAuswahl(null);
    setEintragWahl(null);
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
    if (!istDesktop || inAkte) return;
    kern<Akte[]>("akten.liste")
      .then(setAkten)
      .catch((f) => setFehler(String(f)));
  }, []);

  async function waehle(dokument: SuchDokument, f: SuchFundstelle) {
    setUrteilWahl(null);
    setEintragWahl(null);
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

  // Welche Wörter ein Platzhalter am Wortanfang gefunden hat, damit die Suche nachvollziehbar bleibt.
  const wortformenText = Object.entries(ergebnis?.wortformen ?? {})
    .map(([muster, w]) =>
      w.length === 0
        ? `${muster}: kein passendes Wort`
        : `${muster}: ${w.slice(0, 8).join(", ")}${w.length > 8 ? ` und ${w.length - 8} weitere` : ""}` +
          (ergebnis?.wortformen_gekuerzt ? " (nur die häufigsten)" : ""),
    )
    .join(" · ");
  const vorschlag = wortteilVorschlag(eingabe);
  // Alle gefundenen Wortformen des Dokuments markieren, nicht nur die der gewählten Seite.
  const begriffe = [...new Set(auswahl?.dokument.fundstellen.flatMap((f) => f.begriffe) ?? [])];
  const ohneTreffer =
    gesuchtFuer &&
    gesuchtFuer === eingabe &&
    !ergebnis?.dokumente.length &&
    !anmerkungen.length &&
    !urteile.length &&
    !eintraege.length;
  // Für den Bildschirmleser: wie viel gefunden wurde, sobald die Suche zur Eingabe fertig ist.
  const ansage = !gesuchtFuer || gesuchtFuer !== eingabe
    ? ""
    : ohneTreffer
      ? "Keine Treffer."
      : [
          ergebnis?.dokumente.length ? `${ergebnis.treffer} Treffer in ${ergebnis.dokumente.length} ${ergebnis.dokumente.length === 1 ? "Dokument" : "Dokumenten"}` : "",
          anmerkungen.length ? `${anmerkungen.length} in Markierungen und Kommentaren` : "",
          eintraege.length ? `${eintraege.length} in Notizen, Fristen, Beteiligten und weiteren Einträgen der Akte` : "",
          urteile.length ? `${urteile.length} in der Rechtsprechung` : "",
        ]
          .filter(Boolean)
          .join(", ") + ".";
  const ortText = (inAkte && AKTE_SUCH_ORT[bereich]) || SUCH_ORT[bereich];
  return (
    <div className={inAkte ? "suche-bereich in-akte" : "suche-bereich"}>
      {!inAkte && (
        <header className="kopf">
          <h1>Suche</h1>
        </header>
      )}
      <form className="suche-feld" onSubmit={absenden} role="search" aria-label={inAkte ? "In dieser Akte suchen" : undefined}>
        <input
          ref={feld}
          autoFocus={!inAkte}
          type="search"
          value={eingabe}
          onChange={(e) => setEingabe(e.target.value)}
          placeholder={
            inAkte
              ? "In dieser Akte suchen, z. B. Mechatronik, „Frist bis zum“, Nachbesser* oder *protokoll*"
              : "Suchen, z. B. Mechatronik, „Frist bis zum“, Nachbesser* oder *protokoll*"
          }
          aria-label={inAkte ? "Suchbegriff für diese Akte" : "Suchbegriff"}
          title={inAkte ? "Strg/⌘+F springt in der Akte hierher" : undefined}
        />
        <select
          className="such-bereich"
          value={bereich}
          onChange={(e) => bereichWaehlen(e.target.value as SuchBereich)}
          aria-label="Suchen in"
        >
          {bereiche.map((b) => (
            <option key={b.id} value={b.id}>
              {b.titel}
            </option>
          ))}
        </select>
        {!inAkte && bereich !== "rechtsprechung" && <AktenWahl akten={akten} akteId={akteId} onWahl={setAkteId} />}
      </form>
      <p className="nur-vorlesen" aria-live="polite">
        {ansage}
      </p>
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {ergebnis && (
        <div className="such-stand">
          <span>
            {ergebnis.dokumente.length} {ergebnis.dokumente.length === 1 ? "Dokument" : "Dokumente"}, {ergebnis.seiten}{" "}
            {ergebnis.seiten === 1 ? "Fundstelle" : "Fundstellen"}, {ergebnis.treffer} Treffer (
            {(ergebnis.dauer_ms / 1000).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 3 })} s)
          </span>
          {eintraege.length > 0 && (
            <span>
              {" "}
              · {eintraege.length} weitere in Notizen, Fristen, Beteiligten usw.
            </span>
          )}
          {ergebnis.gekuerzt && <span className="hinweis"> · nur die ersten 5.000 passenden Abschnitte</span>}
          {wortformenText && <span className="hinweis such-wortformen"> · {wortformenText}</span>}
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
          {ohneTreffer && <li className="leer">Keine Treffer.</li>}
          {vorschlag && gesuchtFuer === eingabe && mit("dokumente") && (
            <li className="such-vorschlag">
              <button className="link" onClick={() => setEingabe(vorschlag)}>
                Auch als Wortteil suchen: {vorschlag}
              </button>{" "}
              <span className="hinweis">findet z. B. auch zusammengesetzte Wörter wie „Diagnoseprotokoll“</span>
            </li>
          )}
          {!eingabe.trim() && (
            <li className="leer">
              Gesucht wird {ortText}. Groß- und Kleinschreibung spielt keine Rolle. Mehrere Wörter müssen alle
              vorkommen; „genaue Wortfolge“ in Anführungszeichen. Der Stern * steht für beliebige Buchstaben: Nachbesser*
              (Wortanfang), *protokoll (Wortende), *protokoll* (Wortteil, findet auch „Diagnoseprotokoll“).
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
          {AKTEN_GRUPPEN.map((g) => {
            const liste = eintraege.filter((t) => t.bereich === g.bereich);
            if (!liste.length) return null;
            return (
              <li key={g.bereich} className="such-dokument">
                <div className="such-dokument-kopf such-anmerkungen-kopf">
                  <span className="such-name">{g.titel}</span>
                  <span className="such-meta">{liste.length} Treffer</span>
                </div>
                <ul>
                  {liste.map((t) => (
                    <li key={`${t.bereich}${t.id}`}>
                      <button
                        className={`such-fundstelle${eintragWahl === t ? " gewaehlt" : ""}`}
                        onClick={() => waehleEintrag(t)}
                        onDoubleClick={() => inAkte?.onReiter(t.reiter)}
                      >
                        <span className="such-ort">
                          {t.art} · {t.titel}
                          {t.datum && <> · {datumDe(t.datum)}</>}
                        </span>
                        <span className="such-rang such-feld-name">{t.feld}</span>
                        <span className="ausschnitt">
                          {t.ausschnitt.vor}
                          <mark>{t.ausschnitt.treffer}</mark>
                          {t.ausschnitt.nach}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
          {urteile.length > 0 && (
            <li className="such-dokument">
              <div className="such-dokument-kopf such-anmerkungen-kopf">
                <span className="such-name">In der Rechtsprechung</span>
                <span className="such-meta">
                  {urteile.length} {urteile.length === 1 ? "Entscheidung" : "Entscheidungen"} aus der Sammlung
                  {!inAkte && akteId != null && bereich === "alles" ? ", unabhängig von der Akte" : ""}
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
          {eintragWahl && inAkte && (
            <div className="such-eintrag">
              <p className="such-eintrag-art">
                {eintragWahl.art}
                {eintragWahl.datum && ` · ${datumDe(eintragWahl.datum)}`}
              </p>
              <h2>{eintragWahl.titel}</h2>
              <p className="such-meta">Gefunden im Feld „{eintragWahl.feld}“:</p>
              <p className="ausschnitt">
                {eintragWahl.ausschnitt.vor}
                <mark>{eintragWahl.ausschnitt.treffer}</mark>
                {eintragWahl.ausschnitt.nach}
              </p>
              <p className="such-eintrag-knoepfe">
                <button onClick={() => inAkte.onReiter(eintragWahl.reiter)}>{REITER_NAME[eintragWahl.reiter]} öffnen</button>
                {eintragWahl.dokument_id != null && (
                  <button className="zweitrangig" onClick={() => inAkte.onDokument(eintragWahl.dokument_id!)}>
                    Zugehöriges Dokument öffnen
                  </button>
                )}
              </p>
            </div>
          )}
          {auswahl && (
            <div className="such-dokument-titel">
              <strong>{auswahl.dokument.dateiname}</strong>
              {inAkte ? (
                <button className="link" onClick={() => inAkte.onDokument(auswahl.dokument.id)}>
                  im Reiter Dokumente öffnen
                </button>
              ) : (
                <>
                  <span className="such-meta"> · Akte {auswahl.dokument.akte}</span>
                  <button className="link" onClick={() => onAkte?.(auswahl.dokument.akte_id)}>
                    in der Akte öffnen
                  </button>
                </>
              )}
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
              {...anm.rahmenProps}
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
