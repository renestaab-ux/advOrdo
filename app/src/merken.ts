/** Ein/Aus-Zustände je Gerät, etwa ob eine Leiste eingeklappt ist. Ohne Speicher gelten sie bis zum Neustart. */
export function gemerkt(schluessel: string): boolean {
  try {
    return localStorage.getItem(schluessel) === "1";
  } catch {
    return false;
  }
}

export function merke(schluessel: string, wert: boolean) {
  try {
    localStorage.setItem(schluessel, wert ? "1" : "0");
  } catch {
    // Ohne Speicher gilt der Zustand nur bis zum Neustart.
  }
}
