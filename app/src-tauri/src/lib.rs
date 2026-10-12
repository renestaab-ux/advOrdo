mod kern;

use std::sync::Arc;

use tauri::Manager;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let daten = app.path().app_data_dir()?;
            app.manage(Arc::new(kern::Kern::new(daten)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![kern::kern_aufruf])
        .run(tauri::generate_context!())
        .expect("Fehler beim Start der Anwendung");
}
