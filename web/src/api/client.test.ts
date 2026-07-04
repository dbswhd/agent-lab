import { describe, expect, it } from "vitest";
import {
  apiBase,
  fetchGatewaySettings,
  listWorkspaceFileRoots,
  terminalWsUrl,
} from "./client";

describe("api client barrel", () => {
  it("re-exports core transport and domain modules", () => {
    expect(typeof apiBase).toBe("function");
    expect(typeof listWorkspaceFileRoots).toBe("function");
    expect(typeof fetchGatewaySettings).toBe("function");
    expect(typeof terminalWsUrl).toBe("function");
  });
});
