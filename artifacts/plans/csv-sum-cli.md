<!-- plan-path: artifacts/plans/csv-sum-cli.md -->

## TL;DR
> Summary: `scratch/csv_sum/`에 `--column` 옵션 기반 CSV 숫자 합산 CLI를 구현하고 15개 pytest로 전체 검증 완료.
> Deliverables:
> - `csv_sum.py` (CLI 진입점, argparse)
> - `fixtures/sales.csv`, `fixtures/scores.csv`
> - `test_csv_sum.py` (15/15 PASSED)
> Risk: Low — 구현·테스트 모두 완료, 외부 의존 없음.

## Must
- `--column COL` 옵션 필수; 없으면 argparse가 오류 출력
- 빈 파일·헤더만 있는 파일·존재하지 않는 컬럼 각각 별도 예외 경로 처리
- 비숫자 셀은 skip 또는 오류 (현재: `ValueError` 발생 시 종료)
- fixtures 2개 포함 (`sales.csv`, `scores.csv`)

## Must-NOT
- 코어 Room/plan 코드 수정 금지 (Trading F5 규칙 동일하게 적용 — scratch는 격리 레인)
- `sessions/*` 커밋 금지
- 실 LLM 호출 테스트 추가 금지

## Parallel waves
Wave 1 (완료): csv_sum.py 구현, fixtures 생성, test_csv_sum.py 작성
Wave 2 (완료): pytest 15/15 통과 확인

## Evidence paths
- `scratch/csv_sum/csv_sum.py`
- `scratch/csv_sum/test_csv_sum.py`
- `scratch/csv_sum/fixtures/sales.csv`
- `scratch/csv_sum/fixtures/scores.csv`

---

## 지금 논의 중인 것

`scratch/csv_sum/` CLI 구현이 요청 직후 완료됐다. Codex(L3)가 Claude의 15/15 결과를 독립 재확인하겠다고 선언한 상태이며, Cursor(L4)는 전체 방향을 ENDORSE했다. 현재 핵심 관심사는 **독립 검증 완료 여부**와 `DictReader` 빈 줄 스킵 동작에 대한 주의사항 공유다.

## 합의된 점

- `--column` argparse 옵션, 헤더 없는 파일·컬럼 누락·빈 파일 예외 처리, fixtures 2개, pytest 15케이스 모두 요구사항 충족.
- `csv.DictReader`는 데이터 중간 빈 줄을 자동으로 skip하므로 `test_blank_lines_skipped`가 별도 처리 없이 통과됨 — 이 동작은 의도된 Python 표준 동작. (ref: chat.jsonl#L2)
- Cursor: 기존 합의(L1)를 그대로 ENDORSE, 추가 수정 요구 없음. (ref: chat.jsonl#L4)

## 쟁점 / 미결정

Codex의 독립 확인 결과가 아직 반영되지 않음 — 15/15를 동일하게 재현하면 완료, 편차 발견 시 버그 픽스 필요. (ref: chat.jsonl#L3)

## 에이전트별 핵심

**Claude:** csv_sum.py + fixtures + test 15케이스 구현 완료; `DictReader` 빈 줄 skip 동작 주의사항 공유. (ref: chat.jsonl#L2)
**Codex:** Claude 결과 독립 재확인 선언; 요구사항별 완료 기준(CLI 실행, 예외 코드/메시지, fixtures 존재) 체크 예정. (ref: chat.jsonl#L3)
**Cursor:** ENDORSE — 추가 의견 없이 기존 합의 지지. (ref: chat.jsonl#L4)

---

## 지금 실행

1.
   - 무엇을: Codex 독립 검증 — pytest 15/15 재현 및 CLI 예외 경로 smoke 확인
   - 어디서: `scratch/csv_sum/test_csv_sum.py`
   - 검증: `pytest scratch/csv_sum/test_csv_sum.py -v` 출력에서 `15 passed` 확인 (`scratch/csv_sum/.pytest_cache/` 갱신)

## 실행 순서 (이후)

2.
   - 무엇을: 비숫자 셀 처리 정책 확정 (현재 ValueError → exit; skip 옵션 추가 여부)
   - 어디서: `scratch/csv_sum/csv_sum.py`
   - 검증: `--skip-errors` 플래그 추가 시 관련 테스트 케이스 통과 확인 (ref: chat.jsonl#L2)

3. Human이 `scratch/csv_sum/` 결과를 코어 모듈로 승격 요청할 경우 별도 PR로 분리 — execute gate 준수. (ref: 불명확)
