import { agentLabel } from "../utils/transcript";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";

const R2_REVIEW_ORDER = ["claude", "codex", "cursor"] as const;

type Props = {
  totalRounds: number;
  reviewMode: boolean;
  /** Selected agents (API order). */
  agents: string[];
  /** Keys `agentId:round` (1-based round). */
  doneKeys: Set<string>;
  active: { agent: string; round: number } | null;
};

function chipState(
  agent: string,
  round: number,
  doneKeys: Set<string>,
  active: Props["active"],
): "done" | "active" | "pending" {
  const k = `${agent}:${round}`;
  if (doneKeys.has(k)) return "done";
  if (active?.agent === agent && active.round === round) return "active";
  return "pending";
}

function Chip({
  agent,
  round,
  doneKeys,
  active,
  reviewOrder,
}: {
  agent: string;
  round: number;
  doneKeys: Set<string>;
  active: Props["active"];
  reviewOrder?: number;
}) {
  const st = chipState(agent, round, doneKeys, active);
  const label = agentLabel(agent);
  return (
    <span
      className={`turn-progress-chip turn-progress-chip--${st} turn-progress-chip--${agent}`}
      title={`${label} · R${round}`}
    >
      {st === "done" ? "✓ " : null}
      {reviewOrder != null ? (
        <span className="turn-progress-chip__ord" aria-hidden>
          {reviewOrder}
        </span>
      ) : null}
      {label}
      <span className="turn-progress-chip__r">R{round}</span>
    </span>
  );
}

function collapseSummary(
  agents: string[],
  totalRounds: number,
  doneKeys: Set<string>,
  active: Props["active"],
): string {
  if (active) {
    return `${agentLabel(active.agent)} · R${active.round} 진행 중`;
  }
  const expected = agents.length * totalRounds;
  if (doneKeys.size >= expected && expected > 0) {
    return "완료";
  }
  if (doneKeys.size > 0) {
    return `${doneKeys.size}/${expected} 완료`;
  }
  return totalRounds >= 2 ? "R1 병렬 · R2 순차" : "R1 병렬";
}

export function TurnProgressStrip({
  totalRounds,
  reviewMode,
  agents,
  doneKeys,
  active,
}: Props) {
  const r1 = agents.filter(Boolean);
  const r2 = reviewMode
    ? R2_REVIEW_ORDER.filter((a) => agents.includes(a))
    : agents.filter(Boolean);
  const summary = collapseSummary(agents, totalRounds, doneKeys, active);

  return (
    <CollapsibleGlassPanel
      className="turn-progress-panel"
      title="라운드 진행"
      summary={summary}
      defaultOpen
    >
      <div className="turn-progress-strip" aria-label="라운드 진행">
        <div className="turn-progress-strip__row">
          <span className="turn-progress-strip__title">1라운드 · 병렬</span>
          <div className="turn-progress-strip__chips">
            {r1.map((a) => (
              <Chip
                key={`${a}-1`}
                agent={a}
                round={1}
                doneKeys={doneKeys}
                active={active}
              />
            ))}
          </div>
        </div>
        {totalRounds >= 2 ? (
          <div className="turn-progress-strip__row">
            <span className="turn-progress-strip__title">
              2라운드 · 순차
              {reviewMode ? " · 검토" : ""}
            </span>
            <div className="turn-progress-strip__chips">
              {r2.map((a, i) => (
                <Chip
                  key={`${a}-2`}
                  agent={a}
                  round={2}
                  doneKeys={doneKeys}
                  active={active}
                  reviewOrder={reviewMode ? i + 1 : undefined}
                />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </CollapsibleGlassPanel>
  );
}
