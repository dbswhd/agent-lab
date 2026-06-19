# RALPLAN Critic — partial-retry stage 1

## Verdict: ITERATE

## 평가
- Principle–Option 일관성: 양호하나 Principle 1("같은 턴 보존")이 마감 레코드 변경을 함의 — Architect의 영속성 안전 모델과 충돌, 재정의 필요.
- 대안 공정성: A/B/C + invalidation — 공정.
- 리스크 완화: R1~R4 구체적이나 **영속성 모델(마감 턴 재오픈 vs 링크 서브레코드)**·**컨텍스트 정합성**·**멱등성** 미해소가 합격기준 신뢰를 위협.
- 테스트 가능 합격기준: 6종 관측 가능하나 (가) turn_status 갱신 위치, (나) 성공 peer가 이번-턴 컨텍스트로 보임, (다) 멱등 재시도 합격기준 부재.
- 검증 구체성: 레인 명시 — 양호.

## 수정 요구 (ITERATE 해소)
1. 영속성 모델을 **링크된 retry 서브레코드 + 원본 턴 turn_status 1필드 갱신**으로 확정(마감 레코드 재오픈 회피). chat.jsonl는 append-only retried reply, run.json은 원본 턴의 status/failed/succeeded만 갱신.
2. **컨텍스트 정합성** 합격기준 추가: 재시도 에이전트 payload가 Human 메시지 + 성공 peer reply를 "이번 턴" 컨텍스트로 포함(테스트로 단언).
3. **멱등성** 규칙·합격기준 추가: 동일 retry 재호출 시 reply 중복 append 0(이미 성공한 에이전트는 스킵).
4. human_turn_num 불변 + turn_status 소유 필드 명시.
