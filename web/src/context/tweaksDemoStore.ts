import { createContext } from "react";

export type ExecQueueDemoMode = false | "normal" | "blocked" | "hidden";

export type TweaksDemoContextValue = {
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

export const TweaksDemoContext = createContext<TweaksDemoContextValue | null>(
  null,
);

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
