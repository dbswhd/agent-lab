# Agent Lab — UI/UX 방향 & 외주 가이드

> **Legacy / deprecated (Tier 4)** — messenger RFP. **Current UI:** [developer-agent-console.md](./developer-agent-console.md) · [README.md](./README.md)
> 아래 iMessage/Instagram DM/Telegram 매핑은 역사 참고용입니다.

> **레거시 구현 메모:** [Figma macOS 26 UI Kit](https://www.figma.com/community/file/1543337041090580818/macos-26). Glass는 chrome만.

---

## 1. 레퍼런스 매핑 (무엇을 어디서 가져왔는지)

| 레퍼런스 | 가져온 요소 | Agent Lab 화면 |
|----------|-------------|----------------|
| **iMessage** | 파란 **보낸** 말풍선, 둥근 radius, 하단 **입력창 + 원형 전송** | 새 대화 · 내 주제 |
| **Instagram DM** | 왼쪽 **대화 목록**, 아바타·제목·한 줄 프리뷰·시간 | 세션 목록 |
| **Telegram** | **발신자 이름** 라벨(그룹 채팅), **고정 메시지** 블록 | Planner/Critic/Scribe 라벨 · plan.md 고정 |

### 제품 톤 (유지)

- 무한 채팅앱이 아니라 **3명이 차례로 답하는 짧은 스레드**
- 최종 산출물 = **plan.md** (고정/문서 탭)
- 다크 UI 기본 (`#000` / `#0A84FF` iOS blue)

---

## 2. 화면 3종 (Figma 프레임)

| # | 화면 | 스펙 |
|---|------|------|
| A | **새 대화** | 헤더, 말풍선 영역, typing `...`, composer, 백엔드 pill |
| B | **DM 목록** | 행 높이 72px 전후, 아바타 28px, selected state |
| C | **세션 상세** | 탭: 대화 / plan.md, pinned plan 카드 |

### 상태

- Typing indicator (3 dots bounce)
- Sent / received bubble colors
- Error banner (빨간 배경 15%)
- Empty list / empty chat

---

## 3. 디자인 토큰 (코드와 1:1)

`web/src/styles/tokens.css`:

| Token | 용도 |
|-------|------|
| `--color-bubble-sent` | iMessage blue `#0A84FF` |
| `--color-bubble-received` | gray `#3A3A3C` |
| `--gradient-avatar` | IG-style avatar ring |
| `--radius-bubble` | 18px |
| `--chat-list-width` | 320px |

외주 시 **Variables** 이름을 위와 동일하게 유지하면 교체가 쉽습니다.

---

## 4. Figma 커뮤니티 템플릿 — **괜찮고, 오히려 추천**

처음부터 그리지 않아도 됩니다. **이미 등록된 UI Kit / 템플릿**을 베이스로 쓰고, Agent Lab에 맞게 **3화면만 조립**하는 방식이 빠릅니다.

### 검색 키워드 (Figma Community)

| 검색어 | 쓸 부분 |
|--------|---------|
| `iOS iMessage` / `Messages UI Kit` | 말풍선, composer, sent/received |
| `Instagram DM` / `Messenger chat list` | 왼쪽 대화 목록 행 |
| `Telegram UI Kit` / `Telegram dark` | 발신자 라벨, 그룹 채팅, pinned |
| `Chat app dark` / `Messaging UI kit` | 통합 키트 (한 파일에 다 있을 때) |

### 템플릿 고를 때 체크

- [ ] **Dark mode** 프레임 있음  
- [ ] **Auto Layout** + Component variants (sent / received / typing)  
- [ ] 상업적 이용·라이선스 OK (Community 대부분 Free, 파일 설명 확인)  
- [ ] 과한 일러스트·브랜드 로고 없음 (교육용 로컬 앱)  

### 우리 코드에 맞추는 법 (템플릿 → 핸드오프)

1. 템플릿 **복제(Duplicate)** → 프로젝트 파일 `Agent-Lab.fig`  
2. 화면 3개만 남기거나 새 프레임: **Run / Session list / Session detail**  
3. 색상을 `tokens.css` 변수와 **이름 맞추기** (또는 Variables import 후 export)  
4. 컴포넌트 이름을 코드와 대응:
   - `ChatBubble` → Sent / Received / Typing  
   - `SessionList` → List row  
   - `Composer` → Input bar  
5. Dev Mode에서 CSS 복사 → `web/src/styles/` (한 번에 덮지 말고 토큰부터)

**주의:** 템플릿은 보통 “무한 채팅” 가정 → **3턴 + plan 고정**만 남기고 나머지 프레임은 삭제해도 됨.

### 템플릿 vs 처음부터 vs Stitch

| 방식 | 언제 |
|------|------|
| **Figma 템플릿** | 픽셀·간격·상태를 빠르게 맞출 때 (**지금 추천**) |
| 처음부터 Figma | 브랜드·특수 레이아웃이 필요할 때 |
| Stitch / Claude Design | 템플릿 고르기 **전** 레이아웃 2안만 볼 때 |

---

## 5. 어디에 외주 맡기면 좋은지

| 도구 | 추천 용도 |
|------|-----------|
| **Figma (+ Community 템플릿)** | **1순위** — Kit 복제 후 3화면 조립, Dev Mode |
| **Stitch** | 템플릿 고르기 **전** 레이아웃 감 잡기 |
| **Claude Design** | 말풍선·목록 컴포넌트만 뽑아서 CSS 이식 |

### 워크플로 (템플릿 있을 때)

1. Community에서 Messaging / iOS / Telegram Kit **1개** Duplicate  
2. Run · List · Detail 프레임 정리 + 한국어 라벨  
3. `tokens.css` ↔ Figma Variables 동기화  
4. `web/src/components/*` className·spacing만 PR  

상세 사용 흐름: **[docs/03-workflow.md](./03-workflow.md)**

---

## 6. 핸드오프 파일 맵

| 컴포넌트 | 경로 |
|----------|------|
| 말풍선 | `web/src/components/ChatBubble.tsx` |
| 아바타 | `web/src/components/Avatar.tsx` |
| DM 목록 | `web/src/components/SessionList.tsx` |
| 새 대화 | `web/src/components/RunPanel.tsx` |
| 세션 뷰 | `web/src/components/SessionViewer.tsx` |
| 레이아웃 | `web/src/App.tsx` |
| API (변경 자제) | `web/src/api/client.ts` |

---

## 7. 외주 RFP (복붙용)

> Dark messenger UI for “Agent Lab”: user sends a topic (blue bubble), three agents reply in sequence (gray bubbles with sender names, typing indicator). Left panel = conversation list (Instagram DM style). Pinned plan.md tab (Telegram-style). Deliver Figma with CSS variables matching `tokens.css`. Korean UI labels.

---

## 8. 하지 말 것

- 카톡/슬랙 **무한 스크롤** 채팅 UX (우리는 3턴 고정)  
- pipeline 트레이딩·차트 UI  
- API/SSE 계약 변경 (백엔드 팀 합의 없이)

관련: [docs/03-workflow.md](./03-workflow.md) · [docs/APP.md](./APP.md)
