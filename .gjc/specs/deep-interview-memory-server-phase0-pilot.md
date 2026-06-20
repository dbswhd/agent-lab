# Deep Interview Spec: 외부 Code-Memory MCP 서버 — Phase 0 파일럿 (§5)

## Metadata
- Interview ID: mem-pilot-0620
- Rounds: 4 (+ Round 0 topology, + Restate gate)
- Final Ambiguity Score: 5%
- Type: brownfield
- Generated: 2026-06-20
- Threshold: 0.05
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED
- Auto-Researched Rounds: []
- Auto-Answered Rounds: []
- Architect Failures: 0
- Lateral Reviews: 2 (R1 initial→progress: contrarian/simplifier/researcher; R3 progress→refined + topology merge: architect)
- Lateral Panel Failures: 0
- Refined Rounds: []
- Closure Overrides: none
- Restated Goal: 기존 MCP allowlist를 통해 Claude/Codex에만, 로컬·읽기전용 code-memory MCP 서버(결정적 mock + 결정적 로컬 text/AST 인덱스, path/line source-ref+freshness 강제, mcp_tool_contract 재사용)를 AGENT_LAB_CODE_MEMORY_MCP 플래그(기본 off, OFF-parity byte-stable) 뒤에 올려 1-2 세션 동안 에이전트가 수동 호출하게 하고(자동주입 Phase 1 연기), 레포 밖 메트릭 시트에 측정해 kill rule 기준으로 go/no-go 판정한다.

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.95 | 0.35 | 0.333 |
| Constraint Clarity | 0.95 | 0.25 | 0.238 |
| Success Criteria | 0.93 | 0.25 | 0.233 |
| Context Clarity | 0.92 | 0.15 | 0.138 |
| **Total Clarity** | | | **0.942** |
| **Ambiguity** | | | **0.058 (≈5%)** |

## Topology
4개 최상위 구성요소가 Round 0에서 확정되었고, R3에서 tool-contract가 사용자 확정으로 mcp-server에 흡수(deferred)되었습니다.

| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| MCP 서버 (read-only code-memory) | active | 로컬·읽기전용 메모리 MCP 서버, mock+실제 인덱스 듀얼모드 | 서버명/툴/스키마/모드/계약/인덱스 백엔드/freshness 전부 확정 (AC 1-6) |
| 등록/마운트 배선 | active | plugin_discovery allowlist + 프로바이더별 마운트, Claude/Codex만 | 마운트 범위·플래그·OFF-parity·세션수 확정 (AC 7-9) |
| 도구 계약/안전 가드 | deferred | mcp_tool_contract.py 재사용으로 mcp-server에 흡수 | 사용자 확정 병합(2026-06-20T08:11:00Z): 별도 구성요소 불필요, 기존 계약 직접 재사용 |
| 측정/판정 harness | active | latency·useful-hit/query·manual-reads-avoided + kill rule | 3-metric·kill rule·OFF 베이스라인·시트 위치 확정 (AC 10-13) |

## Established Facts
| # | Fact | Source Round | Disputed |
|---|------|-------------|----------|
| 1 | 서버는 플래그 전환 듀얼모드: 결정적 mock(CI) + 실제 로컬 결정적 text/AST 인덱스(path/line 근거) | R1 | no |
| 2 | 성공기준 = 3-metric(latency p50/p95, useful-hit/query, manual-reads-avoided) + kill rule + OFF 베이스라인 1세션 | R2 | no |
| 3 | Phase 0 = tool-only 수동 호출; 자동주입·injected_chars·budget_pct는 Phase 1 | R2 | no |
| 4 | 마운트 = Claude/Codex만(plugin_discovery allowlist + cursor_inbox_mcp 템플릿); Cursor 제외 | R3 | no |
| 5 | 계약 = 기존 mcp_tool_contract.py 재사용(write/execute/full-json 금지, path/start_line/end_line source-ref 필수); server에 흡수 | R3 | no |
| 6 | 실제 인덱스 = 단순 결정적 로컬 text/AST(wisdom_index 모델); .codegraph·외부MCP 아님 | R3 | no |
| 7 | 서버 = agent-lab-code-memory; 필수 code_memory_search(query,k=5,path_glob?), 선택 code_memory_status(); 모든 hit에 path/start_line/end_line/source_ref/bounded snippet/fresh | R4 | no |
| 8 | 계약 테스트 = 툴 목록 열거 + mock 응답 1건이 모든 hit에 path/start/end 갖춤 검증 | R4 | no |
| 9 | Freshness = Phase 0 AC: index가 repo_rev + 파일별 mtime_ns + size 저장, 반환 전 재-stat, stale 드롭 + stale_hit_count++ | R4 | no |
| 10 | 플래그 AGENT_LAB_CODE_MEMORY_MCP(기본 off) + AGENT_LAB_CODE_MEMORY_MODE=mock\|index; OFF시 allowlist·overlay·Codex -c args·manifest 미생성(byte-stable); runtime_flags.py 문서화 | R4 | no |
| 11 | 메트릭 시트 = /tmp/agent-lab-code-memory-pilot-metrics.md(레포·세션 context 밖); evidence/notepad 기록 금지; 베이스라인 = OFF·mock·index에 동일 3-5 task, 동일 path/range cited hit가 read 대체 시만 reads-avoided 카운트 | R4 | no |

## Trigger Metadata
| Round | Trigger | Status | Affected | Prior→New Ambiguity | Evidence |
|-------|---------|--------|----------|---------------------|----------|
| 0 | — (topology lock) | n/a | all | n/a | 4개 구성요소 확정 |
| 1 | none | clear | mcp-server/goal | 100%→59% (down) | dual-mode 목표 확정 |
| 2 | none | clear | metrics/criteria | 59%→42% (down) | go/no-go+kill rule 확정 |
| 3 | scope reduction (merge) | clear | tool-contract→mcp-server | 42%→24% (down) | 계약 흡수, 백엔드/마운트 확정 |
| 4 | none | clear | mcp-server/metrics/register-mount | 24%→5% (down) | MCP 표면·freshness·플래그·시트 확정 |

ambiguity 상승 트리거(contradiction/inconsistency/evasive/scope-expansion) 없음. R3는 사용자 확정 scope reduction(병합)으로 모호도 하락.

## Lateral Review Panel
- **R1 (initial→progress)**: contrarian + simplifier + researcher. 접힌 발견: Phase 0는 tool-only/수동 유지(자동주입은 Phase 1 경계), 명시적 go/no-go+kill 기준 필요, tool-contract 흡수, injected_chars/budget_pct Phase 1 연기, pre-pilot OFF 베이스라인, 실제 인덱스 후보(.codegraph vs 단순 로컬 vs 외부MCP).
- **R3 (progress→refined + 토폴로지 병합)**: architect. 접힌 발견: MCP 표면(agent-lab-code-memory / code_memory_search+code_memory_status + 스키마), 메트릭 시트 /tmp 레포밖, freshness=Phase 0 AC, 플래그 AGENT_LAB_CODE_MEMORY_MCP off + MODE mock|index byte-stable, 계약 테스트(툴 열거 + 모든 hit에 path/start/end).
- Panel failures: 0.

## Goal
agent-lab에 외부 code-memory를 **기본 채택하지 않고**, §5 합의대로 가치/위험을 측정만 하는 Phase 0 파일럿을 만든다: `AGENT_LAB_CODE_MEMORY_MCP` 플래그(기본 off, OFF-parity byte-stable) 뒤에서, 로컬·읽기전용 `agent-lab-code-memory` MCP 서버(결정적 mock 모드 + 결정적 로컬 text/AST 인덱스 모드, 모든 hit에 path/line source-ref와 freshness 강제, 기존 `mcp_tool_contract.py` 재사용)를 기존 plugin allowlist로 Claude/Codex에만 마운트하고(Cursor 제외), 1-2 세션 동안 에이전트가 **수동 호출**(자동 주입은 Phase 1로 연기)하며, 레포 밖 메트릭 시트에 latency·useful-hit/query·manual-reads-avoided를 OFF 베이스라인과 비교 측정해 kill rule 기준으로 go/no-go를 판정한다.

## Constraints
- 로컬 전용·읽기 전용. write/execute/full-file/full-json 도구 금지 (mcp_tool_contract.py 재사용).
- 플래그 OFF(`AGENT_LAB_CODE_MEMORY_MCP` 미설정)일 때 byte-stable: allowlist·overlay·Codex `-c mcp_servers` args·`.agent-lab/*code-memory*.json` manifest 모두 미생성, 프롬프트 바이트 불변.
- Claude/Codex만 마운트(plugin_discovery allowlist 경로). Cursor는 Phase 0 제외.
- 모든 검색 hit은 path/start_line/end_line/source_ref/bounded snippet/fresh 필수. stale hit 반환 금지.
- 자동 주입(context_bundle/wisdom_index) 및 injected_chars/budget_pct 측정은 Phase 0에서 제외 → Phase 1.
- 메트릭은 레포·세션 context 밖(`/tmp/agent-lab-code-memory-pilot-metrics.md`)에만 기록. evidence.jsonl·notepad·wisdom_index 오염 금지.
- 새 플래그는 runtime_flags.py에 문서화하고 기존 `_env_bool` + OFF-parity 관례 준수.

## Non-Goals
- 외부 메모리의 기본 채택 / 상시 활성화.
- context_bundle/wisdom_index 자동 주입 (Phase 1).
- Cursor 마운트 / 프로바이더 일반 fan-out.
- 임베딩/벡터/시맨틱/콜그래프 백엔드 (`.codegraph` 데몬·외부 MCP 포함) — Phase 0는 단순 결정적 로컬 text/AST 인덱스만.
- 별도 재사용 가능한 MCP 정책/계약 추상화 레이어 신설.
- 콘텐츠 해시·증분 file-watch·고급 무효화 (Phase 1).

## Acceptance Criteria
- [ ] AC1: 서버 `agent-lab-code-memory`가 FastMCP 패턴(inbox_mcp_server.py 류)으로 `code_memory_search(query,k=5,path_glob?)`(필수)와 `code_memory_status()`(선택)를 노출한다.
- [ ] AC2: `code_memory_search` 응답이 ok/enabled/mode/query/hit_count/stale_hit_count/hits[]/index 스키마를 따르고, 모든 hit이 path/start_line/end_line/source_ref/snippet(bounded)/score/kind/symbol/file_mtime_ns/fresh를 갖는다.
- [ ] AC3: full-file/full-json/write/execute 류 도구가 존재하지 않으며, path/start_line/end_line 중 하나라도 없는 hit은 서버·테스트가 거부한다.
- [ ] AC4: `AGENT_LAB_CODE_MEMORY_MODE=mock`에서 동일 query에 대해 결정적 고정 응답을 반환한다(CI 재현 가능).
- [ ] AC5: `AGENT_LAB_CODE_MEMORY_MODE=index`에서 로컬 text/AST 인덱스로 top-k snippet을 path/line 근거와 함께 반환한다(외부 의존성·비결정성 없음).
- [ ] AC6 (freshness): index가 repo_rev + 파일별 mtime_ns + size를 저장하고, 검색이 반환 전 각 후보를 재-stat하여 stale을 드롭하고 stale_hit_count를 증가시킨다.
- [ ] AC7: plugin_discovery allowlist + 프로바이더별 마운트로 Claude/Codex에만 서버가 노출되고 Cursor에는 노출되지 않는다.
- [ ] AC8 (OFF-parity): `AGENT_LAB_CODE_MEMORY_MCP` 미설정 시 allowlist·overlay·Codex `-c` args·manifest가 생성되지 않고 프롬프트/컨텍스트 바이트가 플래그 도입 전과 동일하다.
- [ ] AC9: 새 플래그 2종이 runtime_flags.py에 문서화된다.
- [ ] AC10: 계약 테스트가 노출 툴 목록을 열거하고, mock 응답 1건이 모든 hit에 path/start/end를 갖는지 검증한다.
- [ ] AC11: 파일럿 전 OFF 베이스라인 1세션이 동일 3-5 task로 manual read 수를 기록한다.
- [ ] AC12: 파일럿 세션이 `/tmp/agent-lab-code-memory-pilot-metrics.md`에 session/flag_state/task_id/query_count/latency(p50/p95)/useful_hits/cited_hits/manual_reads/reads_avoided/notes 행을 기록하며, evidence/notepad/wisdom_index를 변경하지 않는다.
- [ ] AC13: go/no-go 판정이 kill rule(2세션에서 task당 reads-avoided<2 OR cited-hit 재사용<30% OR correctness 개선 없이 latency +10% → 중단)로 산출된다. reads-avoided는 동일 path/range cited hit이 file read를 대체한 경우만 카운트한다.

## Deferrals
- **tool-contract 구성요소**: 사용자 확정으로 mcp-server에 흡수 — 기존 mcp_tool_contract.py 직접 재사용, 별도 모듈 불필요.
- **Phase 1로 연기**: 자동 주입(context_bundle._append_wisdom_search_block / wisdom_index provider), injected_chars·bundle budget_pct 측정, 콘텐츠 해시·증분 watch·고급 무효화, Cursor·프로바이더 일반 fan-out, 임베딩/시맨틱/콜그래프 백엔드.
- **Convergence Pacing 연기**: min-round floor / score-drop cap / confidence dampening 미도입 — 양방향 채점이 페이싱 메커니즘.
- **베이스라인 task 프롬프트의 구체 내용**: 파일럿 시작 시 대표 3-5 task를 고정하는 런타임 파라미터(선택 *방법*은 AC11/AC13에 고정).

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "mock"은 곧 순수 고정 응답이다 | mock vs 실제 인덱스 두 해석 (R1) | 듀얼모드 플래그 전환: 결정적 mock + 결정적 로컬 인덱스 |
| 파일럿이 가치 있으면 채택한다 | 무엇이 가설을 falsify하는가? (contrarian) | 명시적 kill rule + OFF 베이스라인 비교 |
| code-memory MCP가 곧 정답 비교 대상 | 개선된 lexical wisdom_index가 진짜 비교군 아닌가? (contrarian) | Phase 0는 가치/위험 측정에 한정, 채택 보류 |
| Phase 0에 4개 구성요소 모두 필요 | tool-contract는 기존 계약 재사용으로 충분 (simplifier) | mcp-server에 흡수 |
| 자동 주입까지 Phase 0 | 자동 주입이 Phase 0/1 경계를 흐림 (researcher) | tool-only 유지, 자동 주입 Phase 1 |
| 등록만 하면 안전 | 등록은 가용성일 뿐 안전 증명 아님 (researcher/architect) | 계약 테스트 + freshness AC |
| 실제 인덱스는 .codegraph로 | .codegraph는 비결정적(100ms~2.8s) | 단순 결정적 로컬 text/AST 인덱스 채택 |
| 메트릭은 기존 ledger에 기록 | evidence/notepad는 wisdom/context를 오염 | 레포 밖 /tmp 시트에만 기록 |

## Technical Context
- 선행 §5 합의: `.gjc/plans/ralplan/2026-06-19-1324-4062/stage-05-architect.md` (pilot behind flag + hard caps, never default; Phase 0 = manual deterministic-mock measurement, Phase 1 = provider behind wisdom_index + bounded injection).
- 기존 MCP substrate: `inbox_mcp_server.py`(FastMCP 내장 서버 선례), `plugin_discovery.py`(Claude/Codex MCP 발견 + per-session allowlist :326-353,380-417), `mcp_spec_export.py`(per-agent overlay :96-123), `session_plugin_runtime.py`(execute/repair 전달 :58-125), `cursor_inbox_mcp.py`(프로바이더별 마운트 템플릿), `mcp_tool_contract.py`(allowed/forbidden/required 계약 :95-160).
- 기존 메모리/컨텍스트 substrate(모두 결정적·파일기반·lexical): `wisdom_index.py`(substring/token 점수, mtime/size fingerprint :114-136), `context_bundle.py`(`_append_wisdom_search_block` R1/deep/critical, _WISDOM_BLOCK_CAP=800 :340-409), established_facts(`clarity.py` → run.json mission_loop.clarity.facts), `evidence_ledger.py`, `mission_notepad.py`.
- 플래그 관례: 모듈별 `_env_bool` + OFF-parity byte-stable(agent_roster.py AGENT_LAB_DYNAMIC_ROOM, context_bundle.py AGENT_LAB_COMMS_COMPACT, clarity.py AGENT_LAB_CLARITY_TOPOLOGY 선례), `runtime_flags.py` 중앙 문서화.
- 파일럿 스캐폴딩: 전무(AGENT_LAB_MEMORY* 없음). 체크아웃에 `.codegraph/` 데몬 아티팩트 존재하나 agent-lab 통합 0.

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| MemoryMCPServer | core domain | name, mode, tools | exposes code_memory_search/status; mounted to Claude/Codex |
| MockMode | supporting | deterministic fixed responses | mode of MemoryMCPServer (CI) |
| IndexMode | supporting | top-k, path_glob | mode of MemoryMCPServer (세션) |
| LocalTextASTIndex | core domain | repo_rev, mtime_ns, size, chunks | backs IndexMode; produces Snippet+SourceRef |
| SourceRef | core domain | path, start_line, end_line | required on every hit |
| Freshness | supporting | repo_rev, mtime_ns, size, fresh | gates SourceRef validity |
| Metric | core domain | latency, useful-hit/query, reads-avoided | recorded to metrics sheet |
| KillRule | core domain | thresholds | judges go/no-go from Metric |
| Baseline | supporting | OFF session, 3-5 tasks | comparator for Metric |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1 | 5 | 5 | - | - | N/A |
| 2 | 8 | 4 | 0 | 4 | 50% |
| 3 | 8 | 1 | 0 | 7 | 87.5% |
| 4 | 9 | 1 | 0 | 8 | 88.9% |

## Interview Transcript
<details>
<summary>Full Q&A (Round 0 + 4 rounds + Restate)</summary>

### Round 0 — Topology
**Q:** 4개 최상위 구성요소(MCP 서버 / 등록·마운트 / 도구 계약 / 측정)로 읽었는데 맞는가?
**A:** 맞음 — 4개 구성요소로 진행.

### Round 1 — mcp-server / Goal
**Q:** Phase 0 서버가 에이전트 쿼리에 무엇을 반환해야 하나? (순수 mock / 실제 로컬 인덱스 / 둘 다)
**A:** (C) 둘 다 — mock(결정적 테스트) + 실제 인덱스(세션용) 플래그 전환.
**Ambiguity:** 100%→59% (Goal 0.85, Constraints 0.4, Criteria 0.25)

### Round 2 — metrics / Success Criteria
**Q:** 1-2 세션 뒤 go/no-go를 판단할 성공/폐기 기준은? (최소 3-metric+kill rule / 가볍게 / 엄격+negative control)
**A:** (A) 최소 3-metric + kill rule + OFF 베이스라인.
**Ambiguity:** 59%→42% (Goal 0.7, Constraints 0.48, Criteria 0.6)

### Round 3 — register-mount / Constraints
**Q:** 마운트 범위 + 계약 + 실제 인덱스 백엔드 조합은?
**A:** Claude/Codex만 + 계약은 mcp_tool_contract 재사용(tool-contract를 server에 흡수) + 실제인덱스=단순 로컬 text/AST(결정적).
**Ambiguity:** 42%→24% (Goal 0.82, Constraints 0.75, Criteria 0.72)

### Round 4 — mcp-server/metrics/register-mount / Criteria+Constraints
**Q:** architect 패널이 채운 잔여 4개(서버 표면/스키마, 메트릭 시트 위치, freshness, 플래그·OFF-parity)를 전원 채택할까?
**A:** 전원 채택 — architect 권장안 그대로 스펙 확정.
**Ambiguity:** 24%→5% (Goal 0.95, Constraints 0.95, Criteria 0.93, Context 0.92)

### Restate Gate
**Q:** 한 문장 목표가 동일 결과에 도달하는가?
**A:** Yes, crystallize.

</details>
