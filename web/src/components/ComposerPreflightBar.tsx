import type { AgentHealthRow } from "../api/client";
import { ComposerStrip } from "./ComposerStrip";

type Props = {
  agents: AgentHealthRow[];
  selected: string[];
};

/** ComposerPreflightBar — warning shown above the composer when
 *  one or more selected agents are not ready.
 *
 *  Renders via ComposerStrip (tone="danger") so it matches the other
 *  composer-area notices instead of its own one-off chrome.
 *
 *  Returns null when all agents are ready — safe to render unconditionally.
 */
export function ComposerPreflightBar({ agents, selected }: Props) {
  const blocked = selected
    .map((id) => agents.find((a) => a.id === id))
    .filter((row): row is AgentHealthRow => Boolean(row && !row.ready));

  if (blocked.length === 0) return null;

  return (
    <ComposerStrip
      tone="danger"
      role="alert"
      ariaLabel="에이전트 준비 상태"
      title="에이전트 준비 안 됨"
      description="선택은 유지됩니다. 재연결 후 전송하세요."
      items={blocked.map((row) => (
        <>
          <strong>{row.label}</strong>
          {": "}
          {row.reason ?? row.hint ?? "not ready"}
          {row.fallback ? (
            <span className="composer-strip__fallback"> fallback: {row.fallback}</span>
          ) : null}
        </>
      ))}
    />
  );
}
