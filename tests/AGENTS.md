# tests — 테스트 에이전트 가이드

## 필수 규칙
- mock-only: `AGENT_LAB_MOCK_AGENTS=1` (실 LLM CI 절대 금지)
- 모든 테스트는 `pytest -m "not live"` 통과해야 함

## 패턴
- 회귀 fixture: `sessions/_regression/` (JSONL + `run.json`)
- tmp_path: pytest 내장 사용 (직접 tempdir 생성 금지)
- 새 기능 테스트 시 반드시 mock agent 경로 확인

## 금지
- `sessions/*` 커밋 (`sessions/_regression/` 제외)
- live API 호출 (ANTHROPIC_API_KEY 사용) in pytest
