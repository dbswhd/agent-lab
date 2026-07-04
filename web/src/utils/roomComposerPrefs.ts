import type { ComposerTurnProfile } from "./turnProfile";

/** Map room_preset id → default turn profile (fast/supervisor only). */
export function turnProfileForRoomPreset(
  presetId: string | null | undefined,
): ComposerTurnProfile | null {
  if (presetId === "fast") return "quick";
  if (presetId === "supervisor") return "loop";
  return null;
}
