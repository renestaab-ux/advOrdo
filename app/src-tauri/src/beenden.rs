// Rückfrage beim Beenden der App, solange ein Timer der Zeiterfassung läuft. Rust hält das Schließen des
// Hauptfensters bzw. das Beenden (macOS: „JuraBox beenden“, ⌘Q) an und meldet es der Oberfläche; die prüft den
// Timer, fragt nach und beendet dann selbst mit `app_beenden` oder bricht mit `beenden_abgebrochen` ab.
// Antwortet die Oberfläche nicht, schließt der zweite Versuch ohne Rückfrage, damit die App nie festhängt.

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{AppHandle, Emitter, Manager, Runtime, State};

pub const HAUPTFENSTER: &str = "main";
/// Ereignis an die Oberfläche des Hauptfensters.
pub const EREIGNIS: &str = "beenden-angefragt";
/// Menüeintrag „JuraBox beenden“ (macOS).
pub const MENUE_ID: &str = "beenden";

#[derive(Default)]
pub struct Rueckfrage {
    offen: AtomicBool,
    freigegeben: AtomicBool,
}

impl Rueckfrage {
    /// Ob das Beenden angehalten und die Oberfläche gefragt werden soll. Nein, wenn schon freigegeben oder eine
    /// Rückfrage offen ist (zweiter Versuch).
    pub fn anhalten(&self) -> bool {
        !self.freigegeben.load(Ordering::SeqCst) && !self.offen.swap(true, Ordering::SeqCst)
    }

    pub fn abgebrochen(&self) {
        self.offen.store(false, Ordering::SeqCst);
    }

    pub fn freigeben(&self) {
        self.freigegeben.store(true, Ordering::SeqCst);
    }
}

/// Meldet den Wunsch zu beenden an die Oberfläche. `true`: das Beenden ist angehalten, die Oberfläche entscheidet.
pub fn anfragen<R: Runtime>(app: &AppHandle<R>) -> bool {
    let Some(fenster) = app.get_webview_window(HAUPTFENSTER) else {
        return false;
    };
    if !app.state::<Rueckfrage>().anhalten() {
        return false;
    }
    let _ = fenster.unminimize();
    let _ = fenster.show();
    let _ = fenster.set_focus();
    if app.emit_to(HAUPTFENSTER, EREIGNIS, ()).is_err() {
        app.state::<Rueckfrage>().freigeben();
        return false;
    }
    true
}

#[tauri::command]
pub fn app_beenden(app: AppHandle, rueckfrage: State<'_, Rueckfrage>) {
    rueckfrage.freigeben();
    app.exit(0);
}

#[tauri::command]
pub fn beenden_abgebrochen(rueckfrage: State<'_, Rueckfrage>) {
    rueckfrage.abgebrochen();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn erst_fragen_dann_beim_zweiten_versuch_schliessen() {
        let r = Rueckfrage::default();
        assert!(r.anhalten());
        assert!(!r.anhalten(), "zweiter Versuch während offener Rückfrage schließt");
        r.abgebrochen();
        assert!(r.anhalten(), "nach Abbrechen wird wieder gefragt");
    }

    #[test]
    fn nach_freigabe_nicht_mehr_fragen() {
        let r = Rueckfrage::default();
        r.freigeben();
        assert!(!r.anhalten());
    }
}
