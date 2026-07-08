import type {
  ConsensusGatePayload,
  RoomTask,
  RoomTasksPayload,
  PlanExecutionRecord,
} from "../api/client";
import type { ComposerTurnProfile } from "./turnProfile";

export type TaskBarComposerVariant = "discuss" | "plan" | "consensus";

export type TaskBarMode =
  | "discuss"
  | "team"
  | "loop"
  | "analyze"
  | "quick"
  | "consensus"
  | "plan"
  | "specialist";

/** Matches backend `consensus_tasks_ready` (majority of active agents). */
export function requiredTeamAgreements(activeAgentCount: number): number {
  if (activeAgentCount <= 0) return 1;
  return Math.max(1, activeAgentCount - 1);
}

function activeAgentCount(agents: string[] | undefined): number {
  const n = (agents ?? []).filter((a) => String(a).trim()).length;
  return n > 0 ? n : 3;
}

export function resolveRequiredAgreements(
  payload: RoomTasksPayload | null,
): number {
  const gate = payload?.consensus_gate;
  if (gate && gate.required_endorsements > 0) {
    return gate.required_endorsements;
  }
  return requiredTeamAgreements(activeAgentCount(payload?.agents));
}

export function resolveTaskBarMode(
  composerVariant: TaskBarComposerVariant,
  turnProfile: ComposerTurnProfile,
): TaskBarMode {
  if (composerVariant === "consensus") return "consensus";
  if (composerVariant === "plan") return "plan";
  if (turnProfile === "quick") return "quick";
  return "loop";
}

export function lastTurnHadConsensusMode(
  run: Record<string, unknown> | undefined,
): boolean {
  if (!run) return false;
  const last = run.last_turn as { consensus_mode?: boolean } | undefined;
  if (last?.consensus_mode) return true;
  const turns = run.turns;
  if (!Array.isArray(turns) || turns.length === 0) return false;
  const tail = turns[turns.length - 1] as { consensus_mode?: boolean };
  return Boolean(tail?.consensus_mode);
}

export function shouldShowConsensusBlocker(
  payload: RoomTasksPayload,
  mode: TaskBarMode,
  lastTurnHadConsensus: boolean,
): boolean {
  const blockers = payload.consensus_task_blockers ?? [];
  if (payload.consensus_tasks_ready !== false) return false;
  if (blockers.length === 0) return false;
  if (mode === "consensus") return true;
  if (lastTurnHadConsensus) return true;
  return false;
}

export function shouldShowTurnLeadDetails(mode: TaskBarMode): boolean {
  return mode === "consensus" || mode === "plan";
}

export function formatTaskBarModeHint(
  mode: TaskBarMode,
  opts: {
    taskCount: number;
    openCount: number;
    selectedAgentCount: number;
  },
): string {
  const { taskCount, openCount, selectedAgentCount } = opts;
  switch (mode) {
    case "consensus":
      return openCount > 0
        ? `♾️ 합의 모드 · 열린 할 일 ${openCount}건 · 동의가 채워져야 합의가 끝납니다`
        : "♾️ 합의 모드 · 할 일 동의가 필요할 때만 아래에 표시됩니다";
    case "plan":
      return taskCount > 0
        ? `plan 탭 · 할 일 ${taskCount}건 · 실행 연결`
        : "plan 탭 · 문서·실행은 여기서";
    case "team":
    case "analyze":
      return selectedAgentCount > 1
        ? `팀 · ${selectedAgentCount}명 병렬 · 할 일은 [PROPOSED:] 제안만 (자동 배정 없음)`
        : "팀 · R1 · 할 일은 제안만 쌓입니다";
    case "quick":
      return "빠른 · 1명 · 할 일 제안은 가능하지만 자동 배정 없음";
    case "loop":
      return "루프 · plan/execute/verify 게이트 · 팀 동의와 검증을 기다립니다";
    default:
      return taskCount > 0
        ? `토론 · 제안된 할 일 ${taskCount}건 · 담당 자동 배정 없음`
        : "토론 · [PROPOSED:] 제안 시 할 일이 쌓입니다 · 담당 자동 배정 없음";
  }
}

export function endorsementCount(task: RoomTask): number {
  return Object.keys(task.endorsements ?? {}).length;
}

export function formatTeamAgreementLabel(
  current: number,
  required: number,
): string {
  return `동의 ${current}/${required}`;
}

export function taskMatchesBlockerRef(task: RoomTask, ref: string): boolean {
  const r = ref.trim();
  return task.id === r || task.title === r;
}

export function findTaskByBlockerRef(
  tasks: RoomTask[],
  ref: string,
): RoomTask | undefined {
  return tasks.find((t) => taskMatchesBlockerRef(t, ref));
}

export function formatTurnLeadLabel(turn: string, agent: string): string {
  return `${turn}번째 질문 · 리드 ${agent}`;
}

export const LEAD_HELP_TOGGLE_LABEL = "리드 안내";
export const LEAD_HELP_SUMMARY =
  "세션 리드는 룸 기본값, 이번 턴 리드는 GO/리드 지정 또는 턴별 자동 회전입니다.";
export const LEAD_HELP_DETAIL = [
  "세션 리드: 룸 전체 기본값. 아래 선택 상자에서 바꿀 수 있습니다.",
  "이번 턴 리드: 메시지에 GO codex / 리드: claude 가 있으면 그 에이전트, 없으면 선택된 에이전트 순서로 돌아갑니다.",
].join(" ");

export const UNASSIGNED_OWNER_LABEL = "담당 없음";
export const UNASSIGNED_OWNER_TOOLTIP =
  "에이전트가 가져가거나, plan·합의 턴에서 담당이 붙습니다. 토론만 할 때는 자동 배정하지 않습니다.";

export const TASK_BAR_AUTO_REFRESH_HINT = "턴마다 자동 갱신";

export function formatConsensusBlockerCopy(
  blockers: string[],
  tasks: RoomTask[],
  required: number,
  gate?: ConsensusGatePayload,
): { headline: string; detail: string } {
  if (blockers.length === 0) {
    return { headline: "", detail: "" };
  }
  const gateBlocked = gate?.blocked_tasks ?? [];
  const firstGate = gateBlocked[0];
  const firstRef = blockers[0];
  const firstTask = findTaskByBlockerRef(tasks, firstRef);
  const title = firstGate?.title ?? firstTask?.title ?? firstRef;
  const current =
    firstGate?.endorsements ?? (firstTask ? endorsementCount(firstTask) : 0);

  if (blockers.length === 1) {
    return {
      headline: `「${title}」에 팀 동의가 더 필요해요 (${current}/${required})`,
      detail:
        "에이전트가 채팅에서 이 할 일을 ref로 동의하면 숫자가 올라갑니다. 더 이상 필요 없으면 아래 [완료]로 닫을 수 있어요.",
    };
  }
  return {
    headline: `열린 할 일 ${blockers.length}건에 팀 동의가 부족해요 (각 ${required}명 중)`,
    detail:
      "♾️ 합의가 끝나려면 열린 할 일마다 팀 동의가 채워져야 합니다. 필요 없는 항목은 [완료]로 닫을 수 있어요.",
  };
}

export function isUnassignedOpenTask(task: RoomTask): boolean {
  return (
    !task.owner_agent &&
    (task.status === "pending" || task.status === "in_progress")
  );
}

export type TaskCrossLink = {
  taskId: string;
  planIndex: number;
  execStatus: string | null;
};

function latestExecutionForTask(
  task: RoomTask,
  executions: PlanExecutionRecord[] | undefined,
): PlanExecutionRecord | null {
  if (!executions?.length) return null;
  for (let i = executions.length - 1; i >= 0; i -= 1) {
    const ex = executions[i];
    const match =
      (task.plan_action_index != null &&
        ex.action_index === task.plan_action_index) ||
      (task.plan_action_id != null && ex.action_id === task.plan_action_id);
    if (match) return ex;
  }
  return null;
}

/** plan #N ↔ task ↔ execution status rows for taskbar footer (D7). */
export function buildTaskCrossLinks(
  tasks: RoomTask[],
  executions: PlanExecutionRecord[] | undefined,
  maxVisible = 5,
): { visible: TaskCrossLink[]; hidden: number } {
  const rows: TaskCrossLink[] = [];
  for (const task of tasks) {
    if (task.plan_action_index == null) continue;
    const ex = latestExecutionForTask(task, executions);
    rows.push({
      taskId: task.id,
      planIndex: task.plan_action_index,
      execStatus: ex?.status ?? null,
    });
  }
  return {
    visible: rows.slice(0, maxVisible),
    hidden: Math.max(0, rows.length - maxVisible),
  };
}

export type ChatSearchLine = {
  content?: string;
  body?: string;
};

export function messageMentionsTask(
  text: string,
  task: { id: string; title: string },
): boolean {
  const raw = (text ?? "").toLowerCase();
  if (!raw) return false;
  const id = task.id.trim();
  const title = task.title.trim();
  if (id && raw.includes(id.toLowerCase())) return true;
  if (title && raw.includes(title.toLowerCase())) return true;
  if (title && raw.includes(`[proposed: ${title.toLowerCase()}`)) return true;
  if (title && raw.includes(`[proposed:${title.toLowerCase()}`)) return true;
  return false;
}

/** Find latest chat.jsonl line mentioning a task (id, title, or [PROPOSED:]). */
export function findChatLineIndexForTask(
  lines: ChatSearchLine[],
  task: { id: string; title: string },
): number | null {
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const text = lines[i].content ?? lines[i].body ?? "";
    if (messageMentionsTask(text, task)) return i;
  }
  return null;
}

export function buildEndorsementRequestPrefill(task: {
  id: string;
  title: string;
}): string {
  const title = task.title.trim() || task.id;
  return `「${title}」 할 일(id: ${task.id})에 팀 동의가 더 필요합니다. 각자 envelope JSON에서 act: ENDORSE, refs에 "${task.id}" 또는 제목을 넣어 동의해 주세요.`;
}

export function formatTaskBarEmptyState(mode: TaskBarMode): {
  message: string;
  example: string;
} {
  switch (mode) {
    case "consensus":
      return {
        message:
          "♾️ 합의 중 제안된 할 일이 여기에 쌓입니다. 팀 동의가 채워져야 합의가 끝납니다.",
        example:
          "예: 에이전트가 [PROPOSED: 다음 검증] 이라고 쓰면 항목이 생깁니다.",
      };
    case "plan":
      return {
        message: "plan 정리 턴에서 나온 할 일이 plan 실행과 연결됩니다.",
        example: "예: [PROPOSED: API 스키마 확정] → plan #2와 연결",
      };
    case "team":
    case "analyze":
      return {
        message:
          "팀 턴에서는 할 일을 제안만 하고, 담당은 자동으로 붙지 않습니다.",
        example: "예: [PROPOSED: 현황 요약]",
      };
    case "quick":
      return {
        message: "빠른 모드에서도 [PROPOSED:] 제안은 할 일로 쌓일 수 있습니다.",
        example: "예: [PROPOSED: 버그 재현 확인]",
      };
    case "loop":
      return {
        message:
          "루프에서는 plan/execute/verify로 이어질 수 있는 할 일이 게이트와 연결됩니다.",
        example: "예: [PROPOSED: 검증 자동화]",
      };
    default:
      return {
        message:
          "토론 중 에이전트가 [PROPOSED: …]로 적으면 할 일이 자동으로 추가됩니다.",
        example: "예: [PROPOSED: 다음 검증]",
      };
  }
}

export function focusComposerInput(): void {
  requestAnimationFrame(() => {
    const el = document.querySelector<HTMLTextAreaElement>(".composer-input");
    if (!el) return;
    el.focus();
    const len = el.value.length;
    el.setSelectionRange(len, len);
  });
}

export function formatTaskBarCollapsedSummary(opts: {
  pending: number;
  inProgress: number;
  blockedCount: number;
  taskCount: number;
  currentTurnLead?: string;
}): string {
  const parts = [`할 일 ${opts.taskCount}`];
  if (opts.blockedCount > 0) {
    parts.push(`막힘 ${opts.blockedCount}`);
  } else if (opts.pending > 0) {
    parts.push(`대기 ${opts.pending}`);
  } else if (opts.inProgress > 0) {
    parts.push(`진행 ${opts.inProgress}`);
  }
  if (opts.currentTurnLead) {
    parts.push(`리드 ${opts.currentTurnLead}`);
  }
  return parts.join(" · ");
}
