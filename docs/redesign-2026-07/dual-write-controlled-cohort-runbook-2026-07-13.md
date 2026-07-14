# Dual-write controlled cohort runbook — 2026-07-13

> **Current runtime note (M6-9):** This runbook's v3d GO and any enable evidence are historical records. The dual-write bridge now fails closed unless `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS` is non-empty and contains the session ID; an empty or missing allowlist disables the bridge. Slice 1–3 authority functions and their environment variables are retired, ignored, and fail-closed. Do not use historical authority examples as configuration.

## 판정 (historical evidence; non-runtime)

- Historical evidence gate: **GO** (operational cohort **v3d** — [cohort run report](./dual-write-cohort-run-report-2026-07-13.md))
- `AGENT_LAB_MISSION_DUAL_WRITE=1`: controlled cohort 전용 process에서 **non-empty allowlist와 함께** 사용해야 함; Full traffic은 **별도** Human 승인 ([full-traffic runbook](./dual-write-full-traffic-bounded-cutover-2026-07-14.md), soak ≥15 Room turns)
- legacy writer: cohort·Full traffic soak 전체 기간 **항상 유지**
- legacy writer 제거·irreversible cleanup: **Human 승인 전 금지** (Full traffic soak 이후 별도 gate)

## Cutover scope SSOT

판정 범위·문서화된 제한·커버리지·후속 설계 분리: **[dual-write cutover scope and limitations](./dual-write-cutover-scope-limitations-2026-07-13.md)**.

요약 — cohort **실패로 세지 않는** Human Inbox 경계:

- plan 승인 직후 human question → mirror 대상
- 실행 도중 question → v1 기준 `mirrored=false`, `reason=mission_not_ready_to_execute` (기대 동작)
- execution-level gate / `MissionOperationalStatus` projection / dashboard 전환 → **이번 cutover에 섞지 않음** (cohort 통과 후 별도 이슈)

cohort 시작 전·이전 운영분이 있으면 `scripts/mission_dual_write_verify.py --cohort`로 baseline divergence를 확인한다.

## 운영 경계

`AGENT_LAB_MISSION_DUAL_WRITE`는 프로세스 단위 master flag이고, `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS`는 코드가 매 호출마다 적용하는 session allowlist다. 현재 코드는 allowlist가 비어 있거나 누락되면 **fail-closed**로 bridge를 끈다. controlled cohort는 다음처럼 항상 non-empty allowlist로 격리한다.

1. cohort traffic만 전달하는 전용 API 프로세스에도 `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS=session-a,session-b`처럼 non-empty allowlist를 설정한다.
2. 공유 API 프로세스를 사용할 때도 cohort session ID만 포함하는 non-empty allowlist를 반드시 설정한다.
3. cohort session identity를 전용 deployment/route로 고정하고, 나머지 traffic은 legacy-only 프로세스로 보낸다.

allowlist 없이 master flag만 켜는 것은 controlled cohort가 아니며, 현재 런타임에서는 bridge가 동작하지 않는다.

## Cohort 규모

| 항목 | 값 |
| --- | --- |
| Dual-write 작업 | **100건** |
| 관찰 창 | **60분** (baseline 이후 주기적 verify + health) |
| 실패 | unexplained mismatch / missing / unexpected duplicate **0건** |

## 필수 스모크 (시작 전·종료 후)

1. Startup eager recovery — `/api/health/daemon` → `last_activity_recovery_result.reason=startup`
2. `AGENT_LAB_MISSION_DUAL_WRITE=0` rollback — 신규 세션 journal 없음 + 기존 mirrored 세션 legacy 정상

## 커버리지 ledger (판정과 별도)

[scope doc](./dual-write-cutover-scope-limitations-2026-07-13.md) §커버리지: human question 총수, mirrored, `mission_not_ready_to_execute`, 실행 중 question 비율.

## 시작 전 체크

- cohort session ID와 담당 Human을 ledger에 기록한다.
- `AGENT_LAB_MISSION_DUAL_WRITE=1`이 전용 process에만 적용됐는지 확인한다.
- 공유 process를 사용하는 경우 allowlist가 비어 있지 않고 cohort session ID만 포함하는지 확인한다.
- legacy route의 plan/approve, plan/reject, inbox/resolve, execute/resolve, merge/confirm, reverify가 계속 접근 가능한지 확인한다.
- rollback 명령과 flag OFF 후 legacy-only health check를 준비한다.
- 시작 시점의 `migrated`, `mirrored`, event cursor, side-effect count를 baseline으로 남긴다.

## 관찰해야 할 증거

각 cohort 작업마다 다음을 같은 `session_id`·`mission_id`·`idempotency_key`로 기록한다.

- legacy response/status와 Mission event sequence
- `mission_dual_write.mirrored=true` 및 read-model `migrated=true`
- merge commit SHA와 event cursor parity
- side-effect 실행 횟수 1회 및 duplicate 없음
- Oracle verdict, repair attempt, Human Inbox pause/resume 결과
- 재시작/reconnect 후 read-model과 projection의 동일성

누락 write, 중복 side-effect, ordered event mismatch, rollback 실패가 한 건이라도 발생하면 cohort를 즉시 중지하고 flag OFF 경로를 실행한다.

## Rollback

`AGENT_LAB_MISSION_DUAL_WRITE`는 순수 OS 환경변수이며 live-reload/toggle API가 없다(코드에 POST 라우트 없음, 확인됨: [dual-write-operational-readiness-check-2026-07-13](dual-write-operational-readiness-check-2026-07-13.md)). "즉시 rollback"은 재시작 없이 되는 것이 아니라 **재시작 한 번이면 100% 안전하게** 되는 것이다. 코드는 매 호출마다 flag를 새로 읽으므로(캐싱 없음) 재시작 이후에는 지연 없이 legacy-only로 복귀한다.

1. 전용 process의 `AGENT_LAB_MISSION_DUAL_WRITE`를 `0`으로 바꾸고 **프로세스를 재시작한다.**
2. 새 session에서 Mission journal이 생성되지 않고 legacy route가 정상 동작하는지 확인한다.
3. 이미 mirrored된 session에서도 legacy route가 계속 정상 동작하는지 확인한다.
4. 실패한 cohort identity와 evidence를 보존하고, 원인·재현·재개 조건을 Human Inbox에 남긴다.

Rollback은 legacy writer를 제거하지 않으며, Mission journal을 삭제하지 않는다.

## Cohort 밖 승격 조건

다음 조건을 모두 충족하고 Human이 별도 승인할 때만 cohort 범위를 넓힌다.

- dual-write 결과가 legacy observation과 Mission read-model/event sequence에서 일관된다.
- material duplicate write 또는 missing write가 관찰되지 않는다.
- side-effect가 모든 검증 경로에서 단일 실행으로 유지된다.
- fail→repair, Human pause/resume, reconnect/restart 결과가 parity를 유지한다.
- flag OFF rollback이 실제 운영 경로에서 재현된다.
- rollback window, legacy writer retire 시점, irreversible cleanup 범위를 Human이 명시적으로 승인한다.

이 문서는 legacy writer retire 승인으로 해석하지 않는다. 현재 권위는 [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)과 [NOW](../NOW.md)다.
