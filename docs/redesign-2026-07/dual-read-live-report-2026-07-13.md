# Live supervisor dual-read report — 2026-07-13

> **판정:** provider 실행은 시작됐지만 client `curl --max-time 300`이 provider/sidecar completion 전에 끊겨 `incomplete/timeout`으로 종료됐다. 이후 조사에서 Room stream generator cancellation 경로와 서버 측 timeout persistence가 부족한 문제가 확인되어 2026-07-13에 보강했다.
> **안전 범위:** 임시 sessions root, Kimi Work 단일 provider, `synthesize=true`, `execute_inbox=0`, production enqueue 없음.

## 실행 증거

| 항목 | 결과 |
| --- | --- |
| API health preflight | `200`; Kimi Work `configured=true`, `ready=true`, `loop_ready=true` |
| Room preset | `supervisor` |
| provider | `kimi_work` live bridge |
| session | `2026-07-13-live-supervisor-dogfood-review-agent-lab-mission` |
| live stream | `live.jsonl` 약 909 KB, `agent_token` 1,765건, `agent_done` 1건 |
| client result | `curl` 300초 timeout, terminal SSE event 수신 전 종료 |
| runtime timeline | `agent_done`은 timeout 뒤 `live.jsonl`에 기록; 이후 `scribe:claude` sidecar가 추가 실행 |
| recovery | `/api/room/runs/cancel`로 child 1개 종료, run lock 해제 확인 |
| follow-up fix | `app/server/routers/room.py` stream cancellation path가 `request_cancel(session_id)`를 호출하도록 보강; `AGENT_LAB_ROOM_SERVER_TIMEOUT_SEC` opt-in timeout은 `run_timeout` SSE와 `run.json.status=partial` / `room_timeout.reason=server_timeout`을 기록; mock HTTP smoke에서 early disconnect 후 lock 해제 확인 |
| repository mutation | 없음; execute gate와 production writer를 호출하지 않음 |

실행은 다음과 같이 별도 임시 환경에서 했다.

```bash
AGENT_LAB_SESSIONS_DIR=/tmp/agent-lab-live.qdhvS7 \
AGENT_LAB_MOCK_AGENTS=0 \
AGENT_LAB_ROOM_PRESET=supervisor \
AGENT_LAB_EXECUTE_INBOX=0 \
.venv/bin/uvicorn app.server.main:app --host 127.0.0.1 --port 8765
```

그 뒤 `/api/room/runs`에 plan/review topic을 보내 실제 Kimi Work stream을 수신했다. provider payload에는 `agent_done`과 리뷰 본문이 있었으므로 provider 호출 자체는 관찰됐다. 다만 `trace.jsonl` 대조 결과 `agent_done`은 client 300초 timeout 이후에 기록됐고, 그 뒤 scribe sidecar도 실행됐다. 따라서 이 실행은 terminal event 누락 단정이 아니라 **client deadline 전에 Room turn이 닫히지 않은 timeout**으로 해석한다.

## 해석

- **live smoke는 부분 통과:** health preflight, provider auth/bridge, supervisor composition, token streaming, agent completion은 실제로 동작했다.
- **운영 완료는 실패:** client deadline 안에 terminal event·최종 run status·Human decision surface까지 닫히지 않았다. 이 결과를 parity pass나 cutover 근거로 사용할 수 없다.
- 실행 topic이 “repository changes를 실행하지 말라”고 명시했기 때문에 execute/merge/Oracle 경로는 의도적으로 시험하지 않았다.
- timeout 뒤 명시적 cancel은 run lock과 child를 정상 회수했다. 후속 fix 후 mock HTTP smoke에서도 early disconnect 뒤 `run-lock locked=false`, `active_workers=0`, 생성 세션 `status=cancelled`를 확인했다. 추가로 direct route regression에서 server timeout이 `request_cancel(session_id)`를 호출하고 terminal SSE를 `partial/cancelled`로 닫으며 `run.json`에 `room_timeout`을 남기는 것을 확인했다. 임시 sessions root는 production sessions와 분리됐다.

provider가 반환한 리뷰의 핵심도 확인했다. 현재 `MissionRepository`/`MissionApplication`은 production phase transition writer에 연결되어 있지 않고, 실제 전이는 여전히 `run.json` writer가 소유한다. 따라서 이번 실행은 **실제 provider smoke**이지, production dual-write나 live dual-read parity 증거가 아니다.

## 다음 blocker

1. 실제 Kimi Work provider로 early client disconnect와 `AGENT_LAB_ROOM_SERVER_TIMEOUT_SEC` timeout을 다시 재현해 child termination latency, lock release, persisted partial state를 측정한다.
2. provider/sidecar별 deadline 기본값을 정한다. 현재 서버 timeout은 opt-in safety valve이며 기본값 `0`(disabled)이다.
3. 짧은 deterministic topic으로 재현한 뒤에만 Human Inbox pause/resume와 execute→merge→Oracle live scenario를 순차 검증한다.

## Live server-timeout 재측정 — 2026-07-13

첫 실측에서 `run_timeout(status=partial)` 직후 worker의 cancellation completion이 `complete.status=cancelled`와 `run.json.status=cancelled`를 덮어쓰는 race를 확인했다. `app/server/routers/room.py`에서 timeout terminal event를 보호하고 worker 종료 후 partial metadata를 재영속화하도록 보강한 뒤 동일한 실제 Kimi Work 경로를 재실행했다.

| 항목 | 관찰값 |
| --- | --- |
| 격리 sessions root | `/tmp/agent-lab-live-timeout-guaPhZ` |
| timeout guard | `AGENT_LAB_ROOM_SERVER_TIMEOUT_SEC=15` |
| API health | Kimi Work `configured=true`, `ready=true`, `loop_ready=true` |
| provider | `kimi_work:k2p6`, live bridge, `AGENT_LAB_MOCK_AGENTS=0` |
| curl duration | `18.83s`, exit `0` |
| timeout SSE | `run_timeout`, `timeout_sec=15.0`, `status=partial` |
| terminal SSE | `complete.status=partial`, `cancelled=true` |
| run.json | `status=partial`, `room_timeout.reason=server_timeout`, `timeout_sec=15.0` |
| run lock | `locked=false`, `active_workers=0` |
| trace/live | provider tool activity와 cancellation timeline 기록 |
| repository mutation | execute/merge/Oracle 호출 없음 |

이 재측정으로 timeout·partial persistence·lock recovery의 live provider 증거가 확보됐다. 다음은 provider/sidecar별 기본 deadline 정책 결정과 Human Inbox pause/resume, execute→merge→Oracle 시나리오를 별도로 검증하는 것이다. Human cutover gate는 production dual-write evidence가 남아 있어 아직 열지 않는다.
