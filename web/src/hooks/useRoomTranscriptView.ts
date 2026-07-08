import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RoomTasksPayload, SessionDetail } from "../api/client";
import type { WorkFocusTarget } from "../components/WorkToolPanel";
import { useMessagesScroll } from "./useMessagesScroll";
import type { LiveMsg } from "../run/runSessionRegistry";
import { derivePendingReplyAgents } from "../run/runningAgents";
import { effectiveTurnAgents } from "../utils/agentMentions";
import { latestDraftMessageIdsByAgent } from "../utils/draftResponsePrefs";
import { stripAgentReplyBody } from "../utils/agentResponseCard";
import {
  findChatLineIndexForTask,
  messageMentionsTask,
} from "../utils/taskBarCopy";
import {
  getShowPeerChannel,
  setShowPeerChannel,
  TRANSCRIPT_VIEW_PREFS_EVENT,
} from "../utils/transcriptViewPrefs";
import { isReplyWaitRole } from "../utils/transcript";
import {
  resolveTurnSend,
  type ComposerTurnProfile,
} from "../utils/turnProfile";

export type UseRoomTranscriptViewOptions = {
  sessionId: string | null;
  sessionRun: SessionDetail["run"] | undefined;
  sessionChat: SessionDetail["chat"] | undefined;
  messages: LiveMsg[];
  roomTasks: RoomTasksPayload | null;
  running: boolean;
  localSseRun: boolean;
  topologyActive: { agent: string; round: number } | null;
  topologyDone: Set<string>;
  turnProfile: ComposerTurnProfile;
  selected: string[];
  openTranscriptTab: () => void;
  focusWorkStack: (target: WorkFocusTarget) => void;
};

/** Transcript filtering, scroll, highlight, and pending-reply affordances (F9 slice 4c). */
export function useRoomTranscriptView({
  sessionId,
  sessionRun,
  sessionChat,
  messages,
  roomTasks,
  running,
  localSseRun,
  topologyActive,
  topologyDone,
  turnProfile,
  selected,
  openTranscriptTab,
  focusWorkStack,
}: UseRoomTranscriptViewOptions) {
  const [showPeerChannel, setShowPeerChannelState] =
    useState(getShowPeerChannel);
  const [highlightChatLine, setHighlightChatLine] = useState<number | null>(
    null,
  );
  const highlightTimerRef = useRef<number | null>(null);

  useEffect(() => {
    const onPrefs = () => {
      setShowPeerChannelState(getShowPeerChannel());
    };
    window.addEventListener(TRANSCRIPT_VIEW_PREFS_EVENT, onPrefs);
    return () =>
      window.removeEventListener(TRANSCRIPT_VIEW_PREFS_EVENT, onPrefs);
  }, []);

  const onPeerChannelChange = useCallback((on: boolean) => {
    setShowPeerChannel(on);
    setShowPeerChannelState(on);
  }, []);

  const visibleMessages = useMemo(() => {
    const rows = messages.filter((m) => !m.humanSynthesis);
    if (showPeerChannel) return rows;
    return rows.filter((m) => !m.peerChannel);
  }, [messages, showPeerChannel]);

  const openDraftMessageIds = useMemo(
    () =>
      latestDraftMessageIdsByAgent(
        visibleMessages,
        (role) => isReplyWaitRole(role as LiveMsg["role"]),
        (body) => Boolean(stripAgentReplyBody(body ?? "").trim()),
      ),
    [visibleMessages],
  );

  const advisorRationales = useMemo(() => {
    const turns = sessionRun?.turns;
    if (!Array.isArray(turns)) return [] as (string | null)[];
    return (turns as Array<Record<string, unknown>>).map((t) => {
      const tm = t?.turn_metrics;
      if (!tm || typeof tm !== "object") return null;
      const rat = (tm as Record<string, unknown>).advisor_rationale;
      return typeof rat === "string" && rat ? rat : null;
    });
  }, [sessionRun?.turns]);

  const transcriptActive = true;
  const typingAgents = messages.filter(
    (m) => m.typing && isReplyWaitRole(m.role),
  );
  const pendingReplyCount =
    running && typingAgents.length === 0
      ? resolveTurnSend(turnProfile, selected).agents.length
      : 0;

  const { scrollRef, scrollElRef, showJumpButton, scrollToBottom } =
    useMessagesScroll(
      [messages, running, pendingReplyCount, selected.join(",")],
      transcriptActive,
      `${sessionId ?? "new"}:chat`,
    );

  const handlePlanRefClick = useCallback(
    (lineNumber: number) => {
      openTranscriptTab();
      setHighlightChatLine(lineNumber - 1);
    },
    [openTranscriptTab],
  );

  useEffect(() => {
    if (highlightChatLine == null) return;
    const root = scrollElRef.current;
    const el = root?.querySelector(
      `[data-chat-line="${highlightChatLine}"]`,
    ) as HTMLElement | null;
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (highlightTimerRef.current != null) {
      window.clearTimeout(highlightTimerRef.current);
    }
    highlightTimerRef.current = window.setTimeout(() => {
      setHighlightChatLine(null);
      highlightTimerRef.current = null;
    }, 2600);
    return () => {
      if (highlightTimerRef.current != null) {
        window.clearTimeout(highlightTimerRef.current);
      }
    };
  }, [highlightChatLine, messages, scrollElRef]);

  const turnResolved = resolveTurnSend(turnProfile, selected);
  const turnUserBody = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const row = messages[i];
      if (row?.role === "you" && row.sent) return row.body ?? "";
    }
    return "";
  }, [messages]);

  const turnTargetAgents = useMemo(
    () => effectiveTurnAgents(turnUserBody, turnResolved.agents),
    [turnUserBody, turnResolved.agents],
  );

  const pendingReplyAgents = useMemo(
    () =>
      derivePendingReplyAgents(messages, {
        running: running || localSseRun,
        expectedAgents: turnTargetAgents,
        topologyActive,
        topologyDone,
      }),
    [
      messages,
      running,
      localSseRun,
      turnTargetAgents,
      topologyActive,
      topologyDone,
    ],
  );

  const focusTask = useCallback(
    (taskId: string) => {
      openTranscriptTab();
      focusWorkStack("plan");
      const task =
        roomTasks?.tasks?.find((t) => t.id === taskId) ??
        roomTasks?.claimable?.find((t) => t.id === taskId);
      const chatLines = sessionChat ?? [];
      let lineIdx: number | null = null;
      if (task) {
        lineIdx = findChatLineIndexForTask(chatLines, task);
      }
      if (lineIdx == null && task) {
        for (let i = messages.length - 1; i >= 0; i -= 1) {
          const m = messages[i];
          if (m.chatLineIndex == null) continue;
          if (messageMentionsTask(m.body ?? "", task)) {
            lineIdx = m.chatLineIndex;
            break;
          }
        }
      }
      if (lineIdx != null) {
        setHighlightChatLine(lineIdx);
      }
      window.setTimeout(() => {
        document
          .querySelector(`[data-task-id="${taskId}"]`)
          ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 60);
    },
    [focusWorkStack, messages, openTranscriptTab, roomTasks, sessionChat],
  );

  return {
    showPeerChannel,
    onPeerChannelChange,
    visibleMessages,
    openDraftMessageIds,
    advisorRationales,
    transcriptActive,
    scrollRef,
    showJumpButton,
    scrollToBottom,
    highlightChatLine,
    handlePlanRefClick,
    focusTask,
    pendingReplyAgents,
  };
}
