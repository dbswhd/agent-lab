# UI Progressive Disclosure Improvements

## 배경

기능 추가가 누적되면서 사이드바와 뷰 탭바에 개발자용 정보가 항상 노출되어 macOS 네이티브 앱 수준의 깔끔함이 저하됨. 이를 **progressive disclosure** 패턴으로 개선 — 기능은 모두 유지하되 기본 상태를 최소화.

---

## 변경 내역

### 1. `AgentHealthPanel.tsx` — 단일 요약 라인 + 펼침

**Before:** 3개 에이전트 행이 항상 펼쳐진 채 표시.

**After:** 기본은 `"● API 8765 · N/3 ready"` 한 줄만 표시. 클릭하면 에이전트별 상세 행이 펼쳐짐.

- `useState(false)`로 접힘 상태 추가
- 기존 head 영역이 toggle button 역할 (접근성: `aria-expanded` 포함)
- 새로고침 버튼(↻)은 이벤트 버블링 차단 (`e.stopPropagation()`) 처리로 별도 동작 유지
- chevron(`›`) 아이콘이 CSS로 회전하여 펼침 상태 시각적 피드백

### 2. `ApiDiagnosticsBar.tsx` — 경로만 항상, 진단 도구는 접힘

**Before:** 세션 경로 + 진단 버튼 2개 + 부트 로그가 항상 노출.

**After:** 세션 경로(및 오프라인/bridge 실패 경고)만 항상 표시. 진단 버튼과 부트 로그는 `<details>` "진단 도구" 안으로 이동.

- 외부 `<details className="api-diagnostics-bar__detail">` 추가
- 기존 부트 로그 `<details>`는 중첩 구조로 유지
- 오류/경고 메시지는 여전히 항상 표시 (기능 우선순위 유지)

### 3. `AgentSessionSettings.tsx` — 기본 접힘

**Before:** `compact` prop이 false일 때(새 세션) 3열 에이전트 설정 그리드가 자동으로 펼쳐짐.

**After:** 항상 접힌 채 시작. 사용자가 토글을 클릭해야 펼쳐짐.

- `useState(!compact)` → `useState(false)` 한 줄 변경
- 기존 toggle button/aria-expanded 구조는 이미 있었으므로 JSX 변경 불필요

### 4. `RoomChat.tsx` — 뷰 탭바 체크박스 이동

**Before:** "Human 요약" / "동료 채널" 체크박스가 view-tabs-bar 안에 항상 노출되어 어수선함.

**After:** 탭바 우측의 `⋯` 버튼 클릭 시 나타나는 popover 안으로 이동.

- `useState(false)`로 `viewOptionsOpen` state 추가
- `view-tabs-bar__trailing` div 안에 `view-options-btn` + 조건부 `view-options-popover` 배치
- 체크박스 기능(showHumanSynthesis, showPeerChannel, 카운트 표시)은 완전히 동일하게 유지

### 5. `app.css` — 컴포저 힌트 텍스트 약화

**Before:** `font-size: var(--text-footnote)` — 기본 밝기로 항상 표시.

**After:** `font-size: 10px; opacity: 0.7;` — 크기 줄이고 불투명도 낮춰 시각적 노이즈 감소.

### 6. `macos26.css` — 신규 컴포넌트 스타일 추가

새로 추가된 UI 패턴을 위한 CSS 추가:
- `.agent-health-panel__toggle` / `__chev` — 토글 버튼 및 chevron 회전 애니메이션
- `.api-diagnostics-bar details summary` — details/summary 기본 마커 제거 및 커스텀 chevron
- `.agent-session-settings__toggle*` — 에이전트 설정 토글 hover 스타일
- `.view-tabs-bar__trailing` / `.view-options-btn` / `.view-options-popover` / `.view-options-row` — 뷰 옵션 popover 전체 스타일 (Liquid Glass backdrop-filter 적용)

---

## 설계 원칙

| 원칙 | 적용 |
|------|------|
| Progressive Disclosure | 기본 상태 최소화, 필요 시 펼침 |
| Feature Parity | 모든 기능 유지, 접근 경로만 변경 |
| Accessibility | aria-expanded, aria-label, role 유지 |
| macOS 네이티브 느낌 | Liquid Glass backdrop-filter, 부드러운 transition |
