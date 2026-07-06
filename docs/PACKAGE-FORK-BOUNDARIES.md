# Package fork boundaries (N8)

> **Status:** 2026-07-06 · **선행:** F12 `agent_lab.core` (순환 0) ✅  
> **관련:** [FORK.md](./FORK.md) · [EMERGENCE-BENCH.md](./EMERGENCE-BENCH.md) · ADR [NORTH-STAR.md §3.5](./NORTH-STAR.md)

외부 fork가 **한 덩어리 없이** 가져갈 수 있는 경계. 5모트(BLOCK→409, worktree, Oracle, run.json 감사, Human Inbox)는 모든 경계에서 유지.

---

## 1. 분리 가능 단위

| 단위 | 경로 | 단독 fork 시나리오 | 의존 |
|------|------|-------------------|------|
| **Core contracts** | `src/agent_lab/core/` | 타입·루프-as-data만 재사용 | stdlib only |
| **Oracle verify** | `src/agent_lab/oracle_core.py`, `plan/execute_verify.py` | diff 검증 microservice | plan execute hooks |
| **Worktree execute** | `src/agent_lab/plan/worktree.py`, `plan/execute*.py` | 격리 실행 라이브러리 | git, run meta |
| **Room consensus** | `src/agent_lab/room/` | 합의·objection만 | agents, runtime |
| **Mission loop** | `src/agent_lab/mission/` | FSM 오케스트레이션 | plan, run meta |
| **Wisdom / feedback** | `wisdom/`, `feedback_*`, outcomes ledger | 학습·KPI만 | sessions layout |

**권장 fork 패턴:** 위 단위 중 **1개 + core** 만 가져가고, 나머지는 adapter로 stub.

---

## 2. 분리 불가 (모놀리식 유지)

| 영역 | 이유 |
|------|------|
| `app/server/` FastAPI 전체 | UI·API·Room 런타임 한 제품 |
| Human Inbox + execute gate | 5모트 — 우회 fork 금지 |
| `run.json` F4 패치 규율 | 감사 trail 단일 SSOT |

---

## 3. 검증 명령 (fork 후)

```bash
make layer-cycles-check          # core DAG 유지
make quickstart-verify           # T1 mock 미션 경로
make emergence-bench-check       # 창발 bench 재현
python scripts/smoke_room.py     # regression + _examples
```

---

## 4. Layer 3 닫힘 (분리 가능 기둥)

| # | 조건 | 상태 |
|---|------|------|
| 1 | F12 core 추출 · no 2-cycle | ✅ |
| 2 | 본 문서 + [FORK.md](./FORK.md) | ✅ |
| 3 | fork 후 `quickstart-verify` 통과 | T1 (외부 재현) |
| 4 | 단위별 추출 예제 repo | **잔여** (선택 — 별도 샘플 repo) |

live emergence 증명·T2(외부 PR)는 [REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md) · 생태계 지표 — 코드만으로 닫히지 않음.
