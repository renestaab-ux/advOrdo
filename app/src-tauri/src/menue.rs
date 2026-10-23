// Menüleiste unter macOS. Tauris Standardmenü nennt die App in „Über …“, „… ausblenden“ und „… beenden“
// nach dem Programmnamen; im Entwicklungsmodus ist das der Paketname „juristischer-datenabgleich“, der bewusst
// so bleibt (Datenordner). Dieses Menü setzt den sichtbaren Namen aus `productName` und deutsche Bezeichnungen.
// Windows und Linux zeigen kein Menü; die Funktion wird nur unter macOS eingebunden.
#![cfg_attr(not(target_os = "macos"), allow(dead_code))]

use tauri::menu::{
    AboutMetadata, Menu, PredefinedMenuItem, Submenu, HELP_SUBMENU_ID, WINDOW_SUBMENU_ID,
};
use tauri::{AppHandle, Runtime};

/// Einträge im App-Menü, die den Namen der App tragen.
pub fn app_eintraege(name: &str) -> [String; 3] {
    [format!("Über {name}"), format!("{name} ausblenden"), format!("{name} beenden")]
}

pub fn hauptmenue<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<Menu<R>> {
    let info = app.package_info();
    let name = info.name.clone();
    let [ueber, ausblenden, beenden] = app_eintraege(&name);
    let metadaten = AboutMetadata {
        name: Some(name.clone()),
        version: Some(info.version.to_string()),
        ..Default::default()
    };

    let app_menue = Submenu::with_items(
        app,
        &name,
        true,
        &[
            &PredefinedMenuItem::about(app, Some(&ueber), Some(metadaten))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::services(app, Some("Dienste"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::hide(app, Some(&ausblenden))?,
            &PredefinedMenuItem::hide_others(app, Some("Andere ausblenden"))?,
            &PredefinedMenuItem::show_all(app, Some("Alle einblenden"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::quit(app, Some(&beenden))?,
        ],
    )?;
    let ablage = Submenu::with_items(
        app,
        "Ablage",
        true,
        &[&PredefinedMenuItem::close_window(app, Some("Fenster schließen"))?],
    )?;
    let bearbeiten = Submenu::with_items(
        app,
        "Bearbeiten",
        true,
        &[
            &PredefinedMenuItem::undo(app, Some("Widerrufen"))?,
            &PredefinedMenuItem::redo(app, Some("Wiederholen"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, Some("Ausschneiden"))?,
            &PredefinedMenuItem::copy(app, Some("Kopieren"))?,
            &PredefinedMenuItem::paste(app, Some("Einsetzen"))?,
            &PredefinedMenuItem::select_all(app, Some("Alles auswählen"))?,
        ],
    )?;
    let darstellung = Submenu::with_items(
        app,
        "Darstellung",
        true,
        &[&PredefinedMenuItem::fullscreen(app, Some("Vollbild"))?],
    )?;
    // Mit diesen Kennungen erkennt macOS das Fenster- und das Hilfemenü (Fensterliste, Suchfeld).
    let fenster = Submenu::with_id_and_items(
        app,
        WINDOW_SUBMENU_ID,
        "Fenster",
        true,
        &[
            &PredefinedMenuItem::minimize(app, Some("Im Dock ablegen"))?,
            &PredefinedMenuItem::maximize(app, Some("Zoomen"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::close_window(app, Some("Fenster schließen"))?,
        ],
    )?;
    let hilfe = Submenu::with_id_and_items(app, HELP_SUBMENU_ID, "Hilfe", true, &[])?;

    Menu::with_items(app, &[&app_menue, &ablage, &bearbeiten, &darstellung, &fenster, &hilfe])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn app_eintraege_tragen_den_anzeigenamen() {
        assert_eq!(app_eintraege("JuraBox"), ["Über JuraBox", "JuraBox ausblenden", "JuraBox beenden"]);
    }
}
