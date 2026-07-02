import type { TurnItem } from "../utils/turnItems";
import {
  activityStepSummary,
  formatTurnActivitySummary,
  latestStepSummary,
  reasoningStepSummary,
  stepDetailsOpen,
  summarizeTurnItems,
  toolStepSummary,
} from "../utils/turnTimeline";

type Props = {
  readonly items?: readonly TurnItem[];
  readonly running: boolean;
};

function TurnStep({ item, running }: { item: TurnItem; running: boolean }) {
  if (item.kind === "error") {
    return (
      <details className="turn-step turn-step--error" open>
        <summary>{item.text}</summary>
      </details>
    );
  }

  if (item.kind === "tool") {
    const summary = toolStepSummary(item);
    return (
      <details
        className="turn-step turn-step--tool"
        open={stepDetailsOpen(item, running) || undefined}
      >
        <summary>{summary}</summary>
        {(item.args || item.output) && (
          <div className="turn-step__body">
            {item.args ? (
              <code className="turn-step__cmd">{item.args}</code>
            ) : null}
            {item.output ? <pre>{item.output}</pre> : null}
          </div>
        )}
      </details>
    );
  }

  if (item.kind === "reasoning_summary") {
    const summary = reasoningStepSummary(item);
    return (
      <details
        className="turn-step turn-step--thought"
        open={stepDetailsOpen(item, running) || undefined}
      >
        <summary>{summary}</summary>
        <div className="turn-step__body turn-step__body--prose">
          {item.text}
        </div>
      </details>
    );
  }

  if (item.kind === "activity") {
    const summary = activityStepSummary(item);
    return (
      <details
        className="turn-step turn-step--thought"
        open={stepDetailsOpen(item, running) || undefined}
      >
        <summary>{summary}</summary>
        <div className="turn-step__body turn-step__body--prose">
          {item.text}
        </div>
      </details>
    );
  }

  return null;
}

export function TurnActivityGroup({ items = [], running }: Props) {
  const steps = items.filter((item) => item.kind !== "final_output");
  if (steps.length === 0 && !running) return null;

  const stats = summarizeTurnItems(steps, running);
  const summary =
    (running && latestStepSummary(steps)) ||
    formatTurnActivitySummary(stats, running);
  const hasError = steps.some((item) => item.kind === "error");
  const state = running ? "progress" : hasError ? "error" : "done";

  return (
    <details className="turn-timeline" open={steps.length > 0 || running}>
      <summary
        className={`turn-timeline__summary turn-timeline__summary--${state}`}
      >
        <span className="turn-timeline__label">{summary}</span>
        {stats.linesAdded > 0 || stats.linesRemoved > 0 ? (
          <span className="turn-timeline__diff" aria-label="Diff stat">
            {stats.linesAdded > 0 ? (
              <span className="turn-timeline__add">+{stats.linesAdded}</span>
            ) : null}
            {stats.linesRemoved > 0 ? (
              <span className="turn-timeline__del">-{stats.linesRemoved}</span>
            ) : null}
          </span>
        ) : null}
      </summary>
      {steps.length > 0 ? (
        <div className="turn-timeline__steps">
          {steps.map((item) => (
            <TurnStep key={item.id} item={item} running={running} />
          ))}
        </div>
      ) : null}
    </details>
  );
}
