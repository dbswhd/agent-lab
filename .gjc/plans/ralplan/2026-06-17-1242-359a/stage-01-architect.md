# RALPLAN Architect Review — stage 1 plan

## Verdict: WATCH / REQUEST CHANGES (수정 후 재검토)

## Steelman Antithesis (가장 강한 반정립)
계획 전체가 과설계일 수 있다. '발산'은 **메커니즘이 아니라 프롬프트 문제**일 가능성이 크다 — 에이전트에게 "서로 다른 접근을 제시하라, 조기 동의 금지"를 지시하는 system instruction만으로도 발산이 나올 수 있다. 신규 turn profile + ModeContract 필드 + round-flow 분기 + consensus_policy 변종은, 본질이 prompting인 문제에 구조를 과하게 얹는 것일 수 있다. 최소 가설(프롬프트-온리 baseline)을 Options에서 먼저 반증하지 않았다.

## Tradeoff Tension (실재 긴장)
Principle 4("최소 침습")와 Option B("신규 코드 경로")는 정면으로 긴장한다. B는 *수렴 경로엔* 최소 침습이지만 *전체적으론* 두 번째 라운드-오케스트레이션 경로를 추가한다 — 이미 결합도 높은 `room_turn_flow.py`(887 LOC)/`room_consensus_rounds.py`(771 LOC) 위에. 발산 러너가 `run_parallel_round`를 **재사용**하는지, 아니면 병렬 로직을 **재구현**하는지가 이 긴장의 분기점이다. 재사용이면 B가 정당, 재구현이면 C의 "공유 경로 오염" 비판이 B에게도 돌아온다.

## 누락된 차원 (핵심)
계획의 파일 목록이 **에이전트 행동/프롬프트 차원을 빠뜨렸다.** consensus 머신을 꺼도, `agents/prompts.py`·`context_bundle`·`reply_policy`의 프롬프트가 합의·plan 합성을 향해 튜닝돼 있으면 에이전트는 여전히 수렴한다. 발산 모드는 거의 확실히 **발산 전용 system instruction**(조기 동의 금지, 접근-수준 차별화 요구)이 필요하다. 메커니즘만 바꾸면 합격 기준 #2/#3(조기수렴 안 함, 구분 대안 N개)이 충족 안 될 위험.

## 부차 지적
- `ModeContract`는 frozen+slots dataclass. `divergence: bool` 추가 시 quick/team/loop 3개 생성 분기 전부 기본값 처리 필요(계획에 명시됨—OK) + run.json/contract 직렬화·`patch_run_mode_contract` 경로 점검 필요(계획 미언급).
- 발산 산출물의 "정지" 보장은 router뿐 아니라 plan 합성/auto-scribe SSE 경로에서도 트리거 안 됨을 확인해야 한다(계획은 router만 언급).

## Synthesis (건설적 합의안)
B 방향은 타당하다(수렴 경로 무손상이 가장 중요). 단 (1) Options에 **프롬프트-온리 baseline**을 명시적 대안으로 넣고 왜 그것만으론 부족한지(메커니즘 endorse-exit가 여전히 조기 종료시킴) 반증, (2) 파일 목록에 **발산 전용 프롬프트/instruction 차원** 추가, (3) 발산 러너가 `run_parallel_round` 재사용임을 못박아 Principle 4 긴장 해소, (4) contract 직렬화·auto-scribe 정지 경로 점검을 명시하면 CLEAR.
