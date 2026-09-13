# Verification economics

S/M/L은 상대 구현+검증 비용이며 일정 추정이 아니다.

| pattern/probe | risk | error cost | cost | info gain | reversibility | dependency risk | cheapest faithful probe | decision/outcome | residual risk |
|---|---|---|---|---|---|---|---|---|---|
| Inspect-compatible event export | normal | event loss/misorder | S | high | high | low | fixture mission journal → read-only JSONL export, count/order/schema equality | verify first | external schema drift |
| OpenHands-inspired Condensation record | normal | context corruption | S/M | high | high | low/med | append record, rebuild view, assert raw events unchanged | verify second | nested condensation/tool pairing |
| OpenInference redacted projection | high | secret exfiltration | M | high | high | med | secret-labeled tool input → projected trace, raw content absent | verify third | instrumentor config compliance |
| Burr-inspired typed StateDelta | normal | stale state write | M | high | med/high | med | apply twice/out-of-order, expected-version conflict + projection parity | verify fourth | duplicate state abstraction |
| Cline-inspired event/replay translator | normal | lost terminal/tool correlation | M | med/high | high | med/high | synthetic tool/cancel/malformed stream → canonical replay | verify fifth | provider-specific drift |
| Warren origin/inbox/salvage conformance | high | authority forgery/data loss | M/L | high | med | high | unknown origin + duplicate claim + failed push salvage fixture | conditional | teardown/transport integration |
| Native Dialogue Room Bench | normal | misleading benchmark | M/L | high | med | high | five deterministic journal/kernel fixtures, agent/infra outcome split | native foundation; Inspect exporter later | fixture validity/coverage |
| OpenSandbox/SWE-ReX adapter contract | high | sandbox escape/credential leak | L | high | med/low | high | fake adapter tests deny-by-default, cancel, destroy receipt | defer live runtime | deployment/host TCB |

Deferred proofs: external project test suites were not run because the user requested comparative research, not dependency adoption or compatibility implementation. Their source/test contracts are evidence for pattern selection, not runtime certification.
