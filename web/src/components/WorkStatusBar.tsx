import type { PlanExecutionRecord } from "../api/client";

export type WorkPhase =
  | "plan_draft"
  | "review_needed"
  | "execute_pending"
  | "merge_verify"
  | "done";

const STEPS: { id: WorkPhase; label: string }[] = [
  { id: "plan_draft", label: "Plan" },
  { id: "review_needed", label: "Review" },
  { id: "execute_pending", label: "Execute" },
  { id: "merge_verify", label: "Verify" },
  { id: "done", label: "Done" },
];

type Props = {
  phase: WorkPhase;
  metaLine: string | null;
  hasPlan: boolean;
};

/** Map mission_loop.phase (Layer 6) to Work tab stepper when mission is enabled. */
export function resolveWorkPhaseFromMission(
  missionPhase?: string | null,
): WorkPhase | null {
  if (!missionPhase?.trim()) return null;
  const phase = missionPhase.trim().toUpperCase();
  if (phase === "MISSION_DONE") return "done";
  if (phase === "MERGE_REVIEW" || phase === "PLAN_REJECT") return "review_needed";
  if (phase === "VERIFY") return "merge_verify";
  if (phase === "EXECUTE_QUEUE" || phase === "DRY_RUN" || phase === "REPAIR") {
    return "execute_pending";
  }
  if (
    phase === "DISCUSS" ||
    phase === "PLAN_GATE" ||
    phase === "MISSION_DEFINE" ||
    phase === "MISSION_PAUSED"
  ) {
    return "plan_draft";
  }
  return null;
}

export function resolveWorkPhase(input: {
  hasPlan: boolean;
  hasPendingExecution: boolean;
  hasDryRunDiff: boolean;
  pendingAgreement: boolean;
  latestExecution?: PlanExecutionRecord | null;
}): WorkPhase {
  const exec = input.latestExecution;
  const oraclePass = exec?.oracle?.verdict === "pass";
  if (exec?.status === "completed" && oraclePass) return "done";
  if (
    exec &&
    (exec.status === "merged" ||
      exec.status === "review_required" ||
      exec.status === "pending_approval" ||
      exec.status === "merge_conflict" ||
      Boolean(exec.oracle))
  ) {
    return "merge_verify";
  }
  if (input.hasPendingExecution) return "execute_pending";
  if (input.hasDryRunDiff || input.pendingAgreement) return "review_needed";
  if (input.hasPlan) return "plan_draft";
  return "plan_draft";
}

export function WorkStatusBar({ phase, metaLine, hasPlan }: Props) {
  const phaseIndex = STEPS.findIndex((s) => s.id === phase);

  return (
    <div className="work-status-bar" role="status">
      <ol className="work-status-bar__steps" aria-label="Work progress">
        {STEPS.map((step, i) => (
          <li
            key={step.id}
            className={[
              "work-status-bar__step",
              i === phaseIndex ? "is-active" : i < phaseIndex ? "is-done" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {step.label}
          </li>
        ))}
      </ol>
      {metaLine && hasPlan ? (
        <p className="work-status-bar__meta">{metaLine}</p>
      ) : null}
    </div>
  );
}
