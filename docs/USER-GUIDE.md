# Agent Lab 기능·동작 명세 (USER-GUIDE)

> **Canonical product spec (Tier 1).** Doc index: [docs/README.md](./README.md) · Shipped matrix: [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md)

> **목적:** UI/UX를 전면 재설계할 때 참고하는 **기능·로직·상태** 문서  
> **대상:** 제품·디자인·프론트·백엔드 개발자  
> **기준 코드:** `main` 브랜치 — `web/src/`, `src/agent_lab/`  
> **관련 설계:** [WORK-TAB-IA.md](./WORK-TAB-IA.md) · [HUMAN-INBOX.md](./HUMAN-INBOX.md) · [04-multi-agent-room.md](./04-multi-agent-room.md) · [GOAL-LOOP.md](./GOAL-LOOP.md) · [EXECUTE-WORKTREE-REFORM.md](./EXECUTE-WORKTREE-REFORM.md)

---

## 이 문서의 범위

| 포함 | 제외(별도 문서) |
|------|-----------------|
| 사용자가 **무엇을 할 수 있는지** | 픽셀·컴포넌트 CSS 상세 |
| **언제** UI/백엔드가 바뀌는지 (게이트·조건) | Figma 시안 |
| **데이터**가 어디에 저장되는지 | quant-pipeline 운영 런북 |
| 현재 IA와 **알려진 UI drift** | 완전한 OpenAPI 스펙 |

**Human(사용자)** 은 방향·승인·결정을 하고, 에이전트끼리 맞추도록 설계되어 있다. Human에게 A/B 선택지만 넘기지 않는다.

---

## 목차

1. [개요](#1-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [설치·실행·설정](#3-설치실행설정)
4. [정보 구조(IA)](#4-정보-구조ia)
5. [세션 생명주기](#5-세션-생명주기)
6. [Composer·메시지 전송](#6-composermessage-전송)
7. [Room 턴 오케스트레이션](#7-room-턴-오케스트레이션)
8. [Transcript](#8-transcript)
9. [Work surface (plan + execute)](#9-work-surface-plan--execute)
10. [Tasks·합의·이의·산출물](#10-tasks합의이의산출물)
11. [Human Inbox](#11-human-inbox)
12. [Goal Loop](#12-goal-loop)
13. [Context·효율·에이전트 역량](#13-context효율에이전트-역량)
14. [Plugins·슬래시 명령](#14-plugins슬래시-명령)
15. [Run 탭](#15-run-탭)
16. [Artifacts 탭](#16-artifacts-탭)
17. [Settings·Health·진단](#17-settingshealth진단)
18. [Workbench (Overview / Tasks / Inbox / Tools)](#18-workbench-overview--tasks--inbox--tools)
19. [알림·SSE·스트리밍](#19-알림sse스트리밍)
20. [키보드·상태 유지(localStorage)](#20-키보드상태-유지localstorage)
21. [REST API 개요](#21-rest-api-개요)
22. [환경 변수](#22-환경-변수)
23. [Classic 모드 (레거시)](#23-classic-모드-레거시)
24. [CLI](#24-cli)
25. [문제 해결](#25-문제-해결)
26. [용어 사전](#26-용어-사전)
27. [UI 재설계 시 알려진 gap](#27-ui-재설계-시-알려진-gap)

---

## 1. 개요

### 1.1 Agent Lab이란

**Agent Lab**은 주제(질문·기획·조사·코드 작업)를 던지면 **세 명의 AI 에이전트(Cursor · Codex · Claude)** 가 협업하고, 대화를 **`plan.md`** 로 정리하며, 필요 시 **코드 변경을 dry-run → Human 승인 → merge**까지 이어가는 **개발자용 에이전트 콘솔**이다.

| 축 | 설명 |
|----|------|
| **토론** | 3자 Room — 병렬·순차·합의 라운드 |
| **기록** | `chat.jsonl` (원문) + Transcript UI |
| **정리** | Scribe → `plan.md` |
| **실행** | plan `## 지금 실행` → worktree dry-run → diff 승인 |
| **추적** | Tasks · endorsements · objections · executions |

### 1.2 세 에이전트 역할

| 에이전트 | 한 줄 역할 | 잘 맡기는 일 |
|----------|------------|--------------|
| **Cursor** | 레포를 직접 보고 **파일·UI·빌드·패치** | “이 버그 왜?” “패치 방법” execute |
| **Codex** | **쪼개기·순서·검증·완료 기준** | 테스트 플랜, 원인 추적, decompose |
| **Claude** | **맹점·리스크·설명** — 두 번째 의견 | 설계 검토, 요약, Oracle(선택) |

역할 프롬프트: `src/agent_lab/agents/prompts.py`  
상세: [05-room-agent-roles.md](./05-room-agent-roles.md)

### 1.3 quant-pipeline과의 관계

| quant-pipeline | Agent Lab |
|----------------|-----------|
| DB, 백테스트, 실거래 | 없음 (기본) |
| TASK · pytest · Handoff | PLAN · 토론 · 문서화 |
| 프로덕션 실행 | **기획·토론·execute gate·검증 루프** (pipeline 대체 아님) |

`plan.md`를 Human이 검토한 뒤 pipeline의 `TASK-*.md`로 옮길 수 있다. Agent Lab이 pipeline을 **대신 실행하지는 않는다**.

### 1.4 핵심 개념

| 용어 | 정의 |
|------|------|
| **Session** | 주제 하나 = 디스크 폴더 하나 |
| **Turn / 턴** | Human 메시지 1회 + 그에 대한 에이전트 라운드 전체 |
| **Round / 라운드** | 같은 턴 안 에이전트 웨이브 (R1, R2, …) |
| **Room** | Cursor + Codex + Claude 병렬·순차 토론 (기본 워크플로) |
| **Work** | plan 문서 + execute/review/approval **단일 surface** |
| **Scribe** | `plan.md`를 쓰는 정리 에이전트 (기본 Claude) |
| **Gate** | 조건 충족 전 다음 단계 진행 불가 |

---

## 2. 시스템 아키텍처

### 2.1 스택

| 계층 | 기술 |
|------|------|
| Desktop | Tauri 2 + Rust (`web/src-tauri/`) |
| Frontend | React 18 + Vite (dev **5173**) |
| Backend | FastAPI + uvicorn (**8765**) |
| 에이전트 | Cursor SDK / Codex CLI / Claude CLI |

### 2.2 실행 형태

| 명령 | URL / 결과 |
|------|------------|
| `make dev` | UI `http://127.0.0.1:5173` · API `8765` |
| `make prod` | UI+API 통합 `http://127.0.0.1:8765` |
| `make tauri-dev` | 네이티브 창 (내부 API spawn) |
| `python -m agent_lab run "주제"` | CLI — 같은 `sessions/` 사용 |

### 2.3 데이터 흐름 (한 턴)

```text
Human Composer 전송
    → POST /api/room/runs (SSE)
    → room.py: clarifier? → agent rounds → consensus? → scribe?
    → chat.jsonl + run.json + plan.md 갱신
    → SSE events → web UI (Transcript / Run / Work / Tasks)
```

### 2.4 설정 파일 우선순위

1. `~/.agent-lab/.env` — **권장** (Tauri·GUI)
2. `~/.agent-lab/config.toml` — 경로·포트·로그
3. 프로젝트 루트 `.env` — 개발자 로컬 오버라이드

Tauri/GUI는 PATH가 짧으므로 `CODEX_BIN`, `CLAUDE_BIN` 등 **절대 경로** 권장.

---

## 3. 설치·실행·설정

### 3.1 필요 환경

| 항목 | 설명 |
|------|------|
| macOS (권장) | Tauri 기준; 브라우저만도 가능 |
| Python 3.11+ | 백엔드 |
| Node 18+ | 웹 UI |
| Rust | Tauri 빌드 시 |
| 에이전트 인증 | 아래 표 |

| 에이전트 | 준비 |
|----------|------|
| Codex | `codex login` |
| Claude | `claude login` |
| Cursor | `CURSOR_API_KEY` + `pip install -e ".[cursor]"` |

### 3.2 최초 설치

```bash
cd ~/Projects/agent-lab
make install
mkdir -p ~/.agent-lab
cp .env.example ~/.agent-lab/.env
```

### 3.3 `.env` 예시

```env
AGENT_LAB_PROVIDER=codex
CODEX_BIN=/full/path/to/codex
CLAUDE_BIN=/full/path/to/claude
CURSOR_API_KEY=your_key_here

# 선택 기능
AGENT_LAB_GOAL_LOOP=1
# AGENT_LAB_CLARIFIER=1
# AGENT_LAB_CLARIFIER_MIN_CHARS=48
# AGENT_LAB_EFFICIENCY=1
```

전체 목록: [§22 환경 변수](#22-환경-변수)

---

## 4. 정보 구조(IA)

> **설계 의도:** Plan 탭과 Review 탭을 **Work** 하나로 합친다. 사용자는 “어느 탭?”이 아니라 **작업 단계**를 본다. ([WORK-TAB-IA.md](./WORK-TAB-IA.md))

### 4.1 앱 셸 (Room 모드)

```text
┌─────────────────┬──────────────────────────────────┬─────────────────┐
│ Session rail    │ Transcript + taskbar-dock           │ Workbench       │
│ (세션 목록)     │ Composer (하단)                     │ Overview/Tasks/ │
│ Health chip     │                                     │ Inbox/Tools     │
└─────────────────┴──────────────────────────────────┴─────────────────┘
```

**Workbench Tools** (`rightPanelMode`): `plan`(WorkToolPanel + execute), `background`, `diff`, `files`, `preview`, `terminal`.

별도 **Settings 페이지** (`shellView === "settings"`) — Context 미리보기·에이전트 cwd·Plugin·진단.

**Classic 모드:** 레거시 Planner→Critic→Scribe (`RunPanel` / `SessionViewer`). Room이 기본·권장.

### 4.2 Workspace · Tools 탭

| ID | 라벨 | 단축키 | 역할 |
|----|------|--------|------|
| `transcript` | Transcript | ⌘1 | Human·에이전트 대화 전체 |
| `plan` | Plan | ⌘2 | `WorkToolPanel` — plan + execute/review/approval |
| `background` | Background | ⌘3 | 백그라운드 태스크 |
| `diff` | Diff | ⌘4 | execute diff |
| `files` | Files | ⌘5 | workspace files · Monaco |
| `preview` | Preview | ⌘6 | dev preview |
| `terminal` | Terminal | ⌘7 | xterm |

레거시 alias: `work` / `review` / `artifacts` → `plan`, `run` → `background`, `chat` → `transcript`.

### 4.3 Work 내부 단계 (stepper)

`WorkStatusBar` — 5단계 stepper:

```text
Plan → Review → Execute → Verify → Done
```

| Resolver | 우선순위 | 역할 |
|----------|----------|------|
| `GET /api/sessions/{id}/runtime` → `work_phase` | **최우선** (`WorkToolPanel` / `WorkStatusBar`) | Python SSOT [`work_phase.py`](../src/agent_lab/runtime/work_phase.py) |
| `resolveWorkPhaseFromMission()` | runtime 없을 때, 미션 `phase` 매핑 | Layer 6 FSM → stepper |
| `resolveWorkPhase()` | mission 매핑 `null`일 때 fallback | plan · execution · Oracle에서 **5상태** 파생 (`done`·`merge_verify` 포함) |

| Phase | 조건 (파생) | 강조 UI |
|-------|-------------|---------|
| `plan_draft` | plan만 / `MISSION_DEFINE`·`PLAN_GATE`·`DISCUSS` | Plan 문서 · 「지금 정리」 |
| `review_needed` | consensus / dry-run / `MERGE_REVIEW`·`PLAN_REJECT` | ConsensusDryRunGateBar |
| `execute_pending` | pending execution / `EXECUTE_QUEUE`·`DRY_RUN`·`REPAIR` | ExecuteQueueBar + PlanExecutePanel |
| `merge_verify` | merged·review_required·oracle pending / `VERIFY` | PlanExecutePanel · Oracle 배지 |
| `done` | Oracle pass + completed / `MISSION_DONE` | 완료 표시 |

**미션 일시정지:** `MISSION_PAUSED`이면 stepper는 `last_partial.resume_phase` 기준으로 강조하고 **Paused** 배지를 표시합니다. 재개는 Work alert의 「미션 재개」.

### 4.4 Workbench 탭

| ID | 라벨 | 역할 |
|----|------|------|
| `overview` | Overview | ContextOverviewPanel — session · goal · plan meta |
| `tasks` | Tasks | Goal loop · HumanGate · plan approval |
| `inbox` | Inbox | Human Inbox · Discuss Inbox · notifications |
| `tools` | Tools | Workbench tool modes (`plan`, `diff`, `files`, …) |

**Context 미리보기는 Workbench 탭이 아님** — Settings 페이지 Workspace 섹션.

### 4.5 탭 자동 전환 규칙

**Tools 기본 모드** (`resolveDefaultWorkspaceTab`):

1. `hasDryRunDiff` → **diff**
2. `hasPendingExecution` OR `planMd` 비어 있지 않음 → **plan** (WorkToolPanel)
3. else → **transcript**

**Workbench 기본:** blocker 있으면 **tasks**; else **overview**.

**핀(pin) 동작:** 사용자가 탭/모드를 직접 고르면 해당 세션 동안 고정. run 시작/종료는 inspector 쪽만 재평가(Transcript pin 유지).

**프로그램matic 전환 예:**

| 트리거 | 대상 |
|--------|------|
| plan ref 클릭 | transcript + 줄 하이라이트 |
| TaskBar 할 일 클릭 | transcript |
| Human inbox / blocker 알림 | workbench inbox |
| dry-run / plan sync 알림 | tools → plan |
| Bridge 실패 | settings |

### 4.6 Transcript 밖 조건부 strip

Work 탭이 아닐 때:

- `ExecuteQueueBar` (compact) — pending execution 있을 때
- `ConsensusDryRunGateBar` — consensus dry-run proposal 있을 때

---

## 5. 세션 생명주기

### 5.1 새 세션

1. **새 Session** (⌘N)
2. **작업 폴더** (`SessionSetupBar`) — agent-lab / quant-pipeline 프리셋 또는 **다른 폴더…**
3. (선택) Settings에서 에이전트 cwd·툴
4. 에이전트 칩 (Cursor / Codex / Claude)
5. Composer: 주제 + **응답 방식**
6. 전송 → `sessions/YYYY-MM-DD-slug/` 생성

**게이트:** 「다른 폴더…」 선택 후 경로 없으면 전송 불가.

### 5.2 디스크 레이아웃

```text
sessions/2026-06-02-my-topic/
├── topic.txt           # 주제 (매 턴 갱신 가능)
├── chat.jsonl          # 대화 원문 (한 줄 = JSON)
├── plan.md             # Scribe 정리 문서
├── run.json            # 턴 메타·tasks·executions·합의·goal
├── meta.json           # workflow·workspace·template
├── transcript.md       # export용 사람 읽기 로그
├── attachments/        # 첨부 파일
└── artifacts/          # 연구·분업·plan 수집 산출물
```

- **폴더명:** `session.py` — `{date}-{slug}` 충돌 시 `-2`, `-3` …
- **세션 루트:** `AGENT_LAB_SESSIONS_DIR` 또는 `config.toml [paths].sessions`
- **복구:** 앱 기동 시 폴더 스캔

### 5.3 `chat.jsonl`

- 턴 종료 시 **전체 rewrite** (append-only 파일이지만 디스크상 rewrite)
- 필드: `role`, `agent`, `content`, `ts`, `parallel_round`, `envelope`, `visibility`
- 후처리: peer digest, human turn synthesis (조건부)

### 5.4 `run.json` (핵심 필드)

| 필드 | 용도 |
|------|------|
| `turns[]` | 턴별 스냅샷 |
| `tasks[]` | 팀 할 일 |
| `objections[]` | plan execute 이의 |
| `artifacts[]` | 산출물 메타 |
| `executions[]` | plan execute 이력 |
| `pending_plans[]` | plan snapshot 승인 대기 |
| `consensus_agreements` | ♾️ 합의 상태 |
| `team_lead` | 세션 리드 (기본 cursor) |
| `turn_leads` | 턴별 리드 |
| `session_goal` / `goal_loop` | Goal Loop |
| `human_inbox[]` | Human Inbox 항목 |
| `agent_capabilities` | cwd·툴 비대칭 |
| `agent_plugins` | plugin allowlist |
| `completed_steps` | 에이전트 재개용 (턴 내 replay) |

**쓰기 규칙:** `run_meta.patch_run_meta()` — ephemeral 키는 persist 시 strip.

### 5.5 첨부 파일

- 저장: `attachments/` — 최대 20개, 8MiB/파일
- 텍스트류는 본문 inline (24k chars cap)
- Human 메시지에 `describe_attachments()` 주입
- 첨부만 전송 시 topic `[첨부] filename`

### 5.6 세션 관리

| 동작 | API |
|------|-----|
| 검색 | 클라이언트 필터 |
| 이름 변경 | `PATCH /api/sessions/{id}` |
| 보관 / 복원 | archive API |
| 삭제 | 폴더 제거 |

---

## 6. Composer·메시지 전송

### 6.1 UI 요소 (현재)

| 요소 | 동작 |
|------|------|
| **응답 방식** | quick / analyze / specialist / ♾️ |
| **효율** 토글 | context·consensus cap 축소 |
| **에이전트 칩** | 참여 agent pool |
| **모드 힌트** | `composerTurnHint` — 모드·인원·라운드 한 줄 |
| **📎 첨부** | FormData upload |
| **↑ 전송** | Enter (Shift+Enter 줄바꿈) |
| **■ 중지** | `cancelRoomRun` |
| **`/`** | 슬래시 메뉴 |

**plan 갱신 UI는 Composer에 없음** — Work 탭 `PlanTabToolbar`만.

### 6.2 응답 방식 (turn profile)

| Profile | 라벨 | R1 | R2+ | consensus | plan |
|---------|------|----|-----|-----------|------|
| **quick** | 빠른 | 선택 1명 | — | off | 유지 |
| **analyze** | 분석 | 선택 전원 병렬 | — | off | 유지 |
| **specialist** | 분업 | Codex+Claude | Cursor | off | 유지; `research_mode` |
| **free** | ♾️ | 전원 | debate+anchor | **on** | 합의 후 auto-scribe 시도 |

레거시: `discuss`→analyze, `review`→free.

**UI 저장:** `localStorage` `agent-lab-turn-profile`

### 6.3 Compose mode (plan 갱신 여부)

| mode | 설정 | 턴 후 Scribe |
|------|------|--------------|
| **discuss** | Work 「전송 시 plan 갱신」 OFF | **안 함** |
| **plan** | 「전송 시 plan 갱신」 ON | **함** |
| **consensus** | ♾️ profile | 합의 **reached** 후 auto-scribe (별도) |

「**지금 정리**」: 새 Human 메시지 없이 `synthesize_only` SSE run.

### 6.4 전송 API body (요약)

`POST /api/room/runs` → SSE

주요 필드: `topic`, `agents[]`, `mode` (discuss|plan), `consensus_mode`, `turn_profile`, `efficiency_mode`, `permissions`, `workspace`, `agent_capabilities`, `files`, `synthesize_only`.

### 6.5 전송 게이트 (`composerSendLocked`)

다음이면 전송 불가:

- `running` / `synthesizing` / `runBusy`
- 선택 agent 0명
- preflight 실패 agent 포함
- custom workspace 경로 미선택
- 본문·첨부 모두 비어 있음
- 미해결 BLOCK objection 시 placeholder만 (execute 쪽)

### 6.6 권한 (permissions)

기본 (`agent_permissions.roomPermissions`):

| Agent | 기본 |
|-------|------|
| Cursor | tools, local_agent_lab, local_pipeline |
| Codex | cli |
| Claude | tools, write, local paths |

**Discuss overlay:** Claude write off; Codex/Claude read-only preamble.

**현재:** `AgentPermissionAlert` UI 있으나 send path는 full defaults 사용 (모달 bypass).

첫 전송 시 capabilities → `run.json` `agent_capabilities`.

### 6.7 Clarifier

`AGENT_LAB_CLARIFIER=1` 일 때:

- topic 길이 < `AGENT_LAB_CLARIFIER_MIN_CHARS` (기본 48) **또는** 세션 첫 턴
- SSE `clarifier_prompt` → 배너
- **에이전트 라운드 skip** (Human 메시지만 저장)
- 질문은 Human Inbox에도 harvest

plan 모드 첫 synthesize 턴은 plan 맥락 질문 세트.

### 6.8 슬래시 명령

Composer `/` 또는 palette에서 삽입.

| 명령 | 동작 |
|------|------|
| `/goal-check` | Goal Oracle 재검 (server) |
| `/stop` | run 취소 (client) |
| `/focus` | composer 포커스 (client) |
| plugin/skills | discovery 목록 (조건부 server invoke) |

---

## 7. Room 턴 오케스트레이션

> 소스: `room.py`, `room_consensus.py`, `room_team_orchestration.py`

### 7.1 턴 파이프라인

```text
Human message
  → clarifier? (skip agents)
  → sync_tasks_from_messages (PROPOSED harvest)
  → resolve_turn_lead (GO / rotation)
  → if consensus_mode: run_consensus_agent_rounds
    else: run_agent_rounds (R1..N)
  → if synthesize: synthesize_plan (Scribe)
  → maybe_check_session_goal (Goal Loop)
  → _write_session_files (chat.jsonl, run.json, plan.md)
  → SSE complete
```

### 7.2 R1 팀 리드 순서

`team_r1_split()`: **팀원 병렬 먼저 → 턴 리드 마지막** (리드는 peer 전체 컨텍스트).

Review R2+ 순서: `claude → codex → cursor` (`review_mode` && round≥2).

### 7.3 Specialist 라운드

| Round | Agents | 비고 |
|-------|--------|------|
| R1 | Codex + Claude | Cursor idle preamble |
| R2 | Cursor | artifact-only context 가능 (`AGENT_LAB_F2_ARTIFACT_ONLY`) |

`ensure_specialist_capabilities()` — cwd role: execute/repo/review.

### 7.4 ♾️ Consensus loop

1. **R1** 병렬 전원
2. **Debate R2..** — `AGENT_LAB_DEBATE_ROUNDS` (기본 4); 짝수=반박, 홀수=확장
3. **Anchor loop** — ENDORSE/PASS 순차
4. **종료 조건** (`consensus.status`):
   - `reached`: anchor 합의 + `consensus_tasks_ready()` + open objection 없음
   - `incomplete`: open_tasks / open_objections / cap / no_anchor
   - `paused`: Human Inbox pending
   - `failed`: agent errors

**구 phrase fallback:** `이의 없습니다` (`is_pure_no_objection`)

**Caps:** max rounds 12, max calls 30 (efficiency 시 8/20)

### 7.5 턴 리드 / 세션 리드

| 개념 | 저장 | 해석 |
|------|------|------|
| **세션 리드** | `run.team_lead` | Tasks UI select |
| **턴 리드** | `turn_leads[human_turn]` | `resolve_turn_lead()` |
| **GO override** | Human 본문 regex | `(?i)(?:GO\|리드\|lead)\s*[:：]?\s*(cursor\|codex\|claude)` — active pool 내 |
| **회전** | `(human_turn-1) % len(agents)` | GO 없을 때 |

**Lead discuss block:** pure discuss 턴·리드 agent에게만 prepended (plan/consensus 제외).

Tasks UI: ♾️·plan 갱신 모드에서만 리드 상세 표시 (`shouldShowTurnLeadDetails`).

### 7.6 Human turn synthesis (턴 요약)

`should_emit_human_turn_synthesis()`:

| 조건 | 생성 |
|------|------|
| ♾️ (free) | **항상** |
| analyze + R1 병렬 agent **≥3** | **생성** |
| quick / specialist / 기타 | **생성 안 함** |

system 메시지: `[human synthesis — 턴 요약]` + Human 발췌 + R1 agent bullets.  
`synthesize_only` 턴에는 skip.

### 7.7 Task auto-assign 정책

| 턴 종류 | PROPOSED 생성 | owner 자동 배정 |
|---------|---------------|-----------------|
| discuss (plan OFF, ♾️ 아님) | O | **X** |
| plan / synthesize / consensus | O | O (round-robin) |

Discuss는 `sync_tasks_from_turn_state()` 도 skip.

### 7.8 Resume / replay

`completed_steps`: 키 `turn_{n}_round_{r}_{agent}` — 같은 턴 재시도 시 성공 agent skip.

---

## 8. Transcript

### 8.1 메시지 종류

| role / 표시 | 설명 |
|-------------|------|
| `you` | Human |
| `agent` | Cursor / Codex / Claude |
| `system` | 라운드 구분선, 턴 실패, consensus incomplete |
| `human synthesis` | 턴 요약 bubble |

### 8.2 View options (Transcript 탭 ⋯)

| 옵션 | 동작 | persist |
|------|------|---------|
| **Human 요약** | you + 턴 요약만; agent 숨김 (+N) | `agent-lab-transcript-human-synthesis` |
| **동료 채널** | `visibility: peer` 표시 (기본 숨김) | 세션 메모리 only |

Human 요약 ON이면 동료 채널 토글 disabled.

### 8.3 Envelope (에이전트 구조화 응답)

R2+ reply의 ```agent-envelope``` JSON:

| act | 의미 | UI 힌트 |
|-----|------|---------|
| **ENDORSE** / **PASS** | 동의 | Tasks endorsement |
| **CHALLENGE** | 할 일/block | task `blocked` |
| **PROPOSE** | plan 제안 | Plan update |
| **BLOCK** | execute 차단 | Review blocker |
| **AMEND** | plan 수정 | Plan update |

parse 실패 시 `envelopeParseError` + “envelope 없음” 경고.

### 8.4 Provenance

plan `(ref: chat.jsonl#L12)` → Transcript 해당 줄 scroll + 2.6s highlight.

`planRefWarnings`: plan ref와 chat 줄 token overlap 낮으면 Work 탭 정보 배너 (plan 무효화 아님).

### 8.5 실패·부분 성공 표시

| 이벤트 | UI |
|--------|-----|
| `turn_failed` | system `[턴 실패 · agent]` |
| `agent_error` | system per agent |
| `consensus_incomplete` | 구분선 `── 합의 미완 · … ──` |
| `run_failed` / `error` | composer 위 error-banner + P0 notification |
| run lock stuck | Run status bar 「잠금 해제」 |

**Partial turn:** 일부 agent만 실패해도 성공 agent 답변은 **유지**.

### 8.6 Typing / activity

`agent_start` → ReplyWaitingBubble; `agent_activity` 스트림 (최대 12줄); `agent_done` → 최종 bubble.

---

## 9. Work surface (plan + execute)

### 9.1 `plan.md` 구조 (Scribe)

Scribe prompt (`ROOM_SCRIBE`): 한국어, 필수 섹션 **`## 지금 실행`**, provenance ref.

| 섹션 | execute 연결 |
|------|--------------|
| `## 지금 실행` | dry-run 대상 action (3-field) |
| `## 실행 순서 (이후)` | 로드맵 |
| `## 미해결 이의` | objection 있을 때 patch only |

**갱신 트리거:**

| 방법 | 조건 |
|------|------|
| 전송 시 plan 갱신 ON + 전송 | Scribe after turn |
| 지금 정리 | synthesize_only |
| ♾️ reached | `maybe_auto_scribe_after_consensus` |
| duplicate / open objection | `scribe_skipped` |

내용 unchanged면 disk write skip.

### 9.2 Work 레이아웃 (현재)

```text
WorkStatusBar (stepper + freshness)
PlanTabToolbar (전송 시 plan 갱신 · 지금 정리)
[ExecuteQueueBar | ConsensusDryRunGateBar]  ← 조건부
PlanDocument
PlanExecutePanel
[execution history footer]
```

### 9.3 PlanTabToolbar

| 컨트롤 | 게이트 |
|--------|--------|
| **전송 시 plan 갱신** | running/synthesizing 시 disabled |
| **지금 정리** | synthesize_only SSE |

상태: `planAfterSend` — `localStorage` `agent-lab-plan-after-send`; send 후 `finally`에서 OFF reset.

### 9.4 Plan execute 파이프라인

```text
plan ## 지금 실행
  → parse actions (plan_actions.py)
  → gates: snapshot · objection · pre_execute hooks
  → worktree dry-run (Cursor)
  → pending_approval + diff
  → Human merge approve/reject
  → Oracle verify (execute, Goal Oracle과 별개)
  → task 완료 연동
```

### 9.5 Execute gates (순서)

| Gate | 모듈 | 실패 시 |
|------|------|---------|
| **Plan snapshot** | `plan_pending` | 첫 dry-run per action+hash → Human 승인 필요 |
| **Objection BLOCK** | `room_objections` | HTTP 409 |
| **pre_execute hooks** | `room_hooks` | `.agent-lab/hooks.toml` exit 2 |
| **Worktree** | `plan_execute_worktree` | dirty base / no git |
| **Human diff** | Review UI | pending_approval |
| **Execute Oracle** | `plan_execute_merge` | PASS/FAIL badge |

### 9.6 PlanExecutePanel 기능

- Action list: now / roadmap
- Dry-run → diff stat + **WorktreePendingBanner** (branch, base, path, SHA)
- Approve label: worktree → 「Merge 승인」
- Reject → worktree 폐기
- Revise / reverify / isolation override
- Linked task jump
- Cursor ready 필요 경로 있음

### 9.7 Consensus → execute 연결

♾️ `reached` 후:

- SSE `consensus_plan_sync_*`
- optional `consensus_dry_run_proposal` — Work에서 dry-run CTA

### 9.8 Hook · Communicate (Room Router)

> 설계: [HOOK-COMMUNICATE-REFORM.md](./HOOK-COMMUNICATE-REFORM.md) · 회귀: `make verify-hooks`

**Hook layers**

| Layer | Scope | Config |
|-------|--------|--------|
| Room Router | Turn boundary — `pre/post_agent_reply`, `post_harvest`, `pre_scribe` | `.agent-lab/hooks.toml` |
| Native overlay | Tool loop — codex/cursor/claude cwd hooks | `AGENT_LAB_NATIVE_HOOKS=1` + session `.agent-lab/agent-hooks/` |
| CC-hooks | Dev only — PostEdit/Stop | `.claude/settings.json` (≠ Room runtime) |

**SSE / UI**

| Event | UI |
|-------|-----|
| `hook_event` | Notification (P0/P1) + typing `activities[]` |
| `agent_activity` | Tool stream (cursor/codex/claude) |
| envelope R2+ issue | `agent_activity` line + P2 `envelope_warn` toast |

**Communicate env**

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENT_LAB_ENVELOPE_STRICT` | `consensus_only` | R2+ envelope required (consensus) |
| `AGENT_LAB_LEGACY_ENDORSE` | `0` | `1` = phrase fallback `이의 없습니다` (legacy); default requires envelope `act: ENDORSE` |
| `AGENT_LAB_GUIDANCE_TIER` | `standard` | `debug` only → full envelope prompt block |
| `AGENT_LAB_STRUCTURED_ENVELOPE` | `1` | Structured adapter on agents |
| `AGENT_LAB_NATIVE_HOOKS` | off | Session hook bundle → workspace cwd |

**Observability:** `GET /api/sessions/{id}` → `observability.hook_runs`, `observability.last_communicate_meta`  
**KPI:** `make measure-communicate-baseline` · weekly report §Hook · Communicate

---

## 10. Tasks·합의·이의·산출물

> UI: Inspector **Tasks** — `RoomTaskBar`  
> API: `GET /api/sessions/{id}/tasks`

### 10.1 할 일 생성

- Regex: `[PROPOSED: title]`
- status `pending`, source `proposed`
- cap: `AGENT_LAB_MAX_TASKS_PER_TURN` (8)
- dedup: open pending/in_progress 동일 title

### 10.2 Endorsement (♾️)

- envelope `ENDORSE|PASS` + `refs` → `task.endorsements[agent]`
- **필요 수 M** = `max(1, active_agents - 1)` — 3명 → M=2
- `consensus_tasks_ready()`: 모든 open task ≥ M
- ♾️ `reached` 차단 요인이 될 수 있음 (anchor만으로 부족)

### 10.3 Consensus blocker UI

**표시 조건** (`shouldShowConsensusBlocker`):

- `consensus_tasks_ready === false` + blockers 있음
- **그리고** (현재 ♾️ 모드 **OR** 직전 턴이 consensus)

CTA:

- 할 일 제목 클릭 → transcript highlight
- 「동의 요청」→ composer ENDORSE prefill
- 「완료」→ Human이 task close

### 10.4 Objections

- envelope **CHALLENGE** / execute path **BLOCK**
- Tasks: 미해결 이의 — **수용** / **won't fix**
- open BLOCK → execute 409, composer placeholder

### 10.5 RoomTaskBar 섹션 (전체)

| 섹션 | 기능 |
|------|------|
| Header | counts, collapse, refresh, session lead select |
| Mode hint | composer variant + turn profile copy |
| Lead help | ♾️/plan only |
| Open objections | 최대 5건 + resolve |
| Consensus blocker | headline + CTA |
| Tabs | 전체 / 담당 없음 |
| Task rows | status, owner, 동의 N/M, plan # link, 완료 |
| Complete gate | linked execution pending/review 시 block |
| Artifacts snippet | recent 8 |
| Mailbox | agent→agent, unread |
| Cross-links | plan↔task↔execution |

collapse: `localStorage` `agent-lab-task-bar-collapsed`

데이터 없고 loading 아니면 **null** (빈 패널).

### 10.6 Artifacts (수집)

harvest when: `research_mode` OR specialist OR plan mode.

- disk: `sessions/.../artifacts/`
- meta: `run.json` `artifacts[]`
- specialist R1: Cursor skip; R2 context에 `build_artifacts_block`

---

## 11. Human Inbox

> 설계: [HUMAN-INBOX.md](./HUMAN-INBOX.md)

**목적:** Human-facing 결정 surface **하나** — Question·Build·Clarifier harvest.

| kind | UI | resolve 후 |
|------|-----|------------|
| **question** | options 또는 freeform | 다음 턴 context |
| **build** | GO / defer / reject | GO → `runPlanDryRun` 가능 |
| (clarifier harvest) | clarifier 배너와 연동 | agents 시작 전 |

**표시 위치:**

- Transcript **popup** (턴 complete + pending)
- Inspector Tasks **inspector** presentation
- Composer chip 「Human Inbox 대기」

**폴링:** pending 시 2.5s `fetchSessionInbox`.

**Consensus pause:** inbox pending → `inbox_pause` SSE, ♾️ 중단.

Execute 경로 1차: MCP `ask_human` / `propose_build` (blocking tool loop). Discuss는 envelope harvest fallback.

---

## 12. Goal Loop

`AGENT_LAB_GOAL_LOOP=1`

| 단계 | 동작 |
|------|------|
| 목표 설정 | Tasks 입력 → `set_session_goal` |
| 자동 검사 | 매 턴 end → Oracle (max 5 checks) |
| Mock Oracle | goal에 `` `literal` `` in transcript → PASS; else keyword 50% |
| Live Oracle | `AGENT_LAB_GOAL_ORACLE_LIVE=1` → Claude |
| FAIL | badge + composer prefill 「한 턴 더 토론」 |
| `/goal-check` | 수동 재검 |

`AGENT_LAB_GOAL_AUTO_CONTINUE=1`: FAIL 후 analyze 1턴 auto (depth cap 1).

**Execute Oracle과 별개** (`AGENT_LAB_ORACLE_LIVE`).

---

## 13. Context·효율·에이전트 역량

### 13.1 ContextBundle 레이어

`build_context_bundle()` 순서:

1. **constraints** — permissions, gates, workspace, plugins, tasks, mailbox, artifacts, objections
2. **plan_open** — open bullets + stale banner
3. **turn_state** — blackboard
4. **bridge** — turn bridge
5. **recent** — trimmed thread
6. **peer** — peer channel
7. **guidance** — mode hints (analysis, specialist, efficiency, …)
8. **connect_hint**, **claude_tools**, **follow_up**

메타: `trim_level` ok|warn|critical, `layer_chars`, `budget_pct`, `efficiency_mode`.

### 13.2 Efficiency mode

ON (`AGENT_LAB_EFFICIENCY=1` 또는 UI 토글):

- recent turns 4 (vs 8)
- consensus caps 축소
- ♾️ slim bundle (`build_slim_consensus_bundle`)
- discuss executor read-only overlay

### 13.3 ContextPreviewPanel (Settings)

- **미리보기:** agent + round 선택 → live payload
- **마지막 턴:** stored layer stats
- API: `fetchContextPreview`

### 13.4 AgentSessionSettings

Per-agent:

- cwd role / path (execute, repo, review)
- tool toggles
- preset: 기본값 / 분업

저장: `PATCH` capabilities → `run.json`  
첫 send 시 merge.

---

## 14. Plugins·슬래시 명령

### 14.1 Discovery

| Source | 경로 |
|--------|------|
| Claude skills | `.claude/skills/*/SKILL.md` |
| Claude/Codex MCP | CLI list |
| Cursor | IDE implicit stub |
| Mock | `AGENT_LAB_MOCK_AGENTS=1` |

### 14.2 Allowlist

`run.json` `agent_plugins` — 세션 checkbox allowlist만 Room context 주입.

UI: Settings → PluginPanel (Plugins / Commands tabs).

### 14.3 Command registry

Built-in: `/goal-check`, `/stop`, `/focus`  
External (opt-in): `~/.agent-lab/tools.yaml` · `AGENT_LAB_EXTERNAL_TOOLS=1` · session allowlist `PATCH /api/sessions/{id}/external-tools` · run with `confirm: true` when `human_approve`  
History: `command_history` max 50.

---

## 15. Run 탭

`TurnRunPanel`:

- **TurnProgressStrip:** agents × rounds grid; SSE `agent_start` active cell
- **Stream panel:** **현재 턴만** (`turnMessages`)
- **RoomRunStatusBar:** 중지, long-run hint (default 180s), lock release

빈 상태: 「실행 중이 아닙니다」

데이터: `runSessionRegistry` (SSE patch).

---

## 16. Artifacts 탭

- `roomTasks.artifacts` 역순 목록
- producer · kind · summary · path
- read-only (다운로드 UI 없음)
- TaskBar snippet과 동일 payload source

---

## 17. Settings·Health·진단

### 17.1 Settings 페이지 섹션

| 섹션 | 내용 |
|------|------|
| Agents | Health + AgentSessionSettings |
| Workspace | binding + ContextPreviewPanel |
| Commands | PluginPanel |
| Diagnostics | ApiDiagnosticsBar, reconnect |
| Appearance | Theme |
| Legacy | Classic mode 진입 |

### 17.2 Health

`GET /api/health?probe_bridge=&probe_preflight=`

Per-agent: configured, ready, reason, bridge status.

**SessionRailStatusChip:** N/3 ready; expand → panel.

**Reconnect:** `POST /api/health/reconnect-cursor` — bridge invalidate + re-probe.

Boot: 90× retry + 45s interval refresh.

---

## 18. Workbench (Overview / Tasks / Inbox / Tools)

### 18.1 Overview

`ContextOverviewPanel` — session meta, goal loop, plan summary.

### 18.2 Tasks

Goal loop banner + plan approval + HumanGate panels.

Blocker 시 auto-focus tasks tab.

### 18.3 Inbox

`HumanInboxPanel`, `DiscussInboxPanel`, `NotificationCenter` (P0/P1/P2 — [NOTIFICATION-TAXONOMY.md](./NOTIFICATION-TAXONOMY.md)).

### 18.4 Tools

`WorkbenchPanel` + tool modes: `WorkToolPanel`(plan/execute), `DiffToolPanel`, `WorkspaceFilesPanel`, `PreviewPanel`, `TerminalPanel`, `BackgroundTasksPanel`.

### 18.5 Workbench chrome

- Toggle: toolbar / **⌃⌘I**
- Width drag resize — persist workbench width prefs

---

## 19. 알림·SSE·스트리밍

### 19.1 Transport

`runRoom` → fetch SSE reader — `data: {json}\n\n`  
terminal: `complete` | `error` | `run_failed`  
disconnect → synthetic `run_failed`

### 19.2 SSE 이벤트 (전체)

| type | 의미 |
|------|------|
| `start` | run 시작 |
| `agent_round_start` | 라운드 구분 |
| `agent_start` | agent 호출 시작 (`resumed` = replay) |
| `agent_activity` | streaming log line |
| `agent_done` | success + envelope + context_meta |
| `agent_error` | failure |
| `turn_partial` | 일부 실패 |
| `turn_failed` | 전부 실패 |
| `run_cancelled` | user stop |
| `complete` | 턴 종료 + send_receipt + inbox_pending |
| `consensus_reached` | ♾️ success |
| `consensus_incomplete` | reason code |
| `inbox_pause` | Human Inbox blocked |
| `consensus_plan_sync_*` | auto scribe |
| `consensus_dry_run_proposal` | execute 제안 |
| `scribe_start/done/error/skipped` | plan |
| `plan_actions_validation` | plan format check |
| `clarifier_prompt` | clarifier questions |
| `error` | worker exception |

### 19.3 send_receipt

| receipt | 의미 |
|---------|------|
| `discuss_saved` | discuss only |
| `plan_updated` | scribe success |
| `consensus_done` | ♾️ 턴 종료 |

Composer 하단 5s status (`sendReceipt.ts`) — Work 탭에선 plan receipt 숨김 가능.

### 19.4 Cancel / lock

- `POST /api/room/runs/cancel`
- `POST /api/room/runs/release-lock`
- 「already in progress」→ auto-cancel attempt UI

---

## 20. 키보드·상태 유지(localStorage)

### 20.1 단축키

| Key | Action |
|-----|--------|
| ⌘N | 새 Session |
| ⌘1–⌘4 | Workspace tabs |
| ⌘5 | **등록만 됨 — 매핑 없음** |
| ⌘K | Command palette |
| ⌃⌘S | Session rail toggle |
| ⌃⌘I | Inspector toggle |
| Enter / Shift+Enter | send / newline |
| `/` | slash menu |

Palette: tab open, stop, release lock, settings, focus composer, slash insert.

**⌘. stop:** palette hint only — global binding 없음.

### 20.2 localStorage keys

| Key | 용도 |
|-----|------|
| `agent-lab-last-session-id` | 세션 복원 |
| `agent-lab-sidebar-open` | rail |
| `agent-lab-session-rail-width` | rail width |
| `agent-lab-inspector-open/width` | inspector |
| `agent-lab-turn-profile` | 응답 방식 |
| `agent-lab-efficiency-mode` | 효율 |
| `agent-lab-plan-after-send` | plan 갱신 toggle |
| `agent-lab-transcript-human-synthesis` | Human 요약 view |
| `agent-lab-task-bar-collapsed` | task bar |
| `agent-lab-workspace-id/path` | new session folder |
| `agent-lab-research-mode` | artifacts harvest |
| `agent-lab-permissions-default` | permissions |
| `agent-lab-theme` | light/dark |

**비 persist:** peer channel toggle, inspector/workspace pin state.

---

## 21. REST API 개요

| Method | Path | 용도 |
|--------|------|------|
| GET | `/api/health` | status + agents |
| GET | `/api/health/flags` | `AGENT_LAB_*` registry + active values (`?category=`) |
| GET | `/api/health/readiness` | dry-run readiness (MB-9) |
| GET | `/api/health/codex-proxy` | Codex proxy probe (MB-11) |
| POST | `/api/health/reconnect-cursor` | bridge |
| GET | `/api/sessions` | list |
| GET | `/api/sessions/{id}` | detail + messages |
| PATCH/DELETE | `/api/sessions/{id}` | rename/archive/delete |
| POST | `/api/room/runs` | **SSE room turn** |
| POST | `/api/room/runs/cancel` | stop |
| POST | `/api/room/runs/release-lock` | unlock |
| GET | `/api/sessions/{id}/tasks` | tasks payload |
| POST | `/api/sessions/{id}/tasks/{tid}/complete` | task complete |
| PATCH | `/api/sessions/{id}/team-lead` | session lead |
| POST | `/api/sessions/{id}/objections/{id}/resolve` | objection |
| GET | `/api/sessions/{id}/inbox` | Human Inbox |
| POST | `/api/sessions/{id}/inbox/{id}/resolve` | inbox resolve |
| GET | `/api/sessions/{id}/plan/actions` | plan actions |
| POST | `/api/sessions/{id}/plan/dry-run` | dry-run |
| POST | `/api/sessions/{id}/plan/approve` | merge approve |
| GET | `/api/commands` | slash list |
| POST | `/api/sessions/{id}/commands/run` | slash server cmd |
| GET | `/api/sessions/{id}/context/preview` | context preview |
| PATCH | `/api/sessions/{id}/agent-capabilities` | cwd/tools |
| PATCH | `/api/sessions/{id}/agent-plugins` | plugin allowlist |
| POST | `/api/runs` | **Classic SSE** |

상세: [APP.md](./APP.md)

---

## 22. 환경 변수

**Discoverability:** canonical list of ~79 `AGENT_LAB_*` flags (description, default, effective value):

- CLI: `make list-flags` · `make list-flags -- --category feature --json`
- API: `GET /api/health/flags` · `GET /api/health/flags?category=infra`

Path-like values are home-masked in API/CLI output. Undocumented `AGENT_LAB_*` vars present in the process env appear under category `undocumented`. Full tables below remain the human-oriented reference; the registry in `runtime_flags.py` is the SSOT for tooling.

### Core / paths

| Variable | Effect |
|----------|--------|
| `AGENT_LAB_ROOT` | project root |
| `AGENT_LAB_SESSIONS_DIR` | sessions folder |
| `AGENT_LAB_API_PORT` | default 8765 |
| `QUANT_PIPELINE_ROOT` | pipeline preset |

### Feature flags

| Variable | Effect |
|----------|--------|
| `AGENT_LAB_GOAL_LOOP` | session goal |
| `AGENT_LAB_GOAL_ORACLE_LIVE` | live goal Oracle |
| `AGENT_LAB_GOAL_AUTO_CONTINUE` | auto continue on FAIL |
| `AGENT_LAB_CLARIFIER` | clarifier gate |
| `AGENT_LAB_CLARIFIER_MIN_CHARS` | default 48 |
| `AGENT_LAB_EFFICIENCY` | default efficiency |
| `AGENT_LAB_MOCK_AGENTS` | mock agents/plugins |
| `AGENT_LAB_F2_ARTIFACT_ONLY` | specialist R2 artifact context |
| `AGENT_LAB_INBOX_MODE` | sync vs soft inbox |
| `AGENT_LAB_ORACLE_LIVE` | execute Oracle live |
| `AGENT_LAB_MISSION_BUDGET_USD` | mission USD ceiling → circuit-breaker pause (empty=unlimited) |
| `AGENT_LAB_BUDGET_WARN_PCT` | budget warn threshold % (default 80) |
| `AGENT_LAB_DIFF_SAFETY` | pre-merge diff secret/danger scanner (default on) |
| `AGENT_LAB_TRACE` | OTel-lite span tracer → `trace.jsonl` (default on) |
| `AGENT_LAB_CRASH_RECOVERY` | boot-time reconcile of crashed in-flight merges, G3 (default on) |
| `AGENT_LAB_JUDGE_LIVE` | live LLM-as-judge quality eval in `score_session` (default off) |
| `AGENT_LAB_JUDGE_MODEL` | override Claude model for the judge |

### Room / consensus

| Variable | Default |
|----------|---------|
| `AGENT_LAB_MAX_CONSENSUS_ROUNDS` | 12 |
| `AGENT_LAB_MAX_CONSENSUS_CALLS` | 30 |
| `AGENT_LAB_DEBATE_ROUNDS` | 4 |
| `AGENT_LAB_MAX_TASKS_PER_TURN` | 8 |
| `ROOM_SCRIBE_AGENT` | claude |

### Context budgets

| Variable | Default |
|----------|---------|
| `AGENT_LAB_RECENT_TURNS` | 8 |
| `AGENT_LAB_MAX_THREAD_CHARS` | 96000 |
| `AGENT_LAB_SCRIBE_*` | scribe limits |

Efficiency overrides: `context_limits.efficiency_limits()`.

### Agents

| Variable | Agent |
|----------|-------|
| `CURSOR_API_KEY`, `CURSOR_MODEL` | Cursor |
| `CURSOR_SDK_BRIDGE_*` | bridge |
| `CODEX_BIN`, `CODEX_*` | Codex |
| `CLAUDE_BIN`, `CLAUDE_ROOM_TIMEOUT_SEC` | Claude |

---

## 23. Classic 모드 (레거시)

Planner → Critic → Scribe 순차 (`graph.py`).

산출물: `topic.txt`, `transcript.md`, `plan.md`, `meta.json`.

API: `POST /api/runs` SSE.

새 작업은 **Room** 사용.

---

## 24. CLI

```bash
python -m agent_lab run "주제"
```

앱과 동일 `sessions/` — 혼용 가능.

---

## 25. 문제 해결

### 준비된 에이전트 0/3

- `codex login` / `claude login`
- `~/.agent-lab/.env` 절대 경로
- `curl 'http://127.0.0.1:8765/api/health?probe_preflight=true'`

### API 연결 실패

```bash
lsof -i :8765
make dev   # or tauri-dev
```

Tauri log: `~/Library/Logs/Agent Lab/agent-lab-api.log`

### Cursor bridge

- `CURSOR_SDK_BRIDGE_BIN` 절대 경로
- Health **재연결**

### 전송 비활성

- agent 0명 / preflight fail / folder 미선택 / running

### plan 안 바뀜

- Work 「전송 시 plan 갱신」OFF → 「지금 정리」
- `scribe_skipped` / plan 알림 확인

### ♾️ 안 끝남

- `이의 없습니다` 대기
- Tasks 동의 부족
- efficiency로 cap 축소

### execute 막힘

- snapshot / BLOCK objection / worktree dirty
- Review 배너 메시지 확인

---

## 26. 용어 사전

| 용어 | 뜻 |
|------|-----|
| **Work** | plan + execute 통합 surface |
| **ENDORSE** | ♾️ 할 일·주장 동의 envelope act |
| **Objection** | CHALLENGE/BLOCK — execute 반대 |
| **Dry-run** | worktree에서 미리 실행 |
| **Worktree** | git 임시 트리 — main 오염 방지 |
| **Merge 승인** | Human diff 후 main 병합 |
| **Peer channel** | agent-only visibility |
| **Provenance** | plan `(ref: Ln)` |
| **Human Inbox** | Human 결정 단일 surface |
| **Blocker** | consensus 동의 / objection / execute pending |
| **Allowlist** | 세션 plugin 허용 목록 |

---

## 27. UI 재설계 시 알려진 gap

재설계 시 **동작 명세 vs 현재 구현** 차이 — fix 또는 의도적 제거 결정 필요.

| 항목 | 명세/의도 | 현재 코드 |
|------|-----------|-----------|
| **Permission modal** | 첫 전송 전 확인 | discuss 기본 bypass · **Mission autonomous 구간** 재진입 시 `RoomChat`에서 재확인 |
| **Composer plan toggle** | — | **제거됨** — Work only (의도적, WORK-TAB-IA) |
| **Inspector Context tab** | — | **Settings로 이동** · `contextSidebarPrefs` orphan |
| **⌘5** | Artifacts? | App 등록 · **shortcut map 없음** |
| **⌘. Stop** | mission pause | `run_control` cancel + `mission_loop` pause · Work 탭 **미션 재개** 버튼 |
| **Plan/Review 탭 이름** | legacy docs | 코드는 **Work** 단일 탭 |
| **Human Inbox execute MCP** | reference-fidelity | discuss harvest **부분 구현** ([HUMAN-INBOX.md](./HUMAN-INBOX.md)) |

---

## 28. Mission Loop (Work 탭)

`AGENT_LAB_MISSION_LOOP=1` 또는 세션에서 미션 활성화 시 FSM이 plan gate → execute queue → verify/repair를 자동 진행합니다. SSOT: [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md).

### Work 탭 구성

| 영역 | 설명 |
|------|------|
| **Stepper** | 5단계: `plan_draft` → `review_needed` → `execute_pending` → `merge_verify` → `done` (§4.3) |
| **Pause alert** | `MISSION_PAUSED` 시 사유·재개 phase 안내 + **미션 재개** |
| **Mission strip** | 목표 · phase · 다음 action · circuit breaker · autonomous 배지 |
| **Setup (접기)** | 세션 plugin allowlist — execute/repair MCP merge |

### 운영 단축키·동작

- **⌘.** — 진행 중 run cancel; 미션은 `MISSION_PAUSED` + `last_partial` 기록
- **Autonomous** — plan gate 통과 후 execute 구간; 구간 재진입 시 permission 재확인
- **Circuit breaker** — Momus cap·구조 실패 시 discuss recovery; Work strip에 사유 표시

### Inspector · Context

Context 사이드바 **Overview**에도 동일 mission 메타(phase, BLOCK, next action). Layer 토글로 repo tree · per-dir `AGENTS.md` · mission wisdom notepad 포함.

### 회귀·dogfood

```bash
python scripts/smoke_room.py   # 32 baselines — mission_loop_execute_queue | paused | circuit_breaker
make score-session SESSION=sessions/<id>   # mission_loop.* KPI
```

Live 품질 체크: [MISSION-DOGFOOD.md](./MISSION-DOGFOOD.md).

---

## 부록: 권장 시나리오

### A — 의견만 듣기

1. analyze · 2~3 agents
2. Work 「전송 시 plan 갱신」OFF · Transcript 2~3턴

### B — 기획서 만들기

1. A로 토론
2. Work → **지금 정리** → 보완 질문 → 반복

### C — 합의

1. ♾️ · Tasks 동의/blocker 확인
2. Work plan 확인

### D — 코드 반영

1. plan `## 지금 실행`
2. Work → dry-run → diff → Merge 승인
3. Tasks 완료

---

## 부록: 더 읽을 문서

| 문서 | 내용 |
|------|------|
| [developer-agent-console.md](./developer-agent-console.md) | 콘솔 레이아웃 |
| [WORK-TAB-IA.md](./WORK-TAB-IA.md) | Work 탭 통합 설계 |
| [04-multi-agent-room.md](./04-multi-agent-room.md) | Room 백엔드 |
| [05-room-agent-roles.md](./05-room-agent-roles.md) | 에이전트 역할 |
| [HUMAN-INBOX.md](./HUMAN-INBOX.md) | Inbox RFC |
| [GOAL-LOOP.md](./GOAL-LOOP.md) | Goal Oracle |
| [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) | Mission Loop FSM |
| [MISSION-DOGFOOD.md](./MISSION-DOGFOOD.md) | Live mission KPI checklist |
| [EXECUTE-WORKTREE-REFORM.md](./EXECUTE-WORKTREE-REFORM.md) | execute/worktree |
| [PLUGIN-DISCOVERY.md](./PLUGIN-DISCOVERY.md) | plugins |
| [STABILITY.md](./STABILITY.md) | 운영·포트·CI |

---

*코드 기준: `web/src/utils/workspaceTabs.ts`, `web/src/components/RoomChat.tsx`, `web/src/components/WorkToolPanel.tsx`, `web/src/components/WorkPanel.tsx`, `src/agent_lab/room.py`, `src/agent_lab/room_tasks.py`, `src/agent_lab/room_team_orchestration.py`. Shipped status: TRACEABILITY + tests.*
