# agent-lab — Codex 가이드

## 제품 한 줄
주제 → Cursor · Codex · Claude Room → `plan.md` → Human 승인 → worktree execute · merge · Oracle verify.

## 에이전트 역할 (Room)
| 에이전트 | 역할 |
|----------|------|
| **Cursor** | 레포·파일·UI·패치 — execute |
| **Codex** | 분해·순서·검증·완료 기준 |
| **Claude** | 맹점·리스크·설명·Oracle(선택) |

프롬프트: `src/agent_lab/agents/prompts.py` · 상세: `docs/USER-GUIDE.md` §1.2

## 환경
- 개발: `make dev` · CI: `make ci` · 테스트: `make test-fast`

## 작업 전 확인
1. `.agent-lab/PROJECT.md` 최신 여부
2. plan action `검증:` 기준 확인
3. Shipped 여부: `docs/EXTERNAL-REFS-TRACEABILITY.md`

## 금지
- execute gate 우회
- subprocess env 전체 상속
