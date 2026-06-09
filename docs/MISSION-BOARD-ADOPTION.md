# Mission Board & harness adoption — external refs → Agent Lab

> **Status (2026-06-09):** **P1–P4 shipped** (MB-9…MB-11) · backlog complete. 원칙·백로그는 이 문서 한 곳.  
> **Canonical for:** 아키텍처 원칙 P1–P9, 외부 레퍼런스 흡수, MB-* 구현 큐, AC-MB-* 수용 기준.  
> **Shipped context (읽기만):** [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) · [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md) · [EXECUTE-WORKTREE-REFORM.md](./EXECUTE-WORKTREE-REFORM.md)  
> **인덱스/README·TRACEABILITY 반영:** MB-* 항목이 ✅ shipped 될 때 한꺼번에 갱신.

---

## 1. 한 줄 요약

외부 레퍼런스(OmO, Conductor, Gajae-Code, OpenHarness, Hermes, Paperclip, openai-oauth)에서 **아이디어만** 가져와 `runtime/` + `session/` + Work UI에 흡수한다.  
별 제품·별 org chart·N-agent Room은 만들지 않는다. Paperclip의 **위임·비용**은 **Mission Board**로, 3-agent **peer discuss**는 그대로 둔다.

---

## 2. 아키텍처 원칙 (정식 + 개정)

초안 원칙은 방향이 맞다. 아래는 **검증 가능한 문장**으로 다듬고, 더 나은 표현이 있는 곳은 **개정(Δ)** 으로 표시한다.

### 2.1 불변 원칙 (절대 깨지 않음)

| ID | 원칙 | 검증 기준 |
|----|------|-----------|
| **P1** | **Discuss는 read-only** | Room discuss/plan 턴 중 main working tree **쓰기 금지**; 구현은 execute lane(worktree)만 |
| **P2** | **Room quorum = 고정 3역할** | discuss/consensus 턴의 active agents ⊆ `{cursor, codex, claude}`; 역할 라벨·리드 순서만 가변 |
| **P3** | **Mutation = worktree** | plan action dry-run/merge는 git worktree; non-git action은 `apply` 경로 분리 ([EXECUTE-WORKTREE-REFORM](./EXECUTE-WORKTREE-REFORM.md)) |
| **P4** | **Mission 완료 = Oracle PASS** | `MISSION_DONE`은 mock/live Oracle + open BLOCK 없음; 에이전트 “끝났습니다”만으로 전이 금지 |
| **P5** | **비가역 = Human gate** | merge approve, mission goal 승인, circuit_breaker clear, execute BLOCK override |
| **P6** | **Orchestration = AgentLabRuntime** | cross-lane 전이는 `runtime/` 경유; `room.py`↔`plan_execute` 직접 import 신규 금지 ([RUNTIME-HARNESS-PLAN](./RUNTIME-HARNESS-PLAN.md)) |
| **P7** | **Provenance SSOT** | 상태 주장은 `run.json` / `evidence.jsonl` / `chat.jsonl#L`에만; UI는 mirror |

### 2.2 초안 대비 개정 (Δ)

| 초안 (대화) | 개정 원칙 | 이유 |
|-------------|-----------|------|
| 합의=Room, 에이전트 수 고정 | **P2 Room quorum** + **lane delegation** | scoped `DELEGATE`·execute/repair는 **전체 Room 라운드 없이** 한 역할만 호출 가능 — “3명 토론”과 “1명 실행”을 **lane**으로 분리해야 OmO Atlas·Paperclip task와 맞음 |
| 완료=Oracle verified | **P4** + **turn complete ≠ mission done** | discuss 턴 종료(`discuss_saved`)와 미션 종료(`MISSION_DONE`)를 UI/FSM에서 **항상 구분** (OmO `ulw-loop`는 둘을 섞기 쉬움) |
| 감사=Human gate | **P5 비가역만 Human** + **plan gate 자동** | Momus-lite·adversarial·verify shell은 **자동**; Human은 merge·목표·circuit만 — Paperclip board approval을 **예외 경로**로만 |
| Harness=runtime 흡수 | **P6** + **`session/` persistence** | OpenHarness engine/coordinator·GJC evidence는 **실행 루프가 아니라** `run.json`·`.agent-lab/missions/`에 붙는 **session SSOT** |
| (없음) | **P8 Degraded mode OK** | Mission Loop는 MCP/skills 없이도 FSM 동작 ([MISSION-LOOP-C-OMO](./MISSION-LOOP-C-OMO.md) §Phase 3) — “하네스 완비 전”에도 제품 사용 가능 |
| (없음) | **P9 Budget = governance** | Paperclip 월 토큰 bill이 아니라 **턴/미션/역할 호출 상한** + circuit_breaker — 3-agent 중 **한 역할만 무한** 방지 |

### 2.3 Agent Lab만의 포지션 (독창성)

```
Peer consensus (Room 3-agent)  +  Isolated execute (Conductor worktree)
        +  Verified mission (OmO Oracle)  +  Audited gates (Human + auto plan gate)
        +  Mission Board (Paperclip task/budget, NOT org chart)
```

| 외부 | Agent Lab이 **하지 않는** 것 | Agent Lab이 **대신 하는** 것 |
|------|---------------------------|------------------------------|
| Paperclip | CEO 고용, N-agent 회사 | Mission Board: goal chain + action checkout + **lane** budget |
| OmO | Codex 단일 harness + category로 agent 수 축소 | 고정 3역할 + 턴 프로필(specialist/verified) |
| Conductor | Mac workspace 앱 | 제품 내 worktree + merge Checks |
| Hermes | 20채널 gateway + skill 자동 생성 | 세션 단위 wisdom/evidence + (선택) Inbox |
| GJC | 별도 `gjc` CLI 필수 | H7 external runner + **handoff JSON** (opt-in) |

---

## 3. 레퍼런스 → 흡수 매트릭스

| Source | 가져올 것 | 흡수 위치 | MB ID |
|--------|-----------|-----------|-------|
| **Paperclip** | Task tree, checkout, goal ancestry, heartbeat tick, budget pause | `mission_board`, `turn_budget`, Mission tick | MB-1, MB-2 |
| **OmO** | 5 evidence gates, boulder ledger, plan/execute split | `evidence_gates`, `runtime.boulder` UI | MB-3, MB-4 |
| **Conductor** | Checks SSOT, setup/run per workspace | Work Checks panel, `worktree.yaml` | MB-5, MB-6 |
| **GJC** | interview→plan→goal, tmux handoff | clarifier v2, external handoff | MB-7, MB-8 |
| **OpenHarness** | dry-run readiness, cost per turn | `/api/health/readiness`, Inspector meter | MB-9 |
| **Hermes** | (선택) cross-session recall | wisdom notepad + evidence index | MB-10 |
| **openai-oauth** | (dev) Codex proxy transport | `runtime/adapters/codex` opt-in | MB-11 |

**의도적 제외:** OmO `quick`/`deep` category routing으로 discuss agent 수 축소 — [MISSION-LOOP-C-OMO](./MISSION-LOOP-C-OMO.md) §12.

---

## 4. Mission Board (Paperclip 위임·비용, 3-agent 보존)

### 4.1 Mental model

Paperclip = **회사 OS**. Agent Lab = **한 세션 미션 OS**.

```mermaid
flowchart TB
  subgraph human [Human]
    H[Goal / merge / circuit clear]
  end
  subgraph board [Mission Board — NOT org chart]
    GC[goal_chain]
    CO[action checkout]
    LB[lane: discuss | execute | verify]
  end
  subgraph room [Room — P2 quorum]
    C[cursor]
    X[codex]
    L[claude]
  end
  subgraph lanes [Lanes — delegation without hire]
    D[discuss lane]
    E[execute lane]
    V[verify lane]
  end
  H --> board
  board --> D
  D --> room
  board --> E
  E --> worktree[worktree]
  board --> V
  V --> oracle[Oracle]
```

### 4.2 `run.json` — `mission_board` (제안)

```json
{
  "mission_board": {
    "goal_chain": [
      { "kind": "verified_loop.loop_goal", "ref": "run.json" },
      { "kind": "plan_action", "index": 2, "title": "…" }
    ],
    "checkout": {
      "lane": "execute",
      "action_index": 2,
      "execution_id": "uuid",
      "checked_out_at": "ISO"
    },
    "lane_roles": {
      "discuss": ["cursor", "codex", "claude"],
      "execute_default": "cursor",
      "repair_default": "codex",
      "verify_oracle": "mock|live"
    }
  }
}
```

| 필드 | 규칙 |
|------|------|
| `lane_roles.discuss` | **항상 3역할 집합** (P2); 비어 있으면 기본 3 |
| `checkout.lane` | `execute`일 때 **Room 턴 자동 시작 금지** (Paperclip heartbeat ≠ discuss) |
| `goal_chain` | Paperclip task ancestry; UI에 “왜 이 action인가” 표시 |

### 4.3 Mission tick (Paperclip heartbeat 변형)

| Paperclip | Agent Lab |
|-----------|-----------|
| Agent 주기적 wake | **Mission tick** — `mission_loop.enabled` + autorun만 |
| 큐에서 task 가져옴 | FSM: dequeue → dry-run → (Human merge 대기는 tick 안 함) |
| 비용 보고 | tick마다 `turn_budget` snapshot 갱신 |

**금지:** tick이 `continue_room_round()`를 **Human send 없이** 호출하는 것 (P2·P5).

---

## 5. Turn budget (Paperclip 비용, P9)

### 5.1 카운터 (제안 기본값)

| Key | Scope | Default cap | 초과 시 |
|-----|-------|-------------|---------|
| `agent_calls_per_human_turn` | 1 Human 메시지 | 9 (3 agents × 3 rounds 상한) | 턴 종료 + inbox `turn_budget` |
| `codex_shell_per_turn` | Room codex | env `CODEX_ROOM_MAX_COMMANDS` 연동 | 기존 limit_hit |
| `repairs_per_action` | execute | `max_repair_per_action` (=2) | DISCUSS recovery |
| `mission_iterations` | mission | 20 | `circuit_breaker` |
| `autorun_ticks_per_hour` | mission tick | configurable | pause + inbox |

**원칙:** 한 provider만 막지 않음 — **미션 전체 pause** (circuit_breaker). 역할별 cap은 **warn → soft stop** 단계만.

### 5.2 UI

- Inspector **Cost & budget** (Paperclip Costs 탭 대응, **회사 아님 세션**)
- Work Mission bar에 `budget_pct` (context budget과 별도 — **호출 예산**)

---

## 6. Evidence harness (OmO + GJC)

### 6.1 Five gates 메타 (MB-3)

`executions[].evidence_gates[]`:

| gate | 자동/ Human | SSOT |
|------|-------------|------|
| `plan_reread` | auto | `plan_gate.status == ok` |
| `automated` | auto | `action.verify` exit 0 |
| `manual_merge` | Human | merge approve 이벤트 |
| `adversarial` | auto (mock default) | LC-L4 note |
| `cleanup` | optional | post-merge lint hook |

Oracle VERDICT는 gates와 **함께** 저장; “gate 4개 통과했는데 Oracle FAIL” 감사 가능.

### 6.2 Evidence ledger (MB-4)

경로: `.agent-lab/missions/<session_id>/evidence.jsonl`

```json
{"at":"ISO","phase":"DRY_RUN","kind":"command","cmd":"make test","exit":0,"refs":["chat.jsonl#L42"]}
```

- Run 탭 / Work 타임라인 **append-only** (GJC ultragoal + 사용자 Run log 요청)
- `runtime.boulder` + ledger tail → Resume 카드 (OmO boulder)

---

## 7. Ops readiness (OpenHarness + Conductor)

### 7.1 Readiness (MB-9)

`GET /api/health/readiness?session_id=`

```json
{
  "verdict": "ready|warning|blocked",
  "checks": [
    { "id": "codex_oauth", "ok": true },
    { "id": "cursor_bridge", "ok": false, "next": "Settings → Cursor 재연결" }
  ]
}
```

- 모델 호출 **없음** (OpenHarness `--dry-run` 정신)
- Room send: `blocked` → 409 또는 composer 경고 (정책 플래그)

### 7.2 Merge Checks SSOT (MB-5)

Work / PlanExecute **Checks** 블록 (Conductor Checks 탭):

- git / worktree status
- last `action.verify`
- last Oracle VERDICT
- open BLOCK / objections
- room tasks todos
- **merge_disabled** boolean

### 7.3 Worktree setup (MB-6)

Repo optional `.agent-lab/worktree.yaml`:

```yaml
setup: ["make install"]
verify: ["make test"]
```

action worktree 생성 후 setup; merge 전 verify (Conductor setup/run script 축소판).

---

## 8. External lane (GJC + H7)

### 8.1 Handoff protocol (MB-8)

`external_runner` / `gjc` 종료 시 필수 JSON:

```json
{
  "stopped_cleanly": true,
  "changed_files": ["src/foo.py"],
  "checks": [{"cmd": "make test", "exit": 0}],
  "evidence_summary": "…",
  "risks": []
}
```

Mission Board가 `executions[].external_handoff`에 attach.

### 8.2 Clarifier / interview (MB-7)

`session_clarifier` → plan 모드에서 structured 2–5문; 답변 후 **정상 3-agent discuss** (P2).

---

## 9. 구현 큐 (단일 백로그 — TRACEABILITY/README는 shipped 후 반영)

| Phase | ID | Deliverable | Depends | Next action |
|-------|-----|-------------|---------|-------------|
| **P1** ✅ | MB-9 | Readiness API + Settings/composer hint | health, codex_oauth | `GET /api/health/readiness` — `readiness.py`, `ReadinessComposerBar` |
| **P1** ✅ | MB-2 | `turn_budget` + Inspector meter | run_meta patch | `mission_board.py`, `TurnBudgetSection`, Work status budget bar |
| **P1** ✅ | MB-1 | `mission_board` schema + Work UI | mission_loop | `goal_chain`, `checkout`, `MissionBoardStrip`, runtime snapshot |
| **P2** ✅ | MB-4 | `evidence.jsonl` + Run/Work stream | run events | `evidence_ledger.py`, `EvidenceTimeline`, Run tab |
| **P2** ✅ | MB-5 | Merge Checks SSOT | PlanExecutePanel | `merge_checks.py`, `MergeChecksPanel`, merge CTA gate |
| **P2** ✅ | MB-3 | Five gates on executions | oracle, adversarial | `evidence_gates.py`, `EvidenceGatesPanel` |
| **P3** ✅ | MB-7 | Clarifier interview v2 | session_clarifier | `build_clarifier_interview`, `GET /clarifier-interview`, RoomChat categories |
| **P3** ✅ | MB-6 | `worktree.yaml` hooks | plan_execute worktree | `worktree_hooks.py` setup after create / verify before merge; merge_checks gate |
| **P3** ✅ | MB-8 | External handoff schema | external_runner H7 | `POST …/external-handoff` → `executions[].external_handoff`; Work panel badge |
| **P4** ✅ | MB-10 | Evidence FTS / wisdom index | missions notepad | `wisdom_index.py`, `GET /wisdom-search`, `WisdomSearchPanel` |
| **P4** ✅ | MB-11 | Codex proxy adapter (dev only) | codex adapter | `runtime/adapters/codex.py`, `AGENT_LAB_CODEX_PROXY=1` |

### Gap-fill (post-P4)

| ID | 보완 |
|----|------|
| MB-8 | `run_external_command` → stdout/`external_handoff.json` 자동 attach (`handoff_attach` in result) |
| MB-10 | mission enabled 시 index 자동 on; `AGENT_LAB_WISDOM_CROSS_SESSION=1` cross-session search |
| MB-11 | Settings `CodexProxyPanel` + `GET /api/health/codex-proxy` |
| MB-7 | `POST …/clarifier-interview/answers` |
| MB-6 | `test_run_dry_run_worktree_setup_hooks` integration test |

---

## 10. 수용 기준

| ID | Criteria |
|----|----------|
| **AC-MB-1** | Mission autorun tick이 **Human send 없이** `continue_room_round` 호출하지 않음 |
| **AC-MB-2** | `lane_roles.discuss`는 항상 3역할; execute lane은 1 adapter 호출 허용 |
| **AC-MB-3** | `turn_budget` 초과 시 `circuit_breaker` 또는 inbox; **한 agent만 영구 비활성화하지 않음** |
| **AC-MB-4** | Checks SSOT: verify FAIL 또는 open BLOCK이면 merge CTA disabled |
| **AC-MB-5** | `evidence.jsonl`에 dry_run/merge/verify/repair 이벤트 append; Work에서 조회 |
| **AC-MB-6** | Readiness `blocked`에 `next_actions[]` 포함; pytest mock health |

---

## 11. 금지 (에이전트·구현 공통)

- Paperclip식 **agent hire** / org chart UI 추가
- discuss 턴 중 main tree **쓰기** (P1)
- Oracle PASS 없이 `MISSION_DONE` (P4)
- `plan_execute` ↔ `mission_loop` **신규** cross-import (P6)
- Heartbeat으로 **3-agent Room** 자동 재개

---

## 12. Related docs (shipped only — backlog은 §9)

- Mission FSM: [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md)
- Runtime harness: [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md)
- Worktree execute: [EXECUTE-WORKTREE-REFORM.md](./EXECUTE-WORKTREE-REFORM.md)
