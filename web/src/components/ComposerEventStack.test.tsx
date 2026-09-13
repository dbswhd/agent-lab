import type { ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MissionReadModelPayload, RuntimeSnapshot } from "../api/client";
import { ComposerEventStack } from "./ComposerEventStack";

const runtimeState = vi.hoisted((): { value: RuntimeSnapshot | null } => ({
  value: null,
}));

const readModelState = vi.hoisted(
  (): { value: MissionReadModelPayload | null } => ({ value: null }),
);

vi.mock("../hooks/useSessionRuntime", () => ({
  useSessionRuntime: () => ({ runtime: runtimeState.value, loading: false }),
}));

vi.mock("../utils/missionReadModel", () => ({
  useMissionReadModel: () => ({ model: readModelState.value, loading: false }),
}));

vi.mock("../i18n/useLocale", () => ({
  useLocale: () => ({ locale: "en", msg: {} }),
}));

vi.mock("./WorkToolPanel", () => ({ WorkToolPanel: () => null }));
vi.mock("./WorkPhaseChip", () => ({ WorkPhaseChip: () => null }));
vi.mock("./WorkPlanApprovalSection", () => ({
  WorkPlanApprovalSection: () => null,
}));

function runtimeWithPlanPhase(phase: string): RuntimeSnapshot {
  return {
    ok: true,
    session_id: "queue-session",
    mode: "mission",
    has_plan: true,
    work_phase: "review_needed",
    mission: { enabled: true, phase: "PLAN_GATE", paused: false },
    execute: { has_pending: false, has_dry_run_diff: false },
    gates: { execute_blocked: false, pending_agreement: false },
    inbox: {
      pending: false,
      pending_count: 0,
      pending_questions: 0,
      pending_builds: 0,
    },
    next_action: "review_plan",
    plan_workflow: { enabled: true, phase, notice: null, round: null },
  };
}

function readModelWithPlanPhase(phase: string): MissionReadModelPayload {
  return {
    session_id: "queue-session",
    migrated: true,
    source: "mission_journal",
    mission_id: "mission-1",
    goal: "Ship the queue",
    state: "PLAN_GATE",
    version: 1,
    plan_revision: 1,
    plan_hash: "plan-hash",
    approved_plan_hash: null,
    repair_attempt: 0,
    max_repair_attempts: 2,
    oracle_verdict: null,
    next_action: "review_plan",
    event_cursor: 1,
    operational_status: "RUNNING",
    open_execution_gates: [{ gate_id: "gate-plan", kind: "plan" }],
    legacy_phase: "CLARIFY",
    plan: {
      phase,
      hash: "plan-hash",
      approved_hash: null,
      pending_approval: false,
    },
  };
}

function eventStackProps(
  overrides: Partial<ComponentProps<typeof ComposerEventStack>> = {},
): ComponentProps<typeof ComposerEventStack> {
  return {
    sessionId: "queue-session",
    session: null,
    planMd: "# Current plan",
    planMeta: {
      lastUpdate: null,
      freshness: "unknown",
      triggerLabel: "—",
      timeLabel: "—",
      agentsLabel: "—",
      freshnessLabel: "—",
      reviewTurnLabel: null,
      turnRolesLabel: null,
      pendingAgreement: null,
      chatLineLabel: null,
    },
    synthesizing: false,
    running: false,
    runBusy: false,
    executeBusy: false,
    onSynthesizeNow: () => {},
    onPlanRefClick: () => {},
    onFocusTask: () => {},
    onFocusObjection: () => {},
    onSessionUpdated: () => {},
    roomTasks: null,
    cursorReady: false,
    planWorkflow: { enabled: true, phase: "CLARIFY" },
    inboxPendingCount: 0,
    inboxReloadKey: 0,
    currentPlanRevision: null,
    onInboxResolved: () => {},
    onInboxBuildStarted: () => {},
    onInboxRefClick: () => {},
    execPending: null,
    storedActions: [],
    onExecuteApprove: () => {},
    onExecuteReject: () => {},
    showExecuteQueue: false,
    consensusProposal: null,
    showConsensusGate: false,
    consensusGateBusy: false,
    onConsensusDryRun: () => {},
    onConsensusDismiss: () => {},
    onOpenDiff: () => {},
    onOpenFiles: () => {},
    onOpenFile: () => {},
    disabled: false,
    ...overrides,
  };
}

describe("ComposerEventStack lifecycle projection", () => {
  afterEach(() => {
    runtimeState.value = null;
    readModelState.value = null;
  });

  it("renders the runtime-approved work surface when the legacy workflow is stale", () => {
    runtimeState.value = runtimeWithPlanPhase("APPROVED");
    readModelState.value = null;

    const html = renderToStaticMarkup(
      <ComposerEventStack {...eventStackProps()} />,
    );

    expect(html).toContain('data-composer-lane="work"');
  });

  it("keeps the read-model phase ahead of a stale runtime projection", () => {
    runtimeState.value = runtimeWithPlanPhase("CLARIFY");
    readModelState.value = readModelWithPlanPhase("APPROVED");

    const html = renderToStaticMarkup(
      <ComposerEventStack {...eventStackProps()} />,
    );

    expect(html).toContain('data-composer-lane="work"');
  });

  it("uses the legacy workflow phase only when newer projections are unavailable", () => {
    const html = renderToStaticMarkup(
      <ComposerEventStack
        {...eventStackProps({
          planWorkflow: { enabled: true, phase: "APPROVED" },
        })}
      />,
    );

    expect(html).toContain('data-composer-lane="work"');
  });

  it("keeps a plan approval as the only active CTA while inbox asks remain queued", () => {
    readModelState.value = readModelWithPlanPhase("HUMAN_PENDING");

    const html = renderToStaticMarkup(
      <ComposerEventStack
        {...eventStackProps({
          inboxPendingCount: 2,
          planApproval: {
            enabled: true,
            canExecute: false,
            busy: false,
            error: null,
            onApprove: () => {},
            onReject: () => {},
          },
        })}
      />,
    );

    expect(html).toContain('data-composer-lane="plan_approval"');
    expect(html).toContain('data-active-decision-id="gate-plan"');
    expect(html).toContain("Then: Answer a question");
    expect(html.match(/composer-decision-queue__current/g)).toHaveLength(1);
    expect(html).not.toContain("composer-question-surface");
  });
});
