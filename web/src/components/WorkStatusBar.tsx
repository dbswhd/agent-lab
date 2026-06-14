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
  /** Mission loop paused — show badge; stepper uses resume phase when set. */
  missionPaused?: boolean;
  /** MB-2 — call budget usage (distinct from context token budget). */
  budgetPct?: number;
};

/** Map mission_loop.phase (Layer 6) to Work tab stepper when mission is enabled. */
export function resolveWorkPhaseFromMission(
  missionPhase?: string | null,
  resumePhase?: string | null,
): WorkPhase | null {
  if (!missionPhase?.trim()) return null;
  const phase = missionPhase.trim().toUpperCase();
  if (phase === "MISSION_PAUSED") {
    const resume = resumePhase?.trim();
    if (resume) {
      return resolveWorkPhaseFromMission(resume, null);
    }
    return "plan_draft";
  }
  if (phase === "MISSION_DONE") return "done";
  if (phase === "MERGE_REVIEW" || phase === "PLAN_REJECT")
    return "review_needed";
  if (phase === "VERIFY") return "merge_verify";
  if (phase === "EXECUTE_QUEUE" || phase === "DRY_RUN" || phase === "REPAIR") {
    return "execute_pending";
  }
  if (
    phase === "DISCUSS" ||
    phase === "PLAN_GATE" ||
    phase === "MISSION_DEFINE"
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

export function WorkStatusBar({
  phase,
  metaLine,
  hasPlan,
  missionPaused = false,
  budgetPct = 0,
}: Props) {
  const phaseIndex = STEPS.findIndex((s) => s.id === phase);

  return (
    <div
      className={[
        "work-status-bar",
        missionPaused ? "work-status-bar--paused" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      role="status"
    >
      {missionPaused ? (
        <span
          className="work-status-bar__pause-badge"
          aria-label="Mission paused"
        >
          Paused
        </span>
      ) : null}
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
      {budgetPct > 0 ? (
        <div
          className="work-status-bar__budget"
          role="meter"
          aria-valuenow={budgetPct}
          aria-valuemin={0}
          aria-valuemax={100}
          title={`Call budget ${budgetPct}%`}
        >
          <span className="work-status-bar__budget-label">Budget</span>
          <span
            className="work-status-bar__budget-fill"
            style={{ width: `${Math.min(100, budgetPct)}%` }}
          />
          <span className="work-status-bar__budget-pct">{budgetPct}%</span>
        </div>
      ) : null}
      {metaLine && hasPlan ? (
        <p className="work-status-bar__meta">{metaLine}</p>
      ) : null}
    </div>
  );
}
