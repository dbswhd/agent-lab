import { useEffect, useRef, useState } from "react";
import {
  fetchHealthFlags,
  fetchMissionEventsSSE,
  fetchMissionReadModel,
} from "../api/client";
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

const SSE_RECONNECT_BACKOFF_MS = [1000, 2000, 4000, 8000, 15000, 15000];

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}

export function useMissionReadModel(
  sessionId: string | null,
  reloadKey = 0,
): MissionReadModelState {
  const [model, setModel] = useState<MissionReadModelPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const requestEpoch = useRef(0);
  const modelRef = useRef(model);

  // Keep a mutable ref in sync with the latest model so reconnects can use
  // the current cursor without capturing stale React state in the async loop.
  useEffect(() => {
    modelRef.current = model;
  }, [model]);

  useEffect(() => {
    if (!sessionId) {
      requestEpoch.current += 1;
      setModel(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setModel(null);
    setLoading(true);
    const epoch = ++requestEpoch.current;

    const apply = (next: MissionReadModelPayload | null) => {
      if (
        !cancelled &&
        shouldApplyMissionReadModelEpoch(requestEpoch.current, epoch)
      ) {
        setModel(next);
      }
    };

    const startStream = async () => {
      if (!(await missionUiReadModelEnabled())) {
        setLoading(false);
        return;
      }
      // Initial snapshot so UI can render immediately before events arrive.
      try {
        const payload = await fetchMissionReadModel(sessionId);
        const parsed = parseMissionReadModel(payload);
        if (!cancelled && epoch === requestEpoch.current) {
          apply(isUsableMissionReadModel(parsed) ? parsed : null);
        }
      } catch {
        // ignore; SSE will catch up if it can
      }
      setLoading(false);

      let reconnectAttempt = 0;
      while (!cancelled && !controller.signal.aborted) {
        const since =
          modelRef.current?.event_cursor !== undefined
            ? String(modelRef.current.event_cursor)
            : undefined;
        let hadError = false;
        try {
          // eslint-disable-next-line no-await-in-loop
          await fetchMissionEventsSSE(
            sessionId,
            since,
            () => {
              // Notification event received; refetch the canonical snapshot.
              void fetchMissionReadModel(sessionId)
                .then((payload) => parseMissionReadModel(payload))
                .then((parsed) => {
                  if (isUsableMissionReadModel(parsed)) {
                    apply(parsed);
                  }
                })
                .catch(() => {
                  /* ignore parse/fetch errors; reconnect will retry */
                });
            },
            () => {
              // Stream ended cleanly (mission caught up or reached a
              // terminal state) — not a failure, so don't escalate backoff.
            },
            () => {
              // Stream disconnected/failed; escalate backoff before retrying.
              hadError = true;
            },
          );
        } catch {
          hadError = true;
        }
        if (cancelled || controller.signal.aborted) break;
        const backoff = hadError
          ? SSE_RECONNECT_BACKOFF_MS[
              Math.min(reconnectAttempt, SSE_RECONNECT_BACKOFF_MS.length - 1)
            ]
          : SSE_RECONNECT_BACKOFF_MS[0];
        reconnectAttempt = hadError ? reconnectAttempt + 1 : 0;
        // eslint-disable-next-line no-await-in-loop
        await sleep(backoff, controller.signal);
      }
    };

    void startStream();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [reloadKey, sessionId]);

  return { model, loading };
}
