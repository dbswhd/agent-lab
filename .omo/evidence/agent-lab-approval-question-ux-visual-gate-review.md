# Agent Lab approval/question UX final gate review

recommendation: REJECT

reviewedAt: 2026-07-12 Asia/Seoul

goal: `agent-lab-approval-question-ux-visual`

baseline: `ccdf465bccde18285a927133d3c3261bf7395dba`

reviewedDiffSha256: `981b481a51bd8c0d6135dbc6572dd0c5d800a0e7d1c0bee35f3309db8a5ad92b`

## originalIntent

최신 Agent Lab 승인/질문 UX를 사용자 관점에서 읽기 전용으로 최종 검토한다. 특히 모바일에서 Workbench가 현재 결정을 가리지 않는지, 상위 decision queue와 카드가 같은 말을 반복하지 않는지, 승인/차단 상태가 이해·조작 가능한지, 질문 선택지가 올바른 radio semantics와 방향키/Home 동작을 갖는지 확인한다.

## desiredOutcome

- 375px 모바일 승인·차단 상태에서 Workbench가 사라지고, 현재 카드·주요 CTA·composer가 가려지지 않는다.
- queue는 현재 결정의 종류만 요약하고, 카드 본문은 구체 질문·영향·차단 사유를 제공해 정보가 중복되지 않는다.
- 정상 승인에는 하나의 명확한 primary action이 있고, 차단 시 그 action은 비활성화되며 바로 인접한 사유와 해소 수단이 보인다.
- 질문 옵션은 radiogroup/radio 계약을 완전히 지키며 ArrowUp/Down/Left/Right, Home/End가 선택과 포커스를 함께 이동한다.
- 현재 diff에 결박된 테스트, 수동 QA matrix, executor evidence, code-review report, notepad가 동일한 완료 주장을 뒷받침한다.
- diff에는 중복·과잉 방어·불필요한 추상화·구현 미러링 테스트·과대 모듈 같은 slop이 남아 있지 않는다.

## blockers

1. **Radio semantics가 완전하지 않다.** `HumanInboxPanel.tsx:398-424`는 `radiogroup`/`radio`와 `aria-checked`를 사용하지만 각 옵션이 기본 `button`의 `tabIndex=0`을 그대로 가진다. 따라서 Tab이 그룹에 한 번 들어오고 나가야 하는 radio-group roving-tabindex 계약과 달리 모든 옵션을 순회한다. `:258-282`의 ArrowUp/Down/Left/Right/Home/End 구현은 선택과 `.focus()`를 이동시키지만, 현재 마크업 계약 전체를 충족하지 못한다.
2. **키보드 테스트가 요구 동작을 충분히 증명하지 않는다.** `plan-approval.spec.ts:404-409`는 ArrowDown/Home 뒤 `aria-checked`만 확인한다. 포커스 이동을 assert하지 않아 `.focus()`가 제거되어도 통과하며, Tab이 그룹을 한 번만 통과하는지, ArrowUp/Left/Right/End, wrap-around, Space, disabled 상태를 검증하지 않는다. `/tmp/agent-lab-plan-question-1440.png`도 선택 전 상태라 selected/focus 시각 증거가 아니다.
3. **상위 queue와 질문 카드의 의미 중복이 남아 있다.** 최신 질문 캡처에서 queue는 `결정 필요 / 질문 응답`, 바로 아래 카드는 `질문에 답해주세요`를 반복한다 (`DecisionQueueHeader.tsx:88-93`, `HumanInboxPanel.tsx:796-815`). 승인 표면은 queue `계획 검토`와 카드의 영향 설명이 구분되어 이전보다 낫지만, 카드 heading과 footer CTA가 모두 `승인하고 실행`으로 동일하다 (`PlanApprovalStrip.tsx:66-70`, `:177-185`).
4. **직접 slop pass가 실패했다.** `tokens.css:54-79`와 `:356-380`에서 light/dark decision token 블록이 각각 완전히 중복된다. `DecisionQueueHeader.tsx:17-54`는 닫힌 `Exclude<ComposerStackLane, "work">` union을 모두 처리한 뒤 불필요한 `default` fallback을 두어 exhaustive proof를 약화한다. `HumanInboxPanel.tsx:262-275`의 중첩 ternary도 새 키 처리 흐름을 불필요하게 어렵게 만든다.
5. **수정된 production 모듈이 programming 유지보수 게이트를 넘는다.** pure LOC는 `HumanInboxPanel.tsx` 806, `PlanApprovalStrip.tsx` 260, `WorkToolPanel.tsx` 357이다. 모두 이번 diff에서 수정됐고 SIZE_OK 예외나 현재 code-review의 분리 근거가 없다.
6. **필수 provenance 아티팩트가 없다.** 현재 UX diff hash에 결박된 code-review report, manual QA matrix, executor evidence bundle, notepad path가 제공되거나 발견되지 않았다. `web/test-results/.last-run.json`은 `status: passed`만 있고 실행 명령, 테스트 목록, diff hash가 없어 완료 증거로 사용할 수 없다. 기존 `.omo/evidence/orchestration-enforcement-code-review.md`와 hands-on QA는 다른 orchestration 변경용이다.
7. **code-review report의 remove-ai-slops/programming coverage가 없다.** 현재 diff에 대한 report 자체가 없으므로 duplicate tokens, overfit/implementation-mirroring tests, unnecessary fallback, nested complexity, oversized modules를 같은 기준으로 검토했다는 명시적·지원 가능한 근거도 없다. 이 부재는 직접 발견과 별개의 승인 차단 조건이다.

## userOutcomeReview

- **모바일 Workbench 가림:** 충족. 승인/차단 375×900 캡처에서 Workbench가 없고 카드, CTA, composer가 보인다. `layout.css:1660-1709`도 900px 이하의 모든 active decision lane에서 `.workbench-tile`을 숨긴다. 승인 E2E는 375/768/1280에서 폭과 hidden 상태를 확인하고, 차단 E2E도 375에서 hidden을 확인한다.
- **상위 queue와 카드 문구 중복:** 부분 충족. 승인 queue는 범주, 카드는 영향과 행동을 나누지만 질문의 `질문 응답`/`질문에 답해주세요`는 인접한 의미 반복이다. 승인 카드 내부 heading/CTA도 동일 문구다.
- **승인 상태:** 충족. 데스크톱·모바일에서 `승인하고 실행`이 primary, `수정 요청`이 secondary이며 worktree 영향 설명과 `plan.md` 근거가 함께 보인다.
- **차단 상태:** 충족. 데스크톱·모바일에서 차단 사유가 disabled `승인하고 실행` 바로 위에 보이고, objection의 `수용`/`기각` 해소 동작도 노출된다. E2E `:418-443`은 alert 사유와 disabled CTA 및 모바일 Workbench hidden을 확인한다.
- **질문 radio와 방향키/Home:** 부분 충족. role/aria와 ArrowUp/Down/Left/Right/Home/End 선택·focus 코드는 존재한다. 그러나 roving tabindex가 없고 테스트가 focus/Tab 계약을 증명하지 않아 semantics 완료로 볼 수 없다.

## directSlopAndOverfitPass

- **Obvious comments:** 새 production diff에서 기능을 단순 재진술하는 신규 주석은 주요 blocker로 발견되지 않았다.
- **Over-defensive/dead fallback:** FAIL. exhaustive lane union 뒤 `default` fallback이 불필요하다.
- **Excessive complexity:** FAIL. 키 이동 계산이 중첩 ternary로 구성돼 읽기·확장 비용을 만든다.
- **Needless abstraction/parsing/normalization:** 새 parser/normalizer는 없다. 수동 radio focus 관리 자체는 Home/End 요구 때문에 정당화될 수 있으나 roving tabindex까지 완성되지 않았다.
- **Duplication:** FAIL. light/dark decision token 선언 블록이 각각 두 번 있다.
- **Oversized modules:** FAIL. 수정된 production TSX 3개가 250 pure LOC를 넘는다.
- **Excessive/useless tests:** 신규 question fixture는 실제 UI 경로를 열기 위해 필요하므로 전부 쓸모없다고 보지 않는다. 다만 61-line mock 확장에 비해 제출 payload와 focus/Tab 결과가 검증되지 않아 효율 대비 계약 coverage가 낮다.
- **Deletion-only/removal-only tests:** 신규 deletion-only test는 발견하지 못했다. 이전 negative-copy assertions는 제거됐지만 중복 감소를 직접 고정하는 대체 assertion도 없다.
- **Tautological/implementation-mirroring tests:** FAIL. question test는 `aria-checked` 구현 상태만 확인하고 사용자 결과인 focus 이동·단일 Tab stop·제출 payload를 확인하지 않는다. responsive test도 DOM hidden/scrollWidth는 확인하지만 primary action의 실제 unobscured hit target은 확인하지 않는다.
- **Unnecessary production extraction:** 별도 parser/normalizer 추출은 없으나 `decisionMeta`의 unreachable fallback은 불필요하다.
- **Maintenance burden/scope drift:** FAIL. `WorkToolPanel`의 recovery test는 실제 retry affordance assertion을 제거하고 설명 문구만 남겼다; 현재 범위의 완료 주장에 비해 약한 회귀 보호다.

## codeReviewCoverageCheck

현재 UX diff용 code-review report를 찾지 못했다. 따라서 mandatory remove-ai-slops/programming 관점과 overfit/slop criterion coverage가 report에 명시됐는지 확인할 대상이 없다. 기존 orchestration review는 baseline과 변경 파일이 달라 이 게이트를 지원하지 않는다.

## verificationEvidence

- `git diff --check`: PASS.
- `web/node_modules/.bin/tsc --noEmit`: PASS.
- `npm run format:check`: PASS.
- `npm run lint -- --max-warnings=0`: FAIL, 0 errors/40 warnings. `HumanInboxPanel.tsx:676` 경고는 `git blame`상 기존 코드지만 전체 zero-warning gate는 green이 아니다.
- `playwright test --list web/e2e/plan-approval.spec.ts`: PASS, 6 tests discovered.
- `web/test-results/.last-run.json`: `passed`. 동시 생성된 `.omo/evidence/agent-lab-decision-surface-gate-review.md`도 6 passed를 주장하며 timestamp가 맞지만 raw command log와 diff-hash binding은 없어 독립 executor evidence로 승격하지 않았다.
- E2E는 사용자 요청대로 최신 캡처를 덮어쓰지 않기 위해 이 reviewer의 gate turn에서는 재실행하지 않았다.

## checkedArtifactPaths

- `/tmp/agent-lab-plan-approval-1280.png` — 1280×900, sha256 `b76377e16bcdc85b1bedca5b701471b7bd5c70c69a899a0f9ca0de75bb444141`.
- `/tmp/agent-lab-plan-question-1440.png` — 1440×900, sha256 `2494ff7290220b49c7fc45fe5d7df5a8d9fd9ea60c84067ce0b296fb64f2859d`.
- `/tmp/agent-lab-plan-blocked-1280.png` — 1280×800, sha256 `0c97b9c1796a8d3c304ecccfa5a6bb2e88ce0b2542ce4ef55c7baedd405ef99b`.
- `/tmp/agent-lab-plan-blocked-375.png` — 375×900, sha256 `b414a51188b1723ef81660354cb512cfedf9432b79741cf8cb43dff4159da4e6`.
- `/tmp/agent-lab-plan-approval-375.png` — 375×900, sha256 `c476c7aec63171250023f2e59e818b3d8874ecbe07ddd035734c4d5ce7babfa8`.
- `/tmp/agent-lab-plan-approval-768.png` — 768×900, sha256 `f0d5fd25544f00f25cd5c4f5aa6e39f9f5c295bd139cadeed0741aa0d1cdd89c`; 동시 gate report가 참조해 직접 시각 확인함.
- `web/DESIGN.md`.
- `web/e2e/plan-approval.spec.ts`.
- `web/src/components/ComposerDecisionSurface.tsx`.
- `web/src/components/ComposerNoticeCard.tsx`.
- `web/src/components/DecisionQueueHeader.tsx`.
- `web/src/components/HumanInboxPanel.tsx`.
- `web/src/components/PlanApprovalStrip.tsx`.
- `web/src/components/WorkToolPanel.tsx`.
- `web/src/styles/layout.css`.
- `web/src/styles/plan-execute.css`.
- `web/src/styles/prototype-panels.css`.
- `web/src/styles/tokens.css`.
- `web/test-results/.last-run.json`.
- `.omo/evidence/orchestration-enforcement-code-review.md` — unrelated change.
- `.omo/evidence/orchestration-hands-on-qa/manual-qa-report.json` — unrelated change.
- `.omo/evidence/agent-lab-decision-surface-gate-review.md` — 같은 diff hash의 동시 gate review로 읽고 참조 경로를 확인했으나, code-review report/manual-QA matrix/executor raw log를 대체하지 못함.

## exactEvidenceGaps

- 현재 UX diff hash에 결박된 executor evidence bundle이 없다.
- 현재 UX diff용 code-review report와 그 안의 remove-ai-slops/programming/overfit coverage가 없다.
- 현재 UX diff용 manual QA matrix가 없다.
- notepad path와 내용이 제공되거나 발견되지 않았다.
- 선택된 radio와 focus ring을 보여주는 캡처가 없다.
- 모바일 질문 캡처가 없다.
- ArrowUp/Left/Right/End, wrap-around, Space, roving Tab stop, focus 이동의 runtime assertion이 없다.
- 질문 제출 request payload와 option/freeform 상호배타의 runtime assertion이 없다.
- responsive assertion은 Workbench hidden과 scroll width까지만 검증하며 primary CTA가 실제 hit-test 가능한지 증명하지 않는다.
- execute-failure recovery의 사용자 조작 가능한 retry 경로를 보여주는 캡처나 assertion이 없다.

## scopeSafety

제품 source, test, configuration, 제공된 캡처는 수정하지 않았다. 게이트 프로토콜이 요구한 이 report artifact만 갱신했다.
