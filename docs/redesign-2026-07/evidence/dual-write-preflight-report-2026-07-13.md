# Dual-write cutover pre-flight report — 2026-07-13

> **판정:** Pre-flight **PASS** — controlled cohort(100건·60분·실운영 ledger)는 **미실행**, Human cutover 승인 전 단계.

## 실행 시각

2026-07-13 20:50 KST · machine: local dev (`/Users/yoonjong/Projects/agent-lab`)

## 범위

[cutover scope limitations](./dual-write-cutover-scope-limitations-2026-07-13.md) 기준 **기술 pre-flight**만 수행했다.

| 항목 | 이번 실행 | 비고 |
| --- | --- | --- |
| pytest (dual-write·verify·observability·recovery·kernel·read_model) | ✅ | 아래 명령 |
| production route cohort + rollback | ✅ | 격리 `/tmp`, `AGENT_LAB_MOCK_AGENTS=1` |
| `sessions/` read-only verify | ✅ | 115세션 스캔, write 없음 |
| controlled cohort 100건·60분 | ⏭ | 실운영 process + ledger — 별도 |
| supervisor dogfood 커버리지 비율 | ⏭ | 실 사용 트래픽 필요 |

## 1) pytest

```bash
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python -m pytest \
  tests/test_mission_dual_write.py \
  tests/test_mission_dual_write_verify.py \
  tests/test_dual_write_observability.py \
  tests/test_activity_queue_recovery.py \
  tests/test_mission_read_model.py \
  tests/test_mission_kernel.py \
  tests/test_crash_recovery.py \
  -q
```

**결과: 80 passed** (2.89s)

추가 harness 회귀:

```bash
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python -m pytest tests/test_mission_dual_write_evidence.py -q
```

**결과: 1 passed**

포함 시나리오 요약: plan approve/reject bridge, inbox create/resolve(execution gate), execute/merge/oracle/repair, observability bucket(`expected_boundary`), verify query item-level parity, ActivityQueue recovery, kernel gate FSM, `compute_operational_status`.

## 2) production route cohort + rollback

```bash
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/mission_dual_write_route_cohort.py \
  --sessions /tmp/.../sessions \
  --repos /tmp/.../repos
```

**exit code: 0**

| 게이트 | 결과 |
| --- | --- |
| `cohort_parity_pass` (10 route session) | true |
| `rollback_pass` (flag OFF 신규 + 기존 mirrored) | true |
| `extended_pass` (fail→repair + crash recovery) | true |

Exercise된 route: `plan/approve`, `plan/reject`, `inbox/resolve`, `execute/resolve`, `execute/merge/confirm`, `execute/reverify` — 전부 `mirrored=true` + read-model `migrated=true` (합성 세션, 운영 `sessions/` 미변경).

## 3) operational `sessions/` verify (read-only)

```bash
.venv/bin/python scripts/mission_dual_write_verify.py --sessions sessions/
```

| 메트릭 | 값 |
| --- | --- |
| checked | 115 |
| migrated_count | 0 |
| hard_mismatch_count | 0 |
| hard_mismatch_sessions | [] |

운영 디렉터리에는 아직 Mission journal이 없다(`migrated=0`). dual-write flag ON 운영 cohort 전 baseline으로 **divergence 없음**.

`git status sessions/` — pre-flight 전후 변경 없음(스크립트는 `sessions/`에 쓰지 않음).

## Pre-flight 판정

| 체크 | 상태 |
| --- | --- |
| Route dual-write + rollback 안전성 | PASS |
| Parity verify 쿼리 (read-only) | PASS |
| Regression pytest | PASS |
| 운영 `sessions/` 오염 | 없음 |

**다음 단계 (Human/운영):**

1. 전용 API process에 `AGENT_LAB_MISSION_DUAL_WRITE=1` (+ 필요 시 allowlist)
2. 100 dual-write · 60분 관찰 + `verify --cohort` / health 카운터 ledger
3. startup eager recovery · `DUAL_WRITE=0` rollback 스모크 (실 process 재시작)
4. 통과 후 cutover 범위 Human 승인 · 후속 설계 이슈(gate/projection/dashboard)

## 참고

- 판정 SSOT: [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)
- 운영 절차: [controlled cohort runbook](./dual-write-controlled-cohort-runbook-2026-07-13.md)
- 이전 route cohort 증거: [dual-write-route-cohort-report](./dual-write-route-cohort-report-2026-07-13.md)
