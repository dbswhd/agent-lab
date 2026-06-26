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

프롬프트: `src/agent_lab/agents/prompts.py` · 상세: `docs/05-room-agent-roles.md` · UI: `docs/USER-GUIDE.md` §1.2 · §6

## 턴 모드 (에이전트 payload)
- **discuss** — plan 갱신 OFF. Codex/Claude/Kimi Work read-only overlay. `[PROPOSED:]`로 실행 제안만.
- **plan** — Scribe가 `plan.md` 갱신. execute 섹션은 Human gate 이후.
- constraints에 정책이 이미 있음 — **「discuss/plan 모드입니다」 같은 메타 선언 금지**, 바로 답변.

## Room preset · Inbox
- **fast** (`quick`) — 리드 1명, plan OFF; orchestrator harvest 스킵, **team lead MCP**(`ask_human` / `propose_build`) 유지 — [docs/05-room-agent-roles.md §Fast preset](./docs/05-room-agent-roles.md)
- **MCP-first Inbox** — Human gate SSOT = agent MCP; orchestrator harvest default **off** (`AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST=0`) — [docs/MCP-FIRST-INBOX.md](./docs/MCP-FIRST-INBOX.md)
- **supervisor** (`loop`) — 전원, consensus ON, plan ON

## 환경
- 개발: `make dev` · CI: `make ci` · 테스트: `make test-fast`

## 작업 전 확인
1. `.agent-lab/PROJECT.md` 최신 여부
2. plan action `검증:` 기준 확인
3. Shipped 여부: `docs/EXTERNAL-REFS-TRACEABILITY.md`

## 금지
- execute gate 우회
- subprocess env 전체 상속
