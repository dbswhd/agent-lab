import { expect, test } from "playwright/test";

/**
 * Real-server checkpoint: only the provider boundary is deterministic.  The
 * browser talks to Vite, Vite proxies HTTP/SSE to the real FastAPI process,
 * and every ideation mutation is read back from the session store.
 */

async function initialize(page: import("playwright/test").Page) {
  await page.addInitScript(() => {
    localStorage.setItem("agent-lab-first-run-onboarding-version", "p1f");
    localStorage.setItem("agent-lab-first-run-onboarding-dismissed", "1");
    localStorage.setItem("agent-lab-locale", "ko");
  });
}

async function startIdeationTurn(page: import("playwright/test").Page, topic: string) {
  return page.evaluate(async (value) => {
    const form = new FormData();
    form.append("topic", value);
    form.append("agents", JSON.stringify(["cursor", "codex", "claude"]));
    form.append("agent_rounds", "1");
    form.append("preset", "supervisor");
    form.append("workspace_id", "agent-lab");
    form.append("ideation", "true");
    form.append("permissions", "{}");
    const response = await fetch("/api/room/runs", { method: "POST", body: form });
    if (!response.ok) throw new Error(await response.text());
    const text = await response.text();
    const complete = text
      .split("\n")
      .filter((line) => line.startsWith("data: "))
      .map((line) => {
        try { return JSON.parse(line.slice(6)) as Record<string, unknown>; } catch { return null; }
      })
      .find((event) => event?.type === "complete");
    if (!complete?.session_id) throw new Error(`no complete event: ${text.slice(-500)}`);
    return String(complete.session_id);
  }, topic);
}

test("real browser journey persists concept shaping and an explicit plan", async ({ page }) => {
  const topic = `E2E 강의자료 학습 도구 ${Date.now()}`;
  await initialize(page);
  await page.goto("/");
  const sessionId = await startIdeationTurn(page, topic);

  await page.reload();
  const sessionButton = page.locator(".session-item", { hasText: topic });
  await expect(sessionButton).toBeVisible();
  await sessionButton.click();

  const panel = page.locator(".concept-panel");
  await expect(panel).toBeVisible();
  await expect(panel.locator(".concept-candidate")).toHaveCount(3);
  await panel.locator(".concept-candidate").first().getByRole("button", { name: "이걸로" }).click();

  const editor = panel.locator(".concept-panel__editor");
  await expect(editor).toBeVisible();
  await editor.locator("textarea").nth(0).fill("iOS 전용\n2주 안에");
  await editor.getByRole("button", { name: "조건 저장" }).click();
  await expect(panel).toContainText("rev");
  await editor.locator("textarea").nth(1).fill("한 과목의 출석과 과제를 출처와 함께 복습한다");
  await editor.getByRole("button", { name: "구체화 저장" }).click();
  await expect(editor.getByRole("button", { name: "계획 만들기" })).toBeEnabled();
  await editor.getByRole("button", { name: "계획 만들기" }).click();
  await expect(editor.getByRole("button", { name: "계획 준비됨" })).toBeVisible();

  const stored = await page.evaluate(async (id) => {
    const [idea, detail] = await Promise.all([
      fetch(`/api/sessions/${encodeURIComponent(id)}/ideation`).then((r) => r.json()),
      fetch(`/api/sessions/${encodeURIComponent(id)}`).then((r) => r.json()),
    ]);
    return { idea, detail };
  }, sessionId);
  expect(stored.idea.ideation.brief.constraints).toEqual(["iOS 전용", "2주 안에"]);
  expect(stored.idea.ideation.concept.summary).toContain("출석과 과제");
  expect(stored.idea.ideation.plan_status).toBe("ready");
  expect(stored.idea.ideation.plan_source_revision).toBe(stored.idea.ideation.revision);
  expect(stored.detail.plan_md).toContain("## 지금 실행");
  expect(stored.detail.run.executions ?? []).toEqual([]);

});
