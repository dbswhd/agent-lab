# S1 — Challenge Precision

> 작성: 2026-07-23 · 상태: **D1 구현 완료** (기록만 — advisor 미소비, `AGENT_LAB_CHALLENGE_PRECISION` default off)
> 선행: NOTE act shipped (envelope.py · consensus.py · role_plan critic persona)
> 관련: [NORTH-STAR.md](NORTH-STAR.md) §S1 · `outcome_harvester.py` · `feedback_advisor.py` · `turn_metrics.py`
>
> **구현 상태 (2026-07-23):** §3의 4개 계측 지점 중 3개 shipped — `turn_metrics._challenge_precision_summary`
> (per-agent challenge_total/challenge_adopted from `objections[].resolution == "challenger_authored_anchor"`,
> note_total from chat.jsonl 스캔), `outcome_harvester.build_outcome_record`(`challenge_precision` 필드 flatten).
> §4(advisor 소비)는 **미착수** — D1 단계 그대로.
> 미구현: §3-3 task claimed/done 지연 보정(§열린 질문 #1), plan.md delta 귀속(§3 신호 3번) — 아래 §7 참조.

## 1. 문제 (dogfood 근거)

2026-07-22 fix_verify 세션: hello.py 한 줄 작업이 **5라운드/12콜 + turn budget inbox pause**.
원인은 critic 역할의 구조적 인센티브 — "지적을 냈다"는 증거를 만들어야 역할을 수행한 것이 되고,
CHALLENGE 1건이 anchor 리셋·deep 승격으로 라운드를 곱셈으로 늘림.

프롬프트(critic persona)와 하네스(NOTE act)는 수정 완료. 남은 것은 **학습 루프**:
지적의 실제 적중률을 측정해 advisor가 역할 배정·라운드 예산을 데이터로 조정하는 것.

## 2. 신호 정의

**challenge_precision** = 채택된 지적 / 전체 지적 (per agent, per turn → ledger 롤업)

"채택"의 조작적 정의 (우선순위 순, 하나라도 참이면 채택):

| 신호 | 판정 소스 (기존 코드) |
|------|----------------------|
| 지적자가 쓴 수정안이 새 anchor로 채택됨 | consensus meta `anchor_lineage[]` — anchor.agent == challenger |
| objection이 `challenger_authored_anchor`로 해소 | `objections.py` resolution 필드 (이미 기록됨) |
| CHALLENGE 이후 같은 턴에서 plan.md delta 발생 | `plan_before/after` diff (plan_scribe에 이미 존재) |
| `[PROPOSED:]` → task 생성 후 이후 턴에서 claimed/done | `room/tasks.py` 태스크 상태 전이 |

**note_adoption** = NOTE의 `[PROPOSED:]`가 이후 처리된 비율 — NOTE가 "무시되는 쓰레기통"이
되는지 감시하는 보조 지표. 낮아도 감점하지 않음 (비차단 관찰은 원래 선택적).

## 3. 계측 지점 (구현됨 — 전부 기존 파일 확장, 신규 모듈 없음)

1. `turn_metrics.py` — `build_turn_metrics`에 `challenge_precision: dict[agent, {challenge_total, challenge_adopted, note_total}]` 필드 추가 (`_challenge_precision_summary`):
   - `challenge_total`/`challenge_adopted`: `objections[]`에서 `act=="CHALLENGE"`이고 이번 human_turn인 행을 `from`(agent)별로 집계. `adopted`는 `resolution == "challenger_authored_anchor"`(§2 신호 1+2 — `consensus_rounds.py`가 이미 이 값으로 `resolve_objections_on_endorse`를 호출함, 신규 계측 불필요).
   - `note_total`: 신규 파라미터 `turn_acts: list[{"agent","act"}]`에서 `act=="NOTE"`만 집계. `objection_summary`(HARVEST_ACTS=BLOCK/CHALLENGE만)에는 NOTE가 안 잡히므로 별도 소스 필요 — 호출자(`outcome_harvester`)가 chat.jsonl에서 채워 넘김.
   - AMEND는 미포함 (§2 신호 3/4, §7 열린 질문 #3과 동일 이유로 보수적 스코프 유지).
2. `outcome_harvester.py`:
   - `challenge_precision_enabled()` — `AGENT_LAB_CHALLENGE_PRECISION`, s1_flags의 supervisor-암묵-ON 트리오와 **독립** (기본 off, 다른 프리셋에 얹혀가지 않음).
   - `_turn_acts_for_human_turn(folder)` — `load_session_messages` + `current_turn_slice`로 이번 턴 메시지만 읽어 `{"agent","act"}` 평탄화 (`envelope_act` 재사용).
   - `record_turn_outcome`이 플래그 ON일 때만 `_turn_acts_for_human_turn`을 호출 (OFF면 `turn_acts=[]` → note_total 항상 0, chat.jsonl 안 읽음).
   - `build_outcome_record`가 `challenge_precision`을 ledger 행에 그대로 flatten. **스키마 버전은 안 올림** — HS1-1 `failure_tags`/`primary_tag` 추가 때도 안 올렸던 기존 선례(순수 additive optional 필드는 `v` 불변) 따름.
3. **미구현 (열린 질문 #1 그대로 보류):** `[PROPOSED:]` → task claimed/done 지연 채택 판정. 다음 턴 이후에나 확정되는 cross-turn 신호라 이번 패스는 손대지 않음 — §7 참조.

## 4. 소비 (feedback_advisor)

`_score_outcome()`에 항 추가 (기존 "Low pure CHALLENGE yield without a critic role → penalize" 주석의 정식화):

- `challenge_precision < 0.2` (표본 n≥10): 해당 agent:critic 콤보 감점
- NOTE 활용 콤보 (`note_total > 0` & `challenge_precision ≥ 0.5`): 소폭 가점 — "막을 것만 막고 관찰은 NOTE로" 행동 강화
- 표본 n<10: 중립 (조기 판단 금지)

advisor는 이미 combo 단위 탐색(`_explore_combo`)을 하므로, 저정밀 critic 콤보는 자연히 덜 뽑힘.
**프롬프트에 개인 점수를 노출하지 않는다** — 점수 사냥(지적 수 부풀리기의 역버전: 채택 확실한 것만 지적) 유도 방지.

## 5. 플래그 · 롤아웃

- `AGENT_LAB_CHALLENGE_PRECISION` (default OFF) — S1 Phase A 패턴: 기록은 fail-open, 소비(advisor 반영)는 별도 단계
- F2 규칙: 신규 플래그는 최소 1개 프로필 `flags`/`owns` 등재 (`test_f2_every_feature_flag_has_owner`)

| 단계 | 조건 | 행동 |
|------|------|------|
| D1 기록 | ✅ **구현 완료 (2026-07-23)** — `AGENT_LAB_CHALLENGE_PRECISION=1`로 켜면 즉시 기록 시작 | ledger에 `challenge_precision` 필드만 쌓임 (advisor 미소비) |
| D2 관찰 | supervisor dogfood 2주 or n≥30 (미착수 — 플래그가 아직 어디서도 기본 ON이 아님) | per-combo precision 분포 확인 (전용 리포트 스크립트 미구현 — `outcomes.jsonl`에서 `challenge_precision` 키로 직접 집계 가능) |
| D3 소비 | 분포가 판별력 있음 (콤보 간 spread ≥ 0.3) | advisor `_score_outcome` 반영 ON (미착수) |
| 롤백 | 지적 총량이 비정상 급감 (진짜 리스크 침묵 의심) | D3 OFF, D1 유지 |

## 6. 비목표

- 실시간 라운드 차단 (낮은 정밀 critic의 CHALLENGE를 즉석에서 무시) — 진짜 리스크를 놓치는 비용이 더 큼
- 개인별 점수 UI 노출 — 관찰용 리포트까지만
- NOTE 채택률 기반 감점 — NOTE는 무비용이어야 의미 있음

## 7. 열린 설계 질문 (미해결 — D2/D3 착수 전 결정 필요)

1. §3의 task claimed/done 지연 채택 판정: append-only 원칙과 "직전 행 1회 patch"의 충돌을 어떻게 풀지 (별도 보정 행 append로 대체 가능 — join 비용은 리포트 쪽 부담)
2. challenge_adopted 판정에서 plan.md delta 귀속 — 같은 턴에 여러 agent가 CHALLENGE하면 delta를 누구에게 귀속? (1안: 전원 공동 채택 / 2안: anchor 채택자만) — 현재 구현은 이 신호를 아예 안 씀 (anchor_lineage 기반 `challenger_authored_anchor`만 사용)
3. `AMEND`를 challenge_total에 포함할지 — AMEND는 이미 건설적 경로라 포함 시 precision이 과대평가될 수 있음 — 현재 구현은 CHALLENGE만 집계, 미포함으로 확정
