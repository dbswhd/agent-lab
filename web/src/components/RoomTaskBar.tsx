import { useEffect, useMemo, useState } from "react";
import {
  completeSessionTask,
  patchSessionTeamLead,
  resolveSessionObjection,
  type RoomObjection,
  type PlanExecutionRecord,
  type RoomTask,
  type RoomTasksPayload,
} from "../api/client";
import { parseApiErrorDetail } from "../utils/apiError";
import {
  buildEndorsementRequestPrefill,
  endorsementCount,
  findTaskByBlockerRef,
  formatConsensusBlockerCopy,
  formatTaskBarEmptyState,
  formatTaskBarModeHint,
  formatTeamAgreementLabel,
  LEAD_HELP_SUMMARY,
  LEAD_HELP_DETAIL,
  resolveRequiredAgreements,
  resolveTaskBarMode,
  shouldShowConsensusBlocker,
  type TaskBarComposerVariant,
  TASK_BAR_AUTO_REFRESH_HINT,
  UNASSIGNED_OWNER_LABEL,
  UNASSIGNED_OWNER_TOOLTIP,
  buildTaskCrossLinks,
  isUnassignedOpenTask,
} from "../utils/taskBarCopy";
import type { ComposerTurnProfile } from "../utils/turnProfile";
import type { AgentRole } from "../utils/transcript";
import { Avatar } from "./Avatar";

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
  /** dock = composer strip; inspector = legacy full-width inspector styling */
  placement?: "dock" | "inspector";
  onRefresh?: () => void;
  onFocusPlanAction?: (actionIndex: number) => void;
  onFocusTask?: (taskId: string) => void;
  onRequestComposerPrefill?: (text: string) => void;
};

const LEAD_OPTIONS = ["cursor", "codex", "claude"] as const;

const STATUS_BADGE: Record<string, string> = {
  pending: "대기",
  in_progress: "진행",
  completed: "완료",
  cancelled: "취소",
  blocked: "차단",
};

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

function agentRole(id: string | undefined): AgentRole {
  if (id === "cursor" || id === "codex" || id === "claude") return id;
  return "system";
}

function TabIcon({ name }: { name: "alert" }) {
  const paths = {
    alert:
      "M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z",
  };
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      aria-hidden
    >
      <path d={paths[name]} />
    </svg>
  );
}

export function RoomTaskBar({
  sessionId,
  payload,
  context,
  loading,
  executions,
  focusObjection,
  placement = "inspector",
  onRefresh,
  onFocusPlanAction,
  onFocusTask,
  onRequestComposerPrefill,
}: Props) {
  const [leadBusy, setLeadBusy] = useState(false);
  const [leadError, setLeadError] = useState<string | null>(null);
  const [blockerCompleteBusy, setBlockerCompleteBusy] = useState(false);
  const [blockerCompleteError, setBlockerCompleteError] = useState<
    string | null
  >(null);
  const [objectionBusyId, setObjectionBusyId] = useState<string | null>(null);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [completeErrors, setCompleteErrors] = useState<Record<string, string>>(
    {},
  );

  useEffect(() => {
    if (!focusObjection?.id) return;
    window.setTimeout(() => {
      const node = document.querySelector<HTMLElement>(
        `[data-objection-id="${focusObjection.id}"]`,
      );
      node?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      node?.focus({ preventScroll: true });
    }, 80);
  }, [focusObjection]);

  const tasks = payload?.tasks ?? [];
  const claimable = payload?.claimable ?? [];
  const claimableCount = claimable.length;
  const requiredAgreements = resolveRequiredAgreements(payload);
  const taskBarMode = resolveTaskBarMode(
    context.composerVariant,
    context.turnProfile,
  );
  const openTaskCount = payload?.open_task_count ?? 0;
  const modeHint = formatTaskBarModeHint(taskBarMode, {
    taskCount: tasks.length,
    openCount: openTaskCount,
    selectedAgentCount: context.selectedAgentCount,
  });
  const emptyCopy = formatTaskBarEmptyState(taskBarMode);

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

  const turnLeadEntries = useMemo(() => {
    const map = payload?.turn_leads ?? {};
    return Object.entries(map)
      .sort(([a], [b]) => Number(a) - Number(b))
      .slice(-6);
  }, [payload?.turn_leads]);

  const claimableIds = useMemo(
    () => new Set(claimable.map((t) => t.id)),
    [claimable],
  );
  const crossLinks = useMemo(
    () => buildTaskCrossLinks(tasks, executions),
    [tasks, executions],
  );

  if (!payload) return null;

  const isDock = placement === "dock";
  const openObjections = payload.open_objections ?? [];
  const allObjections = payload.objections ?? openObjections;
  const openObjectionCount =
    payload.open_objection_count ?? openObjections.length;
  const openObjectionRows = allObjections.filter(
    (obj) => obj.status === "open",
  );

  if (
    isDock
      ? tasks.length === 0 &&
        claimableCount === 0 &&
        openObjectionCount === 0 &&
        !showConsensusBlocker &&
        !loading
      : tasks.length === 0 &&
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

  const taskOpenCount =
    (payload.counts?.pending ?? 0) + (payload.counts?.in_progress ?? 0);
  const taskBlockedCount = showConsensusBlocker ? blockers.length : 0;
  const hasTaskbarAlert = openObjectionRows.length > 0 || taskBlockedCount > 0;

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

  async function markComplete(taskId: string) {
    setBusyTaskId(taskId);
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
      setBusyTaskId(null);
    }
  }

  async function completePrimaryBlockedTask() {
    if (!primaryBlockedTask) return;
    setBlockerCompleteBusy(true);
    setBlockerCompleteError(null);
    try {
      await completeSessionTask(sessionId, primaryBlockedTask.id);
      onRefresh?.();
    } catch (e) {
      const msg =
        e instanceof Error ? parseApiErrorDetail(e.message) : "완료 처리 실패";
      setBlockerCompleteError(msg);
    } finally {
      setBlockerCompleteBusy(false);
    }
  }

  function requestEndorsementPrefill() {
    if (!primaryBlockedTask || !onRequestComposerPrefill) return;
    onRequestComposerPrefill(
      buildEndorsementRequestPrefill(primaryBlockedTask),
    );
  }

  return (
    <div
      className={[
        "taskbar",
        placement === "dock" ? "taskbar--dock" : "taskbar--inspector",
        "is-open",
        hasTaskbarAlert ? "taskbar--alert" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      role="region"
      aria-label="팀 할 일 목록"
    >
      <div className="taskbar__body">
        {isDock ? (
          <header className="taskbar__dock-head">
            <div className="taskbar__dock-title-group">
              <strong className="taskbar__dock-title">팀 큐</strong>
              {openObjectionRows.length > 0 || taskOpenCount > 0 ? (
                <span className="taskbar__dock-meta">
                  {[
                    openObjectionRows.length > 0
                      ? `이의 ${openObjectionRows.length}`
                      : null,
                    taskOpenCount > 0 ? `할 일 ${taskOpenCount}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              ) : null}
            </div>
            {onRefresh ? (
              <button
                type="button"
                className="btn btn--sm btn--ghost"
                onClick={onRefresh}
                disabled={loading}
                title={TASK_BAR_AUTO_REFRESH_HINT}
              >
                {loading ? "…" : "↻"}
              </button>
            ) : null}
          </header>
        ) : null}

        <div className="taskbar__section">
          {!isDock ? (
            <>
              <div className="taskbar-section-label taskbar-section-label--inline">
                <label
                  className="taskbar-lead-select"
                  title={LEAD_HELP_SUMMARY}
                >
                  <span className="taskbar-lead-select__label">세션 리드</span>
                  <select
                    value={payload.team_lead ?? "cursor"}
                    disabled={leadBusy || loading}
                    onChange={(e) => void changeLead(e.target.value)}
                    aria-describedby="taskbar-lead-help"
                  >
                    {LEAD_OPTIONS.map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="btn btn--sm btn--ghost taskbar-lead-help"
                  id="taskbar-lead-help"
                  title={LEAD_HELP_DETAIL}
                  aria-label={LEAD_HELP_SUMMARY}
                >
                  ?
                </button>
                {onRefresh ? (
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={onRefresh}
                    disabled={loading}
                    title={TASK_BAR_AUTO_REFRESH_HINT}
                  >
                    {loading ? "…" : "↻"}
                  </button>
                ) : null}
              </div>
              {leadError ? (
                <p className="taskbar-inline-error" role="alert">
                  {leadError}
                </p>
              ) : null}
              {turnLeadEntries.length > 0 ? (
                <div
                  className="taskbar__turn-leads-history"
                  title={LEAD_HELP_DETAIL}
                >
                  <span className="taskbar__turn-leads-label">
                    이번 턴 리드
                  </span>
                  {turnLeadEntries.map(([turn, agent]) => (
                    <span
                      key={`${turn}-${agent}`}
                      className="taskbar__turn-lead-chip"
                    >
                      T{turn}→{agent}
                    </span>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
          {showConsensusBlocker ? (
            <div className="taskbar__consensus-gate" aria-label="합의 차단">
              <TabIcon name="alert" />
              <div className="taskbar__gate-body">
                <strong>{blockerCopy.headline}</strong>
                <span className="taskbar__gate-meta">{blockerCopy.detail}</span>
                <span className="taskbar__gate-actions">
                  {onRequestComposerPrefill && primaryBlockedTask ? (
                    <button
                      type="button"
                      className="btn btn--sm btn--ok"
                      onClick={requestEndorsementPrefill}
                    >
                      동의 요청
                    </button>
                  ) : null}
                  {primaryBlockedTask ? (
                    <button
                      type="button"
                      className="btn btn--sm"
                      disabled={blockerCompleteBusy}
                      onClick={() => void completePrimaryBlockedTask()}
                    >
                      완료로 닫기
                    </button>
                  ) : null}
                </span>
              </div>
              {blockerCompleteError ? (
                <p className="taskbar-inline-error" role="alert">
                  {blockerCompleteError}
                </p>
              ) : null}
            </div>
          ) : null}
          {openObjectionRows.length > 0 ? (
            <div className="taskbar__queue-block" aria-label="미해결 이의">
              <div className="taskbar__queue-block-label">미해결 이의</div>
              {openObjectionRows.map((obj) => (
                <div
                  key={obj.id}
                  className="objection-row"
                  data-objection-id={obj.id}
                  tabIndex={-1}
                >
                  <div className="objection-row__head">
                    <Avatar role={agentRole(obj.from)} size={18} />
                    <span
                      className={`objection-row__act${
                        obj.act === "CHALLENGE"
                          ? " objection-row__act--challenge"
                          : ""
                      }`}
                    >
                      {obj.act}
                    </span>
                    {obj.plan_action_index != null ? (
                      <span className="objection-row__ref">
                        plan #{obj.plan_action_index}
                      </span>
                    ) : null}
                  </div>
                  <p className="objection-row__body">{obj.body}</p>
                  <div className="objection-row__actions">
                    {obj.plan_action_index != null && onFocusPlanAction ? (
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() =>
                          onFocusPlanAction(obj.plan_action_index!)
                        }
                      >
                        plan 보기
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn--sm btn--ok"
                      disabled={objectionBusyId === obj.id}
                      onClick={() => void resolveObjection(obj, "accepted")}
                    >
                      수용
                    </button>
                    <button
                      type="button"
                      className="btn btn--sm"
                      disabled={objectionBusyId === obj.id}
                      onClick={() => void resolveObjection(obj, "wontfix")}
                    >
                      기각
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {tasks.length > 0 ? (
            <div className="taskbar__queue-block" aria-label="Room tasks">
              {isDock && openObjectionRows.length > 0 ? (
                <div className="taskbar__queue-block-label">할 일</div>
              ) : null}
              {tasks.map((task) => {
                const completeGate = taskCompleteGate(task, executions);
                const agreeCount = endorsementCount(task);
                const rowError = completeErrors[task.id];
                const statusKey =
                  task.status === "cancelled" ? "blocked" : task.status;
                const isClaimable = claimableIds.has(task.id);
                return (
                  <div
                    key={task.id}
                    className={[
                      "task-row",
                      statusKey === "blocked" ? "task-row--blocked" : undefined,
                      isClaimable ? "task-row--claimable" : undefined,
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    data-task-id={task.id}
                  >
                    <span
                      className={`task-row__dot task-row__dot--${statusKey}`}
                    />
                    {onFocusTask ? (
                      <button
                        type="button"
                        className="task-row__title task-row__title--link"
                        onClick={() => onFocusTask(task.id)}
                        title="채팅에서 이 할 일로 이동"
                      >
                        {task.title}
                      </button>
                    ) : (
                      <span className="task-row__title">{task.title}</span>
                    )}
                    {task.owner_agent ? (
                      <span className="task-row__owner">
                        <Avatar role={agentRole(task.owner_agent)} size={18} />
                      </span>
                    ) : (
                      <span
                        className={[
                          "task-row__owner",
                          "task-row__owner--open",
                          isClaimable || isUnassignedOpenTask(task)
                            ? "task-row__owner--claimable"
                            : undefined,
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        title={UNASSIGNED_OWNER_TOOLTIP}
                      >
                        {UNASSIGNED_OWNER_LABEL}
                      </span>
                    )}
                    <span
                      className={`task-row__status-badge task-row__status-badge--${statusKey}`}
                    >
                      {STATUS_BADGE[task.status] ?? task.status}
                    </span>
                    {task.status !== "completed" &&
                    task.status !== "cancelled" ? (
                      <span className="task-row__actions">
                        <span className="task-row__agree" title="팀 동의">
                          {formatTeamAgreementLabel(
                            agreeCount,
                            requiredAgreements,
                          )}
                        </span>
                        {task.plan_action_index != null && onFocusPlanAction ? (
                          <button
                            type="button"
                            className="btn btn--sm"
                            onClick={() =>
                              onFocusPlanAction(task.plan_action_index!)
                            }
                          >
                            plan #{task.plan_action_index}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="btn btn--sm btn--ok"
                          disabled={
                            busyTaskId === task.id || completeGate.blocked
                          }
                          title={completeGate.hint ?? undefined}
                          onClick={() => void markComplete(task.id)}
                        >
                          완료
                        </button>
                      </span>
                    ) : null}
                    {rowError ? (
                      <span className="task-row__error" role="alert">
                        {rowError}
                      </span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : !isDock ? (
            <div className="taskbar__empty">
              <p>{emptyCopy.message}</p>
              <p>{modeHint}</p>
            </div>
          ) : null}
        </div>

        {crossLinks.visible.length > 0 ? (
          <div
            className="taskbar__cross-links"
            role="navigation"
            aria-label="plan-task-execution links"
          >
            <span className="taskbar__cross-links-label">
              plan ↔ task ↔ execution
            </span>
            <ul className="taskbar__cross-links-list">
              {crossLinks.visible.map((link) => (
                <li key={link.taskId} className="taskbar__cross-link-row">
                  {onFocusPlanAction ? (
                    <button
                      type="button"
                      className="btn btn--sm btn--ghost"
                      onClick={() => onFocusPlanAction(link.planIndex)}
                    >
                      plan #{link.planIndex}
                    </button>
                  ) : (
                    <span>plan #{link.planIndex}</span>
                  )}
                  <span aria-hidden>↔</span>
                  {onFocusTask ? (
                    <button
                      type="button"
                      className="btn btn--sm btn--ghost"
                      onClick={() => onFocusTask(link.taskId)}
                    >
                      {link.taskId}
                    </button>
                  ) : (
                    <span>{link.taskId}</span>
                  )}
                  {link.execStatus ? (
                    <span className="badge badge--accent">
                      {link.execStatus}
                    </span>
                  ) : null}
                </li>
              ))}
              {crossLinks.hidden > 0 ? (
                <li className="taskbar__cross-link-more">
                  +{crossLinks.hidden} more
                </li>
              ) : null}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
