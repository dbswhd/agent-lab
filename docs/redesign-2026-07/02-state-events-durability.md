# Sector 2 — 상태·이벤트·내구성

> **상태:** In progress / D0 — lock·tail guard·idempotency·batch record first pass, durable cutover pending  
> **선행:** [01 Mission Kernel](./01-mission-kernel.md) command/event 계약  
> **후행:** 모든 섹터의 저장·관측 기반

## 1. 목표

세션 폴더의 장점인 로컬 우선·감사 가능성은 유지하면서, `run.json` 가변 dict 중심 구조를 **append-only event journal + 재생 가능한 snapshot + 목적별 artifact** 구조로 바꾼다.

## 착수 상태

`src/agent_lab/mission/journal.py`가 JSONL append, sequence conflict, cross-process lock file, fsync, 손상된 마지막 tail 복구와 durable idempotency key 재사용을 제공한다. 다중 event append는 하나의 batch record로 저장해 logical append 단위로 복구한다. `MissionRepository` 경로에는 mission/schema identity도 기록·검증한다. `event_codec.py`와 `repository.py`가 Mission event replay를 연결하며, 기존 `run.json` writer는 아직 compatibility projection으로 유지한다. claim lease와 side-effect reconcile 통합은 아직 cutover 전 과제다.

## 2. 현재 평가

### 강점

- `chat.jsonl`, `plan.md`, `run.json`, evidence JSONL이 사람이 열어볼 수 있다.
- `patch_run_meta()`와 file lock/atomic replace 규율이 직접 쓰기보다 안전하다.
- crash recovery, checkpoint, live archive 등 내구성 문제를 이미 인지하고 있다.

### 결함

| 결함                                                                    | 영향                                    |
| ----------------------------------------------------------------------- | --------------------------------------- |
| `RunState(dict[str, Any])`에 여러 도메인의 현재값·이력·캐시가 공존      | schema ownership과 migration이 약함     |
| 여러 모듈이 `patch_run_meta()` callback으로 같은 문서를 갱신            | 필드 단위 충돌과 stale read 위험        |
| chat, live log, SSE, run snapshot, evidence가 부분적으로 같은 사실 표현 | refresh/reconnect reconciliation이 복잡 |
| 파생 orchestration state를 다시 저장                                    | source와 cache의 경계가 흐림            |
| long-running side effect의 intent/commit 기록이 일관되지 않음           | 재시작 시 중복 실행 판단이 어려움       |

## 3. 설계 결정

### D1. 세션 저장 단위를 분리한다

```text
sessions/<id>/
  manifest.json             # schema/version/workspace/created_at
  events/mission.jsonl      # ordered domain facts
  snapshots/mission.json    # replay checkpoint, rebuildable
  artifacts/plans/<rev>.md
  artifacts/evidence/*.json
  artifacts/diffs/*.patch
  projections/transcript.jsonl
  projections/work.json
  projections/inbox.json
```

projection은 삭제 후 event에서 다시 만들 수 있어야 한다. artifact는 content hash로 참조하며 event 본문에 큰 텍스트를 중복 저장하지 않는다.

### D2. 단일 writer와 optimistic concurrency를 사용한다

Mission command 처리는 다음 순서를 따른다.

1. stream + version load
2. pure decision
3. expected version으로 event batch append
4. side-effect job enqueue
5. projection update

동일 mission의 append는 직렬화한다. 서로 다른 mission은 병렬 처리할 수 있다.

### D3. 이벤트는 감사 로그이지 디버그 로그가 아니다

공통 envelope:

```json
{
  "event_id": "...",
  "mission_id": "...",
  "sequence": 42,
  "type": "PlanApproved",
  "schema_version": 1,
  "occurred_at": "...",
  "actor": { "kind": "human", "id": "local" },
  "causation_id": "command-id",
  "correlation_id": "turn-or-execution-id",
  "payload": {},
  "redactions": []
}
```

모델의 chain-of-thought, secret, 전체 prompt는 event에 저장하지 않는다. 근거는 허용된 summary와 artifact ref로 기록한다.

### D4. side effect는 intent/result 쌍으로 만든다

예:

```text
ExecutionRequested -> ExecutionStarted -> ExecutionSucceeded|ExecutionFailed
MergeRequested     -> MergeStarted     -> MergeCommitted|MergeFailed
AgentCallRequested -> AgentCallStarted -> AgentCallCompleted|AgentCallFailed
```

재시작 시 `Requested/Started`만 있고 terminal result가 없는 작업을 recovery policy가 처리한다. merge처럼 비가역 구간은 git state를 조회해 commit 여부를 reconcile하되, 새 사실을 event로 남긴다.

### D5. 외부 브로커는 보류한다

현재 단일 사용자·로컬 데스크톱 제품에서는 SQLite WAL 또는 file journal로 충분하다. 다음 조건 중 하나가 측정될 때 broker/workflow engine ADR을 연다.

- 여러 프로세스/노드가 같은 mission stream을 소비해야 함
- 1분 이상 작업 수가 로컬 queue 처리량을 지속 초과
- 수일짜리 timer와 대량 schedule recovery가 핵심 SLO가 됨
- local store 장애 허용 범위를 넘어선 HA 요구가 생김

## 4. 구현 계획

### S1. Event catalog와 ownership registry

**산출물:** event type, producer, consumer, payload schema, retention, PII 등급 표.

**Acceptance criteria:**

- 현재 run/chat/live/evidence 변화가 event 또는 projection-only로 분류된다.
- 각 event에 단일 producer가 있다.
- schema evolution 규칙(upcaster, no in-place history rewrite)이 정의된다.

**검증:** catalog coverage 검사로 미분류 lifecycle mutation이 0이다.

### S2. Local journal prototype

**산출물:** append, load, expected-version check, fsync policy, corrupted-tail recovery.

**Acceptance criteria:**

- append 중 crash가 이전 event를 손상시키지 않는다.
- sequence gap과 duplicate event id를 감지한다.
- concurrent append 중 하나만 expected version에 성공한다.
- 10,000 events replay 시간과 snapshot 크기를 측정한다.

**검증:** multiprocessing fault test와 benchmark.

### S3. Projection framework

**산출물:** transcript, work, inbox projection.

**Acceptance criteria:**

- full rebuild와 incremental apply 결과가 byte-equivalent하다.
- SSE resume cursor가 event/projection offset으로 동작한다.
- UI가 lifecycle 필드를 자체 조합하지 않고 projection을 소비한다.

**검증:** reconnect/refresh E2E, projection golden tests.

### S4. Shadow event capture

**산출물:** 기존 mutation 경로 뒤 event journal을 기록하는 adapter.

**Acceptance criteria:**

- 외부 side effect는 기존 경로만 실행한다.
- event replay state와 `run.json` 비교 report가 생성된다.
- secret/PII scan을 통과한다.

**검증:** 대표 fixture 5개 parity, dogfood 10 mission drift report.

### S5. Command write authority 전환

**산출물:** 새 Mission service가 journal을 먼저 쓰고 기존 `run.json`은 compatibility projection이 됨.

**Acceptance criteria:**

- `run.json`을 삭제해도 journal에서 재생성 가능하다.
- stale writer는 version conflict를 받고 재결정한다.
- crash recovery가 event 상태와 실제 git 상태를 함께 사용한다.

**검증:** delete/rebuild, two-writer race, kill -9 recovery.

### S6. Legacy store 축소

**산출물:** `run.json`을 public compatibility snapshot으로 축소하거나 제거.

**Acceptance criteria:**

- lifecycle module의 임의 dict mutation이 없다.
- live archive와 persisted chat의 중복 역할이 정리된다.
- migration tool이 이전 세션을 read-only로 열거나 새 형식으로 변환한다.

**검증:** historical session corpus migration dry-run, full CI.

## 5. 스키마·보존 정책

| 데이터                       | 보존        | 규칙                                |
| ---------------------------- | ----------- | ----------------------------------- |
| domain events                | 장기        | append-only, redact-at-write        |
| plan/diff/evidence artifacts | 장기        | content-addressed, provenance 필수  |
| provider raw stream          | 짧음/옵트인 | 디버그 목적, secret filter, TTL     |
| projections                  | 재생성 가능 | cache, schema 자유롭게 재구축       |
| context bundle               | 기본 미보존 | hash·source refs·token stats만 보존 |
| cost/latency metrics         | 집계 장기   | 원문 prompt 불필요                  |

## 6. 마이그레이션과 롤백

- v0 reader는 기존 session을 그대로 연다.
- 첫 write 시 v1 stream을 만들되 원본 파일을 수정하지 않는다.
- shadow 기간에는 v0이 side-effect authority, v1은 비교 전용이다.
- cutover 후 v1이 authority, v0 `run.json`은 projection이다.
- rollback은 v1 event를 버리지 않고 v0 projection을 재생성해 이전 binary가 읽게 한다.

## 7. 완료 정의

- mission 상태는 event stream에서 결정론적으로 복원된다.
- 같은 side effect가 crash/retry로 두 번 commit되지 않는다.
- refresh/reconnect가 메시지 중복·유실 없이 동일 transcript를 만든다.
- 필드 소유권이 event producer 단위로 명확하다.
- 외부 broker 없이 현재 로컬 workload SLO를 만족한다.
