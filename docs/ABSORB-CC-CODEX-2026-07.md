# ABSORB — Claude Code · Codex → agent-lab (2026-07)

> **역할:** OpenAI Codex / Anthropic Claude Code 패턴을 agent-lab에 흡수할 때의 SSOT (absorb / replace / reject + 웨이브).  
> **근거:** 로컬 설치 코드 + 공식 docs/changelog (조사일 2026-07-10).  
> **모트:** BLOCK→409 · worktree 격리 · Oracle+Repair · run.json 감사 · Human Inbox — 약화 금지.  
> **관계:** [NORTH-STAR.md](./NORTH-STAR.md) §2.5 · [NOW.md](./NOW.md) 분기 리뷰 ② · [TURN-CONTRACT.md](./TURN-CONTRACT.md) §7 · [HUMAN-INBOX.md](./HUMAN-INBOX.md) §2
> **ID 네임스페이스:** ABSORB Wave 3 항목은 **`ABS-P2-*`** (WORKFLOW Composer-preset **P2**와 구분).

---

## 0. 증거 버전

| 소스 | 버전 / URL |
|------|------------|
| Claude Code (local) | telemetry **v2.1.202** · `~/.claude/` |
| Codex CLI (local) | **0.138.0** · `~/.codex/` · `~/.codex/agents/plan.toml` |
| OpenAI Codex changelog | https://developers.openai.com/codex/changelog (Jul 2026: ChatGPT desktop 통합, Needs input) |
| OpenAI worktrees | https://developers.openai.com/codex/app/worktrees (Local/Worktree/Handoff, `.worktreeinclude`) |
| Claude Code What’s new | https://code.claude.com/docs/en/whats-new/index (W13–W26) |
| Claude Code worktrees | https://code.claude.com/docs/en/worktrees (`--worktree`, `baseRef`, hooks) |

---

## 1. Absorb / replace / reject

| 패턴 | 판정 | Agent Lab 매핑 |
|------|------|----------------|
| Codex Local↔Worktree **Handoff** · `.worktreeinclude` · setup script | **absorb** | Workspace 카드 + MB-6 `.agent-lab/worktree.yaml` |
| Conductor workspace = path·branch·diff·checks·archive | **absorb** | `WorkspaceCard` in `PlanExecutePanel` |
| Codex `plan.toml` waves·QA·evidence · CC **Ultraplan** 섹션 리뷰 | **absorb** | Scribe `plan.md` 계약 + plan 승인 |
| Needs input / `claude agents` blocked-on-you · subagent perms→main | **absorb (P1)** | Inbox + session rail 상태 |
| Mid-turn **steer** · Monitor/`/loop` | **absorb (P1)** | Composer + Evidence |
| AskUserQuestion / ExitPlanMode / MCP Inbox | **replace** | 이미 Inbox MCP SSOT — UX만 정렬 |
| Skills / plugins / tool_cards | **absorb (ABS-P2 / N7·S3)** | S3a-0 RECALL만 현행; **S3b mount 구현 동결** ([S3-TOOL-CARD-SPEC.md](./S3-TOOL-CARD-SPEC.md)) |
| Auto mode / Auto-review / guardian | **replace** | AutonomyDial L1 보조만 — Inbox·409 **대체 금지** |
| `/autofix-pr` · Jules auto-merge · fire-and-forget cloud | **reject** | Human gate 없는 CI/merge 루프 |
| Dynamic workflows / MoA aggregator | **reject as Room replace** | [TURN-CONTRACT.md](./TURN-CONTRACT.md) §7의 문서 패턴만 — runtime 카탈로그/엔진 **금지** |
| Plan/Agent 모드 피커 복원 | **reject** | TurnPolicy·TurnContract 암시 라우팅 |
| Sites / Computer Use / Chronicle | **out of core** | extension / dogfood ops만 |

---

## 2. 웨이브

### Wave 0 — 문서 (이 파일 + NORTH-STAR §2.5)

- [x] ABSORB SSOT
- [x] NORTH-STAR §2.5 행 갱신 · NOW 분기 리뷰 링크 · AGENTS.md Plan-toggle drift

### Wave 1 — P0 UX (모트 중립)

| ID | 내용 | 앵커 | 상태 |
|----|------|------|------|
| **W1-A** | Workspace 카드: worktree path · branch · diff · merge checks · archive · handoff | `web/src/components/WorkspaceCard.tsx`, `PlanExecutePanel.tsx` | shipped |
| **W1-B** | `plan.md` TL;DR · Must/Must-NOT · Parallel waves · Evidence paths (+ soft validation) | `agents/prompts.py` `ROOM_SCRIBE`, `plan/actions.py` | shipped |

### Wave 2 — P1 (Needs input / steer)

| ID | 내용 | 공식 근거 | 상태 |
|----|------|-----------|------|
| P1-needs-input | Needs input / blocked-on-you — header badge + session rail dot | Codex Jul · CC agents · W26 | shipped (`NeedsInputBadge`, `needsInputStatus.ts`, SessionList) |
| P1-steer | execute/room 중 mid-turn steer queue | Codex mid-turn steering | shipped (`POST /api/sessions/{id}/steer`, composer Steer, drain in parallel_rounds + enrich_execute_prompt) |
| P1-notify | Inbox OS/모바일 알림 | CC mobile push · Notification hooks | shipped (`notifyNeedsInput.ts`, background desktop + Activity when Needs input / inbox poll) |
| P1-monitor | CI/로그 → Evidence | CC Monitor | shipped (`evidence_monitor.py`, `POST …/evidence/monitor`, merge-checks → MONITOR dedupe, EvidenceTimeline) |
| P1-status | Autonomy × sandbox 상태줄 | CC statusline · Codex policy | shipped (`runtime.status_line`, `SessionStatusLine`, profile/worktree/sandbox chips) |
| P1-fork | session fork | Codex fork | shipped (`session/fork.py`, `POST /api/sessions/{id}/fork`, SessionList context menu) |

### Wave 3 — ABS-P2 (코드 vs 문서 범위)

> **ID:** `ABS-P2-*` — WORKFLOW §8.2 Composer-preset **P2**(strangler)와 **다른 트랙**.
> **훅 레이어 SSOT:** [HOOK-COMMUNICATE-REFORM.md](./HOOK-COMMUNICATE-REFORM.md) §1.1 — **3-layer + worktree lifecycle** (worktree hooks ≠ Layer C).

| ID | 내용 | 지금 허용 | 상태 |
|----|------|-----------|------|
| **ABS-P2-skills** | tool_cards → mount (S3b) | **동결** — S3a-0 관측·RECALL만. S3a 외부 발견 / S3b mount / S3c 활용 학습 구현 금지 ([NOW.md](./NOW.md) 동결 · [NORTH-STAR.md](./NORTH-STAR.md) N7 · [S3-TOOL-CARD-SPEC.md](./S3-TOOL-CARD-SPEC.md)) | frozen |
| **ABS-P2-hooks** | CC SubagentStart/Stop ↔ Room 관측점 | **문서 매핑만** — 이벤트 의미·소유 레이어 표. runtime alias / 새 event / 새 gate = Human OK 필요. SubagentStart≠`pre_agent_reply`, SubagentStop≠`post_agent_reply`/`task_completed` (정책 다름 — `room/hooks.py`) | docs-only backlog |
| **ABS-P2-workflows** | dynamic workflows → TurnContract | **[TURN-CONTRACT.md](./TURN-CONTRACT.md) §7로 문서화 완료.** 기존 네 contract·topology·비용 힌트만. runtime YAML/JSON · DAG · side-effect/gate 제어 · picker · MoA BLOCK 생략은 금지 | docs-only complete |
| **ABS-P2-worktree-yaml** | baseRef · include · Create/Remove | 코드 허용 (모트 중립 MB-6 연장) | shipped (`worktree_hooks.py`, isolation baseRef, include copy, create→setup / remove teardown, WorkspaceCard) |

---

## 3. 완료 판정

- Wave 0: 이 문서 + NORTH-STAR가 로컬 버전 **및** 공식 URL을 인용
- W1-A: Plan→Execute에서 workspace 메타가 **한 화면**
- W1-B: 신규 plan에 waves·Must-NOT·evidence 섹션 + soft validation; X2 mock 통과
- P1-needs-input: 헤더 Needs input 배지 + 세션 레일 점 (Inbox/plan/execute 승인 대기 집계)
- P1-steer: busy 중 Steer → `steer_queue` → 다음 agent/execute 단계에만 주입 (gate 우회 없음)
- P1-status: 헤더 statusline chips (run profile · worktree/isolation · schedule sandbox)
- P1-notify: document hidden 시 Needs input → desktop/Activity (`needs_input` kind)
- P1-monitor: MONITOR evidence (`POST …/evidence/monitor` · merge-checks fail dedupe)
- P1-fork: 세션 포크 (plan/chat 복사, pending inbox/executions 미복사)
- ABS-P2-worktree-yaml: `baseRef` · include/`.worktreeinclude` · create/remove hooks (setup/verify 유지, gate 우회 없음)
- ABS-P2-skills / hooks / workflows: 위 표의 **허용 범위**만 (코드 엔진·alias·mount 없음)
- 전 웨이브: 5모트 회귀 · autofix/auto-merge 경로 없음

---

## 4. 의도적 비범위

Claude/Codex 업스트림 패치 · Plan/Agent 피커 복원 · HS6/HS7 · N5/S2 동결 해제 · N7/S3b+ 구현 · trading/quant · ABS-P2-hooks runtime alias · ABS-P2-workflows runtime 카탈로그/엔진
