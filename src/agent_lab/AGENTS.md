# src/agent_lab — 백엔드 에이전트 가이드

## 불변 규칙
- `run.json` 직접 쓰기 금지 → `patch_run_meta()` / `read_run_meta()` 경유
- subprocess child env 전체 상속 금지 → `subprocess_env()` / `isolated_process_env()`
- 새 HTTP 라우트 → `app/server/routers/`에 추가 (`main.py` 직접 금지)
- execute gate 우회 금지

## 핵심 모듈 요약
- `room.py` — Room 오케스트레이션 (3-agent Discuss, BLOCK/CHALLENGE)
- `plan_execute*.py` — worktree dry-run → merge gate
- `mission_loop.py` — Layer 6 FSM (DISCUSS↔EXECUTE↔VERIFY)
- `run_meta.py` — `run.json` 헬퍼 (patch_run_meta, read_run_meta)
- `session_guidance.py` — 에이전트 context bundle 조립

## 파일 첫 줄
`from __future__ import annotations` 필수
