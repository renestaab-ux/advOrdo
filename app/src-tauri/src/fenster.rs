// Zusätzliche Fenster der App. Die Toolbox (Rechner aus JuraBox Lite) läuft in einem eigenen Fenster,
// das dieselbe Oberfläche mit dem Parameter `fenster=toolbox` lädt und denselben Kern benutzt.

use tauri::{AppHandle, Manager, Theme, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

pub const TOOLBOX: &str = "toolbox";

/// Adresse der Oberfläche für ein zusätzliches Fenster.
pub fn adresse(fenster: &str) -> String {
    format!("index.html?fenster={fenster}")
}

/// Thema der Titelleiste aus der Darstellung der Oberfläche („light“, „dark“, sonst wie das System).
pub fn thema(wert: Option<&str>) -> Option<Theme> {
    match wert {
        Some("light") => Some(Theme::Light),
        Some("dark") => Some(Theme::Dark),
        _ => None,
    }
}

// Asynchron, weil das Anlegen eines Fensters in einem synchronen Befehl unter Windows hängen bleiben kann.
// Das Thema wird schon beim Anlegen gesetzt: Setzt die Oberfläche es erst danach, bleibt die Titelleiste unter
// Windows schwarz und die Knöpfe unsichtbar, bis das Fenster einmal den Fokus wechselt. Die Oberfläche erfährt
// über `thema=` in der Adresse, dass sie es nicht noch einmal setzen muss.
#[tauri::command]
pub async fn toolbox_oeffnen(app: AppHandle, thema: Option<String>) -> Result<(), String> {
    if let Some(fenster) = app.get_webview_window(TOOLBOX) {
        let _ = fenster.unminimize();
        return fenster.set_focus().map_err(|f| f.to_string());
    }
    let wert = thema.as_deref().filter(|w| matches!(*w, "light" | "dark")).unwrap_or("system");
    let url = format!("{}&thema={wert}", adresse(TOOLBOX));
    WebviewWindowBuilder::new(&app, TOOLBOX, WebviewUrl::App(url.into()))
        .title("advOrdo – Toolbox")
        .theme(self::thema(thema.as_deref()))
        .inner_size(1000.0, 760.0)
        .min_inner_size(720.0, 520.0)
        .build()
        .map(|_| ())
        .map_err(|f| f.to_string())
}

/// Druckdialog des Systems für den Inhalt des Fensters; die Oberfläche blendet beim Drucken alles außer der
/// Druckansicht aus (`@media print`). `window.print()` allein reicht nicht: Unter macOS druckt WKWebView damit nichts,
/// Tauri ruft dort den Druckvorgang von AppKit auf, unter Windows und Linux den der Webansicht.
#[tauri::command]
pub fn drucken(fenster: WebviewWindow) -> Result<(), String> {
    fenster.print().map_err(|f| f.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adresse_der_toolbox() {
        assert_eq!(adresse(TOOLBOX), "index.html?fenster=toolbox");
    }

    #[test]
    fn thema_der_titelleiste() {
        assert_eq!(thema(Some("light")), Some(Theme::Light));
        assert_eq!(thema(Some("dark")), Some(Theme::Dark));
        assert_eq!(thema(None), None);
        assert_eq!(thema(Some("unsinn")), None);
    }
}
