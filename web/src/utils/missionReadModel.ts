/**
 * Wave A stub — prefer GET /mission/read-model when the server flag is on.
 * Must not replace Composer / HumanInboxPanel until Wave B cutover.
 *
 * @see docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md
 */

import { fetchHealthFlags, fetchMissionReadModel } from "../api/client";
import type { MissionReadModelPayload } from "../api/client";

const FLAG = "AGENT_LAB_MISSION_UI_READ_MODEL";

function flagEnabled(raw: unknown): boolean {
  if (raw === true || raw === 1) return true;
  if (typeof raw === "string") {
    const v = raw.trim().toLowerCase();
    return v === "1" || v === "true" || v === "on" || v === "yes";
  }
  return false;
}

/** True when server exposes AGENT_LAB_MISSION_UI_READ_MODEL as enabled (default off). */
export async function missionUiReadModelEnabled(): Promise<boolean> {
  try {
    const payload = await fetchHealthFlags("feature");
    const row = payload.flags?.find((f) => f.name === FLAG);
    return flagEnabled(row?.value);
  } catch {
    return false;
  }
}

/**
 * Fetch journal-first read-model only when the UI flag is on; otherwise null.
 * Callers must keep using run.json Inbox/overview until Wave B.
 */
export async function fetchMissionReadModelIfEnabled(
  sessionId: string,
): Promise<MissionReadModelPayload | null> {
  if (!(await missionUiReadModelEnabled())) return null;
  return fetchMissionReadModel(sessionId);
}
