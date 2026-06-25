# Agent Lab documentation index

> **Updated:** 2026-06-26 · **Tests:** `pytest -m "not live"` · **Smoke:** `python scripts/smoke_room.py` · **Hook/communicate:** `make verify-hooks`

이 페이지에서 질문에 맞는 **하나의 canonical doc**을 찾는다. `archive/`로 이동된 문서는 shipped 상태 판단에 사용 금지.

---

## 질문별 빠른 찾기

| 질문 | 문서 |
|------|------|
| **현재 구조 · 플로우 (첫 진입점)** | [FLOW.md](./FLOW.md) |
| 시스템 전체 모듈·레이어 지도 | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| 전략 방향 (Fugu/Harness 대비 포지션) | [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) |
| 역할 오케스트레이션 설계 (P1~P8) | [ROLE-ORCHESTRATION-PLAN.md](./ROLE-ORCHESTRATION-PLAN.md) |
| 기능·동작·API·UI 상세 | [USER-GUIDE.md](./USER-GUIDE.md) |
| shipped / partial / future | [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) |
| Room 합의 / execute / mission 루프 | [FLOW.md](./FLOW.md) §3–7 · [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) |
| Plan FSM 플래그 상세 | [FLOW.md](./FLOW.md) §4 · `AGENT_LAB_PLAN_WORKFLOW` flag |
| 프론트 컴포넌트·IA·Work 탭 | [developer-agent-console.md](./developer-agent-console.md) · ARCHITECTURE §5–6 |
| UX productization 로드맵 | [CONSOLE-PRODUCTIZATION.md](./CONSOLE-PRODUCTIZATION.md) · [UI-IA-ROADMAP.md](./UI-IA-ROADMAP.md) |
| Gateway · scheduler · Mission OS | [MISSION-OS-DIRECTION.md](./MISSION-OS-DIRECTION.md) · OPS-RUNBOOK §daemon |
| Human Inbox · MCP | [HUMAN-INBOX.md](./HUMAN-INBOX.md) · [HUMAN-INBOX-CLAUDE-HANDOFF.md](./HUMAN-INBOX-CLAUDE-HANDOFF.md) |
| Runtime harness · dispatch | [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md) · [ROOM-DISPATCH-PROTOCOL.md](./ROOM-DISPATCH-PROTOCOL.md) |
| CI · regression · live ops · daemon dogfood | [STABILITY.md](./STABILITY.md) · [OPS-RUNBOOK.md](./OPS-RUNBOOK.md) |
| Trading extension | [extensions/QUANT-TRADING.md](./extensions/QUANT-TRADING.md) · [trading-mission/](./trading-mission/) |

---

## Tier 1 — Canonical (매일 참조, plan vs code)

| Doc | 용도 |
|-----|------|
| [FLOW.md](./FLOW.md) | **현재 구조·플로우** — Discuss→Plan→Execute→Verify 전체 흐름, 역할 오케스트레이션, Human gates |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | **시스템 지도** — 백엔드 라우터, 코어 모듈, 프론트 컴포넌트, UX 플로우, 전략 포지션 §0 |
| [USER-GUIDE.md](./USER-GUIDE.md) | 제품 동작, env 플래그, Room · execute · UI 상세 |
| [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) | **shipped 여부** — 증거 경로, partial/future 큐 |
| [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) | **전략 방향** — Fugu/Harness 분석, 5개 모트, P0~P2 이니셔티브 |
| [ROLE-ORCHESTRATION-PLAN.md](./ROLE-ORCHESTRATION-PLAN.md) | **역할 오케스트레이션 설계** — P1~P8, RoleSpec, topic_router 통합, guidance seam |
| [STABILITY.md](./STABILITY.md) | 회귀 baseline, smoke, CI 기대치 |
| [OPS-RUNBOOK.md](./OPS-RUNBOOK.md) | 수동 검증 Tier A~E, live ops, **Mission daemon**, **dogfood 체크리스트** |
| [EVAL-PROGRAM.md](./EVAL-PROGRAM.md) | 라이브 dogfood 테스트 — topic 카탈로그, 주간 matrix, KPI 루프 |
| [CLAUDE.md](../CLAUDE.md) | 레포 개발 퀵스타트 (root) |

**규칙:** 두 문서가 충돌하면 **TRACEABILITY + code + tests**가 우선.

---

## Tier 2 — Feature RFCs (shipped + 활성 backlog)

| Doc | 상태 (2026-06) |
|-----|----------------|
| [HOOK-COMMUNICATE-REFORM.md](./HOOK-COMMUNICATE-REFORM.md) | Phase 0–5 **shipped** incl. `LEGACY_ENDORSE` default off |
| [MISSION-OS-DIRECTION.md](./MISSION-OS-DIRECTION.md) | **Mission OS SSOT** — gate_profile, Human Gates 1–5, Gateway 로드맵 |
| [HUMAN-INBOX.md](./HUMAN-INBOX.md) | Execute MCP + API **shipped**; M1~M6 완료 |
| [HUMAN-INBOX-CLAUDE-HANDOFF.md](./HUMAN-INBOX-CLAUDE-HANDOFF.md) | Inbox handoff 노트 (M3+) — 구현 단계별 AC |
| [LIVE-ORACLE.md](./LIVE-ORACLE.md) | Oracle prompts, evidence, env 플래그 (mock-first default) |
| [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) | **Shipped** — Layer 6 FSM + Track B/C/D |
| [MISSION-BOARD-ADOPTION.md](./MISSION-BOARD-ADOPTION.md) | **Shipped** — Mission Board MB-9…MB-11 (P1~P4); P5 backlog |
| [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md) | **H0–H7 shipped** — runtime contract, dispatch lanes, PolicyEngine |
| [PLUGIN-DISCOVERY.md](./PLUGIN-DISCOVERY.md) | Slash commands + plugins **shipped** |
| [NOTIFICATION-TAXONOMY.md](./NOTIFICATION-TAXONOMY.md) | Toast / Activity notification 분류 |
| [ROOM-DISPATCH-PROTOCOL.md](./ROOM-DISPATCH-PROTOCOL.md) | DELEGATE / parallel dispatch protocol **shipped** |
| [MCP-TOOL-CONTRACT.md](./MCP-TOOL-CONTRACT.md) | Inbox / session plugin MCP 계약 |
| [HYBRID-RELAY-WORKER.md](./HYBRID-RELAY-WORKER.md) | Cloudflare hybrid relay worker 배포 |

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
| [UI-HANDOFF-TEAM-AGENTS.md](./UI-HANDOFF-TEAM-AGENTS.md) | Room UI 핸드오프 — API·SSE 계약, 컴포넌트 props |
| [developer-agent-console.md](./developer-agent-console.md) | 현재 콘솔 UI 레퍼런스 — 3-pane 레이아웃, **Work 탭 stepper** |
| [DESIGN-SYSTEM.md](./DESIGN-SYSTEM.md) | 색·타이포·컴포넌트 설계 원칙 |

**규칙:** UI contract 테스트 실패 시 현재 컴포넌트에 맞게 테스트를 수정 (프로토타입 네이밍으로 되돌리지 않음).

---

## Tier 4 — 아카이브 (shipped 상태 판단에 사용 금지)

| 경로 | 내용 |
|------|------|
| `archive/legacy/` | 00~05 초기 가이드, SPRINT-D-CHECKLIST, UI-MIGRATION-GAPS (모든 갭 종료), WORK-TAB-IA (→ developer-agent-console), MISSION-OS-OPS (→ OPS-RUNBOOK), MISSION-DOGFOOD (→ OPS-RUNBOOK), 세션 노트 등 |
| `archive/rfcs/` | 완료 RFC — EXECUTE-WORKTREE-REFORM, ROOM-REINFORCEMENT, GJC-WORKFLOW-PIPELINE, AGENT-OS-MODE-SIMPLIFICATION-PLAN, PLAN-WORKFLOW (→ FLOW §4), GOAL-LOOP (legacy opt-in), EXTERNAL-REFS-PLAN (→ TRACEABILITY) |
| `archive/` | 핸드오프 감사 문서 |

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
make test-fast                    # pytest ~870 tests (~1분)
make test                         # full pytest (not live)
make verify-hooks                 # Hook · Communicate suite
make ci                           # test + smoke + score fixtures
python scripts/smoke_room.py      # 36 regression baselines
make list-flags                   # AGENT_LAB_* 플래그 레지스트리
make mission-dogfood-run          # Mission loop mock dogfood
make mission-dogfood-weekly       # 주간 KPI rollup
```
