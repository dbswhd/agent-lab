# Plan — 세션 캐시 전략

## 합의
- sqlite WAL + TTL 인덱스 캐시 채택 (ref: chat.jsonl#L2) (ref: chat.jsonl#L4)

## 지금 실행
- [ ] WAL 모드 + TTL 인덱스 구현 (ref: chat.jsonl#L3) (ref: chat.jsonl#L4)
  - 검증: pytest tests/test_cache.py
