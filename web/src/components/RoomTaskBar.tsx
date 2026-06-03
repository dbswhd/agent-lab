import { useEffect, useMemo, useState } from "react";
import {
  completeSessionTask,
  patchSessionTeamLead,
  resolveSessionObjection,
  type MailboxMessage,
  type RoomObjection,
  type PlanExecutionRecord,
  type RoomTask,
  type RoomArtifact,
  type RoomTasksPayload,
} from "../api/client";
import { parseApiErrorDetail } from "../utils/apiError";
import {
  buildEndorsementRequestPrefill,
  endorsementCount,
  findTaskByBlockerRef,
  formatConsensusBlockerCopy,
  formatTaskBarCollapsedSummary,
  formatTaskBarEmptyState,
  formatTaskBarModeHint,
  formatTeamAgreementLabel,
  formatTurnLeadLabel,
  isUnassignedOpenTask,
  LEAD_HELP_DETAIL,
  LEAD_HELP_SUMMARY,
  LEAD_HELP_TOGGLE_LABEL,
  resolveRequiredAgreements,
  resolveTaskBarMode,
  shouldShowConsensusBlocker,
  shouldShowTurnLeadDetails,
  type TaskBarComposerVariant,
  TASK_BAR_AUTO_REFRESH_HINT,
  UNASSIGNED_OWNER_LABEL,
  UNASSIGNED_OWNER_TOOLTIP,
} from "../utils/taskBarCopy";
import { getTaskBarCollapsed, setTaskBarCollapsed } from "../utils/taskBarPrefs";
import type { ComposerTurnProfile } from "../utils/turnProfile";

export type TaskBarContext = {
  composerVariant: TaskBarComposerVariant;
  turnProfile: ComposerTurnProfile;
  lastTurnHadConsensus: boolean;
  selectedAgentCount: number;
};

type Props = {
  sessionId: string;
  payload: RoomTasksPayload | null;
  context: TaskBarContext;
  loading?: boolean;
  executions?: PlanExecutionRecord[];
  focusObjection?: { id: string; nonce: number } | null;
  onRefresh?: () => void;
  onFocusPlanAction?: (actionIndex: number) => void;
  onFocusTask?: (taskId: string) => void;
  onRequestComposerPrefill?: (text: string) => void;
};

type TaskTab = "all" | "unassigned";

function taskCompleteGate(
  task: RoomTask,
  executions: PlanExecutionRecord[] | undefined,
): { blocked: boolean; hint: string | null } {
  if (task.plan_action_index == null && !task.plan_action_id) {
    return { blocked: false, hint: null };
  }
  const rows = executions ?? [];
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const ex = rows[i];
    const match =
      (task.plan_action_index != null &&
        ex.action_index === task.plan_action_index) ||
      (task.plan_action_id != null && ex.action_id === task.plan_action_id);
    if (!match) continue;
    if (ex.status === "pending_approval") {
      return { blocked: true, hint: "plan 실행 승인 대기" };
    }
    if (ex.status === "review_required") {
      return { blocked: true, hint: "plan 실행 검증 미완료" };
    }
    return { blocked: false, hint: null };
  }
  return { blocked: false, hint: null };
}

const STATUS_LABEL: Record<string, string> = {
  pending: "대기",
  in_progress: "진행",
  completed: "완료",
  cancelled: "취소",
};

const LEAD_OPTIONS = ["cursor", "codex", "claude"] as const;

function formatTurnLeads(
  turnLeads: Record<string, string> | undefined,
  currentLead: string,
): { currentTurnLead: string; history: { turn: string; agent: string }[] } {
  const map = turnLeads ?? {};
  const keys = Object.keys(map)
    .map((k) => Number(k))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => b - a);
  const latestTurn = keys[0];
  const currentTurnLead =
    latestTurn != null ? map[String(latestTurn)] ?? currentLead : currentLead;
  const history = keys.map((t) => ({
    turn: String(t),
    agent: map[String(t)] ?? "?",
  }));
  return { currentTurnLead, history };
}

function linkedExecutionRow(
  task: RoomTask,
  executions: PlanExecutionRecord[] | undefined,
): { planIndex: number | null; status: string | null; executionId: string | null } {
  const rows = executions ?? [];
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const ex = rows[i];
    const match =
      (task.plan_action_index != null &&
        ex.action_index === task.plan_action_index) ||
      (task.plan_action_id != null && ex.action_id === task.plan_action_id);
    if (match) {
      return {
        planIndex: ex.action_index ?? task.plan_action_index ?? null,
        status: ex.status ?? null,
        executionId: ex.id ?? null,
      };
    }
  }
  return {
    planIndex: task.plan_action_index ?? null,
    status: null,
    executionId: null,
  };
}

function TaskRows({
  tasks,
  showOwner = true,
  sessionId,
  executions,
  requiredAgreements,
  onRefresh,
  onFocusPlanAction,
  onFocusTask,
}: {
  tasks: RoomTask[];
  showOwner?: boolean;
  sessionId: string;
  executions?: PlanExecutionRecord[];
  requiredAgreements: number;
  onRefresh?: () => void;
  onFocusPlanAction?: (actionIndex: number) => void;
  onFocusTask?: (taskId: string) => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [completeErrors, setCompleteErrors] = useState<Record<string, string>>(
    {},
  );

  async function markComplete(taskId: string) {
    setBusyId(taskId);
    setCompleteErrors((prev) => {
      const next = { ...prev };
      delete next[taskId];
      return next;
    });
    try {
      await completeSessionTask(sessionId, taskId);
      onRefresh?.();
    } catch (e) {
      const msg =
        e instanceof Error ? parseApiErrorDetail(e.message) : "완료 처리 실패";
      setCompleteErrors((prev) => ({ ...prev, [taskId]: msg }));
    } finally {
      setBusyId(null);
    }
  }

  if (tasks.length === 0) {
    return (
      <p className="room-task-bar__tab-empty">이 목록에 표시할 할 일이 없습니다.</p>
    );
  }

  return (
    <ul className="room-task-bar__list">
      {tasks.map((t) => {
        const completeGate = taskCompleteGate(t, executions);
        const rowError = completeErrors[t.id];
        const agreeCount = endorsementCount(t);
        return (
          <li
            key={t.id}
            data-task-id={t.id}
            className={`room-task-bar__item room-task-bar__item--${t.status}`}
          >
            <span className="room-task-bar__status">
              {STATUS_LABEL[t.status] ?? t.status}
            </span>
            {onFocusTask ? (
              <button
                type="button"
                className="room-task-bar__title-link"
                onClick={() => onFocusTask(t.id)}
                title="채팅에서 이 할 일 언급으로 이동"
              >
                {t.title}
              </button>
            ) : (
              <span className="room-task-bar__title-text">{t.title}</span>
            )}
            {showOwner && t.owner_agent ? (
              <span className="room-task-bar__owner">@{t.owner_agent}</span>
            ) : null}
            {showOwner && !t.owner_agent ? (
              <span
                className="room-task-bar__owner room-task-bar__owner--open"
                title={UNASSIGNED_OWNER_TOOLTIP}
              >
                {UNASSIGNED_OWNER_LABEL}
              </span>
            ) : null}
            {t.status !== "completed" && t.status !== "cancelled" ? (
              <span
                className="room-task-bar__endorse"
                title="이 할 일에 동의한 에이전트 수"
              >
                {formatTeamAgreementLabel(agreeCount, requiredAgreements)}
              </span>
            ) : null}
            {t.plan_action_index != null && onFocusPlanAction ? (
              <button
                type="button"
                className="room-task-bar__plan-link"
                onClick={() => onFocusPlanAction(t.plan_action_index!)}
                title={`plan 지금 실행 #${t.plan_action_index}`}
              >
                plan #{t.plan_action_index}
              </button>
            ) : null}
            {t.status === "pending" || t.status === "in_progress" ? (
              <span className="room-task-bar__complete-wrap">
                <button
                  type="button"
                  className="room-task-bar__complete"
                  disabled={busyId === t.id || completeGate.blocked}
                  title={completeGate.hint ?? undefined}
                  onClick={() => void markComplete(t.id)}
                >
                  완료
                </button>
                {completeGate.blocked && completeGate.hint ? (
                  <span className="room-task-bar__complete-hint">
                    {completeGate.hint}
                  </span>
                ) : null}
                {rowError ? (
                  <span className="room-task-bar__complete-error" role="alert">
                    {rowError}
                  </span>
                ) : null}
              </span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function RoomTaskBar({
  sessionId,
  payload,
  context,
  loading,
  executions,
  focusObjection,
  onRefresh,
  onFocusPlanAction,
  onFocusTask,
  onRequestComposerPrefill,
}: Props) {
  const [leadBusy, setLeadBusy] = useState(false);
  const [leadError, setLeadError] = useState<string | null>(null);
  const [leadHelpOpen, setLeadHelpOpen] = useState(false);
  const [turnHistoryExpanded, setTurnHistoryExpanded] = useState(false);
  const [taskTab, setTaskTab] = useState<TaskTab>("all");
  const [collapsed, setCollapsed] = useState(() => getTaskBarCollapsed());
  const [blockerCompleteBusy, setBlockerCompleteBusy] = useState(false);
  const [objectionBusyId, setObjectionBusyId] = useState<string | null>(null);

  useEffect(() => {
    setTaskBarCollapsed(collapsed);
  }, [collapsed]);

  useEffect(() => {
    if (!focusObjection?.id) return;
    setCollapsed(false);
    setTaskBarCollapsed(false);
    window.setTimeout(() => {
      const node = document.querySelector<HTMLElement>(
        `[data-objection-id="${focusObjection.id}"]`,
      );
      node?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      node?.focus({ preventScroll: true });
    }, 80);
  }, [focusObjection]);

  const tasks = payload?.tasks ?? [];
  const claimableCount = (payload?.claimable ?? []).length;
  const requiredAgreements = resolveRequiredAgreements(payload);
  const taskBarMode = resolveTaskBarMode(
    context.composerVariant,
    context.turnProfile,
  );
  const showTurnLead = shouldShowTurnLeadDetails(taskBarMode);
  const openTaskCount = payload?.open_task_count ?? 0;
  const modeHint = formatTaskBarModeHint(taskBarMode, {
    taskCount: tasks.length,
    openCount: openTaskCount,
    selectedAgentCount: context.selectedAgentCount,
  });
  const emptyCopy = formatTaskBarEmptyState(taskBarMode);

  const unassignedTasks = useMemo(
    () => tasks.filter(isUnassignedOpenTask),
    [tasks],
  );

  const visibleTasks = useMemo(() => {
    if (taskTab === "unassigned") return unassignedTasks;
    return tasks;
  }, [taskTab, tasks, unassignedTasks]);

  const blockers = payload?.consensus_task_blockers ?? [];
  const showConsensusBlocker = payload
    ? shouldShowConsensusBlocker(
        payload,
        taskBarMode,
        context.lastTurnHadConsensus,
      )
    : false;

  const primaryBlockedTask = useMemo(() => {
    if (!payload) return undefined;
    const gateFirst = payload.consensus_gate?.blocked_tasks?.[0];
    if (gateFirst?.id) {
      return (
        tasks.find((t) => t.id === gateFirst.id) ?? {
          id: gateFirst.id,
          title: gateFirst.title,
          status: "pending" as const,
        }
      );
    }
    const ref = blockers[0];
    if (!ref) return undefined;
    return findTaskByBlockerRef(tasks, ref);
  }, [payload, blockers, tasks]);

  if (!payload) return null;
  const openObjectionCount = payload.open_objection_count ?? 0;
  if (
    tasks.length === 0 &&
    claimableCount === 0 &&
    openObjectionCount === 0 &&
    !loading
  ) {
    return null;
  }

  async function changeLead(agent: string) {
    if (agent === payload?.team_lead) return;
    setLeadBusy(true);
    setLeadError(null);
    try {
      await patchSessionTeamLead(sessionId, agent);
      onRefresh?.();
    } catch (e) {
      setLeadError(
        e instanceof Error ? parseApiErrorDetail(e.message) : "리드 변경 실패",
      );
    } finally {
      setLeadBusy(false);
    }
  }

  const blockerCopy = showConsensusBlocker
    ? formatConsensusBlockerCopy(
        blockers,
        tasks,
        requiredAgreements,
        payload.consensus_gate,
      )
    : { headline: "", detail: "" };
  const { currentTurnLead, history: turnLeadHistory } = formatTurnLeads(
    payload.turn_leads,
    payload.team_lead ?? "cursor",
  );
  const turnHistoryVisible = turnHistoryExpanded
    ? turnLeadHistory
    : turnLeadHistory.slice(0, 3);
  const turnHistoryHidden = turnLeadHistory.length - turnHistoryVisible.length;

  const collapsedSummary = formatTaskBarCollapsedSummary({
    pending: payload.counts?.pending ?? 0,
    inProgress: payload.counts?.in_progress ?? 0,
    blockedCount: showConsensusBlocker ? blockers.length : 0,
    taskCount: tasks.length,
    currentTurnLead: showTurnLead ? currentTurnLead : undefined,
  });

  const mailbox = payload.mailbox ?? [];
  const mailboxUnread = payload.mailbox_unread ?? {};
  const unreadTotal = Object.values(mailboxUnread).reduce((a, b) => a + b, 0);
  const recentMailbox = [...mailbox].reverse().slice(0, 8);
  const artifacts = payload?.artifacts ?? [];
  const recentArtifacts = [...artifacts].reverse().slice(0, 8);
  const openObjections = payload.open_objections ?? [];
  const showObjectionBlocker = openObjections.length > 0;

  async function resolveObjection(
    obj: RoomObjection,
    verdict: "accepted" | "wontfix",
  ) {
    setObjectionBusyId(obj.id);
    try {
      await resolveSessionObjection(sessionId, obj.id, verdict);
      onRefresh?.();
    } catch {
      /* refresh on next poll */
    } finally {
      setObjectionBusyId(null);
    }
  }

  const linkedRows = tasks
    .filter((t) => t.plan_action_index != null || t.plan_action_id)
    .map((t) => ({ task: t, link: linkedExecutionRow(t, executions) }))
    .filter((r) => r.link.planIndex != null || r.link.status);
  const linkedVisible = linkedRows.slice(0, 5);
  const linkedOverflow = linkedRows.length - linkedVisible.length;

  function focusBlockerRef(ref: string) {
    const task = findTaskByBlockerRef(tasks, ref);
    onFocusTask?.(task?.id ?? ref);
  }

  async function completePrimaryBlockedTask() {
    if (!primaryBlockedTask) return;
    setBlockerCompleteBusy(true);
    try {
      await completeSessionTask(sessionId, primaryBlockedTask.id);
      onRefresh?.();
    } catch {
      /* row-level errors shown on next refresh */
    } finally {
      setBlockerCompleteBusy(false);
    }
  }

  function requestEndorsementPrefill() {
    if (!primaryBlockedTask || !onRequestComposerPrefill) return;
    onRequestComposerPrefill(buildEndorsementRequestPrefill(primaryBlockedTask));
  }

  if (collapsed) {
    return (
      <div
        className={`room-task-bar room-task-bar--collapsed room-task-bar--${taskBarMode}`}
        role="region"
        aria-label="팀 할 일 목록"
      >
        <button
          type="button"
          className="room-task-bar__collapse-trigger"
          aria-expanded={false}
          onClick={() => setCollapsed(false)}
        >
          <strong className="room-task-bar__title">팀 할 일</strong>
          <span className="room-task-bar__collapse-summary">{collapsedSummary}</span>
          <span className="room-task-bar__collapse-action">펼치기</span>
        </button>
      </div>
    );
  }

  return (
    <div
      className={`room-task-bar room-task-bar--${taskBarMode}`}
      role="region"
      aria-label="팀 할 일 목록"
    >
      <div className="room-task-bar__head">
        <strong className="room-task-bar__title">팀 할 일</strong>
        {showTurnLead ? (
          <span className="room-task-bar__turn-lead" title={LEAD_HELP_SUMMARY}>
            이번 턴 · <strong>{currentTurnLead}</strong>
          </span>
        ) : null}
        <label className="room-task-bar__lead-select" title={LEAD_HELP_SUMMARY}>
          세션 리드
          <select
            value={payload.team_lead ?? "cursor"}
            disabled={leadBusy || loading}
            aria-describedby="room-task-bar-lead-help"
            onChange={(e) => void changeLead(e.target.value)}
          >
            {LEAD_OPTIONS.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <span className="room-task-bar__meta">
          대기 {payload.counts?.pending ?? 0} · 진행{" "}
          {payload.counts?.in_progress ?? 0} · 완료{" "}
          {payload.counts?.completed ?? 0}
          <span className="room-task-bar__auto-hint" title={TASK_BAR_AUTO_REFRESH_HINT}>
            {" "}
            · {TASK_BAR_AUTO_REFRESH_HINT}
          </span>
        </span>
        <button
          type="button"
          className="room-task-bar__collapse-btn"
          aria-expanded
          title="할 일 바 접기"
          onClick={() => setCollapsed(true)}
        >
          접기
        </button>
        {onRefresh ? (
          <button
            type="button"
            className="room-task-bar__refresh"
            onClick={onRefresh}
            disabled={loading}
            title="수동으로 목록 다시 불러오기"
            aria-label="할 일 목록 새로고침"
          >
            {loading ? "…" : "↻"}
          </button>
        ) : null}
      </div>
      <p className="room-task-bar__mode-hint" role="status">
        {modeHint}
      </p>
      <div className="room-task-bar__lead-help-row">
        <p id="room-task-bar-lead-help" className="room-task-bar__lead-summary">
          {LEAD_HELP_SUMMARY}
        </p>
        <button
          type="button"
          className="room-task-bar__lead-help-toggle"
          aria-expanded={leadHelpOpen}
          aria-controls="room-task-bar-lead-detail"
          onClick={() => setLeadHelpOpen((v) => !v)}
        >
          {LEAD_HELP_TOGGLE_LABEL}
        </button>
      </div>
      {leadHelpOpen ? (
        <p id="room-task-bar-lead-detail" className="room-task-bar__lead-help">
          {LEAD_HELP_DETAIL}
        </p>
      ) : null}
      {leadError ? (
        <p className="room-task-bar__lead-error" role="alert">
          {leadError}
        </p>
      ) : null}
      {showTurnLead && turnLeadHistory.length > 0 ? (
        <div className="room-task-bar__turn-leads-history">
          <span className="room-task-bar__turn-leads-label">최근 턴 리드</span>
          {turnHistoryVisible.map(({ turn, agent }) => (
            <span key={turn} className="room-task-bar__turn-lead-chip">
              {formatTurnLeadLabel(turn, agent)}
            </span>
          ))}
          {turnHistoryHidden > 0 && !turnHistoryExpanded ? (
            <button
              type="button"
              className="room-task-bar__turn-leads-more"
              onClick={() => setTurnHistoryExpanded(true)}
            >
              +{turnHistoryHidden}개 더 보기
            </button>
          ) : null}
          {turnHistoryExpanded && turnLeadHistory.length > 3 ? (
            <button
              type="button"
              className="room-task-bar__turn-leads-more"
              onClick={() => setTurnHistoryExpanded(false)}
            >
              접기
            </button>
          ) : null}
        </div>
      ) : null}
      {showObjectionBlocker ? (
        <div
          className="room-task-bar__blocker room-task-bar__blocker--objection"
          role="status"
          aria-label="미해결 이의"
        >
          <p className="room-task-bar__blocker-headline">
            미해결 이의 {openObjections.length}건 — plan 실행이 차단될 수 있습니다
          </p>
          <ul className="room-task-bar__objection-list">
            {openObjections.slice(0, 5).map((o) => (
              <li
                key={o.id}
                className="room-task-bar__objection-item"
                data-objection-id={o.id}
                tabIndex={-1}
              >
                <span>
                  <strong>
                    {o.from} · {o.act}
                  </strong>
                  {o.plan_action_index != null ? (
                    <span className="room-task-bar__objection-ref">
                      {" "}
                      → plan #{o.plan_action_index}
                    </span>
                  ) : null}
                  {o.target_ref || o.task_id ? (
                    <span className="room-task-bar__objection-ref">
                      {" "}
                      → {o.target_ref ?? o.task_id}
                    </span>
                  ) : null}
                </span>
                <span className="room-task-bar__objection-body">{o.body}</span>
                <span className="room-task-bar__objection-actions">
                  {o.plan_action_index != null && onFocusPlanAction ? (
                    <button
                      type="button"
                      className="room-task-bar__cta"
                      onClick={() => onFocusPlanAction(o.plan_action_index!)}
                    >
                      plan 보기
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="room-task-bar__cta"
                    disabled={objectionBusyId === o.id}
                    onClick={() => void resolveObjection(o, "accepted")}
                  >
                    수용
                  </button>
                  <button
                    type="button"
                    className="room-task-bar__cta room-task-bar__cta--muted"
                    disabled={objectionBusyId === o.id}
                    onClick={() => void resolveObjection(o, "wontfix")}
                  >
                    기각
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {showConsensusBlocker ? (
        <div className="room-task-bar__blocker" role="status">
          <p className="room-task-bar__blocker-headline">{blockerCopy.headline}</p>
          <p className="room-task-bar__blocker-detail">{blockerCopy.detail}</p>
          <p className="room-task-bar__blocker-tasks">
            {blockers.slice(0, 3).map((ref, i) => (
              <span key={ref}>
                {i > 0 ? ", " : null}
                {onFocusTask ? (
                  <button
                    type="button"
                    className="room-task-bar__blocker-link"
                    onClick={() => focusBlockerRef(ref)}
                  >
                    {findTaskByBlockerRef(tasks, ref)?.title ?? ref}
                  </button>
                ) : (
                  findTaskByBlockerRef(tasks, ref)?.title ?? ref
                )}
              </span>
            ))}
            {blockers.length > 3 ? ` 외 ${blockers.length - 3}건` : ""}
          </p>
          <div className="room-task-bar__blocker-actions">
            {onRequestComposerPrefill && primaryBlockedTask ? (
              <button
                type="button"
                className="room-task-bar__cta room-task-bar__cta--primary"
                onClick={requestEndorsementPrefill}
              >
                채팅에 동의 요청 넣기
              </button>
            ) : null}
            {primaryBlockedTask ? (
              <button
                type="button"
                className="room-task-bar__cta"
                disabled={blockerCompleteBusy}
                onClick={() => void completePrimaryBlockedTask()}
              >
                이 할 일 완료로 닫기
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      {tasks.length > 0 ? (
        <div
          className="room-task-bar__tabs"
          role="tablist"
          aria-label="할 일 목록 필터"
        >
          <button
            type="button"
            role="tab"
            aria-selected={taskTab === "all"}
            className={
              taskTab === "all"
                ? "room-task-bar__tab room-task-bar__tab--active"
                : "room-task-bar__tab"
            }
            onClick={() => setTaskTab("all")}
          >
            전체 {tasks.length}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={taskTab === "unassigned"}
            className={
              taskTab === "unassigned"
                ? "room-task-bar__tab room-task-bar__tab--active"
                : "room-task-bar__tab"
            }
            onClick={() => setTaskTab("unassigned")}
            title={UNASSIGNED_OWNER_TOOLTIP}
          >
            담당 없음 {unassignedTasks.length}
          </button>
        </div>
      ) : null}
      {tasks.length === 0 ? (
        <div className="room-task-bar__empty">
          <p>{emptyCopy.message}</p>
          <p className="room-task-bar__empty-example">{emptyCopy.example}</p>
        </div>
      ) : (
        <TaskRows
          tasks={visibleTasks}
          sessionId={sessionId}
          executions={executions}
          requiredAgreements={requiredAgreements}
          onRefresh={onRefresh}
          onFocusPlanAction={onFocusPlanAction}
          onFocusTask={onFocusTask}
        />
      )}
      {artifacts.length > 0 ? (
        <div className="room-task-bar__artifacts" role="region" aria-label="산출물">
          <span className="room-task-bar__mailbox-label">
            artifacts
            {payload?.artifact_count != null ? (
              <span className="room-task-bar__mailbox-unread">
                {" "}
                ({payload.artifact_count})
              </span>
            ) : null}
          </span>
          <ul className="room-task-bar__mailbox-list">
            {recentArtifacts.map((a: RoomArtifact) => (
              <li key={a.id} className="room-task-bar__mailbox-item">
                <strong>
                  {a.producer} · {a.kind}
                </strong>
                <span className="room-task-bar__mailbox-body">
                  {(a.summary || "").slice(0, 160)}
                  {a.path ? ` · ${a.path}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {mailbox.length > 0 ? (
        <div className="room-task-bar__mailbox" role="region" aria-label="받은함">
          <span className="room-task-bar__mailbox-label">
            받은함
            {unreadTotal > 0 ? (
              <span className="room-task-bar__mailbox-unread">
                {" "}
                (미전달 {unreadTotal})
              </span>
            ) : null}
          </span>
          <ul className="room-task-bar__mailbox-list">
            {recentMailbox.map((m: MailboxMessage) => (
              <li
                key={m.id}
                className={
                  m.read
                    ? "room-task-bar__mailbox-item"
                    : "room-task-bar__mailbox-item room-task-bar__mailbox-item--unread"
                }
              >
                <strong>
                  {m.from} → {m.to}
                </strong>
                <span className="room-task-bar__mailbox-body">{m.body}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {linkedRows.length > 0 ? (
        <div className="room-task-bar__cross-links" role="status">
          <span className="room-task-bar__cross-links-label">
            plan ↔ 작업 ↔ 실행
          </span>
          <ul className="room-task-bar__cross-links-list">
            {linkedVisible.map(({ task, link }) => (
              <li key={task.id} className="room-task-bar__cross-link-row">
                {link.planIndex != null && onFocusPlanAction ? (
                  <button
                    type="button"
                    className="room-task-bar__plan-link"
                    onClick={() => onFocusPlanAction(link.planIndex!)}
                  >
                    plan #{link.planIndex}
                  </button>
                ) : (
                  <span>plan —</span>
                )}
                <span className="room-task-bar__cross-sep">↔</span>
                {onFocusTask ? (
                  <button
                    type="button"
                    className="room-task-bar__task-link"
                    onClick={() => onFocusTask(task.id)}
                  >
                    {task.id}
                  </button>
                ) : (
                  <span>{task.id}</span>
                )}
                <span className="room-task-bar__cross-sep">↔</span>
                <span>
                  {link.status ?? "미실행"}
                  {link.executionId ? ` (${link.executionId.slice(0, 8)}…)` : ""}
                </span>
              </li>
            ))}
            {linkedOverflow > 0 ? (
              <li className="room-task-bar__cross-link-more">
                +{linkedOverflow}건 더 있음 (작업 행의 plan # 링크 참고)
              </li>
            ) : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
