import { describe, expect, it } from "vitest";
import type { AgentHealthRow } from "../api/client";
import { buildRecoveryItems, type RecoveryItemsInput } from "./recoveryItems";
import {
  createRecoveryAttempt,
  resolveRecoveryAttempt,
} from "./recoveryLifecycle";

function agent(overrides: Partial<AgentHealthRow>): AgentHealthRow {
  return {
    id: "codex",
    label: "Codex",
    ready: true,
    configured: true,
    bridge: "n/a",
    ...overrides,
  };
}

function input(overrides: Partial<RecoveryItemsInput>): RecoveryItemsInput {
  return {
    apiOk: true,
    agents: [agent({})],
    readiness: null,
    failure: null,
    selectedAgentIds: ["codex"],
    runLockStuck: false,
    discussRecovery: null,
    executions: [],
    ...overrides,
  };
}

describe("buildRecoveryItems", () => {
  it("does not describe a general API failure as an incomplete turn", () => {
    const items = buildRecoveryItems(
      input({ failure: { source: "transport", message: "HTTP 502" } }),
    );
    expect(items[0]?.kind).toBe("run_failed");
    expect(items[0]?.title).toBe("요청을 완료하지 못했습니다.");
    expect(items[0]?.title).not.toContain("턴");
  });

  it("uses partial turn copy only for an agent failure", () => {
    const items = buildRecoveryItems(
      input({
        failure: {
          source: "agent",
          kind: "partial_turn",
          message: "Claude timed out",
          affectedAgentIds: ["claude"],
        },
      }),
    );
    expect(items[0]?.title).toBe("최근 턴이 완전히 끝나지 않았습니다.");
    expect(items[0]?.affectedAgentIds).toEqual(["claude"]);
  });

  it("does not block send for an unselected agent", () => {
    const items = buildRecoveryItems(
      input({
        agents: [
          agent({}),
          agent({
            id: "claude",
            label: "Claude",
            ready: false,
            reason: "authentication required",
          }),
        ],
      }),
    );
    expect(items).toEqual([]);
  });

  it("uses direct readiness copy when send is blocked", () => {
    const items = buildRecoveryItems(
      input({
        readiness: {
          verdict: "blocked",
          session_id: "s1",
          agents: ["claude"],
          next_actions: [
            "터미널에서 `claude logout` 후 `claude login` (Claude Code OAuth — Room은 API 키 미사용)",
          ],
          checks: [
            {
              id: "claude_auth",
              agent: "claude",
              ok: false,
              detail: "auth expired",
              next: "터미널: claude login",
            },
          ],
        },
      }),
    );

    expect(items[0]?.severity).toBe("blocking_send");
    expect(items[0]?.title).toBe("전송 전에 연결 확인이 필요합니다.");
    expect(items[0]?.title).not.toContain("blocked");
    expect(items[0]?.primaryAction.label).toBe("Settings 열기");
    expect(items[0]?.secondaryAction?.label).toBe("상태 재확인");
  });

  it("resolves after health or retry removes the source state", () => {
    const [item] = buildRecoveryItems(
      input({
        failure: {
          source: "agent",
          kind: "partial_turn",
          message: "timeout",
        },
      }),
    );
    expect(item).toBeDefined();
    const attempt = createRecoveryAttempt({
      item: item!,
      actionId: "retry_failed_agents",
      canRestoreLastMessage: true,
    });
    expect(resolveRecoveryAttempt({ attempt, currentItems: [] }).status).toBe(
      "resolved",
    );
    expect(buildRecoveryItems(input({ failure: null }))).toEqual([]);
  });
});
