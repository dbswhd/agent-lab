import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ExecQueueDemoMode = false | "normal" | "blocked" | "hidden";

type TweaksDemoContextValue = {
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
  togglePanel: () => void;
  showMacAlert: boolean;
  setShowMacAlert: (open: boolean) => void;
  showPermAlert: boolean;
  setShowPermAlert: (open: boolean) => void;
  execQueueDemo: ExecQueueDemoMode;
  setExecQueueDemo: (mode: ExecQueueDemoMode) => void;
  toggleExecQueueVisible: () => void;
  toggleExecBlocked: () => void;
  consensusGateDemo: boolean;
  setConsensusGateDemo: (on: boolean) => void;
  toggleConsensusGateDemo: () => void;
  objectionDemo: boolean;
  setObjectionDemo: (on: boolean) => void;
  toggleObjectionDemo: () => void;
  preflightDemo: boolean;
  setPreflightDemo: (on: boolean) => void;
  togglePreflightDemo: () => void;
  planStaleDemo: boolean;
  setPlanStaleDemo: (on: boolean) => void;
  togglePlanStaleDemo: () => void;
  forceScrollButton: boolean;
  setForceScrollButton: (on: boolean) => void;
};

const TweaksDemoContext = createContext<TweaksDemoContextValue | null>(null);

const PANEL_KEY = "agent-lab-tweaks-open";

function readPanelOpen(): boolean {
  try {
    return localStorage.getItem(PANEL_KEY) === "1";
  } catch {
    return false;
  }
}

export const TWEAKS_DEMO_OFF: TweaksDemoContextValue = {
  panelOpen: false,
  setPanelOpen: () => {},
  togglePanel: () => {},
  showMacAlert: false,
  setShowMacAlert: () => {},
  showPermAlert: false,
  setShowPermAlert: () => {},
  execQueueDemo: false,
  setExecQueueDemo: () => {},
  toggleExecQueueVisible: () => {},
  toggleExecBlocked: () => {},
  consensusGateDemo: false,
  setConsensusGateDemo: () => {},
  toggleConsensusGateDemo: () => {},
  objectionDemo: false,
  setObjectionDemo: () => {},
  toggleObjectionDemo: () => {},
  preflightDemo: false,
  setPreflightDemo: () => {},
  togglePreflightDemo: () => {},
  planStaleDemo: false,
  setPlanStaleDemo: () => {},
  togglePlanStaleDemo: () => {},
  forceScrollButton: false,
  setForceScrollButton: () => {},
};

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

export function useTweaksDemo(): TweaksDemoContextValue {
  const ctx = useContext(TweaksDemoContext);
  if (!ctx) {
    throw new Error("useTweaksDemo must be used inside TweaksDemoProvider");
  }
  return ctx;
}

export function useTweaksDemoOptional(): TweaksDemoContextValue | null {
  return useContext(TweaksDemoContext);
}
