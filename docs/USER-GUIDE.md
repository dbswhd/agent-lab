# Agent Lab 사용 설명서

> **대상:** Agent Lab을 처음 쓰는 사람  
> **버전 기준:** Developer Agent Console UI (Session rail · Workspace · Inspector)  
> **관련 문서:** [APP.md](./APP.md) · [04-multi-agent-room.md](./04-multi-agent-room.md) · [developer-agent-console.md](./developer-agent-console.md) · [GOAL-LOOP.md](./GOAL-LOOP.md)

---

## 목차

1. [Agent Lab이란?](#1-agent-lab이란)
2. [설치와 첫 실행](#2-설치와-첫-실행)
3. [화면 둘러보기 (UI 투어)](#3-화면-둘러보기-ui-투어)
4. [세션 생명주기](#4-세션-생명주기) — 응답 방식·턴 요약·턴 리드 포함
5. [슬래시 명령과 Plugin 패널](#5-슬래시-명령과-plugin-패널)
6. [Goal Loop · Plan Execute · 승인 · Worktree](#6-goal-loop--plan-execute--승인--worktree)
7. [키보드 단축키](#7-키보드-단축키)
8. [문제 해결 (Troubleshooting)](#8-문제-해결-troubleshooting)
9. [용어 사전 (Glossary)](#9-용어-사전-glossary)
10. [부록: 이 프로그램이 하지 않는 것](#10-부록-이-프로그램이-하지-않는-것)

---

## 1. Agent Lab이란?

**Agent Lab**은 주제(질문·기획·조사·코드 작업)를 던지면 **세 명의 AI 에이전트**가 함께 생각하고, 대화를 **문서(plan.md)** 로 정리하고, 필요하면 **코드 변경을 제안·검토·승인**까지 이어가는 **개발자용 에이전트 콘솔**입니다.

메신저처럼 보이지만, 목적은 잡담이 아니라 **통제된 협업**입니다.

| 목적 | 설명 |
|------|------|
| **토론** | Cursor · Codex · Claude가 같은 주제에 대해 각자 의견 |
| **기록** | 대화가 `chat.jsonl`에 저장되고, **Transcript** 탭에서 확인 |
| **정리** | 대화를 바탕으로 `plan.md` 문서 생성·갱신 |
| **실행** | plan에 적힌 작업을 dry-run(미리보기) → Human 승인 → 실제 반영 |
| **추적** | 할 일·합의·실행 상태를 Inspector **Tasks**에서 확인 |

### 1.1 세 명의 에이전트 (3자 룸)

Agent Lab의 기본 팀은 **Cursor · Codex · Claude** 입니다. 같은 질문을 받아도 **역할이 다릅니다.**

| 에이전트 | 한 줄 역할 | 잘 맡기는 일 |
|----------|------------|--------------|
| **Cursor** | 레포를 직접 보고 **파일·UI·빌드** 관점에서 답함 | “이 파일 어디?” “이 버그 왜?” “패치 방법” |
| **Codex** | 문제를 **쪼개고 순서·검증·완료 기준**을 잡음 | “어떤 순서로?” “테스트 플랜” “원인 추적” |
| **Claude** | **맹점·리스크·설명** — 두 번째 의견·요약 | “놓친 게 뭐야?” “이 설계 괜찮아?” |

**Human(당신)** 은 방향을 정하고, 승인하고, 막히면 결정합니다. 에이전트끼리 서로 질문하도록 설계되어 있으며, Human에게 A/B 선택지를 넘기지 않도록 유도합니다.

### 1.2 quant-pipeline과의 관계

| quant-pipeline | Agent Lab |
|----------------|-----------|
| DB, 백테스트, 실거래 | 없음 (기본) |
| TASK · pytest · Handoff | PLAN · 토론 · 문서화 |
| 프로덕션 실행 | **기획·토론·초안** 연습장 |

Agent Lab에서 나온 `plan.md`를 Human이 검토한 뒤, 필요하면 pipeline의 `TASK-*.md`로 옮깁니다. **Agent Lab이 pipeline을 대신 실행하지는 않습니다.**

### 1.3 비유

> “세 명의 동료 개발자와 회의하고, 회의록(plan)을 쓰고, PR 승인까지 하는 도구”

---

## 2. 설치와 첫 실행

### 2.1 필요한 것

| 항목 | 설명 |
|------|------|
| **macOS** (권장) | 데스크톱 앱(Tauri) 기준. 브라우저만 써도 됨 |
| **Python 3.11+** | 백엔드 API |
| **Node 18+** | 웹 UI |
| **Rust** (Tauri만) | `make tauri-dev` / `make tauri-build` 시 |
| **에이전트 인증** | 아래 중 하나 이상 |

**에이전트별 준비:**

| 에이전트 | 준비 방법 |
|----------|-----------|
| **Codex** | 터미널에서 `codex login` (ChatGPT Plus 등) |
| **Claude** | 터미널에서 `claude login` (Claude Code 구독) |
| **Cursor** | `CURSOR_API_KEY` + `pip install -e ".[cursor]"` (선택) |

### 2.2 설치 (최초 1회)

```bash
cd ~/Projects/agent-lab
make install
```

`make install`은 Python 가상환경(`.venv`)과 웹 의존성(`web/node_modules`)을 설치합니다.

### 2.3 환경 설정 (~/.agent-lab/.env)

설정 파일은 **아래 순서**로 적용됩니다 (나중 것이 우선):

1. `~/.agent-lab/.env` — **권장** (데스크톱 앱·GUI용)
2. `~/.agent-lab/config.toml` — 경로·포트·로그
3. 프로젝트 루트 `.env` — 개발자 로컬 오버라이드

**첫 설정:**

```bash
cp .env.example .env          # 개발용 (프로젝트 루트)
mkdir -p ~/.agent-lab
cp .env.example ~/.agent-lab/.env   # 앱·GUI용 (권장)
```

**GUI 앱(Tauri)은 터미널 PATH가 짧습니다.** `CODEX_BIN`, `CLAUDE_BIN` 등은 **절대 경로**로 적어 두세요.

`.env` 예시:

```env
AGENT_LAB_PROVIDER=codex
CODEX_BIN=/Users/you/.nvm/versions/node/v24.13.1/bin/codex
CLAUDE_BIN=/Users/you/.nvm/versions/node/v24.13.1/bin/claude
CURSOR_API_KEY=your_key_here
AGENT_LAB_GOAL_LOOP=1          # 세션 목표 기능 (선택)
# AGENT_LAB_CLARIFIER=1        # 짧은 첫 메시지 확인 질문 배너 (선택)
```

**`~/.agent-lab/config.toml` 예시:**

```toml
[paths]
quant_pipeline = "/Users/you/Desktop/pipeline"
agent_lab = "/Users/you/Projects/agent-lab"

[api]
port = 8765

[logging]
dir = "/Users/you/Library/Logs/Agent Lab"
```

### 2.4 실행 방법 (세 가지)

#### 방법 A — 브라우저 개발 모드 (추천)

```bash
make dev
```

| 구성 | 주소 |
|------|------|
| 웹 UI | **http://127.0.0.1:5173** |
| API | **http://127.0.0.1:8765** |

Vite가 `/api` 요청을 8765로 자동 연결합니다. 코드 수정 시 UI·API 모두 hot reload 됩니다.

#### 방법 B — 데스크톱 앱 (Tauri)

```bash
make tauri-dev
```

별도 URL 없이 **Agent Lab** 네이티브 창이 열립니다. 앱이 백엔드(uvicorn, 포트 8765)를 자동으로 띄웁니다.

**설치 파일 빌드:**

```bash
make tauri-build
# → web/src-tauri/target/release/bundle/macos/Agent Lab.app
```

빌드된 `.app`은 Python venv를 내장하므로, 대상 Mac에서 `make install` 없이 실행 가능합니다.

#### 방법 C — 프로덕션 단일 포트

```bash
make prod
```

브라우저: **http://127.0.0.1:8765** (UI + API 동시)

### 2.5 Tauri vs 브라우저 개발 모드

| | 브라우저 (`make dev`) | Tauri (`make tauri-dev`) |
|---|----------------------|--------------------------|
| UI | http://127.0.0.1:5173 | 네이티브 창 |
| API | 8765 (별도 프로세스) | 앱이 자동 spawn |
| `.env` | 프로젝트 `.env` + `~/.agent-lab/.env` | **`~/.agent-lab/.env` 우선** |
| PATH | 터미널 PATH 그대로 | **짧음** → BIN 절대 경로 필수 |
| 폴더 선택 | 브라우저 제한 | Tauri 다이얼로그 |
| 로그 | 터미널 | `~/Library/Logs/Agent Lab/` |

### 2.6 정상 동작 확인

왼쪽 **Sessions** 영역 상단 또는 헤더에 에이전트 상태가 보입니다.

- `Claude … · Codex … · Cursor …` 형태로 모델/준비 상태 표시
- **준비된 에이전트 0/3** 이면 메시지를 보낼 수 없습니다 → [§8 문제 해결](#8-문제-해결-troubleshooting) 참고

터미널에서 API 확인:

```bash
curl http://127.0.0.1:8765/api/health
```

---

## 3. 화면 둘러보기 (UI 투어)

화면은 크게 **세 영역**입니다.

```text
┌──────────────┬────────────────────────────────────┬─────────────────┐
│ Session rail │ Workspace (메인 작업 영역)          │ Inspector       │
│ (왼쪽)       │ Transcript / Plan / Review / …     │ Context / Tasks │
│              ├────────────────────────────────────┤ Run / Settings  │
│ 세션 목록    │ Composer (하단 입력창)              │ (오른쪽)        │
└──────────────┴────────────────────────────────────┴─────────────────┘
```

### 3.1 Session rail (왼쪽 사이드바)

| 요소 | 역할 |
|------|------|
| **새 Session** (⌘N) | 새 주제로 대화 시작 |
| **세션 검색** | 과거 세션 찾기 |
| **Active / Archive** | 진행 중 / 보관된 세션 |
| **백엔드 상태** (`SessionRailStatusChip`) | Codex/Claude/Cursor 준비 여부·모델 줄 · 클릭 시 **Health** 상세 · **재연결** (Cursor bridge) |
| 세션 목록 | 주제 제목·날짜·상태 칩 |

세션 하나 = **주제 하나** = 디스크의 `sessions/<날짜>-<이름>/` 폴더 하나.

**⌃⌘S** 로 사이드바를 접거나 펼 수 있습니다.

### 3.2 Workspace (가운데) — 탭

상단 **탭**으로 화면 내용이 바뀝니다.

| 탭 | 단축키 | 내용 |
|----|--------|------|
| **Transcript** | ⌘1 | Human·에이전트 대화 로그 |
| **Plan** | ⌘2 | `plan.md` 문서 |
| **Review** | ⌘3 | 실행 미리보기·승인 대기 |
| **Run** | ⌘4 | 현재 턴 진행 상황 |
| **Artifacts** | ⌘5 | 세션 중 생성된 산출물 |

**탭이 자동으로 바뀌는 경우:**

| 상황 | 기본 탭 |
|------|---------|
| 에이전트 실행 중 | **Run** |
| 승인·dry-run 대기 | **Review** |
| plan.md가 있음 | **Plan** |
| 그 외 | **Transcript** |

직접 탭을 바꾼 뒤에는 **그 세션 동안** 선택이 유지됩니다. (실행 시작/완료, 승인 대기 생김 등 특정 이벤트 때만 다시 자동 전환)

#### Transcript

- **append-only** 대화 기록 (Human + 에이전트)
- 말풍선 클릭·스크롤로 흐름 파악
- plan의 `chat.jsonl#L12` 같은 **출처 링크**를 누르면 해당 줄로 이동·하이라이트
- **⋯ 메뉴** 옵션:
  - **Human 요약** — 에이전트 말풍선 숨기고 Human + 턴 요약만
  - **동료 채널** — 에이전트끼리만 보이는 peer 메시지 표시 (기본 OFF)

#### Plan

`plan.md` **읽기 전용 뷰** + plan 전용 도구.

| 도구 | 설명 |
|------|------|
| **전송 시 plan 갱신** | 켜면 메시지 전송 후 Scribe가 plan.md 재작성 |
| **지금 정리** | 새 메시지 없이 **현재 대화만**으로 plan.md 갱신 |
| **plan 알림** (접기) | 합의 반영 실패 등 있을 때만 표시 |
| **ref 경고** (접기) | plan 출처와 대화 내용 불일치 힌트 |

plan 본문의 `## 지금 실행` 섹션은 Review 탭 실행과 연결됩니다.

#### Review

**코드·파일 변경을 Human이 승인하는 곳.**

| 영역 | 설명 |
|------|------|
| **ExecuteQueueBar** | 승인 대기 중인 실행 한 건 |
| **ConsensusDryRunGateBar** | ♾️ 합의 후 자동 실행 제안 |
| **PlanExecutePanel** | plan 액션 목록 · dry-run · diff · 승인/거절 |

Review 탭에 **Pending** 뱃지가 붙으면 할 일이 있습니다.

#### Run

현재 턴의 **에이전트 topology** (누가 몇 라운드까지 완료했는지). 실행 중이면 자동으로 이 탭이 선택되기 쉽습니다.

#### Artifacts

세션 중 저장된 **산출물** 목록 (경로·요약). 에이전트·도구가 만든 파일 메타가 쌓입니다.

### 3.3 Composer (하단 입력창)

| 요소 | 설명 |
|------|------|
| **응답 방식** (세그먼트) | 빠른 / 분석 / 분업 / ♾️ — [§4.4](#44-응답-방식-턴-프로필) |
| **예상 호출** (비용 힌트) | 3명 풀팀·♾️·분업 등 비용 큰 조합 시 `~N회` 표시 + 확인 체크 |
| **효율** 토글 | 토큰·시간 절약 모드 |
| **입력창** | 질문·지시·추가 맥락 |
| **📎 첨부** | 파일 붙이기 |
| **↑ 전송** | Enter도 전송 (Shift+Enter는 줄바꿈) |
| **■ 중지** | 실행 중 답변 중단 |
| **`/` 슬래시** | 슬래시 명령 메뉴 — [§5](#5-슬래시-명령과-plugin-패널) |

**plan 관련 UI는 대화 화면에 두지 않습니다.** plan 갱신·「지금 정리」는 **Plan 탭**에서 합니다.

### 3.4 Inspector (오른쪽 패널)

접었다 펼 수 있는 보조 패널입니다. Transcript에 집중할 때 접으면 화면이 넓어집니다.

| 탭 | 내용 |
|----|------|
| **Context** | 다음 턴에 에이전트에게 넘어갈 컨텍스트 미리보기 |
| **Tasks** | 세션 목표 · **팀 할 일 보드** (`RoomTaskBar`) — [§6.5](#65-팀-할-일-tasks--inspector) |
| **Run** | 실행 취소·잠금 해제 |
| **Settings** | 에이전트별 **cwd·도구** (`AgentSessionSettings`) · **Plugin 패널** |

**Context** 탭은 **미리보기 / 직전 턴** 두 서브탭으로, 다음 턴에 넘어갈 **레이어드 컨텍스트**(예산·trim 수준·에이전트별 미리보기)를 확인합니다. 토큰·누락 디버깅에 씁니다.

### 3.5 첨부 파일 (Attachments)

1. Composer **📎** 버튼으로 파일 선택
2. 전송 시 세션에 저장되어 이후 턴에서도 참고
3. 첨부만 보내면 메시지가 `[첨부] 파일명` 형태로 기록됨
4. 세션에 저장된 첨부는 Composer 아래 **칩**으로 표시

### 3.6 Room vs Classic 모드

상단(또는 설정 영역) **Room / Classic** 토글로 UI 모드를 바꿉니다.

| 모드 | 설명 |
|------|------|
| **Room** (기본·권장) | 3자 룸 — Transcript·Plan·Review·Inspector Tasks 등 **이 설명서 전체**가 이 모드 기준 |
| **Classic** | 레거시 Planner → Critic → Scribe 순차 흐름 — [부록 A](#부록-a-클래식-모드-레거시) |

새 작업은 **Room**을 사용하세요.

---

## 4. 세션 생명주기

### 4.1 새 세션 만들기

1. 왼쪽 **새 Session** (⌘N) 클릭
2. **작업 폴더** 선택 — 에이전트가 코드를 볼 프로젝트 경로
3. (선택) Inspector **Settings**에서 에이전트별 cwd·권한 조정
4. 상단 **에이전트 칩**에서 참여할 에이전트 선택 (Cursor / Codex / Claude)
5. Composer에 **주제** 입력
6. **응답 방식** 선택 (처음엔 **분석** 권장)
7. **↑** 또는 **Enter**로 전송

### 4.2 작업 폴더 (Workspace) 선택

**SessionSetupBar**에서 작업 폴더를 고릅니다.

| 옵션 | 설명 |
|------|------|
| **agent-lab** (프리셋) | Agent Lab 프로젝트 자체 |
| **quant-pipeline** (프리셋) | pipeline 프로젝트 (설정 시) |
| **다른 폴더…** | 직접 폴더 선택 (Tauri: 네이티브 다이얼로그) |

**「다른 폴더…」** 를 고른 뒤 폴더를 선택하지 않으면 전송이 막힐 수 있습니다.

(선택) **연구·분업 (artifacts 수집)** 체크 — Codex/Claude 산출을 artifacts[]에 저장할 때 사용합니다.

### 4.3 주제 (Topic)

첫 메시지가 세션의 **주제**가 됩니다. 한 줄~몇 줄이면 충분합니다.

예:

```text
이 프로젝트의 인증 흐름을 파악하고 개선 포인트를 정리해줘
```

### 4.4 응답 방식 (턴 프로필)

Composer의 **응답 방식**이 “이번 메시지를 어떻게 처리할지”를 정합니다.

| 모드 | 라벨 | 동작 요약 | 언제 쓰나 |
|------|------|-----------|-----------|
| **quick** | 빠른 | 선택 에이전트 **1명**, **1라운드**, 짧게 | 빠른 확인·단순 질문 |
| **analyze** | 분석 | 여러 명 **동시(R1)**, 현황·사실·근거 위주, **plan 유지** | 처음 주제 파악·조사 (**기본 추천**) |
| **specialist** | 분업 | R1 **Codex+Claude** 병렬 → R2 **Cursor** (cwd·툴 비대칭) | 설계·리뷰는 Codex/Claude, 패치는 Cursor |
| **free** | ♾️ | R1 주장 → R2↔R3 토론 루프 → **「이의 없습니다」** 합의 | 쟁점이 있을 때 끝까지 맞추기 |

**plan 갱신**은 Composer가 아니라 **Plan 탭**에서 합니다. **전송 시 plan 갱신**을 켠 뒤 메시지를 내면 Scribe가 `plan.md`를 갱신합니다 (compose mode = `plan`).

#### 라운드(Round)이란?

- **R1:** 에이전트들이 (모드에 따라) 병렬 또는 순차로 **첫 의견**
- **R2+:** 이전 답을 보며 **반박·보완·합의** (♾️·분업에서 활성)

Transcript에 `── 1라운드 · 병렬 · 분석 ──` 같은 **구분선**이 보입니다.

#### discuss / plan / consensus 모드

| 모드 | 의미 | plan.md |
|------|------|---------|
| **discuss (토론)** | 에이전트 토론만 | **유지** (바뀌지 않음) |
| **plan (정리)** | 전송 후 Scribe가 plan 갱신 | **갱신됨** |
| **consensus (♾️)** | 합의까지 맞춘 뒤 plan 동기화 시도 | 합의 완료 시 자동 시도 |

**대화만 하고 plan을 건드리지 않으려면:** Plan 탭 **전송 시 plan 갱신**을 끄고 **분석** 모드로 보내세요.

#### ♾️ 합의 모드 주의

- 에이전트가 **이의 없습니다** 로 맞춰야 턴이 끝납니다.
- 열린 **할 일**에 팀 **동의**가 부족하면 합의가 막힐 수 있습니다 → Inspector **Tasks** 참고.
- 비용·시간이 가장 많이 듭니다. 매 턴 쓰지 마세요.
- 3명 풀팀·♾️·**분업** 등 비용 큰 조합은 **「~N회 호출 이해함」** 체크 후에만 전송됩니다.

#### 분업(specialist) 모드

- R1에서 Codex·Claude가 각자 관점에서 답하고, R2에서 Cursor가 레포·패치 관점으로 이어갑니다.
- Inspector **Settings**에서 에이전트별 **cwd·도구**를 다르게 두는 시나리오에 맞습니다.
- 할 일은 **[PROPOSED:]** 제안만 쌓이고 **담당 자동 배정은 없습니다** (분석·토론과 동일).

#### 효율 모드

**효율** 토글 ON 시:

- 과거 대화 일부만 넘김
- 응답을 짧게 유도
- ♾️ 합의 라운드 상한 축소

긴 세션·반복 질문에 유용합니다.

### 4.5 에이전트 권한 (Permissions)

Codex·Cursor·Claude가 **파일 읽기/쓰기**를 쓸 때, 첫 전송 전 **권한 확인** 대화상자가 뜰 수 있습니다.

| 에이전트 | 설정 항목 |
|----------|-----------|
| **Cursor** | 도구(파일 읽기·검색), agent-lab 폴더, quant-pipeline 폴더 |
| **Codex** | Codex CLI 실행 |
| **Claude** | 읽기, 편집, agent-lab/pipeline 폴더 |

**「기본값으로 기억」** 을 켜면 다음 세션부터 같은 설정이 적용됩니다.

Inspector **Settings**에서도 cwd·권한을 조정할 수 있습니다.

### 4.6 첫 전송 후 일어나는 일

1. 내 메시지가 Transcript에 기록됩니다.
2. (`AGENT_LAB_CLARIFIER=1` 일 때) 주제가 짧으면 **확인 질문(Clarifier)** 배너가 뜹니다 — 답을 포함해 다시 보내야 에이전트 라운드가 시작됩니다.
3. (선택 에이전트 수만큼) **입력 중…** 표시 후 각 에이전트 응답이 Transcript에 쌓입니다.
4. (조건 충족 시) **`[human synthesis — 턴 요약]`** 말풍선이 붙습니다 — [§4.9](#49-턴-요약human-synthesis)
5. (Plan 탭 **전송 시 plan 갱신** ON 일 때) Scribe가 `plan.md`를 작성·갱신합니다.
6. 세션이 `sessions/` 폴더에 저장되고, 왼쪽 목록에 나타납니다.

### 4.7 세션 폴더 (디스크)

주제 1개 = 폴더 1개:

```text
sessions/2026-06-06-my-topic/
├── topic.txt          # 주제
├── chat.jsonl         # 대화 원문 (한 줄 = JSON)
├── plan.md            # 정리 문서
├── run.json           # 턴 메타·tasks·실행·합의
├── transcript.md      # 사람이 읽기 쉬운 로그 (export)
└── attachments/       # 첨부 파일 (있을 때)
```

앱을 껐다 켜도 목록은 **폴더 스캔**으로 복구합니다.

기본 위치: `~/Projects/agent-lab/sessions/`  
`AGENT_LAB_SESSIONS_DIR` 또는 `~/.agent-lab/config.toml`의 `[paths]`로 변경 가능.

### 4.8 세션 관리

| 동작 | 방법 |
|------|------|
| **이름 변경** | 세션 목록에서 |
| **보관** | Archive 탭으로 이동 |
| **삭제** | 목록에서 삭제 (디스크 폴더 제거) |
| **검색** | 왼쪽 검색창 |

### 4.9 턴 요약(Human synthesis)

Transcript에 **`턴 요약`** 배지가 붙은 말풍선은, 한 턴이 끝난 뒤 Human 질문과 에이전트 답을 **짧게 묶어** 보여 줍니다.

**생성 조건 (백엔드):**

| 조건 | 턴 요약 |
|------|---------|
| **♾️ (free)** 모드 | **항상** (합의 턴 종료 후) |
| **분석 (analyze)** + R1 병렬 에이전트 **3명 이상** | **생성** |
| 빠른·분업·일반 토론 등 | **생성 안 함** |

Transcript **⋯ 메뉴 → Human 요약**을 켜면 에이전트 말풍선을 숨기고 Human + 턴 요약만 볼 수 있습니다 (표시 여부와 별개로, 위 조건에서만 턴 요약이 **기록**됩니다).

### 4.10 턴 리드와 GO 명령

**세션 리드**는 룸 전체 기본값이고, **이번 턴 리드**는 메시지마다 달라질 수 있습니다.

| 개념 | 설명 |
|------|------|
| **세션 리드** | Inspector **Tasks** 상단 선택 상자로 변경 |
| **이번 턴 리드** | 메시지에 `GO codex` / `리드: claude` 가 있으면 그 에이전트, 없으면 선택된 에이전트 순서로 **회전** |

♾️·plan 갱신 턴에서만 Tasks에 **리드 안내**가 자세히 보입니다. 토론·분석·빠른·분업에서는 리드 UI가 숨겨집니다.

---

## 5. 슬래시 명령과 Plugin 패널

### 5.1 슬래시 명령이란?

Composer 입력창에 **`/`** 를 치면 등록된 **슬래시 명령** 목록이 나옵니다.  
명령을 선택하거나 타이핑한 뒤 Enter로 실행합니다.

**⌘K 명령 팔레트와의 차이:**

| | **⌘K Command Palette** | **Composer `/`** |
|---|-------------------------|------------------|
| 위치 | 화면 중앙 오버레이 | 입력창 바로 위 |
| 용도 | 탭 전환·Stop·Plugin 열기 등 **UI 액션** | **세션·에이전트 명령** |
| 검색 | 명령 검색 | 슬래시 이름·설명 필터 |

### 5.2 내장(Built-in) 슬래시 명령

| 명령 | 설명 | 조건 |
|------|------|------|
| **`/goal-check`** | 세션 목표 대비 Oracle 재검 | `AGENT_LAB_GOAL_LOOP=1` 필요 |
| **`/stop`** | 현재 Room run 취소 | 실행 중일 때 |
| **`/focus`** | Composer 입력창으로 포커스 | 항상 |

**사용 예:**

```text
/goal-check
/stop
/focus
```

`/goal-check`는 Inspector **Tasks**의 **Oracle 재검** 버튼과 같은 동작입니다.

### 5.3 에이전트·외부 명령

Plugin discovery가 켜져 있으면 Claude skills, Codex/Cursor 플러그인 등이 목록에 추가됩니다.

| 그룹 | 출처 |
|------|------|
| **Built-in** | Agent Lab 내장 |
| **Claude** | `.claude/skills/*/SKILL.md`, MCP |
| **Codex** | `codex plugin list`, MCP |
| **Cursor** | Cursor IDE 설정 (암시적) |
| **External** | `~/.agent-lab/tools.yaml` (계획) |

에이전트 명령 중 일부는 **Room 턴 중 자율 사용**만 가능하고, 슬래시로 직접 호출되지 않을 수 있습니다.

### 5.4 Plugin 패널

Inspector **Settings** 탭 하단 **PluginPanel**에서 관리합니다.

**Plugins 탭:**

- Claude / Codex / Cursor별 설치된 플러그인·MCP 목록
- **체크박스**로 세션 **allowlist**에 추가/제거
- 목록이 비어 있으면: “목록 없음 — 네이티브 앱에서 추가” (각 CLI/IDE에서 설치)

**Commands 탭:**

- 사용 가능한 슬래시 명령 전체 목록
- 클릭하면 Composer에 슬래시가 **프리필**됨

**보안:** 기본 CI/mock 환경에서는 discovery가 비어 있고, 플러그인은 꺼져 있습니다. 세션 allowlist에 넣은 것만 Room 턴에 전달됩니다.

---

## 6. Goal Loop · Plan Execute · 승인 · Worktree

### 6.1 Goal Loop (세션 목표)

Human이 “이 세션이 끝났다”고 판단하는 **기준**을 한 줄로 적고, 턴이 끝날 때마다 **Oracle**이 달성 여부를 자동 점검합니다.

**활성화:**

```env
AGENT_LAB_GOAL_LOOP=1
```

(선택) `AGENT_LAB_GOAL_ORACLE_LIVE=1` — 실제 Claude oracle 사용 (기본: mock, 오프라인)

**사용법 (Inspector Tasks):**

1. **세션 목표** 입력란에 목표 문장 작성 → **목표 설정**
2. 턴 종료 시 Oracle 자동 검사 (최대 5회, `goal_loop.max_checks`)
3. **목표 달성** / **Oracle FAIL** 배지 표시
4. FAIL 시 **한 턴 더 토론** — Composer에 안내 문장 자동 채움
5. 수동 재검: **`/goal-check`** 또는 **Oracle 재검** 버튼

**Mock Oracle 팁:** 목표에 백틱으로 구체적 문자열을 넣으면, transcript에 그 문자열이 있을 때 PASS합니다.

```text
결론에 `GOAL_OK`를 기록한다
```

`AGENT_LAB_GOAL_AUTO_CONTINUE=1` — FAIL 후 **한 턴** 자동 discuss (두 번째 FAIL부터는 Human gate)

Goal Loop는 **Plan Execute 검증(Oracle)** 과 **별개**입니다.

### 6.2 plan.md와 Scribe

| | Transcript | plan.md |
|---|------------|---------|
| 역할 | 대화 **원문** | **정리된** 결론·할 일·실행 항목 |
| 갱신 | 매 메시지 | Plan 탭 **전송 시 plan 갱신** · **지금 정리** · 합의 후 |

**plan 갱신 방법:**

| 방법 | 어디서 |
|------|--------|
| **전송 시 plan 갱신** ON + 전송 | **Plan 탭** 툴바 (`PlanTabToolbar`) |
| **지금 정리** | Plan 탭 (새 메시지 없이 현재 대화만 반영) |
| ♾️ 합의 완료 후 | 백그라운드 자동 시도 |

채팅(Transcript) 화면에는 plan 토글·**지금 정리** 버튼을 **두지 않습니다** — Plan 탭으로 이동하세요.

**plan 읽는 법:**

- `chat.jsonl#Ln` — 클릭 시 Transcript 해당 줄
- `## 지금 실행` — 지금 승인·실행할 액션
- `## 실행 순서 (이후)` — 나중에 할 로드맵

### 6.3 Plan Execute (실행) 흐름

```text
Room 토론 → plan.md ## 지금 실행
    → [gates: objection · pre_execute · plan snapshot]
    → git worktree에서 dry-run (action마다 격리)
    → Human diff 검토 → approve = 제품 내 merge
    → worktree 정리 · task 완료
```

**Human이 하는 일 (Review 탭):**

1. **PlanExecutePanel**에서 `## 지금 실행` 액션 선택
2. **Dry-run** — Cursor가 **worktree**(임시 git 브랜치)에서 미리 실행
3. **diff** 확인 — main 작업 트리는 건드리지 않음
4. **Merge 승인** 또는 **거절**
5. 연결된 Task 상태 갱신

**첫 실행 시:** **plan 스냅샷 승인**을 요구할 수 있습니다 (“이 plan 버전으로 실행한다”).

**Worktree 배너:** branch, base, worktree 경로, commit SHA가 표시됩니다.

| 상태 | 의미 |
|------|------|
| **승인 대기** | diff 검토 필요 |
| **main에 병합됨** | merge 완료 |
| **merge 충돌** | Human이 충돌 해결 필요 |
| **Oracle PASS/FAIL** | merge 후 검증 결과 |

**non-git action:** git merge 없이 현재 작업 폴더에 직접 반영되는 경로도 있습니다 (배너: “git merge 없음”).

### 6.4 승인·게이트·이의

| 게이트 | 설명 |
|--------|------|
| **Objection (이의)** | 에이전트가 plan 실행에 반대 → 해소 전 execute 409 |
| **pre_execute hooks** | 실행 전 자동 검사 |
| **plan snapshot** | 첫 dry-run 전 plan 버전 고정 |
| **Human diff 승인** | Review 탭에서 Merge 승인 |

이의가 있으면 Composer에 안내가 뜹니다. Review·Tasks에서 해당 이의를 열어 해소한 뒤 진행하세요.

### 6.5 팀 할 일 (Tasks · Inspector)

Inspector **Tasks** 탭의 **팀 할 일 보드**(`RoomTaskBar`)에서 목표·할 일·합의·이의·산출물을 봅니다. Transcript 하단이 아니라 **오른쪽 Inspector**에 있습니다.

에이전트가 `[PROPOSED: 할 일 제목]` 을 쓰면 **자동으로 할 일**이 생깁니다.

#### 기본 표시

| 표시 | 의미 |
|------|------|
| **대기 / 진행 / 완료** | 작업 상태 |
| **담당 없음** | 토론·분석·분업 턴 — 자동 배정 없음 (정상) |
| **동의 N/M** | ♾️ 합의 시 필요한 팀 **ENDORSE** (3명 활성이면 보통 M=2) |

♾️에서 열린 할 일마다 **활성 에이전트 수 − 1** 명의 동의가 필요합니다 (`consensus_gate` API가 M을 계산).

#### 탭·접기·모드 힌트

| UI | 설명 |
|----|------|
| **전체 / 담당 없음** 탭 | 열린 할 일 전체 vs 담당 미배정만 |
| **접기** | 한 줄 요약으로 축소 (`localStorage`에 기억) |
| **모드 힌트** (상단) | 현재 응답 방식별 안내 — 예: `분석 · 3명 병렬 · 제안만`, `♾️ 합의 · 동의 필요` |

#### 합의 blocker (동의 부족)

**♾️ 모드**이거나 **직전 턴이 합의 턴**일 때만, 동의가 부족한 할 일에 **blocker** 배너가 뜹니다.

- 할 일 제목 클릭 → Transcript에서 해당 할 일이 언급된 줄로 이동·하이라이트
- **동의 요청** → Composer에 ENDORSE 유도 문장 **프리필**
- **완료** → Human이 할 일을 닫음 (더 이상 동의 불필요)

토론·분석만 할 때는 blocker를 **숨깁니다** (할 일 목록은 그대로 보임).

#### 이의(Objection) blocker

에이전트가 plan 실행에 **이의**를 제기하면 Tasks에 **미해결 이의** 섹션이 뜹니다. **수용** / **won't fix** 로 해소하기 전까지 execute가 막힐 수 있습니다. Review·Transcript 안내와 연동됩니다.

#### 산출물·Goal Loop

- 최근 **artifacts** 칩 (연구·분업 모드에서 수집)
- `AGENT_LAB_GOAL_LOOP=1` 이면 **세션 목표**·Oracle 배지·**한 턴 더 토론** CTA

#### Inspector 자동 전환

합의 blocker·이의·승인 대기 등이 생기면 Inspector가 **Tasks** 탭으로 맞춰지기 쉽습니다 (Workspace 탭 정책과 별도).

---

## 7. 키보드 단축키

| 단축키 | 동작 |
|--------|------|
| **⌘N** | 새 Session |
| **⌘1 ~ ⌘5** | Workspace 탭 (Transcript ~ Artifacts) |
| **⌘K** | **Command palette** — 탭 전환·Stop·Plugin·Composer 포커스 |
| **⌃⌘S** | Session rail 접기/펼치기 |
| **Enter** | Composer 전송 |
| **Shift+Enter** | Composer 줄바꿈 |
| **`/` (Composer)** | 슬래시 명령 메뉴 |
| **↑↓ / Tab** | 슬래시 메뉴에서 항목 선택 |
| **Escape** | Command palette 닫기 |

**Command palette 주요 명령:**

- Open Transcript / Plan / Review / Run / Artifacts
- Stop run
- Release run lock
- Open plugin panel
- Focus composer

---

## 8. 문제 해결 (Troubleshooting)

### Q. `준비된 에이전트가 없습니다 (0/3)`

- 터미널에서 `codex login` / `claude login` 실행
- `~/.agent-lab/.env`에 `CODEX_BIN`, `CLAUDE_BIN` **절대 경로** (GUI 앱은 PATH가 짧음)
- Cursor: `CURSOR_API_KEY` + `pip install -e ".[cursor]"` 확인
- `curl http://127.0.0.1:8765/api/health?probe_preflight=true` 로 agent별 reason 확인
- `make dev` 또는 `make tauri-dev` 재시작

### Q. "일부 에이전트 실패" — 실패: Claude

Transcript 상단 **주황 배너**는 **한 턴 안에서 Claude만 실패**하고 Cursor·Codex는 정상일 때 뜹니다. **이미 저장된 다른 에이전트 답변은 그대로** 남습니다.

1. **Health 확인** — 앱 헤더 Health 패널 또는:
   ```bash
   curl -s 'http://127.0.0.1:8765/api/health?probe_preflight=true' | python3 -m json.tool
   ```
   Claude 행의 `reason` / `detail`을 확인합니다.

2. **CLI 로그인·경로** — 터미널에서:
   ```bash
   claude login          # Claude Code 구독 로그인
   which claude          # 경로 확인
   ```
   Tauri·GUI 앱은 PATH가 짧으므로 `~/.agent-lab/.env`에 절대 경로를 넣습니다:
   ```bash
   CLAUDE_BIN=/full/path/to/claude
   ```

3. **수동 호출 테스트** (세션 workspace 폴더에서):
   ```bash
   claude -p "ping" --output-format text --no-session-persistence
   ```
   여기서도 실패하면 Agent Lab 문제가 아니라 Claude CLI·인증·네트워크 문제입니다.

4. **타임아웃** — Claude가 파일을 많이 읽으면 기본 제한에 걸릴 수 있습니다. `.env`에:
   ```bash
   CLAUDE_ROOM_TIMEOUT_SEC=600
   ```

5. **로그** — Tauri: `~/Library/Logs/Agent Lab/agent-lab-api.log` · dev: 터미널 uvicorn 출력. `claude -p failed (exit …)` 메시지를 찾습니다.

6. **재시도** — 같은 메시지를 다시 보내거나, Claude 칩만 끄고 Cursor·Codex만으로 진행할 수 있습니다.

### Q. `API(8765)에 연결할 수 없습니다`

```bash
lsof -i :8765          # 포트 점유 확인
kill $(lsof -ti:8765)  # 필요 시 (다른 앱이면 주의)
make dev               # 또는 make tauri-dev
```

Tauri 앱이면 **완전 종료** 후 재실행. 로그: `~/Library/Logs/Agent Lab/agent-lab-api.log`

### Q. Cursor bridge 연결 실패

- `CURSOR_SDK_BRIDGE_BIN` 절대 경로 설정
- stale env 제거: `CURSOR_SDK_BRIDGE_URL=`, `CURSOR_SDK_BRIDGE_TOKEN=`
- Health 패널 **재연결** 버튼 (`POST /api/health/reconnect-cursor`)

### Q. 전송 버튼이 비활성

- 에이전트 1명 이상 선택했는지
- ♾️ 풀팀 **호출 확인** 체크했는지
- 미해결 **이의(Objection)** 이 있는지
- **다른 폴더…** 선택 후 경로 미선택인지
- Preflight 실패 — 헤더/Composer 빨간 안내 확인

### Q. plan이 안 바뀜

- Plan 탭 **전송 시 plan 갱신**이 꺼져 있으면 discuss만 → **Plan 탭 → 지금 정리**
- Scribe 실패 시 Plan 탭 **plan 알림** 확인

### Q. 합의(♾️)가 끝나지 않음

- Transcript에서 `이의 없습니다` 나올 때까지 반복 (시간 소요)
- Tasks **동의 부족** 할 일 해소
- **효율** 모드로 상한 축소 가능

### Q. 실행 승인이 막힘

- Review 탭 Pending 확인
- plan 스냅샷 승인 여부
- Objection 미해소
- worktree unavailable / base branch dirty → Review 배너 메시지 확인

### Q. Goal loop가 동작하지 않음

- `.env`에 `AGENT_LAB_GOAL_LOOP=1` 설정 후 API 재시작
- `/goal-check`가 disabled면 env 미설정
- mock Oracle: 목표에 `` `리터럴` `` 포함 또는 키워드 휴리스틱

### Q. OpenAI `insufficient_quota`

ChatGPT Plus(`codex login`) ≠ Platform API 키. `AGENT_LAB_PROVIDER=codex` 사용.

### Q. 실행이 멈춘 것 같음

- **■ 중지** 또는 `/stop`
- Command palette → **Release run lock**
- Inspector **Run** → 잠금 해제

---

## 9. 용어 사전 (Glossary)

| 용어 | 뜻 |
|------|-----|
| **Session** | 주제 하나에 대한 작업 단위 (폴더 하나) |
| **Turn / 턴** | Human 메시지 1회 + 그에 대한 에이전트 라운드 전체 |
| **턴 요약** | `[human synthesis — 턴 요약]` — ♾️ 또는 분석 3+ R1 에이전트 턴 종료 후 |
| **Round / 라운드** | 같은 턴 안 에이전트 웨이브 (R1, R2, …) |
| **specialist / 분업** | R1 Codex+Claude → R2 Cursor 비대칭 라운드 프로필 |
| **3자 룸 (Room)** | Cursor + Codex + Claude 병렬·순차 토론 (기본) |
| **Transcript** | UI上的 대화 로그 탭 |
| **Scribe** | plan.md를 쓰는 정리 에이전트 |
| **plan.md** | 세션의 공유 기획·실행 문서 |
| **Dry-run** | 실제 반영 전 worktree에서 미리 실행 |
| **Worktree** | git 임시 작업 트리 — main을 오염시키지 않음 |
| **Merge 승인** | Human이 diff 검토 후 main에 병합 |
| **Oracle** | 목표·실행 결과 자동 검증 (Goal loop / Execute verify) |
| **ENDORSE / 동의** | ♾️에서 할 일·주장에 동의했다는 에이전트 신호 |
| **Objection / 이의** | plan 실행에 대한 에이전트 반대 |
| **Peer channel** | 에이전트끼리만 보는 보조 채널 |
| **Inspector** | 오른쪽 Context/Tasks/Run/Settings 패널 |
| **Provenance** | plan 항목이 대화 몇 번째 줄에서 왔는지 (`L12`) |
| **ContextBundle** | 에이전트에게 넘기는 레이어드 컨텍스트 |
| **Allowlist** | 세션에서 허용된 플러그인/MCP 목록 |
| **Gate** | 조건 충족 전 다음 단계 진행 불가 지점 |
| **Artifact** | 세션 중 생성·저장된 산출물 |

---

## 10. 부록: 이 프로그램이 하지 않는 것

| 하지 않음 | 대신 |
|-----------|------|
| 실거래·프로덕션 배포 자동화 | plan·Review 승인 후 **다른 repo**에서 실행 |
| 무한 자율 에이전트 | 턴·라운드·합의 **상한** |
| Human에게 A/B 선택지 넘기기 | 에이전트끼리 맞추고 Human은 GO·승인만 |
| DB·파이프라인 대체 | 초안·토론·문서화 **연습장** |
| 브로커·DB 비밀번호 저장 | `.env`에는 **API 키·CLI 경로만** |

---

## 부록 A: 클래식 모드 (레거시)

예전 **Planner → Critic → Scribe** 순차 흐름입니다.  
현재 기본·권장은 **3자 룸(Room)** 입니다. 새 작업은 Room을 사용하세요.

클래식 산출물: `topic.txt`, `transcript.md`, `plan.md`, `meta.json`

---

## 부록 B: CLI로 실행

```bash
python -m agent_lab run "주제"
```

앱과 **같은 `sessions/` 폴더**를 사용하므로 혼용 가능합니다.

---

## 부록 C: 더 읽을 문서

| 문서 | 내용 |
|------|------|
| [developer-agent-console.md](./developer-agent-console.md) | UI 레이아웃·탭 정책 |
| [04-multi-agent-room.md](./04-multi-agent-room.md) | 룸 백엔드·컨텍스트·합의 |
| [05-room-agent-roles.md](./05-room-agent-roles.md) | 에이전트 역할 상세 |
| [GOAL-LOOP.md](./GOAL-LOOP.md) | 세션 목표 Oracle |
| [EXECUTE-WORKTREE-REFORM.md](./EXECUTE-WORKTREE-REFORM.md) | worktree execute 설계 |
| [STABILITY.md](./STABILITY.md) | 포트·설정·CI·운영 |
| [PLUGIN-DISCOVERY.md](./PLUGIN-DISCOVERY.md) | 플러그인·슬래시 discovery |
| [03-workflow.md](./03-workflow.md) | 단계별 사용 워크플로 |

---

## 부록 D: 권장 사용 시나리오

### A — “주제만 던지고 의견 듣기”

1. 새 Session → **분석** → 에이전트 2~3명
2. Plan 탭 **전송 시 plan 갱신** OFF → Transcript만 2~3턴

### B — “대화 끝나고 기획서 만들기”

1. 시나리오 A로 토론
2. Plan 탭 → **지금 정리** → 부족한 점 추가 질문 → 다시 **지금 정리**

### C — “합의까지 맞추기”

1. **♾️** → 쟁점 질문
2. Tasks **동의**·blocker 확인 → 합의 후 Plan 확인

### D — “plan대로 코드 수정”

1. plan `## 지금 실행` 확인
2. **Review** → dry-run → diff → **Merge 승인**
3. Tasks **완료** 처리

---

*이 설명서는 코드베이스(`web/src/components/RoomChat.tsx`, `web/src/utils/taskBarCopy.ts`, `web/src/utils/turnProfile.ts`, `src/agent_lab/room_team_orchestration.py` 등)를 기준으로 작성되었습니다. UI가 바뀌면 `docs/developer-agent-console.md`와 함께 갱신하세요.*
