import { describe, expect, it } from "vitest";
import {
  pendingComposerDecisionCount,
  pendingComposerStackLanes,
  resolveActiveComposerStackLane,
} from "./composerStackLane";

const base = {
  inboxPendingCount: 0,
  planApprovalEnabled: false,
  showClarifyNotice: false,
  hasPlan: true,
  showExecuteQueue: false,
  execPending: false,
  showConsensusGate: false,
  consensusProposal: null,
  showWorkSurface: true,
};

describe("composerStackLane — idea lane (RI-12)", () => {
  it("does not open the work lane just because a plan exists", () => {
    // On the idea lane a written plan is an export, not something to run.
    const input = { ...base, ideaLane: true };
    expect(pendingComposerStackLanes(input)).toEqual([]);
    expect(resolveActiveComposerStackLane(input)).toBeNull();
  });

  it("still opens it for a real pending execution", () => {
    const input = { ...base, ideaLane: true, execPending: true };
    expect(pendingComposerStackLanes(input)).toContain("work");
  });

  it("leaves an execute-lane session alone", () => {
    expect(pendingComposerStackLanes(base)).toEqual(["work"]);
    expect(pendingComposerStackLanes({ ...base, ideaLane: false })).toEqual([
      "work",
    ]);
  });

  it("keeps the other lanes reachable on the idea lane", () => {
    expect(
      pendingComposerStackLanes({
        ...base,
        ideaLane: true,
        inboxPendingCount: 1,
      }),
    ).toEqual(["inbox"]);
  });
});

describe("composerStackLane", () => {
  it("prioritizes inbox over work surface", () => {
    const input = { ...base, inboxPendingCount: 1, showWorkSurface: true };
    expect(resolveActiveComposerStackLane(input)).toBe("inbox");
    expect(pendingComposerStackLanes(input)).toEqual(["inbox", "work"]);
  });

  it("prioritizes workflow approvals over generic inbox asks", () => {
    const input = {
      ...base,
      inboxPendingCount: 2,
      planApprovalEnabled: true,
      showExecuteQueue: true,
      execPending: true,
      showConsensusGate: true,
      consensusProposal: {},
    };
    expect(resolveActiveComposerStackLane(input)).toBe("plan_approval");
    expect(pendingComposerStackLanes(input)).toEqual([
      "plan_approval",
      "execute_queue",
      "consensus",
      "inbox",
    ]);
  });

  it("shows plan approval before execute queue", () => {
    const input = {
      ...base,
      planApprovalEnabled: true,
      showExecuteQueue: true,
      execPending: true,
      showWorkSurface: false,
    };
    expect(resolveActiveComposerStackLane(input)).toBe("plan_approval");
  });

  it("shows execute queue before work", () => {
    const input = {
      ...base,
      showExecuteQueue: true,
      execPending: true,
    };
    expect(resolveActiveComposerStackLane(input)).toBe("execute_queue");
  });

  it("shows consensus before inbox and work when dry-run review is pending", () => {
    const input = {
      ...base,
      inboxPendingCount: 1,
      showConsensusGate: true,
      consensusProposal: {},
    };
    expect(resolveActiveComposerStackLane(input)).toBe("consensus");
    expect(pendingComposerStackLanes(input)).toEqual([
      "consensus",
      "inbox",
      "work",
    ]);
  });

  it("shows work after inbox clears", () => {
    const input = { ...base, inboxPendingCount: 0, showWorkSurface: true };
    expect(resolveActiveComposerStackLane(input)).toBe("work");
  });

  it("returns null when nothing pending", () => {
    expect(
      resolveActiveComposerStackLane({ ...base, showWorkSurface: false }),
    ).toBeNull();
  });

  it("counts Human Inbox items rather than treating the inbox as one decision", () => {
    expect(
      pendingComposerDecisionCount({
        ...base,
        inboxPendingCount: 3,
        planApprovalEnabled: true,
      }),
    ).toBe(4);
  });
});
