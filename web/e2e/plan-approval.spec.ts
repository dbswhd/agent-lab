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
  question?: boolean;
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
  const question = options.question ?? false;
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
            plan_workflow: question
              ? { enabled: false, phase: "INACTIVE" }
              : {
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
            pending: question,
            pending_count: question ? 1 : 0,
            pending_questions: question ? 1 : 0,
            pending_builds: 0,
          },
          next_action: "계획 검토",
        },
      });
      return;
    }
    if (url.pathname === "/api/inbox/summary") {
      await route.fulfill({
        json: {
          ok: true,
          total_pending: question ? 1 : 0,
          pending_questions: question ? 1 : 0,
          pending_builds: 0,
          sessions: question
            ? [
                {
                  session_id: "plan-review",
                  topic: "Plan approval review",
                  pending_count: 1,
                  pending_questions: 1,
                  pending_builds: 0,
                  inbox_pending: true,
                },
              ]
            : [],
        },
      });
      return;
    }
    if (url.pathname === "/api/sessions/plan-review/inbox") {
      await route.fulfill({
        json: {
          pending_count: question ? 1 : 0,
          pending_questions: question ? 1 : 0,
          pending_builds: 0,
          human_inbox: question
            ? [
                {
                  id: "question-1",
                  kind: "question",
                  status: "pending",
                  prompt: "어떤 롤백 전략으로 진행할까요?",
                  body: "비가역 변경 전에 하나의 방향을 선택해야 합니다.",
                  source: "claude",
                  caller_agent: "claude",
                  created_at: "2026-06-21T00:00:00Z",
                  options: [
                    {
                      id: "snapshot",
                      label: "스냅샷 후 진행",
                      description: "실행 전 복구 지점을 남깁니다.",
                      recommended: true,
                    },
                    {
                      id: "staged",
                      label: "단계적 전환",
                      description: "작은 범위부터 순차적으로 적용합니다.",
                      recommended: false,
                    },
                  ],
                },
              ]
            : [],
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
  await expect(page.locator(".plan-approval-strip")).toBeVisible();
}

test("plan review is one decision surface and approval starts dry-run", async ({
  page,
}) => {
  const requests: string[] = [];
  await initializePlanReview(page);
  await mockPlanApprovalApi(page, requests);
  await page.goto("/");
  await openPlanReview(page);

  const review = page.locator(".plan-approval-strip");
  await expect(
    review.getByRole("heading", { name: "승인하고 실행" }),
  ).toBeVisible();
  await expect(review).toContainText("격리된 worktree");
  await expect(review.locator(".btn--primary")).toHaveCount(1);
  await expect(page.locator(".work-decision")).toHaveCount(0);

  const approveAndExecute = review.getByRole("button", {
    name: "승인하고 실행",
  });
  await approveAndExecute.focus();
  await page.keyboard.press("Tab");
  await expect(review.getByRole("button", { name: "수정 요청" })).toBeFocused();

  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(review).toBeVisible();
    if (width <= 900) {
      await expect(page.locator(".workbench-tile")).toBeHidden();
    }
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

test("question surface keeps options, freeform fallback, and submit state together", async ({
  page,
}) => {
  await initializePlanReview(page);
  await mockPlanApprovalApi(page, [], { question: true });
  await page.goto("/");
  await page.getByRole("button", { name: "Plan approval review" }).click();

  const question = page.locator(".human-inbox--composer");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(question).toContainText("질문에 답해주세요");
  await expect(question).toContainText("답변하면 작업이 재개됩니다");
  await page.screenshot({
    path: "/tmp/agent-lab-plan-question-1440.png",
    fullPage: true,
  });
  await expect(question).toContainText("선택지를 고르거나 직접 입력하세요");
  await expect(question.getByRole("button", { name: "제출" })).toBeDisabled();
  const options = question.getByRole("radio");
  await options.nth(0).click();
  await page.keyboard.press("ArrowDown");
  await expect(options.nth(1)).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Home");
  await expect(options.nth(0)).toHaveAttribute("aria-checked", "true");
  await expect(question).not.toContainText("선택지를 고르거나 직접 입력하세요");
  await expect(question.getByRole("button", { name: "제출" })).toBeEnabled();
  await expect(question.locator("textarea")).toHaveAttribute(
    "placeholder",
    "기타 — 직접 입력…",
  );
});

test("BLOCK objection disables approval and shows the reason", async ({
  page,
}) => {
  await initializePlanReview(page);
  await mockPlanApprovalApi(page, [], { blockingObjection: true });
  await page.goto("/");
  await openPlanReview(page);

  const review = page.locator(".plan-approval-strip");
  await expect(review.getByRole("alert")).toContainText(
    "보안 위험을 먼저 해결하세요.",
  );
  await expect(
    review.getByRole("button", { name: "승인하고 실행" }),
  ).toBeDisabled();
  await page.screenshot({
    path: "/tmp/agent-lab-plan-blocked-1280.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 375, height: 900 });
  await expect(review).toBeVisible();
  await expect(page.locator(".workbench-tile")).toBeHidden();
  await page.screenshot({
    path: "/tmp/agent-lab-plan-blocked-375.png",
    fullPage: true,
  });
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

    const review = page.locator(".plan-approval-strip");
    await expect(review.getByRole("button", { name: "승인만" })).toBeVisible();
    await expect(
      review.getByRole("button", { name: "승인하고 실행" }),
    ).toHaveCount(0);
    await expect(review.locator(".btn--primary")).toHaveCount(1);
  });
}

test("dry-run failure preserves the approval decision and explains recovery", async ({
  page,
}) => {
  const requests: string[] = [];
  await initializePlanReview(page);
  await mockPlanApprovalApi(page, requests, { dryRunFailure: true });
  await page.goto("/");
  await openPlanReview(page);

  await page
    .locator(".plan-approval-strip")
    .getByRole("button", { name: "승인하고 실행" })
    .click();

  await expect
    .poll(() => requests)
    .toEqual([
      "POST /api/sessions/plan-review/plan/approve",
      "POST /api/sessions/plan-review/execute/dry-run",
    ]);
  await expect(page.locator(".plan-approval-strip")).toHaveCount(0);
  await expect(
    page.locator(".work-surface--alert .plan-card__error"),
  ).toHaveText("cursor unavailable");
  await expect(page.locator(".work-surface--alert")).toContainText(
    "Plan 승인은 유지되었습니다.",
  );
});
