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
  if (detectPlanExecuteIntent(topic) || detectPlanExecuteIntent(sessionTopic)) {
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
        ? "실행 계획 검토가 필요해 다음 작업을 기다리고 있습니다."
        : "The build plan needs your review before work can continue.";
    }
    if (phase === "APPROVED") {
      return locale === "ko"
        ? "계획이 승인되어 격리 실행과 변경 검토를 진행할 수 있습니다."
        : "The approved plan can now move through isolated build and change review.";
    }
    if (phase && phase !== "INTAKE") {
      return locale === "ko"
        ? "작업 계획을 구체화하는 중이라 협업 검토를 유지합니다."
        : "Collaborative review stays active while the build plan is refined.";
    }
  }

  const executeIntent =
    detectPlanExecuteIntent(draft) || detectPlanExecuteIntent(sessionTopic);
  if (executeIntent) {
    return locale === "ko"
      ? "코드 변경과 검증 요청이 감지되어 계획 승인과 격리 실행을 적용합니다."
      : "A code-change request was detected, so plan approval and isolated execution apply.";
  }

  if (run?.discuss_light) {
    return locale === "ko"
      ? "낮은 위험의 간단한 요청이라 한 번의 병렬 검토로 처리합니다."
      : "This low-risk request uses one lightweight parallel review.";
  }

  return null;
}
