import type { ComposerStackLane } from "../utils/composerStackLane";

const LABELS: Record<"ko" | "en", Record<ComposerStackLane, string>> = {
  ko: {
    plan_approval: "실행 계획 승인",
    clarify: "방향 결정",
    execute_queue: "변경사항 병합 결정",
    consensus: "격리 실행 결정",
    inbox: "질문과 승인",
    work: "작업 현황",
  },
  en: {
    plan_approval: "Approve build plan",
    clarify: "Choose direction",
    execute_queue: "Decide whether to merge",
    consensus: "Approve isolated build",
    inbox: "Questions and approvals",
    work: "Work status",
  },
};

type Props = {
  readonly activeLane: Exclude<ComposerStackLane, "work">;
  readonly queuedLanes: readonly ComposerStackLane[];
  readonly pendingCount: number;
  readonly locale: "ko" | "en";
};

export function DecisionQueueHeader({
  activeLane,
  queuedLanes,
  pendingCount,
  locale,
}: Props) {
  const queuedDecisions = queuedLanes.filter((lane) => lane !== "work");
  const labels = LABELS[locale];

  return (
    <>
      <div className="composer-decision-queue__header" role="status">
        <span className="composer-decision-queue__eyebrow">
          {locale === "ko" ? "결정 대기열" : "Decision queue"}
        </span>
        <strong className="composer-decision-queue__current">
          {labels[activeLane]}
        </strong>
        <span className="composer-decision-queue__count">
          {locale === "ko"
            ? `${pendingCount}건 대기`
            : `${pendingCount} pending`}
        </span>
      </div>
      {queuedDecisions.length > 0 ? (
        <p className="composer-stack-queue-hint" role="status">
          {locale === "ko" ? "이후 결정: " : "Next decision: "}
          {queuedDecisions.map((lane) => labels[lane]).join(" → ")}
        </p>
      ) : null}
    </>
  );
}
