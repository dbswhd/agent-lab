import { describe, expect, it, vi } from "vitest";

vi.mock("../theme", () => ({ isTauri: () => false }));

describe("tauriApiShell", () => {
  it("returns null status outside Tauri", async () => {
    const { fetchApiShellStatus, restartTauriApi } =
      await import("./tauriApiShell");
    expect(await fetchApiShellStatus()).toBeNull();
    expect(await restartTauriApi()).toEqual({ ok: false, error: "not tauri" });
  });
});
