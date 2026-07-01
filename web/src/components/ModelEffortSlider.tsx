import { useMemo } from "react";

const EFFORT_LEVEL_KO: Record<string, string> = {
  minimal: "최소",
  low: "낮음",
  medium: "보통",
  high: "높음",
  xhigh: "매우 높음",
  max: "최대",
};

const EFFORT_LABELS_KO: Record<string, string> = Object.fromEntries(
  Object.entries(EFFORT_LEVEL_KO).map(([k, v]) => [k, `작업량 ${v}`]),
);

type Props = {
  efforts: readonly string[];
  value: string;
  disabled?: boolean;
  onChange: (effort: string) => void;
};

/** Effort picker as a slider — the number of steps varies per agent and even
 * per specific model (Codex: 4 tiers, Claude: up to 6, both vary by release),
 * so a fixed-width segmented control doesn't scale; a track with N dots does.
 */
export function ModelEffortSlider({
  efforts,
  value,
  disabled = false,
  onChange,
}: Props) {
  const steps = useMemo(() => [...efforts], [efforts]);
  const index = Math.max(0, steps.indexOf(value));

  if (steps.length === 0) return null;

  const levelLabel = EFFORT_LEVEL_KO[value] ?? value;

  return (
    <div className="model-effort-slider" data-testid="model-effort-slider">
      <div className="model-effort-slider__head">
        <span className="model-effort-slider__title">
          <span className="model-effort-slider__title-prefix">작업량</span>{" "}
          {levelLabel}
        </span>
      </div>
      <div className="model-effort-slider__labels">
        <span>더 빠름</span>
        <span>더 스마트함</span>
      </div>
      <div
        className="model-effort-slider__track-wrap"
        role="group"
        aria-label="Model effort"
      >
        <div className="model-effort-slider__track">
          <div
            className="model-effort-slider__fill"
            style={{
              width:
                steps.length <= 1
                  ? "100%"
                  : `${(index / (steps.length - 1)) * 100}%`,
            }}
          />
          {steps.map((step, stepIndex) => {
            const left =
              steps.length <= 1
                ? "50%"
                : `${(stepIndex / (steps.length - 1)) * 100}%`;
            return (
              <button
                key={step}
                type="button"
                className={[
                  "model-effort-slider__dot",
                  stepIndex <= index ? "is-active" : "",
                  stepIndex === index ? "is-current" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                style={{ left }}
                disabled={disabled}
                aria-label={EFFORT_LABELS_KO[step] ?? step}
                aria-pressed={stepIndex === index}
                onClick={() => onChange(step)}
              />
            );
          })}
          <button
            type="button"
            className="model-effort-slider__thumb"
            disabled={disabled}
            style={{
              left:
                steps.length <= 1
                  ? "50%"
                  : `${(index / (steps.length - 1)) * 100}%`,
            }}
            aria-hidden
            tabIndex={-1}
          />
        </div>
      </div>
    </div>
  );
}
