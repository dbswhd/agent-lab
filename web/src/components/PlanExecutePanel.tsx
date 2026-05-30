import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchPlanActions,
  resolvePlanExecution,
  runPlanDryRun,
  type PlanActionItem,
  type PlanExecutionRecord,
} from "../api/client";
import type { AgentPermissions } from "../utils/agentPermissions";
import { loadDefaultPermissions } from "../utils/agentPermissions";

type Props = {
  sessionId: string;
  run?: Record<string, unknown>;
  cursorReady: boolean;
  disabled?: boolean;
  onUpdated: () => void;
};

function statusLabel(status: string | undefined): string {
  switch (status) {
    case "pending_approval":
      return "승인 대기";
    case "completed":
      return "완료";
    case "review_required":
      return "범위 검토 필요";
    case "rejected":
      return "거부됨";
    case "failed":
      return "실패";
    default:
      return status || "—";
  }
}

function roadmapLabel(item: PlanActionItem): string {
  if (item.executable === false) {
    return item.summary || item.what;
  }
  return item.what;
}

export function PlanExecutePanel({
  sessionId,
  run,
  cursorReady,
  disabled,
  onUpdated,
}: Props) {
  const [recommended, setRecommended] = useState<PlanActionItem | null>(null);
  const [roadmap, setRoadmap] = useState<PlanActionItem[]>([]);
  const [loadingActions, setLoadingActions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [pending, setPending] = useState<PlanExecutionRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const executions = useMemo(
    () => (run?.executions as PlanExecutionRecord[] | undefined) ?? [],
    [run],
  );

  const pendingFromRun = useMemo(
    () =>
      [...executions]
        .reverse()
        .find((row) => row.status === "pending_approval") ?? null,
    [executions],
  );

  const activePending = pending ?? pendingFromRun;

  const refreshActions = useCallback(async () => {
    setLoadingActions(true);
    setError(null);
    try {
      const res = await fetchPlanActions(sessionId);
      setRecommended(res.recommended);
      setRoadmap(res.roadmap);
      if (res.recommended) {
        setSelectedIndex(res.recommended.index);
      } else if (res.actions.length > 0 && selectedIndex == null) {
        setSelectedIndex(res.actions[0]?.index ?? null);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingActions(false);
    }
  }, [sessionId, selectedIndex]);

  const lastPlanUpdateTs = useMemo(() => {
    const lpu = run?.last_plan_update as { completed_at?: string; ts?: string } | undefined;
    return lpu?.completed_at || lpu?.ts || null;
  }, [run?.last_plan_update]);

  useEffect(() => {
    void refreshActions();
  }, [refreshActions, lastPlanUpdateTs]);

  useEffect(() => {
    setPending(null);
  }, [sessionId]);

  async function handleDryRun() {
    if (selectedIndex == null || activePending) return;
    setBusy(true);
    setError(null);
    const permissions: AgentPermissions = loadDefaultPermissions();
    try {
      const res = await runPlanDryRun(sessionId, {
        actionIndex: selectedIndex,
        permissions,
      });
      setPending(res.execution);
      onUpdated();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve(vote: "approve" | "reject") {
    if (!activePending?.id) return;
    setBusy(true);
    setError(null);
    const permissions: AgentPermissions = loadDefaultPermissions();
    try {
      await resolvePlanExecution(sessionId, {
        executionId: activePending.id,
        vote,
        permissions,
      });
      setPending(null);
      onUpdated();
      await refreshActions();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const hasExecutable = Boolean(recommended);

  if (!cursorReady) {
    return (
      <div className="plan-execute-panel plan-execute-panel--muted" role="note">
        plan 실행은 Cursor 에이전트(CURSOR_API_KEY + cursor-sdk)가 필요합니다.
      </div>
    );
  }

  return (
    <div className="plan-execute-panel" aria-label="plan 실행">
      <div className="plan-execute-panel__head">
        <span className="plan-execute-panel__title">실행 (thin execute)</span>
        {hasExecutable ? (
          <span className="plan-execute-panel__ready">
            execute ready
            {roadmap.length > 0 ? ` · +${roadmap.length} later` : ""}
          </span>
        ) : null}
        <span className="plan-execute-panel__hint">
          지금 실행 → dry-run → 승인
        </span>
      </div>

      {loadingActions ? (
        <p className="plan-execute-panel__muted">액션 불러오는 중…</p>
      ) : !hasExecutable ? (
        <p className="plan-execute-panel__muted">
          실행 가능한 3필드 액션이 없습니다 (`## 지금 실행` 또는 `## 다음에 할 일`).
        </p>
      ) : (
        <>
          <div className="plan-execute-now">
            <div className="plan-execute-now__label">
              <span className="plan-execute-badge plan-execute-badge--now">지금 실행</span>
            </div>
            <label
              className={[
                "plan-execute-action plan-execute-action--recommended",
                selectedIndex === recommended?.index ? "is-selected" : "",
                activePending ? "is-disabled" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <input
                type="radio"
                name="plan-action"
                checked={selectedIndex === recommended?.index}
                disabled={Boolean(disabled || busy || activePending)}
                onChange={() => setSelectedIndex(recommended?.index ?? null)}
              />
              <span className="plan-execute-action__body">
                <span className="plan-execute-action__what">{recommended?.what}</span>
                <span className="plan-execute-action__where">{recommended?.where}</span>
                <span className="plan-execute-action__verify">{recommended?.verify}</span>
              </span>
            </label>
          </div>

          {roadmap.length > 0 ? (
            <div className="plan-execute-roadmap">
              <div className="plan-execute-roadmap__label">실행 순서 (이후)</div>
              <ol className="plan-execute-roadmap__list">
                {roadmap.map((item) => (
                  <li
                    key={item.index}
                    className={[
                      "plan-execute-roadmap__item",
                      item.executable === false ? "is-oneliner" : "is-executable",
                    ].join(" ")}
                  >
                    {item.executable !== false ? (
                      <label
                        className={[
                          "plan-execute-action plan-execute-action--roadmap",
                          selectedIndex === item.index ? "is-selected" : "",
                          activePending ? "is-disabled" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        <input
                          type="radio"
                          name="plan-action"
                          checked={selectedIndex === item.index}
                          disabled={Boolean(disabled || busy || activePending)}
                          onChange={() => setSelectedIndex(item.index)}
                        />
                        <span className="plan-execute-action__body">
                          <span className="plan-execute-action__what">{item.what}</span>
                          <span className="plan-execute-action__where">{item.where}</span>
                        </span>
                      </label>
                    ) : (
                      <span className="plan-execute-roadmap__oneliner">
                        <span className="plan-execute-roadmap__index">{item.index}.</span>
                        {roadmapLabel(item)}
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </>
      )}

      {!activePending && hasExecutable ? (
        <button
          type="button"
          className="room-plan-btn room-plan-btn--accent plan-execute-panel__run"
          disabled={disabled || busy || selectedIndex == null}
          onClick={() => void handleDryRun()}
        >
          {busy ? "Cursor 실행 중…" : "dry-run (Cursor + 로컬 diff)"}
        </button>
      ) : null}

      {activePending ? (
        <div className="plan-execute-pending" role="region" aria-label="승인 대기">
          <div className="plan-execute-pending__head">
            <strong>승인 대기</strong>
            <span className="plan-execute-pending__status">
              {statusLabel(activePending.status)}
            </span>
          </div>
          {activePending.draft_summary ? (
            <pre className="plan-execute-pending__summary">
              {activePending.draft_summary}
            </pre>
          ) : null}
          {activePending.touched_paths?.length ? (
            <p className="plan-execute-pending__paths">
              변경 파일: {activePending.touched_paths.join(", ")}
            </p>
          ) : (
            <p className="plan-execute-pending__paths plan-execute-pending__paths--empty">
              변경 없음 (스냅샷 diff 없음)
            </p>
          )}
          {activePending.paths_outside_expected?.length ? (
            <p className="plan-execute-pending__warn">
              예상 범위 밖: {activePending.paths_outside_expected.join(", ")}
            </p>
          ) : null}
          {activePending.diff_stat ? (
            <pre className="plan-execute-pending__stat">{activePending.diff_stat}</pre>
          ) : null}
          {activePending.diff ? (
            <details className="plan-execute-pending__diff">
              <summary>로컬 diff</summary>
              <pre>{activePending.diff}</pre>
            </details>
          ) : null}
          <div className="plan-execute-pending__actions">
            <button
              type="button"
              className="room-plan-btn room-plan-btn--accent"
              disabled={disabled || busy}
              onClick={() => void handleResolve("approve")}
            >
              승인 (변경 유지)
            </button>
            <button
              type="button"
              className="room-plan-btn"
              disabled={disabled || busy}
              onClick={() => void handleResolve("reject")}
            >
              거부 (되돌리기)
            </button>
          </div>
        </div>
      ) : null}

      {executions.filter((row) => row.status !== "pending_approval").length ? (
        <details className="plan-execute-history">
          <summary>실행 기록</summary>
          <ul>
            {executions
              .filter((row) => row.status !== "pending_approval")
              .map((row) => (
                <li key={row.id}>
                  #{row.action_index ?? "?"}{" "}
                  {statusLabel(row.status)}
                  {row.touched_paths?.length
                    ? ` · ${row.touched_paths.join(", ")}`
                    : ""}
                </li>
              ))}
          </ul>
        </details>
      ) : null}

      {error ? <p className="plan-execute-panel__error">{error}</p> : null}
    </div>
  );
}
