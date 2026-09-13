# Agent Lab GitHub 오픈소스 슈퍼샘플 추가 조사

Worker assignments: 30 (22 unique) · Waves: 3 · Excursions: 1 · Sources: 47 (37 GitHub primary + 10 local, 1 web domain) · Verification artifacts: 2 · Elapsed: 33 min  
조사일: 2026-08-06  
기준선: 이전 보고서의 MCP 2026, ACP, AgentGUI, CWC long-running agents, Open SWE, Attractor, A2UI/MCP Apps, OpenAI Agents SDK/Deep Agents 제외  
검증 범위: 공개 GitHub 구현·테스트·README/라이선스, GitHub REST, `git ls-remote`, Agent Lab 현재 코드/SSOT 대조  
판정 단위: 저장소 전체 채택이 아니라 **흡수할 패턴, 통합 실험, 인프라 참고, 관찰, 제외**

## 결론

추가 조사에서 가장 가치가 큰 것은 새 orchestration framework가 아니었다. Agent Lab은 이미 Human Inbox, worktree merge gate, crash recovery, append-only evidence, checkpoint restore-then-stop, 경량 trace를 갖고 있다. 따라서 외부 저장소의 전체 runtime을 들이는 것보다 다음 네 가지를 작은 패턴으로 흡수하는 편이 효과적이다. [L1][L2][L3][L4][L5]

1. **OpenHands SDK의 Condensation record**: raw event를 삭제하지 않고 `forgotten_event_ids + summary + offset`을 append하여 파생 view만 압축한다. Agent Lab의 장기 Room context에 가장 작은 실험으로 붙일 수 있다. [S1][S2][S3]
2. **Cline의 typed event/replay translator**: structured event와 legacy stream을 분리하고, tool call ID를 보존한 history replay를 제공한다. 단, approval controller는 idempotency·expiry가 없어 복제하면 안 된다. [S8][S9][S10][S11]
3. **OpenInference/OTel GenAI의 projection vocabulary**: Agent Lab event SSOT를 바꾸지 않고 외부 tracing으로 내보내는 어휘로만 쓴다. masking 기본값이 모두 false라 안전 기본 adapter가 선행돼야 한다. [S12][S13][S14]
4. **Inspect·Harbor에서 가져온 eval contract**: agent score와 infrastructure error를 분리하고 limit·sandbox·artifact를 명시한다. 다만 Room Bench v1은 이 프레임워크들 위에 만들지 말고 Agent Lab mission journal의 native deterministic fixtures로 시작한다. [S4][S5][S6][S7][L6]

`Warren`, `OpenSandbox`, `Microsoft Agent Framework`, `Magentic-UI`, `Chidori`는 좋은 참고 구현이지만 각각 authority, teardown, restore semantics, UI trust, exactly-once에서 Agent Lab 불변과 충돌하거나 미검증 영역이 있어 **조건부 실험 또는 watch**가 맞다. [S16][S17][S20][S21][S22][S24][S26][S28][S29][S30]

## 1. 선정 기준

후보는 다음 세 gate를 모두 통과해야 active shortlist에 남겼다.

| Gate | 통과 조건 | 실패 시 |
|---|---|---|
| 구현 | README가 아니라 핵심 source/test anchor가 있음 | 관찰 또는 제외 |
| 유지보수 | 2026-08-06 기준 비아카이브, 라이선스·HEAD 식별 가능 | historical/reject |
| Agent Lab fit | 기존 SSOT를 대체하지 않고 새로운 검증 가능한 가치를 더함 | pattern-only 또는 제외 |

“슈퍼샘플”은 dependency 추천과 동의어가 아니다. 이 보고서에서 `pattern source`는 코드·테스트 아이디어만 흡수하고, `integration experiment`는 feature flag/adapter 뒤의 가역적 spike, `watch`는 구현을 추적하되 도입하지 않는다는 뜻이다.

## 2. 한눈에 보는 판정

| 우선 | 후보 | 분류 | 흡수할 최소 단위 | 하지 않을 것 |
|---:|---|---|---|---|
| 1 | [OpenHands software-agent-sdk](https://github.com/OpenHands/software-agent-sdk/tree/da6f5463be9364e55db40435017549340c73bdea) | pattern source | append-only Condensation record와 replay tests | OpenHands runtime 전체 채택 |
| 2 | [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai/tree/a7523133367edde0ea2859a271b36a40de77f948) + [Harbor](https://github.com/harbor-framework/harbor/tree/4698544ea9d5ee95d01b05aeaa9ccbd161d5a7f6) | composition | native Room Bench fixture/schema와 Inspect export | Harbor/SWE-bench를 v1 권위 상태로 사용 |
| 3 | [Cline](https://github.com/cline/cline/tree/81cce3d70e10244cdde40dbd0eb0bb711c93006d) | pattern source | event union, replay translator, done dedupe | approval controller·fire-and-forget ACP 복제 |
| 4 | [OpenInference](https://github.com/Arize-ai/openinference/tree/8053d845d90ae1ad4796c7e2c5eaf807e932f5b4) + [OTel GenAI](https://github.com/open-telemetry/semantic-conventions-genai/tree/4a39b6ef1363fab57bc40e18c82abb32cc89ebcd) | integration experiment | redacted output projection | event/authorization SSOT 교체 |
| 5 | [Apache Burr](https://github.com/apache/burr/tree/a05875f09687b958bd83a5767be25d37821bee83) | pattern source | typed StateDelta, declared reads/writes | workflow runtime 채택 |
| 6 | [Warren](https://github.com/jayminwest/warren/tree/8eb58af4317c0fc91194edceddbb8f3c25570cf0) | conditional pattern | event provenance, atomic inbox claim, salvage-before-destroy | legacy origin trust·best-effort teardown 복제 |
| 7 | [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox/tree/47d85df848f957f5e7b3231e435ef9333a57537c) + [SWE-ReX](https://github.com/SWE-agent/SWE-ReX/tree/5c995c365dfb1fd5bc56fda688be5d8538f9931f) | infrastructure experiment | sandbox lifecycle/egress/credential adapter contract | Docker만으로 hostile isolation 주장 |
| 8 | [Microsoft Agent Framework](https://github.com/microsoft/agent-framework/tree/74a144085a5fd05921b473001528f3ae0725b76a) | schema/test reference | request map, graph fingerprint, approval result | scheduler·restore runtime 교체 |
| 9 | [Magentic-UI](https://github.com/microsoft/magentic-ui/tree/d3c9d13c39288257286a66daabf7c5b5fb72ee69) | UI-only reference | approve/deny/alternative + provenance 표현 | UI를 Human gate authority로 사용 |
| 10 | [Chidori](https://github.com/ThousandBirdsInc/chidori/tree/4bd624028cda6026b7040e57d94dc9c70096f46d) | watch | leased run, divergence-checked replay, paused signal | exactly-once 또는 core runtime 채택 주장 |

상위 순서는 “좋은 프로젝트”의 절대 순위가 아니라 Agent Lab에서 **작게 검증할 수 있는 순서**다. 모든 active 후보는 2026-08-06 GitHub metadata와 default-branch SHA를 재확인했으며, 활동성은 production readiness의 증명이 아니다. [V1]

## 3. 후보별 구현 근거와 흡수 경계

### 3.1 OpenHands SDK: raw history를 보존하는 context condensation

`Condensation`은 삭제 대상 event ID 집합, summary, summary insertion offset, LLM response ID를 기록한다. summary는 파생 view에 동적으로 삽입되며 원본 event tree는 남는다. fork/replay 테스트는 condensation 이후에도 raw event가 유지되고, cache rebuild 실패 시 기존 branch/cache가 보존되는 것을 확인한다. [S1][S2][S3]

Agent Lab에는 `model/version`, prompt/input hash, policy version, token usage, summary hash를 추가한 확장 record가 필요하다. 성공 기준은 “replay한 view가 deterministic하며 raw `chat.jsonl`/mission journal은 바뀌지 않음”, 중단 기준은 tool-call/tool-result pair가 분리되거나 rollback이 원본을 복원하지 못하는 경우다. 연결 seam은 mission journal과 context selection이다. [L6]

### 3.2 Inspect AI + Harbor: eval schema는 흡수하되 native Room Bench로 시작

Inspect의 sample state는 message/token/cost/time/working limit, transcript/events, sandbox, retry/error를 분리한다. Harbor는 artifact upload 실패가 발생해도 verifier reward를 보존하여 `agent_score`와 `infra_status/error`를 독립 필드로 취급한다. [S4][S5][S6][S7]

그러나 Agent Lab은 이미 sequence·schema version·idempotency를 가진 mission journal과 Human Inbox/Oracle authority를 갖는다. v1은 다음 5개 deterministic fixture를 native runner로 실행하는 편이 작고 정확하다. [L2][L3]

1. plan approve → execute → merge → Oracle PASS
2. plan reject/revise → approve
3. Oracle FAIL → repair → PASS
4. Human Inbox pause → process restart/replay → consume-once resume
5. torn-tail recovery + 동일 idempotency key 재시도

Inspect는 read-only result exporter로 먼저 붙이고, Harbor/SWE-bench는 나중의 containerized adversarial lane으로 분리한다. 외부 evaluator가 run state나 Human gate를 쓰게 해서는 안 된다.

### 3.3 Cline: event/replay contract만 가져오기

Cline은 structured `AgentEvent`가 도착하면 legacy chunk fallback을 억제하고, iteration마다 done dedupe를 초기화하며 더 완전한 terminal event를 선택한다. persisted history를 ACP update로 변환할 때 tool call ID와 completed/failed 상태를 보존하고 synthetic prompts를 걸러낸다. [S8][S9][S11]

반면 approval controller는 request-level idempotency, timeout, cancellation이 없고 global/per-request auto-approve가 가능하다. ACP forwarding은 done/error/usage를 내보내지 않고 await 없이 전송한다. [S10]

Agent Lab에는 `event_id`, monotonic sequence, `approval_request_id`, expires_at, decision idempotency key, explicit terminal/error/usage가 추가된 translator fixture만 적합하다. Human Inbox는 계속 유일한 승인 권위다. [L1][L3]

### 3.4 OpenInference + OTel GenAI: redacted projection 전용

OpenInference는 AGENT/TOOL/GUARDRAIL/EVALUATOR span과 parent/trace/session, human/LLM/code annotation을 제공하고, OTel GenAI는 `invoke_agent`/`execute_tool` 명칭을 제공한다. [S13][S14]

하지만 `HIDE_INPUTS`, `HIDE_OUTPUTS`, `HIDE_LLM_TOOLS` 등 masking 기본값이 모두 false다. permission request/decision, Human Inbox, handoff edge도 표준화하지 않는다. [S12]

따라서 기존 `trace.jsonl`과 runtime events를 canonical로 유지하고, 외부 projection에는 ID·hash·status·schema/policy version만 기본 출력한다. raw prompt, tool args/result, approval text는 명시적 opt-in이 아니면 내보내지 않는다. [L1][L5]

### 3.5 Burr: typed delta를 stale-state 회귀 경계로 사용

Burr의 `StateDelta`는 reads/writes를 선언하고 serialize/validate/apply 단계를 분리한다. [S15] Agent Lab에는 이미 mission event journal이 있으므로 Burr runtime을 들일 이유는 없다. 대신 `expected_version`, affected keys, idempotency key를 가진 typed delta test를 `run.json` projection parity와 stale-write 회귀에 적용할 수 있다. [L2]

### 3.6 Warren: lifecycle/recovery 패턴은 좋지만 conditional

Warren은 agent가 terminal authority event를 위조하지 못하도록 origin/carrier/payload를 검증하고, run inbox를 transaction 안에서 sequence 할당 후 `unread → claimed`로 원자 전환한다. plan-run coordinator와 PR gate는 restart/resume, bounded waiting, transient retry를 명시한다. push 실패 시 rescue ref/bundle을 남긴 후 workspace를 제거하는 salvage-before-destroy도 유용하다. [S16][S17][S18][S19][S20]

두 가지는 그대로 복제하면 안 된다. backward compatibility 때문에 origin이 없는 legacy event를 신뢰하며, teardown 실패가 terminalization을 막지 않아 leaked workspace가 GC까지 남을 수 있다. [S16][S21] Agent Lab은 이미 merge lease와 boot reconciliation이 있으므로 Warren 전체를 들이지 말고 `unknown origin = fail closed`, content-addressed decision/event receipt, salvage status, teardown acknowledgment test만 흡수한다. [L4][L7]

### 3.7 OpenSandbox + SWE-ReX: phase-2 sandbox contract 참고

OpenSandbox는 Docker/Kubernetes lifecycle, egress policy, Credential Vault와 gVisor/Kata/Firecracker 선택지를 제공한다. Credential Vault는 real credential을 egress sidecar에 두고 허용된 HTTPS 요청에만 header를 주입한다. 다만 DNS-only/default-allow는 우회 가능하고 service mesh와 충돌할 수 있다. [S22][S23][S24]

SWE-ReX는 Docker/Fargate/Modal backend를 같은 lifecycle interface로 감싼 작은 참고 구현이지만, credential broker, append-only audit, snapshot governance는 제공하지 않는다. [S25]

첫 spike는 실제 container가 아니라 fake adapter contract여야 한다: `create`, immutable repo attach, default-deny network, scoped credential, command stream, timeout/cancel, destroy-and-verify, audit receipt. 현재 Agent Lab의 worktree fallback과 sandbox policy를 유지한다. [L8]

### 3.8 Microsoft Agent Framework: checkpoint shape만 참고

Agent Framework는 checkpoint storage/id, pending request/response map, graph fingerprint와 concurrent-run guard를 구현한다. 그러나 restore는 scheduler를 다시 실행하며 superstep 중간 effect는 재실행될 수 있다. tool approval도 auto-approval rule로 우회 가능하다. [S26][S27]

Agent Lab에는 request correlation과 graph/schema fingerprint field만 가져오고, checkpoint restore-then-stop과 Human Inbox authority는 바꾸지 않는다. [L3][L9]

### 3.9 Magentic-UI: decision 표현만 참고

Magentic-UI의 `ApprovalDecision`은 approve/deny/alternative를, status/source는 user/auto-session/auto-policy provenance를 구분한다. [S28] 이는 Decision Queue 카드 표현에 유용하지만 message metadata는 authorization ledger가 아니다. UI는 immutable request hash에 대한 intent만 보내고 server-side Human Inbox가 actor, expiry, policy hash, decision을 기록해야 한다. [L3]

### 3.10 Chidori: replay conformance watch

Chidori는 active lease가 있는 run의 export를 거부하고 snapshot manifest로 source drift를 감지한다. persisted state는 Running/Cancelled/Paused/AwaitingApproval, pending sequence/signal을 포함하며 call replay가 function/args divergence를 검사한다. [S29][S30][S31]

다만 single-host lease와 journal replay만으로 distributed exactly-once를 증명하지 못한다. 외부 side effect는 idempotency key가 필요하다. 당장은 두 concurrent resume, crash-after-effect-before-journal, source drift, signal consume-once conformance test의 watch source다.

## 4. Agent Lab 적용 우선순위

| 순서 | 최소 실험 | 비용 | 정보 이득 | 성공 기준 | 중단 기준 |
|---:|---|---|---|---|---|
| 1 | mission journal → Inspect-compatible read-only export | S | 높음 | event 순서·schema·count 동일, source 무변경 | exporter가 state를 쓰거나 정보 손실 |
| 2 | provenance를 확장한 Condensation record | S/M | 높음 | raw event 보존, deterministic replay, context 감소 | tool pair 손상 또는 rollback 불가 |
| 3 | OpenInference redacted projection | M | 높음 | secret/raw args 미포함, IDs/hash/provenance 유지 | masking 누락 또는 schema drift silent failure |
| 4 | Burr-inspired typed StateDelta fixture | M | 높음 | stale/out-of-order write 거부, projection parity | 새로운 state authority 생성 |
| 5 | Cline-inspired provider replay fixtures | M | 중상 | tool IDs·terminal/error·sequence 보존 | fire-and-forget 또는 approval bypass 필요 |
| 6 | Warren origin/inbox/salvage conformance | M/L | 높음 | unknown origin fail-close, consume-once, teardown receipt | Human gate/merge SSOT 중복 |
| 7 | native Dialogue Room Bench 5 fixtures | M/L | 높음 | deterministic replay와 agent/infra 결과 분리 | 외부 runtime이 authoritative state가 됨 |
| 8 | OpenSandbox/SWE-ReX fake adapter contract | L | 높음 | deny-by-default·timeout·destroy 검증 | 실제 container가 contract보다 먼저 들어옴 |

가장 먼저 구현할 세 가지는 모두 read-only/additive다. 이 순서라면 새로운 runtime dependency 없이 현재 event가 충분한지, context compaction이 안전한지, telemetry가 비밀을 흘리지 않는지부터 falsify할 수 있다.

## 5. Historical·watch·제외 후보

| 후보 | 판정 | 근거 |
|---|---|---|
| Overstory | historical local-merge reference | 2026-05-28 archive, Warren으로 개발 이동; queue claim/reconciliation gap [S32] |
| AutoGen | legacy only | upstream가 maintenance mode와 Agent Framework migration을 명시 [S33] |
| OpenAI Swarm | historical/educational | upstream가 Agents SDK successor를 명시 [S34] |
| Daytona OSS | reject dependency | upstream가 2026-06 이후 OSS 비유지와 private core 이동을 명시 [S35] |
| Google AX | watch after resume implementation | controller에 incomplete execution resume TODO가 남음 [S36] |
| AutoGPT platform | legal review required | repository 내 Polyform Shield/MIT 혼합 범위 [S37] |
| Netflix Conductor | generic historical reference | agent-native contract가 아니고 조사한 HEAD가 2023-12 수준 |
| Continue | narrow MCP/context reference | process-global manager와 단일 authoritative runtime 부적합 |
| Aider | git UX reference | host repo 직접 편집, structured event/HITL authority 부재 |
| Goose | permission/stream fixture reference | permission은 sandbox가 아니며 Agent Lab gate를 대체하지 않음 |

Overstory의 1차 “좋은 merge 구현” 평가는 archive 확인 후 철회됐다. active lifecycle/recovery 참고는 Warren, local atomic merge는 Agent Lab의 기존 lease·checkpoint·reconciliation이 계속 SSOT다. [L4][L7]

## 6. 제한과 미검증 영역

- 이 문서는 기술적 OSS screen이다. SPDX metadata는 per-file license, NOTICE, trademark, dependency license를 대신하지 않는다.
- 유지보수·archive·HEAD 상태는 2026-08-06 snapshot이다. unarchived와 최근 push는 maturity나 production readiness의 증명이 아니다. [V1]
- SHA-pinned source와 tests를 읽었지만 해당 외부 프로젝트의 test suite를 실행한 것은 아니다. 실행 검증은 GitHub REST와 `git ls-remote`로 identity/HEAD/license/archive를 교차 확인한 범위다. [V1]
- Agent Lab local fit은 조사 시점 현재 worktree 기준이다. 사용자 변경을 포함할 수 있다.
- Warren legacy origin trust, OpenSandbox cleanup/isolation, Chidori distributed exactly-once, Agent Framework effect replay, OpenInference privacy defaults는 해결된 사실이 아니라 명시적 잔여 위험이다.
- GitHub 외의 시장 채택률·성능 benchmark 순위는 이번 요청 범위에 넣지 않았다.

## 7. 조사 방법과 수렴

- Wave 1: 14개 독립 축에서 runtime, harness, orchestration, sandbox, telemetry, eval, UI, IDE, workflow, memory, policy, worktree, governance, local fit 조사.
- Wave 2: 8개 구현 lead를 source/test 수준으로 재감사하고 19개 repository를 GitHub REST + `git ls-remote`로 독립 확인.
- Excursion E1: Overstory archive 발견 → upstream successor Warren 조사 → active shortlist 교체.
- Wave 3: 8개 정제 관점에서 순위, 출처, security, eval practicality, 검증 비용, local duplication, governance, claim completeness를 반대 검토.
- 수렴 이유: 모든 actionable lead를 조사·watch·historical·out-of-scope로 disposition했고, 추가 후보가 top-level 판정이나 실험 순서를 바꾸지 않았다.

세부 원장은 `claim-graph.md`, `intent-diff.md`, `observation-manifest.md`, `verification-economics.md`, `expansion-log.md`, `excursion-log.md`에 있다.

## Sources

- **OpenHands software-agent-sdk @ `da6f546…`**: [Condensation model/apply][S1], [fork/replay tests][S2], [cache rollback][S3].
- **Inspect AI @ `a752313…`**: [ActiveSample limits/state][S4], [EvalSample events/results][S5].
- **Harbor @ `4698544…`**: [reward retained across upload error][S6], [verifier result parser][S7].
- **Cline @ `81cce3d…`**: [session event bridge][S8], [dedupe tests][S9], [approval controller][S10], [history replay tests][S11].
- **OpenInference @ `8053d84…` / OTel GenAI @ `4a39b6e…`**: [masking configuration][S12], [semantic conventions][S13], [agent/tool model][S14].
- **Apache Burr @ `a05875f…`**: [StateDelta][S15].
- **Warren @ `8eb58af…`**: [event provenance][S16], [atomic inbox claim][S17], [plan-run coordinator][S18], [PR merge gate][S19], [salvage][S20], [destroy gates][S21].
- **OpenSandbox @ `47d85df…` / SWE-ReX @ `5c995c3…`**: [architecture][S22], [security policy][S23], [Credential Vault][S24], [runtime backends][S25].
- **Microsoft Agent Framework @ `74a1440…`**: [restore/run semantics][S26], [auto-approval rules][S27].
- **Magentic-UI @ `d3c9d13…`**: [approval decision model][S28].
- **Chidori @ `4bd6240…`**: [export fencing][S29], [persisted states][S30], [replay divergence][S31].
- **Historical/reject primary notices**: [Overstory archive and Warren successor][S32], [AutoGen maintenance][S33], [Swarm successor][S34], [Daytona OSS status][S35], [AX resume TODO][S36], [AutoGPT license scope][S37].
- **Agent Lab local evidence**: [runtime events][L1], [mission journal][L2], [Human Inbox][L3], [merge lease][L4], [trace recorder][L5], [session score][L6], [crash recovery][L7], [sandbox policy][L8], [checkpoint restore][L9].
- **Root verification**: [19-repository metadata/HEAD matrix and Warren follow-up][V1].

[S1]: https://github.com/OpenHands/software-agent-sdk/blob/da6f5463be9364e55db40435017549340c73bdea/openhands-sdk/openhands/sdk/event/condenser.py#L11-L96 "OpenHands Condensation model and apply"
[S2]: https://github.com/OpenHands/software-agent-sdk/blob/da6f5463be9364e55db40435017549340c73bdea/tests/sdk/conversation/local/test_conversation_tree.py#L224-L290 "OpenHands fork and replay tests"
[S3]: https://github.com/OpenHands/software-agent-sdk/blob/da6f5463be9364e55db40435017549340c73bdea/tests/sdk/conversation/test_state_view_cache.py#L219-L231 "OpenHands cache rollback test"
[S4]: https://github.com/UKGovernmentBEIS/inspect_ai/blob/a7523133367edde0ea2859a271b36a40de77f948/src/inspect_ai/log/_samples.py#L101-L185 "Inspect ActiveSample limits and state"
[S5]: https://github.com/UKGovernmentBEIS/inspect_ai/blob/a7523133367edde0ea2859a271b36a40de77f948/src/inspect_ai/log/_log.py#L395-L517 "Inspect EvalSample event and result schema"
[S6]: https://github.com/harbor-framework/harbor/blob/4698544ea9d5ee95d01b05aeaa9ccbd161d5a7f6/src/harbor/upload/uploader.py#L715-L728 "Harbor reward preserved across upload error"
[S7]: https://github.com/harbor-framework/harbor/blob/4698544ea9d5ee95d01b05aeaa9ccbd161d5a7f6/src/harbor/verifier/verifier.py#L227-L238 "Harbor verifier result parsing"
[S8]: https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/runtime/session-events.ts "Cline session event bridge"
[S9]: https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/runtime/session-events.test.ts "Cline event dedupe tests"
[S10]: https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/runtime/interactive/approvals.ts "Cline approval controller"
[S11]: https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/acp/session-load.test.ts "Cline history replay tests"
[S12]: https://github.com/Arize-ai/openinference/blob/8053d845d90ae1ad4796c7e2c5eaf807e932f5b4/spec/configuration.md#L7-L100 "OpenInference masking configuration"
[S13]: https://github.com/Arize-ai/openinference/blob/8053d845d90ae1ad4796c7e2c5eaf807e932f5b4/spec/semantic_conventions.md#L6-L57 "OpenInference semantic conventions"
[S14]: https://github.com/open-telemetry/semantic-conventions-genai/blob/4a39b6ef1363fab57bc40e18c82abb32cc89ebcd/reference/src/semconv_genai/semconv_model.py#L164-L240 "OTel GenAI agent and tool conventions"
[S15]: https://github.com/apache/burr/blob/a05875f09687b958bd83a5767be25d37821bee83/burr/core/state.py#L71-L120 "Burr StateDelta"
[S16]: https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/core/event-envelope.ts#L1-L35 "Warren event provenance"
[S17]: https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/db/repos/run-inbox.ts#L71-L132 "Warren atomic inbox claim"
[S18]: https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/plan-runs/coordinator.ts#L130-L220 "Warren plan-run coordinator"
[S19]: https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/plan-runs/merge-gate.ts#L54-L191 "Warren PR merge gate"
[S20]: https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/runtime/salvage.ts#L1-L99 "Warren salvage-before-destroy"
[S21]: https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/runs/reap/destroy.ts#L23-L100 "Warren destroy gates and best-effort failure"
[S22]: https://github.com/opensandbox-group/OpenSandbox/blob/47d85df848f957f5e7b3231e435ef9333a57537c/README.md "OpenSandbox architecture"
[S23]: https://github.com/opensandbox-group/OpenSandbox/blob/47d85df848f957f5e7b3231e435ef9333a57537c/SECURITY.md "OpenSandbox security policy"
[S24]: https://github.com/opensandbox-group/OpenSandbox/blob/47d85df848f957f5e7b3231e435ef9333a57537c/docs/guides/credential-vault.md "OpenSandbox Credential Vault"
[S25]: https://github.com/SWE-agent/SWE-ReX/blob/5c995c365dfb1fd5bc56fda688be5d8538f9931f/README.md "SWE-ReX runtime backends"
[S26]: https://github.com/microsoft/agent-framework/blob/74a144085a5fd05921b473001528f3ae0725b76a/python/packages/core/agent_framework/_workflows/_workflow.py#L625-L757 "Agent Framework restore and run semantics"
[S27]: https://github.com/microsoft/agent-framework/blob/74a144085a5fd05921b473001528f3ae0725b76a/python/packages/core/agent_framework/_skills.py#L2095-L2125 "Agent Framework auto-approval rules"
[S28]: https://github.com/microsoft/magentic-ui/blob/d3c9d13c39288257286a66daabf7c5b5fb72ee69/src/magentic_ui/approval.py#L1-L46 "Magentic-UI approval model"
[S29]: https://github.com/ThousandBirdsInc/chidori/blob/4bd624028cda6026b7040e57d94dc9c70096f46d/crates/chidori/src/export.rs#L45-L73 "Chidori export fencing"
[S30]: https://github.com/ThousandBirdsInc/chidori/blob/4bd624028cda6026b7040e57d94dc9c70096f46d/crates/chidori/src/storage.rs#L25-L72 "Chidori persisted session states"
[S31]: https://github.com/ThousandBirdsInc/chidori/blob/4bd624028cda6026b7040e57d94dc9c70096f46d/crates/chidori/src/runtime/host_core.rs#L150-L172 "Chidori replay divergence"
[S32]: https://github.com/jayminwest/overstory/blob/ff38f3f76f084abcc34f519bcaa69580f6e53cf1/README.md#L9-L11 "Overstory archive and Warren successor notice"
[S33]: https://github.com/microsoft/autogen/blob/027ecf0a379bcc1d09956d46d12d44a3ad9cee14/README.md#L180-L191 "AutoGen maintenance mode"
[S34]: https://github.com/openai/swarm/blob/6af0b4caf37dca4526dfd98e9fbd8ce36e7eeb22/README.md#L3-L8 "Swarm successor notice"
[S35]: https://github.com/daytonaio/daytona/blob/ec4c21b2d597091ac09ecc278f3bcc172575a987/README.md#L1-L6 "Daytona OSS maintenance notice"
[S36]: https://github.com/google/ax/blob/f327e23b5b842e9b700675ded9a6cdb79c505856/internal/controller/controller.go#L64-L74 "AX resume TODO"
[S37]: https://github.com/Significant-Gravitas/AutoGPT/blob/ce6ab7b074a625ce591c1f41ef17276c8093087d/LICENSE#L1-L18 "AutoGPT mixed license scope"
[V1]: /Users/yoonjong/Projects/agent-lab/.omo/ulw-research/20260806-165836/verify-github-metadata.md "GitHub API and git verification"

[L1]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/runtime/events.py "Agent Lab runtime events"
[L2]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/mission/journal.py "Agent Lab mission journal"
[L3]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/human_inbox.py "Agent Lab Human Inbox"
[L4]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/plan/execute_shared.py "Agent Lab merge lease"
[L5]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/trace_recorder.py "Agent Lab trace recorder"
[L6]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/session/score.py "Agent Lab session score"
[L7]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/crash_recovery.py "Agent Lab crash recovery"
[L8]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/sandbox_policy.py "Agent Lab sandbox policy"
[L9]: /Users/yoonjong/Projects/agent-lab/src/agent_lab/checkpoint_store.py "Agent Lab checkpoint restore"
