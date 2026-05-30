import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const host = process.env.TAURI_DEV_HOST;
const isTauri = Boolean(process.env.TAURI_ENV_PLATFORM);

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: isTauri ? 1420 : 5173,
    strictPort: isTauri,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
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
      },
    },
  },
});
