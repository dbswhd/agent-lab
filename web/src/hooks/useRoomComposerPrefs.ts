import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentHealthRow, RoomPreset } from "../api/client";
import { fetchRoomPresets } from "../api/client";
import { fetchRoomModes, loopCostHintLine } from "../utils/roomModes";
import {
  emergenceHintLine,
  presetHintLine,
  resolveRoomPresets,
} from "../utils/roomPresets";
import {
  composerRoutingHintLine,
  IMPLICIT_ROOM_PRESET,
  resolveComposerModeVariant,
  TOPIC_ONLY_COMPOSER,
} from "../utils/roomComposerPrefs";
import {
  resolveTurnSend,
  turnProfileForRoomPreset,
  type ComposerTurnProfile,
} from "../utils/turnProfile";

export type UseRoomComposerPrefsArgs = {
  sessionRoomPreset?: string | null;
  locale: "en" | "ko";
  healthAgents: AgentHealthRow[];
  selectedAgents: string[];
  sessionRun?: Record<string, unknown>;
  /** Live composer draft — pre-send routing hints. */
  draftTopic?: string;
};

/** Phase 1c (F6): implicit room preset + composer hints — topic-only era. */
export function useRoomComposerPrefs({
  sessionRoomPreset,
  locale,
  healthAgents,
  selectedAgents,
  sessionRun,
  draftTopic = "",
}: UseRoomComposerPrefsArgs) {
  const [loopMaxCostTier, setLoopMaxCostTier] = useState<string | null>(null);
  const [roomPreset, setRoomPreset] = useState<string | null>(null);
  const [availablePresets, setAvailablePresets] = useState<RoomPreset[]>([]);
  const presetBootRef = useRef(false);

  const resolvedRoomPresets = useMemo(
    () => resolveRoomPresets(availablePresets),
    [availablePresets],
  );

  const effectivePreset = roomPreset ?? IMPLICIT_ROOM_PRESET;

  const turnProfile = useMemo(
    (): ComposerTurnProfile => turnProfileForRoomPreset(effectivePreset),
    [effectivePreset],
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
        if (presetBootRef.current) return;
        presetBootRef.current = true;
        const boot = TOPIC_ONLY_COMPOSER
          ? IMPLICIT_ROOM_PRESET
          : (catalog.default?.trim().toLowerCase() ?? IMPLICIT_ROOM_PRESET);
        setRoomPreset(boot);
      })
      .catch(() => {
        if (cancelled) return;
        if (presetBootRef.current) return;
        presetBootRef.current = true;
        if (TOPIC_ONLY_COMPOSER) {
          setRoomPreset(IMPLICIT_ROOM_PRESET);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (TOPIC_ONLY_COMPOSER || presetBootRef.current || roomPreset !== null) {
      return;
    }
    const fallback =
      resolvedRoomPresets.find((p) => p.id === IMPLICIT_ROOM_PRESET) ??
      resolvedRoomPresets[0];
    if (!fallback) return;
    presetBootRef.current = true;
    setRoomPreset(fallback.id);
  }, [resolvedRoomPresets, roomPreset]);

  useEffect(() => {
    if (TOPIC_ONLY_COMPOSER) return;
    const raw = sessionRoomPreset;
    if (typeof raw !== "string" || !raw.trim()) return;
    const id = raw.trim().toLowerCase();
    if (!resolvedRoomPresets.some((p) => p.id === id)) return;
    setRoomPreset(id);
    presetBootRef.current = true;
  }, [sessionRoomPreset, resolvedRoomPresets]);

  const composerModeVariant = useMemo((): "discuss" | "plan" | "consensus" => {
    const profile = resolveTurnSend(turnProfile, selectedAgents);
    const planWorkflow = sessionRun?.plan_workflow as
      | { enabled?: boolean }
      | undefined;
    return resolveComposerModeVariant({
      consensusMode: profile.consensusMode,
      planWorkflowActive: Boolean(planWorkflow?.enabled),
      topic: draftTopic,
      sessionTopic:
        typeof sessionRun?.topic === "string" ? sessionRun.topic : undefined,
      discussLight:
        typeof sessionRun?.discuss_light === "boolean"
          ? sessionRun.discuss_light
          : undefined,
    });
  }, [turnProfile, selectedAgents, sessionRun, draftTopic]);

  const composerRoutingHint = useMemo(
    () =>
      composerRoutingHintLine({
        run: sessionRun,
        draftTopic,
        locale,
      }),
    [sessionRun, draftTopic, locale],
  );

  const composerPresetHint = useMemo(() => {
    if (TOPIC_ONLY_COMPOSER) return null;
    const activePreset = resolvedRoomPresets.find((p) => p.id === roomPreset);
    return presetHintLine(activePreset, locale);
  }, [resolvedRoomPresets, roomPreset, locale]);

  const composerEmergenceHint = useMemo(() => {
    if (effectivePreset !== "supervisor") return null;
    return emergenceHintLine(sessionRun, locale);
  }, [effectivePreset, sessionRun, locale]);

  const composerCostHint = useMemo(() => {
    if (effectivePreset !== "supervisor") return null;
    return loopCostHintLine(
      healthAgents,
      selectedAgents,
      turnProfile,
      locale,
      loopMaxCostTier ?? undefined,
    );
  }, [effectivePreset, loopMaxCostTier, healthAgents, selectedAgents, turnProfile, locale]);

  const forceRoomPreset = useCallback((id: string) => {
    setRoomPreset(id);
    presetBootRef.current = true;
  }, []);

  return {
    turnProfile,
    roomPreset: effectivePreset,
    forceRoomPreset,
    resolvedRoomPresets,
    composerModeVariant,
    composerPresetHint,
    composerRoutingHint,
    composerEmergenceHint,
    composerCostHint,
  };
};
