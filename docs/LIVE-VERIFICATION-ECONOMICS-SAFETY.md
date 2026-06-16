# Live / 수동 검증 체크리스트 — Economics(G1+G2) · Diff Safety(G6) · Tracing(G5)

> **목적.** mock 테스트(`make test-fast`)로 커버되지 않는, **실 LLM 미션**이나 **사람이 직접 눈으로
> 확인해야 하는** 검증 항목만 모았다. 코드·단위/통합 테스트는 이미 green이며(아래 "자동으로 검증된
> 것" 참고), 이 문서의 항목들은 *실제 환경에서 한 번* 돌려 동작을 확증하기 위한 것이다.
>
> **관련 구현 plan:** `~/.claude/plans/agent-lab-imperative-gadget.md`
> **대상 기능:**
> - **G1+G2 Economics** — 실제 토큰·USD 회계(`cost_ledger`) + 예산 초과 시 circuit-breaker pause
> - **G6 Diff Safety** — merge 전 diff의 secret/위험명령 스캔 → merge 차단 + auto-merge 거부
> - **G5 Tracing** — agent/tool span을 latency + 토큰/USD와 함께 `trace.jsonl`에 기록

---

## 자동으로 검증된 것 (재확인 불필요)

| 영역 | 커버 | 위치 |
|------|------|------|
| cost_ledger 누적·캐시율·예산 status | 단위 | `tests/test_cost_ledger.py` |
| Claude usage 이벤트 파싱 | 단위 | `tests/test_cost_ledger.py::test_claude_cli_emits_usage_from_result_event` |
| 예산 초과 → circuit-breaker 전이 | 통합 | `tests/test_mission_loop.py::test_maybe_advance_trips_circuit_breaker_when_budget_exceeded` |
| diff secret/danger 탐지·redaction·allowlist | 단위 | `tests/test_diff_safety.py` |
| safety_scan → merge_disabled gating | 통합 | `tests/test_merge_checks.py` |
| trace span 계층·cost 델타·flush·forward | 단위 | `tests/test_trace_recorder.py` |
| mock 룸 턴 → trace.jsonl 생성 | e2e | `tests/test_trace_recorder.py::test_run_room_writes_trace_jsonl` |
| 플래그 등록 | `make list-flags` | `AGENT_LAB_MISSION_BUDGET_USD`, `AGENT_LAB_BUDGET_WARN_PCT`, `AGENT_LAB_DIFF_SAFETY`, `AGENT_LAB_TRACE` |

**→ 아래 live 항목은 "실제 공급사 호출/실제 diff에서도 위 로직이 동작하는가"만 확인하면 된다.**

---

## 0. 공통 사전 준비

```bash
# 1) 실제 에이전트 인증 (mock 끄기 — 이 문서 전체에서 MOCK 금지)
unset AGENT_LAB_MOCK_AGENTS

# 2) Claude/Codex/Cursor 로그인 상태 확인
make dev            # API :8765 + web :5173 기동 (별도 터미널)
curl -s localhost:8765/api/agents/preflight | jq '.agents'   # ready=true 확인

# 3) 이 문서 명령은 jq 필요
command -v jq || brew install jq
```

> ⚠️ **실 LLM 호출은 과금된다.** Economics 항목은 의도적으로 소액(몇 센트)만 쓰고, 예산 cap 테스트는
> `0.01`처럼 아주 작은 값으로 즉시 트립시켜 비용을 최소화한다.

---

# Part A — G1+G2 Economics

## A1. 실제 미션이 `cost_ledger`를 채우는가  ⬜

**중요 전제:** 토큰/USD는 **스트리밍 Claude 룸 턴**에서만 캡처된다(`claude_cli._run_claude_stream` →
`on_bridge_event("usage")`). 즉 **실제 Room 대화 1턴 이상**이 있어야 채워진다. Claude는 `total_cost_usd`를
직접 보고하고, codex/cursor는 가용 시 토큰만 잡고 USD는 가격표로 환산된다.

1. 웹 UI(`localhost:5173`)에서 새 세션을 만들고 아무 주제로 **Room 턴 1회**를 실제로 돌린다.
   (또는 API: `POST /api/room/runs` multipart form — `topic`, `agents=["claude"]`, `mode=discuss`.)
2. 세션 id 확인 후 cost 확인:

```bash
SID=<세션id>
curl -s localhost:8765/api/sessions/$SID | jq '.cost'
```

**기대 결과:**
```json
{
  "ledger": {
    "by_agent": { "claude": { "calls": 1, "tokens_in": 1234, "tokens_out": 567,
                              "cache_read": 0, "usd": 0.0xx } },
    "cumulative": { "tokens_in": 1234, "tokens_out": 567, "usd": 0.0xx },
    "cache_hit_rate": 0.0,
    "updated_at_turn": 1
  },
  "budget": { "limit_usd": null, "spent_usd": 0.0xx, "over": false, "warn": false }
}
```
- [ ] `ledger.by_agent.claude.usd > 0` (Claude가 `total_cost_usd` 보고)
- [ ] `tokens_in`/`tokens_out`이 실제 값으로 채워짐
- [ ] `run.json`에도 `cost_ledger`가 영속화됨: `jq '.cost_ledger' sessions/$SID/run.json`

## A2. 캐시 효과(cache_read / cache_hit_rate)가 잡히는가  ⬜

긴 컨텍스트로 **연속 2턴 이상** 돌리면 2번째 턴부터 Claude가 캐시를 재사용한다.

```bash
curl -s localhost:8765/api/sessions/$SID | jq '.cost.ledger | {cache_read: .by_agent.claude.cache_read, cache_hit_rate}'
```
- [ ] 2턴 이후 `cache_read > 0`, `cache_hit_rate > 0` (캐시 적중 측정됨 — G2의 핵심 산출물)
- [ ] (참고) prefix가 매 턴 불안정하면 hit_rate가 낮게 나옴 → `context_bundle` 안정성 회귀 신호

## A3. `GET /api/sessions/{id}` 응답에 cost가 노출되는가  ⬜

A1에서 이미 `.cost` 필드를 확인했다면 충족. (구현: `app/server/deps.py:session_detail`)
- [ ] 응답 최상위에 `cost.ledger` + `cost.budget` 존재

## A4. 예산 초과 → mission circuit-breaker pause  ⬜ ⭐

**전제:** 예산 게이트는 **mission loop**의 `maybe_advance_mission`에서 검사된다(standalone Room이 아님).
가장 싸게 재현하는 법:

1. A1으로 `cost_ledger.cumulative.usd > 0`인 세션을 준비(예: $0.03 누적).
2. 그 세션에서 mission loop를 enable하고 **아주 작은 cap**을 건 채 advance를 한 번 친다:

```bash
SID=<누적비용 있는 세션id>

# mission loop 켜기
curl -s -X POST localhost:8765/api/sessions/$SID/mission-loop/enable | jq '.mission_loop.enabled'

# 누적($0.03) 보다 작은 cap을 걸고 advance — 단, 환경변수는 API 서버 프로세스에 적용돼야 한다.
# → make dev 를 띄운 터미널에서 서버를 내리고 아래처럼 cap을 주고 다시 띄운다:
#     AGENT_LAB_MISSION_BUDGET_USD=0.01 make dev
# 그런 다음:
curl -s -X POST localhost:8765/api/sessions/$SID/mission-loop/advance | jq '{skipped, reason, budget}'
```

**기대 결과:**
```json
{ "skipped": true, "reason": "budget_exceeded", "budget": { "limit_usd": 0.01, "spent_usd": 0.03, "over": true } }
```

3. 미션 상태가 일시정지됐는지 확인:
```bash
curl -s localhost:8765/api/sessions/$SID | jq '.run.mission_loop | {phase, circuit_breaker, circuit_breaker_reason}'
```
- [ ] `reason == "budget_exceeded"`, `skipped == true`
- [ ] `mission_loop.phase == "MISSION_PAUSED"`, `circuit_breaker == true`, `circuit_breaker_reason == "budget_exceeded"`
- [ ] human inbox에 예산 초과 알림 항목 생성: `curl -s localhost:8765/api/sessions/$SID/inbox | jq '.items[] | select(.source=="mission_circuit_break")'`
- [ ] cap을 올리고(`AGENT_LAB_MISSION_BUDGET_USD=2.00`) circuit breaker clear 후 정상 재개되는지(선택)

> 💡 cap 환경변수는 **API 서버 프로세스**가 읽으므로 `make dev` 기동 시 함께 export해야 한다.
> (`budget_status()`가 `os.getenv("AGENT_LAB_MISSION_BUDGET_USD")`를 런타임에 읽음.)

---

# Part B — G6 Diff Safety

## B1. secret 포함 diff → dry-run → merge-checks 차단  ⬜ ⭐

**핵심 전제:** 스캔은 dry-run 시점에 diff를 보고 `execution["safety_scan"]`에 캐시된다. 따라서 **에이전트가
실제로 secret을 쓴 diff**가 필요하다. 두 가지 방법:

### 방법 1 — 실제 에이전트 유도 (진짜 live)
plan에 "설정 파일에 API 키를 하드코딩하라"는 식의 액션을 넣고 execute dry-run을 돌려, 에이전트가 secret을
실제 작성하게 한 뒤 merge-checks를 본다. (비용·비결정적)

### 방법 2 — 결정적 재현 (권장, 무과금)
worktree 안에 secret을 직접 넣고 dry-run을 태운다:

```bash
SID=<plan/실행 준비된 세션id>
# (UI에서 plan 승인 → action 1개 준비된 상태)

# dry-run 실행
curl -s -X POST localhost:8765/api/sessions/$SID/execute/dry-run \
  -H 'content-type: application/json' \
  -d '{"action_index": 1}' | jq '.execution.safety_scan'
```

**기대 결과(diff에 secret이 있을 때):**
```json
{ "ok": false,
  "findings": [ { "kind":"secret", "rule":"aws_access_key", "file":"...", "line":N, "snippet":"... AKIA***", "severity":"block" } ],
  "counts": { "secret":1, "danger":0, "blocking":1 } }
```

merge-checks 게이트 확인:
```bash
curl -s localhost:8765/api/sessions/$SID/merge-checks | jq '{merge_disabled, reason: .merge_disabled_reason, diff_safety: (.checks[] | select(.id=="diff_safety"))}'
```
- [ ] `safety_scan.ok == false`, `counts.blocking >= 1`
- [ ] merge-checks의 `diff_safety` 체크가 `ok:false`
- [ ] `merge_disabled == true` (secret이 유일 차단 사유면 reason에 `diff_safety:` 포함)

## B2. auto-merge eligibility 거부 (silent 경로 차단)  ⬜ ⭐

가장 위험한 "사람이 안 보는 자동 머지"가 막히는지가 핵심.

```bash
curl -s "localhost:8765/api/sessions/$SID/auto-merge/eligibility" | jq '{eligible, reason, merge_checks_ok, merge_disabled_reason}'
```
- [ ] `eligible == false`
- [ ] `merge_checks_ok == false` (또는 reason이 diff_safety 차단을 반영)

## B3. secret 평문이 run.json/로그에 새지 않는가 (redaction)  ⬜

```bash
# 원본 secret 문자열이 run.json 어디에도 평문으로 없어야 한다
grep -c "AKIAIOSFODNN7EXAMPLE" sessions/$SID/run.json   # 0 이어야 함
jq '.executions[-1].safety_scan.findings[].snippet' sessions/$SID/run.json   # "...AKIA***" 형태만
```
- [ ] run.json에 secret 평문 **0건**, snippet은 `앞4자+***`로 마스킹됨

## B4. allow-secret 마커 / 테스트 경로 다운그레이드  ⬜

- 같은 라인에 `# agent-lab: allow-secret` 마커가 있으면 secret finding이 **나지 않아야** 한다.
- `tests/`·`fixtures/` 경로의 secret은 `severity:"warn"`으로 강등되어 **merge를 막지 않아야** 한다.
- [ ] 마커 있는 diff → `safety_scan.counts.secret == 0`
- [ ] 테스트 경로 secret → `severity:"warn"`, `safety_scan.ok == true`(blocking 0)

(이 동작 자체는 `tests/test_diff_safety.py`에서 단위로 보장되지만, 실제 dry-run 경로에서도 동일한지 1회 확인)

## B5. 플래그 off 시 스캔 비활성  ⬜

```bash
# 서버를 AGENT_LAB_DIFF_SAFETY=0 으로 재기동 후 dry-run
curl -s -X POST localhost:8765/api/sessions/$SID/execute/dry-run \
  -H 'content-type: application/json' -d '{"action_index":1}' | jq '.execution | has("safety_scan")'
```
- [ ] `AGENT_LAB_DIFF_SAFETY=0`이면 `safety_scan` 키 없음(스캔 skip), merge 게이트도 미적용
- [ ] 기본값(미설정)은 on — `make list-flags | grep DIFF_SAFETY` → `1`

---

# Part C — Tracing (G5)

> 단위/e2e 테스트(`tests/test_trace_recorder.py`)가 span 계층·cost 델타·flush·forward + mock 룸 턴이
> `trace.jsonl`을 쓰는 것까지 이미 보장한다. 아래는 **실제 LLM 턴**에서 토큰/USD/latency가 실수치로
> 붙는지만 확인한다.

## C1. 실제 턴이 span을 latency + 토큰과 함께 기록  ⬜

1. A1처럼 실제 Claude 룸 턴 1회를 돌린 세션(`$SID`)을 준비.
2. trace.jsonl 확인:

```bash
jq -c '{kind,name,round,dur_ms,status,tokens_in,tokens_out,usd}' sessions/$SID/trace.jsonl
# 또는 API:
curl -s localhost:8765/api/sessions/$SID | jq '.observability | {trace_span_count, tail: .trace_tail}'
```

**기대:** agent span(`kind:"agent"`)에 `dur_ms > 0`, `status:"ok"`, 그리고 Claude 턴이면 `tokens_in/out`·`usd`가 cost_ledger 델타로 채워짐. tool 사용 시 `kind:"tool"` span의 `parent_id`가 해당 agent span을 가리킴.
- [ ] agent span에 `dur_ms` 기록
- [ ] Claude 턴 → `tokens_out > 0`, `usd > 0` (cost_ledger 델타)
- [ ] tool span `parent_id`가 agent span_id와 일치
- [ ] `observability.trace_span_count > 0`
- [ ] `AGENT_LAB_TRACE=0`으로 재기동 시 trace.jsonl 미생성

---

## 검증 결과 기록

| 항목 | 결과 | 일시 | 비고 |
|------|------|------|------|
| A1 cost_ledger 채워짐 | ⬜ | | |
| A2 cache_hit_rate | ⬜ | | |
| A3 sessions cost 노출 | ⬜ | | |
| A4 예산 초과 pause | ⬜ | | |
| B1 secret diff 차단 | ⬜ | | |
| B2 auto-merge 거부 | ⬜ | | |
| B3 redaction | ⬜ | | |
| B4 allowlist/다운그레이드 | ⬜ | | |
| B5 플래그 off | ⬜ | | |
| C1 trace span latency/토큰 | ⬜ | | |

---

## 트러블슈팅

- **`.cost.ledger`가 null** → Room 턴이 mock으로 돌았거나(`AGENT_LAB_MOCK_AGENTS` 미해제), 스트리밍 경로가
  아니었음. UI에서 실제 Claude 턴을 돌렸는지 확인. usage는 `result` 이벤트에서만 캡처된다.
- **`usd`는 0인데 토큰만 있음** → codex/cursor 경로(USD 미보고)일 때 가격표 환산. `agent_models.MODEL_PRICE_PER_MTOK`
  단가 확인. Claude는 항상 실제 USD가 와야 정상.
- **A4 advance가 `autorun_off` 등 다른 reason** → 예산 체크는 `circuit_breaker` 직후·`autorun` 체크 직전에서
  돈다(`mission_loop.maybe_advance_mission`). cap이 서버 프로세스 env에 실제 적용됐는지(`/api/health/flags`로
  `AGENT_LAB_MISSION_BUDGET_USD` 값 확인) 점검.
- **B1 `safety_scan`이 null** → `AGENT_LAB_DIFF_SAFETY=0`이거나 dry-run이 실패. diff가 비어있으면(빈 변경)
  findings도 없음.
- **merge_disabled는 true인데 reason이 diff_safety가 아님** → 정상. 여러 체크가 동시에 실패하면 **첫 실패**가
  reason이 된다. `checks[]`에서 `id=="diff_safety"`의 `ok:false`를 직접 확인하면 됨.
