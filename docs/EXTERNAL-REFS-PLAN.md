# 외부 레퍼런스 분석 및 Agent Lab 적용 계획

> 작성: 2026-06-03  
> 분석 대상: Conductor · Centaur · LazyCodex · Claude Code  
> 목적: 각 시스템의 강점을 Agent Lab에 이식하되, 합의·게이트·provenance 핵심 구조는 유지한다.

> **Stale notice (2026-06):** External-ref traceability queue is **empty** — Layers 1–4 (mock-first), CON-diff, CENT-env/durable, MD-PROJECT/PLATFORM/P3, and dev-tool CC-* are **shipped**. Live adversarial: `AGENT_LAB_ADVERSARIAL_LIVE=1` ([LC-L4-ADVERSARIAL-LIVE.md](LC-L4-ADVERSARIAL-LIVE.md)). Hub: **[EXTERNAL-REFS-TRACEABILITY.md](EXTERNAL-REFS-TRACEABILITY.md)**.

---

## 레퍼런스 시스템 한 줄 요약

| 시스템 | 핵심 철학 | Agent Lab에 없는 것 |
|--------|-----------|---------------------|
| **Conductor** | workspace = 격리 단위, PR = 통합 단위 | — (CON-diff ✅, PI-executed ✅) |
| **Centaur** | 팀 공유 에이전트, Slack-native, K8s 격리 | Durable step (재시작 복구) — credential 분리 ✅ [CENT-env](EXTERNAL-REFS-TRACEABILITY.md) |
| **LazyCodex** | 완료를 주장하지 말고 Loop → 검증될 때까지 | **Loop 엔진** (Oracle verified completion) |
| **Claude Code** | 개발자 도구 생태계 완성 | auto-memory (CC-CLAUDE/hooks/rules/skills ✅) |

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

없는 것 (선택):
  goal-driven loop — "이 목표 달성될 때까지 계속" 모드 (Layer 5)
```

### 1.3 Agent Lab에 도입할 Loop 계층

```
Layer 1: CLI Retry Loop (이미 있음 — cli_retry.py)
  에이전트 호출 실패 → 최대 N회 backoff 재시도
  대상: 429, timeout, 일시적 오류

Layer 2: Consensus Loop (이미 있음 — cap_rounds/cap_calls)
  합의 미달 → 다음 라운드 자동 진행
  상한: MAX_AGENT_PARALLEL_ROUNDS=4

Layer 3: Execute Verify Loop (✅ 구현됨)
  merge 완료 → action.verify 필드 자동 확인
  실패 → 새 worktree에서 Cursor/Codex에게 "검증 기준이 아직 안 됐어: {이유}" 재호출
  수정 commit을 base branch에 re-merge한 뒤 Oracle 재검증
  상한: MAX_VERIFY_RETRIES=2

Layer 4: Adversarial Gate (✅ LC-L4)
  dry-run diff → adversarial note (mock default; live: AGENT_LAB_ADVERSARIAL_LIVE=1)
  UI badge non-blocking — adversarial_gate.py, PlanExecutePanel

Layer 5: Goal-Driven Session Loop (✅ LC-L5, mock-first)
  Human이 목표 설정 → 목표 달성 여부를 Oracle이 판단
  미달성 시 Human-gated "한 턴 더 토론" 요청 (discuss 루프)
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
  └─ action.verify 필드를 mock-first Oracle로 확인
  └─ "PASS" → 완료 badge
  └─ "FAIL: {이유}" → Human에게 표시 + "에이전트에게 수정 요청" 버튼
         ↓ (Human이 요청 클릭)
         에이전트 재호출 (이유 포함) → 새 worktree dry-run
         → 수정 commit → 재merge → verify 재실행
         (최대 MAX_VERIFY_RETRIES=2)
```

구현 파일:
- `plan_execute_merge.py` — `verify_after_merge()` + `oracle_verify()`
- `plan_execute.py` — `reverify_merged_execution()` agent repair/re-merge loop
- `PlanExecutePanel.tsx` — verification badge + 재작업 버튼
- `app/server/routers/plan_execute.py` — `/execute/reverify` 엔드포인트

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

### 1.6 Oracle Verified Completion (Layer 3 심화)

#### 왜 별도 섹션인가

Layer 3 Execute Verify Loop (1.4)는 **흐름**을 정의합니다.  
Oracle은 그 흐름의 **판단 주체**입니다. 구현 방식이 다릅니다.

LazyCodex에서 Oracle = Discipline agent (Sisyphus 오케스트레이터가 Oracle을 호출).  
Agent Lab에서 Oracle = **plan action의 `검증:` 필드를 Claude가 실제로 수행**.

#### 현재 상태

```python
# plan_execute.py — _verify_follow_ups() (이미 있음)
# Cursor에게 "Phase 2 — verify and fix" 지시를 follow-up으로 주입함
# 즉 Cursor가 스스로 검증하도록 "부탁"하는 구조

def _cursor_verify_follow_up(verify: str) -> str:
    return f"""Phase 2 — verify and fix:
- Verification criterion from plan: {verify}
..."""
```

**문제:** Cursor가 검증 기준을 충족했다고 보고해도, 그걸 독립적으로 확인하는 주체가 없습니다. 에이전트가 "완료"를 주장하면 바로 Human approve 단계로 넘어갑니다.

#### Oracle 설계 (독립 검증자)

```
[현재 흐름]
Cursor 실행 → "검증 기준 충족" 자기 보고 → Human approve

[Oracle 도입 후]
Cursor 실행 → 자기 보고
                ↓
         Oracle (Claude) 독립 검증
           ├─ action.verify 필드 기준으로 판단
           ├─ merged_paths 실제 파일 읽기
           └─ PASS / FAIL + 이유
                ↓
         PASS → Human approve 화면에 "Oracle PASS ✅" 표시
         FAIL → Human approve 화면에 "Oracle FAIL ⚠️ {이유}" 표시
                + "에이전트에게 수정 요청" 버튼 (Layer 3 loop 트리거)
```

#### Oracle 구현 설계

```python
# plan_execute_merge.py — merge 완료 직후 호출
def oracle_verify(
    action: PlanAction,
    merged_paths: list[str],
    *,
    session_folder: Path,
) -> dict[str, Any]:
    """
    LazyCodex Oracle 패턴 — 에이전트와 독립된 검증자.
    action.verify 필드를 기준으로 실제 파일 상태를 확인.
    """
    if not action.verify or action.verify.strip() in {"검증 기준 없음", "-", "—", "N/A"}:
        return {"verdict": "skipped", "reason": "verify 필드 없음"}

    # 변경된 파일 내용 요약 (최대 3000자)
    file_snippets = []
    for path in merged_paths[:5]:
        full = session_folder.parent / path  # workspace_root 기준
        if full.is_file():
            snippet = full.read_text(encoding="utf-8", errors="replace")[:600]
            file_snippets.append(f"--- {path} ---\n{snippet}")
    files_block = "\n\n".join(file_snippets) or "(변경 파일 없음)"

    prompt = (
        f"다음 작업이 완료됐는지 독립적으로 검증하세요.\n\n"
        f"검증 기준:\n{action.verify}\n\n"
        f"변경된 파일 (요약):\n{files_block}\n\n"
        f"판정: PASS 또는 FAIL\n"
        f"FAIL이면 구체적인 이유 1-2줄.\n"
        f"형식: PASS 또는 FAIL: {{이유}}"
    )

    raw = claude_cli.invoke("oracle", prompt, scribe=True)
    passed = raw.strip().upper().startswith("PASS")
    return {
        "verdict": "pass" if passed else "fail",
        "detail": raw.strip()[:400],
        "verify_criterion": action.verify,
        "checked_paths": merged_paths[:5],
    }
```

#### Oracle 결과의 흐름

```python
# plan_execute_merge.py:merge_and_finalize() 내부
merge_result = git_merge(worktree)
oracle_result = oracle_verify(action, merge_result["touched_paths"], session_folder=folder)

patch_run_meta(folder, {
    f"oracle_{execution_id}": oracle_result
})

# API 응답에 포함
return {
    "status": "merged",
    "oracle": oracle_result,   # UI가 이걸 읽어 badge 표시
    ...
}
```

#### UI 반영 (PlanExecutePanel.tsx)

```
merge 완료 화면:
  ┌────────────────────────────────────────┐
  │ ✅ Merge 완료                           │
  │                                        │
  │ Oracle 검증: ✅ PASS                   │  ← oracle.verdict == "pass"
  │ 기준: "PDF 26p 이상, break-report 포함" │
  │                                        │
  │ [다음 액션으로]                         │
  └────────────────────────────────────────┘

  또는:

  ┌────────────────────────────────────────┐
  │ ✅ Merge 완료                           │
  │                                        │
  │ Oracle 검증: ⚠️ FAIL                  │  ← oracle.verdict == "fail"
  │ "break-report.json 파일이 없습니다"     │
  │                                        │
  │ [그래도 진행]  [에이전트에게 수정 요청] │  ← Layer 3 루프 트리거
  └────────────────────────────────────────┘
```

#### 구현 파일 요약

| 파일 | 변경 내용 | 규모 |
|------|-----------|------|
| `plan_execute_merge.py` | `oracle_verify()` 추가 + `merge_and_finalize()` 호출 | +50줄 |
| `run_meta.py` | `oracle_{exec_id}` 패치 | +3줄 |
| `app/server/routers/execute.py` | oracle 결과 API 응답에 포함 | +5줄 |
| `PlanExecutePanel.tsx` | Oracle badge + 재작업 버튼 | +40줄 |

**우선순위: P1** — Adversarial Gate(Layer 4)와 함께, execute 완료 신뢰성의 핵심.

---

### 1.7 AGENTS.md 계층 — 프로젝트 영속 메모리

#### LazyCodex의 `/init-deep` 패턴

LazyCodex는 프로젝트 시작 시 `/init-deep`을 실행해 계층형 `AGENTS.md`를 생성합니다.

```
project-root/
├── AGENTS.md              ← 전체 프로젝트 아키텍처 요약
├── src/
│   └── AGENTS.md          ← src 서브트리 전용 가이드
└── tests/
    └── AGENTS.md          ← 테스트 컨벤션
```

에이전트는 작업할 파일의 경로를 보고 가장 가까운 `AGENTS.md`를 먼저 읽어 "이 디렉토리의 규칙"을 파악합니다.

#### Agent Lab의 현재 프로젝트 메모리

```python
# session_guidance.py:build_session_guidance_block()
# workspace_binding이 있으면 bound cwd를 에이전트에 주입
# session_template으로 고정 가이던스 블록 주입
```

**문제:** 이 가이던스는 세션마다 `run_meta`에서 읽습니다. 프로젝트 수준의 "이 코드베이스가 무엇인가"는 매 세션 Human이 topic에 포함시켜야 합니다.

#### Agent Lab에 맞는 PROJECT.md 설계

LazyCodex의 계층형 AGENTS.md 대신 **단일 PROJECT.md**로 경량 도입:

```
workspace_root/           ← .agent-lab/ 이 있는 프로젝트
└── .agent-lab/
    ├── hooks.toml        ← 이미 있음
    └── PROJECT.md        ← 신규 (LazyCodex /init-deep 패턴)
```

PROJECT.md 내용 (자동 생성 후 Human 편집):

```markdown
# 프로젝트 메모리

## 아키텍처 한 줄
...

## 핵심 모듈
- 어느 파일이 어떤 역할
...

## 현재 작업 맥락
- 진행 중인 것
- 최근 결정
...

## 에이전트 주의사항
- 이 프로젝트에서 알아야 할 제약
...
```

#### 주입 경로 설계

```python
# session_guidance.py:build_session_guidance_block() 확장

def _read_project_md(run_meta: dict[str, Any] | None) -> str:
    """workspace_binding 경로의 .agent-lab/PROJECT.md 읽기."""
    binding = (run_meta or {}).get("workspace_binding", {})
    path = binding.get("path") if isinstance(binding, dict) else None
    if not path:
        return ""
    project_md = Path(path) / ".agent-lab" / "PROJECT.md"
    if not project_md.is_file():
        return ""
    content = project_md.read_text(encoding="utf-8", errors="replace")
    # 토큰 절약: 2000자 상한
    if len(content) > 2000:
        content = content[:1997] + "…"
    return f"[PROJECT.md — 프로젝트 영속 메모리]\n{content}"


def build_session_guidance_block(run_meta):
    parts = [...]
    project_block = _read_project_md(run_meta)
    if project_block:
        parts.insert(0, project_block)   # 최상단에 주입
    ...
```

#### 에이전트가 받는 것 (before/after)

```
[현재 — 매 세션 topic에 프로젝트 설명 포함 필요]
User: "이 프로젝트는 PDF 교재 생성기고, mjs 빌드 시스템을 써.
      break-report.json이 검증 기준이야. 이번엔 목차를 수정해줘."

[PROJECT.md 도입 후 — topic이 짧아짐]
User: "목차를 수정해줘."

[에이전트 payload 내부]
[PROJECT.md — 프로젝트 영속 메모리]
# 아키텍처 한 줄
PDF 교재 생성기 — build.mjs(Node) + lecture.css + break-report.json 검증

# 핵심 모듈
- build.mjs: 빌드 진입점
- break-report.json: 검증 기준 (appliedBreaks, pdfPageCount)
...
```

#### 생성 방법 (두 가지)

**방법 1 — Human이 직접 작성 (즉시 가능)**
```bash
mkdir -p .agent-lab
cat > .agent-lab/PROJECT.md << 'EOF'
# 프로젝트 메모리
## 아키텍처 한 줄
...
EOF
```

**방법 2 — `init-project-memory` subagent skill (Claude Code 패턴)**

`.claude/agents/init-project-memory/SKILL.md`:

```markdown
---
name: init-project-memory
description: 프로젝트를 분석해 .agent-lab/PROJECT.md 생성 (LazyCodex /init-deep 패턴)
tools: Read, Bash, Edit
---

1. 프로젝트 루트 파악: find . -maxdepth 2 -name "*.md" -o -name "package.json" -o -name "pyproject.toml"
2. 핵심 파일 3-5개 Read
3. 다음 구조로 .agent-lab/PROJECT.md 작성:
   - 아키텍처 한 줄
   - 핵심 모듈 (파일 → 역할 매핑)
   - 빌드/실행 명령어
   - 에이전트 주의사항 (이 프로젝트 고유 제약)
   - 현재 작업 맥락 (비워두기 — Human이 채움)
4. 2000자 이하로 유지
```

#### 구현 파일 요약

| 파일 | 변경 내용 | 규모 |
|------|-----------|------|
| `session_guidance.py` | `_read_project_md()` + `build_session_guidance_block()` 통합 | +25줄 |
| `.agent-lab/PROJECT.md` | 신규 파일 (workspace마다) | 파일 생성 |
| `.claude/agents/init-project-memory/SKILL.md` | 신규 skill | 파일 생성 |

**우선순위: P2** — 세션 품질에 직접 영향은 작지만 Human 마찰을 지속 줄임.  
**가장 빠른 효과:** 자주 쓰는 workspace에 `PROJECT.md` 손으로 작성 → 즉시 적용.

---

## Part 2 — Conductor: 격리 실행

### 2.1 현황
Phase I (M0–M4) 완료 → `plan_execute_worktree.py`, `plan_execute_merge.py` 구현됨.  
git worktree 격리 + approve = merge 구조 확립.

### 2.2 Diff Viewer 인라인 재작업 (✅ shipped — CON-diff)

**Conductor 패턴을 Agent Lab에 적용:**
```
diff 전체 표시 → approve / reject
      또는 diff의 특정 hunk에 인라인 코멘트 → "이 부분만 다시 짜줘"
      → 에이전트가 해당 chunk만 수정 → re-diff → re-approve
```

구현 파일: `PlanExecutePanel.tsx` + `plan_execute.py:revise_pending_execution()` +
`POST /api/sessions/{id}/execute/pending-plans/{exec_id}/revise`

기존 pending worktree는 새 diff 생성 성공 전까지 보존하고, 성공 후에만
`superseded`로 전환한다.

### 2.3 Worktree 실행 이력 보존 (✅ PI-executed)

merge 완료 시 dry-run diff를 `sessions/{id}/executed/{exec_id}.json` 에 저장.  
plan.md provenance와 함께 "왜 이 코드가 이렇게 됐는가" 추적.

구현: `plan_execute_merge.py:archive_executed_diff()` — `_record_verify_after_merge()` 경유

---

## Part 3 — Centaur: 안정성

### 3.1 현황
`cli_retry.py` 이미 구현됨 (429, timeout, overloaded 패턴 처리).  
subprocess credential 분리 **✅ shipped** — [CENT-env](EXTERNAL-REFS-TRACEABILITY.md), `subprocess_env.py`.

### 3.2 Subprocess Credential 분리 (✅ shipped — CENT-env)

```python
# subprocess_env.py — allowlist + AGENT_LAB_/CLAUDE_/CODEX_/CURSOR_ prefixes
# ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN explicitly excluded
from agent_lab.subprocess_env import subprocess_env, isolated_process_env

env = subprocess_env(AGENT_LAB_MOCK_AGENTS="1")
result = subprocess.run([...], env=env)
```

구현: `subprocess_env.py`, `claude_cli.py`, `codex_cli.py`, `cursor_bridge.py`, `tests/test_subprocess_env.py`

### 3.3 Durable Step (Centaur 경량판) — ✅ shipped (CENT-durable)

**문제:** uvicorn 재시작 → 진행 중 round 소실.

`run.json` `completed_steps[]` — `_call_one_agent()` 성공 시 `patch_run_meta()`로 즉시 기록.  
재시작 후 동일 human turn resume 시 `run_parallel_round()`가 completed agent를 skip하고 cached content replay.

구현: `run_meta.py`, `room.py`, `sessions/_regression/durable_completed_steps/`, `tests/test_durable_completed_steps.py`

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
          "command": ".claude/hooks/post-edit-ruff.sh"
        }]
      },
      {
        "matcher": "*.tsx",
        "hooks": [{
          "type": "command",
          "command": ".claude/hooks/post-edit-prettier.sh"
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": ".claude/hooks/stop-pytest.sh",
          "statusMessage": "pytest 실행 중..."
        }]
      }
    ]
  }
}
```

주의: 이 hooks는 **Claude Code 개발 도구용**이고, `room_hooks.py`(AgentLab 런타임 서버사이드 훅)와 다른 레이어입니다. 경로는 repo-root 상대(`.claude/hooks/*.sh`).

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
  └─ subprocess env 분리              [Centaur] ✅ CENT-env

Phase 1 (1–2주)
  ├─ Layer 4: Adversarial Gate        [LazyCodex] 🔶 mock skeleton (LC-L4)
  │   live Claude + PlanExecutePanel UI wiring remains
  ├─ Layer 3: Execute Verify Loop     [LazyCodex]
  │   plan_execute_merge.py + /reverify API
  └─ Durable Step (completed_steps[]) [Centaur] ✅ CENT-durable
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
  └─ 10 시나리오 벤치마크 완성          [운영] ✅ shipped — H-P2 + smoke 17
```

### 우선순위 매트릭스

| 순위 | 출처 | 항목 | 구현 규모 | 임팩트 |
|------|------|------|-----------|-------|
| **P0** | Claude Code | CLAUDE.md 작성 | XS (30분) | 높음 — 즉시 개발 생산성 |
| **P0** | Claude Code | Hooks (ruff + pytest) | XS (10분) | 높음 — 자동 품질 검사 |
| **P0** | Centaur | subprocess env 분리 | XS | ✅ CENT-env |
| **P1** | LazyCodex | Adversarial Gate (Layer 4) | S | 🔶 mock skeleton — live + UI remain |
| **P1** | LazyCodex | Execute Verify Loop (Layer 3) | M (80줄 Python + 40줄 TSX) | 높음 — 완료 신뢰성 |
| **P1** | LazyCodex | Oracle Verified Completion (§1.6) | M (50줄 Python + 40줄 TSX) | 높음 — 에이전트 자기 보고 신뢰 불가 해결 |
| **P1** | Centaur | Durable Step (completed_steps) | S | ✅ CENT-durable |
| **P2** | LazyCodex | PROJECT.md 영속 메모리 (§1.7) | S (25줄 + 파일 생성) | 중간 — 세션 간 기억, Human 마찰 감소 |
| **P2** | Conductor | Diff viewer 인라인 재작업 | L (UI 비중) | ✅ CON-diff |
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
  ├─ Durable Step (Centaur) ✅ CENT-durable
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
| Layer 3: Execute Verify Loop | ✅ 구현됨 | `plan_execute.py:reverify_merged_execution()`, `tests/test_plan_execute_agent_repair.py` — §1.4 |
| Layer 4: Adversarial Gate | ✅ mock + live opt-in | `adversarial_gate.py`, `docs/LC-L4-ADVERSARIAL-LIVE.md` — §1.5 |
| Layer 5: Goal-Driven Loop | ✅ mock-first + Human gate | `goal_loop.py`, `RoomChat.tsx`, `docs/GOAL-LOOP.md` |
| Durable Step | ✅ shipped | `run_meta.py`, `sessions/_regression/durable_completed_steps/` — Part 3 |
| PI-executed archive | ✅ shipped | `archive_executed_diff()`, `sessions/<id>/executed/` — §2.3 |

---

## 참고: LazyCodex 4개 항목 구현 상태

LazyCodex에서 가져올 것으로 식별한 4개 항목:

| # | 항목 | 구현 여부 | 섹션 | TRACEABILITY | 우선순위 |
|---|------|-----------|------|--------------|----------|
| 1 | Socratic interview (session_clarifier) | ✅ opt-in `AGENT_LAB_CLARIFIER=1` | §1.3 | LC-clarifier | — |
| 2 | Adversarial Gate | ✅ mock + live opt-in | §1.5 | LC-L4 | — |
| 3 | Oracle Verified Completion | ✅ mock-first | §1.6 | LC-oracle | — |
| 4 | PROJECT.md + AGENTS/SHARED | ✅ | §1.7 | MD-PROJECT, MD-P3 | — |
