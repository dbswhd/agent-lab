# Dual-write production-route cohort + rollback — 2026-07-13

## 판정

실제 운영 `sessions/` 디렉터리(`/Users/yoonjong/Projects/agent-lab/sessions`, 이 머신에서 앱이 실제로 사용하는 그 디렉터리)를 대상으로 `AGENT_LAB_MISSION_DUAL_WRITE=1`을 켠 채 **production FastAPI route 10건**을 실제로 호출했다. 6개 legacy route(plan/approve, plan/reject, inbox/resolve, execute/resolve, execute/merge/confirm, execute/reverify) 전부를 최소 1회 이상 exercise했고, 모두 `mission_dual_write.mirrored=true` + read-model `migrated=true`를 반환했다. 이어서 flag를 끄고 (a) 신규 세션의 legacy-only 동작, (b) 이미 mirrored된 세션이 flag OFF 이후에도 legacy만으로 계속 동작하는지(rollback 안전성) 2건을 검증했고 모두 통과했다.

**exit code: `0`** — `cohort_parity_pass=true`, `rollback_pass=true`.

이전 [dual-write evidence cohort](dual-write-evidence-report-2026-07-13.md)는 kernel을 직접 호출하는 격리된 `/tmp` harness였다. 이번 실행은 그 문서가 명시한 다음 단계(prod route + 실제 sessions 디렉터리)를 채웠다. [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md) 재심사에 이 결과를 근거로 사용할 수 있다.

## 실행

```bash
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/mission_dual_write_route_cohort.py \
  --sessions "$(pwd)/sessions" \
  --repos /path/to/scratch/dualwrite-route-repos
```

`--sessions`는 운영 `sessions/` 절대경로를 그대로 가리켰다. `--repos`는 execute 시나리오가 쓰는 git 저장소를 위한 scratch 위치로, `sessions/` 바깥(리포지터리 밖 scratchpad)에 뒀다 — 세션 폴더 자체만 `sessions/`에 생성된다.

## Route cohort (10건)

| # | session_id | route | status | mirrored | read-model migrated | read-model state |
| ---: | --- | --- | ---: | --- | --- | --- |
| 1 | `dualwrite-route-01-plan-approve` | `POST /plan/approve` | 200 | true | true | READY_TO_EXECUTE |
| 2 | `dualwrite-route-02-plan-approve` | `POST /plan/approve` | 200 | true | true | READY_TO_EXECUTE |
| 3 | `dualwrite-route-03-plan-reject` | `POST /plan/reject` | 200 | true | true | DRAFTING |
| 4 | `dualwrite-route-04-plan-reject` | `POST /plan/reject` | 200 | true | true | DRAFTING |
| 5 | `dualwrite-route-05-inbox-resolve` | `POST /inbox/{item}/resolve` | 200 | true | true | READY_TO_EXECUTE |
| 6 | `dualwrite-route-06-inbox-resolve` | `POST /inbox/{item}/resolve` | 200 | true | true | READY_TO_EXECUTE |
| 7 | `dualwrite-route-07-execute-resolve` | `POST /execute/resolve` (approve, clean worktree merge) | 200 | true | true | VERIFYING |
| 8 | `dualwrite-route-08-execute-resolve` | `POST /execute/resolve` (approve, clean worktree merge) | 200 | true | true | VERIFYING |
| 9 | `dualwrite-route-09-merge-confirm` | `POST /execute/merge/confirm` (실제 conflict → human 해결) | 200 | true | true | VERIFYING |
| 10 | `dualwrite-route-10-reverify` | `POST /execute/reverify` | 200 | true | true | SUCCEEDED |

세션 7·8·9·10은 dry-run/agent mock 없이 **실제 git worktree/merge**를 사용했다(`create_exec_worktree` → 실제 브랜치·커밋·머지). 9번은 실제로 conflicting commit 두 개를 만들어 첫 `execute/resolve` 호출에서 legacy가 `merge_conflict`를 관측하도록 했고, human이 main에서 conflict를 해결한 뒤 `execute/merge/confirm`으로 마무리했다 — production에서 발생하는 순서 그대로다.

### `execute/resolve`(approve)와 Mission 상태 의미

세션 7·8에서 legacy 실행 상태는 그 호출 안에서 바로 `merged`가 되고, Mission bridge도 반환된 commit SHA가 있으면 같은 호출에서 `RecordMerge`를 기록한다. Mission read-model의 `VERIFYING`은 의도된 값이다. merge는 끝났지만 Oracle 검증이 남아 있기 때문이다. 따라서 parity 기준은 `merged_commit_sha`와 event cursor이며, 상태를 `SUCCEEDED`로 앞당기지 않는다. commit SHA가 없는 conflict 경로만 `merge/confirm` 또는 `reverify`에서 기록한다.

## Rollback (2건)

| session_id | route | flag | mirrored | 결과 |
| --- | --- | --- | --- | --- |
| `dualwrite-route-rb-01-fresh` | `POST /plan/approve` (신규 세션) | OFF | false | legacy 200 정상, `.agent-lab/mission-events.jsonl` **생성되지 않음** |
| `dualwrite-route-01-plan-approve` (cohort에서 이미 mirrored) | `POST /inbox/{item}/resolve` | OFF | false | legacy 200 정상 처리, read-model `event_cursor` 불변(추가 Mission event 없음) |

flag를 끄면 (1) 신규 세션은 Mission journal을 전혀 만들지 않고 legacy만 동작하고, (2) 이미 dual-write로 mirrored된 세션도 flag OFF 이후 legacy route가 계속 정상 동작하며 Mission bridge는 조용히 스킵된다(`mirror_*`가 `dual_write_enabled()`를 매 호출마다 다시 읽으므로 재시작 없이 즉시 반영). 롤백은 안전하다.

## 정리

증거를 남긴 뒤 합성 세션 11개(`dualwrite-route-*`)는 실제 운영 `sessions/`에서 제거했다 — 이 문서와 원본 JSON(`/tmp/route_cohort_real_out.json`, 세션 종료 후 휘발)이 증거 기록이다. 기존 세션은 스크립트가 새 폴더만 생성하므로 전혀 건드리지 않았다(`git status sessions/`에 이 11개 외 변경 없음 확인).

## 다음 판정

- Route coverage: `6/6` legacy route 실사용 경로에서 mirrored 확인.
- 운영 디렉터리: 실제 `sessions/`에서 실행(격리된 `/tmp`가 아님).
- Rollback: 신규/기존 세션 모두 flag OFF에서 안전.
- 남은 gap: 이번 cohort는 스크립트가 트리거한 합성 트래픽이다. 실제 사용자 turn(Room 루프)이 이 route들을 호출하는 실사용 dogfood는 아직 없다 — ADR-001의 "production traffic" 조건까지 완전히 채우려면 다음 단계로 실제 세션 1~2건에서 짧은 opt-in dogfood를 권장한다.
