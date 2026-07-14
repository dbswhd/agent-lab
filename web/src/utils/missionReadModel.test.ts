import { afterEach, describe, expect, it, vi } from "vitest";
import type { MissionReadModelPayload } from "../api/client";
import {
  fetchMissionReadModelIfEnabled,
  missionUiReadModelEnabled,
  parseMissionReadModel,
  shouldApplyMissionReadModelEpoch,
} from "./missionReadModel";

const migratedPayload: MissionReadModelPayload = {
  session_id: "mission-1",
  migrated: true,
  source: "mission_journal",
  mission_id: "mission-1",
  goal: "ship",
  state: "EXECUTING",
  version: 4,
  plan_revision: 1,
  plan_hash: "plan-hash",
  approved_plan_hash: "plan-hash",
  repair_attempt: 0,
  max_repair_attempts: 2,
  oracle_verdict: null,
  next_action: "observe_execution",
  event_cursor: 4,
  operational_status: "RUNNING",
  open_execution_gates: [{ gate_id: "question-1", kind: "question" }],
  legacy_phase: "EXECUTE",
  plan: {
    phase: "APPROVED",
    hash: "plan-hash",
    approved_hash: "plan-hash",
    pending_approval: false,
  },
  work_phase: "execute_pending",
  mission_overview: {
    phase_label: "RUNNING",
    paused: false,
    circuit_breaker: false,
    pending_inbox_count: 1,
  },
  inbox_summary: {
    pending_count: 1,
    pending_questions: 1,
    pending_builds: 0,
  },
  inbox_items: [
    {
      id: "question-1",
      kind: "question",
      status: "pending",
      prompt: "Proceed?",
      options: [{ id: "yes", label: "Yes" }],
    },
  ],
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("mission read-model rollout boundary", () => {
  it("keeps the legacy path when the server flag is off", async () => {
    const fetchMock = vi.fn<typeof fetch>((input) => {
      expect(String(input)).toContain("/api/health/flags?category=feature");
      return Promise.resolve(jsonResponse({ flags: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(missionUiReadModelEnabled()).resolves.toBe(false);
    await expect(
      fetchMissionReadModelIfEnabled("legacy-1"),
    ).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("returns the journal composite only for a migrated session", async () => {
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url = String(input);
      if (url.includes("/api/health/flags")) {
        return Promise.resolve(
          jsonResponse({
            flags: [{ name: "AGENT_LAB_MISSION_UI_READ_MODEL", value: "1" }],
          }),
        );
      }
      expect(url).toContain("/api/sessions/mission-1/mission/read-model");
      return Promise.resolve(jsonResponse(migratedPayload));
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchMissionReadModelIfEnabled("mission-1")).resolves.toEqual(
      migratedPayload,
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("falls back when a flagged session is legacy or the read endpoint fails", async () => {
    const legacyPayload: MissionReadModelPayload = {
      ...migratedPayload,
      migrated: false,
      source: "legacy",
      mission_id: null,
      state: null,
      operational_status: null,
      next_action: "legacy_route",
      event_cursor: 0,
      open_execution_gates: [],
    };
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url = String(input);
      if (url.includes("/api/health/flags")) {
        return Promise.resolve(
          jsonResponse({
            flags: [{ name: "AGENT_LAB_MISSION_UI_READ_MODEL", value: "true" }],
          }),
        );
      }
      return Promise.resolve(jsonResponse(legacyPayload));
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      fetchMissionReadModelIfEnabled("legacy-1"),
    ).resolves.toBeNull();

    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/health/flags")) {
        return Promise.resolve(
          jsonResponse({
            flags: [{ name: "AGENT_LAB_MISSION_UI_READ_MODEL", value: "on" }],
          }),
        );
      }
      return Promise.resolve(
        jsonResponse({ error: "read model unavailable" }, 503),
      );
    });
    await expect(
      fetchMissionReadModelIfEnabled("mission-1"),
    ).resolves.toBeNull();
  });

  it("accepts an incomplete migrated inbox join so non-actionable rows stay hidden", () => {
    const incomplete = {
      ...migratedPayload,
      inbox_items: [],
      inbox_summary: {
        pending_count: 1,
        pending_questions: 1,
        pending_builds: 0,
      },
    };

    expect(parseMissionReadModel(incomplete)?.inbox_items).toEqual([]);
  });

  it("rejects migrated inbox rows that are not execution-gate joins", () => {
    expect(
      parseMissionReadModel({
        ...migratedPayload,
        inbox_items: [
          ...(migratedPayload.inbox_items ?? []),
          { id: "extra", kind: "question", status: "pending", prompt: "Extra" },
        ],
      }),
    ).toBeNull();
  });

  it("rejects duplicate migrated inbox IDs", () => {
    const item = migratedPayload.inbox_items?.[0];
    expect(item).toBeDefined();
    expect(
      parseMissionReadModel({
        ...migratedPayload,
        inbox_items: [item, item],
      }),
    ).toBeNull();
  });

  it("keeps stale gate rows visible for non-actionable review", () => {
    const stale = {
      ...(migratedPayload.inbox_items?.[0] ?? {}),
      status: "resolved",
      actionable: false,
      mission_gate_status: "stale",
    };
    expect(
      parseMissionReadModel({ ...migratedPayload, inbox_items: [stale] })
        ?.inbox_items,
    ).toEqual([stale]);
  });

  it("falls back when a migrated payload omits the inbox row projection", () => {
    expect(
      parseMissionReadModel({ ...migratedPayload, inbox_items: undefined }),
    ).toBeNull();
  });

  it("rejects malformed optional composites", () => {
    expect(
      parseMissionReadModel({
        ...migratedPayload,
        mission_overview: { phase_label: "RUNNING" },
      }),
    ).toBeNull();
    expect(
      parseMissionReadModel({
        ...migratedPayload,
        inbox_summary: { pending_count: "1" },
      }),
    ).toBeNull();
  });

  it("rejects malformed inbox options at the read-model boundary", () => {
    const malformed = {
      ...migratedPayload,
      inbox_items: [
        { ...migratedPayload.inbox_items?.[0], options: [{ label: 42 }] },
      ],
    };

    expect(parseMissionReadModel(malformed)).toBeNull();
  });

  it.each([
    { open_execution_gates: null },
    { open_execution_gates: [{ gate_id: "", kind: "question" }] },
    {
      open_execution_gates: [
        { gate_id: "g1", kind: "question" },
        { gate_id: "g1", kind: "question" },
      ],
    },
  ])("rejects malformed or duplicate execution gates", (patch) => {
    expect(parseMissionReadModel({ ...migratedPayload, ...patch })).toBeNull();
  });

  it("does not apply a response from an older request epoch", () => {
    expect(shouldApplyMissionReadModelEpoch(4, 3)).toBe(false);
    expect(shouldApplyMissionReadModelEpoch(4, 4)).toBe(true);
  });
});
