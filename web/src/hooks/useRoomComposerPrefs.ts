import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentHealthRow, RoomPreset } from "../api/client";
import { fetchRoomPresets } from "../api/client";
import {
  getTurnStrategy,
  setTurnStrategy,
  type ComposeMode,
} from "../utils/composeMode";
import { fetchRoomModes, loopCostHintLine } from "../utils/roomModes";
import {
  emergenceHintLine,
  presetHintLine,
  resolveRoomPresets,
} from "../utils/roomPresets";
import {
  turnProfileForRoomPreset,
} from "../utils/roomComposerPrefs";
import {
  resolveTurnSend,
  setTurnProfile,
  type ComposerTurnProfile,
} from "../utils/turnProfile";

export type UseRoomComposerPrefsArgs = {
  sessionRoomPreset?: string | null;
  locale: "en" | "ko";
  healthAgents: AgentHealthRow[];
  selectedAgents: string[];
  sessionRun?: Record<string, unknown>;
};

/** Phase 1c (F6): room preset + turn profile + composer hints — extracted from RoomChat. */
export function useRoomComposerPrefs({
  sessionRoomPreset,
  locale,
  healthAgents,
  selectedAgents,
  sessionRun,
}: UseRoomComposerPrefsArgs) {
  const [turnProfile, setTurnProfileState] =
    useState<ComposerTurnProfile>(getTurnStrategy);
  const [loopMaxCostTier, setLoopMaxCostTier] = useState<string | null>(null);
  const [roomPreset, setRoomPreset] = useState<string | null>(null);
  const [availablePresets, setAvailablePresets] = useState<RoomPreset[]>([]);
  const presetBootRef = useRef(false);

  const resolvedRoomPresets = useMemo(
    () => resolveRoomPresets(availablePresets),
    [availablePresets],
  );

  const composeMode: ComposeMode = "discuss";

  const changeTurnProfile = useCallback((profile: ComposerTurnProfile) => {
    setTurnProfileState(profile);
    setTurnStrategy(profile);
    setTurnProfile(profile);
  }, []);

  const applyPresetTurnProfile = useCallback(
    (presetId: string) => {
      const mapped = turnProfileForRoomPreset(presetId);
      if (mapped) changeTurnProfile(mapped);
    },
    [changeTurnProfile],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchRoomModes()
      .then((catalog) => {
        if (cancelled) return;
        const loopMode = catalog.modes.find((mode) => mode.id === "loop");
        const maxTier = loopMode?.budget?.max_cost_tier;
        if (typeof maxTier === "string" && maxTier.trim()) {
          setLoopMaxCostTier(maxTier.trim().toLowerCase());
        }
      })
      .catch(() => {
        if (!cancelled) setLoopMaxCostTier(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void fetchRoomPresets()
      .then((catalog) => {
        if (cancelled) return;
        setAvailablePresets(catalog.presets);
        const def = catalog.default?.trim().toLowerCase();
        if (def && !presetBootRef.current) {
          presetBootRef.current = true;
          setRoomPreset(def);
          applyPresetTurnProfile(def);
        }
      })
      .catch(() => {
        if (!cancelled) setAvailablePresets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [applyPresetTurnProfile]);

  useEffect(() => {
    if (presetBootRef.current || roomPreset !== null) return;
    const fallback =
      resolvedRoomPresets.find((p) => p.id === "supervisor") ??
      resolvedRoomPresets[0];
    if (!fallback) return;
    presetBootRef.current = true;
    setRoomPreset(fallback.id);
    applyPresetTurnProfile(fallback.id);
  }, [resolvedRoomPresets, roomPreset, applyPresetTurnProfile]);

  useEffect(() => {
    const raw = sessionRoomPreset;
    if (typeof raw !== "string" || !raw.trim()) return;
    const id = raw.trim().toLowerCase();
    if (!resolvedRoomPresets.some((p) => p.id === id)) return;
    setRoomPreset(id);
    presetBootRef.current = true;
  }, [sessionRoomPreset, resolvedRoomPresets]);

  const composerModeVariant = useMemo((): "discuss" | "plan" | "consensus" => {
    const profile = resolveTurnSend(turnProfile, selectedAgents);
    if (profile.consensusMode) return "consensus";
    return "discuss";
  }, [turnProfile, selectedAgents]);

  const composerPresetHint = useMemo(() => {
    const activePreset = resolvedRoomPresets.find((p) => p.id === roomPreset);
    return presetHintLine(activePreset, locale);
  }, [resolvedRoomPresets, roomPreset, locale]);

  const composerEmergenceHint = useMemo(() => {
    if (roomPreset !== "supervisor" && turnProfile !== "loop") return null;
    return emergenceHintLine(sessionRun, locale);
  }, [roomPreset, turnProfile, sessionRun, locale]);

  const composerCostHint = useMemo(() => {
    if (roomPreset !== "supervisor" && turnProfile !== "loop") return null;
    return loopCostHintLine(
      healthAgents,
      selectedAgents,
      "loop",
      locale,
      loopMaxCostTier ?? undefined,
    );
  }, [
    roomPreset,
    turnProfile,
    healthAgents,
    selectedAgents,
    locale,
    loopMaxCostTier,
  ]);

  const selectRoomPreset = useCallback(
    (id: string) => {
      const next = roomPreset === id ? null : id;
      setRoomPreset(next);
      if (next) applyPresetTurnProfile(next);
    },
    [roomPreset, applyPresetTurnProfile],
  );

  /** §3.2.1: force a preset (no toggle) — e.g. fast→supervisor on roster>1. */
  const forceRoomPreset = useCallback(
    (id: string) => {
      setRoomPreset(id);
      applyPresetTurnProfile(id);
    },
    [applyPresetTurnProfile],
  );

  return {
    turnProfile,
    changeTurnProfile,
    roomPreset,
    setRoomPreset,
    selectRoomPreset,
    forceRoomPreset,
    availablePresets,
    resolvedRoomPresets,
    visiblePresets: resolvedRoomPresets,
    composeMode,
    composerModeVariant,
    composerPresetHint,
    composerEmergenceHint,
    composerCostHint,
    loopMaxCostTier,
  };
}
