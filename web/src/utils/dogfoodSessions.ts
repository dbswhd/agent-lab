import type { SessionSummary } from "../api/client";

/**
 * Dogfood 세션 판별 — 토픽/ID에서 파생하는 순수 분류.
 * 파일 이동·백엔드 변경 없이 rail 표시만 가르므로 진행 중인 라이브 세션과
 * 충돌하지 않고, 패턴에 걸리는 과거·미래 세션이 전부 자동 반영된다.
 */
const DOGFOOD_PATTERNS: RegExp[] = [
  /dogfood/i, // "N4 dogfood …", "docs/_dogfood/x2-lift.md …" 등
  /x2[- ]?lift/i, // x2 execute lift fixture
  /consensus 라운드 cap 기본값/, // S1 관측 고정 토픽 (make s1-dogfood-env)
];

export function isDogfoodSession(session: SessionSummary): boolean {
  return [session.topic ?? "", session.id ?? ""].some((text) =>
    DOGFOOD_PATTERNS.some((pattern) => pattern.test(text)),
  );
}
