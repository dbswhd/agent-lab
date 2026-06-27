import { describe, expect, it } from "vitest";
import { parseModelSlashArgs, readSessionRoomModels } from "./modelSlash";

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
