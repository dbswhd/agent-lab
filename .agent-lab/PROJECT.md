# 프로젝트 메모리 — agent-lab

## 아키텍처 한 줄
AI 개발 작업을 계획·승인·격리 실행·검증하는 Human-in-the-loop 에이전트 개발 콘솔.

주제 → Room (Cursor · Codex · Claude · Kimi Work) → `plan.md` → Human 승인 → worktree execute · merge · Oracle verify

**불변:** 합의=Room · 격리=worktree · 완료=Oracle verified · Human gate 유지

## 현재 작업 맥락

- **2026-09-01 A1–A4 ✅:** `main` CI green · `balanced` profile · quickstart `fork_time_minutes=1`.
- **Phase 1:** C0–C4 shipped — [DELEGATE-SPIKE.md](../docs/DELEGATE-SPIKE.md). 다음: **C5** live dry-run.
- **브랜치:** `main` (origin 대비 unpushed 8 commits — push는 Human 결정).

## Room (2026-07)
- **Composer:** topic-only — preset·Plan picker는 숨김; dogfood 기본 `supervisor`
- **Turn control:** TurnContract가 roster·round·consensus, TurnPolicy가 Scribe·plan FSM·task effect를 결정 — [TURN-CONTRACT.md](../docs/TURN-CONTRACT.md)
- **Human surface:** Composer의 Decision Queue가 현재 Human action 하나를 우선 표시한다. 내부 `work` lane은 실행·결과 surface일 뿐, 제거된 Work navigation tab이 아니다.
- **Workspace navigation:** 현재 visible tabs는 Transcript · Diff · Background · Files · Preview · Terminal이며, Inspector는 Overview · Tools다 (`web/src/utils/workspaceTabs.ts`).
- **Browser acceptance:** Wave B evidence는 현재 red로 **not browser-accepted** 상태다. 이 문서와 관련 문서는 이를 shipped/complete로 표현하지 않는다.
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
- `make dev` · `make test-fast` · `make ci` · `make install`
- dogfood: `export AGENT_LAB_RUN_PROFILE=balanced` (+ `~/.agent-lab/.env` provider paths)
- mock smoke: `AGENT_LAB_MOCK_AGENTS=1 make dogfood-suite-mock ONLY=S1` → `python scripts/smoke_room.py`

## 에이전트 주의사항
- 이 파일은 Agent Lab `session_guidance`가 workspace-bound 세션에 주입 (1500자 cap).
- init-project-memory로 생성됨 — Human 검토·보강 필수.
- 개발 규칙: 루트 `CLAUDE.md` · `AGENTS.md` · `.claude/rules/`
- secrets는 `.env`만; child subprocess에 env 전체 상속 금지.
