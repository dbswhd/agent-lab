import type { AgentHealthRow } from "../api/client";

type Props = {
  agents: AgentHealthRow[];
  selected: string[];
};

/** ComposerPreflightBar — warning shown above the composer when
 *  one or more selected agents are not ready.
 *
 *  Uses .preflight-bar / .preflight-bar__* classes (overlays.css).
 *  Drop-in for old component that used .composer-preflight (legacy-bridge.css).
 *
 *  Returns null when all agents are ready — safe to render unconditionally.
 */
export function ComposerPreflightBar({ agents, selected }: Props) {
  const blocked = selected
    .map((id) => agents.find((a) => a.id === id))
    .filter((row): row is AgentHealthRow => Boolean(row && !row.ready));

  if (blocked.length === 0) return null;

  return (
    <div className="preflight-bar" role="alert">
      <span className="preflight-bar__title">
        전송 불가 — 에이전트 준비 안 됨
      </span>
      <ul className="preflight-bar__list">
        {blocked.map((row) => (
          <li key={row.id}>
            <strong>{row.label}</strong>
            {": "}
            {row.reason ?? row.hint ?? "not ready"}
            {row.fallback ? (
              <span className="preflight-bar__fallback">
                {" "}
                fallback: {row.fallback}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
