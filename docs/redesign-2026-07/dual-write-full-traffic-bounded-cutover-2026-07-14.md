# Dual-write Full traffic — bounded cutover + soak — 2026-07-14

> **역할:** Controlled cohort **GO** 이후 다음 Human gate. **Full traffic만** 승인한다. Legacy writer retire는 이 문서에 포함되지 않으며 별도 Human 승인 전까지 **금지**.

## 승인 단계 (의도된 순서)

```text
1. Controlled cohort evidence     ✅ GO (v3d) — cohort run report
2. Human: Full traffic 승인       ← 지금 이 문서
3. Full traffic 운영 데이터 수집  (bounded cutover + soak)
4. Human: Legacy writer retire    (별도 승인 — 이 단계와 분리)
```

| 금지 | 이유 |
| --- | --- |
| 단계 2 없이 unlimited dual-write | cohort 밖 실사용 검증 없음 |
| 단계 4를 단계 2·3에 묶기 | retire는 soak 증거 + 별도 Human 승인 필요 |
| allowlist 없이 공유 process에 flag만 ON | runbook 미준수 → uncontrolled cutover |

## Full traffic vs Controlled cohort

| | Controlled cohort (완료) | Full traffic (이번 승인 대상) |
| --- | --- | --- |
| Traffic | 합성/스크립트 operational 100건+ | **실사용 Room** (dogfood / daily supervisor) |
| Flag | 전용 API process `DUAL_WRITE=1` | 동일 **또는** shared process + **non-empty allowlist** |
| Legacy writer | 유지 | **유지** |
| 성공 기준 | hard_mm=0 · 60분 · duplicate=0 · route quota | soak 창 동안 verify clean + unexplained fail 0 |
| Retire | 금지 | **여전히 금지** |

## Bounded cutover (기본 제안 — Human이 수정 가능)

Human이 아래 값을 그대로 승인하거나 수정한다.

| 항목 | 기본값 | 의미 |
| --- | --- | --- |
| Process 격리 | **전용 uvicorn** (`AGENT_LAB_MISSION_DUAL_WRITE=1`, allowlist **비움**) | dogfood/UI traffic만 이 포트로 |
| 세션 범위 | 신규 Room 세션만 (기존 `dw-c*` cohort 세션 혼입 금지) | evidence 창 오염 방지 |
| Soak | **≥15 Room turns** (캘린더 일수 아님) | dogfood/supervisor 실사용 turn 수 우선 |
| Verify | turn 진행 중·종료 시 `verify --cohort` + journal audit | hard_mm=0 · duplicate=0 |
| Rollback window | flag OFF + 프로세스 재시작 · **≤15분** | soak 중 언제든 |
| Stop 조건 | unexplained hard_mm · `mission_journal_missing` · material duplicate · rollback 실패 **1건이라도** | 즉시 OFF |

### 대안 (공유 process)

전용 process가 불가하면:

```bash
export AGENT_LAB_MISSION_DUAL_WRITE=1
export AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS=<comma-separated active dogfood session ids>
```

allowlist는 **비우면 안 된다**. 세션을 추가·제거할 때마다 재시작 없이 env가 반영되므로, soak ledger에 allowlist 스냅샷을 남긴다.

## Soak 중 수집 (단계 3)

매일 (또는 **Room turn 종료 시**) ledger에 기록:

1. `/api/health/daemon` → `dual_write.operations` 카운터 스냅샷  
2. `scripts/mission_dual_write_verify.py --sessions sessions/ --cohort` (`AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS`=당일 active set)  
3. `scripts/mission_dual_write_journal_audit.py --sessions sessions/ --cohort`  
4. unexplained mismatch / missing write / duplicate ≥1 → **즉시 rollback**  
5. Room session id · route (plan/execute/inbox) · Human note

산출물 권장 경로: `/tmp/agent-lab-dw-full-traffic-YYYYMMDD/` 또는 `sessions/_reports/dual-write-soak-*.md` (gitignored).

## Rollback (단계 2–3 공통)

```bash
# 전용 process
AGENT_LAB_MISSION_DUAL_WRITE=0  # 재시작 필수
# 신규 세션: journal 미생성 확인
# 기존 mirrored 세션: legacy route 정상 확인
.venv/bin/python scripts/mission_dual_write_rollback_smoke.py \
  --sessions sessions --mirrored-session <one-mirrored-session-id>
```

Legacy writer는 건드리지 않는다. Mission journal은 삭제하지 않는다.

## Human 승인 카드 (단계 2)

아래를 복사해 승인 메시지로 쓰거나, 값을 고친 뒤 승인한다.

```text
[Full traffic — bounded cutover 승인]
- Process: 전용 uvicorn :8765 (또는 shared + non-empty allowlist)
- Soak: ≥15 Room turns (캘린더 일수 아님)
- Legacy writer: 유지 (retire 비승인)
- Stop: unexplained hard_mm / mission_journal_missing / duplicate / rollback fail → 즉시 OFF
- Rollback window: ≤15분 (재시작 1회)
승인일 / 승인자: 2026-07-14 (Human) — turn-count soak (≥15)
```

**이 카드 승인 = 단계 4(retire) 승인이 아니다.**

## 단계 4 이후 (이 문서 범위 밖)

Soak ledger가 깨끗하면 **별도** Human 승인으로:

- legacy writer retire 일정
- Mission 단일 write authority 승격
- irreversible cleanup 범위

권위: [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md) · [NOW](../NOW.md).

## 관련 증거

- [cohort run report](./dual-write-cohort-run-report-2026-07-13.md) — **v3d GO**
- [controlled cohort runbook](./dual-write-controlled-cohort-runbook-2026-07-13.md)
- [cutover scope limitations](./dual-write-cutover-scope-limitations-2026-07-13.md)
