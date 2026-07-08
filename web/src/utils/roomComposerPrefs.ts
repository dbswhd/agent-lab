import type { Locale } from "../i18n/locale";

/** P2: Composer is topic-only — implicit dogfood preset (no fast/supervisor picker). */
export const TOPIC_ONLY_COMPOSER = true;

/** Default room_preset sent to the API when TOPIC_ONLY_COMPOSER is on. */
export const IMPLICIT_ROOM_PRESET = "supervisor" as const;

const PLAN_EXECUTE_INTENT_MARKERS = [
  "dry-run",
  "dry run",
  "dry_run",
  "oracle pass",
  "oracle verify",
  "plan action",
  "propose_build",
  "execute lane",
  "worktree",
  "지금 실행",
] as const;

/** Mirror ``turn_policy.detect_plan_execute_intent`` for composer hints. */
export function detectPlanExecuteIntent(text: string): boolean {
  const lowered = (text || "").trim().toLowerCase();
  if (!lowered) return false;
  if (PLAN_EXECUTE_INTENT_MARKERS.some((marker) => lowered.includes(marker))) {
    return true;
  }
  if (
    lowered.includes("merge") &&
    ["oracle", "승인", "approve", "verify"].some((token) =>
      lowered.includes(token),
    )
  ) {
    return true;
  }
  if (
    lowered.includes("plan") &&
    ["dry", "execute", "승인", "approve", "merge"].some((token) =>
      lowered.includes(token),
    )
  ) {
    return true;
  }
  return false;
}

export function resolveComposerModeVariant(opts: {
  consensusMode: boolean;
  planWorkflowActive?: boolean;
  topic?: string;
  sessionTopic?: string;
  discussLight?: boolean;
}): "discuss" | "plan" | "consensus" {
  if (opts.consensusMode) return "consensus";
  if (opts.planWorkflowActive) return "plan";
  const topic = (opts.topic || "").trim();
  const sessionTopic = (opts.sessionTopic || "").trim();
  if (
    detectPlanExecuteIntent(topic) ||
    detectPlanExecuteIntent(sessionTopic)
  ) {
    return "plan";
  }
  if (opts.discussLight === false && (topic || sessionTopic)) return "plan";
  return "discuss";
}

/** One-line routing hint under composer (TurnPolicy era — no Plan toggle). */
export function composerRoutingHintLine(
  opts: {
    run?: Record<string, unknown> | null;
    draftTopic?: string;
    locale?: Locale;
  } = {},
): string | null {
  const locale = opts.locale ?? "en";
  const run = opts.run ?? null;
  const draft = (opts.draftTopic || "").trim();
  const sessionTopic = String(run?.topic ?? "").trim();
  const planWorkflow = run?.plan_workflow as
    | { enabled?: boolean; phase?: string }
    | undefined;
  const planActive = Boolean(planWorkflow?.enabled);
  const phase = String(planWorkflow?.phase ?? "").toUpperCase();

  if (planActive) {
    if (phase === "HUMAN_PENDING") {
      return locale === "ko"
        ? "Plan 승인 대기 — composer stack에서 승인하세요"
        : "Plan approval pending — approve in the composer stack";
    }
    if (phase === "APPROVED") {
      return locale === "ko"
        ? "Plan 승인됨 — stack에서 dry-run · merge"
        : "Plan approved — dry-run and merge in the composer stack";
    }
    if (phase && phase !== "INTAKE") {
      return locale === "ko"
        ? `Plan workflow · ${phase} — stack에서 진행`
        : `Plan workflow · ${phase} — continue in the composer stack`;
    }
  }

  const executeIntent =
    detectPlanExecuteIntent(draft) ||
    detectPlanExecuteIntent(sessionTopic);
  if (executeIntent) {
    return locale === "ko"
      ? "Plan/execute 토픽 — discuss_light 없이 plan FSM · stack에서 dry-run"
      : "Plan/execute topic — plan FSM (no light discuss); dry-run in stack";
  }

  if (run?.discuss_light) {
    return locale === "ko"
      ? "경량 discuss — 전원 동시 1 wave"
      : "Light discuss — full-parallel 1 wave";
  }

  return null;
}
