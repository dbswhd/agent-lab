import { describe, expect, it } from "vitest";
import type { RoomChatProps } from "./useRoomChat";

describe("useRoomChat", () => {
  it("exports RoomChatProps with session wiring fields", () => {
    const sample: RoomChatProps = {
      agents: [],
      sessionId: null,
      session: null,
      sidebarOpen: false,
      onToggleSidebar: () => {},
      onSessionChange: () => {},
    };
    expect(sample.sessionId).toBeNull();
  });
});
