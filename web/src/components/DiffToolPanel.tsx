import { useMemo } from "react";
import type { PlanExecutionRecord } from "../api/client";
import { findActiveExecution } from "../utils/planExecuteWorktree";
import { PlanDiffStat } from "./PlanDiffStat";
import { SideBySideDiff } from "./SideBySideDiff";

type Props = {
  readonly executions: readonly PlanExecutionRecord[];
};

function rowTime(row: PlanExecutionRecord): number {
  const raw = row.completed_at ?? row.started_at;
  if (!raw) return 0;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function rowTitle(row: PlanExecutionRecord): string {
  if (row.action_what) return row.action_what;
  if (row.action_index != null) return `Plan action #${row.action_index}`;
  return row.id;
}

export function DiffToolPanel({ executions }: Props) {
  const activeRow = useMemo(() => {
    const active = findActiveExecution([...executions]);
    if (active?.diff || active?.diff_stat) return active;
    return [...executions]
      .filter((row) => Boolean(row.diff || row.diff_stat))
      .sort((left, right) => rowTime(right) - rowTime(left))[0] ?? null;
  }, [executions]);

  if (!activeRow) {
    return (
      <div className="diff-tool-panel">
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden>
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 5h10" />
              <path d="M8 12h10" />
              <path d="M8 19h10" />
              <path d="M4 12h.01" />
            </svg>
          </span>
          <span className="empty-state__title">출력할 diff 없음</span>
          <span className="empty-state__hint">
            Execute dry-run 또는 승인 대기 diff가 생기면 여기에 표시됩니다.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="diff-tool-panel">
      <section className="diff-tool-panel__summary">
        <span className="diff-tool-panel__badge">
          {activeRow.status ?? "diff"}
        </span>
        <h3>{rowTitle(activeRow)}</h3>
        {activeRow.executor_label ?? activeRow.executor ? (
          <p>{activeRow.executor_label ?? activeRow.executor}</p>
        ) : null}
      </section>
      {activeRow.diff_stat ? <PlanDiffStat text={activeRow.diff_stat} /> : null}
      {activeRow.diff ? (
        <SideBySideDiff diff={activeRow.diff} />
      ) : (
        <div className="empty-state empty-state--compact">
          <span className="empty-state__title">소스 diff 없음</span>
          <span className="empty-state__hint">
            diff stat만 기록된 실행입니다.
          </span>
        </div>
      )}
    </div>
  );
}
