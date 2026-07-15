# Dual-write cutover scope and limitations — 2026-07-13

> **역할:** controlled cohort의 GO/NO-GO 판정 범위 SSOT. 코드 확장(execution-level gate 전면 채택, projection/dashboard 전환)은 **이 cutover에 섞지 않는다.**

## 우선순위

모델을 더 넓히기 전에 **cutover 검증을 끝낸다.** 지금 할 일은 cohort 증거 수집과 rollback 안전성 확인이며, legacy writer retire는 Human 승인 전까지 금지([ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)).

## Cutover in-scope (반드시 mirror·parity)

| 경로 | dual-write 훅 | cohort 실패 조건 |
| --- | --- | --- |
| `POST /plan/approve` | `mirror_plan_approval` | `mirrored=false` (cohort 제외·아래 경계 제외) |
| `POST /plan/reject` | `mirror_plan_rejection` | 동일 |
| `POST /execute/resolve` · merge/confirm · reverify | `mirror_execution_transition` | unexplained `hard_mismatch` / missing event / unexpected duplicate |
| Plan 승인 직후 human question | `create_inbox_item` → `mirror_inbox_creation` | legacy pending인데 Mission gate 없음 (`mission_dual_write_verify.py` human_inbox) |
| Inbox resolve | `mirror_inbox_resolution` | resolve 후 gate/legacy 불일치 |

## Documented boundary vs cohort failure

| reason / 상황 | cohort 실패? |
| --- | --- |
| `mission_not_ready_to_execute` | **아니오** (`expected_boundary`) |
| `mission_journal_missing` (journal 전 inbox) | **예** — evidence window **폐기 후 재시작** |

v1 `BlockExecution` bridge 기준 실행 도중 question의 `mission_not_ready_to_execute`는 기대 동작이며 실패에 넣지 않는다. **2026-07-13 cohort에서 0건.**

> **코드 참고:** execution-level gate 구현은 리포에 있으나 **이번 cutover 판정과 분리** — [execution-gate-design-draft](./execution-gate-design-draft-2026-07-13.md).

## Controlled cohort 실행 조건

| 항목 | 값 |
| --- | --- |
| Flag | `AGENT_LAB_MISSION_DUAL_WRITE=1` (전용 process 또는 non-empty `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS`) |
| Dual-write 작업 수 | **100건** — **동일 operational cohort** (전용 process + allowlist + `sessions/`); 격리 `/tmp` 합성 **별도·합산 불가** |
| 관찰 창 | **≥60분** — **clean baseline 이후** ledger span ≥3,600s; 종료 시 **final tick**; mismatch 해소 전 구간은 인정하지 않음 |
| 실패 기준 | unexplained `hard_mismatch` / **missing write (`mission_journal_missing` 포함)** / unexpected duplicate **0건** |
| Legacy writer | cohort 전체 기간 **유지** |

운영 절차 상세: [controlled cohort runbook](./dual-write-controlled-cohort-runbook-2026-07-13.md).

## 필수 스모크 (cohort 전·후 각 1회)

1. **Startup eager recovery PASS** — API 부팅 직후 `/api/health/daemon`의 `last_activity_recovery_result.reason=startup` ([activity-queue auto-recovery](./activity-queue-auto-recovery-2026-07-13.md)).
2. **`AGENT_LAB_MISSION_DUAL_WRITE=0` rollback PASS** — flag OFF + 프로세스 재시작 후 (a) 신규 세션 journal 미생성, (b) 이미 mirrored 세션 legacy route 정상 ([route cohort rollback](./dual-write-route-cohort-report-2026-07-13.md) §Rollback).

## 커버리지 (판정과 별도 기록)

cohort ledger에 **통과/실패와 무관하게** 아래를 남긴다.

| 메트릭 | 수집 |
| --- | --- |
| 전체 human question 수 | legacy inbox pending 생성 수 (cohort session `run.json` / inbox API) |
| mirrored 수 | `/api/health/daemon` → `dual_write.operations.inbox_create.mirrored` |
| `mission_not_ready_to_execute` 수 | 동일 → `expected_boundary` (또는 로그 `reason=mission_not_ready_to_execute`) |
| 실행 중 question 비율 | question 생성 시점의 legacy execution phase / `mission.state` 스냅샷 샘플 |

비율은 cutover GO에 필수 조건이 아니다 — 실제 사용 흐름에서 mid-execution question이 차지하는 몫을 **나중 projection 설계** 입력으로 쓴다.

## Cohort 통과 후 (cutover와 분리)

별도 설계 이슈를 연다. 제목 예시:

- execution-level gate 모델 전면 채택 범위 (이미 구현된 kernel/read-model과 production cutover 경계 정리)
- 중앙 `MissionOperationalStatus` projection SSOT
- 대시보드 / MissionOverview read-model 전환 범위

이 이슈들은 legacy writer retire·full traffic 승격 **이후** 또는 Human이 명시적으로 승인한 시점에 착수한다.

## 관련 도구

```bash
# 반복 parity (cohort session만)
.venv/bin/python scripts/mission_dual_write_verify.py --sessions sessions/ --cohort

# health + dual_write 카운터 스냅샷
curl -s localhost:8765/api/health/daemon | jq '.dual_write'
```
