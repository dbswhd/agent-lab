# Emergence bench protocol (SSOT)

> **Status:** N8 Layer 3 — reproducible bench protocol  
> **Runner:** [`scripts/emergence_bench.py`](../scripts/emergence_bench.py) · `make emergence-bench`  
> **Topic SSOT:** [`sessions/_benchmark/topics/emergence-v1.json`](../sessions/_benchmark/topics/emergence-v1.json)  
> **Reference report:** [`sessions/_benchmark/reports/emergence-bench-reference-mock-20260706.json`](../sessions/_benchmark/reports/emergence-bench-reference-mock-20260706.json)

솔로 에이전트 vs 3-agent Room을 **같은 토픽**으로 비교해 `emergence_delta`를 산출한다.  
"창발이 성능을 올린다"는 주장은 이 프로토콜을 따라 **동일 숫자를 재현**할 때만 유효하다.

---

## 1. 판정 정의

| 항목 | 정의 |
|------|------|
| **solo arm** | `cursor`, `codex`, `claude` 각각 단독 1회 (`consensus_mode=false`) |
| **room arm** | 동일 3 에이전트 Room 1회 (`consensus_mode=true`, `synthesize=true`) |
| **composite** | `score_session` KPI 6종 평균 (방향 통일 후 0..1) — 아래 §3 |
| **max_solo_composite** | 세 solo composite 중 **최댓값** (평균 아님) |
| **emergence_delta** | `room_composite − max_solo_composite` |
| **창발 판정 (토픽)** | `emergence_delta > 0` |
| **가설 (카테고리)** | `deep`·`critical`에서만 `delta_mean > 0` — mock heuristic에서는 **관찰용**; live oracle에서 검증 |

`emergence_delta`는 `score_session` 28지표에 없고 **벤치 리포트 전용**이다 ([EVAL-PROGRAM.md](./EVAL-PROGRAM.md) §1).

---

## 2. Topic 세트 (고정)

**파일:** `sessions/_benchmark/topics/emergence-v1.json` (4 topics)

| category | topic (요약) |
|----------|--------------|
| `quick` | "이거 머지됐어?" + `[cat: quick]` |
| `standard` | 주간 리포트 포맷 팀 합의 |
| `deep` | 수집 파이프라인 스트리밍 vs 배치 |
| `critical` | 세션 스토어 마이그레이션 + 롤백 경로 |

커스텀 세트는 `--topics <path>`로 교체 가능. 리포트에 **사용한 topics 파일 경로**를 기록한다.

`dogfood-v1.json`과 호환: bench는 `{category, topic}`만 소비한다.

---

## 3. Composite score (heuristic judge)

Mock·live 공통 합성식 (`scripts/emergence_bench.py:composite_score`):

| KPI key | higher is better |
|---------|------------------|
| `hybrid_action_rate` | yes |
| `challenge_yield` | yes |
| `ref_validity_rate` | yes |
| `objection_resolution_rate` | yes |
| `duplicate_speech_rate` | **no** (inverted) |
| `partial_turn_rate` | **no** (inverted) |

`null` KPI는 제외 후 남은 값의 산술 평균. 전부 `null`이면 composite `null` → `emergence_delta` `null`.

---

## 4. 시드·환경 (재현 필수)

### Mock (CI-safe, 기본)

```bash
make emergence-bench
# 동일:
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/emergence_bench.py
```

| 변수 | 값 | 비고 |
|------|-----|------|
| `AGENT_LAB_MOCK_AGENTS` | `1` | bench가 mock 시 자동 설정 |
| `AGENT_LAB_CLARIFIER` | `0` | bench가 `setdefault` |
| `AGENT_LAB_INBOX_MODE` | `soft` | bench가 `setdefault` |
| `judge` (리포트) | `heuristic` | mock 라벨 |

**solo_agents (고정):** `["cursor", "codex", "claude"]`

### Live (opt-in, CI 금지)

```bash
AGENT_LAB_EMERGENCE_BENCH_LIVE=1 .venv/bin/python scripts/emergence_bench.py --live
```

| 변수 | 값 |
|------|-----|
| `AGENT_LAB_EMERGENCE_BENCH_LIVE` | `1` (필수) |
| `--live` | 필수 |
| `judge` (리포트) | `oracle` |

### Optional 4th arm (DISPATCH)

```bash
AGENT_LAB_EMERGENCE_BENCH_DISPATCH=1 make emergence-bench
# 또는 --include-dispatch
```

---

## 5. 실행·리포트

```bash
# 기본 (mock, emergence-v1.json)
make emergence-bench

# 명시적 출력 경로
.venv/bin/python scripts/emergence_bench.py \
  --out /tmp/my-report.json

# 세션 폴더 고정 (디버그·재현)
.venv/bin/python scripts/emergence_bench.py \
  --sessions-base /tmp/emergence-sessions \
  --out /tmp/my-report.json
```

**리포트 스키마 (top-level):**

| 필드 | 의미 |
|------|------|
| `generated_at` | UTC ISO timestamp |
| `judge` | `heuristic` \| `oracle` |
| `mock` | bool |
| `solo_agents` | solo arm 에이전트 목록 |
| `topics[]` | 토픽별 `solo`, `room`, `emergence_delta` |
| `by_category` | 카테고리별 `topics`, `delta_mean`, `delta_positive` |

기본 출력: `sessions/_reports/emergence_bench_<ts>.json` (gitignore — 로컬 실행용).  
**공개 기준선:** `sessions/_benchmark/reports/emergence-bench-reference-mock-20260706.json`.

---

## 6. 재현 체크리스트

1. `git clone` + `make install` (Python 3.11+)
2. `make emergence-bench`
3. 리포트 `judge=heuristic`, `mock=true`, `solo_agents` 3종 일치 확인
4. `by_category` 각 행의 `delta_mean`·`delta_positive`를 reference JSON과 비교
5. **mock heuristic:** 절대값 일치 기대 (동일 코드·동일 topic SSOT) — `make emergence-bench-check`
6. **live oracle:** 분산 허용 — 동일 프로토콜·동일 topic으로 재실행 후 추세만 비교

실패 시: `git rev-parse HEAD`, Python 버전, `AGENT_LAB_*` 오버라이드, `--topics` 경로를 이슈에 첨부.

---

## 7. 관련 문서

| 문서 | 내용 |
|------|------|
| [REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md) | 공개 재현 리포트 (reference 수치·해석) |
| [QUICKSTART.md](./QUICKSTART.md) | 15분 mock 미션 · `fork_time_minutes` |
| [EVAL-PROGRAM.md](./EVAL-PROGRAM.md) | dogfood 카탈로그 · eval 3층 |
| [NORTH-STAR.md](./NORTH-STAR.md) §1 Layer 3 | 슈퍼 샘플 판정 기준 |
