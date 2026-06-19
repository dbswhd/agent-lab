# Agent-Lab Stabilization Plan

작성일: 2026-06-16
현재 코드베이스 상태를 기준으로 루프 안정성·커뮤니케이션·토큰 효율·구조 4축을 단기/중기/장기로 분해한 실행 계획이다.

---

## 1. 단기 (D1~D3): 검증 가능 단위 안정화

### 1.1 verified_loop failure handling
- `src/agent_lab/verified_loop.py`는 `<promise>` 감지 이후 oracle 호출까지 갈 때마다 `DONE`→repeat 위험이 있음.
- 오라클 실패 시 루프가 `running`으로 휴즈되면서 `continue_prompt`가 계속 주입된다.
- 작업: oracle FAIL 시 `checks`를 기록하고 `failed` 또는 `pending_approval` 분기 로직을 강화한다.
- 검증: `tests/`에 oracle 실패 케이스 1건 이상 추가.

### 1.2 backoff policy 통합
- `src/agent_lab/backoff_policy.py` `wait()`/`next_backoff()`는 코드 크래쉬 확인이 가능하지만, 호출부가 분산되어 있다.
- 작업: 기존 직접 `time.sleep(...)` 사용 코드를 central policy 교체 + 관련 파일 1곳부터 시작.
- 검증: `PYTHONPATH=. python -m pytest tests/test_backoff_policy.py -q`

### 1.3 envelope strict change 공통 경로 확인
- `communicate_kpis.py`는 turnover 메타가 없으면 0으로 떨어지는 것 확인.
- 작업: 누락 시 기본값을 0이 아닌 `None`으로 분리해 nullability를 정리.
- 검증: `PYTHONPATH=. python -m agent_lab.communicate_kpis --run-file <run.json>` 흉내 스크립트 실행.

---

## 2. 중기 (D4~D7): 커뮤니케이션/협업 설계 정리

### 2.1 room turn flow 분할
- `room_turn_flow.py` 882줄은 상태전이, LTS 구성, verify 연동이 섞여 있다.
- 작업: `room_turn_flow.py`의 turn summary 생성과 state machine 부분만 먼저 `room_turn_state.py`로 이동. 불변 규칙 준수.
- 기준: 상태 전이가 기존과 동일하게 동작하는지 회귀 테스트 2건 이상 통과.

### 2.2 consensus_rounds / room_objections 정리
- `room_objections.py`와 `room_consensus_rounds.py`는 BLOCK/CHALLENGE/ENDORSE 중복 분기 구조를 공유한다.
- 작업: 중복되는 Act enum을 `room_consensus.py`의 엄격 계약으로 재정의하고, 각 파일에서 사용자 정의 예외를 제거한다.
- 검증: 단위 테스트에서 BLOCK/CHALLENGE 시 payload 노출 여부 검사.

### 2.3 token budget 가시화
- `room_context.py` / `session_guidance.py`는 토큰 16k/32k 코드에서 사용하지만, 실제 컨텍스트 강등 정책은 분산되어 있다.
- 작업: `policy-token-budget.md`를 작성하고, budget state를 `run.json`의 `verified_loop.last_token_{in,out}` 형식으로 기록.
- 검증: budget 초과 시 fallback warm-up 알림이 runner 로그에 노출되는지 확인.

---

## 3. 장기 (D8~D14): 거버넌스·구조·미구현 정리

### 3.1 미사용 스크립트 · 모듈 정리
- `scripts/cleanup_dmg_mounts.sh`, `scripts/verify_quant_workspace_setup.py`, `scripts/run_dogfood_suite.py`은 존재하지만 실제로 작동 여부가 의심.
- 작업: 각각의 readme, import graph, 사용 위치를 확인해 사용 중 구분. 미사용이면 archive 폴더로 이관하고 import 제거.
- 검증: import freeze 분석 → 사용하지 않는 파일 0.

### 3.2 project structure consolidation
- `app/server/`, `gateway/`, `runtime/`가 겹치는 라우트/설정 파라미터 존재.
- 작업: `app/server/routers/`를 gateway 호출이 1개 이상인지 매핑 후, `gateway/`의 공용 라우트를 top-level `gateway/routers.py`로 통합. `app/server/main.py`는 entrypoint만 유지.
- 검증: `make uv` 로드맵 동작에 영향 없음 확인.

### 3.3 fixme / todo / not implemented 주석 의도값 기반 정리
- 기념비적 파일인 `mission_loop.py`, `goal_loop.py`, `run_control.py` 내 `FIXME` 주석이 실제 동작 시 영향을 주는지 분석하고, 없거나 ignore해도 되는지 표기.
- 작업: 각 FIXME 마다 3가지 분류 중 하나를 부여: ① 제거 ② 이슈 트랙 연결 ③ 문서 주석으로 변환.
- 검증: 코드 리뷰어가 전체 FIXME list를 재검토 없이 이해 가능하도록 `FIXME_TRAIL.md` 작성.

---

## 4. 실행 흐름

1. 본 문서를 `docs/stabilization.md`로 형식 변환해 저장 (1~2일)
2. 단기 이슈를 GitHub issue로 1건씩 분리
3. 스크립트 실행 형식으로 다음 명령 확인:

```
PYTHONPATH=. python -m pytest tests/ -q
```

4. 최초 커밋 범위는 본 repository의 codebase 영역만(a.k.a. 관련 파일만) → staging 이후 human 확인 후 push.

---

## 5. 연속 작업

- D1:DONE → D2:DONE → ... 진행상황을 세션검색으로 확인 가능해야 하며, 계획 문서는 이전 세션이 연결되어 있으므로 다음 단계(`한 단계 더`) 요청 시 해당 트랙을 바로 인계할 수 있다.
