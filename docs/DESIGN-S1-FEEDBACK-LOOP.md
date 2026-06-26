# 설계: S1 내부 피드백 루프 (Session-to-Session Learning)

> **상태**: 설계 (구현 전)
> **기준일**: 2026-06-26
> **북극성 근거**: [`docs/STRATEGIC-DIRECTION-2026.md`](STRATEGIC-DIRECTION-2026.md) "북극성" 섹션 — S1(내부 루프 폐쇄) → S2(팀 자기조정) → S3(외부 통합)
> **범위**: P0(Dynamic Room · Model Policy · Code-memory MCP) + Session-to-session learning를 **단일 내부 피드백 회로(S1)** 로 통합

---

## 1. Context — 왜 지금 이 작업인가

전략 문서의 북극성은 "협업을 통한 창발 → 자기발전"이고, 그 첫 단추가 **S1: 내부 피드백 루프 폐쇄**다. 창발의 3대 전제(비대칭 역할 / 피드백 루프 / **실패 학습**) 중 마지막 — "검증 실패를 기록하고 다음 실행이 그 실패를 알고 시작" — 이 현재 코드에서 **끊겨 있다**.

코드 탐색으로 확인된 단절 지점 4개:

| # | 단절 | 근거 |
|---|---|---|
| 1 | **역할 배정이 휘발됨** | `resolve_role_plan()`이 만든 `_turn_roles`는 `run_meta.py:_EPHEMERAL_RUN_KEYS`에 포함되어 run.json에 저장되지 않음 → 어떤 역할 조합이 효과적이었는지 학습할 데이터 자체가 없음 |
| 2 | **Oracle 판정이 세션 안에 갇힘** | `executions[].oracle.verdict`는 저장되지만 세션 간 집계가 없음. `wisdom_index`(세션 내)·`session_score_weekly`(오프라인 KPI)만 존재 |
| 3 | **Model Policy가 정적** | `model_profile_for()`는 agent별 고정 프로필. complexity→model 배선은 "architecture-ready, not wired" |
| 4 | **Code-memory/Wisdom가 Room 셋업에 미주입** | 인덱싱은 되지만 다음 턴 역할·에이전트 선택에 영향 없음 |

**목표**: 이 4개를 잇는 단일 피드백 회로. `토픽 → 역할 조합 자가 결정 → 실행 → Oracle 검증 → 패턴 기록 → 다음번 더 나은 셋업으로 시작`.

**비목표(이번 범위 밖)**: S2 자동 팀 진화, S3 외부 MCP 자가 통합, Trust-gated auto-approval(P1).

---

## 2. 아키텍처 — 4-스테이지 회로

```
                  ┌──────────────────────────────────────────────┐
                  │  .agent-lab/outcomes.jsonl  (신규)              │
                  │  세션 간 누적 결과 레저                          │
                  └──────────────────────────────────────────────┘
       (4) RECORD ▲                                       │ (1) RECALL
                  │                                       ▼
  run.json ──► [Harvester] ──► append              [Advisor] ──► SetupHint
  (turns,        스테이지 4                           스테이지 1       │
   executions,                                                       ▼
   objections)                                  room_consensus_rounds / role_plan
                                                (2) APPLY: 역할·에이전트·(모델) 조정
                                                              │
                                                              ▼
                                          consensus rounds → execute → Oracle
                                                              │
                                                              ▼ (3) MEASURE
                                          turn_metrics 산출 → run.json (persist)
```

| 스테이지 | 모듈 | 역할 |
|---|---|---|
| **1 RECALL** | `feedback_advisor.py` (신규) | 새 턴 시작 시 `outcomes.jsonl`에서 유사 토픽/카테고리 과거 결과 조회 → `SetupHint` 반환 |
| **2 APPLY** | `role_plan.py` · `topic_router.py` · `model_policy.py` (확장) | `SetupHint`를 역할 배정·에이전트 서브셋·(선택)모델 cost-tier에 주입 |
| **3 MEASURE** | `turn_metrics.py` (신규) | 턴 종료 시 역할 조합·Oracle 결과·objection 패턴을 `turns[i].turn_metrics`로 **persist** |
| **4 RECORD** | `outcome_harvester.py` (신규) | 턴 종료 시 run.json → `outcomes.jsonl` 한 줄 append |

**불변 원칙**: 각 스테이지는 독립 플래그로 켜고, 전체 OFF 시 기존 동작과 100% 동일(fail-open). Advisor는 **역할 텍스트·에이전트 선택만** 조정 — 모트(BLOCK→409·worktree·Oracle·run.json 감사·Human Inbox)를 건드릴 경로가 구조적으로 없음.

---

## 3. 데이터 스키마

### 3.1 `turns[i].turn_metrics` (run.json, 신규 persist 필드)

`turns[i]` 하위 필드이므로 `_EPHEMERAL_RUN_KEYS`(top-level만 필터: `run.items()` 기준) 영향 없음 — 확인 완료. `_turn_snapshot()`에서 채움.

```json
"turn_metrics": {
  "schema_version": 1,
  "category": "standard",
  "route_source": "heuristic",
  "roles": { "cursor": "proposer", "codex": "executor", "claude": "critic" },
  "agents": ["cursor", "codex", "claude"],
  "rounds_used": 3,
  "calls_used": 14,
  "escalated": false,
  "objection_summary": { "CHALLENGE": 2, "BLOCK": 0, "AMEND": 1 },
  "consensus_reached": true,
  "synthesized": true,
  "latency_ms": 311418,
  "oracle_rollup": {
    "verify_pass": 1, "verify_fail": 0,
    "repair_attempts": 0, "final_verdict": "pass"
  },
  "advisor_rationale": null
}
```

`advisor_rationale`은 Phase B에서 채워짐(감사성).

### 3.2 `.agent-lab/outcomes.jsonl` (신규, repo 루트, gitignore 대상)

`.agent-lab/`은 이미 `loop_probe_cache.json`이 쓰는 기존 위치. 세션·턴 단위 1줄.

```json
{"v":1,"ts":"2026-06-26T...","session_id":"...","topic_hash":"sha1:...",
 "topic_terms":["pipeline","preset","verify"],
 "category":"standard","roles":{"cursor":"proposer","codex":"executor","claude":"critic"},
 "agents":["cursor","codex","claude"],
 "rounds_used":3,"escalated":false,
 "final_verdict":"pass","repair_attempts":0,
 "objection_summary":{"CHALLENGE":2,"BLOCK":0},
 "consensus_reached":true,"latency_ms":311418}
```

`topic_terms`는 `wisdom_index._tokenize()` 재사용(중복 토크나이저 금지). `topic_hash`는 정확 일치 dedup용. root 해석은 `code_memory_mcp_server.py`의 root 패턴 재사용.

### 3.3 `SetupHint` (in-memory dataclass, `feedback_advisor.py`)

```python
@dataclass(frozen=True)
class SetupHint:
    source: str                        # "history" | "default"
    sample_size: int                   # 근거가 된 과거 결과 수
    role_overrides: dict[str, str]     # agent -> role_id (빈 dict = 변경 없음)
    suggested_subset: tuple[str, ...]  # 빈 tuple = 변경 없음
    suggested_cost_tier: str | None    # Phase B4 (선택)
    rationale: str                     # 사람이 읽을 근거 (run.json·UI 노출)
```

---

## 4. 구현 단계

### Phase A — MEASURE & RECORD (관측 먼저, 행동 없음)

> 데이터를 먼저 모은다. APPLY 없이 며칠/세션 돌려 근거를 축적.

- **A1.** `turn_metrics.py` 신규 — `build_turn_metrics(run_meta, route, roles, objections, executions) -> dict`. 순수 함수. 입력은 모두 기존 값(`route.category_dict()`, `_turn_roles`, `run["objections"]`, `executions[].oracle`).
- **A2.** `_turn_snapshot()` 수정(`room_turn_flow.py` 스냅샷 작성부) — `turn_metrics` 필드 추가. `_turn_roles`는 ephemeral 유지하되 그 **값만 복사**해 persist.
- **A3.** `outcome_harvester.py` 신규 — `harvest_outcome(folder) -> dict | None`(run.json 마지막 턴 `turn_metrics` + oracle 롤업 → outcomes 1줄), `append_outcome(record)`(atomic append, `run_meta.py`의 atomic write + 락 패턴 차용).
- **A4.** 호출 지점 — 턴 종료 직후(`_write_session_files()` 인접) `if flag: append_outcome(harvest_outcome(folder))`. 실패는 swallow + 로그(피드백이 본 플로우를 막지 않음).
- **플래그**: `AGENT_LAB_TURN_METRICS`(A1·A2), `AGENT_LAB_OUTCOME_LEDGER`(A3·A4).
- **대표 파일**: `src/agent_lab/turn_metrics.py`(신규), `src/agent_lab/outcome_harvester.py`(신규), `src/agent_lab/room_turn_flow.py`, `src/agent_lab/run_meta.py`.

### Phase B — RECALL & APPLY (행동 폐루프)

- **B1.** `feedback_advisor.py` 신규 — `advise_setup(topic, category, available_agents, *, root) -> SetupHint`:
  1. `outcomes.jsonl` tail 로드(최근 N=200 cap, `wisdom_index` recent-N 패턴 차용).
  2. 같은 `category` + `topic_terms` overlap ≥ 임계만 필터.
  3. 성공 가중 집계(`final_verdict==pass` & `repair_attempts==0` → +2, `BLOCK` 존재 → −1 등).
  4. 역할 조합별 평균 성공도 → 최고 조합을 `role_overrides`로. 표본 < `MIN_SAMPLE`(기본 3)이면 `source="default"` 빈 힌트(보수적 fail-open).
- **B2.** `resolve_role_plan()` 시그니처 확장(`role_plan.py`) — `hint: SetupHint | None = None`. hint.role_overrides가 있고 해당 agent가 active면 override, 없으면 기존 cwd_role 로직. **기존 무인자 호출부 동작 불변.** `agent_subset_for_route()`도 동일 패턴.
- **B3.** `room_consensus_rounds.py` 배선 — route 해석 직후 `hint = advise_setup(...) if flag else None` → `resolve_role_plan(route, active, hint=hint)` 전달. `hint.rationale`을 `run_meta["_turn_roles_rationale"]`(ephemeral) + `turn_metrics.advisor_rationale`에 기록.
- **B4. (선택)** Model Policy 연동 — `SetupHint.suggested_cost_tier`를 `model_profile_for()` 호출 전 강등/승격에 사용. 별도 complexity scorer 없이 `category→cost_tier` 매핑 테이블(`model_policy.py`)로 최소 구현(complexity는 `route.category`로 대용).
- **플래그**: `AGENT_LAB_FEEDBACK_ADVISOR`(B1~B3, A 의존), `AGENT_LAB_FEEDBACK_MODEL_HINT`(B4).
- **대표 파일**: `src/agent_lab/feedback_advisor.py`(신규), `src/agent_lab/role_plan.py`, `src/agent_lab/room_consensus_rounds.py`, `src/agent_lab/model_policy.py`.

### Phase C — Wisdom/Code-memory 연결 (RECALL 보강)

- **C1.** `advise_setup()`가 `search_wisdom_cross_sessions()`(기존)를 보조 신호로 사용 — 현재 토픽 관련 과거 `[LEARNED:]` 노트를 `SetupHint.rationale`에 첨부(역할 결정엔 미반영, 컨텍스트 주입만).
- **C2.** code-memory 주입은 이번 범위 밖(별도 작업). `outcomes.jsonl`을 code-memory 인덱싱 대상에 넣을지는 후속 결정.
- **플래그**: 기존 `AGENT_LAB_WISDOM_CROSS_SESSION` 재사용.

### Phase D — 노출 & 가드레일

- **D1. UI** — 세션 turn 카드에 "이 셋업이 선택된 근거"(rationale) 표시. 대표: `web/src/components/` 턴 표시 컴포넌트(구현 단계에서 정확 파일 확정).
- **D2. Health/flags** — 신규 플래그를 `GET /api/health/flags` 레지스트리 + `make list-flags`에 등록.
- **D3. 안전장치** — advisor는 역할/서브셋만 조정. 모트 미손상이 구조적으로 보장됨(역할 텍스트·에이전트 선택만 변경, 게이트 우회 경로 없음).

---

## 5. 재사용할 기존 자산 (신규 작성 금지)

| 필요 | 재사용 대상 | 위치 |
|---|---|---|
| 토크나이저 | `_tokenize()` | `wisdom_index.py` |
| atomic write/락 | `write_run_meta` / `patch_run_meta` 패턴 | `run_meta.py` |
| root 해석 | code-memory root 패턴 | `code_memory_mcp_server.py` |
| recent-N cap | cross-session recent-N 패턴 | `wisdom_index.py` |
| 역할 정의/주입 | `_ROLES`, `persona_for_agent` | `role_plan.py` |
| 카테고리 라우팅 | `CategoryRoute`, `resolve_topic_route` | `topic_router.py` |
| objection 수집 | `run["objections"]` | `room_objections.py` |
| Oracle 판정 | `executions[].oracle` | `plan_execute_verify.py` |
| cross-session 검색 | `search_wisdom_cross_sessions` | `wisdom_index.py` |

---

## 6. 검증 (Verification)

1. **단위** — `build_turn_metrics()`, `advise_setup()` 순수 함수 테스트. 합성 `outcomes.jsonl` 픽스처로 "표본<MIN → 빈 힌트", "성공 조합 우세 → override" 케이스. mock-only(`AGENT_LAB_MOCK_AGENTS=1`).
2. **회귀** — `make test-fast`(~870) 통과. **모든 신규 플래그 OFF 시 결과 불변**이 핵심(기존 스냅샷 미손상). `python scripts/smoke_room.py` 36 baseline 유지.
3. **루프 폐쇄 E2E** — `AGENT_LAB_MOCK_AGENTS=1`로 같은 토픽 2회 실행:
   - 1회차: `outcomes.jsonl`에 1줄 생성 확인.
   - 2회차: advisor가 1회차 결과를 읽어 `turn_metrics.advisor_rationale`에 `source="history"`가 찍히는지 확인.
   - `/smoke-and-score` 또는 `make dogfood-suite-mock`로 점수 회귀 없음 확인.
4. **플래그 레지스트리** — `make list-flags` / `GET /api/health/flags`에 신규 플래그 노출 확인.
5. **감사 불변** — 실행 후 run.json에 BLOCK→409·worktree·Oracle 필드 그대로인지 확인(모트 미손상).

---

## 7. 단계 요약 & 착수 순서

| Phase | 산출물 | 플래그 | 의존 |
|---|---|---|---|
| A | turn_metrics 기록 + outcomes.jsonl 누적 | `TURN_METRICS`, `OUTCOME_LEDGER` | — |
| B | advisor 기반 역할·에이전트·(모델) 자가 조정 | `FEEDBACK_ADVISOR`, `FEEDBACK_MODEL_HINT` | A |
| C | wisdom cross-session 근거 첨부 | `WISDOM_CROSS_SESSION`(기존) | B |
| D | UI 근거 노출 + health flags + 가드레일 | — | A~C |

> **착수 순서**: A(관측) → 며칠 데이터 축적 → B(폐루프) → C/D. A 없이 B를 켜면 표본이 없어 항상 default 힌트가 나오므로 관측이 반드시 선행.
