[Trading Mission — 장전 {{DATE_KST}}]

## 컨텍스트 (읽기 전용, 수정 금지)
- freshness: `artifacts/market_snapshot.json` → `freshness` 블록
- overlay signals: `artifacts/market_snapshot.json` → `overlay_signals`
- PASS cards: `artifacts/market_snapshot.json` → `eligible_cards`
- portfolio: `artifacts/market_snapshot.json` → `portfolio`
- kill switch: `artifacts/market_snapshot.json` → `kill_switch`

## 미션
1. 데이터가 trade 가능한지 판정 (`freshness.blocking`이면 proposal 0건 + 사유만)
2. 활성 PASS 전략·overlay 신호와 포트폴리오 정합성 검토
3. 오늘 Human approval 대상 **TradeProposal 후보** 최대 {{MAX_PROPOSALS}}건 합의
4. 각 proposal: symbol, side, notional, thesis, backtest_ref, data_sources, confidence
5. 장중 thin agent용 playbook 요약 합의

## 산출 (Scribe / 합의)
- plan.md `## 합의`에 `ingest_ready: true|false`, `blocking_reason`, `active_strategies`
- proposal 초안은 `artifacts/proposals_draft.json` 형식으로 Codex가 검증 가능하면 기록
- playbook은 `artifacts/playbook.md`에 「오늘 장중 행동」섹션

## 비목표
- 주문 실행·KIS write·LIVE arm
- full notebook ingest·`*_full.json` 전체 read
- 3라운드 이상 무한 토론
