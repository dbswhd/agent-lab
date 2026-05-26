import type { ReactNode } from "react";
import { SidebarToggle } from "./SidebarToggle";

type Props = {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  title: ReactNode;
  meta?: ReactNode;
  trailing?: ReactNode;
};

/** Title row: sidebar toggle + topic + optional agent pills (Cursor-style). */
export function ChatToolbar({ sidebarOpen, onToggleSidebar, title, meta, trailing }: Props) {
  return (
    <header className="chat-toolbar">
      <SidebarToggle open={sidebarOpen} onToggle={onToggleSidebar} />
      <div className="chat-toolbar__title">
        <h2>{title}</h2>
        {meta != null && meta !== "" && (
          <div className="chat-toolbar__meta">{meta}</div>
        )}
      </div>
      {trailing ? <div className="chat-toolbar__trailing">{trailing}</div> : null}
    </header>
  );
}
