# Reproduction report — emergence bench (mock)

> **Date:** 2026-07-06  
> **Commit:** `e3459f2e` (이후 N8 문서 커밋은 별도)  
> **Protocol:** [EMERGENCE-BENCH.md](./EMERGENCE-BENCH.md)  
> **Reference JSON:** [`sessions/_benchmark/reports/emergence-bench-reference-mock-20260706.json`](../sessions/_benchmark/reports/emergence-bench-reference-mock-20260706.json)

---

## 요약

| 항목 | 값 |
|------|-----|
| Judge | `heuristic` (mock) |
| Topic SSOT | `sessions/_benchmark/topics/emergence-v1.json` (4 topics) |
| Solo agents | cursor, codex, claude |
| Room agents | cursor, codex, claude (consensus) |
| 실행 시간 (mock, 4 topics) | ~1.4s (M-series Mac, venv warm) |

---

## by_category (reference)

| category | topics | delta_mean | delta_positive |
|----------|--------|------------|----------------|
| quick | 1 | −0.1250 | 0 |
| standard | 1 | −0.1550 | 0 |
| deep | 1 | −0.1574 | 0 |
| critical | 1 | −0.1574 | 0 |

`delta_mean`은 해당 카테고리 토픽들의 `emergence_delta` 산술 평균.  
`delta_positive`는 `emergence_delta > 0` 인 토픽 수.

---

## 해석 (mock heuristic)

**현재 mock judge에서는 Room이 max(solo)를 이기지 못한다** (`emergence_delta < 0` 전 카테고리).

이는 실패가 아니라 **프로토콜 가동 증거**다:

1. 동일 topic·동일 시드로 solo 3회 + room 1회가 결정론적으로 실행됨
2. `composite_score` 6-KPI 합성이 산출됨
3. `emergence_delta = room − max(solo)` 공식이 리포트에 기록됨

**가설** ("deep/critical에서만 delta > 0")은 **live oracle judge**에서 검증 대상이다.  
Mock은 CI 회귀·재현성만 담당; 성능 주장은 live 리포트 + Human 리뷰가 필요 ([NORTH-STAR.md](./NORTH-STAR.md) Layer 3).

---

## 재현 명령

```bash
make emergence-bench-check
# 또는
make emergence-bench
.venv/bin/python scripts/verify_emergence_bench_reference.py --check
```

출력 `by_category` 표가 위 reference와 **수치 일치**해야 mock 재현 성공.

명시적 비교:

```bash
.venv/bin/python scripts/emergence_bench.py \
  --out /tmp/my-report.json
diff <(jq '.by_category' sessions/_benchmark/reports/emergence-bench-reference-mock-20260706.json) \
     <(jq '.by_category' /tmp/my-report.json)
```

---

## Quickstart 연계 (T1)

| KPI | 기준선 | 문서 |
|-----|--------|------|
| `fork_time_minutes` | 12 (clean clone + install + S1 mock + smoke) | [QUICKSTART.md](./QUICKSTART.md) |
| emergence mock 재현 | `by_category` 일치 | 본 문서 |

T2(외부 fork·PR)는 생태계 지표 — [FORK.md](./FORK.md).

---

## 변경 시 갱신 규칙

1. `emergence-v1.json` 또는 `composite_score` KPI 변경 → reference JSON 재생성 + 본 문서 날짜·표 갱신
2. PR에 `make emergence-bench` 로그 첨부
3. live 실행 결과는 `sessions/_reports/` (로컬)에 보관; committed reference는 mock만 유지

```bash
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/emergence_bench.py \
  --out sessions/_benchmark/reports/emergence-bench-reference-mock-$(date -u +%Y%m%d).json
```
