import { defineConfig } from "playwright/test";

const uiPort = Number(process.env.WAVE_B_LIVE_UI_PORT || 4173);
const apiTarget =
  process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:18765";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/wave-b-live-journey.spec.ts",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: `http://127.0.0.1:${uiPort}`,
    colorScheme: "dark",
    viewport: { width: 1280, height: 800 },
  },
  webServer: {
    command: `VITE_API_PROXY_TARGET=${apiTarget} npm run dev -- --host 127.0.0.1 --port ${uiPort}`,
    url: `http://127.0.0.1:${uiPort}`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
