import type { ReactNode } from "react";
import { Avatar } from "./Avatar";
import type { AgentRole } from "../utils/transcript";

type Props = {
  role: AgentRole;
  label?: string;
  author: string;
  highlighted?: boolean;
  peer?: boolean;
  chatLineIndex?: number;
  meta?: ReactNode;
  className?: string;
  roleAttr?: "article" | "status";
  ariaLabel?: string;
  children: ReactNode;
};

/** Prototype console turn — avatar + author head, flat body (no left rail). */
export function ConsoleTurn({
  role,
  label,
  author,
  highlighted,
  peer,
  chatLineIndex,
  meta,
  className,
  roleAttr,
  ariaLabel,
  children,
}: Props) {
  return (
    <div
      className={[
        "turn",
        `turn--${role}`,
        className,
        peer ? "turn--peer" : "",
        highlighted ? "turn--highlight" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      role={roleAttr}
      aria-label={ariaLabel}
      {...(chatLineIndex != null ? { "data-chat-line": chatLineIndex } : {})}
    >
      <div className="turn__head">
        <Avatar role={role} label={label} size={20} />
        <span className="turn__author">{author}</span>
        {meta}
      </div>
      <div className="turn__content">{children}</div>
    </div>
  );
}
