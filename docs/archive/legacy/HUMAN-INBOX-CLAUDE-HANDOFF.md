# Human Inbox — Claude Code 인수인계 (M3+)

> **Handoff doc** — complements [HUMAN-INBOX.md](../../HUMAN-INBOX.md). **Index:** [README.md](../../README.md)  
> **전제:** M1·M2 execute path shipped on `main`. **설계 RFC:** [HUMAN-INBOX.md](../../HUMAN-INBOX.md) §3.4, §4.6.  
> **경로 (2026-06):** 본문 `room.py` / `plan_execute.py` → **`room/turn_flow.py`** (`continue_room_round`), **`plan/execute.py`**. Living SSOT: [PACKAGING-BASELINE.md](./PACKAGING-BASELINE.md).

---

## Shipped (M1 + M2) — 건드리지 않을 것

| 영역 | 경로 | 동작 |
|------|------|------|
| Inbox core | `src/agent_lab/human_inbox.py` | `human_inbox[]`, resolve, supersede, wait, tool result builders |
| MCP stdio | `src/agent_lab/inbox_mcp_server.py` | `ask_human`, `propose_build` → blocking poll |
| Cursor wiring | `src/agent_lab/cursor_inbox_mcp.py`, `agents/cursor_agent.py` | `AgentOptions.mcp_servers` |
| Execute | `plan/execute.py` (shim: `plan_execute.py`) | Cursor dry-run: `inbox_mcp=True`, plan-first prompt |
| API | `app/server/routers/human_inbox.py` | GET inbox, POST items, POST resolve, POST supersede |
| UI | `web/src/components/HumanInboxPanel.tsx`, `RoomChat.tsx` | Composer 위 Inbox, polling |
| Discuss supersede | `room/turn_flow.py` `continue_room_round` | 새 Human send → pending supersede |
| Tests | `tests/test_human_inbox.py` | 6 tests |

**Env**

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENT_LAB_EXECUTE_INBOX` | `1` | Cursor dry-run MCP Inbox |
| `AGENT_LAB_INBOX_TIMEOUT_SEC` | `1800` | MCP wait before timeout tool result |
| `AGENT_LAB_INBOX_POLL_SEC` | `0.25` | MCP server poll interval |

**수동 검증**

```bash
# API smoke
curl -s localhost:8765/api/sessions/{session_id}/inbox | jq .

# manual question item
curl -X POST localhost:8765/api/sessions/{session_id}/inbox/items \
  -H 'Content-Type: application/json' \
  -d '{"kind":"question","prompt":"Scope?","options":[{"id":"a","label":"A"},{"id":"b","label":"B"}]}'
```

Execute E2E: PlanExecute dry-run (Cursor) → agent `ask_human` / `propose_build` → Human Inbox → tool result → session continues.

---

## 당신(Claude)이 할 일 — 로드맵 순

### M2b — Clarifier → Inbox (Discuss, 작음) ✅ shipped (`8f927e8`)

**목표:** `session_clarifier.py` 첫 턴 질문을 chat prose가 아니라 Inbox question item으로.

| 파일 | 작업 |
|------|------|
| `inbox_harvest.py` | `harvest_clarifier_questions()` — T-Q0 + `harvest_key` dedupe |
| `src/agent_lab/room.py` | clarifier path → inbox items; `complete` SSE `inbox_pending` |
| `web/` | `HumanInboxPanel` + composer **Human Inbox 대기** chip |

**AC:** 주제 짧은 첫 턴 → Inbox에 question 1건 → resolve → `[HUMAN-DECISION:]` → R1 진행.

---

### M3 — Deterministic harvest → Inbox (Discuss 핵심) ✅ shipped

**목표:** R1+R2 후 open issues / envelope CHALLENGE·AMEND → **options 없이** refs·excerpt만 Inbox question.

**하지 말 것:** Facilitator LLM, option invent, execute-style MCP blocking in discuss.

| 파일 | 작업 |
|------|------|
| `src/agent_lab/room.py` | R1+R2 후 harvest hook |
| `src/agent_lab/agent_envelope.py` | envelope ASK / CHALLENGE 파싱 (이미 있으면 연결만) |
| `src/agent_lab/human_inbox.py` | `create_inbox_item` with `options=[]` 허용 or UI freeform — **RFC §5.5: M3까지 options 없음** |
| `web/src/components/HumanInboxPanel.tsx` | options 빈 배열 → freeform/건너뛰기 only |

**트리거 ID:** T-Q1 (harvest), T-Q2 (plan OPEN) — [HUMAN-INBOX.md §5.4](../../HUMAN-INBOX.md)

**AC (M3 core — verify in `tests/test_human_inbox.py`, `inbox_harvest.py`):**

- [x] harvest → Inbox item (prompt + refs, **no options**)
- [x] Facilitator / LLM 합성 **0%**
- [x] resolve → `[HUMAN-DECISION:]` + next discuss turn context

---

### M4 — FORK + Facilitator ✅ shipped · sync pause ✅ shipped

**목표:** `DECISION-FORK` envelope ref-anchored options; Facilitator merge; `AGENT_LAB_INBOX_MODE=sync` pauses consensus debate when pending question.

| 파일 | 작업 |
|------|------|
| `src/agent_lab/agent_envelope.py` | FORK parse |
| 신규 `src/agent_lab/inbox_facilitator.py` (이름 가칭) | 1-call Claude, refs only, no invent |
| `room.py` | pending Inbox → **discuss 전원 pause** (sync checkpoint) |

**AC:** FORK refs → Facilitator → Inbox options (anchored) → Human resolve → unpause.

---

### M5 — Discuss Build ↔ execute 연동 ✅ shipped

**트리거 위치 (확정):** `room.py` turn-harvest 블록 **(a)** — question/objection harvest와 동일. 별도 orchestrator (b) 없음.

**목표:** T-B1–B4 gates → `append_inbox_item(kind="build", source="orchestrator")` → Human GO → `runPlanDryRun` → execute lane. execute `propose_build`와 **게이트 2개** 유지 (§3.4.4).

| 파일 | 작업 |
|------|------|
| `room.py` / orchestrator | T-B1–B4 → `create_inbox_item(kind="build", source="orchestrator")` |
| `plan_execute.py` | discuss GO 후 dry-run 진입 시 plan phase fast-path (§3.4.3) |
| `web/` | Discuss build card vs execute `propose_build` 구분 표시 (optional) |

---

### M6 — Codex executor MCP bridge ✅ shipped (`046c1e4`)

**목표:** Cursor와 **동일 Inbox contract**; Codex JSONL tool events → Inbox.

| 파일 | 작업 |
|------|------|
| `cursor_inbox_mcp.py` | `inbox_mcp_stdio_spec()`, `build_codex_inbox_mcp_config_args()`, `execute_inbox_mcp_enabled()` |
| `src/agent_lab/codex_cli.py` | MCP attach via `-c`, `mcp_tool_call` JSONL labels |
| `src/agent_lab/agents/codex_agent.py` | `session_folder` / `inbox_mcp` params |
| `plan_execute.py` | `inbox_mcp` for codex executor (dry-run) |

**주의:** Cursor MCP “미지원”은 **사실 오류** — Codex 쪽 갭은 M6에서 닫힘. Live E2E는 Codex CLI + auth 필요.

---

## 아직 없는 것 (선택 개선)

| Gap | 상태 |
|-----|------|
| Room SSE `inbox_pending` + Composer 배지 | ✅ `8f927e8` |
| Build card plan drift (`plan_revision`) | ✅ `8f927e8` |
| clarifier + harvest dedupe (§6.5 ②) | ✅ M2b `8f927e8` |
| `respond_session()` 별도 API | ✅ `cursor_agent` / `codex_agent` — gated multi-prompt (§4.6 E1) |
| Plan phase 별도 `send()` | ✅ `plan_execute` plan-first → GO gate → implement (`8f927e8`+) |
| Live execute E2E (mocked) | ✅ `tests/test_inbox_execute_e2e.py` |
| Live Codex/Cursor CLI E2E | real CLI + auth 필요 |

---

## 아키텍처 상수 (위반 금지)

1. **Execute** = MCP blocking tool result (same session). **Discuss** = post-turn orchestration, **not** inline MCP.
2. **Question + Build** both on **executor session** — no Question-Claude / Build-Cursor split.
3. **Human Inbox** = single Human-facing surface; transcript = debate only.
4. pending **question** blocks **build** item creation (`human_inbox.py` already enforces for MCP/manual).

---

## 테스트

```bash
python -m pytest tests/test_human_inbox.py -q
python -m pytest tests/ -q --ignore=tests/test_goal_loop.py
cd web && npm run build
```

새 테스트: `tests/test_inbox_harvest.py` (M3), `tests/test_inbox_facilitator.py` (M4) 권장.

---

## 커밋 후 브랜치 제안

Claude 작업 시:

```bash
git checkout -b feat/human-inbox-m3-harvest
# M3 only — small PR
```

M3 → M4 → M5 순 **작은 PR**이 리뷰하기 좋음. M6는 execute lane 별 PR.

---

## 관련 문서

- [HUMAN-INBOX.md](../../HUMAN-INBOX.md) — RFC
- [04-multi-agent-room.md](./04-multi-agent-room.md)
- [NOTIFICATION-TAXONOMY.md](../../NOTIFICATION-TAXONOMY.md) — Inbox ≠ NotificationCenter

---

## Claude Code에 붙일 한 줄 프롬프트

```
Read docs/HUMAN-INBOX-CLAUDE-HANDOFF.md and docs/HUMAN-INBOX.md §5. Implement M3 only:
deterministic discuss harvest → Human Inbox question items (refs/excerpt, no LLM Facilitator, no options).
Do not reimplement M1/M2 MCP execute path. Match existing human_inbox.py API and tests style.
```
