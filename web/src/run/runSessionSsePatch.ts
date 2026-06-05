import type { LiveMsg } from "../run/runSessionRegistry";
import { patchSessionMessages } from "../run/runSessionRegistry";

/** Append/update messages for an in-flight turn (full transcript + turn buffer). */
export function patchTurnMessages(
  runKey: string,
  updater: (messages: LiveMsg[]) => LiveMsg[],
): void {
  patchSessionMessages(runKey, updater, { alsoTurn: true });
}
