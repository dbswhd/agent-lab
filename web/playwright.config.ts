import { defineConfig } from "playwright/test";

const portInput = process.env.PLAYWRIGHT_WEB_PORT ?? "4173";
if (!/^[1-9]\d{0,4}$/.test(portInput)) {
  throw new TypeError("PLAYWRIGHT_WEB_PORT must be a decimal TCP port");
}
const portNumber = Number(portInput);
if (portNumber > 65_535) {
  throw new RangeError("PLAYWRIGHT_WEB_PORT must be between 1 and 65535");
}
const port = String(portNumber);
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
