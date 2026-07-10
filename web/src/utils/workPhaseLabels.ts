import type { WorkPhase } from "./workStatusPhase";

export type WorkPhaseLabel = {
  readonly id: WorkPhase;
  readonly ko: string;
  readonly en: string;
};

export const WORK_PHASE_LABELS: readonly WorkPhaseLabel[] = [
  { id: "plan_draft", ko: "실행 준비", en: "Prepare" },
  { id: "review_needed", ko: "실행 검토", en: "Review plan" },
  { id: "execute_pending", ko: "변경 중", en: "Build" },
  { id: "merge_verify", ko: "변경 검토", en: "Review changes" },
  { id: "done", ko: "검증 완료", en: "Verified" },
] as const;

export function workPhaseLabel(phase: WorkPhase, locale: "ko" | "en"): string {
  const entry = WORK_PHASE_LABELS.find((candidate) => candidate.id === phase);
  if (!entry) return phase;
  return locale === "ko" ? entry.ko : entry.en;
}
