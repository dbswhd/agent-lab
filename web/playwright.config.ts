import { defineConfig } from "playwright/test";

const port = process.env.PLAYWRIGHT_WEB_PORT ?? "4173";
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL,
    colorScheme: "dark",
    viewport: { width: 1280, height: 800 },
  },
  webServer: {
    command: `VITE_SKIP_API=1 npm run dev -- --host 127.0.0.1 --port ${port}`,
    url: baseURL,
    reuseExistingServer: false,
  },
});
