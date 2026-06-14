import { apiBase } from "../api/client";

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

export async function fetchRoomModes(
  opts?: { force?: boolean },
): Promise<RoomModeCatalog> {
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
  return catalog.modes
    .filter((m) => m.id === "quick" || m.id === "team" || m.id === "loop")
    .map((mode) => {
      const id = mode.id as "quick" | "team" | "loop";
      return {
        id,
        label: labels[id]?.[locale] ?? mode.id,
        description: roomModeDescription(mode, locale),
      };
    });
}
