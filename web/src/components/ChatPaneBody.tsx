import type { ReactNode } from "react";

/** Flex column wrapper so messages-scroll gets a bounded height. */
export function ChatPaneBody({ children }: { children: ReactNode }) {
  return <div className="chat-pane-body">{children}</div>;
}
