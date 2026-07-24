<!-- plan-path: artifacts/plans/word-freq-cli.md -->

## TL;DR
> Summary: `scratch/word_freq/`에 공백 기준 단어 빈도 집계 CLI(`word_freq.py`)와 pytest 테스트를 구현했으며, 3개 에이전트 모두 ENDORSE 완료.
> Deliverables:
> - `scratch/word_freq/word_freq.py` — CLI 본체
> - `scratch/word_freq/test_word_freq.py` — pytest 테스트
> Risk: Low — 외부 의존성 없는 stdlib 구현

## Must
- `python word_freq.py <file>` 실행 시 상위 10개 단어·빈도 출력
- `-n N` 플래그로 출력 개수 조정 가능
- 파일 없음 → stderr + exit 1, 빈 파일 → 빈 결과 또는 명시적 메시지
- pytest 전체 통과

## Must-NOT
- `src/agent_lab/` 코어 코드 변경 없음 (scratch 전용 구현)
- 외부 라이브러리(`nltk`, `spacy` 등) 의존 금지 — stdlib `collections.Counter`만 사용
- sessions/* 커밋 금지

## Parallel waves
Wave 1 (no deps): `word_freq.py` 구현 + `test_word_freq.py` 작성 (동시 가능)
Wave 2 (after Wave 1): pytest 실행 → 통과 확인

## Evidence paths
- `scratch/word_freq/word_freq.py`
- `scratch/word_freq/test_word_freq.py`

---

## 지금 논의 중인 것

`scratch/word_freq/` 폴더에 단어 빈도 CLI 구현이 완료된 상태. 요구사항은 (1) 공백 기준 토큰화·소문자 정규화, (2) 상위 N개 출력(기본 10), (3) 파일 없음/빈 파일 예외처리, (4) pytest 테스트였다. Claude가 구현을 완료했고 Codex·Cursor 모두 ENDORSE했다. (ref: chat.jsonl#L2, chat.jsonl#L3, chat.jsonl#L4)

## 합의된 점

3개 에이전트가 구현 완료에 동의했다. CLI 인터페이스는 `python word_freq.py <file> [-n N]`, 파일 없음 시 stderr + exit 1로 확정됐다. (ref: chat.jsonl#L2, chat.jsonl#L4)

## 쟁점 / 미결정

Codex가 파일 경로·테스트 결과를 독립 확인하겠다고 선언했으나, 실제 pytest 실행 로그가 아직 공유되지 않았다. pytest 전체 통과 여부를 실증하는 터미널 출력이 아직 없다. (ref: chat.jsonl#L3)

## 에이전트별 핵심

**Claude** (L2): `word_freq.py` 구현 완료 — `python word_freq.py <file> [-n N]`, 파일 없음 → stderr + exit 1.
**Codex** (L3): Claude 완료 주장에 대해 파일·테스트 독립 확인 후 ENDORSE 선언.
**Cursor** (L4): chat.jsonl#L1 기준 ENDORSE.

---

## 지금 실행

1.
   - 무엇을: pytest를 실행해 `test_word_freq.py` 전체 통과 여부를 실증한다.
   - 어디서: `scratch/word_freq/`
   - 검증: pytest 출력에서 `passed` 결과 확인; 실패 시 `scratch/word_freq/test_word_freq.py` 수정.

## 실행 순서 (이후)

2.
   - 무엇을: CLI smoke test — 실제 텍스트 파일로 `python word_freq.py` 수동 실행, `-n 5` 플래그 및 존재하지 않는 파일 경로 오류 경로 검증.
   - 어디서: `scratch/word_freq/word_freq.py`
   - 검증: stdout에 순위별 단어·빈도 출력; 파일 없음 시 exit code 1.

3. 완료 후 Human이 `#done` 또는 추가 요구사항 없으면 `scratch/word_freq/` 그대로 유지 (sessions/* 커밋 금지 규칙 준수). (ref: chat.jsonl#L3)
