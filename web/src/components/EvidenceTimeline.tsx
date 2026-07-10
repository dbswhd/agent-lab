import { useEffect, useId, useMemo, useState } from "react";
import type { EvidenceEntry } from "../api/client";

type Props = {
  entries: EvidenceEntry[];
  ko?: boolean;
  compact?: boolean;
  /** When true, collapse like To-dos during busy execute (UI-only). */
  busy?: boolean;
  defaultExpanded?: boolean;
};

const PHASE_LABELS: Record<string, string> = {
  DRY_RUN: "Dry-run",
  MERGE: "Merge",
  VERIFY: "Verify",
  REPAIR: "Repair",
  MONITOR: "Monitor",
};

function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? phase;
}

function latestSummary(entries: EvidenceEntry[], ko: boolean): string {
  const last = entries[entries.length - 1];
  if (!last) return ko ? "비어 있음" : "Empty";
  const phase = phaseLabel(String(last.phase ?? ""));
  const kind = String(last.kind ?? "event");
  return phase ? `${phase} · ${kind}` : kind;
}

/** MB-4 — append-only evidence.jsonl tail in Work / Run (collapsible like To-dos). */
export function EvidenceTimeline({
  entries,
  ko = true,
  compact = false,
  busy = false,
  defaultExpanded = true,
}: Props) {
  const panelId = useId();
  const [expanded, setExpanded] = useState(defaultExpanded);

  useEffect(() => {
    if (busy) setExpanded(false);
  }, [busy]);

  const summary = useMemo(() => latestSummary(entries, ko), [entries, ko]);

  if (!entries.length) return null;

  return (
    <section
      className={[
        "evidence-timeline",
        compact ? "evidence-timeline--compact" : "",
        expanded
          ? "evidence-timeline--expanded"
          : "evidence-timeline--collapsed",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid="evidence-timeline"
      aria-label={ko ? "증거 타임라인" : "Evidence timeline"}
    >
      <div className="evidence-timeline__head">
        <button
          type="button"
          className="evidence-timeline__toggle"
          aria-expanded={expanded}
          aria-controls={panelId}
          data-testid="evidence-timeline-toggle"
          onClick={() => setExpanded((open) => !open)}
        >
          <span className="evidence-timeline__head-main">
            <span className="evidence-timeline__title-row">
              <span className="evidence-timeline__title">
                {ko ? "증거 타임라인" : "Evidence timeline"}
              </span>
              <span className="evidence-timeline__count">{entries.length}</span>
            </span>
            {!expanded ? (
              <span className="evidence-timeline__summary" title={summary}>
                {summary}
              </span>
            ) : null}
          </span>
          <span
            className={[
              "evidence-timeline__chevron",
              expanded ? "evidence-timeline__chevron--open" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-hidden
          />
        </button>
      </div>

      {expanded ? (
        <ol id={panelId} className="evidence-timeline__list">
          {entries.map((row, i) => (
            <li
              key={`${row.at ?? i}-${row.kind ?? "ev"}`}
              className="evidence-timeline__item"
            >
              <span className="evidence-timeline__phase">
                {phaseLabel(String(row.phase ?? ""))}
              </span>
              <span className="evidence-timeline__kind">
                {row.kind ?? "event"}
              </span>
              {row.detail ? (
                <span className="evidence-timeline__detail" title={row.detail}>
                  {row.detail}
                </span>
              ) : null}
              {row.at ? (
                <time className="evidence-timeline__at" dateTime={row.at}>
                  {row.at.slice(11, 19)}
                </time>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
