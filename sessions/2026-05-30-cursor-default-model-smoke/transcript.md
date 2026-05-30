# Room transcript

**Topic:** cursor default model smoke


## Human

cursor default model smoke

## Cursor

Human 토픽 `cursor default model smoke`는 **Cursor SDK에 `model="default"`가 실제로 들어가 호출되는지**만 보면 되는 좁은 스모크로 이해했습니다. `sessions/2026-05-30-cursor-default-model-smoke/`에는 아직 `topic.txt`만 있고 `chat.jsonl`이 없어서, 룸 1턴은 아직 안 돈 상태로 보입니다.

코드 경로는 이미 한 줄로 묶여 있습니다. `agent_models.py`의 `DEFAULT_CURSOR_MODEL = "default"` → `cursor_agent.respond()`의 `AgentOptions(model=…)` → UI/헬스는 `model_label()` → `GET /api/agents`의 `model: "default"`. `.env.example` 주석대로 **`auto` 문자열은 쓰지 말고** `default`만 쓰는 게 맞습니다.

**PASS 기준 (이번 스모크만):**
1. `GET /api/agents` → `cursor.ready: true`, `model: "default"`
2. discuss · `agents: ["cursor"]` · `agent_rounds: 1` · consensus 끔 · topic 그대로 1턴
3. SSE: `agent_start` → (`agent_activity` 있으면 OK) → `agent_done` (에러 없음)
4. `agent_done.context_meta.model === "default"`
5. `sessions/2026-05-30-cursor-default-model-smoke/chat.jsonl`에 `role: "agent", "agent": "cursor"` 라인 1줄

UI로 하면 왼쪽 백엔드 줄에 `Cursor default`가 보이는지 확인한 뒤, 에이전트는 Cursor만 켜고 1라운드 전송하면 됩니다. API만 치려면 `scripts/smoke_envelope_run.py`를 복사해 topic만 바꾸고 `agents: ["cursor"]`, `consensus_mode: false`, `agent_rounds: 1`로 POST하는 게 제일 빠릅니다.

실패하면 stderr/SSE `agent_error` 메시지부터 보면 됩니다. `CURSOR_API_KEY` 없음·`cursor-sdk` 미설치·`model` 값 오타(`auto` 등) 순으로 나뉩니다. 성공 후에도 회귀용으로는 `tests/`에 `model_label()`이 env 없을 때 `"default"`인지 **SDK 없이** assert 한 줄만 두면 재현 비용이 줄어듭니다. `run.json`의 `context_log[].model`까지 스크립트가 검사하게 하면 UI 없이도 PASS를 자동화할 수 있습니다.

`[PROPOSED:]` Human이 OK면 `scripts/smoke_cursor_default.py` — cursor 단독 1턴 + `context_meta.model` assert — 를 envelope 스모크와 같은 패턴으로 추가하는 정도가 범위에 맞습니다. codex/claude 3자 라운드는 **이번 토픽 범위 밖**입니다.
