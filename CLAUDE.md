# Agent Lab 개발 가이드

## 빠른 시작
- `make dev` → API(8765) + web(5173)
- `make test-fast` → pytest ~2130 tests (`not live and not integration`, `-n auto` when xdist installed, ~1–2 min)
- `make test` / `make ci-full` → full mock suite incl. integration
- `make ci` → pytest + smoke + web build
- `python scripts/smoke_room.py` → 37 regression baselines
- `make dogfood-suite-mock` → Eval Program v1 mock topics ([`docs/EVAL-PROGRAM.md`](docs/EVAL-PROGRAM.md))
- `make list-flags` → `AGENT_LAB_*` registry (or `GET /api/health/flags`)

## 핵심 모듈
- `src/agent_lab/room/` — 멀티에이전트 Room (`agent_lab.room` facade)
- `src/agent_lab/plan/` — execute gate + worktree + merge + verify
- `src/agent_lab/run_meta.py` — `run.json` helpers + `completed_steps`
- `app/server/routers/` — FastAPI routes (`main.py` 조립만)
- `web/src/components/PlanExecutePanel.tsx` — execute UI

## 코드 규칙
- Python: `from __future__ import annotations` 첫 줄
- API 라우터: `app/server/routers/`에 추가 (`main.py` 직접 추가 금지)
- `run.json`: `patch_run_meta()` 경유
- **run_meta (F4):** 합의/턴 진행 중 in-memory `run_meta` 변경은 턴 종료 `_write_session_files` replay 경유로만 디스크에 반영 — 중간 `read_run_meta()`로 dict 재적재 후 patch 금지. 신규 `run_meta[` writer는 `tests/test_run_meta_write_discipline.py` allowlist 리뷰 필수 (baseline 축소만, 확대 금지).
- **Run profile (N2/F2):** `AGENT_LAB_RUN_PROFILE=fast|balanced|thorough|autonomous` — SSOT `src/agent_lab/run/profile.py`. 신규 **feature** 플래그는 최소 1개 프로필의 `flags`(적용 기본값) 또는 `owns`(소속만)에 넣는다 — `tests/test_run_profile.py::test_f2_every_feature_flag_has_owner` 가드.
- **Trading (F5):** `trading_mission/` · `quant/` 는 extension lane. 코어 Room/plan/inbox PR에 trading 표면을 늘리지 않는다. 코어→trading 경계는 `extensions/quant_trading.py` 만.
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
- shipped status: `docs/EXTERNAL-REFS-TRACEABILITY.md` · index: `docs/README.md`
- MD 작성: `docs/MD-WRITING-PLAN.md`

## Claude Code hooks (CC-hooks)
- `.claude/settings.json` — PostToolUse: ruff (`.py`), prettier (`.tsx`); Stop: pytest tail
- `room_hooks.py`와 별개 (서버 런타임 훅)

## Claude Code rules (CC-rules)
- `.claude/rules/python-backend.md` — `src/agent_lab/`, `app/`, `tests/`
- `.claude/rules/react-frontend.md` — `web/src/`

## Claude Code skills (CC-skills)

### Project (git tracked)
- `/agent-lab-ui` — Mission OS UI: tokens, IA, migration gaps, verify commands
- `/smoke-and-score` — E2E smoke + `make score-session`
- `/regression-check` — pytest + failure analysis
- `/init-project-memory` — PROJECT.md + AGENTS.md + SHARED_CONTEXT.md bootstrap

### UI craft (local — `npx skills add`, see `docs/UI-SKILLS.md`)
- `/impeccable` — audit, polish, animate (reads `PRODUCT.md`, `web/DESIGN.md`)
- `/emil-design-eng` — UI polish & motion taste
- `/review-animations` — motion code review (manual invoke)
- `/fixing-motion-performance` — jank / GPU animation fixes
- `/frontend-design` — anti–AI-slop direction before build

Design context: `PRODUCT.md` · `web/DESIGN.md` · `docs/UI-SKILLS.md`
