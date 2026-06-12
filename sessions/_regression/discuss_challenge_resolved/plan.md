# Plan — 이벤트 버스 재설계

## 합의
- 직접 호출 + outbox 테이블 재시도 채택 (ref: chat.jsonl#L2) (ref: chat.jsonl#L4)

## 지금 실행
- [ ] outbox 테이블 + 재시도 워커 구현 (ref: chat.jsonl#L3) (ref: chat.jsonl#L4)
  - 검증: pytest tests/test_outbox.py
