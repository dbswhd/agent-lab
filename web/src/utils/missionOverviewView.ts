import type { MissionLoopState, RoomObjection } from "../api/client";

export type MissionOverviewView = {
  enabled: boolean;
  phase: string | null;
  goalText: string | null;
  verifiedStatus: string | null;
  nextActionIndex: number | null;
  nextActionWhat: string | null;
  pendingCount: number;
  circuitBreaker: boolean;
  circuitBreakerReason: string | null;
  pauseReason: string | null;
  openBlocks: RoomObjection[];
};

function actionTitleFromPlan(planMd: string, index: number): string | null {
  const lines = planMd.split(/\r?\n/);
  const head = new RegExp(`^${index}\\.\\s+(.+)$`);
  for (const line of lines) {
    const match = line.trim().match(head);
    if (match?.[1]) return match[1].trim();
  }
  return null;
}

function actionWhatFromPlan(planMd: string, index: number): string | null {
  const lines = planMd.split(/\r?\n/);
  let inAction = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (new RegExp(`^${index}\\.`).test(line)) {
      inAction = true;
      continue;
    }
    if (inAction && /^\d+\./.test(line)) break;
    if (inAction && line.startsWith("- 무엇을:")) {
      return line.replace(/^- 무엇을:\s*/, "").trim() || null;
    }
  }
  return null;
}

export function buildMissionOverviewView(input: {
  run?: Record<string, unknown> | null;
  planMd?: string;
}): MissionOverviewView {
  const run = input.run ?? {};
  const ml: MissionLoopState =
    (run.mission_loop as MissionLoopState | undefined) ?? {
      enabled: false,
      phase: "MISSION_DEFINE",
    };
  const verified = (run.verified_loop as Record<string, unknown> | undefined) ?? {};
  const loopGoal = (verified.loop_goal as { text?: string } | undefined) ?? {};
  const proposed = (verified.proposed as { goal?: string } | undefined) ?? {};
  const sessionGoal = (run.session_goal as { text?: string } | undefined) ?? {};

  const goalText =
    String(loopGoal.text ?? proposed.goal ?? sessionGoal.text ?? "").trim() || null;

  const pending = ml.pending_action_indices ?? [];
  const nextIndex =
    ml.current_action_index ??
    (pending.length > 0 ? pending[0] : null);

  const planMd = input.planMd ?? "";
  const objections = (run.objections as RoomObjection[] | undefined) ?? [];
  const openBlocks = objections.filter(
    (o) => o.status === "open" && o.act === "BLOCK",
  );

  return {
    enabled: Boolean(ml.enabled),
    phase: ml.phase ?? null,
    goalText,
    verifiedStatus: String(verified.status ?? "") || null,
    nextActionIndex: nextIndex ?? null,
    nextActionWhat:
      nextIndex != null
        ? actionWhatFromPlan(planMd, nextIndex) ??
          actionTitleFromPlan(planMd, nextIndex)
        : null,
    pendingCount: pending.length,
    circuitBreaker: Boolean(ml.circuit_breaker),
    circuitBreakerReason: ml.circuit_breaker_reason ?? null,
    pauseReason: (ml as { pause_reason?: string }).pause_reason ?? null,
    openBlocks,
  };
}
