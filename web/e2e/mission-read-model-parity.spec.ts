import { expect, test, type Page, type Route } from "playwright/test";
import { resolve } from "node:path";

type ReadModelMode = "migrated" | "legacy" | "error" | "disconnect" | "stale";

type ReadModelFixture = {
  readonly state: string;
  readonly operational_status: string;
  readonly next_action: string;
  readonly work_phase: string;
  readonly phase_label: string;
  readonly paused: boolean;
  readonly circuit_breaker: boolean;
  readonly oracle_verdict: string | null;
  readonly repair_attempt: number;
  readonly inbox_items: readonly Record<string, unknown>[];
};

const question = {
  id: "question-1",
  kind: "question",
  status: "pending",
  prompt: "실행 중 어떤 범위로 진행할까요?",
  options: [
    { id: "safe", label: "안전한 범위" },
    { id: "full", label: "전체 범위" },
  ],
};

const terminalQuestion = {
  ...question,
  actionable: false,
  mission_gate_status: "terminal_orphan",
};

const fixtures: Record<string, ReadModelFixture> = {
  approval: {
    state: "AWAITING_PLAN_DECISION",
    operational_status: "WAITING_FOR_HUMAN",
    next_action: "decide_plan",
    work_phase: "plan_draft",
    phase_label: "WAITING_FOR_HUMAN",
    paused: false,
    circuit_breaker: false,
    oracle_verdict: null,
    repair_attempt: 0,
    inbox_items: [],
  },
  question: {
    state: "EXECUTING",
    operational_status: "WAITING_FOR_HUMAN",
    next_action: "answer_human",
    work_phase: "review_needed",
    phase_label: "WAITING_FOR_HUMAN",
    paused: false,
    circuit_breaker: false,
    oracle_verdict: null,
    repair_attempt: 0,
    inbox_items: [question],
  },
  paused: {
    state: "EXECUTING",
    operational_status: "RUNNING",
    next_action: "observe_execution",
    work_phase: "execute_pending",
    phase_label: "MISSION_PAUSED",
    paused: true,
    circuit_breaker: true,
    oracle_verdict: null,
    repair_attempt: 0,
    inbox_items: [],
  },
  repair: {
    state: "REPAIRING",
    operational_status: "RUNNING",
    next_action: "observe_repair",
    work_phase: "merge_verify",
    phase_label: "REPAIR",
    paused: false,
    circuit_breaker: false,
    oracle_verdict: "fail",
    repair_attempt: 1,
    inbox_items: [],
  },
  oracle: {
    state: "SUCCEEDED",
    operational_status: "COMPLETED",
    next_action: "view_result",
    work_phase: "done",
    phase_label: "MISSION_DONE",
    paused: false,
    circuit_breaker: false,
    oracle_verdict: "pass",
    repair_attempt: 1,
    inbox_items: [],
  },
  stale: {
    state: "EXECUTING",
    operational_status: "WAITING_FOR_HUMAN",
    next_action: "answer_human",
    work_phase: "review_needed",
    phase_label: "WAITING_FOR_HUMAN",
    paused: false,
    circuit_breaker: false,
    oracle_verdict: null,
    repair_attempt: 0,
    inbox_items: [],
  },
  terminal: {
    state: "SUCCEEDED",
    operational_status: "COMPLETED",
    next_action: "view_result",
    work_phase: "done",
    phase_label: "COMPLETED",
    paused: false,
    circuit_breaker: false,
    oracle_verdict: "pass",
    repair_attempt: 1,
    inbox_items: [terminalQuestion],
  },
  missing: {
    state: "EXECUTING",
    operational_status: "WAITING_FOR_HUMAN",
    next_action: "answer_human",
    work_phase: "review_needed",
    phase_label: "WAITING_FOR_HUMAN",
    paused: false,
    circuit_breaker: false,
    oracle_verdict: null,
    repair_attempt: 0,
    inbox_items: [],
  },
};

function payloadFor(
  fixture: ReadModelFixture,
  migrated: boolean,
): Record<string, unknown> {
  const actionableItems = fixture.inbox_items.filter(
    (item) => item.actionable !== false,
  );
  return {
    session_id: "read-model-session",
    migrated,
    source: migrated ? "mission_journal" : "legacy",
    mission_id: migrated ? "mission-read-model" : null,
    goal: "read-model parity",
    state: migrated ? fixture.state : null,
    version: migrated ? 7 : null,
    plan_revision: migrated ? 2 : null,
    plan_hash: migrated ? "plan-hash" : null,
    approved_plan_hash: migrated ? "plan-hash" : null,
    repair_attempt: migrated ? fixture.repair_attempt : null,
    max_repair_attempts: migrated ? 2 : null,
    oracle_verdict: migrated ? fixture.oracle_verdict : null,
    next_action: migrated ? fixture.next_action : "legacy_route",
    event_cursor: migrated ? 7 : 0,
    operational_status: migrated ? fixture.operational_status : null,
    open_execution_gates: migrated
      ? fixture.inbox_items.map((item) => ({
          gate_id: item.id,
          kind: item.kind,
        }))
      : [],
    legacy_phase: fixture.phase_label,
    plan: {
      phase: migrated ? "APPROVED" : "HUMAN_PENDING",
      hash: migrated ? "plan-hash" : null,
      approved_hash: migrated ? "plan-hash" : null,
      pending_approval: !migrated && fixture.state === "AWAITING_PLAN_DECISION",
    },
    work_phase: migrated ? fixture.work_phase : "plan_draft",
    mission_overview: {
      phase_label: migrated ? fixture.phase_label : "LEGACY",
      paused: migrated ? fixture.paused : false,
      circuit_breaker: migrated ? fixture.circuit_breaker : false,
      pending_inbox_count: actionableItems.length,
    },
    inbox_summary: {
      pending_count: actionableItems.length,
      pending_questions: actionableItems.length,
      pending_builds: 0,
    },
    inbox_items: fixture.inbox_items,
  };
}

async function fulfillJson(
  route: Route,
  body: unknown,
  status = 200,
): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installFixture(
  page: Page,
  mode: ReadModelMode,
  fixtureName = "question",
  requests: string[] = [],
): Promise<void> {
  const selectedFixture = fixtureName;
  let answered = false;
  let disconnectPending = mode === "disconnect";
  await page.route(/^http:\/\/127\.0\.0\.1:4173\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const key = `${request.method()} ${url.pathname}`;
    requests.push(key);

    if (url.pathname === "/api/health") {
      await fulfillJson(route, {
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
      });
      return;
    }
    if (url.pathname === "/api/health/flags") {
      await fulfillJson(route, {
        ok: true,
        flags: [{ name: "AGENT_LAB_MISSION_UI_READ_MODEL", value: "1" }],
      });
      return;
    }
    if (url.pathname === "/api/room/modes") {
      await fulfillJson(route, { modes: [], legacy_migration: {} });
      return;
    }
    if (url.pathname === "/api/room/presets") {
      await fulfillJson(route, { presets: [], default: null });
      return;
    }
    if (url.pathname === "/api/session-setup/options") {
      await fulfillJson(route, { workspaces: [], defaults: {} });
      return;
    }
    if (url.pathname === "/api/sessions") {
      await fulfillJson(route, {
        sessions: [
          {
            id: "read-model-session",
            topic: "Read model parity",
            updated_at: "2026-07-14T00:00:00Z",
            workflow: "room.parallel",
          },
        ],
      });
      return;
    }
    if (url.pathname === "/api/sessions/read-model-session") {
      const fixture = fixtures[selectedFixture] ?? fixtures.question;
      const items = answered ? [] : fixture.inbox_items;
      await fulfillJson(route, {
        id: "read-model-session",
        topic: "Read model parity",
        plan_md: "## Plan\n\n1. Execute safely",
        transcript_md: "",
        meta: {},
        chat: [],
        run: {
          status: "idle",
          actions: [],
          executions: [
            {
              id: "execution-1",
              status: fixtureName === "oracle" ? "completed" : "running",
              oracle: fixture.oracle_verdict
                ? { verdict: fixture.oracle_verdict }
                : undefined,
            },
          ],
          plan_workflow: {
            enabled: true,
            phase: fixtureName === "approval" ? "HUMAN_PENDING" : "APPROVED",
          },
          mission_loop: {
            enabled: true,
            phase: fixtureName === "paused" ? "EXECUTE" : fixture.phase_label,
            paused: fixture.paused,
            circuit_breaker: fixture.circuit_breaker,
          },
          human_inbox: items,
        },
      });
      return;
    }
    if (url.pathname.endsWith("/mission/read-model")) {
      const queryFixture = url.searchParams.get("fixture") ?? selectedFixture;
      const fixture = fixtures[queryFixture] ?? fixtures.question;
      if (mode === "disconnect" && disconnectPending) {
        disconnectPending = false;
        await route.abort("connectionfailed");
        return;
      }
      if (mode === "error") {
        await fulfillJson(
          route,
          { ok: false, error: "read_model_unavailable" },
          503,
        );
        return;
      }
      const migrated = mode === "migrated";
      const stalePayload =
        mode === "stale"
          ? {
              ...payloadFor({ ...fixture, inbox_items: [] }, true),
              open_execution_gates: [
                { gate_id: question.id, kind: "question" },
              ],
              inbox_summary: {
                pending_count: 0,
                pending_questions: 0,
                pending_builds: 0,
              },
            }
          : null;
      await fulfillJson(
        route,
        stalePayload ??
          payloadFor(
            { ...fixture, inbox_items: answered ? [] : fixture.inbox_items },
            migrated,
          ),
      );
      return;
    }
    if (url.pathname.endsWith("/inbox")) {
      const fixture = fixtures[selectedFixture] ?? fixtures.question;
      const legacyItems =
        selectedFixture === "stale" ? [question] : fixture.inbox_items;
      await fulfillJson(route, {
        pending_count: answered ? 0 : legacyItems.length,
        pending_questions: answered ? 0 : legacyItems.length,
        pending_builds: 0,
        human_inbox: answered ? [] : legacyItems,
      });
      return;
    }
    if (
      url.pathname.endsWith("/inbox/question-1/resolve") &&
      request.method() === "POST"
    ) {
      answered = true;
      await fulfillJson(route, {
        ok: true,
        pending_count: 0,
        pending_questions: 0,
        pending_builds: 0,
        human_inbox: [],
      });
      return;
    }
    if (url.pathname === "/api/inbox/summary") {
      await fulfillJson(route, {
        ok: true,
        total_pending: answered ? 0 : 1,
        pending_questions: answered ? 0 : 1,
        pending_builds: 0,
        sessions: [],
      });
      return;
    }
    if (url.pathname === "/api/room/modes") {
      await fulfillJson(route, { modes: [], legacy_migration: {} });
      return;
    }
    if (url.pathname === "/api/room/presets") {
      await fulfillJson(route, { presets: [], default: null });
      return;
    }
    if (url.pathname === "/api/session-setup/options") {
      await fulfillJson(route, {
        workspaces: [],
        defaults: { workspace_id: "agent-lab", session_template: "general" },
      });
      return;
    }
    if (
      url.pathname === "/api/commands" ||
      url.pathname === "/api/auth/providers"
    ) {
      await fulfillJson(route, { ok: true, commands: [], providers: [] });
      return;
    }
    if (url.pathname.endsWith("/runtime")) {
      await fulfillJson(route, {
        ok: true,
        session_id: "read-model-session",
        mode: "standalone",
        has_plan: true,
        work_phase: "review_needed",
        mission: { enabled: true, phase: "EXECUTE", paused: false },
        execute: { has_pending: false, has_dry_run_diff: false },
        gates: { execute_blocked: false, pending_agreement: false },
        inbox: {
          pending: answered ? false : true,
          pending_count: answered ? 0 : 1,
          pending_questions: answered ? 0 : 1,
          pending_builds: 0,
        },
        next_action: "answer_human",
      });
      return;
    }
    if (url.pathname.endsWith("/tasks")) {
      await fulfillJson(route, {
        team_lead: "codex",
        agents: ["cursor", "codex", "claude"],
        tasks: [],
        claimable: [],
        counts: { pending: 0, in_progress: 0, completed: 0 },
        objections: [],
        open_objections: [],
        open_objection_count: 0,
      });
      return;
    }
    if (url.pathname.endsWith("/agent-capabilities")) {
      await fulfillJson(route, { ok: true, agent_capabilities: {} });
      return;
    }
    if (url.pathname === "/api/health/readiness") {
      await fulfillJson(route, {
        verdict: "ready",
        checks: [],
        next_actions: [],
        agents: [],
      });
      return;
    }
    if (url.pathname.endsWith("/plan-actions")) {
      await fulfillJson(route, {
        recommended: null,
        now: [],
        roadmap: [],
        actions: [],
      });
      return;
    }
    if (url.pathname.includes("/context/layers")) {
      await fulfillJson(route, {
        ok: true,
        context_layers: { mission_wisdom: true, repo_tree: true },
      });
      return;
    }
    await fulfillJson(route, { ok: true });
  });
}

async function openSession(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("agent-lab-first-run-onboarding-version", "p1f");
    localStorage.setItem("agent-lab-locale", "ko");
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Read model parity" }).click();
}

test("browser API contract covers approval, question, pause, repair, reconnect, and merge/oracle states", async ({
  page,
}) => {
  const requests: string[] = [];
  await installFixture(page, "migrated", "question", requests);
  await page.goto("/");

  const observed = await page.evaluate(async () => {
    await fetch("/api/health/flags?category=feature");
    const names = ["approval", "question", "paused", "repair", "oracle"];
    const result: Record<string, Record<string, unknown>> = {};
    for (const name of names) {
      const response = await fetch(
        `/api/sessions/read-model-session/mission/read-model?fixture=${name}`,
      );
      result[name] = (await response.json()) as Record<string, unknown>;
    }
    return result;
  });

  expect(observed.approval?.operational_status).toBe("WAITING_FOR_HUMAN");
  expect(observed.question?.inbox_items).toHaveLength(1);
  expect(observed.question?.open_execution_gates).toEqual([
    { gate_id: "question-1", kind: "question" },
  ]);
  expect(observed.paused?.mission_overview).toMatchObject({
    paused: true,
    circuit_breaker: true,
  });
  expect(observed.repair).toMatchObject({
    state: "REPAIRING",
    repair_attempt: 1,
    oracle_verdict: "fail",
  });
  expect(observed.oracle).toMatchObject({
    state: "SUCCEEDED",
    operational_status: "COMPLETED",
    oracle_verdict: "pass",
  });
  expect(requests).toContain("GET /api/health/flags");
});

test("migrated question preserves options and answer resumes the workflow", async ({
  page,
}) => {
  const requests: string[] = [];
  await installFixture(page, "migrated", "question", requests);
  await openSession(page);

  const inbox = page.locator(".human-inbox--composer");
  await expect(inbox).toBeVisible();
  await expect(inbox).toContainText("실행 중 어떤 범위로 진행할까요?");
  await expect(inbox.getByRole("radio")).toHaveCount(2);
  await page.screenshot({
    path: resolve(process.cwd(), "test-results/read-model-question.png"),
  });
  await inbox.getByRole("radio", { name: "안전한 범위" }).click();
  await expect(
    inbox.getByRole("radio", { name: "안전한 범위" }),
  ).toHaveAttribute("aria-checked", "true");
  await inbox.getByRole("button", { name: "제출" }).click();
  await expect
    .poll(() => requests.filter((entry) => entry.includes("/resolve")))
    .toHaveLength(1);
  await page.reload();
  await expect(inbox).toHaveCount(0);
});

for (const mode of ["legacy", "error", "disconnect"] as const) {
  test(`${mode} read-model path falls back without losing question options`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await installFixture(page, mode, "question");
    await openSession(page);

    const inbox = page.locator(".human-inbox--composer");
    await expect(inbox).toBeVisible();
    await expect(inbox).toContainText("실행 중 어떤 범위로 진행할까요?");
    await expect(inbox.getByRole("radio")).toHaveCount(2);
    expect(errors).toEqual([]);
  });
}

test("stale migrated join does not expose a legacy resolve row", async ({
  page,
}) => {
  await installFixture(page, "stale", "stale");
  await openSession(page);

  await expect(page.locator(".human-inbox--composer")).toHaveCount(0);
});

for (const fixtureName of ["terminal", "missing"] as const) {
  test(`${fixtureName} inbox rows do not expose resolve controls or counts`, async ({
    page,
  }) => {
    await installFixture(page, "migrated", fixtureName);
    await openSession(page);

    await expect(page.locator(".human-inbox--composer")).toHaveCount(0);
    await expect(page.locator(".human-inbox")).toHaveCount(0);
  });
}

test("pause and circuit state uses the canonical read-model label", async ({
  page,
}) => {
  await installFixture(page, "migrated", "paused");
  await openSession(page);

  await expect(page.locator(".ctx-mission")).toContainText("일시정지");
});
