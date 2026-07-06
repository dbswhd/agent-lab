# Quickstart — 15분 mock 미션

> **목표:** `git clone` 후 **15분 이내** mock 에이전트로 미션 1개를 완주하고 회귀를 확인한다.  
> **KPI:** `fork_time_minutes` — clone 시작부터 §4 완료까지 (분, 올림).  
> **선행:** emergence bench 재현은 [EMERGENCE-BENCH.md](./EMERGENCE-BENCH.md) 참고.

---

## 필요 환경

| 항목 | 버전 |
|------|------|
| Python | 3.11+ |
| git | 2.x |
| Node | 18+ (UI는 선택) |

에이전트 CLI(Codex/Claude/Cursor)는 **mock 경로에 불필요**합니다.

---

## 1. Clone & install

```bash
git clone https://github.com/dbswhd/agent-lab.git
cd agent-lab
date +%s   # → T0 (fork_time 측정 시작)
make install
```

`make install`은 venv + Python deps + web `npm ci`를 수행합니다.  
첫 실행은 네트워크·머신에 따라 **3–8분**이 일반적입니다.

---

## 2. Mock 환경

```bash
export AGENT_LAB_MOCK_AGENTS=1
export AGENT_LAB_CLARIFIER=0
```

또는 한 줄:

```bash
AGENT_LAB_MOCK_AGENTS=1 AGENT_LAB_CLARIFIER=0 ...
```

---

## 3. Mock 미션 1개 실행

Eval 카탈로그 **S1** (quick 토픽, Human gate 없음):

```bash
make dogfood-suite-mock ONLY=S1
```

**PASS when:** 터미널에 `mock suite report: ... (0 failed/error)` 출력.

세션은 `sessions/` 아래 임시 폴더에 생성됩니다 (gitignore).

---

## 4. 완주 확인

```bash
AGENT_LAB_MOCK_AGENTS=1 python scripts/smoke_room.py
```

**PASS when:** `OK: 38 regression baseline(s) in .../sessions/_regression`

(선택) 방금 만든 세션 점수:

```bash
ls -td sessions/*/ | head -1 | xargs -I{} .venv/bin/python scripts/score_session.py --json {}
```

---

## 5. fork_time_minutes 기록

```bash
make quickstart-verify
# JSON:
.venv/bin/python scripts/verify_quickstart.py --json
```

`fork_time_minutes`는 스크립트 출력의 `fork_time_minutes` 필드 (미션 경로만, install 제외). 기준선 **12** (install 제외 mock 경로는 보통 1분 미만).

---

## 6. 다음 단계

| 목표 | 명령 |
|------|------|
| 예제 미션 fixture 살펴보기 | [sessions/_examples/README.md](../sessions/_examples/README.md) |
| 창발 벤치 재현 | `make emergence-bench` → [EMERGENCE-BENCH.md](./EMERGENCE-BENCH.md) |
| 공개 수치 비교 | [REPRODUCTION-REPORT.md](./REPRODUCTION-REPORT.md) |
| Fork 후 커스터마이즈 | [FORK.md](./FORK.md) |
| UI 개발 서버 | `make dev` → http://127.0.0.1:5173 |

---

## 트러블슈팅

| 증상 | 조치 |
|------|------|
| `make install` 실패 | Python 3.11+, `npm` 설치 확인 |
| dogfood `failed/error` | `AGENT_LAB_MOCK_AGENTS=1` 재확인; `make test-fast` 로컬 회귀 |
| smoke FAIL | `sessions/_regression/` 손상 여부; `git checkout sessions/_regression` |
| 15분 초과 | `ONLY=S1` 단일 토픽 유지; live 에이전트 비활성 |
