import type { useLocale } from "../i18n/useLocale";
import type { PlanActionItem } from "../api/client";
import type {
  Dispatch,
  MutableRefObject,
  SetStateAction,
} from "react";
import type { RecoveryFailure } from "../utils/recoveryItems";
import {
  applySessionTemplate,
  fetchSessionInbox,
  releaseRoomRunLock,
} from "../api/client";
import type { ConsensusDryRunProposal } from "../components/ConsensusDryRunGateBar";
import { patchTurnMessages } from "../run/runSessionSsePatch";
import {
  PENDING_KEY,
  finalizeCancelledTyping,
  findAgentTurnMessage,
  migratePendingSessionRun,
  updateSessionRun,
  type LiveMsg,
} from "../run/runSessionRegistry";
import {
  agreementPlanSyncedLabel,
  agreementPlanSyncFailedLabel,
} from "../utils/consensusAgreement";
import type { ComposeMode } from "../utils/composeMode";
import {
  formatDispatchActivityLine,
  formatEnvelopeActivityLine,
  formatHookActivityLine,
  isExecutionRelevantHook,
} from "../utils/hookActivity";
import { dedupeStreamAppend, mergeAgentReplyBody } from "../utils/liveRoomLog";
import { planWorkflowPhaseTranscriptLine } from "../utils/planWorkflowView";
import { notifyDesktop } from "../utils/desktopNotify";
import { dispatchNotification } from "../utils/pushNotification";
import {
  consensusIncompleteLabel,
  roundDividerLabel,
} from "../utils/roundTopology";
import { agentLabel, isReplyWaitRole } from "../utils/transcript";
import { reduceTurnItems } from "../utils/turnItems";
import {
  resolveTurnSend,
  type ComposerTurnProfile,
} from "../utils/turnProfile";

/** Mutable per-run state shared between SSE events and executeSend finally block. */
export type RoomRunScope = {
  runKey: string;
  activeSessionId: string | null;
  userStopped: boolean;
  runFailed: boolean;
  lastSendReceipt?: string;
};

export type RoomRunSseDeps = {
  sessionId: string | null;
  profile: ComposerTurnProfile;
  selected: string[];
  mode: ComposeMode;
  localeMsg: ReturnType<typeof useLocale>["msg"];
  activeSessionIdRef: MutableRefObject<string | null>;
  navigatedToSessionRef: MutableRefObject<boolean>;
  pendingMissionTemplateRef: MutableRefObject<string | null>;
  onSessionBind?: (sessionId: string) => void;
  onSessionChange: (sessionId: string) => void;
  onSessionMetaRefresh?: (sessionId: string) => void | Promise<void>;
  onBootstrapMissionTemplateApplied?: () => void;
  setLiveRunSessionKey: (id: string) => void;
  persistPendingSessionRoomModels: (sessionId: string) => void | Promise<void>;
  openPlanTab: () => void;
  setRecoveryFailure: (value: RecoveryFailure | null) => void;
  setRunLockStuck: (value: boolean) => void;
  setClarifierQuestions: (value: string[] | null) => void;
  setClarifierInterview: (value: ClarifierInterview | null) => void;
  setDiscussPaused: (value: boolean) => void;
  setInboxReloadKey: Dispatch<SetStateAction<number>>;
  setWorkHookAlert: (value: WorkHookAlert | null) => void;
  setConsensusProposal: Dispatch<SetStateAction<ConsensusDryRunProposal | null>>;
  notifyConsensusSync: (proposal: ConsensusDryRunProposal) => void;
  notifyConsensusFailure: (excerpt?: string, message?: string) => void;
  pushMacNotification: (payload: MacNotificationPayload) => void;
  refreshSessionMeta: () => void;
  refreshInboxPending: () => void;
  openHumanInbox: () => void;
  openWorkTab: () => void;
};

type WorkHookAlert = {
  event: string;
  body: string;
  blocked: boolean;
};

type ClarifierInterview = {
  questions?: { id?: string; category?: string; prompt?: string }[];
  plan_mode?: boolean;
};

type MacNotificationPayload = {
  title: string;
  body?: string;
};

function parseConsensusDryRunProposal(
  ev: Record<string, unknown>,
): ConsensusDryRunProposal {
  const recommended = ev.recommended as PlanActionItem | null | undefined;
  return {
    excerpt: typeof ev.excerpt === "string" ? ev.excerpt : undefined,
    summary: typeof ev.summary === "string" ? ev.summary : undefined,
    notice: typeof ev.notice === "string" ? ev.notice : undefined,
    recommended: recommended ?? null,
    has_executable: ev.has_executable === true,
    action_key:
      typeof ev.action_key === "string"
        ? ev.action_key
        : (recommended?.action_key ?? null),
  };
}

/** Room SSE event handler for `runRoom()` — session bind, patchTurnMessages, notifications. */
export function createRoomRunEventHandler(
  scope: RoomRunScope,
  deps: RoomRunSseDeps,
): (ev: Record<string, unknown>) => void {
  const {
    sessionId,
    profile,
    selected,
    activeSessionIdRef,
    navigatedToSessionRef,
    pendingMissionTemplateRef,
    onSessionBind,
    onSessionChange,
    onSessionMetaRefresh,
    onBootstrapMissionTemplateApplied,
    setLiveRunSessionKey,
    persistPendingSessionRoomModels,
    openPlanTab,
    setRecoveryFailure,
    setRunLockStuck,
    setClarifierQuestions,
    setClarifierInterview,
    setDiscussPaused,
    setInboxReloadKey,
    setWorkHookAlert,
    setConsensusProposal,
    notifyConsensusSync,
    notifyConsensusFailure,
    pushMacNotification,
    refreshSessionMeta,
    refreshInboxPending,
    openHumanInbox,
    openWorkTab,
    localeMsg,
  } = deps;

  return (ev) => {
    const t = String(ev.type);
    if (t === "start" && ev.session_id) {
      const boundSessionId = String(ev.session_id);
      activeSessionIdRef.current = boundSessionId;
      scope.activeSessionId = boundSessionId;
      if (scope.runKey === PENDING_KEY || scope.runKey !== boundSessionId) {
        migratePendingSessionRun(boundSessionId);
        scope.runKey = boundSessionId;
      }
      setLiveRunSessionKey(boundSessionId);
      if (!sessionId && !navigatedToSessionRef.current) {
        navigatedToSessionRef.current = true;
        if (onSessionBind) {
          onSessionBind(boundSessionId);
        } else {
          void onSessionChange(boundSessionId);
        }
      }
      if (!sessionId && onSessionMetaRefresh) {
        void onSessionMetaRefresh(activeSessionIdRef.current);
      }
      void persistPendingSessionRoomModels(boundSessionId);
      const pendingTemplateId = pendingMissionTemplateRef.current;
      if (!sessionId && pendingTemplateId && boundSessionId) {
        pendingMissionTemplateRef.current = null;
        void applySessionTemplate(boundSessionId, pendingTemplateId)
          .then((res) => {
            onBootstrapMissionTemplateApplied?.();
            if (onSessionMetaRefresh) {
              void onSessionMetaRefresh(boundSessionId);
            }
            if (res.fast_path) {
              openPlanTab();
            }
          })
          .catch(() => {
            /* template apply is best-effort; room run continues */
          });
      }
      if (Array.isArray(ev.attachments) && ev.attachments.length) {
        const saved = ev.attachments as string[];
        patchTurnMessages(scope.runKey, (m) => {
          for (let i = m.length - 1; i >= 0; i--) {
            const row = m[i];
            if (row.role === "you" && row.sent) {
              const next = [...m];
              next[i] = { ...row, attachments: saved };
              return next;
            }
          }
          return m;
        });
      }
    }
    if (t === "run_cancelled") {
      scope.userStopped = true;
      finalizeCancelledTyping(scope.runKey);
    }
    if (t === "agent_round_start" && Number(ev.round) > 1) {
      const round = Number(ev.round);
      updateSessionRun(scope.runKey, { topologyActive: null });
      patchTurnMessages(scope.runKey, (m) => {
        const rid = `round-divider-live-${round}`;
        return [
          ...m.filter((x) => x.id !== rid),
          {
            id: rid,
            role: "system",
            label: "",
            body: roundDividerLabel(
              round,
              Boolean(ev.review_mode),
              resolveTurnSend(profile, selected).consensusMode,
              Boolean(ev.debate),
            ),
            roundDivider: round,
          },
        ];
      });
    }
    if (t === "consensus_plan_synced" || t === "verified_plan_synced") {
      const excerpt = typeof ev.excerpt === "string" ? ev.excerpt : undefined;
      const summary = typeof ev.summary === "string" ? ev.summary : undefined;
      const notice =
        typeof ev.notice === "string"
          ? ev.notice
          : agreementPlanSyncedLabel(excerpt, summary);
      patchTurnMessages(scope.runKey, (m) => [
        ...m,
        {
          id: `consensus-sync-${Date.now()}`,
          role: "system",
          label: "",
          body: notice,
        },
      ]);
      refreshSessionMeta();
      setInboxReloadKey((k) => k + 1);
      const partialProposal = { excerpt, summary, notice };
      setConsensusProposal((prev) => ({
        ...partialProposal,
        recommended: prev?.recommended,
        has_executable: prev?.has_executable ?? false,
        action_key: prev?.action_key,
      }));
      notifyConsensusSync(partialProposal);
    }
    if (t === "consensus_dry_run_proposal") {
      const proposal = parseConsensusDryRunProposal(ev);
      refreshSessionMeta();
      setConsensusProposal(proposal);
      notifyConsensusSync(proposal);
    }
    if (
      t === "consensus_plan_sync_failed" ||
      t === "verified_plan_sync_failed"
    ) {
      const excerpt = typeof ev.excerpt === "string" ? ev.excerpt : undefined;
      const message = typeof ev.message === "string" ? ev.message : undefined;
      patchTurnMessages(scope.runKey, (m) => [
        ...m,
        {
          id: `consensus-sync-fail-${Date.now()}`,
          role: "system",
          label: "",
          body: agreementPlanSyncFailedLabel(excerpt, message),
        },
      ]);
      notifyConsensusFailure(excerpt, message);
    }
    if (t === "clarifier_prompt" && Array.isArray(ev.questions)) {
      setClarifierQuestions(
        (ev.questions as unknown[]).map((q) => String(q)).filter(Boolean),
      );
      if (ev.interview && typeof ev.interview === "object") {
        setClarifierInterview(ev.interview as ClarifierInterview);
      }
    }
    if (t === "consensus_incomplete") {
      patchTurnMessages(scope.runKey, (m) => [
        ...m,
        {
          id: `consensus-inc-${Date.now()}`,
          role: "system",
          label: "",
          body: consensusIncompleteLabel(
            typeof ev.message === "string" ? ev.message : undefined,
          ),
        },
      ]);
    }
    if (t === "agent_start" && ev.agent) {
      const aid = String(ev.agent);
      const round = Number(ev.round ?? 1);
      updateSessionRun(scope.runKey, {
        topologyActive: { agent: aid, round },
      });
      patchTurnMessages(scope.runKey, (m) => [
        ...m.filter((x) => x.id !== `typing-${aid}-r${round}`),
        {
          id: `typing-${aid}-r${round}`,
          role: aid as LiveMsg["role"],
          label: agentLabel(aid),
          body: "",
          typing: true,
          parallelRound: round,
          turnItems: [],
        },
      ]);
    }
    if (t === "agent_activity" && ev.agent && ev.text) {
      const aid = String(ev.agent);
      const round = Number(ev.round ?? 1);
      const tid = `typing-${aid}-r${round}`;
      patchTurnMessages(scope.runKey, (m) =>
        m.map((msg) => {
          if (msg.id !== tid) return msg;
          return {
            ...msg,
            turnItems: reduceTurnItems(msg.turnItems, ev),
          };
        }),
      );
    }
    if (t === "agent_token" && ev.agent && typeof ev.text === "string") {
      const aid = String(ev.agent);
      const round = Number(ev.round ?? 1);
      const tid = `typing-${aid}-r${round}`;
      const chunk = String(ev.text);
      patchTurnMessages(scope.runKey, (m) =>
        m.map((msg) => {
          if (msg.id !== tid) return msg;
          return {
            ...msg,
            body: dedupeStreamAppend(msg.body ?? "", chunk),
          };
        }),
      );
    }
    if (t === "tool_start" && ev.agent) {
      const toolName = String(ev.tool ?? "").toLowerCase();
      if (
        toolName.includes("ask_human") ||
        toolName.includes("propose_build")
      ) {
        setInboxReloadKey((k) => k + 1);
        void refreshInboxPending();
        openHumanInbox();
      }
      const aid = String(ev.agent);
      const round = Number(ev.round ?? 1);
      const tid = `typing-${aid}-r${round}`;
      patchTurnMessages(scope.runKey, (m) =>
        m.map((msg) => {
          if (msg.id !== tid) return msg;
          return {
            ...msg,
            turnItems: reduceTurnItems(msg.turnItems, ev),
          };
        }),
      );
    }
    if (t === "tool_output" && ev.agent) {
      const aid = String(ev.agent);
      const round = Number(ev.round ?? 1);
      const tid = `typing-${aid}-r${round}`;
      const chunk = String(ev.chunk ?? "");
      if (!chunk) return;
      patchTurnMessages(scope.runKey, (m) =>
        m.map((msg) => {
          if (msg.id !== tid) return msg;
          return {
            ...msg,
            turnItems: reduceTurnItems(msg.turnItems, ev),
          };
        }),
      );
    }
    if (t === "tool_done" && ev.agent) {
      const aid = String(ev.agent);
      const round = Number(ev.round ?? 1);
      const tid = `typing-${aid}-r${round}`;
      patchTurnMessages(scope.runKey, (m) =>
        m.map((msg) => {
          if (msg.id !== tid) return msg;
          return {
            ...msg,
            turnItems: reduceTurnItems(msg.turnItems, ev),
          };
        }),
      );
    }
    if (t === "agent_done" && ev.agent) {
      const aid = String(ev.agent);
      const round = Number(ev.round ?? 1);
      const envelopeParseError = ev.envelope_parse_error === true;
      const envelope = ev.envelope as LiveMsg["envelope"];
      const envelopeLine = formatEnvelopeActivityLine(round, {
        hasAct: Boolean(envelope?.act),
        parseError: envelopeParseError,
      });
      if (envelopeLine) {
        dispatchNotification(
          {
            tier: "P2",
            title: `Envelope · ${aid}`,
            body: envelopeLine,
            sessionId: scope.activeSessionId ?? undefined,
            kind: "envelope_warn",
            entityId: `${aid}:r${round}`,
          },
          pushMacNotification,
          notifyDesktop,
        );
      }
      updateSessionRun(scope.runKey, (snap) => {
        const n = new Set(snap.topologyDone);
        n.add(`${aid}:${round}`);
        const stillTyping = snap.turnMessages.filter(
          (m) => m.typing && isReplyWaitRole(m.role),
        );
        const next =
          stillTyping.length > 0
            ? {
                agent: String(stillTyping[0].role),
                round: stillTyping[0].parallelRound ?? round,
              }
            : null;
        return { topologyActive: next, topologyDone: n };
      });
      patchTurnMessages(scope.runKey, (m) => {
        const typing = findAgentTurnMessage(m, aid, round);
        const tid = typing?.id ?? `typing-${aid}-r${round}`;
        const streamed = typing?.body ?? "";
        const body = mergeAgentReplyBody(
          streamed,
          typeof ev.content === "string" ? ev.content : "",
        );
        return [
          ...m.filter((x) => x.id !== tid),
          {
            id: `msg-${aid}-r${round}-${Date.now()}`,
            role: aid as LiveMsg["role"],
            label: agentLabel(aid),
            body,
            parallelRound: round,
            envelope,
            envelopeParseError,
            turnItems: reduceTurnItems(typing?.turnItems, ev),
          },
        ];
      });
    }
    if (t === "agent_error" && ev.agent) {
      const aid = String(ev.agent);
      const round = Number(ev.round ?? 1);
      const nonParticipation = ev.non_participation === true;
      const note = typeof ev.note === "string" ? ev.note : "";
      if (!nonParticipation) {
        setRecoveryFailure({
          source: "agent",
          kind: "partial_turn",
          message:
            typeof ev.message === "string"
              ? ev.message
              : `${agentLabel(aid)} 응답 실패`,
          affectedAgentIds: [aid],
        });
      }
      patchTurnMessages(scope.runKey, (m) => {
        const typing = findAgentTurnMessage(m, aid, round);
        const tid = typing?.id ?? `typing-${aid}-r${round}`;
        const streamedBody = typing?.body ?? "";
        const err = typeof ev.message === "string" ? ev.message : "";
        const resolvedBody =
          nonParticipation && note
            ? note
            : streamedBody.trim() && err
              ? `${streamedBody}\n\n—\n[${agentLabel(aid)}] ${err}`
              : err
                ? `[${agentLabel(aid)}] ${err}`
                : streamedBody || "agent error";
        if (typing && streamedBody.trim()) {
          return m.map((msg) =>
            msg.id === tid
              ? {
                  ...msg,
                  id: `err-${aid}-r${round}-${Date.now()}`,
                  role: "system" as const,
                  label: nonParticipation ? "알림" : agentLabel(aid),
                  body: resolvedBody,
                  typing: false,
                }
              : msg,
          );
        }
        return [
          ...m.filter((x) => x.id !== tid),
          {
            id: `err-${aid}-r${round}-${Date.now()}`,
            role: "system",
            label: nonParticipation ? "알림" : "시스템",
            body: resolvedBody,
          },
        ];
      });
    }
    if (
      (t === "dispatch_start" || t === "dispatch_done") &&
      ev.dispatch_id
    ) {
      const dispatchLine = formatDispatchActivityLine(
        ev as Record<string, unknown>,
      );
      patchTurnMessages(scope.runKey, (m) => [
        ...m,
        {
          id: `${t}-${String(ev.dispatch_id)}-${Date.now()}`,
          role: "system",
          label: "dispatch",
          body: dispatchLine,
        },
      ]);
    }
    if (t === "hook_event" && ev.event) {
      const sid = scope.activeSessionId ?? undefined;
      const agentName = ev.agent ? agentLabel(String(ev.agent)) : "";
      const eventName = String(ev.event);
      const blocked = ev.blocked === true;
      const feedback =
        typeof ev.feedback === "string" ? ev.feedback.trim() : "";
      const subReason =
        typeof ev.sub_reason === "string" ? ev.sub_reason : "";
      const round = Number(ev.round ?? 1);
      const aid = ev.agent ? String(ev.agent) : "";
      if (aid) {
        const tid = `typing-${aid}-r${round}`;
        const hookLine = formatHookActivityLine({
          event: eventName,
          blocked,
          feedback,
          sub_reason: subReason,
        });
        patchTurnMessages(scope.runKey, (m) =>
          m.map((msg) => {
            if (msg.id !== tid) return msg;
            return {
              ...msg,
              turnItems: reduceTurnItems(msg.turnItems, {
                type: "agent_activity",
                text: hookLine,
              }),
            };
          }),
        );
      }
      if (blocked || feedback) {
        if (
          isExecutionRelevantHook(eventName, blocked, feedback || subReason)
        ) {
          setWorkHookAlert({
            event: eventName,
            body:
              feedback ||
              subReason ||
              (blocked ? "Execution blocked by hook" : eventName),
            blocked,
          });
          openWorkTab();
        }
        dispatchNotification(
          {
            tier: blocked ? "P1" : "P2",
            title: blocked
              ? `Hook blocked · ${eventName}`
              : `Hook · ${eventName}`,
            body:
              feedback ||
              (agentName
                ? `${agentName}${subReason ? ` (${subReason})` : ""}`
                : subReason),
            sessionId: sid,
            kind: blocked ? "hook_blocked" : "hook_warn",
            entityId: `${eventName}:${String(ev.agent ?? "")}`,
            forceToast: blocked,
          },
          pushMacNotification,
          notifyDesktop,
        );
      }
    }
    if (t === "plan_workflow_phase" && ev.phase) {
      const phase = String(ev.phase);
      const notice = typeof ev.notice === "string" ? ev.notice : undefined;
      patchTurnMessages(scope.runKey, (m) => [
        ...m,
        {
          id: `plan-workflow-${phase}-${Date.now()}`,
          role: "system",
          label: "",
          body: planWorkflowPhaseTranscriptLine(phase, localeMsg, notice),
        },
      ]);
      refreshSessionMeta();
    }
    if (t === "plan_workflow_pending") {
      void refreshSessionMeta();
      dispatchNotification(
        {
          tier: "P1",
          title: localeMsg.planWorkflowPendingTitle,
          body: localeMsg.planWorkflowPendingDetail,
          sessionId: scope.activeSessionId ?? sessionId ?? undefined,
          kind: "plan_workflow_pending",
          toastAction: { type: "inspector", tab: "overview" },
          toastActionLabel: localeMsg.planWorkflowPendingOpenTasks,
        },
        pushMacNotification,
        notifyDesktop,
      );
    }
    if (t === "turn_failed") {
      const aid = ev.agent ? String(ev.agent) : "";
      const reason = String(ev.reason ?? "agent_error");
      const detail = ev.message ? `: ${ev.message}` : "";
      setRecoveryFailure({
        source: "agent",
        kind: "partial_turn",
        message: `${reason}${detail}`,
        affectedAgentIds: aid ? [aid] : undefined,
      });
      patchTurnMessages(scope.runKey, (m) => [
        ...m,
        {
          id: `turn-failed-${Date.now()}`,
          role: "system",
          label: "시스템",
          body: `[턴 실패${aid ? ` · ${agentLabel(aid)}` : ""}] ${reason}${detail}`,
        },
      ]);
    }
    if (t === "inbox_pause") {
      setDiscussPaused(true);
      setInboxReloadKey((k) => k + 1);
      void refreshInboxPending();
      openHumanInbox();
    }
    if (t === "complete" && ev.session_id) {
      scope.activeSessionId = String(ev.session_id);
      setRecoveryFailure(null);
      setRunLockStuck(false);
      if (typeof ev.send_receipt === "string") {
        scope.lastSendReceipt = ev.send_receipt;
      }
      if (ev.inbox_pending === true) {
        setInboxReloadKey((k) => k + 1);
        void fetchSessionInbox(scope.activeSessionId)
          .then((payload) => {
            const sid = scope.activeSessionId ?? undefined;
            const pending = (payload.human_inbox ?? []).filter(
              (item) => item.status === "pending",
            );
            const question = pending.find((item) => item.kind === "question");
            const build = pending.find((item) => item.kind === "build");
            if (build) {
              dispatchNotification(
                {
                  tier: "P1",
                  title: "Build 승인 필요",
                  body: build.summary ?? build.prompt,
                  sessionId: sid,
                  kind: "human_inbox_build",
                  entityId: build.id,
                  toastAction: { type: "composer", focus: "plan" },
                },
                pushMacNotification,
                notifyDesktop,
              );
            } else if (question) {
              dispatchNotification(
                {
                  tier: "P1",
                  title: "에이전트 질문",
                  body: question.prompt,
                  sessionId: sid,
                  kind: "human_inbox_question",
                  entityId: question.id,
                  toastAction: { type: "composer", focus: "inbox" },
                },
                pushMacNotification,
                notifyDesktop,
              );
            } else if (pending.length > 0) {
              dispatchNotification(
                {
                  tier: "P2",
                  title: "Human Inbox",
                  body: `${pending.length}건 대기`,
                  sessionId: sid,
                  kind: "human_inbox",
                  entityId: pending[0]?.id,
                },
                pushMacNotification,
                notifyDesktop,
              );
            }
          })
          .catch(() => {
            /* hook refreshes inbox state via inboxReloadKey */
          });
      }
      if (ev.verified_loop_pending === true) {
        void refreshSessionMeta();
        const loop = ev.verified_loop as
          | { proposed?: { goal?: string } }
          | undefined;
        const goalHint = loop?.proposed?.goal ?? "에이전트 목표 제안";
        dispatchNotification(
          {
            tier: "P1",
            title: "Verified loop 승인",
            body: goalHint,
            sessionId: scope.activeSessionId,
            kind: "verified_loop_pending",
            toastAction: { type: "inspector", tab: "overview" },
            toastActionLabel: "승인하기",
          },
          pushMacNotification,
          notifyDesktop,
        );
      } else if (ev.verified_loop_status === "done") {
        dispatchNotification(
          {
            tier: "P1",
            title: "Oracle VERIFIED",
            body: "Verified loop 목표 달성",
            sessionId: scope.activeSessionId,
            kind: "verified_loop_done",
            forceToast: true,
          },
          pushMacNotification,
          notifyDesktop,
        );
      } else if (ev.verified_loop_circuit_breaker === true) {
        dispatchNotification(
          {
            tier: "P0",
            title: "Verified loop 중단",
            body: "Oracle 검증 한도 초과",
            sessionId: scope.activeSessionId,
            kind: "verified_loop_failed",
            forceToast: true,
          },
          pushMacNotification,
          notifyDesktop,
        );
      }
      dispatchNotification(
        {
          tier: "P2",
          title: scope.userStopped ? "턴 중지됨" : "턴 완료",
          body: scope.lastSendReceipt,
          sessionId: scope.activeSessionId,
          kind: "turn_complete",
        },
        pushMacNotification,
        notifyDesktop,
      );
    }
    if (t === "run_failed") {
      scope.runFailed = true;
      const msg = String(ev.message ?? "run failed");
      setRecoveryFailure({
        source: "run",
        kind: "partial_turn",
        message: msg,
      });
      setRunLockStuck(msg.includes("already in progress"));
      dispatchNotification(
        {
          tier: "P0",
          title: "Agent run failed",
          body: msg,
          sessionId: sessionId ?? undefined,
          kind: "run_failed",
        },
        pushMacNotification,
        notifyDesktop,
      );
    }
    if (t === "run_lock_blocked") {
      scope.runFailed = true;
      const releasable = Boolean(ev.releasable);
      const msg = String(ev.action ?? "a run is already in progress");
      setRunLockStuck(true);
      setRecoveryFailure({
        source: "run",
        kind: "run_lock",
        message: msg,
      });
      if (releasable) {
        void releaseRoomRunLock()
          .then(() => setRunLockStuck(false))
          .catch(() => {});
      }
    }
    if (t === "error") {
      scope.runFailed = true;
      const msg = String(ev.message ?? "run failed");
      setRecoveryFailure({
        source: "run",
        kind: msg.includes("already in progress") ? "run_lock" : undefined,
        message: msg,
      });
      if (msg.includes("already in progress")) {
        setRunLockStuck(true);
      }
      dispatchNotification(
        {
          tier: "P0",
          title: "Room error",
          body: msg,
          sessionId: sessionId ?? undefined,
          kind: "run_failed",
        },
        pushMacNotification,
        notifyDesktop,
      );
    }
  };
}
