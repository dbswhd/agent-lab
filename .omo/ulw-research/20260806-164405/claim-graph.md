# Claim graph

## verified-claims

- C1: MCP 2026-07-28 호환성 감사가 최우선이다.
- C2: ACP, AgentGUI, CWC harness, Open SWE, Attractor, A2UI가 비교 가능한 공개 슈퍼샘플이다.
- C3: tool-level event spine과 dialogue/trajectory eval이 가장 큰 비중복 제품 갭이다.

| claim_id | statement | type | risk | scope | intent ids | supporting observations | contradicting observations | independent groups | convergence | counter-search | primary source | dependencies | status | synthesis location |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | MCP 2026-07-28 호환성 감사가 최우선이다 | dated technical | high | agent-lab MCP | I1,I3 | O4,O13,O14 | none | MCP spec, SDK, local code | converged | v1 backward compatibility checked | MCP spec + Python SDK | none | supported | SYNTHESIS §1 |
| C2 | 공개 슈퍼샘플 6종은 구현을 직접 비교할 수 있다 | synthesis | normal | OSS | I2 | O7-O12 | maintenance/maturity caveats | six repos | converged | limitations checked | pinned GitHub repos | none | supported | SYNTHESIS §3 |
| C3 | tool-level event spine과 dialogue/trajectory eval이 큰 비중복 갭이다 | recommendation | normal | agent-lab | I3 | O5,O6,O15 | current KPI strengths O3 | local+papers+protocol | converged | current runtime/score searched | ACP, eval papers, local code | C1,C2 | supported | SYNTHESIS §4 |
| C4 | 업계 프로토콜은 tool, IDE-agent, agent-agent, agent-user 층으로 분화한다 | synthesis | normal | protocols | I1 | O4,O5,O16,O17 | overlap between UI protocols | four standards | converged | searched for competing scope | official specs | none | supported | SYNTHESIS §2 |
| C5 | oversight는 반복 승인보다 containment와 risk-sensitive review로 이동한다 | synthesis | normal | safety UX | I1 | O18,O19 | explicit consent remains required | Anthropic+Cursor | converged | counter: MCP consent requirement | first-party engineering posts | none | supported | SYNTHESIS §2 |
| C6 | ACP는 즉시 cutover보다 read-only/probe가 적절하다 | recommendation | normal | adapters | I3 | O5,O20 | v1 stable but v2/remote transport evolving | protocol+repo | converged | maturity and transport searched | ACP docs/changelog | C4 | supported | SYNTHESIS §4 |
