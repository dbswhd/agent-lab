import { useCallback, useRef, useState } from "react";
import type { InspectorTab } from "../utils/workspaceTabs";
import {
  clampInspectorWidth,
  INSPECTOR_MIN_WIDTH,
} from "../utils/inspectorPanePrefs";
import { useLocale } from "../i18n/useLocale";

const TAB_IDS: InspectorTab[] = ["overview", "tasks", "inbox"];

type Props = {
  active: InspectorTab;
  onChange: (tab: InspectorTab) => void;
  children: React.ReactNode;
  disabled?: boolean;
  open: boolean;
  width: number;
  onWidthChange: (width: number) => void;
  onWidthCommit: (width: number) => void;
  badges?: Partial<Record<InspectorTab, number>>;
};

export function InspectorPane({
  active,
  onChange,
  children,
  disabled,
  open,
  width,
  onWidthChange,
  onWidthCommit,
  badges,
}: Props) {
  const { msg } = useLocale();
  const [isResizing, setIsResizing] = useState(false);
  const dragRef = useRef({ startX: 0, startWidth: INSPECTOR_MIN_WIDTH });

  const tabLabel = (tab: InspectorTab) => {
    if (tab === "overview") return msg.ctxOverview;
    if (tab === "tasks") return msg.ctxTasks;
    return msg.ctxInbox;
  };

  const onResizePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!open) return;
      event.preventDefault();
      dragRef.current = { startX: event.clientX, startWidth: width };
      setIsResizing(true);
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    [open, width],
  );

  const onResizePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!isResizing) return;
      const delta = dragRef.current.startX - event.clientX;
      onWidthChange(clampInspectorWidth(dragRef.current.startWidth + delta));
    },
    [isResizing, onWidthChange],
  );

  const finishResize = useCallback(
    (event: React.PointerEvent<HTMLDivElement>, finalWidth: number) => {
      if (!isResizing) return;
      setIsResizing(false);
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      onWidthCommit(clampInspectorWidth(finalWidth));
    },
    [isResizing, onWidthCommit],
  );

  return (
    <aside
      className={[
        "context-sidebar",
        open ? "" : "context-sidebar--collapsed",
        isResizing ? "inspector-pane--resizing" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label={msg.ctxTitle}
      aria-hidden={!open}
      style={
        {
          "--inspector-pane-width": `${width}px`,
          "--context-sidebar-width": `${width}px`,
        } as React.CSSProperties
      }
    >
      {open ? (
        <div
          className="context-sidebar__resize-handle"
          role="separator"
          aria-orientation="vertical"
          aria-label="Context sidebar width"
          onPointerDown={onResizePointerDown}
          onPointerMove={onResizePointerMove}
          onPointerUp={(event) => finishResize(event, width)}
          onPointerCancel={(event) => finishResize(event, width)}
        />
      ) : null}

      <div className="context-sidebar__head">
        <SparkleIcon />
        <span className="context-sidebar__title">{msg.ctxTitle}</span>
      </div>

      <div className="ctx-tabs" role="tablist">
        {TAB_IDS.map((tab) => {
          const badgeCount = badges?.[tab];
          const isDanger = tab === "tasks" && Boolean(badgeCount);
          const isAccent = tab === "inbox" && Boolean(badgeCount);

          return (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={active === tab}
              className={[
                "ctx-tab",
                active === tab ? "is-active" : "",
                isDanger ? "ctx-tab--danger" : "",
                isAccent ? "ctx-tab--accent" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              disabled={disabled || !open}
              onClick={() => onChange(tab)}
            >
              {tabLabel(tab)}
              {badgeCount ? (
                <span
                  className={[
                    "ctx-tab__badge",
                    isDanger ? "ctx-tab__badge--danger" : "",
                    isAccent ? "ctx-tab__badge--accent" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  {badgeCount}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="context-sidebar__body scroll-y" role="tabpanel">
        {children}
      </div>
    </aside>
  );
}

function SparkleIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="15"
      height="15"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 2l1.4 4.3L18 8l-4.6 1.7L12 14l-1.4-4.3L6 8l4.6-1.7L12 2z" />
      <path d="M5 16l.7 2.1L8 19l-2.3.9L5 22l-.7-2.1L2 19l2.3-.9L5 16z" />
    </svg>
  );
}
