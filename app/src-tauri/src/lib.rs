mod fenster;
mod kern;
mod menue;

use std::sync::Arc;

use tauri::Manager;

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
        .invoke_handler(tauri::generate_handler![kern::kern_aufruf, fenster::toolbox_oeffnen])
        .run(tauri::generate_context!())
        .expect("Fehler beim Start der Anwendung");
}
