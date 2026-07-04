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
  supervisor: "창발 모드 · 멀티 에이전트 · plan · 검증 · mission loop",
};

const RECOMB_SKIP_KO: Record<string, string> = {
  efficiency: "효율 모드 — 재조합 라운드 스킵",
  efficiency_mode: "효율 모드 — 재조합 라운드 스킵",
  single_proposer: "제안자 1명 — 재조합 스킵",
  cap: "호출 한도 — 재조합 스킵",
  policy: "정책 — 재조합 스킵",
  insufficient_proposers: "제안 부족 — 재조합 스킵",
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
  if (preset.id === "supervisor" && locale === "en") {
    return "Emergence mode — multi-agent consensus, plan, verify, mission loop";
  }
  return preset.description?.trim() || null;
}

function readRecombinationSkip(run: Record<string, unknown> | null | undefined): string | null {
  const consensus = run?.consensus;
  if (!consensus || typeof consensus !== "object") return null;
  const recomb = (consensus as Record<string, unknown>).recombination;
  if (!recomb || typeof recomb !== "object") return null;
  const skipped = (recomb as Record<string, unknown>).skipped;
  return typeof skipped === "string" && skipped.trim() ? skipped.trim() : null;
}

/** Supervisor emergence / recombination skip line for composer (F3). */
export function emergenceHintLine(
  run: Record<string, unknown> | null | undefined,
  locale: Locale = "en",
): string | null {
  const preset = String(run?.room_preset ?? "").trim().toLowerCase();
  if (preset !== "supervisor") return null;
  const skipped = readRecombinationSkip(run);
  if (skipped) {
    if (locale === "ko") {
      return RECOMB_SKIP_KO[skipped] ?? `재조합 스킵: ${skipped}`;
    }
    return `Recombination skipped: ${skipped}`;
  }
  if (run?.discuss_light) {
    return locale === "ko"
      ? "경량 discuss — 전원 동시 1 wave · 합의 다라운드 없음"
      : "Light discuss — full-parallel 1 wave, no consensus multi-round";
  }
  if (run?.room_preset_promoted_from === "fast") {
    return locale === "ko"
      ? "빠른→감독 승격 (에이전트 2명 이상)"
      : "Promoted fast→supervisor (roster > 1)";
  }
  if (locale === "ko") {
    return "창발 모드 — discuss는 경량 1라운드 · plan 시 합의";
  }
  return "Emergence mode — light discuss; consensus on plan turns";
}

/** §3.2.1: fast is single-agent; roster>1 must not be silent. */
export function fastRosterOverflow(
  roomPreset: string | null | undefined,
  selectedCount: number,
): boolean {
  return roomPreset === "fast" && selectedCount > 1;
}

export function fastRosterOverflowHint(locale: Locale = "en"): string {
  return locale === "ko"
    ? "빠른 모드는 에이전트 1명만 — 2명 이상이면 감독으로 전환됩니다"
    : "Fast is single-agent — switching to supervisor for roster > 1";
}
