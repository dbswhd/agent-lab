# 11 — Mission first-pass UI/UX surface map

> **상태:** In progress / D0
> **목적:** first-pass Mission/Activity/Decision 계약을 사용자가 실제로 이해하고 조작할 수 있는 UI 표면으로 번역한다.
> **선행:** [04 Human UX](./04-human-experience-api-ui.md), [06 Async Runtime](./06-asynchronous-mission-runtime.md), [08 Messaging](./08-collaboration-messaging.md)
> **현재 UI SSOT:** [ROOM-TRANSCRIPT-CONTRACT.md](../ROOM-TRANSCRIPT-CONTRACT.md), [MCP-FIRST-INBOX.md](../MCP-FIRST-INBOX.md), [CONSOLE-PRODUCTIZATION.md](../CONSOLE-PRODUCTIZATION.md)

## 1. 결론

새 kernel의 내부 state를 그대로 UI에 노출하지 않는다. 사용자가 봐야 하는 것은 `현재 약속`, `마지막으로 일어난 일`, `다음에 필요한 결정`, `복구 가능 여부` 네 가지다.

기존 3-pane shell과 `ComposerEventStack`은 유지한다. 바꿀 것은 컴포넌트의 위치가 아니라 lifecycle truth를 조합하는 방식이다.

## 2. 현재 surface와 새 계약의 연결

| 현재 surface                              | 현재 데이터                                            | first-pass 연결                                                              | 충돌/주의                                                       |
| ----------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `ComposerEventStack`                      | `plan_workflow`, `runtime`, inbox count, execute queue | `Decision Queue`의 primary CTA와 최근 Mission event 요약                     | 여러 legacy phase를 직접 조합하지 않도록 read model 하나로 축소 |
| `WorkStatusBar`                           | `work_phase`, `mission_loop.phase`                     | 사용자 언어의 `Plan → Execute → Review → Verify → Done` stepper              | `MissionState`를 그대로 표시하지 말고 projection만 사용         |
| `WorkspaceCard`                           | worktree, branch, diff, merge checks, commit           | `Activity` milestone, diff approval, merge SHA, Oracle verdict               | merge와 Oracle을 같은 “완료” 배지로 합치지 않음                 |
| `HumanInboxPanel` / `DecisionQueueHeader` | `human_inbox[]`                                        | pending question, 추천, 영향, expiry, stale conflict                         | Inbox가 lifecycle writer가 되지 않도록 answer command만 발행    |
| `SessionStatusLine`                       | profile, sandbox, autonomy                             | mission health, activity wait, reconnect/daemon 상태를 compact chip으로 표시 | 상태 chip이 CTA를 대신하지 않음                                 |
| Transcript/SSE                            | chat, progress, activity rows                          | durable event와 ephemeral progress를 시각적으로 구분                         | reconnect 후 durable event가 중복 표시되지 않아야 함            |
| Context sidebar                           | Overview/Tasks/Inbox                                   | Mission overview, tasks/objections, decision queue                           | 기존 Quick/Activity 중복 탭을 재도입하지 않음                   |

## 3. 사용자 상태 언어

| Domain 상태              | 사용자에게 보일 문구      | primary action        | 세부 evidence                           |
| ------------------------ | ------------------------- | --------------------- | --------------------------------------- |
| `DRAFTING`               | 계획 작성 중              | 계획 생성/재논의      | plan revision, open objections          |
| `AWAITING_PLAN_DECISION` | 계획 검토가 필요합니다    | 승인 / 다시 논의      | plan hash, 변경 요약, 근거              |
| `READY_TO_EXECUTE`       | 실행 준비 완료            | 실행 시작             | worktree, permission, budget            |
| `EXECUTING`              | 변경을 실행 중입니다      | 중지 / 진행 보기      | activity, last update, workspace        |
| `AWAITING_DIFF_DECISION` | 변경 검토가 필요합니다    | merge 승인 / 거절     | diff, checks, changed files             |
| `VERIFYING`              | Oracle 검증 중입니다      | 진행 보기             | commit SHA, checks, Oracle lanes        |
| `REPAIRING`              | 검증 실패를 수정 중입니다 | repair detail 보기    | failure evidence, attempt/max, strategy |
| `AWAITING_HUMAN`         | 답변이 필요합니다         | Decision Queue 열기   | question, options, impact, expiry       |
| `SUCCEEDED`              | 검증 완료                 | 결과/아카이브 보기    | commit, Oracle pass, evidence           |
| `FAILED`                 | 완료하지 못했습니다       | 진단/재시도/수동 해결 | failure domain, preserved artifacts     |
| `CANCELLED`              | 사용자가 중지했습니다     | 재개 또는 종료        | checkpoint, cancellation reason         |

## 4. 표시 우선순위

한 화면에는 다음 중 가장 높은 우선순위의 하나만 primary CTA로 둔다.

1. 안전 차단: BLOCK, permission, merge conflict, stale command
2. Human decision: plan, diff, question, repair diagnosis
3. 복구 진행: retry, reconnect, daemon recovery
4. 현재 activity: execute, verify, progress
5. 정보성 상태: budget, profile, provider health

`Plan rejected`, `Mission paused`, `Inbox pending`, `merge review`를 각각 별도 배너로 쌓지 않는다. 하나의 Decision Queue item으로 합치고, 나머지는 evidence drawer에 둔다.

**현재 착수 결과:** `mission/read_model.py`가 사용자 action projection을 제공하고, `mission/application.py`가 plan/Human answer adapter를 제공한다. `/api/sessions/{id}/mission/read-model` read-only route도 추가했으며, journal 없는 세션은 `migrated=false`로 구분한다. React surface·SSE cursor wiring과 browser QA는 아직 다음 단계다.

## 5. 구현 시 충돌 방지 규칙

- UI는 `run.json`, `plan_workflow`, `mission_loop`를 각각 읽어 상태를 조합하지 않는다.
- API는 `MissionReadModel` 하나를 제공하고, 기존 payload는 compatibility projection으로만 소비한다.
- `WorkStatusBar`는 상태를 쓰지 않는다. pause/resume/approve/reject는 command endpoint만 호출한다.
- `HumanInboxPanel` answer는 `decision_id`, `mission_id`, `expected_version`을 함께 전송한다.
- SSE progress는 best-effort, Mission event는 durable로 분류해 reconnect merge 규칙을 분리한다.
- 기존 `WorkspaceCard`의 worktree/diff/checks 정보는 유지하되, 새로운 state badge를 추가해 같은 사실을 두 번 표시하지 않는다.

## 6. 접근성·visual QA acceptance

- [ ] 모든 상태에 색상 외 텍스트와 `aria-live` 우선순위가 있다.
- [ ] keyboard로 `Decision Queue → evidence → answer → resume`를 완료할 수 있다.
- [ ] stale answer는 inline conflict와 현재 상태를 함께 보여준다.
- [ ] `WAITING_HUMAN`과 `WAITING_EXTERNAL`이 다른 아이콘·문구로 표시된다.
- [ ] reconnect 후 transcript, progress, decision count가 snapshot과 수렴한다.
- [ ] 3-pane shell에서 primary CTA가 가려지지 않고, narrow viewport에서도 evidence drawer가 접근 가능하다.

## 7. 구현 순서

1. `/api/sessions/{id}/mission/read-model`과 legacy projection parity를 고정한다.
2. `ComposerEventStack`에 Decision Queue precedence를 연결한다.
3. `WorkStatusBar`/`WorkspaceCard`에 activity·merge·Oracle evidence를 추가한다.
4. SSE cursor/reconnect와 durable event merge를 연결한다.
5. Playwright journey로 plan reject, diff approve, Oracle repair, Human resume을 검증한다.
