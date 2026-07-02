import { describe, expect, it } from "vitest";
import {
  formatRoomRunErrorDetail,
  isLoopReadinessDetail,
  messageLooksLikeLoopReadinessFailure,
} from "./roomRunErrors";

describe("roomRunErrors", () => {
  it("formats loop readiness detail with blockers and hint", () => {
    const text = formatRoomRunErrorDetail({
      code: "loop_readiness_failed",
      message: "loop model readiness failed",
      reason: "selected agent model lacks question/tool capability for Loop",
      topology: "route_auto",
      requested_agents: ["claude", "kimi_work"],
      agents: ["kimi_work"],
      agent_details: [
        {
          id: "kimi_work",
          model_id: "kimi-work-default",
          loop_ready: false,
          loop_blockers: ["supports_tools", "supports_json_envelope"],
          blocker_labels: [
            "tools/MCP (daimon·CLI capability probe)",
            "structured JSON envelope (Loop consensus act)",
          ],
          summary:
            "missing: tools/MCP (daimon·CLI capability probe), structured JSON envelope (Loop consensus act)",
        },
      ],
      hint: "Kimi Work: 왼쪽 rail 「연결」 또는 설정 → 연결에서 Bridge 재연결",
    });

    expect(text).toContain("Loop 모드 전송 차단");
    expect(text).toContain("kimi_work (kimi-work-default)");
    expect(text).toContain("tools/MCP");
    expect(text).toContain("structured JSON envelope");
    expect(text).toContain("요청 roster: claude, kimi_work");
    expect(text).toContain("조치:");
  });

  it("detects loop readiness payloads and messages", () => {
    expect(
      isLoopReadinessDetail({
        code: "loop_readiness_failed",
        agents: ["kimi_work"],
      }),
    ).toBe(true);
    expect(
      messageLooksLikeLoopReadinessFailure(
        "kimi_work: selected agent model lacks question/tool capability for Loop",
      ),
    ).toBe(true);
    expect(
      messageLooksLikeLoopReadinessFailure("Loop 모드 전송 차단 — 선택 agent"),
    ).toBe(true);
  });
});
