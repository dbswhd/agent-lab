# GJC 세션 핸드오프 노트 (단일 진실원본 · 재개 시 가장 먼저 읽을 것)

> 목적: 다른 작업을 하고 돌아온 에이전트(또는 나)가 **기억이 아니라 이 파일 + 디스크 상태**로 phase를 복원하기 위함.
> 규칙: 작업 재개 시 아래 "재개 절차"를 메모리보다 우선해서 실행한다.

최종 갱신: 2026-06-23 (stage-aware routing + anti-drift ultragoal 완료 시점)

---

## 0. 재개 절차 (RESUME — 항상 이 순서로 먼저)

1. `gjc ultragoal status --json` — 현재 ultragoal 스토리/phase
2. `goal({op:"get"})` — GJC goal 모드 상태 (active/paused/none)
3. 필요 시 `gjc state ultragoal read --json` — 스킬 phase / current_phase
4. 특정 세션 미션이면: 해당 `sessions/<id>/run.json`의 `mission_loop.phase` / `plan_workflow.phase`
5. 그 다음에야 작업 판단. **메모리에 의존해 "다 했다/안 했다" 단정 금지** (완료감사 규칙).

---

## 1. 현재 상태 (사실)

- **ultragoal: COMPLETE** — 3개 스토리 전부 complete + 검증 영수증 보유.
  - G001 Stage-aware routing core + RoutingDecisionLog telemetry (per-goal receipt)
  - G002 Anti-drift A — 패널 턴 facts/ledger 재주입 (per-goal receipt)
  - G003 Anti-drift B 만장일치 red-team + fresh-eyes critic seat + 최종검증 (final-aggregate receipt)
- 두 플래그 default-OFF: `AGENT_LAB_STAGE_ROUTING`, `AGENT_LAB_ANTIDRIFT`. OFF-parity 입증됨.
- 검증: `make test-fast` 1529 passed/1 skipped/0 failed · mypy ratchet 243/243 · ruff clean.
- 소스/테스트 커밋됨: `0309942`(routing), `e237c6e`(antidrift). durable 플랜/리뷰 아티팩트 커밋됨.

## 2. 정본 경로 (CANONICAL — 경로 드리프트 주의)

- ultragoal 정본: **`.gjc/ultragoal/`** (git 추적/커밋됨) — goals.json / ledger.jsonl / brief.md
- 주의: `GJC_SESSION_ID`가 설정돼 있으면 `gjc ultragoal`은 `.gjc/_session-<id>/ultragoal/`(gitignore)를 본다.
  두 경로가 어긋나면 `status: missing` 또는 `goal complete` 차단이 발생한다.
  - 복구법: 정본을 세션 경로로 미러
    `cp .gjc/ultragoal/{goals.json,ledger.jsonl,brief.md} .gjc/_session-$GJC_SESSION_ID/ultragoal/`
  - 또는 그 반대로 정본을 최신본으로 동기화 후 커밋.
- 리뷰/QA 증거: `artifacts/g00{1,2,3}-architect-review.md`, `artifacts/g00{1,2,3}-*-qa.txt` (커밋됨)
- ralplan 합의 기록: `.gjc/plans/ralplan/2026-06-19-1737-8485/` (stage-09~14, pending-approval.md)
- 스펙: `.gjc/specs/deep-interview-stage-aware-selective-multiagent.md`

## 3. 미해결/후속 (선택, 비차단)

- **독립 재검토 보류**: 이번 세션 내내 role-agent 서브에이전트(architect/critic/executor) 디스패치가 다운이라
  모든 게이트 레인을 리더 인라인(소스검증·공개)으로 수행. 디스패치 복구 시 3개 스토리 독립 재검토 권장.
- **anti-drift 행동효과 실측(스펙상 deferred)**: 두 플래그 `=1` 도그푸딩으로 실제 drift 감소 측정.

## 4. 다음 후보 작업 (백엔드 레이어 갭 분석 결과 — 우선순위순)

승인 시 deep-interview→ralplan으로 정식 스펙/계획 진행(실행은 별도 승인).

- **P0 — 체크포인트/재개 레이어 (G1, 최우선)**: LangGraph식 phase별 스냅샷 + 재개를 mission_loop/plan FSM에 추가
  (신규 `checkpoint_store.py`, thread=session_id, time-travel/크래시 중간재개). ROI 최고.
- **P1 — 심볼-그래프 repo-map (G2)**: `repo_tree_context`를 Aider식 PageRank repo-map으로 승격(tree-sitter 자산 활용).
- **P2 — tool-output auto-compaction (G3) ✅ SHIPPED (uncommitted)**: `room_context.prepare_recent_messages`에 char-trim 직전 결정론적 선처리 추가 — pre-current-turn agent 메시지의 over-cap 코드펜스(```)를 head+tail+`[...truncated N chars...]`로 `dataclasses.replace` 복사 truncate(현재턴 pin/사용자 메시지 제외, copy-on-truncate, 원본 불변). 플래그 `AGENT_LAB_COMPACT_TOOL_OUTPUT`(off) + `AGENT_LAB_COMPACT_TOOL_CHARS`(2000). 검증: `tests/test_tool_output_compaction.py` 17 passed · `make test-fast` 1600 passed/1 skipped · mypy 243/243 · ruff clean · OFF-parity 입증. ralplan stage-11~15 합의(Architect WATCH/1 HIGH→AC10→Critic OKAY). LLM 요약은 보류.
- **P3 — edit-time linter 게이트 + 샌드박스 강화 (G4)**: SWE-agent식 edit→문법검증 거부 + 옵션 Docker 런타임 adapter.
- **P4 — 표준 평가 하네스 연동 (G5)**: `session_score`↔SWE-bench Verified 어댑터(FAIL_TO_PASS), 모델 vs 하네스 분리측정.
- **P5 — 통일 event bus + 구조화 메모리 store (G6/G7)**: SSE/trace/run-patch를 단일 typed event stream으로, LangGraph Store식 namespace KV.

## 5. 이 세션에서 학습한 운영 함정 (반복 방지)

- **lineage freeze**: skill 활성/phase 전환/create-goals가 턴 중간에 일어나면 도구 권한 경계가 턴 시작 시점에 고정 →
  edit/write/product-bash가 다음 사용자 메시지까지 차단. 해결: 실제 사용자 메시지(또는 goal resume 후 새 턴).
- **clean-command 규칙**: `gjc` 명령에 파이프/`&&`/env 주입을 섞으면 phase 가드에 걸린다. 단일 클린 커맨드로.
- **mypy ratchet**: 베이스라인 `tests/fixtures/mypy-ratchet.json` = 243 (room.py 제외). 신규 코드는 delta 0 유지.
  per-file mypy는 노이즈가 있으니 `scripts/mypy_ratchet.py --check`로 판정.
- **fast-bucket 예산**: 테스트 추가 시 `tests/test_integration_registry.py`의 budget(현재 1560) 상향 필요할 수 있음.
