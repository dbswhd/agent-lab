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

1. `/api/sessions/{id}/mission/read-model`과 legacy projection parity를 고정한다. — **완료** (`AGENT_LAB_MISSION_UI_READ_MODEL` default on, 2026-07-14)
2. `ComposerEventStack`에 Decision Queue precedence를 연결한다. — 완료 (§8 join 규약 참고)
3. `WorkStatusBar`/`WorkspaceCard`에 activity·merge·Oracle evidence를 추가한다.
4. SSE cursor/reconnect와 durable event merge를 연결한다. — **미착수.** `event_cursor`는 payload에 존재하고 파싱 시 타입 검증만 되지만, 어떤 consumer도 SSE 쪽 버전과 비교해 사용하지 않는다. §8 참고.
5. Playwright journey로 plan reject, diff approve, Oracle repair, Human resume을 검증한다.

## 8. Wave B join 규약 (as-built, 2026-07-14)

`AGENT_LAB_MISSION_UI_READ_MODEL` default on 시점 기준, 실제 코드가 수행하는 두 종류의 join을 명문화한다. 이 절은 §5의 설계 원칙("UI는 여러 소스를 조합하지 않는다")이 실제로 어떻게 구현됐는지의 as-built 기록이며, §5를 대체하지 않는다.

### 8.1 내부 join — `inbox_items` ↔ `open_execution_gates`

파싱 경계(`parseMissionReadModel`, `web/src/utils/missionReadModel.ts`)에서 강제한다. payload 전체가 이 조건을 만족하지 않으면 **`null`을 반환** — 부분 적용 없이 legacy 경로로 fail-closed.

- 모든 `open_execution_gates[j].gate_id`는 비어 있지 않고 중복 없음.
- actionable한 `inbox_items[i]` (i.e. `actionable !== false && mission_gate_status !== "stale"`)는 반드시 어떤 `open_execution_gates[j].gate_id`와 `id`가 일치해야 한다.
- stale/non-actionable item은 매칭되는 gate가 없어도 허용 — 조회 전용으로 남아 있는 지난 항목이기 때문.
- `inbox_items[i].id` 중복 금지.

### 8.2 cross-source 우선순위 join — read-model vs legacy/runtime

7개 consumer(`ComposerEventStack`, `HumanInboxPanel`, `WorkToolPanel`, `ContextOverviewPanel`, `NotificationCenter`, `useRoomChatInteractions`, `useAutonomySession`) 모두 동일한 패턴을 쓴다:

```
missionReadModel?.<field> ?? legacy/runtime의 동등 필드
```

규약은 **presence 기반이지 freshness 기반이 아니다**:

- `missionReadModel`이 non-null인 조건은 `isUsableMissionReadModel()` — `migrated === true && source === "mission_journal"`. 이 조건을 만족하는 순간 그 세션은 "journal-authoritative"로 취급된다.
- `missionReadModel`이 non-null이면, 그 안의 **개별 필드 값**(빈 배열/`false`/`0` 포함)이 그대로 이긴다. Legacy로의 fallback은 `missionReadModel` 자체가 `null`일 때(flag off, 미마이그레이션, fetch 실패, 파싱 실패)만 발생한다. 필드 단위 병합(item-by-item merge)은 없다 — 예: `HumanInboxPanel`이 `missionReadModel.inbox_items === []`를 받으면 legacy `human_inbox`에 항목이 남아 있어도 `[]`로 완전히 교체한다. Journal 기준으로는 "pending 없음"이 사실이므로 이는 의도된 동작이다.
- `event_cursor`는 payload에 실려 오고 숫자 타입 검증만 받는다 — **어떤 consumer도 SSE/runtime 쪽 커서·버전과 비교하지 않는다.** 두 소스 중 어느 쪽이 실제로 더 최신인지 판단하는 로직은 없다. §7 항목 4(SSE cursor/reconnect merge)가 이 자리를 메울 예정이며, 아직 미착수다.

### 8.3 durable 스트림 내부 순서 보장 — epoch guard

`useMissionReadModel`(`web/src/utils/missionReadModel.ts`)은 2.5초 간격 폴링이다. 8.2의 cross-source join과는 별개로, **같은 스트림 내부**에서의 순서만 별도로 보장한다:

- `requestEpoch` ref는 poll마다 단조 증가.
- 응답 적용 조건은 `shouldApplyMissionReadModelEpoch(requestEpoch.current, epoch)` → `epoch >= requestEpoch.current`.
- 즉, 오래된 poll이 최신 poll보다 늦게 resolve돼도(네트워크 지연) 버려진다 — `missionReadModel.test.ts`의 durable race 시나리오 테스트로 고정됨.
- 이 guard는 "durable 스트림이 자기 자신에 대해 시간순인지"만 보장한다. 8.2의 "read-model vs legacy/runtime 중 뭐가 최신인지"는 별개 문제이며 아직 풀리지 않았다.

### 8.4 요약 — 지금 안전한 것과 아닌 것

| 보장 대상                                  | 상태                                            |
| ------------------------------------------- | ------------------------------------------------ |
| `inbox_items` ↔ `open_execution_gates` 정합 | 파싱 경계에서 강제, 위반 시 payload 전체 폐기    |
| durable poll 내부 순서 (stale response 무시) | epoch guard로 보장, 테스트 있음                  |
| read-model vs legacy/runtime 중 최신 판정   | **없음** — presence만 보고 판단, cursor 비교 없음 |
| SSE reconnect 후 durable event 중복 방지    | **없음** — §7 항목 4 미착수                       |
