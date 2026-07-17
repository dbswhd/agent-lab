import { expect, test, type Page } from "playwright/test";

const agents = Array.from({ length: 6 }, (_, index) => ({
  id: `agent-${index + 1}`,
  label: `Agent ${index + 1}`,
  ready: true,
  configured: true,
  bridge: "n/a",
  model: `provider/model-with-a-long-name-${index + 1}`,
}));

async function mockApi(page: Page) {
  await page.route(/^http:\/\/127\.0\.0\.1:4173\/api\//, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/health") {
      await route.fulfill({ json: { ok: true, agents } });
      return;
    }
    if (url.pathname === "/api/sessions") {
      await route.fulfill({
        json: {
          sessions: [
            {
              id: "existing-session",
              topic: "Existing session",
              updated_at: "2026-06-20T00:00:00Z",
            },
          ],
        },
      });
      return;
    }
    if (url.pathname === "/api/commands") {
      await route.fulfill({
        json: {
          ok: true,
          commands: [
            {
              id: "model",
              slash: "/model",
              label: "Model",
              kind: "server",
              enabled: true,
            },
          ],
        },
      });
      return;
    }
    if (url.pathname === "/api/auth/providers") {
      await route.fulfill({ json: { ok: true, providers: [] } });
      return;
    }
    if (url.pathname === "/api/health/flags") {
      await route.fulfill({ json: { ok: true, count: 0, flags: [] } });
      return;
    }
    if (url.pathname === "/api/session-setup/options") {
      await route.fulfill({
        json: {
          workspaces: [
            {
              id: "agent-lab",
              label: "agent-lab",
              path: "/workspace/agent-lab",
              available: true,
            },
          ],
          defaults: {
            workspace_id: "agent-lab",
            session_template: "general",
          },
        },
      });
      return;
    }
    await route.fulfill({ json: { ok: true } });
  });
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("agent-lab-first-run-onboarding-version", "p1f");
    if (!localStorage.getItem("agent-lab.settings-category")) {
      localStorage.setItem("agent-lab.settings-category", "general");
    }
  });
  await mockApi(page);
  await page.goto("/");
});

test("workspace-only session and scalable composer models", async ({
  page,
}) => {
  await expect(page.locator(".composer-model-select")).toBeVisible();
  await expect(page.locator(".composer-model-select__more")).toHaveText("+5");
  await page.getByRole("button", { name: "+ 새 Session" }).click();
  const dialog = page.getByRole("dialog", { name: "새 세션" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("/workspace/agent-lab")).toBeVisible();
  await expect(dialog.getByText("세션 템플릿")).toHaveCount(0);
  await expect(dialog.getByText("이 세션에 참여할 에이전트")).toHaveCount(0);
});

test("settings category navigation persists and fits narrow screens", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.locator(".settings-panel--general")).toBeVisible();
  await page.setViewportSize({ width: 768, height: 800 });
  await page.locator("#settings-category").selectOption("advanced");
  await expect(page.locator(".settings-panel--advanced").first()).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.locator("#settings-category")).toHaveValue("advanced");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    768,
  );
});
