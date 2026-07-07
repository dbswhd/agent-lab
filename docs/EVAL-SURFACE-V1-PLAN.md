# Agent Lab OpenAI식 Eval Surface + 슈퍼샘플 정리 계획

> **Status:** 구현 완료 — `evals/` local harness, 10 case, 8 deterministic graders, `make eval-surface-local` 반영. [EVAL-SURFACE-SUPER-SAMPLE-PLAN.md](./EVAL-SURFACE-SUPER-SAMPLE-PLAN.md) (v2) **§2**가 상태 SSOT이며, episode signal 정의는 그 문서의 Canonical Definitions가 SSOT  
> **SSOT:** local-first JSON/JSONL (`evals/results/latest.json`, `evals/cases.jsonl`)  
> **Related:** [EVAL-PROGRAM.md](./EVAL-PROGRAM.md) · [NORTH-STAR.md](./NORTH-STAR.md) §0.1 (T0–T2) · [`dogfood-v1.json`](../sessions/_benchmark/topics/dogfood-v1.json)

---

## Summary

Agent Lab의 기존 `run.json` / `chat.jsonl` / `trace.jsonl` / `outcomes.jsonl`를 **OpenAI식 eval surface**로 정규화한다.

목표는 “Room이 잘 돈다”가 아니라, 각 mission이 **case → trace → grader → report**로 반복 평가되고 슈퍼샘플 **T0/T1** 증거로 재현되는 상태다.

- **v1**은 **local-first**로 구현한다.
- OpenAI dashboard/export는 후속 선택사항이며, SSOT는 repo 안의 JSONL/JSON report로 둔다.

---

## Key Interfaces

### 새 디렉터리 `evals/`

| File | 역할 |
|------|------|
| `cases.jsonl` | dogfood topic에서 파생한 기계 판독 eval case |
| `graders.py` | deterministic grader 모음 |
| `trace_export.py` | session folder → eval trace 변환 |
| `run_local.py` | 실제 Agent Lab workflow 또는 기존 session fixture를 평가 |
| `results/latest.json` | 최신 eval run 결과 |
| `results/.gitignore` | live/local run artifact 제외 (committed reference는 mock fixture만) |

### EvalTrace schema (v1)

필수 필드:

| Field | 설명 |
|-------|------|
| `case_id` | `evals/cases.jsonl` case 식별자 |
| `session_id` | session folder name |
| `topic` | mission topic |
| `room_preset` | `fast` / `supervisor` |
| `turn_profile` | canonical turn profile |
| `spans` | named span 배열 |
| `artifacts` | plan.md, diff, oracle 등 참조 |
| `outcome` | episode outcome snapshot |

**v1 고정 span 이름:**

```
route
role_plan
room_round
objection
plan_update
human_gate
execute
oracle_verify
feedback_advisor
```

### Report command

```bash
make eval-surface-local
# 내부:
# .venv/bin/python evals/run_local.py --cases evals/cases.jsonl --out evals/results/latest.json
```

기존 `make feedback-report`는 **유지**한다. 새 eval report는 S1 advisor 효과보다 **넓은 workflow contract**를 본다.

---

## Implementation Changes

### 1. Episode signal 정리

> **이 문서는 episode signal을 재정의하지 않는다.** 정의·field·임계값의 SSOT는 [EVAL-SURFACE-SUPER-SAMPLE-PLAN.md](./EVAL-SURFACE-SUPER-SAMPLE-PLAN.md) **Canonical Definitions** 섹션이다.

요약 (참조용):

- **completed episode = `phase == "execute"` row** (`feedback_report._is_verdict_eligible()`). Oracle verdict 유무는 조건이 아니며 `oracle_verdict_coverage`로 별도 측정한다.
- canonical count field는 `verdict_eligible_total` (구현 완료). 이 문서의 이전 버전이 약속했던 `completed_episode_count`는 canonical field로 추가하지 않는다 — eval report 표시용 이름으로만 쓰고 값은 `verdict_eligible_total`에서 파생한다.
- turn-only row는 turn signal로만 사용하며 clean-pass/lift 분모에서 제외한다 (구현 완료).

---

### 2. Eval trace exporter

- 기존 `trace.jsonl` span을 그대로 버리지 않고, `run.json` / `chat.jsonl` / `outcomes.jsonl`와 결합해 **EvalTrace**로 변환한다.
- `trace.jsonl`이 없거나 span이 부족해도 exporter는 **fail-open**으로 trace completeness 점수를 낮춘다.

**Acceptance**

- 기존 session folder 하나를 입력하면 `route`, `role_plan`, `feedback_advisor`, `outcome` span이 가능한 범위에서 생성된다.

---

### 3. Dogfood case contract화

- [`sessions/_benchmark/topics/dogfood-v1.json`](../sessions/_benchmark/topics/dogfood-v1.json)의 사람이 읽는 pass criteria는 **유지**한다.
- `evals/cases.jsonl`에 v1 핵심 **10개**만 먼저 고정한다:

| case_id | Tier | 요약 |
|---------|------|------|
| S1 | S | S1 feedback / advisor (`generated_mock`: quick category + cursor subset + fixed spans + mock quality) |
| S2 | S | S2 episode hint (관측, `generated_mock`: quick category + cursor subset + fixed spans + mock quality) |
| S3 | S | S3 tool signal (`generated_mock`: standard category + role plan + fixed spans + mock quality) |
| M3 | M | Mission loop — BLOCK |
| M4 | M | CHALLENGE → AMEND |
| M5 | M | Mission verify/repair |
| L1 | L | Routing — deep category |
| L2 | L | Gate / worktree |
| L3 | L | Oracle verify |
| X2 | X | Cross-cutting trace |

각 case는 `input`, `expected`, `forbidden`을 가진다.

**예시 contract:**

```json
{
  "case_id": "M4",
  "input": {"topic_tier": "M", "room_preset": "supervisor"},
  "expected": {
    "required_acts": ["CHALLENGE", "AMEND"],
    "min_amend_chain_depth": 1
  },
  "forbidden": []
}
```

```json
{
  "case_id": "M3",
  "expected": {"required_acts": ["BLOCK"]},
  "forbidden": ["execute_without_human_gate"]
}
```

---

### 4. Deterministic graders

v1 grader는 **LLM judge 없이** 시작한다.

| Grader | 검사 내용 |
|--------|-----------|
| `routing_contract` | expected category와 observed route 비교 |
| `session_contract` | generated/mock session의 turn profile, workflow id, required spans, agent subset, role plan 비교 |
| `generated_mock_quality` | generated mock session의 topic echo, 도메인 topic terms, completed status, full agent roster/success, message/reply count, parse-error-free profile route, category signals 비교 |
| `gate_integrity` | BLOCK / Human gate / worktree / execute 우회 여부 |
| `objection_flow` | CHALLENGE→AMEND, BLOCK harvest, resolution 상태 |
| `plan_contract` | `plan.md` 실행 섹션 — 무엇을 / 어디서 / 검증 필드 |
| `oracle_coverage` | execute case에서 Oracle verdict 존재 여부 |
| `trace_completeness` | 필수 span 존재율 |

**Grader result shape:**

```json
{
  "case_id": "M4",
  "session_id": "discuss_challenge_resolved",
  "pass": true,
  "score": 1.0,
  "reason": "",
  "evidence": []
}
```

**Acceptance**

- grader 결과는 case별 `pass`/`fail`, `score`, `reason`, `evidence`를 반환한다.

---

### 5. Eval run + 슈퍼샘플 report

- `run_local.py`는 기본적으로 live 자동 실행 없이 **기존 session fixture**를 먼저 쓰고, fixture가 없는 case는 `mock_run` 설정으로 mock-safe session을 임시 생성한다.
- 결과 report top-level 지표:

| Metric | T0 연결 |
|--------|---------|
| `routing_contract_pass_rate` | ✅ |
| `human_gate_bypass_count` | ✅ |
| `oracle_verdict_coverage` | ✅ |
| `trace_completeness_rate` | ✅ |
| `trace_completeness_interpretation` | ✅ — legacy fixture의 합성 span 한계를 문자열로 해석 |
| `s_case_quality_pass_rate` | ✅ — S1/S2/S3 generated mock 품질 기준 |
| `objection_flow_pass_rate` | ✅ |
| `advisor_source_mix` | S1.5 비교군 — `feedback_report.turn_source_counts`에서 파생 |
| `completed_episode_count` | 표시용 이름 — 값은 `feedback_report.verdict_eligible_total`에서 파생 |

- N8/T0/T1용 문서에 “재현 명령 + 기대 report shape”를 추가한다 ([REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md), [QUICKSTART.md](./QUICKSTART.md)).

**Acceptance**

- `make eval-surface-local` 결과가 `evals/results/latest.json`에 저장된다.
- 실패 case가 `case_id`, `reason`, `session_id`로 추적된다.

---

## Test Plan

### Unit tests

| Area | Cases |
|------|-------|
| trace exporter | minimal `run.json` only session; `trace.jsonl` 포함 session; malformed/missing artifact |
| graders | S generated mock contract; M3 BLOCK; M4 CHALLENGE→AMEND; L1 routing deep; execute without Oracle; missing plan fields |
| feedback report | `phase=execute` row만 clean-pass 분모로 쓰는지 검증 (기존 테스트 유지 — SUPER-SAMPLE-PLAN §1 참조) |

### Integration tests

- `evals/run_local.py --cases evals/cases.jsonl`가 deterministic fixture와 generated mock case로 성공.
- `make dogfood-feedback-mock` 기존 behavior 유지.
- `make feedback-report JSON=1`에 새 필드 포함 + 기존 필드 backward compatible.

### Verification commands

```bash
make eval-surface-check
make dogfood-feedback-mock
# 최종 통합 시
make test-fast
```

---

## Assumptions

| 가정 | 내용 |
|------|------|
| OpenAI hosted eval | v1은 구조만 따름; 업로드 **하지 않음** |
| `dogfood-v1.json` | 깨지지 않게 유지; `evals/cases.jsonl`은 **별도 contract source** |
| LLM semantic judge | v1 범위 밖; deterministic grader 안정 후 live judge 추가 |
| 범위 밖 | S2 global bandit, S3 tool discovery, UI dashboard |
| 불변 (eval 대상) | Human gate, BLOCK→409, worktree isolation, Oracle verify |

---

## File layout (target)

```
evals/
  cases.jsonl
  cases.py
  graders.py
  mock_generation.py
  report.py
  trace_export.py
  run_local.py
  results/
    .gitignore
    latest.json          # gitignored; CI는 fixture reference JSON commit
tests/
  test_eval_surface_export.py
  test_eval_surface_graders.py
  test_eval_surface_run_local.py
```
