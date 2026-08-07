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
  /** True while the next step needs a human OK (display level L0). */
  needsYou: boolean;
  /** Short pill text: "승인 필요" / "알아서 진행". */
  statusLabel: string;
  /** One sentence under the pill explaining the current level. */
  statusDetail: string;
  /** Plain-language reason the ladder was demoted, when one applies. */
  whyStopped: string | null;
  summary: string;
  transitions: AutonomyTransition[];
};

/** One rung of the ladder, phrased for a human rather than for the ledger. */
export type AutonomyLevelCard = {
  level: AutonomyLevel;
  title: string;
  hint: string;
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

/** The ladder as a person reads it — what each rung lets the agents do alone. */
export function autonomyLevelCards(locale: "en" | "ko"): AutonomyLevelCard[] {
  const ko = locale === "ko";
  return [
    {
      level: "L0",
      title: ko ? "매번 물어보기" : "Ask me each time",
      hint: ko
        ? "계획·실행 전에 항상 승인이 필요합니다."
        : "Plan and execute always wait for your OK.",
    },
    {
      level: "L1",
      title: ko ? "안전한 것만 알아서" : "OK low-risk alone",
      hint: ko
        ? "낮은 위험은 시간 지나면 자동 승인할 수 있습니다."
        : "Low-risk steps may auto-approve after a short wait.",
    },
    {
      level: "L2",
      title: ko ? "횟수 한도 안에서" : "OK within a budget",
      hint: ko
        ? "정해 둔 횟수만큼 자동으로 이어가고, 다 쓰면 다시 묻습니다."
        : "Continues alone for a set number of merges, then asks again.",
    },
    {
      level: "L3",
      title: ko ? "미션까지 알아서" : "Run the mission",
      hint: ko
        ? "미션 루프가 돌고, 막히거나 위험이 클 때만 묻습니다."
        : "Mission loop runs; asks only on blocks or high risk.",
    },
  ];
}

/**
 * Turn a demotion `reason` code into one sentence a human can act on.
 *
 * The ledger reasons (`trust_budget_consumed`, `oracle_fail_consecutive`, …)
 * answer "which rule fired"; this answers "why did it stop", which is what the
 * dial is asked at a glance. Unknown reasons fall through with level tokens
 * stripped rather than being hidden.
 */
export function autonomyWhyStopped(
  reason: string | null | undefined,
  locale: "en" | "ko",
): string {
  const ko = locale === "ko";
  const raw = (reason || "").trim();
  if (!raw) return ko ? "자동 진행이 꺼졌습니다." : "Auto-run was turned down.";
  const key = raw.toLowerCase();
  if (key.includes("trust_budget") || key.includes("budget_consumed")) {
    return ko
      ? "자동으로 이어갈 횟수를 다 썼습니다."
      : "The auto-continue budget ran out.";
  }
  if (
    key.includes("oracle") &&
    (key.includes("fail") || key.includes("consecutive"))
  ) {
    return ko
      ? "검증(Oracle)이 연속으로 실패했습니다."
      : "Verification (Oracle) failed repeatedly.";
  }
  if (
    key.includes("diff_risk") ||
    key.includes("high_risk") ||
    key === "high"
  ) {
    return ko
      ? "변경 위험이 높게 분류되었습니다."
      : "The change was classified as high risk.";
  }
  if (
    key.includes("quarter") ||
    key.includes("cost_ledger") ||
    key.includes("budget_usd")
  ) {
    return ko
      ? "분기 비용 한도에 닿았습니다."
      : "The quarterly spend limit was hit.";
  }
  if (key.includes("risk_pin") || key.includes("trading")) {
    return ko
      ? "위험 카테고리(예: 트레이딩)라서 더 보수적으로 멈췄습니다."
      : "A risk category (e.g. trading) pinned a more careful mode.";
  }
  if (key.includes("inbox_restore")) {
    return ko ? "이전 설정을 다시 켰습니다." : "Previous setting was restored.";
  }
  return raw
    .replace(/\bL[0-3]\b/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Most recent demotion, which is the one worth explaining. */
function latestDemotion(
  transitions: AutonomyTransition[],
): AutonomyTransition | null {
  for (let i = transitions.length - 1; i >= 0; i -= 1) {
    const row = transitions[i];
    if (row?.trigger === "demotion") return row;
  }
  return null;
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
  const transitions = (autonomy.transitions ?? []).slice(-5);
  const demotion = latestDemotion(transitions);
  const needsYou = displayLevel === "L0";
  const whyStopped = demotion
    ? autonomyWhyStopped(demotion.reason, locale)
    : null;

  const statusLabel = needsYou
    ? ko
      ? "승인 필요"
      : "Needs your OK"
    : ko
      ? "알아서 진행"
      : "Can go alone";

  let statusDetail: string;
  if (needsYou && whyStopped) {
    statusDetail = whyStopped;
  } else if (needsYou) {
    statusDetail = ko
      ? "다음 단계는 승인이 있어야 진행됩니다."
      : "The next step waits for your approval.";
  } else if (displayLevel === "L2" && total > 0) {
    statusDetail = ko
      ? `자동 진행 남은 횟수 ${remaining}/${total}`
      : `${remaining}/${total} auto-continues left`;
  } else if (displayLevel === "L3") {
    statusDetail = ko
      ? "미션이 막히거나 위험이 클 때만 묻습니다."
      : "Asks only when blocked or high risk.";
  } else {
    statusDetail = ko
      ? "낮은 위험은 자동으로 넘어갈 수 있습니다."
      : "Low-risk steps can continue without you.";
  }

  const summary = whyStopped
    ? `${statusLabel} — ${whyStopped}`
    : `${statusLabel}. ${statusDetail}`;

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
    needsYou,
    statusLabel,
    statusDetail,
    whyStopped,
    summary,
    transitions,
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
  if (level !== "L0" && level !== "L1" && level !== "L2" && level !== "L3") {
    return null;
  }
  const tb = block.trust_budget;
  const budget =
    tb && typeof tb === "object" ? (tb as Record<string, unknown>) : {};
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
