# ActivityQueue 자동 복구 연결 — 2026-07-13

ADR-001의 마지막 열린 질문("ActivityQueue crash recovery가 자동이 아님")에 대한 결정: **자동으로 연결한다.** 사용자가 지정한 구조(startup eager + scheduler throttled safety-net, 단일 idempotent 함수, single-flight lock)를 그대로 구현했다.

## 구조

```
_api_startup()
    └─ recover_activity_queue(reason="startup", blocking=True)   # 부팅 완료 전 즉시 1회, 대기하며 락 획득

scheduler_tick()
    └─ _maybe_run_activity_recovery(...)
           if force or recovery_due(interval_s):
               recover_activity_queue(reason="periodic", blocking=False)  # 락 있으면 이번 tick은 skip
```

- **`src/agent_lab/mission/activity_recovery.py`** (신규) — 유일한 실제 로직. `agent_lab.crash_recovery`(G3)와 정확히 같은 관계: `ActivityQueue.recover()`(per-session, idempotent)를 모든 세션에 대해 스캔하는 orchestration layer.
- **single-flight**: `sessions_root/.activity-queue-recovery.lock`에 `fcntl.flock`. Startup 호출은 blocking(대기), scheduler tick 호출은 non-blocking(락 걸려있으면 즉시 skip, `locked_out=true`) — 느린 스캔이 tick을 막지 않는다. 파일 락이라 스레드뿐 아니라 같은 sessions 디렉터리를 공유하는 여러 프로세스도 직렬화된다.
- **throttle**: `sessions_root/.activity-queue-recovery-state.json`에 `last_run_at` 기록. `AGENT_LAB_ACTIVITY_RECOVERY_INTERVAL_S`(기본 300초, 30~3600 clamp) 미경과 시 `scheduler_tick`은 호출 자체를 skip(락도 안 건드림). `force=true`는 interval을 무시하지만 락은 여전히 존중한다.
- **opt-out**: `AGENT_LAB_ACTIVITY_QUEUE_RECOVERY=0` (기본 on, G3의 `AGENT_LAB_CRASH_RECOVERY`와 동일한 관례).
- **가시성**: `daemon_state.py`에 `record_last_activity_recovery()` 추가, `/api/health/daemon`이 `last_activity_recovery_at`/`last_activity_recovery_result`를 G3의 `last_recovery_*`와 나란히 노출.
- 절대 raise하지 않는다(G3 doc string 관례 그대로) — 세션 하나가 깨져도 스캔 전체를 막지 않고, 예외는 `errors` 카운트로 흡수한다.

## 검증

`tests/test_activity_queue_recovery.py` (7건, 신규):
- committed side effect가 스캔 한 번으로 completed 처리됨
- 세션 하나가 깨져도(`activities.json` 손상) 나머지는 정상 처리되고 에러만 카운트
- `AGENT_LAB_ACTIVITY_QUEUE_RECOVERY=0`이면 스캔 자체를 안 함
- 락이 걸려있으면 non-blocking 호출은 `locked_out=true`로 즉시 반환하고 아무것도 건드리지 않음(락 해제 후 재호출하면 정상 복구)
- `recovery_due()`가 interval 경과 여부로 올바르게 throttle
- `scheduler_tick(force=True)`가 activity recovery를 실행하고 실제로 completed 처리
- `scheduler_tick(force=False)`는 방금 돈 recovery를 interval 내에서 다시 돌리지 않음(`activity_recovery=None`)

```
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python -m pytest tests/test_activity_queue_recovery.py tests/test_mission_os_phase1.py tests/test_crash_recovery.py tests/test_mission_dual_write.py -q
→ 50 passed
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python -m pytest tests/ -k "scheduler or activity_queue or crash_recovery or mission_dual_write or daemon_state or health" -q
→ 86 passed
```

실제 uvicorn 서브프로세스로 라이브 스모크도 확인했다: 부팅 직후 `/api/health/daemon`이 `last_activity_recovery_result={"reason":"startup","scanned":0,...}`를 정상 반환.

## scheduler 경로 해석 보정

백그라운드 tick이 모듈 import 시점의 `SESSIONS_DIR=None`을 영구 사용하지 않도록 scheduler가 호출 시점의 `active_sessions_dir()`를 해석하게 보정했다. 명시적 `sessions_dir`와 기존 테스트 seam은 계속 우선한다. 실제 uvicorn에서 startup 후 새 COMMITTED activity를 추가하고 `POST /api/mission-scheduler/tick?force=true`를 호출해 `scanned=2`, `actions={"complete":1}`을 확인했다.

## ADR-001 반영

full cutover의 마지막 블로커였던 "ActivityQueue 자동 복구 결정"은 닫혔다 — (a) `_api_startup()`/`scheduler_tick()`에 연결하는 쪽으로 결정, 구현·테스트 완료. 남은 것은 사용자가 재심사를 요청하는 시점이다.
