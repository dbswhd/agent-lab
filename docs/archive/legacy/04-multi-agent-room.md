# 3자 룸 — Cursor · Codex · Claude

> **Legacy doc (Tier 4)** — Room overview. **Canonical:** [USER-GUIDE.md](./USER-GUIDE.md) §9 · [ROOM-REINFORCEMENT.md](./ROOM-REINFORCEMENT.md)

> 통제 워크플로: [01-CONTROLLED-WORKFLOW-SYSTEM.md](./01-CONTROLLED-WORKFLOW-SYSTEM.md)  
> UI: Figma **Mac & iOS UI Kit** (Messages / system colors)

---

## 1. 무엇이 달라졌나

| | 클래식 (레거시) | **3자 룸** (기본) |
|---|--------|------------------|
| 흐름 | Planner → Critic → Scribe (순차) | **Cursor + Codex + Claude** (라운드 1 병렬, 라운드 2+ 순차) → plan 합성 |
| 백엔드 | codex / openai / anthropic 중 1개 | **에이전트 3명 각자** |
| 저장 | transcript.md | **chat.jsonl** + **run.json** (`turns[]`) + **plan.md** (provenance refs) |

---

## 2. 에이전트 설정

**역할 분담 (상세):** [05-room-agent-roles.md](./05-room-agent-roles.md) — 자기소개·경계·누구에게 무엇을 물을지.  
클래식(레거시) 모드의 Planner/Critic/Scribe와는 **별개**이다.

| 에이전트 | 필요 조건 | 룸에서의 역할 (요약) |
|----------|-----------|----------------------|
| **Cursor** | `CURSOR_API_KEY` + `pip install -e ".[cursor]"` | 레포·파일·UI·빌드 — **실행·다음 편집** |
| **Codex** | `codex login`, `CODEX_BIN` (앱은 PATH 보강) | 분해·순서·검증·완료 기준 — **끝까지 밀기** |
| **Claude** | `claude login`, `CLAUDE_BIN` (앱은 PATH 보강) | 맹점·리스크·설명·요약 — **두 번째 의견·리뷰** |

`.env` 예:

```env
AGENT_LAB_PROVIDER=codex
CODEX_BIN=/Users/you/.nvm/versions/node/v24.13.1/bin/codex
CLAUDE_BIN=/Users/you/.nvm/versions/node/v24.13.1/bin/claude
CURSOR_API_KEY=...
```

---

## 3. 사용 워크플로 (앱)

1. **새 대화** → 상단 **3자 룸** 선택  
2. 참여 칩: Cursor / Codex / Claude (준비된 것만 켜기)  
3. 주제 입력 → **↑** 전송  
4. **1라운드:** 선택한 에이전트가 동시에 첫 답  
5. **2라운드 이상(토론·검토 프로필):** 같은 턴에서 **순차**로 이전 답을 보며 반응 (검토 모드는 claude→codex→cursor 순). 일반 토론은 선택 순서대로 순차  
6. **대화만** 전송하면 `plan.md`는 바뀌지 않음 — **「정리 후 전송」** 또는 **「지금 정리」**로 갱신  
7. 끝나면 **plan.md** 합성(해당 모드일 때) + 왼쪽 목록에 세션 생성  
8. 세션 열기 → **대화** / **plan.md** 탭 · plan의 `chat.jsonl#Ln` 참조는 클릭 시 대화로 점프

CLI:

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from agent_lab.room import run_room
folder, msgs, plan = run_room('주제 테스트')
print(folder, len(msgs), len(plan))
"
```

API: `POST /api/room/runs` (SSE) — `agent_round_start`, `agent_start`, `agent_done`+`content`, `scribe_*`, `complete`  
Form: `agent_rounds` (토론 프로필 기본 `2`, 빠른 `1`, 검토 시 최소 `2`, 최대 4) — 같은 턴 안에서 에이전트 웨이브 수. 라운드 2+는 서버에서 **항상 순차** 실행된다.  
**컨텍스트 미리보기:** `POST /api/room/context-preview` — payload + `meta` (레이어별 길이, `budget_pct`, `trim_level`, pin/dedupe, `line_range`).  
**마지막 턴:** `run.json` → `last_turn.context.agents[]` + `summary` (UI 컨텍스트 사이드바 「마지막 턴」).  
**한도:** `GET /api/health` → `context.agent` / `scribe` / `consensus`.

### ContextBundle (에이전트 user payload)

| 레이어 | 내용 |
|--------|------|
| `[고정 constraints]` | 권한, Human gates, plan 합의 발췌, status tags |
| `[plan 미결]` | stale, 미결 bullet |
| `[최근 N턴]` | trim된 스레드 (**현재 Human 턴 pin**; 기본 `chat.jsonl#L{n}` 번호) |
| `[이번 턴 · 동료 발화]` | R2+ / 동료 있을 때만 — **recent에서 동일 줄 dedupe** |
| guidance + connect hint | 권장 문장만 (형식 강제 없음) |

**자유 토론** (`consensus_mode`): R1 병렬 후 앵커(마지막 실질 제안)에 대해 나머지 에이전트가 순차로 응답. 이의 없으면 첫 줄에만 `이의 없습니다` → 전원 동의 시 `consensus_reached`. 상한: `AGENT_LAB_MAX_CONSENSUS_ROUNDS` (12), `AGENT_LAB_MAX_CONSENSUS_CALLS` (30).

Composer는 전송 전 예상 에이전트 호출 수를 표시한다. 3-agent `분업` / `♾️` 풀 팀 실행은 체크박스 확인 전까지 전송 버튼이 비활성화된다.

**효율 모드** (`efficiency_mode` / Composer **효율 토글** · 모든 응답 방식에 적용 / `AGENT_LAB_EFFICIENCY=1`):

| 항목 | 동작 |
|------|------|
| Pin cap | 현재 Human 턴 pin을 메시지 수·문자 예산(`PIN_BUDGET_PCT`) 안으로 축소 |
| Recent | `AGENT_LAB_EFFICIENCY_RECENT_TURNS` (기본 4) |
| plan/constraints | agreed·open bullet 상한 축소 |
| 응답 유도 | payload에 800자 목표 guidance |
| 자유 토론 합의 | 2라운드+ 호출은 **slim payload** (Human 질문 요약 + 앵커 follow_up만) |
| 합의 상한 | `EFFICIENCY_CONSENSUS_*` (기본 8라운드 / 20호출) |

---

## 4. 통제 워크플로 (현재 구현 범위)

| 원칙 | 구현 |
|------|------|
| 명시적 입력 | `topic` + chat.jsonl |
| 최소 권한 | 텍스트만, 도구 없음 (`T0`) |
| 산출물 중심 | `plan.md` + `run.json` (`run_schema_version`, `turns[]`) |
| 재현성 | `chat.jsonl` 원문 + `plan.md`의 `chat.jsonl#L<n>` provenance 참조 |
| 병렬 상한 | 최대 3 에이전트 × `agent_rounds`(토론 UI 기본 2, 빠른 1, 검토 최소 2, 최대 4) / 사용자 메시지 1회 · **라운드 2+는 순차** |

**다음 단계** (01 문서 Phase 2+): Clarifier gate, human approval, follow-up 메시지, YAML 워크플로 엔진.

---

## 5. Figma (Mac / iOS Kit)

| 화면 | Kit 참고 | 코드 토큰 / 스타일 훅 |
|------|----------|-----------------------|
| 말풍선 | iOS **Messages** — sent blue, received gray | `--color-bubble-sent`, `--color-bubble-received`, `--radius-bubble` |
| 목록 | **Messages** sidebar / IG DM row height | `--chat-list-width`, `.session-list` |
| 칩 | iOS **segmented** / capsule buttons | `--mac-segmented-bg`, `--radius-pill`, `.mac-segmented` |
| 에이전트 색 | Cursor blue, Codex purple, Claude orange | `--color-agent-cursor`, `--color-agent-codex`, `--color-agent-claude` |
| 작업 바 | macOS inset panel, readable body | `--lg-panel-surface`, `--mac-separator`, `.taskbar`, `.taskbar-dock` |
| 턴 요약 | compact document summary | `--space-sm`, `--text-caption`, `.chat-line--synthesis` |
| 확인 질문 | warning banner | `--mac-system-orange`, `.clarifier-banner` |

Community에서 **Apple iOS 18 UI Kit** 또는 **macOS Sonoma** Duplicate → `tokens.css` Variables 동기화.

색상 값은 `tokens.css`를 단일 기준으로 사용한다. Figma 파일에 hex를 별도로
복제하지 말고 위 변수 이름으로 연결한다.

---

## 6. 파일

| 경로 | 내용 |
|------|------|
| `docs/05-room-agent-roles.md` | 3자 룸 역할·경계·체크리스트 |
| `src/agent_lab/room.py` | 라운드 1 병렬 / 라운드 2+ 순차 오케스트레이션 |
| `src/agent_lab/context_bundle.py` | **ContextBundle** — 레이어 조립·`render()`·trim 메타 |
| `src/agent_lab/room_context.py` | constraints·peer·**Human 턴 pin**·peer/recent **dedupe** |
| `src/agent_lab/agents/prompts.py` | 룸 런타임 system prompt (요약) |
| `src/agent_lab/agents/` | cursor / codex / claude |
| `workflows/room.parallel.yaml` | 워크플로 계약 (설정) |
| `sessions/.../chat.jsonl` | 메시지 로그 |
