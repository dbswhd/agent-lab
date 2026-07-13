# Execution-level human gate — 쓰기 모델 분리 + 읽기 모델 통합 (2026-07-13)

## 구현 완료

아래 초안 전체를 구현했다. 6단계 구현 순서를 그대로 따랐고, 각 단계 완료 시점에 관련 테스트를 통과시켰다.

| 파일 | 내용 |
| --- | --- |
| `src/agent_lab/mission/kernel.py` | `GateRecord`, `OpenExecutionGate`/`CloseExecutionGate` command, `ExecutionGateOpened`/`ExecutionGateClosed` event, `Mission.open_gates` 필드. `_require_state` 없음(의도적) |
| `src/agent_lab/mission/event_codec.py` | 두 이벤트 journal 직렬화/역직렬화 추가 |
| `src/agent_lab/mission/dual_write.py` | `mirror_inbox_creation`이 `OpenExecutionGate` 사용(어떤 state에서도 성공); `mirror_inbox_resolution`이 `CloseExecutionGate` + (해당 시) 기존 `ResolveBlock`도 함께 시도 |
| `src/agent_lab/mission/read_model.py` | `MissionOperationalStatus` + `compute_operational_status()`(우선순위 표 그대로) + `open_execution_gates`(gate_id/kind만, reason 제외) |
| `app/server/routers/mission_read_model.py` | `/mission/read-model` 응답에 `operational_status`/`open_execution_gates` 추가 |
| `scripts/mission_dual_write_verify.py` | `human_inbox` 차원을 item-id 단위 비교로 교체 + `orphaned_gate` 차원 신규(terminal + 안 닫힌 gate = review_needed, hard_mismatch 아님) |

**테스트:** kernel 5건, dual_write 4건 신규(+기존 재작성), read_model 6건(우선순위 표 파라미터화 테스트 포함) + PAUSED 도달불가 테스트, verify 쿼리 4건 신규. 관련 스위트 361건 전부 통과, lint 클린.

**실제 production 경로 재검증(핵심 동기였던 시나리오 — mid-execution human question):** 격리 TestClient + 실제 운영 `sessions/` 양쪽에서 `POST /plan/approve` → 직접 `StartExecution`(prep) → `POST /inbox/items`(진짜 route) → `GET /mission/read-model`로 `state=EXECUTING` 그대로, `operational_status=WAITING_FOR_HUMAN`, gate 노출 확인 → `POST /inbox/{item}/resolve` → `operational_status=RUNNING` 복귀, gate 소거 → `mission_dual_write_verify.py` `hard_mismatch_count=0` 전부 확인. 실제 `sessions/`에 만든 테스트 세션은 정리했고 `git status --short sessions/` 변화 없음 재확인.

---

## 왜

`mirror_inbox_creation()`(현재 구현)은 `BlockExecution`을 dispatch해서 human question을 Mission에 반영한다. 그런데 kernel의 `BlockExecution`은 `READY_TO_EXECUTE`에서만 유효하고(`kernel.py:245-247`), `BlockResolved`는 무조건 `READY_TO_EXECUTE`로 되돌린다(`kernel.py:311-312`) — 즉 "실행 시작 직전 승인 게이트" 하나만 모델링하도록 하드코딩돼 있다. 실제 human question의 대다수(merge_gate, autonomy_inbox, room/retry 등)는 `EXECUTING`/`AWAITING_DIFF_DECISION`/`VERIFYING`/`REPAIRING` 도중에 뜨므로, 지금 구조로는 `mirrored=false, reason=mission_not_ready_to_execute`로 계속 no-op한다.

앞선 대화에서 결정한 방향: `BlockExecution`을 넓히는 대신(state-restore 스택 필요, 핵심 FSM 복잡도 상승, "block" 의미가 pause reason별로 다른데 하나로 뭉개짐) **execution-level human gate를 별도의, `MissionState`와 독립적인 모델로 추가**한다.

## 설계 목표 / 비목표

**목표**
- 어떤 `MissionState`에서도 human gate를 열고 닫을 수 있다(READY_TO_EXECUTE 제약 없음).
- 여러 개의 gate가 동시에 열려 있을 수 있다(legacy가 이미 여러 pending inbox item을 지원).
- gate open/close가 `mission.state` 전이에 전혀 영향을 주지 않는다 — 순수 관측용, side-channel.
- 기존 이벤트/상태 전이는 한 글자도 안 바뀐다 — 완전히 additive, 기존 journal replay와 100% 호환.
- 각 gate가 "왜 열렸는지"(kind/reason)를 보존한다.

**비목표**
- `StartExecution`이 gate 존재 여부로 막히게 하지 않는다. 그건 여전히 `blocked`/`BlockExecution`(변경 없음)의 역할이다. 두 메커니즘은 독립적이다.
- legacy `human_inbox[]`를 Mission으로 완전히 대체하지 않는다 — Mission은 "지금 열린 gate가 몇 개, 무엇인지"만 관측 가능하게 만드는 것으로 범위를 좁힌다.

## 데이터 모델

```python
# kernel.py

@dataclass(frozen=True, slots=True)
class GateRecord:
    gate_id: str            # = human_inbox item id, 1:1
    kind: str                # "question" | "build" | ... (legacy inbox kind, 정보용)
    reason: str
    opened_at_state: MissionState   # 열렸을 때 mission.state — 정보용, 전이에 안 씀


@dataclass(frozen=True, slots=True)
class Mission:
    ...  # 기존 필드 전부 그대로
    open_gates: tuple[GateRecord, ...] = ()   # 신규 필드, additive
```

## Command / Event

```python
@dataclass(frozen=True, slots=True)
class OpenExecutionGate:
    gate_id: str
    kind: str = ""
    reason: str = ""

@dataclass(frozen=True, slots=True)
class CloseExecutionGate:
    gate_id: str


@dataclass(frozen=True, slots=True)
class ExecutionGateOpened:
    gate_id: str
    kind: str
    reason: str
    at_state: MissionState

@dataclass(frozen=True, slots=True)
class ExecutionGateClosed:
    gate_id: str
```

`MissionCommand`/`MissionEvent` union에 각각 추가.

**`decide()` — `_require_state` 없음(의도적, 어떤 state에서도 유효):**

```python
case OpenExecutionGate(gate_id=gate_id, kind=kind, reason=reason):
    if any(g.gate_id == gate_id for g in mission.open_gates):
        return ()  # 이미 열려 있음 — idempotent no-op
    return (ExecutionGateOpened(gate_id, kind, reason, mission.state),)
case CloseExecutionGate(gate_id=gate_id):
    if not any(g.gate_id == gate_id for g in mission.open_gates):
        return ()  # 이미 닫혔거나 연 적 없음 — idempotent no-op
    return (ExecutionGateClosed(gate_id),)
```

**`apply_event()` — `state`는 절대 안 건드림:**

```python
case ExecutionGateOpened(gate_id=gate_id, kind=kind, reason=reason, at_state=at_state):
    return replace(mission, version=next_version,
                   open_gates=(*mission.open_gates, GateRecord(gate_id, kind, reason, at_state)))
case ExecutionGateClosed(gate_id=gate_id):
    return replace(mission, version=next_version,
                   open_gates=tuple(g for g in mission.open_gates if g.gate_id != gate_id))
```

idempotency_key: `f"gate-open:{gate_id}"` / `f"gate-close:{gate_id}"` — 기존 관례와 동일.

## `BlockExecution`/`AWAITING_HUMAN`과의 관계

**완전히 그대로 둔다.** `StartExecution`이 `mission.blocked`를 체크하는 유일한 지점이라는 걸 확인했다(`kernel.py:218-221`) — 즉 이 메커니즘은 지금도 "실행 시작 직전 승인 게이트"라는 좁고 명확한 역할만 하고 있고, 그 역할에선 여전히 유효하다. 두 메커니즘을 섞지 않는다:

| | `BlockExecution`/`AWAITING_HUMAN` | `OpenExecutionGate` |
| --- | --- | --- |
| 유효 state | `READY_TO_EXECUTE`만 | 전부 |
| 동시에 몇 개 | 1개(top-level state) | 여러 개(`open_gates` 리스트) |
| 다른 command를 막나 | `StartExecution`을 막음 | 안 막음(순수 관측) |
| resume 목적지 | 항상 `READY_TO_EXECUTE` | 없음(state 자체를 안 건드림) |

## dual_write.py 변경

```python
@_observed
def mirror_inbox_creation(folder, *, item_id, kind="", reason="") -> dict[str, Any]:
    blocked = _blocked_result(folder, "inbox_create")
    if blocked is not None:
        return blocked
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return _result(operation="inbox_create", mirrored=False, reason="mission_journal_missing")
    repo = MissionRepository(journal, folder.name, _goal(folder))
    try:
        mission = repo.dispatch(OpenExecutionGate(item_id, kind, reason), idempotency_key=f"gate-open:{item_id}")
    except (MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="inbox_create", mirrored=False, reason=str(exc)[:240])
    return {**_result(operation="inbox_create", mirrored=True),
            "state": mission.state.value, "open_gate_count": len(mission.open_gates)}
```

`BlockExecution` 시도(READY_TO_EXECUTE 분기)를 완전히 제거한다 — 더 이상 상태 분기 없이 항상 성공하므로 지금 존재하는 `mission_not_ready_to_execute` no-op 케이스가 사라진다. 즉 이번 재설계는 지난번 fix보다 더 넓게 gap을 닫는다(그때는 "plan 승인 직후"만 닫았지만, 이제는 전부 닫힌다).

`mirror_inbox_resolution`도 동일하게 단순해진다 — `AWAITING_HUMAN` 분기 체크 없이 `CloseExecutionGate(item_id)`를 항상 시도. (혹시 그 세션이 우연히 `AWAITING_HUMAN`이기도 하면 별도로 `ResolveBlock`도 시도할지는 구현 시점에 legacy resolve 경로가 실제로 pre-execution 승인과 겹치는 케이스가 있는지 확인하고 결정 — 지금 조사로는 `BlockExecution`의 유일한 production 호출부가 이번에 제거될 `mirror_inbox_creation`이었으므로, 실제로는 이제 아무도 `AWAITING_HUMAN`에 안 들어갈 가능성이 높다. 이 부분은 구현 착수 시 재확인이 필요하다.)

## Read-model / API 노출

`MissionReadModel`(`read_model.py`)에 필드 추가:

```python
open_execution_gates: tuple[dict[str, str], ...]   # [{gate_id, kind, reason}, ...] 또는 최소한 count
```

`/api/sessions/{id}/mission/read-model` 응답에 `open_execution_gate_count`(가벼운 정수) 또는 전체 리스트를 추가 — UI가 "지금 이 세션에 몇 개의 human question이 Mission 기준으로 열려 있나"를 바로 볼 수 있게.

## 검증 쿼리(`mission_dual_write_verify.py`) 변경

지금은 `pending_count > 0` vs `mission.state == AWAITING_HUMAN`(boolean)만 비교한다. 새 모델에서는 **item 단위로 정확히 비교 가능**해진다:

```python
legacy_pending_ids = {item["id"] for item in run.get("human_inbox", []) if item.get("status") == "pending"}
mission_open_ids = {g.gate_id for g in mission.open_gates}
missing_in_mission = legacy_pending_ids - mission_open_ids   # hard_mismatch
stale_in_mission = mission_open_ids - legacy_pending_ids     # hard_mismatch (resolve 안 됐는데 gate만 남음)
```

이전의 "pending 있는데 state가 AWAITING_HUMAN 아님" 같은 뭉뚱그린 비교보다 훨씬 정밀해진다 — 어떤 item이 구체적으로 안 맞는지까지 알 수 있다.

## 중앙 operational-status projection (읽기 모델 통합)

쓰기 모델을 둘로 쪼갠 대가로 생기는 "MissionState 하나만 보면 안 된다"는 비용을, 소비자(대시보드/외부 API)에게는 다시 하나의 합성 상태로 흡수시킨다. 계산 규칙은 **`read_model.py`에만** 존재하는 단일 계약 — 다른 어디서도(대시보드, 다른 라우트) 독자적으로 재계산하지 않는다. `_next_action()`이 이미 `mission.state`에서 파생값을 계산하는 자리이므로 같은 파일에 둔다.

```python
# read_model.py

class MissionOperationalStatus(StrEnum):
    PLANNING = "PLANNING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    RUNNING = "RUNNING"
    READY = "READY"
    PAUSED = "PAUSED"          # 예약됨 — 지금은 이 값을 만드는 신호가 없음(아래 참고)
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_TERMINAL = {MissionState.SUCCEEDED: MissionOperationalStatus.COMPLETED,
             MissionState.FAILED: MissionOperationalStatus.FAILED,
             MissionState.CANCELLED: MissionOperationalStatus.CANCELLED}

_STATE_IS_WAITING_FOR_HUMAN = {
    MissionState.AWAITING_PLAN_DECISION,
    MissionState.AWAITING_DIFF_DECISION,
    MissionState.AWAITING_HUMAN,
}

_RUNNING_STATES = {MissionState.EXECUTING, MissionState.VERIFYING, MissionState.REPAIRING}


def compute_operational_status(mission: Mission) -> MissionOperationalStatus:
    if mission.state in _TERMINAL:
        return _TERMINAL[mission.state]                 # 1순위: terminal은 무조건 이긴다
    if mission.state in _STATE_IS_WAITING_FOR_HUMAN or mission.open_gates:
        return MissionOperationalStatus.WAITING_FOR_HUMAN  # 2순위: 기존 state 기반 대기 + 새 gate 기반 대기 통합
    if mission.state in _RUNNING_STATES:
        return MissionOperationalStatus.RUNNING
    if mission.state is MissionState.READY_TO_EXECUTE:
        return MissionOperationalStatus.READY
    return MissionOperationalStatus.PLANNING             # DRAFTING
```

**우선순위 표 — 실제 `MissionState` 11개 전부 매핑:**

| `mission.state` | `open_gates` | → `operational_status` |
| --- | --- | --- |
| `SUCCEEDED` / `FAILED` / `CANCELLED` | 무관 | `COMPLETED` / `FAILED` / `CANCELLED` (terminal 항상 최우선) |
| `AWAITING_PLAN_DECISION` / `AWAITING_DIFF_DECISION` / `AWAITING_HUMAN` | 무관 | `WAITING_FOR_HUMAN` |
| `EXECUTING` / `VERIFYING` / `REPAIRING` | 비어있지 않음 | `WAITING_FOR_HUMAN` |
| `EXECUTING` / `VERIFYING` / `REPAIRING` | 비어있음 | `RUNNING` |
| `READY_TO_EXECUTE` | 무관 | `READY` |
| `DRAFTING` | 무관 | `PLANNING` |

핵심 통찰: `WAITING_FOR_HUMAN`은 사실 **세 개의 서로 다른 내부 메커니즘**을 하나로 합친다 — ① `AWAITING_PLAN_DECISION`/`AWAITING_DIFF_DECISION`(원래부터 있던, 이름 자체가 대기인 state) ② `AWAITING_HUMAN`/`blocked`(기존 pre-execution 게이트) ③ `open_gates`(이번에 추가하는 execution-level 게이트). 지금까지는 ①·②만 있어서 그럭저럭 `state` 하나로 충분해 보였지만, ③이 추가되는 순간 반드시 이 셋을 한곳에서 합치는 계약이 있어야 드리프트가 안 생긴다 — 그게 이 함수다.

**terminal + orphaned gate는 별도 데이터 위생 신호.** terminal 상태인데 `open_gates`가 비어있지 않다면(닫는 걸 깜빡함) `operational_status`는 여전히 `COMPLETED`/`FAILED`로 정확하지만, 이건 `mission_dual_write_verify.py`에 새 finding 차원으로 추가할 만하다(`dimension: orphaned_gate, severity: review_needed`) — 상태 표시는 안 흔들되 운영자에게는 보여야 하는 케이스.

**`PAUSED`는 지금 예약만 해둔다.** 이 값을 만들 실제 신호(스케줄러 backoff, rate-limit 등)가 현재 데이터 모델에 없다. 없는 신호를 억지로 만들어 채우기보다 enum에 자리만 만들어두고, 나중에 그런 신호가 생기면 그때 우선순위 규칙에 끼워 넣는 게 맞다고 본다.

**API 노출:** `MissionReadModelPayload`(`mission_read_model.py`)에 `operational_status: str` 필드 추가. 기존 `state`/`legacy_phase`/`next_action`은 그대로 유지 — `operational_status`는 "이거 하나만 보면 됨" 용도로 추가되는 것이지 기존 필드를 대체하지 않는다. 세부가 필요한 소비자(디버깅, verify 쿼리)는 여전히 `state`+`open_execution_gates`를 직접 볼 수 있다.

## 마이그레이션/호환성

- 순수 additive: 새 이벤트 타입 2개, `Mission`에 필드 1개 추가. 기존 journal(이미 replay된 것들)은 새 이벤트를 한 번도 안 봤으므로 `open_gates=()` 기본값으로 그대로 replay된다 — 깨지는 것 없음.
- 기존 `test_mission_dual_write.py`의 `test_inbox_bridge_resolves_awaiting_human`(수동 `BlockExecution` dispatch로 `AWAITING_HUMAN` 테스트)은 `BlockExecution` 자체를 안 건드리므로 그대로 유효 — 그 메커니즘이 여전히 존재하고 동작한다는 걸 확인하는 테스트로 남는다.
- 지난 턴에서 추가한 `test_inbox_creation_bridge_blocks_from_ready_to_execute`/`test_inbox_creation_bridge_noops_when_not_ready_to_execute`는 이번 재설계로 의미가 바뀐다(더 이상 no-op 케이스가 없어짐) — 재작성 필요.

## 미결 사항 / 구현 시 확인할 것

1. `mirror_inbox_resolution`이 `AWAITING_HUMAN`+`ResolveBlock` 분기를 완전히 버려도 되는지, 아니면 유지한 채 `CloseExecutionGate`를 추가하는 형태로 갈지 — `BlockExecution`의 다른 production 호출부가 정말 없는지 재확인 필요.
2. `open_gates`가 무한정 쌓이는 걸 막을 상한이 필요한가(예: 세션당 최대 N개) — 지금 legacy도 별도 상한이 없어 보이므로 동일 정책 유지가 무난해 보임.
3. read-model API 응답에 gate 상세(reason 포함)까지 노출할지, count만 노출할지 — reason에 사용자 프롬프트 원문이 섞일 수 있어 payload 크기/민감정보 관점에서 count만 우선 노출하고 상세는 필요시 별도 확인.
4. `PAUSED`를 만들 실제 신호가 생기기 전까지 이 값은 코드상 도달 불가능(unreachable) 상태로 남는다 — enum에는 있지만 `compute_operational_status()`가 절대 반환하지 않는다는 걸 테스트로 명시할지(예: `assert MissionOperationalStatus.PAUSED not in {compute_operational_status(m) for m in all_reachable_missions}` 같은 문서화용 테스트), 아니면 그냥 주석으로 충분한지.
5. terminal + orphaned gate를 verify 쿼리의 새 finding 차원(`orphaned_gate`)으로 추가할지 — 이번 구현 범위에 포함할지 별도 후속으로 뺄지.

## 구현 순서 제안

1. kernel.py: `GateRecord`/`OpenExecutionGate`/`CloseExecutionGate`/이벤트 2종 + `Mission.open_gates` 필드. 단위 테스트(idempotency, state 불변, 여러 개 동시 open).
2. dual_write.py: `mirror_inbox_creation`/`mirror_inbox_resolution`을 새 메커니즘으로 전환. 기존 3개 테스트 재작성.
3. read_model.py: `MissionOperationalStatus` + `compute_operational_status()` + `open_execution_gates` 노출. 우선순위 표의 6개 케이스 전부 단위 테스트(terminal 우선, 3가지 WAITING_FOR_HUMAN 소스 통합, RUNNING/READY/PLANNING).
4. mission_read_model.py router: `operational_status`/`open_execution_gates` payload에 추가.
5. mission_dual_write_verify.py: item 단위 비교로 교체(+ 선택적으로 orphaned_gate 차원).
6. 실제 production 경로(전 턴에서 썼던 real-inbox-flow 재현)로 재검증 — 이번엔 `EXECUTING` 등 mid-execution 상태에서 gate가 열리고 `operational_status`가 `WAITING_FOR_HUMAN`으로 정확히 바뀌는지까지 확인.

구현 진행해도 될지 확인 부탁드립니다.
