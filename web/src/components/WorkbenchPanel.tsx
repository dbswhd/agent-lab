import { useCallback, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { RightPanelMode } from "../utils/workspaceTabs";
import {
  WORKBENCH_PANEL_MIN_WIDTH,
  clampWorkbenchPanelWidth,
} from "../utils/inspectorPanePrefs";
import type { Locale } from "../i18n/locale";
import { workbenchModeLabel } from "../utils/workbenchModeLabel";

type Props = {
  readonly mode: RightPanelMode;
  readonly locale: Locale;
  readonly children: React.ReactNode;
  readonly open: boolean;
  readonly width: number;
  readonly onWidthChange: (width: number) => void;
  readonly onWidthCommit: (width: number) => void;
  readonly onClose: () => void;
};

export function WorkbenchPanel({
  mode,
  locale,
  children,
  open,
  width,
  onWidthChange,
  onWidthCommit,
  onClose,
}: Props) {
  const [isResizing, setIsResizing] = useState(false);
  const dragRef = useRef({ startX: 0, startWidth: WORKBENCH_PANEL_MIN_WIDTH });
  const style: CSSProperties &
    Record<"--inspector-pane-width" | "--context-sidebar-width", string> = {
    "--inspector-pane-width": `${width}px`,
    "--context-sidebar-width": `${width}px`,
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
      onWidthChange(
        clampWorkbenchPanelWidth(dragRef.current.startWidth + delta),
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
      onWidthCommit(clampWorkbenchPanelWidth(finalWidth));
    },
    [isResizing, onWidthCommit],
  );

  return (
    <aside
      className={[
        "context-sidebar",
        "workbench-panel",
        open ? "" : "context-sidebar--collapsed",
        isResizing ? "inspector-pane--resizing" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label={workbenchModeLabel(mode, locale)}
      aria-hidden={!open}
      style={style}
    >
      {open ? (
        <div
          className="context-sidebar__resize-handle"
          role="separator"
          aria-orientation="vertical"
          aria-label="Workbench panel width"
          onPointerDown={onResizePointerDown}
          onPointerMove={onResizePointerMove}
          onPointerUp={(event) => finishResize(event, width)}
          onPointerCancel={(event) => finishResize(event, width)}
        />
      ) : null}
      <div className="workbench-panel__card">
        <header className="workbench-panel__head">
          <h2 className="workbench-panel__title">
            {workbenchModeLabel(mode, locale)}
          </h2>
          <button
            type="button"
            className="workbench-panel__close"
            aria-label="Close panel"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="workbench-panel__body scroll-y" role="tabpanel">
          {children}
        </div>
      </div>
    </aside>
  );
}
