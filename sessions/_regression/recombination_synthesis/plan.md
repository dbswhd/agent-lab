# Plan — 수집 파이프라인 아키텍처

## 합의
- 배치 집계 + 핵심 지표 3종 경량 스트림 분리 (ref: chat.jsonl#L2) (ref: chat.jsonl#L3)

## 지금 실행
- [ ] 핵심 지표 스트림 경로 분리 구현 (ref: chat.jsonl#L3) (ref: chat.jsonl#L4)
  - 검증: pytest tests/test_pipeline.py
