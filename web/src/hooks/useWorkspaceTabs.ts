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
import { focusComposerStack } from "../utils/composerStackFocus";
import type { WorkFocusTarget } from "../components/WorkToolPanel";

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
  return tab === "tools" ? "diff" : "overview";
}

export function useWorkspaceTabs({
  sessionKey,
  isNew,
  autoContext,
  initialRightPanelMode = "overview",
  onToolRequested,
}: Options) {
  const [workspaceTab, setWorkspaceTabState] =
    useState<WorkspaceTab>("transcript");
  const [inspectorTab, setInspectorTabState] =
    useState<InspectorTab>("overview");
  const [rightPanelMode, setRightPanelModeState] = useState<RightPanelMode>(
    initialRightPanelMode,
  );
  const [workspaceTabPinned, setWorkspaceTabPinned] = useState(false);
  const workspacePinnedRef = useRef(false);
  const inspectorPinnedRef = useRef(false);
  const prevBlockerRef = useRef(false);
  const prevSessionKeyRef = useRef(sessionKey);

  const setWorkspaceTab = useCallback(
    (tab: WorkspaceTab) => {
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
    },
    [onToolRequested],
  );

  const setInspectorTab = useCallback((tab: InspectorTab) => {
    inspectorPinnedRef.current = true;
    setInspectorTabState(tab);
    setRightPanelModeState(rightPanelModeFromInspectorTab(tab));
  }, []);

  const setRightPanelMode = useCallback(
    (mode: RightPanelMode) => {
      workspacePinnedRef.current = true;
      setWorkspaceTabPinned(true);
      setWorkspaceTabState("transcript");
      setRightPanelModeState(mode);
      if (mode === "overview") {
        setInspectorTabState("overview");
      } else {
        setInspectorTabState("tools");
      }
      onToolRequested?.();
    },
    [onToolRequested],
  );

  const setToolPanelTab = useCallback(
    (tab: ToolPanelTab) => {
      setRightPanelMode(tab);
    },
    [setRightPanelMode],
  );

  const openRightPanelMode = useCallback(
    (mode: RightPanelMode) => {
      setRightPanelMode(mode);
    },
    [setRightPanelMode],
  );

  const focusWorkStack = useCallback((focus?: WorkFocusTarget) => {
    setWorkspaceTabState("transcript");
    focusComposerStack(focus);
  }, []);

  useEffect(() => {
    const prevSessionKey = prevSessionKeyRef.current;
    prevSessionKeyRef.current = sessionKey;
    const boundFromComposer = prevSessionKey === "new" && sessionKey !== "new";

    if (boundFromComposer) {
      setWorkspaceTabState("transcript");
      setInspectorTabState("overview");
      setRightPanelModeState("overview");
      return;
    }

    workspacePinnedRef.current = false;
    inspectorPinnedRef.current = false;
    setWorkspaceTabPinned(false);
    prevBlockerRef.current = false;
    if (isNew) {
      setWorkspaceTabState("transcript");
      setInspectorTabState("overview");
      setRightPanelModeState("overview");
      return;
    }
    setWorkspaceTabState(resolveDefaultWorkspaceTab(autoContext));
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

    // Only a genuinely new blocker re-opens the (unpinned) inspector panel —
    // every ordinary round start/end used to do this too (resolveDefaultInspectorTab
    // ignores its context and always returns "overview"), which meant the
    // Overview panel silently popped open on every single turn for any
    // session where the user hadn't yet clicked a tab themselves.
    const blockerAppeared = autoContext.hasBlocker && !prevBlockerRef.current;
    prevBlockerRef.current = autoContext.hasBlocker;

    if (!inspectorPinnedRef.current && blockerAppeared) {
      const next = resolveDefaultInspectorTab(autoContext);
      setInspectorTabState(next);
      setRightPanelModeState(rightPanelModeFromInspectorTab(next));
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
      window.removeEventListener(
        WORKSPACE_TAB_SHORTCUT_EVENT,
        onWorkspaceShortcut,
      );
      window.removeEventListener(CONTENT_TAB_SHORTCUT_EVENT, onLegacyShortcut);
    };
  }, [isNew, setWorkspaceTab]);

  return {
    workspaceTab,
    inspectorTab,
    toolPanelTab: rightPanelMode === "overview" ? "diff" : rightPanelMode,
    rightPanelMode,
    suggestedWorkspaceTab,
    workspaceTabPinned,
    setWorkspaceTab,
    setInspectorTab,
    setToolPanelTab,
    setRightPanelMode,
    openRightPanelMode,
    openWorkTab: () => focusWorkStack("execute"),
    openPlanTab: () => focusWorkStack("plan"),
    openReviewTab: () => focusWorkStack("execute"),
    openTranscriptTab: () => setWorkspaceTab("transcript"),
    openDiffTab: () => setToolPanelTab("diff"),
    openFilesTab: () => setToolPanelTab("files"),
    focusWorkStack,
  };
}
