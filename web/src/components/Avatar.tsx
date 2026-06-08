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

/**
 * Rebuilt presentation. Prop signature preserved (role/label/size).
 * New class system: `.avatar` + `.avatar--<role>` (+ `--sm` under 22px).
 */
export function Avatar({ role, label, size = 28 }: Props) {
  const sm = size <= 22 ? " avatar--sm" : "";
  const icon = ICON_ROLES[role];
  if (icon) {
    return (
      <span
        className={`avatar avatar--${role}${sm}`}
        style={{ width: size, height: size }}
      >
        <img src={icon} alt={label ?? role} width={size} height={size} aria-hidden />
      </span>
    );
  }
  const text = label?.slice(0, 2) ?? SHORT[role] ?? "?";
  return (
    <span
      className={`avatar avatar--${role}${sm}`}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
      aria-hidden
    >
      {text}
    </span>
  );
}
