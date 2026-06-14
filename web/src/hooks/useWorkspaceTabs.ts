import { useCallback, useEffect, useRef, useState } from "react";
import {
  resolveDefaultInspectorTab,
  resolveDefaultWorkspaceTab,
  normalizeWorkspaceTab,
  type InspectorTab,
  type RightPanelMode,
  type TabAutoContext,
  type ToolPanelTab,
  type WorkspaceTab,
  workspaceTabFromLegacy,
} from "../utils/workspaceTabs";
import {
  CONTENT_TAB_SHORTCUT_EVENT,
  WORKSPACE_TAB_SHORTCUT_EVENT,
  type ContentTab,
} from "../utils/desktopShortcuts";

type Options = {
  sessionKey: string;
  isNew: boolean;
  autoContext: TabAutoContext;
  initialRightPanelMode?: RightPanelMode;
  onToolRequested?: () => void;
};

function isToolPanelTab(tab: WorkspaceTab): tab is ToolPanelTab {
  return tab !== "transcript";
}

function rightPanelModeFromInspectorTab(tab: InspectorTab): RightPanelMode {
  return tab === "tools" ? "plan" : tab;
}

export function useWorkspaceTabs({
  sessionKey,
  isNew,
  autoContext,
  initialRightPanelMode = "overview",
  onToolRequested,
}: Options) {
  const [workspaceTab, setWorkspaceTabState] = useState<WorkspaceTab>("transcript");
  const [inspectorTab, setInspectorTabState] = useState<InspectorTab>("overview");
  const [rightPanelMode, setRightPanelModeState] =
    useState<RightPanelMode>(initialRightPanelMode);
  const [workspaceTabPinned, setWorkspaceTabPinned] = useState(false);
  const workspacePinnedRef = useRef(false);
  const inspectorPinnedRef = useRef(false);
  const prevRunningRef = useRef(false);
  const prevPendingRef = useRef(false);
  const prevBlockerRef = useRef(false);
  const prevSessionKeyRef = useRef(sessionKey);

  const setWorkspaceTab = useCallback((tab: WorkspaceTab) => {
    workspacePinnedRef.current = true;
    setWorkspaceTabPinned(true);
    if (!isToolPanelTab(tab)) {
      setWorkspaceTabState("transcript");
      return;
    }
    setWorkspaceTabState("transcript");
    setRightPanelModeState(tab);
    inspectorPinnedRef.current = true;
    setInspectorTabState("tools");
    onToolRequested?.();
  }, [onToolRequested]);

  const setInspectorTab = useCallback((tab: InspectorTab) => {
    inspectorPinnedRef.current = true;
    setInspectorTabState(tab);
    setRightPanelModeState(rightPanelModeFromInspectorTab(tab));
  }, []);

  const setRightPanelMode = useCallback((mode: RightPanelMode) => {
    workspacePinnedRef.current = true;
    setWorkspaceTabPinned(true);
    setWorkspaceTabState("transcript");
    setRightPanelModeState(mode);
    if (mode === "overview" || mode === "tasks" || mode === "inbox") {
      setInspectorTabState(mode);
    } else {
      setInspectorTabState("tools");
    }
    onToolRequested?.();
  }, [onToolRequested]);

  const setToolPanelTab = useCallback((tab: ToolPanelTab) => {
    setRightPanelMode(tab);
  }, [setRightPanelMode]);

  const openRightPanelMode = useCallback((mode: RightPanelMode) => {
    setRightPanelMode(mode);
  }, [setRightPanelMode]);

  useEffect(() => {
    const prevSessionKey = prevSessionKeyRef.current;
    prevSessionKeyRef.current = sessionKey;
    const boundFromComposer =
      prevSessionKey === "new" && sessionKey !== "new";

    if (boundFromComposer) {
      // First message bound a session id — keep Transcript visible while SSE streams.
      setWorkspaceTabState("transcript");
      setInspectorTabState("overview");
      setRightPanelModeState("overview");
      return;
    }

    workspacePinnedRef.current = false;
    inspectorPinnedRef.current = false;
    setWorkspaceTabPinned(false);
    prevRunningRef.current = false;
    prevPendingRef.current = false;
    prevBlockerRef.current = false;
    if (isNew) {
      setWorkspaceTabState("transcript");
      setInspectorTabState("overview");
      setRightPanelModeState("overview");
      return;
    }
    setWorkspaceTabState("transcript");
    const defaultInspector = resolveDefaultInspectorTab(autoContext);
    setInspectorTabState(defaultInspector);
    setRightPanelModeState(rightPanelModeFromInspectorTab(defaultInspector));
  }, [
    sessionKey,
    isNew,
    autoContext.hasPendingExecution,
    autoContext.hasDryRunDiff,
    autoContext.planMd,
    autoContext.hasBlocker,
  ]);

  useEffect(() => {
    if (isNew) return;

    const runStarted = autoContext.running && !prevRunningRef.current;
    const runEnded = !autoContext.running && prevRunningRef.current;
    const blockerAppeared = autoContext.hasBlocker && !prevBlockerRef.current;

    prevRunningRef.current = autoContext.running;
    prevPendingRef.current =
      autoContext.hasPendingExecution || autoContext.hasDryRunDiff;
    prevBlockerRef.current = autoContext.hasBlocker;

    if (!inspectorPinnedRef.current) {
      if (runStarted || runEnded || blockerAppeared) {
        const next = resolveDefaultInspectorTab(autoContext);
        setInspectorTabState(next);
        setRightPanelModeState(rightPanelModeFromInspectorTab(next));
      }
    }
  }, [autoContext, isNew]);

  const suggestedWorkspaceTab = isNew
    ? null
    : resolveDefaultWorkspaceTab(autoContext);

  useEffect(() => {
    function onWorkspaceShortcut(event: Event) {
      if (isNew) return;
      const tab = normalizeWorkspaceTab(
        (event as CustomEvent<WorkspaceTab>).detail,
      );
      setWorkspaceTab(tab);
    }
    function onLegacyShortcut(event: Event) {
      if (isNew) return;
      const legacy = (event as CustomEvent<ContentTab>).detail;
      setWorkspaceTab(workspaceTabFromLegacy(legacy));
    }

    window.addEventListener(WORKSPACE_TAB_SHORTCUT_EVENT, onWorkspaceShortcut);
    window.addEventListener(CONTENT_TAB_SHORTCUT_EVENT, onLegacyShortcut);
    return () => {
      window.removeEventListener(WORKSPACE_TAB_SHORTCUT_EVENT, onWorkspaceShortcut);
      window.removeEventListener(CONTENT_TAB_SHORTCUT_EVENT, onLegacyShortcut);
    };
  }, [isNew, setWorkspaceTab]);

  return {
    workspaceTab,
    inspectorTab,
    toolPanelTab:
      rightPanelMode === "overview" ||
      rightPanelMode === "tasks" ||
      rightPanelMode === "inbox"
        ? "plan"
        : rightPanelMode,
    rightPanelMode,
    suggestedWorkspaceTab,
    workspaceTabPinned,
    setWorkspaceTab,
    setInspectorTab,
    setToolPanelTab,
    setRightPanelMode,
    openRightPanelMode,
    openWorkTab: () => setWorkspaceTab("plan"),
    openPlanTab: () => setWorkspaceTab("plan"),
    openReviewTab: () => setWorkspaceTab("plan"),
    openTranscriptTab: () => setWorkspaceTab("transcript"),
  };
}
