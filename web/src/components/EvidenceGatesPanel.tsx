import type { EvidenceGateRow } from "../api/client";

type Props = {
  gates: EvidenceGateRow[] | null | undefined;
  ko?: boolean;
};

const GATE_LABELS_KO: Record<string, string> = {
  plan_reread: "Plan reread",
  automated: "자동 검증",
  manual_merge: "Human merge",
  adversarial: "Adversarial",
  cleanup: "Cleanup",
};

/** MB-3 — five evidence gates on pending execution. */
export function EvidenceGatesPanel({ gates, ko = true }: Props) {
  if (!gates?.length) return null;
  const labels = GATE_LABELS_KO;

  return (
    <section
      id="work-evidence-gates"
      className="evidence-gates"
      data-testid="evidence-gates-panel"
    >
      <div className="evidence-gates__title">
        {ko ? "Evidence gates" : "Evidence gates"}
      </div>
      <ul className="evidence-gates__list">
        {gates.map((gate) => (
          <li
            key={gate.gate}
            className={[
              "evidence-gates__item",
              `evidence-gates__item--${gate.status ?? "pending"}`,
            ].join(" ")}
          >
            <span className="evidence-gates__name">
              {labels[gate.gate] ?? gate.gate}
            </span>
            <span className="evidence-gates__status">{gate.status}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
