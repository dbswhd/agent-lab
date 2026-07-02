# Agent Role Orchestration — Fugu식 역할 분화를 창발 루프 위의 합성 레이어로

> **상태**: P1–P3·P5b·P6 **shipped** (2026-07) — Settings 분업 UI 퇴출, topology/role_plan SSOT. P4 S2 bandit **partial** (`s2_role_bandit.py` interface).
> **배경**: dogfood 중 `team` 흐름이 에이전트를 평면적 peer로만 돌림 — Fugu TRINITY(Proposer/Critic/Judge)나 Harness Producer-Reviewer의 품질 이득 없음.

---

## 문제 진단

| 패턴 | 현황 |
|---|---|
| `producer_reviewer` 프리셋 | 이름만 역할 분화 — 실제로는 `verified` 프로필(팀 병렬 제안 + Oracle 사후검증), "A 제안 → B 리뷰" 아님 |
| 역할 유사 동작 | 하드코딩된 특수 케이스 3개로 분산: `review_advocate`, `specialist R1→R2`, `divergence` |
| 역할 배정 방식 | 정적(에이전트 고정) — 토픽 성격 반영 불가 |

**목표**: 토픽에서 시스템이 스스로 역할 구성을 결정하는 단일 역할 primitive. Fugu식 역할 명확성을 가져오되, 역할은 합의/재조합/에스컬레이션 루프를 **대체하지 않고 그 위에 합성**된다.

사용자 방향: ① 효율보다 장기적 일반화, ② 토픽 기반 동적 배정, ③ 장기적으로 좋은 프리셋 노출.

---

## 핵심 설계 결정

**`topic_router`를 "토픽 → 자기조직화" 단일 브레인으로 확장한다.**

지금 `topic_router`는 토픽에서 (창발 예산 + `agent_subset`)을 산출한다. 여기에 **세 번째 출력 `role_plan`**을 추가한다. 역할은 `topic_router → 합의 루프 → guidance seam`을 타고 흐른다.

### 운반 경로

역할은 `run_meta["_turn_roles"]`(turn-scoped, `_` 접두사 = 비영속, 기존 `_turn_category` 관례)에 턴당 1회 해석되어 실린다. 새 파라미터를 6개 파일에 스레딩하지 않는다 — `run_meta`는 이미 어디에나 흐른다.

### 주입 seam

`reply_policy.py:build_guidance_parts(policy, *, run_meta, agent)` (line 143–179). 이미 `agent`+`run_meta`를 받고 이미 per-agent 분기(`team_lead`, line 156–160)를 한다. 여기서 `persona_for_agent(run_meta["_turn_roles"], agent)`를 추가한다. **호출 체인 변경 0.**

### Synthesizer = 기존 재조합 라운드

새 합성 라운드를 만들지 않는다. `recombination_follow_up()`(`room_consensus.py:193`, 유전 crossover: 타 에이전트 2명+ 인용 합성)이 곧 Judge/Synthesizer 단계다.

### 에스컬레이션이 역할을 해제한다

`agent_subset`과 동일하게, CHALLENGE/BLOCK으로 카테고리가 오르면 정적 역할은 녹아 전원 자유토론으로 전환된다. (모트 보존: 역할은 출발 편향이지 우리가 아니다.)

---

## 단계별 구현

### P1 — `src/agent_lab/role_plan.py` (신규, 순수 모듈)

`from __future__ import annotations` 첫 줄. I/O·run.json 쓰기 없음.

#### RoleSpec 정의

```python
@dataclass(frozen=True, slots=True)
class RoleSpec:
    id: str
    label: str
    persona: str

_ROLES: dict[str, RoleSpec]
```

페르소나는 한국어, 기존 `DIVERGENCE_INSTRUCTION`/`recombination_follow_up()` 문체. **합의 envelope(PROPOSE/CHALLENGE/AMEND/ENDORSE)를 명시 참조**해 루프와 합성되게 작성(우회 금지가 텍스트 차원 계약):

| 역할 | 설명 |
|---|---|
| `proposer` (제안자) | 강한 1차 PROPOSE안 작성, 조기 합의 금지, 검토자가 칠 표면 노출 |
| `critic` (검토자) | 약한 가정·누락 리스크 1건+ CHALLENGE/AMEND, 형식적 동의 금지, 진짜 이견 없으면 근거 한 줄+ENDORSE |
| `synthesizer` (합성자) | `recombination_follow_up()` **import 재사용**(중복 금지) — "재조합 라운드 = 합성자" 매핑을 코드로 못박음 |
| `executor` (실행자) | 합의안을 패치·실행으로, R1 발화/CHALLENGE 반영 — `specialist R2`/cursor 하드코딩 텍스트(`room_agent_capabilities.py:220–221`)의 일반화 |

#### 에이전트 강점 테이블

`cwd_role`(cursor=`execute`, codex=`decompose/verify`, claude=`review`)를 강점 신호로 사용 — `DEFAULT_CAPABILITIES`(`room_agent_capabilities.py:11–27`)에서 읽음.

#### 토픽 기반 동적 배정

```python
def resolve_role_plan(*, route: CategoryRoute, agents: list[str]) -> dict[str, str]:
    """topic_router CategoryRoute → {agent_id: role_id}. {} = 역할 없음(순수 창발)."""
```

| 조건 | 배정 |
|---|---|
| `category="quick"` | `{}` — 단일/경량, 역할 불필요 |
| `task_type="code"` | 편집강(cursor)=proposer/executor, 추론강(claude)=critic, codex=proposer 보조/verify |
| `task_type="review"` | claude=proposer(주 리뷰어), 나머지=critic |
| `category in (deep, critical)` | critic 비중↑(다수 검토자), 재조합 강조 |

배정은 **결정적·순서안정**(registry 순). 미지 역할 → `""`.

#### 킬스위치

`AGENT_LAB_ROOM_ROLES=0` → 항상 `{}`(기존 env-gating 스타일).

#### 접근자

```python
def persona_for_agent(turn_roles: dict[str, str] | None, agent: str) -> str: ...
```

---

### P2 — topic_router에 role_plan 통합

`src/agent_lab/topic_router.py`:

- `CategoryRoute`에 `role_plan: dict[str,str] = field(default_factory=dict)` 추가
- agents를 아는 호출측(`room_consensus_rounds`)에서 `resolve_role_plan(route=…, agents=active)`로 채우는 얇은 후처리
- `category_dict()`에 `role_plan` 직렬화 추가(영속 진단용)

---

### P3 — 합의 루프 결선

**`src/agent_lab/room_consensus_rounds.py`**:

1. `route` 산출 직후(~line 67–73, `active` 확정 후):
   ```python
   run_meta["_turn_roles"] = resolve_role_plan(route=route, agents=active)
   ```
   `_turn_category` stash(line 133) 옆.

2. `reply_policy.py:build_guidance_parts` line 160 직후:
   ```python
   if run_meta and agent:
       from agent_lab.role_plan import persona_for_agent
       role_text = persona_for_agent(run_meta.get("_turn_roles"), agent)
       if role_text:
           parts.append(role_text)
   ```

3. **에스컬레이션 리셋**: `_maybe_escalate`(line 148–184) subset 해제 지점(line 164–167)에서:
   ```python
   run_meta["_turn_roles"] = {}
   ```
   `category_escalated` 이벤트 payload에 `roles_released: bool` 추가(기존 `subset_released` 옆).

---

### P4 — `producer_reviewer` 실체화

정적 토폴로지 신설 없음 — 기존 경로 위 역할 배정.

- `room_preset.py:42–47` 유지(`verified` 프로필 + Oracle 사후검증)
- `verified_loop.py` 팀 라운드에서 `resolve_role_plan` 호출(단일 출처) → `_turn_roles` stash
- 흐름: **proposer 제안 → critic CHALLENGE(합의 토론) → 재조합 합성 → anchor/endorse → Oracle 검증**
- 프리셋 description 갱신: `"Producer 제안 → Reviewer 검증 → 재조합 합성 → Oracle 검증."`

---

### P5 — 하드코딩 3패턴 처리

> 사용자 방침: 효율보다 장기적 일반화 우선

| 패턴 | 파일 | 조치 | 근거 |
|---|---|---|---|
| **specialist** capability 텍스트 | `room_agent_capabilities.py:215–221` | **흡수** — `capability_preamble_block`가 `_turn_roles` 있으면 `persona_for_agent`에 위임, 없으면 기존 폴백 | 동일 altitude(per-agent/per-round), 깨끗한 일반화 |
| **review_advocate** | `room_messages.py:83`, `context_bundle.py:678` | **수렴(마지막 단계, 회귀 게이트)** — critic 페르소나가 곧 악마의 변호인. review_mode가 자체 텍스트 대신 `_turn_roles`에 critic을 SET하도록 전환. quality_gate·frontend·fixture 얽힘 → **회귀 그린 확인 후** 단계적으로 | 사용자가 장기 일반화 택함 → 수렴이 옳음. 위험 큰 만큼 별도 단계+회귀 게이트 |
| **divergence** | `room_consensus.py` | **그대로 유지** | divergence는 *전원* 발산 — uniform이지 per-agent 역할이 아님. role map에 넣는 건 잘못된 altitude |

**순효과**: 특수 케이스 추가 0, 1개(specialist) 제거, 1개(review_advocate) 단계적 수렴, 1개(divergence) 의도적 분리.

---

### P6 — run.json / API / frontend

**run.json** (`room_turn_meta.py`):
- turn 스냅샷에 `roles: dict[str,str]` 추가(review_advocate 스냅샷 line 80/130 미러, non-empty일 때만)
- `_turn_roles`는 `_` 접두사 → 비영속

**API**:
- `room_preset.py:preset_catalog()`에 프리셋별 `role_policy`(`force`/`auto`/`off`) 노출
- `app/server/routers/room.py`에 `GET /room/roles`(role_catalog) 추가 (CLAUDE.md: 라우트는 `routers/`, `main.py` 직접 추가 금지)

**frontend**:
- 기존 turn-meta가 review_advocate 읽는 자리(`web/src/utils/planMeta.ts:69`) 옆에 `roles` 읽어 per-agent 역할 칩 1개
- 신규 컴포넌트 없음. `client.ts` 경유

---

### P7 — 테스트 (`mock-only`, `AGENT_LAB_MOCK_AGENTS=1`)

신규 `tests/test_role_plan.py`:

1. **`resolve_role_plan`**: quick→`{}`; code task→cursor=proposer/claude=critic; review task→claude=proposer; deep→critic 다수; 결정성; `AGENT_LAB_ROOM_ROLES=0`→`{}`
2. **페르소나 텍스트**: 각 역할 non-empty; `synthesizer`==`recombination_follow_up()`(drift 가드)
3. **seam**: `_turn_roles={"codex":"proposer","claude":"critic"}`, `build_guidance_parts(agent="codex")`에 proposer만 / `"claude"`에 critic만 / `agent=""`엔 둘 다 없음
4. **합성**: 에스컬레이션 mock CHALLENGE → `_turn_roles` clear + `category_escalated.roles_released=True`
5. **재조합 유지**: producer_reviewer mock 턴(proposer+critic 2 substantive) → 재조합 라운드 실행(skip 아님)
6. **회귀 fixture** `sessions/_regression/producer-reviewer-roles/`(JSONL+run.json, `roles` 포함). 기존 consensus/recombination/review fixture **무변경** 확인(역할은 `_turn_roles` 비었을 때 가산적·무영향 증명)

---

### P8 — 검증 (E2E, `AGENT_LAB_MOCK_AGENTS=1`)

- `python scripts/smoke_room.py` 36 baseline 무회귀
- `AGENT_LAB_ROOM_PRESET=producer_reviewer`로 스모크 → run.json `roles` 확인, 재조합 이벤트 발화 확인, Oracle 게이트 잔존 확인, proposer/critic payload 차이 diff
- `make test-fast` 통과
- `emergence_kpis.py`(`challenge_yield`, `recombination_validity_rate`) before/after 비교 — critic이 인위적으로 합의를 막지 않는지 모니터

---

## 모트 보존 계약

| 불변 원칙 | 설명 |
|---|---|
| **역할 = 페르소나 텍스트** | anchor/「이의 없습니다」/AMEND 재anchor 기계(`room_consensus.py`) 불변. 역할 에이전트도 정상 envelope 발화·anchoring 참여 |
| **재조합 = 합성, 그대로 재사용** | 2차 합성 경로 없음 |
| **에스컬레이션이 역할 해제** | 토픽이 프리셋 가정보다 어려우면 정적 분화가 녹음 |
| **divergence = uniform 유지** | per-agent 역할 배정 대상 아님 |
| **mission loop(`supervisor`) 역할 = `{}`** | 루프 FSM 분화는 별도 표면 |

---

## 위험 / 범위 경계

### 위험

| 위험 | 완화책 |
|---|---|
| critic 페르소나 과격 → `challenge_yield` 인위 팽창·수렴 정체 | ENDORSE-with-reason 허용, KPI 모니터 |
| `_turn_roles` 영속 누출 | 회귀 fixture가 탐지 |
| 해석 이중화(consensus_rounds + verified_loop) | `resolve_role_plan` 단일 출처 강제 |

### 범위

**IN**: role_plan 모듈, topic_router 통합, guidance seam 주입, producer_reviewer 실체화, 에스컬레이션 리셋, specialist 흡수, run.json `roles`, presets `role_policy`, 최소 frontend 칩, mock 테스트, review_advocate 수렴(회귀 게이트)

**OUT(보류)**: 사용자 커스텀/편집 가능 역할 UI, divergence 흡수(잘못된 altitude), 4역할 초과 신설·신규 토폴로지, supervisor 역할 배정

---

## 구현 순서 (회귀 게이트 단위)

```
1. P1+P2+P3  role_plan + topic_router + seam      → make test-fast 그린
2. P4         producer_reviewer 실체화             → 스모크 그린
3. P5a        specialist 흡수                      → 회귀 그린
4. P6         run.json / API / frontend            → 빌드 그린
5. P7         테스트 보강 + 회귀 fixture
6. P5b        review_advocate 수렴                 → 회귀 그린 필수 (위험 시 1–5 체크포인트 유지)
```

---

## 핵심 파일

| 파일 | 변경 |
|---|---|
| `src/agent_lab/role_plan.py` | **신규** — RoleSpec, `resolve_role_plan`, `persona_for_agent` |
| `src/agent_lab/topic_router.py` | `CategoryRoute.role_plan`, `category_dict` |
| `src/agent_lab/reply_policy.py` | 주입 seam — `build_guidance_parts` line 160 직후 |
| `src/agent_lab/room_consensus_rounds.py` | `_turn_roles` stash ~line 67; `_maybe_escalate` 리셋 line 148–184 |
| `src/agent_lab/room_consensus.py` | `recombination_follow_up` 재사용 — 합성자 출처 |
| `src/agent_lab/verified_loop.py` | producer_reviewer 역할 해석 — 단일 출처 |
| `src/agent_lab/room_agent_capabilities.py` | specialist 흡수 — `capability_preamble_block` line 203–226 |
| `src/agent_lab/room_preset.py` | description + `preset_catalog` role_policy |
| `src/agent_lab/room_turn_meta.py` | run.json `roles` 스냅샷 |
| `app/server/routers/room.py` | `GET /room/roles` |
| `web/src/utils/planMeta.ts` | 역할 칩 읽기 |
| `web/src/api/client.ts` | roles 타입 |
| `tests/test_role_plan.py` | **신규** |
