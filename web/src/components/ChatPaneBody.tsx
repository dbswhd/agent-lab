import type { ReactNode } from "react";

/** Flex column wrapper so messages-scroll gets a bounded height. */
export function ChatPaneBody({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={["chat-pane-body", className].filter(Boolean).join(" ")}
    >
      {children}
    </div>
  );
}
