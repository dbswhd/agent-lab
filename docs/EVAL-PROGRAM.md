# Agent Lab Eval Program v1 — 실사용 테스트 프로그램

> **Status:** v1 shipped (2026-06-12)  
> **Plan source:** Fable 5 session `936215f7` (2026-06-12, Claude Code desktop)  
> **카탈로그:** [`sessions/_benchmark/topics/dogfood-v1.json`](../sessions/_benchmark/topics/dogfood-v1.json)  
> **러너:** [`scripts/run_dogfood_suite.py`](../scripts/run_dogfood_suite.py)

개발 회귀(mock smoke)에서 **실사용 검증**으로 전환할 때 따르는 테스트 프로그램이다. Live Room 세션은 Human gate가 불변이므로 **자동 live 실행은 하지 않는다** — mock 자동 + live 체크리스트 + Human 기록 집계.

---

## 1. 측정 인프라 (3층)

| 층 | 도구 | 역할 | LLM |
|----|------|------|-----|
| **L1 회귀** | `make smoke` | FSM·게이트·메타 shape | mock |
| **L2 KPI** | `score_session`, `score-weekly`, `emergence-bench`, `run_dogfood_suite` | 품질 수치화 | mock/live |
| **L3 dogfood** | `MISSION-DOGFOOD.md`, `make mission-dogfood-run` | end-to-end 미션 | mock/live |

### M4 강제 vs 관찰

`make score-weekly STRICT=1`이 **코드로 강제**하는 것:

| KPI | 목표 |
|-----|------|
| `objection_resolution_rate` | ≥ 80% |
| `execute_retry_rate` | < 30% |

**관찰 지표** (리포트·수동 리뷰; STRICT 미적용):

- `ref_validity_rate` > 90%
- `duplicate_speech_rate` < 20%
- `hybrid_action_rate`, `challenge_yield`, `envelope_parse_success_rate`

`emergence_delta`는 `scripts/emergence_bench.py` 리포트 전용 (`room_composite − max(solo)`); `score_session` 28지표에 없음.

### turn_profile vs mode (흔한 혼동)

| UI/JSON | canonical 값 | 비고 |
|---------|--------------|------|
| **turn_profile** | `quick`, `analyze`, `free`, `specialist`, `verified` | `discuss`→`analyze`, `review`→`free` |
| **mode** (compose) | `discuss`, `plan`, `execute` | plan 갱신·execute는 **mode**; profile 아님 |

### 업계 eval 대응

| 외부 | Agent Lab |
|------|-----------|
| SWE-bench pass/fail | smoke baselines + Oracle verify |
| MT-Bench prompt×model | `emergence_bench` solo vs room |
| Trace + cluster | `chat.jsonl` + `run.json` + `run_diff.py` |
| Tiered harness | L1 mock → L2 benchmark → L3 live dogfood |

---

## 2. 토픽 카탈로그

**SSOT:** `sessions/_benchmark/topics/dogfood-v1.json` (32 topics, 7 tier).

각 항목 필드: `id`, `tier`, `category`, `topic`, `profile`, `flags`, `workspace`, `kpis`, `pass`, `live_only`, `repeat`, `mock`.

| Tier | 목적 | IDs |
|------|------|-----|
| **S** | 단일턴·라우팅 | S1–S3 |
| **M** | 토론·정리·dispatch·goal | M1–M6 |
| **P** | Plan-First FSM (mock + live approval) | PW1–PW5 |
| **L** | 설계·합의·escalation·창발 | L1–L4 |
| **X** | execute·Mission·hook | X1–X4 |
| **A** | 적대/부정 (게이트 공격) | A1–A7 |
| **D** | 외부 도메인 (편향 통제) | D1–D3 |

### Plan workflow KPIs (`score_session`)

| KPI | 의미 |
|-----|------|
| `plan_workflow_enabled` | FSM 활성 |
| `plan_workflow_reached_human_pending` | HUMAN_PENDING 이상 도달 |
| `plan_workflow_approved` | Human 승인 완료 |
| `plan_workflow_cap_triggered` | clarify/peer cap notice |
| `plan_workflow_clarify_rounds` / `plan_workflow_peer_rounds` | 라운드 수 |
| `plan_workflow_approval_latency_sec` | proposed_at → approved_at (초) |

PW5 live: `suite-log.json`의 `human_minutes` median + 위 KPI를 aggregate 모드에서 집계.

`workspace`: `agent-lab` | `pipeline` (`/Users/yoonjong/Desktop/pipeline`) | `neutral`

`make emergence-bench` 호환: bench는 `{category, topic}`만 소비; 나머지 필드는 무시됨.

```bash
.venv/bin/python scripts/emergence_bench.py \
  --topics sessions/_benchmark/topics/dogfood-v1.json
```

---

## 3. 테스트 매트릭스 (live 주 8~10 세션)

### Week 0 — mock baseline (1일)

```bash
make ci
make emergence-bench
make measure-communicate-baseline
make mission-dogfood-run
make dogfood-suite-mock
```

산출물: `sessions/_reports/` (dogfood-suite-mock-*.json, communicate baseline 등).

### Week 1 — 토론·정리 (~9 live)

| Day | Topics | 비고 |
|-----|--------|------|
| D1 | S1, S2, S3 | quick/analyze baseline |
| D2 | M1 ×2 | analyze vs plan ON |
| D3 | M2 ×2 | specialist + artifacts |
| D4 | M4 ×2 | CHALLENGE→AMEND |
| D5 | M5 | DISPATCH parallel |

### Week 2 — 합의·도메인 (~8 live)

M3, M5, L1, L3, D1, D3 (+ 여유 2).

### Week 3 — 미션·적대 (~6 live)

X1–X3, A1 (live Oracle), L2 또는 D2.

### 매주 금요일

```bash
make score-weekly DAYS=7 STRICT=1 REPORT=1
make dogfood-suite-aggregate LOG=suite-log.json   # live 기록 후
```

---

## 4. 러너 사용법

```bash
# mock — Tier S/M/L/D 자동 + Tier A 시나리오 (Human gate 우회 없음)
make dogfood-suite-mock
make dogfood-suite-mock TIER=S,M ONLY=M4

# live — 프롬프트·flags·pass 기준 출력 (Human이 UI에서 실행)
make dogfood-suite-checklist
make dogfood-suite-checklist TIER=L

# aggregate — live 실행 후 suite-log.json 집계
make dogfood-suite-aggregate LOG=suite-log.json
```

Mock에서 `skip:` 토픽은 live 전용 또는 smoke baseline이 커버하는 항목이다.

---

## 5. Live 세션 진행 방법

### 앱 시작

```bash
make dev  # API :8765 + web :5173
```

브라우저 → `http://localhost:5173`

### 세션 만들기

**New Room** → 토픽·프로필 입력 → **Run**

| 항목 | 설정 |
|------|------|
| Prompt | 체크리스트(`make dogfood-suite-checklist`)에서 복사 |
| Turn Profile | 각 토픽의 `profile` 값 (`quick` / `analyze` / `specialist` / `free`) |
| Flags | 각 토픽의 `flags` 값 (없으면 기본값) |
| Workspace | `pipeline` 토픽은 `/Users/yoonjong/Desktop/pipeline` 지정 |

### Human gate

세션 중 **Human Inbox**에 메시지가 오면:

- 승인 → **Approve** / **Resolve**
- 반려 → **Reject** + 사유

S/M 단순 토픽은 Human 개입 없이 1턴에 끝나는 게 정상.  
M3·A2(BLOCK 테스트)는 에이전트가 BLOCK을 걸면 Inbox에서 **Resolve** 처리.

### 세션 종료 후 체크

```bash
make score-session SESSION=sessions/<id>
```

수동 확인:

| 아티팩트 | 확인 포인트 |
|----------|------------|
| `run.json` | `turns[].category`, `objections[]`, `dispatch_ledger[]` |
| `chat.jsonl` | echo 없는지, envelope parse error 없는지 |
| `plan.md` | `## 지금 실행` 섹션 + `(ref: N)` 인용 |

### suite-log.json에 기록

세션 완료 후 `sessions/_benchmark/topics/suite-log.json`에 추가:

```json
[
  {
    "id": "M1",
    "session": "sessions/<id>",
    "repeat": 1,
    "pass": true,
    "human_minutes": 12,
    "tags": [],
    "notes": ""
  }
]
```

파일이 없으면 빈 배열 `[]`에서 시작.

### 주간 집계 (매주 금요일)

```bash
make score-weekly DAYS=7 STRICT=1 REPORT=1
make dogfood-suite-aggregate LOG=sessions/_benchmark/topics/suite-log.json
```

리포트 → `sessions/_reports/weekly-YYYY-MM-DD.md`

### Day 1 빠른 시작 (S1 예시)

```
make dev
→ 브라우저 http://localhost:5173
→ New Room
→ Prompt: "room.py에서 consensus 라운드 cap 기본값이 뭐야?"
→ Turn Profile: quick
→ Run
→ make score-session SESSION=sessions/<id>
→ suite-log.json에 S1 결과 기록
→ S2, S3 반복
```

---

## 6. 세션당 분석 체크리스트

| 아티팩트 | 확인 |
|----------|------|
| `chat.jsonl` | echo, envelope parse error, `[PROPOSED:]` |
| `plan.md` | `(ref: N)`, `## 지금 실행`, hybrid bullets |
| `run.json` | `turns[]`, `communicate_meta`, `objections[]`, `dispatch_ledger[]`, `hook_runs[]`. **라우터 카테고리는 `turns[].category`** (top-level `_turn_category`는 턴 처리 중 in-memory 전용; consensus/free 턴만 분류됨) |
| `artifacts/` | specialist/dispatch 산출물 분리 |
| notepad | `learnings.md` 등 Mission 회고 (X tier) |

수동 질문:

1. Human 개입 지점이 적절했는가?
2. 3-agent가 **다른 각도**였는가?
3. plan이 대화와 **동기화**되었는가?
4. execute gate가 막아야 할 때 막았는가?

---

## 7. 개선 루프

```text
Topic 실행 → score_session → M4/관찰 KPI → 실패 trace 리뷰
→ 원인 태그 1개 → 수정 1건 → make smoke → 동일 topic 재실행
```

| 태그 | 예 | 수정 위치 |
|------|-----|-----------|
| `routing` | quick인데 ♾️ 필요 | `topic_router.py` |
| `communicate` | envelope parse error | `agent_envelope.py` |
| `context` | R2 R1 전문 누수 | `context_bundle.py` |
| `scribe` | ref 불일치 | `ROOM_SCRIBE` |
| `gate` | BLOCK 미연결 | `room_objections.py` |
| `ux` | plan 갱신 인지 못함 | Work toolbar |

**Fixture 규칙:** live 실패 1건 → `sessions/_regression/` baseline 1건 추가 후 수정.

우선순위: 게이트/안전 > KPI regression > emergence delta > UX copy.

---

## 8. suite-log.json (live 기록)

예시: [`sessions/_benchmark/topics/suite-log.example.json`](../sessions/_benchmark/topics/suite-log.example.json)

```json
[
  {
    "id": "M1",
    "session": "sessions/2026-06-12-weekly-kpi-plan",
    "repeat": 1,
    "pass": true,
    "human_minutes": 12,
    "tags": ["scribe"],
    "notes": "plan ## 지금 실행 2 actions"
  }
]
```

필드는 `run_dogfood_suite.py --mode aggregate` 입력과 일치한다.

---

## 9. Tier A 알려진 한계

| ID | mock | live |
|----|------|------|
| A1 Oracle reward-hack | mock Oracle은 리터럴 매칭 → **PASS** (구조적 한계) | live Oracle **FAIL** 기대 |
| A2 BLOCK→409 | harvest만 mock; 409는 `objection_blocks_execute` smoke |
| A7 envelope | aggregate 시 `envelope_parse_success_min` 자동 포함 |

---

## 10. 검증 (v1 ship 기준)

1. `make dogfood-suite-mock TIER=S,M` — 0 failed/error
2. `make dogfood-suite-checklist TIER=S` — flags/profile 실명
3. `make emergence-bench` + `--topics dogfood-v1.json` — 호환
4. `make test` + `make smoke` — 회귀 무영향

---

## 관련 문서

- [STABILITY.md](./STABILITY.md) · [MISSION-DOGFOOD.md](./MISSION-DOGFOOD.md)
- [sessions/_benchmark/README.md](../sessions/_benchmark/README.md)
- `/smoke-and-score` skill (Cursor/Claude Code)
