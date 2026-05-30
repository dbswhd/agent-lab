export function roundDividerLabel(
  round: number,
  reviewMode = false,
  consensusMode = false,
): string {
  if (round <= 1) {
    return consensusMode
      ? `── ${round}라운드 · 병렬 · 자유 토론 ──`
      : `── ${round}라운드 · 병렬 · 동시 응답 ──`;
  }
  if (consensusMode) {
    return `── ${round}라운드 · 순차 · 합의 확인 ──`;
  }
  if (reviewMode) {
    return `── ${round}라운드 · 순차 · 검토(claude→codex→cursor) ──`;
  }
  return `── ${round}라운드 · 순차 · 이전 답변 반영 ──`;
}

export function consensusEndLabel(
  anchorAgent: string,
  agentLabel: (id: string) => string,
): string {
  return `── 합의 종료 · 이의 없음 · 앵커 ${agentLabel(anchorAgent)} ──`;
}

export function consensusIncompleteLabel(message?: string): string {
  return message
    ? `── 합의 미완 · ${message} ──`
    : "── 합의 미완 · 상한 도달 ──";
}
