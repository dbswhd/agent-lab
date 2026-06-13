# web/src — 프론트엔드 에이전트 가이드

## API
- 서버 통신: `web/src/api/client.ts`만 사용 (`apiBase()`, `apiUrl()`, `json()`)
- Room SSE: `runRoom()` + `consumeSse()` 조합 (직접 EventSource 금지)
- axios 도입 금지, API URL 하드코딩 금지

## 컴포넌트·스타일
- 새 컴포넌트: `web/src/components/` PascalCase
- 스타일: `web/src/styles/` — `main.tsx` import 순서: tokens → base → layout → surfaces → plan-execute → overlays → tweaks → prototype-panels (Tailwind/styled-components 금지)
- 상태: React state + context (Redux/Zustand 금지)

## 타입
- API 타입: `client.ts`에서 정의·재사용
- `any` 불가피 시 이유 주석 필수

## 금지
- `console.log` 커밋
- execute/objection UX 우회 fetch

## 주요 컴포넌트
- `PlanExecutePanel.tsx` — execute UI
- `RoomChat.tsx` — Room 대화
- `WorkPanel.tsx` — Work tab (stepper + mission strip)
