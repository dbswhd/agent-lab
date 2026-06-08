---
name: smoke-and-score
description: 스모크 테스트 실행 후 가장 최근 세션의 품질 KPI를 측정하고 리포트
tools: Bash
---

# 스모크 + 세션 스코어 리포트

Repo root에서 실행. 실 LLM 호출 금지 — mock-only.

## 실행 순서

1. **E2E 스모크**
   ```bash
   make smoke-e2e
   ```
   또는:
   ```bash
   AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/smoke_room_e2e.py
   ```

2. **최근 로컬 세션** (`sessions/_regression` 제외)
   ```bash
   LATEST=$(ls -t sessions 2>/dev/null | grep -v '^_' | grep -v '^\.' | head -1)
   echo "대상 세션: sessions/$LATEST"
   ```
   세션이 없으면 `make smoke` (25 regression baselines) 결과만 요약.

3. **품질 스코어** (세션이 있을 때)
   ```bash
   make score-session SESSION=sessions/$LATEST
   ```

## 리포트 형식

표로 요약:
- objection_resolution_rate (목표 >80%)
- execute_retry_rate (목표 <30%)
- ref_validity_rate (목표 >90%)
- duplicate_speech_rate (목표 <20%)
- mission loop (enabled 세션): `repair_events`, `notepad_chars`, `circuit_breaker`, `mission_completed`

임계값 미달 항목은 원인·개선 제안 포함. 스모크 실패 시 fixture 이름과 첫 에러만 인용.

## Mission dogfood (Week 2)

실 미션 1건 후 `docs/MISSION-DOGFOOD.md` 체크리스트로 notepad·pause·gate 품질을 점검하세요.
