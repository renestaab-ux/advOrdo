//! Brücke zum Python-Analysekern.
//!
//! Der Kern läuft als Kindprozess und spricht zeilenweises JSON über
//! stdin/stdout. Es wird kein Netzwerkport geöffnet. Stirbt der Prozess,
//! wird er beim nächsten Aufruf neu gestartet.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use serde_json::{json, Value};

pub struct Kern {
    daten: PathBuf,
    prozess: Mutex<Option<Prozess>>,
    naechste_id: AtomicU64,
}

struct Prozess {
    kind: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl Drop for Prozess {
    fn drop(&mut self) {
        let _ = self.kind.kill();
        let _ = self.kind.wait();
    }
}

impl Kern {
    pub fn new(daten: PathBuf) -> Self {
        Self { daten, prozess: Mutex::new(None), naechste_id: AtomicU64::new(1) }
    }

    pub fn aufruf(&self, methode: &str, params: Value) -> Result<Value, String> {
        let id = self.naechste_id.fetch_add(1, Ordering::Relaxed);
        let anfrage = json!({ "id": id, "method": methode, "params": params });
        let mut sperre = self.prozess.lock().map_err(|_| "Kern-Sperre beschädigt".to_string())?;

        // Ein Wiederholungsversuch, falls der Prozess inzwischen beendet wurde.
        for versuch in 0..2 {
            if sperre.is_none() {
                *sperre = Some(self.starte()?);
            }
            let p = sperre.as_mut().expect("Prozess gerade gestartet");
            match austausch(p, &anfrage, id) {
                Ok(antwort) => return auswerten(antwort),
                Err(e) if versuch == 0 => {
                    eprintln!("Kern nicht erreichbar ({e}), starte neu");
                    *sperre = None;
                }
                Err(e) => return Err(e),
            }
        }
        unreachable!()
    }

    fn starte(&self) -> Result<Prozess, String> {
        let mut befehl = kern_befehl();
        befehl
            .env("JURACORE_DATEN", &self.daten)
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        let mut kind = befehl.spawn().map_err(|e| format!("Analysekern konnte nicht gestartet werden: {e}"))?;
        let stdin = kind.stdin.take().ok_or("stdin des Kerns fehlt")?;
        let stdout = BufReader::new(kind.stdout.take().ok_or("stdout des Kerns fehlt")?);
        Ok(Prozess { kind, stdin, stdout })
    }
}

/// Entwicklung: `python -m juracore serve` im Ordner `core/`.
/// Auslieferung: gebündeltes Kernprogramm neben der App (Sidecar, folgt mit dem Installer).
/// `JURACORE_PYTHON` überschreibt den Python-Interpreter.
fn kern_befehl() -> Command {
    let sidecar = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|d| d.join(format!("juracore{}", std::env::consts::EXE_SUFFIX))));
    if let Some(pfad) = sidecar.filter(|p| p.exists() && !cfg!(debug_assertions)) {
        let mut c = Command::new(pfad);
        c.arg("serve");
        return c;
    }
    let python = std::env::var("JURACORE_PYTHON")
        .unwrap_or_else(|_| if cfg!(windows) { "python".into() } else { "python3".into() });
    let core = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("core");
    let mut c = Command::new(python);
    c.args(["-m", "juracore", "serve"]).current_dir(core);
    c
}

fn austausch(p: &mut Prozess, anfrage: &Value, id: u64) -> Result<Value, String> {
    let zeile = serde_json::to_string(anfrage).map_err(|e| e.to_string())?;
    p.stdin
        .write_all(zeile.as_bytes())
        .and_then(|_| p.stdin.write_all(b"\n"))
        .and_then(|_| p.stdin.flush())
        .map_err(|e| format!("Senden an den Kern fehlgeschlagen: {e}"))?;
    loop {
        let mut antwort = String::new();
        let n = p.stdout.read_line(&mut antwort).map_err(|e| format!("Lesen vom Kern fehlgeschlagen: {e}"))?;
        if n == 0 {
            return Err("Der Analysekern wurde unerwartet beendet".into());
        }
        let wert: Value = serde_json::from_str(&antwort).map_err(|e| format!("Ungültige Antwort des Kerns: {e}"))?;
        if wert.get("id").and_then(Value::as_u64) == Some(id) {
            return Ok(wert);
        }
    }
}

fn auswerten(antwort: Value) -> Result<Value, String> {
    if let Some(fehler) = antwort.get("error") {
        return Err(fehler.get("message").and_then(Value::as_str).unwrap_or("Unbekannter Fehler").to_string());
    }
    Ok(antwort.get("result").cloned().unwrap_or(Value::Null))
}

#[tauri::command]
pub async fn kern_aufruf(
    kern: tauri::State<'_, Arc<Kern>>,
    methode: String,
    params: Value,
) -> Result<Value, String> {
    let kern = Arc::clone(&kern);
    tauri::async_runtime::spawn_blocking(move || kern.aufruf(&methode, params))
        .await
        .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spricht_mit_dem_python_kern() {
        let daten = std::env::temp_dir().join(format!("jda-test-{}", std::process::id()));
        let kern = Kern::new(daten.clone());
        let ping = kern.aufruf("ping", json!({})).expect("ping");
        assert!(ping.get("version").is_some());

        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../core/tests/fixtures/zpo_auszug.xml");
        kern.aufruf("gesetze.importieren_datei", json!({ "pfad": fixture })).expect("import");
        let beleg = kern.aufruf("zitat.aufloesen", json!({ "zitat": "§ 286 Abs. 2 ZPO" })).expect("zitat");
        assert_eq!(beleg["status"], "belegt");

        let fehler = kern.aufruf("gibt.es.nicht", json!({})).unwrap_err();
        assert!(fehler.contains("Unbekannte Methode"));
        let _ = std::fs::remove_dir_all(daten);
    }
}
