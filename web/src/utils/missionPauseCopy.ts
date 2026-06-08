/** Human-readable mission pause / circuit-breaker copy for Work tab. */

const PAUSE_REASON: Record<string, { ko: string; en: string }> = {
  global_cancel: {
    ko: "전역 정지(⌘.)로 미션이 일시정지되었습니다. 진행 중 실행은 정리되었습니다.",
    en: "Mission paused by global stop (⌘.). Open execution was cleaned up when possible.",
  },
  circuit_breaker: {
    ko: "구조적 실패 한도에 도달해 미션이 차단되었습니다. discuss 복구 후 재개하세요.",
    en: "Mission hit a structural failure cap. Resume after discuss recovery.",
  },
  momus_round_cap: {
    ko: "Plan gate Momus 라운드 한도에 도달했습니다. plan을 수정한 뒤 discuss에서 재합의하세요.",
    en: "Plan gate Momus round cap reached. Revise the plan and re-align in discuss.",
  },
  open_block: {
    ko: "열린 BLOCK objection이 있어 execute가 중단되었습니다.",
    en: "Execute stopped due to an open BLOCK objection.",
  },
  test_stop: {
    ko: "미션이 일시정지되었습니다.",
    en: "Mission paused.",
  },
};

export function missionPauseAlertText(input: {
  ko: boolean;
  pauseReason?: string | null;
  circuitBreaker?: boolean;
  circuitBreakerReason?: string | null;
  resumePhase?: string | null;
}): string {
  const lang = input.ko ? "ko" : "en";
  const key =
    (input.circuitBreaker && input.circuitBreakerReason) ||
    input.pauseReason ||
    "";
  const mapped = PAUSE_REASON[key];
  if (mapped) {
    const base = mapped[lang];
    const resume = input.resumePhase?.trim();
    if (!resume) return base;
    return input.ko
      ? `${base} 재개 시 ${resume} 단계로 돌아갑니다.`
      : `${base} Resume returns to ${resume}.`;
  }
  return input.ko
    ? "미션이 일시정지됨 — 진행 중 실행은 정리되었습니다."
    : "Mission paused — open execution cleaned up when possible.";
}

export function missionCircuitBreakerHint(
  reason: string | null | undefined,
  ko: boolean,
): string {
  const key = (reason || "").trim();
  const mapped = PAUSE_REASON[key];
  if (mapped) return mapped[ko ? "ko" : "en"];
  return ko
    ? "회로 차단기가 켜졌습니다. discuss에서 원인을 해결한 뒤 재개하세요."
    : "Circuit breaker is on. Resolve in discuss, then resume.";
}
