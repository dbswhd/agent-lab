import type { RuntimeSnapshot } from "../api/client";
import type { PlanWorkflowRecord } from "../api/client";

type ClarifierQuestion = {
  readonly id?: string;
  readonly prompt?: string;
  readonly category?: string;
  readonly answered?: boolean;
};

type Props = {
  readonly planWorkflow?: PlanWorkflowRecord;
  readonly runtime: RuntimeSnapshot | null;
  readonly inboxPendingCount: number;
  readonly onOpenInbox?: () => void;
};

export function WorkClarifyPanel({
  planWorkflow,
  runtime,
  inboxPendingCount,
  onOpenInbox,
}: Props) {
  const phase = (
    planWorkflow?.phase ??
    runtime?.plan_workflow?.phase ??
    "CLARIFY"
  ).toUpperCase();
  const interview = runtime?.clarifier_interview as
    | {
        readonly questions?: readonly ClarifierQuestion[];
        readonly complete?: boolean;
      }
    | undefined;
  const questions = interview?.questions?.filter((q) => q.prompt?.trim()) ?? [];
  const pendingQuestions = questions.filter((q) => !q.answered);

  return (
    <div className="work-stack work-stack--tool">
      <div className="work-surface work-surface--chrome work-chrome">
        <div className="work-clarify">
          <div className="work-clarify__head">
            <span className="plan-workflow-banner__badge">{phase}</span>
            <h3 className="work-clarify__title">Plan workflow · Clarify</h3>
          </div>
          <p className="work-clarify__detail">
            에이전트가 Human Inbox에 구조화 질문을 올립니다. 답변하면
            Draft(plan.md 작성)로 진행합니다.
          </p>
          {inboxPendingCount > 0 ? (
            <p className="work-clarify__stat">
              Human Inbox 대기 <strong>{inboxPendingCount}</strong>건
            </p>
          ) : (
            <p className="work-clarify__stat work-clarify__stat--muted">
              Inbox 대기 없음 — 에이전트가 질문을 생성 중이거나 이미 답변됨
            </p>
          )}
          {onOpenInbox ? (
            <button
              type="button"
              className="plan-btn plan-btn--primary"
              onClick={onOpenInbox}
            >
              Human Inbox 열기
            </button>
          ) : null}
        </div>
      </div>

      {pendingQuestions.length > 0 ? (
        <div className="work-surface work-clarify-questions">
          <h4 className="work-clarify-questions__title">Clarify 질문</h4>
          <ol className="work-clarify-questions__list">
            {pendingQuestions.map((q) => (
              <li key={q.id ?? q.prompt}>
                {q.category ? (
                  <span className="clarifier-banner__category">
                    {q.category}
                  </span>
                ) : null}
                <span>{q.prompt}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : questions.length > 0 ? (
        <div className="work-surface work-clarify-questions">
          <p className="plan-card__muted">Clarify 질문에 모두 답변했습니다.</p>
        </div>
      ) : null}
    </div>
  );
}
