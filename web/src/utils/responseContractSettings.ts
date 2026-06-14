import type {
  ResponseContractPreset,
  ResponseContractRecord,
} from "../api/client";

export const HOOK_RESPONSE_FLAG_NAMES = new Set([
  "AGENT_LAB_HOOKS_PATH",
  "AGENT_LAB_NATIVE_HOOKS",
  "AGENT_LAB_HOOK_TIMEOUT_S",
  "AGENT_LAB_ENVELOPE_STRICT",
  "AGENT_LAB_STRUCTURED_ENVELOPE",
  "AGENT_LAB_GUIDANCE_TIER",
  "AGENT_LAB_LEGACY_ENDORSE",
  "AGENT_LAB_MOCK_STRUCTURED_ENVELOPE",
]);

export const RESPONSE_CONTRACT_PRESETS: readonly {
  readonly preset: ResponseContractPreset;
  readonly label: string;
  readonly description: string;
}[] = [
  {
    preset: "concise",
    label: "Concise",
    description: "짧은 상태와 다음 행동 중심",
  },
  {
    preset: "evidence_first",
    label: "Evidence-first",
    description: "파일·테스트·근거를 결론보다 먼저",
  },
  {
    preset: "plan_ready",
    label: "Plan-ready",
    description: "what/where/verify 형태로 scribe 친화",
  },
  {
    preset: "review_only",
    label: "Review-only",
    description: "구현 제안보다 검토·위험 지적 우선",
  },
  {
    preset: "build_handoff",
    label: "Build handoff",
    description: "Build GO 전 scope·acceptance·blocker 정리",
  },
];

const COMMUNICATE_META_KEYS = [
  "envelope_strict",
  "guidance_tier",
  "structured_envelope",
  "parse_error",
  "missing_envelope",
  "acts",
  "repair_requested",
  "contract_invalid",
] as const;

export function recordString(
  row: Record<string, unknown> | null | undefined,
  key: string,
): string {
  const value = row?.[key];
  return typeof value === "string" ? value : "";
}

export function recordNumber(
  row: Record<string, unknown> | null | undefined,
  key: string,
): number | null {
  const value = row?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function recordBoolean(
  row: Record<string, unknown> | null | undefined,
  key: string,
): boolean {
  return row?.[key] === true;
}

function compactValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  try {
    return JSON.stringify(value);
  } catch (error) {
    if (error instanceof TypeError) return "[unserializable]";
    throw error;
  }
}

export function formatHookMeta(row: Record<string, unknown>): string {
  const humanTurn = recordNumber(row, "human_turn");
  const round = recordNumber(row, "parallel_round");
  const parts = [
    recordString(row, "agent"),
    humanTurn ? `turn ${humanTurn}` : "",
    round ? `R${round}` : "",
    recordString(row, "ts"),
  ].filter(Boolean);
  return parts.join(" · ") || "session hook";
}

export function communicateMetaRows(
  meta: Record<string, unknown> | null | undefined,
): Array<{ readonly label: string; readonly value: string }> {
  if (!meta) return [];
  const rows = COMMUNICATE_META_KEYS.flatMap((key) => {
    if (!(key in meta)) return [];
    return [{ label: key, value: compactValue(meta[key]) }];
  });
  if (rows.length > 0) return rows.slice(0, 8);
  return Object.entries(meta)
    .slice(0, 6)
    .map(([label, value]) => ({ label, value: compactValue(value) }));
}

export function parseResponseContract(
  value: unknown,
): ResponseContractRecord | null {
  if (!value || typeof value !== "object") return null;
  const record: ResponseContractRecord = {};
  if ("preset" in value && typeof value.preset === "string")
    record.preset = value.preset;
  if ("label" in value && typeof value.label === "string")
    record.label = value.label;
  if ("guidance" in value && typeof value.guidance === "string") {
    record.guidance = value.guidance;
  }
  if ("set_by" in value && typeof value.set_by === "string")
    record.set_by = value.set_by;
  if ("updated_at" in value && typeof value.updated_at === "string") {
    record.updated_at = value.updated_at;
  }
  return record;
}

export function isResponseContractPreset(
  value: unknown,
): value is ResponseContractPreset {
  return RESPONSE_CONTRACT_PRESETS.some((row) => row.preset === value);
}
