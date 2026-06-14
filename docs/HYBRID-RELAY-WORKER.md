# Hybrid relay — Cloudflare Worker (예시)

로컬 PC가 꺼져 있거나 mission daemon이 offline일 때, Agent Lab은 **직접 Telegram push를 못** 보냅니다.  
Phase 5 **hybrid relay**는 그때 이벤트를 **클라우드 URL**로 POST하고, Worker가 Telegram Bot API로 Human에게 알립니다.

```
PC (agent-lab)                    Cloudflare Worker              Telegram
     |  POST relay_url                  |                          |
     |  X-Agent-Lab-Signature           |  sendMessage             |
     +--------------------------------->+------------------------->+
        (daemon_offline 일 때만)
```

Execute / merge / worktree는 **여전히 로컬만** — Worker는 **notify relay** 전용입니다.

---

## 1. Agent Lab 쪽 설정

`~/.agent-lab/gateway.toml`:

```toml
[hybrid]
enabled = true
relay_when = "daemon_offline"
relay_url = "https://agent-lab-hybrid-relay.<your-subdomain>.workers.dev"
relay_secret = "같은-값을-Worker에도-넣기"
timeout_s = 8
```

`relay_secret`은 Worker `RELAY_SECRET`과 **동일**해야 합니다.  
서명 형식: `X-Agent-Lab-Signature: sha256=<hmac-sha256-hex>` (본문 raw JSON bytes).

로컬 daemon online 판정: `AGENT_LAB_DAEMON_STALE_S` (기본 180초) — `src/agent_lab/gateway/hybrid_relay.py`.

예시 전체: [`docs/examples/gateway.toml`](./examples/gateway.toml)

---

## 2. Worker 배포

파일:

| 파일 | 역할 |
|------|------|
| [`docs/examples/hybrid-relay-worker.js`](./examples/hybrid-relay-worker.js) | POST 수신 → HMAC 검증 → Telegram push |
| [`docs/examples/hybrid-relay-worker.wrangler.toml`](./examples/hybrid-relay-worker.wrangler.toml) | Wrangler deploy 설정 |

```bash
cd docs/examples
npx wrangler deploy --config hybrid-relay-worker.wrangler.toml

npx wrangler secret put RELAY_SECRET
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_IDS   # 예: 123456789
```

배포 후 나온 `*.workers.dev` URL을 `relay_url`에 넣습니다.

---

## 3. POST body (Agent Lab → Worker)

```json
{
  "event": "inbox_pending",
  "ts": "2026-06-14T12:00:00+00:00",
  "payload": {
    "session_id": "my-session",
    "item": {
      "id": "inbox-abc",
      "kind": "question",
      "prompt": "Pick scope?"
    }
  },
  "source": "agent-lab-hybrid-relay",
  "daemon_online": false
}
```

지원 이벤트: `inbox_pending`, `merge_ready`, `schedule_tick`, `gate_blocked`, `test_ping`.

---

## 4. 로컬에서 relay 테스트

daemon을 끈 상태(또는 `daemon_state.json` 없음)에서:

```bash
curl -X POST "$RELAY_URL" \
  -H "Content-Type: application/json" \
  -H "X-Agent-Lab-Signature: sha256=<hmac>" \
  -d '{"event":"test_ping","ts":"2026-06-14T00:00:00+00:00","payload":{"message":"hello"},"source":"agent-lab-hybrid-relay","daemon_online":false}'
```

Agent Lab 내부 경로: `fan_out_gateway_notify()` → `maybe_deliver_hybrid_relay()` (`tests/test_mission_os_phase5.py`).

---

## 5. VPS 대안

Worker 대신 VPS에서 같은 contract의 작은 FastAPI/Express 핸들러를 두어도 됩니다.  
필수: POST JSON 수신, `relay_secret` HMAC 검증, Telegram `sendMessage`.

---

## 6. Cloud wake (PC → API inbound)

Hybrid relay는 **outbound-only** (PC → cloud → Telegram/Slack).  
PC가 켜져 있을 때 외부에서 scheduler tick / command를 트리거하려면:

```bash
# routes.toml에 hook 등록 후
curl -X POST "https://your-tunnel.example/api/hooks/mission-wake" \
  -H "Content-Type: application/json" \
  -d '{"text": "/status"}'

# 또는 scheduler tick (ops token 설정 시)
curl -X POST "https://127.0.0.1:8765/api/mission-scheduler/tick?force=true" \
  -H "X-Agent-Lab-Scheduler-Token: $AGENT_LAB_SCHEDULER_HOOK_TOKEN"
```

Tunnel 옵션: Cloudflare Tunnel, Tailscale, always-on Mac mini.  
보안: hook_id는 secret URL로 취급; `AGENT_LAB_SCHEDULER_HOOK_TOKEN`은 env only.

Optional Worker env: `SLACK_WEBHOOK_URL` — Telegram과 병렬 push (`hybrid-relay-worker.js`).

---

## 관련 코드

- `src/agent_lab/gateway/hybrid_relay.py` — relay POST
- `src/agent_lab/gateway/adapters.py` — `fan_out_gateway_notify`
- [MISSION-OS-DIRECTION.md](./MISSION-OS-DIRECTION.md) — Phase 5
