const HUMAN_SYNTHESIS_KEY = "agent-lab-transcript-human-synthesis";

export function getShowHumanSynthesis(): boolean {
  const stored = localStorage.getItem(HUMAN_SYNTHESIS_KEY);
  if (stored === "1" || stored === "true") return true;
  return false;
}

export function setShowHumanSynthesis(on: boolean): void {
  localStorage.setItem(HUMAN_SYNTHESIS_KEY, on ? "1" : "0");
}
