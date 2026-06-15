# Agent-Lab Stabilization Plan

## 초기에 했던 작업 정리

### 1) verify repair policy 연동
- `src/agent_lab/verify_repair_policy.py` 재작성
- Enum 기반 실패 분류 (`MERGE_CONFLICT`, `ORACLE_FAIL`, `WORKTREE_GIT_DIRTY`, `AGENT_TIMEOUT`, `STRUCTURAL_FAIL`)
- `ensure_worktree_usable(mode="recreate")` 추가 → 실제 worktree 재생성과 연동

### 2) mission loop 연동
- `src/agent_lab/mission_loop.py`
  - `_advance_verify_with_policy()` 헬퍼 추가 → verify 실패 시 정책 기반 repair 분기
  - `_on_verify_fail()` 콜사이트 수정 → repair cap 경로 보정
  - `on_verify_result()` 실패 경로에서 `_advance_verify_with_policy()` 호출 후 `_on_verify_fail()`로 위임
  - main path(`_on_verify_pass`) 직접 수정 없이 우회하여 루프 안정성 확보

### 3) discuss recovery 보강
- `discuss_recovery.pending` 기본값 `False` → `True` 정정
- `run_mission_discuss_recovery()` 예외 처리 변경: 실패 시에도 recovery 정상 종료되도록 개선
- scribe 결과가 비어 있을 때 기존 `plan.md` 재사용하는 fallback 추가

### 4) 검증
- `tests/test_verify_repair_policy.py` 13/13 통과
- `py_compile mission_loop.py` 통과
- 커밋 `8602547`, `a094203`, `018bc22` 작성 및 push 완료
- 브랜치: `cursor/room-stream-cancel-live-log`

---

## 아직 수행하지 않은 것

### 이미 파악된 이슈
1. 반복 빈 응답 `(empty)` 발생 원인 불명확
   - tool 결과 처리 흐름상의 응답 누락 가능성 확인 필요
2. worktree discard edge case
   - 기본 recreate 경로만 연동됨, discard edge 연동 강화 필요

### 코드 레벨 미완료
1. `run.json` 런타임 스키마 검증
   - 빈 값/불일치 상태에서 `patch_run_meta()`를 거치지 않는 direct write 경로 존재 가능
2. 합의 라운드 N-of-M 정책 지원 최적화
   - 불필요한 재합성 라운드 스킵 로직 구현 필요
3. context_bundle.py 컨텍스트 바이트 사용량 로깅
   - 토큰/바이트 예산 추적 모듈 추가 필요

### 백오프 정책 완료
- `src/agent_lab/backoff_policy.py` 신규
- `tests/test_backoff_policy.py` 7/7 통과
- retry-style 백오프 4개 call site 교체: `run_meta.py`, `agents/cursor_agent.py`, `agent_health.py`, `bridge_registry.py`
- 남은 intentional `time.sleep(...)` 보존: `claude_cli.py` 폴링/대기 루프, `human_inbox.py` inbox 폴링, `agents/cursor_agent.py` 런 대기 루프, `cli_retry.py` 고유 exponential+jitter 정책

---

## 앞으로 필요한 작업 (단기 → 장기)

### 단기 (1~2일)
1. ~~DISCUSS → PLAN_GATE auto-forward 검증 및 안정화 완료~~
2. ~~worktree discard edge case 반영~~
3. (empty) 원인 분석 및 방지 로직 정리

### 중기 (3~5일)
1. time.sleep 백오프 중앙 정책 모듈 추가
   - 새로운 파일: `src/agent_lab/backoff_policy.py`
   - 기존 9개 call site 교체
   - 테스트: `tests/test_backoff_policy.py`
2. run.json 런타임 스키마 검증 추가
   - `src/agent_lab/run_schema.py` 신규
   - `patch_run_meta()`/`write_run_meta()`에 검증 hook 삽입
   - 테스트: `tests/test_run_schema.py`

### 장기 (1주 이상)
1. 합의 라운드 N-of-M 정책 지원
   - `src/agent_lab/room_consensus_rounds.py` 개선
   - 정책 모듈: `consensus_policy.py` 분리
   - 최적화: 합의 완료 조건이 충족되면 즉시 종료
2. context_bundle.py 토큰/바이트 로깅
   - 예산 한도 초과 시 자르기/압축 정책 추가
3. 종합 안정성 테스트
   - `tests/` 아래 integration test suite 추가
   - CI에서 실행되도록 `Makefile` / workflow 연동
