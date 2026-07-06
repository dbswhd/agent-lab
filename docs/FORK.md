# Fork guide

> **Audience:** Agent Lab을 자기 워크플로·제품에 맞게 fork하는 maintainer  
> **선행:** [QUICKSTART.md](./QUICKSTART.md)로 T1 재현 완료 후 fork 권장

---

## 1. Fork vs clone

| | clone | fork |
|---|-------|------|
| 목적 | upstream 기여·로컬 dogfood | **자기 remote**에서 독립 발전 |
| upstream 동기화 | `git pull origin main` | `git remote add upstream` + merge/rebase |
| 브랜치 정책 | upstream `main` 추종 | 팀 정책 자유 (protected `main` 권장) |

```bash
# GitHub UI에서 Fork 후
git clone https://github.com/<you>/agent-lab.git
cd agent-lab
git remote add upstream https://github.com/dbswhd/agent-lab.git
```

---

## 2. 최소 커스터마이즈 경로

fork 직후 **코어 로직 변경 없이** mock 미션이 돌아가는지 확인:

```bash
make install
export AGENT_LAB_MOCK_AGENTS=1
make dogfood-suite-mock ONLY=S1
python scripts/smoke_room.py
```

`fork_time_minutes` 목표 ≤ 15 — [QUICKSTART.md](./QUICKSTART.md) §5.

---

## 3. 안전한 커스터마이즈 영역

| 영역 | 경로 | 비고 |
|------|------|------|
| 에이전트 프롬프트 | `src/agent_lab/agents/prompts.py` | Room 톤·역할 |
| Run profile | `src/agent_lab/run/profile.py` | `fast`/`balanced`/… 기본값 |
| Skills | `.claude/skills/` | 프로젝트 스킬 (로컬 symlink 가능) |
| Dogfood topics | `sessions/_benchmark/topics/` | eval·bench topic SSOT |
| 예제 미션 | `sessions/_examples/` | 교육용 fixture |
| UI | `web/src/` | Mission OS 콘솔 |

**Human gate 유지:** execute gate 우회·`subprocess` env 전체 상속은 금지 ([CLAUDE.md](../CLAUDE.md)).

---

## 4. 위험 영역 (인간 리뷰 필수)

| 영역 | 이유 |
|------|------|
| `src/agent_lab/plan/` execute gate | 격리·merge·verify 불변 원칙 |
| `src/agent_lab/run_meta.py` / F4 패치 규율 | 턴 중 meta 유실 버그 |
| `src/agent_lab/room/` orchestration | 2-cycle·합의 계약 |
| Trading extension | F5 — `extensions/quant_trading.py` 경계만 |

N6 self-patch 화이트리스트: `.agent-lab/self_patch_allowlist.txt` (초기: skills·프롬프트·preset만).

---

## 5. upstream 동기화

```bash
git fetch upstream
git checkout main
git merge upstream/main   # 또는 rebase — 팀 정책에 따름
make test-fast
make smoke
```

충돌 시 우선순위: **tests + TRACEABILITY + code** ([docs/README.md](./README.md)).

---

## 6. 벤치·KPI 유지

fork 후에도 재현 신뢰를 유지하려면:

```bash
make emergence-bench
# reference와 by_category 비교 — EMERGENCE-BENCH.md §6
make feedback-report JSON=1
```

커스텀 topic은 `sessions/_benchmark/topics/<your>.json` + `--topics`로 분리하고, **emergence-v1.json은 건드리지 않으면** upstream reference와 diff 가능.

---

## 7. T2 — 생태계 신뢰

| 신호 | 의미 |
|------|------|
| 외부 이슈 | 재현 실패·문서 갭 |
| 외부 PR | topic·skill·UI 개선 |
| `fork_time_minutes` 개선 PR | QUICKSTART 경로 단축 |

upstream에 기여 시: mock-only 테스트, `sessions/*` 커밋 금지, `make ci` 통과.

---

## 8. 관련 문서

| 문서 | 내용 |
|------|------|
| [QUICKSTART.md](./QUICKSTART.md) | 15분 mock 미션 |
| [EMERGENCE-BENCH.md](./EMERGENCE-BENCH.md) | bench 프로토콜 SSOT |
| [REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md) | 공개 reference 수치 |
| [PACKAGE-FORK-BOUNDARIES.md](./PACKAGE-FORK-BOUNDARIES.md) | 분리 fork 경계 (N8) |
| [NORTH-STAR.md](./NORTH-STAR.md) | Layer 3 슈퍼 샘플 판정 |
