import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  parseModelSlashArgs,
  readPendingRoomModels,
  readSessionRoomModels,
  writePendingRoomModels,
} from "./modelSlash";

describe("parseModelSlashArgs", () => {
  it("splits composition and session scope", () => {
    expect(parseModelSlashArgs("cursor,claude session")).toEqual({
      composition: ["cursor", "claude"],
      scope: "session",
    });
  });

  it("splits composition and default scope", () => {
    expect(parseModelSlashArgs("cursor default")).toEqual({
      composition: ["cursor"],
      scope: "default",
    });
  });

  it("returns null scope when omitted", () => {
    expect(parseModelSlashArgs("cursor,codex")).toEqual({
      composition: ["cursor", "codex"],
      scope: null,
    });
  });
});

describe("readSessionRoomModels", () => {
  it("reads room_models from run.json payload", () => {
    expect(
      readSessionRoomModels({ room_models: ["claude", "cursor"] }),
    ).toEqual(["cursor", "claude"]);
  });

  it("returns null when missing", () => {
    expect(readSessionRoomModels({})).toBeNull();
  });
});

describe("pending room models storage", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("sessionStorage", {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
      clear: () => {
        store.clear();
      },
    });
  });

  it("round-trips session-scoped picks before bind", () => {
    writePendingRoomModels(["kimi_work", "claude"]);
    expect(readPendingRoomModels()).toEqual(["claude", "kimi_work"]);
    writePendingRoomModels(null);
    expect(readPendingRoomModels()).toBeNull();
  });
});
