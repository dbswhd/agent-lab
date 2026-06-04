# 프로젝트 메모리 — agent-lab

## 아키텍처 한 줄
Educational sandbox: topic → multi-role LLM graph → plan.md

## 핵심 모듈
- `src/agent_lab` — Python Room·execute 코어
- `app/server` — FastAPI 서버
- `web/src` — React/Vite UI
- `tests` — pytest 회귀
- `scripts` — 스모크·운영 스크립트
- `docs` — 설계·런북 문서

## 빌드 & 실행
- `make dev`
- `make test`
- `make ci`
- `make install`

## 에이전트 주의사항
- `.agent-lab/PROJECT.md`는 Agent Lab `session_guidance`가 workspace-bound 세션에 주입 (1500자 cap).
- init-project-memory로 생성됨 — Human 검토·보강 필수.
- 개발 규칙: 루트 `CLAUDE.md` 및 `.claude/rules/` 참고.
- secrets는 `.env`만; child subprocess에 env 전체 상속 금지.

## 현재 작업 맥락
(Human이 채움 — 진행 중 작업·최근 결정)
