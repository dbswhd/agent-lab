# Idea lane 구현 검토와 다음 작업

- 검토일: 2026-09-13
- 기준 커밋: `a0bd4337` (RI-07~13 병합 후)
- 판정: **주요 연결을 보완했다.** 후보→선택→조건·구체화→명시적 계획 요청과 품질 경계를 실제 API에 연결했고, provider만 고정한 실서버 브라우저 E2E를 추가했다.
- 최초 검토의 R1~R6는 이 문서의 발견 기록으로 보존한다. 수정 근거와 남은 평가 한계는 아래 검증 기록과 [room-ideation-results.md](./room-ideation-results.md)에 반영한다.

## 현재 상태

| 범위 | 검토 판정 |
|---|---|
| RI-02~06 | 상태 보존·독립 후보 수집·실행 경계의 회귀 기반은 유지된다. 아래 품질 문제는 별도 보완 필요 |
| Checkpoint A | development 3건의 대리지표에 의한 provisional pass 유지. 사용자 채택·시간 절감의 실측 증거는 아님 |
| RI-07~08 | API와 패널 연결 완료. 신규 세션은 명시적 `아이디어 구상` opt-in |
| RI-09~11 | 조건·구체화·명시적 계획 요청, 품질 경계, 조합 export 보존 연결 |
| Checkpoint B | 미통과. 기존 development 아이디어 한 건으로 시작할 수 있으며 holdout 3건을 기다릴 필요 없음 |
| RI-12 | 조건부 UI 축소 코드는 존재. 실제 브라우저 수용 검증과 별도로 구분해야 함 |
| RI-13 | HTTP 단위/통합 회귀와 브라우저 route mock 유지 + provider-only 실서버 SSE/storage E2E 추가 |
| RI-14~15 | 효용 평가·기본값 전환·철거는 아직 진행 조건 미충족 |

## 주요 발견

### R1 · P1 — 선택 이후 계획 생성으로 이어지는 운영 경로가 없다

근거: `src/agent_lab/ideation.py:278`, `:427`, `:435`, `:574`, `:550`.

`change_condition()`, `set_concept()`, `enter_plan_stage()`는 정의와 테스트 외 생산 호출자가 없다. PATCH 명령은 select/combine/reject/reset만 제공한다. 그런데 Scribe는 idea lane의 `plan` 단계에서만 허용된다.

임시 세션 + 실제 FastAPI TestClient + mock provider로 재현:

1. `/api/room/runs`에 `ideation=true`로 생성 → HTTP 200.
2. 후보 선택 PATCH → HTTP 200, `stage=shape`.
3. PATCH `command=plan` 또는 `change_condition` → HTTP 422.
4. 기존 세션에 “조건을 iOS 전용으로 바꾸고 이 구상으로 계획 만들기”, `synthesize=true` 전송 → HTTP 200이지만 `stage=shape`, `concept=None`, `constraints=[]`, 계획 파일 없음.

해결: 명시 계획 요청과 조건 변경을 기존 Room 턴/명령 처리에 연결하고, 구체화 산출물을 revision과 함께 저장한다. 자연어 의도 해석이 불확실하면 현재 요청만 짧게 확인하되 내부 단계별 승인 흐름은 만들지 않는다. 선택 자체는 실행 승인이 아니다.

### R2 · P1 — 품질 상태가 합성·내보내기의 실제 제한으로 작동하지 않는다

근거: `src/agent_lab/room/plan_scribe.py:64`, `:90`, `src/agent_lab/ideation_export.py:99`, `web/src/utils/conceptPanelView.ts:95`.

`needs_review` 후보를 선택해도 일반 agent summary에는 해당 주장이 남는다. 이후 quality block을 덧붙이지만 Scribe 호출과 반환 내용을 검증하는 제한은 없다. export는 선택 필드를 quality 확인 없이 출력한다. UI도 quality 필드를 소비하지 않는다.

재현: “레포에 이미 인증 엔진이 구현되어 있다.”를 포함하는 6개 필드 후보는 `needs_review`로 분류됐다. 그럼에도 미확인 주장이 일반 Scribe summary에 남았고, mock provider가 돌려준 같은 문장도 그대로 반환됐다. export에는 `- 작동 원리: 레포에 이미 인증 엔진이 구현되어 있다.`가 출력됐으며 후보 품질 경고는 없었다.

해결: 후보 검사 → 합성용 입력 → 최종 문서 → export에서 같은 품질 판단을 사용한다. 제안·가정은 허용하되 확인된 레포 사실과 구분하고, 충족하지 못한 문서는 수정 필요 상태로 반환한다. 이 문제에 대해서는 이전의 “차단 완료” 보고를 “분류와 프롬프트 지침 구현”으로 정정한다.

### R3 · P1 — 조합 선택의 내용이 최종 계획과 export에서 빠진다

근거: `src/agent_lab/ideation.py:377`, `src/agent_lab/room/context/ideation_quality.py:121`, `src/agent_lab/ideation_export.py:67`.

조합은 selection에 새 ID와 parent IDs만 저장한다. options에 새 후보가 없으므로 `selected_option()`은 None이다. 구체화 context에는 parent options가 전달되지만 최종 합성의 구조화된 선택 블록과 export에는 조합 내용이 전달되지 않는다.

재현: 부모 두 개를 조합한 후 `selected_option=None`; 합성 블록에는 조합 ID만 있고 선택 필드가 없었다. export에는 조합 제목과 부모 작동 원리가 모두 없었다.

해결: 선택 해석을 공통 함수로 만들고 단일/조합 모두 같은 경로로 구체화·계획·export에 전달한다. 조합은 어느 부모의 어떤 부분을 채택했는지도 보존한다.

### R4 · P2 — 신규 idea lane 진입과 준비 상태 표시가 불완전하다

근거: `web/src/api/client.ts:1889`, `:2035`, `web/src/utils/conceptPanelView.ts:149`.

서버에는 신규 생성 `ideation` 인자가 있지만 `RunRoomOptions`와 전송 FormData에는 없다. 일반 UI 사용자는 새 idea lane에 들어갈 수 없다. 또한 UI는 stage가 plan이면 계획 파일 존재·생성 실패·stale 여부와 무관하게 “계획 준비됨”을 표시한다.

해결: 새 구상 시작의 명시적 UI 진입점을 연결한다. 기본값 전환은 별도 결정으로 남긴다. 준비 상태는 단계가 아니라 문서 존재·품질·source revision을 함께 근거로 계산한다.

### R5 · P2 — 레포 주장 검사와 메타 제거는 부분적인 휴리스틱이다

근거: `src/agent_lab/room/context/ideation_quality.py:25`, `:41`, `:77`, `:103`, `web/src/utils/conceptPanelView.ts:110`.

재현:

- `ref: src/does-not-exist.py#L99999`를 붙이면 존재 여부와 무관하게 미확인 주장 목록에서 빠진다.
- `Authentication is already implemented in the repository.`도 감지되지 않는다.
- `제안: src/new_module.py에 새 기능을 구현한다.`는 사실 주장이 아닌데 검토 대상으로 분류된다.
- `quality.status=ready`만 있으면 필수 필드가 없어도 synthesis-ready로 인정된다.

메타 제거는 일부 한국어 시작 문장에만 적용된다. 파싱 실패 시 새 UI는 보존된 raw를 그대로 표시하므로 제거했던 과정 설명도 다시 노출될 수 있다.

해결: 자유문장 정규식을 계속 늘리기보다 사실/제안/가정과 evidence를 구분하는 구조를 사용한다. 참조 경로·줄의 존재를 실제 연결 레포에서 검사하되, 존재 확인을 의미적 사실 입증으로 부르지 않는다. raw 감사 기록과 기본 표시용 정제 텍스트를 분리한다.

### R6 · P2 — 현재 E2E가 핵심 연결 누락을 검출하지 못한다

근거: `web/e2e/ideation-journey.spec.ts:4`, `:156`, `:453`, `tests/test_ideation_recovery.py:196`.

브라우저 테스트는 `/api`를 전부 가로채고 mock 상태를 직접 바꾼다. 복구 테스트도 계획 단계·구상·조건을 helper로 직접 주입한다. 따라서 R1처럼 운영 경로가 빠져도 통과한다. mock provider와 mock HTTP는 서로 다른 검증 층이다.

해결: provider만 mock하고 실제 서버·SSE·파일 저장을 통과하는 브라우저 여정을 추가한다. 시작부터 계획 생성·조건 수정·stale 표시·재생성·export까지 사용자 입력만으로 진행한다. 중간 상태 직접 주입은 전체 여정 검증에서 사용하지 않는다.

## 추가 정리

- `.agent-lab/PROJECT.md`는 idea lane을 미구현으로, `docs/NOW.md`는 다음을 RI-07로 기록한다.
- `docs/evals/room-ideation-protocol.md:54`는 사례가 0건이라지만 실제 JSONL에는 development 3건이 있다.
- 결과 문서의 8개 항목 계약 설명과 코드의 후보 6개 필드 계약은 구분해 써야 한다. 최종 문서 형식 전체가 코드로 검증된 것은 아니다.
- 기존 평가의 위험 발견·예상 재사용 점수는 사용자의 핵심 목표인 “채택할 만한 새로운 구상”을 직접 측정하지 않는다. 향후 비교에는 새로 채택한 설계 요소, 목적 적합성, 첫 작업을 시작하기 위한 재설계량, 사용자 개입 시간을 남긴다. 모델 평점은 대리지표다.
- ConceptPanel의 listbox keydown은 하위 버튼의 Enter도 가로채 후보 선택으로 처리할 수 있다. 세션 변경 시 비동기 응답 역전과 이전 export 잔존도 컴포넌트 수준에서 점검해야 한다. 이번에 실제 브라우저로 재현한 항목은 아니다.

## 다음 작업 순서와 완료 기준

1. **운영 흐름 연결 (R1/R4)**: UI에서 명시적으로 새 구상 생성 → 후보 선택 → 조건 수정 → 구체화 저장 → 계획 요청을 실제 API로 완주. refresh 후 동일 결정·구상·계획 보존. 실행 호출 0.
2. **품질 전달과 조합 보존 (R2/R3/R5)**: 미확인 주장이 일반 summary/export로 우회하지 않고, 가정은 가정으로 유지. 조합의 채택 요소가 문서까지 전달. 문서가 없거나 실패·stale이면 준비됨으로 표시하지 않음.
3. **실제 서버 E2E와 기록 정합성 (R6)**: provider mock으로 브라우저→서버→저장 전체 여정 실행. stale·실패·취소·재접속을 포함. 문서 상태 갱신 및 Makefile baseline drift/간헐 테스트 실패 원인 확인.
4. **Checkpoint B**: 기존 development case인 강의자료 기반 학습자료 도구로 live 한 건 완주. 중간에 사용자 제약을 바꾸고 최종 export의 반영 여부 확인. 원본 강의자료 생성 품질이 아니라 Agent Lab의 아이디어→계획 전달 경험을 평가한다.
5. **RI-14**: 실제 새 아이디어가 생길 때 holdout을 수집하고 native와 비교. 외부 에이전트가 첫 작업을 시작할 때 재질문·재설계가 줄었는지 기록. 기준 충족 전 기본값 전환은 보류.
6. **RI-15**: 효용 확인 이후 사용되지 않는 배선만 철거. 지금은 provider 확대·자동 루프 추가·패널 편의 기능 확대보다 완주 가능한 한 경로에 집중.

## 검증 기록

- 실제 서버 E2E: `npm --prefix web run test:e2e -- --config=playwright.ideation.config.ts` — **1 passed**. Provider 응답만 하네스에서 고정하고 Vite 브라우저, FastAPI HTTP/SSE, `run.json`·`plan.md` 저장을 통과했다.
- 여정 회귀: 선택 → 조건 저장 → 구체화 저장 → 명시적 계획 요청 → `plan_status=ready`와 source revision 확인. execute 호출과 execution 기록은 0건.
- 근거 경계 회귀: 최종 Scribe 문서가 미확인 레포 주장을 포함하면 `plan_status=failed`로 남고 준비됨으로 표시하지 않는다.

- `.venv/bin/pytest tests/test_ideation*.py tests/test_scribe_input.py -q`: **228 passed**.
- `npm --prefix web test -- ConceptPanel workspaceTabs`: 실행된 **48 files / 239 tests passed** (스크립트의 `src` 인자로 전체 단위 테스트도 포함됨).
- `npm --prefix web run build`: **통과**, 기존 대형 chunk 경고.
- `make test-fast`: **3684 passed, 2 failed, 1 skipped, 1 xfailed**.
  - `test_structure_metrics_check_passes`: Makefile 기준 543행/112 targets, 실제 551행/114 targets.
  - `test_logout_command_returns_auth_run`: 전체 실행에서 로그아웃 메시지가 chat에 남아 실패. 같은 테스트 단독 재실행은 **1 passed**. 순서/환경 의존 가능성이 있으나 원인은 이번 검토에서 확정하지 않았다.
- R1/R2/R3/R5 재현은 실제 Python 함수/HTTP에 mock provider를 사용했다. live 결과나 브라우저 수용 증거로 해석하지 않는다.
