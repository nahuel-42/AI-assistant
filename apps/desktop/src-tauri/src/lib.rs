use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

/// Handle to the local Python backend so it is stopped when the app exits.
struct Backend(Mutex<Option<Child>>);

/// Starts `python -m uvicorn app.main:app` from the backend folder.
///
/// Env overrides: `COPILOT_SKIP_BACKEND=1` (you run it yourself), `COPILOT_BACKEND_DIR`,
/// `COPILOT_PYTHON`. Defaults to the repo's `backend/` and its `.venv` interpreter.
/// If the port is already taken (backend started manually) the child just exits.
fn spawn_backend() -> Option<Child> {
    if std::env::var_os("COPILOT_SKIP_BACKEND").is_some() {
        return None;
    }
    let dir = std::env::var_os("COPILOT_BACKEND_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../backend"));
    let venv_python = dir.join(".venv").join("Scripts").join("python.exe");
    let python = std::env::var_os("COPILOT_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| if venv_python.exists() { venv_python } else { PathBuf::from("python") });

    let mut cmd = Command::new(python);
    cmd.args(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"])
        .current_dir(&dir);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    match cmd.spawn() {
        Ok(child) => Some(child),
        Err(err) => {
            eprintln!("[copilot] could not start backend in {}: {err}", dir.display());
            None
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            app.manage(Backend(Mutex::new(spawn_backend())));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building AI Interview Copilot")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(backend) = app.try_state::<Backend>() {
                    if let Some(mut child) = backend.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
