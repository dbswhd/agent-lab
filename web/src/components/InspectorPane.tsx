import { useCallback, useRef, useState } from "react";
import type { InspectorTab } from "../utils/workspaceTabs";
import { INSPECTOR_TABS } from "../utils/workspaceTabs";
import {
  clampInspectorWidth,
  INSPECTOR_MIN_WIDTH,
} from "../utils/inspectorPanePrefs";

type Props = {
  active: InspectorTab;
  onChange: (tab: InspectorTab) => void;
  children: React.ReactNode;
  disabled?: boolean;
  open: boolean;
  width: number;
  onWidthChange: (width: number) => void;
  onWidthCommit: (width: number) => void;
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
}: Props) {
  const [isResizing, setIsResizing] = useState(false);
  const dragRef = useRef({ startX: 0, startWidth: INSPECTOR_MIN_WIDTH });

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
      onWidthChange(
        clampInspectorWidth(dragRef.current.startWidth + delta),
      );
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
        "inspector-pane",
        open ? "" : "inspector-pane--collapsed",
        isResizing ? "inspector-pane--resizing" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label="Inspector"
      aria-hidden={!open}
      style={
        {
          "--inspector-pane-width": `${width}px`,
        } as React.CSSProperties
      }
    >
      {open ? (
        <div
          className="inspector-pane__resize-handle"
          role="separator"
          aria-orientation="vertical"
          aria-label="Inspector 너비 조절"
          onPointerDown={onResizePointerDown}
          onPointerMove={onResizePointerMove}
          onPointerUp={(event) => finishResize(event, width)}
          onPointerCancel={(event) => finishResize(event, width)}
        />
      ) : null}
      <div className="inspector-pane__tabs" role="tablist">
        {INSPECTOR_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active === tab.id}
            className={[
              "inspector-pane__tab",
              active === tab.id ? "is-active" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            disabled={disabled || !open}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="inspector-pane__body" role="tabpanel">
        <div className="inspector-pane__body-inner">{children}</div>
      </div>
    </aside>
  );
}
