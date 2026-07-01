import { describe, expect, it } from "vitest";
import {
  hasPlanWorkflowClarifySurface,
  isComposerPlanWorkflowNotice,
  pendingClarifierQuestionCount,
  shouldShowPlanWorkflowComposerNotice,
} from "./planWorkflowView";

describe("planWorkflowView clarify surfaces", () => {
  it("counts unanswered clarifier prompts", () => {
    expect(
      pendingClarifierQuestionCount({
        questions: [
          { id: "scope", prompt: "Scope?" },
          { id: "done", prompt: "Done" },
        ],
        answers: { done: "Shipped" },
      }),
    ).toBe(1);
    expect(
      pendingClarifierQuestionCount({
        pending_count: 2,
        questions: [{ prompt: "ignored when pending_count set" }],
      }),
    ).toBe(2);
  });

  it("hides idle CLARIFY composer notice when nothing is pending", () => {
    expect(
      shouldShowPlanWorkflowComposerNotice({
        showBanner: true,
        showHint: false,
        phase: "CLARIFY",
        inboxPendingCount: 0,
        notice: undefined,
      }),
    ).toBe(false);
  });

  it("shows CLARIFY surface when inbox pending", () => {
    expect(
      hasPlanWorkflowClarifySurface({
        phase: "CLARIFY",
        inboxPendingCount: 2,
      }),
    ).toBe(true);
    expect(
      hasPlanWorkflowClarifySurface({
        phase: "INTAKE",
        inboxPendingCount: 0,
      }),
    ).toBe(false);
  });

  it("ignores internal clarity_pending notice when inbox is empty", () => {
    expect(isComposerPlanWorkflowNotice("clarity_pending")).toBe(false);
    expect(
      shouldShowPlanWorkflowComposerNotice({
        showBanner: true,
        showHint: false,
        phase: "CLARIFY",
        inboxPendingCount: 0,
        notice: "clarity_pending",
      }),
    ).toBe(false);
  });
});
