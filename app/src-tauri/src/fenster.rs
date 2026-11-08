// Zusätzliche Fenster der App. Die Toolbox (Rechner aus JuraBox Lite) läuft in einem eigenen Fenster,
// das dieselbe Oberfläche mit dem Parameter `fenster=toolbox` lädt und denselben Kern benutzt.

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

pub const TOOLBOX: &str = "toolbox";

/// Adresse der Oberfläche für ein zusätzliches Fenster.
pub fn adresse(fenster: &str) -> String {
    format!("index.html?fenster={fenster}")
}

// Asynchron, weil das Anlegen eines Fensters in einem synchronen Befehl unter Windows hängen bleiben kann.
#[tauri::command]
pub async fn toolbox_oeffnen(app: AppHandle) -> Result<(), String> {
    if let Some(fenster) = app.get_webview_window(TOOLBOX) {
        let _ = fenster.unminimize();
        return fenster.set_focus().map_err(|f| f.to_string());
    }
    WebviewWindowBuilder::new(&app, TOOLBOX, WebviewUrl::App(adresse(TOOLBOX).into()))
        .title("advOrdo – Toolbox")
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
}
