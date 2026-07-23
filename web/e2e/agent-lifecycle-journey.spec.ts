import { resolve } from "node:path";
import { expect, test, type Page, type Route } from "playwright/test";

const SESSION_ID = "lifecycle-acceptance";
const SESSION_TOPIC = "Lifecycle acceptance";
const PLAN_HASH_V1 = "a".repeat(64);
const PLAN_HASH_V2 = "b".repeat(64);
const EXECUTION_ID = "execution-golden-1";
const MERGE_SHA = "c".repeat(40);
const EVIDENCE_DIR = resolve(
  process.cwd(),
  "../.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser",
);

const planMarkdown = `## 목표
Decision Queue에서 Oracle PASS까지 한 흐름으로 검증합니다.

## 지금 실행
1.
   - 무엇을: 연결된 golden journey 검증
   - 어디서: \`web/e2e/agent-lifecycle-journey.spec.ts\`
   - 검증: \`npx playwright test e2e/agent-lifecycle-journey.spec.ts\``;

const recommendedAction = {
  index: 1,
  what: "연결된 golden journey 검증",
  where: "web/e2e/agent-lifecycle-journey.spec.ts",
  verify: "npx playwright test e2e/agent-lifecycle-journey.spec.ts",
  refs: [],
  expected_paths: ["web/e2e/agent-lifecycle-journey.spec.ts"],
  recommended: true,
  kind: "now",
  executable: true,
  isolation: "worktree",
};

const queuedQuestion = {
  id: "queued-question-2",
  kind: "question",
  status: "pending",
  prompt: "후속 문서 범위를 선택하세요.",
  body: "현재 gate 다음에 처리됩니다.",
  source: "claude",
  caller_agent: "claude",
  created_at: "2026-07-23T00:00:01Z",
  decision_version: 2,
  priority: 20,
  options: [{ id: "later", label: "나중에" }],
};

const staleQuestion = {
  id: "stale-question-1",
  kind: "question",
  status: "pending",
  prompt: "stale guard 범위를 선택하세요.",
  body: "한 번만 처리할 수 있습니다.",
  source: "codex",
  caller_agent: "codex",
  created_at: "2026-07-23T00:00:00Z",
  decision_version: 7,
  priority: 100,
  options: [
    { id: "safe", label: "안전한 범위", recommended: true },
    { id: "full", label: "전체 범위", recommended: false },
  ],
};

type FixtureKind = "happy" | "repair" | "stale" | "dirty";
type FixturePhase =
  | "intake"
  | "plan_pending"
  | "approved"
  | "execute_pending"
  | "oracle_fail"
  | "succeeded"
  | "question"
  | "dirty_blocked";

type GateLedgerEntry = {
  readonly pre_state: string;
  readonly human_action: string;
  readonly api: string;
  readonly post_state: string;
  readonly negative_assertion: string;
};

type RequestReceipt = {
  readonly method: string;
  readonly path: string;
  readonly body: string;
};

type FixtureState = {
  readonly kind: FixtureKind;
  phase: FixturePhase;
  version: number;
  planRevision: number;
  planHash: string;
  approvedPlanHash: string | null;
  approvedBy: string | null;
  repairAttempt: number;
  staleResolved: boolean;
  readonly requests: RequestReceipt[];
  readonly gateLedger: GateLedgerEntry[];
  readonly audits: Record<string, unknown>[];
};

function createState(kind: FixtureKind): FixtureState {
  return {
    kind,
    phase: kind === "stale" ? "question" : "intake",
    version: kind === "stale" ? 7 : 1,
    planRevision: 1,
    planHash: PLAN_HASH_V1,
    approvedPlanHash: null,
    approvedBy: null,
    repairAttempt: 0,
    staleResolved: false,
    requests: [],
    gateLedger: [],
    audits: [],
  };
}

function activeExecution(state: FixtureState): Record<string, unknown> | null {
  if (
    state.phase !== "execute_pending" &&
    state.phase !== "oracle_fail" &&
    state.phase !== "succeeded"
  ) {
    return null;
  }
  const failed = state.phase === "oracle_fail";
  const succeeded = state.phase === "succeeded";
  return {
    id: EXECUTION_ID,
    action_index: 1,
    action_kind: "now",
    status: succeeded ? "merged" : "pending_approval",
    diff: "diff --git a/web/e2e/agent-lifecycle-journey.spec.ts b/web/e2e/agent-lifecycle-journey.spec.ts\n@@ -1 +1 @@\n-old\n+golden",
    diff_stat: "1 file changed, 1 insertion(+), 1 deletion(-)",
    touched_paths: ["web/e2e/agent-lifecycle-journey.spec.ts"],
    expected_paths: ["web/e2e/agent-lifecycle-journey.spec.ts"],
    paths_outside_expected: [],
    isolation_requested: "worktree",
    isolation_effective: "worktree",
    is_worktree_execution: true,
    worktree_path: "/tmp/agent-lab-golden-worktree",
    exec_branch: "agent-lab/exec-golden",
    base_branch: "main",
    base_sha: "d".repeat(40),
    exec_commit_sha: "e".repeat(40),
    workspace: "/tmp/agent-lab-golden-worktree",
    merge:
      succeeded || failed
        ? {
            status: "merged",
            commit_sha: MERGE_SHA,
            conflict_files: [],
            checks: { clean: true, diff_check: true, tests: true },
          }
        : null,
    oracle:
      succeeded || failed
        ? {
            verdict: failed ? "fail" : "pass",
            detail: failed
              ? "adversarial test failed"
              : "all acceptance checks passed",
            evidence: failed
              ? ["raw/oracle-fail.json"]
              : ["raw/oracle-pass.json", "raw/merge-checks.json"],
          }
        : null,
    oracle_verdict: failed ? "fail" : succeeded ? "pass" : null,
    verify_after_merge:
      succeeded || failed
        ? {
            status: failed ? "failed" : "passed",
            oracle: {
              verdict: failed ? "fail" : "pass",
              detail: failed
                ? "adversarial test failed"
                : "all acceptance checks passed",
              evidence: failed
                ? ["raw/oracle-fail.json"]
                : ["raw/oracle-pass.json", "raw/merge-checks.json"],
            },
          }
        : null,
    repair:
      state.repairAttempt > 0
        ? {
            attempt: state.repairAttempt,
            max_attempts: 2,
            strategy: "re-discuss",
            bounded: true,
          }
        : null,
    approved_by: "human:e2e",
  };
}

function pendingInboxItems(state: FixtureState): Record<string, unknown>[] {
  if (state.phase === "question" && !state.staleResolved) {
    return [staleQuestion, queuedQuestion];
  }
  if (
    state.phase === "plan_pending" ||
    state.phase === "execute_pending" ||
    state.phase === "oracle_fail" ||
    state.phase === "dirty_blocked"
  ) {
    return [queuedQuestion];
  }
  return [];
}

function activeGateId(state: FixtureState): string | null {
  if (state.phase === "plan_pending") return "plan-gate-1";
  if (
    state.phase === "execute_pending" ||
    state.phase === "oracle_fail" ||
    state.phase === "dirty_blocked"
  ) {
    return EXECUTION_ID;
  }
  if (state.phase === "question" && !state.staleResolved) {
    return staleQuestion.id;
  }
  return null;
}

function openGates(state: FixtureState): Array<{
  readonly gate_id: string;
  readonly kind: string;
}> {
  const active = activeGateId(state);
  const gates = active
    ? [
        {
          gate_id: active,
          kind:
            state.phase === "plan_pending"
              ? "plan_approval"
              : state.phase === "question"
                ? "question"
                : "merge_review",
        },
      ]
    : [];
  if (
    active &&
    active !== queuedQuestion.id &&
    pendingInboxItems(state).some((item) => item.id === queuedQuestion.id)
  ) {
    gates.push({ gate_id: queuedQuestion.id, kind: "question" });
  }
  return gates;
}

function missionReadModel(state: FixtureState): Record<string, unknown> {
  const items = pendingInboxItems(state);
  const active = activeGateId(state);
  const succeeded = state.phase === "succeeded";
  const failed = state.phase === "oracle_fail";
  return {
    session_id: SESSION_ID,
    migrated: true,
    source: "mission_journal",
    mission_id: "mission-lifecycle-1",
    goal: "Decision Queue to Oracle PASS",
    state: succeeded
      ? "SUCCEEDED"
      : failed
        ? "REPAIRING"
        : state.phase === "plan_pending"
          ? "AWAITING_PLAN_DECISION"
          : "EXECUTING",
    version: state.version,
    plan_revision: state.planRevision,
    plan_hash: state.planHash,
    approved_plan_hash: state.approvedPlanHash,
    repair_attempt: state.repairAttempt,
    max_repair_attempts: 2,
    oracle_verdict: failed ? "fail" : succeeded ? "pass" : null,
    next_action: succeeded
      ? "view_result"
      : failed
        ? "repair_or_re_discuss"
        : state.phase === "plan_pending"
          ? "decide_plan"
          : "review_execution",
    event_cursor: state.version,
    operational_status: succeeded
      ? "COMPLETED"
      : active
        ? "WAITING_FOR_HUMAN"
        : "RUNNING",
    open_execution_gates: openGates(state),
    legacy_phase: succeeded ? "MISSION_DONE" : "EXECUTE",
    plan: {
      phase: state.phase === "plan_pending" ? "HUMAN_PENDING" : "APPROVED",
      hash: state.planHash,
      approved_hash: state.approvedPlanHash,
      pending_approval: state.phase === "plan_pending",
    },
    work_phase: succeeded
      ? "done"
      : state.phase === "plan_pending"
        ? "plan_draft"
        : state.phase === "intake"
          ? "plan_draft"
          : "review_needed",
    mission_overview: {
      phase_label: succeeded
        ? "MISSION_DONE"
        : failed
          ? "REPAIR"
          : "WAITING_FOR_HUMAN",
      paused: false,
      circuit_breaker: false,
      pending_inbox_count: items.length,
    },
    inbox_summary: {
      pending_count: items.length,
      pending_questions: items.filter((item) => item.kind === "question")
        .length,
      pending_builds: 0,
    },
    inbox_items: items,
    routing: {
      risk: "high",
      intent: "implementation",
      preset: "supervisor",
      turn: "loop",
      safety_floor_applied: true,
    },
    active_decision: active
      ? {
          decision_id: active,
          expected_version: state.version,
          canonical_order: "priority,created_at,id",
        }
      : null,
    run_audit: state.audits,
  };
}

function runtimePayload(state: FixtureState): Record<string, unknown> {
  const execution = activeExecution(state);
  const succeeded = state.phase === "succeeded";
  const failed = state.phase === "oracle_fail";
  const items = pendingInboxItems(state);
  return {
    ok: true,
    session_id: SESSION_ID,
    mode: "mission",
    has_plan: state.phase !== "intake",
    work_phase: succeeded
      ? "done"
      : state.phase === "plan_pending"
        ? "plan_draft"
        : "review_needed",
    mission: {
      enabled: true,
      phase: succeeded ? "MISSION_DONE" : failed ? "REPAIR" : "EXECUTE_QUEUE",
      paused: false,
      circuit_breaker: false,
      current_action_index: execution ? 1 : null,
    },
    execute: {
      has_pending: Boolean(execution && !succeeded),
      pending_execution_id: execution && !succeeded ? EXECUTION_ID : null,
      has_dry_run_diff: Boolean(execution),
      latest_execution_id: execution ? EXECUTION_ID : null,
      latest_status: execution?.status ?? null,
      oracle_verdict: failed ? "fail" : succeeded ? "pass" : null,
    },
    gates: {
      execute_blocked: state.phase === "dirty_blocked",
      pending_agreement: false,
      gate_profile: "dev",
    },
    inbox: {
      pending: items.length > 0,
      pending_count: items.length,
      pending_questions: items.length,
      pending_builds: 0,
    },
    next_action: succeeded ? "완료 결과 확인" : "Human gate 처리",
    merge_checks: {
      merge_disabled: false,
      clean: true,
      diff_check: true,
      tests: true,
      checks: [
        { id: "clean", ok: true },
        { id: "diff_check", ok: true },
        { id: "tests", ok: true },
      ],
    },
    evidence: {
      entries: succeeded
        ? [
            {
              id: "oracle-pass-evidence",
              kind: "ORACLE",
              status: "pass",
              path: "raw/oracle-pass.json",
              created_at: "2026-07-23T00:10:00Z",
            },
          ]
        : [],
    },
    autonomy: {
      level: "L0",
      effective_level: "L0",
      display_level: "L0",
      level_name: "Human controlled",
      trust_budget: { auto_merge_remaining: 0, auto_merge_total: 0 },
      signals: {
        auto_approve_enabled: false,
        mission_loop_enabled: true,
        autonomous_segment_active: false,
      },
    },
    plan_workflow: {
      enabled: state.phase !== "intake",
      phase: state.phase === "plan_pending" ? "HUMAN_PENDING" : "APPROVED",
      notice:
        state.phase === "plan_pending"
          ? "plan_pending_approval"
          : "plan_approved",
      round: state.planRevision,
    },
  };
}

function sessionDetail(state: FixtureState): Record<string, unknown> {
  const execution = activeExecution(state);
  return {
    id: SESSION_ID,
    topic: SESSION_TOPIC,
    plan_md: state.phase === "intake" ? "" : planMarkdown,
    transcript_md: "",
    meta: {},
    chat: [],
    run: {
      status: "idle",
      active_plan_relpath: "plan.md",
      plan_revision: state.planRevision,
      plan_hash: state.planHash,
      approved_by: state.approvedBy,
      actions: state.phase === "intake" ? [] : [recommendedAction],
      executions: execution ? [execution] : [],
      plan_workflow:
        state.phase === "intake"
          ? { enabled: false, phase: "INACTIVE" }
          : {
              enabled: true,
              phase:
                state.phase === "plan_pending" ? "HUMAN_PENDING" : "APPROVED",
              notice:
                state.phase === "plan_pending"
                  ? "plan_pending_approval"
                  : "plan_approved",
              plan_hash_at_approval: state.approvedPlanHash,
              last_plan_gate: {
                ok: true,
                plan_hash: state.planHash,
                revision: state.planRevision,
              },
            },
      mission_loop: {
        enabled: true,
        phase:
          state.phase === "succeeded"
            ? "MISSION_DONE"
            : state.phase === "oracle_fail"
              ? "REPAIR"
              : "EXECUTE_QUEUE",
        paused: false,
        iteration: state.repairAttempt + 1,
        discuss_recovery:
          state.repairAttempt > 0
            ? {
                pending: state.phase === "oracle_fail",
                reason: "oracle_failed_re_discuss",
                action_index: 1,
              }
            : null,
      },
      verified_loop: {
        status: state.phase === "succeeded" ? "done" : "running",
        loop_goal: {
          text: "Decision Queue to Oracle PASS",
          approved_by: state.approvedBy,
        },
        verification_attempts: state.repairAttempt + 1,
        max_verification_attempts: 2,
        last_check:
          state.phase === "succeeded"
            ? {
                verdict: "verified",
                detail: "Oracle PASS with merge evidence",
                source: "oracle",
              }
            : null,
      },
      human_inbox: pendingInboxItems(state),
      run_audit: state.audits,
    },
  };
}

async function fulfillJson(
  route: Route,
  json: Record<string, unknown>,
  status = 200,
): Promise<void> {
  await route.fulfill({ status, json });
}

function recordRequest(state: FixtureState, route: Route): RequestReceipt {
  const request = route.request();
  const receipt = {
    method: request.method(),
    path: new URL(request.url()).pathname,
    body: request.postData() ?? "",
  };
  state.requests.push(receipt);
  return receipt;
}

function addGateLedger(state: FixtureState, entry: GateLedgerEntry): void {
  state.gateLedger.push(entry);
}

async function installFixture(page: Page, state: FixtureState): Promise<void> {
  await page.route(/^http:\/\/127\.0\.0\.1:4173\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/health") {
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
            model: "cursor/default",
          },
          {
            id: "codex",
            label: "Codex",
            ready: true,
            configured: true,
            bridge: "n/a",
            model: "openai/gpt-5.6",
          },
          {
            id: "claude",
            label: "Claude",
            ready: true,
            configured: true,
            bridge: "n/a",
            model: "anthropic/claude-opus",
          },
        ],
      });
      return;
    }
    if (path === "/api/health/flags") {
      await fulfillJson(route, {
        ok: true,
        count: 1,
        flags: [
          {
            name: "AGENT_LAB_MISSION_UI_READ_MODEL",
            value: "1",
            effective: "1",
          },
        ],
      });
      return;
    }
    if (path === "/api/sessions") {
      await fulfillJson(route, {
        sessions: [
          {
            id: SESSION_ID,
            topic: SESSION_TOPIC,
            updated_at: "2026-07-23T00:00:00Z",
            workflow: "room.parallel",
          },
        ],
      });
      return;
    }
    if (path === `/api/sessions/${SESSION_ID}`) {
      await fulfillJson(route, sessionDetail(state));
      return;
    }
    if (path === `/api/sessions/${SESSION_ID}/plan-actions`) {
      const action = state.phase === "intake" ? null : recommendedAction;
      await fulfillJson(route, {
        recommended: action,
        now: action ? [action] : [],
        roadmap: [],
        actions: action ? [action] : [],
      });
      return;
    }
    if (path === `/api/sessions/${SESSION_ID}/tasks`) {
      await fulfillJson(route, {
        team_lead: "codex",
        agents: ["cursor", "codex", "claude"],
        tasks: [],
        claimable: [],
        counts: { pending: 0, in_progress: 0, completed: 0 },
        objections: [],
        open_objections: [],
        open_objection_count: 0,
        consensus_tasks_ready: true,
        consensus_task_blockers: [],
      });
      return;
    }
    if (path === `/api/sessions/${SESSION_ID}/runtime`) {
      await fulfillJson(route, runtimePayload(state));
      return;
    }
    if (path === `/api/sessions/${SESSION_ID}/mission/read-model`) {
      await fulfillJson(route, missionReadModel(state));
      return;
    }
    if (path === `/api/sessions/${SESSION_ID}/mission/events`) {
      await route.fulfill({
        contentType: "text/event-stream",
        body: `data: ${JSON.stringify({ type: "projection_changed", version: state.version })}\n\n`,
      });
      return;
    }
    if (path === `/api/sessions/${SESSION_ID}/inbox`) {
      const items = pendingInboxItems(state);
      await fulfillJson(route, {
        pending_count: items.length,
        pending_questions: items.length,
        pending_builds: 0,
        human_inbox: items,
      });
      return;
    }
    if (
      path ===
        `/api/sessions/${SESSION_ID}/inbox/${staleQuestion.id}/resolve` &&
      request.method() === "POST"
    ) {
      const receipt = recordRequest(state, route);
      const body = JSON.parse(receipt.body) as Record<string, unknown>;
      if (
        state.staleResolved ||
        body.expected_version !== state.version ||
        body.decision_id !== staleQuestion.id
      ) {
        await fulfillJson(
          route,
          {
            detail: {
              code: "stale_answer",
              message: "stale answer: expected_version mismatch",
              current_version: state.version,
            },
          },
          409,
        );
        return;
      }
      const preState = "WAITING_FOR_HUMAN@v7";
      state.staleResolved = true;
      state.version += 1;
      addGateLedger(state, {
        pre_state: preState,
        human_action: `answer:${staleQuestion.id}`,
        api: `POST ${path}`,
        post_state: "EXECUTING@v8",
        negative_assertion: "duplicate answer returns 409 and remains v8",
      });
      await fulfillJson(route, {
        ok: true,
        pending_count: 0,
        pending_questions: 0,
        pending_builds: 0,
        human_inbox: [],
        version: state.version,
      });
      return;
    }
    if (path === "/api/room/runs" && request.method() === "POST") {
      const receipt = recordRequest(state, route);
      const preVersion = state.version;
      state.phase = "plan_pending";
      state.version += 1;
      addGateLedger(state, {
        pre_state: `DISCUSS@v${preVersion}`,
        human_action: "submit topic",
        api: "POST /api/room/runs",
        post_state: `AWAITING_PLAN_DECISION@v${state.version}`,
        negative_assertion: "no plan approval or execution side effect",
      });
      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          {
            type: "start",
            session_id: SESSION_ID,
            routing: {
              risk: "high",
              intent: "implementation",
              preset: "supervisor",
              turn: "loop",
            },
          },
          {
            type: "plan_workflow_phase",
            session_id: SESSION_ID,
            phase: "HUMAN_PENDING",
            notice: "plan_pending_approval",
          },
          {
            type: "complete",
            session_id: SESSION_ID,
            send_receipt: "plan_updated",
          },
        ]
          .map((event) => `data: ${JSON.stringify(event)}\n\n`)
          .join(""),
      });
      return;
    }
    if (
      path === `/api/sessions/${SESSION_ID}/plan/reject` &&
      request.method() === "POST"
    ) {
      const receipt = recordRequest(state, route);
      const preRevision = state.planRevision;
      state.planRevision += 1;
      state.planHash = PLAN_HASH_V2;
      state.version += 1;
      state.phase = "plan_pending";
      addGateLedger(state, {
        pre_state: `HUMAN_PENDING:${PLAN_HASH_V1}:r${preRevision}`,
        human_action: "request plan revision",
        api: `POST ${path}`,
        post_state: `HUMAN_PENDING:${PLAN_HASH_V2}:r${state.planRevision}`,
        negative_assertion: "old plan hash remains unapproved",
      });
      await fulfillJson(route, {
        ok: true,
        plan_workflow: {
          enabled: true,
          phase: "REFINE",
          notice: "plan_rejected_refine",
        },
      });
      return;
    }
    if (
      path === `/api/sessions/${SESSION_ID}/plan/approve` &&
      request.method() === "POST"
    ) {
      recordRequest(state, route);
      const preVersion = state.version;
      state.approvedPlanHash = state.planHash;
      state.approvedBy = "human:e2e";
      state.phase = "approved";
      state.version += 1;
      addGateLedger(state, {
        pre_state: `HUMAN_PENDING:${state.planHash}@v${preVersion}`,
        human_action: "approve and run",
        api: `POST ${path}`,
        post_state: `APPROVED:${state.planHash}@v${state.version}`,
        negative_assertion: "approved_by is not auto",
      });
      await fulfillJson(route, {
        ok: true,
        plan_workflow: {
          enabled: true,
          phase: "APPROVED",
          plan_hash_at_approval: state.planHash,
          approved_by: state.approvedBy,
        },
        verified_loop: {
          status: "running",
          loop_goal: { approved_by: state.approvedBy },
        },
      });
      return;
    }
    if (
      path === `/api/sessions/${SESSION_ID}/execute/dry-run` &&
      request.method() === "POST"
    ) {
      recordRequest(state, route);
      const preVersion = state.version;
      if (state.kind === "dirty") {
        state.phase = "dirty_blocked";
        state.version += 1;
        addGateLedger(state, {
          pre_state: `APPROVED@v${preVersion}`,
          human_action: "start worktree dry-run",
          api: `POST ${path}`,
          post_state: `DIRTY_WORKTREE_BLOCKED@v${state.version}`,
          negative_assertion: "no execution diff or merge produced",
        });
        await fulfillJson(
          route,
          {
            detail: {
              code: "base_branch_dirty",
              message: "base branch working tree must be clean",
              execution_id: EXECUTION_ID,
            },
          },
          409,
        );
        return;
      }
      state.phase = "execute_pending";
      state.version += 1;
      addGateLedger(state, {
        pre_state: `APPROVED@v${preVersion}`,
        human_action: "start worktree dry-run",
        api: `POST ${path}`,
        post_state: `MERGE_REVIEW@v${state.version}`,
        negative_assertion: "worktree diff is not merged automatically",
      });
      await fulfillJson(route, {
        ok: true,
        execution: activeExecution(state),
      });
      return;
    }
    if (
      path === `/api/sessions/${SESSION_ID}/execute/resolve` &&
      request.method() === "POST"
    ) {
      recordRequest(state, route);
      const preVersion = state.version;
      state.phase = state.kind === "repair" ? "oracle_fail" : "succeeded";
      state.version += 1;
      state.audits.push({
        event: "merge_review_resolved",
        approved_by: "human:e2e",
        commit_sha: MERGE_SHA,
        checks: { clean: true, diff_check: true, tests: true },
      });
      addGateLedger(state, {
        pre_state: `MERGE_REVIEW@v${preVersion}`,
        human_action: "approve diff and merge",
        api: `POST ${path}`,
        post_state:
          state.phase === "succeeded"
            ? `SUCCEEDED@v${state.version}`
            : `REPAIRING@v${state.version}`,
        negative_assertion: "trust-budget auto-merge remains unused",
      });
      await fulfillJson(route, {
        ok: true,
        execution: activeExecution(state),
        approval: {
          approved_by: "human:e2e",
          auto_merge: false,
          trust_budget_used: 0,
        },
      });
      return;
    }
    if (
      path === `/api/sessions/${SESSION_ID}/execute/reverify` &&
      request.method() === "POST"
    ) {
      recordRequest(state, route);
      const preVersion = state.version;
      state.repairAttempt += 1;
      state.version += 1;
      const pass = state.repairAttempt >= 2;
      state.phase = pass ? "succeeded" : "oracle_fail";
      state.audits.push({
        event: pass ? "oracle_pass" : "oracle_fail_repair",
        attempt: state.repairAttempt,
        max_attempts: 2,
        strategy: "re-discuss",
        commit_sha: MERGE_SHA,
      });
      addGateLedger(state, {
        pre_state: `REPAIRING@v${preVersion}`,
        human_action: `bounded Oracle retry ${state.repairAttempt}`,
        api: `POST ${path}`,
        post_state: pass
          ? `SUCCEEDED@v${state.version}`
          : `REPAIRING@v${state.version}`,
        negative_assertion: pass
          ? "pending decision is empty only after Oracle PASS"
          : "Oracle FAIL is not counted as success",
      });
      await fulfillJson(route, {
        ok: true,
        execution: activeExecution(state),
        verify_after_merge: {
          status: pass ? "passed" : "failed",
          commit_sha: MERGE_SHA,
          oracle_evidence: pass
            ? ["raw/oracle-pass.json"]
            : ["raw/oracle-fail.json"],
        },
        repair: {
          attempt: state.repairAttempt,
          max_attempts: 2,
          strategy: "re-discuss",
          bounded: true,
        },
      });
      return;
    }
    if (path === "/api/inbox/summary") {
      await fulfillJson(route, {
        ok: true,
        total_pending: pendingInboxItems(state).length,
        pending_questions: pendingInboxItems(state).length,
        pending_builds: 0,
        sessions: [],
      });
      return;
    }
    if (path === "/api/commands") {
      await fulfillJson(route, { ok: true, commands: [] });
      return;
    }
    if (path === "/api/health/readiness") {
      await fulfillJson(route, {
        verdict: "ready",
        checks: [],
        next_actions: [],
        agents: [],
      });
      return;
    }
    if (path === "/api/auth/providers") {
      await fulfillJson(route, { ok: true, providers: [] });
      return;
    }
    if (path === "/api/session-setup/options") {
      await fulfillJson(route, {
        workspaces: [
          {
            id: "agent-lab",
            label: "agent-lab",
            path: "/workspace/agent-lab",
            available: true,
          },
        ],
        defaults: { workspace_id: "agent-lab" },
      });
      return;
    }
    if (path.endsWith("/files/roots")) {
      await fulfillJson(route, { roots: [] });
      return;
    }
    if (path.endsWith("/agent-capabilities")) {
      await fulfillJson(route, { ok: true, agent_capabilities: {} });
      return;
    }
    await fulfillJson(route, { ok: true });
  });
}

async function initialize(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("agent-lab-first-run-onboarding-version", "p1f");
    localStorage.setItem("agent-lab-inspector-open", "1");
    localStorage.setItem("agent-lab-locale", "ko");
    localStorage.setItem("agent-lab-last-session-id", "lifecycle-acceptance");
  });
}

async function openFixtureSession(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByLabel("메시지 입력")).toBeVisible();
}

async function submitTopic(page: Page): Promise<void> {
  const input = page.getByLabel("메시지 입력");
  await input.fill("고위험 구현 요청을 plan-first worktree로 검증해 주세요.");
  await page.getByRole("button", { name: "전송" }).click();
  const permissions = page.getByRole("alertdialog", { name: "에이전트 권한" });
  if (await permissions.isVisible()) {
    await permissions.getByRole("button", { name: "허용하고 전송" }).click();
  }
  await expect(page.locator(".plan-approval-strip")).toBeVisible();
}

async function assertSingleActiveDecision(
  page: Page,
  decisionId: string,
  queuedCount = 2,
): Promise<void> {
  const stack = page.locator(
    `.composer-event-stack[data-active-decision-id="${decisionId}"]`,
  );
  await expect(stack).toHaveCount(1);
  await expect(page.locator("[data-active-decision-id]")).toHaveCount(1);
  await expect(stack.locator(".composer-decision-queue__count")).toHaveText(
    `${queuedCount}건`,
  );
  await expect(
    stack.locator(".composer-event-stack__section").getByRole("button", {
      name: /승인하고 실행|승인|제출/,
    }),
  ).toHaveCount(1);
}

async function browserReadModel(page: Page): Promise<Record<string, unknown>> {
  return page.evaluate(async (sessionId) => {
    const response = await fetch(
      `/api/sessions/${sessionId}/mission/read-model`,
    );
    return (await response.json()) as Record<string, unknown>;
  }, SESSION_ID);
}

async function approvePlanAndAwaitDryRun(page: Page): Promise<void> {
  const review = page.locator(".plan-approval-strip");
  const approveAndExecute = review.getByRole("button", {
    name: "승인하고 실행",
  });
  const combined = await approveAndExecute.isVisible();
  await review
    .getByRole("button", { name: combined ? "승인하고 실행" : "승인만" })
    .click();
  const execute = page.getByRole("button", { name: "Execute", exact: true });
  if (!combined) {
    await expect(execute).toBeVisible();
    await execute.click();
  }
  await expect(
    page.getByRole("region", { name: "실행 승인 대기" }),
  ).toBeVisible();
}

function expectFinalAudit(
  projection: Record<string, unknown>,
  state: FixtureState,
): void {
  expect(projection).toMatchObject({
    state: "SUCCEEDED",
    operational_status: "COMPLETED",
    oracle_verdict: "pass",
    next_action: "view_result",
    approved_plan_hash: state.planHash,
    repair_attempt: state.repairAttempt,
  });
  expect(projection.open_execution_gates).toEqual([]);
  expect(projection.inbox_summary).toMatchObject({ pending_count: 0 });
  expect(projection.mission_overview).toMatchObject({
    phase_label: "MISSION_DONE",
    circuit_breaker: false,
  });
  const execution = activeExecution(state);
  expect(execution).toMatchObject({
    status: "merged",
    merge: {
      status: "merged",
      commit_sha: MERGE_SHA,
      conflict_files: [],
      checks: { clean: true, diff_check: true, tests: true },
    },
    oracle: {
      verdict: "pass",
      evidence: ["raw/oracle-pass.json", "raw/merge-checks.json"],
    },
    approved_by: "human:e2e",
  });
  expect(state.approvedBy).not.toBe("auto");
  expect(
    state.requests.some((request) => request.path.includes("/auto-merge")),
  ).toBe(false);
  expect(state.audits).not.toHaveLength(0);
}

test("connected Human-gated journey reaches PASS only with durable evidence", async ({
  page,
}) => {
  // Given: an existing Room session is idle and every production gate remains Human-controlled.
  const state = createState("happy");
  await initialize(page);
  await installFixture(page, state);
  await openFixtureSession(page);

  // When: the Human submits a high-risk implementation topic.
  await submitTopic(page);

  // Then: routing converges to one canonical plan decision while another Inbox item stays queued.
  await assertSingleActiveDecision(page, "plan-gate-1");
  const routed = await browserReadModel(page);
  expect(routed.routing).toEqual({
    risk: "high",
    intent: "implementation",
    preset: "supervisor",
    turn: "loop",
    safety_floor_applied: true,
  });
  expect(routed).toMatchObject({
    plan_hash: PLAN_HASH_V1,
    plan_revision: 1,
    approved_plan_hash: null,
    version: 2,
  });
  expect(state.requests[0]?.body).toContain("고위험 구현 요청");
  expect(state.requests[0]?.body).toContain("supervisor");

  // When: the Human approves the exact plan snapshot and starts the isolated dry-run.
  await approvePlanAndAwaitDryRun(page);

  // Then: the diff is durable, unmerged, and promoted as the only active decision.
  await assertSingleActiveDecision(page, EXECUTION_ID);
  const pending = activeExecution(state);
  expect(pending).toMatchObject({
    status: "pending_approval",
    isolation_effective: "worktree",
    diff_stat: "1 file changed, 1 insertion(+), 1 deletion(-)",
    paths_outside_expected: [],
  });
  expect(pending?.merge).toBeNull();
  expect(state.approvedBy).toBe("human:e2e");

  // When: the Human reviews the diff and approves merge.
  await page
    .getByRole("region", { name: "실행 승인 대기" })
    .getByRole("button", { name: "승인" })
    .click();

  // Then: completion requires merge provenance, green checks, Oracle evidence, and no pending decision.
  await expect(page.getByText("Oracle PASS").first()).toBeVisible();
  await expect(page.locator("[data-active-decision-id]")).toHaveCount(0);
  const finalProjection = await browserReadModel(page);
  expectFinalAudit(finalProjection, state);
  expect(state.gateLedger).toEqual([
    {
      pre_state: "DISCUSS@v1",
      human_action: "submit topic",
      api: "POST /api/room/runs",
      post_state: "AWAITING_PLAN_DECISION@v2",
      negative_assertion: "no plan approval or execution side effect",
    },
    {
      pre_state: `HUMAN_PENDING:${PLAN_HASH_V1}@v2`,
      human_action: "approve and run",
      api: `POST /api/sessions/${SESSION_ID}/plan/approve`,
      post_state: `APPROVED:${PLAN_HASH_V1}@v3`,
      negative_assertion: "approved_by is not auto",
    },
    {
      pre_state: "APPROVED@v3",
      human_action: "start worktree dry-run",
      api: `POST /api/sessions/${SESSION_ID}/execute/dry-run`,
      post_state: "MERGE_REVIEW@v4",
      negative_assertion: "worktree diff is not merged automatically",
    },
    {
      pre_state: "MERGE_REVIEW@v4",
      human_action: "approve diff and merge",
      api: `POST /api/sessions/${SESSION_ID}/execute/resolve`,
      post_state: "SUCCEEDED@v5",
      negative_assertion: "trust-budget auto-merge remains unused",
    },
  ]);
  await page.screenshot({
    path: resolve(EVIDENCE_DIR, "happy-final-pass.png"),
    fullPage: true,
  });
});

test("Oracle FAIL repairs through bounded re-discuss retries before PASS", async ({
  page,
}) => {
  // Given: a connected journey whose first post-merge Oracle verdict is forced to FAIL.
  const state = createState("repair");
  await initialize(page);
  await installFixture(page, state);
  await openFixtureSession(page);
  await submitTopic(page);

  // When: the Human revises the plan before approving the new durable snapshot.
  const review = page.locator(".plan-approval-strip");
  await review.getByRole("button", { name: "수정 요청" }).click();
  await review
    .locator("textarea#plan-revision-note-strip")
    .fill("Oracle 실패 복구 기준을 계획에 추가해 주세요.");
  await review.getByRole("button", { name: "수정 요청" }).click();
  await expect.poll(() => state.planRevision).toBe(2);
  expect(state.planHash).toBe(PLAN_HASH_V2);
  expect(state.approvedPlanHash).toBeNull();
  await page.reload();
  await expect(page.locator(".plan-approval-strip")).toBeVisible();
  await approvePlanAndAwaitDryRun(page);
  await page
    .getByRole("region", { name: "실행 승인 대기" })
    .getByRole("button", { name: "승인" })
    .click();

  // Then: misleading merge success remains REPAIRING because Oracle evidence failed.
  await expect(
    page
      .getByRole("region", { name: "실행 승인 대기" })
      .getByRole("button", { name: "Oracle 재검증" }),
  ).toBeVisible();
  await expect(page.locator(".ctx-mission")).toContainText("fail");
  await assertSingleActiveDecision(page, EXECUTION_ID);
  const failedProjection = await browserReadModel(page);
  expect(failedProjection).toMatchObject({
    state: "REPAIRING",
    oracle_verdict: "fail",
    repair_attempt: 0,
    max_repair_attempts: 2,
  });
  await page.screenshot({
    path: resolve(EVIDENCE_DIR, "repair-oracle-fail.png"),
    fullPage: true,
  });

  // When: the Human starts the bounded repair/re-discuss attempt.
  const queue = page.getByRole("region", { name: "실행 승인 대기" });
  await queue.getByRole("button", { name: "Oracle 재검증" }).click();

  // Then: attempt one remains failed and cannot close the mission.
  await expect.poll(() => state.repairAttempt).toBe(1);
  const firstRepair = await browserReadModel(page);
  expect(firstRepair).toMatchObject({
    state: "REPAIRING",
    oracle_verdict: "fail",
    repair_attempt: 1,
    next_action: "repair_or_re_discuss",
  });
  expect(state.audits.at(-1)).toMatchObject({
    event: "oracle_fail_repair",
    attempt: 1,
    max_attempts: 2,
    strategy: "re-discuss",
  });
  await assertSingleActiveDecision(page, EXECUTION_ID);

  // When: the Human authorizes the final bounded retry.
  await queue.getByRole("button", { name: "Oracle 재검증" }).click();

  // Then: PASS closes the decision only on attempt two with the same merge SHA.
  await expect(page.getByText("Oracle PASS").first()).toBeVisible();
  const repairedProjection = await browserReadModel(page);
  expectFinalAudit(repairedProjection, state);
  expect(state.repairAttempt).toBe(2);
  expect(state.audits.at(-1)).toMatchObject({
    event: "oracle_pass",
    attempt: 2,
    max_attempts: 2,
    commit_sha: MERGE_SHA,
  });
  expect(state.gateLedger.at(-2)).toMatchObject({
    post_state: "REPAIRING@v7",
    negative_assertion: "Oracle FAIL is not counted as success",
  });
  expect(state.gateLedger.at(-1)).toMatchObject({
    post_state: "SUCCEEDED@v8",
    negative_assertion: "pending decision is empty only after Oracle PASS",
  });
  await page.screenshot({
    path: resolve(EVIDENCE_DIR, "repair-final-pass.png"),
    fullPage: true,
  });
});

test("stale expected_version returns 409 without corrupting the resolved state", async ({
  page,
}) => {
  // Given: the canonical backend order promotes the high-priority question ahead of a queued item.
  const state = createState("stale");
  await initialize(page);
  await installFixture(page, state);
  await openFixtureSession(page);
  await assertSingleActiveDecision(page, staleQuestion.id);
  await page.screenshot({
    path: resolve(EVIDENCE_DIR, "single-active-decision-queued.png"),
    fullPage: true,
  });
  const before = await browserReadModel(page);
  expect(before.open_execution_gates).toEqual([
    { gate_id: staleQuestion.id, kind: "question" },
    { gate_id: queuedQuestion.id, kind: "question" },
  ]);

  // When: the Human answers once through the rendered Decision Queue.
  const inbox = page.locator(".human-inbox--composer");
  await inbox.getByRole("radio", { name: "안전한 범위" }).click();
  await inbox.getByRole("button", { name: "제출" }).click();
  await expect.poll(() => state.version).toBe(8);
  const firstBody = JSON.parse(
    state.requests.find((request) =>
      request.path.endsWith(`/${staleQuestion.id}/resolve`),
    )?.body ?? "{}",
  ) as Record<string, unknown>;
  expect(firstBody).toMatchObject({
    decision_id: staleQuestion.id,
    mission_id: "mission-lifecycle-1",
    expected_version: 7,
    selected: ["safe"],
  });

  // When: an old browser retries the same answer with expected_version 7.
  const staleResponse = await page.evaluate(
    async ({ sessionId, decisionId }) => {
      const response = await fetch(
        `/api/sessions/${sessionId}/inbox/${decisionId}/resolve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            decision_id: decisionId,
            mission_id: "mission-lifecycle-1",
            expected_version: 7,
            selected: ["safe"],
          }),
        },
      );
      return {
        status: response.status,
        body: (await response.json()) as Record<string, unknown>,
      };
    },
    { sessionId: SESSION_ID, decisionId: staleQuestion.id },
  );

  // Then: the duplicate is rejected and the durable v8 projection stays unchanged.
  expect(staleResponse).toMatchObject({
    status: 409,
    body: {
      detail: {
        code: "stale_answer",
        current_version: 8,
      },
    },
  });
  expect(state.version).toBe(8);
  expect(state.staleResolved).toBe(true);
  expect(
    state.requests.filter((request) =>
      request.path.endsWith(`/${staleQuestion.id}/resolve`),
    ),
  ).toHaveLength(2);
});

test("reload resumes the same pending operation without duplicating its decision", async ({
  page,
}) => {
  // Given: the journey is interrupted after a durable worktree diff is ready.
  const state = createState("happy");
  state.phase = "execute_pending";
  state.version = 4;
  state.approvedPlanHash = PLAN_HASH_V1;
  state.approvedBy = "human:e2e";
  await initialize(page);
  await installFixture(page, state);
  await openFixtureSession(page);
  await assertSingleActiveDecision(page, EXECUTION_ID);

  // When: the real page reloads mid-operation.
  await page.reload();

  // Then: one identical decision resumes and no side-effect POST is replayed.
  await assertSingleActiveDecision(page, EXECUTION_ID);
  expect(state.requests.filter((request) => request.method === "POST")).toEqual(
    [],
  );
  expect(activeExecution(state)).toMatchObject({
    id: EXECUTION_ID,
    status: "pending_approval",
    diff_stat: "1 file changed, 1 insertion(+), 1 deletion(-)",
  });
});

test("dirty worktree blocks dry-run and malformed decision payloads never promote success", async ({
  page,
}) => {
  // Given: a cohort fixture has a dirty base branch and no trust-budget authority.
  const state = createState("dirty");
  await initialize(page);
  await installFixture(page, state);
  await openFixtureSession(page);
  await submitTopic(page);

  // When: the Human approves the plan and the server rejects worktree creation.
  const review = page.locator(".plan-approval-strip");
  const approveAndExecute = review.getByRole("button", {
    name: "승인하고 실행",
  });
  const combined = await approveAndExecute.isVisible();
  await review
    .getByRole("button", { name: combined ? "승인하고 실행" : "승인만" })
    .click();
  if (!combined) {
    const execute = page.getByRole("button", { name: "Execute", exact: true });
    await expect(execute).toBeVisible();
    await execute.click();
  }

  // Then: the gate stays blocked with no diff, merge SHA, Oracle PASS, or false audit.
  await expect.poll(() => state.phase).toBe("dirty_blocked");
  expect(
    state.requests.some(
      (request) =>
        request.method === "POST" &&
        request.path === `/api/sessions/${SESSION_ID}/execute/dry-run`,
    ),
  ).toBe(true);
  expect(state.phase).toBe("dirty_blocked");
  expect(activeExecution(state)).toBeNull();
  expect(state.audits).toEqual([]);
  const blockedProjection = await browserReadModel(page);
  expect(blockedProjection).toMatchObject({
    state: "EXECUTING",
    oracle_verdict: null,
    repair_attempt: 0,
  });
  expect(blockedProjection.open_execution_gates).toEqual([
    { gate_id: EXECUTION_ID, kind: "merge_review" },
    { gate_id: queuedQuestion.id, kind: "question" },
  ]);

  // When: a malformed fixture omits decision_id while claiming a current version.
  const malformed = await page.evaluate(
    async ({ sessionId, decisionId }) => {
      const response = await fetch(
        `/api/sessions/${sessionId}/inbox/${decisionId}/resolve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ expected_version: 7, selected: ["safe"] }),
        },
      );
      return response.status;
    },
    { sessionId: SESSION_ID, decisionId: staleQuestion.id },
  );

  // Then: malformed input is rejected and the dirty-worktree blocker remains authoritative.
  expect(malformed).toBe(409);
  expect(state.phase).toBe("dirty_blocked");
  expect(state.audits).toEqual([]);
});
