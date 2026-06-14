import type { TurnBudgetPayload } from "../api/client";

type Props = {
  budget: TurnBudgetPayload | null | undefined;
  ko?: boolean;
};

function meterClass(pct: number): string {
  if (pct >= 90) return "turn-budget__fill--critical";
  if (pct >= 70) return "turn-budget__fill--warn";
  return "turn-budget__fill--ok";
}

/** MB-2 — session call budget meter (Inspector / Work). */
export function TurnBudgetSection({ budget, ko = true }: Props) {
  if (!budget) return null;
  const pct = Math.min(100, Math.max(0, budget.budget_pct ?? 0));
  const counters = budget.counters ?? {};
  const caps = budget.caps ?? {};
  const agentUsed = Number(counters.agent_calls_per_human_turn ?? 0);
  const agentCap = Number(caps.agent_calls_per_human_turn ?? 9);

  return (
    <section className="turn-budget" data-testid="turn-budget-section">
      <div className="turn-budget__head">
        <span className="turn-budget__title">
          {ko ? "호출 예산" : "Call budget"}
        </span>
        <span className="turn-budget__pct">{pct}%</span>
      </div>
      <div
        className="turn-budget__meter"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={ko ? "호출 예산 사용률" : "Call budget usage"}
      >
        <div
          className={["turn-budget__fill", meterClass(pct)].join(" ")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="turn-budget__detail">
        {ko ? "이번 턴 에이전트 호출" : "Agent calls this turn"}: {agentUsed}/
        {agentCap}
      </p>
      {budget.overflow ? (
        <p className="turn-budget__overflow" role="status">
          {budget.overflow.message ?? budget.overflow.key}
        </p>
      ) : null}
    </section>
  );
}
