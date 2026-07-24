import { expect, test, type Page } from "playwright/test";

/**
 * Phase B Small Mission dogfood — B1–B4 surfaces on real API (no /api mocks).
 *
 * Prefer: scripts/run_phase_b_small_mission_dogfood.sh
 */

const TOPICS = {
  gate: "Phase B small gate",
  evidence: "Phase B small evidence",
} as const;

async function initialize(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("agent-lab-first-run-onboarding-version", "p1f");
    localStorage.setItem("agent-lab-inspector-open", "1");
    localStorage.setItem("agent-lab-locale", "ko");
  });
}

async function openSession(page: Page, name: string) {
  await page.getByRole("tab", { name: /Dogfood/ }).click();
  await page
    .getByRole("complementary", { name: /Sessions|세션/i })
    .getByRole("button", {
      name: new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    })
    .click();
}

test.describe("Phase B Small Mission dogfood", () => {
  test("B1 Waiting chip + B3 Needs input age + B4 cost + small profile", async ({
    page,
  }) => {
    await initialize(page);
    await page.goto("/");
    await openSession(page, TOPICS.gate);

    const status = page.getByTestId("session-status-line");
    await expect(status).toBeVisible({ timeout: 20_000 });
    await expect(status).toContainText("small");
    await expect(status).toContainText("대기 중");
    await expect(page.getByTestId("session-cost-chip")).toBeVisible();
    await expect(page.getByTestId("session-cost-chip")).toContainText("$");

    const badge = page.getByTestId("needs-input-badge");
    await expect(badge).toBeVisible();
    await expect(page.getByTestId("needs-input-age")).toBeVisible();

    // B3 steer API (informational queue) — UI button needs mid-run; API proves polish path.
    const steer = await page.request.post(
      "/api/sessions/phase-b-small-gate/steer",
      { data: { text: "Prefer Small Mission scope only" } },
    );
    expect(steer.ok()).toBeTruthy();
    const steerBody = (await steer.json()) as { ok?: boolean; queued?: number };
    expect(steerBody.ok).toBe(true);
    expect((steerBody.queued ?? 0) > 0).toBe(true);
  });

  test("B2 evidence strip on ExecuteQueueBar", async ({ page }) => {
    await initialize(page);
    await page.goto("/");
    await openSession(page, TOPICS.evidence);

    const card = page.getByRole("region", { name: "실행 승인 대기" });
    await expect(card).toBeVisible({ timeout: 20_000 });
    const evidence = card.locator(".exec-queue-bar__evidence");
    await expect(evidence).toBeVisible();
    await expect(evidence).toContainText(/file|changed|\+/i);
    await expect(evidence).toContainText(/Oracle/i);
  });
});
