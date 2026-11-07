//! Brücke zum Python-Analysekern.
//!
//! Der Kern läuft als Kindprozess und spricht zeilenweises JSON über
//! stdin/stdout. Es wird kein Netzwerkport geöffnet. Stirbt der Prozess,
//! wird er beim nächsten Aufruf neu gestartet. Eine Anfrage, die der Kern
//! schon erhalten hat, wird nie ein zweites Mal gesendet: Sie könnte den
//! Absturz verursacht haben oder schon teilweise ausgeführt sein.

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
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

        // Ein schon beendeter Prozess wird vor dem Senden ersetzt.
        if let Some(p) = sperre.as_mut() {
            if !matches!(p.kind.try_wait(), Ok(None)) {
                eprintln!("Kern beendet, starte neu");
                *sperre = None;
            }
        }
        // Ein zweiter Versuch nur, wenn das Senden scheiterte, der Kern die Anfrage also nicht erhalten hat.
        for versuch in 0..2 {
            if sperre.is_none() {
                *sperre = Some(self.starte()?);
            }
            let p = sperre.as_mut().expect("Prozess gerade gestartet");
            match austausch(p, &anfrage, id) {
                Ok(antwort) => return auswerten(antwort),
                Err(Fehler::Senden(e)) if versuch == 0 => {
                    eprintln!("Kern nicht erreichbar ({e}), starte neu");
                    *sperre = None;
                }
                Err(fehler) => {
                    // Der Austausch ist aus dem Takt; der nächste Aufruf beginnt mit einem neuen Prozess.
                    *sperre = None;
                    return Err(fehler.text());
                }
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
        ohne_konsolenfenster(&mut befehl);
        let mut kind = befehl.spawn().map_err(|e| format!("Analysekern konnte nicht gestartet werden: {e}"))?;
        let stdin = kind.stdin.take().ok_or("stdin des Kerns fehlt")?;
        let stdout = BufReader::new(kind.stdout.take().ok_or("stdout des Kerns fehlt")?);
        Ok(Prozess { kind, stdin, stdout })
    }
}

/// Entwicklung: `python -m juracore serve` im Ordner `core/`.
/// Auslieferung: gebündeltes Kernprogramm `juracore` neben der App (Sidecar, `core/kern_bauen.py`).
/// Interpreter: `JURACORE_PYTHON`, sonst die `.venv` im Projektordner, sonst `python`/`python3`.
fn kern_befehl() -> Command {
    let sidecar = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|d| d.join(format!("juracore{}", std::env::consts::EXE_SUFFIX))));
    if let Some(pfad) = sidecar.filter(|p| p.exists() && !cfg!(debug_assertions)) {
        let mut c = Command::new(pfad);
        c.arg("serve");
        return c;
    }
    let projekt = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..");
    let python = std::env::var_os("JURACORE_PYTHON")
        .map(PathBuf::from)
        .or_else(|| Some(venv_python(&projekt)).filter(|p| p.exists()))
        .unwrap_or_else(|| PathBuf::from(if cfg!(windows) { "python" } else { "python3" }));
    let mut c = Command::new(python);
    c.args(["-m", "juracore", "serve"]).current_dir(projekt.join("core"));
    c
}

/// Windows öffnet für ein Konsolenprogramm, das eine Fenster-App startet, sonst ein leeres Konsolenfenster.
#[cfg(windows)]
fn ohne_konsolenfenster(befehl: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    befehl.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn ohne_konsolenfenster(_befehl: &mut Command) {}

/// Interpreter einer virtuellen Umgebung `.venv`; Windows legt ihn unter `Scripts` ab.
fn venv_python(projekt: &Path) -> PathBuf {
    if cfg!(windows) {
        projekt.join(".venv").join("Scripts").join("python.exe")
    } else {
        projekt.join(".venv").join("bin").join("python")
    }
}

/// Fehler im Austausch: beim Senden (der Kern hat die Anfrage nicht) oder danach (er hat sie vielleicht).
#[derive(Debug)]
enum Fehler {
    Senden(String),
    Antwort(String),
}

impl Fehler {
    fn text(self) -> String {
        match self {
            Fehler::Senden(t) | Fehler::Antwort(t) => t,
        }
    }
}

fn austausch(p: &mut Prozess, anfrage: &Value, id: u64) -> Result<Value, Fehler> {
    let zeile = serde_json::to_string(anfrage).map_err(|e| Fehler::Senden(e.to_string()))?;
    p.stdin
        .write_all(zeile.as_bytes())
        .and_then(|_| p.stdin.write_all(b"\n"))
        .and_then(|_| p.stdin.flush())
        .map_err(|e| Fehler::Senden(format!("Senden an den Kern fehlgeschlagen: {e}")))?;
    // Der Kern sendet nur Antworten auf Anfragen. Zeilen mit einer anderen Kennung deuten auf einen
    // Fehler hin (etwa eine Ausgabe auf stdout); ohne Grenze würde hier endlos gelesen.
    let mut fremde_zeilen = 0u32;
    loop {
        let mut antwort = String::new();
        let n = p
            .stdout
            .read_line(&mut antwort)
            .map_err(|e| Fehler::Antwort(format!("Lesen vom Kern fehlgeschlagen: {e}")))?;
        if n == 0 {
            return Err(Fehler::Antwort(
                "Der Analysekern wurde während der Bearbeitung unerwartet beendet. Bitte den Vorgang erneut \
                 starten; der Kern wird dabei neu gestartet."
                    .into(),
            ));
        }
        let wert: Value = serde_json::from_str(&antwort)
            .map_err(|e| Fehler::Antwort(format!("Ungültige Antwort des Kerns: {e}")))?;
        if wert.get("id").and_then(Value::as_u64) == Some(id) {
            return Ok(wert);
        }
        fremde_zeilen += 1;
        if fremde_zeilen >= 64 {
            return Err(Fehler::Antwort(
                "Der Kern antwortet nicht mit der erwarteten Kennung (64 Zeilen ohne Treffer)".into(),
            ));
        }
    }
}

fn auswerten(antwort: Value) -> Result<Value, String> {
    if let Some(fehler) = antwort.get("error") {
        return Err(fehler.get("message").and_then(Value::as_str).unwrap_or("Unbekannter Fehler").to_string());
    }
    Ok(antwort.get("result").cloned().unwrap_or(Value::Null))
}

/// Methoden, die die Oberfläche aufrufen darf (erzeugt mit `python core/kern_methoden.py`).
const FREIGEGEBEN: &str = include_str!("../kern-methoden.txt");

fn freigegeben_name(methode: &str) -> bool {
    FREIGEGEBEN.lines().any(|z| !z.starts_with('#') && z.trim() == methode)
}

/// Nur Methoden aus der Liste; bei `hintergrund.starten` gilt das auch für die gestartete Methode.
fn pruefe_freigabe(methode: &str, params: &Value) -> Result<(), String> {
    if !freigegeben_name(methode) {
        return Err(format!("Die Methode „{methode}“ ist für die Oberfläche nicht freigegeben."));
    }
    if methode == "hintergrund.starten" {
        let innen = params.get("methode").and_then(Value::as_str).unwrap_or("");
        if !freigegeben_name(innen) {
            return Err(format!("Die Methode „{innen}“ ist für die Oberfläche nicht freigegeben."));
        }
    }
    Ok(())
}

#[tauri::command]
pub async fn kern_aufruf(
    kern: tauri::State<'_, Arc<Kern>>,
    methode: String,
    params: Value,
) -> Result<Value, String> {
    pruefe_freigabe(&methode, &params)?;
    let kern = Arc::clone(&kern);
    tauri::async_runtime::spawn_blocking(move || kern.aufruf(&methode, params))
        .await
        .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn venv_interpreter_je_system() {
        let p = venv_python(Path::new("projekt"));
        let erwartet = if cfg!(windows) { "projekt/.venv/Scripts/python.exe" } else { "projekt/.venv/bin/python" };
        assert_eq!(p, PathBuf::from(erwartet.replace('/', std::path::MAIN_SEPARATOR_STR)));
    }

    #[test]
    fn nur_freigegebene_methoden() {
        assert!(pruefe_freigabe("akten.liste", &json!({})).is_ok());
        assert!(pruefe_freigabe("akten.beteiligung_aendern", &json!({})).is_err());
        assert!(pruefe_freigabe("gibt.es.nicht", &json!({})).is_err());
        assert!(pruefe_freigabe("# Kernmethoden", &json!({})).is_err());
        let gut = json!({ "methode": "akten.importieren_dateien", "params": {} });
        assert!(pruefe_freigabe("hintergrund.starten", &gut).is_ok());
        let schlecht = json!({ "methode": "akten.importieren", "params": {} });
        assert!(pruefe_freigabe("hintergrund.starten", &schlecht).is_err());
    }

    #[test]
    fn startet_nach_absturz_neu() {
        let daten = std::env::temp_dir().join(format!("jda-absturz-{}", std::process::id()));
        let kern = Kern::new(daten.clone());
        kern.aufruf("ping", json!({})).expect("ping");
        {
            let mut sperre = kern.prozess.lock().unwrap();
            let p = sperre.as_mut().unwrap();
            p.kind.kill().unwrap();
            p.kind.wait().unwrap();
        }
        // Der beendete Prozess wird vor dem Senden erkannt und ersetzt.
        assert!(kern.aufruf("ping", json!({})).is_ok());
        let _ = std::fs::remove_dir_all(daten);
    }

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

        let akte = kern.aufruf("akten.anlegen", json!({ "name": "Testakte" })).expect("akte");
        assert_eq!(kern.aufruf("akten.dokumente", json!({ "akte_id": akte["id"] })).expect("dokumente"), json!([]));

        // Lange Befehle laufen im Hintergrund des Kerns; die Brücke bleibt währenddessen frei.
        let auftrag = kern
            .aufruf(
                "hintergrund.starten",
                json!({ "methode": "gesetze.importieren_datei", "params": { "pfad": fixture } }),
            )
            .expect("hintergrund");
        let mut stand = auftrag.clone();
        for _ in 0..200 {
            if stand["status"] != "laeuft" {
                break;
            }
            assert!(kern.aufruf("ping", json!({})).is_ok());
            std::thread::sleep(std::time::Duration::from_millis(25));
            stand = kern
                .aufruf("hintergrund.auftrag", json!({ "auftrag_id": auftrag["auftrag_id"] }))
                .expect("auftrag");
        }
        assert_eq!(stand["status"], "fertig", "{stand}");

        let fehler = kern.aufruf("gibt.es.nicht", json!({})).unwrap_err();
        assert!(fehler.contains("Unbekannte Methode"));
        let _ = std::fs::remove_dir_all(daten);
    }
}
