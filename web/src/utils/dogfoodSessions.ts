import type { SessionSummary } from "../api/client";

/**
 * Dogfood 세션 판별 — 토픽/ID에서 파생하는 순수 분류.
 * 파일 이동·백엔드 변경 없이 rail 표시만 가르므로 진행 중인 라이브 세션과
 * 충돌하지 않고, 패턴에 걸리는 과거·미래 세션이 전부 자동 반영된다.
 */
const DOGFOOD_PATTERNS: RegExp[] = [
  /dogfood/i, // "N4 dogfood …", "docs/_dogfood/x2-lift.md …" 등
  /x2[- ]?lift/i, // x2 execute lift fixture
  /consensus[- ]?라운드[- ]?cap[- ]?기본값/, // S1 관측 고정 토픽 — 슬러그(하이픈)/원문(공백) 둘 다
  /[-[]cat[-:\s]*(quick|standard|deep)\b/i, // dogfood-v1.json 카탈로그 "[cat: quick|standard|deep]" 태그
  /오타.*plan[- ]?action|plan[- ]?action.*dry-?run.*(승인|approve).*merge/, // x2-lift 이전 표기("docs 오타 1건 수정 plan action…")
  /trading[- ]?mission[- ]?장전/, // 매일 반복되는 trading mission 준비 세션
];

const HANGUL_RE = /[가-힣]/;

export function isDogfoodSession(session: SessionSummary): boolean {
  const texts = [session.topic ?? "", session.id ?? ""];
  if (
    texts.some((text) => DOGFOOD_PATTERNS.some((pattern) => pattern.test(text)))
  ) {
    return true;
  }
  // 스크립트가 만드는 세션은 전부 영문 kebab-case slug — 실사용 세션은 전부
  // 한글 자연어 문장이라, 한글이 아예 없으면 (그리고 topic/id가 비어있지 않으면)
  // 알려진 패턴을 안 넣어도 새 dogfood/fixture 스크립트가 자동으로 걸러진다.
  const id = session.id ?? "";
  return (
    id.length > 0 && !HANGUL_RE.test(session.topic ?? "") && !HANGUL_RE.test(id)
  );
}
