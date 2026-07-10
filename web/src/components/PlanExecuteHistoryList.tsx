import type { PlanExecutionRecord } from "../api/client";
import {
  AdversarialBadge,
  EXECUTION_HISTORY_LIMIT,
  OracleBadge,
  formatPathList,
  statusLabel,
} from "./PlanExecutePanelSupport";
import { PlanAgentResponse } from "./PlanAgentResponse";
import { PlanActionContext } from "./PlanActionContext";
import {
  executionHistoryBadge,
  executionHistoryTitle,
  executionContextFields,
  formatExecutionTime,
  resolveExecutionAction,
  type StoredPlanAction,
} from "../utils/planExecuteHistory";
import { mergedCommitSha } from "../utils/planExecuteWorktree";

type Props = {
  historyRows: PlanExecutionRecord[];
  storedActions: StoredPlanAction[];
  busy: boolean;
  onChatRefClick?: (lineNumber: number) => void;
  onReverify: (executionId: string) => void;
};

export function PlanExecuteHistoryList({
  historyRows,
  storedActions,
  busy,
  onChatRefClick,
  onReverify,
}: Props) {
  const historyVisible = historyRows.slice(0, EXECUTION_HISTORY_LIMIT);
  const historyHiddenCount = Math.max(
    0,
    historyRows.length - historyVisible.length,
  );

  if (!historyRows.length) return null;

  return (
    <details className="work-exec-history">
      <summary className="work-exec-history__toggle">
        <span className="work-exec-history__toggle-title">실행 기록</span>
        <span className="work-exec-history__count">{historyRows.length}</span>
        {historyHiddenCount ? (
          <span className="work-exec-history__toggle-hint">
            최근 {EXECUTION_HISTORY_LIMIT}건
          </span>
        ) : null}
        <span className="work-exec-history__chevron" aria-hidden />
      </summary>
      <ul className="work-exec-history__list">
        {historyVisible.map((row) => {
          const action = resolveExecutionAction(row, storedActions);
          const context = executionContextFields(row, action);
          const completedAt = formatExecutionTime(
            row.completed_at || row.started_at,
          );
          return (
            <li key={row.id} className="work-exec-history__item">
              <div className="work-exec-history__title-row">
                <span className="work-exec-history__badge">
                  {executionHistoryBadge(row)}
                </span>
                <strong className="work-exec-history__title">
                  {executionHistoryTitle(row, action)}
                </strong>
              </div>
              <div className="work-exec-history__meta">
                <span className="work-exec-history__status">
                  {statusLabel(row.status, row)}
                </span>
                {row.executor_label ? (
                  <span className="work-exec-history__executor">
                    {row.executor_label}
                  </span>
                ) : null}
                {completedAt ? (
                  <span className="work-exec-history__time">{completedAt}</span>
                ) : null}
                {mergedCommitSha(row) ? (
                  <span
                    className="work-exec-history__merge-sha"
                    title={mergedCommitSha(row) ?? undefined}
                  >
                    merge {(mergedCommitSha(row) ?? "").slice(0, 7)}
                  </span>
                ) : null}
              </div>
              <PlanActionContext
                {...context}
                onRefClick={onChatRefClick}
                compact
              />
              <AdversarialBadge row={row} />
              <OracleBadge
                row={row}
                busy={busy}
                onReverify={(executionId) => onReverify(executionId)}
              />
              {row.touched_paths?.length ? (
                <p className="work-exec-history__paths">
                  변경: {formatPathList(row.touched_paths)}
                </p>
              ) : null}
              {row.agent_log?.length ? (
                <details className="work-exec-history__log">
                  <summary>에이전트 로그 ({row.agent_log.length})</summary>
                  <ol className="work-exec-agent-log">
                    {row.agent_log.map((line, i) => (
                      <li key={`${row.id}-log-${i}`}>{line}</li>
                    ))}
                  </ol>
                </details>
              ) : null}
              {row.agent_response || row.draft_summary ? (
                <details className="work-exec-history__response">
                  <summary>에이전트 응답</summary>
                  <PlanAgentResponse
                    text={row.agent_response || row.draft_summary || ""}
                  />
                </details>
              ) : null}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
