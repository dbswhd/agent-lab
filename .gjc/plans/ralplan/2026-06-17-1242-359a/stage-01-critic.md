# RALPLAN Critic — stage 1 plan

## Verdict: ITERATE

## 평가
- Principle–Option 일관성: 대체로 양호하나 **Principle 4(최소 침습) ↔ Option B(신규 경로)** 긴장이 미해소. Architect 지적대로 발산 러너의 `run_parallel_round` 재사용 여부를 명시해야 일관됨.
- 대안 공정성: A/B/C + invalidation 제시 — 공정. 단 Architect가 제기한 **프롬프트-온리 baseline**이 Options에 없음. 가장 싼 대안을 반증하지 않은 건 공백.
- 리스크 완화 명확성: R1~R4는 구체적. 그러나 **에이전트 프롬프트가 수렴을 유도하는 행동 리스크**가 누락 — 이건 합격기준 #2/#3 달성을 직접 위협하므로 치명적 공백.
- 테스트 가능 합격기준: 5종 모두 mock으로 관측 가능 — 양호. 단 #2(조기수렴 안 함)는 프롬프트 차원 없이 메커니즘만으론 실패할 수 있어, 테스트가 "메커니즘 미발화 + 실제 상이 입장 유지"를 둘 다 검증해야 함.
- 검증 구체성: 레인(test-fast/test-integration)·mock 플래그 명시 — 양호. verified BLOCK→409 회귀 테스트 명시 — 우수.

## 수정 요구 (ITERATE 해소 조건)
1. Options에 **D: 프롬프트-온리 baseline** 추가 + 반증(endorse-threshold 메커니즘이 여전히 조기 종료시키므로 프롬프트만으론 불충분 → 메커니즘+프롬프트 둘 다 필요).
2. 파일 목록에 **발산 전용 system instruction**(agents/prompts.py 또는 context_bundle/reply_policy 경유) 추가.
3. Option B 발산 러너가 `run_parallel_round` **재사용**임을 명시 (Principle 4 긴장 해소).
4. Risks에 **에이전트 프롬프트 수렴 편향** 리스크 + 완화(발산 instruction + 테스트가 상이 입장 유지를 검증) 추가.
5. contract 직렬화(`patch_run_mode_contract`/run.json) 및 auto-scribe/plan-합성 정지 경로 점검을 변경 목록에 명시.
