import { useState } from "react";
import {
  completeSessionTask,
  patchSessionTeamLead,
  type PlanExecutionRecord,
  type RoomTask,
  type RoomTasksPayload,
} from "../api/client";
import { parseApiErrorDetail } from "../utils/apiError";

type Props = {
  sessionId: string;
  payload: RoomTasksPayload | null;
  loading?: boolean;
  executions?: PlanExecutionRecord[];
  onRefresh?: () => void;
  onFocusPlanAction?: (actionIndex: number) => void;
  onFocusTask?: (taskId: string) => void;
};

const SESSION_LEAD_HELP =
  "세션 리드: 룸 전체 기본값. 아래 select로 바꿀 수 있습니다.";
const TURN_LEAD_HELP =
  "이번 턴 리드: 메시지에 GO codex / 리드: claude 등이 있으면 그 에이전트, 없으면 턴별 자동 회전.";

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
  const history = keys.slice(0, 6).map((t) => ({
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

function endorsementCount(task: RoomTask): number {
  return Object.keys(task.endorsements ?? {}).length;
}

function TaskRows({
  tasks,
  showOwner = true,
  sessionId,
  executions,
  onRefresh,
  onFocusPlanAction,
}: {
  tasks: RoomTask[];
  showOwner?: boolean;
  sessionId: string;
  executions?: PlanExecutionRecord[];
  onRefresh?: () => void;
  onFocusPlanAction?: (actionIndex: number) => void;
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

  return (
    <ul className="room-task-bar__list">
      {tasks.map((t) => {
        const completeGate = taskCompleteGate(t, executions);
        const rowError = completeErrors[t.id];
        return (
          <li
            key={t.id}
            data-task-id={t.id}
            className={`room-task-bar__item room-task-bar__item--${t.status}`}
          >
            <span className="room-task-bar__status">
              {STATUS_LABEL[t.status] ?? t.status}
            </span>
            <span className="room-task-bar__title-text">{t.title}</span>
            {showOwner && t.owner_agent ? (
              <span className="room-task-bar__owner">@{t.owner_agent}</span>
            ) : null}
            {showOwner && !t.owner_agent ? (
              <span
                className="room-task-bar__owner room-task-bar__owner--open"
                title="토론 턴은 자동 배정 없음 — plan·합의 턴에서 owner가 붙습니다"
              >
                미배정
              </span>
            ) : null}
            {t.status !== "completed" && t.status !== "cancelled" ? (
              <span className="room-task-bar__endorse" title="팀 ENDORSE 수">
                ✓{endorsementCount(t)}
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
  loading,
  executions,
  onRefresh,
  onFocusPlanAction,
  onFocusTask,
}: Props) {
  const [leadBusy, setLeadBusy] = useState(false);
  const [leadError, setLeadError] = useState<string | null>(null);

  if (!payload) return null;
  const tasks = payload.tasks ?? [];
  const claimable = payload.claimable ?? [];
  if (tasks.length === 0 && claimable.length === 0 && !loading) return null;

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

  const blockers = payload.consensus_task_blockers ?? [];
  const tasksReady = payload.consensus_tasks_ready !== false;
  const { currentTurnLead, history: turnLeadHistory } = formatTurnLeads(
    payload.turn_leads,
    payload.team_lead ?? "cursor",
  );
  const linkedRows = tasks
    .filter((t) => t.plan_action_index != null || t.plan_action_id)
    .map((t) => ({ task: t, link: linkedExecutionRow(t, executions) }))
    .filter((r) => r.link.planIndex != null || r.link.status);
  const linkedVisible = linkedRows.slice(0, 5);
  const linkedOverflow = linkedRows.length - linkedVisible.length;

  return (
    <div className="room-task-bar" role="region" aria-label="공유 작업 목록">
      <div className="room-task-bar__head">
        <strong className="room-task-bar__title">작업</strong>
        <span className="room-task-bar__turn-lead" title={TURN_LEAD_HELP}>
          이번 턴 리드 <strong>{currentTurnLead}</strong>
        </span>
        <label
          className="room-task-bar__lead-select"
          title={SESSION_LEAD_HELP}
        >
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
        </span>
        {onRefresh ? (
          <button
            type="button"
            className="room-task-bar__refresh"
            onClick={onRefresh}
            disabled={loading}
          >
            새로고침
          </button>
        ) : null}
      </div>
      <p id="room-task-bar-lead-help" className="room-task-bar__lead-help">
        {SESSION_LEAD_HELP} {TURN_LEAD_HELP}
      </p>
      {leadError ? (
        <p className="room-task-bar__lead-error" role="alert">
          {leadError}
        </p>
      ) : null}
      {turnLeadHistory.length > 0 ? (
        <p className="room-task-bar__turn-leads-history" title="턴 리드 기록">
          턴 리드:{" "}
          {turnLeadHistory.map(({ turn, agent }) => (
            <span key={turn} className="room-task-bar__turn-lead-chip">
              T{turn}→{agent}
            </span>
          ))}
        </p>
      ) : null}
      {!tasksReady && blockers.length > 0 ? (
        <p className="room-task-bar__blocker" role="status">
          합의 대기: 열린 작업에 팀 ENDORSE 부족 —{" "}
          {blockers.slice(0, 3).map((id, i) => (
            <span key={id}>
              {i > 0 ? ", " : null}
              {onFocusTask ? (
                <button
                  type="button"
                  className="room-task-bar__blocker-link"
                  onClick={() => onFocusTask(id)}
                >
                  {id}
                </button>
              ) : (
                id
              )}
            </span>
          ))}
          {blockers.length > 3 ? ` 외 ${blockers.length - 3}건` : ""}
        </p>
      ) : null}
      {tasks.length === 0 ? (
        <p className="room-task-bar__empty">
          아직 작업이 없습니다. 에이전트가 `[PROPOSED: …]`로 제안하면 자동
          추가됩니다. 토론 턴에는 담당 배정이 없고, plan·합의 턴에서 owner가
          붙습니다.
        </p>
      ) : (
        <TaskRows
          tasks={tasks}
          sessionId={sessionId}
          executions={executions}
          onRefresh={onRefresh}
          onFocusPlanAction={onFocusPlanAction}
        />
      )}
      {claimable.length > 0 ? (
        <div className="room-task-bar__claimable">
          <span
            className="room-task-bar__claimable-label"
            title="에이전트가 claim API로 가져갈 수 있는 미배정 작업"
          >
            청구 가능
          </span>
          <TaskRows
            tasks={claimable}
            showOwner={false}
            sessionId={sessionId}
            executions={executions}
            onRefresh={onRefresh}
            onFocusPlanAction={onFocusPlanAction}
          />
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
