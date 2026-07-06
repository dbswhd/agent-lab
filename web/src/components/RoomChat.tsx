import { type RoomChatProps, useRoomChat } from "../hooks/useRoomChat";
import { RoomChatView } from "./RoomChatView";

export type { RoomChatProps };

export function RoomChat(props: RoomChatProps) {
  const chat = useRoomChat(props);
  return <RoomChatView chat={chat} />;
}
