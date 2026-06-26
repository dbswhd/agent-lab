import { describe, expect, it } from "vitest";
import { formatAgentModelName, formatRoomModelLine } from "./roomModels";

describe("roomModels", () => {
  it("strips kimi-work prefix for display", () => {
    expect(formatAgentModelName("kimi-work:k2p6", "kimi_work")).toBe("k2p6");
  });

  it("formats kimi work status line without redundant prefix", () => {
    expect(
      formatRoomModelLine([
        {
          id: "kimi_work",
          label: "Kimi Work",
          ready: true,
          model: "kimi-work:k2p6",
        },
      ]),
    ).toBe("Kimi Work k2p6");
  });

  it("keeps other provider model strings intact", () => {
    expect(
      formatRoomModelLine([
        {
          id: "cursor",
          label: "Cursor",
          ready: true,
          model: "gpt-5",
        },
      ]),
    ).toBe("Cursor gpt-5");
  });
});
