---
name: init-project-memory
description: 워크스페이스를 분석해 .agent-lab/PROJECT.md를 생성하거나 업데이트
tools: Read, Bash, Edit
---

# 프로젝트 메모리 초기화

대상 경로: `$ARGUMENTS` (없으면 Human이 지정한 workspace root, 또는 현재 repo root)

Agent Lab 런타임은 `{workspace}/.agent-lab/PROJECT.md`를 `session_guidance`에 주입 (1500자 cap).

## 1. Bootstrap (스크립트)

Creates `.agent-lab/PROJECT.md`, workspace-root `AGENTS.md`, and `SHARED_CONTEXT.md`.

```bash
TARGET="${1:-.}"
.venv/bin/python scripts/init_project_memory.py "$TARGET"
```

기존 파일 덮어쓰기:
```bash
.venv/bin/python scripts/init_project_memory.py "$TARGET" --overwrite
```

미리보기 (PROJECT만):
```bash
.venv/bin/python scripts/init_project_memory.py "$TARGET" --dry-run | head -40
```

## 2. 수동 보강 (필수)

1. 생성된 `.agent-lab/PROJECT.md` Read
2. **아키텍처 한 줄** — README/pyproject와 대조해 정확히 수정
3. **핵심 모듈** — 실제 파일 경로·역할 3–6개로 압축
4. **에이전트 주의사항** — 이 repo 고유 금지/제약 추가
5. **현재 작업 맥락** — Human이 진행 중 작업 기록

## 3. PROJECT.md 구조 (2000자 이내)

```markdown
# 프로젝트 메모리 — {이름}
## 아키텍처 한 줄
## 핵심 모듈
## 빌드 & 실행
## 에이전트 주의사항
## 현재 작업 맥락
```

## 4. 완료 기준

- `{workspace}/.agent-lab/PROJECT.md` 존재
- 2000자 이하, Human 검토 완료
- (선택) Agent Lab 세션에서 workspace_binding 경로와 일치 확인
