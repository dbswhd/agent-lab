---
name: regression-check
description: 전체 회귀 테스트 실행 후 실패 원인 분석 및 수정 방향 제시
tools: Bash, Read
---

# 회귀 테스트 체크

Repo root에서 실행. 수정은 Human 확인 후 — 이 skill은 분석·제안만.

## 1. 테스트 실행

```bash
.venv/bin/pytest tests/ -q --tb=short 2>&1 | head -80
```

실패 시 전체 재실행 (상위 5개만):
```bash
.venv/bin/pytest tests/ -q --tb=short -x
```

## 2. 실패 분석

- 실패 테스트 파일 Read
- 관련 소스 Read (에러 라인 ±20줄)
- 원인 분류: API 변경 / 로직 버그 / 테스트 stale / fixture drift

## 3. 출력 형식

```
PASS: N tests
FAIL: M tests

실패:
- test_xxx: [원인] → [수정 방향]
```

## 4. 후속

- `sessions/_regression/` drift면 fixture 또는 smoke baseline 갱신 여부 명시
- traceability 변경 필요 시 `docs/EXTERNAL-REFS-TRACEABILITY.md` 언급
