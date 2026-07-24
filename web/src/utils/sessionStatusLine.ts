import type { RuntimeSnapshot, SessionDetail } from "../api/client";

export type StatusLineChip = {
  id: string;
  label: string;
  title?: string;
  tone?: "default" | "warn" | "danger";
};

type StatusLineInput = {
  runtime?: RuntimeSnapshot | null;
  session?: SessionDetail | null;
  locale?: "ko" | "en";
};

function formatUsd(value: number): string {
  if (!Number.isFinite(value)) return "$0";
  if (value >= 10) return `$${value.toFixed(2)}`;
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(2)}`;
  return `$${value.toFixed(3)}`;
}

/** Compose Autonomy×sandbox×cost header chips from runtime/session. */
export function buildSessionStatusChips(
  input: StatusLineInput,
): StatusLineChip[] {
  const ko = input.locale !== "en";
  const line = input.runtime?.status_line;
  const chips: StatusLineChip[] = [];

  if (line?.schedule_sandbox) {
    chips.push({
      id: "schedule_sandbox",
      label: "Schedule RO",
      title: ko
        ? "스케줄 샌드박스 — execute 읽기 전용"
        : "Schedule sandbox — execute read-only",
    });
  }

  if (line?.worktree) {
    chips.push({
      id: "worktree",
      label: "Worktree",
      title: ko ? "격리: worktree" : "Isolation: worktree",
    });
  } else if (line?.isolation) {
    chips.push({
      id: "isolation",
      label: line.isolation,
      title: ko ? `격리: ${line.isolation}` : `Isolation: ${line.isolation}`,
    });
  }

  if (line?.sandbox_intent) {
    chips.push({
      id: "sandbox_intent",
      label: line.sandbox_intent,
      title: `Sandbox intent: ${line.sandbox_intent}`,
    });
  }

  if (line?.run_profile) {
    chips.push({
      id: "run_profile",
      label: line.run_profile,
      title: ko
        ? `Run profile: ${line.run_profile}`
        : `Run profile: ${line.run_profile}`,
    });
  }

  const missionBudget = input.session?.cost?.budget;
  const quarter = input.runtime?.cost_quarter;
  const spent =
    typeof missionBudget?.spent_usd === "number"
      ? missionBudget.spent_usd
      : typeof quarter?.spent_usd === "number"
        ? quarter.spent_usd
        : null;
  const limit =
    typeof missionBudget?.limit_usd === "number"
      ? missionBudget.limit_usd
      : typeof quarter?.limit_usd === "number"
        ? quarter.limit_usd
        : null;
  const warn = Boolean(missionBudget?.warn || quarter?.warn);
  const over = Boolean(missionBudget?.over || quarter?.over);

  if (spent != null && (spent > 0 || limit != null)) {
    const label =
      limit != null
        ? `${formatUsd(spent)} / ${formatUsd(limit)}`
        : formatUsd(spent);
    chips.push({
      id: "cost",
      label,
      tone: over ? "danger" : warn ? "warn" : "default",
      title: ko
        ? over
          ? "미션/분기 예산 초과"
          : warn
            ? "미션/분기 예산 경고"
            : "세션·분기 비용 (F8)"
        : over
          ? "Mission/quarter budget exceeded"
          : warn
            ? "Mission/quarter budget warning"
            : "Session/quarter cost (F8)",
    });
  }

  if (line?.human_gate_opened_at) {
    chips.push({
      id: "human_gate",
      label: ko ? "대기 중" : "Waiting",
      title: ko
        ? `Human gate 열림: ${line.human_gate_kind ?? "decision"} · ${line.human_gate_opened_at}`
        : `Human gate open: ${line.human_gate_kind ?? "decision"} · ${line.human_gate_opened_at}`,
    });
  }

  return chips;
}
