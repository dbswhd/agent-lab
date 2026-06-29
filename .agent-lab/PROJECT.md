# 프로젝트 메모리 — agent-lab

## 아키텍처 한 줄
AI 개발 작업을 계획·승인·격리 실행·검증하는 Human-in-the-loop 에이전트 개발 콘솔.

주제 → Room (Cursor · Codex · Claude · Kimi Work) → `plan.md` → Human 승인 → worktree execute · merge · Oracle verify

**불변:** 합의=Room · 격리=worktree · 완료=Oracle verified · Human gate 유지

## Room (2026-06)
- **Preset:** fast (`quick`, Plan 잠금 OFF) · supervisor (`loop`, Plan 잠금 ON, consensus ON)
- **Plan toggle:** Composer checkbox — OFF=Scribe skip/read-only overlay, ON=plan.md 갱신 — [TURN-MODES.md](../docs/TURN-MODES.md)
- **에이전트:** cursor, codex, claude, kimi_work (+ kimi/local). `/model`로 composition
- **Kimi Work:** daimon bridge, Loop envelope peer

## 핵심 모듈
- `src/agent_lab` — Python Room·execute 코어
- `app/server` — FastAPI 서버
- `web/src` — React/Vite UI
- `tests` — pytest 회귀
- `scripts` — 스모크·운영 스크립트
- `docs` — 설계·런북 (`05-room-agent-roles.md`, `USER-GUIDE.md`)

## 빌드 & 실행
- `make dev`
- `make test-fast` — PR fast lane
- `make ci` — PR gate
- `make install`

## 에이전트 주의사항
- 이 파일은 Agent Lab `session_guidance`가 workspace-bound 세션에 주입 (1500자 cap).
- init-project-memory로 생성됨 — Human 검토·보강 필수.
- 개발 규칙: 루트 `CLAUDE.md` · `AGENTS.md` · `.claude/rules/`
- secrets는 `.env`만; child subprocess에 env 전체 상속 금지.

## 현재 작업 맥락
(Human이 채움 — 진행 중 작업·최근 결정)
