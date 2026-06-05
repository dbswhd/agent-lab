import { useCallback, useRef, useState } from "react";
import {
  clampSessionRailWidth,
  SESSION_RAIL_MIN_WIDTH,
} from "../utils/sessionRailPrefs";

type Props = {
  open: boolean;
  width: number;
  onWidthChange: (width: number) => void;
  onWidthCommit: (width: number) => void;
  children: React.ReactNode;
};

export function SessionRail({
  open,
  width,
  onWidthChange,
  onWidthCommit,
  children,
}: Props) {
  const [isResizing, setIsResizing] = useState(false);
  const dragRef = useRef({ startX: 0, startWidth: SESSION_RAIL_MIN_WIDTH });

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
      const delta = event.clientX - dragRef.current.startX;
      onWidthChange(
        clampSessionRailWidth(dragRef.current.startWidth + delta),
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
      onWidthCommit(clampSessionRailWidth(finalWidth));
    },
    [isResizing, onWidthCommit],
  );

  return (
    <aside
      className={[
        "session-rail",
        isResizing ? "session-rail--resizing" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label="Sessions"
      aria-hidden={!open}
      style={
        {
          "--session-rail-width": `${width}px`,
        } as React.CSSProperties
      }
    >
      {open ? (
        <div
          className="session-rail__resize-handle"
          role="separator"
          aria-orientation="vertical"
          aria-label="세션 목록 너비 조절"
          onPointerDown={onResizePointerDown}
          onPointerMove={onResizePointerMove}
          onPointerUp={(event) => finishResize(event, width)}
          onPointerCancel={(event) => finishResize(event, width)}
        />
      ) : null}
      {children}
    </aside>
  );
}
