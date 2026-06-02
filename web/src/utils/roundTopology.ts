export function roundDividerLabel(
  round: number,
  reviewMode = false,
  consensusMode = false,
  debatePhase = false,
): string {
  if (round <= 1) {
    return consensusMode
      ? `── ${round}라운드 · 병렬 · 주장 ──`
      : `── ${round}라운드 · 병렬 · 분석 ──`;
  }
  if (consensusMode && debatePhase) {
    return reviewMode
      ? `── ${round}라운드 · 순차 · 반박·재검증 ──`
      : `── ${round}라운드 · 순차 · 이어가기·확장 ──`;
  }
  if (consensusMode) {
    return `── ${round}라운드 · 순차 · 합의 확인 ──`;
  }
  if (reviewMode) {
    return `── ${round}라운드 · 순차 · 검토(claude→codex→cursor) ──`;
  }
  return `── ${round}라운드 · 순차 · 토론 이어가기 ──`;
}

export function consensusIncompleteLabel(message?: string): string {
  return message
    ? `── 합의 미완 · ${message} ──`
    : "── 합의 미완 · 상한 도달 ──";
}
