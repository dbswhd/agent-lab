import { useEffect, useRef, useState } from "react";
import { fetchHealthFlags, fetchMissionReadModel } from "../api/client";
import type { MissionReadModelPayload } from "../api/client";

const FLAG = "AGENT_LAB_MISSION_UI_READ_MODEL";

function flagEnabled(raw: unknown): boolean {
  if (raw === true || raw === 1) return true;
  if (typeof raw === "string") {
    const v = raw.trim().toLowerCase();
    return v === "1" || v === "true" || v === "on" || v === "yes";
  }
  return false;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isInboxItem(value: unknown): value is Record<string, unknown> & {
  readonly id: string;
  readonly status: string;
} {
  if (!isRecord(value)) return false;
  const options = value.options;
  const validOptions =
    options === undefined ||
    (Array.isArray(options) &&
      options.every(
        (option) =>
          isRecord(option) &&
          [option.id, option.value, option.label].some(
            (field) => typeof field === "string" && field.length > 0,
          ),
      ));
  return (
    typeof value.id === "string" &&
    typeof value.kind === "string" &&
    typeof value.status === "string" &&
    typeof value.prompt === "string" &&
    validOptions
  );
}

function hasValidGates(value: Record<string, unknown>): boolean {
  if (!Array.isArray(value.open_execution_gates)) return false;
  const ids = new Set<string>();
  for (const gate of value.open_execution_gates) {
    if (!isRecord(gate)) return false;
    if (typeof gate.gate_id !== "string" || !gate.gate_id.trim()) return false;
    if (typeof gate.kind !== "string" || !gate.kind.trim()) return false;
    if (ids.has(gate.gate_id)) return false;
    ids.add(gate.gate_id);
  }
  return true;
}

function isGateExemptItem(item: Record<string, unknown>): boolean {
  return (
    item.actionable === false ||
    item.mission_gate_status === "stale" ||
    item.mission_gate_status === "unrelated"
  );
}

function hasValidInboxJoin(value: Record<string, unknown>): boolean {
  if (!Array.isArray(value.inbox_items)) return true;
  const gates = Array.isArray(value.open_execution_gates)
    ? value.open_execution_gates
    : [];
  const gateIds = new Set(
    gates
      .filter(isRecord)
      .map((gate) => gate.gate_id)
      .filter((id): id is string => typeof id === "string"),
  );
  const seen = new Set<string>();
  for (const item of value.inbox_items) {
    if (!isRecord(item) || typeof item.id !== "string") return false;
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    if (!gateIds.has(item.id) && !isGateExemptItem(item)) return false;
  }
  return true;
}

function hasValidComposites(value: Record<string, unknown>): boolean {
  const summary = value.inbox_summary;
  if (summary !== undefined) {
    if (!isRecord(summary)) return false;
    if (
      typeof summary.pending_count !== "number" ||
      typeof summary.pending_questions !== "number" ||
      typeof summary.pending_builds !== "number"
    ) {
      return false;
    }
  }
  const overview = value.mission_overview;
  if (overview !== undefined) {
    if (!isRecord(overview)) return false;
    if (
      typeof overview.phase_label !== "string" ||
      typeof overview.paused !== "boolean" ||
      typeof overview.circuit_breaker !== "boolean" ||
      typeof overview.pending_inbox_count !== "number"
    ) {
      return false;
    }
  }
  const plan = value.plan;
  if (plan !== undefined && plan !== null) {
    if (!isRecord(plan) || typeof plan.pending_approval !== "boolean") {
      return false;
    }
  }
  return true;
}

export function parseMissionReadModel(
  value: unknown,
): MissionReadModelPayload | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.session_id !== "string" ||
    typeof value.migrated !== "boolean" ||
    (value.source !== "mission_journal" && value.source !== "legacy") ||
    typeof value.next_action !== "string" ||
    typeof value.event_cursor !== "number" ||
    !Number.isFinite(value.event_cursor)
  ) {
    return null;
  }
  if (value.migrated && !Array.isArray(value.inbox_items)) return null;
  if (
    value.inbox_items !== undefined &&
    (!Array.isArray(value.inbox_items) || !value.inbox_items.every(isInboxItem))
  ) {
    return null;
  }
  if (!hasValidGates(value)) return null;
  if (!hasValidInboxJoin(value)) return null;
  if (!hasValidComposites(value)) return null;
  return value as MissionReadModelPayload;
}

export function isUsableMissionReadModel(
  payload: MissionReadModelPayload | null,
): payload is MissionReadModelPayload {
  return payload?.migrated === true && payload.source === "mission_journal";
}

/** True when server exposes AGENT_LAB_MISSION_UI_READ_MODEL as enabled (default off). */
export async function missionUiReadModelEnabled(): Promise<boolean> {
  return fetchHealthFlags("feature")
    .then((payload) => {
      const row = payload.flags?.find((f) => f.name === FLAG);
      return flagEnabled(row?.effective ?? row?.value);
    })
    .catch(() => false);
}

/**
 * Fetch journal-first read-model only when the UI flag is on; otherwise null.
 * Callers must keep using run.json Inbox/overview until Wave B.
 */
export async function fetchMissionReadModelIfEnabled(
  sessionId: string,
): Promise<MissionReadModelPayload | null> {
  if (!(await missionUiReadModelEnabled())) return null;
  try {
    const payload = await fetchMissionReadModel(sessionId);
    const parsed = parseMissionReadModel(payload);
    return isUsableMissionReadModel(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export type MissionReadModelState = {
  readonly model: MissionReadModelPayload | null;
  readonly loading: boolean;
};

export function shouldApplyMissionReadModelEpoch(
  currentEpoch: number,
  responseEpoch: number,
): boolean {
  return responseEpoch >= currentEpoch;
}

export function useMissionReadModel(
  sessionId: string | null,
  reloadKey = 0,
): MissionReadModelState {
  const [model, setModel] = useState<MissionReadModelPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const requestEpoch = useRef(0);

  useEffect(() => {
    if (!sessionId) {
      requestEpoch.current += 1;
      setModel(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setModel(null);
    setLoading(true);
    const apply = (next: MissionReadModelPayload | null, epoch: number) => {
      if (
        !cancelled &&
        shouldApplyMissionReadModelEpoch(requestEpoch.current, epoch)
      ) {
        setModel(next);
      }
    };
    const request = () => {
      const epoch = ++requestEpoch.current;
      void fetchMissionReadModelIfEnabled(sessionId)
        .then((next) => apply(next, epoch))
        .finally(() => {
          if (!cancelled && epoch === requestEpoch.current) setLoading(false);
        });
    };
    request();
    const timer = window.setInterval(request, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [reloadKey, sessionId]);

  return { model, loading };
}
