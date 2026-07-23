# Room 에이전트 역할

Agent Lab Room 에이전트 역할과 topic-only Composer·Decision Queue 턴 규칙.
**턴 모드 호환·history:** [TURN-MODES.md](./TURN-MODES.md) (Plan toggle는 archive/history material이며 현재 Composer control이 아님)
런타임 프롬프트: `src/agent_lab/agents/prompts.py` · payload: `context/bundle.py` · 권한: `agent/permissions.py`.

## 참여 에이전트

| ID | 표시명 | 런타임 | 한 줄 역할 |
|----|--------|--------|------------|
| **cursor** | Cursor | Cursor SDK (로컬 tools) | 레포·파일·UI·패치 — execute 주력 |
| **codex** | Codex | Codex CLI | 분해·순서·검증·완료 기준 |
| **claude** | Claude | Claude Code CLI | 맹점·리스크·설명 · Scribe(기본) |
| **kimi_work** | Kimi Work | daimon Control WS | Work quota peer — 레포 검증·대안·약한 가정 도전 |
| **kimi** | Kimi | Kimi API | API 폴백 (Work bridge 불가 시) |
| **local** | Local | mock / stub | CI·오프라인 대체 |

기본 3자 Room은 `cursor` + `codex` + `claude`. `/model`로 composition 변경 가능. Kimi Work는 Loop·supervisor preset에서 peer로 자주 포함.

## Room preset (internal compatibility)

Composer에는 preset picker가 없다. 아래 preset은 API/run metadata와 dogfood 기본값을 위한 내부 호환 축이다.

| Preset | internal turn_profile | Composer exposure | consensus |
|--------|-----------------------|-------------------|-----------|
| **fast** | `quick` (리드 1명) | topic-only; picker 없음 | OFF |
| **supervisor** | `loop` | topic-only; picker 없음 (dogfood 기본) | ON |

세부 호환 매핑은 [TURN-MODES.md](./TURN-MODES.md) history와 [USER-GUIDE.md §6](./USER-GUIDE.md)를 따른다.

> **레거시 UI (제거됨):** quick/team/loop·discuss/analyze/review/free segmented picker. API는 `discuss`→team, `review`/`free`→loop 등 **별칭만** 수용 — [TURN-MODES.md §3](./TURN-MODES.md).

### Fast preset — orchestrator Inbox skip (discuss lane)

> **MCP-first 방향** (agent MCP SSOT, harvest deprecate, Scribe/plan 분리, Phase A–E) → [MCP-FIRST-INBOX.md](./MCP-FIRST-INBOX.md).  
> **Orchestrator harvest:** default **OFF** — `AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST=0`; legacy `=1`. Fast는 항상 스킵.  
> **제품 가정·향후 execute plan-workflow·재검토 체크리스트**도 위 문서 §5·§8 — 여기서는 **트리거별 스킵 표**만 유지.

**판별 SSOT:** `room_preset.is_fast_room_session(run_meta)` — `room_preset=fast` 또는 `user_mode=quick` + `plan_intent=none`.

```
Fast discuss
  ├─ harvest 3종          → 전부 스킵
  ├─ discuss inbox MCP    → team lead만 (ask_human / propose_build)
  └─ plan CLARIFY inbox   → 스킵
Fast execute              → inbox MCP 유지 (Human GO)
```

#### 1. build harvest — `harvest_build_proposal`

| | |
|---|---|
| **언제** | discuss 턴 종료 후 (`room_session_persist`), `plan.md`에 `## 지금 실행` recommended action이 있을 때 |
| **하는 일** | Human Inbox **build** 항목 생성 — UI: 「Plan updated — review before GO」, `Execute blocked pending build` |
| **Fast** | **스킵** |
| **코드** | `inbox_harvest.harvest_build_proposal` |

Supervisor: T-B1~B3 통과 시 orchestrator가 실행 예고를 Inbox에 올린다. Fast는 스킵.

#### 2. discuss harvest — `harvest_discuss_questions` · `harvest_clarifier_questions`

| | |
|---|---|
| **언제** | discuss 턴 종료 후; clarifier는 엔진/파이프라인 질문 목록이 있을 때 |
| **하는 일** | Inbox **question** — T-Q0(Clarifier), T-Q1(FORK), T-Q2(plan OPEN bullet) 등. sync mode면 discuss auto-round **pause** |
| **Fast** | **스킵** |
| **코드** | `inbox_harvest.harvest_discuss_questions`, `harvest_clarifier_questions` |

CHALLENGE/AMEND는 Inbox가 아니라 `room_objections`에 남는다(변경 없음).

#### 3. discuss inbox MCP — `discuss_inbox_mcp_enabled` · Kimi bridge

| | |
|---|---|
| **언제** | Room이 에이전트 invoke 시 `inbox_mcp=True`를 넘길 때 |
| **하는 일** | Cursor/Codex/Claude: stdio MCP `ask_human` / `propose_build`. Kimi Work: daimon tool-call → Inbox + Human resolve까지 **블로킹** |
| **Fast** | **스킵** — team lead는 MCP `ask_human` / `propose_build` **유지** |
| **코드** | `cursor_inbox_mcp.discuss_inbox_mcp_enabled`, `kimi_work_provider.respond`, `room_agent_invoke` |

Execute lane은 **별도 gate** — Fast에서도 implement GO용 inbox MCP **유지**.

#### 4. plan-workflow CLARIFY inbox — `plan_workflow_wants_inbox_mcp`

| | |
|---|---|
| **언제** | `AGENT_LAB_PLAN_WORKFLOW` FSM이 `CLARIFY`/`PEER_REVIEW` 등 plan gate phase일 때 |
| **하는 일** | plan clarify 질문을 Inbox + `ask_human` MCP로 올림 |
| **Fast** | **스킵** |
| **코드** | `plan_workflow.plan_workflow_wants_inbox_mcp` |

#### 5. Fast에서도 Human gate가 남는 경우

| 경로 | 설명 |
|------|------|
| **Execute lane** | worktree dry-run / implement — `propose_build`, merge approve, Oracle |
| **수동 Inbox** | Human·gateway·`/question` |
| **기존 pending** | 스킵 전에 쌓인 `run.json` `human_inbox[]` |
| **Supervisor로 전환** | 이후 턴부터 harvest/MCP 정상 동작 |

**테스트:** `tests/test_fast_inbox_skip.py` · **Inbox RFC:** [HUMAN-INBOX.md §5.4](./HUMAN-INBOX.md) · **플로우:** [FLOW.md §2.1](./FLOW.md)

## Topic-only Composer와 Decision Queue

현재 Composer에는 Plan 체크박스나 Plan picker가 없다. 사용자는 topic을 입력하고, TurnContract·TurnPolicy가 risk/intent에 따라 plan/execute effect를 라우팅한다. Human action은 Composer 위 Decision Queue에서 우선순위대로 한 번에 하나만 처리한다.

Decision Queue precedence: `plan_approval → execute_queue → consensus → inbox → clarify → work`. 내부 `work` lane은 실행·결과·evidence를 렌더링하지만 제거된 Work navigation tab이 아니다. Visible workspace tabs는 Transcript · Diff · Background · Files · Preview · Terminal이고 Inspector는 Overview · Tools다.

전체 파이프라인·잠금 조건의 예전 Plan OFF/ON 설명은 [TURN-MODES.md §4](./TURN-MODES.md)의 history로 보존한다.

**에이전트 규칙:** `[고정 constraints]`에 이미 턴 정책이 있다. 「discuss/plan 모드입니다」 **선언 금지** — 바로 내용으로 답한다.

**Legacy discuss-policy note (history):**

- 레포 **Read/Grep/도구로 검증** 후 주장
- 파일 수정·execute 완료 **주장 금지** — `[PROPOSED: …]` 텍스트만
- Loop consensus R2+: `agent-envelope` (`ENDORSE`, `CHALLENGE`, …)

## Kimi Work peer

- 세션 `session_folder` ↔ daimon `conversationKey` 매핑 (`kimi_work.json`)
- workspace root는 session binding (`kimi_work_workspace`)
- Human Inbox (`ask_human` / `propose_build`) — MCP-first 방향: [MCP-FIRST-INBOX.md](./MCP-FIRST-INBOX.md); discuss gate는 inbox 도구, plain prose fork 금지
- Bridge warm: API startup `warm_bridge`, probe TTL `AGENT_LAB_KIMI_WORK_PROBE_TTL_S`

## Human vs peer

- **Peer끼리** scope·접근·파일·검증 순서는 envelope + `[PROPOSED:]`로 조율
- **Human**에게만: GO gate, 예산, prod 파괴, secrets, 해결 불가 fork
