import { ComposerPlanToggle } from "./ComposerPlanToggle";
import type { PlanMetaView } from "../utils/planMeta";

type Props = {
  planAfterSend: boolean;
  onPlanAfterSendChange: (on: boolean) => void;
  synthesizing: boolean;
  running: boolean;
  disabled?: boolean;
  onSynthesizeNow: () => void;
  planMeta: PlanMetaView;
};

export function PlanTabToolbar({
  planAfterSend,
  onPlanAfterSendChange,
  synthesizing,
  running,
  disabled,
  onSynthesizeNow,
  planMeta,
}: Props) {
  const metaSummary =
    planMeta.freshnessLabel !== "갱신 이력 없음"
      ? planMeta.freshnessLabel
      : planMeta.timeLabel !== "—"
        ? `${planMeta.timeLabel} · ${planMeta.triggerLabel}`
        : "아직 plan 갱신 기록 없음";

  return (
    <div className="plan-tab-toolbar" role="toolbar" aria-label="plan 도구">
      <div className="plan-tab-toolbar__actions">
        <ComposerPlanToggle
          checked={planAfterSend}
          onChange={onPlanAfterSendChange}
          disabled={disabled || running || synthesizing}
        />
        <button
          type="button"
          className="room-plan-btn room-plan-btn--accent"
          disabled={disabled || running || synthesizing}
          aria-busy={synthesizing}
          title="대화 내용만으로 plan.md 갱신"
          onClick={onSynthesizeNow}
        >
          {synthesizing ? "정리 중…" : "지금 정리"}
        </button>
      </div>
      <p className="plan-tab-toolbar__meta" title={metaSummary}>
        {metaSummary}
      </p>
    </div>
  );
}
