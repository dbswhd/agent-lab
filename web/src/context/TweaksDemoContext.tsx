import { useCallback, useMemo, useState, type ReactNode } from "react";
import {
  TweaksDemoContext,
  type ExecQueueDemoMode,
  type TweaksDemoContextValue,
} from "./tweaksDemoStore";

export type { ExecQueueDemoMode } from "./tweaksDemoStore";

const PANEL_KEY = "agent-lab-tweaks-open";

function readPanelOpen(): boolean {
  try {
    return localStorage.getItem(PANEL_KEY) === "1";
  } catch {
    return false;
  }
}

export function TweaksDemoProvider({ children }: { children: ReactNode }) {
  const [panelOpen, setPanelOpenState] = useState(readPanelOpen);
  const [showMacAlert, setShowMacAlert] = useState(false);
  const [showPermAlert, setShowPermAlert] = useState(false);
  const [execQueueDemo, setExecQueueDemo] = useState<ExecQueueDemoMode>(false);
  const [consensusGateDemo, setConsensusGateDemo] = useState(false);
  const [objectionDemo, setObjectionDemo] = useState(false);
  const [preflightDemo, setPreflightDemo] = useState(false);
  const [planStaleDemo, setPlanStaleDemo] = useState(false);
  const [forceScrollButton, setForceScrollButton] = useState(false);

  const setPanelOpen = useCallback((open: boolean) => {
    setPanelOpenState(open);
    try {
      localStorage.setItem(PANEL_KEY, open ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  const togglePanel = useCallback(() => {
    setPanelOpenState((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(PANEL_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const toggleExecQueueVisible = useCallback(() => {
    setExecQueueDemo((prev) => {
      if (prev === false || prev === "hidden") return "normal";
      return "hidden";
    });
  }, []);

  const toggleExecBlocked = useCallback(() => {
    setExecQueueDemo((prev) => {
      const nextBlocked = prev !== "blocked";
      return nextBlocked ? "blocked" : "normal";
    });
  }, []);

  const toggleConsensusGateDemo = useCallback(() => {
    setConsensusGateDemo((v) => !v);
  }, []);

  const toggleObjectionDemo = useCallback(() => {
    setObjectionDemo((v) => !v);
  }, []);

  const togglePreflightDemo = useCallback(() => {
    setPreflightDemo((v) => !v);
  }, []);

  const togglePlanStaleDemo = useCallback(() => {
    setPlanStaleDemo((v) => !v);
  }, []);

  const value = useMemo<TweaksDemoContextValue>(
    () => ({
      panelOpen,
      setPanelOpen,
      togglePanel,
      showMacAlert,
      setShowMacAlert,
      showPermAlert,
      setShowPermAlert,
      execQueueDemo,
      setExecQueueDemo,
      toggleExecQueueVisible,
      toggleExecBlocked,
      consensusGateDemo,
      setConsensusGateDemo,
      toggleConsensusGateDemo,
      objectionDemo,
      setObjectionDemo,
      toggleObjectionDemo,
      preflightDemo,
      setPreflightDemo,
      togglePreflightDemo,
      planStaleDemo,
      setPlanStaleDemo,
      togglePlanStaleDemo,
      forceScrollButton,
      setForceScrollButton,
    }),
    [
      panelOpen,
      setPanelOpen,
      togglePanel,
      showMacAlert,
      showPermAlert,
      execQueueDemo,
      toggleExecQueueVisible,
      toggleExecBlocked,
      consensusGateDemo,
      toggleConsensusGateDemo,
      objectionDemo,
      toggleObjectionDemo,
      preflightDemo,
      togglePreflightDemo,
      planStaleDemo,
      togglePlanStaleDemo,
      forceScrollButton,
    ],
  );

  return (
    <TweaksDemoContext.Provider value={value}>
      {children}
    </TweaksDemoContext.Provider>
  );
}
