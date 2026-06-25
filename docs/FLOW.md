# Agent Lab — 현재 구조 및 플로우

> **최종 업데이트:** 2026-06-26  
> **관련 문서:** [ARCHITECTURE.md](./ARCHITECTURE.md) (모듈·컴포넌트 맵) · [USER-GUIDE.md](./USER-GUIDE.md) (기능 상세) · [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) (방향성)

---

## 1. 한 줄 포지션

**"신뢰 수준에 따라 자율도가 조정되는 Mission Platform"**

- Fugu/Harness처럼 완전 자율 처리는 하지 않는다 — Human gate는 선택이 아닌 설계.
- 신뢰도 HIGH + 위험도 LOW → 자동 통과. 불확실할 때는 반드시 인간을 거친다.
- 5개 모트는 어떤 이니셔티브에서도 약화 금지: **BLOCK→409 · worktree 격리 · Oracle+Repair · run.json 감사 · Human Inbox**

---

## 2. 전체 플로우 개요

```
사용자 입력 (topic)
      │
      ▼
┌─────────────────────────────────────────────┐
│  DISCUSS (Room)                             │
│  topic_router → agent_subset + role_plan    │
│  3-agent 합의 루프 (R1 → R2 → anchor)       │
│  consensus / BLOCK / CHALLENGE / AMEND      │
│  Scribe → plan.md                           │
└────────────────┬────────────────────────────┘
                 │ plan.md (Human approved)
                 ▼
┌─────────────────────────────────────────────┐
│  PLAN (계약)                                │
│  clarify → peer review gate → Human approve │
│  plan_workflow FSM                          │
└────────────────┬────────────────────────────┘
                 │ approved plan
                 ▼
┌─────────────────────────────────────────────┐
│  EXECUTE (격리)                             │
│  git worktree dry-run                       │
│  Human diff 검토 → merge approve            │
│  Trust auto-merge (LOW risk + Oracle green) │
└────────────────┬────────────────────────────┘
                 │ merged diff
                 ▼
┌─────────────────────────────────────────────┐
│  VERIFY (Oracle)                            │
│  Oracle verdict + evidence gates            │
│  Repair loop (fail → discuss recovery)      │
│  verify_repair_policy                       │
└────────────────┬────────────────────────────┘
                 │ PASS
                 ▼
             DONE / Mission loop 재진입
```

**Work phase SSOT:** `GET /api/sessions/{id}/runtime` → `work_phase` 필드

---

## 3. Discuss — Room 합의 루프

### 3.1 진입점: `topic_router`

토픽이 들어오면 `topic_router.py`가 3가지를 동시에 산출한다:

| 출력 | 설명 | 구현 |
|------|------|------|
| `category` | quick / standard / deep / critical | 창발 예산 결정 |
| `agent_subset` | 활성 에이전트 목록 | quick → 단일, deep → 전원 |
| `role_plan` | `{agent_id: role_id}` | P1 이후, 토픽 기반 동적 배정 |

### 3.2 역할 배정 (Role Orchestration, P1~P8)

`role_plan`은 `run_meta["_turn_roles"]`에 stash되어 `reply_policy.py:build_guidance_parts`를 통해 per-agent 페르소나로 주입된다. 호출 체인 변경 없음.

| 역할 | 에이전트 성향 | 합의 envelope |
|------|-------------|---------------|
| `proposer` | 강한 1차 PROPOSE, 조기 합의 금지 | PROPOSE |
| `critic` | 약한 가정·누락 CHALLENGE/AMEND | CHALLENGE / AMEND |
| `synthesizer` | `recombination_follow_up()` 재사용 | (재조합 라운드) |
| `executor` | 합의안 → 패치·실행, R1 반영 | — |

**토픽 기반 자동 배정 예시:**

| 태스크 타입 | cursor | claude | codex |
|-------------|--------|--------|-------|
| `code` | proposer/executor | critic | proposer 보조 |
| `review` | — | proposer | critic |
| `quick` | `{}` — 역할 없음 | | |

**에스컬레이션 해제:** CHALLENGE/BLOCK으로 category 상승 시 `_turn_roles = {}` — 정적 분화가 녹아 전원 자유토론.

### 3.3 합의 루프 상세

```
R1: 각 에이전트 독립 PROPOSE
     ↓
R2: CHALLENGE / AMEND / ENDORSE  (+ 재조합 라운드)
     ↓
anchor: 「이의 없습니다」 합의 or BLOCK
     ↓ (합의)
Scribe: plan.md 합성
```

| 이벤트 | 의미 | 구현 |
|--------|------|------|
| `PROPOSE` | 1차 제안 | `room_consensus.py` |
| `CHALLENGE` | 이의 제기, 근거 필수 | `room_objections.py` |
| `AMEND` | 수정안 제시 | re-anchor 트리거 |
| `ENDORSE` | 동의 + 근거 한 줄 | anchor 카운트 |
| `BLOCK` → 409 | 실행 전진 차단 | execute gate |

**재조합 라운드:** proposer+critic 2개 substantive 발화 후 `recombination_follow_up()`이 타 에이전트 2명+ 인용 합성. 이것이 synthesizer/Judge 단계를 겸한다.

### 3.4 Human Inbox

토론 중 에이전트가 인간 판단이 필요한 시점에 `ask_human` / `propose_build`를 호출 → **HumanInboxPanel** 에 표시. 답변 전까지 관련 단계 pause.

| 트리거 | 종류 | pause 범위 |
|--------|------|------------|
| T-Q0 (clarifier) | question | 첫 턴 시작 전 |
| T-Q1 (harvest) | question | R1+R2 후 오픈 이슈 |
| T-B1~B4 | build GO | execute 진입 전 |
| execute MCP | question / build | dry-run 중 블로킹 |

---

## 4. Plan — 계약 FSM

```
clarify (Socratic QA)
    ↓
[peer review gate → evaluate_plan_gate()]
    ↓
HUMAN_PENDING  ←──── plan.md draft
    ↓  (POST /plan/approve)
APPROVED
    ↓
execute 진입 가능
```

**plan.md SSOT:** `sessions/<id>/plan.md` — 에이전트별 기여 + 미해결 BLOCK 섹션 포함.

**template 기반 bypass:** `sessions/_templates/{id}/` hash match → `approve_plan_bypass()` (반복 태스크 자동화).

---

## 5. Execute — worktree 격리

```
APPROVED plan
    ↓
git worktree 생성 (action별 격리)
    ↓
Cursor / Codex dry-run (MCP Inbox 연결)
    ↓
diff 생성 → SideBySideDiff UI
    ↓
Human diff 검토
    ↓ merge_classifier (LOW risk + Oracle green)
┌─── trust auto-merge (30s timeout) ← LOW + HIGH
└─── Human approve ← MEDIUM / HIGH
    ↓
worktree merge → main
    ↓
worktree 정리 + provenance + task 완료
```

**gates (순서대로):**

| 게이트 | 구현 | 통과 조건 |
|--------|------|-----------|
| objection gate | `room_objections.py` | BLOCK 없음 |
| pre_execute | `plan_execute_verify.py` | syntax_gate + sandbox_policy |
| merge_checks | `merge_checks.py` | syntax OK + no conflict |
| trust auto-merge | `auto_merge.py`, `merge_classifier.py` | `docs_only`/`test_only`/`single_file` + Oracle green |
| Human approve | `plan_execute.resolve_execution` | dev profile default |

---

## 6. Verify — Oracle

```
merged diff
    ↓
Oracle verdict (oracle_core.py)
 ├─ evidence gates (evidence_gates.py)
 ├─ adversarial gate (adversarial_gate.py)
 └─ quality_judge (quality_judge.py)
    ↓
PASS → task 완료 → run.json 업데이트
FAIL → verify_repair_policy
         ├─ repair loop (재실행)
         └─ discuss recovery → DiscussRecoveryBanner
```

**run.json 감사 이력:** 모든 Oracle 판정 + who/why/when 기록. `patch_run_meta()` 경유 — 직접 쓰기 금지.

---

## 7. Mission Loop FSM

여러 세션 목표를 자동 순환하는 상위 FSM. Room 플로우는 이 FSM의 단일 턴.

```
DISCUSS ──→ EXECUTE ──→ VERIFY
   ↑                        │
   └──── repair loop ←──────┘ (FAIL)
                             │ (PASS)
                         DONE / next goal
```

**`run.json` 핵심 필드:**

| 필드 | 의미 |
|------|------|
| `work_phase` | discuss / plan / execute / verify / done |
| `mission.goals[]` | 목표 목록 + 완료 상태 |
| `turn_budget` | 남은 창발 예산 |
| `_turn_roles` | 현재 턴 역할 배정 (비영속) |
| `trust_budget.auto_merge_remaining` | 자동 머지 잔여 횟수 |

---

## 8. 에이전트 구성

### 8.1 기본 3-agent 팀

| 에이전트 | 강점 | 기본 역할 (code task) |
|----------|------|----------------------|
| **Cursor** | 편집·실행 | proposer / executor |
| **Codex** | 분해·검증 | proposer 보조 |
| **Claude** | 추론·리뷰 | critic |

### 8.2 동적 구성 (P0 진행 중)

`topic_router`의 `agent_subset`이 태스크 유형에 따라 에이전트 풀을 결정:

| 태스크 | 에이전트 풀 |
|--------|------------|
| 코드 작업 | cursor + codex |
| 리뷰 | claude + kimi |
| quick | 단일 에이전트 |
| deep | 전원 |

### 8.3 Room Preset

| 프리셋 | 흐름 | 적합 태스크 |
|--------|------|-------------|
| `quick` | 단일 에이전트 | 단순 질의 |
| `consensus` | 3-agent 합의 (기본) | 일반 개발 |
| `producer_reviewer` | proposer PROPOSE → critic CHALLENGE → 재조합 → Oracle | 코드 리뷰·품질 중시 |
| `pipeline` | 순차 전문화 | 문서·scribe 중심 |
| `supervisor` | Mission Loop FSM | 장기 미션 |

---

## 9. 세션 데이터 구조

```
sessions/<session-id>/
├── topic.txt          # 세션 주제
├── chat.jsonl         # 메시지 원문 (SSOT)
├── plan.md            # Plan contract
├── run.json           # Runtime state + mission + budgets
├── meta.json          # 세션 메타
├── transcript.md      # 렌더된 transcript (파생)
├── artifacts/         # 에이전트 산출물
└── attachments/       # 첨부
```

미션 증거: `.agent-lab/missions/<id>/evidence.jsonl`

---

## 10. Backend Hardening 플래그 (현재 기본값)

| 플래그 | 기본 | 기능 |
|--------|------|------|
| `AGENT_LAB_CHECKPOINT` | **ON** | FSM 상태 스냅샷/재개 |
| `AGENT_LAB_REPO_MAP` | **ON** | 심볼 그래프 repo-map |
| `AGENT_LAB_COMPACT_TOOL_OUTPUT` | off | 도구 출력 압축 |
| `AGENT_LAB_SYNTAX_GATE` | **ON** | 편집 시 syntax 검사 |
| `AGENT_LAB_SANDBOX_POLICY` | off | 실행 sandbox (Docker) |
| `AGENT_LAB_ROOM_ROLES` | ON | 역할 오케스트레이션 (P1 이후) |

전체 목록: `make list-flags` 또는 `GET /api/health/flags`

---

## 11. 빠른 명령

```bash
make dev                                    # API(:8765) + web(:5173)
make test-fast                              # pytest ~870 tests, ~1분
python scripts/smoke_room.py                # 36 regression baselines
AGENT_LAB_ROOM_PRESET=producer_reviewer \
  python scripts/smoke_room.py             # producer_reviewer 검증
make list-flags                             # 플래그 레지스트리
```
