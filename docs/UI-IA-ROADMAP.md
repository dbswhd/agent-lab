# UI IA 로드맵 — 폐기 · 미구현 · 배치

> **Tier 3 (target IA)** — roadmap only. **Shipped backend/UI contracts:** [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) · [docs/README.md](./README.md)
> **Productization SSOT:** [CONSOLE-PRODUCTIZATION.md](CONSOLE-PRODUCTIZATION.md). This file owns detailed UI migration gaps; phase numbering for the broader program lives in Console Productization.

> **기준 시점:** 2026-06-10, `web/src` 새 디자인 셸(`.app` / `.shell` / `.pane`) + dual-class bridge  
> **Shipped since 2026-06-07:** Inspector **Overview / Tasks / Inbox**, `ContextOverviewPanel`, `GET/PATCH …/context-layers` (see [UI-MIGRATION-GAPS.md](UI-MIGRATION-GAPS.md) §1).
> **디자인 SSOT:** `~/Downloads/agent-lab/project/Agent Lab.html`  
> **행동 SSOT:** `project/uploads/03-BEHAVIOR-CONTRACT.md`, `docs/USER-GUIDE.md`  
> **관련:** [UI-MIGRATION-GAPS.md](UI-MIGRATION-GAPS.md) (갭 상세)

---

## 0. 목표 구조 (한 줄)

```
.app
├─ .titlebar          ← 세션 제목 · 에이전트 · 테마 · (inbox) · context 토글
└─ .shell             ← rail | pane  (+ context-sidebar는 pane 내부 pane-row)
   ├─ .rail           ← 세션 목록 · health chip · 새 session
   └─ .pane
      ├─ SettingsPage          (shellView=settings)
      └─ RoomChat              (기본)
         ├─ .tabbar             Transcript · Work · Run · Artifacts
         ├─ .pane-row
         │  ├─ .pane-main       탭 본문 + .taskbar-dock
         │  └─ .context-sidebar Overview · Tasks · Inbox
         └─ .composer           (transcript 탭에서만)
```

**원칙:** 로직(`api/`, `hooks/`, `utils/`, `run/`)은 유지. 화면은 프로토타입 IA에 맞추되, **생산 기능**(⌘K, Activity, Human gate)은 아래 배치표에 따라 흡수한다.

---

## 1. 폐기 (Deprecate → Remove)

기능을 없애는 것이 아니라 **별도 UI 축·중복 레이어·로드되지 않는 CSS**를 제거한다.

### 1.1 즉시 폐기 가능 (마이그레이션 잔재)

| 대상 | 이유 | 제거 조건 |
|------|------|-----------|
| ~~`web/src/styles/app.css`~~, ~~`developer-console.css`~~, ~~`satellites.css`~~, ~~`layout-extensions.css`~~, ~~`content-surfaces.css`~~, ~~`workspace-shell.css`~~, ~~`chrome.css`~~ **(삭제 완료)** · `macos26.css` | `main.tsx`에서 **미로드**. Figma reference only (`web/src/figma/`) | orphan CSS 삭제 완료; `macos26.css`는 import 없이 figma 매핑 참조용 유지 |
| `ChatToolbar.tsx` | 단일 `MacTitlebar` + `TitlebarSlotsContext`로 대체. **RunPanel·SessionViewer만** 아직 사용 | classic 모드 폐기 또는 titlebar 슬롯으로 이전 후 삭제 |
| `App.tsx` `mode: "classic"` 분기 | Room 워크플로가 기본·유일 목표 | `RunPanel` / `SessionViewer` 흡수 또는 Settings Legacy로 격리 후 `mode` state 삭제 |
| Rail footer **「…」 classic 토글** (`icon-btn` 세 번째) | 프로토타입에 없음, IA 분기 증가 | classic 제거와 동시 |
| Dual-class bridge (예: `taskbar room-task-bar`, `context-sidebar inspector-pane`) | canonical rename 완료 후 **한 벌만** 유지 | §2 cosmetic rename 완료 후 `legacy-bridge.css` 삭제 |
| ~~`layout-extensions.css`~~ | `layout.css`에 병합 완료 |
| ~~`satellites.css`~~ | 위성 규칙 `layout.css` / `overlays.css`로 이전 완료 |

### 1.2 프로토타입 전용 — 제품에 넣지 않음

| 대상 | 이유 |
|------|------|
| `TweaksPanel` (accent, density, gate variant, simulate objection) | 디자인 QA용. **ThemeToggle** + Settings로 충분 |
| Mock `DATA.*` 정적 플로우 | 실 API(`fetchSession`, `usePlanExecute`)로 이미 대체됨 |
| 프로토타입 **Context layer switch** (토글만 있고 API 없음) | §3.2 — API 없이 UI만 만들지 않음 |

### 1.3 코드 내부 deprecated (유지하되 신규 사용 금지)

| 대상 | 대체 |
|------|------|
| `LegacyWorkspaceTab` (`plan` / `review`) | `work` |
| `mac-btn-*`, `mac-segmented`, `mac-popup` | `base.css`의 `btn`, `segmented`, `field` |
| `workspace-shell`, `mac-app--developer-console` (TSX) | `.shell`, `.app` |
| `inspector-pane__*` (canonical) | `context-sidebar`, `ctx-*` |

---

## 2. 유지 · 통합 (기능은 살리고 위치/마크업만 정리)

| 현재 | 처리 |
|------|------|
| `RoomChat` + hooks | **앱 심장** — 유지 |
| `PlanExecutePanel` + `usePlanExecute` | Work 탭 본문 — 유지, 마크업만 `work-surface` / `exec-*` |
| `RoomTaskBar` | Transcript/Work **sticky `taskbar-dock`** — 유지. Inspector Tasks와 **역할 분리** (아래 §3.1) |
| `CommandPalette` (⌘K) | 유지 — **전역 오버레이**, 디자인만 `base.css` modal 토큰 적용 |
| `NotificationCenter` | 유지 — **Context Inbox/Activity** 또는 titlebar로 흡수 |
| `HumanInboxPanel` | 유지 — **Context Inbox 탭**으로 이동 |
| `SessionSetupBar` + `AgentSessionSettings` | 유지 — **New Session** 플로우로 통합 (§3.4) |
| `WorkPanel` / `WorkStatusBar` | **래퍼 축소** — `PlanExecutePanel` 직접 렌더, status는 `exec-status` 바 |

---

## 3. 미구현 — 구현 필요

### 3.1 IA 재정렬 (프로토타입 ↔ 생산 기능 매핑)

**현재 Inspector:** Tasks · Activity · Quick  
**목표 Inspector (Context sidebar):** **Overview · Tasks · Inbox**

| 목표 탭 | 넣을 내용 (기존 컴포넌트) | 데이터 소스 |
|---------|---------------------------|-------------|
| **Overview** | Goal (`goal-loop-banner` 요약만) · Next plan step (`plan.recommended`) · Context layers **읽기 전용** (`ContextPreviewPanel` 축약) · Team health (`AgentHealthPanel` mini) | `session`, `planMd`, `fetchContextPreview`, `healthAgents` |
| **Tasks** | Open objections 목록 · Task rows (요약) · consensus gate CTA | `fetchSessionTasks`, `resolveSessionObjection` |
| **Inbox** | `HumanInboxPanel` · `NotificationCenter` (읽지 않음 badge) | inbox API, `notificationStore` |

**옮기기 (Inspector Tasks → 다른 곳):**

| 현재 위치 | 이동 |
|-----------|------|
| `RoomTaskBar` 전체 (Inspector Tasks 안) | **Transcript/Work 본문** `taskbar-dock` (프로토타입과 동일). Inspector Tasks는 **요약+점프**만 |
| `goal-loop-banner` (편집 UI) | Overview: **표시** / 편집은 Overview 또는 Composer 상단 **한 줄** |
| `QuickSettingsPanel` | Settings `AgentSessionSettings`로 **흡수**. Inspector에서 **Quick 탭 삭제** |
| Activity 탭 | Inbox 하위 **「Activity」세그먼트** 또는 Inbox와 **단일 피드** (알림+human gate) |

**코드 터치:**

- `web/src/utils/workspaceTabs.ts` — `InspectorTab` → `"overview" | "tasks" | "inbox"`
- `web/src/components/InspectorPane.tsx` — `ctx-tabs` 라벨·badge 규칙
- `web/src/components/RoomChat.tsx` — Inspector children 재배치; `RoomTaskBar`를 `workspace-scroll` 안 `taskbar-dock`으로
- ✅ `web/src/components/ContextOverviewPanel.tsx` (Overview 전용 조립) — shipped

### 3.2 API 선행 없이 UI만 만들지 않는 것

| 기능 | 블로커 | UI 착수 조건 |
|------|--------|--------------|
| Titlebar **Inbox** unread (rail / multi-session) | `GET /api/inbox/summary` **shipped**; session rail badge 미구현 | Rail row badge 또는 aggregate cache |
| Rail **Sessions+Archive 동시 count** | `fetchSessions`가 탭별 1회 | 양쪽 count 한 번에 주는 API 또는 병렬 fetch + cache |

**Shipped:** Context layer **on/off** — `app/server/routers/context_layers.py`, `ContextOverviewPanel` + `ContextLayerBars`.

### 3.3 디자인 parity (API 있음 · UI만 없음)

| 기능 | 배치 | 구현 메모 |
|------|------|-----------|
| Session row **Avatar strip** | `.rail` → `SessionList` `session-item__agents` | `SessionSummary` + agent ids from session meta |
| Session row **dir/branch** | `session-item__sub` | `workspace_label`, git branch from `run.json` |
| **Transcript presentation** (console/bubble/compact) | Transcript `⋯` popover → `transcript--{mode}` on wrapper | `transcriptViewPrefs` 이미 있음 — UI만 프로토타입 seg |
| **Artifacts** card grid | Work 또는 Artifacts 탭 `artifact-row` / card | `session.run` artifacts list |
| **Run log** stream | Run 탭 `TurnRunPanel` → console stream 스타일 | SSE/`turnMessages` 유지 |
| Titlebar **Inbox** icon | `MacTitlebar` `trailing` (Theme 왼쪽) | unread > 0 badge → Context **Inbox** 탭 열기 |
| **Plan stale / objection** banner | Composer 위 (프로토타입 순서) | 이미 있음 — `CollapsibleGlassPanel` / `composer-objection-alert` canonical class |

### 3.4 New Session 플로우 (IA 결정)

**권장:** 프로토타입 `NewSessionDialog` (`ns-modal`) 채택.

| 단계 | 배치 |
|------|------|
| 트리거 | Rail `+ 새 Session` · ⌘N · (선택) titlebar |
| UI | **Modal** `ns-overlay` / `ns-modal` — dir, branch, agent pick |
| 완료 | 기존 `onRoomSessionChange` / `runRoom` 파이프라인 |
| 폐기 | `composerNew` 인라인 `SessionSetupBar` + `AgentSessionSettings` **신규 세션 전용 노출** |

`App.tsx` `composerNew`는 「모달 열림」 플래그로 축소하거나, 모달 완료 후에만 `RoomChat` mount.

---

## 4. 배치 다이어그램 (목표)

### 4.1 Transcript 탭

```
.pane-main
├─ .tabbar
├─ .workspace-body
│  └─ .workspace-scroll
│     ├─ .taskbar-dock          ← RoomTaskBar (펼침/접힘)
│     └─ .transcript.transcript--console
│        └─ .turn …              ← ChatBubble
└─ .composer                     ← ChatComposer (transcript only)
```

### 4.2 Work 탭

```
.pane-main
├─ .tabbar
└─ .workspace-scroll
   ├─ .taskbar-dock              ← (선택) 축약 taskbar
   └─ .work-surface              ← PlanExecutePanel
      ├─ .plan-card
      └─ .exec-card …
```

### 4.3 Context sidebar (우측)

```
.context-sidebar
├─ .context-sidebar__head       "Context"
├─ .ctx-tabs                    Overview | Tasks | Inbox
└─ .context-sidebar__body
   ├─ [overview] ctx-goal, ctx-plan, ctx-layers (read-only), ctx-team
   ├─ [tasks]    ctx-objection*, task-row (summary)
   └─ [inbox]    HumanInboxPanel + NotificationCenter
```

### 4.4 Shell (App)

```
.app
├─ .titlebar                    sidebar | topic | meta | inbox? | agents | context-toggle | theme
└─ .shell
   ├─ .rail
   └─ .pane
      └─ RoomChat | SettingsPage
```

---

## 5. 구현 순서 (권장)

| Phase | 내용 | 산출 |
|-------|------|------|
| **P0** ✅ | Inspector IA → Overview/Tasks/Inbox, RoomTaskBar를 `taskbar-dock`으로 이동 | `ContextOverviewPanel`, `workspaceTabs.ts` |
| **P1** | SessionList avatar/dir, Transcript presentation UI, Artifacts/Run visual | `SessionList.tsx`, `RoomChat` view-options |
| **P2** | NewSessionDialog, titlebar Inbox, Quick 탭 제거 → Settings | `NewSessionDialog.tsx`, `App.tsx` |
| **P3** ✅ | Classic mode·ChatToolbar 삭제, `legacy-bridge.css` → `layout.css` merge | dual-class TSX rename remains cosmetic |
| **P4** ✅ | Context layer toggle | `context_layers.py` router + `ContextLayerBars` in Overview |

---

## 6. 검증 체크리스트 (IA 완료 정의)

- [x] Inspector 3탭: Overview / Tasks / Inbox — 프로토타입 `ContextSidebar`와 동일 라벨
- [x] RoomTaskBar가 Transcript·Work **본문 sticky**에만 존재 (Inspector Tasks는 jump 가능한 요약 queue만 유지)
- [x] Inbox가 단일 피드 + segment (`All | Activity | Questions | Build`)로 Human Inbox와 Activity를 흡수
- [ ] ⌘N → New Session modal (또는 명시적 product decision 문서화)
- [x] Classic / `RunPanel` / `SessionViewer` / `mode` state **없음**
- [x] `main.tsx` CSS import 8개: tokens, base, layout, surfaces, plan-execute, overlays, tweaks, prototype-panels (orphan `app.css` 체인 0)
- [ ] `03-BEHAVIOR-CONTRACT.md` 체크리스트 전항목 통과

---

## 7. 파일 인덱스

| 역할 | 경로 |
|------|------|
| App 셸·라우팅 | `web/src/App.tsx` |
| 워크스페이스·Inspector 탭 enum | `web/src/utils/workspaceTabs.ts` |
| 메인 워크스페이스 | `web/src/components/RoomChat.tsx` |
| 우측 패널 chrome | `web/src/components/InspectorPane.tsx` |
| Floating taskbar | `web/src/components/RoomTaskBar.tsx` |
| Plan execute | `web/src/components/PlanExecutePanel.tsx` |
| CSS canonical | `web/src/styles/{tokens,base,layout,surfaces,plan-execute}.css` |
| 갭 추적 | [UI-MIGRATION-GAPS.md](UI-MIGRATION-GAPS.md) |
