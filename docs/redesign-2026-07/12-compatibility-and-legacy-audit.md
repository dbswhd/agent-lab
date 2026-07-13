# 12 — First-pass compatibility·legacy audit

> **상태:** In progress / D0
> **목적:** 새 first-pass 코드가 기존 Agent Lab의 writer, dispatcher, UI, 문서와 충돌하거나 가려지는 지점을 고정한다.
> **판정:** `conflict`는 같은 사실을 두 곳이 쓰는 경우, `overlap`은 개념이 겹치지만 교체 경계가 있는 경우, `hidden`은 사용되지 않거나 UI에서 가려질 위험이다.

## 1. 요약 판정

새 코드는 현재 production path에 import되지 않은 격리된 contract/prototype이다. 따라서 즉시 동작 충돌은 없지만, adapter를 추가하는 순간 다음 두 writer가 동시에 살아나는 위험이 있다.

```text
legacy run.json / plan_workflow / mission_loop / human_inbox
                         │
                         ├─ current API + UI projections
                         └─ new Mission journal + kernel + Decision Queue
```

**결론:** 지금은 shadow/projection 단계로 유지한다. legacy writer를 제거하거나 새 kernel을 API에 직접 연결하면 안 된다.

## 2. 코드 충돌·겹침·가려짐

| 새 산출물                                         | 기존 surface                                                                | 판정          | 리스크                                                                  | 처리 기준                                                       |
| ------------------------------------------------- | --------------------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------- |
| `mission/kernel.py`                               | `mission/loop.py`, `mission/advance.py`, `runtime/transitions.py`           | conflict 후보 | phase와 event가 서로 다른 결론을 만들 수 있음                           | application adapter와 parity 후 kernel만 write authority로 승격 |
| `mission/repository.py`, `journal.py`             | `run/meta.py`, `checkpoint_store.py`, `crash_recovery.py`                   | conflict 후보 | journal과 run.json의 부분 commit·재시작 순서가 달라짐                   | batch atomicity, identity, idempotency, recovery proof 필요     |
| `decision_queue.py`                               | `human_inbox.py`, `inbox/`, `app/server/routers/human_inbox.py`             | overlap       | answer가 legacy inbox만 바꾸고 Mission을 재개하지 않을 수 있음          | `human_bridge.py`를 실제 resolve path에 연결                    |
| `mission/dispatcher.py`                           | `runtime/dispatcher.py`, `room/dispatch.py`, MCP routing                    | overlap       | 같은 command가 transport별로 중복 실행될 수 있음                        | envelope/authority/correlation/idempotency registry 통합        |
| `mission/messages.py`                             | `room/messages.py`, SSE types, chat payload                                 | overlap       | 이름은 namespace로 안전하지만 의미·schema가 달라질 수 있음              | `MissionMessage`와 Room message를 adapter에서만 변환            |
| `context/recipe.py`                               | `context/bundle.py`, `context/layers.py`, `context/meta.py`, notepad/wisdom | overlap       | recipe가 선택 정책을 소유하지 못하고 legacy bundle이 계속 prompt를 조립 | provider invocation 하나당 recipe assembler 하나로 수렴         |
| `mission/topology.py`                             | `role_plan.py`, `ROLE-ORCHESTRATION-PLAN.md`, Room presets                  | overlap       | supervisor preset과 topology 결정이 서로 덮어씀                         | preset은 ceiling/default, topology는 task feature 결정으로 분리 |
| `mission/shadow.py`                               | `orchestration_reconcile.py`, work phase derivation                         | hidden        | snapshot diff가 중간 event drift를 숨길 수 있음                         | ordered event ledger와 drift report 추가                        |
| `mission/application.py`, `mission/read_model.py` | plan routers, session snapshot, React hooks                                 | hidden        | adapter/projection이 route에 연결되지 않으면 두 lifecycle이 계속 병존   | API parity 후 read model만 UI에 제공                            |
| `mission/scheduler_shadow.py`                    | `mission/scheduler.py`, `run.json schedules[]`                             | shadow       | due candidate가 다르면 daemon cutover 전에 schedule가 중복·누락될 수 있음 | read-only candidate/idempotency parity 후 queue enqueue 승인      |
| new UI contract                                   | `ComposerEventStack`, `WorkStatusBar`, `WorkspaceCard`, `HumanInboxPanel`   | hidden        | 동일 상태가 여러 badge/CTA로 노출될 수 있음                             | [11 UI surface map](./11-ui-ux-surface-map.md) precedence 적용  |

## 3. 현재 writer inventory

| 사실                    | 현재 writer                                                       | 새 목표 writer                   | 전환 전 금지                                       |
| ----------------------- | ----------------------------------------------------------------- | -------------------------------- | -------------------------------------------------- |
| plan approval/rejection | `plan/workflow_approval.py` → `patch_run_meta`                    | Mission command/event            | 두 writer의 결과를 자동 reconcile하지 않음         |
| mission pause/resume    | `mission/loop.py` → `run.json`                                    | Mission/Activity event           | UI phase를 직접 수정하지 않음                      |
| execute/merge           | `plan/execute*`, `merge_gate.py`                                  | Activity + side-effect event     | merge를 Oracle pass로 간주하지 않음                |
| Oracle/repair           | `oracle_core.py`, `verify_repair_policy.py`, `mission/advance.py` | `RecordOracle` + repair activity | 같은 failure를 legacy/new 양쪽에서 재시도하지 않음 |
| Human answer            | `human_inbox.py` / router                                         | Decision Repository + bridge     | stale answer가 legacy writer에만 반영되지 않음     |
| read model              | `run.json`, runtime snapshot, SSE payload                         | MissionReadModel projection      | UI가 여러 raw payload를 조합하지 않음              |

## 4. 레거시 리스크 등급

### P0 — cutover 전에 반드시 닫을 것

- 새 journal의 cross-process append lock과 command batch atomicity
- journal에 mission identity/schema/version/causation을 기록하고 잘못된 repository replay 차단
- command idempotency를 process memory가 아닌 durable ledger로 이동
- 기존 `run.json`과 Mission event의 ordered parity report
- legacy scheduler due candidate와 ActivityQueue candidate의 idempotency parity

### P1 — UI/API 연결 전에 닫을 것

- Human Inbox answer → Decision Queue → Activity/Mission resume 실제 adapter
- `MissionReadModel` API와 기존 session payload의 compatibility projection
- dispatcher sender/recipient authority와 gateway authentication
- context provenance/trust/redaction을 caller-supplied flag에 맡기지 않기

### P2 — 전환 중 정리할 것

- `ActivityState.CLAIMED`에 lease/heartbeat/timeout 추가
- progress consumer 예외 격리와 dead-letter/replay 정책
- `MessageEnvelope` payload deep immutability와 size limits
- topology/role plan/preset metric의 단일 promotion 기준

## 5. 확인 명령

```bash
rg -n "MissionRepository|DecisionRepository|LocalDispatcher|select_context|choose_topology" src app web
rg -n "patch_run_meta|run.json|mission_loop|plan_workflow|human_inbox" src app web
python scripts/smoke_room.py
pytest -q tests/test_mission_*.py tests/test_no_layer_cycles.py
```

현재 확인 결과 새 contract 모듈은 기존 runtime에서 호출되지 않는다. 이 결과는 안전한 격리를 뜻하지만, 동시에 production 전환이 아직 시작되지 않았다는 뜻이다.
