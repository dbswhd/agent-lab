# Sector 4 — Human UX·API·프론트엔드

> **상태:** UI surface mapping + wiring 완료 (2026-07-15, `11-ui-ux-surface-map.md` §7 1~5)  
> **선행:** Mission states/events/projections  
> **관련 SSOT:** `ROOM-TRANSCRIPT-CONTRACT.md`, `MCP-FIRST-INBOX.md`

## 1. 목표

Human을 “에이전트 실행자”가 아니라 목표·권한·예외의 감독자로 둔다. UI는 내부 구현 phase를 노출하는 대신 현재 미션의 약속, 진행, 근거, 필요한 결정, 복구 경로를 일관되게 보여준다.

## 착수 상태

`decision_queue.py`와 `decision_repository.py`가 질문·답변·만료·stale version conflict를 공통 모델로 고정했고, `human_bridge.py`가 답변을 waiting Activity/Mission block 재개로 연결한다. `MissionApplication.guard_inbox_answer()`(2026-07-15)가 이 CAS 커널을 실제 프로덕션 `/inbox/{item_id}/resolve` 경로에 연결 — `decision_id`/`mission_id`/`expected_version`을 read-model에서 받아 stale/중복 answer를 409로 거부한다. 완전한 단일 트랜잭션(decision journal + `run.json` 원자적 커밋)은 아직 별도 트랙.

## 2. 현재 평가

### 강점

- topic-only composer와 supervisor 기본값은 설정 부담을 줄였다.
- plan approval, diff review, Human Inbox가 실제 권한 경계를 시각화한다.
- Transcript/Work/Files/Diff/Terminal 도구가 개발 미션에 필요한 표면을 갖춘다.
- SSE reconnect와 transcript contract를 별도 SSOT로 관리한다.

### 결함

| 결함                         | 근거                                                           | 영향                                       |
| ---------------------------- | -------------------------------------------------------------- | ------------------------------------------ |
| 내부 상태가 UI 의미로 누출   | plan phase, mission phase, work phase, recovery item 조합      | 사용자가 같은 사실을 여러 배지로 봄        |
| API client가 거대함          | `web/src/api/client.ts` 2,742 LOC                              | 타입·endpoint·transport 변경 결합          |
| 대형 조정 컴포넌트           | HumanInbox 862, ChatComposer 830, App 829, RoomTaskBar 703 LOC | 상태 소유권과 렌더 책임 혼재               |
| 실시간/영속 메시지 병합 복잡 | registry, SSE patch, live archive, refresh merge               | 중복·순서·stale UI 위험                    |
| 기능별 결정 표면이 증가      | plan, diff, objection, clarifier, inbox, recovery              | “지금 무엇을 해야 하는가”가 분산될 수 있음 |

## 3. 경험 모델

### D1. 동기와 비동기를 명시적으로 나눈다

| 경험       | 예                                              | UX 계약                                         |
| ---------- | ----------------------------------------------- | ----------------------------------------------- |
| 동기       | topic 입력, clarifying exchange, plan 문구 수정 | 짧은 latency, streaming, turn-taking, 취소      |
| 비동기     | execute, verify, repair, schedule, monitor      | 떠나도 계속, 상태·다음 update·완료 알림, 재진입 |
| Human wait | plan/diff/risk 질문                             | single decision card, deadline/영향/대안        |

장시간 작업을 composer spinner로 표현하지 않는다. 시작 즉시 background mission으로 전환하고 앱을 닫아도 복원되는 상태를 보여준다.

### D2. 모든 결정을 Decision Queue로 통합한다

```text
DecisionItem
  id, mission_id, kind
  question
  options[]
  recommendation + confidence
  evidence_refs[]
  consequence
  risk
  expires_at
  status
```

plan approval, objection resolution, clarifier answer, diff approval, permission, drift recovery가 같은 envelope를 사용한다. 각각의 상세 editor는 유지할 수 있지만 queue가 우선순위와 단일 pending action을 소유한다.

### D3. UI는 read model만 소비한다

핵심 read model:

- `MissionSummary`: goal, status, progress, current activity, health
- `TranscriptView`: durable messages + ephemeral activity refs
- `WorkView`: plan revision, executions, evidence, next action
- `DecisionQueueView`: pending Human actions
- `AgentActivityView`: running agents, progress, cancelability

클라이언트는 여러 phase를 조합해 새로운 lifecycle truth를 만들지 않는다.

### D4. Command API와 Query API를 구분한다

Command endpoint는 의도를 표현하고 command id/version을 받는다. Query endpoint는 task-oriented read model을 반환한다. SSE는 domain/projection event cursor를 제공한다.

제안:

```text
POST /api/missions
POST /api/missions/{id}/commands
GET  /api/missions/{id}
GET  /api/missions/{id}/work
GET  /api/missions/{id}/transcript
GET  /api/missions/{id}/decisions
GET  /api/missions/{id}/events?after=
```

공개 API를 무조건 6개로 제한한다는 뜻은 아니다. 기능별 mutation endpoint 확장을 command vocabulary로 수렴시키는 방향이다.

### D5. 우아한 실패는 다음 행동을 포함한다

모든 failure surface는 다음을 답한다.

1. 무엇이 실패했나
2. 무엇은 보존됐나
3. 자동으로 무엇을 시도했나
4. 사용자가 선택할 수 있는 안전한 다음 행동은 무엇인가
5. 진단 근거를 어디서 볼 수 있나

raw exception과 generic retry만 보여주지 않는다.

## 4. 정보 구조

```text
Workspace
  Mission rail
  Main
    Transcript | Plan | Diff | Files | Terminal
  Inspector
    Mission status
    Decision queue
    Evidence
    Agent activity
```

기존 3-pane shell은 유지할 가치가 있다. 재설계 대상은 pane 자체보다 같은 상태가 여러 컴포넌트에 흩어진 내부 모델이다.

## 5. 구현 계획

### U1. Human journey와 상태 언어 정리

**산출물:** start, plan approve, execute watch, diff decide, repair, resume의 journey map과 copy lexicon.

**Acceptance criteria:**

- 내부 enum 없이 각 화면의 사용자 질문이 정의된다.
- pending decision이 없을 때 primary CTA가 하나다.
- pause, blocked, failed, waiting-human이 구분된다.

**검증:** 5개 대표 fixture의 화면 storyboard review.

### U2. Read-model API shadow endpoint

**산출물:** 기존 데이터를 새 Mission/Work/Decision view로 변환하는 query endpoint.

**Acceptance criteria:**

- UI에 필요한 lifecycle 계산이 서버 projection에 있다.
- response schema가 versioned type으로 생성된다.
- 같은 session fetch에서 모순되는 phase가 없다.

**검증:** contract tests, fixture snapshots, OpenAPI diff.

### U3. SSE/event cursor 통합

**산출물:** snapshot + ordered updates + resume cursor 계약.

**Acceptance criteria:**

- reconnect 후 duplicate durable message가 없다.
- ephemeral agent activity는 완료 시 durable result와 연결된다.
- out-of-order/gap 감지 시 full snapshot으로 복구한다.

**검증:** browser reconnect, refresh during streaming, network drop E2E.

### U4. Decision Queue 통합

**산출물:** 공통 DecisionItem API와 UI shell.

**Acceptance criteria:**

- plan/diff/inbox/objection/clarifier가 하나의 priority queue에 나타난다.
- 각 결정은 근거, 추천, 영향, 취소/연기 가능 여부를 보여준다.
- command submit은 optimistic concurrency conflict를 처리한다.

**검증:** keyboard-only manual QA, stale decision test, screen reader labels.

### U5. Feature slice 기반 프론트 구조

**산출물:** `features/mission`, `features/transcript`, `features/work`, `features/decisions`, `features/agents`.

**Acceptance criteria:**

- `api/client.ts`가 domain clients와 generated schemas로 분리된다.
- component는 fetch와 lifecycle derivation을 직접 하지 않는다.
- App/Composer/TaskBar/Inbox의 stateful responsibility가 feature store/hook로 이동한다.
- 파일 크기 자체보다 단일 책임과 import boundary를 검사한다.

**검증:** typecheck, component tests, import boundary check, bundle diff.

### U6. 비동기 mission UX

**산출물:** background progress, notification, return-to-context, ETA 대신 milestone/last update.

**Acceptance criteria:**

- 앱을 벗어났다가 돌아와도 현재 activity와 다음 decision을 즉시 본다.
- cancel/pause가 실제 runtime acknowledgement와 연결된다.
- 장시간 무변화는 heartbeat/last activity와 진단 CTA를 제공한다.

**검증:** 10분 mock mission, app reload, daemon restart manual QA.

### U7. Legacy 표면 제거

**산출물:** classic run UI, 중복 banner, 구 endpoint/client types 제거.

**Acceptance criteria:**

- 같은 Human decision이 둘 이상의 primary CTA로 나타나지 않는다.
- 새 UI 경로에서 legacy phase 문자열 의존이 없다.
- endpoint usage inventory에 orphan route가 없다.

**검증:** route usage scan, Playwright 핵심 journey, visual QA.

## 6. 접근성·신뢰 계약

- 모든 decision과 progress는 색상 외 텍스트/아이콘/ARIA 상태를 가진다.
- streaming transcript는 screen reader live region을 과도하게 갱신하지 않는다.
- keyboard로 composer → decision → evidence → submit 흐름을 완료할 수 있다.
- destructive command는 scope와 되돌릴 수 없음 여부를 표시한다.
- confidence는 숫자만 보여주지 않고 근거와 불확실성을 함께 표시한다.
- 비용·tool permission·외부 전송이 발생하기 전 Human이 확인 가능하다.

## 7. 완료 정의

- 사용자는 내부 FSM을 몰라도 미션의 현재 상태와 다음 행동을 이해한다.
- 모든 Human wait가 하나의 Decision Queue에서 처리된다.
- refresh/reconnect 후 transcript와 progress가 일치한다.
- UI가 lifecycle authority가 아니며 server read model을 표시한다.
- 핵심 journey가 browser manual QA와 Playwright에서 통과한다.
