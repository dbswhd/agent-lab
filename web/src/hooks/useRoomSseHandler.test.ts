import { beforeEach, describe, expect, it } from "vitest";
import type { MutableRefObject } from "react";
import { messages } from "../i18n/messages";
import { deriveRunningAgentSlots } from "../run/runningAgents";
import {
  getSessionRunSnapshot,
  updateSessionRun,
  type LiveMsg,
} from "../run/runSessionRegistry";
import {
  createRoomRunEventHandler,
  type RoomRunScope,
  type RoomRunSseDeps,
} from "./useRoomSseHandler";

const sid = "test-room-sse-activity";

function resetSession(): void {
  updateSessionRun(sid, {
    messages: [],
    turnMessages: [],
    running: true,
    runBusy: true,
    synthesizing: false,
    localSseRun: true,
    runStartedAt: null,
    topologyActive: null,
    topologyDone: new Set(),
    backgroundRun: null,
  });
}

function makeScope(): RoomRunScope {
  return {
    runKey: sid,
    activeSessionId: sid,
    userStopped: false,
    runFailed: false,
  };
}

function makeDeps(): RoomRunSseDeps {
  const activeSessionIdRef: MutableRefObject<string | null> = { current: sid };
  const navigatedToSessionRef: MutableRefObject<boolean> = { current: false };
  const pendingMissionTemplateRef: MutableRefObject<string | null> = {
    current: null,
  };
  const setInboxReloadKey: RoomRunSseDeps["setInboxReloadKey"] = () => {};
  const setConsensusProposal: RoomRunSseDeps["setConsensusProposal"] = () => {};

  return {
    sessionId: sid,
    profile: "loop",
    selected: ["codex"],
    localeMsg: messages("ko"),
    activeSessionIdRef,
    navigatedToSessionRef,
    pendingMissionTemplateRef,
    onSessionChange: () => {},
    setLiveRunSessionKey: () => {},
    persistPendingSessionRoomModels: () => {},
    openPlanTab: () => {},
    setRecoveryFailure: () => {},
    setRunLockStuck: () => {},
    setClarifierQuestions: () => {},
    setClarifierInterview: () => {},
    setDiscussPaused: () => {},
    setInboxReloadKey,
    setWorkHookAlert: () => {},
    setConsensusProposal,
    notifyConsensusSync: () => {},
    notifyConsensusFailure: () => {},
    pushMacNotification: () => {},
    refreshSessionMeta: () => {},
    refreshInboxPending: () => {},
    openHumanInbox: () => {},
    openWorkTab: () => {},
  };
}

function codexMessage(): LiveMsg | undefined {
  return getSessionRunSnapshot(sid).messages.find((m) => m.role === "codex");
}

function firstTurnItemText(message: LiveMsg | undefined): string | undefined {
  const item = message?.turnItems?.[0];
  if (!item || item.kind === "tool") return undefined;
  return item.text;
}

describe("createRoomRunEventHandler activity lifecycle", () => {
  beforeEach(resetSession);

  it("keeps activity when agent_activity arrives before agent_start", () => {
    const handler = createRoomRunEventHandler(makeScope(), makeDeps());

    handler({
      type: "agent_activity",
      agent: "codex",
      round: 1,
      text: "Reading repo",
    });

    const beforeStart = codexMessage();
    expect(beforeStart?.typing).toBe(true);
    expect(firstTurnItemText(beforeStart)).toBe("Reading repo");
    expect(
      deriveRunningAgentSlots(getSessionRunSnapshot(sid).messages, {
        running: true,
        expectedAgents: ["codex"],
      })[0]?.activity,
    ).toBe("Reading repo");

    handler({ type: "agent_start", agent: "codex", round: 1 });

    const afterStart = codexMessage();
    expect(afterStart?.typing).toBe(true);
    expect(firstTurnItemText(afterStart)).toBe("Reading repo");
  });

  it("clears the spinner on complete without deleting activity-only rows", () => {
    const handler = createRoomRunEventHandler(makeScope(), makeDeps());

    handler({
      type: "agent_activity",
      agent: "codex",
      round: 1,
      text: "Reading repo",
    });
    handler({ type: "complete", session_id: sid });

    const snap = getSessionRunSnapshot(sid);
    const msg = snap.messages.find((m) => m.role === "codex");
    expect(snap.running).toBe(false);
    expect(snap.localSseRun).toBe(false);
    expect(msg?.typing).toBe(false);
    expect(firstTurnItemText(msg)).toBe("Reading repo");
  });
});
