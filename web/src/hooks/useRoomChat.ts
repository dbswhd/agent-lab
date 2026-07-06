/** Room workspace orchestrator facade (F9 P2). */
export type { RoomChatProps } from "./roomChatTypes";
import type { RoomChatProps } from "./roomChatTypes";
import { useRoomChatBootstrap } from "./useRoomChatBootstrap";
import { useRoomChatInteractions } from "./useRoomChatInteractions";
import { useRoomChatPresentation } from "./useRoomChatPresentation";

export function useRoomChat(props: RoomChatProps) {
  const bootstrap = useRoomChatBootstrap(props);
  const interactions = useRoomChatInteractions(bootstrap);
  return useRoomChatPresentation({ ...bootstrap, ...interactions });
}
