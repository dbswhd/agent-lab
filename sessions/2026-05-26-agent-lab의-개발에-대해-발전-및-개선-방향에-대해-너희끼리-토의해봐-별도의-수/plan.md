## 지금 논의 중인 것
- `#3`은 `ROOM_SCRIBE` 변경과 출력 검증까지 완료된 것으로 정리되었고, `plan.md`에 남은 “정리 1회 검증 남음” 표기만 정리하면 닫을 수 있다. (ref: chat.jsonl#L470, chat.jsonl#L489)
- 현재 핵심 안건은 `#4` thin execute 1차 범위와 착수 조건이다. 1차 초안은 `plan.md`의 3필드 액션 1건을 선택해 dry-run, Human 승인, 실행, `executions[]` 기록까지 연결하는 것이다. (ref: chat.jsonl#L477, chat.jsonl#L479, chat.jsonl#L480)
- Human은 `PASS`를 “그 상태 그대로 적용 가능한 완전 마무리 상태”로 정의했고, 에이전트들도 현재 `#4`는 아직 plan 반영과 4e 결정이 남아 있어 착수 PASS가 아님을 확인했다. (ref: chat.jsonl#L487, chat.jsonl#L488, chat.jsonl#L504)

## 합의된 점
- `#3`에서 변경한 범위는 `prompts.py`의 `ROOM_SCRIBE`뿐이며, execute, UI, 파서, `PLAN_FORMAT_VERSION`은 변경하지 않았다. `## 다음에 할 일`은 작업 액션의 3필드 형식과 Human gate/보류 항목의 한 줄 형식을 구분한다. (ref: chat.jsonl#L468, chat.jsonl#L470)
- `#4` 1차 구현 순서는 `4a(room.py prev_run 보존) → 4b(3필드 액션 파서) → 4c(dry-run+승인 API) → 4d(UI)`로 잡는다. `room.py` 보존이 없으면 실행 기록이 discuss turn에서 덮어써지므로 선결조건이다. (ref: chat.jsonl#L479, chat.jsonl#L480, chat.jsonl#L481)
- `#4` 1차 범위에서 자동 undo, 한 줄 gate/미결 항목 실행, Codex/Claude 기본 write 정책 변경, 전체 execute 파이프라인 확장은 제외한다. (ref: chat.jsonl#L477, chat.jsonl#L479, chat.jsonl#L480, chat.jsonl#L481)
- Human gate 3개는 확정됐다: 1차 executor는 Cursor만, dry-run은 `git diff`와 변경 예정 파일 목록, 자동 undo 없이 범위 밖 변경은 `review_required`로 남기고 Human이 수동 복구한다. (ref: chat.jsonl#L502, chat.jsonl#L503, chat.jsonl#L504, chat.jsonl#L505)

## 쟁점 / 미결정
- `#4` 전 execute 직접 write 금지는 확정 정책이 아니라 미결 항목으로 유지한다. 승인형 execute 경로와 런타임 직접 write 차단은 분리해 다룬다. (ref: chat.jsonl#L481, chat.jsonl#L492, chat.jsonl#L504)
- `4e` regression fixture를 `#4` 1차 완료 조건에 포함할지, stretch 항목으로 둘지 Human 결정이 남아 있다. (ref: chat.jsonl#L485, chat.jsonl#L493, chat.jsonl#L504, chat.jsonl#L505)
- `run.json` 필드명과 3필드 파서 위치(`planMeta.ts` 또는 서버 측 Python)는 구현 착수 전 확정이 필요하다. (ref: chat.jsonl#L485)
- `plan.md`에는 아직 `#4` 채택안, 확정된 gate 3개, 4e 판단이 반영되어 있지 않고 `#3` 잔재가 남아 있다. (ref: chat.jsonl#L495, chat.jsonl#L504)

## 에이전트별 핵심 (Cursor / Codex / Claude)
- Cursor: `#4`는 승인형 execute 경로를 `4a→4d` 순으로 구축해야 하며, plan 정리와 4e 결정 전에는 Human 기준 PASS가 아니라고 정리했다. (ref: chat.jsonl#L481, chat.jsonl#L489, chat.jsonl#L504)
- Codex: 권한 경계만 정의해서는 부족하며, 확정된 gate 3개와 미결 사항이 `plan.md`에 반영·확인된 뒤에만 착수 PASS로 볼 수 있다고 정리했다. (ref: chat.jsonl#L480, chat.jsonl#L492, chat.jsonl#L503)
- Claude: Claude write 기본값 변경은 이번 범위에서 제외해야 하며, Human gate 확정 뒤 `#4` 채택안과 미결을 plan에 반영해야 한다고 확인했다. (ref: chat.jsonl#L479, chat.jsonl#L495, chat.jsonl#L505)

## 다음에 할 일
1.
   - 무엇을: `#3` 완료 상태에 맞게 잔여 표기인 “정리 1회 검증 남음”과 관련 문서 정리 액션을 제거하거나 완료 상태로 정리한다.
   - 어디서: `plan.md`의 `## 쟁점 / 미결정`, `## 다음에 할 일`
   - 검증: `#3`이 미결 또는 후속 검증 대상으로 더 이상 남아 있지 않은지 확인한다. (ref: chat.jsonl#L470, chat.jsonl#L485, chat.jsonl#L495, chat.jsonl#L504)

2.
   - 무엇을: `#4` 1차 채택안과 확정된 Human gate 3개를 문서에 반영하고, execute 직접 write 금지를 미결 항목으로 유지한다.
   - 어디서: `plan.md`
   - 검증: `4a→4b→4c→4d`, 제외 범위, 확정된 gate 3개, execute 직접 write 금지 미결이 모두 구분되어 기록되어 있는지 확인한다. (ref: chat.jsonl#L492, chat.jsonl#L503, chat.jsonl#L504, chat.jsonl#L505)

3. Human이 `4e` regression fixture를 `#4` 1차 완료 조건에 포함할지 stretch로 둘지 확정한다. (ref: chat.jsonl#L485, chat.jsonl#L493, chat.jsonl#L504, chat.jsonl#L505)

4.
   - 무엇을: discuss turn 이후에도 execute 기록 컨테이너가 보존되도록 `prev_run` 기반 보존을 구현한다.
   - 어디서: `room.py`의 `actions[]`, `approvals[]`, `executions[]` 기록 처리
   - 검증: discuss 1턴 실행 후 기존 execute 기록이 `[]`로 덮어써지지 않고 유지되는지 확인한다. (ref: chat.jsonl#L477, chat.jsonl#L479, chat.jsonl#L481)

5.
   - 무엇을: `plan.md`의 3필드 액션만 execute 후보로 추출하는 파서와 후보 필터를 구현한다.
   - 어디서: `planMeta.ts` 또는 서버 측 Python 파서 위치 확정 후 해당 모듈
   - 검증: 3필드 액션과 한 줄 gate/미결 항목이 섞인 plan에서 3필드 액션만 execute 후보로 노출된다. (ref: chat.jsonl#L477, chat.jsonl#L485)

6.
   - 무엇을: 선택한 액션의 dry-run diff, Human 승인/거부, 실행 결과 및 범위 초과 상태 기록 흐름을 구현한다.
   - 어디서: `main.py`, `room.py`, `run.json`의 `actions[]`/`approvals[]`/`executions[]`
   - 검증: `git diff`와 변경 예정 파일 목록 확인 후 승인된 실행만 진행되고, 범위 밖 변경은 `review_required`로 기록된다. (ref: chat.jsonl#L477, chat.jsonl#L502, chat.jsonl#L503)

7.
   - 무엇을: plan 탭에서 3필드 액션 1건을 선택해 dry-run, 승인, 실행 결과까지 확인할 수 있는 UI를 구현한다.
   - 어디서: `RoomRunControls` 등 plan 실행 UI
   - 검증: 한 줄 gate/미결 항목은 실행 UI에 표시되지 않고, 승인된 액션 1건이 `executions[]` 기록까지 end-to-end로 완료된다. (ref: chat.jsonl#L477, chat.jsonl#L480)
