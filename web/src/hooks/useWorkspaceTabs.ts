import { useCallback, useEffect, useRef, useState } from "react";
import {
  resolveDefaultInspectorTab,
  resolveDefaultWorkspaceTab,
  type InspectorTab,
  type TabAutoContext,
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
};

export function useWorkspaceTabs({ sessionKey, isNew, autoContext }: Options) {
  const [workspaceTab, setWorkspaceTabState] = useState<WorkspaceTab>("transcript");
  const [inspectorTab, setInspectorTabState] = useState<InspectorTab>("context");
  const workspacePinnedRef = useRef(false);
  const inspectorPinnedRef = useRef(false);
  const prevRunningRef = useRef(false);
  const prevPendingRef = useRef(false);
  const prevBlockerRef = useRef(false);

  const setWorkspaceTab = useCallback((tab: WorkspaceTab) => {
    workspacePinnedRef.current = true;
    setWorkspaceTabState(tab);
  }, []);

  const setInspectorTab = useCallback((tab: InspectorTab) => {
    inspectorPinnedRef.current = true;
    setInspectorTabState(tab);
  }, []);

  useEffect(() => {
    workspacePinnedRef.current = false;
    inspectorPinnedRef.current = false;
    prevRunningRef.current = false;
    prevPendingRef.current = false;
    prevBlockerRef.current = false;
    if (isNew) {
      setWorkspaceTabState("transcript");
      setInspectorTabState("context");
      return;
    }
    setWorkspaceTabState(resolveDefaultWorkspaceTab(autoContext));
    setInspectorTabState(resolveDefaultInspectorTab(autoContext));
  }, [sessionKey, isNew]);

  useEffect(() => {
    if (isNew) return;

    const runStarted = autoContext.running && !prevRunningRef.current;
    const runEnded = !autoContext.running && prevRunningRef.current;
    const pendingAppeared =
      (autoContext.hasPendingExecution || autoContext.hasDryRunDiff) &&
      !prevPendingRef.current;
    const blockerAppeared = autoContext.hasBlocker && !prevBlockerRef.current;

    prevRunningRef.current = autoContext.running;
    prevPendingRef.current =
      autoContext.hasPendingExecution || autoContext.hasDryRunDiff;
    prevBlockerRef.current = autoContext.hasBlocker;

    if (!workspacePinnedRef.current) {
      if (runStarted || runEnded || pendingAppeared) {
        setWorkspaceTabState(resolveDefaultWorkspaceTab(autoContext));
      }
    }
    if (!inspectorPinnedRef.current) {
      if (runStarted || runEnded || blockerAppeared) {
        setInspectorTabState(resolveDefaultInspectorTab(autoContext));
      }
    }
  }, [autoContext, isNew]);

  useEffect(() => {
    function onWorkspaceShortcut(event: Event) {
      if (isNew) return;
      const tab = (event as CustomEvent<WorkspaceTab>).detail;
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
    setWorkspaceTab,
    setInspectorTab,
    openReviewTab: () => setWorkspaceTab("review"),
    openPlanTab: () => setWorkspaceTab("plan"),
    openTranscriptTab: () => setWorkspaceTab("transcript"),
  };
}
