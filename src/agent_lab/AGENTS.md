# src/agent_lab — 백엔드 에이전트 가이드

## 불변 규칙
- `run.json` 직접 쓰기 금지 → `patch_run_meta()` / `read_run_meta()` 경유
- subprocess child env 전체 상속 금지 → `subprocess_env()` / `isolated_process_env()`
- 새 HTTP 라우트 → `app/server/routers/`에 추가 (`main.py` 직접 금지)
- execute gate 우회 금지

## 핵심 모듈 요약
- `room.py` — Room 오케스트레이션 (multi-agent discuss, BLOCK/CHALLENGE)
- `kimi_work_provider.py` / `kimi_control_client.py` — Kimi Work daimon peer
- `room_preset.py` — fast / supervisor preset catalog
- `agent_permissions.py` — discuss overlay + runtime blocks in `[고정 constraints]`
- `plan_execute*.py` — worktree dry-run → merge gate
- `mission/loop.py` — Layer 6 FSM (DISCUSS↔EXECUTE↔VERIFY)
- `run_meta.py` — `run.json` 헬퍼
- `session_guidance.py` — 에이전트 context bundle + `.agent-lab/PROJECT.md` 주입

## Discuss vs plan
- `apply_discuss_executor_policy()` sets `_discuss_mode` → read-only preamble for codex/claude/kimi_work
- Pure discuss: scribe skip (E2b), tasks harvest without pre-claim
- Agents must not meta-announce mode — policy is in constraints (`permission_preamble`, `KIMI_WORK_TOOL_RULES`)

## 파일 첫 줄
`from __future__ import annotations` 필수
