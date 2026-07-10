import type { RuntimeSnapshot } from "../api/client";

export type StatusLineChip = {
  id: string;
  label: string;
  title?: string;
};

type StatusLineInput = {
  runtime?: RuntimeSnapshot | null;
  locale?: "ko" | "en";
};

/** Compose Autonomy×sandbox header chips from runtime.status_line. */
export function buildSessionStatusChips(
  input: StatusLineInput,
): StatusLineChip[] {
  const ko = input.locale !== "en";
  const line = input.runtime?.status_line;
  if (!line) return [];

  const chips: StatusLineChip[] = [];
  if (line.schedule_sandbox) {
    chips.push({
      id: "schedule_sandbox",
      label: "Schedule RO",
      title: ko
        ? "스케줄 샌드박스 — execute 읽기 전용"
        : "Schedule sandbox — execute read-only",
    });
  }

  if (line.worktree) {
    chips.push({
      id: "worktree",
      label: "Worktree",
      title: ko ? "격리: worktree" : "Isolation: worktree",
    });
  } else if (line.isolation) {
    chips.push({
      id: "isolation",
      label: line.isolation,
      title: ko ? `격리: ${line.isolation}` : `Isolation: ${line.isolation}`,
    });
  }

  if (line.sandbox_intent) {
    chips.push({
      id: "sandbox_intent",
      label: line.sandbox_intent,
      title: `Sandbox intent: ${line.sandbox_intent}`,
    });
  }

  return chips;
}
