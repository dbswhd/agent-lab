import type { CSSProperties } from "react";
import type { AgentRole } from "../utils/transcript";

type Props = {
  role: AgentRole;
  label?: string;
  size?: number;
  variant?: "flat" | "orb";
};

const ICON_ROLES: Partial<Record<AgentRole, string>> = {
  cursor: "/icons/cursor.png",
  codex: "/icons/vendor/codex-app.png",
  claude: "/icons/vendor/claude-app.png",
};

/** Full-color vendor marks on a white round tile (not inverted orb glyphs). */
const BRAND_LOGO_ROLES = new Set<AgentRole>(["cursor", "codex", "claude"]);

const SHORT: Partial<Record<AgentRole, string>> = {
  you: "나",
  planner: "P",
  critic: "C",
  scribe: "S",
  system: "·",
  kimi: "K",
  kimi_work: "KW",
};

function avatarBoxStyle(size: number): CSSProperties {
  return {
    width: size,
    height: size,
    flex: `0 0 ${size}px`,
  };
}

/**
 * Agent avatar — brand logo tile, gradient orb, or flat initials.
 */
export function Avatar({ role, label, size = 28, variant = "orb" }: Props) {
  const sm = size <= 22 ? " avatar--sm" : "";
  const title = label ?? role;
  const boxStyle = avatarBoxStyle(size);
  const icon = ICON_ROLES[role];

  if (variant === "orb" && icon && BRAND_LOGO_ROLES.has(role)) {
    return (
      <span
        className={`avatar avatar--logo avatar--${role}${sm}`}
        style={boxStyle}
        title={title}
        aria-hidden
      >
        <img src={icon} alt="" aria-hidden />
      </span>
    );
  }

  if (variant === "orb") {
    return (
      <span
        className={`avatar avatar--orb avatar--${role}${sm}`}
        style={boxStyle}
        title={title}
        aria-hidden
      />
    );
  }

  if (icon) {
    return (
      <span
        className={`avatar avatar--logo avatar--${role}${sm}`}
        style={boxStyle}
        title={title}
        aria-hidden
      >
        <img src={icon} alt="" aria-hidden />
      </span>
    );
  }

  const text = label?.slice(0, 2) ?? SHORT[role] ?? "?";
  return (
    <span
      className={`avatar avatar--${role}${sm}`}
      style={{ ...boxStyle, fontSize: size * 0.4 }}
      title={title}
      aria-hidden
    >
      {text}
    </span>
  );
}
