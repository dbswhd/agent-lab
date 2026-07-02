// Session-keyed registry of the live `onRoomEvent` handler, so a manual
// "다시 시도" click from a ReconnectStatusCard deep in the transcript (which
// has no prop path back to RoomChat's send handler) can feed replayed/live
// events into the same transcript-patching pipeline the original turn used.
type RoomEventHandler = (data: Record<string, unknown>) => void;

const handlers = new Map<string, RoomEventHandler>();

export function registerRoomEventHandler(
  sessionId: string,
  handler: RoomEventHandler,
): void {
  handlers.set(sessionId, handler);
}

export function getRoomEventHandler(
  sessionId: string,
): RoomEventHandler | undefined {
  return handlers.get(sessionId);
}

export function clearRoomEventHandler(sessionId: string): void {
  handlers.delete(sessionId);
}
