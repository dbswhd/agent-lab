import type { PlanExecutionRecord } from "../api/client";

type Props = {
  execution: PlanExecutionRecord | null;
};

/** Latest execution external handoff summary (MB-8 / GJC runner). */
export function GjcExternalHandoffStrip({ execution }: Props) {
  const handoff = execution?.external_handoff;
  if (!handoff?.evidence_summary) {
    return null;
  }
  const clean = handoff.stopped_cleanly !== false;
  return (
    <div
      className={`gjc-handoff-strip gjc-handoff-strip--${clean ? "ok" : "warn"}`}
      role="status"
      data-testid="gjc-external-handoff-strip"
    >
      <span className="gjc-handoff-strip__badge">
        {clean ? "GJC handoff" : "GJC handoff (unclean stop)"}
      </span>
      <p className="gjc-handoff-strip__summary">{handoff.evidence_summary}</p>
      {handoff.changed_files?.length ? (
        <p className="gjc-handoff-strip__files">
          {handoff.changed_files.slice(0, 4).join(", ")}
          {handoff.changed_files.length > 4 ? " …" : ""}
        </p>
      ) : null}
    </div>
  );
}
