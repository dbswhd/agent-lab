# Agent-Lab Stabilization Plan

## 초기에 했던 작업 정리

### 1) verify repair policy 연동 — 완료
- `src/agent_lab/verify_repair_policy.py` 재작성
- Enum 기반 실패 분류 (`MERGE_CONFLICT`, `ORACLE_FAIL`, `WORKTREE_GIT_DIRTY`, `AGENT_TIMEOUT`, `STRUCTURAL_FAIL`)
- `ensure_worktree_usable(mode="recreate")` 추가 → 실제 worktree 재생성과 연동
- `mission_loop._advance_verify_with_policy()` 연동

### 2) mission loop 연동 — 완료
- verify 실패 시 정책 기반 repair 분기
- `on_verify_result()` 실패 경로에서 policy → `_on_verify_fail()` 위임

### 3) discuss recovery 보강 — 완료 (부분)
- verify/execute 실패 경로에서 `discuss_recovery.pending=True` 설정
- `default_mission_loop()` 기본값은 `pending: False` (정상 — idle 상태)
- `run_mission_discuss_recovery()` + scribe empty fallback

### 4) 검증 — 완료
- `tests/test_verify_repair_policy.py` 통과
- 브랜치: `cursor/room-stream-cancel-live-log`

---

## 완료된 인프라 작업

### run.json 런타임 스키마 검증 — 완료
- `run_schema.py` + `write_run_meta()` / `patch_run_meta()` hook
- production direct-write bypass: `room_plan_scribe`, `session_setup`, live spike/soak → `write_run_meta`

### backoff policy — 완료
- `backoff_policy.py` + `run_meta`, `cursor_agent`, `claude_cli`, `human_inbox`, `agent_health`, `bridge_registry`

### room turn flow 분할 — 부분 완료
- `room_turn_state.py` 추출 (turn blackboard / sync)
- `room_turn_flow.py`는 여전히 ~881줄 — 추가 분할 여지 있음

### consensus / objections — 완료
- central 계약(`envelope_act`, `classify_consensus_reply`) 사용

### 미사용 스크립트 정리 — 완료
- `scripts/cleanup_dmg_mounts.sh` → `archive/cleanup_dmg_mounts.sh`
- `verify_quant_workspace_setup.py`, `run_dogfood_suite.py` — Makefile 참조, 유지

---

## 2026-06-16 후속 작업 (이번 세션)

### 1) import freeze 오적용 롤백 — 완료
- **실수:** 19개 활성 모듈을 `archive/unused_modules/`로 이동 → 런타임 전면 장애
- **조치:** 19개 전부 `src/agent_lab/` 복원 (`llm`/`roles` 포함 — `graph`/`invoke` 전이 의존)
- **재발 방지:** `scripts/import_freeze_check.py` 추가 — `src/app/tests/scripts` import 0인 모듈만 후보

### 2) consensus_policy 실연동 — 완료
- `room_consensus_rounds.py`
  - `should_skip_recombination()` → 재조합 라운드 스킵
  - `should_exit_round(endorse_threshold)` → N-of-M 조기 합의

### 3) token_budget 실연동 — 완료
- `room_agent_invoke.py` — `context_log` append 시 `record_run_token_budget()`
- `room_session_persist.py` — 턴 종료 `write_run_meta` 직전 기록
- `context_bundle.py` — `last_context_bundle` 스냅샷

### 4) 테스트 수정 — 완료
- `test_discuss_execute_recovery.py` — patch 대상 `mission_board.record_autorun_tick`
- `conftest._INTEGRATION_MODULES` — stabilization 신규 suite 5개 추가 (fast bucket ≤1000)

---

## 아직 미완

### 단기
1. `(empty)` 반복 응답 원인 분석
2. `test_claude_hooks`, `test_codex_proxy_adapter` 등 기존 실패 정리

### 중기
1. `room_turn_flow.py` 추가 분할 (`room_turn_state` 이후 잔여)
2. context_bundle 예산 초과 시 자르기/압축 정책

### 장기
1. integration test suite + CI/Makefile 연동
2. import freeze — `scripts/import_freeze_check.py` 결과 0 확인 후에만 archive

---

## 검증 기준

```bash
PYTHONPATH=. python scripts/import_freeze_check.py
make test-fast
PYTHONPATH=. python -m pytest tests/test_discuss_execute_recovery.py \
  tests/test_verify_repair_policy.py tests/test_consensus_policy.py \
  tests/test_token_budget.py tests/test_backoff_policy.py -q
```

## 실행 흐름
- 단기 이슈는 GitHub issue로 1건씩 분리
- 세션 검색으로 진행상황 기록
