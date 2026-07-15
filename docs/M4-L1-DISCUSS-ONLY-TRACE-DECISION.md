# M4 / L1 Discuss-Only Trace Completeness Decision

> **작성:** 2026-07-07  
> **역할:** `M4` / `L1` regression fixture의 `trace_completeness`를 더 올릴지, 아니면 discuss-only 의미를 유지한 채 현 점수를 기준선으로 둘지 결정하는 작업 문서  
> **현재 평가 계약:** [EVAL-CONTRACT.md](./EVAL-CONTRACT.md) · **이력:** [WORKFLOW-DYNAMIC-REFERENCE.md](./archive/rfcs/WORKFLOW-DYNAMIC-REFERENCE.md) §11

---

## 0. 한 줄 결론

**지금은 `M4` / `L1`에 execute/human/oracle 흔적을 억지로 추가하지 않는다.**  
현재 fixture는 **discuss-only 의미를 정확히 담고 있고**, `trace_completeness`를 올리기 위한 후속 단계 합성은 케이스 의미를 흐릴 위험이 더 크다.

따라서:

- `S1/S2/S3 = 1.0`
- `M3/M4/M5/L1/L2/L3/X2 = 1.0`

현재 기준선은 **10개 eval case 전부 `trace_completeness = 1.0`**이다.  
이 값은 fixture 의미를 왜곡해서 만든 것이 아니라, `trace_profile`로 case-type-aware 분모를 적용하고 `M5`에 최소 `plan_update` 신호만 보강한 결과다.

---

## 1. 문제 정의

초기 문제 제기 시점 `evals/results/latest.json` 기준 `trace_completeness`는 다음과 같았다.

| Case | 점수 | 성격 |
|------|------|------|
| `M4` | `0.5556` | discuss-only challenge → amend → endorse |
| `L1` | `0.5556` | discuss-only routing escalation quick → deep |

이 낮은 수치는 exporter/fixture 품질 부족만이 아니라, **실제로 해당 fixture가 execute lane에 들어가지 않기 때문**이었다.

즉, 빠진 span은 단순 누락이 아니라 **존재하지 않는 단계**일 수 있다.

현재 missing spans 성격:

### `M4`
- `execute`
- `human_gate`
- `oracle_verify`
- `feedback_advisor`

### `L1`
- `execute`
- `human_gate`
- `oracle_verify`
- `feedback_advisor`

이 중 앞의 3개는 discuss-only fixture라면 **없어도 자연스럽다**.

---

## 2. 왜 이것이 별도 설계 결정인가

이 문제는 단순히 “점수를 더 올릴까?”가 아니다. 아래 둘 중 하나를 고르는 문제다.

### 선택지 A — completeness 점수 우선

fixture에 eval용 synthetic 흔적을 넣어서:

- `plan_update`
- `human_gate`
- `execute`
- `oracle_verify`

를 복원 가능하게 만든다.

**장점**
- T0 `trace_completeness_rate` 추가 상승
- report 모양이 더 균일해짐

**단점**
- discuss-only fixture가 **실제로는 하지 않은 단계**를 한 것처럼 보이게 됨
- 케이스 의미가 “토론 회귀”에서 “토론+가상 execute”로 바뀜
- 이후 사람이 fixture를 읽을 때 오해하기 쉬움

### 선택지 B — semantics 우선

discuss-only fixture는 discuss-only로 유지하고, 낮은 completeness를 **의미 있는 signal**로 받아들인다.

**장점**
- fixture가 제품 의미와 1:1로 대응
- “후속 단계 없음”과 “신호 부족”을 구분 가능
- M4/L1이 실제로 무엇을 검증하는지 더 명확

**단점**
- T0 `trace_completeness_rate` ceiling이 일부 낮게 유지됨
- raw completeness 숫자만 보면 덜 좋아 보임

**현재 결정:** **B 선택**, 그리고 2026-07-07 후속 작업으로 **grader 분모 해석 개선(`trace_profile`)을 채택**했다.

---

## 3. M4 / L1 fixture의 본래 역할

### `M4` — CHALLENGE → AMEND → ENDORSE

SSOT:
- discuss objection 흐름
- amend chain depth
- consensus 해소

실제 fixture가 검증하는 것은:

```text
PROPOSE → CHALLENGE → AMEND → ENDORSE
```

즉, **합의 품질**이지 실행 성공이 아니다.

### `L1` — quick → deep escalation

SSOT:
- initial route가 충분치 않을 때
- `AMEND`/`CHALLENGE`를 계기로
- category가 `quick`에서 `deep`으로 escalation

즉, **라우팅 적응**이 핵심이다.

이 케이스에 execute/oracle까지 넣으면 “escalation regression”보다 “full mission happy path”에 가까워진다.

---

## 4. 현재 기준선 해석 규칙

앞으로 `M4/L1`의 낮은 completeness는 아래처럼 읽는다.

### Canonical reading

> 초기 raw 9-span 기준에서 `M4` / `L1`의 `trace_completeness ≈ 0.56`은 품질 부족이 아니라,  
> **discuss-only fixture가 후속 stage span을 의도적으로 포함하지 않는 결과**였다.

즉:

- `0.55` = legacy/noisy/under-instrumented 라기보다
- **“토론 단계만 검증하는 fixture”**

### 운영 해석

| 케이스 유형 | 현재 기대 completeness |
|-------------|------------------------|
| generated S-case | `1.0` |
| execute_path / plan_only | `trace_profile`에 필요한 span이 다 있으면 `1.0` |
| discuss_only regression | `trace_profile`에 필요한 span이 다 있으면 `1.0` |

---

## 5. 향후 revisit 조건

다음 중 하나가 생기면 이 결정을 다시 검토한다.

### revisit trigger

1. `trace_profile` 정의 자체를 다시 바꿔야 할 때

2. `M4` / `L1`에 대해 실제 제품 의미가 바뀔 때  
   예: discuss-only가 아니라 plan/approval까지 포함하는 회귀로 재정의

3. T0를 대외 지표로 공개할 때 raw completeness 오해가 커질 때

4. `feedback_advisor` span을 fixture 기반으로도 안정 복원할 수 있게 될 때

---

## 6. 다음 작업 옵션

### 옵션 1 — grader 개선 (권장, 채택됨)

`trace_completeness`를 전 케이스 공통 9-span 분모 대신, 케이스 유형별 기대 span subset 기반으로 해석한다.

예:

| case type | required span subset |
|-----------|----------------------|
| discuss-only | `route`, `role_plan`, `room_round`, `objection` |
| plan-only | discuss subset + `plan_update`, `human_gate` |
| execute path | `route`, `role_plan`, `room_round`, `plan_update`, `human_gate`, `execute`, `oracle_verify` |
| full path | execute path + `objection`, `feedback_advisor` |

**장점**
- fixture 의미를 훼손하지 않음
- discuss-only 케이스가 불필요하게 낮아 보이지 않음

**단점**
- `trace_completeness` 해석 규칙 자체가 바뀜
- `EVAL-SURFACE-*` 문서와 grader 설계를 함께 업데이트해야 함

### 옵션 2 — 새 fixture 분리

`M4` / `L1`은 유지하고, 별도로:

- `M4b`: challenge/amend + later human gate
- `L1b`: routing escalation + execute handoff

를 추가한다.

**장점**
- 원본 fixture 의미 유지
- fuller path coverage 추가 가능

**단점**
- case 수 증가
- T0 기준선이 더 복잡해짐

### 옵션 3 — 현 상태 유지 (초기 결정)

- 문서 기준선만 유지
- raw completeness를 “expected legacy/discuss-only gap”으로 해석

---

## 7. 추천

현재 시점 추천은 아래 순서다.

1. **M4/L1 fixture는 현 상태 유지**
2. **fixture가 아니라 grader 분모 해석 개선** 먼저
3. execute-path fixture는 최소한 `actions`/`approvals`/`executions` 중 필요한 신호를 남겨 `trace_profile` 기대치를 충족

이유:

- raw 9-span 기준의 낮은 구간은 “누락”보다 “의미 차이”의 문제였고, 그래서 데이터보다 **채점 규칙**을 먼저 바꾸는 편이 맞았다
- 그 다음 `M5`에 최소 `plan_update` 신호를 보강해 현재는 10개 케이스 모두 `1.0`으로 정리됐다

---

## 8. 닫힘 기준

이 문서는 다음 상태를 닫힘으로 본다.

- [x] `M4/L1`를 무리하게 손대지 않기로 결정
- [x] 현재 기준선을 문서에 반영
- [x] 후속 작업 방향을 `grader 개선 우선`으로 명시
- [x] `trace_profile` 기반 grader 분모 해석 개선 적용

후속 reopen 조건은 [§5](#5-향후-revisit-조건).
