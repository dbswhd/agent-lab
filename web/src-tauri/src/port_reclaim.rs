//! Cross-platform reclamation of a TCP listen port (primarily :8765).

use std::process::Command;
use std::thread;
use std::time::Duration;

const RECLAIM_SLEEP_MS: u64 = 400;

/// Stop processes listening on `port`. Best-effort; safe to call when port is free.
pub fn stop_process_on_port(port: u16) {
    let _ = stop_process_on_port_impl(port);
    thread::sleep(Duration::from_millis(RECLAIM_SLEEP_MS));
}

fn stop_process_on_port_impl(port: u16) -> Result<usize, String> {
    let killed = pids_on_port(port)?;
    if killed.is_empty() {
        return Ok(0);
    }
    kill_pids(&killed)?;
    Ok(killed.len())
}

/// Human-readable recovery hint for error messages / boot logs.
pub fn port_conflict_hint(port: u16) -> String {
    #[cfg(unix)]
    {
        return format!("kill $(lsof -ti tcp:{port})");
    }
    #[cfg(windows)]
    {
        return format!(
            "netstat -ano -p tcp | findstr LISTENING | findstr :{port} — then taskkill /F /PID <pid>"
        );
    }
    #[cfg(not(any(unix, windows)))]
    {
        format!("free port {port} manually")
    }
}

#[cfg(unix)]
fn pids_on_port(port: u16) -> Result<Vec<u32>, String> {
    let script = format!("lsof -ti tcp:{port} 2>/dev/null || true");
    let output = Command::new("/bin/sh")
        .arg("-c")
        .arg(&script)
        .output()
        .map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&output.stdout);
    Ok(parse_pid_list(&text))
}

#[cfg(unix)]
fn kill_pids(pids: &[u32]) -> Result<(), String> {
    if pids.is_empty() {
        return Ok(());
    }
    let args: Vec<String> = pids.iter().map(|p| p.to_string()).collect();
    let mut cmd = Command::new("kill");
    cmd.arg("-9");
    for pid in &args {
        cmd.arg(pid);
    }
    let status = cmd.status().map_err(|e| e.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("kill exited with {status}"))
    }
}

#[cfg(windows)]
fn pids_on_port(port: u16) -> Result<Vec<u32>, String> {
    let output = Command::new("netstat")
        .args(["-ano", "-p", "tcp"])
        .output()
        .map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&output.stdout);
    Ok(parse_netstat_listen_pids(&text, port))
}

#[cfg(windows)]
fn kill_pids(pids: &[u32]) -> Result<(), String> {
    for pid in pids {
        let _ = Command::new("taskkill")
            .args(["/F", "/PID", &pid.to_string()])
            .status();
    }
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn pids_on_port(_port: u16) -> Result<Vec<u32>, String> {
    Ok(Vec::new())
}

#[cfg(not(any(unix, windows)))]
fn kill_pids(_pids: &[u32]) -> Result<(), String> {
    Ok(())
}

fn parse_pid_list(text: &str) -> Vec<u32> {
    text.split_whitespace()
        .filter_map(|t| t.parse::<u32>().ok())
        .collect()
}

/// Parse `netstat -ano -p tcp` output for LISTENING sockets on `port`.
#[cfg(target_os = "windows")]
pub fn parse_netstat_listen_pids(text: &str, port: u16) -> Vec<u32> {
    let port_token = format!(":{port}");
    let mut pids = Vec::new();
    for line in text.lines() {
        let upper = line.to_ascii_uppercase();
        if !upper.contains("LISTENING") {
            continue;
        }
        if !line.contains(&port_token) {
            continue;
        }
        let Some(pid) = line.split_whitespace().last() else {
            continue;
        };
        if let Ok(n) = pid.parse::<u32>() {
            if n > 0 {
                pids.push(n);
            }
        }
    }
    pids.sort_unstable();
    pids.dedup();
    pids
}

#[cfg(test)]
mod tests {
    use super::parse_netstat_listen_pids;

    #[test]
    fn netstat_parser_finds_listen_pid() {
        let sample = "\
  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:5173         0.0.0.0:0              LISTENING       9999
";
        assert_eq!(parse_netstat_listen_pids(sample, 8765), vec![4242]);
    }

    #[test]
    fn netstat_parser_ignores_non_listen() {
        let sample = "  TCP    127.0.0.1:8765         127.0.0.1:54321        ESTABLISHED     1111\n";
        assert!(parse_netstat_listen_pids(sample, 8765).is_empty());
    }
}
