import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { ensureDevApi } from "./scripts/ensure-dev-api.mjs";

const host = process.env.TAURI_DEV_HOST;
const isTauri = Boolean(process.env.TAURI_ENV_PLATFORM);
const apiProxyTarget =
  process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8765";

/** Start uvicorn :8765 before the dev /api proxy accepts traffic. */
function agentLabDevApi() {
  return {
    name: "agent-lab-dev-api",
    async configureServer() {
      if (process.env.VITEST || process.env.VITE_SKIP_API) return;
      await ensureDevApi();
    },
  };
}

// Relative asset paths — required for Tauri production webview (tauri://localhost).
export default defineConfig({
  plugins: [agentLabDevApi(), react()],
  base: "./",
  clearScreen: false,
  envPrefix: ["VITE_", "TAURI_ENV_*"],
  build: {
    target:
      process.env.TAURI_ENV_PLATFORM === "windows" ? "chrome105" : "safari13",
    minify: process.env.TAURI_ENV_DEBUG ? false : "esbuild",
    sourcemap: Boolean(process.env.TAURI_ENV_DEBUG),
  },
  server: {
    port: isTauri ? 1420 : 5173,
    strictPort: isTauri,
    // 127.0.0.1 avoids macOS localhost → ::1 mismatch with Tauri devUrl.
    host: host || (isTauri ? "127.0.0.1" : false),
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : isTauri
        ? {
            protocol: "ws",
            host: "127.0.0.1",
            port: 1421,
          }
        : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
        timeout: 120_000,
        proxyTimeout: 120_000,
        configure: (proxy) => {
          proxy.on("error", (err, _req, res) => {
            if (!res || res.headersSent) return;
            res.writeHead(503, { "Content-Type": "application/json" });
            res.end(
              JSON.stringify({
                ok: false,
                error: "api_offline",
                message: "API(8765) reconnecting — retry shortly",
                detail: String(err?.message ?? err),
              }),
            );
          });
          proxy.on("proxyRes", (proxyRes) => {
            const ct = String(proxyRes.headers["content-type"] ?? "");
            if (ct.includes("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
              proxyRes.headers["x-accel-buffering"] = "no";
            }
          });
        },
      },
    },
  },
});
