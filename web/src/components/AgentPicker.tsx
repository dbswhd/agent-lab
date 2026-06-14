import type { AgentOption } from "../api/client";

const AGENTS = ["cursor", "codex", "claude"] as const;

type Props = {
  agents: AgentOption[];
  selected: string[];
  disabled?: boolean;
  onToggle: (id: string) => void;
  /** Render in chat toolbar row (compact). */
  inline?: boolean;
};

export function AgentPicker({
  agents,
  selected,
  disabled,
  onToggle,
  inline,
}: Props) {
  return (
    <div
      className={`agent-picker${inline ? " agent-picker--inline" : ""}`}
      role="group"
      aria-label="에이전트 선택"
    >
      <div className="agent-picker-row">
        {agents
          .filter((a) => AGENTS.includes(a.id as (typeof AGENTS)[number]))
          .map((a) => {
            const on = selected.includes(a.id);
            return (
              <button
                key={a.id}
                type="button"
                className={`agent-pill agent-pill--${a.id} ${on ? "is-on" : ""} ${!a.ready ? "is-disabled" : ""}`}
                disabled={!a.ready || disabled}
                aria-pressed={on}
                title={!a.ready ? "미설정" : on ? "참여 중" : "제외됨"}
                onClick={() => onToggle(a.id)}
              >
                <img
                  className="agent-pill-icon"
                  src={`/icons/${a.id}.png`}
                  alt=""
                  width={inline ? 14 : 18}
                  height={inline ? 14 : 18}
                />
                <span className="agent-pill-name">{a.label}</span>
              </button>
            );
          })}
      </div>
    </div>
  );
}
