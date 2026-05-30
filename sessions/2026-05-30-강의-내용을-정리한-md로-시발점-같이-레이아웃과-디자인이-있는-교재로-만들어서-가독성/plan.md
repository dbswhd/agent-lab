## 지금 논의 중인 것

- 강의 md/PDF를 “시발점” 교재처럼 읽히도록 Theme 사이드 레일, 색, 여백, 절 전환, 예제/연습 구조를 계속 피드백하며 다듬는 중이다. (ref: chat.jsonl#L126, chat.jsonl#L206)
- 최신 초점은 레이아웃 핀포인트보다 내용 가독성으로 이동했다: OCR 28건, 빈 풀이 18건, md 안 유령 연습 블록, 수식 렌더링/줄바꿈 규칙이 남아 있다. (ref: chat.jsonl#L209, chat.jsonl#L210)
- 작업 위치는 `/Users/yoonjong/Desktop/강의 스크립트/공수 기말 범위/book/`이고 주요 파일은 `build.mjs`, `lecture.css`, 산출물은 `공수1_기말학습자료.pdf`다. (ref: chat.jsonl#L189, chat.jsonl#L202)

## 합의된 점

- Theme 사이드바는 채움 배경 `#e8f2fc`, 메인 파랑 `#1a5fcc`, PDF 인쇄 색 유지까지 적용된 상태로 본다. (ref: chat.jsonl#L141, chat.jsonl#L142)
- 과한 페이지 여백은 피해야 하며, `break-inside/page-break-inside`류 잠금을 줄이고 PDF 마진도 줄여서 큰 하단 공백을 완화했다. (ref: chat.jsonl#L146, chat.jsonl#L149, chat.jsonl#L156)
- 절이 한 페이지의 반 정도를 채우면 다음 절을 굳이 같은 페이지에 붙이지 않는 방향으로 정했다. (ref: chat.jsonl#L192, chat.jsonl#L194)
- 현재 구현은 `§10.7`에만 `theme-force-break`를 적용해 15p에는 `§10.6`, 16p에는 `§10.7`이 시작되도록 했다. inline 구분선 코드는 제거됐다. (ref: chat.jsonl#L200, chat.jsonl#L202)
- `9.2 → 9.3`은 이미 페이지가 분리되어 있으므로 강제로 이어붙이거나 추가 break를 넣지 않는다. (ref: chat.jsonl#L179, chat.jsonl#L182)

## 쟁점 / 미결정

- 15p의 `§10.6` 단독 페이지가 “반 정도 차서 자연스러운지”는 Human 눈검수 OK/NG가 아직 남아 있다. (ref: chat.jsonl#L203, chat.jsonl#L204)
- 16p에서 `§10.7`과 `§10.8`이 함께 이어지는 밀도가 답답한지도 추가 확인 대상이다. (ref: chat.jsonl#L202, chat.jsonl#L203)
- OCR 28건, 빈 풀이 18건, md 유령 연습 블록은 아직 본격 보정 전이다. (ref: chat.jsonl#L156, chat.jsonl#L210)
- 수식이 길어질 때 줄바꿈/정렬 규칙이 아직 문서화되지 않았다. (ref: chat.jsonl#L209)

## 에이전트별 핵심

- Cursor: 실제 파일 상태를 확인하며 Theme 채움, 여백, `§10.7` break 적용 상태와 남은 OCR/빈 풀이/md 유령 문제를 추적했다. (ref: chat.jsonl#L142, chat.jsonl#L200, chat.jsonl#L210)
- Codex: `build.mjs`/`lecture.css` 수정과 재빌드를 수행했고, `§10.7` page-break 및 inline 구분선 제거 상태를 확인했다. (ref: chat.jsonl#L190, chat.jsonl#L202)
- Claude: CSS/PDF 인쇄 리스크, 비교본 문제, 16p 밀도, 수식/OCR/교재 기본기 검수 누락을 지적했다. (ref: chat.jsonl#L152, chat.jsonl#L205, chat.jsonl#L209)

## 다음에 할 일

1.
   - 무엇을: 현재 PDF에서 15p `§10.6` 단독 페이지와 16p `§10.7/§10.8` 밀도를 눈검수한다. (ref: chat.jsonl#L203, chat.jsonl#L204)
   - 어디서: `공수1_기말학습자료.pdf` 15p, 16p. (ref: chat.jsonl#L202, chat.jsonl#L204)
   - 검증: 15p가 과하게 휑하지 않고, 16p가 답답하지 않으면 OK; 아니면 `§10.7`/`§10.8` 분리 재조정. (ref: chat.jsonl#L203, chat.jsonl#L205)

2.
   - 무엇을: `9.2 → 9.3` 분리 유지와 §9.3·연습 시작부 하단 여백을 회귀 확인한다. (ref: chat.jsonl#L200, chat.jsonl#L203)
   - 어디서: `공수1_기말학습자료.pdf` 3→4p, §9.3, 연습 시작부. (ref: chat.jsonl#L200, chat.jsonl#L203)
   - 검증: `9.2 → 9.3`이 계속 분리되고 하단 공백이 과하지 않으면 통과. (ref: chat.jsonl#L182, chat.jsonl#L203)

3.
   - 무엇을: `§9.2 Ex.2`를 기준 샘플로 OCR/수식 보정 파이프라인을 확정한다. (ref: chat.jsonl#L132, chat.jsonl#L210)
   - 어디서: `lecturenote_exercises.json`, `extract_lecturenote.py`, PDF `§9.2 Ex.2`. (ref: chat.jsonl#L130, chat.jsonl#L142)
   - 검증: 원본 PDF와 수식 의미가 맞고 OCR 노트 없이 읽히면 통과. (ref: chat.jsonl#L132, chat.jsonl#L142)

4.
   - 무엇을: OCR 28건 수식화와 빈 풀이 18건 처리를 진행한다. (ref: chat.jsonl#L156, chat.jsonl#L210)
   - 어디서: `lecturenote_exercises.json`, LectureNote 원본 PDF. (ref: chat.jsonl#L130, chat.jsonl#L210)
   - 검증: OCR 보정 필요 노트가 사라지고, 빈 풀이는 원문 보완 또는 “풀이 없음” 축약으로 일관 처리된다. (ref: chat.jsonl#L128, chat.jsonl#L210)

5.
   - 무엇을: md 안 한국어 `### 연습 문제` 유령 블록을 빌드 혼란이 없도록 정리한다. (ref: chat.jsonl#L130, chat.jsonl#L210)
   - 어디서: `공수(1)…복사본.md`의 연습 블록. (ref: chat.jsonl#L130, chat.jsonl#L148)
   - 검증: PDF 연습문제가 JSON 기준으로만 들어가고 md 수정과 PDF 결과가 엇갈리지 않으면 통과. (ref: chat.jsonl#L131, chat.jsonl#L210)

6.
   - 무엇을: “절이 페이지 반 정도를 채우면 다음 절을 굳이 붙이지 않는다”는 레이아웃 룰을 코드 옆에 짧게 남긴다. (ref: chat.jsonl#L192, chat.jsonl#L203)
   - 어디서: `build.mjs` 관련 절 배치 로직 근처. (ref: chat.jsonl#L203, chat.jsonl#L205)
   - 검증: 이후 절 추가/수정 때 같은 룰을 보고 회귀하지 않으면 통과. (ref: chat.jsonl#L205)

7. Human이 현재 PDF 15p/16p를 보고 OK면 레이아웃은 마감하고, NG면 page-break 유지 여부를 다시 결정한다. (ref: chat.jsonl#L204, chat.jsonl#L205)
