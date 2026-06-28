use std::fs::{self, OpenOptions};
use std::io::Write;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use std::{thread, time::SystemTime};

use tauri::{Manager, RunEvent};

const API_PORT: u16 = 8765;

struct ApiServer(Mutex<Option<Child>>);

fn port_in_use(port: u16) -> bool {
    TcpStream::connect(("127.0.0.1", port)).is_ok()
}

fn http_response_body(raw: &str) -> Option<String> {
    let (_, body) = raw.split_once("\r\n\r\n")?;
    let trimmed = body.trim();
    if trimmed.is_empty() {
        return None;
    }
    Some(trimmed.to_string())
}

fn api_health_body() -> Option<String> {
    use std::io::{Read, Write};
    let Ok(mut stream) = TcpStream::connect(("127.0.0.1", API_PORT)) else {
        return None;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let req = b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    if stream.write_all(req).is_err() {
        return None;
    }
    let mut buf = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        let Ok(n) = stream.read(&mut chunk) else {
            break;
        };
        if n == 0 {
            break;
        }
        buf.extend_from_slice(&chunk[..n]);
        if buf.len() > 65536 {
            break;
        }
    }
    http_response_body(&String::from_utf8_lossy(&buf))
}

fn skip_tauri_api() -> bool {
    std::env::var("AGENT_LAB_SKIP_TAURI_API")
        .map(|v| {
            let t = v.trim().to_ascii_lowercase();
            matches!(t.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
}

fn api_health_ok() -> bool {
    let Some(body) = api_health_body() else {
        return false;
    };
    if !(body.contains("\"ok\":true") || body.contains("\"ok\": true")) {
        return false;
    }
    body.contains("default_agent_parallel_rounds")
}

fn api_health_sessions_dir() -> Option<PathBuf> {
    let body = api_health_body()?;
    let value: serde_json::Value = serde_json::from_str(&body).ok()?;
    value
        .get("sessions_dir")
        .and_then(|v| v.as_str())
        .map(PathBuf::from)
}

fn wait_for_api(max_wait_ms: u64, child: &mut Option<Child>) -> bool {
    let steps = max_wait_ms / 200;
    for _ in 0..steps {
        if let Some(proc) = child.as_mut() {
            if let Ok(Some(status)) = proc.try_wait() {
                append_boot(&format!("API process exited early: {status}"));
                return false;
            }
        }
        if api_health_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(200));
    }
    false
}

fn stop_process_on_port(port: u16) {
    let script = format!("lsof -ti tcp:{port} 2>/dev/null | xargs kill -9 2>/dev/null || true");
    let _ = Command::new("/bin/sh").arg("-c").arg(&script).status();
    thread::sleep(Duration::from_millis(400));
}

fn python_can_import_app(python: &Path, root: &Path) -> bool {
    Command::new(python)
        .args(["-c", "import app.server.main"])
        .current_dir(root)
        .env("AGENT_LAB_ROOT", root)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn dirs_home() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/Users/yoonjong"))
}

fn agent_config_dir() -> PathBuf {
    dirs_home().join(".agent-lab")
}

fn agent_log_dir() -> PathBuf {
    dirs_home().join("Library/Logs/Agent Lab")
}

fn append_boot(message: &str) {
    let log_dir = agent_log_dir();
    let _ = fs::create_dir_all(&log_dir);
    let boot = log_dir.join("agent-lab-boot.log");
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&boot) {
        let stamp = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let _ = writeln!(file, "{stamp} {message}");
    }
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

fn resolve_python(app: &tauri::AppHandle, root: &Path) -> PathBuf {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if !cfg!(debug_assertions) {
        if let Ok(dir) = app.path().resource_dir() {
            for rel in [
                "runtime/venv/bin/python3",
                "runtime/venv/bin/python",
                "runtime/.venv/bin/python3",
                "runtime/.venv/bin/python",
            ] {
                candidates.push(dir.join(rel));
            }
        }
    }

    candidates.push(root.join(".venv/bin/python"));
    candidates.push(dirs_home().join("Projects/agent-lab/.venv/bin/python"));
    if let Ok(from_env) = std::env::var("AGENT_LAB_PYTHON") {
        let trimmed = from_env.trim();
        if !trimmed.is_empty() {
            candidates.push(PathBuf::from(trimmed));
        }
    }
    candidates.push(PathBuf::from("python3"));

    for candidate in candidates {
        if !candidate.is_file() {
            continue;
        }
        if python_can_import_app(&candidate, root) {
            append_boot(&format!("using python {}", candidate.display()));
            return candidate;
        }
        append_boot(&format!(
            "python skipped (cannot import app): {}",
            candidate.display()
        ));
    }

    append_boot("no usable python found; falling back to python3 on PATH");
    PathBuf::from("python3")
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
    let mut out: Vec<String> = prefixes
        .iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect();
    if let Ok(cur) = std::env::var("PATH") {
        out.push(cur);
    }
    out.join(":")
}

fn sessions_dir(_app: &tauri::AppHandle, _root: &Path) -> PathBuf {
    if let Ok(raw) = std::env::var("AGENT_LAB_SESSIONS_DIR") {
        let trimmed = raw.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    // Match tauri-dev: repo `sessions/`, not Application Support.
    let home_repo = dirs_home().join("Projects/agent-lab/sessions");
    if home_repo.is_dir() {
        return home_repo;
    }
    repo_root().join("sessions")
}

fn resolve_dotenv_path(root: &Path) -> Option<PathBuf> {
    let user_env = agent_config_dir().join(".env");
    if user_env.is_file() {
        return Some(user_env);
    }
    let dev_env = dirs_home().join("Projects/agent-lab/.env");
    if dev_env.is_file() {
        return Some(dev_env);
    }
    let root_env = root.join(".env");
    if root_env.is_file() {
        return Some(root_env);
    }
    None
}

fn start_api(app: &tauri::AppHandle, state: &ApiServer) -> Result<(), String> {
    let root = resolve_project_root(app);
    let expected_sessions = sessions_dir(app, &root);

    if port_in_use(API_PORT) {
        if api_health_ok() {
            if let Some(remote) = api_health_sessions_dir() {
                let same = remote
                    .canonicalize()
                    .ok()
                    .zip(expected_sessions.canonicalize().ok())
                    .map(|(a, b)| a == b)
                    .unwrap_or(false);
                if !same {
                    let msg = format!(
                        "Agent Lab: port {API_PORT} uses sessions {} but this app expects {}. \
                         Stop stale API: kill $(lsof -ti:{API_PORT}) then restart.",
                        remote.display(),
                        expected_sessions.display()
                    );
                    append_boot(&msg);
                    eprintln!("{msg}");
                }
            }
            append_boot(&format!("reusing API already listening on {API_PORT}"));
            return Ok(());
        }
        if cfg!(debug_assertions) {
            let msg = format!(
                "port {API_PORT} in use but /api/health failed (dev). \
                 Stop the stale process: kill $(lsof -ti:{API_PORT})"
            );
            append_boot(&msg);
            return Err(msg);
        }
        append_boot(&format!(
            "port {API_PORT} in use but /api/health failed — stopping stale listener"
        ));
        stop_process_on_port(API_PORT);
    }

    let python = resolve_python(app, &root);
    let sessions = expected_sessions;
    fs::create_dir_all(&sessions).map_err(|e| e.to_string())?;

    let log_dir = agent_log_dir();
    fs::create_dir_all(&log_dir).map_err(|e| e.to_string())?;
    let api_log = log_dir.join("agent-lab-api.log");
    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&api_log)
        .map_err(|e| format!("Failed to open {}: {e}", api_log.display()))?;
    let stderr_file = log_file
        .try_clone()
        .map_err(|e| format!("Failed to clone log handle: {e}"))?;

    append_boot(&format!(
        "starting api root={} python={} sessions={}",
        root.display(),
        python.display(),
        sessions.display()
    ));

    let config_dir = agent_config_dir();
    let _ = fs::create_dir_all(&config_dir);

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
    .env("AGENT_LAB_CONFIG_DIR", &config_dir)
    .env("AGENT_LAB_LOG_DIR", &log_dir)
    .env("PATH", path_for_subprocess())
    .stdout(Stdio::from(log_file))
    .stderr(Stdio::from(stderr_file));

    if let Some(dotenv) = resolve_dotenv_path(&root) {
        cmd.env("DOTENV_PATH", dotenv);
    }

    let child = cmd.spawn().map_err(|e| {
        let msg = format!(
            "Failed to start API ({:?}): {}. See {}",
            python,
            e,
            log_dir.join("agent-lab-boot.log").display()
        );
        append_boot(&msg);
        if cfg!(debug_assertions) {
            format!("{msg}. Run `make install` in {}", root.display())
        } else {
            msg
        }
    })?;

    let mut child_slot = Some(child);
    if !wait_for_api(30_000, &mut child_slot) {
        if let Some(mut dead) = child_slot.take() {
            let _ = dead.kill();
            let _ = dead.wait();
        }
        let msg = format!(
            "API did not become healthy on port {} within 30s. See {}",
            API_PORT,
            api_log.display()
        );
        append_boot(&msg);
        return Err(msg);
    }

    append_boot(&format!("api ready on port {API_PORT}"));
    *state.0.lock().unwrap() = child_slot;
    Ok(())
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.set_focus();
    }
}

/// Release builds load UI from uvicorn (http://127.0.0.1:8765) so fetch/SSE share the API origin.
/// https://tauri.localhost → http://127.0.0.1 is blocked by WebKit mixed-content ("Load failed").
fn navigate_main_to_api_origin(app: &tauri::AppHandle) -> Result<(), String> {
    if cfg!(debug_assertions) {
        show_main_window(app);
        return Ok(());
    }
    let win = app
        .get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())?;
    let url = format!("http://127.0.0.1:{API_PORT}/")
        .parse()
        .map_err(|e: url::ParseError| e.to_string())?;
    win.navigate(url)
        .map_err(|e| format!("webview navigate failed: {e}"))?;
    append_boot(&format!("webview at http://127.0.0.1:{API_PORT}/"));
    show_main_window(app);
    Ok(())
}

fn stop_api(state: &ApiServer) {
    if let Some(mut child) = state.0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn spawn_api_supervisor(app: tauri::AppHandle) {
    thread::spawn(move || {
        let mut unhealthy_streak = 0u8;
        loop {
            thread::sleep(Duration::from_secs(4));
            if skip_tauri_api() {
                continue;
            }
            let api_state = app.state::<ApiServer>();
            let child_exited = {
                let mut guard = api_state.0.lock().unwrap();
                match guard.as_mut() {
                    Some(child) => child
                        .try_wait()
                        .map(|opt| opt.is_some())
                        .unwrap_or(true),
                    None => true,
                }
            };
            if api_health_ok() {
                unhealthy_streak = 0;
                continue;
            }
            if child_exited {
                append_boot("supervisor: API exited — restarting");
                unhealthy_streak = 0;
                if let Err(e) = start_api(&app, &api_state) {
                    append_boot(&format!("supervisor: restart failed: {e}"));
                }
                continue;
            }
            unhealthy_streak += 1;
            if unhealthy_streak >= 3 {
                append_boot("supervisor: API unhealthy — restarting");
                stop_api(&api_state);
                unhealthy_streak = 0;
                if let Err(e) = start_api(&app, &api_state) {
                    append_boot(&format!("supervisor: restart failed: {e}"));
                }
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run_app() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .manage(ApiServer(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            // Start API in background so a slow/failed uvicorn boot never blocks the webview.
            thread::spawn(move || {
                if cfg!(debug_assertions) {
                    // Vite's ensure-dev-api.mjs owns :8765 during `tauri dev`.
                    if skip_tauri_api() {
                        append_boot("dev: API startup skipped (AGENT_LAB_SKIP_TAURI_API)");
                    } else {
                        // Fallback when launching the debug binary without Vite.
                        let api_state = handle.state::<ApiServer>();
                        match start_api(&handle, &api_state) {
                            Ok(()) => spawn_api_supervisor(handle.clone()),
                            Err(e) => append_boot(&format!(
                                "dev: API not auto-started ({e}); run `make api`"
                            )),
                        }
                    }
                    let _ = navigate_main_to_api_origin(&handle);
                    return;
                }
                let api_state = handle.state::<ApiServer>();
                match start_api(&handle, &api_state) {
                    Ok(()) => {
                        spawn_api_supervisor(handle.clone());
                        if let Err(e) = navigate_main_to_api_origin(&handle) {
                            append_boot(&format!("UI navigate failed: {e}"));
                            eprintln!("{e}");
                            show_main_window(&handle);
                        }
                    }
                    Err(e) => {
                        let msg = format!("API start failed: {e}");
                        append_boot(&msg);
                        eprintln!("{msg}");
                        show_main_window(&handle);
                    }
                }
            });
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

#[cfg(test)]
mod tests {
    use super::http_response_body;

    #[test]
    fn http_response_body_parses_nested_health_json() {
        let raw = concat!(
            "HTTP/1.1 200 OK\r\n",
            "content-type: application/json\r\n",
            "connection: close\r\n",
            "\r\n",
            r#"{"ok":true,"room":{"default_agent_parallel_rounds":1,"context":{"agent":{"recent_turns":4}}}}"#,
        );
        let body = http_response_body(raw).expect("body");
        assert!(body.contains(r#""ok":true"#));
        assert!(body.contains("default_agent_parallel_rounds"));
    }
}
