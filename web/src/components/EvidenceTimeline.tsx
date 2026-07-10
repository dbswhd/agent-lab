import type { EvidenceEntry } from "../api/client";

type Props = {
  entries: EvidenceEntry[];
  ko?: boolean;
  compact?: boolean;
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

/** MB-4 — append-only evidence.jsonl tail in Work / Run. */
export function EvidenceTimeline({
  entries,
  ko = true,
  compact = false,
}: Props) {
  if (!entries.length) return null;

  return (
    <section
      className={[
        "evidence-timeline",
        compact ? "evidence-timeline--compact" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid="evidence-timeline"
    >
      <div className="evidence-timeline__title">
        {ko ? "증거 타임라인" : "Evidence timeline"}
      </div>
      <ol className="evidence-timeline__list">
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
    </section>
  );
}
