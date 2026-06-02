import type { AgentHealthRow } from "../api/client";

type Props = {
  agents: AgentHealthRow[];
  selected: string[];
};

export function ComposerPreflightBar({ agents, selected }: Props) {
  const blocked = selected
    .map((id) => agents.find((a) => a.id === id))
    .filter((row): row is AgentHealthRow => Boolean(row && !row.ready));

  if (blocked.length === 0) return null;

  return (
    <div className="composer-preflight" role="alert">
      <span className="composer-preflight__title">전송 불가 — 에이전트 준비 안 됨</span>
      <ul className="composer-preflight__list">
        {blocked.map((row) => (
          <li key={row.id}>
            <strong>{row.label}</strong>: {row.reason ?? row.hint ?? "not ready"}
          </li>
        ))}
      </ul>
    </div>
  );
}
