#!/usr/bin/env node
/** Automated browser DOM smoke. The Tauri real-window scenario is separate. */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(new URL("../web/package.json", import.meta.url));
const { chromium } = require("playwright");

const BASE = process.env.AGENT_LAB_WEB_URL ?? "http://127.0.0.1:5173";
const ARTIFACT_DIR =
  process.env.AGENT_LAB_UI_ARTIFACT_DIR ?? "/tmp/agent-lab-ui-smoke/web";
const FIXTURE_TOPIC = "P0 UI smoke · pending dry-run diff";
const DIFF_MARKER = "P0_UI_DIFF_MARKER";
const errors = [];

function pass(msg) {
  console.log(`OK: ${msg}`);
}

function fail(msg) {
  errors.push(msg);
  console.error(`FAIL: ${msg}`);
}

async function dispatchShortcut(page, key, { ctrlKey = false } = {}) {
  await page.evaluate(
    ({ shortcutKey, withControl }) => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: shortcutKey,
          metaKey: true,
          ctrlKey: withControl,
          bubbles: true,
          cancelable: true,
        }),
      );
    },
    { shortcutKey: key, withControl: ctrlKey },
  );
}

async function main() {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });

  try {
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/api/session-setup/options") &&
          resp.status() === 200,
        { timeout: 15_000 },
      ),
      page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 30_000 }),
    ]);
  } catch (e) {
    fail(`could not load isolated smoke server ${BASE} (${e})`);
    await browser.close();
    process.exit(1);
  }

  // Ensure new-chat composer (not an existing session)
  const newChatBtn = page.getByRole("button", { name: /새 (대화|Session)/ });
  if ((await newChatBtn.count()) > 0) {
    await newChatBtn.click();
  }

  // New chat: workspace bar visible, no template field
  const browse = page.locator(".session-setup-bar__browse");
  try {
    await browse.first().waitFor({ state: "visible", timeout: 10_000 });
    pass("session setup — 폴더 선택 button present");
  } catch {
    fail("session setup — 폴더 선택 button missing (setup API or new chat?)");
  }

  const templateLabel = page.getByText("템플릿", { exact: true });
  if ((await templateLabel.count()) === 0) {
    pass("session setup — template UI absent");
  } else {
    fail("session setup — template UI still visible");
  }

  // In-app mac notification (dev hook)
  await page.evaluate(() => {
    window.__agentLabPushNotify?.({
      title: "[smoke] plan 갱신",
      body: "dry-run 확인 대기",
    });
  });
  const toast = page.locator(".mac-notification").first();
  try {
    await toast.waitFor({ state: "visible", timeout: 5000 });
    const title = await toast.locator(".mac-notification-title").textContent();
    if (title?.includes("smoke")) {
      pass("in-app mac notification stack renders");
    } else {
      fail(`mac notification title unexpected: ${title}`);
    }
  } catch {
    fail("mac notification toast did not appear");
  }

  // desktopNotify module exposes ensureDesktopNotifyPermission
  const notifyApi = await page
    .evaluate(async (base) => {
      try {
        const mod = await import(`${base}/src/utils/desktopNotify.ts`);
        return {
          ensure: typeof mod.ensureDesktopNotifyPermission === "function",
          notify: typeof mod.notifyDesktop === "function",
        };
      } catch {
        return { ensure: false, notify: false };
      }
    }, BASE)
    .catch(() => ({ ensure: false, notify: false }));

  if (notifyApi.ensure && notifyApi.notify) {
    pass("desktopNotify — ensure + notify exports load in browser");
  } else {
    fail("desktopNotify module failed to load via Vite");
  }
  await page.getByRole("button", { name: "알림 닫기" }).click();

  try {
    const sessionSearch = page.getByRole("searchbox", { name: "세션 검색" });
    await sessionSearch.waitFor({ state: "visible", timeout: 5000 });
    await sessionSearch.fill("pending dry-run diff");
    pass("session search filters the sidebar");

    const fixture = page.getByRole("button", { name: new RegExp(FIXTURE_TOPIC) });
    await fixture.waitFor({ state: "visible", timeout: 10_000 });
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/api/sessions/ui_pending_diff") &&
          resp.status() === 200,
        { timeout: 10_000 },
      ),
      fixture.press("Enter"),
    ]);
    pass("session row is keyboard-selectable after search");

    await dispatchShortcut(page, "3");
    const pendingRegion = page.getByRole("region", {
      name: "승인 대기",
      exact: true,
    });
    await pendingRegion.waitFor({ state: "visible", timeout: 10_000 });
    pass("Cmd+3 opens review");
    await pendingRegion.locator("summary", { hasText: "로컬 diff" }).waitFor({
      state: "visible",
      timeout: 10_000,
    });
    const diffMarker = pendingRegion
      .locator(".plan-execute-pending__diff")
      .getByText(DIFF_MARKER, { exact: false })
      .first();
    await diffMarker.waitFor({ state: "visible", timeout: 10_000 });
    await diffMarker.scrollIntoViewIfNeeded();
    pass("session → review → pending dry-run diff DOM path");
  } catch (e) {
    fail(`pending dry-run diff DOM path failed (${e})`);
  }

  try {
    await dispatchShortcut(page, "1");
    const transcriptTab = page
      .locator(".workspace-tab-bar")
      .getByRole("tab", { name: "Transcript", exact: true });
    await transcriptTab.waitFor({ state: "visible", timeout: 5000 });
    if ((await transcriptTab.getAttribute("aria-selected")) !== "true") {
      throw new Error("workspace transcript tab was not selected");
    }
    pass("Cmd+1 opens transcript");

    const shell = page.locator(".workspace-shell");
    const before = await shell.getAttribute("class");
    await dispatchShortcut(page, "s", { ctrlKey: true });
    const after = await shell.getAttribute("class");
    if (before !== after) {
      pass("Ctrl+Cmd+S toggles sidebar");
    } else {
      fail("Ctrl+Cmd+S did not toggle sidebar");
    }

    await dispatchShortcut(page, "n");
    await page.getByRole("button", { name: "폴더 선택" }).first().waitFor({
      state: "visible",
      timeout: 5000,
    });
    pass("Cmd+N opens new session");

    await dispatchShortcut(page, "s", { ctrlKey: true });
    await page.getByRole("searchbox", { name: "세션 검색" }).fill(
      "pending dry-run diff",
    );
    await page
      .getByRole("button", { name: new RegExp(FIXTURE_TOPIC) })
      .press("Enter");
    await dispatchShortcut(page, "3");
    await page
      .getByRole("region", { name: "승인 대기", exact: true })
      .waitFor({
        state: "visible",
        timeout: 5000,
      });
  } catch (e) {
    fail(`desktop keyboard shortcuts failed (${e})`);
  }

  for (const theme of ["light", "dark"]) {
    await page.evaluate((nextTheme) => {
      localStorage.setItem("agent-lab-theme", nextTheme);
      document.documentElement.setAttribute("data-theme", nextTheme);
    }, theme);
    for (const viewport of [
      { name: "wide", width: 1280, height: 860 },
      { name: "minimum", width: 900, height: 600 },
    ]) {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      const screenshot = path.join(
        ARTIFACT_DIR,
        `pending-diff-${theme}-${viewport.name}.png`,
      );
      await page.screenshot({ path: screenshot });
      pass(`baseline screenshot — ${theme}/${viewport.name}`);
    }
  }

  await browser.close();

  if (errors.length) {
    console.error(`\n${errors.length} failure(s)`);
    process.exit(1);
  }
  console.log(`\nsmoke_web_ui: all checks passed\nArtifacts: ${ARTIFACT_DIR}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
