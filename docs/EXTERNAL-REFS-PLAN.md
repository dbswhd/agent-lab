# 외부 레퍼런스 분석 및 Agent Lab 적용 계획

> 작성: 2026-06-03  
> 분석 대상: Conductor · Centaur · LazyCodex · Claude Code  
> 목적: 각 시스템의 강점을 Agent Lab에 이식하되, 합의·게이트·provenance 핵심 구조는 유지한다.

> **Stale notice (2026-06):** Part 5 Phase 3 ops items (router split, lifespan, score_session CI, 10-scenario bench) are **shipped**. See **[EXTERNAL-REFS-TRACEABILITY.md](EXTERNAL-REFS-TRACEABILITY.md)** for plan ↔ code ↔ fixture mapping. Layer 3/4 remain future.

---

## 레퍼런스 시스템 한 줄 요약

| 시스템 | 핵심 철학 | Agent Lab에 없는 것 |
|--------|-----------|---------------------|
| **Conductor** | workspace = 격리 단위, PR = 통합 단위 | Diff viewer 인라인 재작업 루프 |
| **Centaur** | 팀 공유 에이전트, Slack-native, K8s 격리 | Durable step (재시작 복구), credential 분리 |
| **LazyCodex** | 완료를 주장하지 말고 Loop → 검증될 때까지 | **Loop 엔진** (Oracle verified completion) |
| **Claude Code** | 개발자 도구 생태계 완성 | CLAUDE.md, hooks, subagent skills, auto-memory |

---

## Part 1 — LazyCodex: Loop가 핵심이다

### 1.1 LazyCodex의 Loop 구조

```
$ulw-plan  ────────────────────────────────────────────────┐
  Socratic interview → codebase 탐색 → gap 분석             │
  → plans/<slug>.md (코드 미변경)                           │
                                                             │
$start-work ─────────────────────────────────────────────── │
  Boulder state (.omo/boulder.json)                         │
  └─ Independent subtasks → parallel subagent fan-out       │
  └─ 5 Evidence Gates:                                       │
       1. plan reread    — 실행 전 플랜 재확인               │
       2. automated test — 자동 검증                         │
       3. manual QA      — 직접 확인                         │
       4. adversarial QA — "이걸 깨보려는" 반증 시도 ★      │
       5. cleanup        — 정리                              │
                                                             │
$ulw-loop ◄──────────────────────────────────────────────── ┘
  Oracle이 검증 → 실패 시 $start-work 재호출
  → 성공할 때까지 (최대 500회 ultrawork / 100회 일반)
  → Boulder state가 "어디까지 했는가" 기록 → 재시작 후에도 재개
```

**핵심 통찰:**
- "완료했습니다"는 에이전트의 주장이고, 완료는 Oracle이 결정한다.
- Loop는 단순 retry가 아니다. 이전 실패의 이유를 state에 기록하고, 다음 이터레이션에서 그 이유를 보고 다른 전략으로 시도한다.
- Boulder state = 이터레이션 간 공유 블랙보드.

### 1.2 Agent Lab의 현재 Loop 구조 (부분 구현)

```
현재 구현된 것:
  consensus loop   — cap_rounds + cap_calls (room_consensus.py)
  parallel_rounds  — Human 1턴 내 최대 4라운드 (room.py:MAX_AGENT_PARALLEL_ROUNDS=4)
  cli_retry.py     — 429/timeout 재시도 (이미 구현됨)
  continue_room_round() — Human이 다음 메시지로 세션 계속

없는 것:
  execute loop     — merge 후 검증 실패 시 에이전트에게 자동 재작업 요청
  adversarial gate — approve 전 반증 시도
  goal-driven loop — "이 목표 달성될 때까지 계속" 모드
  durable loop     — 프로세스 재시작 후 루프 재개
```

### 1.3 Agent Lab에 도입할 Loop 계층

```
Layer 1: CLI Retry Loop (이미 있음 — cli_retry.py)
  에이전트 호출 실패 → 최대 N회 backoff 재시도
  대상: 429, timeout, 일시적 오류

Layer 2: Consensus Loop (이미 있음 — cap_rounds/cap_calls)
  합의 미달 → 다음 라운드 자동 진행
  상한: MAX_AGENT_PARALLEL_ROUNDS=4

Layer 3: Execute Verify Loop (미구현 ★)
  merge 완료 → action.verify 필드 자동 확인
  실패 → 에이전트에게 "검증 기준이 아직 안 됐어: {이유}" 재호출
  상한: MAX_VERIFY_RETRIES=2

Layer 4: Adversarial Gate (미구현 ★)
  dry-run diff 생성 → Claude에게 "이게 실패할 수 있는 이유?" 1회 질문
  결과를 Human approve UI에 표시 (차단은 안 함, 정보 제공)

Layer 5: Goal-Driven Session Loop (미구현, 선택적)
  Human이 목표 설정 → 목표 달성 여부를 Oracle이 판단
  미달성 시 계속 토론 요청 (discuss 루프)
```

### 1.4 Execute Verify Loop 설계 (Layer 3 상세)

```
plan action dry-run
  ↓
Cursor가 worktree에서 작업 + verify follow-up 이미 주입됨
  ↓
Human approve
  ↓
git merge
  ↓
[신규] verify_after_merge(action, merged_paths)
  └─ action.verify 필드를 Claude에게 실제 확인 요청
  └─ "PASS" → 완료 badge
  └─ "FAIL: {이유}" → Human에게 표시 + "에이전트에게 수정 요청" 버튼
         ↓ (Human이 요청 클릭)
         에이전트 재호출 (이유 포함) → 새 worktree dry-run
         → Human re-approve → 재merge → verify 재실행
         (최대 MAX_VERIFY_RETRIES=2)
```

구현 파일:
- `plan_execute_merge.py` — `verify_after_merge()` 추가 (30줄)
- `PlanExecutePanel.tsx` — verification badge + 재작업 버튼
- `app/server/main.py` → `routers/execute.py` — `/execute/{id}/reverify` 엔드포인트

### 1.5 Adversarial Gate 설계 (Layer 4 상세)

```python
# plan_execute.py:run_dry_run() 내부, diff 생성 직후 추가
def _adversarial_check(action: PlanAction, diff: str) -> str:
    """
    LazyCodex adversarial QA 패턴.
    Claude에게 이 diff의 잠재적 문제를 찾게 한다.
    차단이 아닌 정보 제공 — Human이 판단.
    """
    prompt = (
        f"다음 변경을 실행하려 합니다.\n\n"
        f"목적: {action.what}\n"
        f"검증 기준: {action.verify}\n\n"
        f"diff (요약):\n{diff[:2000]}\n\n"
        f"이 실행이 의도와 다르거나 실패할 수 있는 이유를 "
        f"최대 3가지만 간결하게 쓰세요. 없으면 'LGTM'만 쓰세요."
    )
    return claude_cli.invoke("adversarial-reviewer", prompt, scribe=True)
```

Human이 approve 화면에서 diff + adversarial 결과를 같이 봅니다. "LGTM"이면 초록 badge, 문제 발견이면 노란 경고.

---

## Part 2 — Conductor: 격리 실행

### 2.1 현황
Phase I (M0–M4) 완료 → `plan_execute_worktree.py`, `plan_execute_merge.py` 구현됨.  
git worktree 격리 + approve = merge 구조 확립.

### 2.2 남은 것: Diff Viewer 인라인 재작업

**Conductor에 있고 Agent Lab에 없는 것:**
```
현재: diff 전체 표시 → approve / reject 2택
목표: diff의 특정 chunk에 인라인 코멘트 → "이 부분만 다시 짜줘"
      → 에이전트가 해당 chunk만 수정 → re-diff → re-approve
```

구현 파일: `PlanExecutePanel.tsx` + `/api/sessions/{id}/execute/{exec_id}/revise`

**우선순위: P2** (Layer 3 verify loop이 먼저)

### 2.3 Worktree 실행 이력 보존

merge 완료된 worktree의 diff를 `sessions/{id}/executed/` 에 저장해  
"왜 이 코드가 이렇게 됐는가"를 plan.md provenance와 연결.

구현 파일: `plan_execute_merge.py:on_merge_complete()` — 3줄 추가

---

## Part 3 — Centaur: 안정성

### 3.1 현황
`cli_retry.py` 이미 구현됨 (429, timeout, overloaded 패턴 처리).  
subprocess credential 분리는 미구현.

### 3.2 Subprocess Credential 분리

```python
# claude_cli.py / codex_cli.py 공통 패턴 (현재)
result = subprocess.run([...])  # 부모 env 전체 상속

# 목표 — 필요한 키만 전달
_ALLOWED_ENV = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PATH", "HOME",
                "TMPDIR", "TERM", "LANG", "LC_ALL"}

safe_env = {k: v for k, v in os.environ.items() if k in _ALLOWED_ENV}
result = subprocess.run([...], env=safe_env)
```

구현 파일: `claude_cli.py`, `codex_cli.py`, `cursor_bridge.py` — 각 3줄  
**우선순위: P0** (보안 + Centaur 원칙)

### 3.3 Durable Step (Centaur 경량판)

**문제:** uvicorn 재시작 → 진행 중 round 소실.

```python
# run_meta에 completed_steps[] 추가
{
  "completed_steps": [
    {"step": "round_1_codex", "ts": "2026-06-03T...", "msg_idx": 12},
    {"step": "round_1_claude", "ts": "2026-06-03T...", "msg_idx": 13}
  ]
}
```

`_call_one_agent()` 완료 시 `patch_run_meta()`로 즉시 기록.  
재시작 시 `completed_steps`에 있는 에이전트는 스킵하고 재개.

구현 파일: `run_meta.py` + `room.py:_call_one_agent()` — 10줄  
**우선순위: P1**

---

## Part 4 — Claude Code: 개발 도구 생태계

### 4.1 CLAUDE.md (즉시 적용)

`.claude/CLAUDE.md` 또는 루트 `CLAUDE.md`:

```markdown
# Agent Lab 개발 가이드

## 빌드 & 실행
- make dev         — API(8765) + web(5173) 동시 시작
- make api         — API만 (hot-reload)
- make test        — pytest (214 tests, 2.5s)
- make smoke       — mock 스모크
- make smoke-e2e   — E2E 스모크 (MOCK_AGENTS=1)
- make score-session SESSION=sessions/<id>  — 세션 KPI

## 핵심 구조
- src/agent_lab/room.py          — 멀티에이전트 오케스트레이션 (2600줄)
- src/agent_lab/plan_execute*.py — execute gate + worktree + merge
- src/agent_lab/room_objections.py — BLOCK/CHALLENGE → execute 409
- src/agent_lab/cli_retry.py     — CLI 공통 retry (429/timeout)
- app/server/main.py             — FastAPI (~1156줄, routers/ 분리 예정)
- web/src/components/            — React 컴포넌트 40+

## 코드 규칙
- Python: from __future__ import annotations 필수
- 새 라우터는 app/server/main.py에 직접 추가 금지 → routers/ 분리 예정
- 테스트는 mock-only (AGENT_LAB_MOCK_AGENTS=1)
- sessions/* 커밋 금지 (gitignore 처리됨, _regression/만 예외)

## 아키텍처 원칙
- 합의는 Room (discuss/plan), 격리는 worktree (Phase I)
- BLOCK → execute 409 (plan 모드 한정)
- plan.md = 세션 메모리 + execute 계약서 + provenance 앵커
```

### 4.2 Claude Code Hooks (.claude/settings.json)

```json
{
  "hooks": {
    "PostEdit": [
      {
        "matcher": "*.py",
        "hooks": [{
          "type": "command",
          "command": ".venv/bin/python -m ruff check --fix $CLAUDE_EDITED_FILE 2>/dev/null || true"
        }]
      },
      {
        "matcher": "*.tsx",
        "hooks": [{
          "type": "command",
          "command": "cd web && npx prettier --write $CLAUDE_EDITED_FILE 2>/dev/null || true"
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "cd /Users/yoonjong/Projects/agent-lab && .venv/bin/pytest tests/ -q --tb=short -x 2>&1 | tail -5",
          "statusMessage": "pytest 실행 중..."
        }]
      }
    ]
  }
}
```

주의: 이 hooks는 **Claude Code 개발 도구용**이고, `room_hooks.py`(AgentLab 런타임 서버사이드 훅)와 다른 레이어입니다.

### 4.3 Subagent Skills

`.claude/agents/smoke-and-score/SKILL.md`:

```markdown
---
name: smoke-and-score
description: 스모크 테스트 후 가장 최근 세션 품질 KPI 출력
tools: Bash
---

1. AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/smoke_room_e2e.py
2. 가장 최근 sessions/ 폴더 찾기: ls -t sessions | grep -v _regression | head -1
3. make score-session SESSION=sessions/<id>
결과 요약 리포트.
```

`.claude/agents/regression-check/SKILL.md`:

```markdown
---
name: regression-check
description: 회귀 fixture 전체 실행 후 실패 원인 분석
tools: Bash, Read
---

1. .venv/bin/pytest tests/ -q --tb=short
2. 실패 있으면 해당 파일 Read 후 원인 분석
3. 수정 제안
```

### 4.4 Worktree 병렬 개발

Agent Lab 개발 자체에 Claude Code worktree 패턴 적용:

```bash
# 독립적인 두 기능을 동시에 개발
Terminal A: claude --worktree feature-verify-loop    # Layer 3 execute verify
Terminal B: claude --worktree feature-adversarial    # Layer 4 adversarial gate
Terminal C: claude --worktree ops-router-split       # main.py 라우터 분리
```

### 4.5 PROJECT.md — 영속 워크스페이스 메모리 (LazyCodex AGENTS.md 패턴)

```
workspace_root/
└── .agent-lab/
    ├── hooks.toml       — 이미 있음
    └── PROJECT.md       — 신규 (LazyCodex /init-deep 패턴)
```

`PROJECT.md` 내용 (자동 생성 후 Human 편집):

```markdown
# Agent Lab 프로젝트 메모리

## 아키텍처
- Python FastAPI 백엔드 + React/Vite/Tauri 프론트엔드
- 멀티에이전트 Room: Cursor(execute) + Codex(verify) + Claude(risk review)

## 현재 진행 중인 작업
- Phase I (완료): git worktree execute 격리
- Layer 3 (진행): execute verify loop
- R-P0 (진행): CLI retry + partial turn

## 중요한 결정
- BLOCK → execute 409는 plan 모드 한정 (discuss는 soft)
- F2 정보 비대칭은 context 레이어가 아닌 artifacts 파이프로 해결
- Human gate는 설계상 유지 (완전 자율 실행 배제)
```

`context_bundle.py:_workspace_lines_for_agent()`에서 PROJECT.md를 읽어 에이전트 payload에 주입.

---

## Part 5 — 통합 우선순위 및 구현 계획

### 전체 로드맵

```
Phase 0 (즉시, 1일)
  ├─ CLAUDE.md 작성                   [Claude Code]
  ├─ .claude/settings.json hooks 설정 [Claude Code]
  └─ subprocess env 분리              [Centaur]

Phase 1 (1–2주)
  ├─ Layer 4: Adversarial Gate        [LazyCodex]
  │   plan_execute.py + PlanExecutePanel.tsx
  ├─ Layer 3: Execute Verify Loop     [LazyCodex]
  │   plan_execute_merge.py + /reverify API
  └─ Durable Step (completed_steps[]) [Centaur]
       run_meta.py + room.py

Phase 2 (2–4주)
  ├─ PROJECT.md 영속 메모리           [LazyCodex/Claude Code]
  │   context_bundle.py 주입
  ├─ Diff viewer 인라인 재작업        [Conductor]
  │   PlanExecutePanel.tsx
  ├─ session_clarifier plan 모드 강화 [LazyCodex Socratic]
  └─ Subagent skills 2–3개 작성       [Claude Code]

Phase 3 (지속)
  ├─ main.py → routers/ 분리          [운영] ✅ shipped — ops-P2
  ├─ @app.on_event lifespan 마이그레이션 [운영] ✅ shipped — ops-P0
  ├─ score_session CI 연결              [운영] ✅ shipped — H-P1
  └─ 10 시나리오 벤치마크 완성          [운영] ✅ shipped — H-P2 + smoke 16
```

### 우선순위 매트릭스

| 순위 | 출처 | 항목 | 구현 규모 | 임팩트 |
|------|------|------|-----------|-------|
| **P0** | Claude Code | CLAUDE.md 작성 | XS (30분) | 높음 — 즉시 개발 생산성 |
| **P0** | Claude Code | Hooks (ruff + pytest) | XS (10분) | 높음 — 자동 품질 검사 |
| **P0** | Centaur | subprocess env 분리 | XS (3파일 3줄씩) | 중간 — 보안 |
| **P1** | LazyCodex | Adversarial Gate (Layer 4) | S (50줄 Python + 20줄 TSX) | 높음 — False positive approve 감소 |
| **P1** | LazyCodex | Execute Verify Loop (Layer 3) | M (80줄 Python + 40줄 TSX) | 높음 — 완료 신뢰성 |
| **P1** | Centaur | Durable Step (completed_steps) | S (10줄) | 중간 — 재시작 복구 |
| **P2** | LazyCodex | PROJECT.md 영속 메모리 | S (20줄 + 파일 생성) | 중간 — 세션 간 기억 |
| **P2** | Conductor | Diff viewer 인라인 재작업 | L (UI 비중) | 높음 — UX |
| **P2** | LazyCodex | session_clarifier 강화 | S (20줄) | 중간 — 계획 품질 |
| **P2** | Claude Code | Subagent skills | XS (파일 작성) | 중간 — 반복 자동화 |
| **P3** | 운영 | main.py 라우터 분리 | L | ✅ ops-P2 |
| **P3** | 운영 | lifespan 마이그레이션 | S | ✅ ops-P0 |

---

## Part 6 — 경쟁 포지셔닝 업데이트

### Loop 계층 완성 후 포지션

```
Conductor:  격리 실행 후 Human 선택
Centaur:    팀 공유 + durable + K8s
LazyCodex:  loop until verified completion

Agent Lab (목표):
  ┌─ 토론 합의 (Agent Lab 고유)
  ├─ 격리 실행 (Conductor, Phase I 완료)
  ├─ Verify Loop (LazyCodex, Phase 1 예정)
  ├─ Adversarial Gate (LazyCodex, Phase 1 예정)
  ├─ Durable Step (Centaur, Phase 1 예정)
  └─ Provenance + Objection (Agent Lab 고유)
```

### Agent Lab이 유일하게 가진 것 (3가지 조합)

다른 시스템 중 이 세 가지를 동시에 갖춘 시스템이 없습니다:

1. **에이전트 간 합의 추적** — BLOCK이 execute를 막고, CHALLENGE가 task를 blocked로 전환
2. **Plan provenance** — `chat.jsonl#L123`으로 "왜 이 코드가 이렇게 됐는가" 연결
3. **Human-gated execute** — approve가 의미 있는 검토 시점 (rubber stamp 아님)

Loop 계층이 완성되면 "합의로 시작해서 검증될 때까지 반복"이 하나의 세션에서 가능해집니다.

---

## 참고: 현재 구현된 Loop 계층 (확인 필요)

| 계층 | 구현 여부 | 모듈 |
|------|-----------|------|
| Layer 1: CLI Retry | ✅ 구현됨 | `cli_retry.py` |
| Layer 2: Consensus Loop | ✅ 구현됨 | `room_consensus.py:consensus_caps()` |
| Layer 3: Execute Verify Loop | ❌ 미구현 | — |
| Layer 4: Adversarial Gate | ❌ 미구현 | — |
| Layer 5: Goal-Driven Loop | ❌ 미구현 (선택적) | — |
| Durable Step | ❌ 미구현 | — |
