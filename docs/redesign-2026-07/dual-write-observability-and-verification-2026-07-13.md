# Dual-write 로그/메트릭 + parity 검증 쿼리 — 2026-07-13

[운영 준비 3종 점검](dual-write-operational-readiness-check-2026-07-13.md)에서 발견한 3번 gap(비교용 로그/메트릭/쿼리 부재)을 채운 결과다. 두 가지를 만들었고, 두 번째 것으로 실제 검증하다가 **세 번째 gap을 새로 발견해 그 자리에서 수정했다** — Human Inbox pause/resume 브리지가 실제 production 흐름에서는 항상 조용히 실패하고 있었다.

## 1) 로그/메트릭 계측

`src/agent_lab/mission/dual_write_observability.py` (신규) — `dual_write.py`의 4개 public `mirror_*` 함수를 `@_observed` 데코레이터로 감쌌다. 개별 return 지점(총 ~10곳)을 일일이 계측하는 대신 함수 전체를 감싸 모든 exit path(성공/cohort 제외/에러/flag off)를 빠짐없이 잡는다.

- **로그**: `logging.getLogger("agent_lab.mission.dual_write")`로 구조화된 라인 출력 — 이미 `app_logging.setup_app_logging()`이 구성한 `agent-lab-api.log`(rotating)에 자동으로 남는다. `mirrored=true`/`cohort_not_selected`는 INFO, 실제 실패(`mirrored=false`이고 이유가 cohort 제외가 아닌 경우)는 WARNING. `flag OFF`(`enabled=false`)는 매우 잦은 routine이라 로그를 안 남기고 카운터만 올린다(노이즈 방지).
- **메트릭**: 인메모리 카운터(`operations: {plan_approve: {mirrored, blocked_cohort, error}, ...}`, `disabled_calls_total`) — 프로세스 재시작 시 리셋(디스크에 안 씀, 매 호출 I/O 방지). `/api/health/daemon`에 `dual_write` 키로 노출(`app/server/routers/mission_os.py`).

테스트 5건(`tests/test_dual_write_observability.py`) + 기존 dual-write 스위트 전부 통과.

## 2) legacy/Mission parity 검증 쿼리

`scripts/mission_dual_write_verify.py` (신규) — **읽기 전용**, cohort가 실제로 운영되는 동안 반복 실행 가능. 이전 evidence 스크립트들(`mission_dual_write_route_cohort.py` 등)은 사전검증용 합성 트래픽 생성기였지만, 이건 아무것도 쓰지 않고 실제 세션의 `run.json`과 Mission read-model(`/mission/read-model`이 쓰는 것과 동일한 코드 경로)만 비교한다.

```bash
.venv/bin/python scripts/mission_dual_write_verify.py --sessions sessions/
.venv/bin/python scripts/mission_dual_write_verify.py --sessions sessions/ --session <id>
.venv/bin/python scripts/mission_dual_write_verify.py --sessions sessions/ --cohort   # AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS만
```

비교 차원 3개, 각각 `hard_mismatch`(둘 다 값이 있는데 다름) vs `mission_behind`(legacy만 앞서감, 문서화된 partial-parity 경계라 정상)를 구분한다:

- merge commit SHA (legacy `executions[].merge.commit_sha` vs `mission.merged_commit_sha`)
- Oracle verdict (legacy `executions[].oracle.verdict` vs `mission.last_oracle_verdict`)
- Human Inbox pending 여부 vs `mission.state == AWAITING_HUMAN`

exit code는 `hard_mismatch`가 하나라도 있으면 `1` — cron/모니터링에 바로 걸 수 있다. 테스트 8건(`tests/test_mission_dual_write_verify.py`), 실제 운영 `sessions/`(115개, read-only)에 대해서도 부작용 없이 통과 확인(`git status --short sessions/` 변화 없음).

## 3) 새로 발견한 gap — Human Inbox pause/resume 브리지가 실제로는 항상 깨져 있다

검증 쿼리를 **실제 production 코드 경로**(수동으로 `BlockExecution`을 dispatch하지 않고 진짜 `create_inbox_item()` 호출)로 재현하며 확인했다:

```
1) POST /plan/approve (dual-write ON) → Mission READY_TO_EXECUTE, mirrored=true
2) create_inbox_item(folder, kind="question", ...)  # 실제 프로덕션이 쓰는 그 함수
3) verify 쿼리 실행 → hard_mismatch:
   "legacy has 1 pending inbox item(s) but mission.state=READY_TO_EXECUTE (not AWAITING_HUMAN)"
```

**원인:** `mirror_inbox_resolution`(resolve 쪽)은 `dual_write.py`에 있지만, inbox **생성** 쪽에는 dual-write 훅이 전혀 없다. `create_inbox_item`은 `merge_gate.py`, `autonomy_inbox.py`, `drift_audit.py`, `correction_harvester.py`, `skill_drafts.py`, `autonomy_promotion_inbox.py`, `rule_sync.py`, `room/retry.py`, `plan/workflow_clarify.py`, `kimi/work_inbox_bridge.py`, `app/server/routers/human_inbox.py` 등 최소 10곳 이상에서 호출되는데 그중 어디도 Mission에 `BlockExecution`을 dispatch하지 않는다. 그 결과 human question이 실제로 뜨는 순간 Mission은 절대 `AWAITING_HUMAN`에 들어가지 않고, 나중에 `resolve` route를 호출해도 `mirror_inbox_resolution`이 `if mission.state is not AWAITING_HUMAN: return mirrored=False, reason="mission_not_awaiting_human"`로 **매번 조용히 실패**한다.

**이전 evidence가 이걸 놓친 이유:** [dual-write-route-cohort-report](dual-write-route-cohort-report-2026-07-13.md)와 [Room dogfood](dual-write-cutover-followup-2026-07-13.md)의 inbox 시나리오는 `MissionApplication(...).repository.dispatch(BlockExecution(...))`를 **테스트 셋업으로 직접 호출**해서 Mission을 인위적으로 `AWAITING_HUMAN`으로 만든 뒤 resolve를 테스트했다 — 실제 production이 절대 하지 않는 동작이다. 그래서 그 리포트들의 "Human Inbox resume: pass"는 **실제로 발생하지 않는 경로를 검증한 false positive**였다.

**영향 범위:** plan approve/reject, execute/resolve, execute/merge/confirm, execute/reverify는 이 문제와 무관하다(모두 route 자체에 훅이 있음). 오직 human inbox 생성→해결 흐름만 깨져 있다. cohort 세션에서 실제로 human question이 뜬 적이 있다면 그 세션의 Mission은 지금 이 순간에도 legacy와 어긋나 있을 가능성이 높다.

## 4) 수정 완료 — `create_inbox_item()`에 훅 추가

`mirror_inbox_creation(folder, *, item_id, kind, reason)`을 `dual_write.py`에 추가하고(`@_observed`, 다른 mirror_* 함수와 동일한 opt-in/cohort/로그/메트릭 관례), `human_inbox.py::create_inbox_item()` 끝에서 legacy write 이후 fire-and-forget으로 호출한다(`append_live_room_event`/`fan_out_gateway_notify`와 같은 스타일 — bare `try/except: pass`). 호출 지점이 이 한 곳뿐이라 `merge_gate.py`, `autonomy_inbox.py`, `room/retry.py` 등 10여 개 호출부는 전혀 안 건드렸다.

**중요한 경계:** kernel의 `BlockExecution`은 `READY_TO_EXECUTE`에서만 유효하다(Mission은 "block"을 실행 전 human gate로만 모델링한다, pause-from-anywhere가 아니다). 실제 inbox item의 상당수는 실행 도중(merge_gate, autonomy_inbox 등)에 뜨므로, 그 경우 훅은 `mirrored=false, reason=mission_not_ready_to_execute`로 정상적으로 no-op한다 — 이건 버그가 아니라 FSM 계약이다. 이번 수정이 완전히 닫는 것은 "plan 승인 직후, 아직 실행 시작 전에 뜬 human question" 케이스이고, 그 외 케이스는 여전히 `mirrored=false`로 남지만 이제 **이유가 명확하고 관측 가능하다**(로그/카운터로).

**검증 — 실제 production 경로로 버그가 있던 그 시나리오를 그대로 재현:**

```
1) POST /plan/approve (dual-write ON) → Mission READY_TO_EXECUTE
2) create_inbox_item(folder, ...)  # 수정 전: 아무 일도 안 일어남
                                     # 수정 후: Mission이 자동으로 AWAITING_HUMAN
3) mission_dual_write_verify.py → hard_mismatch_count: 0 (수정 전엔 1)
4) POST /inbox/{item}/resolve → mirrored=true, Mission READY_TO_EXECUTE로 복귀
5) mission_dual_write_verify.py → severity: ok
```

pytest 신규 3건(`test_inbox_creation_bridge_blocks_from_ready_to_execute`, `test_inbox_creation_bridge_noops_when_not_ready_to_execute`, `test_full_inbox_pause_resume_lifecycle_without_manual_mission_setup`) + verify-query 회귀 테스트 1건 갱신(`test_pending_inbox_item_created_via_real_path_is_no_longer_a_mismatch`, 수정 전엔 `hard_mismatch`였던 것이 이제 `ok`). 관련 스위트 251건(dual-write/inbox/scheduler/activity_queue/crash_recovery + merge_gate/autonomy_inbox/drift_audit 등 inbox 호출부 10곳 전부) 통과, lint 클린.

## 종합 (최종)

| 요청 항목 | 상태 |
| --- | --- |
| dual-write 로그/메트릭 | 완료 |
| legacy/Mission parity 검증 쿼리 | 완료 |
| Human Inbox 브리지 gap | **수정 완료** — 실제 production 경로로 재검증함 |
| pytest → 실 운영 로그 파일 오염 | **수정 완료** — 아래 5) 참고 |

## 5) 부수 발견 수정 — pytest가 실제 운영 로그 파일에 쓰던 문제

`cohort에서 mirrored=false 세션 스캔` 작업 중 발견했던 것: `app/server/main.py::create_app()`은 `bootstrap` 값과 무관하게 `setup_app_logging()`을 항상 호출한다. 이 함수는 root logger에 `RotatingFileHandler`를 붙이는데, `_CONFIGURED`가 프로세스 전역 sticky flag라서 그 프로세스에서의 **첫 호출이 로그 경로를 영구히 고정**한다. `app.server.main`을 import하는 거의 모든 테스트(모듈 최상단에서 `from app.server.main import app`으로 import하는 파일이 많음, 심지어 `app = create_app()`이 모듈 import 시점에 실행됨)가 실제 사용자 로그 디렉터리(`~/Library/Logs/Agent Lab/agent-lab-api.log`)에 쓰고 있었다.

**수정:** `tests/conftest.py` 최상단(다른 어떤 import보다 먼저)에 `os.environ.setdefault("AGENT_LAB_LOG_DIR", tempfile.mkdtemp(...))` 추가. pytest worker당 고유한 tmp 디렉터리를 pytest 세션/워커 시작 시 한 번 만들어, 그 프로세스의 첫 `setup_app_logging()` 호출이 항상 격리된 경로를 잡도록 한다. `AGENT_LAB_LOG_DIR`이 이미 명시적으로 설정된 경우는 `setdefault`라 덮어쓰지 않는다.

**검증:**
- 단일 테스트 파일 실행 전후로 실 로그 파일의 mtime/size가 변화 없음을 확인.
- `make test-fast`(xdist, `-n auto`, ~3160개 테스트) 실행 전후로도 실 로그 파일 mtime/size 불변 확인 — 임시 진단 코드로 "실 경로로 setup_app_logging이 호출된 적 있는지"까지 직접 계측해 0건 확인(진단 코드는 확인 후 제거).
- `tests/test_app_config.py`의 `AGENT_LAB_LOG_DIR` 관련 테스트 3건은 각각 `monkeypatch.delenv`/`setenv`로 명시적으로 값을 다루므로 `setdefault`와 충돌 없이 통과.
- `make test-fast`에서 실패한 9~10개 테스트(run-lock 클러스터, `test_integration_registry`의 bucket count, `test_structure_metrics`의 프론트엔드 baseline drift)는 이 fix를 `git stash`로 껐다 켰다 하며 대조했을 때 **양쪽에서 동일하게 실패** — 전부 기존에 있던 xdist 병렬 실행 flakiness/baseline 문제이지 이 fix가 만든 회귀가 아님을 확인했다.
