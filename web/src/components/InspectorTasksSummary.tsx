import type {
  PlanWorkflowRecord,
  RoomObjection,
  RoomTasksPayload,
  RuntimeSnapshot,
} from "../api/client";
import { useLocale } from "../i18n/useLocale";
import { buildInspectorTasksSummaryView } from "../utils/inspectorTasksSummary";

type Props = {
  readonly roomTasks: RoomTasksPayload | null;
  readonly inboxPendingCount: number;
  readonly discussPaused: boolean;
  readonly runtime: RuntimeSnapshot | null;
  readonly showPlanApproval: boolean;
  readonly verifiedLoopPendingApproval: boolean;
  readonly firstOpenBlock: RoomObjection | null;
  readonly planWorkflow: PlanWorkflowRecord | undefined;
  readonly consensusBlocked: boolean;
  readonly onOpenWork: () => void;
  readonly onOpenInbox: () => void;
  readonly onFocusComposer: () => void;
};

export function InspectorTasksSummary({
  roomTasks,
  inboxPendingCount,
  discussPaused,
  runtime,
  showPlanApproval,
  verifiedLoopPendingApproval,
  firstOpenBlock,
  planWorkflow,
  consensusBlocked,
  onOpenWork,
  onOpenInbox,
  onFocusComposer,
}: Props) {
  const { locale } = useLocale();
  const view = buildInspectorTasksSummaryView({
    locale,
    roomTasks,
    inboxPendingCount,
    discussPaused,
    runtime,
    showPlanApproval,
    verifiedLoopPendingApproval,
    firstOpenBlock,
    planWorkflow,
    consensusBlocked,
  });

  function runPrimary() {
    if (!view.primary) return;
    switch (view.primary.target) {
      case "work":
        onOpenWork();
        break;
      case "inbox":
        onOpenInbox();
        break;
      case "composer":
        onFocusComposer();
        break;
    }
  }

  return (
    <section
      className="inspector-tasks-summary"
      aria-label={locale === "ko" ? "Tasks 요약" : "Tasks summary"}
    >
      <div className="inspector-tasks-summary__now">
        <span className="inspector-tasks-summary__eyebrow">
          {locale === "ko" ? "지금 할 일" : "Now"}
        </span>
        <strong className="inspector-tasks-summary__headline">
          {view.headline}
        </strong>
        <p className="inspector-tasks-summary__detail">{view.detail}</p>
        {view.primary ? (
          <button
            type="button"
            className="btn btn--sm btn--primary inspector-tasks-summary__cta"
            onClick={runPrimary}
          >
            {view.primary.label}
          </button>
        ) : null}
      </div>
      <dl className="inspector-tasks-summary__stats">
        <div>
          <dt>{locale === "ko" ? "작업" : "Tasks"}</dt>
          <dd>{view.stats.openTasks}</dd>
        </div>
        <div>
          <dt>{locale === "ko" ? "이의" : "Objections"}</dt>
          <dd>{view.stats.openObjections}</dd>
        </div>
        <div>
          <dt>Inbox</dt>
          <dd>{view.stats.inboxPending}</dd>
        </div>
        {view.stats.consensusBlocked ? (
          <div>
            <dt>{locale === "ko" ? "합의" : "Consensus"}</dt>
            <dd>{locale === "ko" ? "대기" : "pending"}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}
