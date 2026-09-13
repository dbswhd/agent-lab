# Agent Lab 관련 AI 에이전트 업계 동향과 슈퍼샘플

조사일: 2026-08-06  
범위: 2025 하반기~2026-08의 공식 사양, 1차 기술 글, 논문, 공개 구현  
검증: Agent Lab SSOT/코드 대조 + 공개 저장소 6개 SHA 고정 확인

## 결론

Agent Lab의 방향은 업계보다 뒤처진 것이 아니라, 오히려 핵심 축인 Human gate, 격리 실행, 검증 완료, durable state를 이미 잘 잡고 있다. 현재 가장 큰 기회는 기능을 더 붙이는 것이 아니라 **프로토콜 호환성, 세밀한 실행 관측, 대화형 평가**를 보강하는 것이다. [S1][S2]

우선순위는 다음과 같다.

1. **MCP 2026-07-28 호환성 감사**: Agent Lab은 `mcp>=1,<2`와 로컬 1.27.2를 사용해 즉시 깨지지는 않지만, Python SDK v1은 maintenance mode이고 v2가 새 stateless 사양을 구현한다. [S3][S4][S5][L1]
2. **tool-level event spine**: 현재 `RuntimeEvent`는 mission/turn/execute 전환에는 강하지만 generation, tool call, handoff, permission, subagent parentage 같은 trajectory 사건은 표준화되어 있지 않다. ACP와 AgentGUI가 이 층의 좋은 비교점이다. [S6][S7][S15][L2]
3. **Dialogue/trajectory eval**: 현재 `score_session`은 결과와 운영 KPI가 풍부하지만, 사용자의 의도를 언제 잘못 이해했는지, 어떤 tool trajectory가 실패를 만들었는지는 별도 평가하지 않는다. 최근 연구는 coding 성능과 dialogue 성능, repo exploration 성능을 분리해서 보라고 한다. [S12][S13][S14][L3]
4. **evidence-read-before-pass**: Agent Lab의 Oracle/evidence ledger를 유지하면서, Anthropic 샘플의 default-FAIL 및 “증거를 실제로 열어보기 전 PASS 금지”를 작은 회귀 규칙으로 흡수할 가치가 있다. [S16][S17]
5. **ACP probe, A2UI/MCP Apps watch**: ACP는 read-only 실험 어댑터가 적절하고, A2UI는 Decision Queue용 실험에 좋지만 v1이 아직 candidate라 코어 채택은 이르다. [S6][S8][S9]

## 1. 최근 개발 동향

### 1) MCP가 ‘툴 연결 규격’에서 agent runtime substrate로 커졌다

2026-07-28 MCP는 protocol-level handshake/session을 없앤 stateless core, per-request capability metadata, header routing, cache hints, W3C trace context, Multi Round-Trip Requests를 도입했다. Tasks, Skills over MCP, MCP Apps는 opt-in extensions가 되었다. [S3][S4]

Agent Lab에 즉시 치명적이지는 않다. 현재 의존성은 `mcp>=1.0.0,<2`이고 로컬 설치본은 1.27.2라 자동으로 v2에 올라가지 않는다. 또한 Human Inbox와 metrics MCP는 주로 stdio 서버라 HTTP stateless 변화의 직접 영향도 작다. 다만 v1은 maintenance mode이며 v2는 2026-07-28과 legacy를 dual-serve하므로, 이제는 **업그레이드 테스트 매트릭스**를 만들 시점이다. [S5][L1]

추천 감사 항목은 `ask_human` blocking semantics, legacy client negotiation, structured tool result, cancellation/progress, Codex·Claude MCP overlay export, trace propagation이다. 새 기능 구현보다 먼저 현재 계약이 v2 dual-era에서 보존되는지 확인해야 한다. [S3][S5][L4]

### 2) 프로토콜 스택이 층별로 분화했다

현재 생태계는 하나의 만능 agent protocol로 수렴하기보다 역할별로 나뉜다.

| 층 | 대표 규격 | Agent Lab 대응 |
|---|---|---|
| LLM/agent ↔ tool/context | MCP | Inbox, metrics, wisdom, plugin pass-through |
| IDE/client ↔ coding agent | ACP | Cursor/Codex/Claude provider adapter의 후보 공통 경계 |
| agent ↔ remote agent | A2A | N9 external verify/handoff의 장기 후보 |
| agent ↔ user-facing app | AG-UI | Room SSE/event surface 참고 |
| agent-generated native UI | A2UI | Decision Queue/Inbox 카드 실험 후보 |

ACP는 2026년 session list/resume/close가 안정화되고 v1.0이 공개됐지만, remote transport와 v2는 여전히 진화 중이다. 따라서 Agent Lab의 provider adapter를 곧장 교체하기보다, 한 provider의 read-only session/list 또는 event translation을 실험하는 편이 안전하다. [S6][S7]

A2A는 v1 사양에서 tasks, streaming, push notification, agent card와 인증을 포괄한다. Agent Lab은 이미 N9 verify API와 external handoff를 보유하므로, 내부 Room peer 통신을 A2A로 바꾸기보다 외부 검증 서비스가 agent card를 발행하는 좁은 실험이 맞다. [S10][S1]

### 3) 경쟁력의 중심이 harness에서 runtime·operator surface로 이동했다

OpenAI Agents SDK와 LangGraph/Deep Agents는 agent loop뿐 아니라 sessions, checkpoint/resume, HITL, tracing, guardrails, sandbox, scheduled jobs를 제품 핵심으로 다룬다. [S20][S21]

Codex, GitHub, Cursor의 최신 제품도 여러 agent를 띄우는 것보다 ‘작업 전환, 중간 steer, subagent 가시성, diff, artifact, resume’를 전면에 둔다. Agent Lab의 Mission OS 방향과 일치한다. [S22][S23]

Agent Lab의 차이는 이미 존재한다. `run.json`, worktree, execute 409, Oracle+Repair, Human Inbox를 한 lifecycle로 묶었다. 남은 갭은 UI 표면보다 **동일한 typed trajectory를 모든 provider가 내보내도록 하는 것**이다. [S1][S2][L2]

### 4) human oversight는 ‘매번 승인’에서 containment + risk dial로 이동했다

Anthropic은 반복 permission prompt가 실제 주의를 약화시킬 수 있다고 보고 sandbox, VM, egress control 같은 blast-radius containment를 강조한다. Cursor도 action risk를 문맥적으로 평가해 low-stakes는 흐르게 하고 boundary-crossing action만 느리게 하는 방식을 제시한다. [S11][S12]

이 흐름은 Agent Lab의 worktree isolation과 Autonomy Ladder를 정당화한다. 다만 classifier가 Human gate를 대체하면 안 된다. Agent Lab에서는 risk classifier를 **승인 권한자**가 아니라 `trust_budget` 조정, demotion inbox, review depth 추천에만 쓰는 것이 제품 불변과 맞다. [S1][L5]

### 5) agent eval은 최종 pass/fail에서 trajectory·dialogue·infrastructure로 분해된다

OpenAI는 2026년 SWE-bench Verified의 오염과 SWE-Bench Pro의 상당한 task-quality 문제를 공개적으로 지적했다. Anthropic은 resource budget과 time limit 차이가 agent 점수 자체를 바꾼다고 분석했다. [S13][S14]

동시에 Dialogue SWE-Bench는 더 좋은 coding model이 더 좋은 dialogue agent라는 보장이 없다고 보고하며, SWE-Explore는 repository understanding, retrieval, localization, diagnosis를 최종 해결률과 분리한다. [S15][S16]

Agent Lab에 가장 직접적인 함의는 ‘Room이 좋은 답을 냈는가’ 외에 아래를 별도 측정하라는 것이다.

- 질문이 필요한 시점에 물었는가, 불필요한 질문을 만들지 않았는가
- Human 답변이 다음 turn의 plan/action에 실제 반영됐는가
- repo 탐색이 적절한 파일·symbol·history에 닿았는가
- tool budget, wall time, model profile이 비교군에서 동일했는가
- Oracle PASS가 실제 evidence read와 연결됐는가

현재 KPI는 objection resolution, merge, partial turn, duplicate speech, decision latency 등 운영 결과에 강하므로, 이 trajectory/dialogue 축을 더하면 좋은 보완 관계가 된다. [L3]

### 6) generative UI는 chat 위의 실용 표면으로 올라왔다

MCP Apps는 sandboxed iframe과 auditable tool path로 대시보드·폼·approval workflow를 대화 안에 렌더링하는 안정 extension이다. A2UI는 실행 가능한 코드를 받지 않고 사전 승인된 native component catalog를 declarative JSON으로 조합한다. [S8][S9]

Agent Lab에서는 자유형 agent UI를 허용하기보다, `ask_human`, `propose_build`, merge checks, evidence summary처럼 이미 schema가 있는 Decision Queue 항목을 A2UI catalog로 표현하는 제한된 실험이 맞다. A2UI v1은 아직 candidate이므로 코어 contract로 고정하면 안 된다. [S9][L6]

## 2. 슈퍼샘플 랭킹

| 순위 | 샘플 | 봐야 할 것 | 흡수 판단 |
|---:|---|---|---|
| 1 | MCP 2026-07-28 + Python SDK v2 | dual-era migration, MRTR, Tasks, Apps, trace context | **즉시 호환성 감사** |
| 2 | Agent Client Protocol | session list/resume/close, permissions, tool/plan/terminal events | **작은 probe** |
| 3 | AgentGUI | trajectory breakdown, saved replay, manual/automatic steer | **Room transcript UX 참고** |
| 4 | Anthropic CWC long-running harness | default-FAIL, evidence-read gate, fresh evaluator, STEER/STOP | **검증 규칙만 흡수** |
| 5 | Open SWE | isolated sandbox, credential separation, deterministic thread id, mid-run message queue | **trigger/sandbox 경계 참고** |
| 6 | StrongDM Attractor | programmable loop spec, provider-aligned toolsets, event stream, loop detection | **runtime contract 비교표** |
| 7 | A2UI + MCP Apps | safe declarative/iframe UI, progressive enhancement | **watch/prototype** |
| 8 | OpenAI Agents SDK / Deep Agents | sessions, HITL, tracing, sandbox, durable execution | **runtime parity checklist** |

### 샘플별 주의점

- **AgentGUI**는 2026-07 공개된 매우 가까운 UX 레퍼런스지만 Hermes와 실험적 Claude 연동 중심이다. 전체 runtime을 베끼기보다 trajectory timeline, idle/tool/reasoning breakdown, saved replay를 본다. [S24]
- **CWC harness**는 제작자 스스로 demo이며 유지보수하지 않는다고 명시한다. shell hook을 복사하기보다 default-FAIL과 fresh-context evaluator 원칙만 흡수한다. [S17]
- **Open SWE**는 sandbox/trigger/credential 설계는 훌륭하지만 validation이 prompt-driven이다. Agent Lab의 Oracle과 merge gate를 대체하면 오히려 후퇴한다. [S18]
- **Attractor**는 Apache-2.0 NLSpec이고 release가 없다. 구현 dependency가 아니라 current runtime contract를 비판적으로 비교하는 체크리스트다. [S19]
- **A2UI**는 v0.9.1이 current이고 v1.0은 candidate다. 실험 표면으로는 좋지만 저장 schema/SSOT로 삼기에는 이르다. [S9]

## 3. Agent Lab 흡수 우선순위

### A0. 이번 달: 호환성·명칭 정리

1. MCP v1.27 ↔ v2 dual-era contract test를 별도 spike로 만든다.
2. 문서에서 `ACP`를 사용할 때 `Agent Communication Protocol`과 `Agent Client Protocol`을 풀네임으로 구분한다.
3. `NORTH-STAR.md`의 A2A 행은 2026 A2A v1 및 주요 SDK 지원 상태를 다시 확인한다.

이 단계는 제품 기능 추가가 아니라 미래 회귀를 줄이는 작업이다. [S3][S5][S6][S10]

### A1. 다음 실험: protocol-native event spine

provider별 activity를 공통 사건으로 번역하는 최소 vocabulary를 만든다.

`generation.start/end`, `tool.call.start/end`, `permission.request/resolved`, `handoff`, `subagent.start/end`, `artifact.created`, `steer.applied`, `usage`, `error`

이 event spine은 transcript 렌더링, evidence ledger, cost ledger, eval trajectory가 같은 원천을 공유하게 한다. ACP schema를 참고하되 Agent Lab의 mission transition SSOT를 대체하지 않는다. [S6][S7][L2]

### A1. 다음 실험: Dialogue Room Bench

기존 `sessions/_benchmark`에 10~20개의 좁은 대화 시나리오를 추가한다.

- 모호하지만 물어야 하는 요청
- 물으면 안 되는 concrete request
- Human answer 뒤 plan이 바뀌어야 하는 요청
- mid-run steer가 다음 tool round에 반영돼야 하는 요청
- BLOCK objection이 해소되기 전 execute가 열리면 안 되는 요청

점수는 final quality와 dialogue policy를 분리한다. live benchmark 이전에는 deterministic replay와 fixture로 시작한다. [S15][L3]

### A2. 검증 강화: evidence-read gate

Oracle PASS나 evidence gate 갱신이 특정 evidence artifact의 read/open event 뒤에만 일어나도록 audit rule을 둔다. 위반 시 바로 실패시키기보다 초기에는 warning/score로 관찰한다. [S17][L2]

### A2. ACP probe

Codex/Claude/Cursor 전체 cutover가 아니라 ACP registry discovery 또는 session list/read-only activity translation 하나만 feature flag 뒤에서 시험한다. 성공 기준은 adapter 코드 감소가 아니라 **이벤트 fidelity, resume 안정성, permission mapping, provider auth 유지**다. [S6][S7]

### Watch. Decision surface prototype

MCP Apps는 plugin이 제공하는 rich UI에, A2UI는 Agent Lab 자체 native Decision Queue에 각각 더 맞는다. 둘을 코어에 섞지 말고 한 개의 read-only evidence card로 비교한다. [S8][S9]

## 4. 지금 흡수하지 않을 것

- risk classifier에 merge/execute 최종 승인권 부여
- Open SWE식 prompt-driven validation으로 Oracle 대체
- 내부 Room peer를 A2A로 재구축
- A2UI payload를 run.json의 authoritative state로 저장
- ACP v2 또는 remote transport draft를 provider SSOT로 고정
- event-triggered autonomous queue를 Human Inbox 우회 경로로 추가

이 항목들은 Agent Lab의 다섯 모트 또는 현재 freeze와 충돌하거나 표준 성숙도가 부족하다. [S1][S2][S6][S9]

## 5. Sources

- [S1] [Agent Lab PROJECT](../../../.agent-lab/PROJECT.md)
- [S2] [External refs traceability](../../../docs/EXTERNAL-REFS-TRACEABILITY.md)
- [S3] [MCP 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28)
- [S4] [MCP 2026-07-28 release](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [S5] [MCP Python SDK v2 changes](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md)
- [S6] [Agent Client Protocol updates](https://agentclientprotocol.com/updates)
- [S7] [ACP repository, inspected SHA](https://github.com/agentclientprotocol/agent-client-protocol/tree/e7846aa3e3755455050b03468d07e6124618da79)
- [S8] [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview)
- [S9] [A2UI roadmap](https://a2ui.org/roadmap/)
- [S10] [A2A v1 specification](https://a2a-protocol.org/latest/specification/)
- [S11] [Anthropic: containing Claude](https://www.anthropic.com/engineering/how-we-contain-claude)
- [S12] [Cursor: governing autonomy with Auto-review](https://cursor.com/blog/agent-autonomy-auto-review)
- [S13] [OpenAI: separating signal from noise in coding evaluations](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)
- [S14] [Anthropic: infrastructure noise in agentic coding evals](https://www.anthropic.com/engineering/infrastructure-noise)
- [S15] [Dialogue SWE-Bench](https://arxiv.org/abs/2606.13995)
- [S16] [SWE-Explore](https://arxiv.org/abs/2606.07297)
- [S17] [Anthropic CWC long-running harness, inspected SHA](https://github.com/anthropics/cwc-long-running-agents/tree/ad107a974bced5244f74dd283dbf2bfd3baee3a1)
- [S18] [Open SWE, inspected SHA](https://github.com/langchain-ai/open-swe/tree/52597446e63c621c61ca919ede81313c74b0f9b6)
- [S19] [StrongDM Attractor, inspected SHA](https://github.com/strongdm/attractor/tree/fb57a55ed97372a27ac90102f436947e29f48426)
- [S20] [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [S21] [LangGraph production deep-agent runtime](https://www.langchain.com/blog/runtime-behind-production-deep-agents)
- [S22] [GitHub Agents tab and session logs](https://github.blog/changelog/2026-01-26-introducing-the-agents-tab-in-your-repository/)
- [S23] [Cursor cloud agents and QA artifacts](https://cursor.com/blog/agent-computer-use)
- [S24] [AgentGUI paper](https://arxiv.org/abs/2607.26300) and [inspected repository SHA](https://github.com/eth-medical-ai-lab/agent-gui/tree/94456371f251258ee8801292ca5c0583153af29e)

## Local evidence

- [L1] [`pyproject.toml`](../../../pyproject.toml) and local command output (`mcp 1.27.2`)
- [L2] [`core/events.py`](../../../src/agent_lab/core/events.py)
- [L3] [`session/score.py`](../../../src/agent_lab/session/score.py)
- [L4] [`session/plugin_runtime.py`](../../../src/agent_lab/session/plugin_runtime.py) and [`mcp_spec_export.py`](../../../src/agent_lab/mcp_spec_export.py)
- [L5] [`autonomy_ladder.py`](../../../src/agent_lab/autonomy_ladder.py)
- [L6] [`MCP-FIRST-INBOX.md`](../../../docs/MCP-FIRST-INBOX.md)

## 방법과 한계

- 공식 사양과 1차 기술 글을 우선하고, 구현 주장은 저장소를 shallow clone하여 SHA를 고정했다.
- vendor 생산성 수치는 독립 재현이 없어 우선순위 근거로 사용하지 않았다.
- AgentGUI 수치는 논문 저자 보고로만 취급했고 추천은 수치가 아닌 인터페이스 구조에 근거했다.
- 실제 MCP v2/ACP integration은 실행하지 않았다. 이번 산출물은 조사·비교이며 구현 spike가 아니다.
