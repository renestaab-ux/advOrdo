mod beenden;
mod fenster;
mod kern;
mod menue;

use std::sync::Arc;

use tauri::{Manager, RunEvent, WindowEvent};

pub fn run() {
    let builder = tauri::Builder::default();
    #[cfg(target_os = "macos")]
    let builder = builder.menu(menue::hauptmenue);
    builder
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let daten = app.path().app_data_dir()?;
            app.manage(Arc::new(kern::Kern::new(daten)));
            Ok(())
        })
        .manage(beenden::Rueckfrage::default())
        // Läuft ein Timer der Zeiterfassung, fragt die Oberfläche vor dem Beenden nach (siehe beenden.rs).
        .on_window_event(|fenster, ereignis| match ereignis {
            WindowEvent::CloseRequested { api, .. } => {
                if fenster.label() == beenden::HAUPTFENSTER && beenden::anfragen(fenster.app_handle()) {
                    api.prevent_close();
                }
            }
            // Mit dem Hauptfenster gehen die Arbeitsfenster der Akten zu, sonst liefe die App ohne Hauptfenster weiter.
            WindowEvent::Destroyed if fenster.label() == beenden::HAUPTFENSTER => {
                fenster::arbeitsfenster_schliessen(fenster.app_handle());
            }
            _ => {}
        })
        .on_menu_event(|app, ereignis| {
            let id = ereignis.id().as_ref();
            if id == menue::UEBER_ID {
                menue::ueber_zeigen(app);
            } else if id == beenden::MENUE_ID && !beenden::anfragen(app) {
                app.exit(0);
            }
        })
        .invoke_handler(tauri::generate_handler![
            kern::kern_aufruf,
            fenster::toolbox_oeffnen,
            fenster::arbeitsfenster_oeffnen,
            fenster::drucken,
            beenden::app_beenden,
            beenden::beenden_abgebrochen
        ])
        .build(tauri::generate_context!())
        .expect("Fehler beim Start der Anwendung")
        .run(|app, ereignis| {
            // Beenden über das Dock o. Ä. (ohne Exit-Code); app.exit(0) kommt mit Code und ist freigegeben.
            if let RunEvent::ExitRequested { code: None, api, .. } = ereignis {
                if beenden::anfragen(app) {
                    api.prevent_exit();
                }
            }
        });
}
