import { defineConfig } from "playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Inherited by test workers; evidence is retained in this isolated temp folder.
const sandbox = process.env.AGENT_LAB_IDEATION_E2E_ROOT ??
  mkdtempSync(join(tmpdir(), "agent-lab-ideation-e2e-"));
process.env.AGENT_LAB_IDEATION_E2E_ROOT = sandbox;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "ideation-real-server.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: "http://127.0.0.1:4178",
    colorScheme: "dark",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "../.venv/bin/python ../tests/support/ideation_e2e_server.py",
      url: "http://127.0.0.1:8877/api/health",
      env: { AGENT_LAB_IDEATION_E2E_ROOT: sandbox },
      reuseExistingServer: false,
      timeout: 90_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4178 --strictPort",
      url: "http://127.0.0.1:4178",
      env: { VITE_SKIP_API: "1", VITE_API_PROXY_TARGET: "http://127.0.0.1:8877" },
      reuseExistingServer: false,
    },
  ],
});
