# Agent Lab Eval Surface + 슈퍼샘플 준비 계획 (v2)

> **현행 가치:** 이 문서에서 지금도 참조할 canonical 정의는 **[Canonical Definitions](#canonical-definitions)** 절뿐이다(episode 정의·표본 임계값). 나머지(Summary·Current Status·Implementation Changes 등)는 **완료된 계획의 이력** — episode/lift 수치를 해석할 때만 Canonical Definitions를, 구현 배경이 궁금할 때만 나머지를 읽는다.  
> **Status:** 완료 — §1(episode 보강)·§2(eval surface: `evals/` + 10 case + 8 grader)·§3(T0/T1/T2 `supersample` report)·§4(explore 운영 문서화)·§5(공개 재현 패키지 문서 정리) 전부 반영됨. 잔여: `fork_time_minutes` clean-clone 자동화(N8, 범위 밖)  
> **SSOT:** local-first JSON/JSONL report (`evals/results/latest.json`, `feedback_report`)  
> **Related:** [NORTH-STAR.md](./NORTH-STAR.md) §0.1 (T0–T2) · [EVAL-PROGRAM.md](./EVAL-PROGRAM.md) · [EVAL-SURFACE-V1-PLAN.md](./EVAL-SURFACE-V1-PLAN.md) (§2 구체 스펙) · [REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md) · [QUICKSTART.md](./QUICKSTART.md)

---

## Summary

이 계획은 **S1.5를 재구현하지 않는다.** 현재 코드 기준으로 Phase 1·4는 완료 상태다.

남은 일은 구현된 S1.5 신호를 정리하고, 그 위에 OpenAI식 **case → trace → grader → report** eval surface와 **T0/T1/T2 슈퍼샘플 판정 report**를 붙이는 것이다. SSOT는 local-first JSON/JSONL이며 OpenAI hosted eval 업로드는 v1 범위 밖이다.

---

## Canonical Definitions

이 섹션이 아래 개념들의 **단일 SSOT**다. [EVAL-SURFACE-V1-PLAN.md](./EVAL-SURFACE-V1-PLAN.md)를 포함한 다른 문서는 이 섹션을 참조만 하고 재정의하지 않는다.

### Completed episode

> **completed episode = `outcomes.jsonl`에서 `phase == "execute"`인 row.**

- 구현 SSOT: `feedback_report._is_verdict_eligible()` (`src/agent_lab/feedback_report.py`).
- turn-phase / legacy(pre-phase) row는 `final_verdict`가 구조적으로 null이므로 clean-pass/lift **분모에서 제외**한다. 이 row들은 **turn signal**(routing, role, advisor, latency 관측)로만 사용한다.
- Oracle verdict 유무는 completed episode 판정 조건이 **아니다** — verdict가 null인 execute row도 분모에 포함되며(clean-pass는 아님), verdict 존재율은 `oracle_verdict_coverage`로 별도 측정한다.
- ~~"Oracle verdict가 있는 execute/verify 결과"~~, ~~"`phase=execute` 또는 verdict가 있는 row"~~ 같은 과거 문서 정의는 폐기한다.

### 표본 임계값 — 두 임계값은 목적이 다르다

| 임계값 | 값 | 성격 | 위치 |
|--------|----|------|------|
| `MIN_SAMPLE` | 3 (`AGENT_LAB_FEEDBACK_MIN_SAMPLE`) | **기계 게이트** — advisor override 억제 + report lift `null` 처리 | `feedback_advisor.MIN_SAMPLE` (코드) |
| n≥30 | 30 | **사람 해석 기준** — source별 비교군을 신뢰할 최소 표본 | 문서·report 해석 가이드 (코드 아님) |
| n≥10 | 10 | **사람 해석 기준** — 초기 dogfood "early signal" | 문서·report 해석 가이드 (코드 아님) |

- `MIN_SAMPLE=3`은 cold-start에서 advisor가 아예 멈추지 않기 위한 하한이며, "통계적으로 유의하다"는 뜻이 아니다.
- n≥30/10은 **코드 플래그로 추가하지 않는다** — report를 읽는 사람의 판독 기준일 뿐이다. 따라서 F2 run-profile 플래그 등록 대상도 아니다. 이후 코드 강제가 필요해지면 그 시점에 별도 플래그로 승격하고 F2 가드(`test_f2_every_feature_flag_has_owner`)를 따른다.

### Insufficient sample

> **`advisor_lift.<source>_vs_default: null` = below MIN_SAMPLE의 canonical machine-readable 표현.**

별도 `insufficient_sample` field는 추가하지 않는다. text render는 기존 `— (below MIN_SAMPLE)`를 유지한다.

---

## Current Status

### 이미 구현됨 — 유지

- `feedback_report._is_verdict_eligible()`: `phase == "execute"`만 clean-pass/lift 분모로 사용.
- `verdict_eligible_total` field는 이미 report에 있다.
- `default` / `history` / `explore` source별 bucket과 `advisor_lift`.
- MIN_SAMPLE 미달 lift는 `null`, text render는 `— (below MIN_SAMPLE)`.
- `AGENT_LAB_FEEDBACK_EXPLORE_RATE` — `feedback_advisor.py` + `runtime_flags.py` 등록 완료.
- **(§1 완료)** `feedback_report`에 `turn_signal_total`, `oracle_verdict_coverage` field 추가 완료 — `verdict_eligible_total`에서 파생, `total`이 0이면 `oracle_verdict_coverage`는 0.0.
- **(§1 완료)** `turn_source_counts` field 추가 완료 — 전체 ledger(row phase 무관)의 `advisor_source` 분포. `by_source`는 completed episode 품질 분모 전용이고, `turn_source_counts`는 S1.5 loop closure / explore 비교군 관측 전용이다.
- **(§1 완료)** `feedback_advisor._advise_inner()`가 2단계 selection을 수행: 같은 category/topic overlap 중 `phase=execute` row가 MIN_SAMPLE 이상이면 그것만 사용(`evidence=execute`), 부족하면 기존 turn row까지 포함한 전체 pool로 fallback(`evidence=turn_fallback`) — cold-start 동작 유지. rationale에 `evidence=` marker 포함.

- **(§2 완료)** `evals/` 추가 완료: `cases.jsonl`(10 case) · `trace_export.py` · `graders.py`(8 grader) · `run_local.py` · `results/.gitignore`. `make eval-surface-local` 실행 시 10 graded / 0 skipped / 0 failed.
- **(§3 완료)** `run_local.build_report()`가 `evals/results/latest.json`에 `supersample: {t0, t1, t2}` 섹션을 생성 — T0 지표는 실제 grader 결과에서 계산, T1은 quickstart 명령 목록 + `fork_time_minutes: 12` 기준선, T2는 정의만(`gate: false`).
- **(§2 완료)** S1/S2/S3는 committed fixture 대신 `mock_run` contract로 임시 sessions directory에 deterministic mock run을 생성해 채점 — v1 local surface에서 skip 상태로 남는 case는 없다. 세 case는 `routing_contract`와 `session_contract`로 category, `turn_profile`, required spans, quick `agent_subset`, S3 role plan을 고정하고, `generated_mock_quality`로 topic echo, 도메인 topic terms, completed status, full agent roster/success, message/reply count, parse-error-free profile route, category signal을 검증한다. report에는 `supersample.t0.s_case_quality_pass_rate`와 `s_case_quality_failed`로 별도 노출한다.
- **(§5 완료)** 공개 재현 문서(REPRODUCTION-REPORT/QUICKSTART/FORK)에 eval-surface 재현 절차가 반영됐다.

### 부족한 부분

- `fork_time_minutes`는 여전히 수동 측정값 — clean-clone 자동화는 N8 잔여 항목으로 이 계획의 범위 밖.

---

## Key Decisions

- `feedback_report`의 canonical field는 **`verdict_eligible_total` 유지**. `completed_episode_count`는 새 canonical field로 추가하지 않고 문서를 정정한다.
- 새로 추가한 field는 중복이 적고 유용한 것만 (§1에서 구현 완료):
  - `turn_signal_total = total - verdict_eligible_total`
  - `oracle_verdict_coverage = verdict_eligible_total / total`
  - `turn_source_counts = 전체 ledger의 advisor_source 분포`
- `feedback_advisor`는 completed episode를 우선 사용하되, 표본 부족 시 기존 turn signal fallback을 유지한다 (§1에서 구현 완료).
- eval surface report(§2)에는 표시용 이름으로 `completed_episode_count`를 써도 되지만, 값은 `feedback_report.verdict_eligible_total`에서 **파생**한다 (재계산 금지).
- 문서 중복 제거: episode signal 정의·field는 이 문서 [Canonical Definitions](#canonical-definitions)가 SSOT이고, [EVAL-SURFACE-V1-PLAN.md](./EVAL-SURFACE-V1-PLAN.md)는 EvalTrace schema / case contract / grader 스펙만 담는다.

---

## Implementation Changes

### 1. Episode 품질 정리 보강 — ✅ 완료

- ~~`feedback_report`에 `turn_signal_total`, `oracle_verdict_coverage`를 추가한다.~~ 완료 ([feedback_report.py](../src/agent_lab/feedback_report.py)).
- ~~docs의 `completed_episode_count` 약속을 `verdict_eligible_total`로 정정한다.~~ 완료 (이 문서 + V1-PLAN).
- ~~`feedback_advisor`의 relevant row selection을 두 단계로.~~ 완료:
  1. 같은 category/topic overlap의 **phase=execute rows**를 먼저 사용.
  2. execute rows가 MIN_SAMPLE 미만이면 기존 turn rows까지 fallback (cold-start 동작 유지).

**Acceptance — 검증 완료**

- `make feedback-report JSON=1`에 기존 field가 유지되고 새 coverage field가 추가된다. (`.venv/bin/python scripts/feedback_report.py --root . --json`로 확인: `turn_signal_total`, `oracle_verdict_coverage` 존재.)
- `make dogfood-feedback-mock`은 completed episode가 없어도 `turn_source_counts`로 advisor history/explore 사용량을 출력한다 (실측: default 42 · history 34 · explore 0).
- verdict 없는 turn row가 clean-pass/lift 분모에 섞이지 않는다. (`tests/test_feedback_report.py::test_turn_and_legacy_rows_excluded_from_clean_pass` 등.)
- advisor는 execute evidence가 충분할 때 turn-only row에 끌려가지 않는다. (`tests/test_feedback_advisor.py::test_advise_setup_prefers_execute_evidence_over_turn_rows`, `::test_advise_setup_falls_back_to_turn_rows_below_min_sample`.)

---

### 2. OpenAI식 Eval Surface 추가 — ✅ 완료

> **구체 스펙:** [EVAL-SURFACE-V1-PLAN.md](./EVAL-SURFACE-V1-PLAN.md) — EvalTrace schema, span 이름, case contract 예시, grader result shape.

- `evals/` 추가 완료:

| Artifact | 역할 |
|----------|------|
| [`cases.jsonl`](../evals/cases.jsonl) | v1 case contract (10개) |
| [`cases.py`](../evals/cases.py) | case JSONL loader |
| [`trace_export.py`](../evals/trace_export.py) | session folder → eval trace 변환 (fail-open, span 합성) |
| [`graders.py`](../evals/graders.py) | deterministic graders (8개, opt-in 방식) |
| [`mock_generation.py`](../evals/mock_generation.py) | fixture 없는 case의 deterministic mock session 생성 |
| [`report.py`](../evals/report.py) | fixture/mock-safe grading + supersample report |
| [`run_local.py`](../evals/run_local.py) | CLI facade |
| `results/.gitignore` | local result 제외 (committed reference는 mock fixture만) |

- v1 case 10개: S1, S2, S3(`generated_mock`), M3, M4, M5, L1, L2, L3, X2(fixture 매핑 완료).
- v1 grader: `routing_contract` · `session_contract` · `generated_mock_quality` · `gate_integrity` · `objection_flow` · `plan_contract` · `oracle_coverage` · `trace_completeness`. `gate_integrity`/`trace_completeness`는 항상 실행(불변식 검사); 나머지는 case의 `expected` key 또는 `mock_run` 선언 여부로 opt-in.
- `make eval-surface-local` 추가 완료 → `evals/results/latest.json` 생성 (10 graded / 0 skipped / 0 failed).

**구현 중 확정된 사실**

- 기존 `sessions/_regression/*` fixture에는 `trace.jsonl` / `outcomes.jsonl`이 없다(`run.json` / `chat.jsonl` / `plan.md`만) — exporter는 `run.json`의 구조적 근거(category/objections/actions/approvals/executions)만으로 v1 span을 **합성**한다. `feedback_advisor` span은 session_id ↔ outcomes.jsonl join이 필요해 v1에서는 항상 부재(향후 과제) — `trace_completeness`를 구조적으로 낮추지만 실패로 처리하지 않는다.
- S1/S2/S3에 맞는 committed fixture가 `sessions/_regression`에 없으므로, `run_local.py`는 case의 `mock_run` 설정을 읽어 `AGENT_LAB_MOCK_AGENTS=1`로 임시 sessions directory에 deterministic mock session을 생성한 뒤 `session_source: "generated_mock"`으로 채점한다. 이 generated case들은 단순 completeness smoke가 아니라 `category`, `turn_profile`, `workflow_id`, `required_spans`를 고정하고, S1/S2는 quick `agent_subset=["cursor"]`, S3는 `role_plan={"cursor":"proposer","codex":"executor","claude":"critic"}`를 검증한다. 추가로 `generated_mock_quality`가 topic echo, 도메인 topic terms, `status="completed"`, cursor/codex/claude roster와 succeeded agents, 최소 message/reply count, envelope parse error 0, `category.source="profile"`, `category.signals`를 검증한다. room 회귀 스위트(`scripts/smoke_room.py`의 고정 `SCENARIOS` 목록)에는 새 fixture를 추가하지 않는다.
- `oracle_coverage`는 case가 `expected.final_oracle_verdict`/`min_oracle_coverage`를 선언할 때만 채점한다 — 선언 없이 실행마다 강제하면 오라클 단계가 없는 정상 실행(예: L2 worktree-merge-only)을 오탐으로 fail 처리하게 된다.

**Acceptance — 검증 완료**

- `router=absent != deep` 같은 문제는 routing regression으로 기록된다 (`routing_contract` grader, `tests/test_eval_surface_graders.py`).
- 실패 case는 `case_id`, `session_id`, `reason`, `evidence`를 가진다 (`tests/test_eval_surface_run_local.py::test_missing_fixture_folder_reports_error_not_crash` 등).

---

### 3. T0/T1/T2 슈퍼샘플 판정 연결 — ✅ 완료

**산출 위치:** `report.py`가 `evals/results/latest.json` top-level에 `supersample` 섹션을 생성한다. "T0/T1/T2 표"는 이 JSON과 `make eval-surface-local`의 text summary를 말하며, 별도 문서 수작업 집계가 아니다.

```jsonc
// evals/results/latest.json (shape)
{
  "cases": [...],
  "supersample": {
    "t0": {
      "routing_pass_rate": 1.0,
      "human_gate_bypass_count": 0,
      "oracle_verdict_coverage": 1.0,
      "trace_completeness_rate": 1.0,
      "trace_completeness_interpretation": "strong_trace_coverage",
      "s_case_quality_pass_rate": 1.0,
      "s_case_quality_failed": [],
      "objection_flow_pass_rate": 1.0
    },
    "t1": {
      "quickstart_commands": ["make quickstart-verify", "..."],
      "expected_report_shape": "evals/results/latest.json#supersample",
      "fork_time_minutes": 12     // REPRODUCTION-REPORT 기준선 — 수동 재측정 시 함께 갱신
    },
    "t2": {
      "external_fork_count": null,
      "external_issue_count": null,
      "external_pr_count": null,
      "gate": false               // v1에서 gate로 쓰지 않음
    }
  }
}
```

- **T0** — eval report에서 계산: routing pass rate · human gate bypass count · Oracle coverage · trace completeness · objection flow pass rate.
- **T1** — 재현 report에서 계산하거나 기록: quickstart command list · expected report shape · `fork_time_minutes`.
  - `fork_time_minutes`는 **v1에서는 수동 측정 기준선**이다: clean clone에서 quickstart 완주까지 걸린 시간을 [REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md)에 기록하고 `evals/report.py`의 `FORK_TIME_MINUTES_BASELINE`과 동기화한다. clean-clone 자동 측정은 NORTH-STAR N8 잔여 항목이며 **이 계획의 범위 밖**이다.
- **T2** — 지표 정의만 문서화: external fork/issue/PR count. v1에서는 gate로 쓰지 않는다.

**Acceptance — 검증 완료**

- `make eval-surface-local` 실행 후 `evals/results/latest.json`의 `supersample` 섹션만으로 T0/T1/T2 준비도가 판독된다 (2026-07-07 실측: `routing_pass_rate=1.0`, `human_gate_bypass_count=0`, `oracle_verdict_coverage=1.0`, `s_case_quality_pass_rate=1.0`, `trace_completeness_rate=1.0`, `trace_completeness_interpretation=strong_trace_coverage`).
- generated mock `S1/S2/S3`는 eval-only trace enrichment로 `trace_completeness=1.0`을 달성한다.
- 2026-07-07 이후 `trace_completeness`는 case별 `trace_profile` 분모를 사용한다. 즉 `M4`/`L1` 같은 discuss-only fixture는 execute/human/oracle 부재 때문에 구조적으로 낮게 보지 않는다. 이어서 `M5` fixture에 최소 `plan_update` 신호를 보강해 v1 10개 케이스 전부 `trace_completeness=1.0`을 달성했다.
- T2 지표가 null이어도 T0/T1 판정이 실패로 표시되지 않는다 (`tests/test_eval_surface_run_local.py::test_supersample_section_shape`).

---

### 4. S1.5 Explore 비교군 운영화 — ✅ 완료

explore mechanism은 **유지하고 재구현하지 않는다** (코드 변경 없음). 운영 절차와 해석 기준을 [EVAL-PROGRAM.md](./EVAL-PROGRAM.md) §4 "S1.5 explore 비교군"에 문서화했다:

```bash
AGENT_LAB_FEEDBACK_EXPLORE_RATE=0.1 make dogfood-feedback-mock
# 초기 강제 검증은 별도 smoke에서만:
AGENT_LAB_FEEDBACK_EXPLORE_RATE=1.0 make dogfood-feedback-mock
```

- report 해석 기준 ([Canonical Definitions](#canonical-definitions)의 임계값 표 참조):
  - `advisor_lift.history_vs_default == null` → below MIN_SAMPLE.
  - `advisor_lift.explore_vs_default == null` → explore 비교군 부족.
  - n≥30 = 비교군 신뢰 기준, n≥10 = early signal (둘 다 사람 해석 기준, 코드 게이트 아님).

**Acceptance — 충족 (기존 구현 + 문서화)**

- explore row가 0개일 때 `advisor_lift.explore_vs_default == null` → "비교군 없음"으로 해석된다 (기존 `feedback_report.py` 동작, `tests/test_feedback_report.py`로 검증됨).
- explore row가 있을 때 `by_source.explore`에 별도 집계된다 (기존 동작).

---

### 5. 공개 재현 패키지 + 문서 정리 — ✅ 완료

- **문서 drift 제거 — 완료:**
  - 이 문서(v2)가 현행 구현 상태의 SSOT.
  - [EVAL-SURFACE-V1-PLAN.md](./EVAL-SURFACE-V1-PLAN.md)의 "Episode signal 정리" 섹션을 이 문서 참조로 대체하고, `completed_episode_count` 등 폐기된 field 이름을 정정 완료. V1-PLAN에는 EvalTrace schema / case contract / grader 스펙만 남았다.
- [REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md)에 "Eval Surface 재현 (T0/T1)" 섹션 추가 완료 — `make eval-surface-check` 절차 + `fork_time_minutes=12` 기준선 연결(`evals/report.py`의 `FORK_TIME_MINUTES_BASELINE`과 동기화).
- [QUICKSTART.md](./QUICKSTART.md)의 필수 1~6단계는 그대로 두고, "다음 단계" 표에 eval-surface 재현 링크만 추가 — **최소 경로** 원칙 유지.
- [FORK.md](./FORK.md) §6에 `make eval-surface-check`를 벤치·KPI 유지 번들에 추가하고, 신뢰 report 표(Quickstart/Emergence/Eval surface/S1.5 feedback × T-layer)를 신설했다.
- [EVAL-PROGRAM.md](./EVAL-PROGRAM.md) §4에 S1.5 explore 운영 절차를 추가했다 (§4 참조).
- 공개 재현 명령:

```bash
make quickstart-verify
make emergence-bench-check
make feedback-report JSON=1
make dogfood-feedback-mock
make eval-surface-check
make eval-surface-local
```

**Acceptance — 검증 완료**

- clean clone 기준으로 T0/T1 mock evidence를 재현할 수 있다 (`make eval-surface-local` 종료 코드 0, `evals/results/latest.json#supersample`).
- committed reference는 **mock-only**이고 live evidence는 로컬 report로 남긴다 (`evals/results/.gitignore`가 생성 JSON을 제외).
- 두 계획 문서 사이에 completed episode 정의·field 이름이 서로 다르게 남아 있지 않다 (V1-PLAN §1이 이 문서를 참조만 함).

---

## Test Plan

### Unit

- `feedback_report`가 `verdict_eligible_total`, `turn_signal_total`, `oracle_verdict_coverage`를 정확히 계산한다. — ✅ (`tests/test_feedback_report.py`)
- `feedback_report`가 quality denominator와 별도로 `turn_source_counts`를 계산한다. — ✅ (`tests/test_feedback_report.py`)
- `feedback_advisor`가 execute rows를 우선하고 부족할 때만 turn rows로 fallback한다. — ✅ (`tests/test_feedback_advisor.py`)
- trace exporter가 minimal `run.json`, missing/malformed run.json을 fail-open으로 처리한다. — ✅ (`tests/test_eval_surface_export.py`)
- graders가 S generated mock session contract, M3 BLOCK, M4 CHALLENGE→AMEND, L1 deep routing, Oracle missing/mismatch를 판정한다. — ✅ (`tests/test_eval_surface_graders.py`, `tests/test_eval_surface_run_local.py`)
- 신규 테스트는 `test-fast` lane에 포함되도록 `live`/`integration` marker 없이 작성한다.

### Integration

```bash
make feedback-report JSON=1
make dogfood-feedback-mock
make eval-surface-check
make emergence-bench-check
# 최종 통합 전
make test-fast
```

### Manual

- supervisor dogfood 1회 후 `.agent-lab/outcomes.jsonl` row 증가 확인.
- `make feedback-report JSON=1`에서 `verdict_eligible_total`, `turn_source_counts`, null lift 해석 확인.

---

## Assumptions

| 가정 | 내용 |
|------|------|
| canonical field | `feedback_report.verdict_eligible_total`이 completed episode count의 canonical 이름 |
| insufficient sample | `advisor_lift: null`이 canonical machine-readable 표현 |
| OpenAI식 eval | 구조를 따른다는 뜻; hosted eval 업로드는 v1에서 하지 않음 |
| 범위 밖 | LLM semantic judge, S2 global bandit, S3 tool discovery, UI dashboard, clean-clone fork_time 자동 측정 |
| 불변 (eval 대상) | Human gate, BLOCK→409, worktree isolation, Oracle verify — 변경 대상이 아니라 **eval 대상** |
