import type { ComposerStackLane } from "../utils/composerStackLane";
import { WorkPlanIcon } from "./WorkPlanIcon";

type DecisionTone = "question" | "approval" | "review";

type DecisionMeta = {
  readonly label: string;
  readonly tone: DecisionTone;
  readonly icon: "alert" | "doc" | "gitMerge" | "bolt";
};

function decisionMeta(
  lane: Exclude<ComposerStackLane, "work">,
  locale: "ko" | "en",
): DecisionMeta {
  const ko = locale === "ko";
  switch (lane) {
    case "plan_approval":
      return {
        label: ko ? "계획 검토" : "Plan review",
        tone: "approval",
        icon: "doc",
      };
    case "clarify":
      return {
        label: ko ? "방향 선택" : "Choose a direction",
        tone: "question",
        icon: "alert",
      };
    case "execute_queue":
      return {
        label: ko ? "변경사항 검토" : "Review the changes",
        tone: "review",
        icon: "gitMerge",
      };
    case "consensus":
      return {
        label: ko ? "격리 실행 확인" : "Confirm the isolated run",
        tone: "approval",
        icon: "bolt",
      };
    case "inbox":
      return {
        label: ko ? "질문 응답" : "Answer a question",
        tone: "question",
        icon: "alert",
      };
  }
}

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
  const queuedDecisions = queuedLanes.filter(
    (lane): lane is Exclude<ComposerStackLane, "work"> => lane !== "work",
  );
  const activeMeta = decisionMeta(activeLane, locale);
  const queuedLabels = queuedDecisions.map(
    (lane) => decisionMeta(lane, locale).label,
  );

  return (
    <div
      className={`composer-decision-queue composer-decision-queue--${activeMeta.tone}`}
      role="status"
      aria-live="polite"
    >
      <span className="composer-decision-queue__icon" aria-hidden>
        <WorkPlanIcon name={activeMeta.icon} size={16} />
      </span>
      <div className="composer-decision-queue__copy">
        <span className="composer-decision-queue__eyebrow">
          {locale === "ko" ? "결정 필요" : "Needs your input"}
        </span>
        <strong className="composer-decision-queue__current">
          {activeMeta.label}
        </strong>
      </div>
      <span className="composer-decision-queue__count">
        {locale === "ko" ? `${pendingCount}건` : `${pendingCount}`}
      </span>
      {queuedLabels.length > 0 ? (
        <p className="composer-stack-queue-hint">
          {locale === "ko" ? "다음: " : "Then: "}
          {queuedLabels.join(" → ")}
        </p>
      ) : null}
    </div>
  );
}
