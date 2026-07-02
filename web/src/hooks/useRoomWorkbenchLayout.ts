import { useCallback, useEffect, useRef, useState } from "react";
import {
  clampWorkbenchPanelWidth,
  getInspectorOpen,
  getLastRightPanelMode,
  resolveDefaultWorkbenchWidth,
  setInspectorOpen,
  type StoredRightPanelMode,
} from "../utils/inspectorPanePrefs";

/** Phase 1c (F6): workbench / inspector layout state — extracted from RoomChat. */
export function useRoomWorkbenchLayout(rightPanelMode: StoredRightPanelMode) {
  const [inspectorOpen, setInspectorOpenState] = useState(getInspectorOpen);
  const [workbenchMenuOpen, setWorkbenchMenuOpen] = useState(false);
  const [filesFocusRevision, setFilesFocusRevision] = useState(0);
  const [filesFocusPath, setFilesFocusPath] = useState<string | null>(null);
  const [workbenchPanelWidth, setWorkbenchPanelWidthState] = useState(() =>
    resolveDefaultWorkbenchWidth(getLastRightPanelMode()),
  );
  const workbenchWidthUserAdjustedRef = useRef(false);

  const openInspectorPane = useCallback(() => {
    setInspectorOpenState(true);
    setInspectorOpen(true);
  }, []);

  const applyDefaultWorkbenchWidth = useCallback(
    (mode: StoredRightPanelMode = rightPanelMode) => {
      const apply = () => {
        setWorkbenchPanelWidthState(resolveDefaultWorkbenchWidth(mode));
      };
      if (typeof requestAnimationFrame === "function") {
        requestAnimationFrame(apply);
      } else {
        apply();
      }
    },
    [rightPanelMode],
  );

  const resetWorkbenchWidthForMode = useCallback(
    (mode: StoredRightPanelMode) => {
      workbenchWidthUserAdjustedRef.current = false;
      applyDefaultWorkbenchWidth(mode);
    },
    [applyDefaultWorkbenchWidth],
  );

  useEffect(() => {
    if (!inspectorOpen) {
      workbenchWidthUserAdjustedRef.current = false;
      return;
    }
    workbenchWidthUserAdjustedRef.current = false;
    applyDefaultWorkbenchWidth();
  }, [inspectorOpen, rightPanelMode, applyDefaultWorkbenchWidth]);

  useEffect(() => {
    if (!inspectorOpen || workbenchWidthUserAdjustedRef.current) return;
    const canvas = document.querySelector(".workspace-canvas");
    if (!canvas) return;

    const refit = () => applyDefaultWorkbenchWidth();
    const observer = new ResizeObserver(refit);
    observer.observe(canvas);
    window.addEventListener("resize", refit);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", refit);
    };
  }, [inspectorOpen, applyDefaultWorkbenchWidth]);

  const toggleInspector = useCallback(() => {
    setInspectorOpenState((current) => {
      const next = !current;
      setInspectorOpen(next);
      return next;
    });
  }, []);

  const setActiveWorkbenchWidth = useCallback((width: number) => {
    workbenchWidthUserAdjustedRef.current = true;
    setWorkbenchPanelWidthState(clampWorkbenchPanelWidth(width));
  }, []);

  const commitWorkbenchWidth = useCallback((width: number) => {
    workbenchWidthUserAdjustedRef.current = true;
    setWorkbenchPanelWidthState(clampWorkbenchPanelWidth(width));
  }, []);

  return {
    inspectorOpen,
    workbenchMenuOpen,
    setWorkbenchMenuOpen,
    filesFocusRevision,
    setFilesFocusRevision,
    filesFocusPath,
    setFilesFocusPath,
    workbenchPanelWidth,
    openInspectorPane,
    toggleInspector,
    setActiveWorkbenchWidth,
    commitWorkbenchWidth,
    resetWorkbenchWidthForMode,
  };
}
