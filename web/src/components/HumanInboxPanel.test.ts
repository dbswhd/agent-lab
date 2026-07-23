import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { HumanInboxItem, MissionReadModelPayload } from "../api/client";
import { HumanInboxPanel, projectInboxDecisionQueue } from "./HumanInboxPanel";

const readModelState = vi.hoisted(
  (): { model: MissionReadModelPayload | null } => ({ model: null }),
);

vi.mock("../utils/missionReadModel", () => ({
  useMissionReadModel: () => ({ model: readModelState.model, loading: false }),
}));

vi.mock("../i18n/useLocale", () => ({
  useLocale: () => ({ locale: "en", msg: {} }),
}));

const firstQuestion: HumanInboxItem = {
  id: "question-first",
  kind: "question",
  status: "pending",
  prompt: "Choose the bounded approach",
};

const queuedQuestion: HumanInboxItem = {
  id: "question-queued",
  kind: "question",
  status: "pending",
  prompt: "Confirm the follow-up",
};

function readModelWithQuestions(): MissionReadModelPayload {
  return {
    session_id: "queue-session",
    migrated: true,
    source: "mission_journal",
    mission_id: "mission-1",
    goal: "Ship the queue",
    state: "AWAITING_HUMAN",
    version: 1,
    plan_revision: 1,
    plan_hash: "plan-hash",
    approved_plan_hash: null,
    repair_attempt: 0,
    max_repair_attempts: 2,
    oracle_verdict: null,
    next_action: "answer_human",
    event_cursor: 1,
    operational_status: "WAITING_FOR_HUMAN",
    open_execution_gates: [
      { gate_id: firstQuestion.id, kind: "question" },
      { gate_id: queuedQuestion.id, kind: "question" },
    ],
    legacy_phase: "CLARIFY",
    inbox_summary: {
      pending_count: 2,
      pending_questions: 2,
      pending_builds: 0,
    },
    inbox_items: [firstQuestion, queuedQuestion],
  };
}

describe("projectInboxDecisionQueue", () => {
  afterEach(() => {
    readModelState.model = null;
  });

  it("keeps only the canonical first pending item active and queues the rest", () => {
    const projection = projectInboxDecisionQueue([
      firstQuestion,
      queuedQuestion,
    ]);

    expect(projection.active?.id).toBe("question-first");
    expect(projection.queuedCount).toBe(1);
  });

  it("renders one active Submit CTA and a queued hint for two pending questions", () => {
    readModelState.model = readModelWithQuestions();

    const html = renderToStaticMarkup(
      createElement(HumanInboxPanel, { sessionId: "queue-session" }),
    );

    expect(html).toContain("Choose the bounded approach");
    expect(html).not.toContain("Confirm the follow-up");
    expect(html).toContain("1 queued");
    expect(html.match(/>Submit</g)).toHaveLength(1);
  });
});
