import type { ReactNode } from "react";
import {
  TURN_PROFILE_OPTIONS,
  turnProfileDescription,
  type ComposerTurnProfile,
} from "../utils/turnProfile";
import { profileLabel } from "../utils/turnProfileBandit";

type Props = {
  value: ComposerTurnProfile;
  onChange: (profile: ComposerTurnProfile) => void;
  disabled?: boolean;
  recommendedProfile?: ComposerTurnProfile | null;
  onApplyRecommendation?: () => void;
  /** Segmented control 오른쪽 (효율 토글 등) */
  trailing?: ReactNode;
};

export function ComposerTurnPicker({
  value,
  onChange,
  disabled,
  recommendedProfile,
  onApplyRecommendation,
  trailing,
}: Props) {
  const description = turnProfileDescription(value);
  const showRec =
    recommendedProfile &&
    recommendedProfile !== value &&
    onApplyRecommendation;

  return (
    <div
      className="composer-turn-picker"
      role="radiogroup"
      aria-label="응답 방식"
      aria-describedby="composer-turn-desc"
    >
      <div className="composer-turn-picker__head">
        <div className="composer-turn-seg">
          {TURN_PROFILE_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={value === opt.id}
              className={[
                value === opt.id ? "is-active" : "",
                opt.id === "free" ? "composer-turn-seg__infinity" : "",
                recommendedProfile === opt.id ? "is-recommended" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              data-profile={opt.id}
              disabled={disabled}
              onClick={() => onChange(opt.id)}
            >
              {opt.label}
              {recommendedProfile === opt.id ? (
                <span className="composer-turn-rec-badge">추천</span>
              ) : null}
            </button>
          ))}
        </div>
        {trailing}
      </div>
      {showRec ? (
        <p className="composer-turn-rec-hint">
          학습 추천:{" "}
          <button
            type="button"
            className="composer-turn-rec-apply"
            onClick={onApplyRecommendation}
            disabled={disabled}
          >
            {profileLabel(recommendedProfile)} 적용
          </button>
        </p>
      ) : null}
      {description ? (
        <p id="composer-turn-desc" className="composer-turn-hint">
          {description}
        </p>
      ) : null}
    </div>
  );
}
