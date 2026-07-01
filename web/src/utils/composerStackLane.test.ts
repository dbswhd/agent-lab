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
