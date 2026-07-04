import { useEffect, useMemo, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { fetchSessionAgentCapabilities } from "../api/client";
import {
  cloneCapabilities,
  DEFAULT_AGENT_CAPABILITIES,
  parseAgentCapabilities,
  type AgentCapabilitiesMap,
} from "../utils/agentCapabilities";
import { roomPermissions } from "../utils/agentPermissions";
import { readPendingRoomModels, readSessionRoomModels } from "../utils/modelSlash";
import { sortAgentIds } from "../utils/agentOrder";

export type RoomAgentCapabilitiesOptions = {
  sessionId: string | null;
  sessionRun: Record<string, unknown> | undefined;
  selected: string[];
  pendingSessionRoomModelsRef: MutableRefObject<string[] | null>;
  agentsPickerInitRef: MutableRefObject<boolean>;
  setSelected: Dispatch<SetStateAction<string[]>>;
};

/** Agent capability map + session model roster sync — extracted from RoomChat (F9). */
export function useRoomAgentCapabilities({
  sessionId,
  sessionRun,
  selected,
  pendingSessionRoomModelsRef,
  agentsPickerInitRef,
  setSelected,
}: RoomAgentCapabilitiesOptions) {
  const [agentCapabilities, setAgentCapabilities] =
    useState<AgentCapabilitiesMap>(() =>
      cloneCapabilities(DEFAULT_AGENT_CAPABILITIES),
    );
  const [, setResolvedAgentCwd] = useState<Record<string, string>>({});
  const agentCapsDirtyRef = useRef(false);
  const prevSessionIdRef = useRef<string | null>(sessionId);

  useEffect(() => {
    const prev = prevSessionIdRef.current;
    prevSessionIdRef.current = sessionId;
    if (prev !== null && prev !== sessionId) {
      agentCapsDirtyRef.current = false;
    }
  }, [sessionId]);

  useEffect(() => {
    if (sessionId !== null) return;
    setAgentCapabilities(cloneCapabilities(DEFAULT_AGENT_CAPABILITIES));
    setResolvedAgentCwd({});
    agentCapsDirtyRef.current = false;
    if (!agentsPickerInitRef.current) {
      const restored = readPendingRoomModels();
      if (restored?.length) {
        pendingSessionRoomModelsRef.current = restored;
        setSelected(restored);
        agentsPickerInitRef.current = true;
      }
    }
  }, [
    agentsPickerInitRef,
    pendingSessionRoomModelsRef,
    sessionId,
    setSelected,
  ]);

  const sessionRoomModelsKey = useMemo(() => {
    const models = readSessionRoomModels(sessionRun);
    return models ? models.join(",") : null;
  }, [sessionRun]);

  useEffect(() => {
    if (!sessionId || !sessionRoomModelsKey) return;
    const models = readSessionRoomModels(sessionRun);
    if (!models) return;
    setSelected((prev) => {
      const next = sortAgentIds(models);
      return prev.join(",") === next.join(",") ? prev : next;
    });
    agentsPickerInitRef.current = true;
  }, [agentsPickerInitRef, sessionId, sessionRoomModelsKey, sessionRun, setSelected]);

  useEffect(() => {
    if (!sessionId) {
      setResolvedAgentCwd({});
      return;
    }
    if (agentCapsDirtyRef.current) {
      const perms = roomPermissions(selected);
      void fetchSessionAgentCapabilities(
        sessionId,
        perms as Record<string, unknown>,
      )
        .then((r) => setResolvedAgentCwd(r.resolved_cwd ?? {}))
        .catch(() => {});
      return;
    }
    const raw = sessionRun?.agent_capabilities;
    if (raw && typeof raw === "object") {
      setAgentCapabilities(parseAgentCapabilities(raw));
    }
    const perms = roomPermissions(selected);
    void fetchSessionAgentCapabilities(
      sessionId,
      perms as Record<string, unknown>,
    )
      .then((r) => {
        if (!raw && r.agent_capabilities) {
          setAgentCapabilities(parseAgentCapabilities(r.agent_capabilities));
        }
        setResolvedAgentCwd(r.resolved_cwd ?? {});
      })
      .catch(() => {});
  }, [
    selected.join(","),
    sessionId,
    JSON.stringify(sessionRun?.agent_capabilities),
  ]);

  return { agentCapabilities };
}
