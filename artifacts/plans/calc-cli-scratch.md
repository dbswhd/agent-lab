<!-- plan-path: artifacts/plans/calc-cli-scratch.md -->

## TL;DR
> Summary: `scratch/calc_cli/` 안에 사칙연산 CLI 계산기를 구현했다. 기존 agent-lab 코드에 영향 없이 독립 작동하며, 테스트 17개 전부 통과한 상태로 확정됐다.
> Deliverables:
> - `scratch/calc_cli/calc.py` — CLI 진입점 + 사칙연산 로직
> - `scratch/calc_cli/test_calc.py` — pytest 17개
> - `scratch/calc_cli/README.md` — 간단한 사용법
> - `scratch/.gitignore` — `__pycache__` 등 캐시 제외
> Risk: Low — 독립 폴더, 기존 코드 영향 없음

## Must
- `scratch/calc_cli/` 내부에서만 파일 생성·수정
- 덧셈/뺄셈/곱셈/나눗셈 4연산 지원
- 0 나눗셈·비숫자 입력·OverflowError·nan/inf 입력 모두 에러 처리
- pytest 17개 통과 유지

## Must-NOT
- 기존 `src/agent_lab/`, `app/`, `tests/`, `web/` 코드 수정 금지
- agent-lab CI(`make test-fast`, `make ci`) 테스트 영향 금지
- 추가 개선 작업 금지 (Human이 명시적으로 마무리 지시)

## Parallel waves
Wave 1 (완료): `calc.py` 구현, `test_calc.py` 작성, `README.md` 작성, `scratch/.gitignore` 추가
Wave 2 (스킵): nan/inf 추가 논의 — Human 종료 선언으로 스킵

## Evidence paths
- `scratch/calc_cli/calc.py`
- `scratch/calc_cli/test_calc.py`
- `scratch/calc_cli/README.md`
- `scratch/.gitignore`

---

## 지금 논의 중인 것

Human이 "nan/inf 관련 논의 종료, 추가 개선 없이 마무리"를 선언했다. 에이전트들이 발견한 두 가지 미세 이슈(`calc.py:28` callable 타입 힌트, `README.md:24` 한/영 혼용)는 이번 사이클 범위 밖으로 확정됐다. (ref: chat.jsonl#L28, chat.jsonl#L30)

## 합의된 점

`scratch/calc_cli/` 구현이 완료됐다. `calc.py`는 `math.isfinite` 가드(`:58`)로 nan/inf를 차단하고, 0 나눗셈·비숫자 입력·OverflowError도 처리한다. pytest 17개 전부 통과. 기존 agent-lab 코드 영향 없음. (ref: chat.jsonl#L29, chat.jsonl#L30)

## 쟁점 / 미결정

알려진 한계 (다음 사이클로 이월, 이번에는 수정 안 함):
- `calc.py:28` — `dict[str, callable]` 타입 힌트가 정밀하지 않음 (`Callable[[float, float], float]` 권장) (ref: chat.jsonl#L28)
- `README.md:24` — 한국어/영어 혼용 OOS 표기 (ref: chat.jsonl#L30)

## 에이전트별 핵심

**Claude** (L28): `calc.py:28` callable 힌트 및 README 혼용 문제를 CHALLENGE로 제기했으나, Human 마무리 지시에 따라 이번 사이클 수정 대상 아님으로 정리.
**Codex** (L29): 전체 구현 완료 보고 — CLI·테스트·README·gitignore 포함, 17개 테스트 통과 확인.
**Cursor** (L30): 현재 파일 상태 팩트 체크 — `calc.py:58` isfinite 가드 존재, `README.md:24` OOS 한 줄 확인.

---

## 지금 실행

1.
   - 무엇을: 테스트 17개가 현재도 통과하는지 최종 확인한다.
   - 어디서: `scratch/calc_cli/test_calc.py`
   - 검증: `pytest scratch/calc_cli/ -v` 출력에서 17 passed, 0 failed.

## 실행 순서 (이후)

2. Human `#next` 전까지 `calc.py:28` 타입 힌트 및 README 언어 혼용 수정 보류. (ref: chat.jsonl#L28, chat.jsonl#L30)
3.
   - 무엇을: `callable` → `Callable[[float, float], float]` 타입 힌트로 교체 (다음 사이클).
   - 어디서: `scratch/calc_cli/calc.py`
   - 검증: `mypy scratch/calc_cli/calc.py` 에러 0개.
4.
   - 무엇을: README 한/영 혼용 OOS 표기 통일 (다음 사이클).
   - 어디서: `scratch/calc_cli/README.md`
   - 검증: README 전체 한국어 또는 영어로 일관성 확인.
