import type {
  AgentHealthRow,
  MissionLoopState,
  PlanExecutionRecord,
  ReadinessResponse,
} from "../api/client";
import { messageLooksLikeLoopReadinessFailure } from "./roomRunErrors";

export type RecoveryKind =
  | "auth_expired"
  | "bridge_failed"
  | "run_lock"
  | "run_failed"
  | "partial_turn"
  | "oracle_fail"
  | "discuss_recovery";

export type RecoverySeverity =
  | "blocking_execute"
  | "blocking_send"
  | "degraded_team"
  | "informational";

export type RecoveryFailureSource =
  | "transport"
  | "run"
  | "agent"
  | "execute"
  | "command";

export type RecoveryFailureKind =
  | "partial_turn"
  | "run_lock"
  | "api_validation"
  | "loop_readiness"
  | "api_offline";

export type RecoveryFailure = {
  readonly source: RecoveryFailureSource;
  readonly message: string;
  readonly kind?: RecoveryFailureKind;
  readonly affectedAgentIds?: readonly string[];
};

/** Classify send failures — 422 validation vs run lock vs offline vs generic run. */
export function classifySendFailure(message: string): {
  source: RecoveryFailureSource;
  kind?: RecoveryFailureKind;
} {
  const detail = message.trim();
  const lower = detail.toLowerCase();
  if (
    lower.includes("already in progress") ||
    lower.includes("run lock") ||
    lower.includes("run_lock")
  ) {
    return { source: "run", kind: "run_lock" };
  }
  if (
    lower.includes("loop requires plan") ||
    lower.includes("agents not ready") ||
    messageLooksLikeLoopReadinessFailure(detail) ||
    /\b422\b/.test(lower) ||
    lower.includes("validation error") ||
    lower.includes("unprocessable")
  ) {
    if (messageLooksLikeLoopReadinessFailure(detail)) {
      return { source: "run", kind: "loop_readiness" };
    }
    return { source: "run", kind: "api_validation" };
  }
  if (isTransportFailure(detail)) {
    return { source: "transport", kind: "api_offline" };
  }
  return { source: "run" };
}

/** True only for network/proxy failures — not HTTP 4xx validation from the API. */
export function isTransportFailure(message: string): boolean {
  const m = message.trim().toLowerCase();
  if (!m) return true;
  if (m.includes("loop requires plan") || m.includes("agents not ready")) {
    return false;
  }
  return (
    m.includes("failed to fetch") ||
    m.includes("networkerror") ||
    m.includes("network request failed") ||
    m.includes("load failed") ||
    m.includes("api(8765) reconnecting") ||
    m.includes("api_offline") ||
    m.includes("etimedout") ||
    m.includes("econnrefused") ||
    m.includes("sse 연결")
  );
}

export type RecoveryActionId =
  | "open_settings"
  | "refresh_health"
  | "reconnect_cursor"
  | "reconnect_claude"
  | "reconnect_codex"
  | "reconnect_kimi_work"
  | "release_lock"
  | "retry_failed_agents"
  | "open_work"
  | "open_inbox"
  | "run_discuss_recovery";

export type RecoveryAction = {
  readonly id: RecoveryActionId;
  readonly label: string;
};

export type RecoveryItem = {
  readonly kind: RecoveryKind;
  readonly severity: RecoverySeverity;
  readonly title: string;
  readonly reason: string;
  readonly details?: string;
  readonly source: "health" | "readiness" | "run" | "execute" | "mission";
  readonly affectedAgentIds?: readonly string[];
  readonly primaryAction: RecoveryAction;
  readonly secondaryAction?: RecoveryAction;
};

export type RecoveryItemsInput = {
  readonly apiOk: boolean;
  readonly agents: readonly AgentHealthRow[];
  readonly readiness: ReadinessResponse | null;
  readonly failure: RecoveryFailure | null;
  readonly selectedAgentIds: readonly string[];
  readonly runLockStuck: boolean;
  readonly discussRecovery:
    | MissionLoopState["discuss_recovery"]
    | null
    | undefined;
  readonly executions: readonly PlanExecutionRecord[];
};

const SEVERITY_RANK: Record<RecoverySeverity, number> = {
  blocking_execute: 0,
  blocking_send: 1,
  degraded_team: 2,
  informational: 3,
};

function readableAgentName(row: AgentHealthRow): string {
  return row.label || row.id;
}

function statusDetail(row: AgentHealthRow): string {
  return (
    row.reason ??
    row.hint ??
    row.detail ??
    row.failure_code ??
    row.model ??
    "상태 세부 정보가 없습니다."
  );
}

function textLooksAuthRelated(text: string): boolean {
  const normalized = text.toLowerCase();
  return (
    normalized.includes("auth") ||
    normalized.includes("login") ||
    normalized.includes("oauth") ||
    normalized.includes("token") ||
    normalized.includes("credential") ||
    normalized.includes("unauthorized") ||
    normalized.includes("인증") ||
    normalized.includes("로그인")
  );
}

function agentLooksAuthExpired(row: AgentHealthRow): boolean {
  if (row.ready) return false;
  const detail = [
    row.reason,
    row.hint,
    row.detail,
    row.failure_code,
    ...(row.remediation ?? []),
  ]
    .filter((part): part is string => Boolean(part?.trim()))
    .join(" ");
  if (textLooksAuthRelated(detail)) return true;
  return row.configured && row.id !== "cursor" && !row.ready;
}

function authAction(row: AgentHealthRow): RecoveryAction {
  if (row.id === "claude") {
    return { id: "reconnect_claude", label: "Claude 재로그인" };
  }
  if (row.id === "codex") {
    return { id: "reconnect_codex", label: "Codex 재로그인" };
  }
  return { id: "open_settings", label: "Settings 열기" };
}

function failedBridgeRows(agents: readonly AgentHealthRow[]): AgentHealthRow[] {
  return agents.filter(
    (row) =>
      row.id === "cursor" &&
      (row.bridge === "error" || row.degraded === true || !row.ready),
  );
}

function failedKimiWorkBridgeRows(
  agents: readonly AgentHealthRow[],
): AgentHealthRow[] {
  return agents.filter(
    (row) =>
      row.id === "kimi_work" &&
      row.configured &&
      (row.bridge === "error" || row.degraded === true || !row.ready),
  );
}

function oracleVerdict(row: PlanExecutionRecord): string {
  return String(
    row.verify_after_merge?.oracle?.verdict ??
      row.verify_after_merge?.status ??
      row.oracle?.verdict ??
      row.oracle_verdict ??
      "",
  ).toLowerCase();
}

function oracleDetail(row: PlanExecutionRecord): string {
  return String(
    row.verify_after_merge?.oracle?.detail ??
      row.oracle?.detail ??
      row.status ??
      "Oracle verification failed.",
  );
}

function latestOracleFailure(
  executions: readonly PlanExecutionRecord[],
): PlanExecutionRecord | null {
  const rows = [...executions].reverse();
  return (
    rows.find((row) => {
      const verdict = oracleVerdict(row);
      return verdict === "fail" || verdict === "failed";
    }) ?? null
  );
}

function buildFailureItem(
  failure: RecoveryFailure | null,
): RecoveryItem | null {
  if (!failure) return null;
  const trimmed = failure.message.trim();
  if (!trimmed) return null;
  if (trimmed.includes("already in progress")) return null;
  if (textLooksAuthRelated(trimmed)) return null;
  if (failure.kind === "run_lock") {
    return {
      kind: "run_lock",
      severity: "blocking_send",
      title: "이전 실행 잠금이 남아 있습니다.",
      reason: "새 턴을 시작하기 전에 stale/orphan run lock을 해제해야 합니다.",
      details: trimmed,
      source: "run",
      primaryAction: { id: "release_lock", label: "실행 잠금 해제" },
      secondaryAction: { id: "refresh_health", label: "상태 재확인" },
    };
  }
  if (failure.kind === "loop_readiness") {
    return {
      kind: "run_failed",
      severity: "blocking_send",
      title: "Loop 모드 전송이 차단되었습니다.",
      reason:
        "선택한 agent 중 Loop capability probe에 실패한 peer가 있습니다. 아래 미충족 항목과 조치를 확인하세요.",
      details: trimmed,
      source: "run",
      affectedAgentIds: failure.affectedAgentIds,
      primaryAction: { id: "refresh_health", label: "상태 재확인" },
      secondaryAction: { id: "reconnect_kimi_work", label: "Kimi Work Bridge" },
    };
  }
  if (failure.kind === "api_validation") {
    return {
      kind: "run_failed",
      severity: "blocking_send",
      title: "요청 형식이 서버에서 거부되었습니다.",
      reason:
        "Room preset·모드 조합이 API 규칙과 맞지 않을 수 있습니다. 메시지를 확인하거나 preset을 바꿔 보세요.",
      details: trimmed,
      source: "run",
      primaryAction: { id: "refresh_health", label: "상태 재확인" },
    };
  }
  if (failure.kind === "api_offline" || failure.source === "transport") {
    return {
      kind: "run_failed",
      severity: "blocking_send",
      title: "Agent Lab API에 연결할 수 없습니다.",
      reason: "API(8765) 또는 dev proxy 상태를 확인한 뒤 다시 시도하세요.",
      details: trimmed,
      source: "run",
      primaryAction: { id: "refresh_health", label: "상태 재확인" },
      secondaryAction: { id: "open_settings", label: "Settings 열기" },
    };
  }
  if (failure.kind !== "partial_turn") {
    return {
      kind: "run_failed",
      severity: "blocking_send",
      title:
        failure.source === "execute"
          ? "실행을 완료하지 못했습니다."
          : "요청을 완료하지 못했습니다.",
      reason:
        trimmed && trimmed !== "run failed"
          ? trimmed
          : "세부 원인을 확인한 뒤 다시 시도할 수 있습니다.",
      details: trimmed,
      source: failure.source === "execute" ? "execute" : "run",
      affectedAgentIds: failure.affectedAgentIds,
      primaryAction:
        failure.source === "execute"
          ? { id: "open_work", label: "Work 열기" }
          : { id: "refresh_health", label: "상태 재확인" },
    };
  }
  return {
    kind: "partial_turn",
    severity: "blocking_send",
    title: "최근 턴이 완전히 끝나지 않았습니다.",
    reason:
      "성공한 에이전트 답변은 유지됩니다. 실패 원인을 확인한 뒤 이어서 전송할 수 있습니다.",
    details: trimmed,
    source: "run",
    affectedAgentIds: failure.affectedAgentIds,
    primaryAction: {
      id: "retry_failed_agents",
      label: "실패한 에이전트만 재시도",
    },
    secondaryAction: { id: "refresh_health", label: "상태 재확인" },
  };
}

export function buildRecoveryItems(
  input: RecoveryItemsInput,
): readonly RecoveryItem[] {
  const items: RecoveryItem[] = [];
  const selected = new Set(input.selectedAgentIds);
  const relevantAgents = input.agents.filter(
    (row) => selected.size === 0 || selected.has(row.id),
  );

  if (!input.apiOk) {
    items.push({
      kind: "auth_expired",
      severity: "blocking_send",
      title: "Agent Lab API에 연결할 수 없습니다.",
      reason:
        "세션과 에이전트 상태를 확인할 수 없어 새 턴을 시작할 수 없습니다.",
      details: input.failure?.message ?? "API(8765) 연결 상태를 확인하세요.",
      source: "health",
      primaryAction: { id: "open_settings", label: "Settings 열기" },
      secondaryAction: { id: "refresh_health", label: "상태 재확인" },
    });
  }

  for (const row of relevantAgents.filter(agentLooksAuthExpired)) {
    items.push({
      kind: "auth_expired",
      severity: "blocking_send",
      title: `${readableAgentName(row)} 인증이 필요합니다.`,
      reason: "이 에이전트를 포함한 Room 턴은 인증을 다시 확인해야 진행됩니다.",
      details: statusDetail(row),
      source: "health",
      affectedAgentIds: [row.id],
      primaryAction: authAction(row),
      secondaryAction: { id: "refresh_health", label: "상태 재확인" },
    });
  }

  for (const row of failedBridgeRows(relevantAgents)) {
    items.push({
      kind: "bridge_failed",
      severity: row.ready ? "degraded_team" : "blocking_send",
      title: "Cursor bridge 연결을 확인해야 합니다.",
      reason: row.ready
        ? "Cursor가 degraded 상태입니다. 실행 전 bridge 상태를 재확인하세요."
        : "Cursor가 준비되지 않아 Cursor 포함 턴이 막힐 수 있습니다.",
      details: statusDetail(row),
      source: "health",
      affectedAgentIds: [row.id],
      primaryAction: { id: "reconnect_cursor", label: "Bridge 재연결" },
      secondaryAction: { id: "open_settings", label: "Settings 열기" },
    });
  }

  for (const row of failedKimiWorkBridgeRows(relevantAgents)) {
    items.push({
      kind: "bridge_failed",
      severity: row.ready ? "degraded_team" : "blocking_send",
      title: "Kimi Work bridge 연결을 확인해야 합니다.",
      reason: row.ready
        ? "Kimi Work가 degraded 상태입니다. 실행 전 bridge 상태를 재확인하세요."
        : "Kimi Work daimon에 연결되지 않아 Kimi Work 포함 턴이 실패할 수 있습니다.",
      details: statusDetail(row),
      source: "health",
      affectedAgentIds: [row.id],
      primaryAction: { id: "reconnect_kimi_work", label: "Bridge 재연결" },
      secondaryAction: { id: "refresh_health", label: "상태 재확인" },
    });
  }

  if (input.runLockStuck) {
    items.push({
      kind: "run_lock",
      severity: "blocking_send",
      title: "이전 실행 잠금이 남아 있습니다.",
      reason: "새 턴을 시작하기 전에 stale/orphan run lock을 해제해야 합니다.",
      details:
        input.failure?.message ?? "이미 실행 중이라는 응답을 받았습니다.",
      source: "run",
      primaryAction: { id: "release_lock", label: "실행 잠금 해제" },
      secondaryAction: { id: "refresh_health", label: "상태 재확인" },
    });
  }

  const runErrorItem = buildFailureItem(input.failure);
  if (runErrorItem) items.push(runErrorItem);

  const oracleFailure = latestOracleFailure(input.executions);
  if (oracleFailure) {
    items.push({
      kind: "oracle_fail",
      severity: "blocking_execute",
      title: `Oracle 검증 실패 · ${oracleFailure.action_index ?? "?"}`,
      reason:
        "완료로 볼 수 없습니다. Work에서 재검증 또는 repair 흐름을 선택하세요.",
      details: oracleDetail(oracleFailure),
      source: "execute",
      primaryAction: { id: "open_work", label: "Work 열기" },
      secondaryAction: { id: "open_inbox", label: "Inbox 확인" },
    });
  }

  if (input.discussRecovery?.pending) {
    items.push({
      kind: "discuss_recovery",
      severity: "blocking_execute",
      title: "Discuss recovery가 필요합니다.",
      reason:
        "Verify/repair 한도에 도달했습니다. 회복 라운드로 plan을 다시 정리해야 합니다.",
      details: input.discussRecovery.reason ?? undefined,
      source: "mission",
      primaryAction: { id: "run_discuss_recovery", label: "Recovery 실행" },
      secondaryAction: { id: "open_inbox", label: "Discuss Inbox" },
    });
  }

  const readinessBlocked = input.readiness?.verdict === "blocked";
  if (readinessBlocked && items.length === 0) {
    items.push({
      kind: "partial_turn",
      severity: "blocking_send",
      title: "전송 전에 연결 확인이 필요합니다.",
      reason:
        input.readiness?.next_actions[0] ?? "준비 상태를 확인해야 합니다.",
      details: input.readiness?.checks
        .filter((check) => !check.ok)
        .map(
          (check) => `${check.id}: ${check.detail ?? check.next ?? "blocked"}`,
        )
        .join("\n"),
      source: "readiness",
      primaryAction: { id: "open_settings", label: "Settings 열기" },
      secondaryAction: { id: "refresh_health", label: "상태 재확인" },
    });
  }

  return items.sort(
    (left, right) =>
      SEVERITY_RANK[left.severity] - SEVERITY_RANK[right.severity],
  );
}
