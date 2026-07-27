# Agent Lab documentation index

> **Updated:** 2026-07-15 · **Authority:** code+tests → domain canonical doc → history/reference · **Smoke:** `python scripts/smoke_room.py`

이 페이지에서 질문에 맞는 **하나의 canonical doc**을 찾는다. `archive/`로 이동된 문서는 shipped 상태 판단에 사용 금지.

---

## 질문별 빠른 찾기

| 질문 | 문서 |
|------|------|
| **지금 무엇을 해야 하나 (실행 큐 · 시한 · shipped 확인)** | [NOW.md](./NOW.md) |
| **현재 구조 · 플로우 (첫 진입점)** | [FLOW.md](./FLOW.md) |
| **Room 턴 제어 · TurnPolicy · TurnContract · safety floor** | [TURN-CONTRACT.md](./TURN-CONTRACT.md) |
| **episode · 표본 · trace · grader · T0~T2 판정** | [EVAL-CONTRACT.md](./EVAL-CONTRACT.md) |
| **중장기 방향 · 완성도 · 동결 해제 조건** | [NORTH-STAR.md](./NORTH-STAR.md) |
| **새 작업 시작용 착수 템플릿** | [WORK-TASK-KICKOFF-TEMPLATE.md](./WORK-TASK-KICKOFF-TEMPLATE.md) |
| **M4/L1 discuss-only trace 기준선 결정** | [M4-L1-DISCUSS-ONLY-TRACE-DECISION.md](./M4-L1-DISCUSS-ONLY-TRACE-DECISION.md) |
| 시스템 전체 모듈·레이어 지도 | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| Desktop packaging baseline · hybrid 전 복귀점 | [PACKAGING-BASELINE.md](./archive/legacy/PACKAGING-BASELINE.md) |
| Hybrid Rust + Python ADR (Track 1 proceed / Track 2 conditional) | [HYBRID-RUST-PYTHON-ADR.md](./HYBRID-RUST-PYTHON-ADR.md) |
| Track 2.0 profile gate report | [TRACK2-PROFILE.md](./archive/rfcs/TRACK2-PROFILE.md) |
| Track 2.2 native gate — CLOSED (native rejected, crate removed) | [TRACK2-NATIVE-GATE.md](./archive/rfcs/TRACK2-NATIVE-GATE.md) |
| **N10 User-Loop Wisdom 설계 상세 (개정 반영됨 — canonical은 NORTH-STAR §2.1 N10)** | [N10-USER-LOOP-WISDOM-DRAFT.md](./N10-USER-LOOP-WISDOM-DRAFT.md) |
| **N6 Phase 2 — Harness Self-Improvement Loop (Weng / Self-Harness / DGM 변용)** | [DESIGN-HARNESS-SELF-IMPROVE.md](./DESIGN-HARNESS-SELF-IMPROVE.md) |
| **N7 S3 도구 카드 · `[NEED-TOOL:]` · Inbox mount 설계 (구현은 S1/S2 닫힌 후)** | [S3-TOOL-CARD-SPEC.md](./S3-TOOL-CARD-SPEC.md) |
| **15분 mock 미션 · fork_time_minutes (N8)** | [QUICKSTART.md](./QUICKSTART.md) |
| **Emergence bench 프로토콜 SSOT (N8)** | [EMERGENCE-BENCH.md](./EMERGENCE-BENCH.md) · [REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md) |
| **Fork 가이드 (N8)** | [FORK.md](./FORK.md) · [PACKAGE-FORK-BOUNDARIES.md](./PACKAGE-FORK-BOUNDARIES.md) |
| **외부 검증 API (N9)** | [VERIFY-API.md](./VERIFY-API.md) · `make n9-verify-consumer` |
| **2026-07 cleanup · dogfood-first SSOT** | [CLEANUP-SSOT-2026-07.md](./CLEANUP-SSOT-2026-07.md) · [CLEANUP-PHASE0-SCOPE-2026-07.md](./archive/legacy/CLEANUP-PHASE0-SCOPE-2026-07.md) |
| Room transcript UX contract (SSE · lock · activity) | [ROOM-TRANSCRIPT-CONTRACT.md](./ROOM-TRANSCRIPT-CONTRACT.md) |
| 전략 방향 (Fugu/Harness 대비 포지션 — 배경/이력) | [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) |
| 역할 오케스트레이션 설계 (P1~P8) | [ROLE-ORCHESTRATION-PLAN.md](./ROLE-ORCHESTRATION-PLAN.md) |
| 기능·동작·API·UI 상세 | [USER-GUIDE.md](./USER-GUIDE.md) |
| **Turn preset · Plan toggle · legacy profile map** | [TURN-MODES.md](./TURN-MODES.md) |
| TurnPolicy 구현 이력 | [TURN-POLICY.md](./TURN-POLICY.md) — 현재 계약은 [TURN-CONTRACT.md](./TURN-CONTRACT.md) |
| 4과정·동적 적응 비교·구현 로그 | [archive/rfcs/WORKFLOW-DYNAMIC-REFERENCE.md](./archive/rfcs/WORKFLOW-DYNAMIC-REFERENCE.md) — history/reference |
| **Structure refactor execute waves** | [STRUCTURE-REFACTOR-WAVE.md](./STRUCTURE-REFACTOR-WAVE.md) |
| shipped / partial / future | [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) |
| Room 합의 / execute / mission 루프 | [FLOW.md](./FLOW.md) §3–7 · [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) |
| Fast preset Inbox skip (discuss vs execute) | [05-room-agent-roles.md §Fast preset](./05-room-agent-roles.md) · [FLOW.md §2.1](./FLOW.md) |
| MCP-first Inbox · 선다형 `ask_human` · harvest deprecate | [MCP-FIRST-INBOX.md](./MCP-FIRST-INBOX.md) |
| Plan FSM 플래그 상세 | [FLOW.md](./FLOW.md) §4 · `AGENT_LAB_PLAN_WORKFLOW` flag |
| 프론트 컴포넌트·IA·Work 탭 | [developer-agent-console.md](./developer-agent-console.md) · ARCHITECTURE §5–6 |
| UX productization 로드맵 | [CONSOLE-PRODUCTIZATION.md](./CONSOLE-PRODUCTIZATION.md) · [UI-IA-ROADMAP.md](./UI-IA-ROADMAP.md) |
| Gateway · scheduler · Mission OS | [MISSION-OS-DIRECTION.md](./MISSION-OS-DIRECTION.md) · OPS-RUNBOOK §daemon |
| Human Inbox · MCP | [HUMAN-INBOX.md](./HUMAN-INBOX.md) · [HUMAN-INBOX-CLAUDE-HANDOFF.md](./archive/legacy/HUMAN-INBOX-CLAUDE-HANDOFF.md) |
| Runtime harness · dispatch | [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md) · [ROOM-DISPATCH-PROTOCOL.md](./ROOM-DISPATCH-PROTOCOL.md) |
| GJC external pipeline entry | [GJC-ENTRY.md](./GJC-ENTRY.md) · [VERIFY-API.md](./VERIFY-API.md) · Work tab Pipeline stepper |
| CI · regression · live ops · daemon dogfood | [STABILITY.md](./STABILITY.md) · [OPS-RUNBOOK.md](./OPS-RUNBOOK.md) |
| Mission first-pass redesign · UI/UX · legacy audit · next steps | [redesign-2026-07/README.md](./redesign-2026-07/README.md) · [11 UI surface](./redesign-2026-07/11-ui-ux-surface-map.md) · [12 compatibility audit](./redesign-2026-07/12-compatibility-and-legacy-audit.md) · [13 governance/steps](./redesign-2026-07/13-document-governance-and-execution-plan.md) · [controlled cohort runbook](./redesign-2026-07/evidence/dual-write-controlled-cohort-runbook-2026-07-13.md) · [dual-read report](./redesign-2026-07/evidence/dual-read-report-2026-07-13.md) · [route cohort](./redesign-2026-07/evidence/dual-write-route-cohort-report-2026-07-13.md) · [seeded simulation](./redesign-2026-07/evidence/dual-read-seeded-report-2026-07-13.md) · [mock dogfood](./redesign-2026-07/evidence/dual-read-dogfood-report-2026-07-13.md) · [live timeout report](./redesign-2026-07/evidence/dual-read-live-report-2026-07-13.md) |
| Repo structure metrics · package refactors | [STRUCTURE-METRICS.md](./STRUCTURE-METRICS.md) · [STRUCTURE-REFACTOR-WAVE.md](./STRUCTURE-REFACTOR-WAVE.md) · [PROVIDER-LANE](./PROVIDER-LANE-DESIGN.md) · [archive/STRUCTURE-REFACTOR-HISTORY.md](./archive/STRUCTURE-REFACTOR-HISTORY.md) (Room/Plan/Session/Mission/Agent/Quant/Wisdom/Inbox/Context/Run/Workspace/Research — consolidated, all shipped) |
| Trading extension | [extensions/QUANT-TRADING.md](./extensions/QUANT-TRADING.md) · [trading-mission/](./trading-mission/) |

---

## Core 5 — domain canonical

| Doc | 용도 |
|-----|------|
| [NOW.md](./NOW.md) | **현재 상태** — 실행 큐, 시한, 동결, Human 결정 |
| [NORTH-STAR.md](./NORTH-STAR.md) | **장기 방향** — 5모트, D0~D4, N/F 로드맵, 해제 조건 |
| [FLOW.md](./FLOW.md) | **현재 구조·플로우** — Discuss→Plan→Execute→Verify 전체 흐름, 역할 오케스트레이션, Human gates |
| [TURN-CONTRACT.md](./TURN-CONTRACT.md) | **턴 계약** — TurnPolicy, 후보 선택, rollout, safety 권한 |
| [EVAL-CONTRACT.md](./EVAL-CONTRACT.md) | **평가 계약** — outcome 분모, 표본, trace, grader, T0~T2 |

## Tier 1 — supporting operational docs

이 문서들은 담당 기능의 상세 계약이다. 전역 상태나 다른 domain의 권위를 갖지 않는다.

| Doc | 용도 |
|-----|------|
| [WORK-TASK-KICKOFF-TEMPLATE.md](./WORK-TASK-KICKOFF-TEMPLATE.md) | **작업 착수 템플릿** — Core 5 기준으로 범위·검증·닫힘 정의 |
| [M4-L1-DISCUSS-ONLY-TRACE-DECISION.md](./M4-L1-DISCUSS-ONLY-TRACE-DECISION.md) | **설계 결정** — discuss-only fixture completeness를 올리지 않고 semantics를 유지하는 이유와 후속 옵션 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | **시스템 지도** — 백엔드 라우터, 코어 모듈, 프론트 컴포넌트, UX 플로우, 전략 포지션 §0 |
| [USER-GUIDE.md](./USER-GUIDE.md) | 제품 동작, env 플래그, Room · execute · UI 상세 |
| [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) | **shipped 여부** — 증거 경로, partial/future 큐 |
| [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) | **전략 방향** — Fugu/Harness 분석, 5개 모트, P0~P2 이니셔티브 |
| [ROLE-ORCHESTRATION-PLAN.md](./ROLE-ORCHESTRATION-PLAN.md) | **역할 오케스트레이션 설계** — P1~P8, RoleSpec, topic_router 통합, guidance seam |
| [STABILITY.md](./STABILITY.md) | 회귀 baseline, smoke, CI 기대치 |
| [OPS-RUNBOOK.md](./OPS-RUNBOOK.md) | 수동 검증 Tier A~E, live ops, **Mission daemon**, **dogfood 체크리스트** |
| [EVAL-PROGRAM.md](./EVAL-PROGRAM.md) | 라이브 dogfood 테스트 — topic 카탈로그, 주간 matrix, KPI 루프 |
| [EMERGENCE-BENCH.md](./EMERGENCE-BENCH.md) | **창발 벤치 SSOT** — topic·시드·판정·재현 체크리스트 (N8) |
| [QUICKSTART.md](./QUICKSTART.md) | **외부인 15분 경로** — mock 미션 · fork_time_minutes (N8) |
| [VERIFY-API.md](./VERIFY-API.md) | **외부 검증 API (N9)** — `/v1/verify` · audit headers · GJC consumer |
| [FORK.md](./FORK.md) | Fork·upstream 동기화·안전 커스터마이즈 (N8) |
| [PACKAGE-FORK-BOUNDARIES.md](./PACKAGE-FORK-BOUNDARIES.md) | 분리 fork 패키지 경계 (N8) |
| [ABSORB-CC-CODEX-2026-07.md](./ABSORB-CC-CODEX-2026-07.md) | **Claude Code·Codex 패턴 흡수 SSOT** — absorb/replace/reject 매트릭스, NORTH-STAR §2.5·분기 리뷰 ②가 참조 |
| [CLAUDE.md](../CLAUDE.md) | 레포 개발 퀵스타트 (root) |

**규칙:** runtime 사실은 code+tests가 우선한다. `NOW`는 상태, `NORTH-STAR`는 방향, `FLOW`는 구조, `TURN-CONTRACT`는 턴, `EVAL-CONTRACT`는 평가만 소유한다.

---

## Tier 2 — Feature RFCs (shipped + 활성 backlog)

| Doc | 상태 (2026-06) |
|-----|----------------|
| [HOOK-COMMUNICATE-REFORM.md](./HOOK-COMMUNICATE-REFORM.md) | Phase 0–5 **shipped** incl. `LEGACY_ENDORSE` default off |
| [MISSION-OS-DIRECTION.md](./MISSION-OS-DIRECTION.md) | **Mission OS SSOT** — gate_profile, Human Gates 1–5, Gateway 로드맵 |
| [HUMAN-INBOX.md](./HUMAN-INBOX.md) | Execute MCP + API **shipped**; M1~M6 완료 |
| [MCP-FIRST-INBOX.md](./MCP-FIRST-INBOX.md) | **MCP-first 방향** — agent MCP SSOT, harvest 축소, Scribe/plan 분리; Phase A **shipped**, B–E **planned** |
| [LIVE-ORACLE.md](./LIVE-ORACLE.md) | Oracle prompts, evidence, env 플래그 (mock-first default) |
| [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) | **Shipped** — Layer 6 FSM + Track B/C/D |
| [MISSION-BOARD-ADOPTION.md](./MISSION-BOARD-ADOPTION.md) | **Shipped** — Mission Board MB-9…MB-11 (P1~P4); P5 backlog |
| [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md) | **H0–H7 shipped** — runtime contract, dispatch lanes, PolicyEngine |
| [GJC-ENTRY.md](./GJC-ENTRY.md) | **GJC external entry** — Room vs gjc, tools.yaml, Work pipeline stepper |
| [PLUGIN-DISCOVERY.md](./PLUGIN-DISCOVERY.md) | Slash commands + plugins **shipped** |
| [NOTIFICATION-TAXONOMY.md](./NOTIFICATION-TAXONOMY.md) | Toast / Activity notification 분류 |
| [ROOM-DISPATCH-PROTOCOL.md](./ROOM-DISPATCH-PROTOCOL.md) | DELEGATE / parallel dispatch protocol **shipped** |
| [MCP-TOOL-CONTRACT.md](./MCP-TOOL-CONTRACT.md) | Inbox / session plugin MCP 계약 |
| [HYBRID-RELAY-WORKER.md](./HYBRID-RELAY-WORKER.md) | Cloudflare hybrid relay worker 배포 |
| [F5-TRADING-ISOLATION.md](./F5-TRADING-ISOLATION.md) | NORTH-STAR F5 — **decided**; trading extension lane, core PR trading delta 0 |
| [F7-REPO-MAP-COMPACTION-DOGFOOD.md](./F7-REPO-MAP-COMPACTION-DOGFOOD.md) | NORTH-STAR F7 — 7일 dogfood **진행 중**, 마감 2026-07-16 (`make f7-dogfood-report`) |
| [F8-COST-VISIBILITY.md](./F8-COST-VISIBILITY.md) | NORTH-STAR F8 — **instrumented**, quarter cost ledger + L0 demotion |
| [DESIGN-HARNESS-SELF-IMPROVE.md](./DESIGN-HARNESS-SELF-IMPROVE.md) | N6 전용 approved feature spec; HS 작업 시만 참조 |

### History / research (현재 상태 판단에 사용 금지 — `archive/`로 이동됨)

| Doc | 보존 이유 |
|-----|-----------|
| [archive/rfcs/WORKFLOW-DYNAMIC-REFERENCE.md](./archive/rfcs/WORKFLOW-DYNAMIC-REFERENCE.md) | 4과정·동적 적응 비교와 TurnContract 도입 이력 |
| [archive/rfcs/EVAL-SURFACE-SUPER-SAMPLE-PLAN.md](./archive/rfcs/EVAL-SURFACE-SUPER-SAMPLE-PLAN.md) | eval surface 구현 완료 계획; 정의는 EVAL-CONTRACT로 이동 |
| [archive/rfcs/EVAL-SURFACE-V1-PLAN.md](./archive/rfcs/EVAL-SURFACE-V1-PLAN.md) | v1 local eval harness 구현 완료 history; 정의는 EVAL-CONTRACT로 이동 |
| [archive/rfcs/DESIGN-S1-FEEDBACK-LOOP.md](./archive/rfcs/DESIGN-S1-FEEDBACK-LOOP.md) | S1 내부 피드백 루프 Phase A~D + S1.5 구현 완료 (2026-06-26) |
| [archive/rfcs/S1.5-LANE-CONNECTOR-ADR.md](./archive/rfcs/S1.5-LANE-CONNECTOR-ADR.md) | S1.5 execute lane connector 제안(2026-06) — 채택되지 않음, `s2_role_bandit.py` subset 힌트로 대체 구현 |
| [archive/legacy/REVIEW-LINER-RESEARCH-2026-07.md](./archive/legacy/REVIEW-LINER-RESEARCH-2026-07.md) | HSIL 승인에 반영된 연구 검토 스냅샷 |

### Extensions & trading

| Doc | 역할 |
|-----|------|
| [extensions/QUANT-TRADING.md](./extensions/QUANT-TRADING.md) | Quant trading extension 개요 |
| [trading-mission/THIN-RUNTIME.md](./trading-mission/THIN-RUNTIME.md) | Trading 씬 런타임 |
| [trading-mission/OFFLINE-LANE.md](./trading-mission/OFFLINE-LANE.md) | Offline lane |
| [trading-mission/SCHEDULER.md](./trading-mission/SCHEDULER.md) | Trading 스케줄러 |

---

## Tier 3 — UI (cosmetic / IA, 백엔드 비블로킹)

| Doc | 비고 |
|-----|------|
| [CONSOLE-PRODUCTIZATION.md](./CONSOLE-PRODUCTIZATION.md) | Productization SSOT: IA P0, Hooks/Response P1, verification P2 |
| [UI-IA-ROADMAP.md](./UI-IA-ROADMAP.md) | Deprecate list + target IA (P0~P4 대부분 ✅) |
| [developer-agent-console.md](./developer-agent-console.md) | 현재 콘솔 UI 레퍼런스 — 3-pane 레이아웃, **Work 탭 stepper** |
| [DESIGN.md](./DESIGN.md) | 프론트 비주얼 설계 원칙 (canonical: `web/DESIGN.md`) |

**규칙:** UI contract 테스트 실패 시 현재 컴포넌트에 맞게 테스트를 수정 (프로토타입 네이밍으로 되돌리지 않음).

---

## Tier 4 — 아카이브 (shipped 상태 판단에 사용 금지)

| 경로 | 내용 |
|------|------|
| `archive/legacy/` | 00~05 초기 가이드, SPRINT-D-CHECKLIST, UI-MIGRATION-GAPS (모든 갭 종료), WORK-TAB-IA (→ developer-agent-console), MISSION-OS-OPS (→ OPS-RUNBOOK), MISSION-DOGFOOD (→ OPS-RUNBOOK), 세션 노트, HUMAN-INBOX-CLAUDE-HANDOFF (M3+ handoff, → HUMAN-INBOX.md), UI-HANDOFF-TEAM-AGENTS (Sprint A-D 완료, IA는 DESIGN.md 참고), DESIGN-SYSTEM (→ `web/DESIGN.md`), CLEANUP-PHASE0-SCOPE-2026-07 (→ CLEANUP-SSOT-2026-07), PACKAGING-BASELINE (pre-hybrid-rust rollback point, hybrid 완료) 등 |
| `archive/rfcs/` | 완료 RFC — EXECUTE-WORKTREE-REFORM, ROOM-REINFORCEMENT, GJC-WORKFLOW-PIPELINE, AGENT-OS-MODE-SIMPLIFICATION-PLAN, PLAN-WORKFLOW (→ FLOW §4), GOAL-LOOP (legacy opt-in), EXTERNAL-REFS-PLAN (→ TRACEABILITY), TRACK2-NATIVE-GATE + TRACK2-PROFILE (Rust native 시도 CLOSED, → HYBRID-RUST-PYTHON-ADR.md) |
| `archive/` | 핸드오프 감사 문서, [STRUCTURE-REFACTOR-HISTORY.md](./archive/STRUCTURE-REFACTOR-HISTORY.md) (13개 package refactor 문서 통합, 전부 shipped) |

### Root & `.hermes/` (레포 외부)

| Doc | 역할 | 비고 |
|-----|------|------|
| [../README.md](../README.md) | 프로젝트 개요, 퀵스타트 | |
| [../CLAUDE.md](../CLAUDE.md) | Dev 퀵스타트 | Tier 1 canonical |
| [../AGENTS.md](../AGENTS.md) | 코딩 컨벤션 | |
| `../.agent-lab/PROJECT.md` | Workspace project memory | Runtime-injected, 설계 문서 아님 |

---

## Tier 5 — 저작 가이드 & live ops 런북

| Doc | 역할 |
|-----|------|
| [MD-WRITING-PLAN.md](./MD-WRITING-PLAN.md) | PROJECT.md, CLAUDE.md, skills 작성 방법 |
| [UI-SKILLS.md](./UI-SKILLS.md) | UI craft agent skill 설치·사용 가이드 (`npx skills add`) — CLAUDE.md CC-skills가 참조 |
| [LIVE-CURSOR-WORKTREE-DRY-RUN.md](./LIVE-CURSOR-WORKTREE-DRY-RUN.md) | Tier B — live dry-run 운영 가이드 |
| [LIVE-MERGE-OPERATOR.md](./LIVE-MERGE-OPERATOR.md) | Tier C — live merge 운영 가이드 |
| [LIVE-VERIFICATION-ECONOMICS-SAFETY.md](./LIVE-VERIFICATION-ECONOMICS-SAFETY.md) | launch 전 체크리스트 — cost_ledger · diff 안전 스캔 · judge |
| [TUNNEL-LAUNCHD-SOAK-RUNBOOK.md](./TUNNEL-LAUNCHD-SOAK-RUNBOOK.md) | Tier E — launchd + tunnel soak 상세 운영 절차 |
| [LC-L4-ADVERSARIAL-LIVE.md](./LC-L4-ADVERSARIAL-LIVE.md) | Live adversarial gate opt-in 절차 |
| [APP.md](./APP.md) | 앱 패키징·배포 노트 |
| [apple-kit-specs.md](./apple-kit-specs.md) | macOS 비주얼 스펙 |

---

## Quick commands

```bash
make dev                          # API(:8765) + web(:5173)
make test-fast                    # pytest ~2130 tests (~1–2분)
make test                         # full pytest (not live)
make verify-hooks                 # Hook · Communicate suite
make ci                           # test + smoke + score fixtures
python scripts/smoke_room.py      # 37 regression baselines
make list-flags                   # AGENT_LAB_* 플래그 레지스트리
make mission-dogfood-run          # Mission loop mock dogfood
make mission-dogfood-weekly       # 주간 KPI rollup
```
