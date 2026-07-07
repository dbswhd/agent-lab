import { describe, expect, it } from "vitest";
import {
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
});
