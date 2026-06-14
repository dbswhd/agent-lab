const HUMAN_SYNTHESIS_KEY = "agent-lab-transcript-human-synthesis";
const PEER_CHANNEL_KEY = "agent-lab-transcript-peer-channel";

export const TRANSCRIPT_VIEW_PREFS_EVENT = "agent-lab:transcript-view-prefs";

function notifyPrefsChanged(): void {
  window.dispatchEvent(new CustomEvent(TRANSCRIPT_VIEW_PREFS_EVENT));
}

export function getShowHumanSynthesis(): boolean {
  const stored = localStorage.getItem(HUMAN_SYNTHESIS_KEY);
  if (stored === "1" || stored === "true") return true;
  return false;
}

export function setShowHumanSynthesis(on: boolean): void {
  localStorage.setItem(HUMAN_SYNTHESIS_KEY, on ? "1" : "0");
  notifyPrefsChanged();
}

export function getShowPeerChannel(): boolean {
  const stored = localStorage.getItem(PEER_CHANNEL_KEY);
  return stored === "1" || stored === "true";
}

export function setShowPeerChannel(on: boolean): void {
  localStorage.setItem(PEER_CHANNEL_KEY, on ? "1" : "0");
  notifyPrefsChanged();
}
