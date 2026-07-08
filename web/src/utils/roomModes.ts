import { apiBase } from "../api/client";
import type { AgentHealthRow } from "../api/client";
import { normalizeTurnProfile, type ComposerTurnProfile } from "./turnProfile";
import { TURN_MODE_ORDER } from "./agentOrder";

export type RoomModeRow = {
  id: string;
  agents: string;
  plan: string;
  plan_intent: string;
  execute_loop_on_approve: boolean;
  budget?: Record<string, unknown>;
};

export type RoomModeCatalog = {
  modes: RoomModeRow[];
  legacy_migration: Record<string, string>;
  verified_routing?: Record<string, Record<string, unknown>>;
};

let cachedCatalog: RoomModeCatalog | null = null;

export async function fetchRoomModes(opts?: {
  force?: boolean;
}): Promise<RoomModeCatalog> {
  if (cachedCatalog && !opts?.force) {
    return cachedCatalog;
  }
  const res = await fetch(`${apiBase()}/api/room/modes`);
  if (!res.ok) {
    throw new Error(await res.text());
  }
  const body = (await res.json()) as RoomModeCatalog;
  cachedCatalog = body;
  return body;
}

export function roomModeDescription(
  mode: RoomModeRow,
  locale: "en" | "ko" = "en",
): string {
  const ko = locale === "ko";
  const plan =
    mode.plan === "required"
      ? ko
        ? "plan 필수"
        : "plan required"
      : ko
        ? "plan 선택"
        : "optional plan";
  const exec = mode.execute_loop_on_approve
    ? ko
      ? "실행/검증 게이트"
      : "execute/verify gates"
    : ko
      ? "plan-only"
      : "plan-only";
  return `${mode.agents} · ${plan} · ${exec}`;
}

export function turnStrategyFromCatalog(
  catalog: RoomModeCatalog,
  locale: "en" | "ko" = "en",
): {
  id: "quick" | "team" | "loop";
  label: string;
  description: string;
}[] {
  const labels: Record<string, { en: string; ko: string }> = {
    quick: { en: "Quick", ko: "빠른" },
    team: { en: "Team", ko: "팀" },
    loop: { en: "Loop", ko: "루프" },
  };
  const byId = new Map(
    catalog.modes
      .filter((m) =>
        TURN_MODE_ORDER.includes(m.id as (typeof TURN_MODE_ORDER)[number]),
      )
      .map((mode) => [mode.id, mode] as const),
  );
  return TURN_MODE_ORDER.map((id) => byId.get(id))
    .filter((mode): mode is RoomModeRow => Boolean(mode))
    .map((mode) => {
      const id = mode.id as "quick" | "team" | "loop";
      return {
        id,
        label: labels[id]?.[locale] ?? mode.id,
        description: roomModeDescription(mode, locale),
      };
    });
}

const TIER_LABEL: Record<string, { en: string; ko: string }> = {
  low: { en: "low", ko: "저" },
  medium: { en: "med", ko: "중" },
  high: { en: "high", ko: "고" },
};

export function loopCostHintLine(
  healthAgents: AgentHealthRow[],
  selectedAgentIds: string[],
  profile: ComposerTurnProfile,
  locale: "en" | "ko" = "en",
  maxCostTier?: string,
): string | null {
  const normalized = normalizeTurnProfile(profile);
  if (normalized !== "loop") return null;
  const ko = locale === "ko";
  const max = (maxCostTier || "high").toLowerCase();
  const maxLabel = TIER_LABEL[max]?.[locale] ?? max;
  const selected = selectedAgentIds
    .map((id) => healthAgents.find((row) => row.id === id))
    .filter((row): row is AgentHealthRow => Boolean(row));
  const blocked = selected.filter((row) => row.loop_cost_blocked);
  if (blocked.length) {
    const names = blocked.map((row) => row.id).join(", ");
    return ko
      ? `비용 한도 ${maxLabel} 초과 · ${names}`
      : `Cost ceiling ${maxLabel} · blocked ${names}`;
  }
  const tiers = [
    ...new Set(
      selected
        .map((row) => row.model_cost_tier)
        .filter((tier): tier is "low" | "medium" | "high" => Boolean(tier)),
    ),
  ];
  if (tiers.length) {
    const labels = tiers
      .map((tier) => TIER_LABEL[tier]?.[locale] ?? tier)
      .join("/");
    return ko
      ? `모델 비용 ${labels} · 루프 한도 ${maxLabel}`
      : `Model cost ${labels} · loop max ${maxLabel}`;
  }
  return ko ? `루프 비용 한도 ${maxLabel}` : `Loop cost ceiling ${maxLabel}`;
}
