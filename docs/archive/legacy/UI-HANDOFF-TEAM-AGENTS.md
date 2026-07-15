# UI 핸드오프 — Claude Code Agent Teams 패턴 (agent-lab Room)

**대상:** UI 담당 에이전트  
**범위:** 멀티 에이전트 룸의 팀 조율(Phase 1–3) + Sprint A/B/C/D  
**백엔드·동작 근거:** [`STABILITY.md`](../../STABILITY.md), [`SPRINT-D-CHECKLIST.md`](./SPRINT-D-CHECKLIST.md)

이 문서는 **이미 코드에 들어간 UI**와 **UI 담당이 맞춰야 할 동작·검증·폴리시**를 구분합니다. 새 API 설계나 워크플로 엔진은 범위 밖입니다.

---

## 1. 제품 목표 (UI 관점)

Human이 3자 룸(Cursor / Codex / Claude)에서:

1. **토론** — 에이전트 말풍선·동료 채널·요약 뷰로 맥락 조절  
2. **작업 보드** — `[PROPOSED:]` → 공유 task, 리드·청구·합의 게이트  
3. **plan + execute** — `plan.md` 액션 dry-run → Human 승인 → task 상태 연동  
4. **Plan workflow (Merge Verified)** — plan mode send → inbox clarify → scribe → peer review → **Plan 승인** panel → execute  
5. **신뢰 신호** — 모드·영수증·차단 사유·plan↔task↔execution 한 줄로 “지금 뭐가 막혔는지” 표시  

아키텍처는 **단일 오케스트레이터** (멀티 프로세스 Teams UI 아님).

---

## 2. 화면 구조 (Room 탭)

```
┌─────────────────────────────────────────────────────────────┐
│ Header: 세션 제목 · 탭 [채팅 | plan] · Human요약/동료채널 토글 │
├─────────────────────────────────────────────────────────────┤
│ RoomTaskBar — 작업 · 이번 턴 리드 · 리드 select · 청구 가능    │
│             · 합의 blocker · plan↔task↔execution 푸터        │
├─────────────────────────────────────────────────────────────┤
│ Chat scroll (말풍선 / 턴요약 / peer 스타일)                  │
├─────────────────────────────────────────────────────────────┤
│ clarifier-banner (조건부)                                    │
├─────────────────────────────────────────────────────────────┤
│ send-receipt chip (전송 후 잠깐)                             │
├─────────────────────────────────────────────────────────────┤
│ ChatComposer — mode chip · turn picker · plan toggle · 전송  │
└─────────────────────────────────────────────────────────────┘

plan 탭: PlanExecutePanel — 액션 카드 · pending plan 스냅샷 · dry-run · 승인
```

**주 파일**

| 영역 | 파일 |
|------|------|
| 룸 셸 | `web/src/components/RoomChat.tsx` |
| 작업 바 | `web/src/components/RoomTaskBar.tsx` |
| plan 실행 | `web/src/components/PlanExecutePanel.tsx` |
| 입력 | `web/src/components/ChatComposer.tsx`, `ComposerTurnPicker.tsx` |
| chat 파싱 | `web/src/utils/transcript.ts` |
| API 타입 | `web/src/api/client.ts` |
| 스타일 | `web/src/styles/` (`.taskbar`, `.taskbar-dock`, `.taskbar__*`, `.composer-mode-chip`, `.clarifier-banner`, `.chat-line--synthesis`, `.chat-line--peer`) |

---

## 3. 기능 ↔ UI 매트릭스

### Phase 1 — tasks + channels

| 기능 | Human이 보는 것 | UI 구현 상태 | UI 담당 액션 |
|------|-----------------|-------------|--------------|
| `tasks[]` | **작업** 바, 상태 칩, owner | ✅ `RoomTaskBar` | 빈 상태·로딩·에러 토스트 정리 |
| `visibility: peer` | **동료 채널** 체크박스, peer 말풍선 스타일 | ✅ `RoomChat` + `transcript.ts` | 기본 OFF 유지, 카운트 `(N)` 가독성 |
| claim API | (에이전트 주도; Human은 owner 확인) | ✅ claimable 행 `task-row--claimable` 강조 | — |

### Phase 2 — lead + assign

| 기능 | Human이 보는 것 | UI 구현 상태 | UI 담당 액션 |
|------|-----------------|-------------|--------------|
| `team_lead` | 리드 `<select>` + PATCH | ✅ | 세션 리드 vs **이번 턴 리드** 문구 혼동 방지 (툴팁) |
| pre-round assign | task `owner_agent` | ✅ TaskRows | discuss 턴 후 owner 비어 있음 = **정상** (안내 1줄) |
| envelope consensus | (채팅 본문) | ✅ 기존 envelope UI | 변경 최소 |

### Phase 3 — board + execute + consensus

| 기능 | Human이 보는 것 | UI 구현 상태 | UI 담당 액션 |
|------|-----------------|-------------|--------------|
| plan #N ↔ task | **plan #N** 버튼, plan 탭 scroll | ✅ | 포커스 링·스크롤 애니 일관성 |
| execute → task 완료 | task **완료** / 상태 | ✅ | — |
| consensus task gate | blocker 배너 | ✅ `consensus_task_blockers` | 문구 shorten, 링크 to task id |
| manual **완료** | 버튼 disabled + hint | ✅ `taskCompleteGate` | API **409** 시 에러 메시지 노출 확인 |

### Sprint A

| 기능 | UI |
|------|-----|
| task ↔ plan 패널 링크 | ✅ `PlanExecutePanel` **연결 작업**, `data-plan-action-index` / `data-task-id` |
| 완료 차단 (execute 미검증) | ✅ hint: `plan 실행 승인 대기` / `검증 미완료` |

### Sprint B

| 기능 | UI |
|------|-----|
| `pending_plans[]` | ✅ 스냅샷 배너 → 승인 → dry-run (`PlanExecutePanel`) |
| task `in_progress` | ✅ 작업 바 상태 |
| `409 plan_snapshot_required` | ✅ `PlanSnapshotRequiredError` → 스냅샷 UI |

### Sprint C

| 기능 | UI |
|------|-----|
| **Human 요약** (기본 ON) | ✅ 체크박스; user + `[human synthesis — 턴 요약]` 만 |
| **동료 채널** | ✅ Human 요약 ON 시 disabled |
| 턴별 리드 (`GO codex`) | △ 백엔드만; **이번 턴 리드**는 D1에서 표시 |
| 턴 요약 말풍선 | ✅ `chat-line--synthesis`, 라벨 **턴 요약** |

### Sprint D

| ID | 기능 | UI |
|----|------|-----|
| D1 | `turn_leads` | ✅ **이번 턴 리드** + `T{n}→agent` chips |
| D6 | 모드 chip | ✅ `composer-mode-chip`: 토론 / 정리·plan / 합의 |
| D7 | plan↔task↔execution | ✅ 작업 바 푸터 한 줄 |
| D9 | Clarifier | ✅ `clarifier-banner` (`AGENT_LAB_CLARIFIER=1`) |
| D11 | `send_receipt` | ✅ SSE → composer 위 칩 (~5s) |
| D4 | plan provenance | ✅ `PlanProvenanceFooter` + plan ref 클릭 → Transcript scroll/highlight |

---

## 4. API · SSE 계약 (UI가 알아야 할 것)

### REST

| Method | Path | UI 사용처 |
|--------|------|-----------|
| GET | `/api/sessions/{id}/tasks` | `RoomTaskBar` payload |
| PATCH | `/api/sessions/{id}/team-lead` | 리드 select |
| POST | `/api/sessions/{id}/tasks/{task_id}/complete` | **완료** — **409** + `detail` 처리 필수 |
| POST | `/api/sessions/{id}/tasks/{task_id}/claim` | (에이전트; Human UI 없음) |
| GET/POST | `.../execute/pending-plans[...]` | `PlanExecutePanel` |

`RoomTasksPayload` (`client.ts`):

- `team_lead`, `turn_leads?: Record<string,string>` (키 = human turn 번호 문자열)
- `tasks`, `claimable`, `counts`
- `consensus_tasks_ready`, `consensus_task_blockers[]`

### Room run SSE (`RoomChat`)

| 이벤트 | UI 동작 |
|--------|---------|
| `clarifier_prompt` | `questions[]` → 배너; **에이전트 라운드 스킵** — Human이 보강 입력 |
| `complete` | `send_receipt?: "discuss_saved" \| "plan_updated" \| "consensus_done"` |
| `plan_actions_validation` | (기존) plan 품질 이슈 |
| `consensus_dry_run_proposal` | (기존) execute 제안 게이트 |

### chat.jsonl → UI

| 필드 | `transcript.ts` |
|------|-----------------|
| `visibility: "peer"` | `peerChannel: true`, 기본 숨김 |
| system + `[human synthesis` | `humanSynthesis: true`, 라벨 **턴 요약** |
| `envelope` | 기존 agent 말풍선 메타 |

---

## 5. 사용자 플로우 (QA 시나리오)

UI 담당은 아래를 **수동 스모크** 체크리스트로 사용.

### A. 토론-only

1. 새 세션, **plan after send OFF**, consensus OFF → mode chip **토론**
2. 전송 → 에이전트 응답 → receipt `discuss_saved`
3. **Human 요약** ON → 에이전트 말풍선 숨김, **턴 요약**만 보임
4. **작업** 바: `[PROPOSED:]` harvest 되나 **청구 가능**만 (discuss는 assign 없음)
5. **동료 채널** ON → peer/digest 보임

### B. plan 정리

1. **plan after send ON** (New Session: Plan workflow 체크 기본 ON) → chip **정리·plan**, receipt `plan_updated`
2. plan 탭 → `## 지금 실행` 액션 선택

### B2. Plan workflow (Merge Verified)

1. plan mode send → `plan_workflow.phase=CLARIFY` (inbox MCP 질문 가능)
2. Inbox resolve → CLARIFY→DRAFT (별도 채팅 없이 phase advance)
3. Scribe + peer review → Tasks inspector **Plan 승인** panel (`PlanApprovalPanel`)
4. Action cards + open objections 표시; Approve → `POST /plan/approve`
5. Work runtime `work_phase=review_needed` at HUMAN_PENDING; `execute_pending` after APPROVED
6. Legacy: `VerifiedLoopBanner` / `GoalLoopBanner` / Composer **verified** profile 숨김 (`plan_workflow.enabled`)

### C. execute + task

1. dry-run → **plan 스냅샷 승인** (첫 dry-run) → diff 승인
2. 작업 바: task **진행**; 푸터 `plan #N ↔ t-… ↔ pending_approval`
3. **완료** 클릭 → 409 + hint (검증 전)
4. execute approve (verified) → task **완료**

### D. 리드 · 합의

1. 메시지에 `GO codex` → **이번 턴 리드** codex, `T1→codex` chip
2. consensus ON → blocker 배너 → ENDORSE 후 해소
3. receipt `consensus_done`

### E. Clarifier (dev only)

1. API env `AGENT_LAB_CLARIFIER=1`, 짧은 첫 메시지
2. `clarifier-banner` 표시, 에이전트 미호출
3. 보강 후 재전송

---

## 6. UI 담당 권장 작업 (폴리시·미완)

백엔드는 동작합니다. **아래는 UX/시각·일관성** 중심입니다.

### P0 — 혼동 제거

- [x] **objection resolve discoverability**: dry-run 409 `open_objection`을 Composer/plan 인라인 알림으로 표시하고 **이의 해결** CTA가 TaskBar 항목으로 이동
- [x] **plan BLOCK visibility**: selected plan action에 open BLOCK이 있으면 PlanExecutePanel에서 execute 차단 배너 표시
- [x] **세션 리드 vs 이번 턴 리드**: `RoomTaskBar`에 짧은 설명 또는 `?` 툴팁 (“세션 리드 select는 기본값; 이번 턴은 메시지 `GO codex` 또는 자동 회전”)
- [x] **409 complete**: `markComplete` catch 시 서버 `detail` 문자열을 toast/인라인으로 표시 (현재 silent ignore 가능)
- [x] **Human 요약 + 동료 채널**: disabled 상태 시 왜 꺼졌는지 `title` 속성
- [x] **discuss 턴 빈 owner**: 작업 바 empty hint에 “토론 턴은 자동 배정 없음 — plan/합의 턴에서 배정” 추가

### P1 — 정보 밀도·내비

- [x] **plan provenance**: plan.md 내 `(ref: chat.jsonl#L12)` 링크 스타일·hover·클릭 시 chat 스크롤 하이라이트 (`RoomChat` `onRefClick` / `data-chat-line-index`)
- [x] **cross-link 푸터**: 5건 cap → “+N more” (`buildTaskCrossLinks` + `taskbar__cross-links`)
- [x] **send_receipt** 한글 라벨 매핑 테이블을 `sendReceiptLabel` 한곳에 문서화 (`web/src/utils/sendReceipt.ts`)
- [x] **mode chip** + `ComposerTurnPicker` / `planAfterSend` / consensus 토글 **상호 배타** 시각 (동시에 켜진 것처럼 보이지 않게)

### P2 — 시각·a11y·Figma

- [x] `docs/04-multi-agent-room.md` §5 Figma 토큰과 `.taskbar`, `.chat-line--synthesis`, `.clarifier-banner` 대조
- [x] `role="region"` / `aria-label` on 작업 바·배너 점검
- [x] narrow width(Tauri)에서 작업 바 head 줄바꿈

### 하지 말 것 (UI)

- `peer.jsonl` / 별도 tasks 파일 UI
- 멀티 창 teammate 프로세스 UI
- YAML 워크플로 편집기 (01 문서 Phase 3 — 별도 로드맵)

---

## 7. 컴포넌트 props 체크리스트

### `RoomChat` → 자식

| Prop / state | 용도 |
|--------------|------|
| `showHumanSynthesis` | Human 요약 필터 |
| `showPeerChannel` | peer 표시 |
| `clarifierQuestions` | D9 배너 |
| `sendReceipt` | D11 칩 |
| `composerModeChip` | D6 → `ChatComposer.modeChip` |
| `RoomTaskBar` | `executions` from plan hook, `onFocusPlanAction` → plan 탭 |

### `RoomTaskBar`

| 입력 | 필수 |
|------|------|
| `payload: RoomTasksPayload` | GET tasks 후 |
| `executions` | cross-link · complete gate |
| `onFocusPlanAction(index)` | plan 탭 전환 + scroll |
| `focusObjection` | objection resolve CTA에서 TaskBar 항목 scroll/focus |

### `PlanExecutePanel`

| 입력 | 필수 |
|------|------|
| `linkedTasks` | 연결 작업 버튼 |
| `onFocusTask(taskId)` | → chat `data-task-id` scroll |
| `onFocusObjection(objectionId)` | → TaskBar objection resolve 위치 |
| `onChatRefClick(line)` | provenance |

---

## 8. 스타일 훅 (검색용)

```css
.taskbar, .taskbar__turn-leads-history, .taskbar__cross-links
.room-peer-toggle, .chat-line--peer, .chat-line--synthesis
.mode-chip, .clarifier-banner
.plan-card__linked-task, .plan-execute-plan-snapshot (스냅샷 배너)
```

에이전트 색: `web/src/styles/tokens.css` — Cursor / Codex / Claude.

---

## 9. 환경·디버그

| 변수 | UI 영향 |
|------|---------|
| `AGENT_LAB_CLARIFIER=1` | Clarifier 배너 경로 활성 |
| `VITE_ROOM_LONG_RUN_HINT_MS` | 장시간 run 힌트 (기존) |
| API `8765` / Tauri | `client.ts` `apiBase()` |

로컬: `make dev` → Room 세션 열기 → 위 §5 시나리오.

---

## 10. 완료 정의 (UI 담당)

- [x] §5 시나리오 A–E 스모크 통과 — `tests/test_ui_handoff_scenarios.py` (2026-06-14)
- [x] §6 P0 체크 4항목 이상 반영
- [x] `npm run build` 통과
- [ ] 회귀: 기존 plan execute·consensus·단일 에이전트 채팅 깨지지 않음 (수동 `make dev` 권장)

---

## 11. 참고 문서

| 문서 | 내용 |
|------|------|
| [`STABILITY.md`](../../STABILITY.md) | Phase 1–3, Sprint A–D 동작·Verify |
| [`SPRINT-D-CHECKLIST.md`](./SPRINT-D-CHECKLIST.md) | D1–D11 구현 체크 |
| [`04-multi-agent-room.md`](./04-multi-agent-room.md) | 룸 제품 개요·Figma |
| [`05-room-agent-roles.md`](./05-room-agent-roles.md) | 3자 역할 (카피 참고) |

**문의 시 백엔드 담당:** `src/agent_lab/room.py`, `room_tasks.py`, `room_team_orchestration.py`, `plan_execute.py`, `plan_pending.py`, `app/server/main.py`
