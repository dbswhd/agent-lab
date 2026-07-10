import { useEffect, useLayoutEffect, useRef, useState } from "react";
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

function turnTimelineState(
  running: boolean,
  hasError: boolean,
): "progress" | "error" | "done" {
  if (running) return "progress";
  if (hasError) return "error";
  return "done";
}

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
  const hasError = steps.some((item) => item.kind === "error");

  // Open while streaming; auto-collapse once the turn completes (errors stay open).
  // User toggles are respected until the running state flips again.
  const [open, setOpen] = useState(running || hasError);
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current !== running) {
      wasRunning.current = running;
      setOpen(running || hasError);
    }
  }, [running, hasError]);

  // While streaming the step list is height-clamped and pinned to the newest
  // step; the top fade only shows once older steps overflow past the clamp.
  const stepsRef = useRef<HTMLDivElement | null>(null);
  const [overflowing, setOverflowing] = useState(false);
  useLayoutEffect(() => {
    const el = stepsRef.current;
    let next = false;
    if (el && running) {
      el.scrollTop = el.scrollHeight;
      next = el.scrollHeight > el.clientHeight + 1;
    }
    setOverflowing((prev) => (prev === next ? prev : next));
  });

  if (steps.length === 0 && !running) return null;

  const stats = summarizeTurnItems(steps, running);
  const summary =
    (running && latestStepSummary(steps)) ||
    formatTurnActivitySummary(stats, running);
  const state = turnTimelineState(running, hasError);

  const stepsClass = `turn-timeline__steps${
    running ? " turn-timeline__steps--clamped" : ""
  }`;

  return (
    <details
      className="turn-timeline"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
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
        <div className="turn-timeline__window">
          <div ref={stepsRef} className={stepsClass}>
            {steps.map((item) => (
              <TurnStep key={item.id} item={item} running={running} />
            ))}
          </div>
          {overflowing ? (
            <div className="turn-timeline__steps-fade" aria-hidden />
          ) : null}
        </div>
      ) : null}
    </details>
  );
}
