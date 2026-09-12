# Agent Lab — 아이디어 구체화 Room 개발 계획

작성: 2026-09-12 · 대상: 개인 개발 생산성 · 상태: 개발 계획, 미구현

사용자가 확정한 방향: 막연한 개념에서 출발해 창의적인 구상과 구체적인 구현 계획을 만드는 Room에 집중한다. 실행·배포는 기존 개발 에이전트에 넘긴다.

이 문서는 이번 전환의 제안 범위와 실행 순서를 소유한다. 현재 런타임·shipped 상태를 변경하거나 기존 세션의 실행 권한을 부여하지 않는다. 코드를 확인해 작성했으며 이번 작업에서 live 비교나 앱 QA를 수행하지 않았다.

## 1. 제품 결정

**제품 한 줄:** 생각의 씨앗을 넣으면, 서로 다른 가능성을 탐색하고 내 선택을 반영해 만들고 싶은 구상과 착수 가능한 계획으로 발전시키는 개인 설계 Room.

**주 경로:** 개념 입력 → 접근이 다른 구상 → 선택·조합·수정 → 사용 경험과 작동 방식 구체화 → 구현 계획 → 복사/내보내기.

**완료:** 사용자가 만들 방향을 이해하고, 중요한 가정과 첫 검증 방법을 알고, 외부 에이전트에서 첫 작업을 시작할 수 있다. Room 내 코드 실행이나 Oracle PASS는 이 제품의 완료 조건이 아니다.

- 처음부터 레포 연결·요구사항 명세·모델별 역할 설정을 요구하지 않는다.
- 질문보다 제안을 먼저 만든다. 빠진 정보는 가정으로 표시하고, 방향을 크게 바꾸는 질문만 한 번에 하나 제시한다. 필요한 사실은 꾸며내지 않는다.
- 과정은 왕복 가능하다. 사용자가 이미 방향을 정했으면 탐색을 생략하고, 선택 이후에도 다시 탐색할 수 있다.
- 선택·계획 확정은 사용자의 판단이다. 에이전트 합의, 다수결, 모델 confidence를 선택 승인으로 대체하지 않는다.
- v1은 텍스트와 Markdown 중심이다. 캔버스·드래그 보드·워크플로 편집기·자체 프로토타입 런타임은 만들지 않는다.
- 코딩·시제품 실행이 필요한 기술 가정은 별도 실험 계획으로 내보낸다. 레포 읽기와 이미 제공된 자료 조사는 기존 권한 안에서 수행한다.

## 2. 코드 조사에서 확인한 출발점

| 근거 | 현재 동작 | 이번 변경의 의미 |
|---|---|---|
| `src/agent_lab/divergence.py` | 발산 응답을 최대 4개 옵션으로 포맷. 접근의 차이는 검증하지 않음 | 새 발산 엔진 대신 옵션 내용·선택 후 흐름 강화 |
| `src/agent_lab/agents/prompts.py` | `DIVERGENCE_INSTRUCTION` 존재. 제공자별 고정 역할과 CHALLENGE 지침도 존재 | 탐색에서 상충하는 역할 지침을 제거하고 단계별 역할 적용 |
| `src/agent_lab/room/parallel_rounds.py` | 후속 wave는 앞선 응답을 읽음 | 첫 탐색의 공통 입력을 고정하고, 비교·합성은 이후에 수행 |
| `src/agent_lab/role_plan.py`, `reply_policy.py` | proposer/critic/synthesizer와 역할 주입 경로 존재 | 제공자 이름과 역할을 분리해 재사용 |
| `src/agent_lab/room/turn_policy.py`, `turn_policy_models.py` | TurnPolicy가 Scribe·FSM·task effects 결정 | 아이디어 상태에 따른 출력 정책을 이 경계에 통합 |
| `src/agent_lab/room/plan_scribe.py` | 요약·Scribe·출처 연결 구현 | 선택한 구상과 근거를 직접 입력해 구상→계획 전환 |
| `src/agent_lab/plan/workflow_approval.py` | 승인 시 조건에 따라 mission/goal/verified loop 시작 | 구상 선택·내보내기는 이 API를 호출하지 않도록 분리 |
| `app/server/routers/sessions.py` | 세션 GET도 `ensure_session_plan_pipeline` 호출 | 읽기·새로고침이 새 Room에서 계획 생성/실행을 유발하지 않는지 검사 |
| `src/agent_lab/run/meta.py`, `session/guidance.py` | patch/stamp와 세션 필드 보존 규칙 | 같은 저장 경로에 작은 하위 상태를 추가. 별도 DB/저널 금지 |
| `web/src/components/RoomChatView.tsx`, `utils/workspaceTabs.ts` | 실행·autonomy·IDE 도구 중심 표면 | 새 Room에는 구상·계획을 우선 표시, 기존 세션은 호환 |

기존 divergence 테스트는 계약·포맷·주입을 다룬다. 이것만으로 창의성이나 사용자 효용이 검증됐다고 표현하지 않는다.

## 3. 쳐낼 것·유지할 것·개발할 것

### 3.1 새 Room의 기본 경로에서 제외

| 대상 | 결정 | 코드 처리 |
|---|---|---|
| execute/merge/Oracle/repair/goal loop | 제품 핵심 범위에서 제외 | 기존 `plan/execute*`, `mission/loop.py`, `oracle_core.py`, `goal_loop.py`, `verified_loop.py`는 기존 세션용으로 보존. 새 Room에서 호출 금지 |
| delegate 실행 버튼·자동 외부 CLI 실행 | 내보내기 중심으로 축소 | `DelegateExecuteBar.tsx`와 외부 runner 확장 중단. 이미 구현한 경로는 호환 유지 |
| Autonomy ladder·trust budget·승격/강등 | 새 Room에 불필요 | `AutonomyDial`·실행 예산 UI 숨김. 대화 호출 비용·취소 기능은 유지 |
| Diff/Terminal/Background 중심 탐색 | 보조 도구로 내림 | 새 Room 기본 표면에서 숨김. Files는 레포를 연결한 경우 선택적 제공. 기존 URL·세션 접근 보존 |
| 필수 합의·ENDORSE/CHALLENGE 횟수·자동 plan 전환 | 탐색의 완료 조건에서 제거 | 새로운 idea lane에서 조기 합의·질문 대기·task assign·자동 Scribe가 발산을 막지 않게 함 |
| 실행 성과 기반 advisor/bandit | 새 Room 라우팅에서 사용 중단 | 실행 성공률을 아이디어 품질 신호로 쓰지 않음. 기존 세션 소비처가 있는 모듈은 보존 |
| 전사적 metrics·정기 리포트·super-sample 목표 | 이번 로드맵에서 제외 | 작은 수동 효용 평가만 추가. 기존 지표를 일괄 삭제하지 않음 |

`BLOCK→409`, 권한 경계, subprocess env allowlist, 취소, 기존 Human gate는 유지한다. 창의적 이견은 후보와 위험 설명으로 보존하되, 실제 안전 제약을 무시하거나 기존 BLOCK을 자동 해제하지 않는다. BLOCK 상태의 구상도 논의·복사는 가능하지만 실행 가능한 확정본으로 표기하지 않는다.

### 3.2 추가 개발을 동결

- 신규 provider/bridge, Gateway, 자체 IDE 완성, 범용 scheduler, 자동 배포·merge 고도화.
- S2/S3 학습·도구 자동 통합, 자기개선 엔진의 부활, 새 자율도 체계.
- trading/quant 코어 확장. 기존 extension lane 유지.
- 모델별 역할을 사용자가 세세하게 구성하는 설정 화면, 새 profile/flag 조합 확대.

### 3.3 강화

| 우선순위 | 기능 | 사용자에게 주는 가치 |
|---|---|---|
| P0 | 제안 중심 intake와 접근이 다른 2~3개 구상 | 생각이 정리되지 않은 상태에서도 진행 가능 |
| P0 | 선택·조합·기각과 이유 보존 | 이미 한 결정을 반복 설명하지 않음 |
| P0 | 실제 사용 장면·입출력 예·작동 원리 | 무엇을 만들지 구체적으로 상상 가능 |
| P0 | 선택한 구상에 근거한 계획과 첫 실험 | 문서를 다시 설계하지 않고 착수 가능 |
| P1 | 구상/계획 요약 패널과 새로고침 복원 | 긴 대화를 전부 읽을 필요가 줄어듦 |
| P1 | 레포 사실·추정·선호 구분 | 창의적인 제안과 기술적 사실을 혼동하지 않음 |
| P2 | 세션 간 사용자 선호 재사용 | 반복 효용 확인 후 검토. v1은 세션 내부 기록만 |

### 3.4 삭제 순서

초기에는 실행 기능을 제품의 기본 경험에서 제거하고 개발 투자를 중단한다. 연결 관계를 확인하지 않은 파일의 즉시 hard-delete 목록은 만들지 않는다.

새 경로 검증 후 제거 대상은 **idea lane에서 더 이상 호출하지 않는 실행 UI 배선, 중복 안내·설정, 사라진 기능의 전용 테스트/문서**다. 공유 저장소·Inbox·provider·권한 모듈은 삭제 대상에서 제외한다. 물리 삭제는 RI-15의 호출 그래프와 기존 세션 회귀를 근거로 한 묶음씩 수행한다. 전체 재작성이나 대규모 선행 리팩터링은 계획에 없다.

## 4. 최소 제품 계약

### 4.1 저장 구조

신규 아이디어 Room은 `run.json.ideation`의 `schema_version: 1`로 구분한다. 런타임 run profile은 기존 비용·환경 설정으로 유지하고, 새 전역 feature flag나 preset picker는 만들지 않는다. `ideation`이 없는 기존 세션은 기존 동작을 유지한다.

`run.json.ideation`이 구조화된 구상 상태의 단일 권위다. `concept.md`는 사람이 읽는 파생 출력이며, 별도 writer나 입력 권위가 아니다. `plan.md`는 기존 plan 저장 API를 사용하고 기존 source/mirror 관계를 보존한다.

필요한 필드만 둔다:

- `schema_version`, `revision`, `stage`: `explore | shape | plan`.
- `brief`: 원래 개념, 원하는 변화, constraints, assumptions, unresolved questions.
- `options`: 안정된 ID, 제목, 핵심 원리, 사용 장면, 차이, tradeoff, 첫 실험, 근거 refs. 처음 2~3개를 목표로 하되 실패·단일 답변을 숨기지 않는다.
- `selection`: 고른 ID 또는 조합한 새 ID, 부모 ID, 사용자 이유, 선택 당시 revision. 옵션 index를 영구 식별자로 사용하지 않는다.
- `concept`: 선택한 방향의 사용자 흐름, 예시 입출력, 작동 방식, MVP/비범위, 미확인 가정.
- `decisions`: 사용자 수정·기각·선호의 출처와 이유. 기각한 후보를 새 근거 없이 다시 기본안으로 제시하지 않는다.
- `plan_source_revision`, `plan_source_hash`: 계획이 어느 구상을 반영했는지 기록. 구상이 바뀌면 이전 계획은 stale 표시.

대화는 `chat.jsonl`에 유지한다. 저장은 기존 `stamp_run_meta`/`patch_run_meta`와 turn-end replay를 따른다. 턴 중 디스크 재적재로 선택을 덮어쓰지 않는다. 구조 필드 보존과 mutation의 revision 검사를 함께 검증한다. 일반 채팅에서의 선택은 lead가 해석할 수 있지만 애매한 표현을 확정으로 기록하지 않는다.

### 4.2 상태와 권한

이 세 상태는 진행 위치를 기억하는 데이터다. 별도 workflow engine이나 실행 권한 체계를 만들지 않는다.

| 사용자 행동 | 상태 효과 | 실행 효과 |
|---|---|---|
| 막연한 개념 입력 | explore: 가정을 표시하며 대안 생성 | 없음 |
| 선택 / 조합 / 내가 제시한 방향 사용 | selection 기록 후 shape | 없음 |
| 다른 방향 탐색 | explore로 복귀, 이전 결정 보존 | 없음 |
| 이 구상으로 계획 만들기 | plan, 기존 Scribe 경계로 계획 생성 | 없음 |
| 복사 / 내보내기 | 해당 revision의 산출물 반환 | 없음 |
| 구현 요청 | 실행 도구용 작업 지시문 제공. 실행 환경 이동은 사용자가 수행 | Room 내부 실행 없음 |

레이블은 `구상 선택`, `계획 준비됨`, `추가 확인 필요`를 사용한다. `APPROVED`, `VERIFIED`와 혼용하지 않는다. 기존 `plan/approve`를 구상 선택 API로 재사용하지 않는다. 새 Room에서는 `/plan/approve`, execute API 직접 호출, legacy template fast-path도 구현 실행을 시작하지 못해야 한다.

기존 mission template loader는 승인 fast-path를 갖고 있으므로, 새로운 idea lane의 생성 수단으로 재사용하지 않는다. 초기 개발은 명시적인 세션 opt-in, live 검증 후 새 일반 Room의 기본 생성값으로 전환한다. composer는 topic-only 유지.

### 4.3 대화 운영

- 탐색: 공통 brief의 같은 revision을 2~3개 사용 가능한 seat에 제공. 첫 발산에서는 같은 배치의 다른 답변·상호 메시지를 보지 않도록 입력과 coordination 경로를 확인한다. 기존 provider 인증·전송은 재사용한다.
- 관점: 사용자 경험, 가능한 다른 작동 방식, 제약을 바꾼 접근처럼 차이를 만들되 제공자 이름에 고정하지 않는다. 모델 한 개만 가능하면 한 번의 호출로 대안을 만들고 다중 모델의 독립성으로 표현하지 않는다.
- 비교: lead는 장단점을 정리한다. 서로 비슷한 안이면 비슷하다고 밝히고 억지로 세 개를 채우지 않는다. 사용자가 원할 때 다른 접근을 추가한다.
- 구체화: 선택 이후 feasibility/critic을 적용한다. 구현을 막는 가정과 단순 취향 차이를 나눠 설명하고, 기존 레포가 있으면 변경 지점을 실제로 읽는다.
- 계획: 선택한 구상·결정 기록·미확인 사실을 Scribe에 직접 제공한다. 대화 요약만으로 선택을 추정하지 않는다.
- 첫 탐색 예산: 후보 생성 2~3회 + 비교 1회, 기본 최대 4 provider 호출. 사용자 1턴당 자동 재탐색 없음. 구체화 최대 2회, 계획 작성+필요한 형식 수리 최대 2회. 모두 기존 회계·취소 경계 안에서 집계한다.
- budget 초과·provider 실패: 부분 결과와 미완료 항목을 보존하고 멈춘다. 성공으로 꾸미거나 합의까지 무제한 재시도하지 않는다.
- 차이를 만드는 질문은 한 번에 하나. 답을 몰라도 가정 선택으로 계속 진행할 수 있다. 법칙처럼 매 단계 승인 질문을 추가하지 않는다.

### 4.4 내보내는 계획의 내용

1. 만들려는 경험과 선택 이유.
2. 사용자 시나리오와 구체적인 입출력 예.
3. MVP 범위·비범위, 가정과 아직 결정하지 않은 것.
4. 작동 방식과 주요 구조. 레포 확인 사항은 실제 경로·근거, 미확인 경로는 제안으로 표시.
5. 먼저 확인할 위험 가정과 가장 작은 실험.
6. 의존성 순서로 나눈 작업: 무엇을, 어디에, 완료 조건, `검증:`.
7. 첫 작업용 외부 에이전트 프롬프트. 자동 실행·merge 승인 권한을 포함하지 않음.

불확실성이 큰 경우 첫 산출물은 조사/실험 계획이어도 된다. 파일명·API·기간을 사실처럼 꾸며 완성된 인상을 만들지 않는다. 기존 미결 BLOCK이 있거나 구상 revision이 바뀐 경우 내보내는 문서에 명시한다.

## 5. 구현 작업

작업은 순서대로 진행한다. 아래 경로는 저장소 루트 기준이며 `(신규)`는 아직 존재하지 않는 계획 파일이다. 각 작업은 단독 diff와 검증으로 끝내고, 실제 변경이 5개 파일을 크게 넘으면 다음 작업으로 분리한다. 시간은 숙련 개발자와 에이전트의 집중 작업 기준 추정이며 live 피드백 대기 시간은 별도다.

### RI-00 — 방향 문서와 적용 경계 정리 (S, 0.5일)

- 의존: 없음.
- 파일: `README.md`, `.agent-lab/PROJECT.md`, `docs/NOW.md`, `docs/NORTH-STAR.md`, `docs/TURN-CONTRACT.md`.
- 작업: 제품 한 줄·이번 큐·제외 범위·idea lane과 기존 execute lane의 차이를 반영. 현재 NOW의 미커밋 변경을 보존하며 편집.
- 완료: 새 방향을 현재 구현 완료로 표기하지 않음 / 기존 safety gate 불변 명시 / 실행 중심 신규 백로그는 보류.
- 검증: 문서 링크·상태 충돌 확인, `git diff --check`. PROJECT의 주입 글자 cap도 확인. 다른 상태 문서 전체 정리는 RI-15에서 수행.

### RI-01 — 실제 아이디어 기준선 (S, 0.5~1일)

- 의존: RI-00.
- 파일: `docs/evals/room-ideation-protocol.md` (신규), `evals/ideation_cases.jsonl` (신규).
- 작업: 사용자의 실제 아이디어 6개를 익명화해 수집. 처음 3개는 개발용, 나머지 3개는 확인용으로 보류. 레포 미연결·기존 레포·조건 변경 사례 포함.
- 완료: native 단일 에이전트 비교용 공정한 프롬프트와 시간 상한 고정 / 사용자 평가표 준비 / 아직 결과가 없으면 미측정 표시.
- 검증: 사례별 실제 seed와 제약 존재, 어떤 사례도 mock 생성 결과를 사용자 평가로 사용하지 않음.

### RI-02 — 새 Room 상태와 보존 (M, 1일)

- 의존: RI-00.
- 파일: `src/agent_lab/ideation.py` (신규), `src/agent_lab/run/state.py`, `src/agent_lab/session/guidance.py`, `tests/test_ideation_state.py` (신규).
- 작업: 최소 상태와 revision patch 검증 구현. 기존 세션에 자동 migration하지 않음. 처음에는 test fixture로만 opt-in.
- 완료: 선택·기각·revision 왕복 보존 / stale 변경 거절 / ideation 필드가 없는 기존 세션 동일 동작.
- 검증: `.venv/bin/pytest tests/test_ideation_state.py tests/test_session_guidance.py tests/test_run_meta_concurrency.py tests/test_run_meta_write_discipline.py -q`.

### RI-03 — 아이디어 경로의 부수 효과 차단 (M, 1일)

- 의존: RI-02.
- 파일: `src/agent_lab/room/turn_policy.py`, `src/agent_lab/room/turn_policy_models.py`, `src/agent_lab/room/turn_flow_phases.py`, `src/agent_lab/room/plan_scribe.py`, `tests/test_ideation_policy.py` (신규).
- 작업: 탐색·구체화에서 기존 CLARIFY 대기, 합의 완료 기반 Scribe, task claim, execute history 라우팅의 부적절한 개입을 막음. plan 요청만 명시적으로 Scribe 허용.
- 완료: vague topic에도 가정 기반 제안 진행 / 새로고침·synthesize가 실행 경로를 열지 않음 / 구형 경로와 BLOCK 보존.
- 검증: `.venv/bin/pytest tests/test_ideation_policy.py tests/test_turn_policy.py tests/test_divergence_profile.py tests/test_room_objections.py -q`; auto-sync GET 경로도 포함.

### RI-04 — 실행 승인 경계 고정 (M, 0.5~1일)

- 의존: RI-03.
- 파일: `src/agent_lab/plan/workflow_approval.py`, `src/agent_lab/turn_modes.py`, `src/agent_lab/plan/execute.py`, `tests/test_ideation_no_execute.py` (신규).
- 작업: idea lane에서 legacy plan approval·template fast-path·직접 execute가 실행을 활성화하지 못하도록 기존 공통 권한 경계에서 거절. 구현 착수 시 실제 execute façade의 하위 gate 위치를 추적해 그 파일로 책임을 이동할 수 있음.
- 완료: API 직접 호출 포함 execute/mission/goal loop 시작 0 / 복사·구상 선택은 동작 / 기존 승인된 실행 회귀 유지.
- 검증: `.venv/bin/pytest tests/test_ideation_no_execute.py tests/test_plan_workflow.py tests/test_plan_execute_worktree.py -q`; subprocess spy로 worktree/실행 호출이 없음을 확인.

### RI-05 — 독립 발산과 단계별 역할 (M, 1일)

- 의존: RI-03.
- 파일: `src/agent_lab/agents/prompts.py`, `src/agent_lab/role_plan.py`, `src/agent_lab/reply_policy.py`, `src/agent_lab/room/parallel_rounds.py`, `tests/test_ideation_exploration.py` (신규).
- 작업: 기존 divergence 재사용. 첫 탐색의 고정 brief, 비판의 적용 시점, 상충하는 고정 persona/peer guidance 정리. 같은 배치 coordination 입력이 섞이면 별도 작은 후속 작업으로 분리.
- 완료: 첫 배치에 동료 답변 노출 없음 / 중복 후보·한 provider 실패 시 부분 결과 유지 / 모델 한 개에서 유용한 대안 생성 가능.
- 검증: `.venv/bin/pytest tests/test_ideation_exploration.py tests/test_divergence_profile.py tests/test_role_plan.py -q`; 캡처한 실제 payload의 역할 충돌 수동 확인.

### RI-06 — 비교 가능한 구상 산출물 (M, 1일)

- 의존: RI-02, RI-05.
- 파일: `src/agent_lab/divergence.py`, `src/agent_lab/room/turn_flow_support.py`, `src/agent_lab/ideation.py`, `tests/test_ideation_options.py` (신규).
- 작업: 후보의 제목·작동 원리·사용 장면·차이·tradeoff·첫 실험을 구조화하고 저장. 기존 `divergence_options` 이벤트의 구형 consumer와 호환.
- 완료: 옵션 ID/revision 재접속 후 유지 / 형식 파싱 실패는 원문과 실패 상태 보존 / 유사도 점수를 창의성 정답으로 취급하지 않음.
- 검증: `.venv/bin/pytest tests/test_ideation_options.py tests/test_divergence_profile.py -q`; 옵션 순서 변경 후 같은 ID의 선택이 유지되는 사례.

### Checkpoint A — 대화 품질의 첫 판단

RI-01의 개발용 실제 아이디어 3개로 생성된 구상을 사용자가 평가한다. 기존 transcript로 읽어도 되며 전용 UI 완성을 기다리지 않는다. 다른 접근이 없거나 구체적 장면이 없으면 RI-05/06을 한 차례 조정한다. 여전히 native 단일 에이전트보다 도움이 없다면 신규 UI 투자를 중단하고 프롬프트/skill 수준으로 축소한다. mock 통과는 이 판정을 대신하지 않는다.

### RI-07 — 세션 생성·선택 API (M, 1일)

- 의존: RI-04, RI-06, Checkpoint A.
- 파일: `app/server/routers/room.py`, `app/server/routers/sessions.py`, `src/agent_lab/ideation.py`, `tests/test_ideation_api.py` (신규).
- 작업: 신규 세션의 명시 opt-in과 기존 sessions router 내 GET/PATCH ideation API. `expected_revision`, request ID, 사용자 선택·조합·reset 명령 지원. 기존 room run/SSE 전송 재사용.
- 완료: 중복 선택 멱등·오래된 선택 409 / 선택이 실행 승인으로 해석되지 않음 / 세션 GET 무부수효과.
- 검증: `.venv/bin/pytest tests/test_ideation_api.py tests/test_ideation_no_execute.py -q`; run 중 변경은 기존 busy 정책으로 거절하거나 다음 턴에 적용하고 최신 상태 유실 금지.

### RI-08 — 구상 비교와 선택 UI (M, 1~1.5일)

- 의존: RI-07.
- 파일: `web/src/api/client.ts`, `web/src/components/ConceptPanel.tsx` (신규), `web/src/components/RoomChatView.tsx`, `web/src/components/ConceptPanel.test.tsx` (신규), `web/src/styles/surfaces.css`.
- 작업: 기존 Room 옆에 작은 구상 패널. 후보 선택·부분 조합·모두 아님·방향 수정은 자연어와 명시 선택을 병행. 패널 자체 fetch는 기존 API client만 사용.
- 완료: 새로고침 후 선택/기각 복원 / stale/busy/API 실패 표시 / 키보드로 비교·선택 가능.
- 검증: `npm --prefix web test -- ConceptPanel`, `npm --prefix web run build`; 실제 API 브라우저에서 선택→새로고침→수정 확인. SSE가 필요한 후속 개선은 별도 작업으로 제한.

### RI-09 — 선택한 방향을 구체화 (M, 1일)

- 의존: RI-07.
- 파일: `src/agent_lab/ideation.py`, `src/agent_lab/agents/prompts.py`, `src/agent_lab/room/messages.py`, `tests/test_ideation_shaping.py` (신규).
- 작업: 선택·기각 이유를 context에 명시. 사용자 흐름·입출력 예·주요 구조·MVP/비범위·위험 가정을 만든다. 레포가 있으면 기존 read 도구로 근거를 확인.
- 완료: 사용자가 바꾼 조건 반영 / 기각 후보가 이유 없이 복귀하지 않음 / 사실·제안·미확인 가정 구분.
- 검증: `.venv/bin/pytest tests/test_ideation_shaping.py -q`; 실제 아이디어 한 건에서 중간에 시간/플랫폼 제약을 바꾸고 사용자 확인.

### RI-10 — 구상에 연결된 구현 계획 (M, 1일)

- 의존: RI-09.
- 파일: `src/agent_lab/room/plan_scribe.py`, `src/agent_lab/agents/prompts.py`, `src/agent_lab/ideation.py`, `tests/test_ideation_plan.py` (신규).
- 작업: 기존 Scribe 호출 한 곳에 선택 구상·결정·근거 입력 추가. 기존 plan writer로 기록하고 source revision/hash 연결. 선택 없는 경우 조건부 계획임을 표시.
- 완료: 작업별 범위·의존성·검증 포함 / 모르는 경로·사실을 제안으로 표시 / 구상 변경 시 기존 계획 stale.
- 검증: `.venv/bin/pytest tests/test_ideation_plan.py tests/test_scribe_input.py tests/test_plan_pending.py -q`; 실제 프로젝트에서 첫 작업을 담당할 에이전트가 미결 질문을 얼마나 다시 묻는지 관찰.

### RI-11 — 계획 내보내기 (M, 0.5~1일)

- 의존: RI-08, RI-10.
- 파일: `app/server/routers/sessions.py`, `web/src/api/client.ts`, `web/src/components/ConceptPanel.tsx`, `tests/test_ideation_export.py` (신규).
- 작업: 최신 구상과 계획, 첫 작업 지시문을 Markdown으로 복사/다운로드. 기존 `plan/approve`·외부 runner 호출 금지. 구형 실행 세션의 plan overwrite 금지.
- 완료: export revision이 표시되고 stale 상태 경고 / 미결 BLOCK·가정 포함 / export만으로 subprocess나 승인 상태 변화 없음.
- 검증: `.venv/bin/pytest tests/test_ideation_export.py tests/test_ideation_no_execute.py -q`; 내려받은 문서를 외부 에이전트에서 읽고 범위가 전달되는지 수동 확인.

### Checkpoint B — 핵심 경험 완주

개념 입력→비교→선택→구체화→계획→내보내기를 실제 API·live 모델로 한 건 완주한다. 중간 새로고침, 조건 수정, provider 실패도 각각 확인한다. 앱 표면의 결과와 저장 artifact를 대조하고 실행 시작이 없음을 확인한다. 텍스트 내용의 가치는 사용자에게 확인하되 각 내부 단계마다 승인 대기하는 제품 흐름을 만들지는 않는다.

### RI-12 — 새 Room의 실행 중심 UI 축소 (M, 1일)

- 의존: Checkpoint B.
- 파일: `web/src/components/RoomChatView.tsx`, `web/src/components/RoomChatMainPane.tsx`, `web/src/components/RoomChatComposerShell.tsx`, `web/src/utils/workspaceTabs.ts`, `web/src/utils/workspaceTabs.test.ts` (신규).
- 작업: 새 Room에서 autonomy/execute CTA·기본 IDE tab 표시 제거. 구상·계획·현재 질문을 우선. 기존 세션의 pending execution과 Inbox는 숨기지 않음. 실제 실행 UI 하위 소유 파일로 수정 범위를 옮길 수 있으나 독립 영역이면 분할.
- 완료: 새 Room에 실행 승인 문구 없음 / 기존 세션의 결정을 처리할 수 있음 / composer는 topic-only 유지.
- 검증: `npm --prefix web run build`, 해당 Vitest; 구형 pending execution fixture와 새 Room을 번갈아 열어 수동 확인.

### RI-13 — 실제 API E2E와 복구 (M, 1일)

- 의존: RI-11, RI-12.
- 파일: `web/e2e/ideation-journey.spec.ts` (신규), `tests/test_ideation_recovery.py` (신규), `docs/evals/room-ideation-protocol.md`.
- 작업: 정상 경로와 한 명 실패·취소·refresh·stale 선택·구상 변경 후 stale plan·기존 세션 호환을 기록. live 모델 호출은 opt-in 별도 실행.
- 완료: 데이터 유실 없이 resume / 미완료를 준비됨으로 표시하지 않음 / 전체 경로에서 의도치 않은 execute 0.
- 검증: `npm --prefix web run test:e2e -- ideation-journey.spec.ts`; mock 회귀와 live evidence packet을 구분. CI는 기존 mock-only 원칙 유지.

### RI-14 — 효용 확인과 기본값 전환 (S, 1일 + 사용 기간)

- 의존: RI-13, RI-01.
- 파일: `docs/evals/room-ideation-results.md` (신규), `app/server/routers/room.py`, `tests/test_ideation_api.py`.
- 작업: 보류한 실제 아이디어 3개를 포함한 비교 결과 확인. 기준 충족 시 신규 일반 Room 생성만 idea lane으로 전환. 기존 세션은 opt-in 없는 자동 변경 금지.
- 완료: §6의 결과·비용·실패 공개 / 기준 미달이면 기본 전환 보류 / 기존 세션 새로고침으로 migration 없음.
- 검증: 생성·재개 API 회귀, `make ci`, `npm --prefix web run build`; 전환 후 live 신규 Room 1건 재확인. 프론트 전체 테스트는 UI 변경 release 체크에서 한 번 실행.

### RI-15 — 사용되지 않는 배선 철거 (S/M 반복, 별도 작업)

- 의존: RI-14 이후 1~2주 실제 사용.
- 첫 작업 파일: `docs/ROOM-IDEATION-RETIREMENT.md` (신규), `docs/NOW.md`, `docs/CLEANUP-SSOT-2026-07.md`, `docs/EXTERNAL-REFS-TRACEABILITY.md`, `docs/F7-REPO-MAP-COMPACTION-DOGFOOD.md`.
- 작업: 문서 상태를 정리하고 실제 import·route·UI 참조와 구형 세션 지원 요구로 삭제 목록 확정. 이후 묶음마다 생산 코드 1~3개와 전용 테스트를 별도 작업으로 삭제. shared KPI를 죽은 코드로 재분류하려면 소비처 부재를 입증.
- 완료: 삭제한 기능의 사용자 대체 경로 명시 / 기존 세션 지원이 필요한 코드는 보존 / stale 문서·노출만 남지 않음.
- 검증: 목록마다 `rg` 호출자 확인, 필요한 테스트 lane, 구조 ratchet, `git diff --check`. 삭제량을 성과 지표로 사용하지 않음.

## 6. 효용 평가

목적은 개인의 재사용 여부를 결정하는 것이다. 6개 사례로 통계적 우위를 주장하지 않는다.

### 비교 방법

- A: 평소 사용하는 native 단일 에이전트에 목적·좋은 계획 기준을 충분히 전달. B: Agent Lab Room. 약한 프롬프트를 baseline으로 만들지 않는다.
- 같은 brief와 자료를 사용하고 실행 순서를 번갈아 둔다. 같은 아이디어를 먼저 본 효과와 실행 차이는 기록한다. A의 출력물을 B에만 제공하지 않는다.
- 같은 인간 상호작용 시간 상한을 사용한다. 모델별 비용/latency 차이는 별도 기록하고, 품질 차이를 멀티에이전트의 인과 효과라고 단정하지 않는다.
- 후보 초안은 가능하면 도구명을 가리고 비교한다. interactive 과정의 완전한 blind는 불가능하므로 한계로 기록한다.
- 모델 judge는 문서 형식·누락 점검 보조만 사용. 사용자 효용 판정자는 사용자다. mock와 live 결과 파일은 구분한다.

### 사용자 판정표 (사례마다 1~5점과 구체적인 한 줄 이유)

| 항목 | 확인 질문 |
|---|---|
| 유용한 새 방향 | 원래 생각하지 못했지만 실제 채택할 요소가 나왔는가? |
| 구체성 | 실제 사용 장면과 작동 방식을 설명할 수 있는가? |
| 적합성 | 내 목적·제약·취향을 반영했는가? |
| 착수 가능성 | 첫 작업을 시작하기 위해 다시 설계해야 할 부분이 얼마나 남았는가? |

추가 기록: 사용자 개입 시간, provider 호출/비용, 실패·재시도, 장황해서 버린 출력, 다음 날 계획 수정 범위, 어느 결과로 실제 작업을 시작했는가.

**제안 운영 기준:** 6개 중 4개 이상에서 Room 결과를 선호하고, 보류한 확인용 3개 중 2개 이상에서도 선호하며, 2개 이상의 계획으로 실제 외부 개발을 시작한다. 설정·대화 부담이 이 이익을 없애지 않아야 한다. 사용자 사용 시간이 부족하면 미측정 상태로 유지하고 새로운 지표를 만들어 대체하지 않는다.

기준 미달: 한 차례 개선 후 재평가. 여전히 이득이 없으면 좋은 prompt/문서 템플릿만 추출하고 전용 Room 개발은 동결한다. 특정 종류의 아이디어에만 효과가 있으면 그 용도로 좁힌다.

## 7. 일정과 중단 지점

| 묶음 | 작업 | 예상 |
|---|---|---|
| 첫 주 | RI-00~06, Checkpoint A | 집중 개발 약 5~6일 + 아이디어 평가 |
| 둘째 주 | RI-07~11, Checkpoint B | 약 5~6일 |
| 셋째 주 | RI-12~14, live 비교·기본값 판단 | 약 3일 개발 + 실제 사용 |
| 이후 | RI-15, 효용 확인된 불필요 배선만 철거 | 주당 작은 작업 1~2개 |

전체는 약 13~16 집중 작업일 추정이다. 기존 정책·상태 결합 때문에 늘어날 수 있다. **우선 투자 범위는 첫 주까지**로 잡고, 구상 품질이 나아지는지 확인한 뒤 UI·내보내기 구현을 계속한다. 구현 예측이 4주를 크게 넘으면 multi-provider 확장·전용 패널의 편의 기능을 줄이고 기존 transcript와 Markdown으로 먼저 완성한다.

## 8. 주요 위험과 대응

| 위험 | 대응 |
|---|---|
| 기존 divergence보다 달라지는 것이 형식뿐 | 실제 선택을 바꾼 새 접근으로 평가, Checkpoint A에서 중단 가능 |
| 개념을 구조화하다가 다시 복잡한 플랫폼이 됨 | run.json 하위 상태 하나, 새 engine·DB·자동 학습·workflow editor 없음 |
| 발산과 기존 고정 critic/합의 지침 충돌 | payload 캡처와 단계별 지침 검사. explore에서 critique를 기본 호출하지 않음 |
| 선택을 기록했는데 Scribe 요약에서 소실 | selection/decision을 직접 입력, revision/hash로 stale 판정 |
| 외부 검증 없이 기술을 사실로 단정 | repo/source 근거와 가정 분리, 가장 작은 실험을 계획의 첫 작업으로 |
| 새 Room의 선택이 legacy 승인에 연결 | 별도 ideation mutation, legacy approve/execute 진입 회귀 |
| 한 모델 장애로 Room 전체 정지 | 부분 후보와 실패 상태 유지, 단일 모델도 지원 |
| mock으로 다시 효용을 증명하려 함 | deterministic 회귀와 사용자 live 평가 분리, 미측정 값 보존 |
| 코드 삭제가 목표가 됨 | 제품 경로 축소부터 적용. shared·legacy 소비처가 있으면 물리 삭제 보류 |

## 9. 이번 계획 작성에서 변경한 것

이 계획 파일만 추가했다. 기존 `docs/NOW.md`, 미추적 flag 문서·테스트와 연구 폴더는 수정하지 않았다. 실행·삭제·신규 UI 구현은 수행하지 않았다. 다음 구현 착수점은 RI-00과 RI-01이며, 첫 기술 작업은 RI-02다.
