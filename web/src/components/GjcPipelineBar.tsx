import type { GjcPipelinePhase } from "../utils/gjcPipelinePhase";

const STEPS: { id: GjcPipelinePhase; label: string }[] = [
  { id: "interview", label: "Interview" },
  { id: "plan", label: "Plan" },
  { id: "approve", label: "Approve" },
  { id: "goal", label: "Goal" },
  { id: "verify", label: "Verify" },
];

type Props = {
  phase: GjcPipelinePhase;
  metaLine?: string | null;
  externalRunnerEnabled?: boolean;
};

export function GjcPipelineBar({
  phase,
  metaLine = null,
  externalRunnerEnabled = false,
}: Props) {
  const phaseIndex =
    phase === "done"
      ? STEPS.length
      : STEPS.findIndex((step) => step.id === phase);

  return (
    <div className="gjc-pipeline-bar" role="status" aria-label="GJC pipeline">
      <div className="gjc-pipeline-bar__head">
        <span className="gjc-pipeline-bar__title">Pipeline</span>
        {externalRunnerEnabled ? (
          <span className="gjc-pipeline-bar__badge">GJC external</span>
        ) : null}
        {phase === "done" ? (
          <span className="gjc-pipeline-bar__done">Done</span>
        ) : null}
      </div>
      <ol className="work-status-bar__steps gjc-pipeline-bar__steps">
        {STEPS.map((step, index) => (
          <li
            key={step.id}
            className={[
              "work-status-bar__step",
              index === phaseIndex ? "is-active" : "",
              index < phaseIndex || phase === "done" ? "is-done" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {step.label}
          </li>
        ))}
      </ol>
      {metaLine ? <p className="work-status-bar__meta">{metaLine}</p> : null}
    </div>
  );
}
