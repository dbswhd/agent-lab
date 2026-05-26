import type { AgentRole } from "../utils/transcript";

type Props = {
  role: AgentRole;
  label?: string;
  size?: number;
};

const ICON_ROLES: Partial<Record<AgentRole, string>> = {
  cursor: "/icons/cursor.png",
  codex: "/icons/codex.png",
  claude: "/icons/claude.png",
};

const SHORT: Partial<Record<AgentRole, string>> = {
  you: "나",
  planner: "P",
  critic: "C",
  scribe: "S",
  system: "·",
};

export function Avatar({ role, label, size = 28 }: Props) {
  const icon = ICON_ROLES[role];
  if (icon) {
    return (
      <span
        className={`avatar avatar--icon-wrap avatar--${role}`}
        style={{ width: size, height: size }}
      >
        <img
          className="avatar avatar--img"
          src={icon}
          alt={label ?? role}
          width={size}
          height={size}
          aria-hidden
        />
      </span>
    );
  }
  const text = label?.slice(0, 2) ?? SHORT[role] ?? "?";
  return (
    <span
      className={`avatar avatar--${role}`}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden
    >
      {text}
    </span>
  );
}
