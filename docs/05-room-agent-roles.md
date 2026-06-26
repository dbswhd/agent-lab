# Room 에이전트 역할

Agent Lab Room에 참여할 수 있는 에이전트와 **discuss / plan** 턴 규칙 요약.  
런타임 프롬프트 SSOT: `src/agent_lab/agents/prompts.py` · payload 조립: `context_bundle.py` · 권한: `agent_permissions.py`.

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

| Preset | UI | turn_profile | plan 갱신 | consensus |
|--------|-----|--------------|-----------|-----------|
| **fast** | 빠른 | `quick` (리드 1명) | OFF | OFF |
| **supervisor** | 감독 | `loop` | ON | ON |

세부: [USER-GUIDE.md §6.2–6.4](./USER-GUIDE.md).

### Fast preset — orchestrator Inbox skip (discuss lane)

**제품 가정 (현재):** Fast는 **discuss lane에서** `clarify → plan → execute` 오케스트레이션을 쓰지 않는다.  
즉답 Q&A(리드 1명, plan OFF, consensus OFF)가 목표이며, Human gate는 **execute lane**과 **수동 Inbox**에만 남긴다.

**향후 (문서화 필수):** Execute에서도 plan-workflow(`CLARIFY` → `plan.md` → Human approve → worktree)를 쓰게 될 수 있다.  
그때는 `is_fast_room_session()` 스킵 범위를 **재검토**해야 한다 — discuss harvest/MCP는 계속 OFF일 수 있지만, **execute lane inbox MCP**·plan CLARIFY 연동은 Fast에서도 켤 수 있음.

**판별 SSOT:** `room_preset.is_fast_room_session(run_meta)` — `room_preset=fast` 또는 `user_mode=quick` + `plan_intent=none`.

```
Fast discuss
  ├─ harvest 3종          → 전부 스킵
  ├─ discuss inbox MCP    → 스킵
  └─ plan CLARIFY inbox   → 스킵
Fast execute              → inbox MCP 유지 (Human GO)
```

#### 1. build harvest — `harvest_build_proposal`

| | |
|---|---|
| **언제** | discuss 턴 종료 후 (`room_session_persist`), `plan.md`에 `## 지금 실행` recommended action이 있을 때 |
| **하는 일** | Human Inbox **build** 항목 생성 — UI: 「Plan updated — review before GO」, `Execute blocked pending build` |
| **Fast** | **스킵** — stale `plan.md`만으로 자동 GO gate가 뜨지 않음 |
| **코드** | `inbox_harvest.harvest_build_proposal` |

Supervisor/discuss에서는 T-B1~B3 gate 통과 시 orchestrator가 실행 예고를 Inbox에 올린다. Fast는 이 자동 surfacing을 하지 않는다.

#### 2. discuss harvest — `harvest_discuss_questions` · `harvest_clarifier_questions`

| | |
|---|---|
| **언제** | discuss 턴 종료 후; clarifier는 엔진/파이프라인 질문 목록이 있을 때 |
| **하는 일** | Inbox **question** 항목 — T-Q0(Clarifier), T-Q1(FORK), T-Q2(plan OPEN bullet) 등. sync mode면 discuss auto-round **pause** |
| **Fast** | **스킵** — 토론 harvest·clarifier→Inbox 경로 없음 |
| **코드** | `inbox_harvest.harvest_discuss_questions`, `harvest_clarifier_questions` |

CHALLENGE/AMEND는 Inbox가 아니라 `room_objections`에 남는다(변경 없음).

#### 3. discuss inbox MCP — `discuss_inbox_mcp_enabled` · Kimi bridge

| | |
|---|---|
| **언제** | Room이 에이전트 invoke 시 `inbox_mcp=True`를 넘길 때 |
| **하는 일** | Cursor/Codex/Claude: stdio MCP `ask_human` / `propose_build`. Kimi Work: daimon tool-call을 Inbox에 연결하고 Human resolve까지 **블로킹** |
| **Fast** | **스킵** — discuss 턴에 inbox 도구·bridge·프롬프트 addon 미부착. 에이전트는 채팅 본문으로만 Human과 대화 |
| **코드** | `cursor_inbox_mcp.discuss_inbox_mcp_enabled`, `kimi_work_provider.respond` (`use_inbox_mcp`), `room_agent_invoke` |

Execute lane(`plan_execute`, worktree implement)은 **별도 gate** — Fast에서도 `AGENT_LAB_EXECUTE_INBOX` 등이 켜져 있으면 implement GO용 inbox MCP는 **유지**.

#### 4. plan-workflow CLARIFY inbox — `plan_workflow_wants_inbox_mcp`

| | |
|---|---|
| **언제** | `AGENT_LAB_PLAN_WORKFLOW` FSM이 `CLARIFY`/`PEER_REVIEW` 등 plan gate phase일 때 |
| **하는 일** | plan clarify 질문을 Inbox + `ask_human` MCP로 올림 — full **clarify → plan → execute**의 plan 구간 |
| **Fast** | **스킵** — Fast는 plan-workflow inbox를 discuss에 붙이지 않음 (현재 Fast는 plan FSM 경로 자체를 쓰지 않는다고 가정) |
| **코드** | `plan_workflow.plan_workflow_wants_inbox_mcp` |

#### 5. Fast에서도 Human gate가 남는 경우

| 경로 | 설명 |
|------|------|
| **Execute lane** | worktree dry-run / implement — `propose_build`, merge approve, Oracle |
| **수동 Inbox** | Human·gateway·`/question` |
| **기존 pending** | 스킵 전에 쌓인 `run.json` `human_inbox[]` — resolve 필요 |
| **Supervisor로 전환** | 이후 턴부터 harvest/MCP 정상 동작 |

**테스트:** `tests/test_fast_inbox_skip.py`, `tests/test_inbox_build.py::test_fast_room_skips_build_harvest`  
**Inbox 전체:** [HUMAN-INBOX.md §5.4](./HUMAN-INBOX.md) · **플로우 대비:** [FLOW.md §2.1](./FLOW.md)

## Discuss vs plan (Compose mode)

Human이 Work에서 「전송 시 plan 갱신」을 켜면 **plan** 턴, 끄면 **discuss** 턴.

| | discuss | plan |
|---|---------|------|
| Scribe | **안 함** | 턴 후 `plan.md` 갱신 |
| Codex / Claude | read-only overlay (write off) | tools/write per permissions |
| Kimi Work | read-only — 검증·`[PROPOSED:]`만 | 동일 (execute 주장 금지) |
| Cursor | tools 유지 (execute는 별도 gate) | tools 유지 |
| receipt | `discuss_saved` | `plan_updated` |

**에이전트 규칙:** `[고정 constraints]`에 이미 턴 정책이 있다. 답변 첫 줄에 「discuss/plan 모드입니다」처럼 **모드를 선언하지 말고** 바로 내용으로 답한다.

Discuss 턴에서:

- 레포는 **Read/Grep/도구로 검증** 후 주장
- 파일 수정·execute 완료 **주장 금지** — 실행 제안은 `[PROPOSED: …]` 텍스트
- Loop consensus R2+에서는 `agent-envelope` speech act (`ENDORSE`, `CHALLENGE`, …)

## Kimi Work peer

- 세션 `session_folder` ↔ daimon `conversationKey` 매핑 (`kimi_work.json`)
- workspace root는 session binding (`kimi_work_workspace`)
- Human Inbox (`ask_human` / `propose_build`) — 방향·GO gate는 inbox 도구, plain prose fork 금지
- Bridge warm: API startup `warm_bridge`, probe TTL `AGENT_LAB_KIMI_WORK_PROBE_TTL_S`

## Human vs peer

- **Peer끼리** scope·접근·파일·검증 순서는 envelope + `[PROPOSED:]`로 조율
- **Human**에게만: GO gate, 예산, prod 파괴, secrets, 해결 불가 fork
