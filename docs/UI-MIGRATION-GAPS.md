# UI 마이그레이션 — 미구현 · 동작 불가 정리

> **Tier 3 (cosmetic IA)** — does not block Room · execute · hooks. **Status:** [docs/README.md](./README.md)  
> **Conflict rule:** When this doc disagrees with code or contract tests, **code wins** (e.g. `session-item` not `session-row`).

> 디자인 SSOT: `~/Downloads/agent-lab/project/Agent Lab.html`  
> 구현 대상: `web/src/` (React + Vite + FastAPI)  
> 원칙: **로직·API 계약 불변**, **프레젠테이션만** 프로토타입 클래스/IA에 맞춤

마지막 업데이트: 2026-06-07

---

## 1. 완료된 마이그레이션 (요약)

| 영역 | 상태 |
|------|------|
| CSS 스택 | `tokens → base → layout → surfaces → plan-execute → layout-extensions → legacy-bridge → satellites` |
| App 셸 | `.app` / `.shell` / `.pane` / `.rail__*` + 단일 `MacTitlebar` (`TitlebarSlotsContext`) |
| 리프 컴포넌트 | Avatar, SessionRail, SessionList, ChatComposer, WorkspaceTabBar, PlanActionCard 등 |
| Settings | `settings-section*` dual-class + `layout-extensions.css` |
| Inspector | `context-sidebar` + `ctx-tabs` dual-class (탭 IA는 아래 §3 유지) |
| Taskbar | `taskbar` + `room-task-bar` dual-class root |
| Plan execute | `work-surface` + `plan-execute-panel` dual-class root |
| Transcript | `turn` + `chat-turn` dual-class |
| 위성 UI CSS | `satellites.css` (구 `app.css` 스택에서 추출) |

---

## 2. UI 구조 미구현 — 기능이 제대로 안 되거나 UX가 어긋나는 부분

### 2.1 프로토타입 IA와 다른 탭 구조 (의도적 생산 확장 + 미매핑)

| 프로토타입 | 현재 앱 | 영향 |
|-----------|---------|------|
| Context sidebar: **Overview / Tasks / Inbox** | Inspector: **Tasks / Activity / Quick** | Overview(목표·다음 plan step·context layers·팀 health 한 화면) **없음**. 정보가 Settings·Taskbar·Tasks 탭에 **분산** |
| Settings의 Context layer **토글** | `ContextPreviewPanel` (API 읽기 전용) | 레이어 on/off **UI 없음** — 서버에 토글 API도 없음 |
| Run 탭 mock `RunLog` | `TurnRunPanel` + SSE | **동작함**. 비주얼만 프로토타입 run log와 다름 |
| Artifacts mock `artifact-card` | `workspace-artifacts-list` | **동작함**. 카드 레이아웃 다름 |

**체감 증상:** 프로토타입 우측 패널 “Overview”에 있던 goal + next step + layers + team이 한곳에 안 모임.

---

### 2.2 프로토타입에만 있는 UI (앱에 대응 기능 없음)

| 프로토타입 | 상태 |
|-----------|------|
| `TweaksPanel` (accent, density, gate variant, simulate objection) | **미구현** — 디자인 QA용. `ThemeToggle`만 제공 |
| `NewSessionDialog` (`ns-modal`) | **미구현** — 앱은 `composerNew` + `SessionSetupBar` 인라인 플로우 |
| Titlebar **Inbox** 버튼 | **미구현** — Human inbox는 Taskbar/Inspector Tasks에만 |
| Context layer **switch** (repo tree 등) | **mock only** — 토글해도 서버 상태 변경 없음 |

---

### 2.3 생산 전용 UI (프로토타입에 없음 — 디자인 미적용)

아래는 **로직은 동작**하나 프로토타입 HTML/CSS에 **1:1 마크업이 없어** `satellites.css` + legacy 클래스로 스타일링:

- `WorkPanel` / `WorkStatusBar` / `PlanTabToolbar` / `PlanMetaBar`
- `ExecuteQueueBar` / `ConsensusDryRunGateBar`
- `CommandPalette` (⌘K)
- `NotificationCenter` + `MacNotificationHost`
- `AgentPermissionAlert` / `MacAlert`
- `SessionSetupBar` / `AgentSessionSettings` (Settings 내 grid는 prototype `agent-settings`와 부분 일치)
- `RunPanel` / `SessionViewer` (classic 모드)
- `SlashCommandMenu` / `CollapsibleGlassPanel`
- `ScrollToBottomButton` / `ComposerPreflightBar`

**체감 증상:** classic 모드, ⌘K 팔레트, 알림 센터 등은 **새 디자인 토큰은 쓰지만** 프로토타입 스크린샷과 **픽셀 일치 불가**.

---

### 2.4 거대 컨테이너 — dual-class + bridge (canonical rename 미완)

TSX 내부 클래스는 **아직 legacy 이름**이 대부분. 루트만 canonical 추가:

| 파일 | 루트 dual-class | 내부 |
|------|----------------|------|
| `RoomTaskBar.tsx` | `taskbar` | `room-task-bar__*` 전부 (~880줄) |
| `PlanExecutePanel.tsx` | `work-surface` | `plan-execute-*`, `room-plan-btn` |
| `RoomChat.tsx` | — | `room-workspace-shell`, `messages-scroll`, `view-options-*` |
| `ChatBubble.tsx` | `turn` | `chat-turn__*`, `mac-bubble__*` |

**체감 증상:** 없음(bridge가 스타일). 유지보수 시 **클래스 두 벌** 혼재.

---

### 2.5 API/백엔드 없이 UI만 있는 프로토타입 동작

프로토타입 `planexec.jsx` / `main.jsx`의 `alert()` 핸들러 — **앱에서는 실 API** (`usePlanExecute`, execute gate).  
아래는 프로토타입 버튼은 있으나 **앱에서 다른 진입점**이거나 **조건부로만** 보임:

| UX | 앱 |
|----|-----|
| Plan approve → alert | `PlanExecutePanel` → `approve()` + 409 gate |
| Objection resolve in sidebar | Taskbar + `resolveSessionObjection` |
| Settings save hint (timeout) | `patchSessionAgentCapabilities` |

---

## 3. 알려진 시각/레이아웃 갭 (기능은 됨)

1. **Shell 3-column** — 프로토타입은 `.shell { grid: rail | pane | context-sidebar }`. 앱은 context sidebar가 `RoomChat` 내부 flex. 접힘/리사이즈 **동작은 함**, grid 구조만 다름.
2. **Taskbar 탭 IA** — 프로토타입 `Overview/Tasks/Inbox` vs 앱 `all/unassigned` + objections/mailbox/artifacts **섹션**. 탭 라벨·개수 badge 스타일은 `layout-extensions`에 추가됨.
3. **Transcript presentation** — 프로토타입 `transcript--console|bubble|compact` vs 앱 `transcriptViewPrefs`. Console/bubble **부분** bridge.
4. **Session list row** — prototype `session-item__agents` Avatar strip; 앱 `SessionList`는 subtitle 문자열 위주 (avatar strip **미구현**).
5. **Rail session counts** — active/archive **동시 count**는 API가 탭별 fetch라 한 탭에만 badge (프로토타입은 mock 전체 배열).

---

## 4. 검증

```bash
cd web && npm run build
pytest tests/test_liquid_glass_scope_contract.py -q
make dev   # http://localhost:5173 + API 8765
```

---

## 5. 후속 작업 (선택, cosmetic)

1. `RoomTaskBar` / `PlanExecutePanel` / `RoomChat` **내부** legacy class → canonical 일괄 rename (bridge 제거)
2. Inspector IA를 prototype **Overview/Tasks/Inbox**로 맞출지, Activity/Quick을 유지할지 **제품 결정**
3. `SessionList`에 agent Avatar strip + dir/branch (prototype `session-item__sub`)
4. `NewSessionDialog` vs inline setup — IA 통일
5. Classic / RunPanel / SessionViewer deprecate 또는 별도 “legacy theme”

---

## 6. 파일 참조

| 문서 | 경로 |
|------|------|
| 보존 매니페스트 | `~/Downloads/agent-lab/project/uploads/01-PRESERVE-MANIFEST.md` |
| IA 맵 | `~/Downloads/agent-lab/project/uploads/02-LAYOUT-IA-MAP.md` |
| 행동 계약 | `~/Downloads/agent-lab/project/uploads/03-BEHAVIOR-CONTRACT.md` |
| Port README | `~/Downloads/agent-lab/project/port/README.md` |
