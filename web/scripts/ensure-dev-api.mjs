/**
 * Start uvicorn on :8765 before Vite proxies /api (any dev entry: tauri, vite, 5173/1420).
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

let child = null;
let startedHere = false;

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

/** Port taken but uvicorn still booting — wait before killing a duplicate listener. */
async function waitForExistingApi(maxMs = 15_000) {
  const steps = Math.ceil(maxMs / 400);
  for (let i = 0; i < steps; i += 1) {
    if (await apiHealthy()) {
      console.log(`[agent-lab] API already on http://127.0.0.1:${API_PORT}`);
      return true;
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

function isAgentLabUvicorn(command) {
  return AGENT_LAB_UVICORN_MARKERS.some((marker) => command.includes(marker));
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

function stopStaleApiOnPort() {
  const listeners = listPortListeners();
  const agentLab = listeners.filter((row) => isAgentLabUvicorn(row.command));
  const foreign = listeners.filter((row) => !isAgentLabUvicorn(row.command));

  if (foreign.length > 0) {
    throw new Error(
      `[agent-lab] Port ${API_PORT} is held by a non–Agent Lab process:\n` +
        foreign.map((row) => `  pid ${row.pid}: ${row.command}`).join("\n") +
        `\nStop it manually, then retry:\n` +
        `  kill $(lsof -ti:${API_PORT})\n` +
        `  make tauri-dev`,
    );
  }

  const pids = [...new Set(agentLab.map((row) => row.pid))];
  killPids(pids, "TERM");
  try {
    execSync(`pkill -f "uvicorn app.server.main:app" 2>/dev/null || true`, {
      stdio: "ignore",
    });
  } catch {
    /* best-effort */
  }

  if (!pids.length) {
    try {
      execSync(
        `lsof -ti tcp:${API_PORT} 2>/dev/null | xargs kill -TERM 2>/dev/null || true`,
        { stdio: "ignore" },
      );
    } catch {
      /* best-effort */
    }
  }
}

async function waitPortClosed(maxMs = 6_000) {
  const steps = Math.ceil(maxMs / 250);
  for (let i = 0; i < steps; i += 1) {
    if (!(await portOpen())) return true;
    if (i === 3) {
      const pids = listPortListeners().map((row) => row.pid);
      killPids(pids, 9);
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
  stopStaleApiOnPort();
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

export async function ensureDevApi() {
  if (await apiHealthy()) {
    console.log(`[agent-lab] API already on http://127.0.0.1:${API_PORT}`);
    return;
  }

  if (await portOpen()) {
    if (await waitForExistingApi()) {
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
  startedHere = true;

  child.on("exit", (code, signal) => {
    if (startedHere && code !== 0 && code !== null) {
      console.error(`[agent-lab] API exited (code=${code}, signal=${signal})`);
    }
  });

  const onExit = () => stopChild();
  process.on("SIGINT", onExit);
  process.on("SIGTERM", onExit);
  process.on("exit", onExit);

  for (let i = 0; i < 90; i += 1) {
    if (await apiHealthy()) {
      console.log("[agent-lab] API ready");
      return;
    }
    if (child.exitCode !== null) {
      throw new Error("[agent-lab] API process exited before becoming healthy");
    }
    await sleep(400);
  }

  throw new Error(
    `[agent-lab] API did not respond on :${API_PORT} within ~36s`,
  );
}
