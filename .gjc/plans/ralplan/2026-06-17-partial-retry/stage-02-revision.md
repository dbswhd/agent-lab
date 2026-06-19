# RALPLAN Planner Revision — partial-retry stage 2 (Architect+Critic 반영)

stage-01에 피드백 4건 반영. 핵심: 마감 턴 재오픈을 회피하는 안전 영속성 모델로 전환. 변경분만 기재.

## 영속성 모델 — 확정 (마감 레코드 재오픈 회피)
- **chat.jsonl: append-only.** retried reply는 새 reply 라인으로 append하되 `retry_of_turn=<human_turn_num>` 메타를 달아 같은 Human 턴에 속함을 표시(새 Human 메시지 추가 0, human_turn_num 불변). 기존 성공 reply 라인은 불변.
- **run.json: 원본 턴의 turn_status 1필드만 갱신.** 마감된 턴 레코드를 재오픈해 구조를 바꾸지 않고, 해당 턴의 `status`/`failed_agents`/`succeeded_agents`만 patch_run_meta로 갱신(예: turns[-1].status 또는 동등 위치). 추가로 `retry_history`에 {turn, agent, ts} append(감사·멱등).
- turn_status **소유 위치**: 원본 턴 메타의 status 필드(단일 소스). retried reply 반영 후 _turn_status_from_replies로 재계산해 그 필드만 갱신.

## 컨텍스트 정합성 — 확정
재시도는 run_agent_rounds(topic, messages, agents=failed_subset, parallel_rounds>=2)로 호출해, 성공 peer reply가 **"이번 턴 동료 발화"**로 컨텍스트에 포함되게 한다(parallel_round>=2 경로가 peer 발화를 동일 턴 컨텍스트로 취급). 합격기준: 재시도 payload에 Human 메시지 + 성공 peer reply가 포함됨을 테스트로 단언.

## 멱등성 — 확정
retry는 **현재 failed_agents ∩ 요청 agents**만 재호출. 이미 succeeded인 에이전트는 스킵(재호출·중복 append 0). 동일 retry 두 번째 호출 시 이미 성공 전이된 에이전트는 no-op. `retry_history`로 중복 감지.

## 파일별 변경 — 확정
1. `src/agent_lab/room_retry.py` (신규): `retry_failed_agents(folder, *, agents=None, on_event, permissions)` — load_session_messages → 마지막 턴 status/ failed_agents 식별 → consensus/verified면 422 거부 → failed∩agents subset만 run_agent_rounds(parallel_rounds>=2) → retried reply를 `retry_of_turn` 메타와 함께 append-only 저장 → 원본 턴 status/failed/succeeded 1필드 갱신 + retry_history append. human_turn_num 불변.
2. `app/server/routers/room.py`: POST /api/room/runs/retry-agents {session_id, agents?} — try_begin_run/preflight 재사용; 마지막 턴이 partial 아니면 409; consensus 턴이면 422; SSE/result로 retried reply + 갱신 status.

## Acceptance Criteria 보강
- [ ] partial 턴(cursor 성공·codex 실패)에서 retry → **codex만** 재호출, cursor 재호출 0.
- [ ] 재시도 payload에 Human 메시지 + 성공 peer(cursor) reply가 이번-턴 컨텍스트로 포함(테스트 단언).
- [ ] retried reply가 `retry_of_turn=<n>`로 append, human_turn_num 불변, 기존 reply 불변.
- [ ] 성공 시 원본 턴 status partial→completed(단일 필드 갱신, 마감 레코드 구조 무변경).
- [ ] 멱등: 동일 retry 재호출 시 이미 성공한 에이전트 no-op(중복 append 0).
- [ ] consensus/verified 턴 retry 422 거부; run-lock·기존 /room/runs 회귀 불변.

## Risks 보강
- R1 중복/이중계상 → append-only + retry_history 멱등 + human_turn_num 불변 테스트.
- R5 마감 레코드 손상 → 재오픈 안 함; status 1필드만 patch.
