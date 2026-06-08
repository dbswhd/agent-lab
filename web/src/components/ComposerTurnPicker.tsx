import type { ReactNode } from "react";
import {
  turnStrategyOptions,
  turnProfileDescription,
  type ComposerTurnProfile,
} from "../utils/turnProfile";
import type { Locale } from "../i18n/locale";

type Props = {
  value: ComposerTurnProfile;
  onChange: (profile: ComposerTurnProfile) => void;
  disabled?: boolean;
  locale?: Locale;
  /** Right of the segmented control (cleanup toggle · efficiency toggle …) */
  trailing?: ReactNode;
  /** Inline with mode description (single hint line). */
  costHint?: string | null;
  /** When set, replaces joined description + costHint (prototype one-liner). */
  hint?: string | null;
};

/**
 * Rebuilt turn-strategy picker. Prop signature + turn strategies preserved.
 * New class system: `.turn-seg` segmented + `.turn-hint`.
 */
export function ComposerTurnPicker({
  value,
  onChange,
  disabled,
  locale = "en",
  trailing,
  costHint,
  hint,
}: Props) {
  const options = turnStrategyOptions(locale);
  const description = turnProfileDescription(value);
  const hintText =
    hint?.trim() ||
    [description, costHint?.trim()].filter(Boolean).join(" · ");

  return (
    <div
      className="turn-row"
      role="radiogroup"
      aria-label={locale === "ko" ? "토론 방식" : "Turn strategy"}
      aria-describedby="composer-turn-desc"
    >
      <div className="turn-picker__head">
        <div className="turn-seg">
          {options.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={value === opt.id}
              className={[
                value === opt.id ? "is-active" : "",
                opt.id === "free" ? "turn-seg__infinity" : "",
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
        {trailing ? <div className="turn-picker__trailing">{trailing}</div> : null}
      </div>
      {hintText ? (
        <p id="composer-turn-desc" className="turn-hint">
          {hintText}
        </p>
      ) : null}
    </div>
  );
}
