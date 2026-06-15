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

/** Port taken but uvicorn still booting — wait before killing a duplicate listener. */
async function waitForExistingApi(maxMs = 8_000) {
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

function stopStaleApiOnPort() {
  try {
    execSync(
      `lsof -ti tcp:${API_PORT} 2>/dev/null | xargs kill -9 2>/dev/null || true`,
      { stdio: "ignore" },
    );
  } catch {
    /* best-effort */
  }
}

async function reclaimApiPort() {
  console.warn(
    `[agent-lab] Port ${API_PORT} is open but /api/health is not ready — stopping stale listener`,
  );
  stopStaleApiOnPort();
  await sleep(500);
  if (await portOpen()) {
    throw new Error(
      `[agent-lab] Port ${API_PORT} still in use after cleanup.\n` +
        `Run: kill $(lsof -ti:${API_PORT})`,
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
