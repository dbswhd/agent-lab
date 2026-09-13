import { expect, test, type Page } from "playwright/test";

/**
 * RI-13 — idea-lane journey against a stateful /api mock.
 *
 * Mock-routed like the rest of the CI e2e suite (see `wave-b-journey.spec.ts`);
 * the real-API variant is opt-in and lives outside CI, as does anything that
 * calls a live model. What this pins is the browser-side contract:
 *
 *   concept → candidates → select → refresh restores → stale select is refused
 *   → changing the concept marks the plan stale → export carries the warnings
 *
 * plus: an existing session shows none of this and keeps its execute surfaces.
 */

const IDEA_SESSION = "ideation-journey";
const LEGACY_SESSION = "legacy-execute";

const OPTIONS = [
  {
    id: "opt-0-cursor",
    agent: "cursor",
    title: "하루 한 줄 회고",
    principle: "매일 밤 알림 하나, 한 줄만 받는다",
    usage: "자기 전 알림 → 한 줄 입력",
    difference: "일기 앱과 달리 길게 쓸 수 없다",
    tradeoff: "깊은 기록은 못 남긴다",
    first_experiment: "종이와 알람으로 2주",
  },
  {
    id: "opt-0-codex",
    agent: "codex",
    title: "자동 수집 타임라인",
    principle: "캘린더·커밋을 모아 하루를 자동 재구성",
    usage: "밤에 열면 이미 정리돼 있다",
    difference: "사용자가 아무것도 쓰지 않는다",
    tradeoff: "연동 없이는 동작하지 않는다",
    first_experiment: "커밋 로그만으로 요약해 본다",
  },
  {
    id: "opt-0-claude",
    agent: "claude",
    raw: "형식을 지키지 않은 자유 응답",
    parse_error: "no_recognized_sections",
  },
];

type IdeationState = {
  schema_version: number;
  revision: number;
  stage: "explore" | "shape" | "plan";
  brief: Record<string, unknown>;
  options: Record<string, unknown>[];
  selection: Record<string, unknown> | null;
  decisions: Record<string, unknown>[];
  plan_source_revision: number | null;
};

function freshState(): IdeationState {
  return {
    schema_version: 1,
    revision: 1,
    stage: "explore",
    brief: {
      original_concept: "하루를 정리하는 뭔가",
      constraints: ["웹에서 쓴다"],
    },
    options: OPTIONS,
    selection: null,
    decisions: [],
    plan_source_revision: null,
  };
}

/** Mirrors the server's command rules closely enough to exercise the UI. */
function applyCommand(
  state: IdeationState,
  body: Record<string, unknown>,
): { status: number; json: Record<string, unknown> } {
  const command = String(body.command ?? "");
  const optionId = String(body.option_id ?? "");
  const expected = body.expected_revision;

  const alreadySelected =
    command === "select" && state.selection?.option_id === optionId;
  const rejectedIds = state.decisions
    .filter((d) => d.kind === "reject")
    .map((d) => String(d.option_id));
  const alreadyRejected =
    command === "reject" && rejectedIds.includes(optionId);

  if (alreadySelected || alreadyRejected) {
    return {
      status: 200,
      json: payload(state, { applied: false, idempotent: true }),
    };
  }
  if (typeof expected === "number" && expected !== state.revision) {
    return {
      status: 409,
      json: {
        detail: {
          code: "stale_revision",
          message: `stale ideation revision: expected ${expected}, current ${state.revision}`,
          expected_revision: expected,
          current_revision: state.revision,
        },
      },
    };
  }

  if (command === "select") {
    state.selection = {
      option_id: optionId,
      parent_ids: [],
      reason: String(body.reason ?? ""),
    };
    state.stage = "shape";
    state.decisions.push({ kind: "select", option_id: optionId });
  } else if (command === "reject") {
    state.decisions.push({
      kind: "reject",
      option_id: optionId,
      reason: String(body.reason ?? ""),
    });
  } else if (command === "reset") {
    state.selection = null;
    state.stage = "explore";
    state.decisions.push({ kind: "reopen" });
  }
  state.revision += 1;
  return {
    status: 200,
    json: payload(state, { applied: true, idempotent: false }),
  };
}

function planStale(state: IdeationState): boolean {
  return (
    typeof state.plan_source_revision === "number" &&
    state.revision > state.plan_source_revision
  );
}

function payload(state: IdeationState, extra: Record<string, unknown> = {}) {
  return {
    ok: true,
    ideation: state,
    revision: state.revision,
    stage: state.stage,
    plan_stale: planStale(state),
    ...extra,
  };
}

async function mockIdeationApi(
  page: Page,
  state: IdeationState,
  requests: string[],
) {
  await page.route(/^http:\/\/127\.0\.0\.1:4173\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    requests.push(`${request.method()} ${path}`);

    if (path === "/api/health") {
      await route.fulfill({
        json: {
          ok: true,
          api: { ok: true },
          agents: ["cursor", "codex", "claude"].map((id) => ({
            id,
            label: id,
            ready: true,
            configured: true,
            bridge: "ok",
          })),
        },
      });
      return;
    }
    // Shapes the app reads arrays out of — a bare {ok:true} here crashes the
    // shell before it ever opens a session.
    if (path === "/api/commands") {
      await route.fulfill({ json: { ok: true, commands: [] } });
      return;
    }
    if (path === "/api/health/readiness") {
      await route.fulfill({
        json: { verdict: "ready", checks: [], next_actions: [] },
      });
      return;
    }
    if (path === "/api/auth/providers") {
      await route.fulfill({ json: { ok: true, providers: [] } });
      return;
    }
    if (path === "/api/inbox/summary") {
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
    if (path === "/api/session-setup/options") {
      await route.fulfill({
        json: { ok: true, workspaces: [], templates: [], agents: [] },
      });
      return;
    }

    if (path === "/api/sessions") {
      await route.fulfill({
        json: {
          ok: true,
          total: 2,
          sessions: [
            {
              id: IDEA_SESSION,
              topic: "Ideation journey",
              updated_at: "2026-09-13T00:00:00Z",
              workflow: "room.parallel",
            },
            {
              id: LEGACY_SESSION,
              topic: "Legacy execute",
              updated_at: "2026-09-13T00:00:00Z",
              workflow: "room.parallel",
            },
          ],
        },
      });
      return;
    }

    const ideation = path.match(/^\/api\/sessions\/([^/]+)\/ideation$/);
    if (ideation) {
      if (ideation[1] !== IDEA_SESSION) {
        await route.fulfill({
          status: 404,
          json: { detail: "session has no ideation state" },
        });
        return;
      }
      if (request.method() === "PATCH") {
        const result = applyCommand(state, request.postDataJSON());
        await route.fulfill({ status: result.status, json: result.json });
        return;
      }
      await route.fulfill({ json: payload(state) });
      return;
    }

    if (path === `/api/sessions/${IDEA_SESSION}/ideation/export`) {
      await route.fulfill({
        json: {
          ok: true,
          schema: "ideation-export.v1",
          revision: state.revision,
          stage: state.stage,
          plan_stale: planStale(state),
          open_blocks: 1,
          filename: `${IDEA_SESSION}-rev${state.revision}.md`,
          markdown: `# 하루를 정리하는 뭔가\n\n- 구상 revision: **${state.revision}**\n`,
        },
      });
      return;
    }

    if (/^\/api\/sessions\/[^/]+\/plan-actions$/.test(path)) {
      await route.fulfill({
        json: { recommended: null, now: [], roadmap: [], actions: [] },
      });
      return;
    }
    if (/^\/api\/sessions\/[^/]+\/tasks$/.test(path)) {
      await route.fulfill({
        json: {
          team_lead: "codex",
          agents: ["cursor", "codex", "claude"],
          tasks: [],
          claimable: [],
        },
      });
      return;
    }
    if (/^\/api\/sessions\/[^/]+\/inbox$/.test(path)) {
      await route.fulfill({
        json: {
          pending_count: 0,
          pending_questions: 0,
          pending_builds: 0,
          human_inbox: [],
        },
      });
      return;
    }
    if (/^\/api\/sessions\/[^/]+\/objections$/.test(path)) {
      await route.fulfill({ json: { ok: true, objections: [] } });
      return;
    }

    const detail = path.match(/^\/api\/sessions\/([^/]+)$/);
    if (detail) {
      const isIdea = detail[1] === IDEA_SESSION;
      await route.fulfill({
        json: {
          id: detail[1],
          topic: isIdea ? "Ideation journey" : "Legacy execute",
          plan_md:
            "## 지금 실행\n1.\n   - 무엇을: 한다\n   - 어디서: `x.py`\n   - 검증: 됨",
          transcript_md: "",
          meta: {},
          chat: [],
          // `actions` must be present — the plan/execute surface filters it and
          // a missing array crashes the shell before the session renders.
          run: isIdea
            ? { status: "idle", ideation: state, actions: [], executions: [] }
            : {
                status: "idle",
                actions: [],
                executions: [],
                plan_workflow: { enabled: true, phase: "APPROVED" },
              },
        },
      });
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
  await page.getByRole("tab", { name: "Dogfood" }).click();
  // Scope to the rail: once a session is open the chrome shows its topic as a
  // button too, which makes a bare name lookup ambiguous.
  await page
    .getByRole("complementary", { name: /Sessions|세션/i })
    .getByRole("button", { name })
    .click();
}

const panel = (page: Page) => page.locator(".concept-panel");

test("candidates are comparable and a choice survives a refresh", async ({
  page,
}) => {
  const state = freshState();
  const requests: string[] = [];
  await initialize(page);
  await mockIdeationApi(page, state, requests);
  await page.goto("/");
  await openSession(page, "Ideation journey");

  await expect(panel(page)).toBeVisible();
  await expect(panel(page).locator(".concept-candidate")).toHaveCount(3);
  await expect(panel(page)).toContainText("일기 앱과 달리 길게 쓸 수 없다");
  // an unparsed candidate is shown, not hidden
  await expect(panel(page)).toContainText("형식을 지키지 않은 자유 응답");

  await panel(page)
    .locator(".concept-candidate", { hasText: "자동 수집 타임라인" })
    .getByRole("button", { name: "이걸로" })
    .click();

  await expect(panel(page)).toContainText("구상 선택");
  await expect(
    panel(page).locator(".concept-candidate.is-selected"),
  ).toContainText("자동 수집 타임라인");

  // refresh → restored from the server, not from local state
  await page.reload();
  await openSession(page, "Ideation journey");
  await expect(
    panel(page).locator(".concept-candidate.is-selected"),
  ).toContainText("자동 수집 타임라인");
});

test("a rejection is kept visible with the rest of the candidates", async ({
  page,
}) => {
  const state = freshState();
  await initialize(page);
  await mockIdeationApi(page, state, []);
  await page.goto("/");
  await openSession(page, "Ideation journey");

  await panel(page)
    .locator(".concept-candidate", { hasText: "하루 한 줄 회고" })
    .getByRole("button", { name: "아님" })
    .click();

  await expect(
    panel(page).locator(".concept-candidate.is-rejected"),
  ).toContainText("하루 한 줄 회고");
  await expect(panel(page).locator(".concept-candidate")).toHaveCount(3);
});

test("a stale choice is refused and the newer candidates are shown", async ({
  page,
}) => {
  const state = freshState();
  await initialize(page);
  await mockIdeationApi(page, state, []);
  await page.goto("/");
  await openSession(page, "Ideation journey");
  await expect(panel(page)).toBeVisible();

  // the concept moves on somewhere else while this view is open
  state.revision += 5;
  state.selection = {
    option_id: "opt-0-cursor",
    parent_ids: [],
    reason: "다른 곳에서",
  };
  state.stage = "shape";

  await panel(page)
    .locator(".concept-candidate", { hasText: "자동 수집 타임라인" })
    .getByRole("button", { name: "이걸로" })
    .click();

  await expect(panel(page)).toContainText("다른 곳에서 구상이 바뀌었습니다");
  await expect(
    panel(page).locator(".concept-candidate.is-selected"),
  ).toContainText("하루 한 줄 회고");
});

test("export warns about a stale plan before the user copies it", async ({
  page,
}) => {
  const state = freshState();
  await initialize(page);
  await mockIdeationApi(page, state, []);
  await page.goto("/");
  await openSession(page, "Ideation journey");

  // a plan was written, then the concept changed
  state.plan_source_revision = state.revision;
  state.revision += 1;

  await panel(page).getByRole("button", { name: "계획 복사" }).click();

  await expect(panel(page)).toContainText("계획이 최신 구상보다 오래됐습니다");
  await expect(panel(page)).toContainText("미결 BLOCK 1건이 문서에 포함됩니다");
  await expect(panel(page)).toContainText(
    `내보낼 문서 보기 (rev ${state.revision})`,
  );
});

test("nothing on the idea lane requests an execute endpoint", async ({
  page,
}) => {
  const state = freshState();
  const requests: string[] = [];
  await initialize(page);
  await mockIdeationApi(page, state, requests);
  await page.goto("/");
  await openSession(page, "Ideation journey");
  await expect(panel(page)).toBeVisible();

  await panel(page)
    .locator(".concept-candidate", { hasText: "자동 수집 타임라인" })
    .getByRole("button", { name: "이걸로" })
    .click();
  await expect(panel(page)).toContainText("구상 선택");
  await panel(page).getByRole("button", { name: "계획 복사" }).click();
  await expect(panel(page)).toContainText("내보낼 문서 보기");

  const execCalls = requests.filter((r) =>
    /(execute|plan\/approve|dry-run|merge|verify)/.test(r),
  );
  expect(execCalls).toEqual([]);
  // and the execute-lane surfaces are not on screen
  await expect(page.locator(".composer-event-stack__work")).toHaveCount(0);
  await expect(page.locator(".plan-approval-strip")).toHaveCount(0);
});

test("an existing session keeps its own surface", async ({ page }) => {
  const state = freshState();
  await initialize(page);
  await mockIdeationApi(page, state, []);
  await page.goto("/");
  await openSession(page, "Legacy execute");

  await expect(panel(page)).toHaveCount(0);
  await expect(page.locator(".workbench-mode-tabs button")).toHaveCount(6);
});
