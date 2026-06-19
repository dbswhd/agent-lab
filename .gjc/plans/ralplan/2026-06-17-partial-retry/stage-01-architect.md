# RALPLAN Architect Review — partial-retry stage 1

## Verdict: WATCH / REQUEST CHANGES

## Steelman Antithesis
가장 큰 리스크는 "같은 Human 턴에 append"라는 핵심 가정이다. 턴은 종료 시 `_finalize_durable_turn` + `_write_session_files`로 **마감(finalized)**된다. 이미 마감된 턴 레코드를 다시 열어 reply를 끼워넣는 것은 턴 경계·메타(turn_index, summary, send_receipt)를 손상시킬 위험이 크다. 더 안전한 모델은 **원본 턴을 불변으로 두고, retried reply를 원본에 링크된 경량 'retry' 레코드로 추가**하는 것 — 마감된 상태를 재오픈하지 않는다. 계획의 "현재 턴 메타 갱신(partial→completed)"은 마감 레코드 변경을 함의하므로 재검토 필요.

## Tradeoff Tension (실재)
**(가) 마감 턴 직접 변경**(UX 깔끔: 한 턴으로 보임, 그러나 마감 메타 손상·중복 위험) vs **(나) 링크된 retry 서브레코드**(영속성 안전, 그러나 turn_status가 두 레코드에 걸쳐 재계산되어야 함). 계획은 (가)를 택했는데, 영속성 안전성 관점에서 (나)가 더 방어적이다. 최소한 turn_status의 **소유 위치**(원본 턴 메타 필드 1곳)와 갱신 규칙을 명시해야 한다.

## 누락/리스크
- **컨텍스트 정합성:** run_agent_rounds에 현재 messages(Human+성공 peer)를 넘길 때, context_bundle의 "이번 턴 동료 발화" 탐지가 그 성공 reply를 *이번 턴 peer*로 보는지 *이전 턴 history*로 보는지 불명. 잘못되면 재시도 에이전트가 peer를 못 보거나 중복 인식. → 테스트로 단언 필요.
- **turn_status 갱신 지점 미특정:** "재계산"이 원본 턴 run.json 메타의 어느 필드를 어떻게 바꾸는지(또는 retry 레코드에서 파생 계산하는지) 명시 필요.
- **멱등성:** 같은 retry 두 번 호출 시 reply 중복 방지 규칙 부재.

## Synthesis
A(전용 경로+엔드포인트)는 타당. 단 (1) 영속성 모델을 **(나) 링크된 retry 서브레코드 + 원본 턴의 turn_status 1필드 갱신**으로 명시(마감 레코드 재오픈 회피), (2) 컨텍스트 정합성(성공 peer를 이번-턴 peer로 봄)을 합격기준·테스트로 고정, (3) 멱등성(중복 append 방지) 규칙 추가 — 그러면 CLEAR.
