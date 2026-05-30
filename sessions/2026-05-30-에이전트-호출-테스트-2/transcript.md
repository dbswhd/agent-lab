# Room transcript

**Topic:** 에이전트 호출 테스트


## Human

에이전트 호출 테스트

## Cursor

Human이 "에이전트 호출 테스트"만 던진 첫 턴이라, 레포 기준으로 **어디를 치면 되는지**부터 짚을게요. 방금 `GET /api/agents` 확인했는데 API(8765) 살아 있고 cursor/codex/claude 전부 `ready: true`입니다.

호출 경로는 UI `RoomChat.tsx` → `POST /api/room/runs`(SSE) → `room.py`의 `call_one_agent()` → `agents/registry.py`의 `call_agent()` → 각 `*_agent.respond()`예요. 성공 기준은 SSE에서 `agent_start` → (`agent_activity`, cursor만) → `agent_done`이 오고, `sessions/<id>/chat.jsonl`에 agent 라인이 쌓이는 것.

**지금 Human이 이 채팅에서 보고 있는 건** 이미 cursor 1회 호출이 된 상태라, 1차 스모크는 PASS에 가깝습니다. 다음은 **3에이전트 병렬 1라운드**를 한 번 더 돌려서 codex/claude까지 같은 경로로 도는지 보면 됩니다. UI에서 discuss · agent_rounds=1 · cursor+codex+claude 선택 후 전송, 또는 API만 치려면 `scripts/smoke_envelope_run.py`를 topic만 `"에이전트 호출 테스트"`로 바꿔 consensus 없이 `agent_rounds=1`, `consensus_mode=false`로 POST하면 됩니다.

LLM 없이 컨텍스트만 보고 싶으면 `POST /api/room/context-preview` — `preview_agent_payload()`까지 가고 `call_agent`는 안 탑니다. Cursor SDK activity 스트림은 `cursor_agent.respond()`의 `on_activity` → `agent_activity` SSE → `RoomChat` typing bubble 쪽이에요.

**실패하면 볼 파일**
- `agent_error` / system `[Cursor error]` → `.env`의 `CURSOR_API_KEY`, `pip install -e ".[cursor]"` (cursor-sdk)
- codex/claude → `GET /api/health`의 `codex_cli` / `claude_cli`
- run lock → `a run is already in progress`면 이전 run이 안 끝난 것

**[PROPOSED: 이번 테스트 PASS 조건]** discuss 1라운드에서 ready 3에이전트 각각 `agent_done` 1건 + `chat.jsonl` agent 3줄. envelope/consensus/plan execute는 이번 토픽 범위 밖.

Human이 UI로 보낼지, curl/스크립트로 칠지만 정해주시면 그 경로에 맞춰 체크 포인트만 더 좁혀 드릴게요.
