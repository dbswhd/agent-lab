import { expect, test, type Page } from "playwright/test";

const planMarkdown = `## 목표
Wave B 5번 journey를 검증합니다.

## 지금 실행
1.
   - 무엇을: plan reject, diff approve, Oracle repair, Human resume
   - 어디서: \`e2e/wave-b-journey.spec.ts\`
   - 검증: \`npx playwright test\``;

const recommendedAction = {
  index: 1,
  what: "Wave B 5번 journey를 검증",
  where: "e2e/wave-b-journey.spec.ts",
  verify: "npx playwright test",
  refs: [],
  expected_paths: ["e2e/wave-b-journey.spec.ts"],
  recommended: true,
  kind: "now",
  executable: true,
  isolation: "worktree",
};

const questionItem = {
  id: "question-1",
  kind: "question",
  status: "pending",
  prompt: "실행 중 어떤 범위로 진행할까요?",
  body: "범위를 선택하면 작업이 재개됩니다.",
  source: "claude",
  caller_agent: "claude",
  created_at: "2026-07-15T00:00:00Z",
  decision_version: 7,
  options: [
    {
      id: "safe",
      label: "안전한 범위",
      description: "변경 영향이 적은 범위만 진행합니다.",
      recommended: true,
    },
    {
      id: "full",
      label: "전체 범위",
      description: "모든 변경을 한 번에 적용합니다.",
      recommended: false,
    },
  ],
};

function missionReadModelPayload(input: {
  sessionId: string;
  resolved: boolean;
  rejected: boolean;
  journey: Journey;
}): Record<string, unknown> {
  const isHumanResume = input.sessionId === "wave-b-human-resume";
  const isPlanReject = input.sessionId === "wave-b-plan-reject";
  const inbox = isHumanResume && !input.resolved ? [questionItem] : [];
  const awaitingPlan =
    isPlanReject && !input.rejected && input.journey === "plan-reject";
  return {
    session_id: input.sessionId,
    migrated: true,
    source: "mission_journal",
    mission_id: "mission-wave-b",
    goal: "Wave B journey",
    state: isHumanResume
      ? "AWAITING_HUMAN"
      : awaitingPlan
        ? "AWAITING_PLAN_DECISION"
        : "EXECUTING",
    version: 7,
    plan_revision: 2,
    plan_hash: "plan-hash",
    approved_plan_hash: awaitingPlan ? null : "plan-hash",
    repair_attempt: 0,
    max_repair_attempts: 2,
    oracle_verdict: null,
    next_action: isHumanResume ? "answer_inbox" : "continue",
    event_cursor: 7,
    operational_status: isHumanResume ? "awaiting_human" : "executing",
    open_execution_gates: inbox.map((item) => ({
      gate_id: item.id,
      kind: item.kind,
    })),
    legacy_phase: isHumanResume ? "WAITING_FOR_HUMAN" : "EXECUTE",
    plan: {
      phase: awaitingPlan ? "HUMAN_PENDING" : "APPROVED",
      hash: "plan-hash",
      approved_hash: awaitingPlan ? null : "plan-hash",
      pending_approval: awaitingPlan,
    },
    work_phase: awaitingPlan ? "review_needed" : "execute_pending",
    mission_overview: {
      phase_label: isHumanResume ? "WAITING_FOR_HUMAN" : "EXECUTE",
      paused: isHumanResume,
      circuit_breaker: false,
      pending_inbox_count: inbox.length,
    },
    inbox_summary: {
      pending_count: inbox.length,
      pending_questions: inbox.length,
      pending_builds: 0,
    },
    inbox_items: inbox,
  };
}

type Journey =
  | "plan-reject"
  | "diff-approve"
  | "oracle-repair"
  | "human-resume";

async function mockWaveBJourneyApi(
  page: Page,
  requests: string[],
  journey: Journey,
  postBodies: Record<string, unknown>[] = [],
) {
  let rejected = false;
  let resolved = false;
  let reverifyCalled = false;
  const executionId = "execution-1";

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
              ready: true,
              configured: true,
              bridge: "ok",
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

    if (url.pathname === "/api/health/flags") {
      await route.fulfill({
        json: {
          ok: true,
          count: 1,
          flags: [
            { name: "AGENT_LAB_MISSION_UI_READ_MODEL", value: "1" },
          ],
        },
      });
      return;
    }

    const readModelMatch = url.pathname.match(
      /^\/api\/sessions\/(wave-b-[^/]+)\/mission\/read-model$/,
    );
    if (readModelMatch) {
      requests.push(key);
      await route.fulfill({
        json: missionReadModelPayload({
          sessionId: readModelMatch[1],
          resolved,
          rejected,
          journey,
        }),
      });
      return;
    }

    const missionEventsMatch = url.pathname.match(
      /^\/api\/sessions\/(wave-b-[^/]+)\/mission\/events$/,
    );
    if (missionEventsMatch) {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: "event: ping\ndata: {}\n\n",
      });
      return;
    }

    if (url.pathname === "/api/sessions") {
      const sessions = [
        {
          id: "wave-b-plan-reject",
          topic: "Wave B plan reject",
          updated_at: "2026-07-15T00:00:00Z",
          workflow: "room.parallel",
        },
        {
          id: "wave-b-diff-approve",
          topic: "Wave B diff approve",
          updated_at: "2026-07-15T00:00:00Z",
          workflow: "room.parallel",
        },
        {
          id: "wave-b-oracle-repair",
          topic: "Wave B Oracle repair",
          updated_at: "2026-07-15T00:00:00Z",
          workflow: "room.parallel",
        },
        {
          id: "wave-b-human-resume",
          topic: "Wave B human resume",
          updated_at: "2026-07-15T00:00:00Z",
          workflow: "room.parallel",
        },
      ];
      await route.fulfill({
        json: { ok: true, sessions, total: sessions.length },
      });
      return;
    }

    const sessionMatch = url.pathname.match(
      /^\/api\/sessions\/(wave-b-[^/]+)$/,
    );
    if (sessionMatch) {
      const sessionId = sessionMatch[1];
      const isHumanResume =
        sessionId === "wave-b-human-resume" && !resolved;
      const isPlanReject = sessionId === "wave-b-plan-reject";
      const isDiffApprove = sessionId === "wave-b-diff-approve";
      const isOracleRepair = sessionId === "wave-b-oracle-repair";

      const executions: Record<string, unknown>[] = [];
      if (isDiffApprove || isOracleRepair) {
        executions.push({
          id: executionId,
          action_index: 1,
          action_kind: "now",
          status: "pending_approval",
          diff: "diff --git a/file.txt b/file.txt\n+change",
          diff_stat: "1 file changed, 1 insertion(+)",
          touched_paths: ["file.txt"],
          executor_label: "Cursor",
          oracle:
            isOracleRepair && !reverifyCalled
              ? { verdict: "fail", detail: "test failed" }
              : { verdict: "pass" },
          oracle_verdict:
            isOracleRepair && !reverifyCalled ? "fail" : "pass",
          is_worktree_execution: true,
          workspace: "/tmp/wave-b-worktree",
        });
      }

      await route.fulfill({
        json: {
          id: sessionId,
          topic: `Wave B ${sessionId.replace("wave-b-", "")}`,
          plan_md: planMarkdown,
          transcript_md: "",
          meta: {},
          chat: [],
          run: {
            status: "idle",
            actions: [recommendedAction],
            executions,
            plan_workflow: {
              enabled: true,
              // Only the plan-reject journey needs the plan-approval strip
              // (composer stack's highest-priority lane) visible — every
              // other journey must already be past plan approval so its own
              // lane (execute_queue / inbox) can become active instead.
              phase: isPlanReject
                ? rejected
                  ? "REFINE"
                  : "HUMAN_PENDING"
                : "APPROVED",
              notice: isPlanReject
                ? rejected
                  ? "plan_rejected_refine"
                  : "plan_pending_approval"
                : "plan_approved",
            },
            mission_loop: {
              enabled: true,
              phase:
                isHumanResume ? "WAITING_FOR_HUMAN" : "EXECUTE",
              paused: isHumanResume,
            },
            human_inbox: isHumanResume ? [questionItem] : [],
          },
        },
      });
      return;
    }

    const planActionsMatch = url.pathname.match(
      /^\/api\/sessions\/(wave-b-[^/]+)\/plan-actions$/,
    );
    if (planActionsMatch) {
      const isPlanReject = planActionsMatch[1] === "wave-b-plan-reject";
      const hidden = isPlanReject && rejected;
      await route.fulfill({
        json: {
          recommended: hidden ? null : recommendedAction,
          now: hidden ? [] : [recommendedAction],
          roadmap: [],
          actions: hidden ? [] : [recommendedAction],
        },
      });
      return;
    }

    const tasksMatch = url.pathname.match(
      /^\/api\/sessions\/(wave-b-[^/]+)\/tasks$/,
    );
    if (tasksMatch) {
      await route.fulfill({
        json: {
          team_lead: "codex",
          agents: ["cursor", "codex", "claude"],
          tasks: [],
          claimable: [],
          counts: { pending: 0, in_progress: 0, completed: 0 },
          objections: [],
          open_objections: [],
          open_objection_count: 0,
        },
      });
      return;
    }

    const runtimeMatch = url.pathname.match(
      /^\/api\/sessions\/(wave-b-[^/]+)\/runtime$/,
    );
    if (runtimeMatch) {
      const runtimeSessionId = runtimeMatch[1];
      const hasPendingExecution =
        runtimeSessionId === "wave-b-diff-approve" ||
        runtimeSessionId === "wave-b-oracle-repair";
      await route.fulfill({
        json: {
          ok: true,
          session_id: runtimeSessionId,
          mode: "standalone",
          has_plan: true,
          work_phase: "review_needed",
          mission: { enabled: true, phase: "idle", paused: false },
          execute: {
            has_pending: hasPendingExecution,
            has_dry_run_diff: hasPendingExecution,
          },
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

    const filesRootsMatch = url.pathname.match(
      /^\/api\/sessions\/(wave-b-[^/]+)\/files\/roots$/,
    );
    if (filesRootsMatch) {
      await route.fulfill({ json: { roots: [] } });
      return;
    }

    if (url.pathname === "/api/sessions/wave-b-human-resume/inbox") {
      await route.fulfill({
        json: {
          pending_count: resolved ? 0 : 1,
          pending_questions: resolved ? 0 : 1,
          pending_builds: 0,
          human_inbox: resolved ? [] : [questionItem],
        },
      });
      return;
    }

    if (url.pathname === "/api/inbox/summary") {
      await route.fulfill({
        json: {
          ok: true,
          total_pending: 0,
          pending_questions: 0,
          pending_builds: 0,
          sessions: [],
        },
      });
      return;
    }

    if (
      url.pathname === "/api/sessions/wave-b-plan-reject/plan/reject" &&
      request.method() === "POST"
    ) {
      requests.push(key);
      rejected = true;
      await route.fulfill({
        json: {
          ok: true,
          plan_workflow: {
            enabled: true,
            phase: "REFINE",
            notice: "plan_rejected_refine",
          },
        },
      });
      return;
    }

    if (
      url.pathname === "/api/sessions/wave-b-diff-approve/execute/resolve" &&
      request.method() === "POST"
    ) {
      requests.push(key);
      await route.fulfill({
        json: {
          ok: true,
          execution: { id: executionId, status: "merged" },
        },
      });
      return;
    }

    if (
      url.pathname === "/api/sessions/wave-b-oracle-repair/execute/reverify" &&
      request.method() === "POST"
    ) {
      requests.push(key);
      reverifyCalled = true;
      await route.fulfill({
        json: { ok: true, execution: { id: executionId, status: "running" } },
      });
      return;
    }

    if (
      url.pathname ===
        "/api/sessions/wave-b-human-resume/inbox/question-1/resolve" &&
      request.method() === "POST"
    ) {
      requests.push(key);
      try {
        postBodies.push(request.postDataJSON() as Record<string, unknown>);
      } catch {
        postBodies.push({});
      }
      resolved = true;
      await route.fulfill({
        json: {
          ok: true,
          pending_count: 0,
          pending_questions: 0,
          pending_builds: 0,
          human_inbox: [],
        },
      });
      return;
    }

    if (url.pathname === "/api/commands") {
      await route.fulfill({ json: { ok: true, commands: [] } });
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

async function initialize(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("agent-lab-first-run-onboarding-version", "p1f");
    localStorage.setItem("agent-lab-inspector-open", "1");
    localStorage.setItem("agent-lab-locale", "ko");
  });
}

async function openSession(page: Page, name: string) {
  // English-only fixture topics classify as Dogfood (no Hangul heuristic).
  await page.getByRole("tab", { name: "Dogfood" }).click();
  await page.getByRole("button", { name }).click();
}

test("plan reject journey sends reject request and enters refine phase", async ({
  page,
}) => {
  const requests: string[] = [];
  await initialize(page);
  await mockWaveBJourneyApi(page, requests, "plan-reject");
  await page.goto("/");
  await openSession(page, "Wave B plan reject");

  const review = page.locator(".plan-approval-strip");
  await expect(review).toBeVisible();
  await review.getByRole("button", { name: "수정 요청" }).click();

  const textarea = review.locator("textarea#plan-revision-note-strip");
  await expect(textarea).toBeFocused();
  await textarea.fill("계획 범위를 축소해서 다시 작성해 주세요.");

  // Same "수정 요청" button toggles the revision form open and, once it has
  // a note, submits it — PlanApprovalStrip has no separate "제출" button.
  const submit = review.getByRole("button", { name: "수정 요청" });
  await expect(submit).toBeEnabled();
  await submit.click();

  await expect.poll(() => requests).toContain(
    "POST /api/sessions/wave-b-plan-reject/plan/reject",
  );
});

test("diff approve journey resolves pending execution", async ({ page }) => {
  const requests: string[] = [];
  await initialize(page);
  await mockWaveBJourneyApi(page, requests, "diff-approve");
  await page.goto("/");
  await openSession(page, "Wave B diff approve");

  // A pending execution activates the composer stack's "execute_queue" lane
  // (highest priority after plan_approval, per composerStackLane.ts) — that
  // renders the compact ExecuteQueueBar, not the full PlanExecutePendingCard
  // (#work-execute-queue), which only appears in the lower-priority "work"
  // lane and is unreachable while an execution is pending.
  const card = page.getByRole("region", { name: "실행 승인 대기" });
  await expect(card).toBeVisible();

  const approve = card.getByRole("button", { name: "승인" });
  await expect(approve).toBeEnabled();
  await approve.click();

  await expect.poll(() => requests).toContain(
    "POST /api/sessions/wave-b-diff-approve/execute/resolve",
  );
});

test("Oracle repair journey re-verifies failed execution", async ({
  page,
}) => {
  const requests: string[] = [];
  await initialize(page);
  await mockWaveBJourneyApi(page, requests, "oracle-repair");
  await page.goto("/");
  await openSession(page, "Wave B Oracle repair");

  // Same execute_queue lane as the diff-approve journey — the compact
  // ExecuteQueueBar, not #work-execute-queue (see the diff-approve journey
  // above). It grows an "Oracle 재검증" button when the verdict failed,
  // since #work-execute-queue's card is unreachable while an execution is
  // pending.
  const card = page.getByRole("region", { name: "실행 승인 대기" });
  await expect(card).toBeVisible();

  await card.getByRole("button", { name: "Oracle 재검증" }).click();

  await expect.poll(() => requests).toContain(
    "POST /api/sessions/wave-b-oracle-repair/execute/reverify",
  );
});

test("human resume journey answers inbox question", async ({ page }) => {
  const requests: string[] = [];
  const postBodies: Record<string, unknown>[] = [];
  await initialize(page);
  await mockWaveBJourneyApi(page, requests, "human-resume", postBodies);
  await page.goto("/");
  await openSession(page, "Wave B human resume");

  await expect.poll(() =>
    requests.some((row) => row.includes("/mission/read-model")),
  ).toBe(true);

  const inbox = page.locator(".human-inbox--composer");
  await expect(inbox).toBeVisible();
  await expect(inbox).toContainText("실행 중 어떤 범위로 진행할까요?");

  await inbox
    .getByRole("radio", { name: "안전한 범위" })
    .click();

  await inbox.getByRole("button", { name: "제출" }).click();

  await expect.poll(() => requests).toContain(
    "POST /api/sessions/wave-b-human-resume/inbox/question-1/resolve",
  );
  await expect.poll(() => postBodies.length).toBeGreaterThan(0);
  expect(postBodies[0]).toMatchObject({
    decision_id: "question-1",
    mission_id: "mission-wave-b",
    expected_version: 7,
  });
});
