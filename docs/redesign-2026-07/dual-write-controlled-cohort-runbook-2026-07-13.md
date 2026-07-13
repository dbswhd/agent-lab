# Dual-write controlled cohort runbook — 2026-07-13

## 판정

- Evidence gate: **GO**
- `AGENT_LAB_MISSION_DUAL_WRITE=1`: **승인된 controlled cohort에서만 GO**
- legacy writer: cohort 전체 기간 동안 **항상 유지**
- 전체 traffic 승격, legacy writer 제거, irreversible cleanup: **Human 승인 전 금지**

## 운영 경계

`AGENT_LAB_MISSION_DUAL_WRITE`는 프로세스 단위 master flag이고, `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS`는 코드가 매 호출마다 적용하는 session allowlist다. allowlist가 비어 있으면 master flag가 켜진 모든 session이 대상이 된다. controlled cohort는 다음 중 하나로 격리한다.

1. cohort traffic만 전달하는 전용 API 프로세스에 flag를 켠다.
2. 공유 API 프로세스를 사용할 경우 `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS=session-a,session-b`처럼 non-empty allowlist를 반드시 설정한다.
3. cohort session identity를 전용 deployment/route로 고정하고, 나머지 traffic은 legacy-only 프로세스로 보낸다.

공유 production process에서 allowlist 없이 임의로 master flag만 켜는 것은 controlled cohort가 아니다.

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

1. 전용 process의 `AGENT_LAB_MISSION_DUAL_WRITE`를 `0`으로 전환한다.
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
