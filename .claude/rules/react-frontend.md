---
paths:
  - "web/src/**/*.tsx"
  - "web/src/**/*.ts"
---

# React 프론트엔드 규칙

## API
- 서버 통신: `web/src/api/client.ts`만 사용 (`apiBase()`, `apiUrl()`, `json()`)
- Room SSE: `runRoom()` + `consumeSse()` (직접 EventSource/fetch 조합 금지)
- axios 도입 금지; API URL 하드코딩 금지

## 컴포넌트 & 스타일
- 새 UI: `web/src/components/` (기존 PascalCase 패턴)
- 스타일: `web/src/styles/app.css` 클래스 (Tailwind/styled-components 금지)
- 상태: React state + context (Redux/Zustand 금지)

## 타입
- API 타입: `client.ts`에 정의·재사용
- `any` 사용 시 이유 주석

## 금지
- `console.log` 커밋
- execute/objection UX를 우회하는 one-off fetch

## 참고
- Execute UI: `PlanExecutePanel.tsx` · Room: `RoomChat.tsx`
