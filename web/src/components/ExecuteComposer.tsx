import type { PlanActionItem } from "../api/client";
import { actionKey } from "../hooks/usePlanExecute";

type Props = {
  items: PlanActionItem[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  selectedAction: PlanActionItem | null;
  busy?: boolean;
  disabled?: boolean;
  loading?: boolean;
  onDryRun: () => void;
  onOpenPlan?: () => void;
};

function stripRefs(text: string): string {
  return text.replace(/\s*\(ref:[^)]+\)/g, "").trim();
}

export function ExecuteComposer({
  items,
  selectedKey,
  onSelect,
  selectedAction,
  busy,
  disabled,
  loading,
  onDryRun,
  onOpenPlan,
}: Props) {
  const workspace = selectedAction?.execute_workspace?.label;

  return (
    <div className="execute-composer" aria-label="plan 실행">
      {loading ? (
        <p className="execute-composer__muted">plan 액션 불러오는 중…</p>
      ) : items.length === 0 ? (
        <p className="execute-composer__muted">
          실행 가능한 plan 액션이 없습니다.{" "}
          {onOpenPlan ? (
            <button type="button" className="execute-composer__link" onClick={onOpenPlan}>
              plan.md 확인
            </button>
          ) : (
            "plan.md에 `## 지금 실행` 섹션을 추가하세요."
          )}
        </p>
      ) : (
        <>
          <label className="execute-composer__field">
            <span className="execute-composer__label">plan 액션</span>
            <select
              className="execute-composer__select"
              value={selectedKey ?? ""}
              disabled={disabled || busy}
              onChange={(e) => onSelect(e.target.value)}
            >
              {items.map((item) => (
                <option key={actionKey(item)} value={actionKey(item)}>
                  #{item.index} {stripRefs(item.what).slice(0, 72)}
                </option>
              ))}
            </select>
          </label>
          {selectedAction ? (
            <p className="execute-composer__meta">
              {selectedAction.where ? (
                <span>어디서: {stripRefs(selectedAction.where)}</span>
              ) : null}
              {selectedAction.verify ? (
                <span> · 검증: {stripRefs(selectedAction.verify)}</span>
              ) : null}
              {workspace ? <span> · {workspace}</span> : null}
            </p>
          ) : null}
          <div className="execute-composer__actions">
            <button
              type="button"
              className="room-plan-btn room-plan-btn--accent execute-composer__run"
              disabled={disabled || busy || !selectedKey}
              onClick={onDryRun}
            >
              {busy ? "Cursor 실행 중…" : "dry-run"}
            </button>
            {onOpenPlan ? (
              <button
                type="button"
                className="room-plan-btn"
                disabled={disabled}
                onClick={onOpenPlan}
              >
                plan 전체
              </button>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}
