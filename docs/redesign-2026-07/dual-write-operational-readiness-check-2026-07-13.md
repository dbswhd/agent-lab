# Dual-write 운영 준비 3종 점검 — 2026-07-13

Human cutover 승인 전, 세 가지를 코드 레벨 + 라이브 TestClient 재현으로 직접 검증했다.

## 1) `AGENT_LAB_MISSION_DUAL_WRITE=1`이 전역이 아니라 cohort에만 적용되는가

**부분 충족 — 메커니즘은 존재하고 정상 동작하지만, code-enforced가 아니라 운영자가 반드시 함께 설정해야 하는 opt-in이다.**

`src/agent_lab/mission/dual_write.py:29`:
```python
def dual_write_enabled(folder: Path | None = None) -> bool:
    if not is_truthy(os.getenv("AGENT_LAB_MISSION_DUAL_WRITE")):
        return False
    cohort = _cohort_ids()
    return not cohort or (folder is not None and folder.name in cohort)
```
`AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS`가 **비어 있으면 `not cohort` == `True`** — master flag만 켜진 모든 세션이 대상이 된다. 이건 flag registry에도 "empty means all"로 이미 문서화돼 있었다(`runtime_flags.py:50`).

실제 production route(TestClient, 격리된 sessions dir)로 3가지 시나리오를 라이브 재현:

| 시나리오 | 결과 |
| --- | --- |
| flag ON + allowlist에 다른 세션만 포함 | `mirrored=false`, `reason=cohort_not_selected`, journal 파일 생성 안 됨 — **격리 확인** |
| flag ON + allowlist에 해당 세션 포함 | `mirrored=true`, journal 생성됨 — **정상** |
| flag ON + allowlist 미설정(빈 값) | `mirrored=true`, journal 생성됨 — **전역 적용, cohort 아님** |
| flag OFF (rollback) | `enabled=false, mirrored=false`, legacy route는 정상 200 | **정상** |

`tests/test_mission_dual_write.py`의 `test_plan_bridge_respects_session_cohort_allowlist`/`test_plan_bridge_mirrors_allowlisted_session` 2건도 같은 내용을 커버하며 통과(`9 passed`).

**결론:** cohort 격리는 [dual-write-controlled-cohort-runbook-2026-07-13.md](dual-write-controlled-cohort-runbook-2026-07-13.md)가 이미 정확히 문서화하고 체크리스트로 강제하려 하고 있다 — "공유 process를 사용하는 경우 allowlist가 비어 있지 않고 cohort session ID만 포함하는지 확인한다." 하지만 **코드는 이를 강제하지 않는다** — allowlist를 깜빡 빼먹고 master flag만 켜도 에러 없이 조용히 전역으로 동작한다. 운영자 실수 하나로 cohort 경계가 사라질 수 있다는 뜻이다.

## 2) 문제가 생기면 플래그를 내려 즉시 legacy-only로 복귀 가능한가

**코드 레벨: 그렇다, 완전히 stateless.** `dual_write_enabled()`는 매 호출마다 `os.getenv()`를 새로 읽는다 — import 시점 캐싱도, 세션 상태에 저장되는 의존성도 없다. 위 표의 "flag OFF" 시나리오에서 이미 mirrored됐던 세션이 flag OFF 이후에도 legacy route만으로 정상 동작하는 것을 라이브로 재확인했다(`agent_lab.crash_recovery`/ActivityQueue 쪽 정지-재기동 evidence와 별개로, dual-write 자체는 restart 없이도 로직상 즉시 반영된다).

**운영 레벨: "즉시"는 프로세스 재시작을 전제로 한다.** `AGENT_LAB_MISSION_DUAL_WRITE`는 순수 OS 환경변수이고, 이 값을 실시간으로 바꾸는 관리 API/live-reload 엔드포인트는 없다(`/api/health/flags`는 GET-only 조회용, POST로 토글하는 라우트는 존재하지 않음 — 코드베이스 전수 검색으로 확인). 즉 실제 rollback 절차는:

1. 환경변수를 `0`으로 바꾼다.
2. 프로세스를 재시작한다(이 프로젝트의 다른 feature flag들과 동일한 관례 — hot-reload 메커니즘 자체가 없음).
3. flag OFF 상태에서 신규/기존 세션 모두 legacy-only로 동작하는지 확인한다(이미 여러 차례 라이브 증거로 확인됨).

runbook의 "Rollback" 절 1번이 "전용 process의 `AGENT_LAB_MISSION_DUAL_WRITE`를 `0`으로 전환한다"라고만 되어 있어 재시작이 필요하다는 점이 명시돼 있지 않다 — on-call이 "live toggle이 있나?"를 찾다 시간을 버릴 수 있으므로 한 줄 보강을 권장한다(아래 조치 참고).

**결론:** 데이터 손상·마이그레이션 위험은 없고 코드는 안전하지만, "즉시"는 "재시작 없이"가 아니라 "재시작 한 번이면 100% 안전하게"로 이해해야 한다.

## 3) dual-write 결과를 비교할 로그·메트릭·검증 쿼리가 준비돼 있는가

**준비 안 됨 — 이번 점검에서 발견한 실질적 gap이다.**

`src/agent_lab/mission/dual_write.py`와 이를 호출하는 6개 router 지점(`plan_workflow.py`, `human_inbox.py`, `plan_execute.py`)을 전수 검색한 결과:

- `mirror_*` 함수 어디에도 `logging`/`logger` 호출, 카운터, `record_control_span` 같은 계측이 없다.
- 결과(`mission_dual_write.mirrored`, `reason` 등)는 **그 요청을 보낸 클라이언트에게만** HTTP 응답 본문으로 반환된다 — 서버 로그나 집계 가능한 지표로는 전혀 남지 않는다.
- `/api/health/daemon`은 G3 crash-recovery와 ActivityQueue recovery 상태만 보여준다(내가 지난 턴에 연결한 것) — dual-write mirror 성공/실패 카운트는 여기 없다.
- runbook의 "관찰해야 할 증거" 절은 무엇을 봐야 하는지는 정확히 나열하지만, 그걸 어떻게 자동으로 기록·조회할지에 대해서는 "같은 session_id로 기록한다"는 수동 ledger 지침뿐이다.
- 지금까지 만든 `scripts/mission_dual_write_route_cohort.py` 등은 **사전 검증용 1회성 합성 트래픽 스크립트**다 — cutover 전에 한 번 돌려서 증거를 남기는 도구지, cohort가 실제로 운영되는 동안 실제 세션들의 legacy/Mission parity를 지속적으로 비교하는 쿼리나 대시보드가 아니다.

**결론:** cohort를 실제로 켜고 운영하기 시작하면, "지금 mirror가 잘 되고 있는지" "legacy와 Mission이 갈라진 세션이 있는지"를 확인할 자동화된 수단이 없다. 각 라우트 응답을 개별적으로 관찰하거나, 세션 폴더를 손으로 뒤져 `run.json`과 `.agent-lab/mission-events.jsonl`을 비교하는 수밖에 없다.

## 종합 판정

| 항목 | 상태 |
| --- | --- |
| 1. cohort 격리 (전역 아님) | 메커니즘 존재·정상 동작, **but 코드가 강제하지 않음** — allowlist 설정은 운영자 책임 |
| 2. flag OFF → 즉시 legacy 복귀 | 코드는 안전·stateless, **but "즉시"는 프로세스 재시작 전제** — live toggle 없음 |
| 3. 비교용 로그/메트릭/쿼리 | **없음** — runbook은 수동 기록만 지시, 자동화된 관측 도구 부재 |

3개 중 1·2는 "동작은 하지만 운영 절차/문서에 명시가 부족", 3은 "실제로 없음"이다. 이 상태로 cohort를 켜면 mirror가 조용히 실패하거나 의도치 않게 전역으로 켜져도 알아챌 자동 신호가 없다. Human이 cutover 승인 전에 최소 3번 gap(관측 도구)은 채우는 걸 권장한다.

## 다음 조치 제안 (미실행 — 승인 필요)

1. runbook의 Rollback 절에 "재시작 필요" 한 줄 추가 — 문서만 고치는 사소한 변경.
2. `dual_write.py`의 각 `mirror_*` 결과를 구조화 로그(최소한 `logger.info`)로 남기거나, `/api/health/daemon`에 `dual_write` 카운터(mirrored/blocked/error 건수)를 추가.
3. 세션 하나를 지정하면 legacy `run.json`과 Mission `read-model`을 비교해 divergence를 보고하는 verification 쿼리(스크립트 또는 route)를 만든다 — cohort 운영 중 반복 실행 가능한 형태로.

2·3은 실제 구현이 필요한 작업이라 진행 여부를 확인받고 싶다.
