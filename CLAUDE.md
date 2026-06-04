# Agent Lab 개발 가이드

## 빠른 시작
- `make dev` → API(8765) + web(5173)
- `make test` → pytest 343+ tests
- `make ci` → pytest + smoke + web build
- `python scripts/smoke_room.py` → 19 regression baselines

## 핵심 모듈
- `src/agent_lab/room.py` — 멀티에이전트 Room
- `src/agent_lab/plan_execute*.py` — execute gate + worktree + merge + verify
- `src/agent_lab/run_meta.py` — `run.json` helpers + `completed_steps`
- `app/server/routers/` — FastAPI routes (`main.py` 조립만)
- `web/src/components/PlanExecutePanel.tsx` — execute UI

## 코드 규칙
- Python: `from __future__ import annotations` 첫 줄
- API 라우터: `app/server/routers/`에 추가 (`main.py` 직접 추가 금지)
- `run.json`: `patch_run_meta()` 경유
- subprocess: `subprocess_env.subprocess_env()` (env 전체 상속 금지)
- 테스트: mock-only (`AGENT_LAB_MOCK_AGENTS=1`), 실 LLM CI 금지

## 절대 금지
- `sessions/*` 커밋 (`sessions/_regression/` 제외)
- execute gate 우회
- `.env` 전체를 child process에 전달

## 아키텍처 불변 원칙
- 합의=Room · 격리=worktree · 완료=Oracle verified
- BLOCK → execute 409 (plan 모드)
- Human gate 유지

## 추적 문서
- shipped status: `docs/EXTERNAL-REFS-TRACEABILITY.md`
- MD 작성: `docs/MD-WRITING-PLAN.md`

## Claude Code hooks (CC-hooks)
- `.claude/settings.json` — PostEdit: ruff (`.py`), prettier (`.tsx`); Stop: pytest tail
- `room_hooks.py`와 별개 (서버 런타임 훅)

## Claude Code rules (CC-rules)
- `.claude/rules/python-backend.md` — `src/agent_lab/`, `app/`, `tests/`
- `.claude/rules/react-frontend.md` — `web/src/`

## Claude Code skills (CC-skills)
- `/smoke-and-score` — E2E smoke + `make score-session`
- `/regression-check` — pytest + failure analysis
