import { afterEach, describe, expect, it, vi } from "vitest";
import {
  apiBase,
  fetchGatewaySettings,
  listWorkspaceFileRoots,
  runRoom,
  terminalWsUrl,
} from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("api client barrel", () => {
  it("re-exports core transport and domain modules", () => {
    expect(typeof apiBase).toBe("function");
    expect(typeof listWorkspaceFileRoots).toBe("function");
    expect(typeof fetchGatewaySettings).toBe("function");
    expect(typeof terminalWsUrl).toBe("function");
  });

  it("sends an explicit idea-lane opt-in only for a new room run", async () => {
    const fetchMock = vi.fn().mockImplementation(() => new Response(
      'data: {"type":"complete","session_id":"idea-1"}\n\n', {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("document", {
      visibilityState: "visible",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });

    await runRoom("강의자료 학습 도구", ["cursor"], () => undefined, { ideation: true });
    const body = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(body.get("ideation")).toBe("true");

    fetchMock.mockClear();
    await runRoom("이어가기", ["cursor"], () => undefined, { sessionId: "legacy" });
    const resumed = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(resumed.get("ideation")).toBeNull();
  });
});
