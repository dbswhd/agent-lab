import { defineConfig } from "playwright/test";

const uiPort = Number(process.env.PHASE_B_UI_PORT || 4174);
const apiTarget =
  process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:18768";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/phase-b-small-mission-dogfood.spec.ts",
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
