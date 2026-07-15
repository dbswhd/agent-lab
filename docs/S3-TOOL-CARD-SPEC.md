# 설계: S3 도구 카드 · `[NEED-TOOL:]` · Human Inbox mount 승인

> **상태**: 설계 문서만 (N7, NORTH-STAR §2.1) — **구현 착수 금지** (S1/S2 닫힌 후)
> **ABSORB:** **ABS-P2-skills** = 이 문서의 S3b mount 트랙 — **동결** (S3a-0 관측만 현행). WORKFLOW Composer-preset P2와 무관.
> **기준일**: 2026-07-07
> **북극성 근거**: [`NORTH-STAR.md`](./NORTH-STAR.md) §1 Layer 1 S3a~S3d · §2.1 N7
> **선행 완료**: S3a-0 로컬 인벤토리 (`src/agent_lab/tool_cards.py`, 2026-07-06) — 이 문서가 확장하는 기반
> **의존 문서**: [`N10-USER-LOOP-WISDOM-DRAFT.md`](./N10-USER-LOOP-WISDOM-DRAFT.md) §4-C4(S3a-0) · [`DESIGN-S1-FEEDBACK-LOOP.md`](./archive/rfcs/DESIGN-S1-FEEDBACK-LOOP.md)(RECALL/SetupHint 재사용 대상)

---

## 1. Context — 왜 지금 이 문서만 쓰고 멈추는가

NORTH-STAR의 순서 불변: **S1 dogfood → (선택) S1.5 explore → S2 episode 힌트 → S3**. S3부터 손대면 도구만 늘고 창발은 안 생긴다 — 이건 이미 여러 번 확인된 원칙이다. 지금 시점(2026-07-07)에 S1은 dogfood 초기 관측 단계이고 S2는 동결이므로, S3 구현(에이전트가 실제로 도구를 찾아 mount하는 코드)에 착수할 수 없다.

하지만 **설계는 지금 해둘 가치가 있다** — S3a-0(로컬 인벤토리)을 만들면서 이미 확인했듯, S3의 나머지 조각(S3a 외부 크롤, S3b 연결, S3c 활용 학습, S3d 자기적용)이 무엇을 재사용하고 무엇을 새로 지어야 하는지가 이번에 구체적으로 드러났다. 이 문서는 그 설계를 고정해서, S1/S2가 닫혔을 때 바로 구현에 들어갈 수 있게 한다.

**이 문서가 정의하는 것 (구현 없음):**
1. 도구 카드(Tool Card) 스키마 — S3a-0의 로컬 스키마를 외부 소스까지 포괄하도록 확장
2. `[NEED-TOOL:]` 시그널 문법 — 에이전트가 미션 중 도구 부족을 선언하는 방법
3. Human Inbox 승인 flow — 선언 → 검색 → 후보 제시 → 승인 → mount → 기록의 전체 경로

---

## 2. S3 전체 그림 (S3a-0 ~ S3d)

| 단계 | 내용 | 상태 |
|---|---|---|
| **S3a-0** | 로컬 인벤토리 — 이미 설치된 능력(CC skills·MCP·Codex/Cursor 플러그인)을 도구 카드로 인덱싱, RECALL 시점에 미사용 카드 제안 | ✅ 구현 완료 (`tool_cards.py`) |
| **S3a** | 외부 발견 — MCP registry + CC skills 디렉터리(외부) + Codex/Cursor 플러그인 마켓플레이스를 주기적으로 크롤/인덱싱 | 설계만 (본 문서 §3) |
| **S3b** | 연결 — 에이전트가 도구 부족을 선언(`[NEED-TOOL:]`) → 카드 검색 → 후보 제시 → **Human Inbox 승인 필수** → 세션 스코프 mount | 설계만 (본 문서 §4~5) |
| **S3c** | 활용 학습 — 어떤 카테고리 미션에서 어떤 도구가 clean-pass에 기여했는지 S1 outcome 파이프라인에 기록 | 설계만 (본 문서 §6) — S3a-0의 `tool_card_hit_rate` 패턴을 mount된 도구까지 확장 |
| **S3d** | 자기적용 — Agent Lab이 자기 개발 미션(dogfood)에서 CC skills를 스스로 골라 쓰는 상태 | 판정 기준만 (본 문서 §7) |

**핵심 원칙 (S3a-0에서 이미 검증됨, 이 문서 전체에 적용):**
- 새 학습 루프를 만들지 않는다 — S1 RECALL/RECORD 파이프라인의 입력 차원을 넓힐 뿐이다.
- 새 Inbox kind는 만들되, Inbox 표면 자체는 늘리지 않는다 (모트 5: Human Inbox가 유일한 결정 표면).
- LLM 호출 없이 결정론적으로 가능한 건 전부 결정론적으로 한다 (분류, 매칭 — S1.5 explore 규율과 동일).

---

## 3. S3a — 도구 카드 스키마 (외부 발견까지 포괄)

### 3.1 현재 (S3a-0, 로컬 전용)

`tool_cards.py`의 현재 스키마:

```json
{
  "id": "claude:skill:impeccable",
  "name": "impeccable",
  "agent": "claude",
  "kind": "skill",
  "description": "UI polish, animation, design review",
  "categories": ["standard", "deep"]
}
```

`plugin_discovery.py`가 이미 로컬(스킬 파일, `claude mcp list`, `codex plugin list` 등)에서 채워주는 필드 + S3a-0이 붙인 `categories` 태그가 전부다. **외부 소스**(source가 로컬이 아닌 것)를 위한 필드가 없다.

### 3.2 확장 스키마 (S3a 목표)

```json
{
  "id": "mcp:registry:context7",
  "name": "context7",
  "agent": "codex",
  "kind": "mcp",
  "description": "Library documentation lookup",
  "categories": ["standard", "deep"],

  "source": "local | registry | marketplace",
  "source_ref": "https://.../context7 또는 마켓플레이스 slug — 감사용, 클릭 가능해야 함",
  "capabilities": ["docs_lookup", "read_only"],
  "mount": {
    "method": "mcp_stdio | mcp_http | cli_plugin_install | skill_file_copy",
    "command_or_path": "codex mcp add context7 ... (mount 실행에 필요한 실제 커맨드/경로)",
    "risk_level": "low | medium | high",
    "requires_network": true
  },
  "discovered_at": "2026-07-07T00:00:00Z",
  "last_verified_at": "2026-07-07T00:00:00Z",
  "verification_status": "unverified | reachable | broken"
}
```

**필드 추가 원칙:**
- 기존 5개 필드(`id`/`name`/`agent`/`kind`/`description`/`categories`)는 **불변** — S3a-0 소비자(`feedback_advisor.py`)를 깨지 않는다.
- 신규 필드는 전부 **옵셔널**, 기본값 없음(부재 = "로컬 카드"로 하위호환).
- `capabilities`는 자유 텍스트가 아니라 **작은 고정 vocabulary**로 시작 (`read_only`, `write`, `network`, `docs_lookup`, `code_search`, `execute` 등) — MCP tool contract(`mcp_tool_contract.py`)의 allowed/forbidden 셋과 같은 규율.
- `mount.risk_level`은 이 문서 §5의 승인 문구 강도를 결정한다 (high risk → Inbox 문구에 명시적 경고 문장 추가).

### 3.3 발견 소스 (크롤 대상)

| 소스 | 크롤 방법 | 신뢰도 |
|---|---|---|
| MCP registry (공개) | HTTP GET, 결과 캐시 TTL 필요(`plugin_discovery.py`의 60초 캐시 패턴 재사용) | 낮음 — 서명 검증 없음, 항상 `verification_status: unverified`로 시작 |
| CC skills 디렉터리 (marketplace, 외부) | 로컬 스캔과 동일 파서(`_parse_skill`) 재사용, root만 외부 캐시 경로로 교체 | 중간 |
| Codex/Cursor 플러그인 마켓플레이스 | 이미 `config.toml`의 `[marketplaces.*]` 섹션에 등록된 것만 (임의 URL 크롤 금지 — 사용자가 이미 신뢰한 마켓플레이스로 범위 제한) | 중간 |

**의도적 비목표:** 임의 URL/GitHub repo를 크롤해서 "발견"하지 않는다. 사용자가 이미 등록한 마켓플레이스/레지스트리 안에서만 찾는다 — 이건 F1(Default-OFF 무덤) 예방과 같은 이유: 검증 안 된 발견 경로를 넓히면 신뢰가 아니라 노이즈가 는다.

---

## 4. `[NEED-TOOL:]` 시그널 문법

### 4.1 문법 (기존 `[PROPOSED:]`/`[LEARNED:]`와 동일 컨벤션)

```
[NEED-TOOL: <capability 요약> | category=<선택> | reason=<한 줄>]
```

정규식 (기존 `_PROPOSED_RE`/`_LEARNED_RE`와 같은 스타일, `src/agent_lab/agent/envelope.py`에 추가 예정):

```python
_NEED_TOOL_RE = re.compile(r"\[NEED-TOOL:\s*([^\]]+)\]", re.I)
```

**예시:**
```
[NEED-TOOL: Figma에서 디자인 토큰 읽기 | category=deep | reason=현재 워크스페이스에 Figma MCP 없음]
```

파싱된 그룹(`([^\]]+)`)은 `|`로 split해서 `{summary, category?, reason?}`로 분해 — `[PROPOSED:]`가 자유 텍스트 하나만 받는 것과 달리 구조화가 필요한 이유: 검색 매칭(§5.1)에 `category`가 필수 입력이기 때문.

### 4.2 에이전트 프롬프트 가이드 (구현 시 `agents/prompts.py`/`room/roster_context.py`에 추가)

기존 `[PROPOSED:]` 가이드 문구(`roster_context.py:84-86`)와 나란히 배치:

```
도구/능력이 부족해서 막히면 직접 설치를 시도하지 말고
[NEED-TOOL: <무엇이 필요한지> | category=<현재 미션 카테고리> | reason=<왜 막혔는지>]
로 선언하세요. Human이 승인해야 세션에 연결됩니다.
```

**금지 (명시):** 에이전트가 `[NEED-TOOL:]` 선언 없이 스스로 `pip install`, `npm install -g`, MCP 설정 파일 직접 수정 등을 시도하는 것 — 이건 이미 실행 권한(permissions) 레이어에서 막혀야 하지만, 프롬프트 레벨에서도 명시.

---

## 5. Human Inbox 승인 flow

### 5.1 선언 → 검색 → 후보

턴 종료 시점(기존 N10 계열 훅과 같은 위치, `room/agent_invoke.py::_finalize_durable_turn` 부근)에서:

1. 이번 턴 에이전트 응답에서 `[NEED-TOOL:]` 마커 추출 (`extract_need_tool_signals`, `[LEARNED:]` 추출과 동일 패턴).
2. 마커가 없으면 즉시 종료 (fail-open, 다른 N10 계열 훅과 동일).
3. 마커의 `category`(또는 이번 턴의 `route.category`로 대체)로 **S3a-0의 `unused_tool_cards_for_category()`를 먼저 조회** — 이미 로컬에 설치돼 있는데 안 쓰인 것부터 제안 (외부 크롤보다 로컬 우선 — S3a-0의 핵심 통찰 재사용: "발견보다 회상이 먼저").
4. 로컬에 후보가 없을 때만 §3의 확장 크롤 소스(S3a) 조회.
5. 후보 0~3개로 압축 (많아도 3개 — Inbox 카드가 선택지 과잉으로 무거워지지 않게, 기존 `_escalate_drift`의 "최대 5개 표시" 관례와 유사).

### 5.2 Inbox 카드 (신규 kind: `tool_mount`)

기존 N10 계열 Inbox 확장과 완전히 같은 패턴 (`human_inbox.py`의 `InboxKind` Literal에 추가, `usesGenericOptionsUi`에 포함 — 새 UI 컴포넌트 불필요):

```python
create_inbox_item(
    folder,
    kind="tool_mount",
    source="need_tool_signal",
    prompt=f"{agent}가 도구가 필요하다고 선언했습니다: {summary}. 후보: {candidate_names}",
    summary=reason,
    options=[
        {"id": f"mount:{card_id}", "label": f"{card.name} 연결"} for card in candidates
    ] + [{"id": "reject", "label": "연결하지 않음"}],
    refs=[human_turn, agent, *[c.id for c in candidates]],
)
```

**승인 시 (resolve dispatcher, `tool_mount_dispatch.py` 가칭):**
- `mount.risk_level == "high"`인 카드는 옵션 라벨에 위험 문구 강제 포함 (예: `"context7 연결 (⚠ 외부 네트워크 접근)"`) — 승인 UI에서 위험이 숨겨지지 않게.
- 승인된 카드는 **세션 스코프**로만 mount — `agent_plugins`(기존 `patch_agent_plugins`, `plugin_discovery.py`)에 추가, 워크스페이스나 전역 설정은 건드리지 않는다 (N10b Rule Sync의 "전역 파일은 별도 승인" 원칙과 일치 — mount는 세션, sync는 별도 상위 결정).
- `run.json`에 `tool_mount_events` 배열로 기록 (누가 언제 무엇을 왜 승인했는지 — F4 감사 원칙).

### 5.3 거절 시

`reject` 선택 시 아무 것도 mount하지 않고, 같은 `(agent, capability_summary)` 조합은 이번 세션에서 재제안하지 않음 (N10a/C1/C2/C3가 이미 쓰는 dedup 패턴 — `_pending_*` 헬퍼 재사용).

---

## 6. S3c — 활용 학습 (mount된 도구의 outcome 연결)

S3a-0이 이미 "제안된 도구"를 outcome ledger까지 관통시켰다(`SetupHint.tool_card_suggestions` → `turns[].category` → `turn_metrics` → `outcomes.jsonl` → `feedback_report.py`의 `tool_card_hit_rate`). S3c는 이 파이프라인을 **"제안됨"에서 "실제로 mount되어 쓰임"으로 한 단계 좁히는 것**뿐이다 — 새 학습 루프가 아니라 같은 계측의 정밀도를 올리는 것.

- `outcome_harvester.py`의 outcome row에 `tool_card_mounted: list[str]` 필드 추가 (기존 `tool_card_suggestions`와 나란히 — "제안됨" vs "실제 채택됨" 구분).
- `feedback_report.py`의 `tool_card_hit_rate`를 두 버전으로 분리: `suggested_hit_rate`(현재 구현, S3a-0) / `mounted_hit_rate`(신규, S3c) — S3a-0 문서에 이미 명시한 스코프 축소("채택 여부까지는 추적 안 함")를 정확히 메우는 지점.

**측정:** `mounted_hit_rate` > `suggested_hit_rate`이면 "제안이 실제로 유용해서 채택으로 이어졌다"는 신호로 해석 — D4 KPI 후보.

---

## 7. S3d — 자기적용 판정 기준

S3 "완성"의 정의는 기능 목록이 아니라 **관측 가능한 사건**이어야 한다 (D-사다리 원칙: 측정 없는 완료 선언 금지). 판정 기준:

| # | 조건 | 관측 방법 |
|---|---|---|
| 1 | Agent Lab 자기 개발 미션(dogfood) 중 `[NEED-TOOL:]`이 최소 1회 발생 | `outcomes.jsonl`에서 `tool_mount_events` 존재 여부 |
| 2 | 그 요청이 Human Inbox를 거쳐 실제로 mount됨 (거절 아님) | `tool_mount_events[].decision == "mounted"` |
| 3 | mount된 도구가 같은 미션의 clean-pass에 기여함 (`execution.oracle.verdict == pass`) | S3c `mounted_hit_rate` 해당 row |
| 4 | 위 사이클이 서로 다른 카테고리에서 최소 2회 반복 | `MIN_SAMPLE`과 동일한 규율 — 우연 1회를 "완성"으로 부르지 않는다 |

4개 전부 만족 시 "S3d 완성 관측" — **의식적 formal closure는 없음** (S1과 동일 원칙, dogfood-first).

---

## 8. 재사용할 기존 자산 (신규 작성 금지 대상)

| 조각 | 기존 위치 | 용도 |
|---|---|---|
| 도구 카드 기본 스키마 | `src/agent_lab/tool_cards.py` | §3.2 확장의 기반, 5개 필드 불변 |
| 로컬 발견 스캔 | `src/agent_lab/plugin_discovery.py` | S3a 외부 발견의 파서 재사용 (`_parse_skill` 등) |
| RECALL 채널 | `src/agent_lab/feedback_advisor.py::advise_setup` | S3a/S3a-0 제안 주입 지점, 신규 게이트 불필요 |
| Inbox 생성/dedup 패턴 | `human_inbox.py::create_inbox_item` + N10 계열 `_pending_*` 헬퍼 | §5.2~5.3, 신규 UI 불필요 (`usesGenericOptionsUi`) |
| 세션 스코프 allowlist | `plugin_discovery.py::patch_agent_plugins`/`agent_plugins` | §5.2 mount 대상, 전역 설정 오염 방지 |
| outcome ledger 관통 패턴 | `outcome_harvester.py` + `turn_metrics.py` (S3a-0에서 이미 배선) | §6, 필드만 추가 |
| MCP 도구 allowlist 규율 | `mcp_tool_contract.py` (allowed/required/forbidden) | §3.2 `capabilities` vocabulary 설계 참고 |
| 마커 파싱 컨벤션 | `agent/envelope.py::_LEARNED_RE`, `room/turn_policy.py::_PROPOSED_RE` | §4.1 `_NEED_TOOL_RE` |

**신규로 지어야 하는 것 (구현 시):** §3.2 확장 필드 파서, §3.3 외부 크롤러(3개 소스), §4.1 `_NEED_TOOL_RE`/추출 함수, §5.2 `tool_mount` Inbox kind + dispatcher, §6 `tool_card_mounted` 필드 + `mounted_hit_rate`.

---

## 9. 모트 체크 (NORTH-STAR §6과 동일 형식)

| 모트 | 판정 |
|---|---|
| BLOCK→409 | 중립 |
| worktree 격리 | 중립 |
| Oracle+Repair | 중립 (mount 자체는 execute가 아님) |
| run.json 감사 | **강화** — `tool_mount_events`로 무엇을 언제 왜 연결했는지 전부 기록 |
| Human Inbox | **강화** — mount는 예외 없이 승인 경유, 세션 스코프로만 제한 |

**금지 (명시, S3a-0/N10b와 동일 원칙 계승):**
- Human 승인 없는 자동 mount 금지 (설령 `risk_level: low`여도).
- 워크스페이스/전역 설정 파일에 mount 결과를 자동 반영 금지 — 그건 별도 결정(N10b Rule Sync류)이지 S3b의 책임이 아니다.
- 임의 URL 크롤 금지 (§3.3) — 사용자가 이미 등록한 소스 안에서만.

---

## 10. 구현 순서 (착수 시, 지금 아님)

1. §3.2 스키마 확장 — `tool_cards.py`에 옵셔널 필드 추가, 기존 5개 필드/소비자 무변경 확인 (회귀 테스트로 고정).
2. §4.1 `_NEED_TOOL_RE` + 추출 함수 — `[LEARNED:]` 추출과 동일 패턴, 유닛 테스트 우선.
3. §5.2 `tool_mount` Inbox kind + dispatcher — N10 계열과 완전히 같은 코드 모양(신규 kind, `usesGenericOptionsUi` 추가, resolve 핸들러).
4. §3.3 외부 크롤러 — 소스 3개 중 하나(가장 안전한 것부터, 아마 CC skills 마켓플레이스)만 먼저.
5. §6 outcome 필드 확장 — `tool_card_mounted`, `mounted_hit_rate`.
6. §7 판정 관측 — 코드 아님, dogfood 중 자연 발생 대기.

**착수 트리거 (재확인):** S1 dogfood formal 재검토(`by_source.history.n` ≥ 30) 이후, 또는 Human이 명시적으로 순서를 바꾸라고 지시할 때만.
