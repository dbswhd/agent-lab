---
paths:
  - "src/agent_lab/**/*.py"
  - "app/**/*.py"
  - "tests/**/*.py"
---

# Python 백엔드 규칙

## 타입 & 스타일
- `from __future__ import annotations` 모든 파일 첫 줄
- dataclass 우선; 단순 dict return보다 typed class
- 함수 반환 타입 명시 (`-> dict[str, Any]` 등)

## 상태 변경
- `run.json` → `patch_run_meta()` / `read_run_meta()` 경유 (직접 JSON 쓰기 금지)
- `chat.jsonl` → `session.py` 헬퍼 경유
- `plan.md` → `synthesize_plan()` / `_write_plan_if_changed()` 경유

## subprocess
- child env 전체 상속 금지 → `subprocess_env.subprocess_env()` 또는 `isolated_process_env()` 사용

## 테스트
- mock-only (`AGENT_LAB_MOCK_AGENTS=1`); 실 LLM CI 금지
- 회귀 fixture: `sessions/_regression/` (JSONL + `run.json`)

## 금지
- execute gate 우회, `sessions/*` 커밋 (regression 제외)
- 라우트를 `main.py`에 직접 추가 (`app/server/routers/` 사용)

## 참고
- Room: `room.py` · Execute: `plan_execute*.py` · Meta: `run_meta.py`
