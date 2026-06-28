/**
 * Start uvicorn on :8765 before Vite proxies /api (any dev entry: tauri, vite, 5173/1420).
 * Keeps a lightweight watchdog so API restarts after crashes/reload without manual `make api`.
 */
import { execSync, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");
const PYTHON = path.join(ROOT, ".venv/bin/python");
const HEALTH_URL = "http://127.0.0.1:8765/api/health";
const API_PORT = 8765;
const WATCH_INTERVAL_MS = 4_000;
const UNHEALTHY_RESTART_AFTER = 3;
const RELOAD_WAIT_MS = 45_000;
const BOOT_WAIT_MS = 20_000;
const HUNG_HEALTH_TIMEOUT_MS = 5_000;
const HUNG_RESTART_AFTER = 3;

let child = null;
let startedHere = false;
let starting = false;
let watchdogStarted = false;
let unhealthyStreak = 0;
let restartTimer = null;
let reloadGraceUntil = 0;
let reloadWaitUsed = false;
let hungStreak = 0;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function portOpen() {
  const net = await import("node:net");
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port: API_PORT });
    const done = (open) => {
      socket.destroy();
      resolve(open);
    };
    socket.setTimeout(500);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
  });
}

async function isApiHung() {
  if (!(await portOpen())) return false;
  try {
    const res = await fetch(HEALTH_URL, {
      signal: AbortSignal.timeout(HUNG_HEALTH_TIMEOUT_MS),
    });
    if (!res.ok) return true;
    const body = await res.json();
    return !Boolean(body?.ok);
  } catch {
    return true;
  }
}

async function apiHealthy() {
  try {
    const res = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return false;
    const body = await res.json();
    return Boolean(body?.ok);
  } catch {
    return false;
  }
}

const AGENT_LAB_UVICORN_MARKERS = ["app.server.main:app", "uvicorn app.server.main"];

function getProcessInfo(pid) {
  try {
    const out = execSync(`ps -p ${pid} -o ppid=,command= 2>/dev/null`, {
      encoding: "utf8",
    }).trim();
    const match = out.match(/^(\d+)\s+(.*)$/s);
    if (!match) return null;
    return { ppid: match[1].trim(), command: match[2].trim() };
  } catch {
    return null;
  }
}

function isAgentLabUvicornCommand(command) {
  return AGENT_LAB_UVICORN_MARKERS.some((marker) => command.includes(marker));
}

function isAgentLabVenvPython(command) {
  return (
    command.includes(PYTHON) ||
    command.includes(path.join(ROOT, ".venv/bin/python"))
  );
}

function isUvicornReloadWorker(command) {
  return (
    command.includes("multiprocessing.spawn") ||
    command.includes("spawn_main(tracker_fd")
  );
}

/** uvicorn --reload worker/reloader: command line is not "uvicorn app.server.main". */
function isAgentLabProcessTree(pid, seen = new Set()) {
  if (!pid || seen.has(pid)) return false;
  seen.add(pid);

  const info = getProcessInfo(pid);
  if (!info) return false;

  if (isAgentLabUvicornCommand(info.command)) return true;

  if (
    isUvicornReloadWorker(info.command) &&
    isAgentLabVenvPython(info.command)
  ) {
    return true;
  }

  if (info.command.includes("uvicorn") && isAgentLabVenvPython(info.command)) {
    return true;
  }

  const ppid = info.ppid;
  if (!ppid || ppid === "0" || ppid === "1" || ppid === pid) {
    return false;
  }
  return isAgentLabProcessTree(ppid, seen);
}

function isAgentLabPortProcess(row) {
  return isAgentLabUvicornCommand(row.command) || isAgentLabProcessTree(row.pid);
}

function portOwnedByAgentLab() {
  const listeners = listPortListeners();
  return listeners.some((row) => isAgentLabPortProcess(row));
}

function markReloadGrace() {
  reloadGraceUntil = Date.now() + RELOAD_WAIT_MS;
}

function inReloadGrace() {
  return Date.now() < reloadGraceUntil;
}

/** Port taken but uvicorn still booting/reloading — wait before killing. */
async function waitForExistingApi(maxMs = RELOAD_WAIT_MS) {
  if (portOwnedByAgentLab()) {
    markReloadGrace();
  }
  const steps = Math.ceil(maxMs / 400);
  for (let i = 0; i < steps; i += 1) {
    if (await apiHealthy()) {
      console.log(`[agent-lab] API ready on http://127.0.0.1:${API_PORT}`);
      reloadGraceUntil = 0;
      return true;
    }
    if (i > 0 && i % 10 === 0) {
      console.log(
        `[agent-lab] Waiting for API on :${API_PORT}… (${Math.round((i * 400) / 1000)}s)`,
      );
    }
    await sleep(400);
  }
  return false;
}

function listPortListeners() {
  try {
    const out = execSync(`lsof -nP -iTCP:${API_PORT} -sTCP:LISTEN 2>/dev/null`, {
      encoding: "utf8",
    }).trim();
    if (!out) return [];
    return out
      .split("\n")
      .slice(1)
      .map((line) => {
        const parts = line.trim().split(/\s+/);
        const pid = parts[1];
        let command = parts[0] ?? "";
        try {
          command =
            execSync(`ps -p ${pid} -o command= 2>/dev/null`, { encoding: "utf8" }).trim() ||
            command;
        } catch {
          /* keep lsof command name */
        }
        return { pid, command };
      })
      .filter((row) => row.pid);
  } catch {
    return [];
  }
}

function describePortBlockers() {
  const listeners = listPortListeners();
  if (!listeners.length) {
    return "(no LISTEN socket found — port may still be releasing)";
  }
  return listeners.map((row) => `  pid ${row.pid}: ${row.command}`).join("\n");
}

function killPids(pids, signal) {
  if (!pids.length) return;
  try {
    execSync(`kill -${signal} ${pids.join(" ")} 2>/dev/null || true`, {
      stdio: "ignore",
    });
  } catch {
    /* best-effort */
  }
}

function killProcessTree(pid) {
  if (!pid) return;
  try {
    const children = execSync(`pgrep -P ${pid} 2>/dev/null || true`, {
      encoding: "utf8",
    })
      .trim()
      .split("\n")
      .filter(Boolean);
    for (const childPid of children) {
      killProcessTree(childPid);
    }
  } catch {
    /* best-effort */
  }
  killPids([pid], "TERM");
}

function stopAgentLabApiProcesses() {
  try {
    execSync(`pkill -f "uvicorn app.server.main:app" 2>/dev/null || true`, {
      stdio: "ignore",
    });
  } catch {
    /* best-effort */
  }

  if (child?.pid) {
    killProcessTree(String(child.pid));
  }

  const listeners = listPortListeners();
  for (const row of listeners) {
    if (isAgentLabPortProcess(row)) {
      killProcessTree(row.pid);
    }
  }

  try {
    execSync("sleep 0.4");
  } catch {
    /* best-effort */
  }

  const hung = listPortListeners().filter((row) => isAgentLabPortProcess(row));
  if (hung.length) {
    killPids(
      hung.map((row) => row.pid),
      9,
    );
  }

  const remaining = listPortListeners().filter((row) => !isAgentLabPortProcess(row));
  if (remaining.length === 0) {
    const pids = [...new Set(listeners.map((row) => row.pid))];
    if (pids.length) killPids(pids, "TERM");
    return;
  }

  throw new Error(
    `[agent-lab] Port ${API_PORT} is held by a non–Agent Lab process:\n` +
      remaining.map((row) => `  pid ${row.pid}: ${row.command}`).join("\n") +
      `\nStop it manually, then retry:\n` +
      `  kill $(lsof -ti:${API_PORT})\n` +
      `  make tauri-dev`,
  );
}

async function waitPortClosed(maxMs = 6_000) {
  const steps = Math.ceil(maxMs / 250);
  for (let i = 0; i < steps; i += 1) {
    if (!(await portOpen())) return true;
    if (i === 3) {
      stopAgentLabApiProcesses();
      try {
        execSync(
          `lsof -ti tcp:${API_PORT} 2>/dev/null | xargs kill -9 2>/dev/null || true`,
          { stdio: "ignore" },
        );
        execSync(`pkill -9 -f "uvicorn app.server.main:app" 2>/dev/null || true`, {
          stdio: "ignore",
        });
      } catch {
        /* best-effort */
      }
    }
    await sleep(250);
  }
  return !(await portOpen());
}

async function reclaimApiPort() {
  console.warn(
    `[agent-lab] Port ${API_PORT} is open but /api/health is not ready — stopping stale listener`,
  );
  stopAgentLabApiProcesses();
  if (!(await waitPortClosed())) {
    throw new Error(
      `[agent-lab] Port ${API_PORT} still in use after cleanup.\n${describePortBlockers()}\n` +
        `Run:\n` +
        `  kill $(lsof -ti:${API_PORT})\n` +
        `  make tauri-dev`,
    );
  }
}

function stopChild() {
  if (startedHere && child && !child.killed) {
    child.kill("SIGTERM");
  }
}

function attachChildHandlers(proc) {
  proc.on("exit", (code, signal) => {
    if (!startedHere || proc !== child) return;
    if (starting) return;
    child = null;
    startedHere = false;
    if (code === 0 && signal === null) {
      markReloadGrace();
      return;
    }
    console.warn(
      `[agent-lab] API exited (code=${code ?? "—"}, signal=${signal ?? "—"}) — scheduling restart`,
    );
    scheduleApiRestart("exit");
  });
}

function scheduleApiRestart(reason) {
  if (restartTimer) return;
  restartTimer = setTimeout(() => {
    restartTimer = null;
    void restartManagedApi(reason);
  }, 1_500);
}

async function restartManagedApi(reason) {
  if (process.env.VITEST || process.env.VITE_SKIP_API) return;
  if (starting) return;
  if (await apiHealthy()) {
    unhealthyStreak = 0;
    reloadGraceUntil = 0;
    return;
  }
  if (inReloadGrace() && portOwnedByAgentLab()) {
    return;
  }
  console.warn(`[agent-lab] Restarting API (${reason})…`);
  if (child && !child.killed) {
    child.kill("SIGTERM");
    await sleep(400);
  }
  child = null;
  startedHere = false;
  try {
    if (await portOpen()) {
      if (portOwnedByAgentLab()) {
        markReloadGrace();
        if (await waitForExistingApi(RELOAD_WAIT_MS)) return;
      } else if (await waitForExistingApi(8_000)) {
        return;
      }
      await reclaimApiPort();
    }
    await spawnManagedApi();
  } catch (err) {
    console.error(`[agent-lab] API restart failed: ${err instanceof Error ? err.message : err}`);
  }
}

async function spawnManagedApi() {
  if (starting) return;
  if (await apiHealthy()) {
    unhealthyStreak = 0;
    reloadGraceUntil = 0;
    return;
  }
  starting = true;
  try {
    if (await portOpen()) {
      if (portOwnedByAgentLab()) {
        markReloadGrace();
        if (await waitForExistingApi(RELOAD_WAIT_MS)) {
          return;
        }
      } else if (await waitForExistingApi()) {
        return;
      }
      await reclaimApiPort();
    }

    if (!fs.existsSync(PYTHON)) {
      throw new Error(
        `[agent-lab] Missing ${PYTHON}\nRun: cd ${ROOT} && make install`,
      );
    }

    console.log(`[agent-lab] Starting API → http://127.0.0.1:${API_PORT}`);
    process.env.AGENT_LAB_SKIP_TAURI_API = "1";

    child = spawn(
      PYTHON,
      [
        "-m",
        "uvicorn",
        "app.server.main:app",
        "--reload",
        "--reload-delay",
        "1",
        "--host",
        "127.0.0.1",
        "--port",
        String(API_PORT),
        "--reload-dir",
        "app",
        "--reload-dir",
        "src",
        "--reload-dir",
        "tests",
      ],
      {
        cwd: ROOT,
        stdio: "inherit",
        env: { ...process.env, AGENT_LAB_SKIP_TAURI_API: "1" },
      },
    );
    const proc = child;
    startedHere = true;
    markReloadGrace();
    attachChildHandlers(proc);

    for (let i = 0; i < 90; i += 1) {
      if (await apiHealthy()) {
        console.log("[agent-lab] API ready");
        unhealthyStreak = 0;
        reloadGraceUntil = 0;
        return;
      }
      if (proc.exitCode !== null) {
        if (portOwnedByAgentLab() && (await waitForExistingApi(8_000))) {
          return;
        }
        throw new Error(
          `[agent-lab] API process exited before becoming healthy (code=${proc.exitCode})`,
        );
      }
      await sleep(400);
    }

    throw new Error(
      `[agent-lab] API did not respond on :${API_PORT} within ~36s`,
    );
  } finally {
    starting = false;
  }
}

function startApiWatchdog() {
  if (watchdogStarted) return;
  if (process.env.VITEST || process.env.VITE_SKIP_API) return;
  watchdogStarted = true;

  setInterval(() => {
    void (async () => {
      if (starting) return;
      if (await apiHealthy()) {
        unhealthyStreak = 0;
        hungStreak = 0;
        reloadGraceUntil = 0;
        reloadWaitUsed = false;
        return;
      }

      if (await isApiHung() && portOwnedByAgentLab()) {
        const earlyReloadGrace =
          inReloadGrace() && Date.now() < reloadGraceUntil - 25_000;
        if (earlyReloadGrace) {
          return;
        }
        hungStreak += 1;
        if (hungStreak >= HUNG_RESTART_AFTER) {
          hungStreak = 0;
          reloadWaitUsed = false;
          console.warn(
            "[agent-lab] API hung on :8765 (port open, /api/health silent) — restarting",
          );
          scheduleApiRestart("hung");
          return;
        }
      } else {
        hungStreak = 0;
      }

      if (portOwnedByAgentLab()) {
        if (inReloadGrace()) {
          return;
        }
        if (!reloadWaitUsed) {
          reloadWaitUsed = true;
          markReloadGrace();
          console.log(
            `[agent-lab] API reloading on :${API_PORT} — waiting up to ${RELOAD_WAIT_MS / 1000}s`,
          );
          return;
        }
        unhealthyStreak += 1;
        if (unhealthyStreak < UNHEALTHY_RESTART_AFTER) return;
        unhealthyStreak = 0;
        reloadWaitUsed = false;
        scheduleApiRestart("watchdog-stuck-reload");
        return;
      }

      reloadWaitUsed = false;

      unhealthyStreak += 1;
      if (unhealthyStreak < UNHEALTHY_RESTART_AFTER) return;

      const listeners = listPortListeners();
      const ownsPort =
        startedHere ||
        listeners.some((row) => isAgentLabPortProcess(row)) ||
        listeners.length === 0;

      unhealthyStreak = 0;
      if (!ownsPort) {
        console.warn(
          "[agent-lab] API offline and port is not managed by Agent Lab — not auto-restarting",
        );
        return;
      }
      scheduleApiRestart("watchdog");
    })();
  }, WATCH_INTERVAL_MS);
}

export async function ensureDevApi() {
  if (process.env.VITEST || process.env.VITE_SKIP_API) return;

  console.log(`[agent-lab] Ensuring API on http://127.0.0.1:${API_PORT}…`);

  if (await apiHealthy()) {
    console.log(`[agent-lab] API ready on http://127.0.0.1:${API_PORT}`);
    startApiWatchdog();
    return;
  }

  if (await portOpen()) {
    if (portOwnedByAgentLab()) {
      console.log("[agent-lab] Port open — waiting for API health…");
      if (await waitForExistingApi(BOOT_WAIT_MS)) {
        startApiWatchdog();
        return;
      }
      console.warn("[agent-lab] Stale listener on :8765 — recycling");
      await reclaimApiPort();
    } else {
      throw new Error(
        `[agent-lab] Port ${API_PORT} is in use by another app:\n${describePortBlockers()}\n` +
          `Run: kill $(lsof -ti:${API_PORT}) && make tauri-dev`,
      );
    }
  }

  try {
    await spawnManagedApi();
  } catch (err) {
    console.error(`[agent-lab] API start failed: ${err instanceof Error ? err.message : err}`);
    if (!(await portOpen()) || !(await waitForExistingApi(BOOT_WAIT_MS))) {
      throw err;
    }
  }

  if (!(await apiHealthy())) {
    throw new Error(
      `[agent-lab] API did not become healthy on http://127.0.0.1:${API_PORT}`,
    );
  }

  const onExit = () => stopChild();
  process.on("SIGINT", onExit);
  process.on("SIGTERM", onExit);
  process.on("exit", onExit);

  startApiWatchdog();
}
