<!-- plan-path: artifacts/plans/x2-lift-typo-fix.md -->

## TL;DR
> Summary: `docs/_dogfood/x2-lift.md` L17의 `roompy에서` → `room.py에서` 오타 1건을 수정하고, dry-run → Human 승인 → merge → Oracle PASS 순으로 완주한다.
> Deliverables:
> - L17 단일 라인 패치 (main 병합)
> - Oracle grep PASS (`room.py에서` 존재 + L17 `roompy에서` 부재)
> Risk: Low — 단일 파일 단일 행; L5·L11·L13(의도적 `roompy`) 불변이 유일한 가드레일.

## Must
- L17 `roompy에서` → `room.py에서` 정확히 1건만 교체
- Human gate 통과 후에만 commit/merge 실행
- Oracle grep PASS 증거 확인 후 완료 처리

## Must-NOT
- L5·L11·L13 (세션 슬러그·의도적 마커) 수정 금지
- execute gate 우회 금지
- 기능 코드(`.py`, `.tsx`) 변경 금지

## Parallel waves
Wave 1 (no deps): dry-run diff 출력 + `grep -n "roompy"` 사전 상태 확인
Wave 2 (after Wave 1 + Human 승인): Edit 적용 → git commit → Oracle PASS

## Evidence paths
- `docs/_dogfood/x2-lift.md`
- `artifacts/plans/x2-lift-typo-fix.md`

---

## 지금 논의 중인 것

`docs/_dogfood/x2-lift.md` L17 Evidence row의 `roompy에서` 오타를 `room.py에서`로 교체하는 1행 수정이다. Claude가 변경 범위를 L17 단 1곳으로 한정하고 L5·L11·L13의 `roompy`는 세션 슬러그이므로 보존 대상임을 확인했다. Codex가 Human gate 이전에 독립 dry-run 확인을 먼저 고정하는 AMEND를 제안했다. (ref: chat.jsonl#L3, chat.jsonl#L4)

## 합의된 점

수정 대상 L17 단 1곳, 보존 대상 L5·L11·L13. Oracle 검증은 grep 기반 (`room.py에서` 존재 + `roompy에서` 부재). dry-run diff로 1행 범위를 시각 확인한 뒤 Human 승인 → commit → merge 순으로 진행한다. (ref: chat.jsonl#L2, chat.jsonl#L3, chat.jsonl#L4)

## 쟁점 / 미결정

Oracle PASS 판정이 grep 단독인지 `python scripts/smoke_room.py` 연동인지 아직 명시되지 않았다. merge 방식(직접 커밋 vs PR)도 Human gate에서 최종 결정 예정. (ref: chat.jsonl#L4)

## 에이전트별 핵심

**Cursor:** Agent Lab 3-agent room 참여; dry-run 결과 기준점 및 작업 컨텍스트 설정. (ref: chat.jsonl#L2)
**Claude:** L17 단 1행 변경 범위 확정, L5·L11·L13 보존 가드레일 정의. (ref: chat.jsonl#L3)
**Codex:** Human gate 이전 독립 확인 순서 고정 AMEND; 승인 후에만 execute 진행하도록 워크플로우 앵커. (ref: chat.jsonl#L4)

## 에이전트별 기여 (자동)

- **Cursor** (L2): I am acting as Cursor in Agent Lab's 3-agent room.
- **Claude** (L3): `docs/_dogfood/x2-lift.md` before 상태 확인; L17 단 1곳(`roompy에서` → `room.py에서`) 변경; L5·L11·L13의 `roompy`는 의도적으로 그대로 유지.
- **Codex** (L4): AMEND — Cursor/Claude의 dry-run 결과 기준, 승인 후 검증 순서를 최소 단위로 고정; Human gate 이후에만 실행.

---

## 지금 실행

1.
   - 무엇을: `docs/_dogfood/x2-lift.md`에서 L17 `roompy에서` → `room.py에서` 변경 diff를 dry-run으로 출력한다 (파일 저장 전).
   - 어디서: `docs/_dogfood/x2-lift.md`
   - 검증: diff 출력이 정확히 1라인(L17)이고, `grep -n "roompy" docs/_dogfood/x2-lift.md`에서 L17이 제거되어 L5·L11·L13만 남으면 Human 육안 PASS.
   (ref: chat.jsonl#L3)

## 실행 순서 (이후)

2. Human `#approve` 수신 전까지 Edit·commit·merge 전면 보류. (ref: chat.jsonl#L4)

3.
   - 무엇을: 승인 후 L17 오타를 Edit으로 실제 적용한다.
   - 어디서: `docs/_dogfood/x2-lift.md`
   - 검증: `git diff docs/_dogfood/x2-lift.md` 출력이 1행 변경만 포함.
   (ref: chat.jsonl#L3)

4.
   - 무엇을: `docs(_dogfood): fix typo roompy→room.py in x2-lift` 메시지로 커밋한다.
   - 어디서: `docs/_dogfood/x2-lift.md`
   - 검증: `git log --oneline -1` 커밋 메시지 확인.
   (ref: chat.jsonl#L4)

5.
   - 무엇을: Oracle grep 검증 실행 — `room.py에서` 존재 + L17 `roompy에서` 부재.
   - 어디서: `docs/_dogfood/x2-lift.md`
   - 검증: 두 grep 모두 기대값 반환 시 Oracle PASS 선언.
   (ref: chat.jsonl#L3)

6. Oracle PASS 이후 `make x2-lift-dogfood-prepare` 리셋 타이밍 Human 재확인 — 다음 패스 준비는 이 단계 이후에만 진행. (ref: chat.jsonl#L2, chat.jsonl#L4)
