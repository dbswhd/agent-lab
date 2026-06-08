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
  formatTaskBarEmptyState,
  formatTaskBarModeHint,
  formatTeamAgreementLabel,
  LEAD_HELP_SUMMARY,
  resolveRequiredAgreements,
  resolveTaskBarMode,
  shouldShowConsensusBlocker,
  type TaskBarComposerVariant,
  TASK_BAR_AUTO_REFRESH_HINT,
  UNASSIGNED_OWNER_LABEL,
  UNASSIGNED_OWNER_TOOLTIP,
} from "../utils/taskBarCopy";
import { getTaskBarCollapsed, setTaskBarCollapsed } from "../utils/taskBarPrefs";
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
  onRefresh?: () => void;
  onFocusPlanAction?: (actionIndex: number) => void;
  onFocusTask?: (taskId: string) => void;
  onRequestComposerPrefill?: (text: string) => void;
};

type TaskSection = "tasks" | "objections" | "inbox" | "artifacts";

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

function artifactTypeClass(kind: string): string {
  const lower = kind.toLowerCase();
  if (lower.includes("pdf")) return "artifact-row__type--pdf";
  if (lower.includes("json")) return "artifact-row__type--json";
  if (lower.includes("ts") || lower.includes("typescript")) {
    return "artifact-row__type--ts";
  }
  return "";
}

function TaskbarListIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  );
}

function TaskbarChevronIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="15"
      height="15"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function TabIcon({ name }: { name: "list" | "alert" | "mail" | "doc" }) {
  const paths = {
    list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    alert: "M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z",
    mail: "M4 4h16v16H4V4zM4 8l8 5 8-5",
    doc: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM14 2v6h6",
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
  onRefresh,
  onFocusPlanAction,
  onFocusTask,
  onRequestComposerPrefill,
}: Props) {
  const [leadBusy, setLeadBusy] = useState(false);
  const [leadError, setLeadError] = useState<string | null>(null);
  const [section, setSection] = useState<TaskSection>("tasks");
  const [collapsed, setCollapsed] = useState(() => getTaskBarCollapsed());
  const [blockerCompleteBusy, setBlockerCompleteBusy] = useState(false);
  const [objectionBusyId, setObjectionBusyId] = useState<string | null>(null);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [completeErrors, setCompleteErrors] = useState<Record<string, string>>(
    {},
  );

  useEffect(() => {
    setTaskBarCollapsed(collapsed);
  }, [collapsed]);

  useEffect(() => {
    if (!focusObjection?.id) return;
    setCollapsed(false);
    setTaskBarCollapsed(false);
    setSection("objections");
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

  if (!payload) return null;
  const openObjections = payload.open_objections ?? [];
  const allObjections = payload.objections ?? openObjections;
  const openObjectionCount = payload.open_objection_count ?? openObjections.length;
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

  const mailbox = payload.mailbox ?? [];
  const mailboxUnread = payload.mailbox_unread ?? {};
  const unreadTotal = Object.values(mailboxUnread).reduce((a, b) => a + b, 0);
  const artifacts = payload.artifacts ?? [];

  const taskOpenCount =
    (payload.counts?.pending ?? 0) + (payload.counts?.in_progress ?? 0);
  const taskDoneCount = payload.counts?.completed ?? 0;
  const taskBlockedCount = showConsensusBlocker ? blockers.length : 0;
  const hasTaskbarAlert = openObjections.length > 0 || taskBlockedCount > 0;
  const isOpen = !collapsed;

  const sections: {
    id: TaskSection;
    icon: "list" | "alert" | "mail" | "doc";
    label: string;
    count: number;
    danger?: boolean;
    accent?: boolean;
  }[] = [
    {
      id: "tasks",
      icon: "list",
      label: "Room tasks",
      count: taskOpenCount,
      danger: taskBlockedCount > 0,
    },
    {
      id: "objections",
      icon: "alert",
      label: "이의",
      count: openObjections.length,
      danger: openObjections.length > 0,
    },
    {
      id: "inbox",
      icon: "mail",
      label: "받은함",
      count: unreadTotal,
      accent: unreadTotal > 0,
    },
    {
      id: "artifacts",
      icon: "doc",
      label: "산출물",
      count: artifacts.length,
    },
  ];

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

  return (
    <div
      className={[
        "taskbar",
        isOpen ? "is-open" : "",
        hasTaskbarAlert ? "taskbar--alert" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      role="region"
      aria-label="팀 할 일 목록"
    >
      <button
        type="button"
        className="taskbar__summary"
        aria-expanded={isOpen}
        onClick={() => setCollapsed((v) => !v)}
      >
        <span className="taskbar__title">
          <TaskbarListIcon />
          Room tasks
        </span>
        <span className="taskbar__counts">
          {taskOpenCount > 0 ? (
            <span className="badge badge--accent">{taskOpenCount} open</span>
          ) : null}
          {taskDoneCount > 0 ? (
            <span className="badge badge--ok">{taskDoneCount} done</span>
          ) : null}
          {taskBlockedCount > 0 ? (
            <span className="badge badge--danger">
              {taskBlockedCount} blocked
            </span>
          ) : null}
          {openObjections.length > 0 ? (
            <span className="badge badge--danger">
              <TabIcon name="alert" /> {openObjections.length}
            </span>
          ) : null}
          {unreadTotal > 0 ? (
            <span className="badge badge--accent">
              <TabIcon name="mail" /> {unreadTotal}
            </span>
          ) : null}
          {artifacts.length > 0 ? (
            <span className="badge">
              <TabIcon name="doc" /> {artifacts.length}
            </span>
          ) : null}
          <span className="taskbar__caret" aria-hidden>
            <TaskbarChevronIcon />
          </span>
        </span>
      </button>

      {isOpen ? (
        <div className="taskbar__body">
          <div className="taskbar__tabs" role="tablist" aria-label="Room tasks">
            {sections.map((s) => (
              <button
                key={s.id}
                type="button"
                role="tab"
                aria-selected={section === s.id}
                className={[
                  "taskbar__tab",
                  section === s.id ? "is-active" : "",
                  s.danger ? "taskbar__tab--danger" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => setSection(s.id)}
              >
                <TabIcon name={s.icon} />
                <span>{s.label}</span>
                {s.count > 0 ? (
                  <span
                    className={[
                      "taskbar__tab-badge",
                      s.danger ? "taskbar__tab-badge--danger" : "",
                      s.accent ? "taskbar__tab-badge--accent" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {s.count}
                  </span>
                ) : null}
              </button>
            ))}
          </div>

          <div className="taskbar__section">
            {section === "tasks" ? (
              <>
                <div className="taskbar-section-label taskbar-section-label--inline">
                  <label className="taskbar-lead-select" title={LEAD_HELP_SUMMARY}>
                    세션 리드
                    <select
                      value={payload.team_lead ?? "cursor"}
                      disabled={leadBusy || loading}
                      onChange={(e) => void changeLead(e.target.value)}
                    >
                      {LEAD_OPTIONS.map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                    </select>
                  </label>
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
                  </div>
                ) : null}
                {tasks.length === 0 ? (
                  <div className="taskbar__empty">
                    <p>{emptyCopy.message}</p>
                    <p>{modeHint}</p>
                  </div>
                ) : (
                  tasks.map((task) => {
                    const completeGate = taskCompleteGate(task, executions);
                    const agreeCount = endorsementCount(task);
                    const rowError = completeErrors[task.id];
                    const statusKey =
                      task.status === "cancelled" ? "blocked" : task.status;
                    return (
                      <div
                        key={task.id}
                        className={`task-row${statusKey === "blocked" ? " task-row--blocked" : ""}`}
                        data-task-id={task.id}
                      >
                        <span className={`task-row__dot task-row__dot--${statusKey}`} />
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
                            className="task-row__owner task-row__owner--open"
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
                            <span
                              className="task-row__agree"
                              title="팀 동의"
                            >
                              {formatTeamAgreementLabel(
                                agreeCount,
                                requiredAgreements,
                              )}
                            </span>
                            {task.plan_action_index != null &&
                            onFocusPlanAction ? (
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
                  })
                )}
              </>
            ) : null}

            {section === "objections" ? (
              <>
                {allObjections.length === 0 ? (
                  <div className="taskbar__empty">미해결 이의 없음</div>
                ) : (
                  allObjections.map((obj) => {
                    const isOpenObj = obj.status === "open";
                    return (
                      <div
                        key={obj.id}
                        className={`objection-row${!isOpenObj ? " objection-row--resolved" : ""}`}
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
                          {!isOpenObj ? (
                            <span className="badge badge--ok">해결됨</span>
                          ) : null}
                        </div>
                        <p className="objection-row__body">{obj.body}</p>
                        {isOpenObj ? (
                          <div className="objection-row__actions">
                            {obj.plan_action_index != null &&
                            onFocusPlanAction ? (
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
                              onClick={() =>
                                void resolveObjection(obj, "accepted")
                              }
                            >
                              수용
                            </button>
                            <button
                              type="button"
                              className="btn btn--sm"
                              disabled={objectionBusyId === obj.id}
                              onClick={() =>
                                void resolveObjection(obj, "wontfix")
                              }
                            >
                              기각
                            </button>
                          </div>
                        ) : null}
                      </div>
                    );
                  })
                )}
              </>
            ) : null}

            {section === "inbox" ? (
              <>
                {mailbox.length === 0 ? (
                  <div className="taskbar__empty">받은함이 비어 있습니다</div>
                ) : (
                  mailbox.map((m: MailboxMessage) => (
                    <div
                      key={m.id}
                      className={`inbox-row${m.read ? " inbox-row--resolved" : ""}`}
                    >
                      <div className="inbox-row__head">
                        <Avatar role={agentRole(m.from)} size={18} />
                        <span className="inbox-row__subject">
                          {m.from} → {m.to}
                        </span>
                        <span className="inbox-row__time">{m.ts}</span>
                      </div>
                      <p className="inbox-row__body">{m.body}</p>
                    </div>
                  ))
                )}
              </>
            ) : null}

            {section === "artifacts" ? (
              <>
                {artifacts.length === 0 ? (
                  <div className="taskbar__empty">산출물 없음</div>
                ) : (
                  artifacts.map((a: RoomArtifact) => (
                    <div key={a.id} className="artifact-row">
                      <span
                        className={`artifact-row__type ${artifactTypeClass(a.kind)}`.trim()}
                      >
                        {a.kind}
                      </span>
                      <div className="artifact-row__main">
                        <span className="artifact-row__name">
                          {a.path ?? a.summary ?? a.id}
                        </span>
                        <span className="artifact-row__meta">
                          {a.producer}
                          {a.ts ? ` · ${a.ts}` : ""}
                        </span>
                      </div>
                      <Avatar role={agentRole(a.producer)} size={18} />
                    </div>
                  ))
                )}
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
