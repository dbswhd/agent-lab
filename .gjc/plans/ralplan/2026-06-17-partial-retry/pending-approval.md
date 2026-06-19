# RALPLAN Final Plan (pending approval) — partial-turn 실패 에이전트 부분 재시도

합의: Planner→Architect→Critic, iteration 2 APPROVE. run-id 2026-06-17-partial-retry.
사용자 마찰: "여러 에이전트 중 하나 실패하면 그 하나만 재시도가 안 되고 전체를 다시 돌려야 한다."

## ADR
- **Decision:** partial 턴(일부 성공·일부 실패)에서 **실패한 에이전트만** 같은 Human 턴 컨텍스트로 재호출하는 전용 경로 + 엔드포인트(POST /api/room/runs/retry-agents)를 추가한다. 마감 턴 레코드는 재오픈하지 않고, retried reply는 `retry_of_turn` 메타로 append-only, 원본 턴의 status/failed/succeeded 단일 필드만 갱신. 1차는 비-consensus discuss/team 턴 한정.
- **Drivers:** (1) 부분 실패 시 전체 재실행 비용 큼(실측 마찰), (2) 턴 응집성·중복 방지, (3) 기존 turn 의미론 충돌 회피.
- **Alternatives considered:** B(continue_room_round에 retry 플래그) — 887줄 핵심 함수 오염·회귀; C(프론트 재전송) — 새 Human 턴·메시지 중복으로 "같은 턴 부분 재시도" 미충족.
- **Why chosen (A):** 전용 경로로 깨끗이 분리, append-only + 단일 status 갱신으로 마감 레코드 손상 회피, run_agent_rounds(agents=subset)·run-lock·preflight 재사용.
- **Consequences:** retried reply는 retry_of_turn으로 같은 턴에 귀속; turn_status 단일 소유 필드; consensus/verified 턴은 후속. 구현 시 retry 라운드 비용 상한·턴 위치 식별을 테스트로 고정.
- **Follow-ups:** consensus/verified 턴 부분 재시도; 프론트 partial-turn 카드의 retry CTA를 신규 엔드포인트에 연결; retry 라운드 수 정책.

## 구현 계획 (mock-only)
1. `src/agent_lab/room_retry.py` (신규): `retry_failed_agents(folder, *, agents=None, on_event, permissions)` — load_session_messages → 마지막 턴 status/failed_agents 식별 → consensus/verified면 422 거부 → (failed_agents ∩ 요청 agents) subset만 run_agent_rounds(topic, messages, agents=subset, parallel_rounds>=2)로 재호출(성공 peer를 이번-턴 컨텍스트로) → retried reply를 `retry_of_turn=<human_turn_num>` 메타로 append-only 저장 → _turn_status_from_replies로 원본 턴 status/failed/succeeded 재계산해 단일 필드 patch_run_meta 갱신 + retry_history append. human_turn_num 불변. 이미 성공한 에이전트 skip(멱등).
2. `app/server/routers/room.py`: POST /api/room/runs/retry-agents {session_id, agents?} — try_begin_run/preflight 재사용; 세션 없음 404; 마지막 턴 partial 아님 409; consensus/verified 턴 422; SSE/result로 retried reply + 갱신 status 반환.

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] partial 턴(cursor 성공·codex 실패)에서 retry → codex만 재호출, cursor 재호출 0.
- [ ] 재시도 payload에 Human 메시지 + 성공 peer(cursor) reply가 이번-턴 컨텍스트로 포함.
- [ ] retried reply가 retry_of_turn=<n>로 append, human_turn_num 불변, 기존 reply 불변.
- [ ] 성공 시 원본 턴 status partial→completed(단일 필드 갱신, 마감 레코드 구조 무변경).
- [ ] 멱등: 동일 retry 재호출 시 이미 성공한 에이전트 no-op(중복 append 0).
- [ ] consensus/verified 턴 retry 422; run-lock·기존 /room/runs 회귀 불변.

## Test Plan
- Unit: failed_agents 식별; consensus 턴 거부(422); turn_status 재계산(partial→completed); 멱등 skip.
- Mock integration: partial 턴 fixture → retry-agents → 실패분만 재호출 + 성공 보존 + status 전이 + human_turn 불변 + 컨텍스트에 성공 peer 포함; 멱등 재호출 no-op; release-lock/기존 run 회귀.
- 레인: test-fast(unit) + test-integration(엔드포인트/병합).

## Non-Goals
consensus/verified 턴 부분 재시도, UI 재설계, run-lock 정책 변경, 전체 턴 재실행 경로 제거.

## Risks
- R1 중복/이중계상 → append-only + retry_history 멱등 + human_turn_num 불변 테스트.
- R2 컨텍스트 blank → 성공 peer 포함 단언 테스트.
- R3 consensus 의미론 충돌 → 422 거부.
- R4 run-lock 경합 → try_begin_run/end_run 재사용.
- R5 마감 레코드 손상 → 재오픈 안 함, status 1필드만 patch.

## 상태: PENDING APPROVAL — 실행은 별도 승인 필요. 자동 실행/위임 없음.
