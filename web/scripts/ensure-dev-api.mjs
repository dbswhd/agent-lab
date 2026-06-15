/**
 * Start uvicorn on :8765 before Vite proxies /api (any dev entry: tauri, vite, 5173/1420).
 */
import { spawn } from "node:child_process";
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

/** Port taken but uvicorn still booting — wait before spawning a duplicate. */
async function waitForExistingApi(maxMs = 30_000) {
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
    throw new Error(
      `[agent-lab] Port ${API_PORT} is in use but /api/health is not ready.\n` +
        `Stop the stale process: kill $(lsof -ti:${API_PORT})`,
    );
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
