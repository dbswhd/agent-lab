# CX1 — Source registry (2026-07-16)

> [09-context-engineering.md](../09-context-engineering.md) §11 CX1의 산출물. `context/recipe.py`의
> `select_context()`는 순수 selector이고 실제 프로젝트 소스를 `ContextItem`으로 만드는 producer가
> 없다 — 이 문서가 지금 존재하는 producer를 실제 코드에서 찾아 §4의 taxonomy로 분류한다.
> **판정을 바꾸지 않는다** — CX2(ContextNeed/recipe를 실제 producer에 연결)를 시작할 근거 문서다.

## 1. 현재 producer 인벤토리

`context/bundle.py`(레거시 assembler, 798줄)와 그 아래로 호출되는 모듈들이 실제 소스 목록이다.
`select_context()`는 아직 이 producer들 중 어느 것도 소비하지 않는다 — 전부 `bundle.py`가
문자열 concat으로 직접 조립한다.

| producer | source | SourceClass | authority | freshness | owner |
| --- | --- | --- | --- | --- | --- |
| `project_memory.py::bootstrap_project_md` | `.agent-lab/PROJECT.md` (bootstrap-time 생성) | project_doc | 중상 | 재부트스트랩 필요 시까지 | 파일시스템 heuristic |
| `session/guidance.py` L394 | `.agent-lab/PROJECT.md` (session_guidance가 1500자 cap으로 주입) | project_doc | 중상 | 매 turn 재읽음 | session/guidance.py |
| `workspace/md.py::read_agents_md_for_injection` | workspace-root `AGENTS.md` (flat, 단일 파일) | project_doc | 중상 | 매 turn 재읽음 | workspace/md.py |
| `workspace/md.py::read_agents_md_hierarchy_for_injection` → `repo_tree_context.py::build_per_dir_agents_block` | plan path hint부터 root까지 ancestor chain의 `AGENTS.md` 전부 | project_doc | 중상 | plan path 기준 매번 재수집 | repo_tree_context.py |
| `workspace/md.py::read_shared_context_for_injection` | workspace-root `SHARED_CONTEXT.md` | project_doc | 중상 | 매 turn 재읽음 | workspace/md.py |
| `repo_tree_context.py::build_repo_tree_block` | repo 파일 tree(depth-limited listing) | repo_context | 중상 | commit-bound(디렉터리 스냅샷) | repo_tree_context.py |
| `session/guidance.py::build_session_guidance_block` | session phase/workspace binding/steer 안내문 | human_intent | 높음 | 실시간 | session/guidance.py |
| `reply_policy.py::build_guidance_parts` | reply policy·roster·divergence 지시문 | system_invariant | 최상 | 실시간 | reply_policy.py |
| `mission/notepad.py::build_mission_wisdom_block`(→ `runtime/context.py` 얇은 wrapper) | session-scoped mission notepad tail | episode | 중 | session-local, mission 종료 시 만료 | mission/notepad.py |
| `steer.py::drain_steer_follow_up` | Human steer 후속 지시(drain 후 소비됨) | human_intent | 높음 | 1회성(drain) | steer.py |
| `wisdom/index.py::search_wisdom_index` | cross-session wisdom index 검색 hit(evidence/notepad 문서 기반) | semantic_memory | 중상 | relevance-scored, supersede 가능 | wisdom/index.py |
| `wisdom/playbook.py::playbook_bullets_for_topic` | 승인된 playbook bullet(harness_rev로 quarantine 가능) | semantic_memory | 중상 | harness_rev 기준 quarantine | wisdom/playbook.py |
| `wisdom/store.py::wisdom_query`/`wisdom_list_recent` | append-only wisdom entry log | episode | 중 | append 순서, 별도 supersede 없음 | wisdom/store.py |
| `context/bundle.py::_format_clarity_facts` | run_meta의 clarity fact 필드 | runtime_state | 높음 | 실시간 | context/bundle.py |
| `context/bundle.py::_format_decision_ledger` | run_meta의 decision ledger(최근 N건) | runtime_state | 높음 | 실시간, capped ring buffer | context/bundle.py |
| `context/bundle.py::_format_grounding_block` | run_meta의 grounding/consensus 상태 | runtime_state | 높음 | 실시간 | context/bundle.py |

## 2. 중복/다중 표현 소스 (CX1 acceptance criteria)

| 발견 | 설명 | 판단 |
| --- | --- | --- |
| AGENTS.md — flat vs hierarchy | `read_agents_md_for_injection`(workspace-root 1개)과 `read_agents_md_hierarchy_for_injection`(plan path ancestor chain 전체)이 별도 함수로 존재 | **중복 아님** — 서로 다른 scope(root-only vs per-dir chain)를 의도적으로 분리한 것. 다만 CX1 taxonomy 관점에선 둘 다 같은 `SourceClass.PROJECT_DOC`으로 합쳐지므로, recipe가 이 둘을 구분해서 authority를 줄지는 CX2에서 결정 필요 |
| PROJECT.md — bootstrap vs injection | `project_memory.py`가 파일을 **쓰고**, `session/guidance.py`가 그 파일을 **읽어서 주입**함 | **중복 아님, 정상적인 producer/consumer 분리** — 다만 두 파일이 서로의 존재를 모르고 "PROJECT.md" 문자열 경로를 각자 하드코딩(`.agent-lab/PROJECT.md`)하고 있어 경로가 바뀌면 한쪽만 갱신될 위험이 있다 |
| wisdom 3계층 — notepad(session) vs index(cross-session search) vs store(append log) vs playbook(승인된 규칙) | 이름이 비슷해 보이지만(`mission/notepad`, `wisdom/index`, `wisdom/store`, `wisdom/playbook`) 실제로는 4개의 서로 다른 저장소·수명·authority를 가진 별개 소스 | **중복 아님** — 하지만 taxonomy 문서(§4)엔 "Episode memory"/"Semantic memory" 2종류만 있어 4개를 2종류에 강제로 매핑해야 함(§1 표에서 notepad/store→episode, index/playbook→semantic_memory로 매핑) — 구분이 거칠다는 게 발견 |

## 3. Taxonomy 갭

`context/recipe.py::SourceClass`(10종)에는 09 문서 §4의 taxonomy 11종 중 **`agent_opinion`이 없다**.
Room의 다른 agent 분석/의견을 컨텍스트에 넣는 경로가 실제로 있는지(`_format_grounding_block` 등이
근접) 확인이 필요 — CX2에서 `SourceClass`를 11종으로 맞출지, 지금 10종을 taxonomy 쪽에서 줄일지
결정해야 한다.

## 4. CX1 acceptance criteria 대조

| 기준 | 상태 |
| --- | --- |
| 모든 source에 authority, freshness, security, owner | §1 표 완료(security 열은 생략 — 지금 producer 전부 `trusted=True` 취급, untrusted 소스(§8 tool/외부 콘텐츠) 감사는 CX6 소관으로 남김) |
| 중복 source와 다중 표현 발견 | §2 완료 — 진짜 버그성 중복은 없었지만, taxonomy 세분화 필요성(§3)과 하드코딩된 경로 이중관리(§2 PROJECT.md) 발견 |
| provider-specific prompt source 분리 | 미착수 — `bundle.py`가 Claude/Kimi 공용 텍스트만 다루고 provider별 분기는 발견 안 됨(추가 확인 필요, 이번 감사 범위 밖) |

## 5. 다음

CX2(ContextNeed/recipe)는 이 표의 producer들을 실제로 `ContextItem`으로 변환하는 어댑터가 필요하다 —
지금 `select_context()`는 여전히 synthetic `ContextItem` 단위 테스트에서만 쓰인다. `SourceClass`에
`agent_opinion`을 추가할지(§3)가 CX2 착수 전에 결정돼야 하는 유일한 열린 질문이다.
