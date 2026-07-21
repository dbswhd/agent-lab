# CM1 — 메시지 inventory (2026-07-16)

> [08-collaboration-messaging.md](../08-collaboration-messaging.md) §11 CM1의 산출물. `messages.py`/`dispatcher.py`
> 프로토타입은 어디에도 연결돼 있지 않고(§0), CM2 registry를 설계하기 전에 실제로 뭘 감싸야 하는지부터 고정한다.
> **판정을 바꾸지 않는다** — 이 문서는 감사 결과이지 CM2 착수 승인이 아니다.

## 0. 왜 필요한가

`mission/messages.py`(`MessageEnvelope`)와 `mission/dispatcher.py`(`LocalDispatcher`)는 다른 모듈에서
`JsonValue` 타입 하나만 재사용될 뿐, 실제 callback/SSE/chat/dispatch/MCP/gateway 메시지 흐름과 **완전히 분리된
프로토타입**이다. CM1 없이 CM2(schema registry)를 만들면 어떤 사실을 감쌀지 근거가 없다.

## 1. Callback channel — `on_event(type, payload)` (기계적 추출, 검증 가능)

`scripts/message_inventory_scan.py`가 `src/agent_lab/room/*.py` + `plan/workflow_state.py`의
`on_event(` 리터럴 호출(및 `dispatch.py`의 `_emit_dispatch_events` 1단계 간접 호출)을 스캔한다.
`tests/test_message_inventory.py`가 스캔 결과와 이 표의 행 집합이 정확히 일치하는지 검증 — 새 타입이
분류 없이 추가되면 테스트가 실패한다(CM1 acceptance criteria: "미분류 on_event type ... 0").

**현재 실태:** 40개 타입 전부 in-process callback → SSE 변환만 거치고, 어디에도 journal되지 않는다.
프로세스 재시작·SSE reconnect 시 이미 지나간 타입은 전부 유실된다(§2 결함 표의 "callback, persisted
chat, live log, SSE가 같은 사실을 다르게 표현"과 동일 문제). 아래 durability 열은 08 문서 §5.1 규칙을
적용했을 때 "요구되는" 값이지, 지금 실제로 보장되는 값이 아니다 — 실제는 전부 best-effort(비영속)다.

| event_type | owner | kind | 요구 durability (§5.1 규칙 적용) | 비고 |
| --- | --- | --- | --- | --- |
| `agent_start` | `room/agent_invoke.py` | progress | best_effort | 개별 agent 호출 시작 |
| `agent_done` | `room/agent_invoke.py` | event | at_least_once | 개별 agent 호출 종료(terminal) |
| `agent_round_start` | `room/consensus_rounds.py`, `parallel_rounds.py` | progress | best_effort | 라운드 시작 |
| `delegate_start` | `room/dispatch.py` | progress | best_effort | delegate dispatch 시작(dispatch_start의 fan-out) |
| `delegate_done` | `room/dispatch.py` | event | at_least_once | delegate dispatch 종료(terminal, dispatch_done의 fan-out) |
| `dispatch_start` | `room/dispatch.py` | progress | best_effort | 범용 dispatch 시작 |
| `dispatch_done` | `room/dispatch.py` | event | at_least_once | 범용 dispatch 종료(terminal) |
| `hook_event` | `room/dispatch.py` | event | at_least_once | dispatch hook 실행 결과 |
| `consensus_reached` | `room/consensus_rounds.py` | event | at_least_once | consensus FSM terminal fact |
| `consensus_incomplete` | `room/consensus_rounds.py` | event | at_least_once | consensus round 미완료(terminal for that round) |
| `consensus_retry` | `room/consensus_rounds.py` | progress | best_effort | round 1 에이전트 호출 실패 → 해당 에이전트만 1회 재시도 |
| `consensus_dry_run_proposal` | `room/turn_meta.py` | human_decision | at_least_once | Human 승인 대상 제안 |
| `consensus_plan_sync_start` | `room/turn_meta.py` | progress | best_effort | plan sync 시작 |
| `consensus_plan_sync_failed` | `room/turn_meta.py` | event | at_least_once | plan sync 실패(terminal) |
| `verified_plan_sync_start` | `room/turn_meta.py` | progress | best_effort | verified-loop plan sync 시작 |
| `verified_plan_sync_failed` | `room/turn_meta.py` | event | at_least_once | verified-loop plan sync 실패(terminal) |
| `debate_convergence` | `room/consensus_rounds.py` | event | at_least_once | 토론 수렴 판정 |
| `divergence_options` | `room/turn_flow_support.py` | human_decision | at_least_once | 분기 선택지 — Human 판단 필요 |
| `category_escalated` | `room/consensus_rounds.py` | event | at_least_once | 토픽 카테고리 escalation 판정 |
| `quality_gate_review` | `room/consensus_rounds.py` | human_decision | at_least_once | 품질 게이트 — Human review 대상 |
| `model_policy_applied` | `room/consensus_rounds.py` | event | at_least_once | 모델 정책 적용 결과 |
| `efficiency_auto_enabled` | `room/turn_flow_support.py` | event | at_least_once | 자동 효율 모드 전환 |
| `agent_subset_applied` | `room/turn_routing.py` | event | at_least_once | agent subset 라우팅 결정 |
| `recombination_round_start` | `room/consensus_rounds.py` | progress | best_effort | 재조합 라운드 시작 |
| `budget_status` | `room/turn_flow_support.py` | progress | best_effort | 예산 잔여 상태 |
| `budget_exhausted` | `room/turn_flow_support.py` | event | at_least_once | 예산 소진(terminal for that budget) |
| `clarifier_prompt` | `room/turn_flow_setup.py` | human_decision | at_least_once | clarifier 질문 |
| `inbox_pending` | `room/plan_scribe.py`, `turn_policy.py` | human_decision | at_least_once | Human Inbox 항목 발생 |
| `inbox_pause` | `room/consensus_rounds.py` | human_decision | at_least_once | Inbox 대기로 인한 turn 일시정지 |
| `plan_actions_validation` | `room/plan_scribe.py` | event | at_least_once | plan action 파싱/검증 결과 |
| `plan_workflow_pending` | `room/plan_scribe.py`, `turn_policy.py` | human_decision | at_least_once | plan 승인 대기 |
| `plan_workflow_phase` | `plan/workflow_state.py` | event | at_least_once | plan_workflow.phase 전이 |
| `scribe_start` | `room/plan_scribe.py`, `turn_meta.py` | progress | best_effort | scribe 작업 시작 |
| `scribe_done` | `room/plan_scribe.py`, `turn_meta.py` | event | at_least_once | scribe 작업 완료(terminal) |
| `scribe_error` | `room/plan_scribe.py`, `turn_meta.py` | event | at_least_once | scribe 작업 실패(terminal) |
| `scribe_skipped` | `room/plan_scribe.py`, `turn_meta.py` | event | at_least_once | scribe 작업 건너뜀(terminal) |
| `turn_failed` | `room/messages.py`, `turn_flow_support.py` | event | at_least_once | turn 실패(terminal) |
| `turn_partial` | `room/messages.py` | event | at_least_once | turn 부분 완료(terminal) |
| `run_cancelled` | `room/turn_flow_rounds.py` | event | at_least_once | run 취소(terminal) |
| `run_failed` | `room/turn_flow_support.py` | event | at_least_once | run 실패(terminal) |
| `complete` | `room/turn_flow_finalize.py` | event | at_least_once | run 정상 완료(terminal) |

**분류 요약:** command 0 · event 24 · work_request 0 · progress 9 · human_decision 7 · artifact_ref 0. (합계 40)
(work_request/artifact_ref가 0인 것 자체가 발견 — 지금 callback 채널은 순수 fire-and-forget 알림뿐이고,
08 문서가 정의한 "WorkRequested→Accepted→Progress→Result" 계약이나 artifact 참조 방식은 아직 어디에도
없다.)

**자연어 제어 directive:** callback 채널 안에는 없다. Room의 자연어 directive는 agent 응답 텍스트 안의
delegate/dispatch 지시문(§2 결함 "agent output 텍스트 안의 directive가 routing protocol 역할")이며,
`room/dispatch_intents.py`가 파싱한다 — 이건 별도 감사 대상이라 이번 CM1 스캔 범위 밖에 남겨둔다.

## 2. 나머지 5개 채널 — 채널 단위 개요 (기계적 검증 대상 아님)

이 표는 CM1이 요구하는 "producer-consumer 표"의 나머지 절반을 채널 단위로만 기록한다. 개별 메시지
타입 단위 전수 조사는 CM1의 남은 후속 작업으로 남긴다(아래 §3).

| 채널 | producer | consumer | 현재 durability | 비고 |
| --- | --- | --- | --- | --- |
| SSE | `room/sse_stream.py` | web `RoomChat.tsx`/`useRoomSseHandler.ts` | best_effort, resume cursor 있음 | callback event를 그대로 프레임으로 변환 — 별도 스키마 없음 |
| chat | `session.py`(`chat.jsonl` append) | 세션 재로드, transcript UI | at_least_once(파일 append) | 유일하게 실제로 durable한 채널 — 하지만 스키마가 자유 dict |
| dispatch ledger | `room/dispatch.py::append_dispatch_ledger` | `run.json.dispatch_ledger`(최근 100건) | at_least_once, capped ring buffer | 100건 초과분은 조용히 버려짐 — 08 문서의 "Dead Letter"/"retry 구분" 개념 없음 |
| MCP | `human_inbox/mcp_server.py`, `wisdom/mcp_server.py`, `research/mcp_server.py` | Cursor/Claude MCP client | tool-call 단위(호출자 책임) | stdio MCP — 08 문서의 work_request 계약과 개념적으로 가장 가까움 |
| gateway | Telegram/Slack/Discord/Webhook adapter | 외부 사람 | at_least_once(adapter별 상이) | `gateway.notification` 채널만 08 문서에 명명, 실제 adapter별 재시도/dedupe 정책은 코드 감사 전 |

## 3. CM1 acceptance criteria 대조

| 기준 | 상태 |
| --- | --- |
| 각 메시지가 6종 중 하나로 분류 | callback 채널 40/40 완료(§1). 나머지 5채널은 채널 단위만(§2) — 항목 단위 분류는 남은 작업 |
| owner와 durability 요구 명시 | callback 채널 완료. 나머지 채널은 producer 파일만 명시, durability는 "현재 실태" 수준 |
| 자연어 control directive 별도 목록 | callback 채널 안에는 없음을 확인, 실제 위치(`dispatch_intents.py`)만 특정 — 상세 스캔은 미착수 |
| 미분류 on_event type 0 검증 | `tests/test_message_inventory.py`가 `scripts/message_inventory_scan.py` 출력과 §1 표를 diff — 자동 검증됨 |

## 4. 다음

CM2(schema registry)는 이 표가 command/event/work_request/progress/human_decision/artifact_ref
각각에 실제로 몇 개가 있는지 근거로 삼을 수 있지만, work_request/artifact_ref가 현재 0건이라는 게
이 감사의 핵심 발견이다 — CM2를 시작하기 전에 그 두 종류가 실제로 필요한지(예: MCP 채널을 work_request로
공식화) 먼저 결정해야 한다. 이건 이번 세션 범위 밖 — 별도 설계 논의 필요.
