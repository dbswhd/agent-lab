use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use std::{fs, thread};

use tauri::{Manager, RunEvent};

const API_PORT: u16 = 8765;

struct ApiServer(Mutex<Option<Child>>);

fn port_in_use(port: u16) -> bool {
    TcpStream::connect(("127.0.0.1", port)).is_ok()
}

fn wait_for_api(max_wait_ms: u64) -> bool {
    let steps = max_wait_ms / 200;
    for _ in 0..steps {
        if port_in_use(API_PORT) {
            return true;
        }
        thread::sleep(Duration::from_millis(200));
    }
    false
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn resolve_project_root(app: &tauri::AppHandle) -> PathBuf {
    if cfg!(debug_assertions) {
        return repo_root();
    }
    if let Ok(dir) = app.path().resource_dir() {
        let runtime = dir.join("runtime");
        if runtime.join("app").is_dir() {
            return runtime;
        }
        if dir.join("app").is_dir() {
            return dir;
        }
    }
    repo_root()
}

fn resolve_python(root: &Path) -> PathBuf {
    let venv_py = root.join(".venv/bin/python");
    if venv_py.is_file() {
        return venv_py;
    }
    let home_venv = dirs_home().join("Projects/agent-lab/.venv/bin/python");
    if home_venv.is_file() {
        return home_venv;
    }
    PathBuf::from(
        std::env::var("AGENT_LAB_PYTHON")
            .unwrap_or_else(|_| "python3".to_string()),
    )
}

fn dirs_home() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/Users/yoonjong"))
}

/// GUI-launched apps often miss nvm/homebrew on PATH.
fn path_for_subprocess() -> String {
    let home = dirs_home();
    let mut prefixes: Vec<PathBuf> = vec![
        PathBuf::from("/opt/homebrew/bin"),
        PathBuf::from("/usr/local/bin"),
    ];
    let nvm = home.join(".nvm/versions/node");
    if let Ok(entries) = fs::read_dir(&nvm) {
        let mut vers: Vec<PathBuf> = entries
            .filter_map(|e| e.ok())
            .map(|e| e.path().join("bin"))
            .filter(|p| p.is_dir())
            .collect();
        vers.sort_by(|a, b| b.cmp(a));
        prefixes.extend(vers);
    }
    let mut out: Vec<String> = prefixes.iter().map(|p| p.to_string_lossy().into_owned()).collect();
    if let Ok(cur) = std::env::var("PATH") {
        out.push(cur);
    }
    out.join(":")
}

fn sessions_dir(app: &tauri::AppHandle, root: &Path) -> PathBuf {
    if cfg!(debug_assertions) {
        return root.join("sessions");
    }
    app.path()
        .app_data_dir()
        .map(|d| d.join("sessions"))
        .unwrap_or_else(|_| root.join("sessions"))
}

fn start_api(app: &tauri::AppHandle, state: &ApiServer) -> Result<(), String> {
    if port_in_use(API_PORT) {
        return Ok(());
    }

    let root = resolve_project_root(app);
    let python = resolve_python(&root);
    let sessions = sessions_dir(app, &root);
    fs::create_dir_all(&sessions).map_err(|e| e.to_string())?;

    let mut cmd = Command::new(&python);
    cmd.args([
        "-m",
        "uvicorn",
        "app.server.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        &API_PORT.to_string(),
    ])
    .current_dir(&root)
    .env("AGENT_LAB_ROOT", &root)
    .env("AGENT_LAB_SESSIONS_DIR", &sessions)
    .stdout(Stdio::null())
    .stderr(Stdio::null());

    cmd.env("PATH", path_for_subprocess());

    let dev_env = dirs_home().join("Projects/agent-lab/.env");
    if dev_env.is_file() {
        cmd.env("DOTENV_PATH", &dev_env);
    } else if root.join(".env").is_file() {
        cmd.env("DOTENV_PATH", root.join(".env"));
    }

    let mut child = cmd.spawn().map_err(|e| {
        format!(
            "Failed to start API ({:?}): {}. Run `make install` in {}",
            python,
            e,
            root.display()
        )
    })?;

    if !wait_for_api(15_000) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(format!(
            "API did not start on port {} within 15s",
            API_PORT
        ));
    }

    *state.0.lock().unwrap() = Some(child);
    Ok(())
}

fn stop_api(state: &ApiServer) {
    if let Some(mut child) = state.0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run_app() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(ApiServer(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            let api_state = app.state::<ApiServer>();
            start_api(&handle, &api_state).map_err(|e| -> Box<dyn std::error::Error> {
                e.into()
            })?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app.try_state::<ApiServer>() {
                    stop_api(&state);
                }
            }
        });
}
