import { describe, expect, it } from "vitest";
import { bindRoomSessionRefreshCommands } from "./useRoomSessionSync";

describe("bindRoomSessionRefreshCommands", () => {
  it("wires refreshCommands into the session sync ref", () => {
    const ref: { current: (sid?: string | null) => void } = { current: () => {} };
    const calls: string[] = [];
    bindRoomSessionRefreshCommands(ref, (sid?: string | null) => {
      calls.push(String(sid ?? ""));
    });
    ref.current?.("sess-1");
    expect(calls).toEqual(["sess-1"]);
  });
});
