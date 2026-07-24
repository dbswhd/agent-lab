---
slug: agent-lab-ux-flow-alignment-roadmap
status: approved
intent: clear
review_required: false
pending-action: execute .omo/plans/agent-lab-ux-flow-alignment-roadmap.md in a separate implementation session
approach: freeze the current Decision Queue UX contract, restore truthful browser acceptance evidence, then roll out routing and Mission authority through bounded human-gated cohorts
---

# Draft: agent-lab-ux-flow-alignment-roadmap

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
| id | outcome | status | evidence path |
|---|---|---|---|
| UX-SSOT | Topic-only Composer와 단일 Decision Queue를 제품·문서의 공통 계약으로 고정한다. | active | `web/src/utils/roomComposerPrefs.ts`, `web/src/utils/composerStackLane.ts`, `web/src/utils/workspaceTabs.ts` |
| ACCEPTANCE | 주제 입력부터 Oracle PASS 완료까지 실제 브라우저 골든 여정을 재현하고 증거를 남긴다. | active | `web/e2e/wave-b-journey.spec.ts`, `web/e2e/ui-simplification.spec.ts` |
| ROUTING | TurnContract를 shadow 관측에서 roles/adaptive로 안전하게 승격할 판단 근거를 만든다. | active | `src/agent_lab/room/turn_contract.py`, `src/agent_lab/room/preset.py` |
| AUTHORITY | Mission dual-write/read-model을 bounded cohort에서 plan→Inbox→execution 순으로 권한 전환한다. | active | `src/agent_lab/mission/dual_write.py`, `src/agent_lab/plan/execute_merge.py` |
| OPERATIONS | dogfood·Oracle·repair·false-success 지표로 실제 운영 준비도를 판정한다. | active | `docs/NOW.md`, dogfood/feedback reports |
| HARDENING | 큰 UI/authority 모듈과 번들 위험은 계약·인수증거가 고정된 뒤 분리·최적화한다. | deferred | `ComposerEventStack.tsx`, `HumanInboxPanel.tsx`, web build output |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
| assumption | adopted default | rationale | reversible? |
|---|---|---|---|
| 사용자 결정 표면 | Work 탭을 복원하지 않고 Composer Decision Queue를 SSOT로 유지 | 사용자가 확정한 흐름과 현재 코드가 이 방향에 일치 | yes |
| Decision Queue 우선순위 | 현행 `plan_approval → execute_queue → consensus → inbox → clarify → work`를 기준선으로 두되 골든 여정에서 UX 충돌을 검증 | 코드상의 명시적 product SSOT이며 변경 전 증거가 필요 | yes |
| TurnContract 기본값 | 계획 수행 중에는 `shadow` 유지; 관측 기준 통과 후 별도 Human GO로 roles/adaptive 승격 | 안전·비용·행동 범위를 바꾸는 cross-cutting default | yes |
| Mission cutover | bounded allowlist cohort와 legacy fallback을 유지; full traffic과 hard delete는 별도 Human GO 전까지 금지 | 비가역 데이터·권한 전환을 분리 | yes |
| 테스트 전략 | 문서/계약 정정 후 browser regression을 먼저 red→green으로 만들고, 이후 routing/authority 변경은 테스트 우선 | 현재 가장 큰 불확실성은 구현 존재가 아니라 실제 UX 증거의 신뢰성 | yes |

## Findings (cited - path:lines)
- Topic-only Composer와 implicit supervisor는 코드상 명시되어 있다 (`web/src/utils/roomComposerPrefs.ts:3-7`).
- Decision Queue는 한 번에 하나의 active lane을 택하며 우선순위가 코드로 고정되어 있다 (`web/src/utils/composerStackLane.ts:23-36`, `web/src/utils/composerStackLane.ts:75-89`).
- Work 탭은 제거되었고 legacy work/plan/review는 transcript로 정규화된다 (`web/src/utils/workspaceTabs.ts:13-19`, `web/src/utils/workspaceTabs.ts:52-64`).
- USER-GUIDE는 여전히 Work 탭·Workbench 구조를 현행처럼 설명한다 (`docs/USER-GUIDE.md:200-231`, `docs/USER-GUIDE.md:259-289`)면서 뒤에서는 topic-only/Decision Queue를 설명해 자기모순이다 (`docs/USER-GUIDE.md:397-412`).
- Room 역할 문서는 제거된 Composer Plan toggle 표면을 현행처럼 설명한다 (`docs/05-room-agent-roles.md:1-27`).
- UI surface map은 헤더가 In progress/D0인데 후반은 구현 완료라고 기록한다 (`docs/redesign-2026-07/11-ui-ux-surface-map.md:1-12`, `docs/redesign-2026-07/11-ui-ux-surface-map.md:134`).
- NOW는 Wave B 브라우저 journey 4/4를 완료 증거로 기록한다 (`docs/NOW.md:32`)지만 현재 테스트는 세션을 이름으로 바로 클릭하고 (`web/e2e/wave-b-journey.spec.ts:423-425`) 영문 fixture를 Dogfood로 자동 분류하는 UI 정책 (`web/src/utils/dogfoodSessions.ts:17-32`) 때문에 0/4 navigation timeout이다.
- TurnContract의 실제 기본 권한은 adaptive가 아니라 shadow다 (`src/agent_lab/room/turn_contract.py:146-150`).
- Mission authority는 bounded cohort이며 full cutover와 M6 hard delete에 Human 판정이 필요하다 (`docs/NOW.md:36-38`).
- core path의 단위/통합 기준선은 건전하다: `make test-fast` 3592 pass, targeted pytest 233 pass, Vitest 179 pass, build pass, smoke 38 baselines pass, UI simplification Playwright 2/2 pass. 따라서 다음 병목은 기능을 새로 만드는 것보다 UX 계약과 실제 브라우저 증거를 맞추는 일이다.

## Decisions (with rationale)
- 순서는 UX 계약 → 인수증거 → routing → authority → 운영 판정으로 고정한다. 뒤 단계가 앞 단계의 truth를 소비하기 때문이다.
- 문서의 shipped/complete는 “코드 또는 테스트가 존재함”이 아니라 “현재 기본 경로에서 browser journey와 운영 gate가 green”일 때만 사용한다.
- routing 승격은 `shadow → roles → adaptive`; 각 단계에서 safety-floor 위반 0, route regret/latency/round 비용, shadow/applied parity를 검증한다.
- authority 승격은 `plan dual-write → journal-first Inbox → execution/merge/Oracle`; parity, idempotency, stale/duplicate 409, restart recovery, rollback을 통과한 cohort만 확대한다.
- Oracle FAIL은 완료가 아니며 repair/re-discuss로 돌아간다. retry cap 이후 plateau는 Human decision으로 승격한다.
- full-traffic Mission authority, legacy writer hard delete, 전역 default flip은 이 계획의 자동 실행 범위 밖이며 별도 Human GO가 필요하다.

## Scope IN
- 현재 UX와 문서의 SSOT 재정렬
- Wave B navigation contract 및 full golden journey browser acceptance
- 상태/evidence assertion: plan hash/revision, worktree/diff, merge SHA/checks, Oracle verdict, repair attempt, final audit
- TurnContract 관측·승격 기준과 단계별 rollout
- Mission plan/Inbox/execution authority cohort rollout과 rollback
- dogfood 및 false-success/Oracle coverage 운영 판정
- (후속 계획) 계약 안정화 후 제한적 UI 모듈 분리와 번들 budget

## Scope OUT (Must NOT have)
- Work 탭 복원
- Human plan/execute/merge/repair gate 우회
- 브라우저 증거가 red인 상태에서 문서만 shipped/complete로 변경
- 빈 allowlist를 통한 Mission authority 전역 활성화
- 자동 full-traffic cutover 또는 legacy journal/run data 삭제
- trading/quant extension surface 확대
- 핵심 UX 계약 확정 전의 대규모 UI 리라이트

## Open questions
- 없음. 권한 승격과 hard delete는 실행 중 증거를 제시한 뒤 별도 Human GO로 남긴다.

## Approval gate
status: approved
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
