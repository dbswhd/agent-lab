import type { ComposerTurnProfile } from "./turnProfile";

export type TurnProfileBanditStats = {
  up: number;
  down: number;
  total: number;
};

export type TurnProfileRecommendation = {
  recommended: ComposerTurnProfile;
  default: ComposerTurnProfile;
  scores: Record<string, number>;
  stats: Record<string, TurnProfileBanditStats>;
  total_feedback: number;
};

export type PendingTurnFeedback = {
  sessionId: string;
  turnIndex: number;
  profile: ComposerTurnProfile;
  partial?: boolean;
};

export function profileLabel(id: ComposerTurnProfile): string {
  const labels: Record<ComposerTurnProfile, string> = {
    quick: "빠른",
    discuss: "회의",
    review: "논쟁",
    free: "♾️",
  };
  return labels[id] ?? id;
}
