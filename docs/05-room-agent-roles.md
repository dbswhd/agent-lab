# Room 에이전트 역할

Agent Lab Room 에이전트 역할과 **Plan toggle OFF/ON** 턴 규칙.  
**턴 모드 계약 (preset · profile · legacy):** [TURN-MODES.md](./TURN-MODES.md)  
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

## Room preset (Composer)

| Preset | UI | turn_profile | Plan toggle | consensus |
|--------|-----|--------------|-------------|-----------|
| **fast** | 빠른 | `quick` (리드 1명) | **잠금 OFF** | OFF |
| **supervisor** | 감독 | `loop` | **잠금 ON** | ON |

세부·Plan OFF/ON 차이: [TURN-MODES.md](./TURN-MODES.md) · [USER-GUIDE.md §6](./USER-GUIDE.md).

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

## Plan toggle OFF vs ON (Compose mode)

Composer **Plan** 체크박스 (`ComposerPlanToggle`). OFF → API `mode: discuss`, ON → `mode: plan`.

| | Plan OFF | Plan ON |
|---|----------|---------|
| Scribe | **안 함** | 턴 후 `plan.md` 갱신 |
| Codex / Claude | read-only overlay (write off) | tools/write per permissions |
| Kimi Work | read-only — 검증·`[PROPOSED:]`만 | 동일 (execute 주장 금지) |
| Cursor | tools 유지 (execute는 별도 gate) | tools 유지 |
| receipt | `discuss_saved` | `plan_updated` |

전체 파이프라인·잠금 조건: [TURN-MODES.md §4](./TURN-MODES.md).

**에이전트 규칙:** `[고정 constraints]`에 이미 턴 정책이 있다. 「discuss/plan 모드입니다」 **선언 금지** — 바로 내용으로 답한다.

**Plan OFF 턴:**

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
