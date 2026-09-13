# Claim graph

## verified-claims

| claim_id | verified claim | gate outcome |
|---|---|---|
| C12 | Overstory는 2026-05-28 archive됐고 upstream는 Warren을 successor로 지목했다 | Primary README + GitHub API, root/worker independent observations, counter-search confirmed; supported |
| C6 | OpenInference masking 옵션의 기본값은 false이며 permission/HITL/handoff 표준이 없다 | Primary spec/source + independent observability/security review; supported |
| C10 | Agent Framework restore는 scheduler를 재개하고 superstep effect replay 가능성이 있어 Agent Lab restore-then-stop을 대체할 수 없다 | Primary workflow source + local invariant comparison + red team; supported |
| C9 | OpenSandbox는 policy/control layer이며 Docker alone은 hostile multi-tenant isolation을 보장하지 않는다 | Primary security/vault docs + sandbox/security review; supported |
| C13 | AutoGen·Swarm·Daytona OSS는 upstream가 각각 maintenance/successor/unmaintained 상태를 명시했다 | Primary README notices + maintenance counter-search; supported as 2026-08-06 snapshot |

## Claims

| claim_id | statement | type/risk | scope | intents | support / contradiction | independent groups | convergence / counter-search | primary backing | dependencies | status | synthesis |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | 기존 8개 외에 구현 근거가 있는 추가 OSS 후보가 존재한다 | factual/normal | shortlist | I1 | O2–O24; none stronger | 14+ | converged after 3 waves; duplicate baseline excluded | candidate repos | none | supported | §2 |
| C2 | 최종 active 판정은 repo 채택이 아니라 pattern·experiment·reference·watch로 나눠야 한다 | comparative/normal | report taxonomy | I1,I3 | O15,O18–O24; framework wholesale adoption contradicted by local SSOT | local fit + 8 refiners | converged; authority-replacement counter-search failed | local SSOT + source audits | C1 | supported | §1–2 |
| C3 | OpenHands Condensation은 raw history를 보존한 파생 view compaction pattern이다 | code/normal | context | I2,I3 | O11,O21; provenance fields incomplete | memory audit + source tests + report review | supported with bounded caveat | S1–S3 | C1 | supported | §3.1 |
| C4 | Inspect/Harbor schema는 유용하지만 native mission-journal Room Bench가 v1 권위 상태여야 한다 | design/normal | eval | I2,I3 | O7,O19 + refine_eval; whole-framework adoption contradicted by local journal | eval audit + local duplication + skeptic | converged; single-framework path rejected | S4–S7 + L2/L3 | C1,C2 | supported | §3.2 |
| C5 | Cline은 event/replay pattern source지만 approval authority로 부적합하다 | code/security-high | adapters/HITL | I2,I3 | O9,O17 + security review; no durable idempotency/expiry | IDE audit + red team + local fit | converged; direct controller adoption rejected | S8–S11 | C2 | supported | §3.3 |
| C6 | OpenInference/OTel은 redacted projection vocabulary로만 적합하다 | security-high | observability | I2,I3 | O6,O20 + security review; raw defaults contradict safe-by-default | telemetry audit + red team + local tracer audit | converged; event SSOT counter-search failed | S12–S14 | C2 | supported | §3.4 |
| C7 | Burr StateDelta는 stale-state/expected-version test pattern으로 유용하다 | code/normal | state | I2,I3 | O10 + verification economics; distributed durability not claimed | workflow audit + cost refinement | partial but sufficient for pattern-only | S15 | C2 | supported | §3.5 |
| C8 | Warren은 event provenance/inbox/salvage pattern source지만 security gates가 필요하다 | security-high | lifecycle | I2,I3 | O18,O24 + E1 + security review; absent-origin and best-effort teardown contradict unconditional adoption | GitHub root + worktree audit + red team | converged as conditional; full dependency rejected | S16–S21 | C2,C12 | supported | §3.6 |
| C9 | OpenSandbox+SWE-ReX는 phase-2 adapter contract reference이며 isolation authority가 아니다 | security-high | sandbox | I2,I3 | O3,O23 + local sandbox policy; cleanup/snapshot gaps | sandbox audit + red team + local fit | converged as conditional experiment | S22–S25 | C2 | supported | §3.7 |
| C10 | Agent Framework는 request/fingerprint/approval shape reference이며 scheduler replacement가 아니다 | safety-high | checkpoint/runtime | I2,I3 | O5,O16 + local checkpoint; restore semantics contradict invariant | framework audit + red team + local fit | converged; scheduler adoption rejected | S26,S27 | C2 | supported | §3.8 |
| C11 | Magentic-UI는 decision provenance UI reference이며 Human Inbox authority를 대체할 수 없다 | security-high | UI | I2,I3 | O8 + security review + local Inbox | UI audit + red team + local fit | converged as UI-only | S28 | C2 | supported | §3.9 |
| C12 | Overstory는 historical reference로만 남아야 한다 | dated/high | maintenance | I1,I2 | O13,O18,O24 + E1; Warren successor | GitHub API + README + worker/root | confirmed, counter-search found successor not continuation | S32 | C1 | supported | §5 |
| C13 | AutoGen·Swarm·Daytona OSS는 신규 core dependency에서 제외해야 한다 | dated/high | maintenance | I1,I2 | O3,O5,O14 + primary notices | maintenance + relevant axis workers | confirmed as dated snapshot | S33–S35 | C1 | supported | §5 |
| C14 | Chidori는 replay conformance watch source이며 exactly-once 채택 근거는 부족하다 | code/high | durability | I2,I3 | O2,O22 + security review; distributed lease evidence absent | runtime audit + red team | partial; unresolved exactly-once explicitly retained | S29–S31 | C2 | partial | §3.10,§6 |
| C15 | 실행 우선순위는 additive read-only probes부터 시작해야 한다 | recommendation/normal | roadmap | I3 | verification-economics + local duplication | cost reviewer + local fit + report skeptic | converged | synthesis sources | C3–C11 | supported | §4 |
| C16 | 외부 test suite는 실행하지 않았으므로 production readiness를 주장할 수 없다 | methodological/high | evidence scope | I2 | V1 + source audit; no execution artifacts | root verification + source skeptic | supported; explicit abstention | V1 | none | supported | §6 |

## Unresolved / refuted annex

- `C14` distributed exactly-once: unresolved. Chidori source demonstrates local lease/replay guards, not multi-host fencing or external effect exactly-once.
- Refuted: Overstory as active adoption target; GitHub archive + upstream successor won.
- Refuted: AX as implemented resume sample; current controller contains explicit TODO.
- Refuted: OpenInference, Magentic-UI, Agent Framework, or external policy engine as Human gate/event SSOT.
