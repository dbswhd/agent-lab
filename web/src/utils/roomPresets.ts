import type { RoomPreset } from "../api/client";
import type { Locale } from "../i18n/locale";

/** Static fallback when /api/room/presets is unreachable — matches `room_preset.py`. */
export const FALLBACK_ROOM_PRESETS: RoomPreset[] = [
  {
    id: "fast",
    turn_profile: "quick",
    description: "Single-agent instant response — no debate, no consensus",
    role_policy: "off",
    max_agents: 1,
    label: "Fast",
  },
  {
    id: "supervisor",
    turn_profile: "loop",
    description: "Multi-agent consensus, plan, verify, and mission loop execute",
    role_policy: "auto",
    label: "Supervisor",
  },
];

export function resolveRoomPresets(apiPresets?: RoomPreset[] | null): RoomPreset[] {
  const fromApi = (apiPresets ?? []).filter((p) => String(p.id || "").trim());
  return fromApi.length > 0 ? fromApi : [...FALLBACK_ROOM_PRESETS];
}

const PRESET_LABEL_KO: Record<string, string> = {
  fast: "빠른",
  supervisor: "감독",
};

const PRESET_DESC_KO: Record<string, string> = {
  fast: "에이전트 1명 · 즉답 · plan 없음",
  supervisor: "멀티 에이전트 · plan · 검증 · mission loop",
};

export function presetDisplayLabel(
  preset: RoomPreset | string,
  locale: Locale = "en",
): string {
  const id = typeof preset === "string" ? preset : preset.id;
  if (locale === "ko") {
    return PRESET_LABEL_KO[id] ?? (typeof preset === "object" ? preset.label : undefined) ?? id;
  }
  if (typeof preset === "object" && preset.label?.trim()) {
    return preset.label.trim();
  }
  return id;
}

export function presetHintLine(
  preset: RoomPreset | null | undefined,
  locale: Locale = "en",
): string | null {
  if (!preset) return null;
  if (locale === "ko" && PRESET_DESC_KO[preset.id]) {
    return PRESET_DESC_KO[preset.id];
  }
  return preset.description?.trim() || null;
}
