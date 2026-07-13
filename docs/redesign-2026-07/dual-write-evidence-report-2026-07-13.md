# Dual-write evidence cohort — 2026-07-13

## 판정

동일 `session_id`를 legacy `run.json` writer와 Mission journal writer에 함께 사용한 **실제 코드 경로 cohort 10건**을 확보했다. 5개 핵심 시나리오를 2건씩 실행했고, parity·side-effect 단일 실행·restart replay·read-model reconnect·Human Inbox resume가 모두 통과했다.

이 결과는 production sessions가 아닌 격리된 `/tmp/agent-lab-dual-write-evidence-20260713`에서 실행한 **production-like evidence**다. production HTTP route 자체에 dual-write flag를 켠 증거는 아니므로, Human cutover 승인 증거로 과장하지 않는다.

## 실행

```bash
AGENT_LAB_MOCK_AGENTS=1 \
.venv/bin/python scripts/mission_dual_write_evidence.py \
  --sessions /tmp/agent-lab-dual-write-evidence-20260713
```

결과 exit code: `0`

| 검증 항목 | 결과 |
| --- | --- |
| session count | `10` |
| scenario distribution | 각 시나리오 `2`건 |
| ordered Mission/legacy parity | `pass` |
| side-effect single execution | `pass` |
| fresh repository restart replay | `pass` |
| read-model API reconnect | `pass` |
| Human Inbox answer → Mission resume | `pass` |
| production route mutation | 없음 |

## 세션 대장

| # | session identity | 시나리오 | event parity | side effects | replay | reconnect | Inbox resume |
| ---: | --- | --- | --- | ---: | --- | --- | --- |
| 1 | `dualwrite-01-plan_reject_revisit` | plan reject → revisit | pass | 0 | pass | pass | n/a |
| 2 | `dualwrite-02-execute_success_merge_oracle_pass` | execute → merge → Oracle pass | pass | 1 | pass | pass | n/a |
| 3 | `dualwrite-03-oracle_fail_repair` | Oracle fail → repair | pass | 2 distinct keys, each once | pass | pass | n/a |
| 4 | `dualwrite-04-human_inbox_pause_resume` | Inbox pause → answer → resume | pass | 0 | pass | pass | pass |
| 5 | `dualwrite-05-daemon_crash_recovery` | daemon/crash recovery | pass + ActivityQueue completion | 0 | pass | pass | n/a |
| 6 | `dualwrite-06-plan_reject_revisit` | plan reject → revisit | pass | 0 | pass | pass | n/a |
| 7 | `dualwrite-07-execute_success_merge_oracle_pass` | execute → merge → Oracle pass | pass | 1 | pass | pass | n/a |
| 8 | `dualwrite-08-oracle_fail_repair` | Oracle fail → repair | pass | 2 distinct keys, each once | pass | pass | n/a |
| 9 | `dualwrite-09-human_inbox_pause_resume` | Inbox pause → answer → resume | pass | 0 | pass | pass | pass |
| 10 | `dualwrite-10-daemon_crash_recovery` | daemon/crash recovery | pass + ActivityQueue completion | 0 | pass | pass | n/a |

## 무엇을 실제로 확인했는가

- 모든 journal event의 `mission_id`와 세션 디렉터리 이름이 동일했다.
- legacy 관측은 `run.json` writer로 기록했고, Mission event는 `MissionRepository`/`MissionJournal`로 기록했다.
- execute/repair merge side effect는 exclusive-create idempotency key로 두 번 시도해도 key당 파일이 한 번만 생성됐다.
- 각 세션의 fresh `MissionRepository.load()`가 프로세스 재시작 후 상태를 복원했다.
- 실제 `/api/sessions/{session_id}/mission/read-model`을 `TestClient`로 호출해 `migrated=true`, `event_cursor` 일치를 확인했다.
- Inbox 시나리오는 실제 `create_inbox_item`과 `MissionApplication.answer_inbox()`를 사용해 resolved item과 `READY_TO_EXECUTE` resume을 확인했다.
- crash 시나리오는 실제 `ActivityQueue` claim → side-effect commit → complete와 새 queue snapshot을 사용했다.

## 제한과 다음 판정

이 문서는 후속 production route adapter·Room dogfood·fail→repair·recovery wiring이 반영되기 전의 baseline report다. 당시 cohort는 production-like dual-write 증거 10건이었지만 lifecycle writer 자동 연결 증거로 인정하지 않았고, 그 시점의 ADR 판정은 `NO-GO`였다. 최신 판정은 [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)과 [dual-write cutover follow-up](./dual-write-cutover-followup-2026-07-13.md)을 따른다.

다음 단계는 이 harness의 동일 계약을 production route의 opt-in cohort에 연결하고, 실제 sessions directory에서 10건을 재실행하는 것이다. 그때만 cutover 재심사를 요청한다.
