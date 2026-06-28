import type { AgentRole } from "../utils/transcript";
import { Avatar } from "./Avatar";

type AgentRow = {
  id: string;
  label: string;
};

type Props = {
  agents: readonly AgentRow[];
  max?: number;
  size?: number;
};

function asAgentRole(id: string): AgentRole {
  return id as AgentRole;
}

export function ComposerAgentStack({ agents, max = 4, size = 32 }: Props) {
  if (agents.length === 0) return null;
  const visible = agents.slice(0, max);
  const overflow = agents.length - visible.length;

  return (
    <div
      className="composer-agent-stack"
      aria-label={agents.map((a) => a.label).join(", ")}
    >
      {visible.map((agent) => (
        <Avatar
          key={agent.id}
          role={asAgentRole(agent.id)}
          label={agent.label}
          size={size}
          variant="orb"
        />
      ))}
      {overflow > 0 ? (
        <span className="composer-agent-stack__more" aria-hidden>
          +{overflow}
        </span>
      ) : null}
    </div>
  );
}
