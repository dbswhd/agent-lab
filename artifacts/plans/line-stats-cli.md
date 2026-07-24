<!-- plan-path: artifacts/plans/line-stats-cli.md -->

## TL;DR
> Summary: `scratch/line_stats/`에 여러 텍스트 파일의 줄 수·문자 수를 합산 출력하는 CLI를 구현하고 pytest 13개 전부 통과했다.
> Deliverables:
> - `scratch/line_stats/main.py` — CLI 진입점
> - `scratch/line_stats/fixtures/` — 샘플 텍스트 3개
> - `scratch/line_stats/tests/` — pytest 13개
> Risk: Low — 독립된 scratch 폴더, 코어 모듈 무관

## Must
- pytest 13개 전원 green 유지
- fixtures/ 파일 3개 이상 존재

## Must-NOT
- 코어 `src/agent_lab/` 수정 없음
- `sessions/*` 커밋 없음
- execute gate 우회 없음

## Parallel waves
Wave 1 (완료): CLI 구현 + fixtures 생성 + pytest 작성
Wave 2 (완료): Codex 검증(출력 확인), Cursor 최종 ENDORSE

## Evidence paths
- `scratch/line_stats/main.py`
- `scratch/line_stats/fixtures/`
- `scratch/line_stats/tests/`

---

## 지금 논의 중인 것

`scratch/line_stats/` 하위에 텍스트 파일 여러 개의 줄 수·문자 수를 합산해 출력하는 CLI를 만드는 작업. fixtures 서브폴더에 샘플 파일 2–3개, pytest 테스트를 포함하는 요구사항이었다. 구현과 검증까지 한 턴에 완료됐다. (ref: chat.jsonl#L2)

## 합의된 점

세 에이전트 모두 구현 완료·검증·ENDORSE까지 한 턴에 마무리했다. Claude가 구현하고 13/13 통과를 확인했으며, Codex가 독립적으로 CLI 샘플 출력(총 12줄·242문자)과 fixtures 3개 존재를 재확인했다. Cursor는 결과를 ENDORSE했다. (ref: chat.jsonl#L2, chat.jsonl#L3, chat.jsonl#L4)

## 쟁점 / 미결정

현재 미결 사항 없음. 필요 시 인코딩 처리(UTF-8 외 파일) 또는 재귀 디렉터리 스캔 옵션 추가를 고려할 수 있다.

## 에이전트별 핵심

**Claude:** CLI + fixtures + pytest 13개 구현, 실행 출력 확인까지 완료. (ref: chat.jsonl#L2)
**Codex:** pytest 13개 재검증, CLI 샘플 출력(12줄·242문자) 및 fixtures 3개 존재 독립 확인. (ref: chat.jsonl#L3)
**Cursor:** 구현 결과 전체 ENDORSE. (ref: chat.jsonl#L4)

---

## 지금 실행

1.
   - 무엇을: pytest를 실행해 13개 테스트가 여전히 green인지 확인한다.
   - 어디서: `scratch/line_stats/`
   - 검증: 터미널에서 `13 passed` 출력 확인. (ref: chat.jsonl#L3)

## 실행 순서 (이후)

2.
   - 무엇을: 재귀 디렉터리 스캔 옵션(`--recursive`) 추가 여부를 결정한다.
   - 어디서: `scratch/line_stats/main.py`
   - 검증: 옵션 추가 시 해당 경로 pytest 통과 확인. (ref: 불명확)

3. 인코딩 처리(UTF-8 외) 요건이 생기면 Human 승인 후 착수. (ref: 불명확)
