import type { ReactNode } from "react";
import {
  TURN_STRATEGY_OPTIONS,
  turnProfileDescription,
  type ComposerTurnProfile,
} from "../utils/turnProfile";

type Props = {
  value: ComposerTurnProfile;
  onChange: (profile: ComposerTurnProfile) => void;
  disabled?: boolean;
  /** Segmented control 오른쪽 (정리 토글 · 효율 토글 등) */
  trailing?: ReactNode;
};

export function ComposerTurnPicker({
  value,
  onChange,
  disabled,
  trailing,
}: Props) {
  const description = turnProfileDescription(value);

  return (
    <div
      className="composer-turn-picker"
      role="radiogroup"
      aria-label="토론 방식"
      aria-describedby="composer-turn-desc"
    >
      <div className="composer-turn-picker__head">
        <div className="composer-turn-seg">
          {TURN_STRATEGY_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={value === opt.id}
              className={[
                value === opt.id ? "is-active" : "",
                opt.id === "free" ? "composer-turn-seg__infinity" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              data-profile={opt.id}
              disabled={disabled}
              title={opt.description}
              onClick={() => onChange(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {trailing}
      </div>
      {description ? (
        <p id="composer-turn-desc" className="composer-turn-hint">
          {description}
        </p>
      ) : null}
    </div>
  );
}
