import { ReactNode, createContext, useContext, useState } from "react";
import { AbgleichFundstelle, fundstelle } from "./kern";

type Zitate = { zeigen: boolean; setZeigen: (z: boolean) => void };

/** Ob Fundstellen mit Zitat oder nur als kurze Quellenangabe erscheinen. Ohne Schalter: mit Zitat. */
const ZitateKontext = createContext<Zitate>({ zeigen: true, setZeigen: () => {} });

/** Belege darunter starten eingeklappt; der ZitateSchalter blendet die Zitate ein. */
export function Zitatbereich({ children, zeigen: anfang = false }: { children: ReactNode; zeigen?: boolean }) {
  const [zeigen, setZeigen] = useState(anfang);
  return <ZitateKontext.Provider value={{ zeigen, setZeigen }}>{children}</ZitateKontext.Provider>;
}

export function ZitateSchalter() {
  const { zeigen, setZeigen } = useContext(ZitateKontext);
  return (
    <button className="link klein zitate-schalter" onClick={() => setZeigen(!zeigen)} aria-pressed={zeigen}>
      {zeigen ? "Zitate ausblenden" : "Zitate einblenden"}
    </button>
  );
}

/** Eine Fundstelle: eingeklappt als kurze Quellenangabe (Zitat im Tooltip), ausgeklappt mit dem Satz aus dem Dokument. */
export function Beleg({
  f,
  gewaehlt,
  onFundstelle,
  zusatz,
}: {
  f: AbgleichFundstelle;
  gewaehlt: boolean;
  onFundstelle: () => void;
  zusatz?: ReactNode;
}) {
  const { zeigen } = useContext(ZitateKontext);
  const ort = `${f.dateiname}, ${fundstelle(f)}`;
  if (!zeigen) {
    return (
      <li className="kompakt">
        <button
          className={gewaehlt ? "quelle gewaehlt" : "quelle"}
          onClick={onFundstelle}
          title={`${ort}\n„${f.ausschnitt.wert}“\nKlick öffnet das Dokument an dieser Stelle.`}
        >
          {f.dateiname.replace(/\.[^.]+$/, "")}, {fundstelle(f)}
          {f.parteien.length > 0 && <span className="quelle-partei"> · {f.parteien.join(", ")}</span>}
        </button>
      </li>
    );
  }
  return (
    <li className={gewaehlt ? "gewaehlt" : undefined}>
      <button className="link" onClick={onFundstelle} title="Dokument an dieser Stelle öffnen">
        {ort}
      </button>
      {f.parteien.map((p) => (
        <span key={p} className="tag">
          {p}
        </span>
      ))}
      {zusatz}
      <div className="ausschnitt">
        {f.ausschnitt.davor}
        <mark>{f.ausschnitt.wert}</mark>
        {f.ausschnitt.danach}
      </div>
    </li>
  );
}
