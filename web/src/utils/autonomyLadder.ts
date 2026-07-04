import type { RuntimeSnapshot } from "../api/client";

export type AutonomyLevel = "L0" | "L1" | "L2" | "L3";

export const AUTONOMY_LEVELS: readonly AutonomyLevel[] = [
  "L0",
  "L1",
  "L2",
  "L3",
];

export type AutonomyTransition = {
  from?: string;
  to?: string;
  reason?: string;
  trigger?: string;
  at?: string;
};

export type AutonomySessionView = {
  level: AutonomyLevel;
  effectiveLevel: AutonomyLevel;
  displayLevel: AutonomyLevel;
  levelName: string;
  trustBudgetRemaining: number;
  trustBudgetTotal: number;
  autoApproveEnabled: boolean;
  missionLoopEnabled: boolean;
  autonomousSegmentActive: boolean;
  summary: string;
  transitions: AutonomyTransition[];
};

type AutonomyPayload = NonNullable<RuntimeSnapshot["autonomy"]>;

export function autonomyLevelLabel(
  level: AutonomyLevel,
  locale: "en" | "ko",
): string {
  const ko = locale === "ko";
  switch (level) {
    case "L0":
      return ko ? "수동" : "Manual";
    case "L1":
      return ko ? "보조" : "Assisted";
    case "L2":
      return ko ? "예산" : "Budgeted";
    case "L3":
      return ko ? "자율" : "Autonomous";
    default:
      return level;
  }
}

export function buildAutonomySessionView(
  autonomy: AutonomyPayload | null | undefined,
  locale: "en" | "ko",
): AutonomySessionView | null {
  if (!autonomy) return null;
  const displayLevel = autonomy.display_level;
  const remaining = autonomy.trust_budget.auto_merge_remaining;
  const total = autonomy.trust_budget.auto_merge_total;
  const ko = locale === "ko";
  let summary = autonomyLevelLabel(displayLevel, locale);
  if (total > 0) {
    summary += ko
      ? ` · trust ${remaining}/${total}`
      : ` · trust ${remaining}/${total}`;
  } else if (autonomy.signals.auto_approve_enabled && displayLevel === "L1") {
    summary += ko ? " · auto-approve" : " · auto-approve";
  }
  return {
    level: autonomy.level,
    effectiveLevel: autonomy.effective_level,
    displayLevel,
    levelName: autonomy.level_name,
    trustBudgetRemaining: remaining,
    trustBudgetTotal: total,
    autoApproveEnabled: autonomy.signals.auto_approve_enabled,
    missionLoopEnabled: autonomy.signals.mission_loop_enabled,
    autonomousSegmentActive: autonomy.signals.autonomous_segment_active,
    summary,
    transitions: (autonomy.transitions ?? []).slice(-5),
  };
}

export function autonomyFromSessionRun(
  run: Record<string, unknown> | null | undefined,
): AutonomyPayload | null {
  const raw = run?.autonomy;
  if (!raw || typeof raw !== "object") return null;
  const block = raw as Record<string, unknown>;
  const level = block.level;
  const effective = block.effective_level ?? block.level;
  const display = block.display_level ?? effective;
  if (
    level !== "L0" &&
    level !== "L1" &&
    level !== "L2" &&
    level !== "L3"
  ) {
    return null;
  }
  const tb = block.trust_budget;
  const budget =
    tb && typeof tb === "object"
      ? (tb as Record<string, unknown>)
      : {};
  const signals = block.signals;
  const sig =
    signals && typeof signals === "object"
      ? (signals as Record<string, unknown>)
      : {};
  return {
    level,
    effective_level:
      effective === "L0" ||
      effective === "L1" ||
      effective === "L2" ||
      effective === "L3"
        ? effective
        : level,
    display_level:
      display === "L0" ||
      display === "L1" ||
      display === "L2" ||
      display === "L3"
        ? display
        : level,
    level_name:
      typeof block.level_name === "string" ? block.level_name : String(display),
    trust_budget: {
      auto_merge_remaining: Number(budget.auto_merge_remaining ?? 0),
      auto_merge_total: Number(budget.auto_merge_total ?? 0),
    },
    signals: {
      auto_approve_enabled: Boolean(sig.auto_approve_enabled),
      mission_loop_enabled: Boolean(sig.mission_loop_enabled),
      autonomous_segment_active: Boolean(sig.autonomous_segment_active),
    },
    ceiling_set: Boolean(block.ceiling_set),
    transitions: Array.isArray(block.transitions)
      ? (block.transitions as AutonomyTransition[]).slice(-5)
      : [],
  };
}
