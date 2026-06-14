import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { ensureDevApi } from "./scripts/ensure-dev-api.mjs";

const host = process.env.TAURI_DEV_HOST;
const isTauri = Boolean(process.env.TAURI_ENV_PLATFORM);

/** Start uvicorn :8765 before the /api proxy accepts traffic. */
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
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
