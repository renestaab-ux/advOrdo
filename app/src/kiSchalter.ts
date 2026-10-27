import { createContext, useContext } from "react";

/**
 * Ob die KI eingeschaltet ist (Einstellungen → Lokales Sprachmodell, Schalter „KI verwenden“). Aus: Reiter und Knöpfe,
 * die zwingend ein Sprachmodell brauchen (Analyse, Chat, Gegenüberstellung), sind ausgeblendet; die Texterkennung und
 * alles Übrige arbeiten weiter.
 */
export const KiAn = createContext(true);

export const useKiAn = () => useContext(KiAn);
