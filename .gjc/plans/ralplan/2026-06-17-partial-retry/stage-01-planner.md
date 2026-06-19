# RALPLAN Planner — partial-turn 실패 에이전트 부분 재시도 (stage 1, short mode)

원천: 사용자 마찰 "여러 에이전트 중 하나 실패하면 그 하나만 재시도가 안 되고 전체를 다시 돌려야 한다". 진단(read-only): turn_status="partial"은 room_messages._turn_status_from_replies(failed and succeeded), turn_partial SSE가 failed_agents/succeeded_agents 방출, run.json 턴 메타에 persist. 그러나 run_room/continue_room_round는 항상 전체 선택 에이전트를 run_agent_rounds/run_parallel_round로 실행 — 같은 Human 턴에 실패분만 재호출하는 경로 없음. run_agent_rounds(topic, messages, agents=...)는 agents subset을 받음(재사용 가능). messages(chat.jsonl 로드)에 Human 메시지 + 성공 reply가 이미 있어 재시도 에이전트가 올바른 컨텍스트(Human msg + 성공 peer)를 봄.

## Principles
1. 같은 Human 턴 보존: 재시도는 새 Human 메시지/턴을 만들지 않음(human_turn_num 증가 금지) — 턴 응집성 유지.
2. 성공 reply 불변: 이미 성공한 에이전트 reply는 재호출/덮어쓰기 금지, 보존.
3. 기존 인프라 재사용: run_agent_rounds(agents=subset)·run-lock·preflight·patch_run_meta 재사용, 새 오케스트레이션 로직 최소.
4. 비파괴·범위 한정: 1차는 비-consensus discuss/team 턴에 한정; consensus 라운드(anchor/endorse 의미)는 후속.

## Decision Drivers (top 3)
1. 사용자 실측 마찰 — 부분 실패 시 전체 재실행 비용(토큰·시간) 큼.
2. 턴 응집성/중복 방지 — chat.jsonl·run.json 병합이 중복·이중계상 없이.
3. 기존 turn 의미론(consensus/verified)과 충돌 회피.

## Viable Options
**A — 전용 retry 경로 + 엔드포인트. [CHOSEN]** `retry_failed_agents(folder, *, agents=None, on_event, permissions)` 신규(room_turn_flow 또는 신규 room_retry.py): 마지막 턴 메타에서 failed_agents 식별 → run_agent_rounds(messages, agents=failed_subset, parallel_rounds=1)로 실패분만 1라운드 → 성공 reply 보존한 채 retried reply append → turn_status 재계산(partial→completed) → patch_run_meta로 현재 턴 메타 갱신(failed/succeeded/status). 새 엔드포인트 POST /api/room/runs/retry-agents {session_id, agents?}.
- Pro: 깨끗한 분리, 887줄 continue_room_round 무수정, agents subset 재사용. Con: 신규 경로/엔드포인트.

**B — continue_room_round에 retry_failed 플래그.** 기존 함수에 분기 추가(새 Human 턴 스킵 + agent subset).
- Pro: 엔드포인트 1개 재사용. Con: 887줄 함수에 턴-의미론 분기 추가 — 회귀 표면·복잡도 큼.

**C — 프론트엔드 재전송(실패 에이전트만 선택).** 기존 /room/runs를 failed agents만으로 재호출.
- Pro: 백엔드 변경 0. Con: 새 Human 턴 생성 + Human 메시지 중복 → 턴 응집성 파괴(사용자 마찰 미해결), 성공 reply가 이전 턴에 고립.

**Invalidation:** C는 새 턴/중복 메시지로 "같은 턴 부분 재시도" 요구 미충족. B는 핵심 함수 오염·회귀 위험. → **A 채택**(consensus 턴 retry는 후속 범위).

## Chosen Approach — 파일별 변경
1. `src/agent_lab/room_retry.py` (신규) 또는 room_turn_flow에 `retry_failed_agents(...)`: (a) load_session_messages로 현재 메시지 로드, (b) 마지막 턴 메타/turn_status에서 failed_agents 결정(인자 agents로 부분 지정 가능, 미지정 시 전체 failed), (c) consensus/verified 턴이면 거부(422, "consensus turn retry not supported yet"), (d) run_agent_rounds(topic, messages, agents=failed_subset, parallel_rounds=1, ...)로 실패분만, (e) 성공 reply 보존+retried reply append, (f) _write_session_files/save로 chat.jsonl append(중복 없이) + patch_run_meta로 현재 턴의 failed_agents/succeeded_agents/turn_status 재계산, human_turn_num 불변.
2. `app/server/routers/room.py`: POST /api/room/runs/retry-agents {session_id, agents?} — run-lock(try_begin_run)·preflight 재사용, SSE/result로 retried replies + 갱신된 turn_status 반환. session 없으면 404, 마지막 턴이 partial 아니면 409/422.

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] partial 턴(예: cursor 성공·codex 실패)에서 retry-agents 호출 시 **codex만** 재호출(cursor 재호출 0).
- [ ] 재시도 에이전트가 Human 메시지 + 성공 peer reply 컨텍스트를 받음.
- [ ] 성공 reply 보존(덮어쓰기/중복 0), retried reply가 같은 Human 턴에 append(human_turn_num 불변).
- [ ] 재시도 성공 시 turn_status partial→completed, run.json failed/succeeded 갱신.
- [ ] consensus/verified 턴 retry는 명시적 거부(미지원, 후속).
- [ ] run-lock·preflight·기존 /room/runs 동작 불변(회귀).

## Test Plan
- Unit: failed_agents 식별; consensus 턴 거부; turn_status 재계산(partial→completed).
- Mock integration: partial 턴 fixture → retry-agents → 실패분만 재호출 + 성공 보존 + status 전이 + Human 턴 불변; release-lock/기존 run 회귀.

## Non-Goals
consensus/verified 턴 부분 재시도(후속), UI 재설계, run-lock 정책 변경, 전체 턴 재실행 제거(기존 경로 유지).

## Risks + Mitigations
- R1 chat.jsonl/run.json 중복·이중계상 → append-only 병합 + human_turn_num 불변 + 멱등 테스트.
- R2 재시도 컨텍스트 오류(blank turn) → messages에 Human+성공 peer 포함됨을 단언하는 테스트.
- R3 consensus 의미론 충돌 → 1차에서 consensus 턴 명시 거부.
- R4 run-lock 경합 → 기존 try_begin_run/end_run 재사용.
