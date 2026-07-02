export type RoomRunAgentDetail = {
  readonly id?: string;
  readonly loop_ready?: boolean;
  readonly loop_blockers?: readonly string[];
  readonly blocker_labels?: readonly string[];
  readonly model_id?: string | null;
  readonly summary?: string;
  readonly reason?: string;
};

export type RoomRunErrorDetail = {
  readonly code?: string;
  readonly message?: string;
  readonly reason?: string;
  readonly hint?: string | null;
  readonly topology?: string;
  readonly requested_agents?: readonly string[];
  readonly agents?: readonly (string | RoomRunAgentDetail)[];
  readonly agent_details?: readonly RoomRunAgentDetail[];
};

export function isLoopReadinessDetail(
  detail: unknown,
): detail is RoomRunErrorDetail {
  if (!detail || typeof detail !== "object") return false;
  const code = (detail as RoomRunErrorDetail).code;
  const message = (detail as RoomRunErrorDetail).message ?? "";
  const reason = (detail as RoomRunErrorDetail).reason ?? "";
  return (
    code === "loop_readiness_failed" ||
    message.includes("loop model readiness") ||
    reason.includes("question/tool capability for Loop")
  );
}

export function formatRoomRunErrorDetail(detail: RoomRunErrorDetail): string {
  const lines: string[] = [];
  const headline =
    detail.code === "loop_readiness_failed"
      ? "Loop 모드 전송 차단 — 선택 agent가 Loop capability probe를 통과하지 못했습니다."
      : (detail.message?.trim() ?? "요청이 서버에서 거부되었습니다.");
  lines.push(headline);

  if (detail.topology?.trim()) {
    lines.push(`topology: ${detail.topology.trim()}`);
  }
  if (detail.requested_agents?.length) {
    lines.push(`요청 roster: ${detail.requested_agents.join(", ")}`);
  }

  const agentDetails =
    detail.agent_details ??
    (Array.isArray(detail.agents)
      ? detail.agents.filter(
          (row): row is RoomRunAgentDetail =>
            typeof row === "object" && row !== null && "id" in row,
        )
      : []);

  if (agentDetails.length > 0) {
    lines.push("");
    for (const row of agentDetails) {
      const id = row.id ?? "agent";
      const model = row.model_id ? ` (${row.model_id})` : "";
      lines.push(`• ${id}${model}`);
      if (row.summary?.trim()) {
        lines.push(`  ${row.summary.trim()}`);
      } else if (row.blocker_labels?.length) {
        lines.push(`  미충족: ${row.blocker_labels.join(" · ")}`);
      } else if (row.loop_blockers?.length) {
        lines.push(`  미충족: ${row.loop_blockers.join(", ")}`);
      } else if (row.reason?.trim()) {
        lines.push(`  ${row.reason.trim()}`);
      }
    }
  } else if (Array.isArray(detail.agents) && detail.agents.length > 0) {
    const sharedReason = detail.reason?.trim() ?? "";
    lines.push("");
    for (const agent of detail.agents) {
      if (typeof agent === "string") {
        lines.push(
          sharedReason ? `• ${agent}: ${sharedReason}` : `• ${agent}`,
        );
      }
    }
  } else if (detail.reason?.trim()) {
    lines.push("");
    lines.push(detail.reason.trim());
  }

  if (detail.hint?.trim()) {
    lines.push("");
    lines.push(`조치: ${detail.hint.trim()}`);
  }

  return lines.join("\n");
}

export function messageLooksLikeLoopReadinessFailure(message: string): boolean {
  const lower = message.trim().toLowerCase();
  return (
    lower.includes("loop model readiness") ||
    lower.includes("question/tool capability for loop") ||
    lower.includes("loop 모드 전송 차단")
  );
}
