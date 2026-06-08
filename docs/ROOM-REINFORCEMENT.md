# Room 실효성 보강 계획

> **Status (2026-06):** Room **implementation queue is empty**. Phase E–H + Phase I + H-P1–P4 + R-P0/P1 + UX-P2 + ops-P0/P2 **shipped**. Evidence: [`EXTERNAL-REFS-TRACEABILITY.md`](EXTERNAL-REFS-TRACEABILITY.md), [`STABILITY.md`](STABILITY.md), `scripts/smoke_room.py` (**20** regression baselines).  
> **Phase I:** M0–M4 — [`EXECUTE-WORKTREE-REFORM.md`](EXECUTE-WORKTREE-REFORM.md). Live: [`LIVE-CURSOR-WORKTREE-DRY-RUN.md`](LIVE-CURSOR-WORKTREE-DRY-RUN.md), `make live-worktree-dry-run`.  
> 아래 Phase E–H 본문은 **설계·배경**; shipped 여부는 위 추적 문서가 canonical.

> 목표: "3명이 같은 문서 보고 말만 더 하는 구조"에서 → 분업·게이트·검증 가능한 산출로 이동,
> 단일 에이전트+subagent / CC Agent Team 대비 이득이 재현 가능하게 된다.

---

## 성공 기준 (6개월 관점)

| 지표 | 현재 | 목표 |
|------|------|------|
| 교차 검증 턴 비율 | ✅ E-smoke: `challenge_revises_metric` CI smoke 고정 | 회귀 fixture에서 ≥1건 CHALLENGE→수정 자동 검출 |
| BLOCK/CHALLENGE가 다음 행동 변경 | ✅ E-smoke: `objection_blocks_execute` + challenge task block CI smoke 고정 | execute·consensus·task claim 중 ≥1 경로 hard 연동 |
| 에이전트 비대칭 컨텍스트 | ✅ F-R3/F-R3-ops: `capability_cwd` meta 비대칭을 fixture/smoke + 실사용 KPI로 누적 | ≥2 에이전트 서로 다른 cwd/툴 블록 |
| 비용 대비 | ~3× 호출 | ✅ H2: quick/analyze는 낮은 호출 유지, composer turn hint |
| Human 신뢰 | ✅ H1: `## 에이전트별 기여` / `## 미해결 이의` (scribe enrichment) | plan에 에이전트별 기여·미해결 BLOCK 섹션 유지 |

---

## Baseline (이미 있음 — 보강의 토대)

Phase 1–3 + Sprint A–D에서 구축된 것:
tasks, execute gate, consensus task ENDORSE, turn lead, discuss/plan 분리, provenance, mailbox, server hooks.

`docs/STABILITY.md` Verify 항목을 회귀 세트로 고정한다.

**원칙: 보강은 새 축을 얹는 것이지, plan/execute/task를 다시 짜는 것이 아니다.**

---

## 전략 축 (4트랙)

| 트랙 | 한 줄 | "team 넘어섬"에 기여 |
|------|-------|---------------------|
| E — 대화 Hard Gate | 말 → 상태 기계에 binding | BLOCK이 진행·실행을 막음 |
| F — 비대칭 에이전트 | 에이전트별 다른 입력·권한 | 진짜 multi-source |
| G — 산출물 파이프 | 도구 결과가 다음 에이전트 입력 | subagent형 깊이 + room 검토 |
| H — 측정·회귀 | 재현·벤치 | 주장을 숫자로 증명 |
| **I — Execute worktree** | action마다 git 격리 · approve=merge | Conductor급 실행 신뢰 (Room과 별 층) |

---

## 사전 피드백 레지스트리 (Conductor 개혁 이후에도 유효)

Conductor/worktree 계획 수립 **전** 코드 리뷰·벤치 논의에서 확정된 항목.  
**Phase I가 해결하는 것**과 **여전히 Room/H 트랙인 것**을 분리해 둔다 (중복 작업 방지).

### 개혁(Phase I)으로 흡수·확정된 것

| 피드백 | 확정 내용 | 문서 |
|--------|-----------|------|
| execute 시 main tree 오염 | git worktree 기본; approve = **제품 내 merge** | EXECUTE-WORKTREE-REFORM §7 |
| approve ≠ merge (구 snapshot) | worktree 경로만 「Merge 승인」; non-git/override는 별 FSM | §4–5 |
| worktree 실패 시 자동 snapshot degrade | **금지** — fail closed + Human override(예외) | §4.3 |
| plan action마다 repo 다름 | action별 `git_root` 탐지; multi-root → block | §4.5 |
| Conductor 격리 vs Room 합의 | **합의=Room · 격리=worktree** — 토론 구조는 유지 | §0, §1.2 |

### 여전히 유효 — Room / Discuss 트랙 (Phase I가 대체하지 않음)

| 피드백 | 현재 상태 | 우선순위 | 담당 모듈 |
|--------|-----------|----------|-----------|
| **CLI retry 없음** (429/timeout → 턴 실패) | ✅ R-P0: 공통 retry 정책 적용 | **P0** | `cli_retry.py`, `claude_cli.py`, `codex_cli.py` |
| **Partial turn** (1 agent fail ≠ 전체 fail) | ✅ R-P0: 일반 discuss/plan partial 저장 | P0–P1 | `room.py`, `RoomChat.tsx` |
| **F2 R2 비대칭** — full `recent`/`peer` + artifacts 힌트만 | ✅ R-P1: Cursor R2 artifact-only 강제 | **P1** | `context_bundle.py`, `room_artifacts.py` |
| Cursor bridge 끊김 시 fallback 약함 | ✅ Room P1: bridge 실패 원인·degraded 상태·Cursor 제외/재연결 fallback 표시 | P1 | `cursor_bridge.py`, health |
| **E4 discoverability** — resolve API·TaskBar **있음**; Composer/plan 노출 약함 | ✅ UX-P2: Composer/plan resolve 경로 노출 | P2 UX | `RoomTaskBar`, `PlanExecutePanel`, `ChatComposer` |
| vs CC/subagent — **실행·복구** 비교 문서 | ⬜ Phase I 후 **재평가 (문서만, 티켓 없음)** | — | — |

**F2 R-P1 완료:** `research_mode`/`specialist` Cursor R2는 `context_mode: artifact_only`로 전환한다. `recent`는 이번 Human 질문 요약만, `peer`/R1 bridge는 비우고, Codex/Claude R1은 artifacts summary/path/body cap으로만 전달한다. R1, non-Cursor R2, analyze/discuss 기본 경로는 full context 유지.

### 여전히 유효 — 측정·운영 트랙 (H + 플랫폼)

| 피드백 | 현재 상태 | 우선순위 | 담당 |
|--------|-----------|----------|------|
| `score_session.py` CI·KPI 미연결 | ✅ H-P1: CI/Makefile regression score 연결 | P1–P2 | H4, Makefile/CI |
| 10 시나리오 벤치 | ✅ H-P2: room R1–R5 catalog + execute fixture cross-ref | P2 | `sessions/_benchmark/`, H3 |
| DELEGATE **LLM 호출 수** ≤2N 검증 | ✅ H-P2: mock replay call count 고정 | P2 | `tests/test_room_delegate_replay.py` |
| Cursor bridge degraded fallback shape | ✅ H-P3: `bridge_degraded_health` fixture + smoke/API pytest 고정 | P1–P2 | `smoke_room.py`, health |
| BLOCK/CHALLENGE governance smoke | ✅ E-smoke: `objection_blocks_execute`, `challenge_revises_metric` in `smoke_room.py` | P1–P2 | `tests/test_smoke_room_governance.py` |
| Mailbox / specialist cwd smoke | ✅ H-P4: `mailbox_handoff`, `specialist_asymmetric_cwd` in `smoke_room.py` | P2 | `tests/test_smoke_room_governance.py` |
| 실사용 주간 KPI / M4 | ✅ H4-weekly: `score_sessions_weekly.py`, `make score-weekly` | H4 | `session_score_weekly.py` |
| `@app.on_event` deprecation | ✅ ops-P0: FastAPI lifespan 적용 | P0 ops | `app/server/main.py` |
| `main.py` ~1.1k줄 라우터 분리 | ✅ ops-P2: APIRouter 도메인 분리 | P2 ops | `app/server/routers/` |

### 피드백으로 **폐기·수정**된 주장 (문서에 남기지 않음)

| 과거 주장 | 실제 |
|-----------|------|
| artifact가 context에 **미연결** | P2에서 `context_bundle` 연결됨 (`tests/test_room_artifacts.py`) |
| E4 resolve **UI 없음** | `RoomTaskBar` 수용/기각 + API 존재 |
| `sessions/*` gitignore **미처리** | `.gitignore` + `_regression/` only |

---

## Phase I — Execute worktree (Conductor 레퍼런스)

**문제:** P0–P3까지 Room **합의·게이트**는 올랐으나, execute는 snapshot in-place라 Conductor/CC 대비 **통합 전 main 오염·approve 의미 불일치**.

**한 줄:** plan action 1건 ≈ worktree 1개 → dry-run → Human diff → **제품 내 merge** → GC.

| M단계 | 내용 | 상태 |
|-------|------|------|
| M0 | `plan_execute_git/worktree/merge` + pytest | ✅ + live Go/No-Go script |
| M1 | `run_dry_run` / `resolve_execution` 연동 | ✅ |
| M2 | PlanExecutePanel Merge·conflict | ✅ |
| M3 | isolation override · apply(non-git) | ✅ |
| M4 | merge KPI · orphan GC · room retry (R-P0) | ✅ |

전체 설계·FSM·API: **[EXECUTE-WORKTREE-REFORM.md](EXECUTE-WORKTREE-REFORM.md)**

**CC/Conductor 비교 (확정 포지션):**

- **Agent Lab 우위:** plan 자동 분해, objection→execute 409, provenance, pre_execute, cross-action BLOCK.
- **Conductor/단일 에이전트 우위(개혁 전):** 실행 격리·retry·tool loop 깊이 → **Phase I가 격리만 닫음**; retry·F2는 Room 트랙.

---

## Phase E — 대화·합의 Hard Gate

> **✅ Shipped:** E1–E4, E-smoke — `room_objections.py`, plan execute 409, resolve API/UI, `sessions/_regression/objection_blocks_execute/`, `challenge_revises_metric/`.

**문제 (배경):** ENDORSE/BLOCK이 채팅 장식에 가깝고, BLOCK은 앵커 리셋만 함.

> **범위 주의:** E2는 `plan` 모드 하나에서만 먼저 검증. 4개 모드 동시 적용 시 엣지 케이스 폭증.

### E1. run.json objection 레지스트리

envelope BLOCK / CHALLENGE(refs 포함)를 harvest → `objections[]`

```json
{
  "id": "obj-1",
  "from": "claude",
  "target_ref": "plan_action:1",
  "act": "BLOCK",
  "body": "근거 없는 수치",
  "status": "open",
  "turn": 3
}
```

UI: 작업 바에 미해결 이의 배너 (consensus blocker와 동일 패턴).

완료 조건: BLOCK 1건 → Human이 resolve 전까지 linked plan_action execute **409**.

### E2. 턴 정책 (plan 모드 우선)

| 모드 | BLOCK 효과 |
|------|-----------|
| **plan** | ✅ scribe가 objection 섹션 반영; BLOCK된 action을 지금 실행에서 금지 |
| **discuss** (synthesize, non-plan) | ✅ **E2b:** scribe skip + `## 미해결 이의` only (`should_skip_scribe_for_open_objections`) |
| **analyze** (synthesize + open objections) | ⬜ **후순위 (E2-analyze):** discuss와 동일 정책 적용 여부·회귀 미정 |
| ♾️ | ✅ substantive→앵커 리셋 + `consensus_incomplete` reason `open_objections` |

### E3. CHALLENGE → follow-up 강제 (soft→semi-hard)

CHALLENGE + ref가 task/plan action이면:
- 해당 task `status = blocked` (새 상태) 또는 `needs_revision`
- owner에게만 다음 턴 payload에 "반드시 AMEND 또는 근거" 블록 주입

완료 조건: 회귀 `sessions/_regression/challenge_blocks_execute/` — CHALLENGE 후 dry-run 거부.

### E4. Human override

```
POST /api/objections/{id}/resolve
{ "verdict": "wontfix" | "accepted", "note": "..." }
```

audit: `resolved_by: human`, timestamp.

**완료:** Composer/plan dry-run 409와 selected plan action BLOCK에서 TaskBar resolve 경로로 이동한다.

---

## Phase F — 비대칭 에이전트

> **✅ Shipped:** F1 `agent_capabilities`, F2 R-P1 artifact-only, F3 specialist preset, F4 permissions UX, F-R3 — `room_agent_capabilities.py`, `context_bundle.py`, smoke `specialist_asymmetric_cwd`.

**문제 (배경):** 동일 context_bundle → "셋이 같은 방".

> **선행 확인:** `session_setup.py`와 `app_config.py` 두 레이어의 merge 순서를 확인한 뒤 F1 작업. 확인 없이 진행 시 per-session cwd 설정이 조용히 override됨.

### F1. Agent capability profile

run.json 또는 session meta에 추가:

```yaml
agents:
  cursor: { tools: [sdk_edit], cwd: pipeline }
  codex:  { tools: [codex_sandbox], cwd: repo }
  claude: { tools: [read_only_dirs], external: [] }
```

`build_agent_context_bundle`이 agent별로 다른 workspace_lines, tool preamble, 금지 목록을 주입.

### F2. 정보 비대칭 (선택 턴)

Research turn preset:
- Claude/Codex만 외부·sandbox 결과를 `artifacts[]`에 JSON 저장
- Cursor R2는 artifacts만 보고 패치 제안 (전체 chat 재주입 최소화)

### F3. 기본 room preset "분업 토론" (turnProfile: specialist)

| 단계 | 호출 | 역할 |
|------|------|------|
| R1 | Codex | 분해·검증 계획 (텍스트 or sandbox) |
| R1 | Claude | 리스크·반증 |
| R2 | Cursor | R1 artifact + challenge 반영 (권한 on일 때만 SDK) |

Composer에 「분업」 프로필 추가.

완료 조건: 동일 주제에서 F off vs on — 회귀 diff가 서로 다른 cwd 경로를 payload meta에 기록.

### F4. 권한 UX

- 세션 시작 시 "이번 세션 분업" 토글 → permissions 템플릿 일괄 적용
- health에 "cursor: sdk / codex: cli / claude: read-only" 표시

---

## Phase G — 산출물 파이프

> **✅ Shipped:** G1 `artifacts[]`, G2 `pre_execute`/`pre_verify`, G3 delegate — `room_artifacts.py`, `room_hooks.py`, `room_delegate.py`, fixtures + `tests/test_room_delegate_replay.py`.

**문제 (배경):** R1 병렬 = independent 3 calls; 상호 참조는 말뿐.

> **G2 선행 조건:** Human이 approve UI에서 pre_verify 중간 단계를 인지할 수 있도록 UI 스케치를 먼저 확정. 확정 없이 hooks.toml 확장 시 클릭 흐름 파손 위험.

### G1. artifacts[] 1급 시민

```json
{
  "id": "art-1",
  "producer": "codex",
  "kind": "log | diff | table | file_ref",
  "path": "sessions/.../artifacts/result.json",
  "turn": 2,
  "refs": ["plan_action:1"]
}
```

harvest: Codex/Cursor CLI stdout 요약, Human 업로드 연동.

### G2. Execute 전 검증 체인 (semi-automated)

```
plan ## 지금 실행
  → (optional) Codex: verify script in sandbox → artifact
  → Cursor: dry-run patch
  → Human approve
```

`plan_execute.py`에 `pre_verify_hook` 이벤트 (기존 hooks.toml 확장: `pre_execute`).

### G3. Scoped delegate (room 내부)

Human 또는 턴 리드가 `DELEGATE codex: "백테스트만"` 한 줄
→ 단일 에이전트 1회 호출, 결과만 artifacts + peer 요약.

전체 3N 라운드 대신 비용 통제.

완료 조건: quant 회귀 시나리오 — artifact에 수정 로그 + plan ref 일치.

**M3 성공 기준 명세:** delegate가 해당 라운드를 완전히 대체할 때만 "LLM 호출 수 ≤ 2N" 카운트. delegate 이후 room discuss가 붙으면 별도 라운드로 집계. H-P2 mock replay에서 `DELEGATE codex`가 agent invocation 1회와 `kind: delegate` artifact를 남기는지 검증한다.

---

## Phase H — Scribe·비용·측정

> **✅ Shipped:** H1 scribe enrichment, H2 composer turn hint, H3 smoke 20 baselines + benchmark catalog (H-P2), H4 `score_session` + weekly (H-P1/H4-weekly).

**문제 (배경):** 3N 비용, Scribe가 에이전트 기여를 흡수.

### H1. Scribe 입력 분리

- Scribe에 에이전트별 diff 요약만 전달 (전문 재토론 X)
- plan 섹션 추가: `## 에이전트별 기여 (자동)` / `## 미해결 이의`

### H2. Composer turn hint (비용 안내)

- [x] 전송 전: 모드·인원·라운드 한 줄 hint (`composerTurnHint`)
- [x] 기본 프로필은 analyze=1R 유지 (현행 존중)
- ~~체크박스 opt-in 전 Send 비활성~~ — **제거됨** (2026-06)

### H3. 회귀·벤치 패키지

`sessions/_regression/` 확장:

| fixture | 검증 |
|---------|------|
| `objection_blocks_execute` | ✅ smoke/CI: BLOCK → plan action execute gate |
| `challenge_revises_metric` | ✅ smoke/CI: CHALLENGE → task blocked |
| `specialist_asymmetric_cwd` | ✅ smoke/CI: specialist + asymmetric `cwd_role` + `capability_cwd` meta |
| `mailbox_handoff` | ✅ smoke/CI: unread mailbox handoff |
| `sessions/_benchmark/analyze_1r_three_views` | R1 duplicate speech KPI |
| `sessions/_benchmark/plan_now_actions` | R2 `## 지금 실행` parser shape |
| `sessions/_benchmark/delegate_codex` | R4 delegate metadata/artifact fixture |
| `sessions/_benchmark/ten_turn_kpi_stub` | R5 score_session key shape |

CI: `pytest tests/ -q` + `scripts/smoke_room.py` (20 baselines) + `check_worktree_orphans.py` + `score_session.py --json` fixture smoke (LLM/secrets 없음).

### H4. 세션 품질 스코어 (offline)

`scripts/score_session.py`:
- objection 해결률
- execute 1회 성공률
- partial turn 비율
- specialist `capability_cwd` 비대칭률
- ref 유효률
- 중복 발화률

주간 리포트: `python scripts/score_sessions_weekly.py` 또는 `make score-weekly` — 실사용 `sessions/*` 롤업 + M4 마일스톤(objection ≥80%, execute retry <30%) + specialist cwd 비대칭률. `--include-fixtures`로 회귀 샘플 검증. H-P1에서 단건 `score_session` CI smoke 연결됨.

---

## 우선순위·순서

**완료:** P0-a~d, P1 E/F/G(대부분), P2, P3 — 아래 표는 **이후** 우선순위 (사전 피드백 + Phase I 반영).

| 순위 | 항목 | 이유 | 기간 |
|------|------|------|------|
| ~~**I-M0**~~ | worktree spike + Cursor cwd Go/No-Go | ✅ 완료 — pytest + (선택) live SDK | — |
| ~~**I-M1–M4**~~ | dry-run/merge/UI/isolation/KPI | ✅ 완료 — PR #1–#4, M4 orphan/score | — |
| ~~**Room P1**~~ | Cursor bridge degraded fallback | ✅ 완료 — PR #13 | — |
| ~~**H-P3**~~ | bridge degraded CI fixture | ✅ 완료 — PR #14 | — |
| ~~**E-smoke**~~ | objection/challenge smoke | ✅ 완료 — PR #15, 14 baselines | — |
| ~~**H-P4**~~ | mailbox + specialist cwd smoke | ✅ 완료 — 16 baselines | — |
| ~~**H4-weekly**~~ | 실사용 KPI rollup + M4 gates | ✅ 완료 — `score_sessions_weekly.py` | — |
| ~~**R-P0**~~ | CLI retry + partial turn | ✅ 완료 — consensus ENDORSE 루프는 strict 유지 | — |
| ~~**R-P1**~~ | F2 R2 context slimming (`recent`/`peer` truncate) | ✅ 완료 — Cursor R2 artifact-only | — |
| ~~**H-P1**~~ | `score_session` CI + merge/objection KPI | ✅ 완료 — regression smoke/score/orphan guard in CI | — |
| ~~**H-P2**~~ | 벤치 10 시나리오 (room + execute); mock replay for delegate | ✅ 완료 — room catalog + execute cross-ref + delegate replay | — |
| ~~**H2**~~ | Composer turn hint | ✅ 완료 — `composerTurnHint` 한 줄 | — |
| ~~**ops-P0**~~ | FastAPI lifespan | ✅ 완료 — startup hook lifespan 이관 | — |
| ~~**ops-P2**~~ | `main.py` 라우터 분리 | ✅ 완료 — FastAPI app 조립만 유지 | — |
| ~~**UX-P2**~~ | E4 resolve Composer/plan 노출 | ✅ 완료 — dry-run 409 + plan BLOCK에서 이의 해결 CTA | — |
| ~~P0-b/c/d~~ | objections, execute 409, TaskBar resolve | ✅ 완료 | — |

---

## 마일스톤

**M1 (E 완료):** BLOCK 1건으로 execute 차단 + UI에서 resolve → 재시도 성공 (회귀 green)

**M2 (F 완료):** 분업 preset 세션에서 payload meta상 서로 다른 cwd/툴 + artifact 1건 이상 교환

**M3 (G 완료):** delegate 1회 + execute approve까지 Human 클릭 ≤ 기존 대비 동일, LLM 호출 수 ≤ 2N (delegate가 라운드 대체 시 한정)

**M4 (H 완료):** 4주 연속 실사용 세션 스코어 — objection 해결률 >80%, execute 재시도율 <30%

---

## 하지 말 것 (범위 통제)

- CC Agent Team 프로세스 클론 (별도 `.claude` 팀 프로세스) — in-process 오케스트레이션 유지
- 매 턴 무조건 3인 풀라운드 — 비용 폭주, analyze 기본값 유지
- `plan.md` 제거 — Human 계약·Telegram 고정 메시지 역할 유지 (Scribe 입력·이의 섹션은 개선)
- YAML 워크플로 엔진 전면 도입 — 01-CONTROLLED-WORKFLOW Phase 3와 충돌; Room 보강 후 재평가

---

## 다음 액션 (통합 로드맵)

**Shipped (2026-06):** Phase I M0–M4, Room P0/P1, F2 R-P1, H-P1/H-P2/H-P3, H2, E-smoke (20 smoke baselines), UX-P2, ops-P0/P2, EXTERNAL-REFS (Layers 1–5, CON-diff, CENT/MD/CC).

**다음 후보 (코드 작업 — 완료, 이력):**

1. ~~**H-P4**~~ — `mailbox_handoff`, `specialist_asymmetric_cwd` smoke ✅
2. ~~**실사용 KPI**~~ — `score_sessions_weekly.py` + `make score-weekly` + M4 gates ✅
3. ~~**Live execute**~~ — `scripts/live_cursor_worktree_dry_run.py` + `docs/LIVE-CURSOR-WORKTREE-DRY-RUN.md` ✅
4. ~~**F 비대칭**~~ — payload meta `capability_cwd` 실세션 벤치 (R3) — smoke/benchmark 확장 ✅
5. ~~**F-R3-ops**~~ — `capability_cwd` 비대칭을 `score_session`/weekly KPI에 누적 ✅
6. ~~**H4-ops**~~ — weekly M4 + F-R3 Markdown/JSON 운영 artifact export ✅
7. ~~**ops-verify**~~ — `make verify-ops` 수동 운영 점검 타깃 + report path 출력 ✅
8. ~~**ops-runbook-live**~~ — Tier B live worktree runbook + `make verify-ops-live` ✅
9. ~~**Tier C live merge**~~ — disposable repo approve→merge operator runbook + `make verify-ops-live-merge` ✅
10. ~~**H4-ops last-live**~~ — weekly ops summary에 Tier B/C 최신 live GO/NO_GO 표시 ✅
11. ~~**external-refs traceability**~~ — `EXTERNAL-REFS-TRACEABILITY.md` plan ↔ fixture/smoke 매트릭스 ✅
12. ~~**LC-L3 execute_verify_loop**~~ — mock `verify_after_merge` + oracle regression fixture smoke ✅
13. ~~**LC-L3-runtime**~~ — merge response `verify_after_merge` evidence + reverify API/UI badge ✅
14. ~~**LC-L3-agent-repair**~~ — Oracle FAIL → Cursor/Codex repair worktree → re-merge → Oracle 재검증, 최대 2회 ✅
15. ~~**CENT-durable**~~ — `completed_steps[]` resume skip ✅
16. ~~**MD-PLATFORM / MD-PROJECT / MD-P3**~~ — PLATFORM + PROJECT + AGENTS/SHARED injection ✅
17. ~~**CC-dev-tool**~~ — hooks, rules, skills ✅
18. ~~**CON-diff**~~ — hunk inline revise ✅
19. ~~**PI-executed**~~ — merged diff → `sessions/<id>/executed/` ✅
20. ~~**LC-L5**~~ — goal-driven session loop (`docs/GOAL-LOOP.md`) ✅

**다음 후보 (후순위 코드, 선택):**

| ID | 내용 | 비고 |
|----|------|------|
| **E2-analyze** | analyze + synthesize + open objections 시 plan/scribe 정책 | discuss E2b와 동일 처리할지 결정 + 회귀 1건 |
| **CC-compare** | vs CC/subagent·Conductor 포지션 비교 1페이지 | 문서만; 제품 변경 없음 |

**다음 후보 (운영·워크스페이스, 코드 티켓 없음):** 주기적 `make verify-ops-live` / Tier C; opt-in live env 스모크; `make score-weekly`로 M4 실사용 KPI; 워크스페이스 MD는 [`MD-SYSTEM-DESIGN.md`](MD-SYSTEM-DESIGN.md) §워크스페이스 연동; 제품·UX는 TRACEABILITY 외 로드맵.

~~**Room P0**~~ · ~~**F2 R-P1**~~ · ~~**H-P1/H-P2/H-P3/H-P4**~~ · ~~**H2**~~ · ~~**E-smoke (20)**~~ · ~~**ops lifespan/router**~~ · ~~**UX-P2**~~ · ~~**Phase I M1–M4**~~ — 완료.
