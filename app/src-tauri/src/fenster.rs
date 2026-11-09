// Zusätzliche Fenster der App. Die Toolbox (Rechner aus JuraBox Lite) läuft in einem eigenen Fenster,
// das dieselbe Oberfläche mit dem Parameter `fenster=toolbox` lädt und denselben Kern benutzt. Ebenso das
// Arbeitsfenster einer Akte (`fenster=akte&akte=<id>`), eines je Akte, z. B. für einen zweiten Bildschirm.

use serde::Deserialize;
use tauri::{
    AppHandle, Manager, PhysicalPosition, PhysicalSize, Theme, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder,
};

pub const TOOLBOX: &str = "toolbox";
/// Wert von `fenster=` für das Arbeitsfenster einer Akte.
pub const ARBEITSFENSTER: &str = "akte";
/// Anfang der Fensternamen der Arbeitsfenster; muss zu `capabilities/arbeitsfenster.json` passen.
pub const ARBEITSFENSTER_PRAEFIX: &str = "akte-";

/// Name des Arbeitsfensters einer Akte: eines je Akte.
pub fn arbeitsfenster_name(akte_id: i64) -> String {
    format!("{ARBEITSFENSTER_PRAEFIX}{akte_id}")
}

/// Lage und Größe eines Fensters oder Bildschirms in physischen Punkten. Beim Fenster ist die Größe die des
/// Inhalts (ohne Rahmen), die Lage die der äußeren Ecke, so wie die Oberfläche sie gemerkt hat.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub struct Lage {
    pub x: i32,
    pub y: i32,
    pub breite: u32,
    pub hoehe: u32,
}

/// Ob ein gemerktes Fenster noch erreichbar wäre: Der obere Streifen (Titelleiste) muss zu einem guten Teil auf
/// einem der Bildschirme liegen. Sonst, etwa am Laptop ohne den zweiten Bildschirm, öffnet es mittig.
pub fn lage_sichtbar(lage: &Lage, bildschirme: &[Lage]) -> bool {
    let streifen_hoehe: i64 = 40;
    let noetig_breite = i64::from(lage.breite).min(120);
    bildschirme.iter().any(|b| {
        let links = i64::from(lage.x).max(i64::from(b.x));
        let rechts =
            (i64::from(lage.x) + i64::from(lage.breite)).min(i64::from(b.x) + i64::from(b.breite));
        let oben = i64::from(lage.y).max(i64::from(b.y));
        let unten = (i64::from(lage.y) + streifen_hoehe).min(i64::from(b.y) + i64::from(b.hoehe));
        rechts - links >= noetig_breite && unten - oben >= streifen_hoehe / 2
    })
}

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
    let wert = thema
        .as_deref()
        .filter(|w| matches!(*w, "light" | "dark"))
        .unwrap_or("system");
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

/// Öffnet das Arbeitsfenster einer Akte oder holt es nach vorn, wenn es schon offen ist. Es bleibt an diese Akte
/// gebunden, auch wenn im Hauptfenster eine andere geöffnet wird. `lage` ist die zuletzt gemerkte Lage; liegt sie
/// auf keinem Bildschirm mehr, öffnet das Fenster mittig auf dem Hauptbildschirm.
#[tauri::command]
pub async fn arbeitsfenster_oeffnen(
    app: AppHandle,
    akte_id: i64,
    titel: String,
    thema: Option<String>,
    lage: Option<Lage>,
) -> Result<(), String> {
    let name = arbeitsfenster_name(akte_id);
    if let Some(fenster) = app.get_webview_window(&name) {
        let _ = fenster.unminimize();
        let _ = fenster.show();
        return fenster.set_focus().map_err(|f| f.to_string());
    }
    let wert = thema
        .as_deref()
        .filter(|w| matches!(*w, "light" | "dark"))
        .unwrap_or("system");
    let url = format!("{}&akte={akte_id}&thema={wert}", adresse(ARBEITSFENSTER));
    // Erst unsichtbar anlegen, dann an die gemerkte Stelle setzen und zeigen: So springt es nicht sichtbar umher.
    let fenster = WebviewWindowBuilder::new(&app, &name, WebviewUrl::App(url.into()))
        .title(format!("advOrdo – Arbeitsfenster · {titel}"))
        .theme(self::thema(thema.as_deref()))
        .inner_size(1400.0, 900.0)
        .min_inner_size(640.0, 480.0)
        .visible(false)
        .build()
        .map_err(|f| f.to_string())?;
    let bildschirme: Vec<Lage> = fenster
        .available_monitors()
        .unwrap_or_default()
        .iter()
        .map(|m| Lage {
            x: m.position().x,
            y: m.position().y,
            breite: m.size().width,
            hoehe: m.size().height,
        })
        .collect();
    match lage.filter(|l| lage_sichtbar(l, &bildschirme)) {
        Some(l) => {
            let _ = fenster.set_size(PhysicalSize::new(l.breite, l.hoehe));
            let _ = fenster.set_position(PhysicalPosition::new(l.x, l.y));
        }
        None => {
            let _ = fenster.center();
        }
    }
    fenster.show().map_err(|f| f.to_string())?;
    fenster.set_focus().map_err(|f| f.to_string())
}

/// Schließt alle Arbeitsfenster, etwa wenn das Hauptfenster zugeht; ohne Hauptfenster liefe die App sonst weiter.
pub fn arbeitsfenster_schliessen<R: tauri::Runtime>(app: &AppHandle<R>) {
    for (name, fenster) in app.webview_windows() {
        if name.starts_with(ARBEITSFENSTER_PRAEFIX) {
            let _ = fenster.destroy();
        }
    }
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
    fn name_und_adresse_des_arbeitsfensters() {
        assert_eq!(arbeitsfenster_name(12), "akte-12");
        assert_eq!(adresse(ARBEITSFENSTER), "index.html?fenster=akte");
    }

    #[test]
    fn gemerkte_lage_nur_wenn_ein_bildschirm_sie_zeigt() {
        let laptop = Lage {
            x: 0,
            y: 0,
            breite: 2880,
            hoehe: 1800,
        };
        let zweiter = Lage {
            x: 2880,
            y: 0,
            breite: 2560,
            hoehe: 1440,
        };
        let rechts = Lage {
            x: 3000,
            y: 100,
            breite: 1400,
            hoehe: 900,
        };
        assert!(lage_sichtbar(&rechts, &[laptop, zweiter]));
        // Im Gericht ohne zweiten Bildschirm: nicht mehr erreichbar, also mittig öffnen.
        assert!(!lage_sichtbar(&rechts, &[laptop]));
        // Nur ein schmaler Rand ragt ins Bild: zu wenig zum Greifen.
        let rand = Lage {
            x: 2850,
            y: 100,
            breite: 1400,
            hoehe: 900,
        };
        assert!(!lage_sichtbar(&rand, &[laptop]));
        // Titelleiste über dem oberen Rand: nicht greifbar.
        let oben = Lage {
            x: 100,
            y: -500,
            breite: 1400,
            hoehe: 900,
        };
        assert!(!lage_sichtbar(&oben, &[laptop]));
        // Bildschirm links vom Hauptbildschirm (negative Koordinaten).
        let links = Lage {
            x: -1920,
            y: 0,
            breite: 1920,
            hoehe: 1080,
        };
        assert!(lage_sichtbar(
            &Lage {
                x: -1800,
                y: 50,
                breite: 1200,
                hoehe: 800
            },
            &[laptop, links]
        ));
        assert!(!lage_sichtbar(&rechts, &[]));
    }

    #[test]
    fn thema_der_titelleiste() {
        assert_eq!(thema(Some("light")), Some(Theme::Light));
        assert_eq!(thema(Some("dark")), Some(Theme::Dark));
        assert_eq!(thema(None), None);
        assert_eq!(thema(Some("unsinn")), None);
    }
}
