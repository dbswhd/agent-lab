import { expect, test, type Page } from "playwright/test";

/**
 * Wave B live browser acceptance — real API (no /api route mocks).
 *
 * Requires:
 *   - seeded sessions via scripts/seed_wave_b_live_sessions.py
 *   - uvicorn with AGENT_LAB_SESSIONS_DIR pointing at that dir
 *   - Vite proxy to that API (VITE_API_PROXY_TARGET)
 *
 * Prefer: scripts/run_wave_b_live_acceptance.sh
 */

const TOPICS = {
  planReject: "Wave B live plan reject",
  diffApprove: "Wave B live diff approve",
  oracleRepair: "Wave B live Oracle repair",
  humanResume: "Wave B live human resume",
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
  // Session rail buttons may prefix "Needs input" when a gate is open.
  await page
    .getByRole("complementary", { name: /Sessions|세션/i })
    .getByRole("button", { name: new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
}

function trackPosts(page: Page, paths: string[]) {
  const hits: { path: string; body: Record<string, unknown>; status: number }[] =
    [];
  page.on("requestfinished", async (request) => {
    if (request.method() !== "POST") return;
    let pathname = "";
    try {
      pathname = new URL(request.url()).pathname;
    } catch {
      return;
    }
    if (!paths.some((p) => pathname.includes(p))) return;
    let body: Record<string, unknown> = {};
    try {
      body = (request.postDataJSON() as Record<string, unknown>) || {};
    } catch {
      body = {};
    }
    let status = 0;
    try {
      status = (await request.response())?.status() ?? 0;
    } catch {
      status = 0;
    }
    hits.push({ path: pathname, body, status });
  });
  return hits;
}

test.describe("Wave B live journeys", () => {
  test("plan reject journey", async ({ page }) => {
    await initialize(page);
    const hits = trackPosts(page, ["/plan/reject"]);
    await page.goto("/");
    await openSession(page, TOPICS.planReject);

    const review = page.locator(".plan-approval-strip");
    await expect(review).toBeVisible({ timeout: 20_000 });
    await review.getByRole("button", { name: "수정 요청" }).click();
    const textarea = review.locator("textarea#plan-revision-note-strip");
    await expect(textarea).toBeFocused();
    await textarea.fill("계획 범위를 축소해서 다시 작성해 주세요.");
    await review.getByRole("button", { name: "수정 요청" }).click();

    await expect.poll(() => hits.length).toBeGreaterThan(0);
    expect(hits[0]?.status).toBeLessThan(400);
    expect(hits[0]?.path).toContain("/plan/reject");
  });

  test("diff approve journey", async ({ page }) => {
    await initialize(page);
    const hits = trackPosts(page, ["/execute/resolve"]);
    await page.goto("/");
    await openSession(page, TOPICS.diffApprove);

    const card = page.getByRole("region", { name: "실행 승인 대기" });
    await expect(card).toBeVisible({ timeout: 20_000 });
    const approve = card.getByRole("button", { name: "승인" });
    await expect(approve).toBeEnabled();
    await approve.click();

    await expect.poll(() => hits.length).toBeGreaterThan(0);
    expect(hits[0]?.status).toBeLessThan(400);
    expect(hits[0]?.path).toContain("/execute/resolve");
  });

  test("Oracle repair journey", async ({ page }) => {
    await initialize(page);
    const hits = trackPosts(page, ["/execute/reverify"]);
    await page.goto("/");
    await openSession(page, TOPICS.oracleRepair);

    // Pending + Oracle fail → ExecuteQueueBar (same surface as mock suite).
    // Full merged worktree repair is out of scope; assert CTA posts reverify.
    const card = page.getByRole("region", { name: "실행 승인 대기" });
    await expect(card).toBeVisible({ timeout: 20_000 });
    await card.getByRole("button", { name: "Oracle 재검증" }).click();

    await expect.poll(() => hits.length).toBeGreaterThan(0);
    expect(hits[0]?.path).toContain("/execute/reverify");
    // 409 = execution not merged (expected for pending seed); proves wiring.
    expect([200, 409]).toContain(hits[0]?.status);
  });

  test("human resume journey", async ({ page }) => {
    await initialize(page);
    const hits = trackPosts(page, ["/inbox/"]);
    await page.goto("/");
    await openSession(page, TOPICS.humanResume);

    const inbox = page.locator(".human-inbox--composer");
    await expect(inbox).toBeVisible({ timeout: 20_000 });
    await expect(inbox).toContainText("실행 중 어떤 범위로 진행할까요?");

    await inbox.getByRole("radio", { name: /안전한 범위/ }).click();
    const submit = inbox.getByRole("button", { name: "제출" });
    await expect(submit).toBeEnabled();
    const waitResolve = page.waitForResponse(
      (res) =>
        res.request().method() === "POST" &&
        res.url().includes("/inbox/") &&
        res.url().includes("/resolve"),
      { timeout: 20_000 },
    );
    await submit.click();
    const response = await waitResolve;

    await expect.poll(() => hits.length).toBeGreaterThan(0);
    const hit = hits.find((row) => row.path.includes("/resolve"));
    expect(hit).toBeTruthy();
    expect(response.status()).toBeLessThan(400);
    expect(hit?.body).toMatchObject({
      decision_id: expect.any(String),
      mission_id: expect.any(String),
      expected_version: expect.any(Number),
      selected: ["safe"],
    });
  });
});
