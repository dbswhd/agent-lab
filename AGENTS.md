# agent-lab — Codex 가이드

## 제품 한 줄
주제 → Room (Cursor · Codex · Claude · optional Kimi Work) → `plan.md` → Human 승인 → worktree execute · merge · Oracle verify.

## 에이전트 역할 (Room)
| 에이전트 | 역할 |
|----------|------|
| **Cursor** | 레포·파일·UI·패치 — execute |
| **Codex** | 분해·순서·검증·완료 기준 |
| **Claude** | 맹점·리스크·설명·Oracle(선택) |
| **Kimi Work** | daimon peer — 레포 검증·대안·Loop envelope |

프롬프트: `src/agent_lab/agents/prompts.py` · 턴 모드 SSOT: [docs/TURN-MODES.md](./docs/TURN-MODES.md) · 역할: [docs/05-room-agent-roles.md](./docs/05-room-agent-roles.md)

## 턴 제어 (현재 UI — 2026-07)

Composer는 **topic-only**다. 레거시 Plan 체크·빠른/감독 picker는 **제거됨** (`web/src/utils/roomComposerPrefs.ts`).

| 축 | 현재 | 값 |
|----|------|-----|
| **Room preset** | 설정/세션 기본 (composer 숨김) | dogfood 기본 `supervisor` → turn `loop` |
| **Plan / Scribe** | **TurnPolicy** 신호 (FSM·consensus·skill_intent·MCP) | 사용자가 Plan 토글하지 않음 — [TURN-POLICY.md](./docs/TURN-POLICY.md) |
| **결정 표면** | Composer event stack + Human Inbox | plan 승인 · execute · ask_human — [ABSORB-CC-CODEX-2026-07.md](./docs/ABSORB-CC-CODEX-2026-07.md) |

constraints에 정책이 이미 있음 — **「discuss/plan 모드입니다」 메타 선언 금지**.

## Room preset · Inbox
- **fast** — 1 lead, Scribe 기본 억제, orchestrator harvest 스킵; **team lead MCP** 유지 — [05-room-agent-roles.md §Fast preset](./docs/05-room-agent-roles.md)
- **supervisor** — team + consensus · **실작업(dogfood) preset** — S1 trio implicit ON ([DESIGN-S1-FEEDBACK-LOOP.md](./docs/DESIGN-S1-FEEDBACK-LOOP.md))
- **MCP-first Inbox** — Human gate SSOT = agent MCP; harvest default **off** — [MCP-FIRST-INBOX.md](./docs/MCP-FIRST-INBOX.md)

## Dogfood · cleanup (2026-07)
- **운영:** supervisor로 매일 사용 · S1 D3 “닫힘” 의식 없음 — [docs/CLEANUP-SSOT-2026-07.md](docs/CLEANUP-SSOT-2026-07.md)
- **Room UI 버그:** [ROOM-TRANSCRIPT-CONTRACT.md](./docs/ROOM-TRANSCRIPT-CONTRACT.md) · Phase 1a blocker 우선

## 환경
- 개발: `make dev` · CI: `make ci` · 테스트: `make test-fast`

## 작업 전 확인
1. `.agent-lab/PROJECT.md` 최신 여부
2. plan action `검증:` 기준 확인
3. Shipped 여부: `docs/EXTERNAL-REFS-TRACEABILITY.md`

## 금지
- execute gate 우회
- subprocess env 전체 상속
- 턴 중 `read_run_meta()` 재적재 후 in-memory 변경 유실 (F4 — `patch_run_meta` / turn-end replay만)
- 코어 PR에 `trading_mission/` · `quant/` 표면 확대 (F5 — extension lane)

## Run profile (N2 / F2)
- `AGENT_LAB_RUN_PROFILE`: `fast` · `balanced`(default) · `thorough` · `autonomous`
- SSOT: `src/agent_lab/run/profile.py` — `flags` = applied defaults, `owns` = membership only
- catalog: `GET /api/profiles` · flags: `make list-flags --profile …` / `GET /api/health/flags?profile=`
- 신규 feature 플래그는 `flags` 또는 `owns`에 소속 필수 (F2)
- 개별 `AGENT_LAB_*` env는 프로필 기본값을 override
