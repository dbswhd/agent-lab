# Verify API — external agent verification service (N9)

> **SSOT** for Agent Lab's public verification surface.  
> **Related:** [GJC-ENTRY.md](./GJC-ENTRY.md) (external handoff) · [LIVE-ORACLE.md](./LIVE-ORACLE.md) · `app/server/routers/evidence_api.py` · `app/server/routers/openai_compat.py`

Agent Lab exposes Oracle verification as an HTTP service so **external agent systems** (GJC pipelines, third-party coding agents, fork consumers) can submit diffs and receive independent risk assessment + Oracle verdict before merge.

---

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/verify` | Assess diff risk + run Oracle on diff/claim |
| `GET` | `/v1/verify/status` | Service health, oracle mode, gate list |
| `POST` | `/v1/chat/completions` | OpenAI-compatible Room turn (optional path) |
| `GET` | `/v1/models` | List `agent-lab-*` models |

Base URL (dev): `http://127.0.0.1:8765`

---

## POST /v1/verify

### Request body

```json
{
  "diff": "+def helper():\n+    return 42\n",
  "touched_paths": ["src/example.py"],
  "claim": "Add helper function",
  "safety_scan": null,
  "paths_outside_expected": false,
  "needs_artifact_review": false,
  "oracle_prompt": "",
  "external_handoff": null
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `diff` | yes | Unified diff text |
| `touched_paths` | no | Paths changed (feeds diff-risk) |
| `claim` | no | Human/agent claim summary for Oracle |
| `external_handoff` | no | GJC MB-8 handoff object — see [GJC-ENTRY.md](./GJC-ENTRY.md) |
| `oracle_prompt` | no | Override Oracle prompt (live mode) |

When `external_handoff` is present and `claim` is empty, `evidence_summary` from the handoff is used as the claim.

### Response body

```json
{
  "verdict": "pass",
  "risk_level": "low",
  "risk_reasons": [],
  "oracle": {"verdict": "pass", "detail": "...", "evidence": []},
  "evidence_gates": [],
  "auto_approve_eligible": true,
  "auto_approve_reason": "eligible",
  "agentlab": {
    "service": "verify",
    "request_id": "verify-abc123",
    "oracle_mode": "mock",
    "consumer": "external"
  }
}
```

### Audit headers (N9)

Every verify response includes:

| Header | Example | Meaning |
|--------|---------|---------|
| `X-AgentLab-Service` | `verify` | Which surface answered |
| `X-AgentLab-Request-Id` | `verify-abc123` | Correlation id (matches `agentlab.request_id`) |
| `X-AgentLab-Oracle-Verdict` | `pass` / `fail` | Oracle verdict (matches body `verdict`) |
| `X-AgentLab-Oracle-Mode` | `mock` / `live` | `AGENT_LAB_ORACLE_LIVE=1` → live |
| `X-AgentLab-Risk-Level` | `low` / `medium` / `high` | Diff-risk assessment |

---

## GET /v1/verify/status

```json
{
  "ok": true,
  "oracle_mode": "mock",
  "auto_approve_threshold": "low",
  "auto_approve_timeout_sec": 300,
  "gates": ["plan_reread", "automated", "manual_merge", "adversarial", "cleanup"]
}
```

---

## POST /v1/chat/completions (OpenAI-compat)

Standard OpenAI chat completion shape. Internally runs an Agent Lab Room turn.

**Response headers:**

| Header | Notes |
|--------|-------|
| `X-AgentLab-RunId` | Session folder id |
| `X-AgentLab-Service` | `chat` |
| `X-AgentLab-Request-Id` | Per-request correlation id |
| `X-AgentLab-Oracle-Verdict` | `pending` until execute; latest execution oracle when present |
| `X-AgentLab-Oracle-Mode` | `mock` / `live` |
| `X-AgentLab-Preset` | `fast` / `supervisor` |
| `X-AgentLab-Risk-Level` | From latest execution when available |

**Response extension:** `agentlab` object on the completion JSON (`session_id`, `service`, `request_id`, `oracle_mode`, optional `oracle` snapshot).

Models: `agent-lab-fast`, `agent-lab-balanced`, `agent-lab-thorough` — see `GET /v1/models`.

---

## Reference consumer (N9)

```bash
make dev                    # terminal 1
make n9-verify-consumer     # terminal 2 — posts sample diff, prints headers + verdict

# GJC handoff path
python scripts/n9_verify_consumer.py \
  --handoff sessions/_examples/n9-gjc-handoff.json
```

Implementation: `scripts/n9_verify_consumer.py`  
Fixture handoff: `sessions/_examples/n9-gjc-handoff.json`

---

## GJC integration path

1. External GJC pipeline completes → writes MB-8 handoff JSON (`stopped_cleanly`, `changed_files`, `checks`, `evidence_summary`, `risks`).
2. Consumer posts diff + `external_handoff` to `POST /v1/verify`.
3. Agent Lab returns Oracle verdict + risk level + evidence gates — **without** requiring a full Room session.
4. Human or auto-approve policy decides merge based on `auto_approve_eligible` and org threshold (`AGENT_LAB_AUTO_APPROVE_THRESHOLD`).

For in-session handoff attach: `POST /api/sessions/{id}/executions/{exec_id}/external-handoff` — see [GJC-ENTRY.md](./GJC-ENTRY.md).

---

## Oracle modes

| Mode | Env | Behavior |
|------|-----|----------|
| **mock** | default | Heuristic: small diff → pass; large/destructive claim → fail |
| **live** | `AGENT_LAB_ORACLE_LIVE=1` | Invokes configured Oracle provider; falls back to mock on error |

See [LIVE-ORACLE.md](./LIVE-ORACLE.md) for provider setup.

---

## Tests

```bash
pytest tests/test_evidence_api.py tests/test_n9_verify_api.py -q
make n9-verify-consumer   # requires running API
```
