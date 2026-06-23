import { expect, test, type Page } from "playwright/test";

const planMarkdown = `## 목표
승인 흐름을 한 번의 결정으로 단순화합니다.

## 지금 실행
1.
   - 무엇을: 계획 승인 화면을 단일 결정 surface로 정리
   - 어디서: \`web/src/components/PlanApprovalPanel.tsx\`
   - 검증: \`npm run test\`와 반응형 화면 확인

## 영향 영역
- Plan 승인 UI
- execute dry-run 연결`;

const recommendedAction = {
  index: 1,
  what: "계획 승인 화면을 단일 결정 surface로 정리",
  where: "web/src/components/PlanApprovalPanel.tsx",
  verify: "npm run test와 반응형 화면 확인",
  refs: [],
  expected_paths: ["web/src/components/PlanApprovalPanel.tsx"],
  recommended: true,
  kind: "now",
  executable: true,
  isolation: "worktree",
};

type FixtureOptions = {
  cursorReady?: boolean;
  hasAction?: boolean;
  blockingObjection?: boolean;
  dryRunFailure?: boolean;
};

async function mockPlanApprovalApi(
  page: Page,
  requests: string[],
  options: FixtureOptions = {},
) {
  let approved = false;
  const cursorReady = options.cursorReady ?? true;
  const hasAction = options.hasAction ?? true;
  const blockingObjection = options.blockingObjection ?? false;
  await page.route(/^http:\/\/127\.0\.0\.1:4173\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const key = `${request.method()} ${url.pathname}`;

    if (url.pathname === "/api/health") {
      await route.fulfill({
        json: {
          ok: true,
          api: { ok: true },
          agents: [
            {
              id: "cursor",
              label: "Cursor",
              ready: cursorReady,
              configured: true,
              bridge: cursorReady ? "ok" : "error",
            },
            {
              id: "codex",
              label: "Codex",
              ready: true,
              configured: true,
              bridge: "n/a",
            },
            {
              id: "claude",
              label: "Claude",
              ready: true,
              configured: true,
              bridge: "n/a",
            },
          ],
        },
      });
      return;
    }
    if (url.pathname === "/api/sessions") {
      await route.fulfill({
        json: {
          sessions: [
            {
              id: "plan-review",
              topic: "Plan approval review",
              updated_at: "2026-06-21T00:00:00Z",
              workflow: "room.parallel",
            },
          ],
        },
      });
      return;
    }
    if (url.pathname === "/api/sessions/plan-review") {
      await route.fulfill({
        json: {
          id: "plan-review",
          topic: "Plan approval review",
          plan_md: planMarkdown,
          transcript_md: "",
          meta: {},
          chat: [],
          run: {
            status: "idle",
            actions: hasAction ? [recommendedAction] : [],
            executions: [],
            plan_workflow: {
              enabled: true,
              phase: approved ? "APPROVED" : "HUMAN_PENDING",
              notice: approved ? "plan_approved" : "plan_pending_approval",
              last_plan_gate: { ok: true },
            },
          },
        },
      });
      return;
    }
    if (url.pathname === "/api/sessions/plan-review/plan-actions") {
      await route.fulfill({
        json: {
          recommended: hasAction ? recommendedAction : null,
          now: hasAction ? [recommendedAction] : [],
          roadmap: [],
          actions: hasAction ? [recommendedAction] : [],
        },
      });
      return;
    }
    if (url.pathname === "/api/sessions/plan-review/tasks") {
      await route.fulfill({
        json: {
          team_lead: "codex",
          agents: ["cursor", "codex", "claude"],
          tasks: [],
          claimable: [],
          counts: { pending: 0, in_progress: 0, completed: 0 },
          objections: blockingObjection
            ? [
                {
                  id: "objection-1",
                  from: "claude",
                  act: "BLOCK",
                  body: "보안 위험을 먼저 해결하세요.",
                  status: "open",
                  plan_action_index: 1,
                },
              ]
            : [],
          open_objections: blockingObjection
            ? [
                {
                  id: "objection-1",
                  from: "claude",
                  act: "BLOCK",
                  body: "보안 위험을 먼저 해결하세요.",
                  status: "open",
                  plan_action_index: 1,
                },
              ]
            : [],
          open_objection_count: blockingObjection ? 1 : 0,
        },
      });
      return;
    }
    if (url.pathname === "/api/sessions/plan-review/runtime") {
      await route.fulfill({
        json: {
          ok: true,
          session_id: "plan-review",
          mode: "standalone",
          has_plan: true,
          work_phase: "review_needed",
          mission: { enabled: false, phase: "idle", paused: false },
          execute: { has_pending: false, has_dry_run_diff: false },
          gates: {
            execute_blocked: false,
            pending_agreement: false,
          },
          inbox: {
            pending: false,
            pending_count: 0,
            pending_questions: 0,
            pending_builds: 0,
          },
          next_action: "계획 검토",
        },
      });
      return;
    }
    if (
      url.pathname === "/api/sessions/plan-review/plan/approve" &&
      request.method() === "POST"
    ) {
      requests.push(key);
      approved = true;
      await route.fulfill({
        json: {
          ok: true,
          plan_workflow: { enabled: true, phase: "APPROVED" },
          verified_loop: { status: "running" },
        },
      });
      return;
    }
    if (
      url.pathname === "/api/sessions/plan-review/execute/dry-run" &&
      request.method() === "POST"
    ) {
      requests.push(key);
      if (options.dryRunFailure) {
        await route.fulfill({ status: 500, body: "cursor unavailable" });
        return;
      }
      await route.fulfill({
        json: {
          ok: true,
          execution: {
            id: "execution-1",
            action_index: 1,
            action_kind: "now",
            status: "pending_approval",
            diff: "",
          },
        },
      });
      return;
    }
    if (url.pathname === "/api/commands") {
      await route.fulfill({ json: { ok: true, commands: [] } });
      return;
    }
    if (url.pathname === "/api/health/flags") {
      await route.fulfill({ json: { ok: true, count: 0, flags: [] } });
      return;
    }
    if (url.pathname === "/api/health/readiness") {
      await route.fulfill({
        json: { verdict: "ready", checks: [], next_actions: [] },
      });
      return;
    }
    if (url.pathname === "/api/auth/providers") {
      await route.fulfill({ json: { ok: true, providers: [] } });
      return;
    }
    await route.fulfill({ json: { ok: true } });
  });
}

async function initializePlanReview(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("agent-lab-first-run-onboarding-version", "p1f");
    localStorage.setItem("agent-lab-inspector-open", "1");
    localStorage.setItem("agent-lab-locale", "ko");
  });
}

async function openPlanReview(page: Page) {
  await page.getByRole("button", { name: "Plan approval review" }).click();
  await page.getByRole("button", { name: "Workbench panel" }).click();
  await page
    .getByRole("menuitem", { name: "작업", exact: true })
    .first()
    .click();
  await expect(page.locator(".plan-approval-review")).toBeVisible();
}

test("plan review is one decision surface and approval starts dry-run", async ({
  page,
}) => {
  const requests: string[] = [];
  await initializePlanReview(page);
  await mockPlanApprovalApi(page, requests);
  await page.goto("/");
  await openPlanReview(page);

  const review = page.locator(".plan-approval-review");
  await expect(
    review.getByRole("heading", { name: "계획 검토" }),
  ).toBeVisible();
  await expect(review.locator(".plan-action")).toHaveCount(1);
  await expect(
    review.getByRole("button", { name: "승인하고 실행" }),
  ).toBeVisible();
  await expect(review.locator(".btn--primary")).toHaveCount(1);
  await expect(page.locator(".work-decision")).toHaveCount(0);
  await expect(review).not.toContainText("completion promise");
  await expect(review).not.toContainText("CLARIFY");
  await expect(review).not.toContainText("DRAFT");
  await expect(review).not.toContainText("REFINE");

  const approveAndExecute = review.getByRole("button", {
    name: "승인하고 실행",
  });
  await approveAndExecute.focus();
  await page.keyboard.press("Tab");
  await expect(
    review.getByRole("button", { name: "승인만", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(review.getByRole("button", { name: "수정 요청" })).toBeFocused();

  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(review).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBe(width);
    await page.screenshot({
      path: `/tmp/agent-lab-plan-approval-${width}.png`,
      fullPage: true,
    });
  }

  await review.getByRole("button", { name: "수정 요청" }).click();
  await expect(review.locator("textarea")).toBeFocused();
  await expect(review.locator(".btn--primary")).toHaveCount(1);
  await expect(review.locator(".btn--primary")).toBeDisabled();
  await review.getByRole("button", { name: "취소" }).click();

  await review.getByRole("button", { name: "승인하고 실행" }).click();
  await expect
    .poll(() => requests)
    .toEqual([
      "POST /api/sessions/plan-review/plan/approve",
      "POST /api/sessions/plan-review/execute/dry-run",
    ]);
});

test("BLOCK objection disables approval and shows the reason", async ({
  page,
}) => {
  await initializePlanReview(page);
  await mockPlanApprovalApi(page, [], { blockingObjection: true });
  await page.goto("/");
  await openPlanReview(page);

  const review = page.locator(".plan-approval-review");
  await expect(review.getByRole("alert")).toContainText(
    "보안 위험을 먼저 해결하세요.",
  );
  await expect(
    review.getByRole("button", { name: "승인하고 실행" }),
  ).toBeDisabled();
});

for (const fixture of [
  { name: "no executable action", options: { hasAction: false } },
  { name: "Cursor unavailable", options: { cursorReady: false } },
]) {
  test(`${fixture.name} falls back to approve only`, async ({ page }) => {
    await initializePlanReview(page);
    await mockPlanApprovalApi(page, [], fixture.options);
    await page.goto("/");
    await openPlanReview(page);

    const review = page.locator(".plan-approval-review");
    await expect(
      review.getByRole("button", { name: "승인만", exact: true }),
    ).toBeVisible();
    await expect(
      review.getByRole("button", { name: "승인하고 실행" }),
    ).toHaveCount(0);
    await expect(review.locator(".btn--primary")).toHaveCount(1);
  });
}

test("dry-run failure keeps plan approval and offers retry", async ({
  page,
}) => {
  const requests: string[] = [];
  await initializePlanReview(page);
  await mockPlanApprovalApi(page, requests, { dryRunFailure: true });
  await page.goto("/");
  await openPlanReview(page);

  await page
    .locator(".plan-approval-review")
    .getByRole("button", { name: "승인하고 실행" })
    .click();

  await expect
    .poll(() => requests)
    .toEqual([
      "POST /api/sessions/plan-review/plan/approve",
      "POST /api/sessions/plan-review/execute/dry-run",
    ]);
  await expect(page.locator(".plan-approval-review")).toHaveCount(0);
  await expect(
    page.locator(".work-surface--alert .plan-card__error"),
  ).toHaveText("cursor unavailable");
  await expect(page.getByRole("button", { name: "Dry-run" })).toBeVisible();
});
