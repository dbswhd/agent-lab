# 13 — 문서 거버넌스와 다음 실행 단계

> **상태:** In progress / D0
> **목적:** 기존 142개 docs와 11개 재설계 문서의 권위를 분리하고, first-pass 이후 실제 실행 순서를 고정한다.
> **원칙:** 문서를 대량 삭제하지 않는다. 먼저 authority를 지정하고, 링크·코드·테스트가 없는 문서는 archive/retire 후보로 분류한 뒤 별도 승인 후 이동한다.

## 1. 문서 권위 규칙

1. runtime 동작은 code + tests가 최우선이다.
2. 현재 실행 큐는 `docs/NOW.md`만 소유한다.
3. 현재 flow는 `docs/FLOW.md`, 턴은 `docs/TURN-CONTRACT.md`, 평가는 `docs/EVAL-CONTRACT.md`가 소유한다.
4. 새 Mission 설계와 전환은 `docs/redesign-2026-07/README.md`와 00~13 문서가 소유한다.
5. feature 상세는 Human Inbox, Room transcript, Role orchestration 같은 domain 문서가 소유하되, lifecycle authority를 새로 만들지 않는다.
6. `archive/`, `historical reference`, `completed plan` 문서는 배경과 근거로만 읽고 현재 상태 판정에 사용하지 않는다.

## 1.1 11개 문서의 남은 작업 판정

| 문서                          | first-pass 상태                  | 아직 남은 일                                                 | 다음 실행 단계 |
| ----------------------------- | -------------------------------- | ------------------------------------------------------------ | -------------- |
| `00` inventory                | 기준선·fixture 완료              | Human review, ordered event 근거 보강                        | Step 0/6       |
| `01` kernel                   | pure aggregate·merge/repair 완료 | session adapter, legacy authority cutover                    | Step 1/6       |
| `02` durability               | lock·tail guard·idempotency·identity·atomic batch·claim lease(scheduler + 실 execute merge 경로) 완료 (2026-07-16) | side-effect reconcile 자동화(현재는 lease만 가드, recovery decision 수렴은 daemon 실통합 후) | Step 5         |
| `03` runtime/context/memory   | recipe contract 완료             | provider port, memory promotion, provenance                  | Step 2/4       |
| `04` Human UX/API/UI          | decision model·bridge·read-model route·UI wiring·SSE cursor·optimistic locking 완료 (2026-07-15) | 완전한 decision+run.json 단일 트랜잭션 원자성                | Step 2/3 완료  |
| `05` reliability/ops          | test baseline 완료               | fault injection, telemetry, dogfood SLO                      | Step 4/5/6     |
| `06` async runtime            | Activity·lease·recovery·queue first pass | daemon/scheduler integration, provider/execute wiring        | Step 4/5       |
| `07` five principles          | design constraints 완료          | scorecard CI, adoption gate, quarterly review                | Step 5/6       |
| `08` messaging                | local envelope/dispatcher 완료 · CM1 콜백 채널 inventory 완료(2026-07-16) | registry(work_request/artifact_ref 필요성 결정 선행), durable delivery, SSE/gateway adapters, 나머지 5채널 항목 단위 inventory | Step 2/5       |
| `09` context engineering      | selector/manifest 완료           | source registry, redaction/provenance, assembler convergence | Step 2/4       |
| `10` multi-agent coordination | topology selector 완료           | task/result contract, quorum/critic, lift benchmark          | Step 4/6       |

따라서 11개 문서에서 “더 할 일이 없다”가 아니라, **계약 first pass는 닫혔고 실제 시스템으로 옮기는 application/UI/runtime wave가 남아 있다.**

## 2. 기존 docs 분류

### A. 계속 유지할 canonical docs

| 묶음       | 문서                                                                                           | 이유                             |
| ---------- | ---------------------------------------------------------------------------------------------- | -------------------------------- |
| Core       | `README.md`, `NOW.md`, `NORTH-STAR.md`, `FLOW.md`, `ARCHITECTURE.md`                           | 현재 방향·구조·우선순위의 진입점 |
| Contract   | `TURN-CONTRACT.md`, `EVAL-CONTRACT.md`, `ROOM-TRANSCRIPT-CONTRACT.md`                          | 현재 동작 계약과 검증 기준       |
| Operations | `STABILITY.md`, `OPS-RUNBOOK.md`, `EXTERNAL-REFS-TRACEABILITY.md`                              | 운영·shipped·외부 reference 근거 |
| Human/Room | `MCP-FIRST-INBOX.md`, `HUMAN-INBOX.md`, `05-room-agent-roles.md`, `ROLE-ORCHESTRATION-PLAN.md` | 현재 UI·권한·역할 surface        |
| Product/UI | `CONSOLE-PRODUCTIZATION.md`, `DESIGN-SYSTEM.md`, `USER-GUIDE.md`, `MISSION-OS-DIRECTION.md`    | 현재 사용 경험과 제품화 기준     |

이 문서들은 새 11~13에서 대체하지 않는다. 새 문서는 Mission read model과 cutover 관점의 보완 문서다.

### B. 새 재설계 문서군에서 계속 유지할 문서

`00`은 기준선, `01~05`는 core sector, `06~10`은 async·principles·messaging·context·coordination contract, `11`은 UI surface, `12`는 compatibility audit, `13`은 governance/steps를 소유한다.

### C. 통합해서 참조만 남길 문서

| 문서/묶음                                                   | 조치                                                                                       |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `UI-IA-ROADMAP.md`                                          | 기존 UI migration history로 유지하되, 새 UI 판단은 11과 `CONSOLE-PRODUCTIZATION.md`로 이동 |
| `MISSION-LOOP-C-OMO.md`                                     | shipped legacy loop 근거로 유지; 새 lifecycle 설계 권위는 01/06/12로 이동                  |
| `RUNTIME-HARNESS-PLAN.md`, `ROOM-DISPATCH-PROTOCOL.md`      | runtime/transport history와 contract 근거로 유지; Mission event authority는 02/08로 이동   |
| `archive/STRUCTURE-REFACTOR-HISTORY.md` (구 package refactor 문서 13개, 2026-07-15 통합) | 이미 shipped인 구조 이동 기록으로 유지; recipe 정책은 09로 이동                            |
| `HUMAN-INBOX-CLAUDE-HANDOFF.md`                             | handoff/history로 유지; current answer UX는 `HUMAN-INBOX.md`와 11로 이동                   |
| `ABSORB-CC-CODEX-2026-07.md`                                | provider/UI 패턴 채택 기록으로 유지; Mission state 의미는 01/12로 연결                     |

### D. archive/reference로 강등할 문서

- `WORKFLOW-DYNAMIC-REFERENCE.md`, `TURN-MODES.md`, `TURN-POLICY.md`
- `EVAL-SURFACE-SUPER-SAMPLE-PLAN.md`, `EVAL-SURFACE-V1-PLAN.md`
- `N10-USER-LOOP-WISDOM-DRAFT.md`, `REVIEW-LINER-RESEARCH-2026-07.md`, `STRATEGIC-DIRECTION-2026.md`
- 이미 `docs/archive/**`, `docs/archive/legacy/**`, `docs/archive/rfcs/**`에 있는 문서 전체

이 문서들은 삭제하지 않고 상단에 `historical/reference — current authority는 링크된 canonical doc`를 유지한다.

### E. 계속 분리할 extension lane

`docs/extensions/`, `docs/trading-mission/`, `F5-TRADING-ISOLATION.md`, quant package 문서는 core Mission cutover에 섞지 않는다. 새 Mission port를 소비하는 선택 기능으로만 검토한다.

## 2.1 문서 링크 위생 baseline

현재 `docs/**/*.md`의 상대 링크를 기계적으로 검사한 결과, **40개 문서에서 127개 상대 경로가 존재하지 않는다.** 대표 원인은 이미 `docs/archive/`로 이동한 문서를 옛 경로로 가리키거나, package refactor 뒤 source 경로를 갱신하지 않은 경우다.

우선순위는 다음과 같다.

1. `docs/README.md`, `NOW.md`, `FLOW.md`, `STABILITY.md`, `USER-GUIDE.md`, `MCP-FIRST-INBOX.md`의 링크를 먼저 복구한다.
2. archive 문서의 링크는 current canonical 링크로 치환하거나 historical reference임을 명시한다.
3. package refactor 문서의 source 경로는 실제 `src/agent_lab/<package>/`를 기준으로 갱신한다.
4. 링크 checker를 CI 문서 gate로 추가하되, external URL과 archive 의도 링크는 allowlist로 분리한다.

## 3. 지금 바로 정리할 문서 metadata

- 11개 재설계 문서의 상태와 first-pass/cutover 경계를 현재 구현과 맞춘다.
- `00`의 M1 완료 기준은 Human review pending으로 유지한다.
- `docs/README.md`에 11~13을 “Migration / first-pass” 묶음으로 추가한다.
- 기존 docs를 삭제하기 전에 inbound link와 `EXTERNAL-REFS-TRACEABILITY.md`를 검사한다.
- 하나의 주제에 canonical doc을 두 개 만들지 않는다.

## 4. 실행 단계

### Step 0 — authority와 baseline 고정

**산출:** 문서 상태·owner·canonical 링크 정리.

**완료 기준:** `docs/README.md`, redesign README, NOW가 서로 다른 현재 상태를 말하지 않는다.

**검증:** docs link scan, `python scripts/smoke_room.py`.

### Step 1 — Mission application adapter

**현재 상태:** first-pass adapter와 opt-in canonical route bridge 완료 (`src/agent_lab/mission/application.py`, `src/agent_lab/mission/dual_write.py`); 실제 `sessions/` route cohort 10건과 rollback 2건 통과. full traffic cutover는 보류.

**산출:** session folder의 `plan.md`와 기존 API를 Mission repository command로 연결하는 adapter.

**완료 기준:** plan approve/reject가 동일 command/event와 legacy read model parity report를 만든다. execute gate는 우회하지 않는다.

**검증:** plan reject→reopen→approve API integration, stale version, restart replay.

### Step 2 — MissionReadModel과 UI contract

**현재 상태:** `src/agent_lab/mission/read_model.py` projection contract와 read-only `/api/sessions/{id}/mission/read-model` route first pass 완료; SSE cursor와 browser QA는 pending.

**산출:** `MissionReadModel` schema, compatibility projection, SSE cursor.

**완료 기준:** UI가 `run.json`·`plan_workflow`·`mission_loop`를 직접 조합하지 않는다.

**검증:** schema test, snapshot parity, reconnect duplicate test.

### Step 3 — Decision Queue vertical slice

**현재 상태:** `MissionApplication.answer_inbox()` first-pass adapter, production router opt-in bridge, restart/resolve test, 실제 Room dogfood 2건 완료; cross-store atomicity는 pending.

**산출:** `HumanInboxPanel` answer를 Decision Repository와 `human_bridge`에 연결.

**완료 기준:** pending → answer → Activity/Mission resume가 앱 재시작 후에도 한 번만 실행된다.

**검증:** browser journey, stale answer, duplicate answer, expiry.

### Step 4 — Execute/merge/Oracle vertical slice

**현재 상태:** kernel/repository first-pass path already covers execute→diff approval→merge→Oracle pass and Oracle fail→repair→new merge; real worktree/Oracle ports remain pending.

**산출:** worktree activity, diff approval, merge side effect, Oracle/repair event를 동일 Mission stream에 기록.

**완료 기준:** merge와 Oracle pass가 분리되고, 동일 idempotency key가 merge를 중복 실행하지 않는다.

**검증:** temporary git repo, process kill/restart, repair cap.

### Step 5 — Durable runtime hardening

**현재 상태:** Journal append에 cross-process lock file, non-monotonic/malformed tail guard, durable idempotency key 재사용·충돌 검사, MissionRepository 경로의 mission/schema identity와 multi-event batch record가 first pass로 적용됨. `activity_lease.py`(root-level — `mission`↔`plan` 2-cycle 회피), `mission/recovery.py`, Activity claim/heartbeat/release 전이와 `activity_queue.py`의 priority/idempotent enqueue/lease-aware recovery도 추가했다. `scheduler_shadow.py`가 기존 `schedule_due`와 새 candidate/idempotency key를 read-only로 비교한다. **2026-07-16:** claim lease가 scheduler shadow 경로뿐 아니라 실제 production merge side effect(`plan/execute_shared.py::_do_worktree_merge`, `plan/execute_resolve.py::confirm_merge_execution`)에도 연결돼, 동일 execution의 동시 merge 시도가 `MergeInProgressError`(409)로 거부된다. Production daemon enqueue와 daemon crash 시 recovery decision 자동 수렴은 여전히 pending(섹터 06).

**산출:** cross-process lock, atomic batch/commit marker, claim lease, heartbeat, side-effect reconcile.

**완료 기준:** daemon crash가 orphan/ambiguous side effect를 하나의 recovery decision으로 수렴시킨다.

**검증:** multiprocessing contention, fault injection, corrupted journal, long-running daemon.

### Step 6 — Legacy shadow parity와 cutover gate

**현재 상태:** scheduler shadow candidate report와 ordered parity evaluator first pass 완료. 실제 `sessions/` route cohort, Room dogfood 2건, fail→repair `RepairScheduled` parity, G3 process kill/restart, ActivityQueue startup/scheduler recovery 및 daemon health 관찰이 통과했다. [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)은 evidence GO로 재판정하며, legacy retire/Mission 단일 authority 승격은 명시적 Human cutover 승인 전까지 보류한다.

**산출:** ordered event drift report와 dual-read 기간.

**완료 기준:** 대표 5개 fixture와 dogfood sample에서 parity가 기준을 만족하고, legacy writer 제거 날짜가 승인된다.

**검증:** full regression, 10 mission dogfood, Human review.

### Step 7 — 문서·코드 retire

**산출:** retire list, migration note, 삭제 PR.

**완료 기준:** 중복 FSM/reconcile/compatibility path와 stale docs가 남지 않고, extension lane은 독립적으로 동작한다.

**검증:** dead import/route scan, docs link check, clean clone quickstart.

## 5. 체크포인트

- **Checkpoint A:** Step 0~1 후 Human review. 기존 API와 새 command의 권위 경계를 승인한다.
- **Checkpoint B:** Step 2~3 후 browser QA. Decision Queue와 reconnect UX를 승인한다.
- **Checkpoint C:** Step 4~5 후 reliability review. crash/duplicate side effect 기준을 승인한다.
- **Checkpoint D:** Step 6 후 cutover 승인. 그 전에는 legacy writer를 삭제하지 않는다.
